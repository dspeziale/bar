import secrets as _secrets
from datetime import date, timedelta, datetime as _dt
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, abort, jsonify
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
                        DailyFixedMeal, CorporateMealBooking, MealConfiguration,
                        Transaction, CustomOrderItem, CustomOrderItemIngredient,
                        BancoItem, BancoSession,
                        ALLERGENS)
from app.notifications import (send_telegram, send_telegram_to_user,
                                send_email_to_all_users, send_supplier_low_stock_alert,
                                telegram_poll_message, email_poll_html, get_setting)


# ── Tenant scope helpers ──────────────────────────────────────────────────────

def _tenant_filter():
    """Per query filter_by: vuoto per il super admin globale, tenant_id per gli altri."""
    if current_user.is_admin:
        return {}
    return {'tenant_id': current_user.tenant_id}


def _active_tenant_id():
    """Ritorna il tenant_id da usare per categorie/prodotti.
    Super admin (tenant_id=None) → tenant 'default'.
    """
    if current_user.tenant_id:
        return current_user.tenant_id
    default_t = Tenant.query.filter_by(slug='default').first()
    return default_t.id if default_t else None


# ── User cascade delete ───────────────────────────────────────────────────────

def _delete_user_cascade(uid):
    """Elimina un utente e tutti i record collegati rispettando i vincoli FK NOT NULL."""
    # ordini: prima i sotto-record, poi gli ordini stessi
    order_ids   = db.session.query(Order.id).filter_by(user_id=uid).subquery()
    coi_ids     = db.session.query(CustomOrderItem.id).filter(
                      CustomOrderItem.order_id.in_(order_ids)).subquery()

    CustomOrderItemIngredient.query.filter(
        CustomOrderItemIngredient.custom_item_id.in_(coi_ids)
    ).delete(synchronize_session=False)

    CustomOrderItem.query.filter(
        CustomOrderItem.order_id.in_(order_ids)
    ).delete(synchronize_session=False)

    OrderItem.query.filter(
        OrderItem.order_id.in_(order_ids)
    ).delete(synchronize_session=False)

    # transazioni che referenziano ordini di questo utente: annulla il FK nullable
    Transaction.query.filter(
        Transaction.order_id.in_(order_ids)
    ).update({'order_id': None}, synchronize_session=False)

    Order.query.filter_by(user_id=uid).delete(synchronize_session=False)

    # tutti gli altri record collegati direttamente all'utente
    Transaction.query.filter_by(user_id=uid).delete(synchronize_session=False)
    TableReservation.query.filter_by(user_id=uid).delete(synchronize_session=False)
    PollVote.query.filter_by(user_id=uid).delete(synchronize_session=False)
    CorporateMealBooking.query.filter_by(user_id=uid).delete(synchronize_session=False)
    CorporateMembership.query.filter_by(user_id=uid).delete(synchronize_session=False)

    user = db.session.get(User, uid)
    if user:
        db.session.delete(user)


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
    clients_count = User.query.filter_by(is_client=True, is_active=True, **_tenant_filter()).count()
    staff_count   = User.query.filter_by(is_client=False, is_admin=False, **_tenant_filter()).count()
    products_count = Product.query.filter_by(is_active=True).count()
    res_today = TableReservation.query.filter_by(reservation_date=today)\
        .filter(TableReservation.status != 'cancelled').count()
    stock_alerts = [(p, p.available_today())
                    for p in Product.query.filter_by(is_active=True).all()
                    if p.available_today() <= 3]
    wallet_users = User.query.filter_by(is_client=True, is_active=True, **_tenant_filter()).all()
    total_wallet = round(sum(u.wallet_balance for u in wallet_users), 2)
    consumable_alerts = ConsumableItem.query.filter_by(**_tenant_filter())\
        .filter(ConsumableItem.alert_active == True).count()
    # Panoramica pasti aziendali — tutte le opzioni di oggi
    corp_meals_today = DailyFixedMeal.query.filter_by(meal_date=today)\
        .order_by(DailyFixedMeal.corporate_id, DailyFixedMeal.name).all()

    # Clienti in attesa di attivazione
    pending_clients = User.query.filter_by(
        is_client=True, is_active=False, **_tenant_filter()
    ).count()

    # Sondaggio attivo più recente + andamento voti
    active_poll = Poll.query.filter_by(is_active=True)\
        .order_by(Poll.poll_date.desc()).first()
    poll_stats = None
    if active_poll:
        total_votes = active_poll.total_votes()
        poll_stats = {
            'poll': active_poll,
            'total': total_votes,
            'choices': [
                {'text': c.text, 'emoji': c.emoji,
                 'count': c.vote_count,
                 'pct': round(c.vote_count / total_votes * 100, 1) if total_votes else 0}
                for c in sorted(active_poll.choices, key=lambda x: x.vote_count, reverse=True)
            ],
        }

    today_meal_booking    = None
    meal_booking_reminder = False
    membership = getattr(current_user, 'corporate_membership', None)
    if membership and membership.is_active:
        today_meals_corp = DailyFixedMeal.query.filter_by(
            corporate_id=membership.corporate_id,
            meal_date=today,
            is_active=True,
        ).all()
        if today_meals_corp:
            meal_ids = [m.id for m in today_meals_corp]
            today_meal_booking = CorporateMealBooking.query.filter(
                CorporateMealBooking.user_id == current_user.id,
                CorporateMealBooking.meal_id.in_(meal_ids),
                CorporateMealBooking.status != 'cancelled',
            ).first()
            if not today_meal_booking:
                meal_booking_reminder = True

    return render_template('admin/dashboard.html',
                           orders_today=orders_today,
                           pending=[o for o in orders_today if o.status in ('pending', 'confirmed')],
                           revenue_today=revenue_today,
                           clients_count=clients_count,
                           staff_count=staff_count,
                           products_count=products_count,
                           res_today=res_today,
                           stock_alerts=stock_alerts,
                           total_wallet=total_wallet,
                           consumable_alerts=consumable_alerts,
                           today_meal_booking=today_meal_booking,
                           meal_booking_reminder=meal_booking_reminder,
                           corp_meals_today=corp_meals_today,
                           poll_stats=poll_stats,
                           pending_clients=pending_clients)


# ── Prodotti ──────────────────────────────────────────────────────────────────

@bp.route('/products')
@require_permission('manage_products')
def products():
    tid = _active_tenant_id()
    return render_template('admin/products.html',
                           products=Product.query.filter_by(tenant_id=tid).order_by(Product.category_id, Product.name).all(),
                           categories=Category.query.filter_by(tenant_id=tid).order_by(Category.name).all(),
                           allergens=ALLERGENS)


