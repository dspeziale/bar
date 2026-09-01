import os
import time as _time
from zoneinfo import ZoneInfo
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from authlib.integrations.flask_client import OAuth
from markupsafe import Markup

_ROME = ZoneInfo('Europe/Rome')

# ── Reminder tavoli: ultimo check (time-gate, per-process) ────────────────────
_reminder_last_run = [0.0]   # list per consentire la modifica nel before_request

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Devi effettuare il login per accedere a questa pagina.'
login_manager.login_message_category = 'warning'
oauth = OAuth()
csrf = CSRFProtect()


def create_app(config_object='config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Authlib: disabilita verifica HTTPS in sviluppo locale
    if app.config.get('AUTHLIB_INSECURE_TRANSPORT'):
        os.environ['AUTHLIB_INSECURE_TRANSPORT'] = '1'

    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)
    csrf.init_app(app)

    # ── Filtri Jinja2 per fuso orario Europe/Rome ─────────────────────────
    from datetime import datetime, timezone

    @app.template_filter('dt_rome')
    def _dt_rome(dt, fmt='%d/%m/%Y %H:%M'):
        if dt is None:
            return ''
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(_ROME).strftime(fmt)
        return dt.strftime(fmt.split(' ')[0] if ' ' in fmt else fmt)

    @app.template_filter('d_rome')
    def _d_rome(d):
        if d is None:
            return ''
        return d.strftime('%d/%m/%Y')

    # ── CSRF: campo nascosto da inserire in ogni form POST ────────────────
    @app.template_global()
    def csrf_field():
        from flask_wtf.csrf import generate_csrf
        return Markup(
            '<input type="hidden" name="csrf_token" value="%s">' % generate_csrf()
        )

    # ── Funzionalita' attivabili: flag disponibile in ogni template ───────
    @app.context_processor
    def _inject_feature_flags():
        return {'tables_enabled': tables_enabled()}

    # Registra Google OAuth (se configurato)
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID', ''),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET', ''),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.tenant import bp as tenant_bp
    app.register_blueprint(tenant_bp, url_prefix='/t')

    # ── Reminder (lazy polling: max 1 check/min per processo) ─────────────────
    @app.before_request
    def _maybe_remind_table_bookings():
        now = _time.monotonic()
        if now - _reminder_last_run[0] < 60:
            return
        _reminder_last_run[0] = now
        try:
            if tables_enabled():
                _check_table_reminders()
            _check_order_reminders()
            _check_meal_reminders()
        except Exception:
            pass

    with app.app_context():
        db.create_all()
        _migrate_tenant_columns()
        _seed_defaults()

    # ── CLI: flask seed-demo ───────────────────────────────────────────────
    @app.cli.command('seed-demo')
    def seed_demo_command():
        """Resetta e ricarica i dati di demo: 3 tenant, 36 clienti, prodotti alimentari."""
        with app.app_context():
            from app.demo_seed import reset_demo_data, seed_demo_data
            reset_demo_data()
            ok, msg = seed_demo_data()
            print(('[OK]' if ok else '[SKIP]'), msg)

    return app


def tables_enabled():
    """True se la gestione tavoli e prenotazioni e' attiva (Impostazioni).

    Il valore viene letto a ogni render di base.html, quindi lo teniamo in cache
    per richiesta. In assenza dell'impostazione la funzione resta attiva, per non
    cambiare il comportamento delle installazioni esistenti.
    """
    from flask import g, has_request_context

    if has_request_context() and hasattr(g, '_ql_tables_enabled'):
        return g._ql_tables_enabled
    try:
        from app.notifications import get_setting
        val = (get_setting('tables_enabled', '1') or '1') != '0'
    except Exception:
        val = True
    if has_request_context():
        g._ql_tables_enabled = val
    return val


def _check_table_reminders():
    from datetime import datetime as _dtt
    from app.models import TableReservation
    from app.notifications import send_telegram_to_user, get_numeric_setting

    remind = get_numeric_setting('table_reminder_minutes', 10)
    now    = _dtt.utcnow()
    today  = now.date()

    candidates = (
        TableReservation.query
        .filter_by(reservation_date=today, status='confirmed', table_alert_sent=False)
        .filter(TableReservation.checkin_at.is_(None))
        .all()
    )
    changed = False
    for res in candidates:
        if not res.session_start or not getattr(res.user, 'telegram_chat_id', None):
            continue
        try:
            slot_dt = _dtt.strptime(
                f'{today.isoformat()} {res.session_start}', '%Y-%m-%d %H:%M'
            )
        except ValueError:
            continue
        diff = (slot_dt - now).total_seconds() / 60
        if 0 < diff <= remind:
            send_telegram_to_user(
                res.user,
                f'⏰ Reminder: il tuo tavolo è tra <b>{int(diff)} minuti</b>!\n'
                f'🪑 Tavolo <b>{res.table.number}</b> — ore <b>{res.session_start}</b>\n'
                f'📅 {res.reservation_date.strftime("%d/%m/%Y")}'
            )
            res.table_alert_sent = True
            changed = True
    if changed:
        db.session.commit()


