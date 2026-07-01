"""
Demo seed: tenant default (Bar Centrale).
Eseguibile via CLI  →  flask seed-demo
Eseguibile via UI   →  POST /admin/seed-demo  (solo super admin)
"""
from datetime import date, timedelta
import secrets
from app import db
from app.models import (
    User, Tenant, Category, Product, TimeSlot,
    Role, Permission, AppSetting, Supplier, ConsumableItem,
    DailyStock, Order, OrderItem, IngredientCategory, Ingredient,
    CustomOrderItem, CustomOrderItemIngredient, Table, TableReservation,
    TableTimeBand,
    Transaction, ConsumableMovement, CorporateAccount, CorporateMembership,
    DailyFixedMeal, CorporateMealBooking, PollVote, user_roles,
)
from config import Config

# ── Helpers ───────────────────────────────────────────────────────────────────

def _tenant(name, slug, color):
    t = Tenant.query.filter_by(slug=slug).first()
    if not t:
        t = Tenant(name=name, slug=slug, primary_color=color, is_active=True)
        db.session.add(t)
        db.session.flush()
    return t



def _slots(tenant_id):
    if TimeSlot.query.filter_by(tenant_id=tenant_id).first():
        return
    for t in Config.PICKUP_SLOTS:
        db.session.add(TimeSlot(time_str=t, max_orders=30, is_active=True,
                                tenant_id=tenant_id))


def _tables(tenant_id):
    if Table.query.filter_by(tenant_id=tenant_id).first():
        return
    specs = [
        (1, 4, 'Finestra'), (2, 4, 'Finestra'),
        (3, 2, 'Centro'),   (4, 2, 'Centro'),
        (5, 4, 'Terrazzo'), (6, 4, 'Terrazzo'),
    ]
    for number, seats, location in specs:
        db.session.add(Table(number=number, seats=seats,
                             location=location, is_active=True,
                             tenant_id=tenant_id))


def _bands(tenant_id):
    if TableTimeBand.query.filter_by(tenant_id=tenant_id).first():
        return
    configs = [
        ('11:25', '12:30', 30, 0),
        ('12:30', '13:30', 20, 1),
        ('13:30', '15:00', 25, 2),
    ]
    for start, end, dur, order in configs:
        db.session.add(TableTimeBand(start_time=start, end_time=end,
                                     duration_minutes=dur, sort_order=order,
                                     tenant_id=tenant_id))


def _cat(name, icon, color, tenant_id):
    c = Category.query.filter_by(name=name, tenant_id=tenant_id).first()
    if not c:
        c = Category(name=name, icon=icon, color=color, tenant_id=tenant_id)
        db.session.add(c)
        db.session.flush()
    return c


def _prod(name, desc, price, category, qty, tenant_id):
    if not Product.query.filter_by(name=name, tenant_id=tenant_id).first():
        db.session.add(Product(name=name, description=desc, price=price,
                               category_id=category.id, daily_quantity=qty,
                               is_active=True, tenant_id=tenant_id))


def _supplier(name, email, phone, tenant_id):
    s = Supplier.query.filter_by(name=name, tenant_id=tenant_id).first()
    if not s:
        s = Supplier(name=name, email=email, phone=phone, tenant_id=tenant_id)
        db.session.add(s)
        db.session.flush()
    return s


def _consumable(name, unit, qty, threshold, supplier, tenant_id):
    if not ConsumableItem.query.filter_by(name=name, tenant_id=tenant_id).first():
        db.session.add(ConsumableItem(
            name=name, unit=unit, quantity=qty, min_threshold=threshold,
            supplier_id=supplier.id if supplier else None, tenant_id=tenant_id))


def _client(first, last, email, phone, bdate, address, tg, tenant_id, wallet=0.0):
    if User.query.filter_by(email=email).first():
        return
    u = User(
        username=email.split('@')[0].replace('.', '_'),
        email=email,
        is_client=True,
        first_name=first,
        last_name=last,
        phone=phone,
        birth_date=date.fromisoformat(bdate),
        address=address,
        telegram_chat_id=tg,
        tenant_id=tenant_id,
        wallet_balance=wallet,
        loyalty_points=int(wallet * 10),
    )
    u.set_password('cliente123')
    db.session.add(u)


