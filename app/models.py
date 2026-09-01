from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager, numero_italiano

# ── RBAC association tables ────────────────────────────────────────────────────

user_roles = db.Table(
    'user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id',  ondelete='CASCADE'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id',  ondelete='CASCADE'), primary_key=True),
)

role_permissions = db.Table(
    'role_permissions',
    db.Column('role_id',       db.Integer, db.ForeignKey('roles.id',       ondelete='CASCADE'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
)


# ── Tenant ─────────────────────────────────────────────────────────────────────

class Tenant(db.Model):
    __tablename__ = 'tenants'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(128), nullable=False)
    slug          = db.Column(db.String(64), unique=True, nullable=False)
    logo_url      = db.Column(db.String(256), default='')
    primary_color = db.Column(db.String(20),  default='#e94560')
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship('User', foreign_keys='User.tenant_id', lazy='dynamic')

    @property
    def user_count(self):
        return self.users.count()

    @property
    def register_url(self):
        from flask import url_for
        try:
            return url_for('tenant.register', slug=self.slug, _external=True)
        except Exception:
            return f'/t/{self.slug}/register'


# ── Permission ─────────────────────────────────────────────────────────────────

class Permission(db.Model):
    __tablename__ = 'permissions'
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(64),  unique=True, nullable=False)  # codename
    label    = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(64),  default='generale')


# ── Role ───────────────────────────────────────────────────────────────────────

class Role(db.Model):
    __tablename__ = 'roles'
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(64),  unique=True, nullable=False)
    label     = db.Column(db.String(128), nullable=False)
    color     = db.Column(db.String(20),  default='secondary')
    is_system = db.Column(db.Boolean,     default=False)  # system roles can't be deleted
    permissions = db.relationship('Permission', secondary=role_permissions, lazy='subquery')

    def permission_names(self):
        return {p.name for p in self.permissions}


# ── User ───────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    is_client = db.Column(db.Boolean, default=False)
    wallet_balance   = db.Column(db.Float, default=0.0)
    wallet_overdraft = db.Column(db.Float, default=0.0)  # massimo rosso consentito
    loyalty_points   = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    google_id  = db.Column(db.String(128), nullable=True, unique=True)
    avatar_url = db.Column(db.String(256), default='')

    # ── Anagrafica (clienti) ──────────────────────────────────────────────────
    first_name       = db.Column(db.String(64),  default='')
    last_name        = db.Column(db.String(64),  default='')
    phone            = db.Column(db.String(20),  default='')
    birth_date       = db.Column(db.Date,        nullable=True)
    address          = db.Column(db.Text,        default='')
    telegram_chat_id = db.Column(db.String(64),  default='')

    # ── MFA (TOTP) ────────────────────────────────────────────────────────────
    totp_secret  = db.Column(db.String(64),  nullable=True)
    totp_enabled = db.Column(db.Boolean,     default=False)

    @property
    def full_name(self):
        parts = [self.first_name or '', self.last_name or '']
        return ' '.join(p for p in parts if p) or self.username

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id], overlaps='users')

    orders               = db.relationship('Order',            back_populates='user', lazy='dynamic')
    transactions         = db.relationship('Transaction',      back_populates='user', lazy='dynamic')
    reservations         = db.relationship('TableReservation', back_populates='user', lazy='dynamic')
    corporate_membership = db.relationship('CorporateMembership', back_populates='user',
                                           uselist=False)
    roles        = db.relationship('Role', secondary=user_roles, lazy='subquery',
                                   backref=db.backref('users', lazy='dynamic'))

    # ── Auth helpers ──────────────────────────────────────────────────────────

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    # ── RBAC helpers ──────────────────────────────────────────────────────────

    def has_permission(self, perm_name):
        """True if admin (bypass) or if any assigned role grants the permission."""
        if self.is_admin:
            return True
        return any(
            any(p.name == perm_name for p in role.permissions)
            for role in self.roles
        )

    def has_role(self, role_name):
        return any(r.name == role_name for r in self.roles)

    @property
    def is_staff(self):
        """Has at least one backoffice permission (can access the admin area)."""
        if self.is_admin:
            return True
        BACKOFFICE = {
            'view_orders', 'manage_orders', 'manage_products', 'manage_categories',
            'manage_ingredients', 'manage_stock', 'manage_tables_admin',
            'manage_reservations_admin', 'manage_slots', 'manage_users',
            'manage_clients', 'manage_roles', 'view_reports',
        }
        return any(
            any(p.name in BACKOFFICE for p in role.permissions)
            for role in self.roles
        )

    @property
    def is_superadmin(self):
        """True solo per il super admin globale (admin@bar.local)."""
        return self.is_admin

    @property
    def all_permission_names(self):
        if self.is_admin:
            return {'*'}
        return {p.name for role in self.roles for p in role.permissions}

    # ── Wallet helpers ────────────────────────────────────────────────────────

    def credit_wallet(self, amount, description, order_id=None):
        self.wallet_balance = round(self.wallet_balance + amount, 2)
        db.session.add(Transaction(user_id=self.id, amount=amount,
                                   ttype='topup', description=description, order_id=order_id))

    def debit_wallet(self, amount, description, order_id=None):
        self.wallet_balance = round(self.wallet_balance - amount, 2)
        db.session.add(Transaction(user_id=self.id, amount=-amount,
                                   ttype='payment', description=description, order_id=order_id))

    def add_points(self, points):
        self.loyalty_points += points
        db.session.add(Transaction(user_id=self.id, amount=0,
                                   ttype='points', description=f'+{points} punti fedeltà'))

    def redeem_points(self, points, reward_amount):
        self.loyalty_points -= points
        self.wallet_balance = round(self.wallet_balance + reward_amount, 2)
        db.session.add(Transaction(user_id=self.id, amount=reward_amount,
                                   ttype='reward',
                                   description=f'Premio: {points} punti → +{numero_italiano(reward_amount)}€'))

    def apply_registration_bonus(self):
        """Accredita il bonus di benvenuto configurato in Impostazioni.

        Va chiamato per ogni nuovo cliente, da qualunque via arrivi
        (registrazione pubblica, Google, link del tenant, creazione da
        backoffice): il bonus deve valere per tutti allo stesso modo.
        Non fa nulla se il bonus non e' configurato o e' zero.
        """
        from app.notifications import get_setting
        try:
            val = float(get_setting('registration_bonus') or 0)
        except (ValueError, TypeError):
            val = 0.0
        if val <= 0:
            return 0.0
        self.credit_wallet(val, 'Bonus benvenuto')
        db.session.commit()
        return val


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Categorie & Prodotti ───────────────────────────────────────────────────────

