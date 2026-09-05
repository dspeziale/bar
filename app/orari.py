# -*- coding: utf-8 -*-
"""Orari dell'esercizio: il posto unico da cui discende la programmazione.

Il gestore compila una sola tabella (Impostazioni → Orari): quando il locale
è aperto e in quali giorni, quando si accettano gli ordini e quando si
ritirano, entro che ora si prenota il pasto aziendale, le fasce dei tavoli,
quanto vive il QR del banco e un'etichetta del cesto, in che giorno e a che
ora partono gli avvisi settimanali, con quanto anticipo i promemoria.

Da qui l'applicazione **deriva** il resto: gli slot di ritiro e le fasce
dei tavoli si generano da questi valori, il carrello mostra solo gli slot
ancora raggiungibili, l'ordine viene rifiutato fuori finestra o nei giorni
di chiusura, il pasto aziendale si prenota entro l'ora stabilita, la dieta
non pianifica i giorni chiusi, gli avvisi partono nel giorno e all'ora
scelti. Cambiare un orario qui cambia il comportamento ovunque; non
esistono altri orari cablati nel codice.

Tutti i valori stanno in AppSetting (chiavi di CHIAVI_ORARI), letti con
`leggi_orari()` che riporta ai tipi giusti e ripiega sul default se un valore
è corrotto: la programmazione non si ferma per un orario scritto male.
"""
from datetime import date, datetime, time, timedelta

from app import db, _ROME
from app.notifications import get_setting

GIORNI = ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom']
NOMI_GIORNI = {'lun': 'Lunedì', 'mar': 'Martedì', 'mer': 'Mercoledì', 'gio': 'Giovedì',
               'ven': 'Venerdì', 'sab': 'Sabato', 'dom': 'Domenica'}

GRUPPI = [
    ('locale',     'Il locale',              'fa-store',          'Quando siete aperti al pubblico.'),
    ('ordini',     'Ordini e ritiro',        'fa-utensils',       'La finestra degli ordini e gli slot di ritiro, '
                                                                  'da cui nascono gli slot veri.'),
    ('pasto',      'Pasto aziendale',        'fa-building',       'I tempi delle convenzioni.'),
    ('tavoli',     'Tavoli',                 'fa-chair',          'Le fasce delle prenotazioni, da cui nascono le fasce vere.'),
    ('servizi',    'Banco e cesto',          'fa-qrcode',         'Quanto vivono un conto al banco e un\'etichetta.'),
    ('settimana',  'Appuntamenti della settimana', 'fa-calendar-week', 'Il giorno e l\'ora degli avvisi automatici.'),
    ('promemoria', 'Promemoria',             'fa-bell',           'Con quanto anticipo arrivano i promemoria.'),
]

