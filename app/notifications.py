import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    import urllib.request as _urllib_req
    import urllib.parse as _urllib_parse
    import json as _json
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

def send_telegram(text):
    """Invia un messaggio HTML al canale/gruppo Telegram configurato."""
    token   = get_setting('telegram_bot_token')
    chat_id = get_setting('telegram_chat_id')
    if not token or not chat_id:
        return False, 'Token o Chat ID Telegram non configurati'
    url     = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    try:
        if _HAS_REQUESTS:
            r = _requests.post(url, json=payload, timeout=8)
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


def blocco_telegram_html(user):
    """Il riquadro "Collega Telegram" delle email al cliente.

    Un pulsante che collega da se' (deep link col token firmato) e sotto la
    via manuale, per chi apre l'email dal computer.
    """
    co_name = get_setting('company_name') or 'QuickLunch'
    try:
        link_bot = link_collegamento_bot(user)
    except Exception:
        link_bot = ''
    bot = nome_bot()
    return f"""
    <div style="margin-top:22px;padding:16px 18px;background:#f5faff;
                border:1px solid #d9ecff;border-radius:8px;">
      <p style="margin:0 0 8px;font-size:15px;"><strong>
        Collega Telegram e ricevi gli avvisi sul telefono
      </strong></p>
      <p style="margin:0 0 10px;font-size:14px;line-height:1.6;">
        Ti avvisiamo quando l'ordine e' pronto e ti ricordiamo il ritiro del
        pasto: dal promemoria puoi confermare o disdire con un tocco.
      </p>
      <div style="margin:14px 0 10px;">
        <a href="{link_bot}"
           style="background:#229ED9;color:#fff;padding:11px 24px;
                  border-radius:6px;text-decoration:none;font-weight:bold;
                  font-size:15px;">
          Collega Telegram con un clic &rarr;
        </a>
      </div>
      <p style="margin:12px 0 4px;font-size:13px;color:#555;">
        <strong>Se il pulsante non funziona</strong> (per esempio apri questa
        email dal computer), fai così dal telefono:
      </p>
      <ol style="padding-left:20px;margin:6px 0;font-size:13px;color:#555;
                 line-height:1.7;">
        <li>Apri Telegram e cerca <strong>@{bot}</strong>.</li>
        <li>Apri la chat e premi <strong>Avvia</strong> (o scrivi
            <code>/start</code>).</li>
        <li>Scrivi <code>/id</code>: il bot ti risponde con il tuo
            <strong>ID Telegram</strong>, un numero come 123456789.</li>
        <li>Copia quel numero nel tuo profilo su {co_name}, nel campo
            <em>Telegram Chat ID</em>, e salva.</li>
      </ol>
      <p style="margin:8px 0 0;font-size:12px;color:#888;">
        Il collegamento e' facoltativo: senza Telegram continuerai a
        ricevere gli avvisi per email.
      </p>
    </div>"""


def blocco_telegram_testo(user):
    """La stessa cosa per la versione testuale dell'email."""
    try:
        link_bot = link_collegamento_bot(user)
    except Exception:
        link_bot = ''
    bot = nome_bot()
    return (f"Per ricevere gli avvisi su Telegram collega il bot @{bot}: "
            f"apri {link_bot} oppure cerca @{bot} su Telegram, premi Avvia e "
            f"scrivi /id per conoscere il tuo ID Telegram da incollare nel "
            f"tuo profilo.")


