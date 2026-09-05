# -*- coding: utf-8 -*-
"""Comunicazioni ai clienti: campagne per segmento, modelli di contenuto,
canale automatico (Telegram per chi lo usa, email per gli altri), invii
programmati e automatismi (benvenuto, compleanno, "ci manchi").

Regole che valgono ovunque:
- si scrive solo a chi ha `comunicazioni_ok` (revocabile dal profilo o dal
  link in fondo a ogni email); gli avvisi di servizio non passano da qui;
- ogni invio lascia una riga in `ComunicazioneInvio`, così il gestore vede a
  chi è arrivato e perché qualcuno è stato saltato;
- il testo usa segnaposto in graffe ({nome}, {locale}, {link_menu}...):
  `rendi()` li sostituisce per ciascun destinatario.
"""
import html as _html
from datetime import date, datetime, timedelta

from itsdangerous import URLSafeSerializer, BadSignature

from app import db
from app.models import (User, Order, DietProfile, Tenant, AppSetting,
                        Comunicazione, ComunicazioneInvio)
from app.notifications import (get_setting, send_email, send_telegram_to_user,
                               _guscio_email, _bottone, nome_bot)


# ── Segmenti ────────────────────────────────────────────────────────────────

# (chiave, etichetta, descrizione)
SEGMENTI = [
    ('tutti',          'Tutti i clienti',           'Ogni cliente attivo che accetta le comunicazioni.'),
    ('attivi_30',      'Clienti abituali',          'Hanno ordinato negli ultimi 30 giorni.'),
    ('inattivi_30',    'Non ordinano da un mese',   'Hanno ordinato almeno una volta, ma non negli ultimi 30 giorni.'),
    ('mai_ordinato',   'Registrati senza ordini',   'Si sono iscritti ma non hanno mai ordinato.'),
    ('nuovi_7',        'Iscritti da meno di 7 giorni', 'I nuovi arrivati della settimana.'),
    ('convenzionati',  'Convenzionati',             'Hanno una convenzione aziendale attiva.'),
    ('dieta',          'Con la dieta attiva',       'Seguono il piano settimanale.'),
    ('senza_dieta',    'Senza dieta',               'Non hanno ancora impostato la dieta.'),
    ('compleanno_7',   'Compleanno entro 7 giorni', 'Festeggiano nei prossimi sette giorni.'),
    ('telegram',       'Collegati a Telegram',      'Ricevono i messaggi in chat.'),
    ('senza_telegram', 'Non collegati a Telegram',  'Da invitare a collegare il bot.'),
]
SEGMENTI_MAP = {s[0]: s for s in SEGMENTI}

CANALI = [
    ('auto',     'Automatico: Telegram a chi lo usa, email agli altri'),
    ('email',    'Solo email'),
    ('telegram', 'Solo Telegram (chi non è collegato viene saltato)'),
    ('entrambi', 'Email e Telegram insieme'),
]


def _ultimi_ordini(user_ids):
    """{user_id: data dell'ultimo ordine non annullato}."""
    if not user_ids:
        return {}
    righe = (db.session.query(Order.user_id, db.func.max(Order.order_date))
             .filter(Order.user_id.in_(user_ids), Order.status != 'cancelled')
             .group_by(Order.user_id).all())
    return {uid: d for uid, d in righe}


def _base_clienti(tenant_id, con_consenso=True):
    q = User.query.filter_by(is_client=True, is_active=True)
    if tenant_id is not None:
        q = q.filter_by(tenant_id=tenant_id)
    utenti = q.order_by(User.last_name, User.first_name).all()
    if con_consenso:
        utenti = [u for u in utenti if u.comunicazioni_ok is None or u.comunicazioni_ok]
    return utenti


