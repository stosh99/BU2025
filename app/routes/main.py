from flask import Blueprint, render_template
from app.services.team_service import get_all_teams

main = Blueprint('main', __name__)

@main.route('/')
def home():
    teams = get_all_teams()
    return render_template('home.html', teams=teams)