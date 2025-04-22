from flask import Blueprint, render_template
from app.models.team import Team
from sqlalchemy import desc
from datetime import datetime  # Add this import

main = Blueprint('main', __name__)


@main.route('/')
def home():
    # Get the most recent date in the teamstat table
    most_recent_date = Team.query.order_by(desc(Team.Date)).first().Date

    # Get all teams for that date, sorted by WP (Win Percentage) descending
    teams = Team.query.filter_by(Date=most_recent_date).order_by(desc(Team.WP)).all()

    # Pass the current date to the template
    now = datetime.now()

    return render_template('home.html', teams=teams, date=most_recent_date, now=now)