def destinatari(segmento, tenant_id, oggi=None, con_consenso=True):
    """I clienti del segmento, già filtrati per consenso."""
    oggi = oggi or date.today()
    utenti = _base_clienti(tenant_id, con_consenso)
    if segmento in ('attivi_30', 'inattivi_30', 'mai_ordinato'):
        ultimi = _ultimi_ordini([u.id for u in utenti])
        soglia = oggi - timedelta(days=30)
        if segmento == 'attivi_30':
            return [u for u in utenti if ultimi.get(u.id) and ultimi[u.id] >= soglia]
        if segmento == 'inattivi_30':
            return [u for u in utenti if ultimi.get(u.id) and ultimi[u.id] < soglia]
        return [u for u in utenti if not ultimi.get(u.id)]
    if segmento == 'nuovi_7':
        soglia = datetime.utcnow() - timedelta(days=7)
        return [u for u in utenti if u.created_at and u.created_at >= soglia]
    if segmento == 'convenzionati':
        return [u for u in utenti if u.corporate_membership and u.corporate_membership.is_active]
    if segmento in ('dieta', 'senza_dieta'):
        con = {p.user_id for p in DietProfile.query.filter_by(attivo=True)
               .with_entities(DietProfile.user_id).all()}
        return [u for u in utenti if (u.id in con) == (segmento == 'dieta')]
    if segmento == 'compleanno_7':
        esito = []
        for u in utenti:
            if not u.birth_date:
                continue
            for anno in (oggi.year, oggi.year + 1):
                try:
                    c = u.birth_date.replace(year=anno)
                except ValueError:          # 29 febbraio
                    c = date(anno, 3, 1)
                if 0 <= (c - oggi).days <= 7:
                    esito.append(u)
                    break
        return esito
    if segmento == 'telegram':
        return [u for u in utenti if (u.telegram_chat_id or '').strip()]
    if segmento == 'senza_telegram':
        return [u for u in utenti if not (u.telegram_chat_id or '').strip()]
    return utenti


def conteggi_segmenti(tenant_id, oggi=None):
    return {s[0]: len(destinatari(s[0], tenant_id, oggi)) for s in SEGMENTI}


# ── Modelli di contenuto ────────────────────────────────────────────────────

