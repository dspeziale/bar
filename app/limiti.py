# -*- coding: utf-8 -*-
"""Limite di spesa giornaliero per cliente.

Ogni locale può fissare quanto un cliente può ordinare in una giornata
(`AppSetting limite_giornaliero_importo`, 0 = nessun limite); ogni cliente
può avere un proprio importo diverso (`User.limite_giornaliero_override`:
`None` = usa quello del locale, un numero — anche 0 — lo sostituisce: 0
esplicito toglie il limite solo per quel cliente).

Conta solo quello che passa dal menu (`Order`, con o senza slot — "adesso al
banco" è comunque un Order): il POS al banco con QR e il cesto sono canali
di acquisto rapido a sé stanti e restano fuori da questo controllo.

Quando un carrello supererebbe il limite, l'ordine non parte da solo: nasce
una `RichiestaSpesa` in attesa, il gestore viene avvisato su Telegram con due
bottoni (Approva / Rifiuta) — la stessa idea del promemoria del pasto — e
può decidere anche dal backoffice. Solo alla decisione l'ordine viene creato
davvero (o la richiesta chiusa come rifiutata), con gli stessi controlli di
un ordine normale (stock, slot, saldo).
"""
import json
from datetime import date, datetime

from app import db, wallet_enabled


def limite_di(user):
    """Il limite giornaliero di questo cliente: il suo, se impostato,
    altrimenti quello del locale. 0 o assente = nessun limite."""
    from app.notifications import get_numeric_setting
    if user.limite_giornaliero_override is not None:
        return user.limite_giornaliero_override
    return get_numeric_setting('limite_giornaliero_importo', 0.0)


def speso_oggi(user, tenant_id, oggi=None):
    """Quanto ha già ordinato oggi (Order, esclusi gli annullati)."""
    from app.models import Order
    oggi = oggi or date.today()
    tot = (db.session.query(db.func.coalesce(db.func.sum(Order.total_price), 0.0))
           .filter(Order.user_id == user.id, Order.tenant_id == tenant_id,
                   Order.order_date == oggi, Order.status != 'cancelled')
           .scalar() or 0.0)
    return round(tot, 2)


def verifica(user, tenant_id, importo_carrello, oggi=None):
    """(supera, limite, speso_oggi, disponibile).

    `supera` è True se questo carrello, sommato a quanto già ordinato oggi,
    supererebbe il limite del cliente. Con limite 0/assente non supera mai.
    """
    limite = limite_di(user)
    if not limite or limite <= 0:
        return False, 0.0, 0.0, None
    speso = speso_oggi(user, tenant_id, oggi)
    disponibile = round(limite - speso, 2)
    supera = round(speso + importo_carrello, 2) > round(limite, 2) + 0.001
    return supera, limite, speso, disponibile


def crea_richiesta(user, tenant_id, importo, limite, speso, cart, custom_cart,
                   slot_id, banco, notes, dieta_giorno_id=None):
    """La richiesta in attesa, col carrello congelato in JSON."""
    from app.models import RichiestaSpesa
    dati = {'cart': {str(k): int(v) for k, v in (cart or {}).items()},
            'custom_cart': custom_cart or [], 'slot_id': slot_id,
            'banco': bool(banco), 'notes': notes or '',
            'dieta_giorno_id': dieta_giorno_id}
    r = RichiestaSpesa(tenant_id=tenant_id, user_id=user.id, importo=importo,
                       limite_al_momento=limite, speso_al_momento=speso,
                       carrello=json.dumps(dati, ensure_ascii=False))
    db.session.add(r)
    db.session.flush()
    return r


def tastiera_richiesta_spesa(richiesta_id):
    """I due bottoni sotto l'avviso al gestore: stessa idea del promemoria pasto."""
    return {'inline_keyboard': [[
        {'text': '✅ Approva', 'callback_data': 'spesa:%d:si' % richiesta_id},
        {'text': '❌ Rifiuta', 'callback_data': 'spesa:%d:no' % richiesta_id},
    ]]}


def avvisa_gestore(richiesta):
    """Manda la richiesta sul canale dello staff, coi bottoni per decidere."""
    from app.notifications import send_telegram
    from app import numero_italiano
    u = richiesta.user
    testo = (
        '💶 <b>Richiesta di spesa oltre il limite</b>\n'
        f'👤 {u.full_name}\n'
        f'🛒 Carrello: <b>{numero_italiano(richiesta.importo)}€</b>\n'
        f'📊 Già ordinato oggi: {numero_italiano(richiesta.speso_al_momento)}€ '
        f'· limite {numero_italiano(richiesta.limite_al_momento)}€\n'
        'Approvi?'
    )
    return send_telegram(testo, reply_markup=tastiera_richiesta_spesa(richiesta.id))


