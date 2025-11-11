# app/extensions.py
from concurrent.futures import ThreadPoolExecutor
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO

executor = ThreadPoolExecutor(max_workers=4)
task_statuses = {}

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Пожалуйста, войдите, чтобы получить доступ к этой странице."
login_manager.login_message_category = "error"

# --- НОВЫЕ ЭКЗЕМПЛЯРЫ ---
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()