@bp.route('/products/dt')
@require_permission('manage_products')
def products_dt():
    tid    = _active_tenant_id()
    draw   = request.args.get('draw', 1, type=int)
    start  = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search = (request.args.get('search[value]') or '').strip()
    col    = request.args.get('order[0][column]', 0, type=int)
    dirn   = request.args.get('order[0][dir]', 'asc')

    q = Product.query.join(Category).filter(Product.tenant_id == tid)
    total = q.count()

    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(
            Product.name.ilike(like),
            Product.description.ilike(like),
            Category.name.ilike(like),
        ))
    filtered = q.count()

    col_map = {0: Product.name, 1: Category.name, 2: Product.price,
               3: Product.daily_quantity, 5: Product.is_active}
    order_expr = col_map.get(col, Product.name)
    q = q.order_by(order_expr.desc() if dirn == 'desc' else order_expr.asc())

    data = []
    for p in q.offset(start).limit(length).all():
        data.append({
            'id':             p.id,
            'name':           p.name,
            'description':    p.description or '',
            'category_id':    p.category_id,
            'category_name':  p.category.name,
            'category_color': p.category.color,
            'category_icon':  p.category.icon,
            'price':          p.price,
            'daily_quantity': p.daily_quantity,
            'allergens':      p.allergens or '',
            'allergen_list':  [[k, l, i] for k, l, i in p.allergen_list],
            'is_active':      p.is_active,
        })
    return jsonify(draw=draw, recordsTotal=total, recordsFiltered=filtered, data=data)


@bp.route('/products/new', methods=['POST'])
@require_permission('manage_products')
def product_new():
    name = request.form.get('name', '').strip()
    price = request.form.get('price', type=float)
    category_id = request.form.get('category_id', type=int)
    daily_quantity = request.form.get('daily_quantity', type=int, default=20)
    description = request.form.get('description', '').strip()
    allergens = ','.join(request.form.getlist('allergens'))
    if not name or not price or price <= 0 or not category_id:
        flash('Compila tutti i campi obbligatori.', 'danger')
        return redirect(url_for('admin.products'))
    db.session.add(Product(name=name, description=description, price=price,
                           category_id=category_id, daily_quantity=daily_quantity,
                           allergens=allergens))
    db.session.commit()
    flash(f'Prodotto "{name}" aggiunto.', 'success')
    return redirect(url_for('admin.products'))


@bp.route('/products/<int:pid>/edit', methods=['POST'])
@require_permission('manage_products')
def product_edit(pid):
    p = db.get_or_404(Product, pid)
    p.name         = request.form.get('name', p.name).strip()
    p.description  = request.form.get('description', p.description).strip()
    p.price        = request.form.get('price', type=float) or p.price
    p.category_id  = request.form.get('category_id', type=int) or p.category_id
    p.daily_quantity = request.form.get('daily_quantity', type=int) or p.daily_quantity
    p.is_active    = 'is_active' in request.form
    p.allergens    = ','.join(request.form.getlist('allergens'))
    db.session.commit()
    flash(f'Prodotto "{p.name}" aggiornato.', 'success')
    return redirect(url_for('admin.products'))


@bp.route('/products/<int:pid>/delete', methods=['POST'])
@require_permission('manage_products')
def product_delete(pid):
    p = db.get_or_404(Product, pid)
    DailyStock.query.filter_by(product_id=pid).delete(synchronize_session=False)
    OrderItem.query.filter_by(product_id=pid).delete(synchronize_session=False)
    name = p.name
    db.session.delete(p)
    db.session.commit()
    flash(f'Prodotto "{name}" eliminato.', 'success')
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
    if new_status == 'preparing':
        has_grill = any(ci.grill_requested for ci in order.custom_items)
        if has_grill:
            send_telegram(
                f'🔥 <b>PANINO SULLA PIASTRA</b>\n'
                f'Ordine <b>{order_ref}</b> — {order.user.full_name}\n'
                + '\n'.join(
                    f'  • {ci.label}'
                    for ci in order.custom_items if ci.grill_requested
                )
            )
        else:
            send_telegram(
                f'👨‍🍳 Ordine <b>{order_ref}</b> in preparazione\n'
                f'👤 {order.user.full_name}'
            )
        send_telegram_to_user(
            order.user,
            f'👨‍🍳 Il tuo ordine <b>{order_ref}</b> è <b>in preparazione</b>!\n'
            f'Ti avvisiamo quando è pronto.'
        )
    elif new_status == 'ready':
        send_telegram(
            f'🔔 Ordine <b>{order_ref}</b> PRONTO — {order.user.full_name}'
        )
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

@bp.route('/clients/registration-qr')
@require_permission('manage_clients')
def clients_registration_qr():
    """Pagina stampabile con QR code per la registrazione clienti."""
    from flask import request as _req
    join_url = _req.host_url.rstrip('/') + url_for('auth.join')
    tenant = Tenant.query.filter_by(slug='default').first()
    return render_template('admin/registration_qr.html',
                           join_url=join_url, tenant=tenant)


@bp.route('/clients')
@require_permission('manage_clients')
def clients():
    all_clients = User.query.filter_by(is_client=True,
                                       **_tenant_filter()).order_by(User.last_name, User.first_name).all()
    corporates  = CorporateAccount.query.filter_by(**_tenant_filter()).order_by(CorporateAccount.name).all()
    return render_template('admin/clients.html', clients=all_clients, corporates=corporates)


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
    activating = not u.is_active
    u.is_active = activating
    if activating:
        corporate_id = request.form.get('corporate_id', '').strip()
        if corporate_id:
            try:
                cid = int(corporate_id)
                mem = CorporateMembership.query.filter_by(user_id=u.id).first()
                if mem:
                    mem.corporate_id = cid
                    mem.is_active    = True
                else:
                    db.session.add(CorporateMembership(user_id=u.id, corporate_id=cid, is_active=True))
            except (ValueError, TypeError):
                pass
    db.session.commit()
    if activating:
        send_telegram_to_user(u,
            '✅ Il tuo account è stato attivato!\n'
            'Puoi ora accedere al servizio.')
    else:
        send_telegram_to_user(u,
            '🔒 Il tuo account è stato sospeso.\n'
            'Contatta l\'amministratore per informazioni.')
    flash(f'Cliente {u.full_name} {"attivato" if activating else "sospeso"}.', 'info')
    return redirect(url_for('admin.clients'))


@bp.route('/clients/<int:uid>/delete', methods=['POST'])
@require_permission('manage_clients')
def client_delete(uid):
    u = db.get_or_404(User, uid)
    if not u.is_client:
        abort(404)
    name = u.full_name
    _delete_user_cascade(uid)
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
    send_telegram_to_user(u,
        f'💳 Ricarica wallet: <b>+{amount:.2f}€</b>\n'
        f'💰 Saldo attuale: <b>{u.wallet_balance:.2f}€</b>\n'
        f'📝 {note}'
    )
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
    if user.is_active:
        send_telegram_to_user(user,
            f'\U00002705 Il tuo account è stato attivato!\n'
            f'Puoi ora accedere al servizio.')
    flash(f'Utente {user.username} {"attivato" if user.is_active else "sospeso"}.', 'info')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:uid>/delete', methods=['POST'])