class Category(db.Model):
    __tablename__ = 'categories'
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(64), nullable=False)
    icon      = db.Column(db.String(64), default='fa-utensils')
    color     = db.Column(db.String(32), default='secondary')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    products  = db.relationship('Product', back_populates='category', lazy='dynamic')


class Product(db.Model):
    __tablename__ = 'products'
    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(128), nullable=False)
    description    = db.Column(db.Text, default='')
    price          = db.Column(db.Float, nullable=False)
    category_id    = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    daily_quantity = db.Column(db.Integer, default=20)
    is_active      = db.Column(db.Boolean, default=True)
    allergens      = db.Column(db.String(512), default='')
    barcode        = db.Column(db.String(32), nullable=True, index=True)
    tenant_id      = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    category = db.relationship('Category', back_populates='products')
    order_items = db.relationship('OrderItem', back_populates='product')
    daily_stocks = db.relationship('DailyStock', back_populates='product')

    @property
    def allergen_list(self):
        keys = [k.strip() for k in (self.allergens or '').split(',') if k.strip()]
        return [(k, *ALLERGEN_LABELS[k]) for k in keys if k in ALLERGEN_LABELS]

    def available_today(self):
        stock = DailyStock.query.filter_by(product_id=self.id, stock_date=date.today()).first()
        if stock:
            return stock.quantity_available - stock.quantity_reserved
        return self.daily_quantity

    def get_or_create_stock(self):
        stock = DailyStock.query.filter_by(product_id=self.id, stock_date=date.today()).first()
        if not stock:
            stock = DailyStock(product_id=self.id, stock_date=date.today(),
                               quantity_available=self.daily_quantity, quantity_reserved=0)
            db.session.add(stock)
        return stock


class DailyStock(db.Model):
    __tablename__ = 'daily_stocks'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    stock_date = db.Column(db.Date, nullable=False, default=date.today)
    quantity_available = db.Column(db.Integer, nullable=False)
    quantity_reserved = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint('product_id', 'stock_date'),)
    product = db.relationship('Product', back_populates='daily_stocks')


