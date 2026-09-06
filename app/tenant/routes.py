import re
from flask import render_template, redirect, url_for, flash, request, session, abort
from flask_login import login_user, current_user
from app import db, oauth
from app.tenant import bp
from app.models import Tenant, User
from app.tenancy import utente_globale
from app.notifications import (get_setting, send_telegram,
                               send_registration_received_email,
                               send_account_activated_email)
# I due messaggi vivono in app/auth/routes.py: qui si riusano, cosi' il
# testo mostrato al cliente e' lo stesso da qualunque via si registri.
from app.auth.routes import MESSAGGIO_REGISTRATO, MESSAGGIO_IN_ATTESA


def _get_tenant_or_404(slug):
    t = Tenant.query.filter_by(slug=slug, is_active=True).first()
    if not t:
        abort(404)
    return t


def _make_username(email, tenant_id=None):
    """Genera uno username unico a partire dall'email."""
    base = re.sub(r'[^a-z0-9]', '.', email.split('@')[0].lower()).strip('.') or 'utente'
    base = base[:30]
    username, n = base, 1
    while utente_globale(username=username):
        username = f'{base}{n}'
        n += 1
    return username


# ── Landing page tenant ───────────────────────────────────────────────────────

@bp.route('/<slug>')
def landing(slug):
    tenant = _get_tenant_or_404(slug)
    return render_template('tenant/landing.html', tenant=tenant)


# ── Registrazione email/password ──────────────────────────────────────────────

@bp.route('/<slug>/register', methods=['GET', 'POST'])
def register(slug):
    tenant = _get_tenant_or_404(slug)
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        error = None
        if not email or '@' not in email:
            error = 'Email non valida.'
        elif len(password) < 6:
            error = 'Password troppo corta (min 6 caratteri).'
        elif password != password2:
            error = 'Le password non coincidono.'
        elif utente_globale(email=email):
            error = 'Email già registrata. Prova ad accedere.'

        if error:
            flash(error, 'danger')
        else:
            user = User(
                username  = _make_username(email, tenant.id),
                email     = email,
                tenant_id = tenant.id,
                is_client = True,
                # Come dalla pagina globale: il titolare approva le nuove
                # iscrizioni. Un percorso che entrava subito e uno che
                # aspettava l'attivazione erano una fonte di confusione.
                is_active = False,
                first_name = request.form.get('first_name', '').strip(),
                last_name  = request.form.get('last_name', '').strip(),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            user.apply_registration_bonus()
            send_registration_received_email(user)
            send_telegram(
                f'🆕 <b>Nuovo cliente in attesa</b> — {tenant.name}\n'
                f'📧 {email}'
            )
            flash(MESSAGGIO_REGISTRATO, 'success')
            return redirect(url_for('tenant.login', slug=tenant.slug))

    return render_template('tenant/register.html', tenant=tenant, mode='register')


# ── Login per utenti del tenant ───────────────────────────────────────────────

@bp.route('/<slug>/login', methods=['GET', 'POST'])
def login(slug):
    tenant = _get_tenant_or_404(slug)
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = utente_globale(email=email)
        if user and user.check_password(password):
            if user.is_superadmin:
                # L'amministratore dei tenant che entra dalla pagina di un
                # locale ci lavora dentro da subito.
                login_user(user, remember=True)
                session['tenant_attivo'] = tenant.id
                flash('Sei l\'amministratore dei tenant: stai lavorando nel locale «%s». '
                      'Per cambiare locale usa il selettore in alto a destra.' % tenant.name, 'info')
                return redirect(url_for('admin.dashboard'))
            if user.tenant_id != tenant.id:
                # Account di un altro locale: lo si dice, senza nominare
                # l'altro locale ne' il suo indirizzo. Nessun locale deve
                # sapere degli altri: l'indirizzo giusto lo ha gia' il cliente
                # (locandina, email di attivazione).
                flash('Questo account non appartiene a questo locale: usa l\'indirizzo di '
                      'accesso che ti ha dato il tuo locale (lo trovi anche nell\'email di '
                      'attivazione).', 'warning')
                return redirect(url_for('tenant.login', slug=tenant.slug))
            if not user.is_active:
                send_registration_received_email(user)
                flash(MESSAGGIO_IN_ATTESA, 'info')
                return redirect(url_for('tenant.login', slug=tenant.slug))
            if user.totp_enabled:
                session['_mfa_uid']  = user.id
                session['_mfa_next'] = ''
                return redirect(url_for('auth.mfa_verify'))
            login_user(user, remember=True)
            flash('Sei entrato nel locale «%s».' % tenant.name, 'info')
            if user.is_admin or user.is_staff:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('main.index'))
        flash('Credenziali non valide.', 'danger')

    return render_template('tenant/register.html', tenant=tenant, mode='login')


