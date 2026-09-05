import json
import secrets
from datetime import date, datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from app import (db, tables_enabled, cesto_enabled, wallet_enabled,
                 dieta_enabled, numero_italiano)
from app.main import bp
from app.notifications import (send_telegram, send_telegram_to_user,
                               get_numeric_setting, _get_or_create_vapid_keys)
from app.models import (Product, Category, Order, OrderItem, TimeSlot,
                        Transaction, DailyStock, IngredientCategory, Ingredient,
                        CustomOrderItem, CustomOrderItemIngredient,
                        Table, TableReservation, Poll, PollVote, PollChoice,
                        DailyFixedMeal, CorporateMealBooking, Tenant, BancoSession,
                        CorporateMembership, PrepLabel, User,
                        Prenotazione, PrenotazioneItem, PushSubscription,
                        DietProfile, DietPlan, DietPlanDay, ALLERGENS,
                        CONDIZIONI_DIETA, REGIMI_DIETA, OBIETTIVI_DIETA,
                        ATTIVITA_DIETA, GIORNI_SETTIMANA)
from app.dieta import profilo_attivo
from config import Config


def tables_required(f):
    """Blocca la rotta se la gestione tavoli e' disattivata da Impostazioni."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not tables_enabled():
            flash('La prenotazione dei tavoli non e\' attiva.', 'warning')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


def cesto_required(f):
    """Blocca la rotta se la gestione del cesto e' disattivata da Impostazioni."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not cesto_enabled():
            flash('Il cesto non e\' attivo.', 'warning')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


def wallet_required(f):
    """Blocca la rotta se il portafoglio prepagato e' disattivato."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not wallet_enabled():
            flash('Il portafoglio prepagato non e\' attivo.', 'warning')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


def dieta_required(f):
    """Blocca la rotta se la dieta settimanale e' disattivata."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not dieta_enabled():
            flash('La dieta settimanale non e\' attiva.', 'warning')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


def _effective_tenant_id():
    """Superadmin ha tenant_id=None → usa il tenant 'default' per le query utente."""
    if current_user.tenant_id:
        return current_user.tenant_id
    default_t = Tenant.query.filter_by(slug='default').first()
    return default_t.id if default_t else None


# ── Home ──────────────────────────────────────────────────────────────────────

@bp.route('/')
@login_required
def index():
    if current_user.is_admin or current_user.is_staff:
        return redirect(url_for('admin.dashboard'))
    today_orders = Order.query.filter_by(
        user_id=current_user.id, order_date=date.today()
    ).filter(Order.status != 'cancelled').all()
    today_reservations = TableReservation.query.filter_by(
        user_id=current_user.id, reservation_date=date.today()
    ).filter(TableReservation.status != 'cancelled').all()
    recent_tx = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc()).limit(5).all()

    # pasto aziendale di oggi
    today_meal_booking  = None
    meal_booking_reminder = False
    membership = current_user.corporate_membership
    if membership and membership.is_active:
        today_meals = DailyFixedMeal.query.filter_by(
            corporate_id=membership.corporate_id,
            meal_date=date.today(),
            is_active=True,
        ).all()
        if today_meals:
            today_meal_ids = [m.id for m in today_meals]
            today_meal_booking = CorporateMealBooking.query.filter(
                CorporateMealBooking.user_id == current_user.id,
                CorporateMealBooking.meal_id.in_(today_meal_ids),
                CorporateMealBooking.status != 'cancelled',
            ).first()
            if not today_meal_booking:
                meal_booking_reminder = True

    riepilogo_dieta = None
    _profilo = profilo_attivo(current_user) if dieta_enabled() else None
    if _profilo:
        from app.dieta import riepilogo_giornata
        riepilogo_dieta = riepilogo_giornata(current_user, _profilo)

    return render_template('main/dashboard.html',
                           riepilogo_dieta=riepilogo_dieta,
                           today_orders=today_orders,
                           today_reservations=today_reservations,
                           recent_tx=recent_tx,
                           today_meal_booking=today_meal_booking,
                           meal_booking_reminder=meal_booking_reminder,
                           loyalty_threshold=get_numeric_setting('loyalty_reward_points', 100),
                           reward_amount=get_numeric_setting('loyalty_reward_amount', 1.0))


# ── Menu ──────────────────────────────────────────────────────────────────────

@bp.route('/menu')
@login_required
def menu():
    tid = _effective_tenant_id()
    categories = Category.query.filter_by(tenant_id=tid).order_by(Category.name).all()
    products = Product.query.filter_by(is_active=True, tenant_id=tid).order_by(
        Product.category_id, Product.name).all()
    slots = TimeSlot.query.filter_by(is_active=True, tenant_id=tid).order_by(TimeSlot.time_str).all()
    cart = session.get('cart', {})
    # Con la dieta attiva ogni scheda dice se il piatto va bene e quante kcal fa.
    profilo = profilo_attivo(current_user) if dieta_enabled() else None
    compat = {}
    if profilo:
        from app.dieta import compatibilita
        for p in products:
            ok, motivi = compatibilita(p, profilo)
            compat[p.id] = {'ok': ok, 'motivi': motivi}
    return render_template('main/menu.html', categories=categories,
                           products=products, slots=slots, cart=cart,
                           profilo_dieta=profilo, compat=compat)


@bp.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def cart_add(product_id):
    product = db.get_or_404(Product, product_id)
    qty = int(request.form.get('qty', 1))
    qty = max(1, qty)
    cart = session.get('cart', {})
    key = str(product_id)
    cart[key] = min(cart.get(key, 0) + qty, product.available_today())
    session['cart'] = cart
    flash(f'"{product.name}" aggiunto al carrello.', 'success')
    return redirect(url_for('main.menu'))


@bp.route('/cart/remove/<int:product_id>', methods=['POST'])
@login_required
def cart_remove(product_id):
    cart = session.get('cart', {})
    cart.pop(str(product_id), None)
    session['cart'] = cart
    return redirect(url_for('main.cart'))


@bp.route('/cart/remove-custom/<uid>', methods=['POST'])
@login_required
def cart_remove_custom(uid):
    custom_cart = session.get('custom_cart', [])
    session['custom_cart'] = [i for i in custom_cart if i.get('uid') != uid]
    return redirect(url_for('main.cart'))


@bp.route('/cart/update', methods=['POST'])
@login_required
def cart_update():
    cart = session.get('cart', {})
    for key in list(cart.keys()):
        new_qty = request.form.get(f'qty_{key}', type=int)
        if new_qty is not None:
            if new_qty <= 0:
                del cart[key]
            else:
                cart[key] = new_qty
    session['cart'] = cart
    return redirect(url_for('main.cart'))


@bp.route('/cart')
@login_required
def cart():
    cart = session.get('cart', {})
    items = []
    total = 0.0
    for pid, qty in cart.items():
        p = db.session.get(Product, int(pid))
        if p:
            subtotal = round(p.price * qty, 2)
            items.append({'product': p, 'qty': qty, 'subtotal': subtotal})
            total += subtotal

    custom_cart = session.get('custom_cart', [])
    kcal_composti = {}
    for ci in custom_cart:
        total += ci['total_price']
        try:
            from app.dieta import nutrienti_composto
            kcal_composti[ci['uid']] = nutrienti_composto(ci.get('ingredients', []))
        except Exception:
            kcal_composti[ci['uid']] = None

    tid = _effective_tenant_id()
    slots = TimeSlot.query.filter_by(is_active=True, tenant_id=tid).order_by(TimeSlot.time_str).all()
    analisi = None
    profilo = profilo_attivo(current_user) if dieta_enabled() else None
    if profilo and (items or custom_cart):
        from app.dieta import analizza_carrello
        analisi = analizza_carrello(current_user, profilo, cart, custom_cart)
    return render_template('main/cart.html', items=items,
                           custom_cart=custom_cart,
                           total=round(total, 2),
                           slots=slots,
                           wallet=current_user.wallet_balance,
                           analisi_dieta=analisi, kcal_composti=kcal_composti)


# ── Ordine ────────────────────────────────────────────────────────────────────

