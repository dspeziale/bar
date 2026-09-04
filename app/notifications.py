import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# json serve in entrambi i rami: reply_markup viaggia come stringa JSON
# anche quando la chiamata la fa requests. Lasciarlo nel solo ramo di
# ripiego era un NameError silenzioso su ogni messaggio coi bottoni.
import json as _json

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    import urllib.request as _urllib_req
    import urllib.parse as _urllib_parse
    _HAS_REQUESTS = False


def get_setting(key, default=''):
    """Legge un'impostazione dall'AppSetting table."""
    from app.models import AppSetting
    s = AppSetting.query.filter_by(key=key).first()
    return (s.value or default) if s else default


def get_numeric_setting(key, default):
    """Legge un'impostazione numerica dal DB con fallback al default (int o float)."""
    val = get_setting(key)
    if not val:
        return default
    try:
        return int(float(val)) if isinstance(default, int) else float(val)
    except (ValueError, TypeError):
        return default


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text, reply_markup=None):
    """Invia un messaggio HTML al canale/gruppo Telegram configurato.

    Con `reply_markup` il messaggio porta i bottoni inline: e' cosi' che la
    domanda di prova chiede una risposta a chi la riceve.
    """
    token   = get_setting('telegram_bot_token')
    chat_id = get_setting('telegram_chat_id')
    if not token or not chat_id:
        return False, 'Token o Chat ID Telegram non configurati'
    url     = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    try:
        if _HAS_REQUESTS:
            if reply_markup:
                payload['reply_markup'] = reply_markup
            r = _requests.post(url, json=payload, timeout=8)
            data = r.json()
            if r.ok and data.get('ok'):
                return True, 'Messaggio inviato'
            return False, data.get('description', 'Errore Telegram')
        else:
            if reply_markup:
                # urlencode non sa annidare: i bottoni vanno come JSON.
                payload['reply_markup'] = _json.dumps(reply_markup)
            body = _urllib_parse.urlencode(payload).encode()
            req  = _urllib_req.Request(url, data=body)
            resp = _urllib_req.urlopen(req, timeout=8)
            data = _json.loads(resp.read())
            if data.get('ok'):
                return True, 'Messaggio inviato'
            return False, data.get('description', 'Errore Telegram')
    except Exception as exc:
        return False, str(exc)


BOT_PREDEFINITO = 'dslunch_bot'

# Documento che accompagna l'email di benvenuto: la guida del cliente, la
# sola scritta per lui. Il PDF e' versionato (lo produce
# docs/genera_pdf_manuali.py): in produzione non c'e' modo di convertire un
# .docx al momento dell'invio.
MANUALE_BENVENUTO = 'guida_cliente.pdf'


def percorso_manuale_benvenuto():
    """Percorso del PDF da allegare, o '' se non e' stato generato."""
    import os as _os
    base = _os.path.dirname(_os.path.abspath(__file__))
    percorso = _os.path.join(base, 'static', 'docs', MANUALE_BENVENUTO)
    return percorso if _os.path.isfile(percorso) else ''


def nome_bot():
    """Nome utente del bot, senza @ (impostabile in Impostazioni)."""
    return (get_setting('telegram_bot_username') or BOT_PREDEFINITO).lstrip('@')


def _serializzatore_collegamento():
    from flask import current_app
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(current_app.config['SECRET_KEY'],
                             salt='telegram-link')


def token_collegamento(user):
    """Token firmato che identifica l'utente nel deep link del bot.

    Sta nei 64 caratteri ammessi dal parametro start di Telegram e non
    richiede colonne nuove: e' l'id utente firmato con la SECRET_KEY.
    """
    return _serializzatore_collegamento().dumps(int(user.id))


def utente_da_token(token):
    """L'utente dietro un token di collegamento, o None se non e' valido."""
    from app.models import User
    try:
        uid = int(_serializzatore_collegamento().loads(token))
    except Exception:
        return None
    return User.query.get(uid)


def link_collegamento_bot(user):
    """Indirizzo da mettere nell'email: un clic e il Telegram e' collegato."""
    return 'https://t.me/%s?start=%s' % (nome_bot(), token_collegamento(user))


# ── Collegamento del bot senza webhook ───────────────────────────────────────
#
# Chiedere al cliente il proprio "ID Telegram" non funziona: il bot puo'
# rispondere solo se il webhook e' registrato, cosa che richiede HTTPS e
# un'attivazione manuale. Qui si fa il contrario: il cliente invia al bot un
# codice personale e l'applicazione lo cerca fra i messaggi ricevuti dal bot
# (getUpdates), ricavando da se' il chat id. Funziona sempre, anche senza
# webhook.

CARATTERI_CODICE = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # senza I, O, 0, 1


def codice_collegamento(user, rigenera=False):
    """Il codice personale da inviare al bot. Lo crea se non c'e'."""
    import secrets as _secrets
    from app import db as _db

    attuale = (getattr(user, 'telegram_link_code', '') or '').strip()
    if attuale and not rigenera:
        return attuale
    codice = 'QL-' + ''.join(_secrets.choice(CARATTERI_CODICE)
                             for _ in range(6))
    user.telegram_link_code = codice
    _db.session.commit()
    return codice


def link_avvio_bot(user):
    """Deep link che apre la chat col codice gia' scritto."""
    return 'https://t.me/%s?start=%s' % (nome_bot(),
                                         codice_collegamento(user))


