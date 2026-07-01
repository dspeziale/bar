from datetime import date, timedelta
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.admin import bp
from app.models import (User, Product, Category, Order, OrderItem,
                        TimeSlot, DailyStock,
                        IngredientCategory, Ingredient,
                        Table, TableReservation, TableTimeBand,
                        Permission, Role, AppSetting, Poll, PollChoice, PollVote,
                        Tenant, Supplier, ConsumableItem, ConsumableMovement,
                        CorporateAccount, CorporateMembership,
                        DailyFixedMeal, CorporateMealBooking,
                        Transaction, CustomOrderItem, CustomOrderItemIngredient,
                        ALLERGENS)
from app.notifications import (send_telegram, send_telegram_to_user,
                                send_email_to_all_users, send_supplier_low_stock_alert,
                                telegram_poll_message, email_poll_html, get_setting)


# ── Tenant scope helper ───────────────────────────────────────────────────────

def _tenant_filter():
    """Per query filter_by: vuoto per il super admin globale, tenant_id per gli altri."""
    if current_user.is_admin:
        return {}
    return {'tenant_id': current_user.tenant_id}


# ── Decorators ────────────────────────────────────────────────────────────────

def staff_required(f):
    """Admin o qualsiasi utente con almeno un permesso backoffice."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not (current_user.is_admin or current_user.is_staff):
            flash('Accesso riservato al personale.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return login_required(decorated)


def require_permission(perm_name):
    """Richiede un permesso specifico; admin bypassa sempre."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not current_user.has_permission(perm_name):
                abort(403)
            return f(*args, **kwargs)
        return login_required(decorated_function)
    return decorator


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route('/')
@staff_required
def dashboard():
    today = date.today()
    orders_today = Order.query.filter_by(order_date=today)\
        .filter(Order.status != 'cancelled').all()
    revenue_today = sum(o.total_price for o in orders_today)
    users_count = User.query.filter_by(is_admin=False, **_tenant_filter()).count()
    products_count = Product.query.filter_by(is_active=True).count()
    res_today = TableReservation.query.filter_by(reservation_date=today)\
        .filter(TableReservation.status != 'cancelled').count()
    stock_alerts = [(p, p.available_today())
                    for p in Product.query.filter_by(is_active=True).all()
                    if p.available_today() <= 3]
    wallet_users = User.query.filter_by(is_admin=False, **_tenant_filter()).all()
    total_wallet = round(sum(u.wallet_balance for u in wallet_users), 2)
    consumable_alerts = ConsumableItem.query.filter_by(**_tenant_filter())\
        .filter(ConsumableItem.alert_active == True).count()
    return render_template('admin/dashboard.html',
                           orders_today=orders_today,
                           pending=[o for o in orders_today if o.status in ('pending', 'confirmed')],
                           revenue_today=revenue_today,
                           users_count=users_count,
                           products_count=products_count,
                           res_today=res_today,
                           stock_alerts=stock_alerts,
                           total_wallet=total_wallet,
                           consumable_alerts=consumable_alerts)


# ── Prodotti ──────────────────────────────────────────────────────────────────

@bp.route('/products')
@require_permission('manage_products')
def products():
    return render_template('admin/products.html',
                           products=Product.query.order_by(Product.category_id, Product.name).all(),
                           categories=Category.query.order_by(Category.name).all())


@bp.route('/products/new', methods=['POST'])
@require_permission('manage_products')
def product_new():
    name = request.form.get('name', '').strip()
    price = request.form.get('price', type=float)
    category_id = request.form.get('category_id', type=int)
    daily_quantity = request.form.get('daily_quantity', type=int, default=20)
    description = request.form.get('description', '').strip()
    if not name or not price or price <= 0 or not category_id:
        flash('Compila tutti i campi obbligatori.', 'danger')
        return redirect(url_for('admin.products'))
    db.session.add(Product(name=name, description=description, price=price,
                           category_id=category_id, daily_quantity=daily_quantity))
    db.session.commit()
    flash(f'Prodotto "{name}" aggiunto.', 'success')
    return redirect(url_for('admin.products'))


@bp.route('/products/<int:pid>/edit', methods=['POST'])
@require_permission('manage_products')
def product_edit(pid):
    p = db.get_or_404(Product, pid)
    p.name = request.form.get('name', p.name).strip()
    p.description = request.form.get('description', p.description).strip()
    p.price = request.form.get('price', type=float) or p.price
    p.category_id = request.form.get('category_id', type=int) or p.category_id
    p.daily_quantity = request.form.get('daily_quantity', type=int) or p.daily_quantity
    p.is_active = 'is_active' in request.form
    db.session.commit()
    flash(f'Prodotto "{p.name}" aggiornato.', 'success')
    return redirect(url_for('admin.products'))


@bp.route('/products/<int:pid>/toggle', methods=['POST'])
@require_permission('manage_products')
def product_toggle(pid):
    p = db.get_or_404(Product, pid)
    p.is_active = not p.is_active
    db.session.commit()
    flash(f'"{p.name}" {"attivato" if p.is_active else "disattivato"}.', 'info')
    return redirect(url_for('admin.products'))


# ── Stock giornaliero ─────────────────────────────────────────────────────────

@bp.route('/stock')
@require_permission('manage_stock')
def stock():
    today = date.today()
    products = Product.query.filter_by(is_active=True).all()
    stock_data = []
    for p in products:
        s = DailyStock.query.filter_by(product_id=p.id, stock_date=today).first()
        if not s:
            s = DailyStock(product_id=p.id, stock_date=today,
                           quantity_available=p.daily_quantity, quantity_reserved=0)
            db.session.add(s)
        stock_data.append((p, s))
    db.session.commit()
    return render_template('admin/stock.html', stock_data=stock_data, today=today)


@bp.route('/stock/<int:pid>/update', methods=['POST'])
@require_permission('manage_stock')
def stock_update(pid):
    today = date.today()
    new_qty = request.form.get('quantity_available', type=int)
    s = DailyStock.query.filter_by(product_id=pid, stock_date=today).first()
    if not s:
        p = db.get_or_404(Product, pid)
        s = DailyStock(product_id=pid, stock_date=today,
                       quantity_available=p.daily_quantity, quantity_reserved=0)
        db.session.add(s)
    if new_qty is not None and new_qty >= 0:
        s.quantity_available = new_qty
    db.session.commit()
    flash('Stock aggiornato.', 'success')
    return redirect(url_for('admin.stock'))


# ── Ordini ────────────────────────────────────────────────────────────────────

@bp.route('/orders')
@require_permission('view_orders')
def orders():
    filter_date = request.args.get('date', str(date.today()))
    try:
        from datetime import datetime as dt
        filter_date_obj = dt.strptime(filter_date, '%Y-%m-%d').date()
    except ValueError:
        filter_date_obj = date.today()
        filter_date = str(filter_date_obj)
    status_filter = request.args.get('status', '')
    q = Order.query.filter_by(order_date=filter_date_obj)
    if status_filter:
        q = q.filter_by(status=status_filter)
    orders = q.order_by(Order.slot_id, Order.created_at).all()
    slots = TimeSlot.query.filter_by(is_active=True).order_by(TimeSlot.time_str).all()
    return render_template('admin/orders.html', orders=orders, slots=slots,
                           filter_date=filter_date, status_filter=status_filter)


@bp.route('/orders/<int:oid>/slip')
@require_permission('view_orders')
def order_slip(oid):
    order = db.get_or_404(Order, oid)
    return render_template('admin/order_slip.html', order=order)


