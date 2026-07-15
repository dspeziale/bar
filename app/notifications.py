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


def send_telegram_to_user(user, text):
    """Invia un messaggio Telegram direttamente all'utente tramite il suo chat_id personale."""
    token   = get_setting('telegram_bot_token')
    chat_id = getattr(user, 'telegram_chat_id', None)
    if not token or not chat_id:
        return False, 'Token o Telegram Chat ID utente non disponibili'
    url     = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
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

def send_email(to_addr, subject, html_body, text_body=None):
    """Invia un'email HTML tramite Gmail SMTP (App Password)."""
    gmail_user = get_setting('gmail_user')
    gmail_pass = get_setting('gmail_app_password')
    if not gmail_user or not gmail_pass:
        return False, 'Gmail non configurata'
    if not to_addr:
        return False, 'Destinatario mancante'
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f'QuickLunch Ufficio <{gmail_user}>'
        msg['To']      = to_addr
        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ctx) as srv:
            srv.login(gmail_user, gmail_pass)
            srv.send_message(msg)
        return True, 'Email inviata'
    except Exception as exc:
        return False, str(exc)


def send_supplier_low_stock_alert(item):
    """Invia email al fornitore quando la giacenza scende sotto la soglia minima."""
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
        <td style="padding:8px 12px;border:1px solid #eee;color:#e94560;font-weight:bold;">{item.quantity:.1f} {item.unit}</td>
      </tr>
      <tr style="background:#f5f5f5;">
        <td style="padding:8px 12px;font-weight:bold;border:1px solid #eee;">Soglia minima</td>
        <td style="padding:8px 12px;border:1px solid #eee;">{item.min_threshold:.1f} {item.unit}</td>
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