# (chiave, etichetta, icona, quando usarlo, oggetto, corpo, testo pulsante,
#  link pulsante, segmento consigliato, canale consigliato)
MODELLI = [
    ('libero', 'Messaggio libero', 'fa-pen', 'Quando nessun modello va bene: scrivi tu.',
     'Una comunicazione da {locale}', 'Ciao {nome},\n\n', 'Apri QuickLunch', '{link_app}',
     'tutti', 'auto'),
    ('benvenuto', 'Benvenuto', 'fa-hand-sparkles',
     'Ai nuovi iscritti dopo qualche giorno: spiega come si usa e invita al primo ordine.',
     'Benvenuto da {locale}, {nome}!',
     'Ciao {nome},\n\nsiamo contenti di averti con noi. Da QuickLunch ordini il pranzo dal '
     'telefono, scegli l\'orario di ritiro e trovi tutto pronto senza fare la coda.\n\n'
     'Se non l\'hai ancora fatto, collega Telegram dal tuo profilo: ti avvisiamo quando '
     'l\'ordine è pronto.\n\nSiamo aperti {orari}. Ti aspettiamo!',
     'Guarda il menu', '{link_menu}', 'nuovi_7', 'auto'),
    ('menu_settimana', 'Menu della settimana', 'fa-calendar-week',
     'Il lunedì, per raccontare cosa c\'è di buono nei prossimi giorni.',
     'Il menu di questa settimana da {locale}',
     'Ciao {nome},\n\necco cosa abbiamo preparato per questa settimana:\n\n'
     '- Lunedì: \n- Martedì: \n- Mercoledì: \n- Giovedì: \n- Venerdì: \n\n'
     'Ordina in anticipo e scegli il tuo orario di ritiro.',
     'Ordina il pranzo', '{link_menu}', 'tutti', 'auto'),
    ('novita', 'Novità nel menu', 'fa-star',
     'Un piatto nuovo, una promozione, un prodotto di stagione.',
     'Novità da {locale}: da provare',
     'Ciao {nome},\n\nda oggi trovi nel menu una novità: \n\n'
     'Raccontaci cosa ne pensi: le tue opinioni ci aiutano a scegliere cosa tenere.',
     'Scopri la novità', '{link_menu}', 'tutti', 'auto'),
    ('ci_manchi', 'Ci manchi', 'fa-heart',
     'A chi non ordina da un mese: un richiamo gentile, senza insistere.',
     '{nome}, ci manchi!',
     'Ciao {nome},\n\nè un po\' che non passi da noi e ci farebbe piacere rivederti. '
     'Nel frattempo il menu è cambiato: dai un\'occhiata, magari trovi qualcosa che ti va.\n\n'
     'Siamo aperti {orari}.',
     'Guarda il menu', '{link_menu}', 'inattivi_30', 'auto'),
    ('compleanno', 'Buon compleanno', 'fa-birthday-cake',
     'Il giorno del compleanno: un augurio, e se vuoi un omaggio da ritirare al banco.',
     'Tanti auguri, {nome}!',
     'Ciao {nome},\n\noggi è il tuo compleanno e ti facciamo tanti auguri da tutto lo staff '
     'di {locale}.\n\nPassa a trovarci: il caffè oggi lo offriamo noi.',
     'Vieni a trovarci', '{link_menu}', 'compleanno_7', 'auto'),
    ('sondaggio', 'Invito a votare', 'fa-square-poll-vertical',
     'Per un sondaggio sul menu: il link porta dritto alla pagina di voto.',
     'Dicci la tua: {sondaggio}',
     'Ciao {nome},\n\nstiamo decidendo il menu del {data_sondaggio} e vorremmo il tuo parere. '
     'Le scelte in gara:\n\n{scelte_sondaggio}\n\nBasta un tocco per votare.',
     'Vota ora', '{link_sondaggio}', 'tutti', 'auto'),
    ('chiusura', 'Avviso di chiusura', 'fa-door-closed',
     'Chiusura straordinaria, orario ridotto, lavori in corso.',
     'Avviso da {locale}: chiusura straordinaria',
     'Ciao {nome},\n\nti avvisiamo che il giorno  il locale resterà chiuso. '
     'Riapriremo regolarmente il giorno successivo, con i soliti orari ({orari}).\n\n'
     'Grazie per la comprensione.',
     '', '', 'tutti', 'entrambi'),
    ('promemoria_pasti', 'Prenota i pasti della settimana', 'fa-building',
     'Ai convenzionati, il lunedì: ricordare di prenotare evita sprechi in cucina.',
     'Prenota i pasti di questa settimana',
     'Ciao {nome},\n\nricordati di prenotare i pasti della convenzione per i prossimi giorni: '
     'la cucina prepara solo quello che è prenotato, così niente va sprecato.\n\n'
     'Puoi confermare o disdire fino a poco prima del ritiro.',
     'Prenota il pasto', '{link_pasto}', 'convenzionati', 'auto'),
    ('invito_dieta', 'La tua dieta settimanale', 'fa-leaf',
     'A chi non l\'ha ancora provata: il piano su misura che ordina con un tocco.',
     'Un pranzo su misura, ogni giorno',
     'Ciao {nome},\n\nsu QuickLunch puoi impostare la tua dieta settimanale: indichi esigenze '
     '(celiachia, lattosio, vegetariano...), gusti e obiettivo, e ogni settimana ricevi un piano '
     'di pranzi dal nostro menu, con le calorie sotto controllo. Ogni giorno lo ordini con un tocco.\n\n'
     'Le indicazioni sono stime informative, non hanno validità medica.',
     'Imposta la dieta', '{link_dieta}', 'senza_dieta', 'auto'),
    ('invito_telegram', 'Collega Telegram', 'fa-paper-plane',
     'A chi riceve ancora tutto per email: gli avvisi in chat sono più comodi.',
     'Ricevi gli avvisi su Telegram',
     'Ciao {nome},\n\ncollegando Telegram ricevi in chat l\'avviso di ordine pronto e il '
     'promemoria del pasto, con i bottoni per confermare o disdire con un tocco.\n\n'
     'Bastano trenta secondi: apri la pagina, invia il tuo codice al bot @{bot} e hai finito.',
     'Collega Telegram', '{link_telegram}', 'senza_telegram', 'email'),
    ('grazie', 'Grazie', 'fa-mug-hot',
     'Un ringraziamento ai clienti abituali, magari con un\'anticipazione.',
     'Grazie, {nome}',
     'Ciao {nome},\n\nvolevamo solo dirti grazie: sei tra i clienti che passano più spesso da '
     '{locale}, e per noi conta. Continueremo a fare del nostro meglio.\n\nA presto!',
     'Guarda il menu', '{link_menu}', 'attivi_30', 'auto'),
]
MODELLI_MAP = {m[0]: m for m in MODELLI}

