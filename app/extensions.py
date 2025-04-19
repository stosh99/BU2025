from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Create extensions instances
db = SQLAlchemy()
migrate = Migrate()