def collega_telegram_da_messaggi(user):
    """Cerca il codice dell'utente fra i messaggi arrivati al bot.

    Ritorna (ok, messaggio). Non richiede il webhook: usa getUpdates, che
    Telegram consente solo quando il webhook NON e' attivo — se lo e', il
    collegamento e' gia' avvenuto da se' e lo si verifica sul database.
    """
    from app import db as _db

    codice = codice_collegamento(user)
    ok, risultato = telegram_api('getUpdates', {'limit': 100, 'timeout': 0})

    if not ok:
        testo = str(risultato).lower()
        if 'webhook is active' in testo or 'conflict' in testo:
            if (getattr(user, 'telegram_chat_id', '') or '').strip():
                return True, 'Telegram e collegato.'
            return False, ('Apri il bot e premi Avvia: il collegamento '
                           'avviene da se, poi ricarica questa pagina.')
        return False, 'Telegram non risponde: %s' % risultato

    for aggiornamento in reversed(risultato or []):
        messaggio = (aggiornamento.get('message')
                     or aggiornamento.get('edited_message') or {})
        testo = (messaggio.get('text') or '').upper()
        if codice.upper() not in testo:
            continue
        chat = (messaggio.get('chat') or {}).get('id')
        if not chat:
            continue
        user.telegram_chat_id = str(chat)
        _db.session.commit()
        telegram_api('sendMessage', {
            'chat_id': chat,
            'text': ('Telegram collegato, %s! Da adesso ricevi qui gli '
                     'avvisi degli ordini e i promemoria del pasto.'
                     % user.display_name),
        })
        return True, 'Telegram collegato.'

    return False, ('Non ho ancora ricevuto il tuo codice. Apri il bot, '
                   'premi Avvia e invia il codice, poi riprova.')


def telegram_api(metodo, payload):
    """Chiama un metodo dell'API del bot. Ritorna (ok, dati_o_errore).

    Serve ai metodi diversi da sendMessage — rispondere a un bottone,
    riscrivere un messaggio, registrare il webhook — che prima non
    esistevano.
    """
    token = get_setting('telegram_bot_token')
    if not token:
        return False, 'Token Telegram non configurato'
    url = f'https://api.telegram.org/bot{token}/{metodo}'
    dati = dict(payload or {})
    # reply_markup viaggia come stringa JSON: e' l'unica forma accettata
    # anche dalla chiamata urlencoded di ripiego.
    if isinstance(dati.get('reply_markup'), (dict, list)):
        dati['reply_markup'] = _json.dumps(dati['reply_markup'])
    try:
        if _HAS_REQUESTS:
            r = _requests.post(url, json=dati, timeout=8)
            risposta = r.json()
        else:
            body = _urllib_parse.urlencode(dati).encode()
            req = _urllib_req.Request(url, data=body)
            risposta = _json.loads(_urllib_req.urlopen(req, timeout=8).read())
        if risposta.get('ok'):
            return True, risposta.get('result', {})
        return False, risposta.get('description', 'Errore Telegram')
    except Exception as exc:
        return False, str(exc)


def tastiera_conferma_pasto(booking_id):
    """I due bottoni sotto il promemoria del pasto aziendale."""
    return {'inline_keyboard': [[
        {'text': '✅ Sì, lo ritiro',
         'callback_data': 'pasto:%d:si' % booking_id},
        {'text': '❌ No, non vengo',
         'callback_data': 'pasto:%d:no' % booking_id},
    ]]}


# ── Domanda di prova: si verifica anche la direzione di ritorno ─────────────
#
# Il vecchio "messaggio di test" diceva soltanto che l'invio funziona. Ma il
# punto delicato e' la risposta: i bottoni dei promemoria arrivano sempre,
# mentre l'esito torna solo se il canale e' configurato per riportarlo. Qui
# la prova pone una domanda e poi si va a leggere che cosa e' stato
# risposto: con le risposte attive l'aggiornamento arriva sul webhook, senza
# di esse lo si recupera con getUpdates.

def tastiera_prova(codice):
    """I due bottoni della domanda di prova."""
    return {'inline_keyboard': [[
        {'text': '\U0001F44D Sì, l\u2019ho ricevuto',
         'callback_data': 'prova:%s:si' % codice},
        {'text': '\U0001F44E No', 'callback_data': 'prova:%s:no' % codice},
    ]]}


def _scrivi_impostazione(chiave, valore, etichetta=''):
    from app import db
    from app.models import AppSetting
    riga = AppSetting.query.filter_by(key=chiave).first()
    if riga:
        riga.value = valore
    else:
        db.session.add(AppSetting(key=chiave, value=valore, label=etichetta))
    db.session.commit()


def invia_domanda_prova():
    """Manda al canale dello staff una domanda con i due bottoni."""
    import secrets as _secrets
    codice = _secrets.token_hex(4)
    testo = ('\U0001F514 <b>Prova QuickLunch</b>\n'
             'Questo messaggio porta gli stessi bottoni dei promemoria del '
             'pasto.\n\n<b>Domanda: lo hai ricevuto?</b>\n'
             'Rispondi con un tocco, poi in QuickLunch premi '
             '<i>Leggi la risposta</i>.')
    ok, msg = send_telegram(testo, reply_markup=tastiera_prova(codice))
    if not ok:
        return False, msg
    _scrivi_impostazione('telegram_prova_codice', codice,
                         'Domanda di prova Telegram in corso')
    _scrivi_impostazione('telegram_prova_risposta', '',
                         'Risposta alla domanda di prova')
    _scrivi_impostazione('telegram_prova_chi', '',
                         'Chi ha risposto alla domanda di prova')
    return True, ('Domanda inviata su Telegram. Rispondi col bottone, poi '
                  'premi "Leggi la risposta".')


