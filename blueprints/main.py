from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database as db
from utils.helpers import get_user_by_id
from decorators import login_required
from extensions import mail
from flask_mail import Message

main_bp = Blueprint('main', __name__)

# Публичные страницы
@main_bp.route('/')
def public_index():
    return render_template('public_index.html')

@main_bp.route('/how-to-play')
def how_to_play():
    return render_template('how_to_play.html')

@main_bp.route('/faq')
def faq():
    return render_template('faq.html')

@main_bp.route('/contacts')
def contacts():
    return render_template('contacts.html')

@main_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

# Игровая панель (дашборд)
@main_bp.route('/dashboard')
@login_required
def dashboard():
    current_user = get_user_by_id(session['user_id'])
    if not current_user:
        session.clear()
        flash('Сессия устарела, войдите заново')
        return redirect(url_for('auth.login'))
    with db.get_db() as conn:
        row = conn.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        user_coins = row['coins'] if row else 0
        recent_offers = conn.execute('''
            SELECT o.id, u.username, c.name as give_name, o.quantity, wc.name as want_name, o.wanted_type, o.wanted_coins
            FROM trade_offers o
            JOIN users u ON o.user_id = u.id
            JOIN cards c ON o.card_id = c.id
            LEFT JOIN cards wc ON o.wanted_card_id = wc.id
            WHERE o.user_id != ? AND o.status = 'active'
            ORDER BY o.created_at DESC LIMIT 5
        ''', (session['user_id'],)).fetchall()
    return render_template('index.html', current_user=current_user, user_coins=user_coins, recent_offers=recent_offers)

@main_bp.route('/reset_story', methods=['POST'])
@login_required
def reset_story():
    with db.get_db() as conn:
        conn.execute('UPDATE story_progress SET chapter = 1, battle_index = 0 WHERE user_id = ?', (session['user_id'],))
        conn.commit()
    flash('Прогресс сюжета сброшен.')
    return redirect(url_for('main.dashboard'))

# Просмотр чужого профиля
@main_bp.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    if user_id == session['user_id']:
        return redirect(url_for('profile.profile'))
    user = get_user_by_id(user_id)
    if not user:
        flash('Пользователь не найден')
        return redirect(url_for('main.dashboard'))
    with db.get_db() as conn:
        stats = conn.execute('SELECT wins, losses, total_damage FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
        achievements = conn.execute('''
            SELECT a.name, a.description, ua.unlocked_at
            FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.id
            WHERE ua.user_id = ?
        ''', (user_id,)).fetchall()
        showcase = conn.execute('''
            SELECT c.id, c.name, c.rarity, s.slot
            FROM showcase s
            JOIN cards c ON s.card_id = c.id
            WHERE s.user_id = ?
            ORDER BY s.slot
        ''', (user_id,)).fetchall()
        friendship = conn.execute('''
            SELECT status FROM friends
            WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)
        ''', (session['user_id'], user_id, user_id, session['user_id'])).fetchone()
        friend_status = friendship['status'] if friendship else None
        friend_from_me = False
        if friend_status == 'pending':
            sender = conn.execute('SELECT user_id FROM friends WHERE user_id = ? AND friend_id = ? AND status = "pending"',
                                  (session['user_id'], user_id)).fetchone()
            friend_from_me = bool(sender)
    return render_template('profile_view.html', user=user, stats=stats,
                           achievements=achievements, showcase=showcase,
                           friend_status=friend_status, friend_from_me=friend_from_me)

@main_bp.route('/contacts/send', methods=['POST'])
def send_contact():
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')
    
    if not name or not email or not message:
        flash('Заполните все поля')
        return redirect(url_for('main.contacts'))
    
    # Отправляем письмо администратору
    msg = Message(
        subject=f'Сообщение с сайта от {name}',
        recipients=['your_admin_email@example.com'],  # Укажите свой email
        body=f'Имя: {name}\nEmail: {email}\n\nСообщение:\n{message}'
    )
    try:
        mail.send(msg)
        flash('Сообщение отправлено. Мы ответим вам в ближайшее время.', 'success')
    except Exception as e:
        flash('Ошибка при отправке. Попробуйте позже.', 'danger')
    
    return redirect(url_for('main.contacts'))
