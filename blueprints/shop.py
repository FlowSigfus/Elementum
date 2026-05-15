from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
import database as db
from decorators import login_required
import uuid
import os
import random
from utils.helpers import get_user_by_id
from services.yookassa_service import YookassaService
from extensions import mail
from flask_mail import Message
import logging

logger = logging.getLogger(__name__)

shop_bp = Blueprint('shop', __name__)

# Инициализация ЮKassa (ключи из .env)
yookassa = YookassaService(
    os.environ.get('YOOKASSA_SHOP_ID'),
    os.environ.get('YOOKASSA_SECRET_KEY')
)

# ---------- Вспомогательные функции ----------
def get_cart():
    cart = session.get('cart', {})
    return {int(k): v for k, v in cart.items()}

def set_cart(cart):
    session['cart'] = {str(k): v for k, v in cart.items()}
    session.modified = True

def get_product(product_id):
    with db.get_db() as conn:
        return conn.execute('SELECT * FROM shop_products WHERE id = ? AND is_active = 1', (product_id,)).fetchone()

def send_receipt_email(order, payment_info):
    """Отправляет чек на email покупателя."""
    try:
        amount_rub = payment_info['amount_cents'] / 100
        msg = Message(
            subject=f'Чек по заказу №{order["id"]}',
            recipients=[order['email']]
        )
        msg.body = f"""Здравствуйте, {order['fullname']}!

Ваш заказ №{order['id']} успешно оплачен.
Сумма: {amount_rub:.2f} руб.

Спасибо за покупку!"""
        mail.send(msg)
        logger.info(f"Чек отправлен на {order['email']}")
    except Exception as e:
        logger.error(f"Ошибка отправки чека: {e}")

# ---------- Маршруты ----------
@shop_bp.route('/')
def catalog():
    with db.get_db() as conn:
        products = conn.execute('SELECT * FROM shop_products WHERE is_active = 1').fetchall()
    cart = get_cart()
    return render_template('shop_catalog.html', products=products, cart=cart)

@shop_bp.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    product_id = int(request.form.get('product_id'))
    quantity = int(request.form.get('quantity', 1))
    cart = get_cart()
    cart[product_id] = cart.get(product_id, 0) + quantity
    set_cart(cart)
    flash('Товар добавлен в корзину')
    return redirect(url_for('shop.catalog'))

@shop_bp.route('/cart')
@login_required
def cart():
    cart = get_cart()
    products = []
    total_cents = 0
    with db.get_db() as conn:
        for pid, qty in cart.items():
            product = conn.execute('SELECT * FROM shop_products WHERE id = ?', (pid,)).fetchone()
            if product:
                item_total = product['price_cents'] * qty
                total_cents += item_total
                products.append({
                    'product': product,
                    'quantity': qty,
                    'item_total_cents': item_total
                })
    return render_template('shop_cart.html', products=products, total_cents=total_cents)

@shop_bp.route('/cart/update', methods=['POST'])
@login_required
def update_cart():
    product_id = int(request.form.get('product_id'))
    quantity = int(request.form.get('quantity', 0))
    cart = get_cart()
    if quantity <= 0:
        cart.pop(product_id, None)
    else:
        cart[product_id] = quantity
    set_cart(cart)
    return redirect(url_for('shop.cart'))