@bp.route('/orders/<int:oid>/status', methods=['POST'])
@require_permission('manage_orders')
def order_status(oid):
    order = db.get_or_404(Order, oid)
    new_status = request.form.get('status')
    if new_status not in ('pending', 'confirmed', 'preparing', 'ready', 'completed', 'cancelled'):
        flash('Stato non valido.', 'danger')
        return redirect(url_for('admin.orders'))
    if new_status == 'cancelled' and order.status != 'cancelled':
        order.user.credit_wallet(order.total_price,
                                 f'Rimborso ordine #{order.id} (admin)', order_id=order.id)
        for item in order.items:
            s = DailyStock.query.filter_by(product_id=item.product_id,
                                           stock_date=date.today()).first()
            if s:
                s.quantity_reserved = max(0, s.quantity_reserved - item.quantity)
    order.status = new_status
    db.session.commit()
    flash(f'Ordine #{order.id} → {new_status}', 'success')
    order_ref = order.order_code or f'#{order.id}'
    if new_status == 'ready':
        send_telegram_to_user(
            order.user,
            f'🔔 Il tuo ordine <b>{order_ref}</b> è <b>PRONTO</b> per il ritiro!\n'
            f'Vieni a ritirarlo entro qualche minuto.'
        )
    elif new_status == 'cancelled':
        send_telegram_to_user(
            order.user,
            f'❌ Ordine <b>{order_ref}</b> annullato dall\'amministratore.\n'
            f'Rimborso di <b>{order.total_price:.2f}€</b> sul tuo wallet.'
        )
    referer = request.referrer or ''
    if 'cucina' in referer:
        return redirect(url_for('admin.cucina'))
    return redirect(url_for('admin.orders'))


# ── Cucina / KDS ──────────────────────────────────────────────────────────────

@bp.route('/cucina')
@require_permission('view_orders')
def cucina():
    today = date.today()
    da_fare  = Order.query.filter_by(order_date=today, status='confirmed')\
                          .order_by(Order.slot_id, Order.created_at).all()
    in_prep  = Order.query.filter_by(order_date=today, status='preparing')\
                          .order_by(Order.slot_id, Order.created_at).all()
    pronti   = Order.query.filter_by(order_date=today, status='ready')\
                          .order_by(Order.slot_id, Order.created_at).all()
    return render_template('admin/cucina.html',
                           orders_da_fare=da_fare,
                           orders_in_prep=in_prep,
                           orders_pronti=pronti,
                           today=today)


# ── Utenti ────────────────────────────────────────────────────────────────────

@bp.route('/users')
@require_permission('manage_users')
def users():
    all_roles = Role.query.order_by(Role.name).all()
    all_users = User.query.filter_by(is_admin=False, is_client=False,
                                     **_tenant_filter()).order_by(User.username).all()
    return render_template('admin/users.html', users=all_users, all_roles=all_roles)


# ── Clienti ───────────────────────────────────────────────────────────────────

@bp.route('/clients')
@require_permission('manage_clients')
def clients():
    all_clients = User.query.filter_by(is_client=True,
                                       **_tenant_filter()).order_by(User.last_name, User.first_name).all()
    return render_template('admin/clients.html', clients=all_clients)


@bp.route('/clients/new', methods=['POST'])
@require_permission('manage_clients')
def client_new():
    import re
    from datetime import datetime as dt
    email      = request.form.get('email', '').strip().lower()
    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name', '').strip()
    if not email or '@' not in email or not first_name or not last_name:
        flash('Email, nome e cognome sono obbligatori.', 'danger')
        return redirect(url_for('admin.clients'))
    if User.query.filter_by(email=email).first():
        flash(f'Email "{email}" già registrata.', 'warning')
        return redirect(url_for('admin.clients'))
    base = re.sub(r'[^a-z0-9]', '.', email.split('@')[0]).strip('.') or 'cliente'
    username, n = base[:30], 1
    while User.query.filter_by(username=username).first():
        username = f'{base[:28]}{n}'; n += 1
    birth_raw = request.form.get('birth_date', '').strip()
    birth_date = None
    if birth_raw:
        try:
            birth_date = dt.strptime(birth_raw, '%Y-%m-%d').date()
        except ValueError:
            pass
    u = User(
        username=username, email=email,
        is_client=True,
        first_name=first_name,
        last_name=last_name,
        phone=request.form.get('phone', '').strip(),
        birth_date=birth_date,
        address=request.form.get('address', '').strip(),
        telegram_chat_id=request.form.get('telegram_chat_id', '').strip(),
    )
    pwd = request.form.get('password', '').strip()
    if pwd:
        u.set_password(pwd)
    db.session.add(u)
    db.session.commit()
    flash(f'Cliente "{u.full_name}" creato.', 'success')
    return redirect(url_for('admin.clients'))


@bp.route('/clients/<int:uid>/edit', methods=['POST'])
@require_permission('manage_clients')
def client_edit(uid):
    from datetime import datetime as dt
    u = db.get_or_404(User, uid)
    if not u.is_client:
        abort(404)
    u.first_name       = request.form.get('first_name', u.first_name).strip()
    u.last_name        = request.form.get('last_name',  u.last_name).strip()
    u.phone            = request.form.get('phone',      u.phone or '').strip()
    u.address          = request.form.get('address',    u.address or '').strip()
    u.telegram_chat_id = request.form.get('telegram_chat_id', u.telegram_chat_id or '').strip()
    birth_raw = request.form.get('birth_date', '').strip()
    if birth_raw:
        try:
            u.birth_date = dt.strptime(birth_raw, '%Y-%m-%d').date()
        except ValueError:
            pass
    pwd = request.form.get('password', '').strip()
    if pwd:
        u.set_password(pwd)
    db.session.commit()
    flash(f'Cliente "{u.full_name}" aggiornato.', 'success')
    return redirect(url_for('admin.clients'))


@bp.route('/clients/<int:uid>/toggle', methods=['POST'])
@require_permission('manage_clients')
def client_toggle(uid):
    u = db.get_or_404(User, uid)
    if not u.is_client:
        abort(404)
    u.is_active = not u.is_active
    db.session.commit()
    flash(f'Cliente {u.full_name} {"attivato" if u.is_active else "sospeso"}.', 'info')
    return redirect(url_for('admin.clients'))


@bp.route('/clients/<int:uid>/delete', methods=['POST'])
@require_permission('manage_clients')
def client_delete(uid):
    u = db.get_or_404(User, uid)
    if not u.is_client:
        abort(404)
    name = u.full_name
    db.session.delete(u)
    db.session.commit()
    flash(f'Cliente "{name}" eliminato.', 'info')
    return redirect(url_for('admin.clients'))


@bp.route('/clients/<int:uid>/topup', methods=['POST'])
@require_permission('manage_clients')
def client_topup(uid):
    u = db.get_or_404(User, uid)
    if not u.is_client:
        abort(404)
    amount = request.form.get('amount', type=float)
    note = request.form.get('note', 'Ricarica manuale').strip() or 'Ricarica manuale'
    if not amount or amount <= 0:
        flash('Importo non valido.', 'danger')
        return redirect(url_for('admin.clients'))
    u.credit_wallet(amount, note)
    db.session.commit()
    flash(f'+{amount:.2f}€ aggiunti al wallet di {u.full_name}.', 'success')
    return redirect(url_for('admin.clients'))


@bp.route('/users/new', methods=['POST'])
@require_permission('manage_users')
def user_new():
    import re
    email    = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    if not email or '@' not in email or not password:
        flash('Email e password obbligatori.', 'danger')
        return redirect(url_for('admin.users'))
    if User.query.filter_by(email=email).first():
        flash(f'Email "{email}" già registrata.', 'warning')
        return redirect(url_for('admin.users'))
    base = re.sub(r'[^a-z0-9]', '.', email.split('@')[0]).strip('.') or 'utente'
    username, n = base[:30], 1
    while User.query.filter_by(username=username).first():
        username = f'{base[:28]}{n}'; n += 1
    u = User(username=username, email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    flash(f'Utente "{email}" creato.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:uid>/topup', methods=['POST'])
@require_permission('manage_users')
def user_topup(uid):
    user = db.get_or_404(User, uid)
    amount = request.form.get('amount', type=float)
    note = request.form.get('note', 'Ricarica manuale').strip() or 'Ricarica manuale'
    if not amount or amount <= 0:
        flash('Importo non valido.', 'danger')
        return redirect(url_for('admin.users'))
    user.credit_wallet(amount, note)
    db.session.commit()
    flash(f'+{amount:.2f}€ aggiunti al wallet di {user.username}.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:uid>/toggle', methods=['POST'])
@require_permission('manage_users')
def user_toggle(uid):
    user = db.get_or_404(User, uid)
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'Utente {user.username} {"attivato" if user.is_active else "sospeso"}.', 'info')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:uid>/roles', methods=['POST'])
@require_permission('manage_users')
def user_roles_assign(uid):
    user = db.get_or_404(User, uid)
    role_ids = request.form.getlist('role_ids', type=int)
    user.roles = Role.query.filter(Role.id.in_(role_ids)).all() if role_ids else []
    db.session.commit()
    flash(f'Ruoli di {user.username} aggiornati.', 'success')
    return redirect(url_for('admin.users'))


