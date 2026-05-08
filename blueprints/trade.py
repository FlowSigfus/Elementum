from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database as db
import rewards
from decorators import login_required
from utils.helpers import get_user_by_id

trade_bp = Blueprint('trade', __name__)

@trade_bp.route('/trade')
@login_required
def trade():
    """ Отображает страницу торговой площадки
    Получает параметры запроса: page – номер страницы, sort – тип сортировки (newest, oldest, give_card, want_card, give_coins, want_coins), search – поисковый запрос (по имени пользователя, названию отдаваемой или желаемой карты).
    Запрашивает из БД активные предложения обмена (status = 'active'), исключая предложения текущего пользователя.
    Применяет поиск и сортировку, затем пагинацию (10 предложений на страницу).
    Запрашивает дополнительные данные для формы создания предложения: my_cards – карты текущего пользователя, all_cards – все существующие карты, user_coins – количество монет у пользователя"""
    current_user = get_user_by_id(session['user_id'])   
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'newest')
    search = request.args.get('search', '').strip()
    per_page = 10
    with db.get_db() as conn:
        # Базовый запрос
        query = '''
            SELECT o.*, u.username,
                   c.name as give_name,
                   wc.name as want_name
            FROM trade_offers o
            JOIN users u ON o.user_id = u.id
            LEFT JOIN cards c ON o.card_id = c.id
            LEFT JOIN cards wc ON o.wanted_card_id = wc.id
            WHERE o.user_id != ? AND o.status = 'active'
        '''
        params = [session['user_id']]

        if search:
            query += ' AND (u.username LIKE ? OR c.name LIKE ? OR wc.name LIKE ?)'
            search_param = f'%{search}%'
            params += [search_param, search_param, search_param]

        # Сортировка
        if sort_by == 'newest':
            query += ' ORDER BY o.created_at DESC'
        elif sort_by == 'oldest':
            query += ' ORDER BY o.created_at ASC'
        elif sort_by == 'give_card':
            query += ' ORDER BY c.name ASC'
        elif sort_by == 'want_card':
            query += ' ORDER BY wc.name ASC'
        elif sort_by == 'give_coins':
            query += ' ORDER BY o.give_coins ASC'
        elif sort_by == 'want_coins':
            query += ' ORDER BY o.wanted_coins ASC'
        else:
            query += ' ORDER BY o.created_at DESC'

        # Пагинация
        offset = (page - 1) * per_page
        query += ' LIMIT ? OFFSET ?'
        params.extend([per_page, offset])

        offers = conn.execute(query, params).fetchall()

        # Подсчёт общего количества для пагинации
        count_query = '''
            SELECT COUNT(*) as cnt
            FROM trade_offers o
            JOIN users u ON o.user_id = u.id
            LEFT JOIN cards c ON o.card_id = c.id
            LEFT JOIN cards wc ON o.wanted_card_id = wc.id
            WHERE o.user_id != ? AND o.status = 'active'
        '''
        count_params = [session['user_id']]
        if search:
            count_query += ' AND (u.username LIKE ? OR c.name LIKE ? OR wc.name LIKE ?)'
            count_params.extend([search_param, search_param, search_param])
        total = conn.execute(count_query, count_params).fetchone()['cnt']
        total_pages = (total + per_page - 1) // per_page

        # Данные для формы создания
        my_cards = conn.execute('''
            SELECT c.id, c.name, c.rarity, uc.quantity
            FROM user_cards uc JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = ? AND uc.quantity > 0
        ''', (session['user_id'],)).fetchall()
        all_cards = conn.execute('SELECT id, name, rarity FROM cards').fetchall()
        user_coins = conn.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],)).fetchone()['coins']

    return render_template('trade.html',
                           current_user=current_user, 
                           offers=offers,
                           my_cards=my_cards,
                           all_cards=all_cards,
                           user_coins=user_coins,
                           page=page,
                           total_pages=total_pages,
                           sort_by=sort_by,
                           search=search)