def registra_risposta_prova(codice, valore, chi=''):
    """Annota la risposta arrivata. Ritorna True se era la prova in corso."""
    if valore not in ('si', 'no'):
        return False
    atteso = get_setting('telegram_prova_codice')
    if not atteso or codice != atteso:
        return False
    _scrivi_impostazione('telegram_prova_risposta', valore)
    _scrivi_impostazione('telegram_prova_chi', (chi or '')[:60])
    return True


def leggi_risposta_prova():
    """Che cosa e' stato risposto alla domanda di prova.

    Ritorna (stato, dettaglio) con stato fra 'assente', 'attesa', 'si', 'no'.
    """
    codice = get_setting('telegram_prova_codice')
    if not codice:
        return 'assente', 'Nessuna domanda di prova da controllare.'

    risposta = get_setting('telegram_prova_risposta')
    if risposta in ('si', 'no'):
        return risposta, get_setting('telegram_prova_chi')

    # Nessuna risposta registrata dal webhook: si guarda fra gli
    # aggiornamenti in coda, cosi' la prova funziona anche prima di
    # attivare le risposte.
    ok, risultato = telegram_api('getUpdates', {'limit': 100, 'timeout': 0})
    if not ok:
        testo = str(risultato)
        if 'webhook' in testo.lower() or 'conflict' in testo.lower():
            return 'attesa', ('Le risposte passano dal webhook: se hai '
                              'appena premuto il bottone riprova fra qualche '
                              'secondo.')
        return 'attesa', testo

    atteso = 'prova:%s:' % codice
    for aggiornamento in (risultato or []):
        callback = (aggiornamento or {}).get('callback_query') or {}
        dati = (callback.get('data') or '').strip()
        if not dati.startswith(atteso):
            continue
        valore = dati.rsplit(':', 1)[-1]
        chi = ((callback.get('from') or {}).get('first_name') or '').strip()
        if registra_risposta_prova(codice, valore, chi):
            return valore, chi
    return 'attesa', 'Non e ancora arrivata nessuna risposta.'


def stato_webhook(url_attesa=''):
    """Che cosa dice Telegram del webhook registrato.

    Ritorna url registrato, se combacia con quello di questa applicazione,
    aggiornamenti in coda ed eventuale errore di consegna: sono i fatti che
    spiegano perché una risposta non torna. Chiederli a Telegram è l'unico
    modo di distinguere "nessuno ha premuto" da "non riesco a consegnare".
    """
    ok, info = telegram_api('getWebhookInfo', {})
    if not ok:
        return {'errore': str(info)}
    info = info if isinstance(info, dict) else {}
    url = (info.get('url') or '').strip()
    return {
        'errore': '',
        'url': url,
        'attivo': bool(url),
        'combacia': (not url_attesa) or (url == url_attesa),
        'in_coda': info.get('pending_update_count') or 0,
        'ultimo_errore': (info.get('last_error_message') or '').strip(),
    }


def motivo_mancata_risposta(url_attesa=''):
    """Una frase che dice perché la risposta alla prova non è tornata."""
    w = stato_webhook(url_attesa)
    if w.get('errore'):
        return 'Telegram non risponde: %s' % w['errore']
    if not w['attivo']:
        return ('Le risposte ai bottoni non sono attive: premi "Attiva le '
                'risposte ai bottoni" qui sopra, poi rifai la prova.')
    if w['ultimo_errore']:
        return ('Telegram non riesce a consegnare le risposte: "%s". '
                'Ripeti la registrazione.' % w['ultimo_errore'])
    if url_attesa and not w['combacia']:
        return ('Il webhook registrato punta a un altro indirizzo (%s): '
                'ripeti la registrazione.' % w['url'])
    if w['in_coda']:
        return ('Ci sono %d aggiornamenti in coda non ancora consegnati: '
                'riprova fra qualche secondo.' % w['in_coda'])
    return ('Il canale risulta configurato: se hai premuto il bottone '
            'adesso, riprova fra qualche secondo.')