# (chiave, default, etichetta, gruppo, tipo). Tipi: ora 'HH:MM', min (minuti),
# int, giorni (elenco di GIORNI), date (elenco 'YYYY-MM-DD'), giorno (uno di GIORNI).
CHIAVI_ORARI = [
    ('orario_apertura',          '07:00', 'Apertura al pubblico',                        'locale',     'ora'),
    ('orario_chiusura',          '17:30', 'Chiusura al pubblico',                        'locale',     'ora'),
    ('giorni_apertura',          'lun,mar,mer,gio,ven', 'Giorni di apertura',            'locale',     'giorni'),
    ('chiusure_straordinarie',   '',      'Chiusure straordinarie',                      'locale',     'date'),
    ('ordini_apertura',          '07:30', 'Gli ordini per oggi si accettano dalle',      'ordini',     'ora'),
    ('ordini_chiusura',          '13:15', 'Ultimo ordine per oggi entro le',             'ordini',     'ora'),
    ('ordini_anticipo_min',      '20',    'Minuti minimi fra l\'ordine e il ritiro',     'ordini',     'min'),
    ('pranzo_inizio',            '11:45', 'Primo slot di ritiro',                        'ordini',     'ora'),
    ('pranzo_fine',              '13:30', 'Ultimo slot di ritiro',                       'ordini',     'ora'),
    ('slot_intervallo_min',      '15',    'Intervallo fra uno slot e l\'altro',          'ordini',     'min'),
    ('slot_capienza',            '20',    'Ordini per slot (capienza)',                  'ordini',     'int'),
    ('cucina_anticipo_min',      '15',    'La cucina inizia a preparare prima dello slot di', 'ordini', 'min'),
    ('pasto_prenotazione_entro', '10:30', 'Prenotazione del pasto entro le',             'pasto',      'ora'),
    ('pasto_annullo_min',        '30',    'Disdetta possibile fino a (minuti prima del ritiro)', 'pasto', 'min'),
    ('tavoli_inizio',            '12:00', 'Prima fascia dei tavoli',                     'tavoli',     'ora'),
    ('tavoli_fine',              '14:30', 'Fine dell\'ultima fascia',                    'tavoli',     'ora'),
    ('tavoli_durata_min',        '30',    'Durata di una fascia',                        'tavoli',     'min'),
    ('banco_sessione_min',       '10',    'Il QR di un conto al banco vale',             'servizi',    'min'),
    ('cesto_scadenza_ore',       '24',    'Un\'etichetta del cesto scade dopo (ore)',    'servizi',    'int'),
    ('dieta_avviso_giorno',      'lun',   'Il piano della dieta arriva di',              'settimana',  'giorno'),
    ('dieta_avviso_ora',         '07:00', 'a partire dalle',                             'settimana',  'ora'),
    ('backup_promemoria_giorno', 'ven',   'Il promemoria del backup arriva di',          'settimana',  'giorno'),
    ('backup_promemoria_ora',    '09:00', 'a partire dalle',                             'settimana',  'ora'),
    ('comunicazioni_ora',        '10:00', 'Le comunicazioni automatiche e programmate partono dalle', 'settimana', 'ora'),
    ('table_reminder_minutes',   '10',    'Prenotazione tavolo: promemoria (minuti prima)', 'promemoria', 'min'),
    ('order_reminder_minutes',   '15',    'Ritiro ordine: promemoria (minuti prima)',    'promemoria', 'min'),
    ('meal_reminder_minutes',    '15',    'Pasto aziendale: promemoria (minuti prima)',  'promemoria', 'min'),
]
CHIAVI_MAP = {c[0]: c for c in CHIAVI_ORARI}
DEFAULT = {c[0]: c[1] for c in CHIAVI_ORARI}


# ── Lettura e conversione ───────────────────────────────────────────────────

def _ora(testo, default):
    try:
        h, m = str(testo).strip().split(':')
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        h, m = default.split(':')
        return time(int(h), int(m))


def _intero(testo, default, minimo=0, massimo=100000):
    try:
        v = int(str(testo).strip())
    except (ValueError, TypeError):
        v = int(default)
    return max(minimo, min(massimo, v))


def _giorni(testo, default):
    chiavi = [g.strip().lower() for g in str(testo or '').split(',') if g.strip()]
    buoni = [g for g in GIORNI if g in chiavi]
    return buoni or [g for g in GIORNI if g in default.split(',')]


def _date(testo):
    out = []
    for pezzo in str(testo or '').replace(';', ',').replace('\n', ',').split(','):
        pezzo = pezzo.strip()
        if not pezzo:
            continue
        try:
            out.append(date.fromisoformat(pezzo))
        except ValueError:
            continue
    return sorted(set(out))


def _giorno(testo, default):
    g = str(testo or '').strip().lower()
    return g if g in GIORNI else default


def converti(chiave, grezzo):
    """Il valore grezzo di una chiave riportato al suo tipo, con ripiego."""
    _k, default, _et, _gr, tipo = CHIAVI_MAP[chiave]
    if tipo == 'ora':
        return _ora(grezzo, default)
    if tipo in ('min', 'int'):
        return _intero(grezzo, default, 0 if tipo == 'int' else 0, 100000)
    if tipo == 'giorni':
        return _giorni(grezzo, default)
    if tipo == 'date':
        return _date(grezzo)
    if tipo == 'giorno':
        return _giorno(grezzo, default)
    return grezzo


def leggi_orari():
    """Tutti gli orari, già convertiti. Un valore mancante o corrotto vale il default."""
    return {c[0]: converti(c[0], get_setting(c[0]) or c[1]) for c in CHIAVI_ORARI}


def formatta(chiave, valore):
    """Il valore nella forma da salvare / mostrare nel modulo."""
    tipo = CHIAVI_MAP[chiave][4]
    if tipo == 'ora':
        return valore.strftime('%H:%M')
    if tipo == 'giorni':
        return ','.join(valore)
    if tipo == 'date':
        return ', '.join(d.isoformat() for d in valore)
    return str(valore)