def crea_ordine_da_richiesta(richiesta):
    """Crea davvero l'ordine di una richiesta approvata, con gli controlli di
    un ordine normale (stock, slot, saldo): può ancora fallire se qualcosa è
    cambiato nel frattempo. Ritorna (order, errore)."""
    from app.models import (Product, TimeSlot, Order, OrderItem, CustomOrderItem,
                            CustomOrderItemIngredient, Ingredient, DietPlanDay)
    from app import magazzino_enabled
    from app.notifications import get_numeric_setting

    dati = richiesta.dict_carrello
    cart = dati.get('cart') or {}
    custom_cart = dati.get('custom_cart') or []
    slot_id = dati.get('slot_id')
    banco = bool(dati.get('banco'))
    notes = dati.get('notes') or ''
    user = richiesta.user
    tenant_id = richiesta.tenant_id

    slot = db.session.get(TimeSlot, slot_id) if slot_id else None
    if not banco:
        if not slot or not slot.is_active or slot.is_full():
            return None, 'Lo slot di ritiro scelto non è più disponibile.'

    regular_items = []
    total = 0.0
    for pid, qty in cart.items():
        product = db.session.get(Product, int(pid))
        if not product or not product.is_active:
            return None, 'Un prodotto del carrello non è più disponibile.'
        if qty > product.available_today():
            return None, f'"{product.name}": disponibili solo {product.available_today()} unità.'
        regular_items.append((product, int(qty)))
        total += product.price * qty
    for ci in custom_cart:
        total += ci['total_price']
    total = round(total, 2)

    if wallet_enabled():
        overdraft = user.wallet_overdraft or 0.0
        if user.wallet_balance + overdraft < total:
            return None, 'Il saldo wallet del cliente non è più sufficiente.'

    order = Order(user_id=user.id, slot_id=slot_id, order_date=date.today(),
                 notes=notes, status='confirmed', tenant_id=tenant_id)
    db.session.add(order)
    db.session.flush()

    for product, qty in regular_items:
        db.session.add(OrderItem(order_id=order.id, product_id=product.id,
                                 quantity=qty, unit_price=product.price))
        stock = product.get_or_create_stock()
        stock.quantity_reserved += qty

    for ci in custom_cart:
        coi = CustomOrderItem(order_id=order.id, builder_type=ci.get('type', ''),
                              label=ci.get('label', ''), unit_price=ci['total_price'],
                              grill_requested=ci.get('grill_requested', False))
        db.session.add(coi)
        db.session.flush()
        for ing in ci.get('ingredients', []):
            db.session.add(CustomOrderItemIngredient(
                custom_item_id=coi.id, ingredient_name=ing['name'],
                price_extra=ing.get('price_extra', 0.0)))
            if ing.get('id') and magazzino_enabled():
                _ingredient = db.session.get(Ingredient, ing['id'])
                if (_ingredient and _ingredient.stock_qty is not None
                        and _ingredient.grams_per_serving):
                    _ingredient.stock_qty = max(
                        0.0, _ingredient.stock_qty - _ingredient.grams_per_serving * coi.quantity)

    if banco:
        order.order_code = f'BANCO-{order.id:04d}'
    else:
        order.order_code = (f"QL-{order.order_date.strftime('%y%m%d')}"
                           f"-{slot.time_str.replace(':', '')}-{order.id:04d}")
    order.compute_total()
    if wallet_enabled():
        user.debit_wallet(total, f'Ordine {order.order_code}', order_id=order.id)
        points = int(total * get_numeric_setting('loyalty_points_per_euro', 10))
        if points:
            user.add_points(points)

    giorno_id = dati.get('dieta_giorno_id')
    if giorno_id:
        giorno = db.session.get(DietPlanDay, giorno_id)
        if giorno and giorno.plan and giorno.plan.user_id == user.id:
            giorno.stato = 'ordinato'
            giorno.order_id = order.id

    return order, None


def decidi_richiesta(richiesta, approvata, staff=None, motivo=''):
    """Applica la decisione del gestore (da Telegram o dal backoffice):
    approvata -> crea l'ordine; rifiutata -> chiude la richiesta.
    Ritorna (ok, messaggio) da mostrare a chi ha deciso."""
    from app.notifications import send_reminder_to_user
    from app import numero_italiano

    if richiesta.stato != 'in_attesa':
        return False, 'Questa richiesta è già stata decisa.'

    richiesta.decisa_il = datetime.utcnow()
    richiesta.decisa_da = staff.id if staff else None
    richiesta.motivo = (motivo or '').strip()[:300]

    if approvata:
        order, errore = crea_ordine_da_richiesta(richiesta)
        if errore:
            richiesta.stato = 'rifiutata'
            richiesta.motivo = errore
            db.session.commit()
            send_reminder_to_user(
                richiesta.user,
                f'😕 La tua richiesta di <b>{numero_italiano(richiesta.importo)}€</b> non può '
                f'essere approvata: {errore}',
                subject='Richiesta non approvabile')
            return False, 'Non approvabile: %s' % errore
        richiesta.stato = 'approvata'
        richiesta.order_id = order.id
        db.session.commit()
        slot_label = 'adesso al banco' if not order.slot_id else f'alle {order.slot.time_str}'
        send_reminder_to_user(
            richiesta.user,
            f'✅ La tua richiesta di <b>{numero_italiano(richiesta.importo)}€</b> è stata '
            f'approvata! Ordine <b>{order.order_code}</b> confermato, ritiro {slot_label}.',
            subject='Richiesta approvata')
        return True, 'Approvata: ordine %s creato.' % order.order_code

    richiesta.stato = 'rifiutata'
    db.session.commit()
    testo = f'😕 La tua richiesta di <b>{numero_italiano(richiesta.importo)}€</b> è stata rifiutata.'
    if richiesta.motivo:
        testo += f'\nMotivo: {richiesta.motivo}'
    send_reminder_to_user(richiesta.user, testo, subject='Richiesta rifiutata')
    return True, 'Richiesta rifiutata.'