def diagnostica_canale(url_attesa=''):
    """Le righe della pagina di diagnostica del canale Telegram."""
    righe = []

    def riga(voce, valore, stato='info', nota=''):
        righe.append({'voce': voce, 'valore': valore, 'stato': stato,
                      'nota': nota})

    token = get_setting('telegram_bot_token')
    riga('Token del bot', 'configurato' if token else 'mancante',
         'ok' if token else 'ko',
         '' if token else 'Senza token non parte nessun messaggio.')
    if not token:
        return righe

    ok, me = telegram_api('getMe', {})
    nome = ('@%s' % (me or {}).get('username', '')) if ok else str(me)
    riga('Bot raggiunto', nome, 'ok' if ok else 'ko',
         '' if ok else 'Token non valido, o rete non raggiungibile.')

    chat = get_setting('telegram_chat_id')
    riga('Canale dello staff', chat or 'mancante', 'ok' if chat else 'ko',
         '' if chat else 'È la chat su cui arrivano gli avvisi e la prova.')

    w = stato_webhook(url_attesa)
    if w.get('errore'):
        riga('Risposte ai bottoni', 'non verificabili', 'ko', w['errore'])
        return righe

    if not w['attivo']:
        riga('Risposte ai bottoni', 'non attive', 'ko',
             'Il "No" del cliente sul promemoria non annulla nulla. Le '
             'risposte alla domanda di prova si recuperano comunque, '
             'leggendo i messaggi in attesa.')
    else:
        riga('Risposte ai bottoni', 'attive', 'ok')
        riga('Indirizzo registrato', w['url'],
             'ok' if w['combacia'] else 'ko',
             '' if w['combacia'] else
             'Diverso da quello di questa applicazione (%s): finché resta '
             'così le risposte vanno altrove. Ripeti la registrazione.'
             % url_attesa)
        riga('Aggiornamenti in coda', str(w['in_coda']),
             'ok' if not w['in_coda'] else 'info',
             '' if not w['in_coda'] else
             'Telegram li sta ancora consegnando.')
        if w['ultimo_errore']:
            riga('Ultimo errore di consegna', w['ultimo_errore'], 'ko',
                 'Telegram ha provato a consegnare e non ci è riuscito.')

    if not w['attivo']:
        ok, aggiornamenti = telegram_api('getUpdates',
                                         {'limit': 100, 'timeout': 0})
        if not ok:
            riga('Messaggi in attesa', 'non leggibili', 'ko',
                 str(aggiornamenti))
        else:
            elenco = aggiornamenti or []
            premuti = [a for a in elenco if (a or {}).get('callback_query')]
            riga('Messaggi in attesa', str(len(elenco)))
            riga('Bottoni premuti in attesa', str(len(premuti)),
                 'ok' if premuti else 'info',
                 '' if premuti else
                 'Nessuno ha premuto un bottone, oppure la risposta è già '
                 'stata letta.')

    codice = get_setting('telegram_prova_codice')
    risposta = get_setting('telegram_prova_risposta')
    riga('Domanda di prova', codice or 'nessuna inviata')
    riga('Risposta alla prova',
         {'si': 'Sì', 'no': 'No'}.get(risposta, 'non ancora arrivata'),
         'ok' if risposta else 'info',
         '' if risposta else motivo_mancata_risposta(url_attesa)
         if codice else '')
    return righe


def send_telegram_to_user(user, text, reply_markup=None):
    """Invia un messaggio Telegram direttamente all'utente tramite il suo chat_id personale.

    Con `reply_markup` (vedi tastiera_conferma_pasto) il messaggio porta i
    bottoni su cui l'utente puo' rispondere.
    """
    token   = get_setting('telegram_bot_token')
    chat_id = getattr(user, 'telegram_chat_id', None)
    if not token or not chat_id:
        return False, 'Token o Telegram Chat ID utente non disponibili'
    url     = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = _json.dumps(reply_markup)
    try:
        if _HAS_REQUESTS:
            r    = _requests.post(url, json=payload, timeout=8)
            data = r.json()
            if r.ok and data.get('ok'):
                return True, 'Messaggio inviato'
            return False, data.get('description', 'Errore Telegram')
        else:
            body = _urllib_parse.urlencode(payload).encode()
            req  = _urllib_req.Request(url, data=body)
            resp = _urllib_req.urlopen(req, timeout=8)
            data = _json.loads(resp.read())
            if data.get('ok'):
                return True, 'Messaggio inviato'
            return False, data.get('description', 'Errore Telegram')
    except Exception as exc:
        return False, str(exc)


# ── Web Push ──────────────────────────────────────────────────────────────────

def _get_or_create_vapid_keys():
    """Restituisce (private_pem, public_b64url). Genera le chiavi VAPID al primo utilizzo."""
    from app.models import AppSetting
    from app import db
    priv = get_setting('vapid_private_key')
    pub  = get_setting('vapid_public_key')
    if priv and pub:
        return priv, pub
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        import base64
        pk = ec.generate_private_key(ec.SECP256R1())
        priv_pem = pk.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()
        ).decode()
        pub_bytes = pk.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode()
        for key, val in [('vapid_private_key', priv_pem), ('vapid_public_key', pub_b64)]:
            s = AppSetting.query.filter_by(key=key).first()
            if s:
                s.value = val
            else:
                db.session.add(AppSetting(key=key, value=val))
        db.session.commit()
        return priv_pem, pub_b64
    except Exception:
        return None, None


def send_web_push_to_user(user, title, body, url='/prenotazioni'):
    """Invia una notifica Web Push a tutti i browser registrati dell'utente."""
    import os, tempfile, json
    from flask import current_app
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        current_app.logger.warning('send_web_push_to_user: pywebpush non installato')
        return
    try:
        from app.models import PushSubscription
        from app import db
        priv, _ = _get_or_create_vapid_keys()
        if not priv:
            current_app.logger.warning('send_web_push_to_user: chiavi VAPID non disponibili')
            return
        vapid_email = get_setting('company_email') or 'admin@quicklunch.local'
        subs = PushSubscription.query.filter_by(user_id=user.id).all()
        if not subs:
            current_app.logger.debug(f'send_web_push_to_user: nessuna subscription per user_id={user.id}')
            return
        # pywebpush 2.x vuole un percorso file PEM, non la stringa PEM diretta
        fd, key_path = tempfile.mkstemp(suffix='.pem')
        try:
            os.write(fd, priv.encode('utf-8'))
            os.close(fd)
            dead = []
            for sub in subs:
                try:
                    webpush(
                        subscription_info={
                            'endpoint': sub.endpoint,
                            'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}
                        },
                        data=json.dumps({'title': title, 'body': body, 'url': url}),
                        vapid_private_key=key_path,
                        vapid_claims={'sub': f'mailto:{vapid_email}'}
                    )
                    current_app.logger.info(f'Web push OK → user_id={user.id} sub_id={sub.id}')
                except WebPushException as ex:
                    current_app.logger.warning(f'WebPushException sub_id={sub.id}: {ex}')
                    if ex.response and ex.response.status_code in (404, 410):
                        dead.append(sub.id)
                except Exception as ex:
                    current_app.logger.error(f'WebPush errore sub_id={sub.id}: {ex}', exc_info=True)
        finally:
            try:
                os.unlink(key_path)
            except OSError:
                pass
        if dead:
            PushSubscription.query.filter(
                PushSubscription.id.in_(dead)
            ).delete(synchronize_session=False)
            db.session.commit()
    except Exception as ex:
        current_app.logger.error(f'send_web_push_to_user: errore generico: {ex}', exc_info=True)