def ora_locale(adesso=None):
    """L'ora del locale (Roma), come datetime naive: è così che sono scritti gli slot."""
    if adesso is None:
        return datetime.now(_ROME).replace(tzinfo=None)
    if adesso.tzinfo is not None:
        return adesso.astimezone(_ROME).replace(tzinfo=None)
    return adesso


# ── Giorni e finestre ───────────────────────────────────────────────────────

def indice_giorno(chiave):
    return GIORNI.index(chiave) if chiave in GIORNI else 0


def giorno_aperto(d, orari=None):
    """True se in quel giorno il locale è aperto (giorno della settimana e
    chiusure straordinarie)."""
    orari = orari or leggi_orari()
    return GIORNI[d.weekday()] in orari['giorni_apertura'] and d not in orari['chiusure_straordinarie']


def prossimo_giorno_aperto(d, orari=None):
    orari = orari or leggi_orari()
    for i in range(1, 60):
        g = d + timedelta(days=i)
        if giorno_aperto(g, orari):
            return g
    return None


def aperto_adesso(adesso=None, orari=None):
    orari = orari or leggi_orari()
    now = ora_locale(adesso)
    return (giorno_aperto(now.date(), orari)
            and orari['orario_apertura'] <= now.time() < orari['orario_chiusura'])


def finestra_ordini(adesso=None, orari=None):
    """(aperta, motivo): si può ordinare adesso per oggi?"""
    orari = orari or leggi_orari()
    now = ora_locale(adesso)
    if not giorno_aperto(now.date(), orari):
        prossimo = prossimo_giorno_aperto(now.date(), orari)
        return False, ('Oggi il locale è chiuso.' +
                       (' Riapre %s %s.' % (NOMI_GIORNI[GIORNI[prossimo.weekday()]].lower(),
                                            prossimo.strftime('%d/%m')) if prossimo else ''))
    if now.time() < orari['ordini_apertura']:
        return False, 'Gli ordini per oggi si accettano dalle %s.' % orari['ordini_apertura'].strftime('%H:%M')
    if now.time() > orari['ordini_chiusura']:
        return False, ('Gli ordini per oggi si sono chiusi alle %s.'
                       % orari['ordini_chiusura'].strftime('%H:%M'))
    return True, ''


def slot_previsti(orari=None):
    """Gli orari 'HH:MM' che gli slot di ritiro devono avere, dal primo
    all'ultimo, a passo dell'intervallo."""
    orari = orari or leggi_orari()
    passo = max(5, orari['slot_intervallo_min'])
    inizio = datetime.combine(date.today(), orari['pranzo_inizio'])
    fine = datetime.combine(date.today(), orari['pranzo_fine'])
    out = []
    t = inizio
    while t <= fine and len(out) < 96:
        out.append(t.strftime('%H:%M'))
        t += timedelta(minutes=passo)
    return out


def slot_ordinabili(slots, adesso=None, orari=None):
    """Gli slot su cui si può ancora ordinare adesso: attivi e abbastanza
    lontani da lasciare il tempo alla cucina (ordini_anticipo_min)."""
    orari = orari or leggi_orari()
    now = ora_locale(adesso)
    # Si confrontano istanti, non soli orari: un anticipo che supera la
    # mezzanotte confrontato come ora "gira" e lascerebbe raggiungibile tutto.
    limite = now + timedelta(minutes=orari['ordini_anticipo_min'])
    buoni = []
    for s in slots:
        try:
            h, m = s.time_str.split(':')
            slot_dt = datetime.combine(now.date(), time(int(h), int(m)))
        except (ValueError, AttributeError):
            continue
        if slot_dt >= limite:
            buoni.append(s)
    return buoni


def fasce_previste(orari=None):
    """Le fasce dei tavoli (inizio, fine) derivate da inizio, fine e durata."""
    orari = orari or leggi_orari()
    durata = max(10, orari['tavoli_durata_min'])
    t = datetime.combine(date.today(), orari['tavoli_inizio'])
    fine = datetime.combine(date.today(), orari['tavoli_fine'])
    out = []
    while t + timedelta(minutes=durata) <= fine and len(out) < 48:
        out.append((t.strftime('%H:%M'), (t + timedelta(minutes=durata)).strftime('%H:%M')))
        t += timedelta(minutes=durata)
    return out