# ── Categorie prodotto ────────────────────────────────────────────────────────

@bp.route('/categories')
@require_permission('manage_categories')
def categories():
    return render_template('admin/categories.html',
                           categories=Category.query.order_by(Category.name).all())


@bp.route('/categories/new', methods=['POST'])
@require_permission('manage_categories')
def category_new():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Nome obbligatorio.', 'danger')
        return redirect(url_for('admin.categories'))
    if Category.query.filter_by(name=name).first():
        flash('Categoria già esistente.', 'warning')
        return redirect(url_for('admin.categories'))
    db.session.add(Category(name=name,
                            icon=request.form.get('icon', 'fa-utensils'),
                            color=request.form.get('color', 'secondary')))
    db.session.commit()
    flash(f'Categoria "{name}" creata.', 'success')
    return redirect(url_for('admin.categories'))


@bp.route('/categories/<int:cid>/delete', methods=['POST'])
@require_permission('manage_categories')
def category_delete(cid):
    cat = Category.query.get_or_404(cid)
    if cat.products:
        flash(f'Impossibile eliminare "{cat.name}": contiene {len(cat.products)} prodott{"o" if len(cat.products)==1 else "i"}. Spostali prima.', 'danger')
        return redirect(url_for('admin.categories'))
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    flash(f'Categoria "{name}" eliminata.', 'success')
    return redirect(url_for('admin.categories'))


# ── Slot orari ────────────────────────────────────────────────────────────────

@bp.route('/slots')
@require_permission('manage_slots')
def slots():
    return redirect(url_for('admin.tavoli', tab='slot'))


@bp.route('/slots/<int:sid>/toggle', methods=['POST'])
@require_permission('manage_slots')
def slot_toggle(sid):
    slot = db.get_or_404(TimeSlot, sid)
    slot.is_active = not slot.is_active
    db.session.commit()
    flash(f'Slot {slot.time_str} {"attivato" if slot.is_active else "disattivato"}.', 'info')
    return redirect(url_for('admin.tavoli', tab='slot'))


@bp.route('/slots/<int:sid>/capacity', methods=['POST'])
@require_permission('manage_slots')
def slot_capacity(sid):
    slot = db.get_or_404(TimeSlot, sid)
    cap = request.form.get('max_orders', type=int)
    if cap and cap > 0:
        slot.max_orders = cap
        db.session.commit()
        flash(f'Capacità slot {slot.time_str} → {cap}.', 'success')
    return redirect(url_for('admin.tavoli', tab='slot'))


# ── Tavoli ────────────────────────────────────────────────────────────────────

@bp.route('/tables')
@require_permission('manage_tables_admin')
def tables():
    return redirect(url_for('admin.tavoli', tab='tavoli'))


@bp.route('/tables/new', methods=['POST'])
@require_permission('manage_tables_admin')
def table_new():
    number = request.form.get('number', type=int)
    seats = request.form.get('seats', type=int, default=4)
    location = request.form.get('location', '').strip()
    if not number:
        flash('Numero tavolo obbligatorio.', 'danger')
        return redirect(url_for('admin.tables'))
    if Table.query.filter_by(number=number).first():
        flash(f'Tavolo {number} già esistente.', 'warning')
        return redirect(url_for('admin.tables'))
    db.session.add(Table(number=number, seats=seats, location=location))
    db.session.commit()
    flash(f'Tavolo {number} aggiunto.', 'success')
    return redirect(url_for('admin.tavoli', tab='tavoli'))


@bp.route('/tables/<int:tid>/edit', methods=['POST'])
@require_permission('manage_tables_admin')
def table_edit(tid):
    t = db.get_or_404(Table, tid)
    t.seats = request.form.get('seats', type=int) or t.seats
    t.location = request.form.get('location', t.location).strip()
    t.is_active = 'is_active' in request.form
    db.session.commit()
    flash(f'Tavolo {t.number} aggiornato.', 'success')
    return redirect(url_for('admin.tavoli', tab='tavoli'))


# ── Prenotazioni tavoli ───────────────────────────────────────────────────────

@bp.route('/reservations')
@require_permission('manage_reservations_admin')
def reservations():
    d = request.args.get('date', '')
    return redirect(url_for('admin.tavoli', date=d or None))


@bp.route('/reservations/<int:rid>/cancel', methods=['POST'])
@require_permission('manage_reservations_admin')
def reservation_cancel(rid):
    res = db.get_or_404(TableReservation, rid)
    res.status = 'cancelled'
    db.session.commit()
    flash(f'Prenotazione tavolo {res.table.number} annullata.', 'info')
    return redirect(url_for('admin.tavoli'))


# ── Gestione Tavoli unificata ─────────────────────────────────────────────────

@bp.route('/tavoli')
@require_permission('manage_tables_admin')
def tavoli():
    from datetime import datetime as dt
    tab = request.args.get('tab', 'panoramica')

    raw_date = request.args.get('date', str(date.today()))
    try:
        sel_date = dt.strptime(raw_date, '%Y-%m-%d').date()
    except ValueError:
        sel_date = date.today()
        raw_date = str(sel_date)

    prev_day = (sel_date - timedelta(days=1)).isoformat()
    next_day = (sel_date + timedelta(days=1)).isoformat()

    all_tables = Table.query.filter_by(is_active=True).order_by(Table.number).all()
    all_tables_with_inactive = Table.query.order_by(Table.number).all()
    bands = TableTimeBand.query.order_by(TableTimeBand.sort_order, TableTimeBand.start_time).all()
    order_slots = TimeSlot.query.order_by(TimeSlot.time_str).all()

    # Per la panoramica: prenotazioni del giorno indicizzate per (table_id, session_start)
    day_reservations = (TableReservation.query
                        .filter_by(reservation_date=sel_date)
                        .filter(TableReservation.status != 'cancelled')
                        .all())
    # index: (table_id, session_start) → reservation
    res_index = {(r.table_id, r.session_start): r for r in day_reservations}

    # Tutte le prenotazioni del giorno (incluse annullate) per la lista completa
    all_day_res = (TableReservation.query
                   .filter_by(reservation_date=sel_date)
                   .order_by(TableReservation.session_start, TableReservation.table_id)
                   .all())

    return render_template('admin/tavoli.html',
                           tab=tab, sel_date=raw_date, today=str(date.today()),
                           prev_day=prev_day, next_day=next_day,
                           all_tables=all_tables,
                           all_tables_with_inactive=all_tables_with_inactive,
                           bands=bands, order_slots=order_slots,
                           res_index=res_index,
                           all_day_res=all_day_res)


@bp.route('/tavoli/bande/new', methods=['POST'])
@require_permission('manage_tables_admin')
def band_new():
    start = request.form.get('start_time', '').strip()
    end   = request.form.get('end_time',   '').strip()
    dur   = request.form.get('duration_minutes', type=int)
    if not start or not end or not dur or dur < 1:
        flash('Compila tutti i campi della fascia oraria.', 'danger')
        return redirect(url_for('admin.tavoli', tab='fasce'))
    tid = current_user.tenant_id if not current_user.is_admin else None
    # calcola sort_order come posizione temporale
    existing = TableTimeBand.query.count()
    band = TableTimeBand(start_time=start, end_time=end,
                         duration_minutes=dur, sort_order=existing,
                         tenant_id=tid)
    db.session.add(band)
    db.session.commit()
    flash(f'Fascia {start}–{end} ({dur} min) aggiunta.', 'success')
    return redirect(url_for('admin.tavoli', tab='fasce'))


