# /routes/__init__.py

def register_routes(app):
    """
    Регистрирует все Blueprint'ы в приложении Flask.
    """
    from .main import main_bp
    from .templates import templates_bp
    from .dictionaries import dictionaries_bp
    from .auth import auth_bp           # НОВЫЙ
    from .admin import admin_bp         # НОВЫЙ

    app.register_blueprint(main_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(dictionaries_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)