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

    # ── Numeri in italiano: virgola sui decimali, punto sulle migliaia ────
    @app.template_filter('num_it')
    def _num_it(v, decimali=2):
        return numero_italiano(v, decimali)

    # ── Date in italiano: strftime userebbe i nomi inglesi del locale ─────
    @app.template_filter('data_it')
    def _data_it(d, stile='lunga'):
        return data_italiana(d, stile)

    # ── Saluto in base alla fascia oraria del locale, non del server ───────
    @app.template_global()
    def saluto():
        return saluto_per_ora(datetime.now(_ROME).hour)

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
        from app.models import DISCLAIMER_DIETA
        return {'tables_enabled': tables_enabled(),
                'cesto_enabled': cesto_enabled(),
                'wallet_enabled': wallet_enabled(),
                'dieta_enabled': dieta_enabled(),
                'magazzino_enabled': magazzino_enabled(),
                'disclaimer_dieta': DISCLAIMER_DIETA}

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
    # Telegram chiama il webhook senza sessione ne' token CSRF.
    from app.main.routes import telegram_webhook as _tg_hook
    csrf.exempt(_tg_hook)

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
            _check_backup_reminder()
            if dieta_enabled():
                _check_diet_weekly()
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


def _funzione_attiva(chiave):
    """True se il flag di funzionalita' e' attivo ('0' = spento).

    Il valore viene letto a ogni render di base.html, quindi sta in cache per
    richiesta. In assenza dell'impostazione la funzione resta attiva, per non
    cambiare il comportamento delle installazioni esistenti.
    """
    from flask import g, has_request_context

    attr = '_ql_flag_' + chiave
    if has_request_context() and hasattr(g, attr):
        return getattr(g, attr)
    try:
        from app.notifications import get_setting
        val = (get_setting(chiave, '1') or '1') != '0'
    except Exception:
        val = True
    if has_request_context():
        setattr(g, attr, val)
    return val


def tables_enabled():
    """True se la gestione tavoli e prenotazioni e' attiva (Impostazioni)."""
    return _funzione_attiva('tables_enabled')


def magazzino_enabled():
    """Magazzino: consumabili, fornitori, avvisi di sottoscorta, giacenze
    degli ingredienti e scarico automatico del builder."""
    return _funzione_attiva('magazzino_enabled')


def dieta_enabled():
    """Dieta settimanale dei clienti: profilo, piano e controllo delle kcal."""
    return _funzione_attiva('dieta_enabled')


def cesto_enabled():
    """True se la gestione del cesto cucina e' attiva (Impostazioni)."""
    return _funzione_attiva('cesto_enabled')


def wallet_enabled():
    """True se il portafoglio prepagato (e la fedelta') e' attivo.

    A flag spento l'applicazione non muove denaro: niente controlli di
    saldo, addebiti, ricariche o punti. Le vendite restano registrate e il
    pagamento avviene alla cassa, fuori da QuickLunch.
    """
    return _funzione_attiva('wallet_enabled')


GIORNI_IT = ['lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì',
             'sabato', 'domenica']
MESI_IT = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
           'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']


def numero_italiano(v, decimali=2):
    """Numero in formato italiano: punto per le migliaia, virgola per i decimali.

    1234.5 -> '1.234,50'    0.4 -> '0,40'    12000 -> '12.000,00'

    Da usare per i valori mostrati. NON per il contenuto di un
    `<input type="number">`: lì il browser pretende il punto decimale e
    scarterebbe il valore.
    """
    try:
        n = float(v)
    except (TypeError, ValueError):
        return ''
    segno = '-' if n < 0 else ''
    testo = f'{abs(n):.{decimali}f}'
    if '.' in testo:
        interi, dec = testo.split('.')
    else:
        interi, dec = testo, ''
    gruppi = []
    while len(interi) > 3:
        gruppi.insert(0, interi[-3:])
        interi = interi[:-3]
    gruppi.insert(0, interi)
    out = segno + '.'.join(gruppi)
    return f'{out},{dec}' if dec else out


def data_italiana(d, stile='lunga'):
    """Data con nomi di giorno e mese in italiano.

    Serve perche' strftime('%A'/'%B') restituisce i nomi del locale del
    sistema, che sul server e' inglese.

    Stili disponibili:
      'lunga'       Lunedì 15 settembre 2025
      'giorno_mese' Lunedì 15 settembre
      'numerica'    Lunedì 15/09/2025
      'mese'        Settembre 2025
    """
    if d is None:
        return ''
    giorno = GIORNI_IT[d.weekday()].capitalize()
    mese = MESI_IT[d.month - 1]
    if stile == 'giorno_mese':
        return f'{giorno} {d.day} {mese}'
    if stile == 'numerica':
        return f'{giorno} {d.strftime("%d/%m/%Y")}'
    if stile == 'mese':
        return f'{mese.capitalize()} {d.year}'
    return f'{giorno} {d.day} {mese} {d.year}'


def saluto_per_ora(ora):
    """Saluto italiano corrispondente all'ora data (0-23).

    Fasce: mattina fino alle 13, pomeriggio fino alle 18, poi sera.
    """
    if 5 <= ora < 13:
        return 'Buongiorno'
    if 13 <= ora < 18:
        return 'Buon pomeriggio'
    return 'Buonasera'