# ── Slot orari ─────────────────────────────────────────────────────────────────

class TimeSlot(db.Model):
    __tablename__ = 'time_slots'
    id                   = db.Column(db.Integer, primary_key=True)
    time_str             = db.Column(db.String(5), nullable=False)
    max_orders           = db.Column(db.Integer, default=20)
    is_active            = db.Column(db.Boolean, default=True)
    seat_duration_minutes= db.Column(db.Integer, default=0)  # 0 = illimitato
    tenant_id            = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    orders             = db.relationship('Order', back_populates='slot')
    table_reservations = db.relationship('TableReservation', back_populates='slot')

    def orders_today(self):
        return Order.query.filter_by(slot_id=self.id, order_date=date.today())\
            .filter(Order.status != 'cancelled').count()

    def is_full(self):
        return self.orders_today() >= self.max_orders


# ── Ordini ─────────────────────────────────────────────────────────────────────

class Order(db.Model):
    __tablename__ = 'orders'
    id         = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(32), nullable=True, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    slot_id    = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=True)
    order_date = db.Column(db.Date, nullable=False, default=date.today)
    status     = db.Column(db.String(20), default='pending')
    total_price= db.Column(db.Float, default=0.0)
    notes         = db.Column(db.Text, default='')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    tenant_id     = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    reminder_sent = db.Column(db.Boolean, default=False)

    user = db.relationship('User', back_populates='orders')
    slot = db.relationship('TimeSlot', back_populates='orders')
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    custom_items = db.relationship('CustomOrderItem', back_populates='order', cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', back_populates='order')

    STATUS_LABELS = {
        'pending':    ('Ricevuto',       'warning'),
        'confirmed':  ('Confermato',     'info'),
        'preparing':  ('In preparazione','primary'),
        'ready':      ('Pronto',         'success'),
        'completed':  ('Consegnato',     'secondary'),
        'cancelled':  ('Annullato',      'danger'),
    }

    def label(self):
        return self.STATUS_LABELS.get(self.status, (self.status, 'secondary'))

    def compute_total(self):
        regular = sum(i.unit_price * i.quantity for i in self.items)
        custom  = sum(ci.unit_price * ci.quantity for ci in self.custom_items)
        self.total_price = round(regular + custom, 2)


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product', back_populates='order_items')


# ── Builder (panino/insalata personalizzati) ───────────────────────────────────

class IngredientCategory(db.Model):
    __tablename__ = 'ingredient_categories'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(64), nullable=False)
    builder_type = db.Column(db.String(10), nullable=False)
    is_required  = db.Column(db.Boolean, default=False)
    max_choices  = db.Column(db.Integer, default=3)
    sort_order   = db.Column(db.Integer, default=0)
    icon         = db.Column(db.String(32), default='fa-circle')
    tenant_id    = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    ingredients  = db.relationship('Ingredient', back_populates='category',
                                   order_by='Ingredient.name')


class Ingredient(db.Model):
    __tablename__ = 'ingredients'
    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.String(128), nullable=False)
    price_extra       = db.Column(db.Float, default=0.0)
    category_id       = db.Column(db.Integer, db.ForeignKey('ingredient_categories.id'), nullable=False)
    is_active         = db.Column(db.Boolean, default=True)
    is_vegetarian     = db.Column(db.Boolean, default=False)
    allergens         = db.Column(db.String(128), default='')
    tenant_id         = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    # Magazzino (opzionale): grammi per porzione e giacenza attuale in grammi
    grams_per_serving = db.Column(db.Float, nullable=True)
    stock_qty         = db.Column(db.Float, nullable=True)
    category          = db.relationship('IngredientCategory', back_populates='ingredients')


class CustomOrderItem(db.Model):
    __tablename__ = 'custom_order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    builder_type = db.Column(db.String(10), nullable=False)
    label = db.Column(db.String(512), default='')
    unit_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    grill_requested = db.Column(db.Boolean, default=False)
    order = db.relationship('Order', back_populates='custom_items')
    ingredients = db.relationship('CustomOrderItemIngredient', cascade='all, delete-orphan')


class CustomOrderItemIngredient(db.Model):
    __tablename__ = 'custom_order_item_ingredients'
    id = db.Column(db.Integer, primary_key=True)
    custom_item_id = db.Column(db.Integer, db.ForeignKey('custom_order_items.id'), nullable=False)
    ingredient_name = db.Column(db.String(128), nullable=False)
    price_extra = db.Column(db.Float, default=0.0)