def telegram_poll_message(poll, base_url):
    """Formatta il messaggio Telegram per un sondaggio."""
    choices = '\n'.join(
        f'{c.emoji}  <b>{c.text}</b>'
        for c in poll.choices
    )
    link = f'{base_url}/poll/{poll.id}'
    return (
        f'📊 <b>Sondaggio: {poll.title}</b>\n'
        f'Per il <b>{poll.poll_date.strftime("%d/%m/%Y")}</b>\n\n'
        f'{choices}\n\n'
        f'👉 <a href="{link}">Vota qui</a>'
    )


# ── Gmail ─────────────────────────────────────────────────────────────────────

def send_email(to_addr, subject, html_body, text_body=None, allegati=None):
    """Invia un'email HTML tramite Gmail SMTP (App Password).

    `allegati` e' una lista di percorsi: quelli assenti o illeggibili vengono
    ignorati, perche' un allegato mancante non deve impedire l'invio.
    """
    import mimetypes
    import os as _os
    from email.mime.base import MIMEBase
    from email import encoders as _encoders

    gmail_user = get_setting('gmail_user')
    gmail_pass = get_setting('gmail_app_password')
    if not gmail_user or not gmail_pass:
        return False, 'Gmail non configurata'
    if not to_addr:
        return False, 'Destinatario mancante'
    try:
        # Con un allegato la struttura e' mixed, con testo e HTML in un ramo
        # alternative: altrimenti alcuni client mostrano l'HTML come file.
        corpo = MIMEMultipart('alternative')
        if text_body:
            corpo.attach(MIMEText(text_body, 'plain'))
        corpo.attach(MIMEText(html_body, 'html'))

        percorsi = [p for p in (allegati or []) if p and _os.path.isfile(p)]
        if percorsi:
            msg = MIMEMultipart('mixed')
            msg.attach(corpo)
        else:
            msg = corpo
        msg['Subject'] = subject
        msg['From']    = f'QuickLunch Ufficio <{gmail_user}>'
        msg['To']      = to_addr
        for percorso in percorsi:
            tipo, _ = mimetypes.guess_type(percorso)
            principale, _, secondario = (tipo or 'application/octet-stream'
                                         ).partition('/')
            parte = MIMEBase(principale, secondario or 'octet-stream')
            with open(percorso, 'rb') as f:
                parte.set_payload(f.read())
            _encoders.encode_base64(parte)
            parte.add_header('Content-Disposition', 'attachment',
                             filename=_os.path.basename(percorso))
            msg.attach(parte)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ctx) as srv:
            srv.login(gmail_user, gmail_pass)
            srv.send_message(msg)
        return True, 'Email inviata'
    except Exception as exc:
        return False, str(exc)


def send_supplier_low_stock_alert(item):
    """Invia email al fornitore quando la giacenza scende sotto la soglia minima."""
    from app import numero_italiano

    if not item.supplier or not item.supplier.email:
        return False, 'Fornitore senza email configurata'
    subject = f'[QuickLunch] ⚠️ Riordino necessario: {item.name}'
    html = f"""
<div style="font-family:sans-serif;max-width:560px;margin:auto;padding:0;">
  <div style="background:#e94560;color:#fff;padding:16px 24px;border-radius:8px 8px 0 0;">
    <h2 style="margin:0;font-size:20px;">⚠️ Scorte sotto soglia minima</h2>
  </div>
  <div style="border:1px solid #eee;border-top:none;padding:20px 24px;border-radius:0 0 8px 8px;">
    <p>Gentile <strong>{item.supplier.name}</strong>,</p>
    <p>il materiale <strong>{item.name}</strong> ha raggiunto la soglia minima di riordino.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px;">
      <tr style="background:#f5f5f5;">
        <td style="padding:8px 12px;font-weight:bold;border:1px solid #eee;">Materiale</td>
        <td style="padding:8px 12px;border:1px solid #eee;">{item.name}</td>
      </tr>
      <tr>
        <td style="padding:8px 12px;font-weight:bold;border:1px solid #eee;">Giacenza attuale</td>
        <td style="padding:8px 12px;border:1px solid #eee;color:#e94560;font-weight:bold;">{numero_italiano(item.quantity, 1)} {item.unit}</td>
      </tr>
      <tr style="background:#f5f5f5;">
        <td style="padding:8px 12px;font-weight:bold;border:1px solid #eee;">Soglia minima</td>
        <td style="padding:8px 12px;border:1px solid #eee;">{numero_italiano(item.min_threshold, 1)} {item.unit}</td>
      </tr>
    </table>
    <p>Si prega di procedere con il rifornimento al più presto.</p>
    <p style="margin-top:24px;color:#aaa;font-size:11px;">
      Messaggio automatico generato da QuickLunch &mdash; Bar Self-Service
    </p>
  </div>
</div>"""
    ok, msg = send_email(item.supplier.email, subject, html)
    if ok:
        from datetime import datetime as _dt
        from app import db as _db
        item.last_alert_at = _dt.utcnow()
        item.alert_active  = True
        _db.session.commit()
    return ok, msg


