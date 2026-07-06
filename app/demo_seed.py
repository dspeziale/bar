"""
Demo seed completo v2 – 100 clienti, 5 aziende convenzionate,
catalogo esteso (panini/poke/piatti caldi/dolci/bevande/colazione/s.g.),
ordini storici con articoli e transazioni wallet, sessioni banco QR,
menu pasti aziendali con prenotazioni, prenotazioni tavoli.

Eseguibile via UI  → Amministratore ▸ DS Consulting ▸ Manutenzione ▸ [Demo]
"""

import json
import random as _random
from datetime import date, timedelta, datetime as _dt
import secrets as _secrets

from app import db
from app.models import (
    User, Tenant, Category, Product, TimeSlot, Role,
    Supplier, ConsumableItem, DailyStock, Order, OrderItem,
    IngredientCategory, Ingredient, CustomOrderItem,
    CustomOrderItemIngredient, Table, TableReservation, TableTimeBand,
    Transaction, ConsumableMovement, CorporateAccount, CorporateMembership,
    DailyFixedMeal, CorporateMealBooking, PollVote, user_roles,
    BancoSession,
)
from config import Config

# ── Generatore deterministico (stesso seed → stessi dati) ────────────────────

_RNG = _random.Random(42)

# ── Dati anagrafici ───────────────────────────────────────────────────────────

_NOMI_M = [
    'Marco', 'Luca', 'Andrea', 'Matteo', 'Davide',
    'Stefano', 'Federico', 'Simone', 'Alessandro', 'Gabriele',
    'Lorenzo', 'Roberto', 'Fabio', 'Daniele', 'Paolo',
    'Giovanni', 'Francesco', 'Antonio', 'Riccardo', 'Emanuele',
]
_NOMI_F = [
    'Giulia', 'Sara', 'Martina', 'Chiara', 'Elena',
    'Laura', 'Valentina', 'Francesca', 'Paola', 'Silvia',
    'Alessia', 'Roberta', 'Michela', 'Barbara', 'Monica',
    'Serena', 'Cristina', 'Arianna', 'Beatrice', 'Claudia',
]
_COGNOMI = [
    'Rossi', 'Ferrari', 'Bianchi', 'Romano', 'Colombo',
    'Ricci', 'Marino', 'Greco', 'Bruno', 'Gallo',
    'Conti', 'Deluca', 'Costa', 'Giordano', 'Mancini',
    'Esposito', 'Villa', 'Fontana', 'Marchetti', 'Ferrara',
    'Lombardi', 'Barbieri', 'Moretti', 'Caruso', 'Fabbri',
]
_DOMINI = ['gmail.com', 'libero.it', 'hotmail.it', 'yahoo.it', 'tiscali.it']
_VIE    = [
    'Via Roma', 'Via Garibaldi', 'Corso Italia', 'Via Dante',
    'Via Manzoni', 'Via Verdi', 'Corso Buenos Aires', 'Via Padova',
    'Viale Monza', 'Via Torino',
]
_CITTA  = [
    'Milano', 'Sesto S.G.', 'Rho', 'Corsico', 'Cinisello B.',
    'Cologno M.', 'Paderno D.', 'Bollate', 'Cesano B.', 'Segrate',
]

# ── Menu pasti aziendali (7 rotazioni) ───────────────────────────────────────

_MENU_ROT = [
    ('Pasta al pomodoro fresco',        'Pollo arrosto alle erbe',           'Verdure grigliate',          'Acqua',         'Caffè'),
    ('Risotto ai funghi porcini',        'Cotoletta di maiale panata',        'Patate al forno',            'Acqua/Bibita',  'Caffè'),
    ('Gnocchi al ragù di carne',         'Pesce al forno con patate',         'Insalata mista',             'Acqua',         'Caffè'),
    ('Pasta al pesto genovese',          'Pollo alla cacciatora',             'Caponata siciliana',         'Acqua/Bibita',  ''),
    ('Riso alla parmigiana',             'Vitello tonnato con capperi',       'Fagiolini al vapore',        'Acqua',         'Caffè'),
    ('Tagliatelle al ragù bianco',       'Arrosto di tacchino con rosmarino', 'Zucchine trifolate',         'Acqua',         ''),
    ('Pasta e fagioli alla veneta',      'Salmone in crosta di sesamo',       'Spinaci saltati con aglio',  'Acqua/Bibita',  'Caffè'),
]

# ── Prodotti usati negli ordini self-service ──────────────────────────────────

_PRODOTTI_ORDINI = [
    'Panino Prosciutto e Mozzarella', 'Panino Bresaola e Rucola',
    'Panino Porchetta', 'Club Sandwich', 'Piadina Squacquerone e Prosciutto',
    'Tramezzino Tonno e Olive', 'Focaccia Pomodoro e Mozzarella',
    'Pasta al Pomodoro Fresco', 'Cotoletta alla Milanese',
    'Gnocchi al Ragù', 'Petto di Pollo Grigliato', 'Lasagna al Forno',
    'Polpette al Sugo', 'Caesar Salad', 'Insalata Caprese',
    'Insalata Nizzarda', 'Poke Salmone Classico', 'Poke Tonno Spicy',
    'Tiramisù Classico', 'Cannolo Siciliano', 'Cheesecake New York',
    'Acqua Naturale 0,5L', 'Coca-Cola 0,33L', 'Caffè Espresso',
    'Cappuccino', 'Birra Peroni Media',
]