@require_permission('manage_users')
def user_delete(uid):
    user = db.get_or_404(User, uid)
    if user.is_admin:
        flash('Non puoi eliminare un amministratore.', 'danger')
        return redirect(url_for('admin.users'))
    name = user.username
    _delete_user_cascade(uid)
    db.session.commit()
    flash(f'Utente "{name}" eliminato.', 'info')
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
    tid = _active_tenant_id()
    cats = Category.query.filter_by(tenant_id=tid).order_by(Category.name).all()
    return render_template('admin/categories.html', categories=cats)


@bp.route('/categories/new', methods=['POST'])
@require_permission('manage_categories')
def category_new():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Nome obbligatorio.', 'danger')
        return redirect(url_for('admin.categories'))
    tid = _active_tenant_id()
    if Category.query.filter_by(name=name, tenant_id=tid).first():
        flash('Categoria già esistente.', 'warning')
        return redirect(url_for('admin.categories'))
    db.session.add(Category(name=name,
                            icon=request.form.get('icon', 'fa-utensils'),
                            color=request.form.get('color', 'secondary'),
                            tenant_id=tid))
    db.session.commit()
    flash(f'Categoria "{name}" creata.', 'success')
    return redirect(url_for('admin.categories'))


@bp.route('/categories/<int:cid>/edit', methods=['POST'])
@require_permission('manage_categories')
def category_edit(cid):
    cat = Category.query.get_or_404(cid)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Nome obbligatorio.', 'danger')
        return redirect(url_for('admin.categories'))
    existing = Category.query.filter_by(name=name, tenant_id=cat.tenant_id).first()
    if existing and existing.id != cid:
        flash(f'Esiste già una categoria con il nome "{name}".', 'warning')
        return redirect(url_for('admin.categories'))
    cat.name  = name
    cat.icon  = request.form.get('icon', cat.icon)
    cat.color = request.form.get('color', cat.color)
    db.session.commit()
    flash(f'Categoria "{name}" aggiornata.', 'success')
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


@bp.route('/slots/new', methods=['POST'])
@require_permission('manage_slots')
def slot_new():
    time_str = (request.form.get('time_str') or '').strip()
    max_orders = request.form.get('max_orders', 20, type=int)
    if not time_str:
        flash('Orario obbligatorio.', 'danger')
        return redirect(url_for('admin.tavoli', tab='slot'))
    import re
    if not re.match(r'^\d{2}:\d{2}$', time_str):
        flash('Formato orario non valido (HH:MM).', 'danger')
        return redirect(url_for('admin.tavoli', tab='slot'))
    tid = _active_tenant_id()
    if TimeSlot.query.filter_by(time_str=time_str, tenant_id=tid).first():
        flash(f'Lo slot {time_str} esiste già.', 'warning')
        return redirect(url_for('admin.tavoli', tab='slot'))
    db.session.add(TimeSlot(time_str=time_str, max_orders=max(1, max_orders), tenant_id=tid))
    db.session.commit()
    flash(f'Slot {time_str} creato.', 'success')
    return redirect(url_for('admin.tavoli', tab='slot'))


@bp.route('/slots/<int:sid>/delete', methods=['POST'])
@require_permission('manage_slots')
def slot_delete(sid):
    slot = db.get_or_404(TimeSlot, sid)
    if slot.orders:
        flash(f'Impossibile eliminare lo slot {slot.time_str}: ha ordini associati.', 'danger')
        return redirect(url_for('admin.tavoli', tab='slot'))
    db.session.delete(slot)
    db.session.commit()
    flash(f'Slot {slot.time_str} eliminato.', 'info')
    return redirect(url_for('admin.tavoli', tab='slot'))


# ── Banco POS ─────────────────────────────────────────────────────────────────

@bp.route('/banco')
@staff_required
def banco():
    tid   = _active_tenant_id()
    items = BancoItem.query.filter_by(is_active=True, tenant_id=tid)\
                    .order_by(BancoItem.sort_order, BancoItem.name).all()
    users = User.query.filter_by(is_admin=False, is_staff=False)\
                      .order_by(User.username).all()
    import json
    items_json = json.dumps([
        {'id': i.id, 'name': i.name, 'price': i.price,
         'icon': i.icon, 'color': i.color}
        for i in items
    ])
    return render_template('admin/banco_pos.html',
                           items=items, users=users, items_json=items_json)


@bp.route('/banco/session', methods=['POST'])
@staff_required
def banco_session_new():
    import json
    cart_json = request.form.get('cart_json', '[]')
    try:
        cart = json.loads(cart_json)
    except Exception:
        cart = []
    if not cart:
        return jsonify({'error': 'Nessun articolo'}), 400
    total = round(sum(i['price'] * i['qty'] for i in cart), 2)
    token = _secrets.token_hex(16)
    now   = _dt.utcnow()
    sess  = BancoSession(
        token=token, staff_id=current_user.id,
        items_json=cart_json, total=total,
        status='pending',
        created_at=now, expires_at=now + timedelta(minutes=10),
        tenant_id=_active_tenant_id(),
    )
    db.session.add(sess)
    db.session.commit()
    pay_url = request.host_url.rstrip('/') + '/banco/pay/' + token
    return jsonify({'token': token, 'pay_url': pay_url, 'total': total, 'expires_in': 600})


@bp.route('/banco/session/<token>/status')
@staff_required
def banco_session_status(token):
    sess = BancoSession.query.filter_by(token=token).first_or_404()
    if sess.status == 'pending' and _dt.utcnow() > sess.expires_at:
        sess.status = 'expired'
        db.session.commit()
    customer_name = None
    if sess.customer:
        customer_name = sess.customer.full_name or sess.customer.username
    return jsonify({'status': sess.status, 'customer': customer_name})


@bp.route('/banco/session/<token>/cancel', methods=['POST'])
@staff_required
def banco_session_cancel(token):
    sess = BancoSession.query.filter_by(token=token).first_or_404()
    if sess.status == 'pending':
        sess.status = 'cancelled'
        db.session.commit()
    return jsonify({'ok': True})


@bp.route('/banco/items')
@staff_required
def banco_items():
    tid   = _active_tenant_id()
    items = BancoItem.query.filter_by(tenant_id=tid)\
                    .order_by(BancoItem.sort_order, BancoItem.name).all()
    return render_template('admin/banco_items.html', items=items)


