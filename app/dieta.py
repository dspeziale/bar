# -*- coding: utf-8 -*-
"""Dieta settimanale del cliente.

Quattro cose, tutte qui:

- compatibilità di un prodotto, un ingrediente o un pasto con le esigenze del
  cliente (allergeni esclusi e regime);
- fabbisogno calorico giornaliero e quota destinata al pranzo;
- consumo effettivo di una giornata, letto dagli ordini veri;
- compositore: costruisce il pranzo che si avvicina alla quota rispettando
  esclusioni, varietà nella settimana e budget, e con esso il piano
  settimanale.

I valori nutrizionali mancanti sono sconosciuti, non zero: un piatto senza
dati non entra nel piano e nel carrello viene contato a parte, così il
totale non mente per difetto.
"""
import random
from datetime import date, timedelta

from app import db
from app.models import (Product, Ingredient, Order, CorporateMealBooking,
                        DailyFixedMeal, DietPlan, DietPlanDay,
                        ALLERGEN_LABELS, OBIETTIVI_DIETA, ATTIVITA_DIETA,
                        GIORNI_SETTIMANA)

CHIAVI_GIORNI = [g for g, _n in GIORNI_SETTIMANA]

# Gli ingredienti hanno gli allergeni scritti a mano ("frutta a guscio",
# "uova, latte"): li si riporta alle chiavi di ALLERGENS.
_ALIAS_ALLERGENI = {
    'frutta a guscio': 'frutta_guscio', 'frutta_a_guscio': 'frutta_guscio',
    'noci': 'frutta_guscio', 'nocciole': 'frutta_guscio', 'mandorle': 'frutta_guscio',
    'latte e derivati': 'latte', 'lattosio': 'latte', 'latticini': 'latte',
    'formaggio': 'latte', 'uovo': 'uova', 'grano': 'glutine', 'frumento': 'glutine',
    'anidride solforosa': 'solfiti', 'anidride solforosa/solfiti': 'solfiti',
    'crostaceo': 'crostacei', 'mollusco': 'molluschi', 'arachide': 'arachidi',
}

# Che parte del pranzo può fare un prodotto, dal nome della sua categoria.
# Caffetteria, colazione, snack, gelati e alcolici restano fuori dal piano.
CATEGORIE_PRINCIPALE = {'Primi piatti', 'Secondi piatti', 'Panini', 'Tramezzini',
                        'Pizza e Focacce', 'Poke e Bowl', 'Insalate'}
CATEGORIE_CONTORNO = {'Contorni'}
CATEGORIE_CHIUSURA = {'Frutta', 'Yogurt', 'Dolci'}
CATEGORIE_BEVANDA = {'Bevande', 'Succhi e Bibite'}
KCAL_MINIME_PRINCIPALE = 250      # sotto, un piatto "principale" è in realtà un contorno


# ── Allergeni e compatibilità ───────────────────────────────────────────────

def chiavi_allergeni(testo):
    """'glutine,latte' oppure 'uova, latte' oppure 'frutta a guscio' → chiavi."""
    chiavi = []
    for pezzo in (testo or '').replace(';', ',').split(','):
        k = pezzo.strip().lower()
        if not k:
            continue
        k = _ALIAS_ALLERGENI.get(k, k.replace(' ', '_'))
        if k in ALLERGEN_LABELS and k not in chiavi:
            chiavi.append(k)
    return chiavi


def compatibilita(oggetto, profilo):
    """(ok, motivi): perché un prodotto, ingrediente o pasto non va bene.

    I motivi sono frasi brevi da mostrare accanto al nome: "contiene latte",
    "non indicato come vegetariano".
    """
    motivi = []
    esclusi = set(profilo.lista_esclusioni)
    presenti = set(chiavi_allergeni(getattr(oggetto, 'allergens', '')))
    for k in sorted(presenti & esclusi):
        motivi.append('contiene %s' % ALLERGEN_LABELS[k][0].lower())
    vegetariano = bool(getattr(oggetto, 'is_vegetarian', False)
                       or getattr(oggetto, 'is_vegan', False))
    vegano = bool(getattr(oggetto, 'is_vegan', False))
    if profilo.regime == 'vegetariano' and not vegetariano:
        motivi.append('non indicato come vegetariano')
    elif profilo.regime == 'vegano' and not vegano:
        motivi.append('non indicato come vegano')
    return (not motivi), motivi