def prenotazione_pasto_aperta(adesso=None, orari=None):
    """(aperta, motivo): si può ancora prenotare il pasto aziendale di oggi?"""
    orari = orari or leggi_orari()
    now = ora_locale(adesso)
    if not giorno_aperto(now.date(), orari):
        return False, 'Oggi il locale è chiuso.'
    if now.time() > orari['pasto_prenotazione_entro']:
        return False, ('Le prenotazioni di oggi si sono chiuse alle %s.'
                       % orari['pasto_prenotazione_entro'].strftime('%H:%M'))
    return True, ''


def momento_settimanale(chiave_giorno, chiave_ora, adesso=None, orari=None):
    """True se adesso è il giorno giusto e l'ora è già passata: per gli avvisi settimanali."""
    orari = orari or leggi_orari()
    now = ora_locale(adesso)
    return (now.weekday() == indice_giorno(orari[chiave_giorno])
            and now.time() >= orari[chiave_ora])


# ── Validazione e programma ─────────────────────────────────────────────────

def valida(orari):
    """Le incoerenze fra gli orari, in frasi. Vuoto = tutto coerente."""
    e = []
    o = orari
    if o['orario_apertura'] >= o['orario_chiusura']:
        e.append('L\'apertura deve precedere la chiusura.')
    if not o['giorni_apertura']:
        e.append('Serve almeno un giorno di apertura.')
    if o['ordini_apertura'] >= o['ordini_chiusura']:
        e.append('Gli ordini devono aprirsi prima di chiudersi.')
    if o['ordini_apertura'] < o['orario_apertura']:
        e.append('Gli ordini non possono aprirsi prima del locale (%s).' % o['orario_apertura'].strftime('%H:%M'))
    if o['pranzo_inizio'] >= o['pranzo_fine']:
        e.append('Il primo slot di ritiro deve precedere l\'ultimo.')
    if o['pranzo_fine'] > o['orario_chiusura']:
        e.append('L\'ultimo slot di ritiro (%s) è dopo la chiusura (%s).'
                 % (o['pranzo_fine'].strftime('%H:%M'), o['orario_chiusura'].strftime('%H:%M')))
    if o['ordini_chiusura'] > o['pranzo_fine']:
        e.append('L\'ultimo ordine (%s) non può essere dopo l\'ultimo slot di ritiro (%s).'
                 % (o['ordini_chiusura'].strftime('%H:%M'), o['pranzo_fine'].strftime('%H:%M')))
    if o['slot_intervallo_min'] < 5:
        e.append('L\'intervallo fra gli slot non può essere sotto i 5 minuti.')
    if o['slot_capienza'] < 1:
        e.append('La capienza di uno slot deve essere almeno 1.')
    if o['pasto_prenotazione_entro'] > o['pranzo_inizio']:
        e.append('Il pasto aziendale va prenotato prima del primo slot di ritiro (%s).'
                 % o['pranzo_inizio'].strftime('%H:%M'))
    if o['tavoli_inizio'] >= o['tavoli_fine']:
        e.append('La prima fascia dei tavoli deve precedere la fine dell\'ultima.')
    if o['tavoli_fine'] > o['orario_chiusura']:
        e.append('Le fasce dei tavoli finiscono dopo la chiusura.')
    if o['tavoli_durata_min'] < 10:
        e.append('Una fascia dei tavoli dura almeno 10 minuti.')
    if o['banco_sessione_min'] < 1:
        e.append('Il QR del banco deve valere almeno 1 minuto.')
    if o['cesto_scadenza_ore'] < 1:
        e.append('Un\'etichetta del cesto deve valere almeno 1 ora.')
    return e


