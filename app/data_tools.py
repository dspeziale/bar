"""Strumenti sui dati: carico mensile di prova, reset totale, backup e restore.

Tre procedure distinte, tutte destinate al solo super admin:

  * genera_carico()  crea dati realistici su un mese intero, annotando ogni riga
                     creata in modo che l'operazione sia annullabile;
  * reset_totale()   svuota tutte le tabelle e ricrea i dati di base;
  * esporta_backup() / importa_backup()  copia integrale del database in JSON,
                     indipendente dal motore (SQLite in locale, PostgreSQL in
                     produzione).

Vincolo da rispettare (vedi CLAUDE.md): in produzione il pool ha una sola
connessione. Dove serve una connessione esplicita si chiama prima
`db.session.remove()`, e non si mescolano mai sessione ORM e connessione aperta.
"""

import json
import random
import secrets
from calendar import monthrange
from datetime import date, datetime, timedelta

from app import db

# Intervalli predefiniti: quante righe al giorno per ciascuna categoria.
INTERVALLI_DEFAULT = {
    'pasti':   (20, 50),
    'snack':   (10, 20),
    'caffe':   (80, 120),
    'builder': (10, 20),
}

# Chiavi in AppSetting che rendono gli intervalli modificabili dall'interfaccia.
CHIAVI_INTERVALLI = {
    'pasti':   ('sim_pasti_min',   'sim_pasti_max'),
    'snack':   ('sim_snack_min',   'sim_snack_max'),
    'caffe':   ('sim_caffe_min',   'sim_caffe_max'),
    'builder': ('sim_builder_min', 'sim_builder_max'),
}

_CHUNK = 400            # righe per istruzione, per non gonfiare le query
_PREFISSO_CODICE = 'SIM'


# ═══════════════════════════════════════════════════════════════════════════
#  Intervalli configurati
# ═══════════════════════════════════════════════════════════════════════════

def leggi_intervalli():
    """Intervalli correnti letti dalle impostazioni, con i default come rete."""
    from app.notifications import get_numeric_setting

    out = {}
    for cat, (k_min, k_max) in CHIAVI_INTERVALLI.items():
        d_min, d_max = INTERVALLI_DEFAULT[cat]
        v_min = max(0, get_numeric_setting(k_min, d_min))
        v_max = max(v_min, get_numeric_setting(k_max, d_max))
        out[cat] = (int(v_min), int(v_max))
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Generazione del carico mensile
# ═══════════════════════════════════════════════════════════════════════════

class DatiInsufficienti(Exception):
    """Il catalogo non basta per generare: il messaggio elenca cosa manca."""


def _prodotti_per_parola(prodotti, parole):
    scelti = [p for p in prodotti
              if any(w in (p.name or '').lower() for w in parole)]
    return scelti


def verifica_prerequisiti(tenant_id):
    """Cosa manca per poter generare. Ritorna una lista di messaggi."""
    from app.models import (User, Product, TimeSlot, CorporateAccount,
                            CorporateMembership, Ingredient, BancoItem)

    mancanti = []

    clienti = User.query.filter_by(is_client=True, is_active=True,
                                   tenant_id=tenant_id).count()
    if clienti < 1:
        mancanti.append('nessun cliente attivo: servono clienti a cui '
                        'attribuire ordini e prenotazioni')

    prodotti = Product.query.filter_by(is_active=True, tenant_id=tenant_id).all()
    if not prodotti:
        mancanti.append('nessun prodotto attivo in listino')
    else:
        if not _prodotti_per_parola(prodotti, ('panin', 'tramezz', 'toast')):
            mancanti.append('nessun panino o tramezzino in listino '
                            '(serve per gli ordini del banco)')
        if not _prodotti_per_parola(prodotti, ('acqua', 'bibita', 'succo',
                                               'birra', 'bevand', 'lattina')):
            mancanti.append('nessuna bevanda in listino')

    if TimeSlot.query.filter_by(is_active=True, tenant_id=tenant_id).count() < 1:
        mancanti.append('nessuno slot di ritiro attivo')

    if BancoItem.query.filter_by(is_active=True, tenant_id=tenant_id).count() < 1:
        mancanti.append('nessun articolo del banco (servono per i caffe)')

    corp = (CorporateAccount.query
            .filter_by(is_active=True, tenant_id=tenant_id).all())
    if not corp:
        mancanti.append('nessuna convenzione aziendale attiva')
    else:
        soci = sum(CorporateMembership.query
                   .filter_by(corporate_id=c.id, is_active=True).count()
                   for c in corp)
        if soci < 1:
            mancanti.append('nessun dipendente associato a una convenzione')

    if Ingredient.query.filter_by(is_active=True, tenant_id=tenant_id).count() < 3:
        mancanti.append('meno di 3 ingredienti attivi per il builder')

    return mancanti


