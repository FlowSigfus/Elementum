from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
import database as db
import os
from werkzeug.utils import secure_filename
from utils.helpers import get_user_by_id, allowed_file
from decorators import login_required

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/profile')
@login_required
def profile():
    current_user = get_user_by_id(session['user_id'])
    with db.get_db() as conn:
        stats = conn.execute('SELECT wins, losses, total_damage FROM user_stats WHERE user_id = ?', (session['user_id'],)).fetchone()
        achievements = conn.execute('''
            SELECT a.name, a.description, ua.unlocked_at
            FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.id
            WHERE ua.user_id = ?
        ''', (session['user_id'],)).fetchall()
        showcase = conn.execute('''
            SELECT c.id, c.name, c.rarity, s.slot
            FROM showcase s
            JOIN cards c ON s.card_id = c.id
            WHERE s.user_id = ?
            ORDER BY s.slot
        ''', (session['user_id'],)).fetchall()
        user_cards = conn.execute('''
            SELECT c.id, c.name, c.rarity
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = ? AND uc.quantity > 0
        ''', (session['user_id'],)).fetchall()
    return render_template('profile.html', current_user=current_user, stats=stats, achievements=achievements, showcase=showcase, user_cards=user_cards)

@profile_bp.route('/update_showcase', methods=['POST'])
@login_required
def update_showcase():
    slot = request.form.get('slot')
    card_id = request.form.get('card_id')
    if not slot or not card_id:
        flash('Выберите карту и слот')
        return redirect(url_for('profile.profile'))
    with db.get_db() as conn:
        conn.execute('INSERT OR REPLACE INTO showcase (user_id, slot, card_id) VALUES (?, ?, ?)',
                     (session['user_id'], slot, card_id))
        conn.commit()
    flash('Витрина обновлена')
    return redirect(url_for('profile.profile'))

@profile_bp.route('/change_nickname', methods=['POST'])
@login_required
def change_nickname():
    new_nick = request.form.get('nickname')
    if not new_nick or len(new_nick) < 3:
        flash('Никнейм должен содержать минимум 3 символа')
        return redirect(url_for('profile.profile'))
    current_user = get_user_by_id(session['user_id'])
    success, msg = current_user.change_nickname(new_nick)
    flash(msg)
    return redirect(url_for('profile.profile'))

@profile_bp.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('Файл не выбран')
        return redirect(url_for('profile.profile'))
    file = request.files['avatar']
    if file.filename == '':
        flash('Файл не выбран')
        return redirect(url_for('profile.profile'))
    if file and allowed_file(file.filename):
        filename = secure_filename(f"current_user{session['user_id']}_{file.filename}")
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        current_user = get_user_by_id(session['user_id'])
        current_user.set_avatar(filename)
        flash('Аватарка обновлена')
    else:
        flash('Недопустимый формат файла')
    return redirect(url_for('profile.profile'))

@profile_bp.route('/change_element', methods=['GET', 'POST'])
@login_required
def change_element():
    current_user = get_user_by_id(session['user_id'])
    if request.method == 'POST':
        new_element = request.form['element']
        success, msg = current_user.set_element(new_element)
        flash(msg)
        return redirect(url_for('main.dashboard'))
    return render_template('change_element.html', current_user=current_user)

@profile_bp.route('/train_element', methods=['GET', 'POST'])
@login_required
def train_element():
    current_user = get_user_by_id(session['user_id'])
    if request.method == 'GET':
        with db.get_db() as conn:
            row = conn.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            coins = row['coins']
        return render_template('train_element.html', current_user=current_user, coins=coins)
    # POST – подтверждение
    with db.get_db() as conn:
        row = conn.execute('SELECT coins, trained FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if row['trained']:
            flash('Вы уже обучены')
            return redirect(url_for('profile.profile'))
        if row['coins'] < 100:
            flash('Недостаточно монет (нужно 100)')
            return redirect(url_for('profile.profile'))
        conn.execute('UPDATE users SET trained = 1, coins = coins - 100 WHERE id = ?', (session['user_id'],))
        conn.commit()
    current_user._trained = True
    flash('Стихия усилена! С вас списано 100 монет.')
    return redirect(url_for('profile.profile'))

@profile_bp.route('/toggle_duels')
@login_required
def toggle_duels():
    with db.get_db() as conn:
        current = conn.execute('SELECT allow_duels FROM users WHERE id = ?', (session['user_id'],)).fetchone()['allow_duels']
        new = 0 if current else 1
        conn.execute('UPDATE users SET allow_duels = ? WHERE id = ?', (new, session['user_id']))
        conn.commit()
    flash(f'Вызовы {"включены" if new else "отключены"}')
    return redirect(url_for('profile.profile'))