@bp.route('/tavoli/bande/<int:bid>/delete', methods=['POST'])
@require_permission('manage_tables_admin')
def band_delete(bid):
    band = TableTimeBand.query.get_or_404(bid)
    label = band.label
    if band.reservations:
        flash(f'Impossibile eliminare la fascia "{label}": ha prenotazioni collegate.', 'danger')
        return redirect(url_for('admin.tavoli', tab='fasce'))
    db.session.delete(band)
    db.session.commit()
    flash(f'Fascia "{label}" eliminata.', 'success')
    return redirect(url_for('admin.tavoli', tab='fasce'))


@bp.route('/tables/<int:tid>/delete', methods=['POST'])
@require_permission('manage_tables_admin')
def table_delete(tid):
    t = Table.query.get_or_404(tid)
    active_res = TableReservation.query.filter_by(
        table_id=tid, status='confirmed').count()
    if active_res:
        flash(f'Tavolo {t.number} ha {active_res} prenotazioni attive: annullale prima.', 'danger')
        return redirect(url_for('admin.tavoli', tab='tavoli'))
    db.session.delete(t)
    db.session.commit()
    flash(f'Tavolo {t.number} eliminato.', 'success')
    return redirect(url_for('admin.tavoli', tab='tavoli'))


# ── Ingredienti builder ───────────────────────────────────────────────────────

@bp.route('/ingredients')
@require_permission('manage_ingredients')
def ingredients():
    cats = IngredientCategory.query.order_by(
        IngredientCategory.builder_type, IngredientCategory.sort_order).all()
    return render_template('admin/ingredients.html', categories=cats)


@bp.route('/ingredients/new', methods=['POST'])
@require_permission('manage_ingredients')
def ingredient_new():
    name = request.form.get('name', '').strip()
    category_id = request.form.get('category_id', type=int)
    price_extra = request.form.get('price_extra', type=float, default=0.0)
    is_vegetarian = 'is_vegetarian' in request.form
    allergens = request.form.get('allergens', '').strip()
    if not name or not category_id:
        flash('Nome e categoria obbligatori.', 'danger')
        return redirect(url_for('admin.ingredients'))
    db.session.add(Ingredient(name=name, category_id=category_id,
                              price_extra=price_extra or 0.0,
                              is_vegetarian=is_vegetarian, allergens=allergens))
    db.session.commit()
    flash(f'Ingrediente "{name}" aggiunto.', 'success')
    return redirect(url_for('admin.ingredients'))


@bp.route('/ingredients/<int:iid>/toggle', methods=['POST'])
@require_permission('manage_ingredients')
def ingredient_toggle(iid):
    ing = db.get_or_404(Ingredient, iid)
    ing.is_active = not ing.is_active
    db.session.commit()
    flash(f'"{ing.name}" {"attivato" if ing.is_active else "disattivato"}.', 'info')
    return redirect(url_for('admin.ingredients'))


@bp.route('/ingredients/<int:iid>/edit', methods=['POST'])
@require_permission('manage_ingredients')
def ingredient_edit(iid):
    ing = db.get_or_404(Ingredient, iid)
    ing.name = request.form.get('name', ing.name).strip()
    ing.price_extra = request.form.get('price_extra', type=float, default=ing.price_extra) or 0.0
    ing.is_vegetarian = 'is_vegetarian' in request.form
    ing.allergens = request.form.get('allergens', '').strip()
    db.session.commit()
    flash(f'Ingrediente "{ing.name}" aggiornato.', 'success')
    return redirect(url_for('admin.ingredients'))


# ── Report ────────────────────────────────────────────────────────────────────

