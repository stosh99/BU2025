from flask import Blueprint, render_template
from app.models.team import Team
from app.models.hitter import HitterStats, HitterStats_yest
from app.models.pitcher import PitcherStats, PitcherStats_yest
from app.models.games import Games
from app.extensions import db
from sqlalchemy import desc
from datetime import datetime  # Add this import


main = Blueprint('main', __name__)


@main.context_processor
def inject_bu_teams():
    try:
        # Get the most recent date to ensure teams are current
        most_recent_date = db.session.query(db.func.max(Team.Date)).scalar()
        if most_recent_date:
            teams = db.session.query(Team.BUTeam).filter_by(Date=most_recent_date).distinct().order_by(Team.BUTeam).all()
            # Extract the string values from the Row objects
            team_names = [team[0] for team in teams]
            return dict(bu_teams=team_names)
        return dict(bu_teams=[]) # Return empty list if no date or teams
    except Exception as e:
        print(f"Error fetching BU teams: {e}") # Optional: for debugging
        return dict(bu_teams=[]) # Return empty on error


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
        if player.AB and (player.AB + player.BB + player.HP) > 0:
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


@main.route('/teamstatsyest')
def teamstatsyest():
    # Find the two most recent dates in the teamstat table
    recent_dates = db.session.query(Team.Date).distinct().order_by(desc(Team.Date)).limit(2).all()

    if len(recent_dates) < 2:
        # Not enough dates for comparison
        flash("Need at least two dates with data to calculate changes", "warning")
        return redirect(url_for('main.team_stats'))

    most_recent_date = recent_dates[0][0]
    previous_date = recent_dates[1][0]

    # Get team data for both dates
    current_teams = {team.BUTeam: team for team in Team.query.filter_by(Date=most_recent_date).all()}
    previous_teams = {team.BUTeam: team for team in Team.query.filter_by(Date=previous_date).all()}

    # Calculate differences
    team_changes = []
    for buteam, current in current_teams.items():
        if buteam in previous_teams:
            # Create a new object to hold the changes
            changes = type('TeamChanges', (), {})()
            changes.BUTeam = buteam

            # Hitting stats changes
            changes.G = current.G - previous_teams[buteam].G if current.G and previous_teams[buteam].G else 0
            changes.AB = current.AB - previous_teams[buteam].AB if current.AB and previous_teams[buteam].AB else 0
            changes.H = current.H - previous_teams[buteam].H if current.H and previous_teams[buteam].H else 0
            changes._2B = current._2B - previous_teams[buteam]._2B if current._2B and previous_teams[buteam]._2B else 0
            changes._3B = current._3B - previous_teams[buteam]._3B if current._3B and previous_teams[buteam]._3B else 0
            changes.HR = current.HR - previous_teams[buteam].HR if current.HR and previous_teams[buteam].HR else 0
            changes.BB = current.BB - previous_teams[buteam].BB if current.BB and previous_teams[buteam].BB else 0
            changes.HP = current.HP - previous_teams[buteam].HP if current.HP and previous_teams[buteam].HP else 0
            changes.SB = current.SB - previous_teams[buteam].SB if current.SB and previous_teams[buteam].SB else 0
            changes.CS = current.CS - previous_teams[buteam].CS if current.CS and previous_teams[buteam].CS else 0
            changes.E = current.E - previous_teams[buteam].E if current.E and previous_teams[buteam].E else 0
            changes.KO = current.KO - previous_teams[buteam].KO if current.KO and previous_teams[buteam].KO else 0
            changes.RC = current.RC - previous_teams[buteam].RC if current.RC and previous_teams[buteam].RC else 0
            changes.OPS = current.OPS - previous_teams[buteam].OPS if current.OPS and previous_teams[buteam].OPS else 0

            # Pitching stats changes
            changes.APP = current.APP - previous_teams[buteam].APP if current.APP and previous_teams[buteam].APP else 0
            changes.GS = current.GS - previous_teams[buteam].GS if current.GS and previous_teams[buteam].GS else 0
            changes.QS = current.QS - previous_teams[buteam].QS if current.QS and previous_teams[buteam].QS else 0
            changes.INN = current.INN - previous_teams[buteam].INN if current.INN and previous_teams[buteam].INN else 0
            changes.ER = current.ER - previous_teams[buteam].ER if current.ER and previous_teams[buteam].ER else 0
            changes.RA = current.RA - previous_teams[buteam].RA if current.RA and previous_teams[buteam].RA else 0
            changes.ERA = current.ERA - previous_teams[buteam].ERA if current.ERA and previous_teams[buteam].ERA else 0
            changes.HA = current.HA - previous_teams[buteam].HA if current.HA and previous_teams[buteam].HA else 0
            changes.K = current.K - previous_teams[buteam].K if current.K and previous_teams[buteam].K else 0
            changes.BBI = current.BBI - previous_teams[buteam].BBI if current.BBI and previous_teams[buteam].BBI else 0
            changes.W = current.W - previous_teams[buteam].W if current.W and previous_teams[buteam].W else 0
            changes.L = current.L - previous_teams[buteam].L if current.L and previous_teams[buteam].L else 0
            changes.S = current.S - previous_teams[buteam].S if current.S and previous_teams[buteam].S else 0

            # Derived pitching stats
            if changes.INN and changes.INN > 0:
                changes.BB9 = changes.BBI * 9 / changes.INN
                changes.K9 = changes.K * 9 / changes.INN
                changes.WHIP = (changes.BBI + changes.HA) / changes.INN
                changes.ERA = changes.ER * 9 / changes.INN
            else:
                changes.BB9 = 0
                changes.K9 = 0
                changes.WHIP = 0
                changes.ERA = 0

            if changes.AB != 0:
                changes.AVG = changes.H / changes.AB
                changes.SLG = (changes.H + changes._2B + 2 * changes._3B + 3 * changes.HR) / changes.AB
            else:
                changes.AVG = 0
                changes.SLG = 0

            if changes.AB + changes.BBI + changes.HP != 0:
                changes.OBP = (changes.H + changes.BBI + changes.HP)/(changes.AB + changes.BBI + changes.HP)
            else:
                changes.OBP = 0

            if changes.AB-changes.H+changes.CS != 0:
                changes.RC = (2*(changes.H+changes._2B+2*changes._3B+3*changes.HR+changes.BBI+changes.HP)+changes.H+changes.SB - .61 * (changes.AB-changes.H+changes.CS)) * 4.12 /(changes.AB-changes.H+changes.CS)
            else:
                changes.RC = 0

            if changes.AB != 0:
                changes.SLG = (changes.H + changes._2B + 2 * changes._3B + 3 * changes.HR) / changes.AB
            else:
                changes.SLG = 0

            changes.OPS = changes.OPS + changes.SLG

            team_changes.append(changes)

    hitting_teams = sorted(team_changes, key=lambda x: x.RC, reverse=True)  # Sort by RC descending
    pitching_teams = sorted(team_changes, key=lambda x: x.ERA)  # Sort by ERA ascending

    return render_template('teamstatsyest.html',
                           teams=team_changes,  # Keep the original for backward compatibility
                           hitting_teams=hitting_teams,
                           pitching_teams=pitching_teams,
                           current_date=most_recent_date,
                           previous_date=previous_date,
                           now=datetime.now())


