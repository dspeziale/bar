"""
Demo seed: 3 tenant, 12 clienti ciascuno, prodotti e categorie complete.
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

DEMO_SLUGS = ['mensa-tech', 'caffetteria-duomo']  # bar-centrale usa il tenant 'default'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tenant(name, slug, color):
    t = Tenant.query.filter_by(slug=slug).first()
    if not t:
        t = Tenant(name=name, slug=slug, primary_color=color, is_active=True)
        db.session.add(t)
        db.session.flush()
    return t


def _tenant_admin(tenant, sa_role):
    email = f'admin@{tenant.slug}.local'
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(username=f'admin.{tenant.slug}', email=email,
                 is_admin=False, tenant_id=tenant.id,
                 wallet_balance=0.0, loyalty_points=0)
        u.set_password('demo1234')
        if sa_role:
            u.roles = [sa_role]
        db.session.add(u)
        db.session.flush()
    return u


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


# ── Dati tenant 2: Mensa Azienda Tech ─────────────────────────────────────────

def _seed_mensa_tech(sa_role):
    t = _tenant('Mensa AziendaTech', 'mensa-tech', '#0f3460')
    _tenant_admin(t, sa_role)
    _slots(t.id)
    _tables(t.id)
    _bands(t.id)

    pri  = _cat('Primo Piatto',  'fa-bowl-food',    'danger',    t.id)
    sec  = _cat('Secondo Piatto','fa-drumstick-bite','warning',  t.id)
    con  = _cat('Contorno',      'fa-carrot',        'success',  t.id)
    sal  = _cat('Insalate',      'fa-leaf',          'info',     t.id)
    des  = _cat('Dessert',       'fa-cake-candles',  'pink',     t.id)
    bev  = _cat('Bevande',       'fa-bottle-water',  'secondary',t.id)

    # Primi
    _prod('Pasta alla Carbonara',        'Spaghetti, guanciale DOP, uova, pecorino romano, pepe', 5.50, pri, 40, t.id)
    _prod('Risotto ai Funghi Porcini',   'Riso Carnaroli, porcini secchi e freschi, burro, parmigiano', 6.00, pri, 25, t.id)
    _prod('Lasagne al Forno',            'Pasta all\'uovo, ragù bolognese, besciamella, fior di latte', 6.00, pri, 30, t.id)
    _prod('Minestra di Verdure',         'Stagionale con legumi misti, verdure di campo, olio a crudo', 4.00, pri, 35, t.id)
    _prod('Zuppa di Ceci e Rosmarino',   'Ceci lessati, passata di pomodoro, rosmarino, crostini', 4.50, pri, 25, t.id)
    _prod('Orecchiette alle Cime di Rapa','Pasta fresca pugliese, cime di rapa, alici, aglio, peperoncino', 5.00, pri, 30, t.id)
    _prod('Penne all\'Arrabbiata',       'Penne rigate, pomodoro San Marzano, aglio, peperoncino, prezzemolo', 4.50, pri, 40, t.id)
    _prod('Gnocchi alla Sorrentina',     'Gnocchi di patate, pomodoro fresco, mozzarella, basilico, forno', 5.50, pri, 25, t.id)

    # Secondi
    _prod('Arrosto di Maiale alle Erbe', 'Lonza di maiale, rosmarino, aglio, patate al forno', 7.50, sec, 20, t.id)
    _prod('Pesce al Forno con Patate',   'Filetto di orata o branzino (rotazione), patate, olive, capperi', 8.00, sec, 15, t.id)
    _prod('Scaloppina al Limone',        'Fettine di vitello, burro, succo di limone, prezzemolo', 7.00, sec, 20, t.id)
    _prod('Pollo alla Cacciatora',       'Pollo ruspante, pomodoro, olive, capperi, vino bianco', 7.00, sec, 20, t.id)
    _prod('Frittata alle Verdure',       'Uova fresche, zucchine, peperoni, cipolla, erbe aromatiche', 5.00, sec, 20, t.id)
    _prod('Polpette al Sugo',            'Polpette di manzo e maiale, salsa di pomodoro casalinga', 6.50, sec, 25, t.id)

    # Contorni
    _prod('Patate al Forno',             'Patate novelle, rosmarino, olio EVO', 2.50, con, 50, t.id)
    _prod('Verdure Grigliate',           'Zucchine, melanzane, peperoni, radicchio grigliati', 2.50, con, 40, t.id)
    _prod('Spinaci Saltati al Burro',    'Spinaci freschi, burro, aglio, noce moscata', 2.00, con, 35, t.id)
    _prod('Fagiolini all\'Olio',         'Fagiolini verdi, olio EVO, aglio, limone', 2.00, con, 35, t.id)
    _prod('Caponata Siciliana',          'Melanzane, sedano, olive, capperi, aceto, zucchero', 3.00, con, 25, t.id)

    # Insalate
    _prod('Insalata Mista',              'Lattuga, pomodorini, carote, mais, ravanelli', 2.50, sal, 40, t.id)
    _prod('Insalata di Farro e Pollo',   'Farro, petto di pollo, verdure, olive, limone', 5.00, sal, 20, t.id)
    _prod('Insalata Nizzarda',           'Tonno, fagiolini, uova sode, olive nere, pomodorini', 5.50, sal, 20, t.id)

    # Dessert
    _prod('Budino al Cioccolato',        'Budino fondente fatto in casa, caramello salato', 2.50, des, 30, t.id)
    _prod('Torta di Mele della Nonna',   'Mele golden, cannella, pasta frolla burro', 2.50, des, 25, t.id)
    _prod('Frutta Fresca di Stagione',   'Frutta selezionata, dipende dalla stagione', 1.80, des, 30, t.id)
    _prod('Panna Cotta alla Vaniglia',   'Panna fresca, baccello di vaniglia, coulis fragole', 3.00, des, 20, t.id)

    # Bevande
    _prod('Acqua Naturale 0,5L',         '', 0.80, bev, 100, t.id)
    _prod('Acqua Frizzante 0,5L',        '', 0.80, bev, 100, t.id)
    _prod('Coca-Cola 0,33L',            '', 1.50, bev, 80,  t.id)
    _prod('Aranciata San Pellegrino',    '', 1.50, bev, 60,  t.id)
    _prod('Succo d\'Arancia Frescos',    'Arancia rossa di Sicilia, spremitura del giorno', 2.50, bev, 30, t.id)
    _prod('Caffè Espresso',             '', 1.00, bev, 100, t.id)
    _prod('Tè Freddo Pesca',            '', 1.50, bev, 60,  t.id)

    # Senza Glutine
    gf = _cat('Senza Glutine', 'fa-wheat-awn-circle-exclamation', 'success', t.id)
    _prod('🌾 Riso Basmati con Pollo e Verdure',  'Riso basmati, petto di pollo, verdure saltate — 100% gluten free', 6.50, gf, 15, t.id)
    _prod('🌾 Pasta Senza Glutine al Ragù',        'Pasta di mais, ragù di carne, cottura separata certificata', 6.00, gf, 15, t.id)
    _prod('🌾 Polenta con Spezzatino',             'Polenta di mais, spezzatino di manzo al sugo', 7.00, gf, 12, t.id)
    _prod('🌾 Torta di Riso Senza Glutine',        'Farina di riso, mandorle, scorza di limone', 2.80, gf, 12, t.id)

    # Clienti
    clienti = [
        ('Andrea',   'Mancini',   'andrea.mancini@aziendatech.it',  '+39 347 222 0001', '1982-05-12', 'Via dell\'Innovazione 1, Roma',    '-100222001', t.id, 30.00),
        ('Paola',    'Costa',     'paola.costa@aziendatech.it',     '+39 347 222 0002', '1979-09-27', 'Via Tiburtina 88, Roma',           '',           t.id, 15.00),
        ('Simone',   'Giordano',  'simone.giordano@aziendatech.it', '+39 347 222 0003', '1991-01-04', 'Piazza Navona 2, Roma',            '-100222003', t.id, 42.00),
        ('Silvia',   'Rizzo',     'silvia.rizzo@aziendatech.it',    '+39 347 222 0004', '1986-11-16', 'Via del Corso 15, Roma',           '',           t.id, 8.00),
        ('Lorenzo',  'Lombardi',  'lorenzo.lombardi@aziendatech.it','+39 347 222 0005', '1994-03-23', 'Via Cavour 100, Roma',             '-100222005', t.id, 20.00),
        ('Francesca','Moretti',   'francesca.moretti@libero.it',    '+39 347 222 0006', '1988-07-31', 'Via Appia Nuova 44, Roma',         '',           t.id, 5.00),
        ('Paolo',    'Barbieri',  'paolo.barbieri@gmail.com',       '+39 347 222 0007', '1972-12-09', 'Via Aurelia 200, Roma',            '-100222007', t.id, 75.00),
        ('Anna',     'Fontana',   'anna.fontana@gmail.com',         '+39 347 222 0008', '1997-04-14', 'Via Prati 7, Roma',                '',           t.id, 11.00),
        ('Giovanni', 'Esposito',  'giovanni.esposito@gmail.com',    '+39 347 222 0009', '1984-08-20', 'Via Prenestina 55, Roma',          '-100222009', t.id, 18.50),
        ('Laura',    'Pellegrini','laura.pellegrini@gmail.com',     '+39 347 222 0010', '1990-02-05', 'Via Tuscolana 30, Roma',           '',           t.id, 6.00),
        ('Stefano',  'Ferraro',   'stefano.ferraro@gmail.com',      '+39 347 222 0011', '1968-06-17', 'Via Nomentana 77, Roma',           '-100222011', t.id, 100.00),
        ('Monica',   'Russo',     'monica.russo@gmail.com',         '+39 347 222 0012', '1993-10-29', 'Via Flaminia 12, Roma',            '',           t.id, 4.50),
    ]
    for c in clienti:
        _client(*c)

    # Consumabili di magazzino (mensa aziendale: volumi alti)
    forn = _supplier('HoReCa Supply Roma', 'ordini@horecasupply.it', '+39 06 4440 2020', t.id)
    _consumable('Vassoi mensa riutilizzabili',        'pz', 220,  100, forn, t.id)
    _consumable('Tovagliette di carta',               'pz', 900,  300, forn, t.id)
    _consumable('Posate monouso — set completo',      'pz', 150,  300, forn, t.id)  # sotto soglia
    _consumable('Bicchieri di plastica 300ml',        'pz', 500,  200, forn, t.id)
    _consumable('Contenitori porta-pasto richiudibili','pz', 90,   150, forn, t.id)  # sotto soglia
    _consumable('Tovaglioli di carta',                'pz', 700,  250, forn, t.id)
    _consumable('Guanti monouso (scatola da 100)',    'pz', 20,   8,   forn, t.id)
    _consumable('Sacchi per rifiuti organici',        'pz', 60,   30,  forn, t.id)
    _consumable('Detersivo lavastoviglie industriale','lt', 12,   5,   forn, t.id)

    return t


# ── Dati tenant 3: Caffetteria Duomo ─────────────────────────────────────────

def _seed_caffetteria_duomo(sa_role):
    t = _tenant('Caffetteria Duomo', 'caffetteria-duomo', '#8e44ad')
    _tenant_admin(t, sa_role)
    _slots(t.id)
    _tables(t.id)
    _bands(t.id)

    caf  = _cat('Caffetteria',       'fa-mug-hot',       'warning',   t.id)
    ape  = _cat('Aperitivi',         'fa-wine-glass',    'danger',    t.id)
    stu  = _cat('Stuzzichini',       'fa-cheese',        'secondary', t.id)
    dol  = _cat('Dolci da Forno',    'fa-cake-candles',  'pink',      t.id)
    smo  = _cat('Smoothie & Freschi','fa-blender',       'success',   t.id)
    bev  = _cat('Bevande Fredde',    'fa-bottle-water',  'info',      t.id)

    # Caffetteria
    _prod('Espresso',                'Miscela arabica 100% tostatura artigianale', 1.20, caf, 200, t.id)
    _prod('Cappuccino',              'Espresso doppio, latte montato vellutato, cacao', 1.60, caf, 150, t.id)
    _prod('Marocchino',              'Espresso, crema di cacao, latte schiumato, cacao amaro', 2.00, caf, 80, t.id)
    _prod('Caffè Americano',         'Espresso allungato con acqua calda', 1.50, caf, 100, t.id)
    _prod('Latte Macchiato',         'Latte caldo con una vena di espresso', 1.80, caf, 80,  t.id)
    _prod('Cappuccino Vegano',       'Espresso, latte di avena o soia a scelta', 2.00, caf, 50, t.id)
    _prod('Tè Verde Matcha',         'Matcha giapponese, latte di avena, miele', 3.50, caf, 30, t.id)
    _prod('Cioccolata Calda',        'Cioccolato fondente belga, latte intero, panna montata', 3.00, caf, 40, t.id)

    # Aperitivi
    _prod('Spritz Aperol',           'Prosecco, Aperol, seltz, arancia, olive', 5.00, ape, 50, t.id)
    _prod('Spritz Campari',          'Prosecco, Campari, seltz, arancia', 5.00, ape, 50, t.id)
    _prod('Negroni',                 'Gin, Campari, vermut rosso, arancia bruciata', 6.00, ape, 30, t.id)
    _prod('Prosecco Valdobbiadene',  'Calice di prosecco DOCG Valdobbiadene Extra Dry', 4.50, ape, 40, t.id)
    _prod('Mimosa',                  'Prosecco, succo d\'arancia fresca 50/50', 5.00, ape, 30, t.id)
    _prod('Hugo',                    'Prosecco, sciroppo di sambuco, menta, lime, seltz', 5.50, ape, 30, t.id)
    _prod('Birra Artigianale IPA',   'IPA locale da microbirrificio, 0,4L', 5.00, ape, 40, t.id)

    # Stuzzichini
    _prod('Bruschetta Pomodoro e Basilico', 'Pane di Altamura tostato, pomodorini datterini, olio EVO', 3.00, stu, 40, t.id)
    _prod('Bruschetta Avocado e Lime',     'Pane tostato, avocado, lime, peperoncino, sesamo', 4.50, stu, 30, t.id)
    _prod('Tagliere Salumi DOP',           'Prosciutto crudo Parma, salame, mortadella, grissini', 10.00, stu, 15, t.id)
    _prod('Tagliere Formaggi Misti',       'Parmigiano 36 mesi, gorgonzola, pecorino, miele', 10.00, stu, 15, t.id)
    _prod('Olive Ascolane Fritte',         'Olive farcite con carne, panate e fritte, maionese', 4.50, stu, 30, t.id)
    _prod('Frittelle di Baccalà',          'Baccalà in pastella croccante, salsa tartara', 5.00, stu, 25, t.id)
    _prod('Mini Tramezzini Misti (3 pz)',  'Tonno, prosciutto, vegetariano, pane morbido', 4.00, stu, 30, t.id)

    # Dolci da forno
    _prod('Cornetto al Burro',             'Sfogliatura artigianale, burro francese', 1.40, dol, 80, t.id)
    _prod('Cornetto alla Crema Pasticcera','Farcitura di crema fresca artigianale', 1.70, dol, 80, t.id)
    _prod('Cornetto ai Pistacchi',         'Crema di pistacchio di Bronte, granella croccante', 2.50, dol, 40, t.id)
    _prod('Muffin ai Mirtilli',            'Muffin americano, mirtilli freschi, streusel al burro', 2.80, dol, 40, t.id)
    _prod('Torta della Settimana',         'Ricetta che cambia ogni settimana, domanda al bancone!', 3.50, dol, 20, t.id)
    _prod('Plumcake Limone e Mandorle',    'Plumcake morbido, scorza di limone, farina di mandorle', 3.00, dol, 25, t.id)
    _prod('Cookies Cioccolato Fondente',   'Cookies americani, chips di cioccolato 70%, sale di Maldon', 2.00, dol, 40, t.id)

    # Smoothie
    _prod('Smoothie Tropical',             'Mango, ananas, banana, latte di cocco, zenzero', 5.00, smo, 25, t.id)
    _prod('Smoothie Verde Detox',          'Spinaci baby, mela verde, cetriolo, zenzero, limone', 5.00, smo, 20, t.id)
    _prod('Frullato Fragole e Yogurt',     'Fragole fresche, yogurt greco, miele, granola', 4.50, smo, 25, t.id)
    _prod('Centrifugato Carote e Zenzero', 'Carote, mela, zenzero, curcuma, limone', 4.00, smo, 20, t.id)

    # Bevande fredde
    _prod('Acqua Frizzante 0,5L',          'San Pellegrino', 1.50, bev, 80, t.id)
    _prod('Limonata Artigianale',          'Limoni biologici, menta fresca, zucchero di canna', 3.50, bev, 30, t.id)
    _prod('Tè Freddo Pesca Homemade',      'Tè nero, pesche fresche, zucchero di canna, ghiaccio', 3.50, bev, 30, t.id)
    _prod('Acqua di Cocco',                'Acqua di cocco naturale, no zuccheri aggiunti', 3.00, bev, 25, t.id)
    _prod('Kombucha Allo Zenzero',         'Tè fermentato, zenzero, limone, probiotici naturali', 4.00, bev, 20, t.id)

    # Senza Glutine
    gf = _cat('Senza Glutine', 'fa-wheat-awn-circle-exclamation', 'success', t.id)
    _prod('🌾 Cornetto Senza Glutine alla Crema', 'Sfogliatura gluten free certificata AIC, crema pasticcera', 2.50, gf, 15, t.id)
    _prod('🌾 Muffin Senza Glutine al Cioccolato', 'Farina di riso e mais, gocce di cioccolato fondente', 3.00, gf, 15, t.id)
    _prod('🌾 Tagliere Salumi e Formaggi Senza Glutine', 'Affettati e formaggi, crackers di mais certificati', 9.50, gf, 10, t.id)
    _prod('🌾 Plumcake Senza Glutine Limone',     'Farina di mandorle, scorza di limone, senza lattosio', 3.20, gf, 12, t.id)

    # Clienti
    clienti = [
        ('Alessia',  'Vitale',    'alessia.vitale@gmail.com',       '+39 340 333 0001', '1994-04-11', 'Via Toledo 45, Napoli',            '-100333001', t.id, 20.00),
        ('Davide',   'Esposito',  'davide.esposito@gmail.com',      '+39 340 333 0002', '1989-08-07', 'Via Caracciolo 10, Napoli',        '',           t.id, 7.50),
        ('Federica', 'Sorrentino','federica.sorrentino@gmail.com',  '+39 340 333 0003', '1996-01-25', 'Via Chiaia 88, Napoli',            '-100333003', t.id, 33.00),
        ('Gianluca', 'Caputo',    'gianluca.caputo@gmail.com',      '+39 340 333 0004', '1981-06-13', 'Via Posillipo 5, Napoli',          '',           t.id, 16.00),
        ('Ilaria',   'Ferrara',   'ilaria.ferrara@gmail.com',       '+39 340 333 0005', '1999-09-02', 'Via Mergellina 22, Napoli',        '-100333005', t.id, 0.00),
        ('Carlo',    'Amendola',  'carlo.amendola@libero.it',       '+39 340 333 0006', '1976-11-19', 'Via Foria 100, Napoli',            '',           t.id, 55.00),
        ('Daniela',  'Russo',     'daniela.russo@gmail.com',        '+39 340 333 0007', '1988-03-08', 'Via Spaccanapoli 3, Napoli',       '-100333007', t.id, 9.00),
        ('Emanuele', 'Napolitano','emanuele.napolitano@gmail.com',  '+39 340 333 0008', '1985-07-16', 'Via Parthenope 1, Napoli',         '',           t.id, 25.00),
        ('Gabriella','De Rosa',   'gabriella.derosa@gmail.com',     '+39 340 333 0009', '1972-12-31', 'Corso Vittorio Emanuele 40, Napoli','-100333009',t.id, 80.00),
        ('Nicola',   'Palumbo',   'nicola.palumbo@gmail.com',       '+39 340 333 0010', '1991-05-04', 'Via Foria 55, Napoli',             '',           t.id, 14.00),
        ('Roberta',  'Montefusco','roberta.montefusco@gmail.com',   '+39 340 333 0011', '1984-02-22', 'Via San Gregorio Armeno 7, Napoli','',           t.id, 2.50),
        ('Salvatore','Coppola',   'salvatore.coppola@gmail.com',    '+39 340 333 0012', '1966-10-10', 'Via Scarlatti 15, Napoli',         '-100333012', t.id, 120.00),
    ]
    for c in clienti:
        _client(*c)

    # Consumabili di magazzino (caffetteria: volumi alti su caffè/take-away)
    forn = _supplier('Partenope Monouso SRL', 'info@partenopemonouso.it', '+39 081 6660 3030', t.id)
    _consumable('Bicchierini caffè da asporto',       'pz', 50,   150, forn, t.id)  # sotto soglia
    _consumable('Coperchi per bicchierini caffè',     'pz', 60,   150, forn, t.id)  # sotto soglia
    _consumable('Filtri caffè in carta',              'pz', 1200, 300, forn, t.id)
    _consumable('Bicchieri smoothie/frullati 400ml',  'pz', 180,  100, forn, t.id)
    _consumable('Cannucce biodegradabili',            'pz', 500,  200, forn, t.id)
    _consumable('Tovaglioli di carta',                'pz', 600,  250, forn, t.id)
    _consumable('Zucchero monoporzione (bustine)',    'pz', 800,  300, forn, t.id)
    _consumable('Stuzzicadenti decorativi per aperitivi','pz', 250, 150, forn, t.id)
    _consumable('Sacchetti carta per cornetti',       'pz', 90,   150, forn, t.id)  # sotto soglia

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
    """
    Cancella i dati demo:
    - Tenant 'default': svuota catalogo e clienti (il tenant rimane).
    - mensa-tech, caffetteria-duomo: eliminati completamente.
    """
    default_t = Tenant.query.filter_by(slug='default').first()
    extra_tenants = Tenant.query.filter(Tenant.slug.in_(DEMO_SLUGS)).all()

    if not default_t and not extra_tenants:
        return True, 'Nessun dato demo presente: nulla da resettare.'

    # Svuota il tenant default (solo clienti + catalogo, non l'admin né il tenant)
    if default_t:
        _delete_tenant_data([default_t.id], delete_tenants=False, clients_only=True)

    # Elimina completamente i tenant demo extra
    if extra_tenants:
        _delete_tenant_data([t.id for t in extra_tenants], delete_tenants=True, clients_only=False)

    db.session.commit()
    return True, f'Reset completato: tenant default svuotato, {len(extra_tenants)} tenant demo rimossi.'


# ── Entry point ───────────────────────────────────────────────────────────────

def seed_demo_data():
    """
    Ritorna (ok: bool, message: str).
    Idempotente: ogni helper (_tenant/_cat/_prod/_client/_supplier/_consumable)
    salta i record già esistenti, quindi è sicuro rilanciarla più volte per
    aggiungere nuovi prodotti/consumabili anche se i tenant esistono già.
    """
    sa_role = Role.query.filter_by(name='superadmin').first()

    t1 = _seed_bar_centrale(sa_role)
    t2 = _seed_mensa_tech(sa_role)
    t3 = _seed_caffetteria_duomo(sa_role)
    db.session.commit()

    n_clients = sum(
        User.query.filter_by(is_client=True, tenant_id=t.id).count()
        for t in [t1, t2, t3]
    )
    n_products = sum(
        Product.query.filter_by(tenant_id=t.id).count()
        for t in [t1, t2, t3]
    )
    n_consumables = sum(
        ConsumableItem.query.filter_by(tenant_id=t.id).count()
        for t in [t1, t2, t3]
    )
    return True, (
        f'Demo caricato/aggiornato: 3 tenant, {n_clients} clienti, '
        f'{n_products} prodotti (incl. gluten free), {n_consumables} consumabili di magazzino. '
        f'Password admin tenant: demo1234 | Password clienti: cliente123'
    )