@bp.route('/banco/items/new', methods=['POST'])
@staff_required
def banco_item_new():
    name  = request.form.get('name', '').strip()
    price = request.form.get('price', type=float)
    if not name or not price or price <= 0:
        flash('Nome e prezzo obbligatori.', 'danger')
        return redirect(url_for('admin.banco_items'))
    tid = _active_tenant_id()
    db.session.add(BancoItem(
        name=name, price=price,
        icon=request.form.get('icon', 'fa-mug-hot').strip(),
        color=request.form.get('color', 'info').strip(),
        sort_order=request.form.get('sort_order', 0, type=int),
        tenant_id=tid,
    ))
    db.session.commit()
    flash(f'Articolo "{name}" aggiunto.', 'success')
    return redirect(url_for('admin.banco_items'))


@bp.route('/banco/items/<int:iid>/edit', methods=['POST'])
@staff_required
def banco_item_edit(iid):
    item = db.get_or_404(BancoItem, iid)
    item.name       = request.form.get('name', item.name).strip()
    item.price      = request.form.get('price', type=float) or item.price
    item.icon       = request.form.get('icon', item.icon).strip()
    item.color      = request.form.get('color', item.color).strip()
    item.sort_order = request.form.get('sort_order', item.sort_order, type=int)
    item.is_active  = request.form.get('is_active') == '1'
    db.session.commit()
    flash(f'Articolo "{item.name}" aggiornato.', 'success')
    return redirect(url_for('admin.banco_items'))


@bp.route('/banco/items/<int:iid>/delete', methods=['POST'])
@staff_required
def banco_item_delete(iid):
    item = db.get_or_404(BancoItem, iid)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f'Articolo "{name}" eliminato.', 'info')
    return redirect(url_for('admin.banco_items'))


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
    send_telegram_to_user(
        res.user,
        f'❌ La tua prenotazione del tavolo <b>{res.table.number}</b> '
        f'per le <b>{res.session_start}</b> del '
        f'{res.reservation_date.strftime("%d/%m/%Y")} è stata annullata dall\'amministratore.'
    )
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


@bp.route('/ingredients/<int:iid>/stock', methods=['POST'])
@require_permission('manage_ingredients')
def ingredient_stock(iid):
    ing = db.get_or_404(Ingredient, iid)
    op  = request.form.get('op', 'set')
    try:
        qty = float(request.form.get('qty', 0))
    except (ValueError, TypeError):
        qty = 0.0
    if op == 'add':
        ing.stock_qty = (ing.stock_qty or 0.0) + qty
    elif op == 'sub':
        ing.stock_qty = max(0.0, (ing.stock_qty or 0.0) - qty)
    else:
        ing.stock_qty = qty if qty >= 0 else None
    db.session.commit()
    flash(f'Giacenza "{ing.name}" aggiornata: {ing.stock_qty:.0f}g.', 'success')
    return redirect(url_for('admin.ingredients'))


@bp.route('/ingredients/new', methods=['POST'])
@require_permission('manage_ingredients')
def ingredient_new():
    name = request.form.get('name', '').strip()
    category_id = request.form.get('category_id', type=int)
    price_extra = request.form.get('price_extra', type=float, default=0.0)
    is_vegetarian = 'is_vegetarian' in request.form
    allergens = request.form.get('allergens', '').strip()
    gps_raw = request.form.get('grams_per_serving', '').strip()
    grams_per_serving = float(gps_raw) if gps_raw else None
    if not name or not category_id:
        flash('Nome e categoria obbligatori.', 'danger')
        return redirect(url_for('admin.ingredients'))
    db.session.add(Ingredient(name=name, category_id=category_id,
                              price_extra=price_extra or 0.0,
                              is_vegetarian=is_vegetarian, allergens=allergens,
                              grams_per_serving=grams_per_serving))
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
    ing.name        = request.form.get('name', ing.name).strip()
    ing.price_extra = request.form.get('price_extra', type=float, default=ing.price_extra) or 0.0
    gps_raw = request.form.get('grams_per_serving', '').strip()
    ing.grams_per_serving = float(gps_raw) if gps_raw else None
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
    all_keys = [
        'telegram_bot_token', 'telegram_chat_id',
        'gmail_user', 'gmail_app_password',
        'registration_bonus',
        'loyalty_points_per_euro', 'loyalty_reward_points', 'loyalty_reward_amount',
        'builder_price_panino', 'builder_price_insalata', 'builder_price_poke',
        'table_reminder_minutes', 'order_reminder_minutes', 'meal_reminder_minutes',
    ]
    cfg = {k: get_setting(k) for k in all_keys}
    return render_template('admin/settings.html', cfg=cfg)


@bp.route('/settings/save', methods=['POST'])
@require_permission('manage_settings')
def settings_save():
    # Ogni sezione del form include un campo "keys" con i propri tasti (comma-separated)
    keys_raw = request.form.get('keys', '')
    keys = [k.strip() for k in keys_raw.split(',') if k.strip()]
    if not keys:
        flash('Nessun campo da salvare.', 'warning')
        return redirect(url_for('admin.settings'))
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