# ── Tavoli ─────────────────────────────────────────────────────────────────────

class Table(db.Model):
    __tablename__ = 'tables'
    id           = db.Column(db.Integer, primary_key=True)
    number       = db.Column(db.Integer, nullable=False)
    seats        = db.Column(db.Integer, default=4)
    location     = db.Column(db.String(64), default='')
    is_active    = db.Column(db.Boolean, default=True)
    tenant_id    = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    reservations = db.relationship('TableReservation', back_populates='table')

    def reservation_for(self, slot_id, res_date):
        return TableReservation.query.filter_by(
            table_id=self.id, slot_id=slot_id, reservation_date=res_date
        ).filter(TableReservation.status != 'cancelled').first()

    def is_available(self, slot_id, res_date):
        return self.reservation_for(slot_id, res_date) is None


class TableTimeBand(db.Model):
    """Fascia oraria dei tavoli con durata seduta variabile."""
    __tablename__ = 'table_time_bands'
    id               = db.Column(db.Integer, primary_key=True)
    start_time       = db.Column(db.String(5), nullable=False)   # 'HH:MM'
    end_time         = db.Column(db.String(5), nullable=False)   # 'HH:MM'
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    sort_order       = db.Column(db.Integer, default=0)
    tenant_id        = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    reservations = db.relationship('TableReservation', back_populates='band')

    def computed_slots(self):
        """Restituisce la lista di orari di inizio (HH:MM) calcolati per questa fascia."""
        from datetime import datetime as _dt, timedelta as _td
        fmt = '%H:%M'
        t   = _dt.strptime(self.start_time, fmt)
        end = _dt.strptime(self.end_time, fmt)
        delta = _td(minutes=self.duration_minutes)
        slots = []
        while t + delta <= end:
            slots.append(t.strftime(fmt))
            t += delta
        return slots

    @property
    def label(self):
        return f'{self.start_time} – {self.end_time}  ({self.duration_minutes} min)'


class TableReservation(db.Model):
    __tablename__ = 'table_reservations'
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    table_id         = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    slot_id          = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=True)
    band_id          = db.Column(db.Integer, db.ForeignKey('table_time_bands.id'), nullable=True)
    session_start    = db.Column(db.String(5), default='')  # 'HH:MM' computed from band
    reservation_date = db.Column(db.Date, nullable=False, default=date.today)
    party_size       = db.Column(db.Integer, default=1)
    notes            = db.Column(db.Text, default='')
    status           = db.Column(db.String(20), default='confirmed')
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    checkin_at       = db.Column(db.DateTime, nullable=True)
    table_alert_sent = db.Column(db.Boolean, default=False)
    tenant_id        = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    user  = db.relationship('User', back_populates='reservations')
    table = db.relationship('Table', back_populates='reservations')
    slot  = db.relationship('TimeSlot', back_populates='table_reservations')
    band  = db.relationship('TableTimeBand', back_populates='reservations')

    @property
    def minutes_remaining(self):
        """Minuti rimanenti; None se non c'è check-in o durata non impostata."""
        if not self.checkin_at or not self.slot or not self.slot.seat_duration_minutes:
            return None
        from datetime import datetime as _dt
        elapsed = (_dt.utcnow() - self.checkin_at).total_seconds() / 60
        return max(0, self.slot.seat_duration_minutes - elapsed)

    STATUS_LABELS = {
        'confirmed': ('Confermata', 'success'),
        'cancelled': ('Annullata',  'danger'),
    }

    def label(self):
        return self.STATUS_LABELS.get(self.status, (self.status, 'secondary'))


# ── Transazioni ────────────────────────────────────────────────────────────────

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    ttype = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(256), default='')
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='transactions')
    order = db.relationship('Order', back_populates='transactions')

    TYPE_ICONS = {
        'topup':      ('fa-arrow-down',   'success',   'Ricarica'),
        'payment':    ('fa-arrow-up',     'danger',    'Pagamento'),
        'refund':     ('fa-rotate-left',  'info',      'Rimborso'),
        'reward':     ('fa-gift',         'warning',   'Premio'),
        'points':     ('fa-star',         'purple',    'Punti'),
        'adjustment': ('fa-pen',          'secondary', 'Rettifica'),
        'banco':      ('fa-mug-hot',      'info',      'Banco'),
    }

    def icon_info(self):
        return self.TYPE_ICONS.get(self.ttype, ('fa-circle', 'secondary', self.ttype))