@bp.route('/order/place', methods=['POST'])
@login_required
def place_order():
    cart = session.get('cart', {})
    custom_cart = session.get('custom_cart', [])

    if not cart and not custom_cart:
        flash('Il carrello è vuoto.', 'warning')
        return redirect(url_for('main.menu'))

    slot_raw = request.form.get('slot_id', '')
    notes    = request.form.get('notes', '').strip()
    banco    = (slot_raw == 'banco')

    if banco:
        slot_id = None
        slot    = None
    else:
        slot_id = int(slot_raw) if slot_raw.isdigit() else None
        slot    = db.session.get(TimeSlot, slot_id) if slot_id else None
        if not slot or not slot.is_active or slot.is_full():
            flash('Slot di ritiro non disponibile. Scegline un altro.', 'danger')
            return redirect(url_for('main.cart'))

    # Valida prodotti regolari
    regular_items = []
    total = 0.0
    for pid, qty in cart.items():
        product = db.session.get(Product, int(pid))
        if not product or not product.is_active:
            flash('Un prodotto non è più disponibile.', 'danger')
            return redirect(url_for('main.menu'))
        if qty > product.available_today():
            flash(f'"{product.name}": disponibili solo {product.available_today()} unità.', 'danger')
            return redirect(url_for('main.cart'))
        regular_items.append((product, qty))
        total += product.price * qty

    # Aggiungi custom items al totale
    for ci in custom_cart:
        total += ci['total_price']

    total = round(total, 2)

    # Dieta: chi ha esclusioni dichiarate non ordina per sbaglio un piatto che
    # le contiene. Non e' un divieto: basta confermare dopo aver letto l'avviso.
    analisi_dieta = None
    profilo_dieta = profilo_attivo(current_user) if dieta_enabled() else None
    if profilo_dieta:
        from app.dieta import analizza_carrello
        analisi_dieta = analizza_carrello(current_user, profilo_dieta, cart, custom_cart)
        if analisi_dieta['ha_incompatibili'] and request.form.get('conferma_dieta') != '1':
            flash('Nel carrello c\'e\' qualcosa che non e\' adatto alle tue esigenze: '
                  'leggi gli avvisi e, se vuoi procedere comunque, conferma.', 'warning')
            return redirect(url_for('main.cart'))

    if wallet_enabled():
        _overdraft = current_user.wallet_overdraft or 0.0
        if current_user.wallet_balance + _overdraft < total:
            flash(f'Saldo wallet insufficiente ({numero_italiano(current_user.wallet_balance)}€). '
                  f'Servono {numero_italiano(total)}€.', 'danger')
            return redirect(url_for('main.wallet'))

    # Crea ordine
    order = Order(user_id=current_user.id, slot_id=slot_id,
                  order_date=date.today(), notes=notes, status='confirmed',
                  tenant_id=_effective_tenant_id())
    db.session.add(order)
    db.session.flush()

    for product, qty in regular_items:
        db.session.add(OrderItem(order_id=order.id, product_id=product.id,
                                 quantity=qty, unit_price=product.price))
        stock = product.get_or_create_stock()
        stock.quantity_reserved += qty

    for ci in custom_cart:
        coi = CustomOrderItem(order_id=order.id, builder_type=ci['type'],
                              label=ci['label'], unit_price=ci['total_price'],
                              grill_requested=ci.get('grill_requested', False))
        db.session.add(coi)
        db.session.flush()
        for ing in ci.get('ingredients', []):
            db.session.add(CustomOrderItemIngredient(
                custom_item_id=coi.id,
                ingredient_name=ing['name'],
                price_extra=ing.get('price_extra', 0.0)
            ))
            if ing.get('id'):
                _ingredient = db.session.get(Ingredient, ing['id'])
                if (_ingredient and _ingredient.stock_qty is not None
                        and _ingredient.grams_per_serving):
                    _ingredient.stock_qty = max(
                        0.0,
                        _ingredient.stock_qty - _ingredient.grams_per_serving * coi.quantity
                    )

    slot_label = 'adesso al banco' if banco else f'alle {slot.time_str}'
    if banco:
        order.order_code = f"BANCO-{order.id:04d}"
    else:
        order.order_code = (
            f"QL-{order.order_date.strftime('%y%m%d')}"
            f"-{slot.time_str.replace(':', '')}"
            f"-{order.id:04d}"
        )
    order.compute_total()
    if wallet_enabled():
        current_user.debit_wallet(total, f'Ordine {order.order_code}', order_id=order.id)
        points = int(total * get_numeric_setting('loyalty_points_per_euro', 10))
        if points:
            current_user.add_points(points)

    db.session.commit()
    session.pop('cart', None)
    session.pop('custom_cart', None)

    # Se il carrello veniva da un giorno del piano, quel giorno e' ordinato.
    _giorno_id = session.pop('dieta_giorno_id', None)
    if _giorno_id:
        _giorno = db.session.get(DietPlanDay, _giorno_id)
        if _giorno and _giorno.plan and _giorno.plan.user_id == current_user.id:
            _giorno.stato = 'ordinato'
            _giorno.order_id = order.id
            db.session.commit()
    _cassa = '' if wallet_enabled() else ' Pagamento alla cassa al ritiro.'
    flash(f'Ordine {order.order_code} confermato! Ritiro {slot_label}.{_cassa}',
          'success')

    # notifica utente
    _riga_dieta = ''
    if analisi_dieta:
        _fabb = analisi_dieta['fabbisogno']
        _riga_dieta = ('\n🥗 Pranzo: <b>%d kcal</b> su una quota di %d · oggi %d/%d kcal'
                       % (analisi_dieta['totale']['kcal'], _fabb['pranzo'],
                          analisi_dieta['totale_giorno'], _fabb['target']))
    send_telegram_to_user(
        current_user,
        f'✅ Ordine <b>{order.order_code}</b> confermato!\n'
        f'Ritiro {slot_label}. Totale: <b>{numero_italiano(total)}€</b>' + _riga_dieta
    )

    # notifica admin / cucina
    lines = [f'🛒 <b>Nuovo ordine</b> — {order.order_code}',
             f'👤 {current_user.full_name}  •  ritiro: <b>{slot_label}</b>',
             f'💶 Totale: <b>{numero_italiano(total)}€</b>', '']
    for item in order.items:
        lines.append(f'  • {item.quantity}× {item.product.name}')
    for ci in order.custom_items:
        grill_tag = ' 🔥 <b>PIASTRA</b>' if ci.grill_requested else ''
        lines.append(f'  • {ci.label}{grill_tag}')
    has_grill = any(ci.grill_requested for ci in order.custom_items)
    if has_grill:
        lines.insert(0, '🔥 <b>PANINO SULLA PIASTRA!</b>')
    send_telegram('\n'.join(lines))

    return redirect(url_for('main.my_orders'))


@bp.route('/orders')
@login_required
def my_orders():
    return render_template('main/my_orders.html')


@bp.route('/orders/dt')
@login_required
def my_orders_dt():
    draw   = request.args.get('draw', 1, type=int)
    start  = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search = (request.args.get('search[value]') or '').strip()
    col    = request.args.get('order[0][column]', 0, type=int)
    dirn   = request.args.get('order[0][dir]', 'desc')
    q = Order.query.filter_by(user_id=current_user.id)
    total = q.count()
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(Order.order_code.ilike(like),
                             Order.status.ilike(like)))
    filtered = q.count()
    col_map = {0: Order.order_code, 1: Order.order_date, 2: Order.total_price, 4: Order.status}
    order_expr = col_map.get(col, Order.created_at)
    q = q.order_by(order_expr.desc() if dirn == 'desc' else order_expr.asc())
    _STATUS = {'pending':('Ricevuto','warning'), 'confirmed':('Confermato','info'),
               'preparing':('In prep.','primary'), 'ready':('Pronto','success'),
               'completed':('Consegnato','success'), 'cancelled':('Annullato','secondary')}
    data = []
    for o in q.offset(start).limit(length).all():
        lbl = _STATUS.get(o.status, (o.status, 'light'))
        items_parts = [f'{it.quantity}× {it.product.name}' for it in o.items]
        for ci in o.custom_items:
            t = '🥪' if ci.builder_type == 'panino' else '🥗'
            items_parts.append(f'{t} Builder')
        can_cancel = o.status in ('pending', 'confirmed')
        data.append({
            'id':           o.id,
            'order_code':   o.order_code or f'#{o.id}',
            'date':         o.order_date.strftime('%d/%m/%Y'),
            'slot':         o.slot.time_str if o.slot else '—',
            'items':        ' · '.join(items_parts) if items_parts else '—',
            'notes':        o.notes or '',
            'total_price':  round(o.total_price, 2),
            'status_label': lbl[0],
            'status_color': lbl[1],
            'can_cancel':   can_cancel,
            'cancel_url':   url_for('main.cancel_order', order_id=o.id),
        })
    return jsonify(draw=draw, recordsTotal=total, recordsFiltered=filtered, data=data)


@bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    order = db.get_or_404(Order, order_id)
    if order.user_id != current_user.id:
        flash('Accesso non autorizzato.', 'danger')
        return redirect(url_for('main.my_orders'))
    if order.status not in ('pending', 'confirmed'):
        flash('Questo ordine non può essere annullato.', 'warning')
        return redirect(url_for('main.my_orders'))

    order.status = 'cancelled'
    if wallet_enabled():
        current_user.credit_wallet(order.total_price,
                                   f'Rimborso ordine #{order.id}', order_id=order.id)
        points_back = int(order.total_price * get_numeric_setting('loyalty_points_per_euro', 10))
        current_user.loyalty_points = max(0, current_user.loyalty_points - points_back)

    for item in order.items:
        stock = DailyStock.query.filter_by(
            product_id=item.product_id, stock_date=date.today()).first()
        if stock:
            stock.quantity_reserved = max(0, stock.quantity_reserved - item.quantity)

    db.session.commit()
    flash(f'Ordine #{order.id} annullato. Rimborso {numero_italiano(order.total_price)}€.', 'info')
    send_telegram_to_user(
        current_user,
        f'❌ Ordine <b>#{order.id}</b> annullato.\n'
        f'Rimborso di <b>{numero_italiano(order.total_price)}€</b> sul tuo wallet.'
    )
    return redirect(url_for('main.my_orders'))


# ── Wallet ────────────────────────────────────────────────────────────────────

@bp.route('/wallet')
@login_required
@wallet_required
def wallet():
    return render_template('main/wallet.html',
                           loyalty_threshold=get_numeric_setting('loyalty_reward_points', 100),
                           reward_amount=get_numeric_setting('loyalty_reward_amount', 1.0))


