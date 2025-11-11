# app/extensions.py
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_executor import Executor

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Пожалуйста, войдите, чтобы получить доступ к этой странице."
login_manager.login_message_category = "error"

db = SQLAlchemy()
migrate = Migrate()

# --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
# 1. Возвращаем 'threading'
# 2. Добавляем message_queue (kombu у вас уже есть в requirements.txt)
socketio = SocketIO(async_mode='threading', message_queue='memory://')
# --- КОНЕЦ ИЗМЕНЕНИЯ ---

executor = Executor()
task_statuses = {}