@bp.route('/report')
@require_permission('view_reports')
def report():
    from datetime import timedelta
    from sqlalchemy import func
    today = date.today()
    days = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
    revenue_by_day, orders_by_day = {}, {}
    for d in days:
        res = db.session.query(func.sum(Order.total_price), func.count(Order.id))\
            .filter(Order.order_date == d, Order.status != 'cancelled').first()
        revenue_by_day[str(d)] = round(res[0] or 0, 2)
        orders_by_day[str(d)] = res[1] or 0

    top_products = db.session.query(
        Product.name, func.sum(OrderItem.quantity).label('sold')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .filter(Order.status != 'cancelled')\
     .group_by(Product.id)\
     .order_by(func.sum(OrderItem.quantity).desc()).limit(10).all()

    return render_template('admin/report.html',
                           days=[str(d) for d in days],
                           revenue_by_day=revenue_by_day,
                           orders_by_day=orders_by_day,
                           top_products=top_products)


# ── Ruoli & Permessi ──────────────────────────────────────────────────────────

@bp.route('/roles')
@require_permission('manage_roles')
def roles():
    all_roles = Role.query.order_by(Role.name).all()
    all_perms = Permission.query.order_by(Permission.category, Permission.label).all()
    # group permissions by category
    from itertools import groupby
    cats = {}
    for p in all_perms:
        cats.setdefault(p.category, []).append(p)
    return render_template('admin/roles.html',
                           roles=all_roles,
                           all_perms=all_perms,
                           perm_cats=cats)


@bp.route('/roles/new', methods=['POST'])
@require_permission('manage_roles')
def role_new():
    name  = request.form.get('name', '').strip().lower().replace(' ', '_')
    label = request.form.get('label', '').strip()
    color = request.form.get('color', 'secondary')
    if not name or not label:
        flash('Nome e etichetta obbligatori.', 'danger')
        return redirect(url_for('admin.roles'))
    if Role.query.filter_by(name=name).first():
        flash(f'Ruolo "{name}" già esistente.', 'warning')
        return redirect(url_for('admin.roles'))
    role = Role(name=name, label=label, color=color, is_system=False)
    perm_ids = request.form.getlist('perm_ids', type=int)
    role.permissions = Permission.query.filter(Permission.id.in_(perm_ids)).all() if perm_ids else []
    db.session.add(role)
    db.session.commit()
    flash(f'Ruolo "{label}" creato.', 'success')
    return redirect(url_for('admin.roles'))


@bp.route('/roles/<int:rid>/edit', methods=['POST'])
@require_permission('manage_roles')
def role_edit(rid):
    role = db.get_or_404(Role, rid)
    role.label = request.form.get('label', role.label).strip()
    role.color = request.form.get('color', role.color)
    perm_ids = request.form.getlist('perm_ids', type=int)
    role.permissions = Permission.query.filter(Permission.id.in_(perm_ids)).all() if perm_ids else []
    db.session.commit()
    flash(f'Ruolo "{role.label}" aggiornato.', 'success')
    return redirect(url_for('admin.roles'))


@bp.route('/roles/<int:rid>/delete', methods=['POST'])
@require_permission('manage_roles')
def role_delete(rid):
    role = db.get_or_404(Role, rid)
    if role.is_system:
        flash('I ruoli di sistema non possono essere eliminati.', 'warning')
        return redirect(url_for('admin.roles'))
    db.session.delete(role)
    db.session.commit()
    flash(f'Ruolo "{role.label}" eliminato.', 'info')
    return redirect(url_for('admin.roles'))


# ── Impostazioni (Telegram / Gmail) ───────────────────────────────────────────

@bp.route('/settings')
@require_permission('manage_settings')
def settings():
    keys = ['telegram_bot_token', 'telegram_chat_id', 'gmail_user', 'gmail_app_password']
    cfg  = {k: get_setting(k) for k in keys}
    return render_template('admin/settings.html', cfg=cfg)


@bp.route('/settings/save', methods=['POST'])
@require_permission('manage_settings')
def settings_save():
    keys = ['telegram_bot_token', 'telegram_chat_id', 'gmail_user', 'gmail_app_password']
    for k in keys:
        val = request.form.get(k, '').strip()
        s   = AppSetting.query.filter_by(key=k).first()
        if s:
            s.value = val
        else:
            db.session.add(AppSetting(key=k, value=val))
    db.session.commit()
    flash('Impostazioni salvate.', 'success')
    return redirect(url_for('admin.settings'))


@bp.route('/settings/test-telegram', methods=['POST'])
@require_permission('manage_settings')
def settings_test_telegram():
    ok, msg = send_telegram('✅ <b>Test QuickLunch</b>\nConnessione Telegram funzionante!')
    flash(f'Telegram: {msg}', 'success' if ok else 'danger')
    return redirect(url_for('admin.settings'))


@bp.route('/settings/test-email', methods=['POST'])
@require_permission('manage_settings')
def settings_test_email():
    from app.notifications import send_email
    dest = get_setting('gmail_user')
    ok, msg = send_email(dest, 'Test QuickLunch', '<b>Test email QuickLunch</b> — configurazione Gmail funzionante!')
    flash(f'Email: {msg}', 'success' if ok else 'danger')
    return redirect(url_for('admin.settings'))


@bp.route('/settings/broadcast-telegram', methods=['POST'])
@require_permission('send_notifications')
def broadcast_telegram():
    text = request.form.get('message', '').strip()
    if not text:
        flash('Messaggio vuoto.', 'warning')
        return redirect(url_for('admin.settings'))
    ok, msg = send_telegram(text)
    flash(f'Telegram: {msg}', 'success' if ok else 'danger')
    return redirect(url_for('admin.settings'))


@bp.route('/settings/broadcast-email', methods=['POST'])
@require_permission('send_notifications')
def broadcast_email():
    subject = request.form.get('subject', 'Comunicazione QuickLunch').strip()
    text    = request.form.get('message', '').strip()
    if not text:
        flash('Messaggio vuoto.', 'warning')
        return redirect(url_for('admin.settings'))
    html = f'<div style="font-family:sans-serif;max-width:520px;">{text}</div>'
    sent, failed, _ = send_email_to_all_users(subject, html)
    flash(f'Email inviate: {sent} ok, {failed} fallite.', 'success' if not failed else 'warning')
    return redirect(url_for('admin.settings'))


# ── Sondaggi (Polls) ──────────────────────────────────────────────────────────

@bp.route('/polls')
@require_permission('manage_polls')
def polls():
    from datetime import timedelta
    all_polls = Poll.query.order_by(Poll.poll_date.desc()).all()
    products  = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    tomorrow  = str(date.today() + timedelta(days=1))
    return render_template('admin/polls.html', polls=all_polls, products=products,
                           tomorrow=tomorrow)


@bp.route('/polls/new', methods=['POST'])
@require_permission('manage_polls')
def poll_new():
    from datetime import datetime as dt
    title     = request.form.get('title', '').strip()
    poll_date = request.form.get('poll_date', '').strip()
    if not title or not poll_date:
        flash('Titolo e data obbligatori.', 'danger')
        return redirect(url_for('admin.polls'))
    try:
        pd = dt.strptime(poll_date, '%Y-%m-%d').date()
    except ValueError:
        flash('Data non valida.', 'danger')
        return redirect(url_for('admin.polls'))

    poll = Poll(title=title, poll_date=pd, is_active=True)
    db.session.add(poll)
    db.session.flush()

    # Scelte da prodotti selezionati
    product_ids = request.form.getlist('product_ids', type=int)
    for pid in product_ids:
        p = Product.query.get(pid)
        if p:
            db.session.add(PollChoice(poll_id=poll.id, text=p.name, emoji='🍽️'))

    # Scelte custom
    for i in range(1, 8):
        ct = request.form.get(f'custom_text_{i}', '').strip()
        ce = request.form.get(f'custom_emoji_{i}', '🍽️').strip() or '🍽️'
        if ct:
            db.session.add(PollChoice(poll_id=poll.id, text=ct, emoji=ce))

    db.session.commit()
    flash(f'Sondaggio "{title}" creato con {len(product_ids)} scelte.', 'success')
    return redirect(url_for('admin.polls'))


@bp.route('/polls/<int:pid>/toggle', methods=['POST'])
@require_permission('manage_polls')
def poll_toggle(pid):
    poll = db.get_or_404(Poll, pid)
    poll.is_active = not poll.is_active
    db.session.commit()
    flash(f'Sondaggio {"attivato" if poll.is_active else "chiuso"}.', 'info')
    return redirect(url_for('admin.polls'))


@bp.route('/polls/<int:pid>/delete', methods=['POST'])
@require_permission('manage_polls')
def poll_delete(pid):
    poll = db.get_or_404(Poll, pid)
    db.session.delete(poll)
    db.session.commit()
    flash('Sondaggio eliminato.', 'info')
    return redirect(url_for('admin.polls'))


@bp.route('/polls/<int:pid>/notify-telegram', methods=['POST'])
@require_permission('send_notifications')
def poll_notify_telegram(pid):
    poll     = db.get_or_404(Poll, pid)
    base_url = request.host_url.rstrip('/')
    msg      = telegram_poll_message(poll, base_url)
    ok, info = send_telegram(msg)
    flash(f'Telegram: {info}', 'success' if ok else 'danger')
    return redirect(url_for('admin.polls'))


@bp.route('/polls/<int:pid>/notify-email', methods=['POST'])
@require_permission('send_notifications')
def poll_notify_email(pid):
    poll     = db.get_or_404(Poll, pid)
    base_url = request.host_url.rstrip('/')
    html     = email_poll_html(poll, base_url)
    subject  = f'📊 Vota: {poll.title}'
    sent, failed, _ = send_email_to_all_users(subject, html)
    flash(f'Email inviate: {sent} ok, {failed} fallite.', 'success' if not failed else 'warning')
    return redirect(url_for('admin.polls'))


# ── Tenant management (solo superadmin) ───────────────────────────────────────

def _superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return login_required(decorated)


@bp.route('/tenants')
@_superadmin_required
def tenants():
    all_tenants = Tenant.query.order_by(Tenant.name).all()
    # Per ogni tenant trova l'admin (is_admin=False, ruolo superadmin)
    sa_role = Role.query.filter_by(name='superadmin').first()
    tenant_admins = {}
    if sa_role:
        admins = User.query.filter(
            User.is_admin == False,
            User.roles.contains(sa_role)
        ).all()
        for u in admins:
            if u.tenant_id and u.tenant_id not in tenant_admins:
                tenant_admins[u.tenant_id] = u
    return render_template('admin/tenants.html', tenants=all_tenants,
                           tenant_admins=tenant_admins)


@bp.route('/tenants/new', methods=['POST'])
@_superadmin_required
def tenant_new():
    name          = request.form.get('name', '').strip()
    slug          = request.form.get('slug', '').strip().lower().replace(' ', '-')
    primary_color = request.form.get('primary_color', '#e94560').strip()
    logo_url      = request.form.get('logo_url', '').strip()
    if not name or not slug:
        flash('Nome e slug sono obbligatori.', 'danger')
        return redirect(url_for('admin.tenants'))
    if Tenant.query.filter_by(slug=slug).first():
        flash(f'Slug "{slug}" già in uso.', 'danger')
        return redirect(url_for('admin.tenants'))
    t = Tenant(name=name, slug=slug, primary_color=primary_color, logo_url=logo_url)
    db.session.add(t)
    db.session.commit()
    flash(f'Tenant "{name}" creato.', 'success')
    return redirect(url_for('admin.tenants'))


@bp.route('/tenants/<int:tid>/edit', methods=['POST'])
@_superadmin_required
def tenant_edit(tid):
    t             = db.get_or_404(Tenant, tid)
    t.name          = request.form.get('name', t.name).strip()
    t.primary_color = request.form.get('primary_color', t.primary_color).strip()
    t.logo_url      = request.form.get('logo_url', t.logo_url).strip()
    t.is_active     = request.form.get('is_active') == '1'
    db.session.commit()
    flash(f'Tenant "{t.name}" aggiornato.', 'success')
    return redirect(url_for('admin.tenants'))


@bp.route('/tenants/<int:tid>/delete', methods=['POST'])
@_superadmin_required
def tenant_delete(tid):
    t = db.get_or_404(Tenant, tid)
    users_count = User.query.filter_by(tenant_id=tid).count()
    if users_count:
        flash(f'Impossibile eliminare: ci sono {users_count} utenti associati.', 'danger')
        return redirect(url_for('admin.tenants'))
    db.session.delete(t)
    db.session.commit()
    flash('Tenant eliminato.', 'success')
    return redirect(url_for('admin.tenants'))


@bp.route('/seed-demo', methods=['POST'])
@_superadmin_required
def seed_demo():
    from app.demo_seed import reset_demo_data, seed_demo_data
    reset_demo_data()
    ok, msg = seed_demo_data()
    flash(msg, 'success' if ok else 'warning')
    return redirect(url_for('admin.tenants'))


@bp.route('/tenants/<int:tid>/create-admin', methods=['POST'])
@_superadmin_required
def tenant_create_admin(tid):
    import secrets
    t = db.get_or_404(Tenant, tid)

    # Controlla che non esista già un admin per questo tenant
    existing = User.query.filter_by(tenant_id=tid, is_admin=False)\
        .join(User.roles).filter(Role.name == 'superadmin').first()
    if existing:
        flash(f'Il tenant "{t.name}" ha già un admin: {existing.email}', 'warning')
        return redirect(url_for('admin.tenants'))

    email    = f'admin@{t.slug}.local'
    username = f'admin.{t.slug}'

    # Evita collisioni di username/email su DB condiviso
    if User.query.filter_by(email=email).first():
        flash(f'Email {email} già in uso. Rinomina il tenant o crea l\'admin manualmente.', 'danger')
        return redirect(url_for('admin.tenants'))

    password = secrets.token_urlsafe(12)
    sa_role  = Role.query.filter_by(name='superadmin').first()

    u = User(username=username, email=email,
             is_admin=False, tenant_id=tid,
             wallet_balance=0.0, loyalty_points=0)
    u.set_password(password)
    if sa_role:
        u.roles = [sa_role]
    db.session.add(u)
    db.session.commit()

    flash(f'Admin tenant "{t.name}" creato — '
          f'email: {email} | password: {password} '
          f'(copiala adesso, non verrà mostrata di nuovo)', 'success')
    return redirect(url_for('admin.tenants'))


# ── Magazzino materiali di consumo ────────────────────────────────────────────

@bp.route('/magazzino')
@require_permission('manage_stock')
def magazzino():
    tf = _tenant_filter()
    items = ConsumableItem.query.filter_by(**tf).order_by(ConsumableItem.name).all()
    alerts = [i for i in items if i.is_below_threshold]
    return render_template('admin/magazzino.html', items=items, alerts=alerts)


@bp.route('/magazzino/nuovo', methods=['GET', 'POST'])
@bp.route('/magazzino/<int:iid>/modifica', methods=['GET', 'POST'])
@require_permission('manage_stock')
def magazzino_edit(iid=None):
    tf = _tenant_filter()
    item = ConsumableItem.query.get_or_404(iid) if iid else None
    suppliers = Supplier.query.filter_by(**tf).order_by(Supplier.name).all()

    if request.method == 'POST':
        name          = request.form.get('name', '').strip()
        unit          = request.form.get('unit', 'pz').strip()
        quantity      = float(request.form.get('quantity', 0) or 0)
        min_threshold = float(request.form.get('min_threshold', 0) or 0)
        supplier_id   = request.form.get('supplier_id') or None
        if supplier_id:
            supplier_id = int(supplier_id)

        if not name:
            flash('Il nome è obbligatorio.', 'danger')
            return render_template('admin/magazzino_edit.html', item=item, suppliers=suppliers)

        if item is None:
            item = ConsumableItem(tenant_id=current_user.tenant_id if not current_user.is_admin else None)
            db.session.add(item)

        item.name          = name
        item.unit          = unit
        item.quantity      = quantity
        item.min_threshold = min_threshold
        item.supplier_id   = supplier_id

        # reset alert se la giacenza torna sopra soglia
        if not item.is_below_threshold:
            item.alert_active = False

        db.session.commit()
        flash(f'Materiale "{name}" salvato.', 'success')
        return redirect(url_for('admin.magazzino'))

    return render_template('admin/magazzino_edit.html', item=item, suppliers=suppliers)


@bp.route('/magazzino/<int:iid>/movimento', methods=['POST'])
@require_permission('manage_stock')
def magazzino_movimento(iid):
    item  = ConsumableItem.query.get_or_404(iid)
    delta = float(request.form.get('delta', 0) or 0)
    notes = request.form.get('notes', '').strip()

    if delta == 0:
        flash('Inserisci un valore diverso da zero.', 'warning')
        return redirect(url_for('admin.magazzino'))

    item.quantity = round(item.quantity + delta, 3)
    mv = ConsumableMovement(item_id=item.id, delta=delta,
                             notes=notes, user_id=current_user.id)
    db.session.add(mv)

    # gestione alert soglia
    if item.is_below_threshold and not item.alert_active:
        ok, msg = send_supplier_low_stock_alert(item)
        if ok:
            flash(f'⚠️ Soglia raggiunta per "{item.name}" — email inviata al fornitore.', 'warning')
        elif item.supplier and item.supplier.email:
            flash(f'⚠️ Soglia raggiunta per "{item.name}" — invio email fallito: {msg}', 'danger')
        else:
            flash(f'⚠️ Soglia raggiunta per "{item.name}" — nessun fornitore con email configurata.', 'warning')
        item.alert_active = True
    elif not item.is_below_threshold:
        item.alert_active = False

    db.session.commit()
    return redirect(url_for('admin.magazzino'))


@bp.route('/magazzino/<int:iid>/elimina', methods=['POST'])
@require_permission('manage_stock')
def magazzino_delete(iid):
    item = ConsumableItem.query.get_or_404(iid)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f'Materiale "{name}" eliminato.', 'success')
    return redirect(url_for('admin.magazzino'))


