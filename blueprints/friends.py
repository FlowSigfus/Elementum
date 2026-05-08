from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import database as db
import secrets
from decorators import login_required
from utils.helpers import get_user_by_id   # добавлен импорт

friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/friends')
@login_required
def friends():
    """ Отображает страницу со списком друзей пользователя, входящими и исходящими заявками"""
    current_user = get_user_by_id(session['user_id'])
    with db.get_db() as conn:
        accepted = conn.execute('''
            SELECT u.id, u.username, u.avatar
            FROM friends f
            JOIN users u ON (f.friend_id = u.id OR f.user_id = u.id)
            WHERE (f.user_id = ? OR f.friend_id = ?) AND f.status = 'accepted' AND u.id != ?
        ''', (session['user_id'], session['user_id'], session['user_id'])).fetchall()
        incoming = conn.execute('''
            SELECT u.id, u.username, u.avatar
            FROM friends f
            JOIN users u ON f.user_id = u.id
            WHERE f.friend_id = ? AND f.status = 'pending'
        ''', (session['user_id'],)).fetchall()
        outgoing = conn.execute('''
            SELECT u.id, u.username, u.avatar
            FROM friends f
            JOIN users u ON f.friend_id = u.id
            WHERE f.user_id = ? AND f.status = 'pending'
        ''', (session['user_id'],)).fetchall()
    return render_template('friends.html',
                           accepted=accepted,
                           incoming=incoming,
                           outgoing=outgoing,
                           current_user=current_user)

@friends_bp.route('/friends/add/<int:user_id>')
@login_required
def friend_add(user_id):
    """Отправка заявки в друзья другому пользователю"""
    if user_id == session['user_id']:
        flash('Нельзя добавить себя')
        return redirect(url_for('main.dashboard'))
    with db.get_db() as conn:
        existing = conn.execute('SELECT status FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)',
                                (session['user_id'], user_id, user_id, session['user_id'])).fetchone()
        if existing:
            flash('Запрос уже отправлен или вы уже друзья')
            return redirect(url_for('main.view_profile', user_id=user_id))
        conn.execute('INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, ?)', (session['user_id'], user_id, 'pending'))
        conn.commit()
    flash('Запрос в друзья отправлен')
    return redirect(url_for('main.view_profile', user_id=user_id))

@friends_bp.route('/friends/accept/<int:user_id>')
@login_required
def friend_accept(user_id):
    """ Принять входящую заявку в друзья"""
    with db.get_db() as conn:
        conn.execute('UPDATE friends SET status = "accepted" WHERE user_id = ? AND friend_id = ?', (user_id, session['user_id']))
        conn.commit()
    flash('Пользователь добавлен в друзья')
    return redirect(url_for('friends.friends'))

@friends_bp.route('/friends/reject/<int:user_id>')
@login_required
def friend_reject(user_id):
    """ Отклонить входящую заявку в друзья"""
    with db.get_db() as conn:
        conn.execute('DELETE FROM friends WHERE user_id = ? AND friend_id = ?', (user_id, session['user_id']))
        conn.commit()
    flash('Запрос отклонён')
    return redirect(url_for('friends.friends'))

@friends_bp.route('/friends/remove/<int:user_id>')
@login_required
def friend_remove(user_id):
    """ Удалить другого пользователя из списка друзей"""
    with db.get_db() as conn:
        conn.execute('DELETE FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)',
                     (session['user_id'], user_id, user_id, session['user_id']))
        conn.commit()
    flash('Пользователь удалён из друзей')
    return redirect(url_for('friends.friends'))

@friends_bp.route('/friends/invite/token')
@login_required
def friend_invite_token():
    """Генерация пригласительной ссылки"""
    token = secrets.token_urlsafe(16)
    with db.get_db() as conn:
        conn.execute('INSERT INTO friend_invites (user_id, token) VALUES (?, ?)', (session['user_id'], token))
        conn.commit()
    invite_link = url_for('friends.friend_join', token=token, _external=True)
    current_user = get_user_by_id(session['user_id'])
    return render_template('friend_invite.html', link=invite_link, current_user=current_user)

@friends_bp.route('/friends/invite/<token>')
@login_required
def friend_join(token):
    """ Принятие приглашения"""
    with db.get_db() as conn:
        inv = conn.execute('SELECT user_id FROM friend_invites WHERE token = ?', (token,)).fetchone()
        if not inv:
            flash('Неверное приглашение')
            return redirect(url_for('friends.friends'))
        inviter_id = inv['user_id']
        if inviter_id == session['user_id']:
            flash('Нельзя добавить себя')
            return redirect(url_for('friends.friends'))
        existing = conn.execute('SELECT status FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)',
                                (session['user_id'], inviter_id, inviter_id, session['user_id'])).fetchone()
        if existing:
            flash('Запрос уже существует или вы уже друзья')
        else:
            conn.execute('INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, ?)', (session['user_id'], inviter_id, 'pending'))
            conn.commit()
            flash('Запрос в друзья отправлен')
    return redirect(url_for('friends.friends'))

@friends_bp.route('/friends/status/<int:user_id>')
@login_required
def friend_status(user_id):
    """ Возвращает статус дружбы между текущим пользователем и указанным user_id в формате JSON"""
    with db.get_db() as conn:
        row = conn.execute('''
            SELECT status FROM friends
            WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)
        ''', (session['user_id'], user_id, user_id, session['user_id'])).fetchone()
        if not row:
            return jsonify({'status': 'none'})
        return jsonify({'status': row['status']})

@friends_bp.route('/friends/cancel/<int:user_id>')
@login_required
def friend_cancel(user_id):
    """ Отменить исходящую заявку в друзья"""
    with db.get_db() as conn:
        conn.execute('''
            DELETE FROM friends
            WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)
        ''', (session['user_id'], user_id, user_id, session['user_id']))
        conn.commit()
    flash('Запрос отменён')
    return redirect(url_for('main.view_profile', user_id=user_id))