def genera_carico(anno, mese, tenant_id, utente_id=None,
                  intervalli=None, solo_lavorativi=True):
    """Crea i dati di un mese intero e restituisce il CaricoMensile.

    Non tocca i saldi dei portafogli e non crea movimenti di wallet: registra
    le vendite, che sono cio' che alimenta report e calcolo del canone. In
    questo modo l'eliminazione del carico e' un annullamento completo.
    """
    from app.models import (CaricoMensile, CaricoMensileRiga, User, Product,
                            TimeSlot, Order, OrderItem, CustomOrderItem,
                            CustomOrderItemIngredient, Ingredient, BancoItem,
                            BancoSession, CorporateAccount, CorporateMembership,
                            DailyFixedMeal, CorporateMealBooking)

    mancanti = verifica_prerequisiti(tenant_id)
    if mancanti:
        raise DatiInsufficienti('; '.join(mancanti))

    if intervalli is None:
        intervalli = leggi_intervalli()

    rng = random.Random(f'{anno}-{mese:02d}-{tenant_id}')

    clienti = User.query.filter_by(is_client=True, is_active=True,
                                   tenant_id=tenant_id).all()
    prodotti = Product.query.filter_by(is_active=True, tenant_id=tenant_id).all()
    panini = _prodotti_per_parola(prodotti, ('panin', 'tramezz', 'toast'))
    bevande = _prodotti_per_parola(prodotti, ('acqua', 'bibita', 'succo',
                                              'birra', 'bevand', 'lattina'))
    slots = TimeSlot.query.filter_by(is_active=True, tenant_id=tenant_id).all()
    caffe_items = [b for b in BancoItem.query.filter_by(
        is_active=True, tenant_id=tenant_id).all()
        if any(w in (b.name or '').lower() for w in
               ('caffe', 'caffè', 'cappuccin', 'macchiat', 'orzo', 'te '))] or \
        BancoItem.query.filter_by(is_active=True, tenant_id=tenant_id).all()
    ingredienti = Ingredient.query.filter_by(is_active=True,
                                             tenant_id=tenant_id).all()
    corporate = CorporateAccount.query.filter_by(is_active=True,
                                                 tenant_id=tenant_id).first()
    soci = [m.user for m in CorporateMembership.query.filter_by(
        corporate_id=corporate.id, is_active=True).all() if m.user]
    staff = (User.query.filter_by(tenant_id=tenant_id, is_client=False).first()
             or clienti[0])

    carico = CaricoMensile(anno=anno, mese=mese, tenant_id=tenant_id,
                           creato_da=utente_id,
                           parametri=json.dumps({
                               'intervalli': {k: list(v) for k, v in intervalli.items()},
                               'solo_lavorativi': bool(solo_lavorativi),
                           }))
    db.session.add(carico)
    db.session.flush()

    registro = []          # (entita, riga_id) nell'ordine di creazione
    tot = {'pasti': 0, 'snack': 0, 'caffe': 0, 'builder': 0}
    incasso = 0.0
    giorni_generati = 0

    def annota(oggetto):
        registro.append((oggetto.__tablename__, oggetto.id))

    ultimo = monthrange(anno, mese)[1]
    for giorno in range(1, ultimo + 1):
        d = date(anno, mese, giorno)
        if solo_lavorativi and d.weekday() >= 5:
            continue
        giorni_generati += 1

        # ── Pasti aziendali: un menu del giorno e N prenotazioni ──────────
        n_pasti = rng.randint(*intervalli['pasti'])
        n_pasti = min(n_pasti, len(soci))       # vincolo: un socio, una prenotazione
        if n_pasti > 0:
            prezzo = round(corporate.daily_price or 7.0, 2)
            meal = DailyFixedMeal(
                meal_date=d, name=f'Menu del giorno {d.strftime("%d/%m")}',
                price=prezzo, corporate_id=corporate.id,
                max_bookings=max(n_pasti, corporate.max_daily_covers or n_pasti),
                is_active=True, tenant_id=tenant_id,
                primo='Primo del giorno', secondo='Secondo del giorno',
                contorno='Contorno', bevanda='Acqua', caffe='Caffe',
            )
            db.session.add(meal)
            db.session.flush()
            annota(meal)
            for u in rng.sample(soci, n_pasti):
                b = CorporateMealBooking(
                    user_id=u.id, meal_id=meal.id,
                    slot_id=rng.choice(slots).id, quantity=1,
                    status='consumed',
                    created_at=datetime.combine(d, datetime.min.time()),
                    pickup_token=secrets.token_hex(3).upper(),
                )
                db.session.add(b)
                db.session.flush()
                annota(b)
                tot['pasti'] += 1
                incasso += prezzo

        # ── Ordini panino/tramezzino + bevanda ────────────────────────────
        for _ in range(rng.randint(*intervalli['snack'])):
            cliente = rng.choice(clienti)
            slot = rng.choice(slots)
            righe = [(rng.choice(panini), 1)]
            if bevande and rng.random() < 0.75:
                righe.append((rng.choice(bevande), 1))
            totale = round(sum(p.price * q for p, q in righe), 2)
            o = Order(user_id=cliente.id, slot_id=slot.id, order_date=d,
                      status='completed', total_price=totale,
                      tenant_id=tenant_id, reminder_sent=True,
                      created_at=datetime.combine(d, datetime.min.time()),
                      notes='')
            db.session.add(o)
            db.session.flush()
            o.order_code = f'{_PREFISSO_CODICE}-{d.strftime("%y%m%d")}-{o.id:05d}'
            annota(o)
            for prod, q in righe:
                it = OrderItem(order_id=o.id, product_id=prod.id,
                               quantity=q, unit_price=prod.price)
                db.session.add(it)
                db.session.flush()
                annota(it)
            tot['snack'] += 1
            incasso += totale

        # ── Caffe al banco: sessioni QR pagate, 1-3 caffe ciascuna ────────
        da_fare = rng.randint(*intervalli['caffe'])
        while da_fare > 0:
            quante = min(da_fare, rng.randint(1, 3))
            da_fare -= quante
            voci, totale = [], 0.0
            for _ in range(quante):
                art = rng.choice(caffe_items)
                voci.append({'name': art.name, 'qty': 1, 'price': art.price})
                totale += art.price
            totale = round(totale, 2)
            creato = datetime.combine(d, datetime.min.time()) + timedelta(
                hours=rng.randint(7, 17), minutes=rng.randint(0, 59))
            s = BancoSession(
                token=secrets.token_urlsafe(12)[:24], staff_id=staff.id,
                customer_id=rng.choice(clienti).id,
                items_json=json.dumps(voci), total=totale, status='paid',
                created_at=creato, expires_at=creato + timedelta(minutes=10),
                tenant_id=tenant_id,
            )
            db.session.add(s)
            db.session.flush()
            annota(s)
            tot['caffe'] += quante
            incasso += totale

        # ── Prodotti del builder ─────────────────────────────────────────
        for _ in range(rng.randint(*intervalli['builder'])):
            cliente = rng.choice(clienti)
            slot = rng.choice(slots)
            tipo = rng.choice(('panino', 'insalata', 'poke'))
            scelti = rng.sample(ingredienti, min(len(ingredienti),
                                                 rng.randint(3, 6)))
            extra = round(sum(i.price_extra or 0 for i in scelti), 2)
            base = {'panino': 3.50, 'insalata': 3.00, 'poke': 4.00}[tipo]
            totale = round(base + extra, 2)
            o = Order(user_id=cliente.id, slot_id=slot.id, order_date=d,
                      status='completed', total_price=totale,
                      tenant_id=tenant_id, reminder_sent=True,
                      created_at=datetime.combine(d, datetime.min.time()),
                      notes='')
            db.session.add(o)
            db.session.flush()
            o.order_code = f'{_PREFISSO_CODICE}-{d.strftime("%y%m%d")}-{o.id:05d}'
            annota(o)
            coi = CustomOrderItem(
                order_id=o.id, builder_type=tipo, unit_price=totale, quantity=1,
                grill_requested=(tipo == 'panino' and rng.random() < 0.3),
                label=f'{tipo.capitalize()} personalizzato: '
                      + ', '.join(i.name for i in scelti),
            )
            db.session.add(coi)
            db.session.flush()
            annota(coi)
            for ing in scelti:
                ci = CustomOrderItemIngredient(
                    custom_item_id=coi.id, ingredient_name=ing.name,
                    price_extra=ing.price_extra or 0.0)
                db.session.add(ci)
                db.session.flush()
                annota(ci)
            tot['builder'] += 1
            incasso += totale

    carico.giorni = giorni_generati
    carico.n_pasti = tot['pasti']
    carico.n_snack = tot['snack']
    carico.n_caffe = tot['caffe']
    carico.n_builder = tot['builder']
    carico.incasso = round(incasso, 2)

    # Registro in blocco: una sola istruzione ogni _CHUNK righe
    for i in range(0, len(registro), _CHUNK):
        db.session.bulk_save_objects([
            CaricoMensileRiga(carico_id=carico.id, entita=e, riga_id=rid)
            for e, rid in registro[i:i + _CHUNK]
        ])

    db.session.commit()
    return carico


