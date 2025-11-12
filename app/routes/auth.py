# app/routes/auth.py
import datetime  # <-- ДОБАВИТЬ ИМПОРТ
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.services import user_service
from app.extensions import db  # <-- ДОБАВИТЬ ИМПОРТ

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form

        user = user_service.get_user_by_username(username)

        if user and user.check_password(password):
            login_user(user, remember=remember)

            # --- НАЧАЛО ИЗМЕНЕНИЯ: ЛОГИРОВАНИЕ ВРЕМЕНИ ВХОДА ---
            try:
                user.last_login = datetime.datetime.now()
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Ошибка обновления last_login: {e}")  # Безопасный вывод в консоль
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---

            flash('Вход выполнен успешно.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('Неверное имя пользователя или пароль.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'success')
    return redirect(url_for('auth.login'))