# ── Fornitori ─────────────────────────────────────────────────────────────────

@bp.route('/fornitori')
@require_permission('manage_stock')
def fornitori():
    tf = _tenant_filter()
    sups = Supplier.query.filter_by(**tf).order_by(Supplier.name).all()
    return render_template('admin/fornitori.html', suppliers=sups)


@bp.route('/fornitori/nuovo', methods=['GET', 'POST'])
@bp.route('/fornitori/<int:sid>/modifica', methods=['GET', 'POST'])
@require_permission('manage_stock')
def fornitore_edit(sid=None):
    sup = Supplier.query.get_or_404(sid) if sid else None

    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        notes = request.form.get('notes', '').strip()

        if not name:
            flash('Il nome è obbligatorio.', 'danger')
            return render_template('admin/fornitore_edit.html', supplier=sup)

        if sup is None:
            sup = Supplier(tenant_id=current_user.tenant_id if not current_user.is_admin else None)
            db.session.add(sup)

        sup.name  = name
        sup.email = email
        sup.phone = phone
        sup.notes = notes
        db.session.commit()
        flash(f'Fornitore "{name}" salvato.', 'success')
        return redirect(url_for('admin.fornitori'))

    return render_template('admin/fornitore_edit.html', supplier=sup)


@bp.route('/fornitori/<int:sid>/elimina', methods=['POST'])
@require_permission('manage_stock')
def fornitore_delete(sid):
    sup = Supplier.query.get_or_404(sid)
    name = sup.name
    # scollega gli articoli prima di eliminare
    for item in sup.items:
        item.supplier_id = None
    db.session.delete(sup)
    db.session.commit()
    flash(f'Fornitore "{name}" eliminato.', 'success')
    return redirect(url_for('admin.fornitori'))

# â”€â”€ Convenzioni aziendali â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@bp.route('/convenzioni')
@require_permission('manage_products')
def convenzioni():
    tf = _tenant_filter()
    corps = CorporateAccount.query.filter_by(**tf).order_by(CorporateAccount.name).all()
    today_meals = {
        m.corporate_id: m
        for m in DailyFixedMeal.query.filter_by(meal_date=date.today(), **tf).all()
    }
    return render_template('admin/convenzioni.html', corps=corps, today_meals=today_meals)


