from flask import Blueprint, render_template, request, jsonify, session
import database as db
from utils.helpers import get_card_by_nfc_hash
from utils.cache import active_battles
from decorators import login_required
from utils.helpers import get_user_by_id

nfc_bp = Blueprint('nfc', __name__)

@nfc_bp.route('/nfc')
@login_required
def nfc_page():
    current_user = get_user_by_id(session['user_id'])
    return render_template('nfc_scan.html', current_user=current_user)

@nfc_bp.route('/api/nfc_scan', methods=['POST'])
@login_required
def nfc_scan():
    """ Cканирование NFC-метки для получения карты/
    Получение данных — из JSON-тела запроса, Проверка наличия tag_id, Ограничение частоты выдачи, Поиск карты по NFC-хешу"""
    data = request.get_json()
    tag_id = data.get('tag_id')
    if not tag_id:
        return jsonify({'success': False, 'message': 'Нет ID метки'})
    with db.get_db() as conn:
        row = conn.execute('SELECT last_nfc FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        today = db.now_msk().date().isoformat()
        if row and row['last_nfc'] == today:
            return jsonify({'success': False, 'message': 'Можно получать карту через NFC только раз в 3 дня'})
        card_row = conn.execute('SELECT id, name FROM cards WHERE nfc_hash = ?', (tag_id,)).fetchone()
        if not card_row:
            return jsonify({'success': False, 'message': 'Неизвестная NFC-метка'})
        card_id = card_row['id']
        card_name = card_row['name']
        conn.execute('''
            INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, 1)
            ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + 1
        ''', (session['user_id'], card_id))
        conn.execute('UPDATE users SET last_nfc = ? WHERE id = ?', (today, session['user_id']))
        conn.commit()
    return jsonify({'success': True, 'message': f'Вы получили карту {card_name} через NFC!'})

@nfc_bp.route('/api/nfc_boost', methods=['POST'])
@login_required
def nfc_boost():
    """Использовать NFC-метку для одноразового усиления карты в текущем бою.
    Получение tag_id из JSON-запроса, Проверка лимита использования, Поиск карты по NFC-хешу, Проверка нахождения в бою, Проверка, что усиление ещё не использовано в этом бою (battle.boost_used), Применение усиления через battle.apply_boost(card).
      При успехе обновляется last_nfc_boost = today у пользователя в БД. Возврат JSON с success: true и сообщением от apply_boost"""
    data = request.get_json()
    tag_id = data.get('tag_id')
    if not tag_id:
        return jsonify({'success': False, 'message': 'Нет ID метки'})
    with db.get_db() as conn:
        row = conn.execute('SELECT last_nfc_boost FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        today = db.now_msk().date().isoformat()
        if row and row['last_nfc_boost'] == today:
            return jsonify({'success': False, 'message': 'Усиление можно использовать только раз в 3 дня'})
    card = get_card_by_nfc_hash(tag_id)
    if not card:
        return jsonify({'success': False, 'message': 'Неизвестная NFC-метка'})
    battle_id = session.get('battle_id')
    if not battle_id:
        return jsonify({'success': False, 'message': 'Вы не в бою'})
    battle = active_battles.get(battle_id)
    if not battle:
        return jsonify({'success': False, 'message': 'Бой не найден'})
    if battle.boost_used:
        return jsonify({'success': False, 'message': 'Усиление уже использовано в этом бою'})
    success, msg = battle.apply_boost(card)
    if not success:
        return jsonify({'success': False, 'message': msg})
    with db.get_db() as conn:
        conn.execute('UPDATE users SET last_nfc_boost = ? WHERE id = ?', (today, session['user_id']))
        conn.commit()
    return jsonify({'success': True, 'message': f'Усиление карты {card.name} применено! {msg}'})