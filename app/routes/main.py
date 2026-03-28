from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from app.models.team import Team
from app.models.hitter import HitterStats, HitterStats_yest
from app.models.pitcher import PitcherStats, PitcherStats_yest
from app.models.games import Games
from app.extensions import db
from app.services.stats import calc_hitting_stats, calc_pitching_stats, clean_player_name
from app.services.charts import generate_player_chart
from sqlalchemy import desc
from datetime import datetime

# Qualifying thresholds
HITTING_AB_MULTIPLIER = 2
PITCHING_INN_QUALIFIER = 0.617
PITCHER_MIN_INNINGS = 0.1
MOVING_AVG_WINDOW = 7

main = Blueprint('main', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_season_year():
    """Return the configured season year, falling back to current calendar year."""
    return current_app.config.get('SEASON_YEAR', datetime.now().year)


def _year_filter(date_column):
    """Return a SQLAlchemy filter expression restricting date_column to the season year."""
    return db.extract('year', date_column) == _get_season_year()


def _get_most_recent_date():
    """Return the most recent date from the Team table for the current season, or None."""
    record = Team.query.filter(
        _year_filter(Team.Date)
    ).order_by(desc(Team.Date)).first()
    return record.Date if record else None


def _max_bu_games(date):
    """Return max BUGames for a given date, defaulting to 0."""
    val = db.session.query(db.func.max(Team.BUGames)).filter(Team.Date == date).scalar()
    return val if val is not None else 0


def _max_date_for_model(model):
    """Return the most recent date for a model filtered by season year, or None."""
    return db.session.query(db.func.max(model.Date)).filter(
        _year_filter(model.Date)
    ).scalar()


def _get_season_start_date():
    """Return the earliest date from CubsSchedule2025 for the current season year, or None."""
    year = _get_season_year()
    result = db.session.execute(
        db.text("SELECT MIN(STR_TO_DATE(Date, '%m/%d/%Y')) FROM CubsSchedule2025 WHERE YEAR(STR_TO_DATE(Date, '%m/%d/%Y')) = :year"),
        {'year': year}
    ).scalar()
    return result


@main.context_processor
def inject_bu_teams():
    try:
        most_recent_date = _max_date_for_model(Team)
        if most_recent_date:
            teams = db.session.query(Team.BUTeam).filter_by(Date=most_recent_date).distinct().order_by(Team.BUTeam).all()
            return dict(bu_teams=[team[0] for team in teams])
        return dict(bu_teams=[])
    except Exception:
        return dict(bu_teams=[])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@main.route('/')
def home():
    most_recent_date = _get_most_recent_date()
    if not most_recent_date:
        flash("No team data available", "warning")
        return render_template('home.html', teams=[], date=None, xfactor=None, now=datetime.now())

    teams = Team.query.filter_by(Date=most_recent_date).order_by(desc(Team.WP)).all()

    # Get Xfactor for the most recent date from CubsSchedule2025
    date_str = most_recent_date.strftime('%-m/%-d/%Y')
    xfactor = db.session.execute(
        db.text("SELECT Xfactor FROM CubsSchedule2025 WHERE Date = :d"),
        {'d': date_str}
    ).scalar()

    return render_template('home.html', teams=teams, date=most_recent_date, xfactor=xfactor, now=datetime.now())


@main.route('/team-stats')
def team_stats():
    most_recent_date = _get_most_recent_date()
    if not most_recent_date:
        flash("No team data available", "warning")
        return redirect(url_for('main.home'))

    teams = Team.query.filter_by(Date=most_recent_date).order_by(Team.BUTeam).all()
    for team in teams:
        calc_hitting_stats(team)
        calc_pitching_stats(team)

    return render_template('teamstats.html', teams=teams, date=most_recent_date, now=datetime.now())


@main.route('/hitleaders')
def hit_leaders():
    most_recent_date = _get_most_recent_date()
    if not most_recent_date:
        flash("No team data available", "warning")
        return redirect(url_for('main.home'))

    qualifying_abs = HITTING_AB_MULTIPLIER * _max_bu_games(most_recent_date)

    players = db.session.query(HitterStats).filter(
        HitterStats.Date == most_recent_date,
        HitterStats.AB >= qualifying_abs
    ).order_by(desc(HitterStats.RC), desc(HitterStats.AB)).all()

    for player in players:
        calc_hitting_stats(player)

    return render_template('hitleaders.html', players=players, date=most_recent_date, now=datetime.now())


@main.route('/pitchleaders')
def pitch_leaders():
    most_recent_date = _get_most_recent_date()
    if not most_recent_date:
        flash("No team data available", "warning")
        return redirect(url_for('main.home'))

    qualifying_innings = PITCHING_INN_QUALIFIER * _max_bu_games(most_recent_date)

    players = db.session.query(PitcherStats).filter(
        PitcherStats.Date == most_recent_date,
        PitcherStats.INN >= qualifying_innings
    ).order_by(PitcherStats.ERA, desc(PitcherStats.INN)).all()

    for player in players:
        player.clean_name = clean_player_name(player.Player)
        calc_pitching_stats(player)

    return render_template('pitchleaders.html', players=players, date=most_recent_date, now=datetime.now())


@main.route('/teamstatsyest')
def teamstatsyest():
    year = _get_season_year()
    recent_dates = db.session.query(Team.Date).filter(
        _year_filter(Team.Date)
    ).distinct().order_by(desc(Team.Date)).limit(2).all()

    if len(recent_dates) < 2:
        flash("Need at least two dates with data to calculate changes", "warning")
        return redirect(url_for('main.team_stats'))

    most_recent_date = recent_dates[0][0]
    previous_date = recent_dates[1][0]

    current_teams = {t.BUTeam: t for t in Team.query.filter_by(Date=most_recent_date).all()}
    previous_teams = {t.BUTeam: t for t in Team.query.filter_by(Date=previous_date).all()}

    team_changes = []
    for buteam, current in current_teams.items():
        if buteam not in previous_teams:
            continue

        prev = previous_teams[buteam]
        changes = type('TeamChanges', (), {})()
        changes.BUTeam = buteam

        # Compute deltas for all stat fields
        hitting_fields = ['G', 'AB', 'H', '_2B', '_3B', 'HR', 'BB', 'HP', 'SB', 'CS', 'E', 'KO', 'RC', 'OPS']
        pitching_fields = ['APP', 'GS', 'QS', 'INN', 'ER', 'RA', 'ERA', 'HA', 'K', 'BBI', 'W', 'L', 'S']

        for field in hitting_fields + pitching_fields:
            cur_val = getattr(current, field, None) or 0
            prev_val = getattr(prev, field, None) or 0
            setattr(changes, field, cur_val - prev_val)

        # Derived pitching stats from deltas
        calc_pitching_stats(changes)
        if changes.INN and changes.INN > 0:
            changes.ERA = changes.ER * 9 / changes.INN

        # Derived hitting stats from deltas
        if changes.AB != 0:
            changes.AVG = changes.H / changes.AB
            changes.SLG = (changes.H + changes._2B + 2 * changes._3B + 3 * changes.HR) / changes.AB
        else:
            changes.AVG = 0
            changes.SLG = 0

        obp_denom = changes.AB + changes.BBI + changes.HP
        if obp_denom != 0:
            changes.OBP = (changes.H + changes.BBI + changes.HP) / obp_denom
        else:
            changes.OBP = 0

        rc_denom = changes.AB - changes.H + changes.CS
        if rc_denom != 0:
            changes.RC = (2 * (changes.H + changes._2B + 2 * changes._3B + 3 * changes.HR + changes.BBI + changes.HP) + changes.H + changes.SB - 0.61 * rc_denom) * 4.12 / rc_denom
        else:
            changes.RC = 0

        changes.OPS = changes.OBP + changes.SLG

        team_changes.append(changes)

    hitting_teams = sorted(team_changes, key=lambda x: x.RC, reverse=True)
    pitching_teams = sorted(team_changes, key=lambda x: x.ERA)

    return render_template('teamstatsyest.html',
                           teams=team_changes,
                           hitting_teams=hitting_teams,
                           pitching_teams=pitching_teams,
                           current_date=most_recent_date,
                           previous_date=previous_date,
                           now=datetime.now())


@main.route('/hitter-analysis', methods=['GET'])
def hitter_analysis():
    most_recent_date = _max_date_for_model(HitterStats)

    players_query = db.session.query(HitterStats.Player).filter(
        HitterStats.Date == most_recent_date
    ).distinct().order_by(HitterStats.Player).all()
    players = [p[0] for p in players_query]

    selected_player_name = request.args.get('player_name')
    plot_url = None

    if selected_player_name:
        season_start = _get_season_start_date()
        date_filter = HitterStats.Date >= season_start if season_start else _year_filter(HitterStats.Date)
        player_stats = db.session.query(HitterStats.Date, HitterStats.RC).filter(
            HitterStats.Player == selected_player_name,
            date_filter
        ).order_by(HitterStats.Date).all()

        plot_url = generate_player_chart(
            player_stats,
            columns=['Date', 'RC'],
            ylabel='RC (Runs Created)',
            title=f'RC Over Time for {selected_player_name}',
            ma_label=f'{MOVING_AVG_WINDOW}-Day Moving Avg RC',
            y_min=2.0, y_max=8.0,
            window=MOVING_AVG_WINDOW
        )

    return render_template('HitterAnalysis.html', players=players, plot_url=plot_url,
                           selected_player_name=selected_player_name, date=most_recent_date, now=datetime.now())


@main.route('/pitcher-analysis', methods=['GET'])
def pitcher_analysis():
    most_recent_date = _max_date_for_model(PitcherStats)

    players_query = db.session.query(PitcherStats.Player).filter(
        PitcherStats.Date == most_recent_date
    ).distinct().order_by(PitcherStats.Player).all()
    players = [p[0] for p in players_query]

    selected_player_name = request.args.get('player_name')
    plot_url = None

    if selected_player_name:
        season_start = _get_season_start_date()
        date_filter = PitcherStats.Date >= season_start if season_start else _year_filter(PitcherStats.Date)
        player_stats = db.session.query(PitcherStats.Date, PitcherStats.ERA).filter(
            PitcherStats.Player == selected_player_name,
            date_filter
        ).order_by(PitcherStats.Date).all()

        plot_url = generate_player_chart(
            player_stats,
            columns=['Date', 'ERA'],
            ylabel='ERA (Earned Run Average)',
            title=f'ERA Over Time for {selected_player_name}',
            ma_label=f'{MOVING_AVG_WINDOW}-Day Moving Avg ERA',
            y_min=0, y_max=5.0,
            window=MOVING_AVG_WINDOW
        )

    return render_template('PitcherAnalysis.html', players=players, plot_url=plot_url,
                           selected_player_name=selected_player_name, date=most_recent_date, now=datetime.now())


@main.route('/hitleadersyest')
def hit_leaders_yest():
    most_recent_date = _max_date_for_model(HitterStats_yest)

    if not most_recent_date:
        flash("No data available in HitterStats_yest table", "warning")
        return redirect(url_for('main.home'))

    players = db.session.query(HitterStats_yest).filter(
        HitterStats_yest.Date == most_recent_date
    ).order_by(desc(HitterStats_yest.RC), desc(HitterStats_yest.AB)).all()

    for player in players:
        player.clean_name = clean_player_name(player.Player)
        calc_hitting_stats(player)

    return render_template('hitleadersyest.html', players=players, date=most_recent_date, now=datetime.now())


@main.route('/pitchleadersyest')
def pitch_leaders_yest():
    most_recent_date = _max_date_for_model(PitcherStats_yest)

    if not most_recent_date:
        flash("No data available in pitcherStats_yest table", "warning")
        return redirect(url_for('main.home'))

    players = db.session.query(PitcherStats_yest).filter(
        PitcherStats_yest.Date == most_recent_date,
        PitcherStats_yest.INN >= PITCHER_MIN_INNINGS
    ).order_by(PitcherStats_yest.ERA, desc(PitcherStats_yest.INN)).all()

    for player in players:
        player.clean_name = clean_player_name(player.Player)
        calc_pitching_stats(player)

    return render_template('pitchleadersyest.html', players=players, date=most_recent_date, now=datetime.now())


@main.route('/games')
def games():
    most_recent_date = _max_date_for_model(Games)

    if not most_recent_date:
        flash("No data available in games table", "warning")
        return redirect(url_for('main.home'))

    games_data = db.session.query(Games).filter(
        Games.Date == most_recent_date
    ).order_by(Games.BUTeam).all()

    return render_template('games.html', games=games_data, date=most_recent_date, now=datetime.now())


@main.route('/my-team-hit/<team_name>')
def my_team_hit_stats(team_name):
    most_recent_date = _get_most_recent_date()
    if not most_recent_date:
        players = []
    else:
        players = db.session.query(HitterStats).filter(
            HitterStats.Date == most_recent_date,
            HitterStats.BUTeam == team_name
        ).order_by(desc(HitterStats.RC)).all()

        for player in players:
            player.clean_name = clean_player_name(player.Player)
            calc_hitting_stats(player)
            if not hasattr(player, 'RC') or player.RC is None:
                player.RC = 0.0

    return render_template('my_team_hit_stats.html',
                           players=players, team_name=team_name,
                           date=most_recent_date, now=datetime.now())


@main.route('/my-team-pitch/<team_name>')
def my_team_pitch_stats(team_name):
    most_recent_date = _get_most_recent_date()
    if not most_recent_date:
        players = []
    else:
        players = db.session.query(PitcherStats).filter(
            PitcherStats.Date == most_recent_date,
            PitcherStats.BUTeam == team_name
        ).order_by(PitcherStats.ERA).all()

        for player in players:
            player.clean_name = clean_player_name(player.Player)
            calc_pitching_stats(player)

            # Default None values for display
            player.APP = player.APP or 0
            player.GS = player.GS or 0
            player.QS = player.QS or 0
            player.INN = player.INN or 0.0
            player.ER = player.ER or 0
            player.ERA = player.ERA or 0.0
            player.W = player.W or 0
            player.L = player.L or 0
            player.S = player.S or 0

    return render_template('my_team_pitch_stats.html',
                           players=players, team_name=team_name,
                           date=most_recent_date, now=datetime.now())