def elimina_carico(carico):
    """Cancella tutte le righe di un carico, in ordine inverso di dipendenza."""
    per_entita = {}
    for r in carico.righe:
        per_entita.setdefault(r.entita, []).append(r.riga_id)

    eliminate = 0
    for tabella in reversed(db.metadata.sorted_tables):
        ids = per_entita.get(tabella.name)
        if not ids:
            continue
        for i in range(0, len(ids), _CHUNK):
            blocco = ids[i:i + _CHUNK]
            res = db.session.execute(
                tabella.delete().where(tabella.c.id.in_(blocco)))
            eliminate += res.rowcount or 0

    db.session.delete(carico)      # la cascata rimuove il registro
    db.session.commit()
    return eliminate


# ═══════════════════════════════════════════════════════════════════════════
#  Reset totale
# ═══════════════════════════════════════════════════════════════════════════

def reset_totale():
    """Svuota ogni tabella e ricrea i dati di base.

    Diversamente dal reset parziale della pagina Manutenzione, qui non resta
    nulla: utenti, catalogo, convenzioni, impostazioni, etichette, prenotazioni.
    Subito dopo viene rieseguito il seed, che ricrea permessi, ruoli, super
    admin, categorie, slot, tavoli, articoli del banco e impostazioni.
    """
    from app import _seed_defaults

    # Nessuna sessione ORM aperta mentre si usa una connessione esplicita:
    # in produzione il pool ha una sola connessione.
    db.session.remove()
    svuotate = 0
    with db.engine.begin() as conn:
        for tabella in reversed(db.metadata.sorted_tables):
            res = conn.execute(tabella.delete())
            svuotate += res.rowcount or 0

    _seed_defaults()
    return svuotate