def send_reminder_to_user(user, text, subject='Promemoria',
                          reply_markup=None):
    """Promemoria all'utente sul canale disponibile: Telegram, altrimenti email.

    `text` e' nel formato dei messaggi Telegram (HTML minimale con <b> e ritorni
    a capo): per l'email i ritorni a capo diventano <br>.

    Ritorna (inviato, canale_o_errore). Chi chiama deve alzare il proprio flag
    "promemoria inviato" solo se il primo valore e' True, altrimenti il
    promemoria andrebbe perso.
    """
    import re as _re

    chat_id = (getattr(user, 'telegram_chat_id', '') or '').strip()
    if chat_id and get_setting('telegram_bot_token'):
        ok, msg = send_telegram_to_user(user, text, reply_markup=reply_markup)
        return (True, 'telegram') if ok else (False, 'telegram: %s' % msg)

    # Telegram non configurato per questo utente: si ripiega sull'email.
    if not getattr(user, 'email', ''):
        return False, 'nessun canale disponibile'

    co_name = get_setting('company_name') or 'QuickLunch'
    corpo   = text.replace('\n', '<br>')
    if reply_markup:
        # I bottoni di conferma esistono solo su Telegram: via email si
        # indirizza l'utente dove puo' fare la stessa cosa.
        corpo += ('<br><br>Se non puoi ritirarlo, annulla la prenotazione '
                  'dalla pagina Pasto Aziendale: la cucina non lo prepara.')
    testo   = _re.sub(r'<[^>]+>', '', text)
    html = f"""
<div style="font-family:sans-serif;max-width:560px;margin:auto;padding:0;">
  <div style="background:#e94560;color:#fff;padding:14px 24px;border-radius:8px 8px 0 0;">
    <h2 style="margin:0;font-size:18px;">{subject}</h2>
  </div>
  <div style="border:1px solid #eee;border-top:none;padding:20px 24px;border-radius:0 0 8px 8px;">
    <p style="font-size:15px;line-height:1.6;">{corpo}</p>
    <p style="margin-top:24px;color:#aaa;font-size:11px;">
      Ricevi questo promemoria per email perche' il tuo Telegram non e' collegato.
      Puoi collegarlo dal tuo profilo su {co_name}.
    </p>
  </div>
</div>"""
    ok, msg = send_email(user.email, f'[{co_name}] {subject}', html, testo)
    return (True, 'email') if ok else (False, 'email: %s' % msg)


# ── Email al cliente: impianto comune ────────────────────────────────────────
#
# Stessa grafica delle guide: banda navy in testa, filetto rosso, titoli
# navy, corpo grigio scuro. Tutto allineato a sinistra: le email centrate
# risultano deformi appena il testo va a capo, e i client di posta ignorano
# meta' del CSS, percio' l'allineamento e' scritto su ogni blocco.

NAVY_HEX = '#0f3460'
ROSSO_HEX = '#e94560'
TESTO_HEX = '#3b4048'
GRIGIO_HEX = '#8b9099'
BORDO_HEX = '#e2e6ec'


def _guscio_email(titolo, corpo_html):
    """La cornice comune: intestazione, corpo, pie' di pagina."""
    co_name = get_setting('company_name') or 'QuickLunch'
    return """
<div style="background:#f4f6f9;padding:24px 0;margin:0;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;
              border:1px solid %(bordo)s;border-radius:10px;overflow:hidden;
              font-family:Arial,Helvetica,sans-serif;text-align:left;">

    <div style="background:%(navy)s;padding:22px 28px;text-align:left;">
      <div style="color:#b2c2d9;font-size:12px;letter-spacing:1.4px;
                  text-align:left;">QUICKLUNCH</div>
      <div style="color:#ffffff;font-size:23px;font-weight:bold;
                  padding-top:4px;text-align:left;">%(titolo)s</div>
    </div>
    <div style="height:3px;background:%(rosso)s;"></div>

    <div style="padding:26px 28px;color:%(testo)s;font-size:15px;
                line-height:1.62;text-align:left;">
%(corpo)s
    </div>

    <div style="border-top:1px solid %(bordo)s;padding:16px 28px;
                text-align:left;">
      <div style="color:%(grigio)s;font-size:12px;line-height:1.6;
                  text-align:left;">
        Messaggio automatico di %(locale)s<br>
        Assistenza: DS Consulting &middot; dspeziale@gmail.com
        &middot; +39 352 0150489
      </div>
    </div>

  </div>
</div>""" % {'titolo': titolo, 'corpo': corpo_html, 'locale': co_name,
             'navy': NAVY_HEX, 'rosso': ROSSO_HEX, 'testo': TESTO_HEX,
             'grigio': GRIGIO_HEX, 'bordo': BORDO_HEX}


def _titolo_sezione(testo):
    return ("""
      <div style="color:%s;font-size:17px;font-weight:bold;margin:26px 0 6px;
                  text-align:left;">%s</div>
      <div style="height:2px;width:44px;background:%s;margin-bottom:12px;">
      </div>""" % (NAVY_HEX, testo, ROSSO_HEX))


def _passi_html(passi):
    """Passi numerati: tabella, perche' gli elenchi <ol> nei client di posta
    rientrano in modo imprevedibile."""
    righe = []
    for numero, (titolo, dettaglio) in enumerate(passi, 1):
        righe.append("""
        <tr>
          <td style="width:26px;vertical-align:top;padding:0 10px 12px 0;
                     text-align:left;">
            <div style="width:24px;height:24px;border-radius:5px;
                        background:%s;color:#ffffff;font-size:13px;
                        font-weight:bold;text-align:center;
                        line-height:24px;">%d</div>
          </td>
          <td style="vertical-align:top;padding:0 0 12px 0;text-align:left;
                     font-size:15px;line-height:1.55;">
            <strong style="color:#1a1a2e;">%s</strong><br>%s
          </td>
        </tr>""" % (NAVY_HEX, numero, titolo, dettaglio))
    return ("""
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"
             style="width:100%%;text-align:left;">%s
      </table>""" % ''.join(righe))