@bp.route('/wallet/dt')
@login_required
@wallet_required
def wallet_dt():
    draw   = request.args.get('draw', 1, type=int)
    start  = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search = (request.args.get('search[value]') or '').strip()
    col    = request.args.get('order[0][column]', 0, type=int)
    dirn   = request.args.get('order[0][dir]', 'desc')
    q = Transaction.query.filter_by(user_id=current_user.id)
    total = q.count()
    if search:
        like = f'%{search}%'
        q = q.filter(Transaction.description.ilike(like))
    filtered = q.count()
    col_map = {0: Transaction.created_at, 3: Transaction.amount}
    order_expr = col_map.get(col, Transaction.created_at)
    q = q.order_by(order_expr.desc() if dirn == 'desc' else order_expr.asc())
    data = []
    for t in q.offset(start).limit(length).all():
        info = t.icon_info()
        data.append({
            'created_at':  t.created_at.strftime('%d/%m/%Y %H:%M') if t.created_at else '',
            'icon':        info[0],
            'badge_color': info[1],
            'type_label':  info[2],
            'description': t.description or '',
            'amount':      round(t.amount, 2),
        })
    return jsonify(draw=draw, recordsTotal=total, recordsFiltered=filtered, data=data)


@bp.route('/wallet/redeem', methods=['POST'])
@login_required
@wallet_required
def redeem_points():
    threshold = get_numeric_setting('loyalty_reward_points', 100)
    reward = get_numeric_setting('loyalty_reward_amount', 1.0)
    if current_user.loyalty_points < threshold:
        flash(f'Punti insufficienti (servono {threshold}).', 'warning')
        return redirect(url_for('main.wallet'))
    blocks = current_user.loyalty_points // threshold
    earned = blocks * reward
    current_user.redeem_points(blocks * threshold, earned)
    db.session.commit()
    flash(f'+{numero_italiano(earned)}€ aggiunti al wallet!', 'success')
    send_telegram_to_user(
        current_user,
        f'🎁 Hai riscattato i tuoi punti fedeltà!\n'
        f'<b>+{numero_italiano(earned)}€</b> aggiunti al wallet.\n'
        f'💰 Saldo attuale: <b>{numero_italiano(current_user.wallet_balance)}€</b>'
    )
    return redirect(url_for('main.wallet'))


# ── Builder ───────────────────────────────────────────────────────────────────

@bp.route('/builder')
@login_required
def builder():
    builder_type = request.args.get('type', 'panino')
    if builder_type not in ('panino', 'insalata', 'poke'):
        builder_type = 'panino'

    tid = _effective_tenant_id()
    categories = IngredientCategory.query.filter(
        IngredientCategory.builder_type.in_([builder_type, 'both']),
        IngredientCategory.tenant_id == tid,
    ).order_by(IngredientCategory.sort_order).all()

    base_price = get_numeric_setting(f'builder_price_{builder_type}', Config.BUILDER_PRICES.get(builder_type, 3.50))
    return render_template('main/builder.html',
                           builder_type=builder_type,
                           categories=categories,
                           base_price=base_price,
                           config=Config)


@bp.route('/builder/add', methods=['POST'])
@login_required
def builder_add():
    builder_type = request.form.get('builder_type', 'panino')
    if builder_type not in ('panino', 'insalata', 'poke'):
        flash('Tipo non valido.', 'danger')
        return redirect(url_for('main.builder'))

    # Raccoglie ingredienti selezionati (field name: ing_<id>)
    tid = _effective_tenant_id()
    categories = IngredientCategory.query.filter(
        IngredientCategory.builder_type.in_([builder_type, 'both']),
        IngredientCategory.tenant_id == tid,
    ).order_by(IngredientCategory.sort_order).all()

    selected_ids = []
    for key in request.form:
        if key.startswith('ing_'):
            try:
                selected_ids.append(int(key[4:]))
            except ValueError:
                pass

    # Valida required categories
    for cat in categories:
        if cat.is_required:
            cat_ids = {i.id for i in cat.ingredients if i.is_active}
            if not any(sid in cat_ids for sid in selected_ids):
                flash(f'Seleziona almeno un ingrediente per "{cat.name}".', 'danger')
                return redirect(url_for('main.builder', type=builder_type))
        selected_in_cat = [i for i in cat.ingredients
                           if i.is_active and i.id in selected_ids]
        if len(selected_in_cat) > cat.max_choices:
            flash(f'"{cat.name}": massimo {cat.max_choices} scelte.', 'danger')
            return redirect(url_for('main.builder', type=builder_type))

    ingredients_data = []
    extra_price = 0.0
    for ing_id in selected_ids:
        ing = db.session.get(Ingredient, ing_id)
        if ing and ing.is_active:
            ingredients_data.append({
                'id': ing.id,
                'name': ing.name,
                'price_extra': ing.price_extra,
                'cat': ing.category.name,
            })
            extra_price += ing.price_extra

    base_price = get_numeric_setting(f'builder_price_{builder_type}', Config.BUILDER_PRICES.get(builder_type, 3.50))
    total_price = round(base_price + extra_price, 2)
    grill_requested = (builder_type == 'panino' and
                       request.form.get('grill_requested', '0') == '1')

    _meta = {'panino': ('Panino', 'o', 'o'), 'insalata': ('Insalata', 'a', 'a'), 'poke': ('Poke', 'o', 'o')}
    type_name, gen_adj, gen_add = _meta[builder_type]

    names = [i['name'] for i in ingredients_data]
    grill_tag = ' 🔥' if grill_requested else ''
    label = f"{type_name} personalizzat{gen_adj}{grill_tag}: " + ', '.join(names)

    custom_cart = session.get('custom_cart', [])
    custom_cart.append({
        'uid': secrets.token_hex(8),
        'type': builder_type,
        'base_price': base_price,
        'extra_price': round(extra_price, 2),
        'total_price': total_price,
        'label': label,
        'grill_requested': grill_requested,
        'ingredients': ingredients_data,
    })
    session['custom_cart'] = custom_cart
    flash(f'{type_name} personalizzat{gen_adj}{grill_tag} aggiunt{gen_add} al carrello!', 'success')
    return redirect(url_for('main.cart'))


# ── Builder Visuale ───────────────────────────────────────────────────────────

@bp.route('/builder-visual')
@login_required
def builder_visual():
    builder_type = request.args.get('type')
    if builder_type not in ('panino', 'insalata', 'poke'):
        builder_type = None

    categories = []
    base_price = 0.0
    if builder_type:
        categories = IngredientCategory.query.filter(
            IngredientCategory.builder_type.in_([builder_type, 'both'])
        ).order_by(IngredientCategory.sort_order).all()
        base_price = get_numeric_setting(f'builder_price_{builder_type}', Config.BUILDER_PRICES.get(builder_type, 3.50))

    return render_template('main/builder_visual.html',
                           builder_type=builder_type,
                           categories=categories,
                           base_price=base_price,
                           config=Config)


# ── Tavoli ────────────────────────────────────────────────────────────────────

@bp.route('/tables')
@login_required
@tables_required
def tables():
    from app.models import TableTimeBand
    res_date_str = request.args.get('d', str(date.today()))
    try:
        from datetime import datetime as _dt
        res_date = _dt.strptime(res_date_str, '%Y-%m-%d').date()
    except ValueError:
        res_date = date.today()
        res_date_str = str(res_date)

    all_tables = Table.query.filter_by(is_active=True).order_by(Table.number).all()
    bands = TableTimeBand.query.order_by(TableTimeBand.sort_order, TableTimeBand.start_time).all()

    # Prenotazioni attive del giorno indicizzate per (table_id, session_start)
    day_res = (TableReservation.query
               .filter_by(reservation_date=res_date)
               .filter(TableReservation.status != 'cancelled')
               .all())
    res_index = {(r.table_id, r.session_start): r for r in day_res}

    # Prenotazioni dell'utente per il giorno
    my_starts = {r.session_start for r in day_res if r.user_id == current_user.id}

    from datetime import timedelta as _td
    prev_day = (res_date - _td(days=1)).isoformat()
    next_day = (res_date + _td(days=1)).isoformat()

    return render_template('main/tables.html',
                           tables=all_tables, bands=bands,
                           res_index=res_index, my_starts=my_starts,
                           res_date=res_date, res_date_str=res_date_str,
                           today=str(date.today()),
                           prev_day=prev_day, next_day=next_day)


@bp.route('/tables/book', methods=['POST'])
@login_required
@tables_required
def table_book():
    from app.models import TableTimeBand
    table_id      = request.form.get('table_id', type=int)
    band_id       = request.form.get('band_id', type=int)
    session_start = request.form.get('session_start', '').strip()
    party_size    = request.form.get('party_size', type=int, default=1)
    notes         = request.form.get('notes', '').strip()
    res_date_str  = request.form.get('res_date', str(date.today()))
    try:
        from datetime import datetime as _dt
        res_date = _dt.strptime(res_date_str, '%Y-%m-%d').date()
    except ValueError:
        res_date = date.today()
        res_date_str = str(res_date)

    table = db.get_or_404(Table, table_id)
    band  = db.get_or_404(TableTimeBand, band_id)

    if not table.is_active:
        flash('Tavolo non disponibile.', 'danger')
        return redirect(url_for('main.tables', d=res_date_str))

    if session_start not in band.computed_slots():
        flash('Orario non valido per questa fascia.', 'danger')
        return redirect(url_for('main.tables', d=res_date_str))

    if party_size > table.seats:
        flash(f'Il tavolo {table.number} ha solo {table.seats} posti.', 'warning')
        return redirect(url_for('main.tables', d=res_date_str))

    conflict = (TableReservation.query
                .filter_by(table_id=table_id, reservation_date=res_date,
                           session_start=session_start)
                .filter(TableReservation.status != 'cancelled')
                .first())
    if conflict:
        flash('Tavolo già prenotato per questo orario.', 'warning')
        return redirect(url_for('main.tables', d=res_date_str))

    is_pg = db.engine.url.drivername.startswith('postgresql')
    slot_sentinel = None if is_pg else 0

    res = TableReservation(
        user_id=current_user.id, table_id=table_id,
        band_id=band_id, session_start=session_start,
        slot_id=slot_sentinel,
        reservation_date=res_date,
        party_size=party_size, notes=notes, status='confirmed',
        tenant_id=_effective_tenant_id()
    )
    db.session.add(res)
    db.session.commit()
    flash(f'Tavolo {table.number} prenotato per le {session_start}!', 'success')

    date_label = res_date.strftime('%d/%m/%Y')
    # notifica utente
    send_telegram_to_user(
        current_user,
        f'🪑 Prenotazione confermata!\n'
        f'Tavolo <b>{table.number}</b> ({table.seats} posti) — '
        f'<b>{session_start}</b> del {date_label}'
    )
    # notifica admin
    send_telegram(
        f'🪑 <b>Nuova prenotazione tavolo</b>\n'
        f'👤 {current_user.full_name}\n'
        f'🪑 Tavolo <b>{table.number}</b> — <b>{session_start}</b> — {date_label}\n'
        f'👥 {party_size} person{"a" if party_size == 1 else "e"}'
        + (f'\n📝 {notes}' if notes else '')
    )
    return redirect(url_for('main.my_reservations'))