# I segnaposto ammessi, con la spiegazione per il modulo.
SEGNAPOSTO = [
    ('{nome}',            'Il nome del cliente'),
    ('{locale}',          'Il nome del locale'),
    ('{orari}',           'Gli orari di apertura (dalla scheda Orari)'),
    ('{indirizzo}',       'L\'indirizzo del locale'),
    ('{telefono}',        'Il telefono del locale'),
    ('{bot}',             'Il nome del bot Telegram'),
    ('{link_app}',        'La pagina iniziale'),
    ('{link_menu}',       'Il menu'),
    ('{link_dieta}',      'La mia dieta'),
    ('{link_pasto}',      'Pasto aziendale'),
    ('{link_profilo}',    'Il profilo del cliente'),
    ('{link_telegram}',   'La pagina per collegare Telegram'),
    ('{sondaggio}',       'Il titolo del sondaggio collegato'),
    ('{data_sondaggio}',  'La data del sondaggio collegato'),
    ('{scelte_sondaggio}', 'L\'elenco delle scelte del sondaggio'),
    ('{link_sondaggio}',  'La pagina di voto del sondaggio'),
]


def indirizzo_base():
    """L'indirizzo pubblico dell'app: dalla richiesta se c'è, altrimenti
    dall'impostazione `public_base_url` (invii dal polling o da riga di comando)."""
    try:
        from flask import request, has_request_context
        if has_request_context():
            return request.host_url.rstrip('/')
    except Exception:
        pass
    return (get_setting('public_base_url') or '').strip().rstrip('/')


def _orari_testo():
    try:
        from app.orari import leggi_orari, formatta, NOMI_GIORNI
        o = leggi_orari()
        giorni = o.get('giorni_apertura') or []
        etichette = NOMI_GIORNI
        if giorni:
            gtxt = (etichette.get(giorni[0], giorni[0]) + '–' + etichette.get(giorni[-1], giorni[-1])
                    if len(giorni) > 2 else ' e '.join(etichette.get(g, g) for g in giorni))
        else:
            gtxt = ''
        return ('%s dalle %s alle %s' % (gtxt, formatta('orario_apertura', o['orario_apertura']),
                                          formatta('orario_chiusura', o['orario_chiusura']))).strip()
    except Exception:
        return 'nei soliti orari'


def valori_segnaposto(user, com, base_url):
    base = base_url or indirizzo_base()
    poll = com.poll if com is not None else None
    scelte = ''
    if poll is not None:
        scelte = '\n'.join('%s %s' % (c.emoji or '•', c.text) for c in poll.choices)
    return {
        'nome': (user.first_name or user.username or 'cliente').strip() if user else 'cliente',
        'locale': get_setting('company_name') or 'QuickLunch',
        'orari': _orari_testo(),
        'indirizzo': ' '.join(x for x in (get_setting('company_address'), get_setting('company_city')) if x),
        'telefono': get_setting('company_phone') or '',
        'bot': nome_bot() or '',
        'link_app': base + '/',
        'link_menu': base + '/menu',
        'link_dieta': base + '/dieta',
        'link_pasto': base + '/pasto-aziendale',
        'link_profilo': base + '/profile',
        'link_telegram': base + '/telegram/collega',
        'sondaggio': poll.title if poll is not None else '',
        'data_sondaggio': poll.poll_date.strftime('%d/%m/%Y') if poll is not None else '',
        'scelte_sondaggio': scelte,
        'link_sondaggio': (base + '/poll/%d' % poll.id) if poll is not None else base + '/poll',
    }