def _bottone(testo, indirizzo, colore=None):
    return """
      <div style="margin:18px 0;text-align:left;">
        <a href="%s" style="background:%s;color:#ffffff;padding:12px 26px;
           border-radius:6px;text-decoration:none;font-weight:bold;
           font-size:15px;display:inline-block;">%s</a>
      </div>""" % (indirizzo, colore or ROSSO_HEX, testo)


def _riquadro(titolo, contenuto, colore=None):
    colore = colore or '#229ED9'
    return """
      <div style="margin:22px 0;border:1px solid %s;border-left:4px solid %s;
                  background:#f7fbff;border-radius:6px;padding:16px 18px;
                  text-align:left;">
        <div style="color:%s;font-weight:bold;font-size:15px;
                    margin-bottom:8px;text-align:left;">%s</div>
        <div style="font-size:14px;line-height:1.6;text-align:left;">%s</div>
      </div>""" % (BORDO_HEX, colore, NAVY_HEX, titolo, contenuto)


def indirizzo_pagina_collegamento():
    """Indirizzo assoluto della pagina che guida il collegamento del bot.

    Dentro una richiesta lo ricava url_for; fuori (invii da riga di comando)
    si usa l'indirizzo pubblico salvato in Impostazioni, se c'e'.
    """
    from flask import url_for
    try:
        return url_for('main.telegram_collega', _external=True)
    except Exception:
        base = (get_setting('public_base_url') or '').strip().rstrip('/')
        return (base + '/telegram/collega') if base else ''


def blocco_telegram_html(user):
    """Come collegare il bot: si punta alla pagina dell'app, che guida il
    cliente col suo codice. Chiedergli il proprio "ID Telegram" non
    funzionava: il bot puo' rispondere solo col webhook attivo."""
    pagina = indirizzo_pagina_collegamento()
    bot = nome_bot()
    contenuto = ("""Ti avvisiamo quando l'ordine e' pronto e ti ricordiamo il
        ritiro del pasto: dal promemoria puoi confermare o disdire con un
        tocco.%s
        <div style="font-size:13px;color:%s;line-height:1.6;text-align:left;">
          La pagina ti mostra un <strong>codice personale</strong> e il
          pulsante per aprire il bot <strong>@%s</strong>: invii il codice
          in chat e il collegamento e' fatto. Non devi cercare nessun
          numero di identificazione.
        </div>""" % (_bottone('Collega Telegram &rarr;', pagina, '#229ED9')
                     if pagina else '', GRIGIO_HEX, bot))
    return _riquadro('Vuoi gli avvisi sul telefono?', contenuto)


def blocco_telegram_testo(user):
    """La stessa cosa per la versione testuale dell'email."""
    pagina = indirizzo_pagina_collegamento()
    return ('Per ricevere gli avvisi su Telegram apri %s: trovi un codice da '
            'inviare al bot @%s e il collegamento e fatto.'
            % (pagina or 'la pagina Collega Telegram nel tuo profilo',
               nome_bot()))


def nota_guida_html():
    """Riga che nomina l'allegato, solo se l'allegato c'e' davvero."""
    if not percorso_manuale_benvenuto():
        return ''
    return """
      <div style="margin-top:22px;font-size:14px;line-height:1.6;
                  color:%s;text-align:left;">
        In allegato trovi la <strong>guida del cliente in PDF</strong>: come
        ordinare, comporre il tuo panino, pagare al banco col QR, prenotare
        il pasto aziendale e gestire le notifiche.
      </div>""" % TESTO_HEX


def avvisa_staff_email_non_inviata(user, motivo, quale='benvenuto'):
    """Dice sul canale dello staff che un'email al cliente non e' partita.

    Senza questo l'errore resta invisibile: chi si registra non riceve
    niente e nel backoffice non compare nulla. Il canale Telegram, che
    funziona anche quando Gmail non e' configurata, e' il posto giusto per
    accorgersene subito.
    """
    try:
        send_telegram(
            '⚠️ <b>Email non inviata</b> (%s)\n'
            '📧 %s\n'
            '❗ %s\n'
            'Controlla Impostazioni › Notifiche › Gmail.'
            % (quale, getattr(user, 'email', '?'), motivo))
    except Exception:
        pass