@bp.route('/reservations')
@login_required
@tables_required
def my_reservations():
    return render_template('main/my_reservations.html', today_date=date.today())


@bp.route('/reservations/dt')
@login_required
@tables_required
def my_reservations_dt():
    draw   = request.args.get('draw', 1, type=int)
    start  = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search = (request.args.get('search[value]') or '').strip()
    col    = request.args.get('order[0][column]', 0, type=int)
    dirn   = request.args.get('order[0][dir]', 'desc')
    from app.models import Table as TableModel
    q = TableReservation.query.join(
        TableModel, TableReservation.table_id == TableModel.id
    ).filter(TableReservation.user_id == current_user.id)
    total = q.count()
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(TableReservation.status.ilike(like),
                             TableReservation.notes.ilike(like)))
    filtered = q.count()
    col_map = {0: TableReservation.reservation_date, 1: TableModel.number,
               5: TableReservation.status}
    order_expr = col_map.get(col, TableReservation.reservation_date)
    q = q.order_by(order_expr.desc() if dirn == 'desc' else order_expr.asc())
    today = date.today()
    data = []
    for r in q.offset(start).limit(length).all():
        lbl = r.label()
        can_cancel = r.status == 'confirmed' and r.reservation_date >= today
        data.append({
            'date':        r.reservation_date.strftime('%d/%m/%Y'),
            'table_num':   r.table.number,
            'table_seats': r.table.seats,
            'location':    r.table.location or '',
            'slot':        r.slot.time_str if r.slot else '—',
            'party_size':  r.party_size,
            'notes':       r.notes or '',
            'status_label': lbl[0],
            'status_color': lbl[1],
            'can_cancel':   can_cancel,
            'cancel_url':   url_for('main.cancel_reservation', rid=r.id),
        })
    return jsonify(draw=draw, recordsTotal=total, recordsFiltered=filtered, data=data)


@bp.route('/reservations/<int:rid>/cancel', methods=['POST'])
@login_required
@tables_required
def cancel_reservation(rid):
    res = db.get_or_404(TableReservation, rid)
    if res.user_id != current_user.id:
        flash('Accesso non autorizzato.', 'danger')
        return redirect(url_for('main.my_reservations'))
    if res.status == 'cancelled':
        flash('Prenotazione già annullata.', 'warning')
        return redirect(url_for('main.my_reservations'))
    res.status = 'cancelled'
    db.session.commit()
    flash(f'Prenotazione tavolo {res.table.number} annullata.', 'info')
    send_telegram(
        f'❌ <b>Prenotazione annullata</b> (dall\'utente)\n'
        f'👤 {current_user.full_name}\n'
        f'🪑 Tavolo <b>{res.table.number}</b> — <b>{res.session_start}</b> — '
        f'{res.reservation_date.strftime("%d/%m/%Y")}'
    )
    send_telegram_to_user(
        current_user,
        f'❌ Prenotazione tavolo <b>{res.table.number}</b> annullata.\n'
        f'Orario: <b>{res.session_start}</b> — {res.reservation_date.strftime("%d/%m/%Y")}'
    )
    return redirect(url_for('main.my_reservations'))


# ── Sondaggi ──────────────────────────────────────────────────────────────────

@bp.route('/poll')
@login_required
def poll_index():
    """Reindirizza al sondaggio attivo più recente, o mostra messaggio."""
    active = Poll.query.filter_by(is_active=True)\
                       .order_by(Poll.poll_date.desc()).first()
    if active:
        return redirect(url_for('main.poll_view', pid=active.id))
    return render_template('main/poll.html', poll=None)


@bp.route('/poll/<int:pid>')
@login_required
def poll_view(pid):
    poll      = db.get_or_404(Poll, pid)
    user_vote = poll.user_vote(current_user.id)
    total     = poll.total_votes()
    return render_template('main/poll.html',
                           poll=poll,
                           user_vote=user_vote,
                           total=total)


@bp.route('/poll/<int:pid>/vote', methods=['POST'])
@login_required
def poll_vote(pid):
    poll      = db.get_or_404(Poll, pid)
    if not poll.is_active:
        flash('Questo sondaggio è chiuso.', 'warning')
        return redirect(url_for('main.poll_view', pid=pid))
    if poll.user_vote(current_user.id):
        flash('Hai già votato in questo sondaggio.', 'warning')
        return redirect(url_for('main.poll_view', pid=pid))
    choice_id  = request.form.get('choice_id', type=int)
    choice     = PollChoice.query.filter_by(id=choice_id, poll_id=pid).first()
    if not choice:
        flash('Scelta non valida.', 'danger')
        return redirect(url_for('main.poll_view', pid=pid))
    confirm_res = 'confirm_reservation' in request.form
    db.session.add(PollVote(poll_id=pid, choice_id=choice_id,
                            user_id=current_user.id,
                            confirm_reservation=confirm_res))
    if confirm_res:
        res = TableReservation.query.filter_by(
            user_id=current_user.id,
            reservation_date=poll.poll_date,
        ).filter(TableReservation.status != 'cancelled').first()
        if res:
            res.status = 'confirmed'
        flash(f'Voto registrato: {choice.emoji} {choice.text} — prenotazione confermata!', 'success')
    else:
        flash(f'Voto registrato: {choice.emoji} {choice.text}', 'success')
    db.session.commit()
    return redirect(url_for('main.poll_view', pid=pid))


# â”€â”€ Pasto aziendale convenzionato â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@bp.route('/pasto-aziendale')
@login_required
def pasto_aziendale():
    membership = getattr(current_user, 'corporate_membership', None)
    if not membership or not membership.is_active:
        flash('Non sei associato a nessuna convenzione aziendale.', 'warning')
        return redirect(url_for('main.index'))

    corp  = membership.corporate
    today = date.today()
    meals = DailyFixedMeal.query.filter_by(
        corporate_id=corp.id, meal_date=today, is_active=True
    ).order_by(DailyFixedMeal.name).all()

    # prenotazione attiva dell'utente per oggi (su qualsiasi opzione)
    my_booking = None
    if meals:
        meal_ids = [m.id for m in meals]
        my_booking = CorporateMealBooking.query.filter(
            CorporateMealBooking.user_id == current_user.id,
            CorporateMealBooking.meal_id.in_(meal_ids),
            CorporateMealBooking.status != 'cancelled',
        ).first()

    slots = TimeSlot.query.filter_by(is_active=True).order_by(TimeSlot.time_str).all()

    can_cancel = True
    if my_booking and my_booking.slot:
        try:
            slot_time = datetime.strptime(my_booking.slot.time_str, '%H:%M').time()
            slot_dt   = datetime.combine(date.today(), slot_time)
            can_cancel = (slot_dt - datetime.now()) >= timedelta(minutes=30)
        except Exception:
            can_cancel = True

    compat_pasti = {}
    _profilo = profilo_attivo(current_user) if dieta_enabled() else None
    if _profilo:
        from app.dieta import compatibilita
        for m in meals:
            ok, motivi = compatibilita(m, _profilo)
            compat_pasti[m.id] = {'ok': ok, 'motivi': motivi}

    return render_template('main/pasto_aziendale.html',
                           corp=corp, meals=meals, my_booking=my_booking,
                           slots=slots, today=today, can_cancel=can_cancel,
                           compat_pasti=compat_pasti, profilo_dieta=_profilo)