def _check_order_reminders():
    from datetime import datetime as _dtt, date as _date
    from app.models import Order
    from app.notifications import send_telegram_to_user, get_numeric_setting

    remind = get_numeric_setting('order_reminder_minutes', 15)
    now    = _dtt.utcnow()
    today  = _date.today()

    candidates = (
        Order.query
        .filter_by(order_date=today, reminder_sent=False)
        .filter(Order.status.in_(['pending', 'confirmed', 'preparing']))
        .filter(Order.slot_id.isnot(None))
        .all()
    )
    changed = False
    for order in candidates:
        if not getattr(order.user, 'telegram_chat_id', None):
            continue
        if not order.slot or not order.slot.time_str:
            continue
        try:
            slot_dt = _dtt.strptime(
                f'{today.isoformat()} {order.slot.time_str}', '%Y-%m-%d %H:%M'
            )
        except ValueError:
            continue
        diff = (slot_dt - now).total_seconds() / 60
        if 0 < diff <= remind:
            send_telegram_to_user(
                order.user,
                f'🍽️ Reminder: il tuo ordine è pronto per il ritiro alle <b>{order.slot.time_str}</b>!\n'
                f'📦 Ordine #{order.order_code or order.id} — <b>{order.total_price:.2f}€</b>\n'
                f'⏱️ Mancano circa <b>{int(diff)} minuti</b>'
            )
            order.reminder_sent = True
            changed = True
    if changed:
        db.session.commit()


def _check_meal_reminders():
    from datetime import datetime as _dtt, date as _date
    from app.models import CorporateMealBooking
    from app.notifications import send_telegram_to_user, get_numeric_setting

    remind = get_numeric_setting('meal_reminder_minutes', 15)
    now    = _dtt.utcnow()
    today  = _date.today()

    candidates = (
        CorporateMealBooking.query
        .filter_by(status='booked', reminder_sent=False)
        .filter(CorporateMealBooking.slot_id.isnot(None))
        .all()
    )
    changed = False
    for booking in candidates:
        if not booking.meal or booking.meal.meal_date != today:
            continue
        if not getattr(booking.user, 'telegram_chat_id', None):
            continue
        if not booking.slot or not booking.slot.time_str:
            continue
        try:
            slot_dt = _dtt.strptime(
                f'{today.isoformat()} {booking.slot.time_str}', '%Y-%m-%d %H:%M'
            )
        except ValueError:
            continue
        diff = (slot_dt - now).total_seconds() / 60
        if 0 < diff <= remind:
            send_telegram_to_user(
                booking.user,
                f'🥗 Reminder: il tuo pasto aziendale è alle <b>{booking.slot.time_str}</b>!\n'
                f'📋 <b>{booking.meal.name}</b>\n'
                f'⏱️ Mancano circa <b>{int(diff)} minuti</b>'
            )
            booking.reminder_sent = True
            changed = True
    if changed:
        db.session.commit()