@trade_bp.route('/trade/create', methods=['POST'])
@login_required
def trade_create():
    """Cоздаёт предложение обмена.
    Получает из формы: give_card_id – ID отдаваемой карты, give_qty – количество, want_type – тип желаемого (card или coins), при want_type == 'card': want_card_id, want_qty, при want_type == 'coins': want_coins.
    Проверяет, что у пользователя есть достаточно карт (quantity >= give_qty).
    Немедленно списывает карты: UPDATE user_cards SET quantity = quantity - give_qty, затем удаляет запись, если количество стало 0.
    Вставляет запись в trade_offers с полями: user_id – текущий пользователь, card_id, quantity – отдаваемая карта и её количество, wanted_type – 'card' или 'coins', wanted_card_id, wanted_quantity – если тип 'card', wanted_coins – если тип 'coins'"""
    give_card_id = request.form.get('give_card_id')
    give_qty = int(request.form.get('give_qty', 1))
    want_type = request.form.get('want_type')
    want_card_id = request.form.get('want_card_id') if want_type == 'card' else None
    want_coins = int(request.form.get('want_coins', 0)) if want_type == 'coins' else 0
    want_qty = int(request.form.get('want_qty', 1)) if want_type == 'card' else 0
    with db.get_db() as conn:
        row = conn.execute('SELECT quantity FROM user_cards WHERE user_id = ? AND card_id = ?', (session['user_id'], give_card_id)).fetchone()
        if not row or row['quantity'] < give_qty:
            flash('У вас недостаточно карт')
            return redirect(url_for('trade.trade'))
        conn.execute('UPDATE user_cards SET quantity = quantity - ? WHERE user_id = ? AND card_id = ?', (give_qty, session['user_id'], give_card_id))
        conn.execute('DELETE FROM user_cards WHERE user_id = ? AND card_id = ? AND quantity <= 0', (session['user_id'], give_card_id))
        conn.execute('''
            INSERT INTO trade_offers (user_id, card_id, quantity, wanted_type, wanted_card_id, wanted_coins, wanted_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], give_card_id, give_qty, want_type, want_card_id, want_coins, want_qty))
        conn.commit()
    flash('Предложение создано')
    return redirect(url_for('trade.trade'))

@trade_bp.route('/trade/accept/<int:offer_id>')
@login_required
def trade_accept(offer_id):
    """обрабатывает принятие предложения обмена другим игроком/
    Поиск активного предложения.
    Запрет принятия своего предложения.
    В зависимости от типа желаемого (wanted_type):
        card – пользователь должен отдать нужную карту:
        Проверка наличия want_card_id в количестве want_qty.
        Списание want_qty карт у принимающего.
        Добавление offer['quantity'] отдаваемой карты принимающему.
        Добавление want_qty желаемой карты автору предложения.
        
        coins – пользователь должен отдать нужное количество монет:
        Проверка баланса (wanted_coins).
        Списание монет у принимающего, начисление автору предложения.
        Добавление offer['quantity'] отдаваемой карты принимающему (если в предложении была карта).
        
    Закрытие предложения – установка статуса closed.
    Проверка достижений – увеличивается счётчик trades."""
    with db.get_db() as conn:
        offer = conn.execute('SELECT * FROM trade_offers WHERE id = ? AND status = "active"', (offer_id,)).fetchone()
        if not offer:
            flash('Предложение не найдено')
            return redirect(url_for('trade.trade'))
        if offer['user_id'] == session['user_id']:
            flash('Нельзя принять своё предложение')
            return redirect(url_for('trade.trade'))
        if offer['wanted_type'] == 'card':
            want_card_id = offer['wanted_card_id']
            want_qty = offer['wanted_quantity']
            my_card = conn.execute('SELECT quantity FROM user_cards WHERE user_id = ? AND card_id = ?', (session['user_id'], want_card_id)).fetchone()
            if not my_card or my_card['quantity'] < want_qty:
                flash('У вас нет нужной карты')
                return redirect(url_for('trade.trade'))
            conn.execute('UPDATE user_cards SET quantity = quantity - ? WHERE user_id = ? AND card_id = ?', (want_qty, session['user_id'], want_card_id))
            conn.execute('DELETE FROM user_cards WHERE user_id = ? AND card_id = ? AND quantity <= 0', (session['user_id'], want_card_id))
            conn.execute('''
                INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + ?
            ''', (session['user_id'], offer['card_id'], offer['quantity'], offer['quantity']))
            conn.execute('''
                INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + ?
            ''', (offer['user_id'], want_card_id, want_qty, want_qty))
        else:  # монеты
            want_coins = offer['wanted_coins']
            user_coins = conn.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],)).fetchone()['coins']
            if user_coins < want_coins:
                flash(f'Недостаточно монет (нужно {want_coins})')
                return redirect(url_for('trade.trade'))
            conn.execute('UPDATE users SET coins = coins - ? WHERE id = ?', (want_coins, session['user_id']))
            conn.execute('UPDATE users SET coins = coins + ? WHERE id = ?', (want_coins, offer['user_id']))
            conn.execute('''
                INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + ?
            ''', (session['user_id'], offer['card_id'], offer['quantity'], offer['quantity']))
        conn.execute('UPDATE trade_offers SET status = "closed" WHERE id = ?', (offer_id,))
        conn.commit()
    rewards.check_achievements(session['user_id'], 'trades', 1)
    flash('Обмен выполнен')
    return redirect(url_for('trade.trade'))