# app/__init__.py
import os
from flask import Flask
from .config import Config
from .extensions import executor, task_statuses, login_manager, db, migrate, socketio

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    login_manager.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, async_mode='threading')

    # Создаем необходимые директории
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)
    os.makedirs(app.config['TEMPLATES_DB_FOLDER'], exist_ok=True)
    os.makedirs(app.config['TEMPLATE_EXCEL_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DICTIONARIES_FOLDER'], exist_ok=True)
    os.makedirs(app.config['GEOCODING_DATA_FOLDER'], exist_ok=True)

    # --- Настройка User Loader ---
    from .services import user_service
    @login_manager.user_loader
    def load_user(user_id):
        return user_service.get_user_by_id(user_id) # Эта функция будет переписана под DB

    # Регистрируем все маршруты (blueprints)
    from .routes import register_routes
    register_routes(app)

    with app.app_context():
        from . import models

    return app