from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager

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
    password_hash = db.Column(db.String(256), nullable=True)  # nullable per Google OAuth
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    wallet_balance = db.Column(db.Float, default=0.0)
    loyalty_points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    google_id  = db.Column(db.String(128), nullable=True, unique=True)
    avatar_url = db.Column(db.String(256), default='')

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id], overlaps='users')

    orders       = db.relationship('Order',            back_populates='user', lazy='dynamic')
    transactions = db.relationship('Transaction',      back_populates='user', lazy='dynamic')
    reservations = db.relationship('TableReservation', back_populates='user', lazy='dynamic')
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
            'manage_roles', 'view_reports',
        }
        return any(
            any(p.name in BACKOFFICE for p in role.permissions)
            for role in self.roles
        )

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
                                   description=f'Premio: {points} punti → +{reward_amount:.2f}€'))


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
    tenant_id      = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    category = db.relationship('Category', back_populates='products')
    order_items = db.relationship('OrderItem', back_populates='product')
    daily_stocks = db.relationship('DailyStock', back_populates='product')

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
    id         = db.Column(db.Integer, primary_key=True)
    time_str   = db.Column(db.String(5), nullable=False)
    max_orders = db.Column(db.Integer, default=20)
    is_active  = db.Column(db.Boolean, default=True)
    tenant_id  = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
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
    slot_id    = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=False)
    order_date = db.Column(db.Date, nullable=False, default=date.today)
    status     = db.Column(db.String(20), default='pending')
    total_price= db.Column(db.Float, default=0.0)
    notes      = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant_id  = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

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
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(128), nullable=False)
    price_extra   = db.Column(db.Float, default=0.0)
    category_id   = db.Column(db.Integer, db.ForeignKey('ingredient_categories.id'), nullable=False)
    is_active     = db.Column(db.Boolean, default=True)
    is_vegetarian = db.Column(db.Boolean, default=False)
    allergens     = db.Column(db.String(128), default='')
    tenant_id     = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    category      = db.relationship('IngredientCategory', back_populates='ingredients')


class CustomOrderItem(db.Model):
    __tablename__ = 'custom_order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    builder_type = db.Column(db.String(10), nullable=False)
    label = db.Column(db.String(512), default='')
    unit_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, default=1)
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


class TableReservation(db.Model):
    __tablename__ = 'table_reservations'
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    table_id         = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    slot_id          = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=False)
    reservation_date = db.Column(db.Date, nullable=False, default=date.today)
    party_size       = db.Column(db.Integer, default=1)
    notes            = db.Column(db.Text, default='')
    status           = db.Column(db.String(20), default='confirmed')
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    tenant_id        = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    user = db.relationship('User', back_populates='reservations')
    table = db.relationship('Table', back_populates='reservations')
    slot = db.relationship('TimeSlot', back_populates='table_reservations')

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
    }

    def icon_info(self):
        return self.TYPE_ICONS.get(self.ttype, ('fa-circle', 'secondary', self.ttype))


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
    id        = db.Column(db.Integer, primary_key=True)
    poll_id   = db.Column(db.Integer, db.ForeignKey('polls.id'),     nullable=False)
    choice_id = db.Column(db.Integer, db.ForeignKey('poll_choices.id'), nullable=False)
    user_id   = db.Column(db.Integer, db.ForeignKey('users.id'),     nullable=False)
    voted_at  = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('poll_id', 'user_id', name='uq_poll_user'),
    )
