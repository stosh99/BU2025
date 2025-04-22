from flask import Flask
from config import config  # Import the config dictionary, not Config directly


def create_app(config_name='default'):
    # Create and configure the app
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    from app.extensions import db, migrate
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app