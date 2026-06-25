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
