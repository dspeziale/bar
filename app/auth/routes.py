import re
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db, oauth
from app.auth import bp
from app.models import Tenant, User
from app.notifications import (get_setting, send_telegram,
                               send_registration_received_email)
from app.tenancy import utente_globale, senza_filtro


MESSAGGIO_REGISTRATO = (
    "Registrazione completata! Il tuo account e' in attesa di approvazione: ti avvisiamo per email appena e' attivo. Nel frattempo controlla la posta, trovi la guida in allegato.")
MESSAGGIO_IN_ATTESA = (
    "Il tuo account e' ancora in attesa di approvazione. Ti abbiamo rimandato l'email di conferma con la guida.")


def _tenant_predefinito():
    """Tenant a cui agganciare chi si registra dalle pagine globali.

    Le registrazioni su /auth non passano da un tenant: senza questo l'utente
    nasce con tenant_id NULL e la lista clienti del backoffice, che filtra per
    tenant, non lo mostra mai. Si usa lo slug 'default' (lo stesso ripiego di
    _active_tenant_id nel backoffice); se non c'e' ma esiste un solo tenant,
    quello.
    """
    from app.tenancy import tenant_corrente, tenant_predefinito
    tid = tenant_corrente()
    if tid:
        return tid
    t = tenant_predefinito()
    return t.id if t else None


def _tenant_attivi():
    """I locali a cui si puo' accedere: la pagina globale li elenca perche'
    ognuno ha il proprio indirizzo di accesso e di registrazione."""
    return Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()


def _saluta_dopo_login(user):
    """Dice subito in quale locale si e' entrati: e' la risposta alla domanda
    "dove sono?" che il multi-tenant altrimenti lascia aperta."""
    from app.tenancy import tenant_predefinito
    if user.is_superadmin:
        t = None
        tid = session.get('tenant_attivo')
        if tid:
            t = db.session.get(Tenant, tid)
        t = t or tenant_predefinito()
        flash('Sei l\'amministratore dei tenant: stai lavorando nel locale «%s». '
              'Per cambiare locale usa il selettore in alto a destra.' % (t.name if t else '—'), 'info')
    elif user.tenant:
        flash('Sei entrato nel locale «%s».' % user.tenant.name, 'info')