def send_registration_received_email(user):
    """Conferma al cliente che la registrazione e' arrivata, con la guida.

    Va inviata da ogni percorso di registrazione: e' il primo riscontro che
    il cliente riceve e l'unico prima che il titolare approvi l'account.
    Se l'invio non riesce lo staff viene avvisato su Telegram: un errore
    silenzioso qui significa un cliente che non sa nulla.
    """
    if not getattr(user, 'email', ''):
        return False, 'Utente senza email'

    co_name = get_setting('company_name') or 'QuickLunch'
    nome = (getattr(user, 'first_name', '') or '').strip() or user.username
    subject = '[%s] Registrazione ricevuta' % co_name
    allegato = percorso_manuale_benvenuto()

    corpo = ("""
      <div style="text-align:left;">Ciao <strong>%(nome)s</strong>,</div>
      <div style="margin-top:10px;text-align:left;">
        abbiamo ricevuto la tua registrazione su <strong>%(locale)s</strong>.
        Il tuo account e' <strong>in attesa di approvazione</strong>: appena
        il personale lo attiva ti arriva un'altra email e puoi iniziare a
        ordinare.
      </div>
      %(titolo)s
      %(passi)s
      %(guida)s%(telegram)s""" % {
        'nome': nome, 'locale': co_name,
        'titolo': _titolo_sezione('Nel frattempo'),
        'passi': _passi_html([
            ('Leggi la guida allegata',
             'Cinque minuti, e sai come ordinare, comporre il tuo piatto e '
             'ritirare.'),
            ('Collega Telegram, se vuoi',
             'Ricevi gli avvisi sul telefono invece che per email.'),
        ]),
        'guida': nota_guida_html(),
        'telegram': blocco_telegram_html(user)})

    html = _guscio_email('Registrazione ricevuta', corpo)
    text = ('Ciao %s, abbiamo ricevuto la tua registrazione su %s. '
            "L'account e' in attesa di approvazione: ti avvisiamo appena e' "
            'attivo. ' % (nome, co_name)
            + ('In allegato la guida del cliente in PDF. '
               if allegato else '')
            + blocco_telegram_testo(user))
    ok, msg = send_email(user.email, subject, html, text,
                         allegati=[allegato] if allegato else None)
    if not ok:
        avvisa_staff_email_non_inviata(user, msg, 'registrazione')
    return ok, msg


def send_account_activated_email(user, login_url=''):
    """Avvisa il cliente per email che il suo account e' stato attivato.

    L'avviso Telegram richiede che l'utente abbia collegato il proprio chat
    id, cosa che un cliente appena registrato non ha ancora fatto: l'email
    e' quindi l'unico canale che lo raggiunge davvero.
    """
    if not getattr(user, 'email', ''):
        return False, 'Utente senza email'

    co_name = get_setting('company_name') or 'QuickLunch'
    nome = (getattr(user, 'first_name', '') or '').strip() or user.username
    subject = "[%s] Il tuo account e' attivo" % co_name

    # Il passo della ricarica ha senso solo col portafoglio prepagato.
    try:
        from app import wallet_enabled as _wallet_attivo
        con_wallet = _wallet_attivo()
    except Exception:
        con_wallet = True

    passi = [('Accedi', 'Con la stessa email con cui ti sei registrato.')]
    if con_wallet:
        passi.append(('Ricarica il credito in cassa',
                      "Il portafoglio e' prepagato: il credito serve per "
                      'ordinare, e al ritiro non paghi nulla.'))
    passi.append(('Scegli dal menu',
                  "Indica l'orario di ritiro e conferma l'ordine."
                  + ('' if con_wallet else
                     ' Pagherai alla cassa quando lo ritiri.')))

    allegato = percorso_manuale_benvenuto()
    corpo = ("""
      <div style="text-align:left;">Ciao <strong>%(nome)s</strong>,</div>
      <div style="margin-top:10px;text-align:left;">
        il tuo account su <strong>%(locale)s</strong> e' attivo: da adesso
        puoi accedere, consultare il menu e ordinare.
      </div>
      %(titolo)s
      %(passi)s%(bottone)s%(guida)s%(telegram)s""" % {
        'nome': nome, 'locale': co_name,
        'titolo': _titolo_sezione('Come iniziare'),
        'passi': _passi_html(passi),
        'bottone': (_bottone('Accedi ora &rarr;', login_url)
                    if login_url else ''),
        'guida': nota_guida_html(),
        'telegram': blocco_telegram_html(user)})

    html = _guscio_email('Account attivato', corpo)
    text = ('Ciao %s, il tuo account su %s e\' stato attivato: puoi accedere '
            'e ordinare. ' % (nome, co_name)
            + ('Ricorda di ricaricare il credito in cassa. '
               if con_wallet else 'Pagherai alla cassa al ritiro. ')
            + blocco_telegram_testo(user))
    ok, msg = send_email(user.email, subject, html, text,
                         allegati=[allegato] if allegato else None)
    if not ok:
        avvisa_staff_email_non_inviata(user, msg, 'attivazione')
    return ok, msg


def send_email_to_all_users(subject, html_body):
    """Invia a tutti gli utenti attivi con email."""
    from app.models import User
    users  = User.query.filter_by(is_active=True, is_admin=False).all()
    sent   = 0
    failed = 0
    errors = []
    for u in users:
        if u.email:
            ok, msg = send_email(u.email, subject, html_body)
            if ok:
                sent += 1
            else:
                failed += 1
                errors.append(f'{u.email}: {msg}')
    return sent, failed, errors


def email_poll_html(poll, base_url):
    """Genera l'HTML email per un sondaggio."""
    choices_html = ''.join(
        f'<li style="margin:6px 0;font-size:16px;">{c.emoji} {c.text}</li>'
        for c in poll.choices
    )
    link = f'{base_url}/poll/{poll.id}'
    return f"""
<div style="font-family:sans-serif;max-width:520px;margin:auto;padding:24px;">
  <h2 style="color:#e94560;">📊 {poll.title}</h2>
  <p>Per il <strong>{poll.poll_date.strftime('%d/%m/%Y')}</strong> vota cosa vuoi mangiare:</p>
  <ul style="padding-left:20px;">{choices_html}</ul>
  <div style="margin-top:24px;">
    <a href="{link}"
       style="background:#e94560;color:#fff;padding:12px 28px;border-radius:6px;
              text-decoration:none;font-weight:bold;font-size:16px;">
      Vota ora →
    </a>
  </div>
  <p style="margin-top:24px;color:#888;font-size:12px;">
    QuickLunch Ufficio — Bar Self-Service Ristoro
  </p>
</div>
"""
