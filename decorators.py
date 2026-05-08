import functools
from flask import session, flash, redirect, url_for
import database as db  # добавим импорт

def logger(func):
    """Логгер вызовов функций (в консоль)"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"[LOG] Вызвана функция {func.__name__} с аргументами: {args} {kwargs}")
        result = func(*args, **kwargs)
        print(f"[LOG] Завершение функции {func.__name__}")
        return result
    return wrapper

def login_required(func):
    """Проверка авторизации для маршрутов Flask"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходимо войти в аккаунт')
            return redirect(url_for('auth.login'))
        # Проверка существования пользователя в БД (чтобы избежать ошибок после сброса БД)
        with db.get_db() as conn:
            row = conn.execute('SELECT id FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            if not row:
                session.clear()
                flash('Сессия устарела. Пожалуйста, войдите заново.')
                return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper

def positive_args(func):
    """Проверка, что все числовые аргументы > 0"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        for arg in args:
            if isinstance(arg, (int, float)) and arg < 0:
                raise ValueError("Аргументы должны быть положительными")
        for v in kwargs.values():
            if isinstance(v, (int, float)) and v < 0:
                raise ValueError("Аргументы должны быть положительными")
        return func(*args, **kwargs)
    return wrapper