# ── Articoli banco (POS rapido) ───────────────────────────────────────────────

class BancoItem(db.Model):
    __tablename__ = 'banco_items'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(64), nullable=False)
    price      = db.Column(db.Float, nullable=False)
    icon       = db.Column(db.String(64), default='fa-mug-hot')
    color      = db.Column(db.String(32), default='info')
    sort_order = db.Column(db.Integer, default=0)
    is_active  = db.Column(db.Boolean, default=True)
    tenant_id  = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)



# ── Sessioni QR banco ────────────────────────────────────────────────────────

class BancoSession(db.Model):
    __tablename__ = 'banco_sessions'
    id          = db.Column(db.Integer, primary_key=True)
    token       = db.Column(db.String(32), unique=True, nullable=False, index=True)
    staff_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    items_json  = db.Column(db.Text, default='[]')
    total       = db.Column(db.Float, nullable=False)
    status      = db.Column(db.String(20), default='pending')  # pending, paid, expired, cancelled
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at  = db.Column(db.DateTime, nullable=False)
    tenant_id   = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True)
    staff    = db.relationship('User', foreign_keys='BancoSession.staff_id')
    customer = db.relationship('User', foreign_keys='BancoSession.customer_id')


# ── Cesto cucina: etichette QR pre-preparate ─────────────────────────────────

class PrepLabel(db.Model):
    """Un'etichetta QR apposta su un panino/tramezzino preparato in cucina."""
    __tablename__ = 'prep_labels'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(16), unique=True, nullable=False, index=True)
    product_id  = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    batch_id    = db.Column(db.String(24), nullable=True, index=True)
    tenant_id   = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True)
    prepared_at = db.Column(db.DateTime, default=datetime.utcnow)
    prepared_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status      = db.Column(db.String(12), default='ready')  # ready | sold | expired
    sold_at     = db.Column(db.DateTime, nullable=True)
    buyer_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    product  = db.relationship('Product', foreign_keys='PrepLabel.product_id')
    preparer = db.relationship('User',    foreign_keys='PrepLabel.prepared_by')
    buyer    = db.relationship('User',    foreign_keys='PrepLabel.buyer_id')


# ── Prenotazione pasto futuro ─────────────────────────────────────────────────

class Prenotazione(db.Model):
    __tablename__ = 'prenotazioni'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(16), unique=True, nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tenant_id   = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    pickup_date = db.Column(db.Date, nullable=False, index=True)
    slot_id     = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=True)
    status      = db.Column(db.String(16), default='pending')  # pending/confirmed/cancelled
    notes       = db.Column(db.Text, default='')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    total_price = db.Column(db.Float, default=0.0)

    user  = db.relationship('User',     foreign_keys='Prenotazione.user_id')
    slot  = db.relationship('TimeSlot', foreign_keys='Prenotazione.slot_id')
    items = db.relationship('PrenotazioneItem', back_populates='prenotazione',
                            cascade='all, delete-orphan')


class PrenotazioneItem(db.Model):
    __tablename__ = 'prenotazione_items'
    id              = db.Column(db.Integer, primary_key=True)
    prenotazione_id = db.Column(db.Integer, db.ForeignKey('prenotazioni.id'), nullable=False)
    product_id      = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity        = db.Column(db.Integer, nullable=False, default=1)
    unit_price      = db.Column(db.Float, nullable=False)

    prenotazione = db.relationship('Prenotazione', back_populates='items')
    product      = db.relationship('Product', foreign_keys='PrenotazioneItem.product_id')


# ── Web Push subscriptions ────────────────────────────────────────────────────

class PushSubscription(db.Model):
    """Sottoscrizione Web Push di un dispositivo/browser per un utente."""
    __tablename__ = 'push_subscriptions'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    endpoint   = db.Column(db.Text, nullable=False, unique=True)
    p256dh     = db.Column(db.String(256), nullable=False)
    auth       = db.Column(db.String(64),  nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='push_subscriptions')