# ── Prodotti usati nelle sessioni banco ───────────────────────────────────────

_PRODOTTI_BANCO = [
    'Caffè Espresso', 'Cappuccino', 'Cornetto Vuoto',
    'Cornetto alla Crema', 'Brioche con Nutella', 'Croissant alle Mandorle',
    'Tramezzino Tonno e Olive', 'Tramezzino Vegetariano',
    'Acqua Naturale 0,5L', 'Acqua Frizzante 0,5L', 'Coca-Cola 0,33L',
    'Succo di Frutta Ace', "Succo d'arancia fresco",
    'Panino Prosciutto e Mozzarella', 'Panino Porchetta',
    'Cannolo Siciliano', 'Torta della Casa',
    'Yogurt con Granola e Frutta', 'Panna Cotta ai Frutti di Bosco',
]

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers base
# ═══════════════════════════════════════════════════════════════════════════════

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
    for ts in Config.PICKUP_SLOTS:
        db.session.add(TimeSlot(time_str=ts, max_orders=30, is_active=True,
                                tenant_id=tenant_id))


def _tables(tenant_id):
    if Table.query.filter_by(tenant_id=tenant_id).first():
        return
    specs = [
        (1, 4, 'Finestra'),      (2, 4, 'Finestra'),
        (3, 2, 'Centro'),        (4, 2, 'Centro'),
        (5, 4, 'Terrazzo'),      (6, 4, 'Terrazzo'),
        (7, 6, 'Sala Interna'),  (8, 6, 'Sala Interna'),
        (9, 2, 'Bancone'),       (10, 2, 'Bancone'),
    ]
    for number, seats, location in specs:
        db.session.add(Table(number=number, seats=seats,
                             location=location, is_active=True,
                             tenant_id=tenant_id))


def _bands(tenant_id):
    if TableTimeBand.query.filter_by(tenant_id=tenant_id).first():
        return
    for start, end, dur, order in [
        ('11:25', '12:30', 30, 0),
        ('12:30', '13:30', 20, 1),
        ('13:30', '15:00', 25, 2),
    ]:
        db.session.add(TableTimeBand(start_time=start, end_time=end,
                                     duration_minutes=dur, sort_order=order,
                                     tenant_id=tenant_id))


def _cat(name, icon, color, tid):
    c = Category.query.filter_by(name=name, tenant_id=tid).first()
    if not c:
        c = Category(name=name, icon=icon, color=color, tenant_id=tid)
        db.session.add(c)
        db.session.flush()
    return c


def _prod(name, desc, price, cat, qty, tid):
    if not Product.query.filter_by(name=name, tenant_id=tid).first():
        db.session.add(Product(name=name, description=desc, price=price,
                               category_id=cat.id, daily_quantity=qty,
                               is_active=True, tenant_id=tid))


def _supplier(name, email, phone, tid):
    s = Supplier.query.filter_by(name=name, tenant_id=tid).first()
    if not s:
        s = Supplier(name=name, email=email, phone=phone, tenant_id=tid)
        db.session.add(s)
        db.session.flush()
    return s


def _consumable(name, unit, qty, threshold, sup, tid):
    if not ConsumableItem.query.filter_by(name=name, tenant_id=tid).first():
        db.session.add(ConsumableItem(
            name=name, unit=unit, quantity=qty, min_threshold=threshold,
            supplier_id=sup.id if sup else None, tenant_id=tid))


def _client(first, last, email, phone, bdate, address, tg, tid, wallet=0.0):
    if User.query.filter_by(email=email).first():
        return None
    u = User(
        username=email.split('@')[0].replace('.', '_'),
        email=email,
        is_client=True,
        is_active=True,
        first_name=first,
        last_name=last,
        phone=phone,
        birth_date=date.fromisoformat(bdate),
        address=address,
        telegram_chat_id=tg,
        tenant_id=tid,
        wallet_balance=wallet,
        loyalty_points=int(wallet * 12),
    )
    u.set_password('cliente123')
    db.session.add(u)
    db.session.flush()
    return u


def _corporate(name, email, price, covers, tid):
    ca = CorporateAccount.query.filter_by(name=name, tenant_id=tid).first()
    if not ca:
        ca = CorporateAccount(
            name=name, contact_email=email, daily_price=price,
            max_daily_covers=covers, is_active=True, tenant_id=tid)
        db.session.add(ca)
        db.session.flush()
    return ca


def _membership(uid, corp_id):
    if not CorporateMembership.query.filter_by(
            user_id=uid, corporate_id=corp_id).first():
        db.session.add(CorporateMembership(
            user_id=uid, corporate_id=corp_id, is_active=True))