@main.route('/hitleadersyest')
def hit_leaders_yest():
    most_recent_date = db.session.query(db.func.max(HitterStats_yest.Date)).scalar()

    if not most_recent_date:
        flash("No data available in HitterStats_yest table", "warning")
        return redirect(url_for('main.home'))

    # Get the maximum BUGames value for qualifying
    max_games_query = db.session.query(db.func.max(Team.BUGames)) \
        .filter(Team.Date == most_recent_date).scalar()
    qualifying_abs = 2 * max_games_query  # This is your 2 * max(BUGames) calculation

    # Query for players with at least the qualifying number of at-bats
    players = db.session.query(HitterStats_yest).filter(
        HitterStats_yest.Date == most_recent_date
    ).order_by(desc(HitterStats_yest.RC)).all()

    # Calculate derived statistics for each player
    for player in players:
        # Clean player name
        if player.Player:
            player.clean_name = player.Player.replace('\xa0', ' ').replace('\u00A0', ' ')
            player.clean_name = ''.join(c if c.isprintable() else ' ' for c in player.clean_name)
            player.clean_name = ' '.join(player.clean_name.split())
        else:
            player.clean_name = ''

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

    return render_template('hitleadersyest.html', players=players, date=most_recent_date, now=datetime.now())


@main.route('/pitchleadersyest')
def pitch_leaders_yest():
    # Find the most recent date in the pitcherStats_yest table
    most_recent_date = db.session.query(db.func.max(PitcherStats_yest.Date)).scalar()

    if not most_recent_date:
        flash("No data available in pitcherStats_yest table", "warning")
        return redirect(url_for('main.home'))

    players = db.session.query(PitcherStats_yest).filter(
        PitcherStats_yest.Date == most_recent_date,
        PitcherStats_yest.INN >= .1
    ).order_by(PitcherStats_yest.ERA).all()  # Ordering by ERA (lower is better)

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

    return render_template('pitchleadersyest.html', players=players, date=most_recent_date, now=datetime.now())


