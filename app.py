# app.py
from app import create_app
from app.extensions import socketio
#qwe
app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5015, allow_unsafe_werkzeug=True)