def _make_username(email):
    base = re.sub(r'[^a-z0-9]', '.', email.split('@')[0].lower()).strip('.') or 'utente'
    base = base[:30]
    username, n = base, 1
    while utente_globale(username=username):
        username = f'{base}{n}'
        n += 1
    return username


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = utente_globale(email=email)
        if user and user.check_password(password) and user.is_active:
            if user.totp_enabled:
                session['_mfa_uid']  = user.id
                session['_mfa_next'] = request.args.get('next', '')
                return redirect(url_for('auth.mfa_verify'))
            login_user(user, remember=True)
            _saluta_dopo_login(user)
            next_page = request.args.get('next')
            if user.is_admin:
                return redirect(next_page or url_for('admin.dashboard'))
            return redirect(next_page or url_for('main.index'))
        if user and user.check_password(password) and not user.is_active:
            # Password giusta, account ancora da approvare: dirgli
            # "credenziali non valide" lo mandava a cercare un errore che
            # non c'era. Gli si rimanda anche la conferma con la guida.
            send_registration_received_email(user)
            flash(MESSAGGIO_IN_ATTESA, 'info')
            return redirect(url_for('auth.login'))
        flash('Credenziali non valide.', 'danger')
    # Pagina neutra: non elenca i locali. Ogni locale pubblica da se' il
    # proprio indirizzo di accesso, e nessun locale deve sapere degli altri.
    return render_template('auth/login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    # La registrazione e' sempre di un locale, dal suo indirizzo
    # /t/<slug>/register (locandina, QR, email). Con un solo locale si va
    # dritti alla sua pagina; con piu' locali non si elenca nulla: si spiega
    # dove trovare il proprio indirizzo.
    tenants = _tenant_attivi()
    if len(tenants) > 1:
        return render_template('auth/registrazione_locale.html')
    if request.method == 'GET' and len(tenants) == 1:
        return redirect(url_for('tenant.register', slug=tenants[0].slug))
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
            first_name = request.form.get('first_name', '').strip()
            last_name  = request.form.get('last_name', '').strip()
            user = User(
                username=_make_username(email),
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_client=True,
                is_active=False,
                tenant_id=_tenant_predefinito(),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            user.apply_registration_bonus()
            send_registration_received_email(user)
            send_telegram(
                f'🆕 <b>Nuovo cliente in attesa</b>\n'
                f'👤 {first_name} {last_name}'.strip() + f'\n📧 {email}'
            )
            flash(MESSAGGIO_REGISTRATO, 'success')
            return redirect(url_for('auth.login'))
    return render_template('auth/register.html')


def _refresh_oauth_google():
    """Load Google OAuth credentials from DB (fallback: env/config)."""
    from flask import current_app
    cid     = current_app.config.get('GOOGLE_CLIENT_ID') or get_setting('google_client_id') or ''
    csecret = current_app.config.get('GOOGLE_CLIENT_SECRET') or get_setting('google_client_secret') or ''
    if not cid or not csecret:
        return False
    oauth.google.client_id     = cid
    oauth.google.client_secret = csecret
    return True


@bp.route('/google')
def google_start():
    if not _refresh_oauth_google():
        flash('Login con Google non configurato. Contatta l\'amministratore.', 'danger')
        return redirect(url_for('auth.login'))
    callback_url = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(callback_url)


@bp.route('/google/callback')
def google_callback():
    _refresh_oauth_google()
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo') or oauth.google.userinfo()
    except Exception as e:
        flash(f'Errore OAuth: {e}', 'danger')
        return redirect(url_for('auth.login'))

    google_id  = user_info.get('sub', '')
    email      = (user_info.get('email') or '').lower()
    avatar     = user_info.get('picture', '')
    first_name = user_info.get('given_name', '')
    last_name  = user_info.get('family_name', '')

    user = (utente_globale(google_id=google_id)
            or utente_globale(email=email))

    if user:
        if not user.is_active:
            # Chi riprova a iscriversi mentre e' ancora in attesa non sta
            # facendo una registrazione nuova: senza questo non riceveva
            # nulla e sembrava che l'iscrizione non avesse funzionato.
            # Gli si rimanda la conferma, con la guida allegata.
            send_registration_received_email(user)
            flash(MESSAGGIO_IN_ATTESA, 'info')
            return redirect(url_for('auth.login'))
        if not user.google_id:
            user.google_id = google_id
        if avatar:
            user.avatar_url = avatar
        if first_name and not user.first_name:
            user.first_name = first_name
        if last_name and not user.last_name:
            user.last_name = last_name
        db.session.commit()
        if user.totp_enabled:
            session['_mfa_uid']  = user.id
            session['_mfa_next'] = request.args.get('next', '')
            return redirect(url_for('auth.mfa_verify'))
        login_user(user, remember=True)
        _saluta_dopo_login(user)
        next_page = request.args.get('next')
        if user.is_admin:
            return redirect(next_page or url_for('admin.dashboard'))
        return redirect(next_page or url_for('main.index'))
    else:
        # Email nuova dalla pagina globale: il locale non e' noto. Con un solo
        # locale si iscrive li'; con piu' locali non si indovina (finirebbe nel
        # predefinito): ci si iscrive dal link del proprio locale, dove lo slug
        # nell'indirizzo dice a chi appartiene.
        tenants = _tenant_attivi()
        if len(tenants) != 1:
            flash('Nessun account con questa email Google. Per iscriverti usa il link del '
                  'tuo locale (locandina, QR o indirizzo che ti ha dato il locale).', 'warning')
            return redirect(url_for('auth.register'))
        user = User(
            username   = _make_username(email),
            email      = email,
            google_id  = google_id,
            avatar_url = avatar,
            first_name = first_name,
            last_name  = last_name,
            is_active  = False,
            is_client  = True,
            tenant_id  = tenants[0].id,
        )
        db.session.add(user)
        db.session.commit()
        user.apply_registration_bonus()
        send_registration_received_email(user)
        send_telegram(
            f'🆕 <b>Nuovo utente (Google)</b> — in attesa di attivazione\n'
            f'👤 {first_name} {last_name}'.strip() + f'\n📧 {email}'
        )
        flash(MESSAGGIO_REGISTRATO, 'success')
        return redirect(url_for('auth.login'))


@bp.route('/join')
def join():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    tenants = _tenant_attivi()
    if len(tenants) == 1:
        join_url = url_for('tenant.register', slug=tenants[0].slug, _external=True)
    else:
        join_url = url_for('auth.register', _external=True)
    return render_template('auth/join.html', join_url=join_url)


@bp.route('/pending')
def pending():
    return render_template('auth/pending.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


# ── MFA — verifica durante il login ──────────────────────────────────────────

@bp.route('/mfa', methods=['GET', 'POST'])
def mfa_verify():
    uid = session.get('_mfa_uid')
    if not uid:
        return redirect(url_for('auth.login'))
    with senza_filtro():
        user = db.session.get(User, uid)
    if not user or not user.totp_enabled:
        session.pop('_mfa_uid', None)
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        import pyotp
        code = request.form.get('code', '').strip().replace(' ', '')
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code, valid_window=1):
            session.pop('_mfa_uid', None)
            next_page = session.pop('_mfa_next', '') or None
            login_user(user, remember=True)
            if user.is_admin:
                return redirect(next_page or url_for('admin.dashboard'))
            return redirect(next_page or url_for('main.index'))
        flash('Codice non valido. Riprova.', 'danger')

    return render_template('auth/mfa.html')


# ── MFA — setup (utente autenticato) ─────────────────────────────────────────

@bp.route('/mfa/setup', methods=['GET', 'POST'])
@login_required
def mfa_setup():
    import pyotp
    from app.notifications import get_setting

    if request.method == 'POST':
        secret = session.get('_mfa_pending_secret')
        code   = request.form.get('code', '').strip().replace(' ', '')
        if not secret:
            flash('Sessione scaduta. Ricomincia la configurazione.', 'danger')
            return redirect(url_for('auth.mfa_setup'))
        totp = pyotp.TOTP(secret)
        if totp.verify(code, valid_window=1):
            current_user.totp_secret  = secret
            current_user.totp_enabled = True
            db.session.commit()
            session.pop('_mfa_pending_secret', None)
            flash('Autenticazione a due fattori attivata.', 'success')
            return redirect(url_for('main.index'))
        flash('Codice non valido. Riprova.', 'danger')

    # Genera (o riusa dalla sessione) il segreto provvisorio
    secret = session.get('_mfa_pending_secret') or pyotp.random_base32()
    session['_mfa_pending_secret'] = secret

    app_name = 'QuickLunch'
    totp_uri = pyotp.TOTP(secret).provisioning_uri(
        name=current_user.email,
        issuer_name=app_name,
    )
    return render_template('auth/mfa_setup.html',
                           totp_uri=totp_uri, secret=secret, app_name=app_name)


# ── MFA — disabilita ─────────────────────────────────────────────────────────

@bp.route('/mfa/disable', methods=['POST'])
@login_required
def mfa_disable():
    import pyotp
    code = request.form.get('code', '').strip().replace(' ', '')
    if not current_user.totp_enabled:
        return redirect(url_for('main.index'))
    totp = pyotp.TOTP(current_user.totp_secret)
    if totp.verify(code, valid_window=1):
        current_user.totp_secret  = None
        current_user.totp_enabled = False
        db.session.commit()
        flash('Autenticazione a due fattori disattivata.', 'info')
        return redirect(url_for('main.index'))
    flash('Codice non valido. MFA non disattivato.', 'danger')
    return redirect(url_for('main.index'))