# ── Magazzino materiali di consumo ────────────────────────────────────────────

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(128), nullable=False)
    email     = db.Column(db.String(120), default='')
    phone     = db.Column(db.String(30),  default='')
    notes     = db.Column(db.Text,        default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    items     = db.relationship('ConsumableItem', back_populates='supplier')


class ConsumableItem(db.Model):
    __tablename__ = 'consumable_items'
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(128), nullable=False)
    unit            = db.Column(db.String(20),  default='pz')
    quantity        = db.Column(db.Float,        default=0.0)
    min_threshold   = db.Column(db.Float,        default=0.0)
    supplier_id     = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    alert_active    = db.Column(db.Boolean, default=False)
    last_alert_at   = db.Column(db.DateTime, nullable=True)
    tenant_id       = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    supplier        = db.relationship('Supplier', back_populates='items')
    movements       = db.relationship('ConsumableMovement', back_populates='item',
                                      cascade='all, delete-orphan',
                                      order_by='ConsumableMovement.created_at.desc()')

    @property
    def is_below_threshold(self):
        return self.min_threshold > 0 and self.quantity <= self.min_threshold

    @property
    def stock_status(self):
        if self.min_threshold <= 0:
            return 'ok'
        ratio = self.quantity / self.min_threshold if self.min_threshold else 1
        if ratio <= 1.0:
            return 'critical'
        if ratio <= 1.5:
            return 'warning'
        return 'ok'


class ConsumableMovement(db.Model):
    __tablename__ = 'consumable_movements'
    id         = db.Column(db.Integer, primary_key=True)
    item_id    = db.Column(db.Integer, db.ForeignKey('consumable_items.id'), nullable=False)
    delta      = db.Column(db.Float,       nullable=False)
    notes      = db.Column(db.String(256), default='')
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    item       = db.relationship('ConsumableItem', back_populates='movements')
    user       = db.relationship('User')


# ── Convenzioni aziendali (pasto fisso) ───────────────────────────────────────

class CorporateAccount(db.Model):
    __tablename__ = 'corporate_accounts'
    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(128), nullable=False)
    contact_email    = db.Column(db.String(120), default='')
    daily_price      = db.Column(db.Float, default=7.0)
    max_daily_covers = db.Column(db.Integer, default=60)
    notes            = db.Column(db.Text, default='')
    is_active        = db.Column(db.Boolean, default=True)
    tenant_id        = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    memberships      = db.relationship('CorporateMembership', back_populates='corporate',
                                       cascade='all, delete-orphan')
    daily_meals      = db.relationship('DailyFixedMeal', back_populates='corporate',
                                       cascade='all, delete-orphan')
    configurations   = db.relationship('MealConfiguration', back_populates='corporate',
                                       cascade='all, delete-orphan',
                                       order_by='MealConfiguration.sort_order, MealConfiguration.name')

    @property
    def active_members(self):
        return [m for m in self.memberships if m.is_active]


class MealConfiguration(db.Model):
    """Template riutilizzabile per il pasto del giorno di una convenzione."""
    __tablename__ = 'meal_configurations'
    id           = db.Column(db.Integer, primary_key=True)
    corporate_id = db.Column(db.Integer, db.ForeignKey('corporate_accounts.id'), nullable=False)
    name         = db.Column(db.String(128), nullable=False)
    primo        = db.Column(db.String(256), default='')
    secondo      = db.Column(db.String(256), default='')
    contorno     = db.Column(db.String(256), default='')
    bevanda      = db.Column(db.String(256), default='')
    caffe        = db.Column(db.String(128), default='')
    description  = db.Column(db.Text, default='')
    allergens    = db.Column(db.String(512), default='')
    price        = db.Column(db.Float, nullable=True)       # None → usa daily_price della convenzione
    max_bookings = db.Column(db.Integer, nullable=True)     # None → usa max_daily_covers della convenzione
    sort_order   = db.Column(db.Integer, default=0)
    tenant_id    = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    corporate    = db.relationship('CorporateAccount', back_populates='configurations')

    @property
    def allergen_list(self):
        keys = [k.strip() for k in (self.allergens or '').split(',') if k.strip()]
        return [(k, *ALLERGEN_LABELS[k]) for k in keys if k in ALLERGEN_LABELS]


class CorporateMembership(db.Model):
    __tablename__ = 'corporate_memberships'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    corporate_id = db.Column(db.Integer, db.ForeignKey('corporate_accounts.id'), nullable=False)
    is_active    = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint('user_id', 'corporate_id'),)
    user      = db.relationship('User', back_populates='corporate_membership')
    corporate = db.relationship('CorporateAccount', back_populates='memberships')