def _check_table_reminders():
    from datetime import datetime as _dtt
    from app.models import TableReservation
    from app.notifications import send_reminder_to_user, get_numeric_setting

    remind = get_numeric_setting('table_reminder_minutes', 10)
    # Gli orari degli slot sono ore locali italiane: il confronto deve
    # avvenire con l'ora di Roma, non con UTC, altrimenti in produzione
    # (server in UTC) la finestra del promemoria cade 1-2 ore piu' tardi.
    now    = _dtt.now(_ROME).replace(tzinfo=None)
    today  = now.date()

    candidates = (
        TableReservation.query
        .filter_by(reservation_date=today, status='confirmed', table_alert_sent=False)
        .filter(TableReservation.checkin_at.is_(None))
        .all()
    )
    changed = False
    for res in candidates:
        if not res.session_start:
            continue
        try:
            slot_dt = _dtt.strptime(
                f'{today.isoformat()} {res.session_start}', '%Y-%m-%d %H:%M'
            )
        except ValueError:
            continue
        diff = (slot_dt - now).total_seconds() / 60
        if 0 < diff <= remind:
            inviato, _canale = send_reminder_to_user(
                res.user,
                f'⏰ Reminder: il tuo tavolo è tra <b>{int(diff)} minuti</b>!\n'
                f'🪑 Tavolo <b>{res.table.number}</b> — ore <b>{res.session_start}</b>\n'
                f'📅 {res.reservation_date.strftime("%d/%m/%Y")}',
                subject='Promemoria prenotazione tavolo',
            )
            if inviato:
                res.table_alert_sent = True
                changed = True
    if changed:
        db.session.commit()


def _check_order_reminders():
    from datetime import datetime as _dtt
    from app.models import Order
    from app.notifications import send_reminder_to_user, get_numeric_setting

    remind = get_numeric_setting('order_reminder_minutes', 15)
    # Gli orari degli slot sono ore locali italiane: il confronto deve
    # avvenire con l'ora di Roma, non con UTC, altrimenti in produzione
    # (server in UTC) la finestra del promemoria cade 1-2 ore piu' tardi.
    now    = _dtt.now(_ROME).replace(tzinfo=None)
    today  = now.date()

    candidates = (
        Order.query
        .filter_by(order_date=today, reminder_sent=False)
        .filter(Order.status.in_(['pending', 'confirmed', 'preparing']))
        .filter(Order.slot_id.isnot(None))
        .all()
    )
    changed = False
    for order in candidates:
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
            inviato, _canale = send_reminder_to_user(
                order.user,
                f'🍽️ Reminder: il tuo ordine è pronto per il ritiro alle <b>{order.slot.time_str}</b>!\n'
                f'📦 Ordine #{order.order_code or order.id} — <b>{numero_italiano(order.total_price)}€</b>\n'
                f'⏱️ Mancano circa <b>{int(diff)} minuti</b>',
                subject='Promemoria ritiro ordine',
            )
            if inviato:
                order.reminder_sent = True
                changed = True
    if changed:
        db.session.commit()


def _check_meal_reminders():
    from datetime import datetime as _dtt
    from app.models import CorporateMealBooking
    from app.notifications import (send_reminder_to_user,
                                   get_numeric_setting,
                                   tastiera_conferma_pasto)

    remind = get_numeric_setting('meal_reminder_minutes', 15)
    # Gli orari degli slot sono ore locali italiane: il confronto deve
    # avvenire con l'ora di Roma, non con UTC, altrimenti in produzione
    # (server in UTC) la finestra del promemoria cade 1-2 ore piu' tardi.
    now    = _dtt.now(_ROME).replace(tzinfo=None)
    today  = now.date()

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
            inviato, _canale = send_reminder_to_user(
                booking.user,
                f'🥗 Reminder: il tuo pasto aziendale è alle <b>{booking.slot.time_str}</b>!\n'
                f'📋 <b>{booking.meal.name}</b>\n'
                f'⏱️ Mancano circa <b>{int(diff)} minuti</b>\n\n'
                f'Confermi il ritiro? Se rispondi <b>No</b> la cucina non '
                f'lo prepara.',
                subject='Promemoria ritiro pasto aziendale',
                reply_markup=tastiera_conferma_pasto(booking.id),
            )
            if inviato:
                booking.reminder_sent = True
                changed = True
    if changed:
        db.session.commit()