def nutrienti(oggetto, quantita=1):
    """Kcal e macro di un oggetto per `quantita` porzioni. `noto` dice se il
    locale ha indicato i valori."""
    kcal = getattr(oggetto, 'kcal', None)
    q = quantita or 1

    def _v(nome):
        v = getattr(oggetto, nome, None)
        return round((v or 0.0) * q, 1)

    return {'kcal': int((kcal or 0) * q), 'proteine': _v('proteine_g'),
            'carboidrati': _v('carboidrati_g'), 'grassi': _v('grassi_g'),
            'noto': kcal is not None}


def _somma(totale, n):
    totale['kcal'] += n['kcal']
    totale['proteine'] = round(totale['proteine'] + n['proteine'], 1)
    totale['carboidrati'] = round(totale['carboidrati'] + n['carboidrati'], 1)
    totale['grassi'] = round(totale['grassi'] + n['grassi'], 1)
    if not n['noto']:
        totale['sconosciute'] += 1


def _totale_vuoto():
    return {'kcal': 0, 'proteine': 0.0, 'carboidrati': 0.0, 'grassi': 0.0,
            'sconosciute': 0}


# ── Fabbisogno ──────────────────────────────────────────────────────────────

def eta_anni(user, oggi=None):
    nascita = getattr(user, 'birth_date', None)
    if not nascita:
        return None
    oggi = oggi or date.today()
    anni = oggi.year - nascita.year
    if (oggi.month, oggi.day) < (nascita.month, nascita.day):
        anni -= 1
    return anni if 10 <= anni <= 110 else None


def fabbisogno(profilo, user):
    """Fabbisogno giornaliero e quota pranzo.

    Mifflin-St Jeor per il metabolismo basale, moltiplicato per il fattore di
    attività e corretto per l'obiettivo. Senza peso, altezza, sesso ed età si
    usa un valore medio e lo si dice: la stima è comunque utile, ma il cliente
    deve sapere che non è su misura.
    """
    fattore = dict((k, f) for k, _l, f in ATTIVITA_DIETA).get(profilo.attivita, 1.2)
    correzione = dict((k, c) for k, _l, c in OBIETTIVI_DIETA).get(profilo.obiettivo, 0.0)
    eta = eta_anni(user)
    esito = {'bmr': None, 'fattore': fattore, 'correzione': correzione,
             'eta': eta, 'stimato': False}

    if profilo.kcal_manuali:
        target = int(profilo.kcal_manuali)
        esito['spiegazione'] = 'Fabbisogno impostato da te.'
    elif profilo.peso_kg and profilo.altezza_cm and profilo.sesso in ('M', 'F') and eta:
        bmr = (10 * profilo.peso_kg + 6.25 * profilo.altezza_cm - 5 * eta
               + (5 if profilo.sesso == 'M' else -161))
        esito['bmr'] = int(round(bmr))
        target = int(round(bmr * fattore * (1 + correzione)))
        esito['spiegazione'] = (
            'Metabolismo basale %d kcal (peso, altezza, età e sesso), '
            'per attività %s = %d kcal al giorno%s.' % (
                esito['bmr'],
                dict((k, l) for k, l, _f in ATTIVITA_DIETA).get(
                    profilo.attivita, '').split(' (')[0].lower(),
                int(round(bmr * fattore)),
                (', ridotto del %d%% per perdere peso' % int(-correzione * 100)
                 if correzione < 0 else
                 (', aumentato del %d%% per la massa' % int(correzione * 100)
                  if correzione > 0 else ''))))
    else:
        base = {'M': 2500, 'F': 2000}.get(profilo.sesso, 2200)
        target = int(round(base * fattore / 1.2 * (1 + correzione)))
        esito['stimato'] = True
        esito['spiegazione'] = ('Valore medio: inserisci peso, altezza, sesso e '
                                'data di nascita per un calcolo su misura.')

    target = max(1200, min(4500, target))
    esito['target'] = target
    esito['quota'] = profilo.quota_pranzo or 0.40
    esito['pranzo'] = int(round(target * esito['quota']))
    return esito


