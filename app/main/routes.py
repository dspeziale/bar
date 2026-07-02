import secrets
from datetime import date, datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app import db
from app.main import bp
from app.notifications import send_telegram, send_telegram_to_user
from app.models import (Product, Category, Order, OrderItem, TimeSlot,
                        Transaction, DailyStock, IngredientCategory, Ingredient,
                        CustomOrderItem, CustomOrderItemIngredient,
                        Table, TableReservation, Poll, PollVote, PollChoice,
                        DailyFixedMeal, CorporateMealBooking, Tenant, BancoSession)
from config import Config


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

    return render_template('main/dashboard.html',
                           today_orders=today_orders,
                           today_reservations=today_reservations,
                           recent_tx=recent_tx,
                           today_meal_booking=today_meal_booking,
                           meal_booking_reminder=meal_booking_reminder,
                           loyalty_threshold=Config.LOYALTY_REWARD_POINTS,
                           reward_amount=Config.LOYALTY_REWARD_AMOUNT)


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
    return render_template('main/menu.html', categories=categories,
                           products=products, slots=slots, cart=cart)


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
    for ci in custom_cart:
        total += ci['total_price']

    tid = _effective_tenant_id()
    slots = TimeSlot.query.filter_by(is_active=True, tenant_id=tid).order_by(TimeSlot.time_str).all()
    return render_template('main/cart.html', items=items,
                           custom_cart=custom_cart,
                           total=round(total, 2),
                           slots=slots,
                           wallet=current_user.wallet_balance)


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

    if current_user.wallet_balance < total:
        flash(f'Saldo wallet insufficiente ({current_user.wallet_balance:.2f}€). '
              f'Servono {total:.2f}€.', 'danger')
        return redirect(url_for('main.wallet'))

    # Crea ordine
    order = Order(user_id=current_user.id, slot_id=slot_id,
                  order_date=date.today(), notes=notes, status='confirmed')
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

    slot_tag   = 'BANCO' if banco else slot.time_str.replace(':', '')
    slot_label = 'adesso al banco' if banco else f'alle {slot.time_str}'
    order.order_code = (
        f"QuickLunch-{order.order_date.strftime('%y%m%d')}"
        f"-{slot_tag}"
        f"-{order.id:04d}"
    )
    order.compute_total()
    current_user.debit_wallet(total, f'Ordine {order.order_code}', order_id=order.id)
    points = int(total * Config.LOYALTY_POINTS_PER_EURO)
    if points:
        current_user.add_points(points)

    db.session.commit()
    session.pop('cart', None)
    session.pop('custom_cart', None)
    flash(f'Ordine {order.order_code} confermato! Ritiro {slot_label}.', 'success')

    # notifica utente
    send_telegram_to_user(
        current_user,
        f'✅ Ordine <b>{order.order_code}</b> confermato!\n'
        f'Ritiro {slot_label}. Totale: <b>{total:.2f}€</b>'
    )

    # notifica admin / cucina
    lines = [f'🛒 <b>Nuovo ordine</b> — {order.order_code}',
             f'👤 {current_user.full_name}  •  ritiro: <b>{slot_label}</b>',
             f'💶 Totale: <b>{total:.2f}€</b>', '']
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
    orders = Order.query.filter_by(user_id=current_user.id)\
        .order_by(Order.created_at.desc()).limit(50).all()
    return render_template('main/my_orders.html', orders=orders)


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
    current_user.credit_wallet(order.total_price,
                               f'Rimborso ordine #{order.id}', order_id=order.id)
    points_back = int(order.total_price * Config.LOYALTY_POINTS_PER_EURO)
    current_user.loyalty_points = max(0, current_user.loyalty_points - points_back)

    for item in order.items:
        stock = DailyStock.query.filter_by(
            product_id=item.product_id, stock_date=date.today()).first()
        if stock:
            stock.quantity_reserved = max(0, stock.quantity_reserved - item.quantity)

    db.session.commit()
    flash(f'Ordine #{order.id} annullato. Rimborso {order.total_price:.2f}€.', 'info')
    send_telegram_to_user(
        current_user,
        f'❌ Ordine <b>#{order.id}</b> annullato.\n'
        f'Rimborso di <b>{order.total_price:.2f}€</b> sul tuo wallet.'
    )
    return redirect(url_for('main.my_orders'))