def _daily_meal(corp, d, meal_name, primo, secondo, contorno, bev, caffe, price, tid):
    m = DailyFixedMeal.query.filter_by(
        corporate_id=corp.id, meal_date=d).first()
    if m:
        return m
    m = DailyFixedMeal(
        corporate_id=corp.id, meal_date=d, name=meal_name,
        primo=primo, secondo=secondo, contorno=contorno,
        bevanda=bev, caffe=caffe,
        price=price, max_bookings=corp.max_daily_covers,
        is_active=True, tenant_id=tid,
    )
    db.session.add(m)
    db.session.flush()
    return m


def _booking(uid, meal, status):
    if CorporateMealBooking.query.filter_by(
            user_id=uid, meal_id=meal.id).first():
        return
    b = CorporateMealBooking(
        user_id=uid, meal_id=meal.id, quantity=1, status=status)
    if status == 'booked':
        b.pickup_token = _secrets.token_hex(3).upper()
    db.session.add(b)


# ═══════════════════════════════════════════════════════════════════════════════
# Catalogo prodotti
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_catalog(t):
    pan = _cat('Panini & Piadine',   'fa-burger',                         'warning',   t.id)
    cal = _cat('Piatti Caldi',       'fa-bowl-food',                      'danger',    t.id)
    ins = _cat('Insalate',           'fa-leaf',                           'success',   t.id)
    pol = _cat('Poke Bowl',          'fa-bowl-rice',                      'info',      t.id)
    dol = _cat('Dolci',              'fa-cake-candles',                   'pink',      t.id)
    bev = _cat('Bevande',            'fa-bottle-water',                   'info',      t.id)
    col = _cat('Colazione',          'fa-mug-hot',                        'secondary', t.id)
    gf  = _cat('Senza Glutine',      'fa-wheat-awn-circle-exclamation',   'success',   t.id)

    # ── Panini & Piadine ─────────────────────────────────────────────────────
    _prod('Panino Prosciutto e Mozzarella',
          'Pane ciabatta, prosciutto cotto DOP, mozzarella fior di latte, pomodoro',
          4.50, pan, 40, t.id)
    _prod('Panino Bresaola e Rucola',
          'Pane integrale, bresaola della Valtellina, rucola, scaglie di Grana Padano',
          5.20, pan, 35, t.id)
    _prod('Panino Porchetta',
          'Rosetta croccante, porchetta artigianale laziale, salsa verde alle erbe',
          4.80, pan, 30, t.id)
    _prod('Tramezzino Tonno e Olive',
          'Pane morbido al latte, tonno sott\'olio, olive taggiasche, maionese',
          3.00, pan, 50, t.id)
    _prod('Tramezzino Vegetariano',
          'Pane morbido, verdure grigliate, hummus di ceci, rucola, carote',
          2.80, pan, 50, t.id)
    _prod('Club Sandwich',
          'Tre strati, pollo arrosto, bacon, lattuga iceberg, pomodoro, maionese',
          5.50, pan, 25, t.id)
    _prod('Piadina Squacquerone e Prosciutto',
          'Piadina romagnola DOC, squacquerone fresco, prosciutto crudo, rucola',
          5.00, pan, 30, t.id)
    _prod('Bagel Salmone e Cream Cheese',
          'Bagel tostato ai semi, salmone norvegese affumicato, cream cheese, capperi',
          5.80, pan, 20, t.id)
    _prod('Focaccia Pomodoro e Mozzarella',
          'Focaccia genovese, pomodorini pachino, mozzarella, basilico fresco',
          4.20, pan, 25, t.id)
    _prod('Panino Vegetariano Avocado',
          'Pane ai cereali, avocado, pomodoro, insalata, salsa yogurt',
          5.00, pan, 20, t.id)

    # ── Piatti Caldi ─────────────────────────────────────────────────────────
    _prod('Pasta al Pomodoro Fresco',
          'Spaghetti trafilati al bronzo, pomodoro San Marzano DOP, basilico fresco',
          5.00, cal, 30, t.id)
    _prod('Risotto Porcini e Taleggio',
          'Riso Carnaroli, funghi porcini secchi e freschi, fonduta di taleggio',
          7.00, cal, 20, t.id)
    _prod('Cotoletta alla Milanese',
          'Lombata di vitello, panatura tradizionale, patate al forno al rosmarino',
          9.00, cal, 15, t.id)
    _prod('Gnocchi al Ragù',
          'Gnocchi di patate fatti in casa, ragù di carne misto lento',
          6.50, cal, 20, t.id)
    _prod('Petto di Pollo Grigliato',
          'Petto di pollo marinato alle erbe aromatiche, contorno a scelta',
          7.50, cal, 25, t.id)
    _prod('Polpette al Sugo',
          'Polpette di carne mista, passata di pomodoro, purè al burro',
          6.00, cal, 20, t.id)
    _prod('Lasagna al Forno',
          'Lasagna classica bolognese, besciamella, ragù, parmigiano 24 mesi',
          7.00, cal, 18, t.id)
    _prod('Zuppa di Legumi',
          'Zuppa di ceci, fagioli borlotti, lenticchie, pane tostato',
          5.50, cal, 15, t.id)

    # ── Insalate ─────────────────────────────────────────────────────────────
    _prod('Insalata Caprese',
          'Pomodori cuore di bue, mozzarella di bufala DOP, basilico, olio EVO Sicilia',
          6.00, ins, 20, t.id)
    _prod('Insalata di Farro e Verdure',
          'Farro integrale, verdure di stagione, feta greca, vinaigrette al limone',
          5.50, ins, 20, t.id)
    _prod('Caesar Salad',
          'Lattuga romana, crostini di pane, parmigiano, salsa Caesar, pollo grigliato',
          6.50, ins, 20, t.id)
    _prod('Insalata Nizzarda',
          'Tonno al naturale, uova sode, olive nere, fagiolini, patate',
          6.50, ins, 18, t.id)
    _prod('Insalata di Quinoa',
          'Quinoa tricolore, avocado, pomodorini, edamame, semi di girasole',
          7.00, ins, 15, t.id)
    _prod('Insalata Greca',
          'Pomodori, cetriolo, peperone, cipolla di Tropea, feta, olive kalamata',
          6.00, ins, 15, t.id)

    # ── Poke Bowl ────────────────────────────────────────────────────────────
    _prod('Poke Salmone Classico',
          'Salmone fresco, riso Jasmine, edamame, cetriolo, avocado, salsa ponzu',
          9.50, pol, 20, t.id)
    _prod('Poke Tonno Spicy',
          'Tonno rosso, riso Jasmine, mango, cipolla rossa, mais, sriracha mayo',
          9.50, pol, 20, t.id)
    _prod('Poke Vegano',
          'Tofu marinato, riso integrale, avocado, carote julienne, edamame, tahini',
          8.50, pol, 15, t.id)
    _prod('Poke Gamberi',
          'Gamberi al vapore, riso Jasmine, mais dolce, avocado, salsa teriyaki',
          10.00, pol, 15, t.id)
    _prod('Poke Pollo Teriyaki',
          'Pollo teriyaki, riso integrale, cetriolo, carote, salsa sesamo-zenzero',
          9.00, pol, 18, t.id)

    # ── Dolci ────────────────────────────────────────────────────────────────
    _prod('Tiramisù Classico',
          'Ricetta tradizionale con mascarpone, savoiardi e caffè espresso',
          3.50, dol, 20, t.id)
    _prod('Cannolo Siciliano',
          'Cannolo croccante con ricotta di pecora, pistacchi di Bronte, scorza arancia',
          3.00, dol, 25, t.id)
    _prod('Torta della Casa',
          'Torta del giorno preparata dalla nostra pasticceria artigianale',
          3.00, dol, 20, t.id)
    _prod('Panna Cotta ai Frutti di Bosco',
          'Panna cotta cremosa con coulis di frutti di bosco freschi',
          3.50, dol, 15, t.id)
    _prod('Brownie al Cioccolato',
          'Brownie fondente belga, ganache al cioccolato, noce pecan tostata',
          3.50, dol, 18, t.id)
    _prod('Cheesecake New York',
          'Cheesecake classica su base biscotto, coulis di lamponi freschi',
          4.00, dol, 12, t.id)
    _prod('Crostata alla Marmellata',
          'Pasta frolla burro, marmellata di albicocche biologiche',
          2.80, dol, 15, t.id)

    # ── Bevande ──────────────────────────────────────────────────────────────
    _prod('Acqua Naturale 0,5L',      '',                                1.00, bev, 120, t.id)
    _prod('Acqua Frizzante 0,5L',     '',                                1.00, bev, 120, t.id)
    _prod('Coca-Cola 0,33L',         '',                                2.00, bev,  80, t.id)
    _prod('Fanta 0,33L',              '',                                2.00, bev,  60, t.id)
    _prod('Succo di Frutta Ace',      '',                                2.00, bev,  60, t.id)
    _prod("Succo d'arancia fresco",   'Spremuta di arance siciliane',    2.50, bev,  30, t.id)
    _prod('Tè freddo al limone',      '',                                2.00, bev,  50, t.id)
    _prod('Birra Peroni Media',       'Birra chiara alla spina 0,4L',    3.50, bev,  40, t.id)
    _prod('Birra Heineken 0,33L',     'Birra in bottiglia',              3.00, bev,  40, t.id)
    _prod('Caffè Espresso',           '',                                1.20, bev, 100, t.id)
    _prod('Cappuccino',               '',                                1.50, bev,  80, t.id)
    _prod('Macchiato',                '',                                1.30, bev,  60, t.id)
    _prod('Caffè d\'orzo',            'Bevanda calda senza caffeina',    1.20, bev,  30, t.id)

    # ── Colazione ────────────────────────────────────────────────────────────
    _prod('Cornetto Vuoto',
          'Cornetto sfogliato al burro e miele, leggero e croccante',
          1.30, col, 60, t.id)
    _prod('Cornetto alla Crema',
          'Cornetto sfogliato farcito con crema pasticcera artigianale',
          1.60, col, 60, t.id)
    _prod('Brioche con Nutella',
          'Brioche soffice farcita con crema alla nocciola',
          2.00, col, 40, t.id)
    _prod('Yogurt con Granola e Frutta',
          'Yogurt greco intero, granola croccante, frutti di stagione',
          3.50, col, 20, t.id)
    _prod('Croissant alle Mandorle',
          'Croissant francese farcito con frangipane alle mandorle',
          2.20, col, 30, t.id)
    _prod('Muffin ai Mirtilli',
          'Muffin americano con mirtilli freschi, senza lattosio',
          2.50, col, 25, t.id)

    # ── Senza Glutine ────────────────────────────────────────────────────────
    _prod('Panino S.G. Prosciutto',
          'Pane senza glutine certificato AIC, prosciutto cotto DOP, mozzarella',
          5.20, gf, 15, t.id)
    _prod('Pasta S.G. al Pomodoro',
          'Pasta di mais e riso, pomodoro San Marzano, basilico — cottura separata',
          5.80, gf, 15, t.id)
    _prod('Torta di Mele S.G.',
          'Farina di mandorle e riso, mele Golden, cannella, senza glutine',
          3.80, gf, 12, t.id)
    _prod('Crackers S.G.',
          'Crackers di mais certificati, confezione monoporzione 30g',
          2.00, gf, 25, t.id)
    _prod('Brownie S.G.',
          'Brownie senza glutine con farina di riso e cioccolato fondente',
          3.50, gf, 10, t.id)