def programma_giornata(orari=None):
    """La giornata tipo, in ordine: quello che discende dagli orari."""
    orari = orari or leggi_orari()
    o = orari
    voci = [
        (o['orario_apertura'], 'Apertura al pubblico', 'fa-door-open', 'navy'),
        (o['ordini_apertura'], 'Si aprono gli ordini per oggi', 'fa-cart-plus', 'success'),
        (o['pasto_prenotazione_entro'], 'Ultimo momento per prenotare il pasto aziendale', 'fa-building', 'purple'),
        ((datetime.combine(date.today(), o['pranzo_inizio']) - timedelta(minutes=o['cucina_anticipo_min'])).time(),
         'La cucina inizia il primo slot', 'fa-fire', 'orange'),
        (o['pranzo_inizio'], 'Primo slot di ritiro (%d slot ogni %d min)' % (len(slot_previsti(o)), o['slot_intervallo_min']),
         'fa-shopping-bag', 'navy'),
        (o['tavoli_inizio'], 'Prima fascia dei tavoli (%d fasce da %d min)' % (len(fasce_previste(o)), o['tavoli_durata_min']),
         'fa-chair', 'teal'),
        (o['ordini_chiusura'], 'Ultimo ordine per oggi', 'fa-hand', 'danger'),
        (o['pranzo_fine'], 'Ultimo slot di ritiro', 'fa-shopping-bag', 'navy'),
        (o['tavoli_fine'], 'Fine dell\'ultima fascia dei tavoli', 'fa-chair', 'teal'),
        (o['orario_chiusura'], 'Chiusura al pubblico', 'fa-door-closed', 'navy'),
    ]
    voci.sort(key=lambda v: v[0])
    return [{'ora': v[0].strftime('%H:%M'), 'testo': v[1], 'icona': v[2], 'colore': v[3]} for v in voci]


# ── Sincronizzazioni: gli orari diventano righe ─────────────────────────────

def sincronizza_slot(tenant_id, orari=None):
    """Allinea i TimeSlot agli orari: crea quelli mancanti con la capienza
    impostata, riattiva quelli previsti, disattiva quelli fuori griglia.

    Non cancella nulla: uno slot disattivato resta per lo storico degli
    ordini. Ritorna (creati, riattivati, disattivati).
    """
    from app.models import TimeSlot
    orari = orari or leggi_orari()
    previsti = slot_previsti(orari)
    esistenti = {s.time_str: s for s in TimeSlot.query.filter_by(tenant_id=tenant_id).all()}
    creati = riattivati = disattivati = 0
    for ora in previsti:
        s = esistenti.get(ora)
        if s is None:
            db.session.add(TimeSlot(time_str=ora, max_orders=orari['slot_capienza'],
                                    is_active=True, tenant_id=tenant_id))
            creati += 1
        elif not s.is_active:
            s.is_active = True
            riattivati += 1
    for ora, s in esistenti.items():
        if ora not in previsti and s.is_active:
            s.is_active = False
            disattivati += 1
    db.session.commit()
    return creati, riattivati, disattivati


def sincronizza_fasce(tenant_id, orari=None):
    """Crea le fasce dei tavoli mancanti; quelle esistenti non si toccano,
    perché le prenotazioni le puntano. Ritorna il numero di fasce create."""
    from app.models import TableTimeBand
    orari = orari or leggi_orari()
    esistenti = {(b.start_time, b.end_time)
                 for b in TableTimeBand.query.filter_by(tenant_id=tenant_id).all()}
    ordine = TableTimeBand.query.filter_by(tenant_id=tenant_id).count()
    creati = 0
    for inizio, fine in fasce_previste(orari):
        if (inizio, fine) in esistenti:
            continue
        db.session.add(TableTimeBand(start_time=inizio, end_time=fine,
                                     duration_minutes=orari['tavoli_durata_min'],
                                     sort_order=ordine, tenant_id=tenant_id))
        ordine += 1
        creati += 1
    db.session.commit()
    return creati


def salva_orari(form):
    """Legge il modulo, converte, valida e salva. Ritorna (orari, errori):
    con errori non si salva nulla, così le incoerenze non arrivano al servizio."""
    from app.models import AppSetting
    grezzi = {}
    for chiave, default, _et, _gr, tipo in CHIAVI_ORARI:
        if tipo == 'giorni':
            grezzi[chiave] = ','.join(g for g in form.getlist('giorni_apertura') if g in GIORNI)
        else:
            grezzi[chiave] = (form.get(chiave) or '').strip() or default
    orari = {k: converti(k, v) for k, v in grezzi.items()}
    errori = valida(orari)
    if errori:
        return orari, errori
    for chiave in orari:
        valore = formatta(chiave, orari[chiave])
        riga = AppSetting.query.filter_by(key=chiave).first()
        if riga:
            riga.value = valore
        else:
            db.session.add(AppSetting(key=chiave, value=valore, label=CHIAVI_MAP[chiave][2]))
    db.session.commit()
    return orari, []
