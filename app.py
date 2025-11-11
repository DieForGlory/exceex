import os
from app import create_app
from app.extensions import socketio, db
from app.models import User, TaskLog
app = create_app()
@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'TaskLog': TaskLog}
if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5015, 
                 debug=True, 
                 allow_unsafe_werkzeug=True) # <-- Флаг должен быть здесь