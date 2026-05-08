from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database as db
import sqlite3
import secrets
import threading
from datetime import timedelta
from extensions import mail
from flask_mail import Message

auth_bp = Blueprint('auth', __name__)

def send_async_email(app, msg):
""" Отправка письма в отдельном фоновом потоке"""
    with app.app_context():
        mail.send(msg)

def send_verification_email(email, token):
""" Формирует и отправляет письмо для подтверждения регистрации нового пользователя"""
    from flask import current_app
    link = url_for('auth.verify_email', token=token, _external=True)
    msg = Message('Подтверждение регистрации', recipients=[email])
    msg.body = f'Перейдите по ссылке, чтобы завершить регистрацию:\n{link}'
    thread = threading.Thread(target=send_async_email, args=(current_app._get_current_object(), msg))
    thread.start()

def send_reset_email(user_email, token):
""" Отправляет письмо для восстановления пароля"""
    from flask import current_app
    link = url_for('auth.reset_password', token=token, _external=True)
    msg = Message('Восстановление пароля', recipients=[user_email])
    msg.body = f'Для сброса пароля перейдите по ссылке:\n{link}\nСсылка действует 1 час.'
    thread = threading.Thread(target=send_async_email, args=(current_app._get_current_object(), msg))
    thread.start()

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
""" Получение и нормализация email, Проверка существующего пользователя в таблице users, Проверка наличия неподтверждённой регистрации, Создание временной записи и токена, Отправка письма, Сообщение об успехе и перенаправление"""
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        if not email:
            flash('Введите email')
            return render_template('register.html')
        # Проверяем, нет ли уже такого email в пользователях или временных регистрациях
        with db.get_db() as conn:
            existing_user = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
            if existing_user:
                flash('Пользователь с таким email уже зарегистрирован.')
                return render_template('register.html')
            existing_pending = conn.execute('SELECT id FROM pending_registrations WHERE email = ?', (email,)).fetchone()
            if existing_pending:
                flash('На этот email уже отправлено письмо. Проверьте почту или запросите повторно.')
                return render_template('register.html', resend_available=True, email=email)
            # Создаём временную запись
            token = secrets.token_urlsafe(32)
            conn.execute('INSERT INTO pending_registrations (email, verification_token) VALUES (?, ?)', (email, token))
            conn.commit()
        send_verification_email(email, token)
        flash('На ваш email отправлено письмо. Перейдите по ссылке, чтобы завершить регистрацию.')
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
""" Повторную отправка письма подтверждения для тех, кто не получил первое письмо или потерял ссылку.
Проверяет наличие записи в таблице pending_registrations с таким email. Генерирует новый токен. Отправляет новое письмо подтверждения через send_verification_email"""
    email = request.form.get('email', '').strip().lower()
    if not email:
        flash('Email не указан')
        return redirect(url_for('auth.register'))
    with db.get_db() as conn:
        pending = conn.execute('SELECT * FROM pending_registrations WHERE email = ?', (email,)).fetchone()
        if not pending:
            flash('Не найдено ожидающей регистрации для этого email.')
            return redirect(url_for('auth.register'))
        # Генерируем новый токен
        new_token = secrets.token_urlsafe(32)
        conn.execute('UPDATE pending_registrations SET verification_token = ?, created_at = CURRENT_TIMESTAMP WHERE email = ?', (new_token, email))
        conn.commit()
    send_verification_email(email, new_token)
    flash('Письмо с подтверждением отправлено повторно.')
    return redirect(url_for('auth.login'))

@auth_bp.route('/verify/<token>')
def verify_email(token):
""" Подтверждения email при регистрации"""
    with db.get_db() as conn:
        pending = conn.execute('SELECT * FROM pending_registrations WHERE verification_token = ?', (token,)).fetchone()
        if not pending:
            flash('Неверная или устаревшая ссылка подтверждения.')
            return redirect(url_for('auth.register'))
        # Сохраняем email в сессии для формы завершения регистрации
        session['verified_email'] = pending['email']
        # Удаляем временную запись
        conn.execute('DELETE FROM pending_registrations WHERE id = ?', (pending['id'],))
        conn.commit()
    return redirect(url_for('auth.complete_registration'))

@auth_bp.route('/complete-registration', methods=['GET', 'POST'])
def complete_registration():
""" Завершает регистрацию пользователя после подтверждения email"""
    email = session.get('verified_email')
    if not email:
        flash('Email не подтверждён. Начните регистрацию заново.')
        return redirect(url_for('auth.register'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not request.form.get('agree_privacy'):
            flash('Необходимо согласиться с политикой конфиденциальности')
            return render_template('complete_registration.html', email=email)
        password_hash = db.hash_password(password)
        try:
            with db.get_db() as conn:
                conn.execute('INSERT INTO users (username, email, password_hash, is_verified) VALUES (?, ?, ?, 1)',
                             (username, email, password_hash))
                user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                conn.execute('INSERT INTO user_stats (user_id) VALUES (?)', (user_id,))
                conn.execute('INSERT INTO story_progress (user_id) VALUES (?)', (user_id,))
                for card_id in [1, 2]:
                    conn.execute('INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, 2)',
                                 (user_id, card_id))
                conn.commit()
            session.pop('verified_email', None)
            flash('Регистрация завершена! Теперь войдите.')
            return redirect(url_for('auth.login'))
        except sqlite3.IntegrityError:
            flash('Это имя пользователя уже занято. Выберите другое.')
    return render_template('complete_registration.html', email=email)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['username']
        password = request.form['password']
        with db.get_db() as conn:
            row = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?',
                               (identifier, identifier)).fetchone()
        if row and db.verify_password(row['password_hash'], password):
            session.permanent = True
            session['user_id'] = row['id']
            session['username'] = row['username']
            return redirect(url_for('main.dashboard'))
        flash('Неверное имя/email или пароль')
    return render_template('login.html')

@auth_bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        email = request.form['email']
        token = secrets.token_urlsafe(32)
        expiry = db.now_msk() + timedelta(hours=1)
        with db.get_db() as conn:
            conn.execute('UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE email = ?',
                         (token, expiry.isoformat(), email))
            conn.commit()
        send_reset_email(email, token)
        flash('Ссылка для сброса пароля отправлена на почту.')
        return redirect(url_for('auth.login'))
    return render_template('forgot.html')

@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    with db.get_db() as conn:
        row = conn.execute('SELECT id FROM users WHERE reset_token = ? AND reset_token_expiry > ?',
                           (token, db.now_msk().isoformat())).fetchone()
        if not row:
            flash('Ссылка недействительна или истекла.')
            return redirect(url_for('auth.login'))
        if request.method == 'POST':
            new_pass = request.form['password']
            pwd_hash = db.hash_password(new_pass)
            conn.execute('UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?',
                         (pwd_hash, row['id']))
            conn.commit()
            flash('Пароль изменён. Войдите.')
            return redirect(url_for('auth.login'))
    return render_template('reset.html', token=token)

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))