# ═══════════════════════════════════════════════════════════════════════════
# Dieta: valori nutrizionali del listino di partenza
# ═══════════════════════════════════════════════════════════════════════════
#
# Stime per porzione servita al banco (kcal, proteine g, carboidrati g,
# grassi g, vegetariano, vegano). Sono valori indicativi da tabelle di
# composizione degli alimenti: il gestore li corregge dal backoffice sui
# propri piatti. Il nome e' la chiave perche' e' l'unica cosa che il seed e
# un'installazione gia' esistente hanno in comune.
_NUTRIZIONE_LISTINO = {
    'Cornetto vuoto':                  (230, 4, 28, 11, True, False),
    'Cornetto alla crema':             (290, 5, 36, 13, True, False),
    'Cornetto integrale':              (220, 5, 27, 10, True, False),
    'Sfogliatella':                    (300, 5, 38, 14, True, False),
    'Ciambella glassata':              (320, 4, 45, 14, True, False),
    'Caffè espresso':                  (2, 0, 0, 0, True, True),
    'Caffè macchiato':                 (15, 1, 1, 1, True, False),
    'Cappuccino':                      (90, 5, 8, 4, True, False),
    'Latte macchiato':                 (130, 7, 11, 6, True, False),
    'Caffè americano':                 (5, 0, 0, 0, True, True),
    'Caffè decaffeinato':              (2, 0, 0, 0, True, True),
    "Caffè d'orzo":                    (10, 0, 2, 0, True, True),
    'Ginseng':                         (70, 1, 12, 2, True, False),
    'Tè caldo':                        (2, 0, 0, 0, True, True),
    'Cioccolata calda':                (220, 8, 30, 8, True, False),
    'Panino prosciutto e mozzarella':  (480, 24, 52, 18, False, False),
    'Panino crudo e squacquerone':     (520, 25, 50, 22, False, False),
    'Panino porchetta':                (560, 26, 50, 27, False, False),
    'Panino vegetariano grigliato':    (420, 12, 60, 14, True, False),
    'Piadina crudo e rucola':          (540, 26, 52, 24, False, False),
    'Tramezzino tonno e pomodoro':     (300, 15, 28, 13, False, False),
    'Tramezzino prosciutto e funghi':  (290, 13, 28, 13, False, False),
    'Tramezzino vegetariano':          (260, 8, 30, 11, True, False),
    'Toast prosciutto e formaggio':    (330, 17, 30, 15, False, False),
    'Pizza margherita al taglio':      (420, 16, 55, 14, True, False),
    'Pizza patate e rosmarino':        (400, 9, 62, 12, True, True),
    'Focaccia farcita':                (480, 18, 52, 20, False, False),
    'Pasta al pomodoro':               (450, 14, 80, 8, True, True),
    'Pasta al ragù':                   (560, 26, 78, 14, False, False),
    'Lasagna al forno':                (620, 30, 50, 30, False, False),
    'Zuppa di legumi':                 (320, 18, 45, 6, True, True),
    'Insalata di riso':                (480, 14, 70, 15, False, False),
    'Pollo arrosto':                   (330, 40, 0, 18, False, False),
    'Cotoletta di pollo':              (420, 32, 22, 22, False, False),
    'Filetto di platessa al forno':    (260, 30, 8, 11, False, False),
    'Frittata di verdure':             (300, 18, 8, 22, True, False),
    'Roast beef':                      (280, 38, 1, 13, False, False),
    'Poke di salmone':                 (620, 30, 70, 22, False, False),
    'Poke di pollo':                   (560, 34, 68, 15, False, False),
    'Bowl vegetariana':                (520, 16, 78, 15, True, True),
    'Insalata mista':                  (120, 3, 8, 8, True, True),
    'Insalata caprese':                (350, 20, 6, 27, True, False),
    'Insalata di pollo e mais':        (380, 30, 18, 20, False, False),
    'Insalata greca':                  (330, 12, 12, 26, True, False),
    'Patate al forno':                 (220, 4, 36, 7, True, True),
    'Verdure grigliate':               (110, 3, 10, 6, True, True),
    'Spinaci saltati':                 (90, 5, 4, 6, True, True),
    "Fagiolini all'olio":              (100, 3, 8, 6, True, True),
    'Frutta di stagione':              (80, 1, 18, 0, True, True),
    'Macedonia fresca':                (120, 1, 28, 0, True, True),
    'Ananas a fette':                  (90, 1, 22, 0, True, True),
    'Yogurt bianco':                   (110, 6, 8, 5, True, False),
    'Yogurt alla frutta':              (150, 5, 24, 3, True, False),
    'Yogurt con granola':              (260, 9, 36, 8, True, False),
    'Tiramisù':                        (420, 8, 40, 25, True, False),
    'Panna cotta':                     (300, 4, 26, 20, True, False),
    'Torta della nonna':               (380, 7, 42, 20, True, False),
    "Crostatina all'albicocca":        (200, 3, 30, 8, True, False),
    'Gelato confezionato':             (220, 4, 26, 11, True, False),
    'Ghiacciolo':                      (60, 0, 15, 0, True, True),
    'Patatine in busta':               (160, 2, 15, 10, True, True),
    'Crackers':                        (120, 3, 20, 3, True, True),
    'Taralli':                         (200, 4, 30, 7, True, True),
    'Barretta di cioccolato':          (240, 3, 28, 13, True, False),
    'Acqua naturale 50 cl':            (0, 0, 0, 0, True, True),
    'Acqua frizzante 50 cl':           (0, 0, 0, 0, True, True),
    'Acqua naturale 1,5 L':            (0, 0, 0, 0, True, True),
    'Cola in lattina':                 (140, 0, 35, 0, True, True),
    'Aranciata in lattina':            (130, 0, 32, 0, True, True),
    'Tè freddo al limone':             (90, 0, 22, 0, True, True),
    'Succo di frutta ACE':             (110, 0, 26, 0, True, True),
    "Spremuta d'arancia":              (100, 2, 22, 0, True, True),
    'Birra bionda 33 cl':              (140, 1, 11, 0, True, True),
    'Calice di vino rosso':            (125, 0, 4, 0, True, True),
    'Calice di vino bianco':           (120, 0, 4, 0, True, True),
}

