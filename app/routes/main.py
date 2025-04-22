from flask import Blueprint, render_template
from app.models.team import Team
from app.models.hitter import HitterStats
from app.models.pitcher import PitcherStats
from app.extensions import db
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


@main.route('/team-stats')
def team_stats():
    # Get the most recent date in the teamstat table
    most_recent_date = Team.query.order_by(desc(Team.Date)).first().Date

    # Get all teams for that date, sorted by BUTeam ascending
    teams = Team.query.filter_by(Date=most_recent_date).order_by(Team.BUTeam).all()

    # Calculate derived statistics for each team
    for team in teams:
        # Hitting stats
        if team.AB and team.AB > 0:  # Avoid division by zero
            team.AVG = team.H / team.AB
            team.OBP = (team.H + team.BB + team.HP) / (team.AB + team.BB + team.HP)
            team.SLG = (team.H + team._2B + 2 * team._3B + 3 * team.HR) / team.AB
            team.OPS = team.OBP + team.SLG
        else:
            team.AVG = 0
            team.OBP = 0
            team.SLG = 0
            team.OPS = 0

        # Pitching stats
        if team.INN and team.INN > 0:  # Avoid division by zero
            team.BB9 = team.BBI * 9 / team.INN
            team.K9 = team.K * 9 / team.INN
            team.WHIP = (team.BBI + team.HA) / team.INN
        else:
            team.BB9 = 0
            team.K9 = 0
            team.WHIP = 0

    return render_template('teamstats.html', teams=teams, date=most_recent_date, now=datetime.now())


@main.route('/hitleaders')
def hit_leaders():
    # Import the hitterStats model at the top of your file if not already there
    # from app.models.hitter import HitterStats

    # First get the latest date
    most_recent_date = Team.query.order_by(desc(Team.Date)).first().Date

    # Get the maximum BUGames value for qualifying
    max_games_query = db.session.query(db.func.max(Team.BUGames)).filter(Team.Date == most_recent_date).scalar()
    qualifying_abs = 2 * max_games_query  # This is your 2 * max(BUGames) calculation

    # Query for players with at least the qualifying number of at-bats
    # You'll need to adjust this query based on your actual model for hitter stats
    players = db.session.query(HitterStats).filter(
        HitterStats.Date == most_recent_date,
        HitterStats.AB >= qualifying_abs
    ).order_by(desc(HitterStats.RC)).all()

    # Calculate derived statistics for each player
    for player in players:
        if player.AB and player.AB > 0:
            player.AVG = player.H / player.AB
            player.OBP = (player.H + player.BB + player.HP) / (player.AB + player.BB + player.HP)
            player.SLG = (player.H + player._2B + 2 * player._3B + 3 * player.HR) / player.AB
            player.OPS = player.OBP + player.SLG
        else:
            player.AVG = 0
            player.OBP = 0
            player.SLG = 0
            player.OPS = 0

    return render_template('hitleaders.html', players=players, date=most_recent_date, now=datetime.now())


@main.route('/pitchleaders')
def pitch_leaders():
    # First get the latest date
    most_recent_date = Team.query.order_by(desc(Team.Date)).first().Date

    # Get the maximum BUGames value for qualifying
    max_games_query = db.session.query(db.func.max(Team.BUGames)).filter(Team.Date == most_recent_date).scalar()
    qualifying_innings = 0.617 * max_games_query  # Half of max BUGames

    # Query for pitchers with at least the qualifying number of innings
    # Using your specified query
    players = db.session.query(PitcherStats).filter(
        PitcherStats.Date == most_recent_date,
        PitcherStats.INN >= qualifying_innings
    ).order_by(PitcherStats.ERA).all()  # Ordering by ERA (lower is better)

    # Calculate derived statistics for each pitcher
    for player in players:
        # Clean player name
        if player.Player:
            player.clean_name = player.Player.replace('\xa0', ' ').replace('\u00A0', ' ')
            player.clean_name = ''.join(c if c.isprintable() else ' ' for c in player.clean_name)
            player.clean_name = ' '.join(player.clean_name.split())
        else:
            player.clean_name = ''

        # Calculate BB/9 and K/9
        if player.INN and player.INN > 0:
            player.BB9 = player.BBI * 9 / player.INN
            player.K9 = player.K * 9 / player.INN
            player.WHIP = (player.BBI + player.HA) / player.INN
        else:
            player.BB9 = 0
            player.K9 = 0
            player.WHIP = 0

    return render_template('pitchleaders.html', players=players, date=most_recent_date, now=datetime.now())