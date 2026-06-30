import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Devi effettuare il login per accedere a questa pagina.'
login_manager.login_message_category = 'warning'
oauth = OAuth()


def create_app(config_object='config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Authlib: disabilita verifica HTTPS in sviluppo locale
    if app.config.get('AUTHLIB_INSECURE_TRANSPORT'):
        os.environ['AUTHLIB_INSECURE_TRANSPORT'] = '1'

    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)

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

    # Composizione e allergeni del pasto aziendale del giorno
    _ensure('daily_fixed_meals', 'composition', "TEXT DEFAULT ''")
    _ensure('daily_fixed_meals', 'allergens',   "VARCHAR(512) DEFAULT ''")
    # Portate strutturate del menu aziendale
    _ensure('daily_fixed_meals', 'primo',    "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'secondo',  "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'contorno', "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'bevanda',  "VARCHAR(256) DEFAULT ''")
    _ensure('daily_fixed_meals', 'caffe',    "VARCHAR(128) DEFAULT ''")

    # Fasce orarie tavoli (nuova tabella) — creata da create_all se non esiste
    # Colonne aggiuntive su table_reservations per il nuovo sistema a fasce
    _ensure('table_reservations', 'band_id',       "INTEGER")
    _ensure('table_reservations', 'session_start',  "VARCHAR(5) DEFAULT ''")
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


def _seed_defaults():
    from app.models import (User, Category, TimeSlot, Table,
                            IngredientCategory, Ingredient,
                            Permission, Role, AppSetting, Tenant)
    from sqlalchemy import text
    from config import Config

    # ── Tenant di default ─────────────────────────────────────────────────
    default_tenant = Tenant.query.filter_by(slug='default').first()
    if not default_tenant:
        default_tenant = Tenant(
            name='QuickLunch',
            slug='default',
            primary_color='#e94560',
            is_active=True,
        )
        db.session.add(default_tenant)
        db.session.flush()  # ottieni l'ID prima del commit

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
                'view_orders', 'manage_orders',
            ]),
            _role('utente',     'Utente',      'secondary', True,  []),
        ]
        db.session.add_all(roles)
        db.session.flush()

    # ── Super admin globale (unico, tenant_id=None) ───────────────────────
    if not User.query.filter_by(is_admin=True).first():
        admin = User(username='admin', email='admin@bar.local',
                     is_admin=True, tenant_id=None,
                     wallet_balance=0.0, loyalty_points=0)
        admin.set_password('admin123')
        db.session.add(admin)

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

    # ── Impostazioni di default (vuote) ───────────────────────────────────
    default_settings = [
        ('telegram_bot_token', '', 'Token Bot Telegram'),
        ('telegram_chat_id',   '', 'Chat ID Telegram'),
        ('gmail_user',         '', 'Account Gmail mittente'),
        ('gmail_app_password', '', 'App Password Gmail'),
    ]
    for skey, sval, slabel in default_settings:
        if not AppSetting.query.filter_by(key=skey).first():
            db.session.add(AppSetting(key=skey, value=sval, label=slabel))

    db.session.commit()