# Ingredienti del builder: (kcal, proteine, carboidrati, grassi, vegano,
# allergeni da aggiungere se mancano). Il pane porta glutine e il seed non lo
# diceva: senza questa correzione un celiaco vedrebbe ogni panino "adatto".
_NUTRIZIONE_INGREDIENTI = {
    'Pane bianco':        (220, 7, 42, 2, True, 'glutine'),
    'Pane integrale':     (200, 8, 38, 2, True, 'glutine'),
    'Ciabatta':           (240, 8, 46, 2, True, 'glutine'),
    'Rosetta':            (210, 7, 42, 1, True, 'glutine'),
    'Senza glutine':      (210, 4, 40, 4, True, ''),
    'Prosciutto cotto':   (70, 10, 1, 3, False, ''),
    'Prosciutto crudo':   (110, 13, 0, 6, False, ''),
    'Tonno':              (100, 20, 0, 2, False, 'pesce'),
    'Mozzarella':         (150, 11, 1, 11, False, ''),
    'Formaggio':          (180, 12, 0, 14, False, ''),
    'Bresaola':           (75, 15, 0, 1, False, ''),
    'Salmone':            (120, 12, 0, 8, False, ''),
    'Feta':               (130, 7, 2, 11, False, ''),
    'Pollo grigliato':    (110, 22, 0, 2, False, ''),
    'Legumi misti':       (130, 8, 20, 1, True, ''),
    'Lattuga':            (8, 1, 1, 0, True, ''),
    'Rucola':             (5, 1, 0, 0, True, ''),
    'Pomodoro':           (15, 1, 3, 0, True, ''),
    'Cetriolo':           (8, 0, 2, 0, True, ''),
    'Cipolla':            (15, 0, 3, 0, True, ''),
    'Peperoni':           (15, 1, 3, 0, True, ''),
    'Mais':               (40, 1, 8, 0, True, ''),
    'Olive':              (45, 0, 1, 5, True, ''),
    'Carote':             (20, 0, 4, 0, True, ''),
    'Avocado':            (120, 1, 4, 11, True, ''),
    'Maionese':           (90, 0, 1, 10, False, ''),
    'Senape':             (10, 0, 1, 0, True, 'senape'),
    'Ketchup':            (20, 0, 5, 0, True, ''),
    'Pesto':              (90, 2, 1, 9, False, ''),
    'Hummus':             (60, 3, 6, 3, True, 'sesamo'),
    'Yogurt greco':       (40, 3, 2, 2, False, ''),
    'Tahini':             (90, 3, 3, 8, True, ''),
    'Uovo':               (75, 6, 0, 5, False, ''),
    'Bacon':              (110, 7, 0, 9, False, ''),
    'Mozzarella extra':   (150, 11, 1, 11, False, ''),
    'Parmigiano':         (40, 4, 0, 3, False, ''),
    'Crostini':           (60, 2, 10, 1, True, 'glutine'),
    'Lattuga mista':      (10, 1, 1, 0, True, ''),
    'Spinaci baby':       (10, 1, 1, 0, True, ''),
    'Iceberg':            (8, 0, 2, 0, True, ''),
    'Aceto balsamico':    (15, 0, 3, 0, True, ''),
    'Olio e limone':      (90, 0, 0, 10, True, ''),
    'Ranch':              (80, 0, 2, 8, False, ''),
    'Semi di girasole':   (60, 2, 2, 5, True, ''),
    'Sesamo':             (55, 2, 2, 5, True, ''),
    'Pinoli':             (70, 1, 1, 7, True, ''),
    'Base poke':          (250, 5, 55, 1, True, ''),
    # Poke
    'Riso bianco':        (250, 5, 55, 1, True, ''),
    'Riso integrale':     (230, 5, 48, 2, True, ''),
    'Quinoa':             (220, 8, 39, 4, True, ''),
    'Mix riso e quinoa':  (235, 6, 47, 2, True, ''),
    'Tonno marinato':     (110, 22, 1, 2, False, 'pesce'),
    'Polpo':              (90, 17, 2, 1, False, 'molluschi'),
    'Gamberi':            (85, 18, 1, 1, False, 'crostacei'),
    'Tofu':               (120, 12, 3, 7, True, 'soia'),
    'Pollo teriyaki':     (150, 22, 6, 4, False, 'soia'),
    'Edamame':            (60, 6, 5, 2, True, 'soia'),
    'Carota julienne':    (20, 0, 4, 0, True, ''),
    'Cavolo rosso':       (15, 1, 3, 0, True, ''),
    'Mango':              (45, 0, 11, 0, True, ''),
    'Cipolla rossa':      (15, 0, 3, 0, True, ''),
    'Salsa ponzu':        (20, 1, 3, 0, True, 'soia'),
    'Maionese spicy':     (90, 0, 1, 10, False, 'uova'),
    'Teriyaki':           (35, 1, 7, 0, True, 'soia'),
    'Salsa di sesamo':    (80, 2, 3, 7, True, 'sesamo'),
    'Miso':               (25, 2, 3, 1, True, 'soia'),
    'Cipollotto':         (5, 0, 1, 0, True, ''),
    'Tempura flakes':     (70, 1, 9, 3, False, 'glutine'),
    'Alga nori':          (5, 1, 1, 0, True, ''),
    'Lime':               (5, 0, 1, 0, True, ''),
}


def _nutrizione_prodotto(nome):
    """I campi nutrizionali per Product(...) dal listino di partenza, o {}."""
    v = _NUTRIZIONE_LISTINO.get(nome)
    if not v:
        return {}
    return {'kcal': v[0], 'proteine_g': float(v[1]), 'carboidrati_g': float(v[2]),
            'grassi_g': float(v[3]), 'is_vegetarian': v[4], 'is_vegan': v[5]}