ALLERGENS = [
    ('glutine',   'Glutine',                 '🌾'),
    ('crostacei', 'Crostacei',               '🦐'),
    ('uova',      'Uova',                    '🥚'),
    ('pesce',     'Pesce',                   '🐟'),
    ('arachidi',  'Arachidi',                '🥜'),
    ('soia',      'Soia',                    '🫘'),
    ('latte',     'Latte e derivati',        '🥛'),
    ('frutta_guscio', 'Frutta a guscio',     '🌰'),
    ('sedano',    'Sedano',                  '🥬'),
    ('senape',    'Senape',                  '🟡'),
    ('sesamo',    'Sesamo',                  '⚪'),
    ('solfiti',   'Anidride solforosa/solfiti', '🍷'),
    ('lupini',    'Lupini',                  '🫛'),
    ('molluschi', 'Molluschi',               '🦪'),
]
ALLERGEN_LABELS = {key: (label, icon) for key, label, icon in ALLERGENS}


class DailyFixedMeal(db.Model):
    __tablename__ = 'daily_fixed_meals'
    id           = db.Column(db.Integer, primary_key=True)
    meal_date    = db.Column(db.Date, nullable=False, default=date.today)
    name         = db.Column(db.String(256), nullable=False)
    description  = db.Column(db.Text, default='')
    composition  = db.Column(db.Text, default='')
    allergens    = db.Column(db.String(512), default='')
    primo        = db.Column(db.String(256), default='')
    secondo      = db.Column(db.String(256), default='')
    contorno     = db.Column(db.String(256), default='')
    bevanda      = db.Column(db.String(256), default='')
    caffe        = db.Column(db.String(128), default='')
    price        = db.Column(db.Float, nullable=False)
    corporate_id = db.Column(db.Integer, db.ForeignKey('corporate_accounts.id'), nullable=False)
    max_bookings = db.Column(db.Integer, default=60)
    is_active    = db.Column(db.Boolean, default=True)
    tenant_id    = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    corporate    = db.relationship('CorporateAccount', back_populates='daily_meals')
    bookings     = db.relationship('CorporateMealBooking', back_populates='meal',
                                   cascade='all, delete-orphan')

    @property
    def booking_count(self):
        return sum((b.quantity or 1) for b in self.bookings if b.status != 'cancelled')

    @property
    def is_available(self):
        return self.is_active and self.booking_count < self.max_bookings

    @property
    def slots_left(self):
        return max(0, self.max_bookings - self.booking_count)

    @property
    def allergen_list(self):
        keys = [k.strip() for k in (self.allergens or '').split(',') if k.strip()]
        return [(k, *ALLERGEN_LABELS[k]) for k in keys if k in ALLERGEN_LABELS]

    @property
    def courses(self):
        labels = [('Primo',   '🥣', self.primo),
                  ('Secondo', '🍗', self.secondo),
                  ('Contorno','🥗', self.contorno),
                  ('Bevanda', '🥤', self.bevanda),
                  ('Caffè',   '☕', self.caffe)]
        return [(lbl, icon, val) for lbl, icon, val in labels if val and val.strip()]


class CorporateMealBooking(db.Model):
    __tablename__ = 'corporate_meal_bookings'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    meal_id      = db.Column(db.Integer, db.ForeignKey('daily_fixed_meals.id'), nullable=False)
    slot_id      = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=True)
    quantity      = db.Column(db.Integer, default=1, nullable=False, server_default='1')
    status        = db.Column(db.String(20), default='booked')  # booked, consumed, cancelled
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    reminder_sent = db.Column(db.Boolean, default=False)
    pickup_token  = db.Column(db.String(16), default='', server_default='')
    __table_args__ = (db.UniqueConstraint('user_id', 'meal_id', name='uq_corp_booking'),)
    user = db.relationship('User')
    meal = db.relationship('DailyFixedMeal', back_populates='bookings')
    slot = db.relationship('TimeSlot')

    STATUS_LABELS = {
        'booked':    ('Prenotato',  'info'),
        'consumed':  ('Consumato',  'success'),
        'cancelled': ('Annullato',  'danger'),
    }

    def label(self):
        return self.STATUS_LABELS.get(self.status, (self.status, 'secondary'))