def rendi(testo, valori):
    """Sostituisce i segnaposto; quelli sconosciuti restano com'erano."""
    out = testo or ''
    for k, v in valori.items():
        out = out.replace('{%s}' % k, str(v))
    return out


# ── Disiscrizione ────────────────────────────────────────────────────────────

def _firmatario():
    from flask import current_app
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='comunicazioni-disiscrizione')


def token_disiscrizione(user):
    return _firmatario().dumps(user.id)


def utente_da_token(token):
    try:
        uid = _firmatario().loads(token)
    except BadSignature:
        return None
    return db.session.get(User, uid) if isinstance(uid, int) else None


# ── Composizione dei messaggi ───────────────────────────────────────────────

def _paragrafi_html(testo):
    blocchi = [b.strip() for b in (testo or '').replace('\r', '').split('\n\n')]
    out = []
    for b in blocchi:
        if not b:
            continue
        righe = [_html.escape(r) for r in b.split('\n')]
        if all(r.startswith('- ') or r.startswith('• ') for r in righe):
            out.append('<ul style="margin:0 0 14px 18px;padding:0;">%s</ul>' % ''.join(
                '<li style="margin:3px 0;">%s</li>' % r[2:] for r in righe))
        else:
            out.append('<p style="margin:0 0 14px;">%s</p>' % '<br>'.join(righe))
    return '\n'.join(out)


def html_email(com, user, base_url=None):
    valori = valori_segnaposto(user, com, base_url)
    oggetto = rendi(com.oggetto, valori)
    corpo = _paragrafi_html(rendi(com.corpo, valori))
    if com.pulsante_testo and com.pulsante_link:
        corpo += _bottone(_html.escape(rendi(com.pulsante_testo, valori)),
                          rendi(com.pulsante_link, valori))
    base = base_url or indirizzo_base()
    link_stop = '%s/comunicazioni/disiscriviti/%s' % (base, token_disiscrizione(user))
    corpo += ('<p style="margin:26px 0 0;font-size:12px;color:#8b9099;line-height:1.6;">'
              'Ricevi questa email perché sei registrato su %s. Gli avvisi di servizio '
              '(ordine pronto, promemoria) arrivano comunque. '
              '<a href="%s" style="color:#8b9099;">Non voglio più ricevere le comunicazioni</a>.'
              '</p>' % (_html.escape(valori['locale']), link_stop))
    return oggetto, _guscio_email(_html.escape(oggetto), corpo)


def testo_telegram(com, user, base_url=None):
    valori = valori_segnaposto(user, com, base_url)
    testo = '<b>%s</b>\n\n%s' % (_html.escape(rendi(com.oggetto, valori)),
                                 _html.escape(rendi(com.corpo, valori)).strip())
    if com.pulsante_testo and com.pulsante_link:
        testo += '\n\n<a href="%s">%s →</a>' % (rendi(com.pulsante_link, valori),
                                                _html.escape(rendi(com.pulsante_testo, valori)))
    return testo


def canali_per(user, com):
    """I canali su cui scrivere a questo cliente per questa campagna, e il
    motivo se nessuno: ([canali], motivo)."""
    ha_tg = bool((user.telegram_chat_id or '').strip()) and bool(get_setting('telegram_bot_token'))
    ha_email = bool((user.email or '').strip())
    c = com.canale or 'auto'
    if c == 'email':
        return (['email'], '') if ha_email else ([], 'senza email')
    if c == 'telegram':
        return (['telegram'], '') if ha_tg else ([], 'Telegram non collegato')
    if c == 'entrambi':
        canali = [x for x, ok in (('email', ha_email), ('telegram', ha_tg)) if ok]
        return (canali, '' if canali else 'nessun canale')
    # auto: rispetta la preferenza del cliente
    pref = user.canale_preferito or 'auto'
    if pref == 'email':
        return (['email'], '') if ha_email else ([], 'senza email')
    if pref == 'telegram':
        return (['telegram'], '') if ha_tg else ([], 'Telegram non collegato')
    if ha_tg:
        return ['telegram'], ''
    if ha_email:
        return ['email'], ''
    return [], 'nessun canale'