# ── Dati tenant 1: Bar Centrale ───────────────────────────────────────────────

def _seed_bar_centrale(sa_role):
    # Usa il tenant 'default' invece di creare un tenant separato,
    # così il super admin vede i dati demo nella sua vista standard.
    t = _tenant('QuickLunch Bar', 'default', '#e94560')
    _slots(t.id)
    _tables(t.id)
    _bands(t.id)

    pan  = _cat('Panini & Piadine',  'fa-burger',       'warning',  t.id)
    cal  = _cat('Piatti Caldi',      'fa-bowl-food',    'danger',   t.id)
    ins  = _cat('Insalate',          'fa-leaf',         'success',  t.id)
    dol  = _cat('Dolci',             'fa-cake-candles', 'pink',     t.id)
    bev  = _cat('Bevande',           'fa-bottle-water', 'info',     t.id)
    col  = _cat('Colazione',         'fa-mug-hot',      'secondary',t.id)

    # Panini
    _prod('Panino Prosciutto e Mozzarella', 'Pane ciabatta, prosciutto cotto DOP, mozzarella fior di latte', 4.50, pan, 40, t.id)
    _prod('Panino Bresaola e Rucola',       'Pane integrale, bresaola della Valtellina, rucola, scaglie di Grana', 5.20, pan, 35, t.id)
    _prod('Panino Porchetta',               'Rosetta croccante, porchetta artigianale, salsa verde', 4.80, pan, 30, t.id)
    _prod('Tramezzino Tonno e Olive',       'Pane morbido, tonno sott\'olio, olive, maionese', 3.00, pan, 50, t.id)
    _prod('Tramezzino Vegetariano',         'Pane morbido, verdure grigliate, hummus, rucola', 2.80, pan, 50, t.id)
    _prod('Club Sandwich',                  'Tre strati con pollo, bacon, insalata, pomodoro, maionese', 5.50, pan, 25, t.id)
    _prod('Piadina Squacquerone e Prosciutto', 'Piadina romagnola, squacquerone fresco, prosciutto crudo, rucola', 5.00, pan, 30, t.id)
    _prod('Bagel Salmone e Cream Cheese',   'Bagel tostato, salmone norvegese, cream cheese, capperi', 5.80, pan, 20, t.id)

    # Piatti caldi
    _prod('Pasta al Pomodoro Fresco',       'Spaghetti trafilati al bronzo, pomodoro San Marzano DOP, basilico', 5.00, cal, 30, t.id)
    _prod('Risotto Porcini e Taleggio',     'Riso Carnaroli, funghi porcini, fonduta di taleggio', 7.00, cal, 20, t.id)
    _prod('Cotoletta alla Milanese',        'Lombata di vitello, panatura tradizionale, patate al forno', 9.00, cal, 15, t.id)
    _prod('Gnocchi al Ragù',               'Gnocchi di patate fatti in casa, ragù di carne lento', 6.50, cal, 20, t.id)
    _prod('Petto di Pollo Grigliato',       'Petto di pollo marinato alle erbe, contorno a scelta', 7.50, cal, 25, t.id)

    # Insalate
    _prod('Insalata Caprese',               'Pomodori cuore di bue, mozzarella di bufala, basilico, olio EVO', 6.00, ins, 20, t.id)
    _prod('Insalata di Farro e Verdure',    'Farro integrale, verdure di stagione, feta, vinaigrette al limone', 5.50, ins, 20, t.id)
    _prod('Caesar Salad',                   'Lattuga romana, crostini, parmigiano, salsa Caesar, pollo grigliato', 6.50, ins, 20, t.id)

    # Dolci
    _prod('Tiramisù Classico',              'Ricetta tradizionale con mascarpone, savoiardi e caffè espresso', 3.50, dol, 20, t.id)
    _prod('Cannolo Siciliano',              'Cannolo croccante con ricotta, pistacchi e scorza d\'arancia', 3.00, dol, 25, t.id)
    _prod('Torta della Casa',               'Torta del giorno preparata dalla nostra pasticceria', 3.00, dol, 20, t.id)
    _prod('Panna Cotta ai Frutti di Bosco', 'Panna cotta cremosa con coulis di frutti di bosco freschi', 3.50, dol, 15, t.id)

    # Bevande
    _prod('Acqua Naturale 0,5L',            '', 1.00, bev, 100, t.id)
    _prod('Acqua Frizzante 0,5L',           '', 1.00, bev, 100, t.id)
    _prod('Coca-Cola 0,33L',               '', 2.00, bev, 80,  t.id)
    _prod('Succo di Frutta Ace',            '', 2.00, bev, 60,  t.id)
    _prod('Birra Peroni Media',             'Birra chiara alla spina 0,4L', 3.50, bev, 40, t.id)
    _prod('Caffè Espresso',                 '', 1.20, bev, 100, t.id)
    _prod('Cappuccino',                     '', 1.50, bev, 80,  t.id)

    # Colazione
    _prod('Cornetto Vuoto',                 'Cornetto sfogliato burro e miele', 1.30, col, 60, t.id)
    _prod('Cornetto alla Crema',            'Cornetto con crema pasticcera artigianale', 1.60, col, 60, t.id)
    _prod('Brioche con Nutella',            'Brioche soffice farcita con crema nocciola', 2.00, col, 40, t.id)
    _prod('Yogurt con Granola e Frutta',    'Yogurt greco, granola croccante, frutti di stagione', 3.50, col, 20, t.id)

    # Senza Glutine
    gf = _cat('Senza Glutine', 'fa-wheat-awn-circle-exclamation', 'success', t.id)
    _prod('🌾 Panino Senza Glutine Prosciutto e Mozzarella', 'Pane senza glutine certificato AIC, prosciutto cotto DOP, mozzarella', 5.20, gf, 15, t.id)
    _prod('🌾 Pasta Senza Glutine al Pomodoro',              'Pasta di mais e riso, pomodoro San Marzano, basilico — cottura separata', 5.80, gf, 15, t.id)
    _prod('🌾 Insalata di Riso Senza Glutine',               'Riso, tonno, mais, pomodorini, olive — 100% gluten free', 5.50, gf, 15, t.id)
    _prod('🌾 Torta di Mele Senza Glutine',                  'Farina di mandorle e riso, mele, cannella', 3.80, gf, 12, t.id)
    _prod('🌾 Crackers Senza Glutine',                       'Crackers di mais certificati, confezione monoporzione', 2.00, gf, 25, t.id)

    # Clienti
    clienti = [
        ('Marco',     'Rossi',     'marco.rossi@gmail.com',       '+39 333 111 0001', '1985-03-15', 'Via Roma 12, Milano',              '-100111001', t.id, 24.50),
        ('Giulia',    'Ferrari',   'giulia.ferrari@gmail.com',     '+39 333 111 0002', '1990-07-22', 'Corso Buenos Aires 45, Milano',    '',           t.id, 10.00),
        ('Luca',      'Bianchi',   'luca.bianchi@gmail.com',       '+39 333 111 0003', '1988-11-03', 'Via Montenapoleone 8, Milano',     '-100111003', t.id, 35.00),
        ('Sara',      'Romano',    'sara.romano@gmail.com',        '+39 333 111 0004', '1992-01-18', 'Piazza Duomo 1, Milano',           '',           t.id, 5.50),
        ('Antonio',   'Colombo',   'antonio.colombo@libero.it',    '+39 333 111 0005', '1975-06-30', 'Via Torino 22, Milano',            '-100111005', t.id, 50.00),
        ('Valentina', 'Ricci',     'valentina.ricci@gmail.com',    '+39 333 111 0006', '1995-09-08', 'Via Dante 5, Milano',              '',           t.id, 15.00),
        ('Francesco', 'Marino',    'francesco.marino@hotmail.it',  '+39 333 111 0007', '1983-04-25', 'Via Garibaldi 33, Rho',            '-100111007', t.id, 0.00),
        ('Chiara',    'Greco',     'chiara.greco@gmail.com',       '+39 333 111 0008', '1998-12-14', 'Corso Lodi 18, Milano',            '',           t.id, 8.00),
        ('Matteo',    'Bruno',     'matteo.bruno@gmail.com',       '+39 333 111 0009', '1987-08-02', 'Via Padova 67, Milano',            '-100111009', t.id, 22.00),
        ('Elena',     'Gallo',     'elena.gallo@gmail.com',        '+39 333 111 0010', '1993-05-19', 'Via Sarpi 14, Milano',             '',           t.id, 12.50),
        ('Roberto',   'Conti',     'roberto.conti@gmail.com',      '+39 333 111 0011', '1970-02-28', 'Piazza Sempione 3, Milano',        '-100111011', t.id, 60.00),
        ('Marta',     'De Luca',   'marta.deluca@gmail.com',       '+39 333 111 0012', '1996-10-07', 'Via Solferino 9, Milano',          '',           t.id, 3.00),
    ]
    for c in clienti:
        _client(*c)

    # Consumabili di magazzino
    forn = _supplier('Cartabella Forniture SRL', 'ordini@cartabellaforniture.it', '+39 02 5550 1010', t.id)
    _consumable('Tovaglioli di carta',              'pz', 480,  200, forn, t.id)
    _consumable('Bicchieri di carta 200ml',         'pz', 80,   150, forn, t.id)   # sotto soglia
    _consumable('Posate monouso — forchette',       'pz', 320,  100, forn, t.id)
    _consumable('Posate monouso — coltelli',        'pz', 310,  100, forn, t.id)
    _consumable('Piatti di carta',                  'pz', 260,  100, forn, t.id)
    _consumable('Contenitori da asporto con coperchio', 'pz', 40, 80, forn, t.id)  # sotto soglia
    _consumable('Sacchetti shopper per asporto',     'pz', 210,  100, forn, t.id)
    _consumable('Guanti monouso (scatola da 100)',   'pz', 14,   5,   forn, t.id)
    _consumable('Cannucce biodegradabili',           'pz', 600,  200, forn, t.id)
    _consumable('Detersivo sgrassatore professionale','lt', 8,   3,   forn, t.id)

    return t


