import re
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db, oauth
from app.auth import bp
from app.models import User


def _make_username(email):
    base = re.sub(r'[^a-z0-9]', '.', email.split('@')[0].lower()).strip('.') or 'utente'
    base = base[:30]
    username, n = base, 1
    while User.query.filter_by(username=username).first():
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
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=True)
            next_page = request.args.get('next')
            if user.is_admin:
                return redirect(next_page or url_for('admin.dashboard'))
            return redirect(next_page or url_for('main.index'))
        flash('Credenziali non valide.', 'danger')
    return render_template('auth/login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
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
            user = User(username=_make_username(email), email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Registrazione completata. Benvenuto!', 'success')
            return redirect(url_for('main.index'))
    return render_template('auth/register.html')


@bp.route('/google')
def google_start():
    callback_url = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(callback_url)


@bp.route('/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo') or oauth.google.userinfo()
    except Exception as e:
        flash(f'Errore OAuth: {e}', 'danger')
        return redirect(url_for('auth.login'))

    google_id = user_info.get('sub', '')
    email = (user_info.get('email') or '').lower()
    avatar = user_info.get('picture', '')

    user = (User.query.filter_by(google_id=google_id).first()
            or User.query.filter_by(email=email).first())

    if not user:
        flash("Nessun account trovato per questa email. Contatta l'amministratore.", 'danger')
        return redirect(url_for('auth.login'))

    if not user.is_active:
        flash("Account sospeso. Contatta l'amministratore.", 'danger')
        return redirect(url_for('auth.login'))

    if not user.google_id:
        user.google_id = google_id
    if avatar:
        user.avatar_url = avatar
    db.session.commit()

    login_user(user, remember=True)
    next_page = request.args.get('next')
    if user.is_admin:
        return redirect(next_page or url_for('admin.dashboard'))
    return redirect(next_page or url_for('main.index'))


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