# ═══════════════════════════════════════════════════════════════════════════════
# Magazzino
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_magazzino(t):
    f1 = _supplier('Cartabella Forniture SRL',    'ordini@cartabella.it',     '+39 02 5550 1010', t.id)
    f2 = _supplier('EcoGreen Imballaggi',          'info@ecogreen.it',         '+39 02 5550 2020', t.id)
    f3 = _supplier('Napolitano Dolciumi SRL',      'ordini@napolitano.it',     '+39 081 5550 1111', t.id)
    f4 = _supplier('Latticini Lombardi SRL',       'info@latticinil.it',       '+39 02 5550 3030', t.id)

    _consumable('Tovaglioli di carta',                  'pz', 480,   200, f1, t.id)
    _consumable('Bicchieri di carta 200ml',             'pz',  80,   150, f1, t.id)   # sotto soglia
    _consumable('Bicchieri compostabili 300ml',         'pz', 240,   100, f2, t.id)
    _consumable('Posate monouso – forchette',           'pz', 320,   100, f1, t.id)
    _consumable('Posate monouso – coltelli',            'pz', 310,   100, f1, t.id)
    _consumable('Posate monouso – cucchiai',            'pz', 290,   100, f1, t.id)
    _consumable('Piatti di carta (confezione 50 pz)',   'pz', 260,   100, f1, t.id)
    _consumable('Contenitori asporto con coperchio',    'pz',  40,    80, f2, t.id)   # sotto soglia
    _consumable('Box salad biodegradabili',             'pz', 180,    80, f2, t.id)
    _consumable('Sacchetti shopper per asporto',        'pz', 210,   100, f2, t.id)
    _consumable('Guanti monouso (scatola da 100)',       'pz',  14,     5, f1, t.id)
    _consumable('Cannucce biodegradabili',               'pz', 600,   200, f2, t.id)
    _consumable('Pellicola alimentare 30m',              'rt',   6,     3, f2, t.id)
    _consumable('Carta forno',                          'rt',  12,     4, f2, t.id)
    _consumable('Detersivo sgrassatore professionale',  'lt',   8,     3, f1, t.id)
    _consumable('Farina 00 (sacco 25kg)',               'kg',  50,    15, f3, t.id)
    _consumable('Zucchero semolato (sacco 10kg)',        'kg',  30,    10, f3, t.id)
    _consumable('Olio EVO (lattina 5L)',                'lt',  20,     8, f3, t.id)
    _consumable('Mozzarella fior di latte (kg)',        'kg',   8,     5, f4, t.id)   # sotto soglia
    _consumable('Prosciutto cotto DOP (kg)',            'kg',   6,     4, f4, t.id)   # sotto soglia