def invia(com, base_url=None, utenti=None, prova_per=None):
    """Invia la campagna. Con `prova_per` manda solo a quell'utente e non
    registra nulla. Ritorna il riepilogo {'email', 'telegram', 'saltati',
    'falliti', 'dettagli': [...]}. Chi chiama fa il commit."""
    base_url = base_url or indirizzo_base()
    esito = {'email': 0, 'telegram': 0, 'saltati': 0, 'falliti': 0, 'dettagli': []}
    if prova_per is not None:
        lista = [prova_per]
    elif utenti is not None:
        lista = utenti
    else:
        lista = destinatari(com.segmento or 'tutti', com.tenant_id)

    for u in lista:
        canali, motivo = canali_per(u, com)
        if prova_per is not None and not canali and (u.email or '').strip():
            canali, motivo = ['email'], ''       # la prova al gestore va sempre per email
        if not canali:
            esito['saltati'] += 1
            esito['dettagli'].append((u, 'saltato', motivo))
            if prova_per is None:
                db.session.add(ComunicazioneInvio(comunicazione_id=com.id, user_id=u.id,
                                                  canale='-', esito='saltato', dettaglio=motivo))
            continue
        for canale in canali:
            if canale == 'telegram':
                ok, msg = send_telegram_to_user(u, testo_telegram(com, u, base_url))
            else:
                oggetto, corpo = html_email(com, u, base_url)
                ok, msg = send_email(u.email, oggetto, corpo)
            if ok:
                esito[canale] += 1
            else:
                esito['falliti'] += 1
            esito['dettagli'].append((u, canale if ok else 'fallito', '' if ok else msg))
            if prova_per is None:
                db.session.add(ComunicazioneInvio(
                    comunicazione_id=com.id, user_id=u.id, canale=canale,
                    esito='ok' if ok else 'fallito', dettaglio=(msg or '')[:200] if not ok else ''))
    if prova_per is None:
        com.n_email = (com.n_email or 0) + esito['email']
        com.n_telegram = (com.n_telegram or 0) + esito['telegram']
        com.n_saltati = (com.n_saltati or 0) + esito['saltati']
        com.n_falliti = (com.n_falliti or 0) + esito['falliti']
        com.stato = 'inviata'
        com.inviata_il = datetime.utcnow()
    return esito


def nuova_da_modello(chiave, tenant_id, poll=None, creata_da=None):
    """Una Comunicazione (non salvata) precompilata dal modello."""
    m = MODELLI_MAP.get(chiave) or MODELLI_MAP['libero']
    com = Comunicazione(tenant_id=tenant_id, titolo=m[1], modello=m[0], oggetto=m[4],
                        corpo=m[5], pulsante_testo=m[6], pulsante_link=m[7],
                        segmento=m[8], canale=m[9], creata_da=creata_da)
    if poll is not None:
        com.poll = poll
        com.poll_id = poll.id
        if chiave == 'sondaggio':
            com.titolo = 'Invito a votare: %s' % poll.title
    return com


# ── Automatismi ─────────────────────────────────────────────────────────────

# (chiave impostazione, modello, etichetta, descrizione)
AUTOMATISMI = [
    ('com_auto_benvenuto',  'benvenuto',  'Benvenuto dopo 7 giorni',
     'A chi si è iscritto una settimana fa e non ha ancora ricevuto il benvenuto.'),
    ('com_auto_compleanno', 'compleanno', 'Auguri di compleanno',
     'Il giorno del compleanno, una volta l\'anno.'),
    ('com_auto_ci_manchi',  'ci_manchi',  '"Ci manchi" dopo 30 giorni',
     'A chi non ordina da 30-45 giorni, non più di una volta ogni due mesi.'),
]