def _backfill_nutrizione():
    """Completa per nome i valori mancanti di prodotti e ingredienti.

    Tocca solo le righe con kcal NULL, cioe' mai compilate: quello che il
    gestore ha gia' scritto a mano non viene sovrascritto. Idempotente, gira
    a ogni avvio e dopo il primo passaggio non trova piu' nulla da fare.
    """
    from app.models import Product, Ingredient
    for p in Product.query.filter(Product.kcal.is_(None)).all():
        v = _NUTRIZIONE_LISTINO.get(p.name)
        if not v:
            continue
        p.kcal, p.proteine_g, p.carboidrati_g, p.grassi_g = v[0], float(v[1]), float(v[2]), float(v[3])
        p.is_vegetarian, p.is_vegan = v[4], v[5]
    for i in Ingredient.query.filter(Ingredient.kcal.is_(None)).all():
        v = _NUTRIZIONE_INGREDIENTI.get(i.name)
        if not v:
            continue
        i.kcal, i.proteine_g, i.carboidrati_g, i.grassi_g = v[0], float(v[1]), float(v[2]), float(v[3])
        i.is_vegan = v[4]
        if v[4]:
            i.is_vegetarian = True
        if v[5]:
            presenti = [a.strip().lower() for a in (i.allergens or '').split(',') if a.strip()]
            if v[5] not in presenti:
                i.allergens = ', '.join(presenti + [v[5]]) if presenti else v[5]


def _check_backup_reminder(adesso=None):
    """Il venerdì dalle 9 ricorda al canale dello staff di scaricare il
    backup, se l'ultimo ha più di sei giorni o non ne risulta nessuno.

    Una volta per settimana (`backup_promemoria_il`), a carico del traffico
    come gli altri promemoria. `adesso` serve ai test.
    """
    from datetime import datetime as _dtt
    from app.models import AppSetting
    from app.notifications import send_telegram

    from app.orari import momento_settimanale
    now = adesso or _dtt.now(_ROME)
    if not momento_settimanale('backup_promemoria_giorno', 'backup_promemoria_ora', now):
        return
    oggi = now.date().isoformat()

    def _leggi(chiave):
        riga = AppSetting.query.filter_by(key=chiave).first()
        return (riga.value if riga else '') or ''

    if _leggi('backup_promemoria_il') == oggi:
        return
    ultimo = _leggi('ultimo_backup_il')
    if ultimo:
        try:
            eta = now.replace(tzinfo=None) - _dtt.fromisoformat(ultimo)
        except ValueError:
            eta = None
        if eta is not None and eta.days < 6:
            return
    testo = ('💾 <b>Promemoria: backup settimanale</b>\n'
             + ("L'ultimo backup è del %s." % ultimo[:10] if ultimo
                else 'Non risulta nessun backup scaricato.')
             + '\nImpostazioni → Dati → <b>Scarica il backup</b>, e conserva il '
             'file fuori dal server.')
    ok, _msg = send_telegram(testo)
    if ok:
        riga = AppSetting.query.filter_by(key='backup_promemoria_il').first()
        if riga:
            riga.value = oggi
        else:
            db.session.add(AppSetting(key='backup_promemoria_il', value=oggi,
                                      label='Ultimo promemoria backup inviato'))
        db.session.commit()