# ── Reset ─────────────────────────────────────────────────────────────────────

def _delete_tenant_data(tenant_ids, delete_tenants=True, clients_only=False):
    """Cancella i dati di una lista di tenant_ids in ordine FK-safe.
    Se delete_tenants=False, non elimina i tenant (usato per 'default').
    Se clients_only=True, elimina solo clienti (non admin) dagli utenti.
    """
    if not tenant_ids:
        return

    is_pg = db.engine.url.drivername.startswith('postgresql')

    if clients_only:
        user_ids = [r[0] for r in db.session.query(User.id).filter(
            User.is_client == True, User.tenant_id.in_(tenant_ids)).all()]
    else:
        user_ids = [r[0] for r in db.session.query(User.id).filter(
            User.tenant_id.in_(tenant_ids)).all()]

    order_ids = [r[0] for r in db.session.query(Order.id).filter(
        Order.tenant_id.in_(tenant_ids)).all()]
    custom_item_ids = ([r[0] for r in db.session.query(CustomOrderItem.id).filter(
        CustomOrderItem.order_id.in_(order_ids)).all()] if order_ids else [])
    product_ids = [r[0] for r in db.session.query(Product.id).filter(
        Product.tenant_id.in_(tenant_ids)).all()]
    consumable_ids = [r[0] for r in db.session.query(ConsumableItem.id).filter(
        ConsumableItem.tenant_id.in_(tenant_ids)).all()]
    meal_ids = [r[0] for r in db.session.query(DailyFixedMeal.id).filter(
        DailyFixedMeal.tenant_id.in_(tenant_ids)).all()]

    # magazzino
    if user_ids:
        if is_pg:
            db.session.execute(
                db.text('UPDATE consumable_movements SET user_id = NULL WHERE user_id = ANY(:ids)'),
                {'ids': user_ids})
        else:
            db.session.execute(db.text(
                'UPDATE consumable_movements SET user_id = NULL WHERE user_id IN ({})'.format(
                    ','.join(str(i) for i in user_ids))))
    if consumable_ids:
        ConsumableMovement.query.filter(ConsumableMovement.item_id.in_(consumable_ids)).delete(synchronize_session=False)
    ConsumableItem.query.filter(ConsumableItem.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    Supplier.query.filter(Supplier.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # pasto aziendale
    if meal_ids:
        CorporateMealBooking.query.filter(CorporateMealBooking.meal_id.in_(meal_ids)).delete(synchronize_session=False)
    DailyFixedMeal.query.filter(DailyFixedMeal.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    if user_ids:
        CorporateMembership.query.filter(CorporateMembership.user_id.in_(user_ids)).delete(synchronize_session=False)
    CorporateAccount.query.filter(CorporateAccount.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # sondaggi e transazioni
    if user_ids:
        PollVote.query.filter(PollVote.user_id.in_(user_ids)).delete(synchronize_session=False)
        Transaction.query.filter(Transaction.user_id.in_(user_ids)).delete(synchronize_session=False)

    # ordini
    if custom_item_ids:
        CustomOrderItemIngredient.query.filter(
            CustomOrderItemIngredient.custom_item_id.in_(custom_item_ids)).delete(synchronize_session=False)
    if order_ids:
        if is_pg:
            db.session.execute(
                db.text('UPDATE transactions SET order_id = NULL WHERE order_id = ANY(:ids)'),
                {'ids': order_ids})
        else:
            db.session.execute(db.text(
                'UPDATE transactions SET order_id = NULL WHERE order_id IN ({})'.format(
                    ','.join(str(i) for i in order_ids))))
        CustomOrderItem.query.filter(CustomOrderItem.order_id.in_(order_ids)).delete(synchronize_session=False)
        OrderItem.query.filter(OrderItem.order_id.in_(order_ids)).delete(synchronize_session=False)
    Order.query.filter(Order.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # tavoli, fasce orarie e prenotazioni
    TableReservation.query.filter(TableReservation.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    TableTimeBand.query.filter(TableTimeBand.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    Table.query.filter(Table.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # catalogo
    if product_ids:
        DailyStock.query.filter(DailyStock.product_id.in_(product_ids)).delete(synchronize_session=False)
    Product.query.filter(Product.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    Ingredient.query.filter(Ingredient.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    IngredientCategory.query.filter(IngredientCategory.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    Category.query.filter(Category.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    TimeSlot.query.filter(TimeSlot.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # utenti
    if user_ids:
        db.session.execute(user_roles.delete().where(user_roles.c.user_id.in_(user_ids)))
        User.query.filter(User.id.in_(user_ids)).delete(synchronize_session=False)

    if delete_tenants:
        Tenant.query.filter(Tenant.id.in_(tenant_ids)).delete(synchronize_session=False)


def reset_demo_data():
    """Svuota catalogo e clienti del tenant 'default' (il tenant rimane)."""
    default_t = Tenant.query.filter_by(slug='default').first()
    if not default_t:
        return True, 'Nessun dato demo presente: nulla da resettare.'
    _delete_tenant_data([default_t.id], delete_tenants=False, clients_only=True)
    db.session.commit()
    return True, 'Reset completato: tenant default svuotato.'


# ── Entry point ───────────────────────────────────────────────────────────────

def seed_demo_data():
    """
    Ritorna (ok: bool, message: str).
    Idempotente: ogni helper (_tenant/_cat/_prod/_client/_supplier/_consumable)
    salta i record già esistenti.
    """
    sa_role = Role.query.filter_by(name='superadmin').first()
    t1 = _seed_bar_centrale(sa_role)
    db.session.commit()

    n_clients    = User.query.filter_by(is_client=True, tenant_id=t1.id).count()
    n_products   = Product.query.filter_by(tenant_id=t1.id).count()
    n_consumables = ConsumableItem.query.filter_by(tenant_id=t1.id).count()
    return True, (
        f'Demo caricato/aggiornato: {n_clients} clienti, '
        f'{n_products} prodotti (incl. gluten free), {n_consumables} consumabili di magazzino. '
        f'Password clienti: cliente123'
    )