def _refresh_oauth_google():
    from flask import current_app
    cid     = current_app.config.get('GOOGLE_CLIENT_ID') or get_setting('google_client_id') or ''
    csecret = current_app.config.get('GOOGLE_CLIENT_SECRET') or get_setting('google_client_secret') or ''
    if not cid or not csecret:
        return False
    oauth.google.client_id     = cid
    oauth.google.client_secret = csecret
    return True


# ── Google OAuth: avvio ───────────────────────────────────────────────────────

@bp.route('/<slug>/google')
def google_start(slug):
    if not _refresh_oauth_google():
        flash('Login con Google non configurato. Contatta l\'amministratore.', 'danger')
        return redirect(url_for('auth.login'))
    tenant = _get_tenant_or_404(slug)
    session['oauth_tenant_slug'] = slug
    callback_url = url_for('tenant.google_callback', _external=True)
    return oauth.google.authorize_redirect(callback_url)


# ── Google OAuth: callback ────────────────────────────────────────────────────

@bp.route('/google/callback')
def google_callback():
    _refresh_oauth_google()
    try:
        token     = oauth.google.authorize_access_token()
        user_info = token.get('userinfo') or oauth.google.userinfo()
    except Exception as e:
        flash(f'Errore Google OAuth: {e}', 'danger')
        return redirect(url_for('auth.login'))

    slug   = session.pop('oauth_tenant_slug', None)
    tenant = Tenant.query.filter_by(slug=slug, is_active=True).first() if slug else None

    google_id  = user_info.get('sub')
    email      = (user_info.get('email') or '').lower()
    avatar     = user_info.get('picture', '')
    first_name = user_info.get('given_name', '')
    last_name  = user_info.get('family_name', '')

    user = (utente_globale(google_id=google_id) or
            utente_globale(email=email))

    if user:
        if not user.google_id:
            user.google_id = google_id
        if avatar:
            user.avatar_url = avatar
        if first_name and not user.first_name:
            user.first_name = first_name
        if last_name and not user.last_name:
            user.last_name = last_name
        db.session.commit()
    else:
        if not tenant:
            flash('Tenant non trovato. Usa il link di registrazione del tuo ufficio.', 'danger')
            return redirect(url_for('auth.login'))
        user = User(
            username   = _make_username(email, tenant.id),
            email      = email,
            google_id  = google_id,
            avatar_url = avatar,
            first_name = first_name,
            last_name  = last_name,
            tenant_id  = tenant.id,
            is_client  = True,
            # La pagina che segue dice "in attesa di attivazione": senza
            # questo l'utente sarebbe attivo di default ed entrerebbe subito,
            # scavalcando l'approvazione del titolare.
            is_active  = False,
        )
        db.session.add(user)
        db.session.commit()
        user.apply_registration_bonus()
        send_registration_received_email(user)
        send_telegram(
            f'🆕 <b>Nuovo utente Google</b> — {tenant.name}\n'
            f'👤 {first_name} {last_name}'.strip() + f'\n📧 {email}'
        )
        flash(MESSAGGIO_REGISTRATO, 'success')
        return redirect(url_for('auth.login'))

    if not user.is_active:
        # Come nel percorso globale: si rimanda la conferma con la guida,
        # cosi chi riprova a iscriversi riceve comunque qualcosa.
        send_registration_received_email(user)
        flash(MESSAGGIO_IN_ATTESA, 'info')
        return redirect(url_for('auth.login'))

    login_user(user, remember=True)
    return redirect(url_for('main.index'))