# ── Consumo del giorno ──────────────────────────────────────────────────────

def _ingrediente_per_nome(nome, cache):
    if nome not in cache:
        cache[nome] = Ingredient.query.filter(Ingredient.name == nome).first()
    return cache[nome]


def nutrienti_composto(ingredienti, quantita=1, cache=None):
    """Kcal di un panino/insalata composto: somma degli ingredienti per nome.

    `ingredienti` è una lista di dict con 'name' (e 'id' se disponibile),
    come nel carrello e in CustomOrderItemIngredient.
    """
    cache = cache if cache is not None else {}
    tot = _totale_vuoto()
    noto_almeno_uno = False
    for ing in ingredienti:
        obj = None
        if isinstance(ing, dict):
            if ing.get('id'):
                obj = db.session.get(Ingredient, ing['id'])
            if obj is None:
                obj = _ingrediente_per_nome(ing.get('name', ''), cache)
        else:
            obj = _ingrediente_per_nome(getattr(ing, 'ingredient_name', ''), cache)
        if obj is None:
            continue
        n = nutrienti(obj, quantita)
        if n['noto']:
            noto_almeno_uno = True
        tot['kcal'] += n['kcal']
        tot['proteine'] = round(tot['proteine'] + n['proteine'], 1)
        tot['carboidrati'] = round(tot['carboidrati'] + n['carboidrati'], 1)
        tot['grassi'] = round(tot['grassi'] + n['grassi'], 1)
    tot['noto'] = noto_almeno_uno
    return tot


def consumo_del_giorno(user, giorno=None):
    """Quanto il cliente ha già ordinato in un giorno: ordini dal menu,
    composti del builder e pasto aziendale. Il cesto non ha un prodotto
    collegato e resta fuori."""
    giorno = giorno or date.today()
    tot = _totale_vuoto()
    tot['voci'] = []
    cache = {}
    ordini = (Order.query.filter_by(user_id=user.id, order_date=giorno)
              .filter(Order.status != 'cancelled').all())
    for o in ordini:
        for it in o.items:
            if not it.product:
                continue
            n = nutrienti(it.product, it.quantity)
            _somma(tot, n)
            tot['voci'].append({'nome': it.product.name, 'quantita': it.quantity,
                                'kcal': n['kcal'], 'noto': n['noto'],
                                'origine': 'ordine %s' % (o.order_code or o.id)})
        for ci in o.custom_items:
            n = nutrienti_composto(list(ci.ingredients), ci.quantity or 1, cache)
            n_fake = dict(n)
            _somma(tot, n_fake)
            tot['voci'].append({'nome': ci.label, 'quantita': ci.quantity or 1,
                                'kcal': n['kcal'], 'noto': n['noto'],
                                'origine': 'ordine %s' % (o.order_code or o.id)})
    prenotazioni = (CorporateMealBooking.query.join(DailyFixedMeal)
                    .filter(CorporateMealBooking.user_id == user.id,
                            DailyFixedMeal.meal_date == giorno,
                            CorporateMealBooking.status != 'cancelled').all())
    for b in prenotazioni:
        n = nutrienti(b.meal, b.quantity or 1)
        _somma(tot, n)
        tot['voci'].append({'nome': b.meal.name, 'quantita': b.quantity or 1,
                            'kcal': n['kcal'], 'noto': n['noto'],
                            'origine': 'pasto aziendale'})
    return tot


def giudizio(kcal, riferimento):
    """'leggero' / 'in_linea' / 'abbondante' rispetto a un riferimento."""
    if not riferimento:
        return 'in_linea'
    rapporto = kcal / float(riferimento)
    if rapporto < 0.8:
        return 'leggero'
    if rapporto <= 1.15:
        return 'in_linea'
    return 'abbondante'


ETICHETTE_GIUDIZIO = {'leggero': ('Leggero', 'info'),
                      'in_linea': ('In linea', 'success'),
                      'abbondante': ('Abbondante', 'warning')}