# ── Impostazioni applicazione ──────────────────────────────────────────────────

class AppSetting(db.Model):
    __tablename__ = 'app_settings'
    id    = db.Column(db.Integer, primary_key=True)
    key   = db.Column(db.String(64),  unique=True, nullable=False)
    value = db.Column(db.Text,        default='')
    label = db.Column(db.String(128), default='')


# ── Sondaggi / Referendum ─────────────────────────────────────────────────────

class Poll(db.Model):
    __tablename__ = 'polls'
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(200), nullable=False)
    poll_date  = db.Column(db.Date,   nullable=False)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    choices    = db.relationship('PollChoice', backref='poll',
                                  cascade='all,delete-orphan',
                                  order_by='PollChoice.id')
    votes      = db.relationship('PollVote', backref='poll',
                                  cascade='all,delete-orphan')

    def total_votes(self):
        return len(self.votes)

    def user_vote(self, user_id):
        return PollVote.query.filter_by(poll_id=self.id, user_id=user_id).first()


class PollChoice(db.Model):
    __tablename__ = 'poll_choices'
    id      = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id'), nullable=False)
    text    = db.Column(db.String(200), nullable=False)
    emoji   = db.Column(db.String(10),  default='🍽️')
    votes   = db.relationship('PollVote', backref='choice',
                               cascade='all,delete-orphan')

    @property
    def vote_count(self):
        return len(self.votes)


class PollVote(db.Model):
    __tablename__ = 'poll_votes'
    id                   = db.Column(db.Integer, primary_key=True)
    poll_id              = db.Column(db.Integer, db.ForeignKey('polls.id'),        nullable=False)
    choice_id            = db.Column(db.Integer, db.ForeignKey('poll_choices.id'), nullable=False)
    user_id              = db.Column(db.Integer, db.ForeignKey('users.id'),        nullable=False)
    voted_at             = db.Column(db.DateTime, default=datetime.utcnow)
    confirm_reservation  = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint('poll_id', 'user_id', name='uq_poll_user'),
    )


# ── Carichi di dati generati ───────────────────────────────────────────────────

class CaricoMensile(db.Model):
    """Un caricamento di dati di prova su un mese.

    Serve a rendere l'operazione reversibile: ogni riga creata viene annotata in
    CaricoMensileRiga, e l'eliminazione del carico ripercorre quell'elenco.
    """
    __tablename__ = 'carichi_mensili'
    id        = db.Column(db.Integer, primary_key=True)
    anno      = db.Column(db.Integer, nullable=False)
    mese      = db.Column(db.Integer, nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    creato_il = db.Column(db.DateTime, default=datetime.utcnow)
    creato_da = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    parametri = db.Column(db.Text, default='')      # JSON degli intervalli usati
    giorni    = db.Column(db.Integer, default=0)
    n_pasti   = db.Column(db.Integer, default=0)
    n_snack   = db.Column(db.Integer, default=0)
    n_caffe   = db.Column(db.Integer, default=0)
    n_builder = db.Column(db.Integer, default=0)
    incasso   = db.Column(db.Float,   default=0.0)

    righe = db.relationship('CaricoMensileRiga', back_populates='carico',
                            cascade='all, delete-orphan', lazy='dynamic')
    autore = db.relationship('User', foreign_keys='CaricoMensile.creato_da')

    MESI = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
            'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']

    @property
    def etichetta(self):
        nome = self.MESI[self.mese - 1] if 1 <= self.mese <= 12 else str(self.mese)
        return f'{nome} {self.anno}'

    @property
    def totale_righe(self):
        return self.righe.count()

    @property
    def parametri_dict(self):
        import json as _json
        try:
            return _json.loads(self.parametri or '{}')
        except (ValueError, TypeError):
            return {}


class CaricoMensileRiga(db.Model):
    """Registro delle righe create da un carico: entita e chiave primaria."""
    __tablename__ = 'carichi_mensili_righe'
    id        = db.Column(db.Integer, primary_key=True)
    carico_id = db.Column(db.Integer,
                          db.ForeignKey('carichi_mensili.id', ondelete='CASCADE'),
                          nullable=False, index=True)
    entita    = db.Column(db.String(64), nullable=False)   # __tablename__
    riga_id   = db.Column(db.Integer, nullable=False)

    carico = db.relationship('CaricoMensile', back_populates='righe')