@bp.route('/convenzioni/nuovo', methods=['GET', 'POST'])
@bp.route('/convenzioni/<int:cid>/modifica', methods=['GET', 'POST'])
@require_permission('manage_products')
def convenzione_edit(cid=None):
    tf = _tenant_filter()
    corp = CorporateAccount.query.get_or_404(cid) if cid else None
    all_users = User.query.filter_by(is_admin=False, **tf).order_by(User.username).all()

    if request.method == 'POST':
        name             = request.form.get('name', '').strip()
        contact_email    = request.form.get('contact_email', '').strip()
        daily_price      = float(request.form.get('daily_price', 7.0) or 7.0)
        max_daily_covers = int(request.form.get('max_daily_covers', 60) or 60)
        notes            = request.form.get('notes', '').strip()
        member_ids       = set(int(x) for x in request.form.getlist('member_ids') if x)

        if not name:
            flash('Il nome Ã¨ obbligatorio.', 'danger')
            return render_template('admin/convenzione_edit.html', corp=corp, all_users=all_users)

        if corp is None:
            corp = CorporateAccount(
                tenant_id=current_user.tenant_id if not current_user.is_admin else None)
            db.session.add(corp)

        corp.name             = name
        corp.contact_email    = contact_email
        corp.daily_price      = daily_price
        corp.max_daily_covers = max_daily_covers
        corp.notes            = notes
        corp.is_active        = 'is_active' in request.form
        db.session.flush()

        existing = {m.user_id: m for m in corp.memberships}
        for uid in member_ids:
            if uid not in existing:
                db.session.add(CorporateMembership(user_id=uid, corporate_id=corp.id))
            else:
                existing[uid].is_active = True
        for uid, m in existing.items():
            if uid not in member_ids:
                m.is_active = False

        db.session.commit()
        flash(f'Azienda "{name}" salvata.', 'success')
        return redirect(url_for('admin.convenzioni'))

    return render_template('admin/convenzione_edit.html', corp=corp, all_users=all_users)


@bp.route('/convenzioni/<int:cid>/elimina', methods=['POST'])
@require_permission('manage_products')
def convenzione_delete(cid):
    corp = CorporateAccount.query.get_or_404(cid)
    name = corp.name
    db.session.delete(corp)
    db.session.commit()
    flash(f'Azienda "{name}" eliminata.', 'success')
    return redirect(url_for('admin.convenzioni'))


@bp.route('/convenzioni/<int:cid>/pasto', methods=['GET', 'POST'])
@require_permission('manage_products')
def convenzione_pasto(cid):
    corp = CorporateAccount.query.get_or_404(cid)
    today = date.today()

    # data selezionata (default oggi); GET ?d=YYYY-MM-DD per navigare
    try:
        sel_date = date.fromisoformat(request.args.get('d', '')) if request.args.get('d') else today
    except ValueError:
        sel_date = today
    prev_date = sel_date - timedelta(days=1)
    next_date = sel_date + timedelta(days=1)

    meal = DailyFixedMeal.query.filter_by(corporate_id=cid, meal_date=sel_date).first()

    if request.method == 'POST':
        action = request.form.get('action', 'save')
        if action == 'delete' and meal:
            db.session.delete(meal)
            db.session.commit()
            flash('Pasto eliminato.', 'info')
            return redirect(url_for('admin.convenzione_pasto', cid=cid))

        name        = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        allergens   = ','.join(request.form.getlist('allergens'))
        primo       = request.form.get('primo',   '').strip()
        secondo     = request.form.get('secondo',  '').strip()
        contorno    = request.form.get('contorno', '').strip()
        bevanda     = request.form.get('bevanda',  '').strip()
        caffe       = request.form.get('caffe',    '').strip()
        price       = float(request.form.get('price', corp.daily_price) or corp.daily_price)
        max_book    = int(request.form.get('max_bookings', corp.max_daily_covers) or corp.max_daily_covers)

        if not name:
            flash('Il nome del pasto è obbligatorio.', 'danger')
            return render_template('admin/convenzione_pasto.html',
                                   corp=corp, meal=meal, sel_date=today, today=today,
                                   prev_date=prev_date, next_date=next_date,
                                   bookings=[], allergens_list=ALLERGENS)

        if meal is None:
            meal = DailyFixedMeal(
                corporate_id=cid, meal_date=today,
                tenant_id=current_user.tenant_id if not current_user.is_admin else None)
            db.session.add(meal)

        meal.name         = name
        meal.description  = description
        meal.allergens    = allergens
        meal.primo        = primo
        meal.secondo      = secondo
        meal.contorno     = contorno
        meal.bevanda      = bevanda
        meal.caffe        = caffe
        meal.price        = price
        meal.max_bookings = max_book
        meal.is_active    = 'is_active' in request.form
        db.session.commit()
        flash(f'Pasto "{name}" salvato.', 'success')
        return redirect(url_for('admin.convenzione_pasto', cid=cid))

    bookings = CorporateMealBooking.query.filter_by(meal_id=meal.id).all() if meal else []
    return render_template('admin/convenzione_pasto.html',
                           corp=corp, meal=meal, sel_date=sel_date, today=today,
                           prev_date=prev_date, next_date=next_date,
                           bookings=bookings, allergens_list=ALLERGENS)


@bp.route('/convenzioni/<int:cid>/pasto/<int:bid>/consuma', methods=['POST'])
@require_permission('manage_products')
def convenzione_consuma(cid, bid):
    booking = CorporateMealBooking.query.get_or_404(bid)
    booking.status = 'consumed'
    db.session.commit()
    d = request.args.get('d', '')
    flash(f'Pasto di {booking.user.username} segnato come consumato.', 'success')
    return redirect(url_for('admin.convenzione_pasto', cid=cid, d=d or None))


# ── Manutenzione ──────────────────────────────────────────────────────────────

