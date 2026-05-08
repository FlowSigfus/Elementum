from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import database as db
import uuid
from utils.helpers import get_user_by_id, get_card_by_id
from battle import PVPBattle
from utils.cache import active_pvp_battles
from decorators import login_required

pvp_bp = Blueprint('pvp', __name__)

# ---------- Вспомогательные функции ----------
def add_to_queue(user_id):
    with db.get_db() as conn:
        existing = conn.execute('SELECT user_id FROM pvp_queue WHERE user_id = ?', (user_id,)).fetchone()
        if existing:
            return False, "Вы уже в очереди"
        conn.execute('INSERT INTO pvp_queue (user_id) VALUES (?)', (user_id,))
        conn.commit()
    return True, "Вы добавлены в очередь"

# ---------- Маршруты ----------
@pvp_bp.route('/pvp')
@login_required
def pvp_index():
    current_user = get_user_by_id(session['user_id'])
    with db.get_db() as conn:
        rating_row = conn.execute('SELECT rating FROM pvp_rating WHERE user_id = ?', (session['user_id'],)).fetchone()
        if not rating_row:
            conn.execute('INSERT INTO pvp_rating (user_id) VALUES (?)', (session['user_id'],))
            conn.commit()
            rating = 1200
        else:
            rating = rating_row['rating']
        leaderboard = conn.execute('''
            SELECT u.username, pr.rating, pr.wins, pr.losses
            FROM pvp_rating pr
            JOIN users u ON pr.user_id = u.id
            ORDER BY pr.rating DESC
            LIMIT 10
        ''').fetchall()
    return render_template('pvp/index.html', current_user=current_user, rating=rating, leaderboard=leaderboard)

@pvp_bp.route('/pvp/leaderboard')
@login_required
def leaderboard():
    current_user = get_user_by_id(session['user_id'])
    with db.get_db() as conn:
        rows = conn.execute('''
            SELECT u.username, pr.rating, pr.wins, pr.losses, pr.user_id
            FROM pvp_rating pr
            JOIN users u ON pr.user_id = u.id
            ORDER BY pr.rating DESC
            LIMIT 50
        ''').fetchall()
    return render_template('pvp/leaderboard.html', current_user=current_user, leaderboard=rows)

@pvp_bp.route('/pvp/queue', methods=['POST'])
@login_required
def queue():
    success, msg = add_to_queue(session['user_id'])
    return jsonify({'success': success, 'message': msg})

@pvp_bp.route('/pvp/status')
@login_required
def queue_status():
    user_id = session['user_id']
    with db.get_db() as conn:
        # Ищем активный матч
        match = conn.execute('''
            SELECT id, player1_id, player2_id, status
            FROM pvp_matches
            WHERE (player1_id = ? OR player2_id = ?) AND status != 'finished'
        ''', (user_id, user_id)).fetchone()
        if match:
            if match['status'] == 'waiting' and match['player2_id'] is not None:
                conn.execute('UPDATE pvp_matches SET status = "active" WHERE id = ?', (match['id'],))
                conn.commit()
            return jsonify({'status': 'found', 'match_id': match['id']})
        # Поиск соперника в очереди
        rating_row = conn.execute('SELECT rating FROM pvp_rating WHERE user_id = ?', (user_id,)).fetchone()
        rating = rating_row['rating'] if rating_row else 1200
        opponent = conn.execute('''
            SELECT user_id FROM pvp_queue
            WHERE user_id != ?
            ORDER BY ABS((SELECT rating FROM pvp_rating WHERE user_id = pvp_queue.user_id) - ?)
            LIMIT 1
        ''', (user_id, rating)).fetchone()
        if opponent:
            # Удаляем из очереди и создаём матч
            conn.execute('DELETE FROM pvp_queue WHERE user_id IN (?, ?)', (user_id, opponent['user_id']))
            match_id = str(uuid.uuid4())
            conn.execute('''
                INSERT INTO pvp_matches (id, player1_id, player2_id, status)
                VALUES (?, ?, ?, 'waiting')
            ''', (match_id, user_id, opponent['user_id']))
            conn.commit()
            return jsonify({'status': 'found', 'match_id': match_id})
    return jsonify({'status': 'waiting'})