# ═══════════════════════════════════════════════════════════════════════════════
# 100 Clienti
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_clienti(tid):
    # 50 M (20 nomi × 25 cognomi, prime 50 combo) + 50 F (stesso schema)
    pairs_m = [(n, c) for n in _NOMI_M for c in _COGNOMI][:50]
    pairs_f = [(n, c) for n in _NOMI_F for c in _COGNOMI][:50]

    created = []
    for idx, (first, last) in enumerate(pairs_m + pairs_f):
        domain = _DOMINI[idx % len(_DOMINI)]
        email  = f'{first.lower()}.{last.lower()}.{idx + 1:03d}@{domain}'
        phone  = f'+39 333 {900 + idx // 100:03d} {idx % 1000:04d}'
        yr     = 1970 + (idx * 7 + 13) % 30         # 1970–1999
        mo     = (idx * 3 + 1) % 12 + 1
        day    = (idx * 11 + 5) % 28 + 1
        bdate  = f'{yr}-{mo:02d}-{day:02d}'
        via    = _VIE[idx % len(_VIE)]
        num    = (idx * 17 + 3) % 120 + 1
        citta  = _CITTA[idx % len(_CITTA)]
        wallet = round(20.0 + (idx * 13 + 7) % 80, 2)  # 20–100 €
        u = _client(first, last, email, phone, bdate,
                    f'{via} {num}, {citta}', '', tid, wallet)
        if u:
            created.append(u)
    return created


