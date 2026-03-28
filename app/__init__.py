import atexit
import logging
from flask import Flask
from config import config, Config


def create_app(config_name='default'):
    # Create and configure the app
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Security settings
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Initialize extensions
    from app.extensions import db, migrate
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Configure logging
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app.logger.setLevel(logging.INFO)

    # Clean up SSH tunnel on shutdown
    if Config.tunnel:
        atexit.register(lambda: Config.tunnel.stop())

    return app