# ── Wallet ────────────────────────────────────────────────────────────────────

@bp.route('/wallet')
@login_required
def wallet():
    transactions = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc()).limit(50).all()
    return render_template('main/wallet.html', transactions=transactions,
                           loyalty_threshold=Config.LOYALTY_REWARD_POINTS,
                           reward_amount=Config.LOYALTY_REWARD_AMOUNT)


@bp.route('/wallet/redeem', methods=['POST'])
@login_required
def redeem_points():
    threshold = Config.LOYALTY_REWARD_POINTS
    reward = Config.LOYALTY_REWARD_AMOUNT
    if current_user.loyalty_points < threshold:
        flash(f'Punti insufficienti (servono {threshold}).', 'warning')
        return redirect(url_for('main.wallet'))
    blocks = current_user.loyalty_points // threshold
    current_user.redeem_points(blocks * threshold, blocks * reward)
    db.session.commit()
    flash(f'+{blocks * reward:.2f}€ aggiunti al wallet!', 'success')
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

    base_price = Config.BUILDER_PRICES[builder_type]
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

    base_price = Config.BUILDER_PRICES[builder_type]
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
        base_price = Config.BUILDER_PRICES[builder_type]

    return render_template('main/builder_visual.html',
                           builder_type=builder_type,
                           categories=categories,
                           base_price=base_price,
                           config=Config)


# ── Tavoli ────────────────────────────────────────────────────────────────────

@bp.route('/tables')
@login_required
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
        party_size=party_size, notes=notes, status='confirmed'
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
def my_reservations():
    reservations = TableReservation.query.filter_by(user_id=current_user.id)\
        .order_by(TableReservation.created_at.desc()).limit(30).all()
    return render_template('main/my_reservations.html', reservations=reservations,
                           today_date=date.today())


@bp.route('/reservations/<int:rid>/cancel', methods=['POST'])
@login_required
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
    choice_id = request.form.get('choice_id', type=int)
    choice    = PollChoice.query.filter_by(id=choice_id, poll_id=pid).first()
    if not choice:
        flash('Scelta non valida.', 'danger')
        return redirect(url_for('main.poll_view', pid=pid))
    db.session.add(PollVote(poll_id=pid,
                             choice_id=choice_id,
                             user_id=current_user.id))
    db.session.commit()
    flash(f'Voto registrato: {choice.emoji} {choice.text}', 'success')
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

    return render_template('main/pasto_aziendale.html',
                           corp=corp, meals=meals, my_booking=my_booking,
                           slots=slots, today=today, can_cancel=can_cancel)


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
            booking.status = 'cancelled'
            db.session.commit()
            flash('Prenotazione annullata.', 'info')
        else:
            flash('Non è più possibile annullare: mancano meno di 30 minuti alla consegna.', 'warning')
    return redirect(url_for('main.pasto_aziendale'))


# ── Guida utente ─────────────────────────────────────────────────────────────

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
    if current_user.wallet_balance < sess.total:
        flash(f'Saldo insufficiente ({current_user.wallet_balance:.2f}€). Ricarica il wallet.', 'danger')
        return redirect(url_for('main.banco_pay', token=token))
    try:
        items = json.loads(sess.items_json)
    except Exception:
        items = []
    lines = ', '.join(f"{i['qty']}× {i['name']}" for i in items)
    current_user.debit_wallet(sess.total, f'Banco: {lines}')
    # marca ttype come banco
    last_tx = current_user.transactions[-1] if current_user.transactions else None
    if last_tx:
        last_tx.ttype = 'banco'
    sess.status      = 'paid'
    sess.customer_id = current_user.id
    db.session.commit()
    flash(f'Pagamento di {sess.total:.2f}€ confermato!', 'success')
    return redirect(url_for('main.index'))