def riepilogo_giornata(user, profilo, giorno=None):
    """Per la home: consumato oggi contro il fabbisogno."""
    fabb = fabbisogno(profilo, user)
    consumo = consumo_del_giorno(user, giorno)
    percento = int(round(100.0 * consumo['kcal'] / fabb['target'])) if fabb['target'] else 0
    return {'fabbisogno': fabb, 'consumo': consumo, 'percento': min(percento, 100),
            'percento_reale': percento,
            'giudizio_pranzo': giudizio(consumo['kcal'], fabb['pranzo']),
            'residuo': max(0, fabb['target'] - consumo['kcal'])}


# ── Analisi del carrello ────────────────────────────────────────────────────

def analizza_carrello(user, profilo, cart, custom_cart, giorno=None):
    """Kcal del carrello, compatibilità voce per voce, avvisi e alternative.

    Non blocca nulla: la scelta resta del cliente. Ma dice chiaramente cosa
    contiene un allergene escluso e quando il pranzo supera la quota.
    """
    fabb = fabbisogno(profilo, user)
    consumo = consumo_del_giorno(user, giorno)
    righe = []
    tot = _totale_vuoto()
    incompatibili = []
    for pid, qty in (cart or {}).items():
        p = db.session.get(Product, int(pid))
        if not p:
            continue
        ok, motivi = compatibilita(p, profilo)
        n = nutrienti(p, qty)
        _somma(tot, n)
        righe.append({'tipo': 'prodotto', 'id': p.id, 'nome': p.name,
                      'quantita': qty, 'kcal': n['kcal'], 'noto': n['noto'],
                      'ok': ok, 'motivi': motivi})
        if not ok:
            incompatibili.append((p, motivi))
    cache = {}
    for ci in (custom_cart or []):
        ingredienti = ci.get('ingredients', [])
        n = nutrienti_composto(ingredienti, 1, cache)
        _somma(tot, dict(n))
        motivi = []
        for ing in ingredienti:
            obj = db.session.get(Ingredient, ing['id']) if ing.get('id') else None
            if obj is None:
                obj = _ingrediente_per_nome(ing.get('name', ''), cache)
            if obj is None:
                continue
            ok_i, m_i = compatibilita(obj, profilo)
            if not ok_i:
                motivi.append('%s: %s' % (obj.name, ', '.join(m_i)))
        righe.append({'tipo': 'composto', 'id': ci.get('uid'), 'nome': ci.get('label', ''),
                      'quantita': 1, 'kcal': n['kcal'], 'noto': n['noto'],
                      'ok': not motivi, 'motivi': motivi})

    totale_giorno = consumo['kcal'] + tot['kcal']
    avvisi = []
    for p, motivi in incompatibili:
        avvisi.append({'livello': 'danger',
                       'testo': '%s: %s.' % (p.name, ', '.join(motivi))})
    for r in righe:
        if r['tipo'] == 'composto' and not r['ok']:
            avvisi.append({'livello': 'danger',
                           'testo': '%s — %s.' % (r['nome'], '; '.join(r['motivi']))})
    if fabb['pranzo'] and tot['kcal'] > fabb['pranzo'] * 1.15:
        avvisi.append({'livello': 'warning',
                       'testo': 'Questo pranzo fa %d kcal, %d oltre la tua quota di %d.'
                                % (tot['kcal'], tot['kcal'] - fabb['pranzo'], fabb['pranzo'])})
    if consumo['kcal'] and totale_giorno > fabb['target']:
        avvisi.append({'livello': 'warning',
                       'testo': 'Con quello che hai già ordinato oggi (%d kcal) arrivi a %d kcal, '
                                'oltre il tuo fabbisogno di %d.'
                                % (consumo['kcal'], totale_giorno, fabb['target'])})
    if tot['sconosciute']:
        avvisi.append({'livello': 'secondary',
                       'testo': 'Per %d voc%s il locale non ha indicato i valori: il totale è '
                                'per difetto.' % (tot['sconosciute'],
                                                  'e' if tot['sconosciute'] == 1 else 'i')})

    alternative = []
    for p, _m in incompatibili[:3]:
        alt = alternativa_per(p, profilo)
        if alt:
            alternative.append({'al_posto_di': p.name, 'prodotto': alt})
    if not incompatibili and fabb['pranzo'] and tot['kcal'] > fabb['pranzo'] * 1.15:
        pesante = max((r for r in righe if r['tipo'] == 'prodotto' and r['noto']),
                      key=lambda r: r['kcal'], default=None)
        if pesante:
            p = db.session.get(Product, pesante['id'])
            alt = alternativa_per(p, profilo, piu_leggera=True)
            if alt:
                alternative.append({'al_posto_di': p.name, 'prodotto': alt})

    return {'righe': righe, 'totale': tot, 'consumo': consumo, 'fabbisogno': fabb,
            'totale_giorno': totale_giorno,
            'giudizio': giudizio(tot['kcal'], fabb['pranzo']),
            'avvisi': avvisi, 'alternative': alternative,
            'ha_incompatibili': bool(incompatibili) or any(
                r['tipo'] == 'composto' and not r['ok'] for r in righe)}