@bp.route('/seed-demo', methods=['POST'])
@_superadmin_required
def seed_demo():
    from app.demo_seed import reset_demo_data, seed_demo_data
    reset_demo_data()
    ok, msg = seed_demo_data()
    flash(msg, 'success' if ok else 'warning')
    return redirect(url_for('admin.dashboard'))


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
    from collections import defaultdict as _dd
    today_meals: dict = _dd(list)
    for m in DailyFixedMeal.query.filter_by(meal_date=date.today(), **tf).all():
        today_meals[m.corporate_id].append(m)
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

    try:
        _d_raw = request.args.get('d') or request.form.get('d') or ''
        sel_date = date.fromisoformat(_d_raw) if _d_raw else today
    except ValueError:
        sel_date = today
    prev_date = sel_date - timedelta(days=1)
    next_date = sel_date + timedelta(days=1)

    def _d_param():
        return sel_date.isoformat() if sel_date != today else None

    if request.method == 'POST':
        action  = request.form.get('action', 'add')
        meal_id = request.form.get('meal_id', type=int)

        # ── Elimina opzione ────────────────────────────────────────────────────
        if action == 'delete' and meal_id:
            meal = DailyFixedMeal.query.get_or_404(meal_id)
            db.session.delete(meal)
            db.session.commit()
            flash('Opzione eliminata.', 'info')
            return redirect(url_for('admin.convenzione_pasto', cid=cid, d=_d_param()))

        # ── Attiva/disattiva opzione ───────────────────────────────────────────
        if action == 'toggle' and meal_id:
            meal = DailyFixedMeal.query.get_or_404(meal_id)
            meal.is_active = not meal.is_active
            db.session.commit()
            stato = 'attivata' if meal.is_active else 'disattivata'
            flash(f'Opzione "{meal.name}" {stato}.', 'success')
            return redirect(url_for('admin.convenzione_pasto', cid=cid, d=_d_param()))

        # ── Aggiunge / modifica opzione ───────────────────────────────────────
        name = request.form.get('name', '').strip()
        if not name:
            flash('Il nome è obbligatorio.', 'danger')
            return redirect(url_for('admin.convenzione_pasto', cid=cid, d=_d_param()))

        price    = request.form.get('price', '').strip()
        max_book = request.form.get('max_bookings', '').strip()

        if action == 'edit' and meal_id:
            meal = DailyFixedMeal.query.get_or_404(meal_id)
        else:
            meal = DailyFixedMeal(
                corporate_id=cid, meal_date=sel_date,
                tenant_id=current_user.tenant_id if not current_user.is_admin else None)
            db.session.add(meal)

        meal.name         = name
        meal.description  = request.form.get('description', '').strip()
        meal.allergens    = ','.join(request.form.getlist('allergens'))
        meal.primo        = request.form.get('primo',    '').strip()
        meal.secondo      = request.form.get('secondo',   '').strip()
        meal.contorno     = request.form.get('contorno',  '').strip()
        meal.bevanda      = request.form.get('bevanda',   '').strip()
        meal.caffe        = request.form.get('caffe',     '').strip()
        meal.price        = float(price)    if price    else corp.daily_price
        meal.max_bookings = int(max_book)   if max_book else corp.max_daily_covers
        meal.is_active    = 'is_active' in request.form
        db.session.commit()
        flash(f'Opzione "{name}" salvata.', 'success')
        return redirect(url_for('admin.convenzione_pasto', cid=cid, d=_d_param()))

    meals = DailyFixedMeal.query.filter_by(corporate_id=cid, meal_date=sel_date)\
        .order_by(DailyFixedMeal.name).all()
    bookings_by_meal = {
        m.id: CorporateMealBooking.query.filter_by(meal_id=m.id).all()
        for m in meals
    }

    import json as _json
    configs_json = _json.dumps({
        cfg.id: {
            'name':         cfg.name,
            'primo':        cfg.primo        or '',
            'secondo':      cfg.secondo      or '',
            'contorno':     cfg.contorno     or '',
            'bevanda':      cfg.bevanda      or '',
            'caffe':        cfg.caffe        or '',
            'description':  cfg.description  or '',
            'allergens':    [a.strip() for a in (cfg.allergens or '').split(',') if a.strip()],
            'price':        cfg.price,
            'max_bookings': cfg.max_bookings,
        }
        for cfg in corp.configurations
    })
    return render_template('admin/convenzione_pasto.html',
                           corp=corp, meals=meals, sel_date=sel_date, today=today,
                           prev_date=prev_date, next_date=next_date,
                           bookings_by_meal=bookings_by_meal, allergens_list=ALLERGENS,
                           configs_json=configs_json)


@bp.route('/convenzioni/<int:cid>/pasto/<int:bid>/consuma', methods=['POST'])
@require_permission('manage_products')
def convenzione_consuma(cid, bid):
    booking = CorporateMealBooking.query.get_or_404(bid)
    booking.status = 'consumed'
    db.session.commit()
    d = request.args.get('d', '')
    flash(f'Pasto di {booking.user.username} segnato come consumato.', 'success')
    return redirect(url_for('admin.convenzione_pasto', cid=cid, d=d or None))


# ── Configurazioni pasto ──────────────────────────────────────────────────────

@bp.route('/convenzioni/<int:cid>/configurazioni', methods=['GET', 'POST'])
@require_permission('manage_products')
def convenzione_configurazioni(cid):
    corp = CorporateAccount.query.get_or_404(cid)
    if request.method == 'POST':
        name    = request.form.get('name', '').strip()
        if not name:
            flash('Il nome è obbligatorio.', 'danger')
            return redirect(url_for('admin.convenzione_configurazioni', cid=cid))
        cfg = MealConfiguration(
            corporate_id = cid,
            name         = name,
            primo        = request.form.get('primo',   '').strip(),
            secondo      = request.form.get('secondo',  '').strip(),
            contorno     = request.form.get('contorno', '').strip(),
            bevanda      = request.form.get('bevanda',  '').strip(),
            caffe        = request.form.get('caffe',    '').strip(),
            description  = request.form.get('description', '').strip(),
            allergens    = ','.join(request.form.getlist('allergens')),
            price        = float(p) if (p := request.form.get('price', '').strip()) else None,
            max_bookings = int(m) if (m := request.form.get('max_bookings', '').strip()) else None,
            sort_order   = int(request.form.get('sort_order', 0) or 0),
            tenant_id    = None if current_user.is_admin else current_user.tenant_id,
        )
        db.session.add(cfg)
        db.session.commit()
        flash(f'Configurazione "{name}" creata.', 'success')
        return redirect(url_for('admin.convenzione_configurazioni', cid=cid))

    configs = MealConfiguration.query.filter_by(corporate_id=cid)\
        .order_by(MealConfiguration.sort_order, MealConfiguration.name).all()
    return render_template('admin/convenzione_configurazioni.html',
                           corp=corp, configs=configs, allergens_list=ALLERGENS)