def nota_guida_html():
    """Riga che nomina l'allegato, solo se l'allegato c'e' davvero."""
    if not percorso_manuale_benvenuto():
        return ''
    return """
    <p style="margin-top:18px;font-size:14px;">
      In allegato trovi la <strong>guida del cliente in PDF</strong>:
      come ordinare, comporre il tuo panino, pagare al banco col QR,
      prenotare il pasto aziendale e gestire le notifiche.
    </p>"""


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
    subject = f'[{co_name}] Registrazione ricevuta'
    allegato = percorso_manuale_benvenuto()

    html = f"""
<div style="font-family:sans-serif;max-width:560px;margin:auto;padding:0;">
  <div style="background:#e94560;color:#fff;padding:16px 24px;border-radius:8px 8px 0 0;">
    <h2 style="margin:0;font-size:20px;">Registrazione ricevuta</h2>
  </div>
  <div style="border:1px solid #eee;border-top:none;padding:20px 24px;border-radius:0 0 8px 8px;">
    <p>Ciao <strong>{nome}</strong>,</p>
    <p>abbiamo ricevuto la tua registrazione su <strong>{co_name}</strong>.
       Il tuo account e' <strong>in attesa di approvazione</strong>: appena
       il personale lo attiva ricevi un'altra email e puoi iniziare a
       ordinare.</p>
    <p style="font-size:14px;">Nel frattempo puoi già fare due cose:
       leggere la guida allegata e collegare Telegram.</p>
    {nota_guida_html()}{blocco_telegram_html(user)}
    <p style="margin-top:24px;color:#aaa;font-size:11px;">
      Messaggio automatico generato da {co_name}
    </p>
  </div>
</div>"""

    text = (f"Ciao {nome}, abbiamo ricevuto la tua registrazione su "
            f"{co_name}. L'account e' in attesa di approvazione: ti avvisiamo "
            f"appena e' attivo. "
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

    L'avviso Telegram richiede che l'utente abbia collegato il proprio chat id,
    cosa che un cliente appena registrato non ha ancora fatto: l'email e' quindi
    l'unico canale che lo raggiunge davvero.
    """
    if not getattr(user, 'email', ''):
        return False, 'Utente senza email'

    co_name = get_setting('company_name') or 'QuickLunch'
    nome    = (getattr(user, 'first_name', '') or '').strip() or user.username
    subject = f'[{co_name}] Il tuo account e\' attivo'

    # Il passo della ricarica ha senso solo col portafoglio prepagato attivo.
    try:
        from app import wallet_enabled as _wallet_attivo
        con_wallet = _wallet_attivo()
    except Exception:
        con_wallet = True
    passo_credito = (
        "<li>Ricarica il credito in cassa: il portafoglio e' prepagato e "
        "serve per ordinare.</li>" if con_wallet else
        '<li>Ordina e paga alla cassa al momento del ritiro.</li>')

    bot = nome_bot()
    blocco_telegram = blocco_telegram_html(user)
    allegato = percorso_manuale_benvenuto()
    nota_allegato = nota_guida_html()

    cta = ''
    if login_url:
        cta = f"""
    <div style="margin:26px 0 6px;">
      <a href="{login_url}"
         style="background:#e94560;color:#fff;padding:12px 28px;border-radius:6px;
                text-decoration:none;font-weight:bold;font-size:16px;">
        Accedi ora &rarr;
      </a>
    </div>"""

    html = f"""
<div style="font-family:sans-serif;max-width:560px;margin:auto;padding:0;">
  <div style="background:#e94560;color:#fff;padding:16px 24px;border-radius:8px 8px 0 0;">
    <h2 style="margin:0;font-size:20px;">Account attivato</h2>
  </div>
  <div style="border:1px solid #eee;border-top:none;padding:20px 24px;border-radius:0 0 8px 8px;">
    <p>Ciao <strong>{nome}</strong>,</p>
    <p>il tuo account su <strong>{co_name}</strong> e' stato attivato: da adesso puoi
       accedere, consultare il menu e ordinare.</p>
    <p style="margin-top:16px;"><strong>Come iniziare</strong></p>
    <ol style="padding-left:20px;margin:8px 0;font-size:14px;">
      <li>Accedi con l'email con cui ti sei registrato.</li>
      {passo_credito}
      <li>Scegli dal menu, indica l'orario di ritiro e conferma.</li>
    </ol>{cta}{blocco_telegram}{nota_allegato}
    <p style="margin-top:24px;color:#aaa;font-size:11px;">
      Messaggio automatico generato da {co_name}
    </p>
  </div>
</div>"""

    text = (f"Ciao {nome}, il tuo account su {co_name} e' stato attivato: "
            f"puoi accedere e ordinare. "
            + ("Ricorda di ricaricare il credito in cassa. "
               if con_wallet else "Pagherai alla cassa al ritiro. ")
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
