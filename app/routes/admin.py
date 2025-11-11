# app/routes/admin.py
import os
import glob
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.utils.decorators import admin_required
from app.services import user_service
from app.services import logging_service
from app.services import geocoding_service  # <-- Убедитесь, что этот импорт есть

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# Применяем декораторы ко всему Blueprint
@admin_bp.before_request
@login_required
@admin_required
def ensure_admin():
    """Защищает все маршруты в этом Blueprint."""
    pass


@admin_bp.route('/users')
def users_list():
    """Страница управления пользователями."""
    # Получаем пользователей из DB
    users = user_service.get_all_users()
    return render_template('admin_users.html', users=users)


@admin_bp.route('/users/create', methods=['POST'])
def create_user():
    """Обрабатывает создание нового пользователя."""
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'user')  # По умолчанию 'user'

    if not username or not password:
        flash('Имя пользователя и пароль обязательны.', 'error')
        return redirect(url_for('admin.users_list'))

    try:
        # Создаем пользователя в DB
        user_service.create_user(username, password, role)
        flash(f'Пользователь {username} ({role}) успешно создан.', 'success')
    except ValueError as e:
        flash(str(e), 'error')

    return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/delete', methods=['POST'])
def delete_user():
    """Обрабатывает удаление пользователя."""
    user_id = request.form.get('user_id')

    if user_id == current_user.id:
        flash('Вы не можете удалить сами себя.', 'error')
        return redirect(url_for('admin.users_list'))

    # Удаляем пользователя из DB
    if user_service.delete_user(user_id):
        flash('Пользователь успешно удален.', 'success')
    else:
        flash('Не удалось удалить пользователя.', 'error')

    return redirect(url_for('admin.users_list'))


@admin_bp.route('/reports')
def reports():
    """Отображает страницу отчетности по активности пользователей."""

    # 1. Загружаем всех пользователей из DB
    users = user_service.get_all_users()

    # 2. Инициализируем структуру отчета
    report_data = {}
    for user in users:
        report_data[user.id] = {
            "username": user.username,
            "templates_created": [],  # Заполним из JSON
            "tasks_run": 0,
            "tasks_success": 0,
            "tasks_error": 0,
            "task_log": []  # Заполним из DB
        }

    # 3. Собираем данные о созданных шаблонах (по-прежнему из JSON)
    template_files = glob.glob(os.path.join(current_app.config['TEMPLATES_DB_FOLDER'], '*.json'))
    for f in template_files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                owner_id = data.get('owner_id')
                # Добавляем шаблон в отчет, только если у него есть владелец
                if owner_id and owner_id in report_data:
                    report_data[owner_id]['templates_created'].append(data.get('template_name', 'Без имени'))
        except Exception:
            pass  # Игнорируем ошибки чтения шаблонов

    # 4. Собираем данные о выполненных задачах (из DB)
    task_logs = logging_service.load_logs()  # <-- Получаем TaskLog объекты

    for task in task_logs:
        owner_id = task.owner_id
        if owner_id in report_data:
            report_data[owner_id]['tasks_run'] += 1
            report_data[owner_id]['task_log'].append(task)  # Добавляем объект

            if "Ошибка" in task.status:
                report_data[owner_id]['tasks_error'] += 1
            else:
                report_data[owner_id]['tasks_success'] += 1

    # task_logs уже отсортированы по дате из DB (см. logging_service.load_logs)

    return render_template('admin_reports.html', report_data=report_data)


#
# --- ВОТ НОВЫЙ МАРШРУТ, КОТОРЫЙ НЕ БЫЛ НАЙДЕН ---
#
@admin_bp.route('/geocoding', methods=['GET', 'POST'])
def geocoding_ui():
    """Страница управления базой геокодинга."""

    if request.method == 'POST':
        # Проверка наличия файла
        if 'address_file' not in request.files:
            flash('Файл не найден.', 'error')
            return redirect(request.url)

        file = request.files['address_file']

        # Проверка имени файла
        if file.filename == '':
            flash('Файл не выбран.', 'error')
            return redirect(request.url)

        # Проверка расширения
        if file and file.filename.endswith('.csv'):
            try:
                # 1. Сохраняем файл, перезаписывая старый
                dest_path = current_app.config['ADDRESS_CSV_FILE']
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                file.save(dest_path)

                # 2. Принудительно перезагружаем сервис
                geocoding_service.force_reload_addresses()

                flash('База адресов (addresses.csv) успешно обновлена.', 'success')
            except Exception as e:
                flash(f'Произошла ошибка при обновлении: {e}', 'error')
                current_app.logger.error(f"Ошибка загрузки addresses.csv: {e}", exc_info=True)
        else:
            flash('Недопустимый формат файла. Требуется .csv', 'error')

        return redirect(url_for('admin.geocoding_ui'))

    # GET-запрос: просто отображаем страницу
    return render_template('admin_geocoding.html')