# ═══════════════════════════════════════════════════════════════════════════════
# 5 Aziende convenzionate
# ═══════════════════════════════════════════════════════════════════════════════

_AZIENDE_DEF = [
    ('Tech Solutions Milano SRL',      'hr@techsolutions.it',          8.00, 50),
    ('Studio Legale Marchetti & C.',   'info@legalemarchetti.it',      8.50, 30),
    ('Farmacia Verde Salute',           'ordini@farmaciaverde.it',      7.00, 25),
    ('Assicurazioni Roma Est SPA',      'hr@assicromaest.it',           7.50, 40),
    ('Istituto Manzoni – Formazione',   'segreteria@istituto-manzoni.it', 6.50, 60),
]


def _seed_aziende(tid, clients):
    aziende = []
    for name, email, price, covers in _AZIENDE_DEF:
        ca = _corporate(name, email, price, covers, tid)
        aziende.append(ca)
    db.session.flush()

    # Distribuisce 20 clienti per azienda (5 × 20 = 100)
    chunk = len(clients) // len(aziende)
    for i, ca in enumerate(aziende):
        group = clients[i * chunk: (i + 1) * chunk]
        for u in group:
            _membership(u.id, ca.id)
    db.session.flush()
    return aziende


# ═══════════════════════════════════════════════════════════════════════════════
# Ordini (ultimi 35 giorni)
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_ordini(t, clients, admin):
    today  = date.today()
    slots  = TimeSlot.query.filter_by(tenant_id=t.id, is_active=True).all()
    if not slots:
        return

    prods = {p.name: p for p in Product.query.filter(
        Product.tenant_id == t.id,
        Product.name.in_(_PRODOTTI_ORDINI),
    ).all()}
    if not prods:
        return
    pl = list(prods.values())

    for delta in range(35, -1, -1):
        d = today - timedelta(days=delta)
        n_day = _RNG.randint(8, 15)
        day_clients = _RNG.sample(clients, min(n_day, len(clients)))

        for client in day_clients:
            n_items = _RNG.randint(1, 3)
            chosen  = _RNG.sample(pl, min(n_items, len(pl)))
            items   = [(p, _RNG.randint(1, 2)) for p in chosen]
            total   = round(sum(p.price * q for p, q in items), 2)

            if delta > 3:
                status = _RNG.choices(['completed', 'cancelled'],
                                       weights=[88, 12])[0]
            elif delta > 0:
                status = _RNG.choices(['completed', 'ready'],
                                       weights=[70, 30])[0]
            else:
                status = _RNG.choices(['pending', 'confirmed', 'preparing'],
                                       weights=[40, 40, 20])[0]

            slot = _RNG.choice(slots)
            o = Order(user_id=client.id, slot_id=slot.id,
                      order_date=d, status=status,
                      total_price=total, tenant_id=t.id)
            db.session.add(o)
            db.session.flush()

            for prod, qty in items:
                db.session.add(OrderItem(
                    order_id=o.id, product_id=prod.id,
                    quantity=qty, unit_price=prod.price))

            if status == 'completed':
                h = _RNG.randint(11, 14)
                mi = _RNG.randint(0, 59)
                db.session.add(Transaction(
                    user_id=client.id,
                    amount=-total,
                    ttype='payment',
                    order_id=o.id,
                    created_at=_dt.combine(d, _dt.min.time()).replace(
                        hour=h, minute=mi),
                ))


# ═══════════════════════════════════════════════════════════════════════════════
# Sessioni Banco QR (ultimi 25 giorni)
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_banco(t, clients, admin):
    if not admin:
        return
    today = date.today()

    prods = {p.name: p for p in Product.query.filter(
        Product.tenant_id == t.id,
        Product.name.in_(_PRODOTTI_BANCO),
    ).all()}
    if not prods:
        return
    pl = list(prods.values())

    for delta in range(25, 0, -1):
        d = today - timedelta(days=delta)
        n_sess = _RNG.randint(3, 7)

        for _ in range(n_sess):
            n_items = _RNG.randint(1, 4)
            chosen  = _RNG.sample(pl, min(n_items, len(pl)))
            items_j = []
            total   = 0.0
            for prod in chosen:
                qty = _RNG.randint(1, 2)
                items_j.append({'id': prod.id, 'name': prod.name,
                                'price': prod.price, 'qty': qty})
                total += prod.price * qty

            total    = round(total, 2)
            customer = _RNG.choice(clients) if _RNG.random() > 0.35 else None
            h        = _RNG.randint(7, 19)
            mi       = _RNG.randint(0, 59)
            created  = _dt.combine(d, _dt.min.time()).replace(hour=h, minute=mi)

            db.session.add(BancoSession(
                token=_secrets.token_hex(8),
                staff_id=admin.id,
                customer_id=customer.id if customer else None,
                items_json=json.dumps(items_j),
                total=total,
                status='paid',
                created_at=created,
                expires_at=created + timedelta(minutes=30),
                tenant_id=t.id,
            ))