def _migrate_tenant_columns():
    """Aggiunge le colonne multi-tenant alle tabelle esistenti (compatibile SQLite e PostgreSQL)."""
    from sqlalchemy import inspect as sa_inspect, text

    insp = sa_inspect(db.engine)
    existing_tables = set(insp.get_table_names())
    is_pg = db.engine.dialect.name == 'postgresql'

    # Mappa tipi SQLite → PostgreSQL per i tipi non compatibili
    _TYPE_MAP_PG = {
        'DATETIME': 'TIMESTAMP',
        'BOOLEAN DEFAULT FALSE': 'BOOLEAN DEFAULT FALSE',
        'BOOLEAN DEFAULT TRUE':  'BOOLEAN DEFAULT TRUE',
    }

    def _pg_type(definition):
        """Traduce definizioni SQLite in equivalenti PostgreSQL."""
        if not is_pg:
            return definition
        for sqlite_t, pg_t in _TYPE_MAP_PG.items():
            if definition.upper().startswith(sqlite_t):
                return definition.upper().replace(sqlite_t, pg_t, 1)
        return definition

    def _ensure(table, col, definition='INTEGER'):
        if table not in existing_tables:
            return
        existing_cols = {c['name'] for c in insp.get_columns(table)}
        if col in existing_cols:
            return
        real_def = _pg_type(definition)
        try:
            with db.engine.connect() as conn:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {real_def}'))
                conn.commit()
            print(f'[migration] added {table}.{col} ({real_def})')
        except Exception as exc:
            # Colonna già presente in una race condition (accettabile) — tutto il resto viene loggato
            if 'already exists' not in str(exc).lower() and 'duplicate column' not in str(exc).lower():
                print(f'[migration] ERROR {table}.{col}: {exc}')

    tables = [
        'users', 'categories', 'products', 'orders', 'time_slots',
        'daily_stocks', 'ingredient_categories', 'ingredients',
        'tables', 'table_reservations', 'polls', 'app_settings',
    ]
    for t in tables:
        _ensure(t, 'tenant_id', 'INTEGER')

    # Colonne aggiuntive su users per OAuth
    _ensure('users', 'google_id', 'VARCHAR(128)')
    _ensure('users', 'avatar_url', "VARCHAR(256) DEFAULT ''")

    # Colonne anagrafica clienti
    _ensure('users', 'is_client',        "BOOLEAN DEFAULT FALSE")
    _ensure('users', 'first_name',        "VARCHAR(64) DEFAULT ''")
    _ensure('users', 'last_name',         "VARCHAR(64) DEFAULT ''")
    _ensure('users', 'phone',             "VARCHAR(20) DEFAULT ''")
    _ensure('users', 'birth_date',        "DATE")
    _ensure('users', 'address',           "TEXT DEFAULT ''")
    _ensure('users', 'telegram_chat_id',  "VARCHAR(64) DEFAULT ''")

    # Colonna piastra per ordini builder
    _ensure('custom_order_items', 'grill_requested', "BOOLEAN DEFAULT FALSE")

    # Durata stazionamento tavolo per fascia oraria
    _ensure('time_slots', 'seat_duration_minutes', "INTEGER DEFAULT 0")

    # Tracciamento check-in e alert tavolo (DATETIME → TIMESTAMP su PostgreSQL)
    _ensure('table_reservations', 'checkin_at',       "DATETIME")
    _ensure('table_reservations', 'table_alert_sent', "BOOLEAN DEFAULT FALSE")

    # Allergeni sui prodotti del menu
    _ensure('products', 'allergens', "VARCHAR(512) DEFAULT ''")

    # Composizione e allergeni del pasto aziendale del giorno
    _ensure('daily_fixed_meals', 'composition', "TEXT DEFAULT ''")
    _ensure('daily_fixed_meals', 'allergens',   "VARCHAR(512) DEFAULT ''")
    # Portate strutturate del menu aziendale
    _ensure('daily_fixed_meals', 'primo',    "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'secondo',  "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'contorno', "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'bevanda',  "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'caffe',    "VARCHAR(128) DEFAULT ''")

    # Porzioni prenotazione pasto aziendale
    _ensure('corporate_meal_bookings', 'quantity', 'INTEGER DEFAULT 1 NOT NULL')

    # Fasce orarie tavoli (nuova tabella) — creata da create_all se non esiste
    # Colonne aggiuntive su table_reservations per il nuovo sistema a fasce
    _ensure('table_reservations', 'band_id',       "INTEGER")
    _ensure('table_reservations', 'session_start',  "VARCHAR(5) DEFAULT ''")
    # Rendi orders.slot_id nullable (per ordini "adesso al banco" senza slot)
    if is_pg and 'orders' in existing_tables:
        cols = {c['name']: c for c in insp.get_columns('orders')}
        if 'slot_id' in cols and not cols['slot_id'].get('nullable', True):
            try:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE orders ALTER COLUMN slot_id DROP NOT NULL'))
                    conn.commit()
                print('[migration] orders.slot_id → nullable')
            except Exception:
                pass

    # Rendi slot_id nullable su PostgreSQL (in SQLite la colonna viene ricreata dal seed)
    if is_pg and 'table_reservations' in existing_tables:
        cols = {c['name']: c for c in insp.get_columns('table_reservations')}
        if 'slot_id' in cols and not cols['slot_id'].get('nullable', True):
            try:
                with db.engine.connect() as conn:
                    conn.execute(text(
                        'ALTER TABLE table_reservations ALTER COLUMN slot_id DROP NOT NULL'))
                    conn.commit()
                print('[migration] table_reservations.slot_id → nullable')
            except Exception:
                pass

    _ensure('banco_sessions', 'tenant_id', 'INTEGER')

    # Magazzino ingredienti (opzionale)
    _ensure('ingredients', 'grams_per_serving', 'REAL')
    _ensure('ingredients', 'stock_qty',         'REAL')

    # Conferma prenotazione dal sondaggio
    _ensure('poll_votes', 'confirm_reservation', 'BOOLEAN DEFAULT FALSE')

    # MFA TOTP
    _ensure('users', 'totp_secret',  "VARCHAR(64)")
    _ensure('users', 'totp_enabled', "BOOLEAN DEFAULT FALSE")

    # Reminder ordine e pasto aziendale
    _ensure('orders',                  'reminder_sent', "BOOLEAN DEFAULT FALSE")
    _ensure('corporate_meal_bookings', 'reminder_sent', "BOOLEAN DEFAULT FALSE")

    # Token di ritiro pasto aziendale
    _ensure('corporate_meal_bookings', 'pickup_token', "VARCHAR(16) DEFAULT ''")

    # Fido wallet (saldo negativo consentito)
    _ensure('users', 'wallet_overdraft', 'FLOAT DEFAULT 0.0')

    # Barcode prodotto (EAN-13/UPC per scansione lattine al cesto)
    _ensure('products', 'barcode', "VARCHAR(32)")

    # Tabella Web Push subscriptions (creata via SQL diretto per garantire presenza
    # indipendentemente dall'ordine degli import dei modelli)
    if 'push_subscriptions' not in existing_tables:
        try:
            if is_pg:
                ddl = """
                    CREATE TABLE IF NOT EXISTS push_subscriptions (
                        id         SERIAL PRIMARY KEY,
                        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        endpoint   TEXT    NOT NULL UNIQUE,
                        p256dh     VARCHAR(256) NOT NULL,
                        auth       VARCHAR(64)  NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """
            else:
                ddl = """
                    CREATE TABLE IF NOT EXISTS push_subscriptions (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        endpoint   TEXT    NOT NULL UNIQUE,
                        p256dh     VARCHAR(256) NOT NULL,
                        auth       VARCHAR(64)  NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """
            with db.engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
            print('[migration] created table push_subscriptions')
        except Exception as exc:
            print(f'[migration] push_subscriptions: {exc}')