# ═══════════════════════════════════════════════════════════════════════════
#  Backup e restore
# ═══════════════════════════════════════════════════════════════════════════

VERSIONE_BACKUP = 1


def _serializza(valore):
    if isinstance(valore, datetime):
        return valore.isoformat(sep=' ')
    if isinstance(valore, date):
        return valore.isoformat()
    return valore


def _deserializza(tabella, riga):
    """Riporta le stringhe ISO al tipo della colonna (necessario su PostgreSQL)."""
    from sqlalchemy import Date, DateTime

    out = {}
    for nome, valore in riga.items():
        col = tabella.c.get(nome)
        if col is None:
            continue                      # colonna non piu' esistente: ignorata
        if isinstance(valore, str) and valore:
            if isinstance(col.type, DateTime):
                valore = datetime.fromisoformat(valore)
            elif isinstance(col.type, Date):
                valore = date.fromisoformat(valore)
        out[nome] = valore
    return out


def esporta_backup():
    """Copia integrale del database come dizionario JSON-serializzabile."""
    db.session.remove()
    dati = {
        'versione': VERSIONE_BACKUP,
        'creato_il': datetime.utcnow().isoformat(sep=' '),
        'motore': db.engine.dialect.name,
        'tabelle': {},
    }
    with db.engine.connect() as conn:
        for tabella in db.metadata.sorted_tables:
            righe = []
            for r in conn.execute(tabella.select()):
                righe.append({k: _serializza(v) for k, v in r._mapping.items()})
            dati['tabelle'][tabella.name] = righe
    return dati


def _sistema_sequenze():
    """Su PostgreSQL riallinea le sequenze dopo un inserimento con id espliciti."""
    if db.engine.dialect.name != 'postgresql':
        return
    from sqlalchemy import text
    with db.engine.begin() as conn:
        for tabella in db.metadata.sorted_tables:
            if 'id' not in tabella.c:
                continue
            conn.execute(text(
                "SELECT setval(pg_get_serial_sequence(:t, 'id'), "
                "COALESCE((SELECT MAX(id) FROM " + tabella.name + "), 1), true)"
            ), {'t': tabella.name})


def importa_backup(dati):
    """Sostituisce il contenuto del database con quello del backup."""
    if not isinstance(dati, dict) or 'tabelle' not in dati:
        raise ValueError('File non riconosciuto: manca la sezione "tabelle".')
    versione = dati.get('versione')
    if versione != VERSIONE_BACKUP:
        raise ValueError(
            f'Versione del backup non supportata ({versione!r}, '
            f'attesa {VERSIONE_BACKUP}).')

    tabelle = dati['tabelle']
    note = []
    ignorate = [n for n in tabelle
                if n not in {t.name for t in db.metadata.sorted_tables}]
    if ignorate:
        note.append('tabelle nel file ma non nel database, ignorate: '
                    + ', '.join(sorted(ignorate)))

    db.session.remove()
    inserite = 0
    with db.engine.begin() as conn:
        for tabella in reversed(db.metadata.sorted_tables):
            conn.execute(tabella.delete())
        for tabella in db.metadata.sorted_tables:
            righe = tabelle.get(tabella.name) or []
            if not righe:
                continue
            valori = [_deserializza(tabella, r) for r in righe]
            for i in range(0, len(valori), _CHUNK):
                conn.execute(tabella.insert(), valori[i:i + _CHUNK])
            inserite += len(valori)

    _sistema_sequenze()
    return inserite, note