# ═══════════════════════════════════════════════════════════════════════════════
# Pasti Aziendali (ultimi 28 giorni lavorativi + prossimi 7)
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_pasti(t, aziende):
    today    = date.today()
    all_days = [today - timedelta(days=i) for i in range(28, -8, -1)]
    workdays = [d for d in all_days if d.weekday() < 5]  # lun–ven

    for i_az, ca in enumerate(aziende):
        members = [m.user for m in
                   CorporateMembership.query.filter_by(
                       corporate_id=ca.id, is_active=True).all()
                   if m.user]

        for d in workdays:
            mi = (d.toordinal() + i_az) % len(_MENU_ROT)
            primo, secondo, contorno, bev, caffe = _MENU_ROT[mi]
            meal = _daily_meal(
                ca, d,
                f'Menu del Giorno – {primo}',
                primo, secondo, contorno, bev, caffe,
                ca.daily_price, t.id,
            )

            is_past = (d < today)
            rate    = 0.60 + i_az * 0.04  # 60–76%
            for u in members:
                if _RNG.random() > rate:
                    continue
                if is_past:
                    status = _RNG.choices(
                        ['consumed', 'cancelled', 'booked'],
                        weights=[78, 14, 8])[0]
                else:
                    status = 'booked'
                _booking(u.id, meal, status)

    db.session.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# Prenotazioni tavoli (ultimi 25 giorni + prossimi 7)
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_tavoli_prenotazioni(t, clients):
    today  = date.today()
    tables = Table.query.filter_by(tenant_id=t.id, is_active=True).all()
    bands  = TableTimeBand.query.filter_by(tenant_id=t.id).all()
    if not tables or not bands:
        return

    for delta in range(25, -8, -1):
        d = today - timedelta(days=delta)
        if d.weekday() == 6:      # no domenica
            continue
        n_res = _RNG.randint(3, 8)
        chosen = _RNG.sample(clients, min(n_res, len(clients)))

        for cl in chosen:
            tbl   = _RNG.choice(tables)
            band  = _RNG.choice(bands)
            party = _RNG.randint(1, min(4, tbl.seats))
            if delta > 0:
                status = _RNG.choices(['completed', 'cancelled'],
                                       weights=[87, 13])[0]
            else:
                status = 'confirmed'
            db.session.add(TableReservation(
                user_id=cl.id, table_id=tbl.id, band_id=band.id,
                reservation_date=d, party_size=party, status=status,
                tenant_id=t.id,
            ))


# ═══════════════════════════════════════════════════════════════════════════════
# Topup wallet storici (rende credibile la cronologia transazioni)
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_topup(clients):
    today = date.today()
    for idx, u in enumerate(clients):
        n_topup = _RNG.randint(1, 3)
        for j in range(n_topup):
            amount = _RNG.choice([10.0, 20.0, 30.0, 50.0])
            days_ago = _RNG.randint(5, 60)
            h  = _RNG.randint(8, 18)
            mi = _RNG.randint(0, 59)
            db.session.add(Transaction(
                user_id=u.id,
                amount=amount,
                ttype='topup',
                order_id=None,
                created_at=_dt.combine(
                    today - timedelta(days=days_ago),
                    _dt.min.time()).replace(hour=h, minute=mi),
            ))


# ═══════════════════════════════════════════════════════════════════════════════
# Reset
# ═══════════════════════════════════════════════════════════════════════════════