def _seed_defaults():
    from app.models import (User, Category, TimeSlot, Table,
                            IngredientCategory, Ingredient,
                            Permission, Role, AppSetting, Tenant, BancoItem)
    from sqlalchemy import text
    from config import Config

    # ── Tenant di default ─────────────────────────────────────────────────
    default_tenant = Tenant.query.filter_by(slug='default').first()
    if not default_tenant:
        default_tenant = Tenant(
            name='Food Service',
            slug='default',
            primary_color='#e94560',
            is_active=True,
        )
        db.session.add(default_tenant)
        db.session.flush()  # ottieni l'ID prima del commit
    elif default_tenant.name != 'Food Service':
        default_tenant.name = 'Food Service'

    # Assegna tenant_id=default_tenant.id a tutti i record orfani
    orphan_tables = [
        'users', 'categories', 'products', 'orders', 'time_slots',
        'daily_stocks', 'ingredient_categories', 'ingredients',
        'tables', 'table_reservations',
    ]
    for tbl in orphan_tables:
        try:
            db.session.execute(text(
                f"UPDATE {tbl} SET tenant_id = :tid WHERE tenant_id IS NULL"
            ), {'tid': default_tenant.id})
        except Exception:
            db.session.rollback()

    # ── Permissions ───────────────────────────────────────────────────────
    if not Permission.query.first():
        perms = [
            # Ordini
            Permission(name='view_orders',               label='Visualizza ordini',              category='ordini'),
            Permission(name='manage_orders',             label='Gestisci stato ordini',          category='ordini'),
            # Prodotti
            Permission(name='manage_products',           label='Gestisci prodotti',              category='prodotti'),
            Permission(name='manage_categories',         label='Gestisci categorie',             category='prodotti'),
            Permission(name='manage_ingredients',        label='Gestisci ingredienti builder',   category='prodotti'),
            Permission(name='manage_stock',              label='Gestisci stock giornaliero',     category='prodotti'),
            Permission(name='manage_cesto',              label='Gestisci cesto cucina (QR)',     category='prodotti'),
            # Tavoli
            Permission(name='manage_tables_admin',       label='Gestisci tavoli',                category='tavoli'),
            Permission(name='manage_reservations_admin', label='Gestisci prenotazioni tavoli',   category='tavoli'),
            # Sistema
            Permission(name='manage_slots',              label='Gestisci slot orari',            category='sistema'),
            Permission(name='manage_users',              label='Gestisci utenti',                category='sistema'),
            Permission(name='manage_roles',              label='Gestisci ruoli e permessi',      category='sistema'),
            # Report
            Permission(name='view_reports',              label='Visualizza report',              category='report'),
        ]
        db.session.add_all(perms)
        db.session.flush()

    # ── Roles ─────────────────────────────────────────────────────────────
    if not Role.query.first():
        all_perms   = Permission.query.all()
        perm_by_name = {p.name: p for p in all_perms}

        def _role(name, label, color, is_system, perm_names):
            r = Role(name=name, label=label, color=color, is_system=is_system)
            r.permissions = [perm_by_name[n] for n in perm_names if n in perm_by_name]
            return r

        all_perm_names = list(perm_by_name.keys())
        roles = [
            _role('superadmin', 'Super Admin', 'danger',    True,  all_perm_names),
            _role('manager',    'Manager',     'warning',   True,  [
                'view_orders', 'manage_orders', 'manage_products', 'manage_categories',
                'manage_ingredients', 'manage_stock', 'manage_tables_admin',
                'manage_reservations_admin', 'manage_slots', 'view_reports',
            ]),
            _role('cassiere',   'Cassiere',    'info',      True,  [
                'view_orders', 'manage_orders', 'view_reports',
            ]),
            _role('cuoco',      'Cuoco',       'success',   True,  [
                'view_orders', 'manage_orders', 'manage_cesto',
            ]),
            _role('utente',     'Utente',      'secondary', True,  []),
        ]
        db.session.add_all(roles)
        db.session.flush()

    # ── Ensure permesso manage_cesto (aggiornamento DB esistenti) ───────────
    _p_cesto = Permission.query.filter_by(name='manage_cesto').first()
    if not _p_cesto:
        _p_cesto = Permission(name='manage_cesto',
                              label='Gestisci cesto cucina (QR)',
                              category='prodotti')
        db.session.add(_p_cesto)
        db.session.flush()
    for _rname in ('cuoco', 'manager', 'superadmin'):
        _r = Role.query.filter_by(name=_rname).first()
        if _r and _p_cesto not in _r.permissions:
            _r.permissions.append(_p_cesto)

    # ── Super admin globale (unico, tenant_id=None) ───────────────────────
    if not User.query.filter_by(is_admin=True).first():
        admin = User(username='admin', email='admin@bar.local',
                     is_admin=True, tenant_id=None,
                     wallet_balance=0.0, loyalty_points=0)
        admin.set_password('admin123')
        db.session.add(admin)

    # ── Super admin DS Consulting ──────────────────────────────────────────
    if not User.query.filter_by(username='super_admin').first():
        sa = User(username='super_admin', email='admin@dsconsulting.it',
                  is_admin=True, tenant_id=None,
                  wallet_balance=0.0, loyalty_points=0)
        sa.set_password('DSConsulting2025!')
        db.session.add(sa)

    # ── Categorie prodotti ────────────────────────────────────────────────
    if not Category.query.first():
        cats = [
            Category(name='Panini',   icon='fa-burger',       color='warning'),
            Category(name='Primo',    icon='fa-bowl-food',    color='danger'),
            Category(name='Insalate', icon='fa-leaf',         color='success'),
            Category(name='Contorni', icon='fa-carrot',       color='info'),
            Category(name='Dolci',    icon='fa-cake-candles', color='pink'),
            Category(name='Bevande',  icon='fa-bottle-water', color='primary'),
        ]
        db.session.add_all(cats)

    # ── Slot orari ────────────────────────────────────────────────────────
    if not TimeSlot.query.first():
        for t in Config.PICKUP_SLOTS:
            db.session.add(TimeSlot(time_str=t, max_orders=20, is_active=True))

    # ── Tavoli ────────────────────────────────────────────────────────────
    if not Table.query.first():
        tables = [
            (1, 2, 'Finestra'),  (2, 2, 'Finestra'),
            (3, 4, 'Centro'),    (4, 4, 'Centro'),
            (5, 4, 'Centro'),    (6, 4, 'Centro'),
            (7, 6, 'Angolo'),    (8, 6, 'Angolo'),
            (9, 2, 'Bancone'),   (10, 2, 'Bancone'),
        ]
        for num, seats, loc in tables:
            db.session.add(Table(number=num, seats=seats, location=loc))

    # ── Categorie ingredienti builder ─────────────────────────────────────
    if not IngredientCategory.query.first():
        ing_cats = [
            # Panino
            IngredientCategory(name='Pane',     builder_type='panino',   is_required=True,
                               max_choices=1,  sort_order=1, icon='fa-bread-slice'),
            IngredientCategory(name='Proteina', builder_type='both',     is_required=True,
                               max_choices=2,  sort_order=2, icon='fa-drumstick-bite'),
            IngredientCategory(name='Verdure',  builder_type='both',     is_required=False,
                               max_choices=5,  sort_order=3, icon='fa-leaf'),
            IngredientCategory(name='Salse',    builder_type='both',     is_required=False,
                               max_choices=2,  sort_order=4, icon='fa-droplet'),
            IngredientCategory(name='Extra',    builder_type='both',     is_required=False,
                               max_choices=3,  sort_order=5, icon='fa-plus'),
            # Insalata
            IngredientCategory(name='Base insalata', builder_type='insalata', is_required=True,
                               max_choices=1,  sort_order=1, icon='fa-leaf'),
            IngredientCategory(name='Condimento',    builder_type='insalata', is_required=False,
                               max_choices=1,  sort_order=6, icon='fa-bottle-droplet'),
            IngredientCategory(name='Topping',       builder_type='insalata', is_required=False,
                               max_choices=2,  sort_order=7, icon='fa-seedling'),
        ]
        db.session.add_all(ing_cats)
        db.session.flush()

        # Recupera IDs
        pane     = IngredientCategory.query.filter_by(name='Pane').first()
        proteina = IngredientCategory.query.filter_by(name='Proteina').first()
        verdure  = IngredientCategory.query.filter_by(name='Verdure').first()
        salse    = IngredientCategory.query.filter_by(name='Salse').first()
        extra    = IngredientCategory.query.filter_by(name='Extra').first()
        base_ins = IngredientCategory.query.filter_by(name='Base insalata').first()
        condim   = IngredientCategory.query.filter_by(name='Condimento').first()
        topping  = IngredientCategory.query.filter_by(name='Topping').first()

        ingredients = [
            # Pane
            Ingredient(name='Pane bianco',       price_extra=0.00, category_id=pane.id,     is_vegetarian=True),
            Ingredient(name='Pane integrale',     price_extra=0.00, category_id=pane.id,     is_vegetarian=True),
            Ingredient(name='Ciabatta',           price_extra=0.00, category_id=pane.id,     is_vegetarian=True),
            Ingredient(name='Rosetta',            price_extra=0.00, category_id=pane.id,     is_vegetarian=True),
            Ingredient(name='Senza glutine',      price_extra=0.50, category_id=pane.id,     is_vegetarian=True,  allergens=''),
            # Proteina
            Ingredient(name='Prosciutto cotto',   price_extra=0.00, category_id=proteina.id),
            Ingredient(name='Prosciutto crudo',   price_extra=0.00, category_id=proteina.id),
            Ingredient(name='Tonno',              price_extra=0.00, category_id=proteina.id),
            Ingredient(name='Mozzarella',         price_extra=0.00, category_id=proteina.id, is_vegetarian=True,  allergens='latte'),
            Ingredient(name='Formaggio',          price_extra=0.00, category_id=proteina.id, is_vegetarian=True,  allergens='latte'),
            Ingredient(name='Bresaola',           price_extra=0.30, category_id=proteina.id),
            Ingredient(name='Salmone',            price_extra=0.50, category_id=proteina.id, allergens='pesce'),
            Ingredient(name='Feta',               price_extra=0.30, category_id=proteina.id, is_vegetarian=True,  allergens='latte'),
            Ingredient(name='Pollo grigliato',    price_extra=0.50, category_id=proteina.id),
            Ingredient(name='Legumi misti',       price_extra=0.00, category_id=proteina.id, is_vegetarian=True),
            # Verdure
            Ingredient(name='Lattuga',            price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Rucola',             price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Pomodoro',           price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Cetriolo',           price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Cipolla',            price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Peperoni',           price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Mais',               price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Olive',              price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Carote',             price_extra=0.00, category_id=verdure.id,  is_vegetarian=True),
            Ingredient(name='Avocado',            price_extra=0.50, category_id=verdure.id,  is_vegetarian=True),
            # Salse
            Ingredient(name='Maionese',           price_extra=0.00, category_id=salse.id,    is_vegetarian=True,  allergens='uova'),
            Ingredient(name='Senape',             price_extra=0.00, category_id=salse.id,    is_vegetarian=True),
            Ingredient(name='Ketchup',            price_extra=0.00, category_id=salse.id,    is_vegetarian=True),
            Ingredient(name='Pesto',              price_extra=0.20, category_id=salse.id,    is_vegetarian=True,  allergens='frutta a guscio'),
            Ingredient(name='Hummus',             price_extra=0.20, category_id=salse.id,    is_vegetarian=True),
            Ingredient(name='Yogurt greco',       price_extra=0.20, category_id=salse.id,    is_vegetarian=True,  allergens='latte'),
            Ingredient(name='Tahini',             price_extra=0.20, category_id=salse.id,    is_vegetarian=True,  allergens='sesamo'),
            # Extra
            Ingredient(name='Uovo',               price_extra=0.30, category_id=extra.id,    is_vegetarian=True,  allergens='uova'),
            Ingredient(name='Bacon',              price_extra=0.30, category_id=extra.id),
            Ingredient(name='Mozzarella extra',   price_extra=0.30, category_id=extra.id,    is_vegetarian=True,  allergens='latte'),
            Ingredient(name='Parmigiano',         price_extra=0.20, category_id=extra.id,    is_vegetarian=True,  allergens='latte'),
            Ingredient(name='Crostini',           price_extra=0.00, category_id=extra.id,    is_vegetarian=True),
            # Base insalata
            Ingredient(name='Lattuga mista',      price_extra=0.00, category_id=base_ins.id, is_vegetarian=True),
            Ingredient(name='Rucola',             price_extra=0.00, category_id=base_ins.id, is_vegetarian=True),
            Ingredient(name='Spinaci baby',       price_extra=0.00, category_id=base_ins.id, is_vegetarian=True),
            Ingredient(name='Iceberg',            price_extra=0.00, category_id=base_ins.id, is_vegetarian=True),
            # Condimento
            Ingredient(name='Aceto balsamico',    price_extra=0.00, category_id=condim.id,   is_vegetarian=True),
            Ingredient(name='Olio e limone',      price_extra=0.00, category_id=condim.id,   is_vegetarian=True),
            Ingredient(name='Ranch',              price_extra=0.20, category_id=condim.id,   is_vegetarian=True,  allergens='uova, latte'),
            # Topping
            Ingredient(name='Crostini',           price_extra=0.00, category_id=topping.id,  is_vegetarian=True),
            Ingredient(name='Semi di girasole',   price_extra=0.00, category_id=topping.id,  is_vegetarian=True),
            Ingredient(name='Sesamo',             price_extra=0.00, category_id=topping.id,  is_vegetarian=True,  allergens='sesamo'),
            Ingredient(name='Pinoli',             price_extra=0.30, category_id=topping.id,  is_vegetarian=True,  allergens='frutta a guscio'),
            Ingredient(name='Parmigiano',         price_extra=0.20, category_id=topping.id,  is_vegetarian=True,  allergens='latte'),
        ]
        db.session.add_all(ingredients)

    # ── Categorie poke (aggiunta idempotente) ─────────────────────────────
    if not IngredientCategory.query.filter_by(builder_type='poke').first():
        poke_cats = [
            IngredientCategory(name='Base poke',     builder_type='poke', is_required=True,
                               max_choices=1,  sort_order=1, icon='fa-bowl-food'),
            IngredientCategory(name='Proteina poke', builder_type='poke', is_required=True,
                               max_choices=2,  sort_order=2, icon='fa-fish'),
            IngredientCategory(name='Verdure poke',  builder_type='poke', is_required=False,
                               max_choices=5,  sort_order=3, icon='fa-seedling'),
            IngredientCategory(name='Salsa poke',    builder_type='poke', is_required=True,
                               max_choices=1,  sort_order=4, icon='fa-droplet'),
            IngredientCategory(name='Extra poke',    builder_type='poke', is_required=False,
                               max_choices=3,  sort_order=5, icon='fa-plus'),
        ]
        db.session.add_all(poke_cats)
        db.session.flush()

        bp = IngredientCategory.query.filter_by(name='Base poke').first()
        pp = IngredientCategory.query.filter_by(name='Proteina poke').first()
        vp = IngredientCategory.query.filter_by(name='Verdure poke').first()
        sp = IngredientCategory.query.filter_by(name='Salsa poke').first()
        ep = IngredientCategory.query.filter_by(name='Extra poke').first()

        poke_ings = [
            # Basi
            Ingredient(name='Riso bianco',       price_extra=0.00, category_id=bp.id, is_vegetarian=True),
            Ingredient(name='Riso integrale',    price_extra=0.00, category_id=bp.id, is_vegetarian=True),
            Ingredient(name='Quinoa',            price_extra=0.30, category_id=bp.id, is_vegetarian=True),
            Ingredient(name='Mix riso e quinoa', price_extra=0.20, category_id=bp.id, is_vegetarian=True),
            # Proteine
            Ingredient(name='Tonno marinato',    price_extra=0.00, category_id=pp.id, allergens='pesce'),
            Ingredient(name='Salmone',           price_extra=0.50, category_id=pp.id, allergens='pesce'),
            Ingredient(name='Polpo',             price_extra=0.50, category_id=pp.id, allergens='molluschi'),
            Ingredient(name='Gamberi',           price_extra=0.50, category_id=pp.id, allergens='crostacei'),
            Ingredient(name='Tofu',              price_extra=0.00, category_id=pp.id, is_vegetarian=True),
            Ingredient(name='Pollo teriyaki',    price_extra=0.30, category_id=pp.id),
            Ingredient(name='Avocado',           price_extra=0.50, category_id=pp.id, is_vegetarian=True),
            # Verdure
            Ingredient(name='Edamame',           price_extra=0.00, category_id=vp.id, is_vegetarian=True),
            Ingredient(name='Cetriolo',          price_extra=0.00, category_id=vp.id, is_vegetarian=True),
            Ingredient(name='Mais',              price_extra=0.00, category_id=vp.id, is_vegetarian=True),
            Ingredient(name='Carota julienne',   price_extra=0.00, category_id=vp.id, is_vegetarian=True),
            Ingredient(name='Cavolo rosso',      price_extra=0.00, category_id=vp.id, is_vegetarian=True),
            Ingredient(name='Mango',             price_extra=0.30, category_id=vp.id, is_vegetarian=True),
            Ingredient(name='Cipolla rossa',     price_extra=0.00, category_id=vp.id, is_vegetarian=True),
            # Salse
            Ingredient(name='Salsa ponzu',       price_extra=0.00, category_id=sp.id, is_vegetarian=True),
            Ingredient(name='Maionese spicy',    price_extra=0.00, category_id=sp.id, is_vegetarian=True, allergens='uova'),
            Ingredient(name='Teriyaki',          price_extra=0.00, category_id=sp.id, is_vegetarian=True),
            Ingredient(name='Salsa di sesamo',   price_extra=0.20, category_id=sp.id, is_vegetarian=True, allergens='sesamo'),
            Ingredient(name='Miso',              price_extra=0.20, category_id=sp.id, is_vegetarian=True),
            # Extra
            Ingredient(name='Sesamo',            price_extra=0.00, category_id=ep.id, is_vegetarian=True, allergens='sesamo'),
            Ingredient(name='Cipollotto',        price_extra=0.00, category_id=ep.id, is_vegetarian=True),
            Ingredient(name='Tempura flakes',    price_extra=0.30, category_id=ep.id, allergens='glutine, uova'),
            Ingredient(name='Alga nori',         price_extra=0.20, category_id=ep.id, is_vegetarian=True),
            Ingredient(name='Lime',              price_extra=0.00, category_id=ep.id, is_vegetarian=True),
        ]
        db.session.add_all(poke_ings)

    # ── Nuovi permessi (idempotente su DB esistenti) ───────────────────────
    extra_perms = [
        ('manage_settings',    'Configurazioni sistema (Telegram/Email)', 'sistema'),
        ('manage_polls',       'Gestisci sondaggi',                       'comunicazioni'),
        ('send_notifications', 'Invia notifiche Telegram/Email',          'comunicazioni'),
        ('manage_clients',     'Gestisci clienti (anagrafica)',            'sistema'),
    ]
    for pname, plabel, pcat in extra_perms:
        if not Permission.query.filter_by(name=pname).first():
            db.session.add(Permission(name=pname, label=plabel, category=pcat))

    # ── Rimozione utenti demo obsoleti (eseguita una volta sola) ─────────
    for _demo_email in ('cliente1@bar.local', 'cliente2@bar.local'):
        _demo_user = User.query.filter_by(email=_demo_email).first()
        if _demo_user:
            db.session.delete(_demo_user)
            db.session.flush()

    # ── Account di lavoro (idempotente) ──────────────────────────────────
    _crew = [
        # (email, username, password, role_name, is_client, wallet)
        ('banco@bar.local',   'banco_staff',  'Banco2024!',  'cassiere', False, 0.0),
        ('cucina@bar.local',  'cuoco_mario',  'Cucina2024!', 'cuoco',    False, 0.0),
        ('sala@bar.local',    'staff_sala',   'Sala2024!',   'manager',  False, 0.0),
    ]
    for email, username, password, role_name, is_client, wallet in _crew:
        if not User.query.filter_by(email=email).first():
            role = Role.query.filter_by(name=role_name).first()
            base = username; n = 2
            while User.query.filter_by(username=base).first():
                base = f'{username}{n}'; n += 1
            u = User(
                username=base, email=email,
                is_active=True, is_client=is_client,
                wallet_balance=wallet, loyalty_points=0,
                tenant_id=default_tenant.id,
            )
            u.set_password(password)
            if role:
                u.roles.append(role)
            db.session.add(u)

    # ── Articoli banco POS (idempotente) ─────────────────────────────────
    if not BancoItem.query.filter_by(tenant_id=default_tenant.id).first():
        _banco_items = [
            # (name, price, icon, color, sort_order)
            # Caffetteria
            ('Caffè',           1.10, 'fa-mug-hot',       'warning',  1),
            ('Caffè macchiato', 1.20, 'fa-mug-hot',       'warning',  2),
            ('Cappuccino',      1.50, 'fa-mug-hot',       'warning',  3),
            ('Latte macchiato', 1.60, 'fa-mug-hot',       'warning',  4),
            ('Caffè americano', 1.30, 'fa-mug-hot',       'warning',  5),
            ('Tè caldo',        1.20, 'fa-mug-saucer',    'warning',  6),
            ('Orzo',            1.10, 'fa-mug-hot',       'warning',  7),
            # Bevande fredde
            ('Acqua naturale',  0.50, 'fa-bottle-water',  'info',     10),
            ('Acqua frizzante', 0.50, 'fa-bottle-water',  'info',     11),
            ('Succo di frutta', 1.50, 'fa-wine-glass',    'success',  12),
            ('Bibita lattina',  1.50, 'fa-wine-bottle',   'danger',   13),
            ('Birra media',     2.50, 'fa-beer-mug-empty','warning',  14),
            # Snack freddi
            ('Tramezzino',      2.50, 'fa-burger',        'success',  20),
            ('Toast',           2.00, 'fa-burger',        'success',  21),
            ('Panino semplice', 2.50, 'fa-burger',        'success',  22),
            ('Cornetto salato', 1.80, 'fa-bread-slice',   'warning',  23),
            # Dolci
            ('Cornetto vuoto',  1.20, 'fa-cookie',        'warning',  30),
            ('Cornetto crema',  1.40, 'fa-cookie',        'warning',  31),
            ('Cornetto marmellata', 1.40, 'fa-cookie',    'warning',  32),
            ('Torta fetta',     2.00, 'fa-cake-candles',  'pink',     33),
            ('Biscotti (3 pz)', 0.80, 'fa-cookie-bite',   'warning',  34),
            # Altro
            ('Crackers',        0.50, 'fa-cookie-bite',   'secondary',40),
            ('Cioccolata calda',1.80, 'fa-mug-hot',       'warning',  41),
        ]
        for name, price, icon, color, sort_order in _banco_items:
            db.session.add(BancoItem(
                name=name, price=price, icon=icon, color=color,
                sort_order=sort_order, is_active=True,
                tenant_id=default_tenant.id,
            ))

    # ── Impostazioni di default ────────────────────────────────────────────
    default_settings = [
        # Anagrafica azienda gestore
        ('company_name',    '',  'Ragione sociale'),
        ('company_address', '',  'Indirizzo'),
        ('company_city',    '',  'Città'),
        ('company_vat',     '',  'Partita IVA'),
        ('company_phone',   '',  'Telefono'),
        ('company_email',   '',  'Email'),
        # Notifiche
        ('telegram_bot_token',     '',      'Token Bot Telegram'),
        ('telegram_chat_id',       '',      'Chat ID canale Telegram'),
        ('gmail_user',             '',      'Account Gmail mittente'),
        ('gmail_app_password',     '',      'App Password Gmail'),
        # Bonus benvenuto
        ('registration_bonus',     '0',     'Bonus wallet alla registrazione €'),
        # Fedeltà
        ('loyalty_points_per_euro','10',    'Punti per ogni euro speso'),
        ('loyalty_reward_points',  '100',   'Punti necessari per riscatto premio'),
        ('loyalty_reward_amount',  '1.00',  'Importo premio wallet €'),
        # Prezzi builder
        ('builder_price_panino',   '3.50',  'Prezzo base panino personalizzato €'),
        ('builder_price_insalata', '3.00',  'Prezzo base insalata personalizzata €'),
        ('builder_price_poke',     '4.00',  'Prezzo base poke personalizzato €'),
        # Funzionalita' attivabili ('0' = disattivata)
        ('tables_enabled',         '1',     'Abilita gestione tavoli e prenotazioni'),
        # Reminder
        ('table_reminder_minutes', '10',    'Minuti anticipo reminder prenotazione tavolo'),
        ('order_reminder_minutes', '15',    'Minuti anticipo reminder ritiro ordine'),
        ('meal_reminder_minutes',  '15',    'Minuti anticipo reminder pasto aziendale'),
        # DS Consulting – piattaforma
        ('platform_fee_percentage', '0.0',  'Percentuale fee DS Consulting sul fatturato tenant (%)'),
        ('tenant_monthly_fee',      '0.0',  'Canone fisso mensile per tenant (€)'),
    ]
    for skey, sval, slabel in default_settings:
        if not AppSetting.query.filter_by(key=skey).first():
            db.session.add(AppSetting(key=skey, value=sval, label=slabel))

    db.session.commit()