@bp.route('/convenzioni/<int:cid>/configurazioni/<int:cfg_id>/edit', methods=['POST'])
@require_permission('manage_products')
def configurazione_edit(cid, cfg_id):
    cfg = MealConfiguration.query.get_or_404(cfg_id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Il nome è obbligatorio.', 'danger')
        return redirect(url_for('admin.convenzione_configurazioni', cid=cid))
    cfg.name         = name
    cfg.primo        = request.form.get('primo',   '').strip()
    cfg.secondo      = request.form.get('secondo',  '').strip()
    cfg.contorno     = request.form.get('contorno', '').strip()
    cfg.bevanda      = request.form.get('bevanda',  '').strip()
    cfg.caffe        = request.form.get('caffe',    '').strip()
    cfg.description  = request.form.get('description', '').strip()
    cfg.allergens    = ','.join(request.form.getlist('allergens'))
    p = request.form.get('price', '').strip()
    cfg.price        = float(p) if p else None
    m = request.form.get('max_bookings', '').strip()
    cfg.max_bookings = int(m) if m else None
    cfg.sort_order   = int(request.form.get('sort_order', 0) or 0)
    db.session.commit()
    flash(f'Configurazione "{cfg.name}" aggiornata.', 'success')
    return redirect(url_for('admin.convenzione_configurazioni', cid=cid))


@bp.route('/convenzioni/<int:cid>/configurazioni/<int:cfg_id>/delete', methods=['POST'])
@require_permission('manage_products')
def configurazione_delete(cid, cfg_id):
    cfg = MealConfiguration.query.get_or_404(cfg_id)
    name = cfg.name
    db.session.delete(cfg)
    db.session.commit()
    flash(f'Configurazione "{name}" eliminata.', 'info')
    return redirect(url_for('admin.convenzione_configurazioni', cid=cid))


@bp.route('/convenzioni/<int:cid>/configurazioni/<int:cfg_id>/json')
@require_permission('manage_products')
def configurazione_json(cid, cfg_id):
    cfg = MealConfiguration.query.get_or_404(cfg_id)
    return jsonify({
        'name':         cfg.name,
        'primo':        cfg.primo        or '',
        'secondo':      cfg.secondo      or '',
        'contorno':     cfg.contorno     or '',
        'bevanda':      cfg.bevanda      or '',
        'caffe':        cfg.caffe        or '',
        'description':  cfg.description  or '',
        'allergens':    [a.strip() for a in (cfg.allergens or '').split(',') if a.strip()],
        'price':        cfg.price,
        'max_bookings': cfg.max_bookings,
    })


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

        elif op == 'clear_catalog':
            # cancella prodotti e categorie (assume ordini già svuotati o li svuota)
            db.session.execute(db.text('UPDATE transactions SET order_id = NULL WHERE order_id IS NOT NULL'))
            CustomOrderItemIngredient.query.delete(synchronize_session=False)
            CustomOrderItem.query.delete(synchronize_session=False)
            OrderItem.query.delete(synchronize_session=False)
            CorporateMealBooking.query.delete(synchronize_session=False)
            Order.query.delete(synchronize_session=False)
            DailyStock.query.delete(synchronize_session=False)
            PollChoice.query.delete(synchronize_session=False)
            Poll.query.delete(synchronize_session=False)
            Product.query.delete(synchronize_session=False)
            Category.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Prodotti e categorie eliminati.', 'success')

        elif op == 'clear_ingredients':
            CustomOrderItemIngredient.query.delete(synchronize_session=False)
            CustomOrderItem.query.delete(synchronize_session=False)
            Ingredient.query.delete(synchronize_session=False)
            IngredientCategory.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Ingredienti eliminati.', 'success')

        elif op == 'clear_consumables':
            ConsumableMovement.query.delete(synchronize_session=False)
            ConsumableItem.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Consumabili e movimenti eliminati.', 'success')

        elif op == 'clear_suppliers':
            ConsumableMovement.query.delete(synchronize_session=False)
            ConsumableItem.query.delete(synchronize_session=False)
            Supplier.query.delete(synchronize_session=False)
            db.session.commit()
            flash('Fornitori, consumabili e movimenti eliminati.', 'success')

        elif op == 'reset_all':
            # step 1: null nullable FKs
            db.session.execute(db.text('UPDATE transactions SET order_id = NULL WHERE order_id IS NOT NULL'))
            db.session.execute(db.text('UPDATE consumable_movements SET user_id = NULL WHERE user_id IS NOT NULL'))
            # step 2: leaf / child tables
            PollVote.query.delete(synchronize_session=False)
            CorporateMealBooking.query.delete(synchronize_session=False)
            CorporateMembership.query.delete(synchronize_session=False)
            CustomOrderItemIngredient.query.delete(synchronize_session=False)
            CustomOrderItem.query.delete(synchronize_session=False)
            OrderItem.query.delete(synchronize_session=False)
            # step 3: transaction / reservation tables
            Order.query.delete(synchronize_session=False)
            TableReservation.query.delete(synchronize_session=False)
            Transaction.query.delete(synchronize_session=False)
            # step 4: catalog / content tables
            DailyStock.query.delete(synchronize_session=False)
            PollChoice.query.delete(synchronize_session=False)
            Poll.query.delete(synchronize_session=False)
            Product.query.delete(synchronize_session=False)
            Category.query.delete(synchronize_session=False)
            Ingredient.query.delete(synchronize_session=False)
            IngredientCategory.query.delete(synchronize_session=False)
            # step 5: magazzino
            ConsumableMovement.query.delete(synchronize_session=False)
            ConsumableItem.query.delete(synchronize_session=False)
            Supplier.query.delete(synchronize_session=False)
            # step 6: users
            User.query.filter_by(is_client=True).delete(synchronize_session=False)
            db.session.commit()
            flash('Reset completo eseguito.', 'success')

        elif op == 'run_demo_seed':
            from app.demo_seed import reset_demo_data, seed_demo_data
            reset_demo_data()
            ok, msg = seed_demo_data()
            flash(f'Seed demo: {msg}', 'success' if ok else 'warning')
            return redirect(url_for('admin.maintenance'))

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
        'products':     Product.query.count(),
        'categories':   Category.query.count(),
        'ingredients':  Ingredient.query.count(),
        'consumables':  ConsumableItem.query.count(),
        'suppliers':    Supplier.query.count(),
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


# ── Report giornaliero pasti aziendali ────────────────────────────────────────

@bp.route('/convenzioni/report')
@require_permission('manage_products')
def convenzioni_report():
    tf = _tenant_filter()
    try:
        sel_date = date.fromisoformat(request.args.get('d', ''))
    except (ValueError, TypeError):
        sel_date = date.today()

    corps = CorporateAccount.query.filter_by(is_active=True, **tf)\
        .order_by(CorporateAccount.name).all()

    report = []
    for corp in corps:
        meals   = DailyFixedMeal.query.filter_by(corporate_id=corp.id, meal_date=sel_date).all()
        entries = []
        for meal in meals:
            for b in meal.bookings:
                if b.status != 'cancelled':
                    entries.append({'booking': b, 'meal': meal, 'user': b.user})
        entries.sort(key=lambda x: (x['user'].last_name or '', x['user'].first_name or '',
                                    x['user'].username))
        report.append({'corp': corp, 'entries': entries})

    prev_date = sel_date - timedelta(days=1)
    next_date = sel_date + timedelta(days=1)
    return render_template('admin/convenzioni_report.html',
                           report=report, sel_date=sel_date, today=date.today(),
                           prev_date=prev_date, next_date=next_date)


@bp.route('/convenzioni/<int:cid>/report-docx')
@require_permission('manage_products')
def convenzione_report_docx(cid):
    from io import BytesIO
    from flask import send_file
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        _HAS_DOCX = True
    except ImportError:
        _HAS_DOCX = False

    corp = CorporateAccount.query.get_or_404(cid)
    try:
        sel_date = date.fromisoformat(request.args.get('d', ''))
    except (ValueError, TypeError):
        sel_date = date.today()

    meals   = DailyFixedMeal.query.filter_by(corporate_id=corp.id, meal_date=sel_date).all()
    entries = []
    for meal in meals:
        for b in meal.bookings:
            if b.status != 'cancelled':
                entries.append((b.user.full_name, meal.name, b.quantity or 1, b.status))
    entries.sort(key=lambda x: x[0])

    if not _HAS_DOCX:
        flash('Libreria python-docx non installata. Esegui: pip install python-docx', 'danger')
        return redirect(url_for('admin.convenzioni_report', d=sel_date.isoformat()))

    doc = Document()

    # ── Intestazione ─────────────────────────────────────────────────────────
    title = doc.add_heading('Lista Pasti Aziendali', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run(f'{corp.name}  —  {sel_date.strftime("%d/%m/%Y")}')
    run.font.size = Pt(13)

    doc.add_paragraph()

    meta = doc.add_paragraph()
    meta.add_run('Totale prenotazioni: ').bold = True
    meta.add_run(str(len(entries)))

    doc.add_paragraph()

    # ── Tabella presenze ──────────────────────────────────────────────────────
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(['Nominativo', 'Pasto', 'Quantità', 'Stato']):
        hdr_cells[i].text = h
        run = hdr_cells[i].paragraphs[0].runs[0]
        run.bold = True
        run.font.size = Pt(10)

    STATUS_IT = {'consumed': 'Consumato', 'booked': 'Prenotato'}
    for full_name, meal_name, qty, status in entries:
        row = table.add_row().cells
        row[0].text = full_name
        row[1].text = meal_name
        row[2].text = str(qty)
        row[3].text = STATUS_IT.get(status, status)
        for cell in row:
            cell.paragraphs[0].runs[0].font.size = Pt(10)

    doc.add_paragraph()
    note = doc.add_paragraph(
        f'Documento generato il {_dt.now().strftime("%d/%m/%Y %H:%M")} da QuickLunch Bar Self-Service')
    note.runs[0].font.size = Pt(8)
    note.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    filename = f'pasti_{corp.name.replace(" ","_")}_{sel_date.isoformat()}.docx'
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

@bp.route('/convenzioni/abstract-docx')
@require_permission('manage_products')
def convenzioni_abstract_docx():
    """Genera il documento descrittivo del modulo Pasti Aziendali."""
    from io import BytesIO
    from flask import send_file
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    BRAND = '#E94560'
    DARK  = '#1a1a2e'
    GRAY  = '#666666'

    def _rgb(h):
        h = h.lstrip('#')
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _heading(doc, text, level=1, color=BRAND):
        p = doc.add_heading(text, level)
        for run in p.runs:
            run.font.color.rgb = _rgb(color)
        return p

    def _body(doc, text):
        p = doc.add_paragraph(text)
        p.paragraph_format.space_after = Pt(5)
        for run in p.runs:
            run.font.size = Pt(11)
        return p

    def _bullet(doc, text, bold_prefix=None):
        p = doc.add_paragraph(style='List Bullet')
        if bold_prefix:
            r = p.add_run(bold_prefix + ' ')
            r.bold = True
            r.font.size = Pt(11)
            r.font.color.rgb = _rgb(BRAND)
        r2 = p.add_run(text)
        r2.font.size = Pt(11)

    def _step(doc, num, title, body):
        p = doc.add_paragraph()
        r1 = p.add_run(f'{num}. {title}  ')
        r1.bold = True
        r1.font.size = Pt(11)
        r1.font.color.rgb = _rgb(BRAND)
        r2 = p.add_run(body)
        r2.font.size = Pt(11)
        p.paragraph_format.left_indent = Inches(0.15)
        p.paragraph_format.space_after  = Pt(6)

    def _divider(doc):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after  = Pt(2)
        pPr  = p._p.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        bot  = OxmlElement('w:bottom')
        bot.set(qn('w:val'),   'single')
        bot.set(qn('w:sz'),    '6')
        bot.set(qn('w:space'), '1')
        bot.set(qn('w:color'), 'E94560')
        pBdr.append(bot)
        pPr.append(pBdr)

    doc = Document()
    for section in doc.sections:
        section.top_margin    = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin   = Inches(1.2)
        section.right_margin  = Inches(1.2)

    # ── Copertina ─────────────────────────────────────────────────────────────
    for _ in range(3):
        doc.add_paragraph()
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = tp.add_run('QuickLunch — Bar Self-Service')
    r.font.size = Pt(26); r.font.bold = True; r.font.color.rgb = _rgb(BRAND)
    sp = doc.add_paragraph()
    sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sp.add_run('Modulo Pasti Aziendali')
    r.font.size = Pt(18); r.font.color.rgb = _rgb(DARK)
    doc.add_paragraph()
    dp = doc.add_paragraph()
    dp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = dp.add_run('Documento descrittivo per le aziende convenzionate')
    r.font.size = Pt(12); r.font.italic = True; r.font.color.rgb = _rgb(GRAY)
    for _ in range(2):
        doc.add_paragraph()
    datp = doc.add_paragraph()
    datp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = datp.add_run(_dt.now().strftime('%B %Y'))
    r.font.size = Pt(11); r.font.color.rgb = _rgb(GRAY)
    doc.add_page_break()

    # ── 1. Introduzione ───────────────────────────────────────────────────────
    _heading(doc, '1. Introduzione')
    _divider(doc)
    _body(doc,
        "QuickLunch è il sistema digitale di gestione del bar e della mensa self-service. "
        "Il modulo Pasti Aziendali consente alle aziende convenzionate di offrire ai propri "
        "dipendenti un servizio di prenotazione pasto strutturato, tracciato e amministrabile "
        "in tempo reale.")
    _body(doc,
        "Ogni azienda dispone di un proprio spazio con configurazioni personalizzate "
        "(prezzo del pasto, numero massimo di coperti, portate). I dipendenti prenotano "
        "autonomamente tramite applicazione web da qualsiasi dispositivo, senza installazione.")
    doc.add_paragraph()

    # ── 2. Attori ─────────────────────────────────────────────────────────────
    _heading(doc, '2. Attori del sistema')
    _divider(doc)
    _heading(doc, 'Amministratore del bar', 2, color=DARK)
    _bullet(doc, 'Gestisce le convenzioni aziendali (creazione, modifica, disattivazione).')
    _bullet(doc, 'Pubblica il menu giornaliero per ciascuna azienda (portate, prezzo, massimo coperti).')
    _bullet(doc, 'Visualizza e scarica il report giornaliero delle presenze in formato Word.')
    _bullet(doc, 'Segna i pasti come Consumati in tempo reale durante il servizio.')
    _bullet(doc, 'Consulta lo storico mensile delle presenze per convenzione.')
    doc.add_paragraph()
    _heading(doc, 'Dipendente (utente finale)', 2, color=DARK)
    _bullet(doc, "Si registra nell'applicazione (email + password oppure account Google).")
    _bullet(doc, "Viene associato alla propria azienda convenzionata dall'amministratore.")
    _bullet(doc, 'Visualizza il menu del giorno e prenota con pochi clic.')
    _bullet(doc, "Può annullare la prenotazione in autonomia.")
    _bullet(doc, 'Riceve facoltativamente notifiche Telegram di conferma e reminder.')
    doc.add_paragraph()

    # ── 3. Flusso ─────────────────────────────────────────────────────────────
    _heading(doc, '3. Flusso operativo giornaliero')
    _divider(doc)
    _heading(doc, '3.1  Lato amministratore (bar)', 2, color=DARK)
    _step(doc, 1, 'Pubblicazione menu:',
          "ogni mattina si inserisce il menu del giorno: nome pasto, portate "
          "(primo, secondo, contorno, bevanda, caffè), prezzo e coperti massimi. "
          "È possibile creare più opzioni pasto per la stessa giornata.")
    _step(doc, 2, 'Monitoraggio prenotazioni:',
          "durante la mattinata si verifica in tempo reale il numero di prenotazioni "
          "ricevute e i nominativi dal Report Giornaliero.")
    _step(doc, 3, 'Servizio pasti:',
          "al momento della distribuzione, lo staff spunta ogni prenotazione come "
          "Consumato dall'interfaccia, tracciando le presenze effettive.")
    _step(doc, 4, 'Report e riconciliazione:',
          "a fine servizio il report giornaliero è scaricabile in formato Word (.docx) "
          "per la riconciliazione contabile con l'azienda.")
    doc.add_paragraph()
    _heading(doc, '3.2  Lato dipendente', 2, color=DARK)
    _step(doc, 1, 'Accesso:',
          "il dipendente apre l'applicazione da browser (PC, tablet, smartphone) "
          "e accede con le proprie credenziali.")
    _step(doc, 2, 'Prenotazione:',
          "dalla sezione Pasto Aziendale visualizza il menu del giorno, seleziona "
          "l'opzione desiderata, sceglie l'orario di ritiro (se configurato) e conferma.")
    _step(doc, 3, 'Conferma:',
          "la prenotazione viene registrata immediatamente con conferma a schermo "
          "e notifica Telegram opzionale.")
    _step(doc, 4, 'Annullamento:',
          "il dipendente può annullare la propria prenotazione finché il pasto "
          "non è stato segnato come consumato.")
    doc.add_paragraph()

    # ── 4. Configurazione ─────────────────────────────────────────────────────
    _heading(doc, '4. Configurazione della convenzione')
    _divider(doc)
    _body(doc, 'Ogni azienda viene configurata con i seguenti parametri:')
    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = 'Table Grid'
    h0, h1 = tbl.rows[0].cells
    h0.text = 'Parametro'
    h1.text = 'Descrizione'
    for cell in [h0, h1]:
        r = cell.paragraphs[0].runs[0]
        r.bold = True
        r.font.size = Pt(10)
    for pname, pdesc in [
        ('Nome azienda',           "Ragione sociale dell'azienda convenzionata."),
        ('Email di contatto',      'Referente aziendale per le comunicazioni.'),
        ('Prezzo giornaliero (€)', 'Prezzo standard del pasto, sovrascrivibile per singola giornata.'),
        ('Massimo coperti/giorno', 'Numero massimo di prenotazioni accettabili per giornata.'),
        ('Dipendenti associati',   'Utenti registrati associati alla convenzione.'),
        ('Template menu',          'Configurazioni riutilizzabili per velocizzare la pubblicazione dei menu ricorrenti.'),
    ]:
        row = tbl.add_row().cells
        rn = row[0].paragraphs[0].add_run(pname)
        rn.bold = True
        rn.font.size = Pt(10)
        rd = row[1].paragraphs[0].add_run(pdesc)
        rd.font.size = Pt(10)
    doc.add_paragraph()

    # ── 5. Report ─────────────────────────────────────────────────────────────
    _heading(doc, '5. Report e documenti disponibili')
    _divider(doc)
    _heading(doc, 'Report Giornaliero (pagina web)', 2, color=DARK)
    _body(doc,
        "Accessibile da Convenzioni → Report Giornaliero: lista dei dipendenti con "
        "la relativa prenotazione pasto del giorno. Navigazione tra date con tasti freccia "
        "o selettore calendario.")
    _heading(doc, 'Report Giornaliero (DOCX scaricabile)', 2, color=DARK)
    _body(doc,
        "Il pulsante Scarica DOCX genera un documento Word con intestazione azienda/data, "
        "totale prenotazioni e tabella: Nominativo, Pasto, Quantità, Stato.")
    _heading(doc, 'Storico mensile presenze', 2, color=DARK)
    _body(doc,
        "Accessibile da Convenzioni → [Azienda] → Storico Presenze. Mostra mese "
        "per mese il dettaglio con i contatori di prenotati, consumati e annullati.")
    doc.add_paragraph()

    # ── 6. Notifiche ──────────────────────────────────────────────────────────
    _heading(doc, '6. Notifiche automatiche')
    _divider(doc)
    _body(doc,
        "Il sistema può inviare notifiche Telegram direttamente al dipendente (opzionale; "
        "richiede Telegram Chat ID configurato nel profilo utente):")
    _bullet(doc, 'Conferma annullamento prenotazione pasto.', 'Annullamento:')
    _bullet(doc,
            "Reminder N minuti prima dell'orario di ritiro (configurabile in Impostazioni → Reminder).",
            'Reminder:')
    doc.add_paragraph()

    # ── 7. Sicurezza ──────────────────────────────────────────────────────────
    _heading(doc, '7. Accesso e sicurezza')
    _divider(doc)
    _bullet(doc, 'Email + password oppure account Google (OAuth 2.0).', 'Autenticazione:')
    _bullet(doc, 'Supporto opzionale MFA con Google Authenticator.', 'Doppio fattore:')
    _bullet(doc, 'Ciascun dipendente vede solo le informazioni della propria azienda.', 'Isolamento:')
    _bullet(doc, 'Tutte le comunicazioni avvengono su connessione cifrata HTTPS.', 'Trasporto:')
    doc.add_paragraph()

    # ── Colophon ──────────────────────────────────────────────────────────────
    doc.add_page_break()
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cp.add_run(
        f'QuickLunch Bar Self-Service  —  Documento generato il {_dt.now().strftime("%d/%m/%Y")}')
    r.font.size = Pt(9)
    r.font.italic = True
    r.font.color.rgb = _rgb(GRAY)

    buf2 = BytesIO()
    doc.save(buf2)
    buf2.seek(0)
    fname = f'QuickLunch_Pasti_Aziendali_Abstract_{_dt.now().strftime("%Y%m")}.docx'
    return send_file(buf2, as_attachment=True, download_name=fname,
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')



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
    send_telegram(
        f'🟢 <b>Tavolo {res.table.number} OCCUPATO</b>\n'
        f'👤 {res.user.full_name}\n'
        f'🕐 Dalle <b>{res.session_start}</b> — '
        f'{res.reservation_date.strftime("%d/%m/%Y")}'
        + (f'\n👥 {res.party_size} persone' if getattr(res, 'party_size', None) else '')
    )
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

