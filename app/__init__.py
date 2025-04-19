from flask import Flask
from config import config, Config
from app.extensions import db, migrate
import atexit


def create_app(config_name='default'):
    # Create and configure the app
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Setup SSH tunnel closure on application exit
    if hasattr(Config, 'tunnel'):
        atexit.register(lambda: Config.tunnel.stop())

    return app