@shop_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = get_cart()
    if not cart:
        flash('Корзина пуста')
        return redirect(url_for('shop.catalog'))

    with db.get_db() as conn:
        # Определяем, есть ли физические товары
        has_physical = False
        items = []
        total_cents = 0
        for pid, qty in cart.items():
            product = conn.execute('SELECT * FROM shop_products WHERE id = ?', (pid,)).fetchone()
            if not product or product['stock'] < qty:
                flash(f'Товар {product["name"] if product else pid} недоступен')
                return redirect(url_for('shop.cart'))
            total_cents += product['price_cents'] * qty
            items.append({'product': product, 'quantity': qty})
            if not product['is_digital']:
                has_physical = True

        if request.method == 'POST':
            fullname = request.form.get('fullname')
            email = request.form.get('email')
            phone = request.form.get('phone')
            delivery_method = request.form.get('delivery_method', 'pickup') if has_physical else 'digital'
            delivery_address = request.form.get('delivery_address', '') if has_physical else ''
            agree_privacy = request.form.get('agree_privacy')
            agree_offer = request.form.get('agree_offer')

            if not agree_privacy or not agree_offer:
                flash('Необходимо принять условия')
                return render_template('shop_checkout.html', has_physical=has_physical)

            delivery_price = 0
            if has_physical and delivery_method != 'pickup':
                if delivery_method == 'pochta':
                    delivery_price = 20000
                elif delivery_method == 'cdek':
                    delivery_price = 35000
                if not delivery_address:
                    flash('Укажите адрес доставки')
                    return render_template('shop_checkout.html', has_physical=has_physical)

            total_cents += delivery_price

            order_id = str(uuid.uuid4())[:8]
            conn.execute('''
                INSERT INTO shop_orders (id, user_id, fullname, email, phone, delivery_method, delivery_address, delivery_price_cents, total_cents, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (order_id, session['user_id'], fullname, email, phone, delivery_method, delivery_address, delivery_price, total_cents, 'new'))
            for item in items:
                conn.execute('''
                    INSERT INTO shop_order_items (order_id, product_id, quantity, price_cents)
                    VALUES (?, ?, ?, ?)
                ''', (order_id, item['product']['id'], item['quantity'], item['product']['price_cents']))
                conn.execute('UPDATE shop_products SET stock = stock - ? WHERE id = ?', (item['quantity'], item['product']['id']))
            conn.commit()

            set_cart({})  # очищаем корзину после создания заказа
            return redirect(url_for('shop.init_payment', order_id=order_id))

    # GET-запрос – просто показываем форму оформления
    return render_template('shop_checkout.html', has_physical=has_physical)

@shop_bp.route('/payment/init/<order_id>')
@login_required
def init_payment(order_id):
    with db.get_db() as conn:
        order = conn.execute('SELECT * FROM shop_orders WHERE id = ? AND user_id = ?', (order_id, session['user_id'])).fetchone()
        if not order or order['status'] != 'new':
            flash('Заказ не найден')
            return redirect(url_for('shop.catalog'))
        # Собираем позиции для чека
        items = conn.execute('''
            SELECT oi.*, p.name, p.is_digital
            FROM shop_order_items oi
            JOIN shop_products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
        ''', (order_id,)).fetchall()
        receipt_items = []
        for item in items:
            receipt_items.append({
                'description': item['name'][:128],
                'quantity': str(item['quantity']),
                'amount': {
                    'value': f'{item["price_cents"] / 100:.2f}',
                    'currency': 'RUB'
                },
                'vat_code': 1,
                'payment_mode': 'full_prepayment',
                'payment_subject': 'commodity' if not item['is_digital'] else 'service'
            })
        # Добавляем доставку как отдельную позицию, если есть
        if order['delivery_price_cents'] > 0:
            receipt_items.append({
                'description': 'Доставка',
                'quantity': '1',
                'amount': {
                    'value': f'{order["delivery_price_cents"] / 100:.2f}',
                    'currency': 'RUB'
                },
                'vat_code': 1,
                'payment_mode': 'full_prepayment',
                'payment_subject': 'service'
            })

    description = f'Заказ №{order_id}'
    return_url = url_for('shop.payment_result', order_id=order_id, _external=True)
    try:
        payment = yookassa.create_payment(
            order_id, order['total_cents'], description,
            order['email'], return_url, receipt_items
        )
    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}")
        flash('Не удалось создать платёж, попробуйте позже')
        return redirect(url_for('shop.cart'))

    # Сохраняем запись о платеже
    with db.get_db() as conn:
        conn.execute('''
            INSERT INTO shop_payments (id, order_id, amount_cents, status, yookassa_id, confirmation_url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), order_id, order['total_cents'], 'pending', payment['id'], payment['confirmation_url']))
        conn.commit()

    return redirect(payment['confirmation_url'])

@shop_bp.route('/payment/result/<order_id>')
@login_required
def payment_result(order_id):
    """Страница после возврата с ЮKassa (успех/неудача)"""
    # Проверяем статус платежа через API
    with db.get_db() as conn:
        payment = conn.execute('SELECT * FROM shop_payments WHERE order_id = ? ORDER BY paid_at DESC LIMIT 1', (order_id,)).fetchone()
        if payment and payment['yookassa_id']:
            try:
                yookassa_payment = yookassa.get_payment(payment['yookassa_id'])
                if yookassa_payment.status == 'succeeded' and payment['status'] != 'succeeded':
                    conn.execute("UPDATE shop_payments SET status = 'succeeded', paid_at = CURRENT_TIMESTAMP WHERE id = ?", (payment['id'],))
                    conn.execute("UPDATE shop_orders SET status = 'paid' WHERE id = ?", (order_id,))
                    conn.commit()
                    # Отправляем чек
                    order = conn.execute('SELECT * FROM shop_orders WHERE id = ?', (order_id,)).fetchone()
                    send_receipt_email(order, payment)
                    flash('Оплата прошла успешно!')
                    return render_template('payment_success.html', order=order)
            except Exception as e:
                logger.error(f"Ошибка проверки статуса: {e}")
    flash('Статус оплаты уточняется. Если деньги списаны, они будут зачислены автоматически.')
    return redirect(url_for('shop.cart'))