@bp.route('/maintenance', methods=['GET', 'POST'])
@login_required
def maintenance():
    if not current_user.is_admin:
        abort(403)

    if request.method == 'POST':
        op = request.form.get('operation', '')

        if op == 'clear_orders':
            db.session.execute(db.text('UPDATE transactions SET order_id = NULL WHERE order_id IS NOT NULL'))
            CustomOrderItemIngredient.query.delete(synchronize_session=False)
            CustomOrderItem.query.delete(synchronize_session=False)
            OrderItem.query.delete(synchronize_session=False)
            CorporateMealBooking.query.delete(synchronize_session=False)
            Order.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Tutti gli ordini eliminati.', 'success')

        elif op == 'clear_reservations':
            TableReservation.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Tutte le prenotazioni tavoli eliminate.', 'success')

        elif op == 'clear_transactions':
            Transaction.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Tutte le transazioni eliminate.', 'success')

        elif op == 'clear_polls':
            PollVote.query.delete(synchronize_session=False)
            PollChoice.query.delete(synchronize_session=False)
            Poll.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Tutti i sondaggi eliminati.', 'success')

        elif op == 'clear_stock':
            DailyStock.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Stock giornaliero eliminato.', 'success')

        elif op == 'clear_movements':
            ConsumableMovement.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Movimenti magazzino eliminati.', 'success')

        elif op == 'clear_clients':
            client_ids = [u.id for u in User.query.filter_by(is_client=True).all()]
            if client_ids:
                # null nullable FK: consumable_movements.user_id
                db.session.execute(
                    db.text('UPDATE consumable_movements SET user_id = NULL WHERE user_id = ANY(:ids)' if db.engine.url.drivername.startswith('postgresql')
                            else 'UPDATE consumable_movements SET user_id = NULL WHERE user_id IN ({})'.format(','.join(str(i) for i in client_ids))),
                    {'ids': client_ids} if db.engine.url.drivername.startswith('postgresql') else {}
                )
                # child tables of orders
                order_ids = [o.id for o in Order.query.filter(Order.user_id.in_(client_ids)).all()]
                if order_ids:
                    db.session.execute(
                        db.text('UPDATE transactions SET order_id = NULL WHERE order_id = ANY(:ids)' if db.engine.url.drivername.startswith('postgresql')
                                else 'UPDATE transactions SET order_id = NULL WHERE order_id IN ({})'.format(','.join(str(i) for i in order_ids))),
                        {'ids': order_ids} if db.engine.url.drivername.startswith('postgresql') else {}
                    )
                    CustomOrderItemIngredient.query.filter(
                        CustomOrderItemIngredient.custom_item_id.in_(
                            db.session.query(CustomOrderItem.id).filter(CustomOrderItem.order_id.in_(order_ids))
                        )
                    ).delete(synchronize_session=False)
                    CustomOrderItem.query.filter(CustomOrderItem.order_id.in_(order_ids)).delete(synchronize_session=False)
                    OrderItem.query.filter(OrderItem.order_id.in_(order_ids)).delete(synchronize_session=False)
                    CorporateMealBooking.query.filter(CorporateMealBooking.order_id.in_(order_ids)).delete(synchronize_session=False)
                    Order.query.filter(Order.id.in_(order_ids)).delete(synchronize_session=False)
                # other tables directly linked to client users
                PollVote.query.filter(PollVote.user_id.in_(client_ids)).delete(synchronize_session=False)
                CorporateMealBooking.query.filter(CorporateMealBooking.user_id.in_(client_ids)).delete(synchronize_session=False)
                CorporateMembership.query.filter(CorporateMembership.user_id.in_(client_ids)).delete(synchronize_session=False)
                TableReservation.query.filter(TableReservation.user_id.in_(client_ids)).delete(synchronize_session=False)
                Transaction.query.filter(Transaction.user_id.in_(client_ids)).delete(synchronize_session=False)
                User.query.filter_by(is_client=True).delete(synchronize_session=False)
            db.session.commit()
            flash('Tutti i clienti e i loro dati eliminati.', 'success')

        elif op == 'reset_all':
            # step 1: null nullable FKs
            db.session.execute(db.text('UPDATE transactions SET order_id = NULL WHERE order_id IS NOT NULL'))
            db.session.execute(db.text('UPDATE consumable_movements SET user_id = NULL WHERE user_id IS NOT NULL'))
            # step 2: leaf tables (no children)
            PollVote.query.delete(synchronize_session=False)
            CorporateMealBooking.query.delete(synchronize_session=False)
            CorporateMembership.query.delete(synchronize_session=False)
            CustomOrderItemIngredient.query.delete(synchronize_session=False)
            CustomOrderItem.query.delete(synchronize_session=False)
            OrderItem.query.delete(synchronize_session=False)
            # step 3: parent tables
            Order.query.delete(synchronize_session=False)
            TableReservation.query.delete(synchronize_session=False)
            Transaction.query.delete(synchronize_session=False)
            PollChoice.query.delete(synchronize_session=False)
            Poll.query.delete(synchronize_session=False)
            DailyStock.query.delete(synchronize_session=False)
            ConsumableMovement.query.delete(synchronize_session=False)
            User.query.filter_by(is_client=True).delete(synchronize_session=False)
            db.session.commit()
            flash('Reset completo eseguito.', 'success')

        elif op == 'reset_admin':
            import re as _re
            email    = request.form.get('admin_email', '').strip().lower()
            password = request.form.get('admin_password', '').strip()
            username = request.form.get('admin_username', 'admin').strip()
            if not email or '@' not in email or len(password) < 6:
                flash('Email valida e password (min 6 caratteri) obbligatorie.', 'danger')
            else:
                user = User.query.filter_by(email=email).first()
                if user:
                    user.is_admin  = True
                    user.is_active = True
                    user.set_password(password)
                    db.session.commit()
                    flash(f'Admin "{email}" aggiornato.', 'success')
                else:
                    base  = _re.sub(r'[^a-z0-9]', '.', username.lower()).strip('.') or 'admin'
                    uname, n = base[:30], 1
                    while User.query.filter_by(username=uname).first():
                        uname = f'{base[:28]}{n}'; n += 1
                    new_admin = User(username=uname, email=email,
                                     is_admin=True, is_active=True)
                    new_admin.set_password(password)
                    db.session.add(new_admin)
                    db.session.commit()
                    flash(f'Admin "{email}" creato con username "{uname}".', 'success')

        return redirect(url_for('admin.maintenance'))

    stats = {
        'orders':       Order.query.count(),
        'reservations': TableReservation.query.count(),
        'transactions': Transaction.query.count(),
        'polls':        Poll.query.count(),
        'stock':        DailyStock.query.count(),
        'movements':    ConsumableMovement.query.count(),
        'clients':      User.query.filter_by(is_client=True).count(),
        'admins':       User.query.filter_by(is_admin=True).all(),
    }
    return render_template('admin/maintenance.html', stats=stats)


@bp.route('/convenzioni/<int:cid>/presenze')
@require_permission('manage_products')
def convenzione_presenze(cid):
    from sqlalchemy import extract
    corp = CorporateAccount.query.get_or_404(cid)

    try:
        mese_str = request.args.get('mese', '')
        if mese_str:
            anno, mese = int(mese_str[:4]), int(mese_str[5:7])
        else:
            anno, mese = date.today().year, date.today().month
    except (ValueError, IndexError):
        anno, mese = date.today().year, date.today().month

    meals = (DailyFixedMeal.query
             .filter_by(corporate_id=cid)
             .filter(extract('year', DailyFixedMeal.meal_date) == anno)
             .filter(extract('month', DailyFixedMeal.meal_date) == mese)
             .order_by(DailyFixedMeal.meal_date.desc())
             .all())

    days = []
    for m in meals:
        consumed  = [b for b in m.bookings if b.status == 'consumed']
        booked    = [b for b in m.bookings if b.status == 'booked']
        cancelled = [b for b in m.bookings if b.status == 'cancelled']
        days.append({'meal': m, 'consumed': consumed,
                     'booked': booked, 'cancelled': cancelled})

    if mese == 1:
        prev_anno, prev_mese = anno - 1, 12
    else:
        prev_anno, prev_mese = anno, mese - 1
    if mese == 12:
        next_anno, next_mese = anno + 1, 1
    else:
        next_anno, next_mese = anno, mese + 1

    MESI = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
            'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']

    return render_template('admin/convenzione_presenze.html',
                           corp=corp, days=days, anno=anno, mese=mese,
                           nome_mese=MESI[mese],
                           prev=f'{prev_anno}-{prev_mese:02d}',
                           nxt=f'{next_anno}-{next_mese:02d}')


# â”€â”€ Slot durata tavolo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@bp.route('/slots/<int:sid>/durata', methods=['POST'])
@require_permission('manage_slots')
def slot_durata(sid):
    slot = TimeSlot.query.get_or_404(sid)
    slot.seat_duration_minutes = int(request.form.get('seat_duration_minutes', 0) or 0)
    db.session.commit()
    flash(f'Durata slot {slot.time_str} aggiornata a {slot.seat_duration_minutes} min.', 'success')
    return redirect(url_for('admin.tavoli', tab='slot'))


# â”€â”€ Check-in tavolo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@bp.route('/prenotazioni/<int:rid>/checkin', methods=['POST'])
@require_permission('manage_reservations_admin')
def reservation_checkin(rid):
    from datetime import datetime as _dt
    res = TableReservation.query.get_or_404(rid)
    res.checkin_at       = _dt.utcnow()
    res.table_alert_sent = False
    db.session.commit()
    flash(f'Check-in tavolo {res.table.number} — {res.user.username}.', 'success')
    return redirect(url_for('admin.tavoli'))


@bp.route('/tavoli/ping-alerts')
@staff_required
def tavoli_ping_alerts():
    import json
    from app.notifications import send_telegram
    WARN_MINUTES = 10
    alerts = []
    active = TableReservation.query\
        .filter(TableReservation.checkin_at.isnot(None))\
        .filter(TableReservation.status == 'confirmed')\
        .filter(TableReservation.table_alert_sent == False)\
        .all()
    for res in active:
        mins_left = res.minutes_remaining
        if mins_left is None:
            continue
        if mins_left <= WARN_MINUTES:
            msg = (f'â° Tavolo <b>{res.table.number}</b> â€” <b>{res.user.username}</b>\n'
                   f'Tempo rimanente: <b>{int(mins_left)} min</b>. Prego liberare il tavolo.')
            send_telegram(msg)
            res.table_alert_sent = True
            alerts.append({'table': res.table.number, 'user': res.user.username,
                           'mins_left': round(mins_left, 1)})
    if alerts:
        db.session.commit()
    return json.dumps({'alerts': alerts}), 200, {'Content-Type': 'application/json'}