def alternativa_per(prodotto, profilo, piu_leggera=False):
    """Un prodotto della stessa categoria, compatibile e disponibile; se
    richiesto, più leggero di quello dato."""
    candidati = (Product.query.filter_by(category_id=prodotto.category_id, is_active=True,
                                         tenant_id=prodotto.tenant_id)
                 .filter(Product.id != prodotto.id).all())
    buoni = []
    for c in candidati:
        if c.available_today() <= 0 or not compatibilita(c, profilo)[0]:
            continue
        if piu_leggera and (c.kcal is None or prodotto.kcal is None or c.kcal >= prodotto.kcal):
            continue
        buoni.append(c)
    if not buoni:
        return None
    if piu_leggera:
        return max(buoni, key=lambda c: c.kcal)      # il più vicino, ma sotto
    return min(buoni, key=lambda c: (c.kcal if c.kcal is not None else 9999))


# ── Compositore ─────────────────────────────────────────────────────────────

def ruolo(prodotto):
    nome = prodotto.category.name if prodotto.category else ''
    if nome in CATEGORIE_PRINCIPALE:
        if prodotto.kcal is not None and prodotto.kcal < KCAL_MINIME_PRINCIPALE:
            return 'contorno'
        return 'principale'
    if nome in CATEGORIE_CONTORNO:
        return 'contorno'
    if nome in CATEGORIE_CHIUSURA:
        return 'chiusura'
    if nome in CATEGORIE_BEVANDA:
        return 'bevanda'
    return None


def candidati_piano(profilo, tenant_id):
    """I prodotti che possono entrare in un piano: attivi, compatibili, con
    i valori indicati e con un ruolo nel pranzo."""
    prodotti = Product.query.filter_by(is_active=True, tenant_id=tenant_id).all()
    buoni = []
    for p in prodotti:
        if p.kcal is None or not ruolo(p):
            continue
        if (p.daily_quantity or 0) <= 0:
            continue
        if not compatibilita(p, profilo)[0]:
            continue
        buoni.append(p)
    return buoni


