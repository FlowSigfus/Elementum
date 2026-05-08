from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database as db
import rewards
from decorators import login_required
from utils.helpers import get_user_by_id   

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/inventory')
@login_required
def inventory():
    """ Отображает коллекцию карт текущего пользователя"""
    current_user = get_user_by_id(session['user_id'])   
    with db.get_db() as conn:
        rows = conn.execute('''
            SELECT c.*, uc.quantity, uc.level
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = ?
        ''', (session['user_id'],)).fetchall()
    cards = list(rows)
    rarity_order = {'обычная': 1, 'редкая': 2, 'эпическая': 3, 'легендарная': 4}
    cards.sort(key=lambda card: rarity_order.get(card['rarity'], 0), reverse=True)
    return render_template('inventory.html', cards=cards, current_user=current_user)

@inventory_bp.route('/craft')
@login_required
def craft_page():
    """ Отображает страницу крафта карт"""
    current_user = get_user_by_id(session['user_id']) 
    with db.get_db() as conn:
        user_cards = conn.execute('''
            SELECT c.id, c.name, c.rarity, uc.quantity
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = ? AND uc.quantity > 0
        ''', (session['user_id'],)).fetchall()
    return render_template('craft.html', user_cards=user_cards, current_user=current_user)

@inventory_bp.route('/craft/do', methods=['POST'])
@login_required
def craft_do():
    """Сбор выбранных карт из формы, Проверка количества карт (3), Проверка наличия и редкости, Определение следующей редкости, Выбор случайной карты новой редкости, Проверка достижений"""
    # Собираем словарь { card_id: количество } из формы
    selected = {}
    for key, value in request.form.items():
        if key.startswith('qty_'):
            try:
                card_id = int(key[4:])
                qty = int(value)
                if qty > 0:
                    selected[card_id] = qty
            except ValueError:
                pass

    total_qty = sum(selected.values())
    if total_qty != 3:
        flash('Нужно выбрать ровно 3 карты')
        return redirect(url_for('inventory.craft_page'))

    with db.get_db() as conn:
        # Проверяем наличие и редкость
        rarities = set()
        for card_id, qty in selected.items():
            row = conn.execute('''
                SELECT c.rarity, uc.quantity
                FROM user_cards uc
                JOIN cards c ON uc.card_id = c.id
                WHERE uc.user_id = ? AND uc.card_id = ?
            ''', (session['user_id'], card_id)).fetchone()
            if not row or row['quantity'] < qty:
                flash('Недостаточно карт для крафта')
                return redirect(url_for('inventory.craft_page'))
            rarities.add(row['rarity'])

        if len(rarities) != 1:
            flash('Все карты должны быть одной редкости')
            return redirect(url_for('inventory.craft_page'))

        rarity = rarities.pop()
        # Определяем следующую редкость
        rarity_map = {
            'обычная': 'редкая',
            'редкая': 'эпическая',
            'эпическая': 'легендарная'
        }
        new_rarity = rarity_map.get(rarity)
        if not new_rarity:
            flash('Эту редкость нельзя улучшить')
            return redirect(url_for('inventory.craft_page'))

        # Выбираем случайную карту новой редкости
        target_card = conn.execute(
            'SELECT id FROM cards WHERE rarity = ? ORDER BY RANDOM() LIMIT 1',
            (new_rarity,)
        ).fetchone()
        if not target_card:
            flash('Нет доступных карт для крафта')
            return redirect(url_for('inventory.craft_page'))

        # Списываем карты
        for card_id, qty in selected.items():
            conn.execute(
                'UPDATE user_cards SET quantity = quantity - ? WHERE user_id = ? AND card_id = ?',
                (qty, session['user_id'], card_id)
            )
            # Удаляем записи с нулевым количеством
            conn.execute(
                'DELETE FROM user_cards WHERE user_id = ? AND card_id = ? AND quantity <= 0',
                (session['user_id'], card_id)
            )

        # Выдаём новую карту
        conn.execute('''
            INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, 1)
            ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + 1
        ''', (session['user_id'], target_card['id']))
        conn.commit()

    # Проверяем достижения
    rewards.check_achievements(session['user_id'], 'crafts', 1)
    flash('Крафт успешен!')
    return redirect(url_for('inventory.craft_page'))
