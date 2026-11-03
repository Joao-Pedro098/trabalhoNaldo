import os
from flask import Flask
from app.models.database import init_db
from app.controllers import map_blueprint, api_blueprint

def create_app(test_config=None):
    """
    Application Factory para criar e configurar a instância do Flask.
    """
    app = Flask(
        __name__,
        template_folder='views',
        static_folder='static'
    )

    app.config.from_mapping(
        SECRET_KEY='super-secret-mini-google-maps-key',
        DATABASE=os.path.join(app.root_path, 'data', 'maps.db'),
    )

    if test_config:
        app.config.update(test_config)

    # Inicializa o banco de dados
    with app.app_context():
        init_db()

    # Registra os controllers (Blueprints)
    app.register_blueprint(map_blueprint)
    app.register_blueprint(api_blueprint)

    return app