@bp.route('/pasto-aziendale/prenota', methods=['POST'])
@login_required
def pasto_aziendale_prenota():
    membership = getattr(current_user, 'corporate_membership', None)
    if not membership or not membership.is_active:
        flash('Non sei associato a nessuna convenzione aziendale.', 'warning')
        return redirect(url_for('main.index'))

    corp    = membership.corporate
    today   = date.today()
    meal_id = request.form.get('meal_id', type=int)
    meal    = DailyFixedMeal.query.get_or_404(meal_id)

    if meal.corporate_id != corp.id or meal.meal_date != today or not meal.is_active:
        flash('Opzione non disponibile.', 'danger')
        return redirect(url_for('main.pasto_aziendale'))

    quantity = max(1, request.form.get('quantity', 1, type=int))
    slot_id  = request.form.get('slot_id') or None
    if slot_id:
        slot_id = int(slot_id)

    # verifica unicit\u00e0: una sola opzione prenotata per giorno
    today_meal_ids = [
        m.id for m in DailyFixedMeal.query.filter_by(
            corporate_id=corp.id, meal_date=today).all()
    ]
    conflict = CorporateMealBooking.query.filter(
        CorporateMealBooking.user_id == current_user.id,
        CorporateMealBooking.meal_id.in_(today_meal_ids),
        CorporateMealBooking.meal_id != meal_id,
        CorporateMealBooking.status != 'cancelled',
    ).first()
    if conflict:
        flash(f'Hai gi\u00e0 prenotato "{conflict.meal.name}" oggi. '
              'Annulla quella prenotazione prima di sceglierne un\'altra.', 'warning')
        return redirect(url_for('main.pasto_aziendale'))

    existing = CorporateMealBooking.query.filter_by(
        user_id=current_user.id, meal_id=meal.id).first()

    if existing:
        available = meal.slots_left + (existing.quantity or 1)
        if quantity > available:
            flash(f'Posti insufficienti. Massimo {available} porzioni.', 'danger')
            return redirect(url_for('main.pasto_aziendale'))
        existing.quantity = quantity
        existing.slot_id  = slot_id
        if existing.status == 'cancelled':
            existing.status = 'booked'
        if not existing.pickup_token:
            existing.pickup_token = secrets.token_hex(3).upper()
        db.session.commit()
        send_telegram_to_user(current_user,
            f'\ud83c\udf7d\ufe0f Prenotazione aggiornata: {quantity} porzioni di <b>{meal.name}</b>')
        flash(f'Prenotazione aggiornata: {quantity} porzioni di "{meal.name}".', 'success')
    else:
        if not meal.is_available or quantity > meal.slots_left:
            flash(f'Posti insufficienti. Disponibili: {meal.slots_left}.', 'danger')
            return redirect(url_for('main.pasto_aziendale'))
        booking = CorporateMealBooking(
            user_id=current_user.id, meal_id=meal.id,
            slot_id=slot_id, quantity=quantity, status='booked')
        booking.pickup_token = secrets.token_hex(3).upper()
        db.session.add(booking)
        db.session.commit()
        send_telegram_to_user(current_user,
            f'\ud83c\udf7d\ufe0f Prenotazione confermata: {quantity} porzioni di <b>{meal.name}</b>')
        flash(f'Pasto prenotato: {quantity} porzioni di "{meal.name}".', 'success')

    return redirect(url_for('main.pasto_aziendale'))


@bp.route('/pasto-aziendale/cancella', methods=['POST'])
@login_required
def pasto_aziendale_cancella():
    bid = request.form.get('booking_id', type=int)
    if not bid:
        return redirect(url_for('main.pasto_aziendale'))
    booking = CorporateMealBooking.query.filter_by(
        id=bid, user_id=current_user.id).first()
    if booking and booking.status == 'booked':
        can_cancel = True
        if booking.slot:
            try:
                slot_time = datetime.strptime(booking.slot.time_str, '%H:%M').time()
                slot_dt   = datetime.combine(date.today(), slot_time)
                can_cancel = (slot_dt - datetime.now()) >= timedelta(minutes=30)
            except Exception:
                can_cancel = True
        if can_cancel:
            meal_name = booking.meal.name
            booking.status = 'cancelled'
            db.session.commit()
            flash('Prenotazione annullata.', 'info')
            send_telegram_to_user(
                current_user,
                f'❌ Prenotazione pasto annullata: <b>{meal_name}</b>'
            )
        else:
            flash('Non è più possibile annullare: mancano meno di 30 minuti alla consegna.', 'warning')
    return redirect(url_for('main.pasto_aziendale'))


# ── Guida utente ─────────────────────────────────────────────────────────────


# ── Dieta settimanale ──────────────────────────────────────────────────────────

def _profilo_del_cliente_o_404(gid):
    """Il giorno del piano, solo se appartiene a chi lo chiede."""
    giorno = db.get_or_404(DietPlanDay, gid)
    if not giorno.plan or giorno.plan.user_id != current_user.id:
        from flask import abort
        abort(404)
    return giorno


@bp.route('/dieta')
@login_required
@dieta_required
def dieta():
    from app.dieta import fabbisogno, inizio_settimana, riepilogo_giornata
    profilo = current_user.diet_profile
    fabb = piano = riepilogo = None
    if profilo:
        fabb = fabbisogno(profilo, current_user)
        piano = DietPlan.query.filter_by(user_id=current_user.id,
                                         week_start=inizio_settimana()).first()
        if profilo.attivo:
            riepilogo = riepilogo_giornata(current_user, profilo)
    return render_template('main/dieta.html', profilo=profilo, fabb=fabb,
                           piano=piano, riepilogo=riepilogo, oggi=date.today(),
                           condizioni=CONDIZIONI_DIETA, regimi=REGIMI_DIETA,
                           obiettivi=OBIETTIVI_DIETA, attivita=ATTIVITA_DIETA,
                           giorni_settimana=GIORNI_SETTIMANA, allergeni=ALLERGENS)


@bp.route('/dieta/profilo', methods=['POST'])
@login_required
@dieta_required
def dieta_profilo():
    """Salva le preferenze; con `genera` prepara subito il piano."""
    from app.dieta import genera_piano

    profilo = current_user.diet_profile
    nuovo = profilo is None
    if request.form.get('presa_atto') != '1':
        flash('Per salvare devi confermare di aver letto che le indicazioni della '
              'dieta non hanno validità medica.', 'warning')
        return redirect(url_for('main.dieta'))
    if nuovo:
        profilo = DietProfile(user_id=current_user.id,
                              tenant_id=_effective_tenant_id())
        db.session.add(profilo)

    chiavi_cond = {c[0] for c in CONDIZIONI_DIETA}
    profilo.condizioni = ','.join(c for c in request.form.getlist('condizioni')
                                  if c in chiavi_cond)
    chiavi_all = {a[0] for a in ALLERGENS}
    profilo.esclusioni = ','.join(a for a in request.form.getlist('esclusioni')
                                  if a in chiavi_all)
    regime = request.form.get('regime', 'onnivoro')
    profilo.regime = regime if regime in {r[0] for r in REGIMI_DIETA} else 'onnivoro'
    obiettivo = request.form.get('obiettivo', 'mantenimento')
    profilo.obiettivo = (obiettivo if obiettivo in {o[0] for o in OBIETTIVI_DIETA}
                         else 'mantenimento')
    attivita = request.form.get('attivita', 'sedentaria')
    profilo.attivita = (attivita if attivita in {a[0] for a in ATTIVITA_DIETA}
                        else 'sedentaria')
    sesso = request.form.get('sesso', '').strip().upper()
    profilo.sesso = sesso if sesso in ('M', 'F') else ''

    def _numero(nome, minimo, massimo, intero=False):
        grezzo = (request.form.get(nome) or '').strip().replace(',', '.')
        if not grezzo:
            return None
        try:
            v = float(grezzo)
        except ValueError:
            return None
        if not (minimo <= v <= massimo):
            return None
        return int(round(v)) if intero else v

    profilo.peso_kg = _numero('peso_kg', 30, 250)
    profilo.altezza_cm = _numero('altezza_cm', 120, 230)
    profilo.kcal_manuali = _numero('kcal_manuali', 1000, 5000, intero=True)
    quota = _numero('quota_pranzo', 25, 60, intero=True)
    profilo.quota_pranzo = (quota / 100.0) if quota else 0.40
    profilo.budget_pranzo = _numero('budget_pranzo', 1, 100)
    chiavi_giorni = {g[0] for g in GIORNI_SETTIMANA}
    giorni = [g for g in request.form.getlist('giorni') if g in chiavi_giorni]
    profilo.giorni = ','.join(giorni) if giorni else 'lun,mar,mer,gio,ven'
    profilo.avvisi = request.form.get('avvisi') == '1'
    profilo.note = (request.form.get('note') or '').strip()[:1000]
    profilo.attivo = True
    db.session.commit()

    if request.form.get('genera') == '1':
        genera_piano(current_user, profilo)
        flash('Preferenze salvate e piano della settimana pronto.', 'success')
    else:
        flash('Preferenze salvate.' if not nuovo else
              'Dieta attivata: da adesso menu e carrello tengono conto delle tue esigenze.',
              'success')
    return redirect(url_for('main.dieta'))


@bp.route('/dieta/genera', methods=['POST'])
@login_required
@dieta_required
def dieta_genera():
    from app.dieta import genera_piano
    profilo = profilo_attivo(current_user)
    if not profilo:
        flash('Prima imposta le tue preferenze.', 'warning')
        return redirect(url_for('main.dieta'))
    piano = genera_piano(current_user, profilo)
    proposti = [d for d in piano.days if d.voci]
    if proposti:
        flash('Piano della settimana pronto: %d pranz%s proposti.'
              % (len(proposti), 'o' if len(proposti) == 1 else 'i'), 'success')
    else:
        flash('Non sono riuscito a comporre nessun pranzo: il listino non ha piatti '
              'compatibili con le tue esigenze, o mancano i valori nutrizionali.', 'warning')
    return redirect(url_for('main.dieta'))


