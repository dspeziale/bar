import secrets
from datetime import date
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app import db
from app.main import bp
from app.notifications import send_telegram_to_user
from app.models import (Product, Category, Order, OrderItem, TimeSlot,
                        Transaction, DailyStock, IngredientCategory, Ingredient,
                        CustomOrderItem, CustomOrderItemIngredient,
                        Table, TableReservation, Poll, PollVote, PollChoice,
                        DailyFixedMeal, CorporateMealBooking)
from config import Config


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
    return render_template('main/dashboard.html',
                           today_orders=today_orders,
                           today_reservations=today_reservations,
                           recent_tx=recent_tx,
                           loyalty_threshold=Config.LOYALTY_REWARD_POINTS,
                           reward_amount=Config.LOYALTY_REWARD_AMOUNT)


# ── Menu ──────────────────────────────────────────────────────────────────────

@bp.route('/menu')
@login_required
def menu():
    categories = Category.query.all()
    products = Product.query.filter_by(is_active=True).order_by(
        Product.category_id, Product.name).all()
    slots = TimeSlot.query.filter_by(is_active=True).order_by(TimeSlot.time_str).all()
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

    slots = TimeSlot.query.filter_by(is_active=True).order_by(TimeSlot.time_str).all()
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

    slot_id = request.form.get('slot_id', type=int)
    notes = request.form.get('notes', '').strip()
    slot = db.session.get(TimeSlot, slot_id)
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

    order.order_code = (
        f"QuickLunch-{order.order_date.strftime('%y%m%d')}"
        f"-{slot.time_str.replace(':', '')}"
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
    flash(f'Ordine {order.order_code} confermato! Ritira alle {slot.time_str}.', 'success')
    send_telegram_to_user(
        current_user,
        f'✅ Ordine <b>{order.order_code}</b> confermato!\n'
        f'Ritiro alle <b>{slot.time_str}</b>. Totale: <b>{total:.2f}€</b>'
    )
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

    categories = IngredientCategory.query.filter(
        IngredientCategory.builder_type.in_([builder_type, 'both'])
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
    categories = IngredientCategory.query.filter(
        IngredientCategory.builder_type.in_([builder_type, 'both'])
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
    slots = TimeSlot.query.filter_by(is_active=True).order_by(TimeSlot.time_str).all()
    all_tables = Table.query.filter_by(is_active=True).order_by(Table.number).all()
    res_date = date.today()

    # Matrice disponibilità: {table_id: {slot_id: reservation_or_None}}
    availability = {}
    for t in all_tables:
        availability[t.id] = {}
        for s in slots:
            availability[t.id][s.id] = t.reservation_for(s.id, res_date)

    # Prenotazione già fatta oggi dall'utente
    my_res_today = TableReservation.query.filter_by(
        user_id=current_user.id, reservation_date=res_date
    ).filter(TableReservation.status != 'cancelled').all()
    my_booked = {(r.table_id, r.slot_id) for r in my_res_today}

    return render_template('main/tables.html',
                           tables=all_tables, slots=slots,
                           availability=availability,
                           my_booked=my_booked,
                           res_date=res_date)


@bp.route('/tables/book', methods=['POST'])
@login_required
def table_book():
    table_id = request.form.get('table_id', type=int)
    slot_id = request.form.get('slot_id', type=int)
    party_size = request.form.get('party_size', type=int, default=1)
    notes = request.form.get('notes', '').strip()
    res_date = date.today()

    table = db.get_or_404(Table, table_id)
    slot = db.get_or_404(TimeSlot, slot_id)

    if not table.is_active or not slot.is_active:
        flash('Tavolo o slot non disponibile.', 'danger')
        return redirect(url_for('main.tables'))

    if not table.is_available(slot_id, res_date):
        flash('Tavolo già occupato per questo slot.', 'warning')
        return redirect(url_for('main.tables'))

    if party_size > table.seats:
        flash(f'Il tavolo {table.number} ha solo {table.seats} posti.', 'warning')
        return redirect(url_for('main.tables'))

    res = TableReservation(
        user_id=current_user.id, table_id=table_id,
        slot_id=slot_id, reservation_date=res_date,
        party_size=party_size, notes=notes, status='confirmed'
    )
    db.session.add(res)
    db.session.commit()
    flash(f'Tavolo {table.number} prenotato per le {slot.time_str}!', 'success')
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
    meal  = DailyFixedMeal.query.filter_by(
        corporate_id=corp.id, meal_date=today, is_active=True).first()

    my_booking = None
    if meal:
        my_booking = CorporateMealBooking.query.filter_by(
            user_id=current_user.id, meal_id=meal.id).first()

    slots = TimeSlot.query.filter_by(is_active=True).order_by(TimeSlot.time_str).all()
    return render_template('main/pasto_aziendale.html',
                           corp=corp, meal=meal, my_booking=my_booking,
                           slots=slots, today=today)


@bp.route('/pasto-aziendale/prenota', methods=['POST'])
@login_required
def pasto_aziendale_prenota():
    membership = getattr(current_user, 'corporate_membership', None)
    if not membership or not membership.is_active:
        flash('Non sei associato a nessuna convenzione aziendale.', 'warning')
        return redirect(url_for('main.index'))

    corp  = membership.corporate
    today = date.today()
    meal  = DailyFixedMeal.query.filter_by(
        corporate_id=corp.id, meal_date=today, is_active=True).first()

    if not meal:
        flash('Nessun pasto disponibile per oggi.', 'warning')
        return redirect(url_for('main.pasto_aziendale'))

    if not meal.is_available:
        flash('Posti esauriti per oggi.', 'danger')
        return redirect(url_for('main.pasto_aziendale'))

    existing = CorporateMealBooking.query.filter_by(
        user_id=current_user.id, meal_id=meal.id).first()
    if existing:
        flash('Hai giÃ  prenotato il pasto di oggi.', 'info')
        return redirect(url_for('main.pasto_aziendale'))

    slot_id = request.form.get('slot_id') or None
    if slot_id:
        slot_id = int(slot_id)

    booking = CorporateMealBooking(
        user_id=current_user.id, meal_id=meal.id,
        slot_id=slot_id, status='booked')
    db.session.add(booking)
    db.session.commit()

    send_telegram_to_user(current_user,
        f'ðŸ½ï¸ Prenotazione confermata!\n'
        f'<b>{meal.name}</b>\n'
        f'Azienda: {corp.name} â€” oggi {today.strftime("%d/%m/%Y")}')

    flash(f'Pasto prenotato: {meal.name}', 'success')
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
        booking.status = 'cancelled'
        db.session.commit()
        flash('Prenotazione annullata.', 'info')
    return redirect(url_for('main.pasto_aziendale'))