@main.route('/games')
def games():
    # Find the most recent date in the games table
    most_recent_date = db.session.query(db.func.max(Games.Date)).scalar()

    if not most_recent_date:
        flash("No data available in games table", "warning")
        return redirect(url_for('main.home'))

    # Get all games for the most recent date, sorted by BUTeam ascending
    games_data = db.session.query(Games).filter(
        Games.Date == most_recent_date
    ).order_by(Games.BUTeam).all()

    return render_template('games.html', games=games_data, date=most_recent_date, now=datetime.now())


@main.route('/my-team-hit/<team_name>')
def my_team_hit_stats(team_name):
    most_recent_date = db.session.query(db.func.max(Team.Date)).scalar()
    if not most_recent_date:
        # Handle case where no date is found, maybe flash a message and redirect
        # For now, can pass empty players list or handle in template
        players = []
    else:
        players = db.session.query(HitterStats).filter(
            HitterStats.Date == most_recent_date,
            HitterStats.BUTeam == team_name
        ).order_by(desc(HitterStats.RC)).all()

        for player in players:
            # Clean player name (if necessary, like in pitch_leaders)
            if player.Player:
                player.clean_name = player.Player.replace('\xa0', ' ').replace('\u00A0', ' ')
                player.clean_name = ''.join(c if c.isprintable() else ' ' for c in player.clean_name)
                player.clean_name = ' '.join(player.clean_name.split())
            else:
                player.clean_name = '' # Or 'Unknown Player'

            if player.AB and player.AB > 0:
                player.AVG = player.H / player.AB
                player.SLG = (player.H + player._2B + 2 * player._3B + 3 * player.HR) / player.AB
                # OBP calculation needs (AB + BB + HP) in denominator
                if (player.AB + player.BB + player.HP) > 0:
                    player.OBP = (player.H + player.BB + player.HP) / (player.AB + player.BB + player.HP)
                else:
                    player.OBP = 0.0
                player.OPS = player.OBP + player.SLG
            else:
                player.AVG = 0.0
                player.OBP = 0.0
                player.SLG = 0.0
                player.OPS = 0.0
            # Ensure RC is present or set to 0.0 if not calculated elsewhere
            if not hasattr(player, 'RC') or player.RC is None:
                player.RC = 0.0

    return render_template('my_team_hit_stats.html',
                           players=players,
                           team_name=team_name,
                           date=most_recent_date,
                           now=datetime.now())