@bp.route('/dieta/giorno/<int:gid>/ordina', methods=['POST'])
@login_required
@dieta_required
def dieta_ordina_giorno(gid):
    """Mette nel carrello il pranzo del giorno: si conferma dal carrello."""
    from app.dieta import carrello_da_giorno
    giorno = _profilo_del_cliente_o_404(gid)
    carrello, mancanti = carrello_da_giorno(giorno)
    if not carrello:
        flash('Nessuno dei prodotti di questo pranzo e\' ordinabile oggi.', 'warning')
        return redirect(url_for('main.dieta'))
    session['cart'] = carrello
    session['custom_cart'] = []
    session['dieta_giorno_id'] = giorno.id
    if mancanti:
        flash('Non disponibili oggi e tolti dal carrello: %s.' % ', '.join(mancanti),
              'warning')
    flash('Pranzo di %s nel carrello: scegli l\'orario di ritiro e conferma.'
          % giorno.etichetta_giorno.lower(), 'success')
    return redirect(url_for('main.cart'))


@bp.route('/dieta/giorno/<int:gid>/rigenera', methods=['POST'])
@login_required
@dieta_required
def dieta_rigenera_giorno(gid):
    from app.dieta import rigenera_giorno
    giorno = _profilo_del_cliente_o_404(gid)
    profilo = profilo_attivo(current_user)
    if not profilo:
        return redirect(url_for('main.dieta'))
    if giorno.stato == 'ordinato':
        flash('Questo pranzo e\' gia\' stato ordinato.', 'info')
    elif rigenera_giorno(giorno, profilo, current_user):
        flash('Nuova proposta per %s.' % giorno.etichetta_giorno.lower(), 'success')
    else:
        flash('Nessuna alternativa compatibile nel listino.', 'warning')
    return redirect(url_for('main.dieta'))


@bp.route('/dieta/stato', methods=['POST'])
@login_required
@dieta_required
def dieta_stato():
    """Sospende o riattiva la dieta senza perdere le preferenze."""
    profilo = current_user.diet_profile
    if not profilo:
        return redirect(url_for('main.dieta'))
    profilo.attivo = request.form.get('attivo') == '1'
    db.session.commit()
    flash('Dieta riattivata.' if profilo.attivo else
          'Dieta sospesa: menu e carrello tornano senza avvisi.', 'info')
    return redirect(url_for('main.dieta'))


@bp.route('/guida')
@login_required
def guida():
    is_cassiere = current_user.has_role('cassiere')
    is_cuoco    = current_user.has_role('cuoco')
    is_manager  = current_user.has_role('manager') or current_user.is_admin
    is_cliente  = not (current_user.is_admin or current_user.is_staff)
    has_corp    = bool(getattr(current_user, 'corporate_membership', None)
                        and current_user.corporate_membership.is_active)
    return render_template('main/guida.html',
                            is_cassiere=is_cassiere, is_cuoco=is_cuoco,
                            is_manager=is_manager, is_cliente=is_cliente,
                            has_corp=has_corp)


# ── Banco QR Pay ──────────────────────────────────────────────────────────────

@bp.route('/banco/scan')
@login_required
def banco_scan():
    return render_template('main/banco_scan.html')


@bp.route('/banco/pay/<token>')
@login_required
def banco_pay(token):
    import json
    sess = BancoSession.query.filter_by(token=token).first_or_404()
    if sess.status == 'pending' and datetime.utcnow() > sess.expires_at:
        sess.status = 'expired'
        db.session.commit()
    try:
        items = json.loads(sess.items_json)
    except Exception:
        items = []
    return render_template('main/banco_pay.html', sess=sess, items=items)


@bp.route('/banco/pay/<token>/confirm', methods=['POST'])
@login_required
def banco_pay_confirm(token):
    import json
    sess = BancoSession.query.filter_by(token=token).first_or_404()
    if sess.status != 'pending':
        flash('Questa sessione non è più valida.', 'warning')
        return redirect(url_for('main.index'))
    if datetime.utcnow() > sess.expires_at:
        sess.status = 'expired'
        db.session.commit()
        flash('QR scaduto. Chiedi al personale di generarne uno nuovo.', 'danger')
        return redirect(url_for('main.index'))
    if wallet_enabled():
        _overdraft = current_user.wallet_overdraft or 0.0
        if current_user.wallet_balance + _overdraft < sess.total:
            flash(f'Saldo insufficiente ({numero_italiano(current_user.wallet_balance)}€). Ricarica il wallet.', 'danger')
            return redirect(url_for('main.banco_pay', token=token))
    try:
        items = json.loads(sess.items_json)
    except Exception:
        items = []
    lines = ', '.join(f"{i['qty']}× {i['name']}" for i in items)
    if wallet_enabled():
        current_user.debit_wallet(sess.total, f'Banco: {lines}')
        # marca ttype come banco
        from app.models import Transaction
        last_tx = Transaction.query.filter_by(user_id=current_user.id)\
            .order_by(Transaction.id.desc()).first()
        if last_tx:
            last_tx.ttype = 'banco'
    sess.status      = 'paid'
    sess.customer_id = current_user.id
    db.session.commit()
    if wallet_enabled():
        flash(f'Pagamento di {numero_italiano(sess.total)}€ confermato!', 'success')
        send_telegram_to_user(
            current_user,
            f'☕ Pagamento banco confermato: <b>{numero_italiano(sess.total)}€</b>\n'
            f'💰 Saldo residuo: <b>{numero_italiano(current_user.wallet_balance)}€</b>'
        )
    else:
        flash(f'Consumazione di {numero_italiano(sess.total)}€ registrata. '
              f'Paga alla cassa.', 'success')
    return redirect(url_for('main.index'))