def automatismo_attivo(chiave):
    return (get_setting(chiave) or '0') == '1'


def _ha_ricevuto(user_id, modello, da=None):
    q = (ComunicazioneInvio.query.join(Comunicazione)
         .filter(ComunicazioneInvio.user_id == user_id, Comunicazione.modello == modello,
                 ComunicazioneInvio.esito == 'ok'))
    if da is not None:
        q = q.filter(ComunicazioneInvio.inviato_il >= da)
    return q.first() is not None


def candidati_automatismo(modello, tenant_id, oggi):
    utenti = _base_clienti(tenant_id)
    if modello == 'benvenuto':
        inizio = datetime.combine(oggi - timedelta(days=7), datetime.min.time())
        return [u for u in utenti if u.created_at and inizio - timedelta(days=7) <= u.created_at < inizio + timedelta(days=1)
                and not _ha_ricevuto(u.id, 'benvenuto')]
    if modello == 'compleanno':
        return [u for u in utenti if u.birth_date and (u.birth_date.month, u.birth_date.day) == (oggi.month, oggi.day)
                and not _ha_ricevuto(u.id, 'compleanno', datetime.combine(oggi - timedelta(days=300), datetime.min.time()))]
    if modello == 'ci_manchi':
        ultimi = _ultimi_ordini([u.id for u in utenti])
        return [u for u in utenti if ultimi.get(u.id)
                and 30 <= (oggi - ultimi[u.id]).days <= 45
                and not _ha_ricevuto(u.id, 'ci_manchi', datetime.combine(oggi - timedelta(days=60), datetime.min.time()))]
    return []


def _imposta(chiave, valore, etichetta):
    riga = AppSetting.query.filter_by(key=chiave).first()
    if riga:
        riga.value = valore
    else:
        db.session.add(AppSetting(key=chiave, value=valore, label=etichetta))


def esegui_programmate(adesso_locale, base_url=None):
    """Spedisce le campagne programmate la cui ora è passata."""
    naive = adesso_locale.replace(tzinfo=None)
    dovute = Comunicazione.query.filter(Comunicazione.stato == 'programmata',
                                        Comunicazione.programmata_il != None,  # noqa: E711
                                        Comunicazione.programmata_il <= naive).all()
    for com in dovute:
        invia(com, base_url)
    if dovute:
        db.session.commit()
    return len(dovute)


def esegui_automatismi(adesso=None, base_url=None):
    """Una volta al giorno, dopo `comunicazioni_ora`: prima le programmate,
    poi gli automatismi accesi. Ritorna il numero di campagne create."""
    from app.orari import ora_locale, leggi_orari
    now = ora_locale(adesso)
    orari = leggi_orari()
    esegui_programmate(now, base_url)
    if now.time() < orari['comunicazioni_ora']:
        return 0
    oggi = now.date()
    if (get_setting('comunicazioni_auto_il') or '') == oggi.isoformat():
        return 0
    creati = 0
    from app.tenancy import tenant_corrente
    tid = tenant_corrente()
    tenants = [db.session.get(Tenant, tid)] if tid else Tenant.query.all()
    for tenant in tenants:
        if tenant is None:
            continue
        for chiave, modello, etichetta, _d in AUTOMATISMI:
            if not automatismo_attivo(chiave):
                continue
            utenti = candidati_automatismo(modello, tenant.id, oggi)
            if not utenti:
                continue
            com = nuova_da_modello(modello, tenant.id)
            com.automatica = True
            com.titolo = '%s (automatico %s)' % (etichetta, oggi.strftime('%d/%m/%Y'))
            db.session.add(com)
            db.session.flush()
            invia(com, base_url, utenti=utenti)
            creati += 1
    _imposta('comunicazioni_auto_il', oggi.isoformat(), 'Ultimo giro delle comunicazioni automatiche')
    db.session.commit()
    return creati
