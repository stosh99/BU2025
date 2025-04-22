print("Starting application...")
import os
from app import create_app
from app.extensions import db
from app.models.team import Team

app = create_app(os.getenv('FLASK_ENV', 'default'))

@app.shell_context_processor
def make_shell_context():
    """Add database and models to flask shell context"""
    return {
        'db': db,
        'Team': Team,
    }

if __name__ == '__main__':
    app.run(debug=True)