def componi_pranzo(candidati, target, rnd=None, usati=(), budget=None,
                   obiettivo='mantenimento'):
    """Il pranzo più vicino alla quota: un principale, eventualmente un
    contorno e una chiusura, più l'acqua. Ritorna (prodotti, punteggio) o
    (None, None) se manca un principale.

    Il punteggio somma lo scarto dalla quota alle penalità: piatti già
    usati nella settimana, budget superato, poche proteine, dolce per chi
    vuole perdere peso. Un pizzico di caso rompe i pareggi, così due clienti
    con lo stesso profilo non ricevono lo stesso identico piano.
    """
    rnd = rnd or random.Random()
    usati = set(usati)
    per_ruolo = {'principale': [], 'contorno': [], 'chiusura': [], 'bevanda': []}
    for p in candidati:
        r = ruolo(p)
        if r:
            per_ruolo[r].append(p)
    if not per_ruolo['principale'] or not target:
        return None, None

    acqua = None
    zero = [b for b in per_ruolo['bevanda'] if (b.kcal or 0) == 0]
    if zero:
        acqua = min(zero, key=lambda b: b.price)

    def punteggio(combo):
        kcal = sum(p.kcal for p in combo)
        prezzo = sum(p.price for p in combo)
        prot = sum(p.proteine_g or 0 for p in combo)
        s = abs(kcal - target) / float(target)
        # Ripetere il piatto principale nella settimana pesa; ripetere la
        # frutta o un contorno e' normale, e se costasse quanto il primo il
        # compositore preferirebbe un pranzo troppo leggero pur di variarli.
        s += sum((0.35 if ruolo(p) == 'principale' else 0.08)
                 for p in combo if p.id in usati)
        if budget and prezzo > budget:
            s += 0.5 + (prezzo - budget) / budget
        if prot < 20:
            s += 0.15
        if obiettivo == 'dimagrimento' and any(
                p.category and p.category.name == 'Dolci' for p in combo):
            s += 0.3
        return s

    migliore, migliore_s = None, None
    for pr in per_ruolo['principale']:
        for co in [None] + per_ruolo['contorno']:
            for ch in [None] + per_ruolo['chiusura']:
                combo = [x for x in (pr, co, ch) if x is not None]
                if sum(p.kcal for p in combo) > target * 1.25:
                    continue
                s = punteggio(combo) + 0.02 * rnd.random()
                if migliore_s is None or s < migliore_s:
                    migliore, migliore_s = combo, s
    if migliore is None:
        # Anche il principale più leggero supera la quota: si prende quello.
        pr = min(per_ruolo['principale'], key=lambda p: (p.id in usati, p.kcal))
        migliore, migliore_s = [pr], punteggio([pr])
    if acqua is not None:
        migliore = migliore + [acqua]
    return migliore, round(migliore_s, 3)


def inizio_settimana(oggi=None):
    """Il lunedì della settimana da pianificare: quella corrente, oppure la
    prossima se siamo già a sabato o domenica."""
    oggi = oggi or date.today()
    lunedi = oggi - timedelta(days=oggi.weekday())
    if oggi.weekday() >= 5:
        lunedi += timedelta(days=7)
    return lunedi


def _voce(prodotto):
    return {'tipo': 'prodotto', 'id': prodotto.id, 'nome': prodotto.name,
            'categoria': prodotto.category.name if prodotto.category else '',
            'ruolo': ruolo(prodotto), 'kcal': prodotto.kcal or 0,
            'prezzo': round(prodotto.price, 2)}


def genera_piano(user, profilo, week_start=None, seed=None, oggi=None):
    """Crea (o rifà) il piano della settimana per i giorni scelti dal cliente.

    I giorni già ordinati restano come sono; gli altri vengono ricomposti.
    I giorni della settimana corrente già trascorsi si segnano come saltati.
    """
    oggi = oggi or date.today()
    week_start = week_start or inizio_settimana(oggi)
    tenant_id = user.tenant_id
    if tenant_id is None:
        from app.models import Tenant
        t = Tenant.query.filter_by(slug='default').first()
        tenant_id = t.id if t else None

    fabb = fabbisogno(profilo, user)
    candidati = candidati_piano(profilo, tenant_id)
    rnd = random.Random(seed) if seed is not None else random.Random()

    piano = DietPlan.query.filter_by(user_id=user.id, week_start=week_start).first()
    if piano is None:
        piano = DietPlan(user_id=user.id, tenant_id=tenant_id, week_start=week_start)
        db.session.add(piano)
        db.session.flush()
    piano.target_pranzo = fabb['pranzo']
    piano.notificato = False if not piano.days else piano.notificato

    ordinati = {d.giorno: d for d in piano.days if d.stato == 'ordinato'}
    for d in list(piano.days):
        if d.stato != 'ordinato':
            db.session.delete(d)
    db.session.flush()

    usati = set()
    for d in ordinati.values():
        usati |= {v['id'] for v in d.voci if v.get('tipo') == 'prodotto'}

    for offset, chiave in enumerate(CHIAVI_GIORNI):
        if chiave not in profilo.lista_giorni:
            continue
        giorno = week_start + timedelta(days=offset)
        if giorno in ordinati:
            continue
        d = DietPlanDay(plan_id=piano.id, giorno=giorno)
        if giorno < oggi:
            d.stato = 'saltato'
            d.nota = 'Giorno già trascorso.'
            db.session.add(d)
            continue
        combo, _s = componi_pranzo(candidati, fabb['pranzo'], rnd, usati,
                                   profilo.budget_pranzo, profilo.obiettivo)
        if not combo:
            d.nota = ('Nessun piatto del listino è compatibile con le tue esigenze, '
                      'o il locale non ha ancora indicato i valori nutrizionali.')
            db.session.add(d)
            continue
        d.voci = [_voce(p) for p in combo]
        d.kcal_totali = sum(p.kcal or 0 for p in combo)
        d.proteine_g = round(sum(p.proteine_g or 0 for p in combo), 1)
        d.carboidrati_g = round(sum(p.carboidrati_g or 0 for p in combo), 1)
        d.grassi_g = round(sum(p.grassi_g or 0 for p in combo), 1)
        d.prezzo_totale = round(sum(p.price for p in combo), 2)
        usati |= {p.id for p in combo if ruolo(p) != 'bevanda'}
        db.session.add(d)
    db.session.commit()
    return piano


