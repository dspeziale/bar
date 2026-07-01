import re
from flask import render_template, redirect, url_for, flash, request, session, abort
from flask_login import login_user, current_user
from app import db, oauth
from app.tenant import bp
from app.models import Tenant, User
from app.notifications import get_setting


def _apply_registration_bonus(user):
    """Accredita il bonus di benvenuto se configurato nelle impostazioni."""
    try:
        val = float(get_setting('registration_bonus') or 0)
    except (ValueError, TypeError):
        val = 0.0
    if val > 0:
        user.credit_wallet(val, 'Bonus benvenuto')
        db.session.commit()


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
    while User.query.filter_by(username=username).first():
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
        elif User.query.filter_by(email=email).first():
            error = 'Email già registrata. Prova ad accedere.'

        if error:
            flash(error, 'danger')
        else:
            user = User(
                username  = _make_username(email, tenant.id),
                email     = email,
                tenant_id = tenant.id,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            _apply_registration_bonus(user)
            login_user(user, remember=True)
            flash(f'Benvenuto in {tenant.name}!', 'success')
            return redirect(url_for('main.index'))

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
        user = User.query.filter_by(email=email, tenant_id=tenant.id).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=True)
            return redirect(url_for('main.index'))
        flash('Credenziali non valide.', 'danger')

    return render_template('tenant/register.html', tenant=tenant, mode='login')


# ── Google OAuth: avvio ───────────────────────────────────────────────────────

@bp.route('/<slug>/google')
def google_start(slug):
    tenant = _get_tenant_or_404(slug)
    session['oauth_tenant_slug'] = slug
    callback_url = url_for('tenant.google_callback', _external=True)
    return oauth.google.authorize_redirect(callback_url)


# ── Google OAuth: callback ────────────────────────────────────────────────────

@bp.route('/google/callback')
def google_callback():
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

    user = (User.query.filter_by(google_id=google_id).first() or
            User.query.filter_by(email=email).first())

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
        )
        db.session.add(user)
        db.session.commit()
        _apply_registration_bonus(user)
        flash('Account creato con Google. Benvenuto!', 'success')

    if not user.is_active:
        flash("Account sospeso. Contatta l'amministratore.", 'danger')
        return redirect(url_for('auth.login'))

    login_user(user, remember=True)
    return redirect(url_for('main.index'))