@shop_bp.route('/payment/webhook', methods=['POST'])
def yookassa_webhook():
    data = request.get_json()
    if not data or data.get('event') != 'payment.succeeded':
        return '', 200
    payment_id = data['object']['id']
    with db.get_db() as conn:
        payment = conn.execute('SELECT * FROM shop_payments WHERE yookassa_id = ?', (payment_id,)).fetchone()
        if not payment or payment['status'] == 'succeeded':
            return '', 200
        order = conn.execute('SELECT * FROM shop_orders WHERE id = ?', (payment['order_id'],)).fetchone()
        if not order:
            return '', 200
        # Обновляем статусы
        conn.execute("UPDATE shop_payments SET status = 'succeeded', paid_at = CURRENT_TIMESTAMP WHERE yookassa_id = ?", (payment_id,))
        conn.execute("UPDATE shop_orders SET status = 'paid' WHERE id = ?", (payment['order_id'],))
        # Начисляем цифровые товары
        items = conn.execute('''
            SELECT oi.quantity, p.name, p.is_digital
            FROM shop_order_items oi
            JOIN shop_products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
        ''', (payment['order_id'],)).fetchall()
        for item in items:
            if item['is_digital'] and 'монет' in item['name'].lower():
                # Извлекаем количество монет (предполагаем, что в названии "100 монет")
                try:
                    coin_amount = int(item['name'].split()[0])
                except:
                    coin_amount = 0
                if coin_amount > 0:
                    conn.execute('UPDATE users SET coins = coins + ? WHERE id = ?', (coin_amount * item['quantity'], order['user_id']))
        conn.commit()
        # Отправляем чек
        send_receipt_email(order, payment)
    return '', 200

# Существующий игровой магазин за монеты (оставляем без изменений)
@shop_bp.route('/game-shop')
@login_required
def game_shop():
    current_user = get_user_by_id(session['user_id'])
    with db.get_db() as conn:
        user_coins = conn.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],)).fetchone()['coins']
        cards = conn.execute('SELECT id, name, rarity FROM cards').fetchall()
        cards_for_sale = []
        for c in cards:
            rarity_prices = {'обычная': 20, 'редкая': 50, 'эпическая': 150, 'легендарная': 500}
            price = rarity_prices.get(c['rarity'], 50)
            cards_for_sale.append({'id': c['id'], 'name': c['name'], 'rarity': c['rarity'], 'price': price})
        random.shuffle(cards_for_sale)
        cards_for_sale = cards_for_sale[:12]
    return render_template('game_shop.html', current_user=current_user, user_coins=user_coins, cards=cards_for_sale)

@shop_bp.route('/buy-card/<int:card_id>')
@login_required
def buy_card(card_id):
    current_user = get_user_by_id(session['user_id'])
    with db.get_db() as conn:
        card = conn.execute('SELECT id, name, rarity FROM cards WHERE id = ?', (card_id,)).fetchone()
        if not card:
            flash('Карта не найдена')
            return redirect(url_for('shop.game_shop'))
        rarity_prices = {'обычная': 20, 'редкая': 50, 'эпическая': 150, 'легендарная': 500}
        price = rarity_prices.get(card['rarity'], 50)
        user_coins = conn.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],)).fetchone()['coins']
        if user_coins < price:
            flash(f'Недостаточно монет. Нужно {price}, у вас {user_coins}')
            return redirect(url_for('shop.game_shop'))
        conn.execute('UPDATE users SET coins = coins - ? WHERE id = ?', (price, session['user_id']))
        conn.execute('''
            INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, 1)
            ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + 1
        ''', (session['user_id'], card_id))
        conn.commit()
    flash(f'Вы купили карту {card["name"]} за {price} монет!')
    return redirect(url_for('shop.game_shop'))