def rigenera_giorno(giorno_piano, profilo, user, seed=None):
    """Ricompone un solo giorno, evitando quello che c'era."""
    piano = giorno_piano.plan
    fabb = fabbisogno(profilo, user)
    candidati = candidati_piano(profilo, piano.tenant_id)
    usati = set()
    for d in piano.days:
        usati |= {v['id'] for v in d.voci if v.get('tipo') == 'prodotto'
                  and v.get('ruolo') != 'bevanda'}
    rnd = random.Random(seed) if seed is not None else random.Random()
    combo, _s = componi_pranzo(candidati, fabb['pranzo'], rnd, usati,
                               profilo.budget_pranzo, profilo.obiettivo)
    if not combo:
        return False
    giorno_piano.voci = [_voce(p) for p in combo]
    giorno_piano.kcal_totali = sum(p.kcal or 0 for p in combo)
    giorno_piano.proteine_g = round(sum(p.proteine_g or 0 for p in combo), 1)
    giorno_piano.carboidrati_g = round(sum(p.carboidrati_g or 0 for p in combo), 1)
    giorno_piano.grassi_g = round(sum(p.grassi_g or 0 for p in combo), 1)
    giorno_piano.prezzo_totale = round(sum(p.price for p in combo), 2)
    giorno_piano.stato = 'proposto'
    giorno_piano.nota = ''
    db.session.commit()
    return True


def carrello_da_giorno(giorno_piano):
    """Il carrello (come in sessione) con i prodotti del giorno ancora
    ordinabili. Ritorna (carrello, nomi_mancanti)."""
    carrello = {}
    mancanti = []
    for v in giorno_piano.voci:
        if v.get('tipo') != 'prodotto':
            continue
        p = db.session.get(Product, v['id'])
        if not p or not p.is_active or p.available_today() <= 0:
            mancanti.append(v.get('nome', '?'))
            continue
        carrello[str(p.id)] = carrello.get(str(p.id), 0) + 1
    return carrello, mancanti


def testo_piano(piano, con_intestazione=True):
    """Il piano in testo, per Telegram ed email."""
    righe = []
    if con_intestazione:
        righe.append('🥗 <b>Il tuo pranzo della settimana</b> (dal %s)'
                     % piano.week_start.strftime('%d/%m'))
        righe.append('Quota pranzo: <b>%d kcal</b>' % (piano.target_pranzo or 0))
        righe.append('')
    for d in piano.days:
        if d.stato == 'saltato':
            continue
        if not d.voci:
            righe.append('• %s %s — %s' % (d.etichetta_giorno, d.giorno.strftime('%d/%m'),
                                           d.nota or 'nessuna proposta'))
            continue
        nomi = ' + '.join(v['nome'] for v in d.voci if v.get('ruolo') != 'bevanda')
        righe.append('• <b>%s %s</b> — %s · %d kcal · %s€'
                     % (d.etichetta_giorno, d.giorno.strftime('%d/%m'), nomi,
                        d.kcal_totali, ('%.2f' % d.prezzo_totale).replace('.', ',')))
    return '\n'.join(righe)


def profilo_attivo(user):
    """Il profilo dieta dell'utente se esiste ed è attivo, altrimenti None."""
    if not getattr(user, 'is_authenticated', False):
        return None
    p = getattr(user, 'diet_profile', None)
    return p if (p and p.attivo) else None
