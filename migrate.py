from flask import Flask
from flask_migrate import Migrate, init, migrate, upgrade
from config import Config
from app.extensions import db
from app.models.team import Team

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
migrate = Migrate(app, db)

# Import models so they're detected by Alembic
# Add all your models here
#
#
#
# Create the migrations directory
    init()

    # Create a migration
    migrate(message="Initial migration")

    # Apply the migration
    upgrade()

print("Database migrations completed!")