def _check_diet_weekly(adesso=None):
    """Il lunedì mattina prepara il piano della settimana a chi ha la dieta
    attiva e vuole gli avvisi, e glielo manda su Telegram o per email.

    Gira nel polling dei promemoria: e' a carico del traffico, come gli
    altri, quindi "lunedì mattina" vuol dire alla prima visita di qualcuno
    dopo le 7. Il flag `notificato` sul piano evita i doppi invii.
    `adesso` serve ai test per fissare il momento.
    """
    from datetime import datetime as _dtt
    from app.models import DietProfile, DietPlan
    from app.dieta import genera_piano, inizio_settimana, testo_piano
    from app.notifications import send_reminder_to_user

    from app.orari import momento_settimanale
    now = adesso or _dtt.now(_ROME)
    if not momento_settimanale('dieta_avviso_giorno', 'dieta_avviso_ora', now):
        return
    lunedi = inizio_settimana(now.date())
    profili = DietProfile.query.filter_by(attivo=True, avvisi=True).all()
    for profilo in profili:
        user = profilo.user
        if not user or not user.is_active:
            continue
        piano = DietPlan.query.filter_by(user_id=user.id, week_start=lunedi).first()
        if piano is None:
            piano = genera_piano(user, profilo, lunedi, oggi=now.date())
        if piano.notificato or not piano.days:
            continue
        inviato, _canale = send_reminder_to_user(
            user, testo_piano(piano) + '\n\nApri QuickLunch → La mia dieta per ordinare '
            'un pranzo del piano con un tocco.',
            subject='Il tuo pranzo della settimana')
        if inviato:
            piano.notificato = True
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

    # Codice di collegamento del bot Telegram
    _ensure('users', 'telegram_link_code', "VARCHAR(16) DEFAULT ''")

    # Risposta ai bottoni Si'/No del promemoria del pasto
    _ensure('corporate_meal_bookings', 'conferma_utente', "VARCHAR(4) DEFAULT ''")

    # Fido wallet (saldo negativo consentito)
    _ensure('users', 'wallet_overdraft', 'FLOAT DEFAULT 0.0')

    # Barcode prodotto (EAN-13/UPC per scansione lattine al cesto)
    _ensure('products', 'barcode', "VARCHAR(32)")

    # Dieta: valori per porzione su prodotti, ingredienti e pasti aziendali.
    # NULL vuol dire "non indicato" e va lasciato tale: la dieta distingue
    # un piatto senza dati da uno a zero calorie.
    for _tab in ('products', 'ingredients', 'daily_fixed_meals', 'meal_configurations'):
        _ensure(_tab, 'kcal',          'INTEGER')
        _ensure(_tab, 'proteine_g',    'FLOAT')
        _ensure(_tab, 'carboidrati_g', 'FLOAT')
        _ensure(_tab, 'grassi_g',      'FLOAT')
        _ensure(_tab, 'is_vegan',      'BOOLEAN DEFAULT FALSE')
    for _tab in ('products', 'daily_fixed_meals', 'meal_configurations'):
        _ensure(_tab, 'is_vegetarian', 'BOOLEAN DEFAULT FALSE')

    # Colonne gia' esistenti da allargare. SQLite non impone la lunghezza di un
    # VARCHAR, PostgreSQL si': una chiave piu' lunga del previsto passa tutti
    # i test in locale e muore in produzione con StringDataRightTruncation.
    def _allarga(table, col, lunghezza):
        if not is_pg or table not in existing_tables:
            return
        for c in insp.get_columns(table):
            if c['name'] != col:
                continue
            attuale = getattr(c['type'], 'length', None)
            if attuale is None or attuale >= lunghezza:
                return
            try:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{col}" '
                                      f'TYPE VARCHAR({lunghezza})'))
                    conn.commit()
                print(f'[migration] widened {table}.{col} to VARCHAR({lunghezza})')
            except Exception as exc:
                print(f'[migration] ERROR widening {table}.{col}: {exc}')

    _allarga('diet_profiles', 'obiettivo', 32)   # 'dimagrimento_forte' sono 18 caratteri
    _ensure('diet_profiles', 'non_graditi',      "VARCHAR(512) DEFAULT ''")
    _ensure('diet_profiles', 'prodotti_esclusi', "TEXT DEFAULT ''")
    _ensure('diet_profiles', 'parole_non_gradite', "VARCHAR(512) DEFAULT ''")
    _ensure('diet_profiles', 'presa_atto_il', 'DATETIME')

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
    from app.models import (User, Category, Product, TimeSlot, Table,
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

    # Chi si e' registrato dal link di un tenant nasceva con is_client=False
    # (il default del modello) e restava invisibile nella lista clienti del
    # backoffice, che filtra proprio su quel campo. Si recuperano gli utenti
    # non amministratori e senza alcun ruolo di backoffice: sono clienti.
    # I letterali true/false valgono su SQLite e su PostgreSQL, dove il
    # confronto con 1/0 su una colonna boolean darebbe errore di tipo.
    try:
        db.session.execute(text(
            "UPDATE users SET is_client = true "
            "WHERE (is_client = false OR is_client IS NULL) "
            "  AND (is_admin = false OR is_admin IS NULL) "
            "  AND id NOT IN (SELECT user_id FROM user_roles)"
        ))
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
        # Catalogo di partenza per un bar/mensa aziendale: si toglie quello
        # che non si vende e si aggiunge il resto, invece di partire da zero.
        _categorie = [
            ('Colazione',      'fa-mug-saucer',      'warning'),
            ('Caffetteria',    'fa-mug-hot',         'dark'),
            ('Panini',         'fa-burger',          'warning'),
            ('Tramezzini',     'fa-bread-slice',     'warning'),
            ('Pizza e Focacce', 'fa-pizza-slice',    'danger'),
            ('Primi piatti',   'fa-bowl-food',       'danger'),
            ('Secondi piatti', 'fa-drumstick-bite',  'danger'),
            ('Poke e Bowl',    'fa-bowl-rice',       'info'),
            ('Insalate',       'fa-leaf',            'success'),
            ('Contorni',       'fa-carrot',          'success'),
            ('Frutta',         'fa-apple-whole',     'success'),
            ('Yogurt',         'fa-jar',             'info'),
            ('Dolci',          'fa-cake-candles',    'secondary'),
            ('Gelati',         'fa-ice-cream',       'info'),
            ('Snack',          'fa-cookie-bite',     'secondary'),
            ('Bevande',        'fa-bottle-water',    'primary'),
            ('Succhi e Bibite', 'fa-glass-water',    'primary'),
            ('Birra e Vino',   'fa-wine-glass',      'dark'),
        ]
        db.session.add_all([
            Category(name=nome, icon=icona, color=colore,
                     tenant_id=default_tenant.id)
            for nome, icona, colore in _categorie
        ])

    # ── Listino di partenza ───────────────────────────────────────────────
    # Prodotti tipici di un bar caffetteria con servizio mensa: si toglie
    # quello che non si vende e si correggono i prezzi, invece di partire da
    # un menu vuoto. Come per le categorie, solo se la tabella e' vuota.
    if not Product.query.first():
        db.session.flush()          # le categorie appena aggiunte devono avere un id
        _cat = {c.name: c.id for c in
                Category.query.filter_by(tenant_id=default_tenant.id).all()}
        # (categoria, nome, prezzo, quantita' al giorno, allergeni)
        _listino = [
            ('Colazione', 'Cornetto vuoto', 1.20, 40, 'glutine,latte,uova'),
            ('Colazione', 'Cornetto alla crema', 1.50, 30, 'glutine,latte,uova'),
            ('Colazione', 'Cornetto integrale', 1.40, 20, 'glutine,latte,uova'),
            ('Colazione', 'Sfogliatella', 1.80, 15, 'glutine,latte,uova'),
            ('Colazione', 'Ciambella glassata', 1.50, 15, 'glutine,latte,uova'),
            ('Caffetteria', 'Caffè espresso', 1.10, 300, ''),
            ('Caffetteria', 'Caffè macchiato', 1.20, 120, 'latte'),
            ('Caffetteria', 'Cappuccino', 1.50, 150, 'latte'),
            ('Caffetteria', 'Latte macchiato', 1.60, 60, 'latte'),
            ('Caffetteria', 'Caffè americano', 1.30, 40, ''),
            ('Caffetteria', 'Caffè decaffeinato', 1.20, 40, ''),
            ('Caffetteria', 'Caffè d\'orzo', 1.20, 30, ''),
            ('Caffetteria', 'Ginseng', 1.40, 30, 'latte'),
            ('Caffetteria', 'Tè caldo', 1.50, 30, ''),
            ('Caffetteria', 'Cioccolata calda', 2.20, 20, 'latte'),
            ('Panini', 'Panino prosciutto e mozzarella', 4.20, 25, 'glutine,latte'),
            ('Panini', 'Panino crudo e squacquerone', 5.00, 20, 'glutine,latte'),
            ('Panini', 'Panino porchetta', 4.50, 15, 'glutine'),
            ('Panini', 'Panino vegetariano grigliato', 4.20, 15, 'glutine'),
            ('Panini', 'Piadina crudo e rucola', 5.00, 15, 'glutine,latte'),
            ('Tramezzini', 'Tramezzino tonno e pomodoro', 3.20, 25, 'glutine,pesce,uova'),
            ('Tramezzini', 'Tramezzino prosciutto e funghi', 3.00, 25, 'glutine,uova,latte'),
            ('Tramezzini', 'Tramezzino vegetariano', 3.00, 15, 'glutine,uova'),
            ('Tramezzini', 'Toast prosciutto e formaggio', 3.00, 20, 'glutine,latte'),
            ('Pizza e Focacce', 'Pizza margherita al taglio', 3.00, 30, 'glutine,latte'),
            ('Pizza e Focacce', 'Pizza patate e rosmarino', 2.80, 20, 'glutine'),
            ('Pizza e Focacce', 'Focaccia farcita', 3.50, 20, 'glutine'),
            ('Primi piatti', 'Pasta al pomodoro', 5.50, 40, 'glutine'),
            ('Primi piatti', 'Pasta al ragù', 6.00, 40, 'glutine,sedano'),
            ('Primi piatti', 'Lasagna al forno', 6.50, 25, 'glutine,latte,uova,sedano'),
            ('Primi piatti', 'Zuppa di legumi', 5.00, 20, 'sedano'),
            ('Primi piatti', 'Insalata di riso', 5.50, 20, 'uova'),
            ('Secondi piatti', 'Pollo arrosto', 6.50, 30, ''),
            ('Secondi piatti', 'Cotoletta di pollo', 6.80, 30, 'glutine,uova'),
            ('Secondi piatti', 'Filetto di platessa al forno', 7.00, 20, 'pesce,glutine'),
            ('Secondi piatti', 'Frittata di verdure', 5.50, 20, 'uova,latte'),
            ('Secondi piatti', 'Roast beef', 7.50, 15, ''),
            ('Poke e Bowl', 'Poke di salmone', 8.50, 15, 'pesce,soia,sesamo'),
            ('Poke e Bowl', 'Poke di pollo', 7.50, 15, 'soia,sesamo'),
            ('Poke e Bowl', 'Bowl vegetariana', 7.00, 15, 'soia,sesamo'),
            ('Insalate', 'Insalata mista', 3.50, 25, ''),
            ('Insalate', 'Insalata caprese', 5.00, 20, 'latte'),
            ('Insalate', 'Insalata di pollo e mais', 6.00, 20, ''),
            ('Insalate', 'Insalata greca', 5.50, 15, 'latte'),
            ('Contorni', 'Patate al forno', 3.00, 40, ''),
            ('Contorni', 'Verdure grigliate', 3.50, 30, ''),
            ('Contorni', 'Spinaci saltati', 3.00, 20, ''),
            ('Contorni', 'Fagiolini all\'olio', 3.00, 20, ''),
            ('Frutta', 'Frutta di stagione', 1.00, 40, ''),
            ('Frutta', 'Macedonia fresca', 2.50, 20, ''),
            ('Frutta', 'Ananas a fette', 2.50, 15, ''),
            ('Yogurt', 'Yogurt bianco', 1.80, 20, 'latte'),
            ('Yogurt', 'Yogurt alla frutta', 1.80, 20, 'latte'),
            ('Yogurt', 'Yogurt con granola', 2.80, 15, 'latte,glutine,frutta_guscio'),
            ('Dolci', 'Tiramisù', 3.50, 20, 'glutine,latte,uova'),
            ('Dolci', 'Panna cotta', 3.00, 15, 'latte'),
            ('Dolci', 'Torta della nonna', 3.00, 15, 'glutine,latte,uova,frutta_guscio'),
            ('Dolci', 'Crostatina all\'albicocca', 1.50, 20, 'glutine,latte,uova'),
            ('Gelati', 'Gelato confezionato', 2.00, 25, 'latte'),
            ('Gelati', 'Ghiacciolo', 1.20, 20, ''),
            ('Snack', 'Patatine in busta', 1.50, 40, ''),
            ('Snack', 'Crackers', 0.80, 40, 'glutine'),
            ('Snack', 'Taralli', 1.50, 25, 'glutine'),
            ('Snack', 'Barretta di cioccolato', 1.30, 30, 'latte,soia,frutta_guscio'),
            ('Bevande', 'Acqua naturale 50 cl', 0.80, 120, ''),
            ('Bevande', 'Acqua frizzante 50 cl', 0.80, 80, ''),
            ('Bevande', 'Acqua naturale 1,5 L', 1.20, 40, ''),
            ('Succhi e Bibite', 'Cola in lattina', 2.00, 60, ''),
            ('Succhi e Bibite', 'Aranciata in lattina', 2.00, 40, ''),
            ('Succhi e Bibite', 'Tè freddo al limone', 1.80, 50, ''),
            ('Succhi e Bibite', 'Succo di frutta ACE', 1.80, 30, ''),
            ('Succhi e Bibite', 'Spremuta d\'arancia', 2.50, 20, ''),
            ('Birra e Vino', 'Birra bionda 33 cl', 3.00, 30, 'glutine'),
            ('Birra e Vino', 'Calice di vino rosso', 3.00, 20, 'solfiti'),
            ('Birra e Vino', 'Calice di vino bianco', 3.00, 20, 'solfiti'),
        ]
        for _cnome, _nome, _prezzo, _qta, _allerg in _listino:
            _cid = _cat.get(_cnome)
            if not _cid:
                continue
            db.session.add(Product(
                name=_nome, price=_prezzo, category_id=_cid,
                daily_quantity=_qta, is_active=True, allergens=_allerg,
                tenant_id=default_tenant.id, **_nutrizione_prodotto(_nome)))

    # ── Slot orari ────────────────────────────────────────────────────────
    if not TimeSlot.query.first():
        for t in Config.PICKUP_SLOTS:
            db.session.add(TimeSlot(time_str=t, max_orders=20,
                                    is_active=True,
                                    tenant_id=default_tenant.id))

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
            db.session.add(Table(number=num, seats=seats, location=loc,
                                 tenant_id=default_tenant.id))

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
        for _ic in ing_cats:
            _ic.tenant_id = default_tenant.id
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

    # ── Valori nutrizionali mancanti: dal listino di partenza ─────────────
    # Le installazioni gia' esistenti hanno prodotti e ingredienti creati da
    # questo stesso seed ma senza kcal: si completano per nome, una volta.
    _backfill_nutrizione()

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
        for _pc in poke_cats:
            _pc.tenant_id = default_tenant.id
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
        ('telegram_bot_username', 'dslunch_bot', 'Nome utente del bot Telegram'),
        ('public_base_url',       '',     'Indirizzo pubblico dell app, per i link nelle email inviate fuori dal web'),
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
        # Intervalli del carico mensile di dati di prova (righe al giorno)
        ('sim_pasti_min',    '20',  'Carico mensile: pasti aziendali minimi/giorno'),
        ('sim_pasti_max',    '50',  'Carico mensile: pasti aziendali massimi/giorno'),
        ('sim_snack_min',    '10',  'Carico mensile: panini e bevande minimi/giorno'),
        ('sim_snack_max',    '20',  'Carico mensile: panini e bevande massimi/giorno'),
        ('sim_caffe_min',    '80',  'Carico mensile: caffe minimi/giorno'),
        ('sim_caffe_max',    '120', 'Carico mensile: caffe massimi/giorno'),
        ('sim_builder_min',  '10',  'Carico mensile: prodotti builder minimi/giorno'),
        ('sim_builder_max',  '20',  'Carico mensile: prodotti builder massimi/giorno'),
        # Funzionalita' attivabili ('0' = disattivata)
        ('tables_enabled',         '1',     'Abilita gestione tavoli e prenotazioni'),
        ('cesto_enabled',          '1',     'Abilita gestione cesto cucina (QR)'),
        ('dieta_enabled',          '1',     'Abilita la dieta settimanale dei clienti'),
        ('magazzino_enabled',      '1',     'Abilita gestione magazzino (consumabili, fornitori, giacenze)'),
        ('wallet_enabled',         '1',     'Abilita portafoglio prepagato e punti'),
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

    # Orari dell'esercizio (app/orari.py): gli stessi default del modulo, cosi'
    # la programmazione parte coerente anche su un database vuoto.
    from app.orari import CHIAVI_ORARI as _CHIAVI_ORARI
    for _k, _v, _lab, _g, _t in _CHIAVI_ORARI:
        if not AppSetting.query.filter_by(key=_k).first():
            db.session.add(AppSetting(key=_k, value=_v, label=_lab))

    # Seconda passata: gli ingredienti poke vengono creati dopo la prima, e
    # al primo avvio resterebbero senza valori fino al riavvio successivo.
    _backfill_nutrizione()

    db.session.commit()