@pvp_bp.route('/pvp/match/<match_id>')
@login_required
def pvp_match(match_id):
    current_user = get_user_by_id(session['user_id'])
    user_id = session['user_id']
    with db.get_db() as conn:
        match = conn.execute('SELECT * FROM pvp_matches WHERE id = ?', (match_id,)).fetchone()
        if not match:
            flash('Матч не найден')
            return redirect(url_for('pvp.pvp_index'))
        if user_id not in (match['player1_id'], match['player2_id']):
            flash('Вы не участник этого матча')
            return redirect(url_for('pvp.pvp_index'))
        if match_id not in active_pvp_battles:
            player1 = get_user_by_id(match['player1_id'])
            player2 = get_user_by_id(match['player2_id'])
            rows1 = conn.execute('SELECT card_id, quantity FROM user_cards WHERE user_id = ? AND quantity > 0', (match['player1_id'],)).fetchall()
            rows2 = conn.execute('SELECT card_id, quantity FROM user_cards WHERE user_id = ? AND quantity > 0', (match['player2_id'],)).fetchall()
            player1_cards = {row['card_id']: row['quantity'] for row in rows1}
            player2_cards = {row['card_id']: row['quantity'] for row in rows2}
            battle = PVPBattle(player1, player2, player1_cards, player2_cards, get_card_by_id)
            active_pvp_battles[match_id] = battle
        else:
            battle = active_pvp_battles[match_id]
        is_player1 = (user_id == match['player1_id'])
        return render_template('pvp/battle.html',
                               current_user=current_user,
                               battle=battle,
                               match_id=match_id,
                               is_player1=is_player1,
                               get_card_by_id=get_card_by_id)

@pvp_bp.route('/pvp/move', methods=['POST'])
@login_required
def pvp_move():
    data = request.get_json()
    match_id = data.get('match_id')
    card_id = data.get('card_id')
    if not match_id or not card_id:
        return jsonify({'success': False, 'message': 'Не хватает данных'})
    battle = active_pvp_battles.get(match_id)
    if not battle:
        return jsonify({'success': False, 'message': 'Бой не найден'})
    success, msg = battle.apply_card(session['user_id'], card_id)
    if success and battle.winner:
        # Обновляем рейтинг и удаляем матч
        with db.get_db() as conn:
            winner_id = battle.winner
            loser_id = battle.player2.id if winner_id == battle.player1.id else battle.player1.id
            # Загружаем текущие рейтинги
            winner_rating = conn.execute('SELECT rating FROM pvp_rating WHERE user_id = ?', (winner_id,)).fetchone()['rating']
            loser_rating = conn.execute('SELECT rating FROM pvp_rating WHERE user_id = ?', (loser_id,)).fetchone()['rating']
            # Формула ELO
            expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
            expected_loser = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))
            new_winner = winner_rating + 32 * (1 - expected_winner)
            new_loser = loser_rating + 32 * (0 - expected_loser)
            conn.execute('UPDATE pvp_rating SET rating = ?, wins = wins + 1 WHERE user_id = ?', (int(new_winner), winner_id))
            conn.execute('UPDATE pvp_rating SET rating = ?, losses = losses + 1 WHERE user_id = ?', (int(new_loser), loser_id))
            conn.execute('UPDATE pvp_matches SET status = "finished", winner_id = ? WHERE id = ?', (winner_id, match_id))
            conn.execute('UPDATE users SET coins = coins + 100 WHERE id = ?', (winner_id,))
            conn.commit()
        del active_pvp_battles[match_id]
    return jsonify({'success': success, 'message': msg})

@pvp_bp.route('/duel/challenge/<int:opponent_id>')
@login_required
def challenge(opponent_id):
    if opponent_id == session['user_id']:
        flash('Нельзя вызвать себя')
        return redirect(url_for('main.index'))
    with db.get_db() as conn:
        # Проверим, не занят ли текущий игрок или соперник в активном матче
        active_match = conn.execute('''
            SELECT id FROM pvp_matches
            WHERE (player1_id = ? OR player2_id = ?) AND status != 'finished'
        ''', (session['user_id'], session['user_id'])).fetchone()
        if active_match:
            flash('Вы уже участвуете в бою. Завершите его.')
            return redirect(url_for('pvp.pvp_index'))
        active_opponent = conn.execute('''
            SELECT id FROM pvp_matches
            WHERE (player1_id = ? OR player2_id = ?) AND status != 'finished'
        ''', (opponent_id, opponent_id)).fetchone()
        if active_opponent:
            flash('Соперник уже в бою')
            return redirect(url_for('main.view_profile', user_id=opponent_id))
        row = conn.execute('SELECT allow_duels FROM users WHERE id = ?', (opponent_id,)).fetchone()
        if not row or not row['allow_duels']:
            flash('Игрок отключил вызовы')
            return redirect(url_for('main.view_profile', user_id=opponent_id))
        # Очищаем очередь
        conn.execute('DELETE FROM pvp_queue WHERE user_id IN (?, ?)', (session['user_id'], opponent_id))
        match_id = str(uuid.uuid4())
        conn.execute('''
            INSERT INTO pvp_matches (id, player1_id, player2_id, status)
            VALUES (?, ?, ?, 'waiting')
        ''', (match_id, session['user_id'], opponent_id))
        conn.commit()
    return redirect(url_for('pvp.pvp_match', match_id=match_id))