def _delete_tenant_data(tenant_ids, delete_tenants=True, clients_only=False):
    """Cancella i dati di una lista di tenant_ids in ordine FK-safe."""
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
                db.text('UPDATE consumable_movements SET user_id = NULL'
                        ' WHERE user_id = ANY(:ids)'),
                {'ids': user_ids})
        else:
            db.session.execute(db.text(
                'UPDATE consumable_movements SET user_id = NULL'
                ' WHERE user_id IN ({})'.format(
                    ','.join(str(i) for i in user_ids))))
    if consumable_ids:
        ConsumableMovement.query.filter(
            ConsumableMovement.item_id.in_(consumable_ids)).delete(
            synchronize_session=False)
    ConsumableItem.query.filter(
        ConsumableItem.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)
    Supplier.query.filter(
        Supplier.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)

    # pasto aziendale
    if meal_ids:
        CorporateMealBooking.query.filter(
            CorporateMealBooking.meal_id.in_(meal_ids)).delete(
            synchronize_session=False)
    DailyFixedMeal.query.filter(
        DailyFixedMeal.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)
    if user_ids:
        CorporateMembership.query.filter(
            CorporateMembership.user_id.in_(user_ids)).delete(
            synchronize_session=False)
    CorporateAccount.query.filter(
        CorporateAccount.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)

    # sondaggi e transazioni clienti
    if user_ids:
        PollVote.query.filter(
            PollVote.user_id.in_(user_ids)).delete(synchronize_session=False)
        Transaction.query.filter(
            Transaction.user_id.in_(user_ids)).delete(synchronize_session=False)

    # banco sessions (per tenant, include sessioni staff/admin demo)
    BancoSession.query.filter(
        BancoSession.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)

    # ordini
    if custom_item_ids:
        CustomOrderItemIngredient.query.filter(
            CustomOrderItemIngredient.custom_item_id.in_(custom_item_ids)).delete(
            synchronize_session=False)
    if order_ids:
        if is_pg:
            db.session.execute(
                db.text('UPDATE transactions SET order_id = NULL'
                        ' WHERE order_id = ANY(:ids)'),
                {'ids': order_ids})
        else:
            db.session.execute(db.text(
                'UPDATE transactions SET order_id = NULL'
                ' WHERE order_id IN ({})'.format(
                    ','.join(str(i) for i in order_ids))))
        CustomOrderItem.query.filter(
            CustomOrderItem.order_id.in_(order_ids)).delete(
            synchronize_session=False)
        OrderItem.query.filter(
            OrderItem.order_id.in_(order_ids)).delete(synchronize_session=False)
    Order.query.filter(
        Order.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # tavoli, fasce e prenotazioni
    TableReservation.query.filter(
        TableReservation.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)
    TableTimeBand.query.filter(
        TableTimeBand.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)
    Table.query.filter(
        Table.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # catalogo
    if product_ids:
        DailyStock.query.filter(
            DailyStock.product_id.in_(product_ids)).delete(
            synchronize_session=False)
    Product.query.filter(
        Product.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    Ingredient.query.filter(
        Ingredient.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    IngredientCategory.query.filter(
        IngredientCategory.tenant_id.in_(tenant_ids)).delete(
        synchronize_session=False)
    Category.query.filter(
        Category.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
    TimeSlot.query.filter(
        TimeSlot.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)

    # utenti
    if user_ids:
        db.session.execute(
            user_roles.delete().where(user_roles.c.user_id.in_(user_ids)))
        User.query.filter(
            User.id.in_(user_ids)).delete(synchronize_session=False)

    if delete_tenants:
        Tenant.query.filter(
            Tenant.id.in_(tenant_ids)).delete(synchronize_session=False)


def reset_demo_data():
    """
    - Elimina completamente tutti i tenant diversi da 'default'.
    - Svuota catalogo, clienti e tutti i dati operativi del tenant 'default'.
    """
    default_t = Tenant.query.filter_by(slug='default').first()

    extra = Tenant.query.filter(Tenant.slug != 'default').all()
    if extra:
        _delete_tenant_data([t.id for t in extra],
                            delete_tenants=True, clients_only=False)

    if default_t:
        _delete_tenant_data([default_t.id],
                            delete_tenants=False, clients_only=True)

    db.session.commit()
    return True, (f'Reset completato: {len(extra)} tenant extra rimossi, '
                  f'tenant default svuotato.')


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def seed_demo_data():
    """
    Carica il demo completo dopo reset.
    Ritorna (ok: bool, messaggio: str).
    """
    t = _tenant('QuickLunch Bar', 'default', '#e94560')
    _slots(t.id)
    _tables(t.id)
    _bands(t.id)
    _seed_catalog(t)
    _seed_magazzino(t)
    db.session.flush()

    clients = _seed_clienti(t.id)
    # Fallback: se i clienti esistevano già (seed senza reset)
    if not clients:
        clients = User.query.filter_by(
            is_client=True, tenant_id=t.id).all()

    aziende = _seed_aziende(t.id, clients)

    admin = (User.query.filter_by(username='admin').first()
             or User.query.filter_by(is_admin=True).first())

    _seed_ordini(t, clients, admin)
    db.session.flush()

    _seed_banco(t, clients, admin)
    db.session.flush()

    _seed_pasti(t, aziende)

    _seed_tavoli_prenotazioni(t, clients)
    db.session.flush()

    _seed_topup(clients)
    db.session.commit()

    # ── Statistiche finali ────────────────────────────────────────────────────
    n_clients  = User.query.filter_by(is_client=True,  tenant_id=t.id).count()
    n_products = Product.query.filter_by(is_active=True, tenant_id=t.id).count()
    n_orders   = Order.query.filter_by(tenant_id=t.id).count()
    n_banco    = BancoSession.query.filter_by(tenant_id=t.id).count()
    n_meals    = DailyFixedMeal.query.filter_by(tenant_id=t.id).count()
    n_bookings = (db.session.query(CorporateMealBooking.id)
                  .join(DailyFixedMeal,
                        CorporateMealBooking.meal_id == DailyFixedMeal.id)
                  .filter(DailyFixedMeal.tenant_id == t.id)
                  .count())
    n_tables   = TableReservation.query.filter_by(tenant_id=t.id).count()
    n_corps    = CorporateAccount.query.filter_by(tenant_id=t.id).count()

    return True, (
        f'Demo caricato con successo! '
        f'{n_clients} clienti · {n_products} prodotti · {n_corps} aziende '
        f'· {n_orders} ordini · {n_banco} sessioni banco QR '
        f'· {n_meals} menu pasto · {n_bookings} prenotazioni pasto '
        f'· {n_tables} prenotazioni tavolo. '
        f'Password clienti: <strong>cliente123</strong>'
    )