# ── Profilo utente ───────────────────────────────────────────────────────────

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    from datetime import datetime as _dt
    if request.method == 'POST':
        action = request.form.get('action', 'info')

        if action == 'info':
            current_user.first_name = request.form.get('first_name', '').strip()
            current_user.last_name  = request.form.get('last_name',  '').strip()
            current_user.phone      = request.form.get('phone',      '').strip()
            current_user.address    = request.form.get('address',    '').strip()
            current_user.telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
            birth_raw = request.form.get('birth_date', '').strip()
            if birth_raw:
                try:
                    current_user.birth_date = _dt.strptime(birth_raw, '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                current_user.birth_date = None
            db.session.commit()
            flash('Profilo aggiornato.', 'success')

        elif action == 'password':
            if current_user.google_id:
                flash('Gli account Google non hanno una password locale.', 'warning')
            else:
                current_pw  = request.form.get('current_password', '')
                new_pw      = request.form.get('new_password', '')
                confirm_pw  = request.form.get('confirm_password', '')
                if not current_user.check_password(current_pw):
                    flash('Password attuale non corretta.', 'danger')
                elif len(new_pw) < 6:
                    flash('La nuova password deve essere di almeno 6 caratteri.', 'danger')
                elif new_pw != confirm_pw:
                    flash('Le password non coincidono.', 'danger')
                else:
                    current_user.set_password(new_pw)
                    db.session.commit()
                    flash('Password aggiornata.', 'success')

        return redirect(url_for('main.profile'))

    return render_template('main/profile.html')


# ── Auto-cancellazione account utente ────────────────────────────────────────

@bp.route('/account/delete', methods=['POST'])
@login_required
def account_delete():
    if current_user.is_admin or current_user.is_staff:
        flash('Gli account staff non possono essere cancellati da qui.', 'danger')
        return redirect(url_for('main.index'))
    if (wallet_enabled() and current_user.wallet_balance
            and current_user.wallet_balance > 0):
        flash(
            f'Impossibile cancellare l\'account: hai ancora '
            f'{numero_italiano(current_user.wallet_balance)}€ nel wallet. '
            f'Contatta l\'amministratore per il rimborso prima di procedere.',
            'danger',
        )
        return redirect(url_for('main.index'))

    from flask_login import logout_user
    from sqlalchemy import text as _text
    uid = current_user.id

    # cascade delete (ordini → transazioni → prenotazioni → voti → membership → utente)
    order_ids = db.session.query(Order.id).filter_by(user_id=uid).subquery()
    coi_ids   = db.session.query(CustomOrderItem.id).filter(
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
    Transaction.query.filter(
        Transaction.order_id.in_(order_ids)
    ).update({'order_id': None}, synchronize_session=False)
    Order.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Transaction.query.filter_by(user_id=uid).delete(synchronize_session=False)
    TableReservation.query.filter_by(user_id=uid).delete(synchronize_session=False)
    PollVote.query.filter_by(user_id=uid).delete(synchronize_session=False)
    CorporateMembership.query.filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.execute(_text('DELETE FROM user_roles WHERE user_id = :uid'), {'uid': uid})
    User.query.filter_by(id=uid).delete(synchronize_session=False)
    db.session.commit()

    logout_user()
    flash('Il tuo account è stato cancellato.', 'info')
    return redirect(url_for('auth.login'))


# ── CESTO: lookup prodotto per barcode (EAN) ─────────────────────────────────

@bp.route('/api/product/barcode/<ean>')
@login_required
@cesto_required
def api_product_by_barcode(ean):
    tid = current_user.tenant_id
    p = Product.query.filter_by(
        barcode=ean.strip(), tenant_id=tid, is_active=True
    ).first()
    if not p:
        return jsonify({'error': 'Prodotto non trovato'}), 404
    return jsonify({'id': p.id, 'name': p.name, 'price': p.price})


# ── CESTO: lista disponibili + scanner ────────────────────────────────────────

@bp.route('/cesto')
@login_required
@cesto_required
def cesto_lista():
    from collections import defaultdict
    tid    = current_user.tenant_id
    labels = (PrepLabel.query
              .filter_by(tenant_id=tid, status='ready')
              .order_by(PrepLabel.product_id, PrepLabel.prepared_at)
              .all())
    by_product = defaultdict(list)
    for lb in labels:
        by_product[lb.product_id].append(lb)
    return render_template('main/cesto_lista.html', labels=labels, by_product=dict(by_product))


# ── CESTO: scansione etichetta QR ─────────────────────────────────────────────

@bp.route('/cesto/<code>')
@login_required
@cesto_required
def cesto_scan(code):
    from datetime import datetime as _dtm, timezone
    lb = PrepLabel.query.filter_by(code=code.upper()).first_or_404()
    # etichette di ieri o più vecchie scadono automaticamente
    if lb.status == 'ready':
        age_hours = (datetime.now(timezone.utc) - lb.prepared_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if age_hours > 24:
            lb.status = 'expired'
            db.session.commit()
    return render_template('main/cesto_scan.html', lb=lb)


@bp.route('/cesto/<code>/acquista', methods=['POST'])
@login_required
@cesto_required
def cesto_acquista(code):
    lb = PrepLabel.query.filter_by(code=code.upper()).first_or_404()
    if lb.status != 'ready':
        flash('Questo prodotto non è più disponibile.', 'danger')
        return redirect(url_for('main.cesto_scan', code=code))

    # Raccoglie extra (lattine/snack scansionati)
    try:
        extra_ids = json.loads(request.form.get('extras', '[]'))
        if not isinstance(extra_ids, list):
            extra_ids = []
    except (ValueError, TypeError):
        extra_ids = []

    extra_products = []
    if extra_ids:
        tid = current_user.tenant_id
        for eid in extra_ids[:10]:  # max 10 extra
            ep = Product.query.filter_by(id=int(eid), tenant_id=tid, is_active=True).first()
            if ep:
                extra_products.append(ep)

    total = lb.product.price + sum(p.price for p in extra_products)
    if wallet_enabled():
        balance = current_user.wallet_balance or 0
        if balance < total:
            flash(
                f'Saldo insufficiente. Hai {numero_italiano(balance)} €, serve {numero_italiano(total)} €.',
                'danger',
            )
            return redirect(url_for('main.cesto_scan', code=code))
        current_user.debit_wallet(lb.product.price, f'Cesto: {lb.product.name}')
        for ep in extra_products:
            current_user.debit_wallet(ep.price, f'Cesto extra: {ep.name}')
    else:
        # La vendita resta nel registro anche senza portafoglio: il cliente
        # paga alla cassa, ma report e guadagni devono vederla.
        current_user.registra_consumo(lb.product.price, f'Cesto: {lb.product.name}')
        for ep in extra_products:
            current_user.registra_consumo(ep.price, f'Cesto extra: {ep.name}')

    lb.status   = 'sold'
    lb.sold_at  = datetime.utcnow()
    lb.buyer_id = current_user.id
    db.session.commit()

    extras_str = ' + ' + ', '.join(p.name for p in extra_products) if extra_products else ''
    _cassa = '' if wallet_enabled() else ' Paga alla cassa.'
    flash(f'Acquisto confermato! {lb.product.name}{extras_str}.{_cassa} Buon appetito.', 'success')
    return redirect(url_for('main.cesto_scan', code=code))


# ── PRENOTAZIONI FUTURE ───────────────────────────────────────────────────────

_PREN_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

def _gen_pren_code():
    while True:
        code = 'PREN-' + ''.join(secrets.choice(_PREN_CHARS) for _ in range(6))
        if not Prenotazione.query.filter_by(code=code).first():
            return code


@bp.route('/prenotazioni')
@login_required
def prenotazioni_list():
    uid = current_user.id
    tid = current_user.tenant_id
    upcoming = (Prenotazione.query
                .filter_by(user_id=uid, tenant_id=tid)
                .filter(Prenotazione.pickup_date >= date.today())
                .filter(Prenotazione.status != 'cancelled')
                .order_by(Prenotazione.pickup_date.asc())
                .all())
    past = (Prenotazione.query
            .filter_by(user_id=uid, tenant_id=tid)
            .filter(Prenotazione.pickup_date < date.today())
            .order_by(Prenotazione.pickup_date.desc())
            .limit(10).all())
    return render_template('main/prenotazioni.html', upcoming=upcoming, past=past,
                           today=date.today())


@bp.route('/prenotazioni/nuova')
@login_required
def prenotazioni_nuova():
    tid = current_user.tenant_id
    tomorrow = date.today() + timedelta(days=1)
    products = (Product.query
                .filter_by(tenant_id=tid, is_active=True)
                .join(Category)
                .order_by(Category.name, Product.name)
                .all())
    slots = (TimeSlot.query
             .filter_by(tenant_id=tid, is_active=True)
             .order_by(TimeSlot.time_str)
             .all())
    categories = {}
    for p in products:
        categories.setdefault(p.category.name, []).append(p)
    return render_template('main/prenotazioni_nuova.html',
                           categories=categories, slots=slots,
                           tomorrow=tomorrow.isoformat())


@bp.route('/prenotazioni/crea', methods=['POST'])
@login_required
def prenotazioni_crea():
    tid = current_user.tenant_id
    tomorrow = date.today() + timedelta(days=1)

    # Valida data
    try:
        pickup_date = date.fromisoformat(request.form.get('pickup_date', ''))
    except ValueError:
        flash('Data non valida.', 'danger')
        return redirect(url_for('main.prenotazioni_nuova'))
    if pickup_date < tomorrow:
        flash('Puoi prenotare solo dal giorno di domani in poi.', 'danger')
        return redirect(url_for('main.prenotazioni_nuova'))

    slot_id = request.form.get('slot_id', type=int) or None
    notes   = request.form.get('notes', '').strip()

    # Raccoglie prodotti
    items_data = []
    for key, val in request.form.items():
        if key.startswith('qty_'):
            try:
                pid = int(key[4:])
                qty = int(val)
            except ValueError:
                continue
            if qty < 1:
                continue
            p = Product.query.filter_by(id=pid, tenant_id=tid, is_active=True).first()
            if p:
                items_data.append((p, qty))

    if not items_data:
        flash('Seleziona almeno un prodotto.', 'danger')
        return redirect(url_for('main.prenotazioni_nuova'))

    total = sum(p.price * q for p, q in items_data)
    if wallet_enabled():
        balance = current_user.wallet_balance or 0
        if balance < total:
            flash(f'Saldo insufficiente. Hai {numero_italiano(balance)} €, serve {numero_italiano(total)} €.', 'danger')
            return redirect(url_for('main.prenotazioni_nuova'))

    # Crea prenotazione
    code = _gen_pren_code()
    pren = Prenotazione(
        code=code, user_id=current_user.id, tenant_id=tid,
        pickup_date=pickup_date, slot_id=slot_id,
        notes=notes, status='pending', total_price=total,
    )
    db.session.add(pren)
    db.session.flush()

    for p, qty in items_data:
        db.session.add(PrenotazioneItem(
            prenotazione_id=pren.id, product_id=p.id,
            quantity=qty, unit_price=p.price,
        ))

    if wallet_enabled():
        current_user.debit_wallet(total, f'Prenotazione {code}')
    db.session.commit()

    flash(f'Prenotazione {code} confermata per il {pickup_date.strftime("%d/%m/%Y")}!', 'success')
    return redirect(url_for('main.prenotazioni_list'))


@bp.route('/prenotazioni/<int:pid>/cancella', methods=['POST'])
@login_required
def prenotazioni_cancella(pid):
    pren = Prenotazione.query.filter_by(id=pid, user_id=current_user.id).first_or_404()
    if pren.status == 'cancelled':
        flash('Prenotazione già cancellata.', 'warning')
        return redirect(url_for('main.prenotazioni_list'))
    if pren.status == 'ready':
        flash('Il tuo ordine è già pronto per il ritiro, non è più possibile cancellarlo.', 'danger')
        return redirect(url_for('main.prenotazioni_list'))
    if pren.pickup_date <= date.today():
        flash('Non è possibile cancellare una prenotazione del giorno stesso o passata.', 'danger')
        return redirect(url_for('main.prenotazioni_list'))
    pren.status = 'cancelled'
    if wallet_enabled() and pren.total_price and pren.total_price > 0:
        current_user.credit_wallet(pren.total_price, f'Rimborso {pren.code}')
        db.session.commit()
        flash(f'Prenotazione {pren.code} cancellata. Rimborso di {numero_italiano(pren.total_price)} € accreditato.', 'info')
    else:
        db.session.commit()
        flash(f'Prenotazione {pren.code} cancellata.', 'info')
    return redirect(url_for('main.prenotazioni_list'))


# ── Web Push ──────────────────────────────────────────────────────────────────

@bp.route('/sw.js')
def service_worker():
    """Serve il Service Worker dalla radice del sito (scope obbligatorio per Push API)."""
    from flask import current_app, make_response
    import os
    sw_path = os.path.join(current_app.static_folder, 'sw.js')
    with open(sw_path, encoding='utf-8') as f:
        content = f.read()
    resp = make_response(content)
    resp.headers['Content-Type']        = 'application/javascript'
    resp.headers['Cache-Control']       = 'no-cache, no-store, must-revalidate'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@bp.route('/api/push/vapid-key')
def push_vapid_key():
    """Restituisce la chiave pubblica VAPID per la sottoscrizione push del browser."""
    _, pub = _get_or_create_vapid_keys()
    if not pub:
        return jsonify({'error': 'Web Push non disponibile'}), 503
    return jsonify({'publicKey': pub})


@bp.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    """Registra la sottoscrizione push del browser corrente."""
    from flask import current_app
    data     = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint', '').strip()
    keys     = data.get('keys', {})
    p256dh   = keys.get('p256dh', '').strip()
    auth     = keys.get('auth', '').strip()
    if not endpoint or not p256dh or not auth:
        current_app.logger.warning(f'push_subscribe: dati incompleti user={current_user.id}')
        return jsonify({'ok': False, 'error': 'Dati incompleti'}), 400
    try:
        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if not existing:
            db.session.add(PushSubscription(
                user_id=current_user.id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth
            ))
            db.session.commit()
            current_app.logger.info(f'push_subscribe: nuova subscription user={current_user.id}')
        return jsonify({'ok': True})
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f'push_subscribe: ERRORE user={current_user.id}: {exc}', exc_info=True)
        return jsonify({'ok': False, 'error': str(exc)}), 500


@bp.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    """Rimuove la sottoscrizione push del browser corrente."""
    data     = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint', '').strip()
    if endpoint:
        PushSubscription.query.filter_by(
            user_id=current_user.id, endpoint=endpoint
        ).delete()
        db.session.commit()
    return jsonify({'ok': True})



# ── Collegamento del bot Telegram, guidato ───────────────────────────────────

@bp.route('/telegram/collega')
@login_required
def telegram_collega():
    """Pagina che accompagna il cliente nel collegamento del bot.

    Non gli si chiede il proprio ID Telegram (che non ha modo di conoscere
    se il webhook non e' attivo): gli si da' un codice da inviare al bot, e
    l'applicazione lo riconosce fra i messaggi ricevuti.
    """
    from app.notifications import (codice_collegamento, link_avvio_bot,
                                   nome_bot)
    return render_template(
        'main/telegram_collega.html',
        codice=codice_collegamento(current_user),
        link_bot=link_avvio_bot(current_user),
        nome_bot=nome_bot(),
        collegato=bool((current_user.telegram_chat_id or '').strip()))


@bp.route('/telegram/collega/verifica', methods=['POST'])
@login_required
def telegram_collega_verifica():
    """Cerca il codice fra i messaggi del bot e salva il collegamento."""
    from app.notifications import collega_telegram_da_messaggi

    ok, messaggio = collega_telegram_da_messaggi(current_user)
    flash(messaggio, 'success' if ok else 'warning')
    return redirect(url_for('main.telegram_collega'))


@bp.route('/telegram/scollega', methods=['POST'])
@login_required
def telegram_scollega():
    """Stacca il bot: gli avvisi tornano per email."""
    current_user.telegram_chat_id = ''
    db.session.commit()
    flash('Telegram scollegato: gli avvisi tornano per email.', 'info')
    return redirect(url_for('main.telegram_collega'))


# ── Risposte ai bottoni Telegram ──────────────────────────────────────────────
#
# Il promemoria del pasto aziendale porta due bottoni (Si' / No). Quando
# l'utente ne premi uno, Telegram chiama questo indirizzo: non c'e' una
# sessione ne' un token CSRF, quindi la rotta e' esente e si autentica con un
# segreto nel percorso, generato all'attivazione dalle Impostazioni.

def _segreto_webhook():
    """Il segreto atteso nell'URL del webhook, generato alla prima attivazione."""
    from app.notifications import get_setting
    return (get_setting('telegram_webhook_secret') or '').strip()


def _conferma_pasto(booking, risposta, chat_id):
    """Applica la risposta ai bottoni. Ritorna il testo da mostrare all'utente.

    "No" annulla la prenotazione: e' il modo in cui l'utente blocca la
    produzione del suo pasto.
    """
    atteso = (getattr(booking.user, 'telegram_chat_id', '') or '').strip()
    if not atteso or str(chat_id) != atteso:
        return None, 'Questa prenotazione non e tua.'
    if booking.status == 'cancelled':
        return 'no', 'Prenotazione gia annullata: la cucina non lo prepara.'
    if booking.status == 'consumed':
        return None, 'Pasto gia consegnato.'
    if risposta == 'si':
        booking.conferma_utente = 'si'
        db.session.commit()
        return 'si', 'Grazie, ritiro confermato.'

    booking.conferma_utente = 'no'
    booking.status = 'cancelled'
    db.session.commit()
    # La cucina deve saperlo: sta per produrre quel pasto.
    nome = booking.meal.name if booking.meal else 'pasto'
    ora = booking.slot.time_str if booking.slot else ''
    send_telegram(
        f'🚫 <b>Pasto annullato dal cliente</b>\n'
        f'👤 {booking.user.display_name}\n'
        f'📋 {nome}{" — " + ora if ora else ""}\n'
        f'Non va preparato.'
    )
    return 'no', 'Annullato: la cucina non lo prepara.'


def _gestisci_messaggio_bot(messaggio):
    """Risponde ai comandi in chat: /start (collega) e /id (mostra l'ID).

    Il collegamento arriva dal link nell'email di benvenuto, che porta un
    token firmato nel parametro start: qui si riconosce l'utente e si salva
    il suo chat id, senza che debba copiare niente.
    """
    from app.notifications import (telegram_api, utente_da_token, nome_bot)

    chat = (messaggio.get('chat') or {}).get('id')
    testo = (messaggio.get('text') or '').strip()
    if not chat or not testo.startswith('/'):
        return
    pezzi = testo.split()
    comando = pezzi[0].split('@')[0].lower()

    if comando == '/start' and len(pezzi) > 1:
        from app.models import User as _U
        chiave = pezzi[1].strip()
        # Prima il codice breve della pagina di collegamento, poi il token
        # firmato dell'email: sono due vie per la stessa cosa.
        utente = _U.query.filter_by(telegram_link_code=chiave.upper()).first()
        if not utente:
            utente = utente_da_token(chiave)
        if utente:
            utente.telegram_chat_id = str(chat)
            db.session.commit()
            risposta = (
                '✅ Telegram collegato, %s!\n\n'
                'Da adesso ricevi qui gli avvisi: ordine pronto e '
                'promemoria del pasto, con i bottoni per confermare o '
                'disdire il ritiro.' % utente.display_name)
        else:
            risposta = (
                'Questo collegamento non è più valido.\n\n'
                'Scrivi /id per conoscere il tuo ID Telegram e incollalo '
                'nel tuo profilo, oppure chiedi al banco una nuova email '
                'di collegamento.')
    elif comando in ('/start', '/id', '/help'):
        risposta = (
            'Il tuo <b>ID Telegram</b> è <code>%s</code>\n\n'
            'Copialo nel tuo profilo su QuickLunch, nel campo '
            '"Telegram Chat ID", e salva: da quel momento ricevi qui gli '
            'avvisi degli ordini e i promemoria del pasto.' % chat)
    else:
        risposta = ('Comando non riconosciuto. Scrivi /id per conoscere il '
                    'tuo ID Telegram.')

    telegram_api('sendMessage', {'chat_id': chat, 'text': risposta,
                                 'parse_mode': 'HTML'})


@bp.route('/telegram/webhook/<segreto>', methods=['POST'])
def telegram_webhook(segreto):
    """Riceve i callback dei bottoni del bot Telegram."""
    from hmac import compare_digest
    from app.notifications import telegram_api

    atteso = _segreto_webhook()
    if not atteso or not compare_digest(str(segreto), atteso):
        return jsonify({'ok': False}), 403

    aggiornamento = request.get_json(silent=True) or {}
    if aggiornamento.get('message'):
        _gestisci_messaggio_bot(aggiornamento['message'])
        return jsonify({'ok': True})
    callback = aggiornamento.get('callback_query') or {}
    dati = (callback.get('data') or '').strip()
    if not dati:
        return jsonify({'ok': True})          # niente da fare: si ignora

    pezzi = dati.split(':')
    esito = 'Comando non riconosciuto.'
    if len(pezzi) == 3 and pezzi[0] == 'prova' and pezzi[2] in ('si', 'no'):
        # La domanda di prova delle Impostazioni: si annota la risposta,
        # che il gestore rilegge dalla pagina.
        from app.notifications import registra_risposta_prova
        chi = ((callback.get('from') or {}).get('first_name') or '').strip()
        if registra_risposta_prova(pezzi[1], pezzi[2], chi):
            esito = ('Risposta registrata: il canale funziona in entrambe '
                     'le direzioni.')
        else:
            esito = 'Questa prova non e piu in corso.'
    elif len(pezzi) == 3 and pezzi[0] == 'pasto' and pezzi[2] in ('si', 'no'):
        try:
            bid = int(pezzi[1])
        except ValueError:
            bid = 0
        booking = CorporateMealBooking.query.get(bid) if bid else None
        if not booking:
            esito = 'Prenotazione non trovata.'
        else:
            chat = ((callback.get('message') or {}).get('chat') or {}).get('id')
            _scelta, esito = _conferma_pasto(booking, pezzi[2], chat)
            messaggio = callback.get('message') or {}
            if messaggio.get('message_id'):
                # Si riscrive il messaggio con l'esito e si togliono i
                # bottoni, cosi' non si puo' rispondere due volte.
                telegram_api('editMessageText', {
                    'chat_id': chat,
                    'message_id': messaggio['message_id'],
                    'text': (messaggio.get('text') or '') + '\n\n➡️ ' + esito,
                    'reply_markup': {'inline_keyboard': []},
                })

    telegram_api('answerCallbackQuery', {
        'callback_query_id': callback.get('id', ''),
        'text': esito,
    })
    return jsonify({'ok': True})
