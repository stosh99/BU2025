from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, jsonify
from app.models.team import Team
from app.models.hitter import HitterStats, HitterStats_yest
from app.models.pitcher import PitcherStats, PitcherStats_yest
from app.models.games import Games
from app.extensions import db
from app.services.stats import calc_hitting_stats, calc_pitching_stats, clean_player_name
from app.services.charts import generate_player_chart
from app.services import trade, formulas
from sqlalchemy import desc
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from functools import wraps
import time

# Qualifying thresholds
HITTING_AB_MULTIPLIER = 2
PITCHING_INN_QUALIFIER = 0.617
PITCHER_MIN_INNINGS = 0.1
MOVING_AVG_WINDOW = 7

main = Blueprint('main', __name__)

# Simple in-process cache for the team list (refreshes every 60 seconds)
_bu_teams_cache: list = []
_bu_teams_cache_ts: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_season_year():
    """Return the configured season year, falling back to current calendar year."""
    return current_app.config.get('SEASON_YEAR', datetime.now().year)


def _year_filter(date_column):
    """Return a SQLAlchemy filter expression restricting date_column to the season year."""
    return db.extract('year', date_column) == _get_season_year()


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
    """Return the earliest date from cubsschedule for the current season year, or None."""
    year = _get_season_year()
    result = db.session.execute(
        db.text("SELECT MIN(date) FROM cubsschedule WHERE EXTRACT(YEAR FROM date) = :year"),
        {'year': year}
    ).scalar()
    return result


@main.context_processor
def inject_bu_teams():
    global _bu_teams_cache, _bu_teams_cache_ts
    try:
        if time.time() - _bu_teams_cache_ts > 60:
            most_recent_date = _max_date_for_model(Team)
            if most_recent_date:
                teams = db.session.query(Team.BUTeam).filter_by(Date=most_recent_date).distinct().order_by(Team.BUTeam).all()
                _bu_teams_cache = [team[0] for team in teams]
            else:
                _bu_teams_cache = []
            _bu_teams_cache_ts = time.time()
        return dict(bu_teams=_bu_teams_cache)
    except Exception:
        return dict(bu_teams=[])


def require_recent_date(model, message, redirect_to='main.home'):
    """Decorator: resolve the most recent season date for `model` and inject it
    as the `most_recent_date` keyword argument. If there is no data, flash
    `message` and redirect to `redirect_to` instead of calling the view.

    This centralizes the repeated
        most_recent_date = _max_date_for_model(...)
        if not most_recent_date: flash(...); return redirect(...)
    guard that opened almost every route.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            most_recent_date = _max_date_for_model(model)
            if not most_recent_date:
                flash(message, "warning")
                return redirect(url_for(redirect_to))
            kwargs['most_recent_date'] = most_recent_date
            return view(*args, **kwargs)
        return wrapper
    return decorator


@dataclass
class TeamChanges:
    """Day-over-day team stat deltas for the teamstatsyest view.

    Replaces the old dynamic ``type('TeamChanges', (), {})()`` object. Fields
    cover the raw hitting/pitching deltas plus the derived stats computed from
    them; all default to 0.0 so calc_pitching_stats and the template can read
    any field safely."""
    BUTeam: str = ''
    # Hitting deltas
    G: float = 0.0
    AB: float = 0.0
    H: float = 0.0
    _2B: float = 0.0
    _3B: float = 0.0
    HR: float = 0.0
    BB: float = 0.0
    HP: float = 0.0
    SB: float = 0.0
    CS: float = 0.0
    E: float = 0.0
    KO: float = 0.0
    RC: float = 0.0
    OPS: float = 0.0
    # Pitching deltas
    APP: float = 0.0
    GS: float = 0.0
    QS: float = 0.0
    INN: float = 0.0
    ER: float = 0.0
    RA: float = 0.0
    ERA: float = 0.0
    HA: float = 0.0
    K: float = 0.0
    BBI: float = 0.0
    W: float = 0.0
    L: float = 0.0
    S: float = 0.0
    # Derived
    BB9: float = 0.0
    K9: float = 0.0
    WHIP: float = 0.0
    AVG: float = 0.0
    SLG: float = 0.0
    OBP: float = 0.0


def _render_hit_leaders(model, most_recent_date, template, min_ab, set_clean_name):
    """Shared rendering for the season and yesterday hitter-leader pages.

    `min_ab` applies a qualifying at-bat threshold (None = no threshold).
    `set_clean_name` attaches a cleaned display name (the season page does not)."""
    query = db.session.query(model).filter(model.Date == most_recent_date)
    if min_ab is not None:
        query = query.filter(model.AB >= min_ab)
    players = query.order_by(desc(model.RC), desc(model.AB)).all()

    for player in players:
        if set_clean_name:
            player.clean_name = clean_player_name(player.Player)
        calc_hitting_stats(player)

    return render_template(template, players=players, date=most_recent_date, now=datetime.now())


def _render_pitch_leaders(model, most_recent_date, template, min_inn):
    """Shared rendering for the season and yesterday pitcher-leader pages.

    `min_inn` is the qualifying innings threshold."""
    players = db.session.query(model).filter(
        model.Date == most_recent_date,
        model.INN >= min_inn
    ).order_by(model.ERA, desc(model.INN)).all()

    for player in players:
        player.clean_name = clean_player_name(player.Player)
        calc_pitching_stats(player)

    return render_template(template, players=players, date=most_recent_date, now=datetime.now())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@main.route('/')
def home():
    most_recent_date = _max_date_for_model(Team)
    if not most_recent_date:
        flash("No team data available", "warning")
        return render_template('home.html', teams=[], date=None, xfactor=None, now=datetime.now())

    teams = Team.query.filter_by(Date=most_recent_date).order_by(desc(Team.WP)).all()

    xfactor = db.session.execute(
        db.text("SELECT xfactor FROM cubsschedule WHERE date = :d"),
        {'d': most_recent_date}
    ).scalar()

    return render_template('home.html', teams=teams, date=most_recent_date, xfactor=xfactor, now=datetime.now())


@main.route('/team-stats')
@require_recent_date(Team, "No team data available")
def team_stats(most_recent_date):
    teams = Team.query.filter_by(Date=most_recent_date).order_by(Team.BUTeam).all()
    for team in teams:
        calc_hitting_stats(team)
        calc_pitching_stats(team)

    return render_template('teamstats.html', teams=teams, date=most_recent_date, now=datetime.now())


@main.route('/hitleaders')
@require_recent_date(Team, "No team data available")
def hit_leaders(most_recent_date):
    qualifying_abs = HITTING_AB_MULTIPLIER * _max_bu_games(most_recent_date)
    return _render_hit_leaders(HitterStats, most_recent_date, 'hitleaders.html',
                               min_ab=qualifying_abs, set_clean_name=False)


@main.route('/pitchleaders')
@require_recent_date(Team, "No team data available")
def pitch_leaders(most_recent_date):
    qualifying_innings = PITCHING_INN_QUALIFIER * _max_bu_games(most_recent_date)
    return _render_pitch_leaders(PitcherStats, most_recent_date, 'pitchleaders.html',
                                 min_inn=qualifying_innings)


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
        changes = TeamChanges(BUTeam=buteam)

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

        obp_denom = changes.AB + changes.BB + changes.HP
        if obp_denom != 0:
            changes.OBP = (changes.H + changes.BB + changes.HP) / obp_denom
        else:
            changes.OBP = 0

        rc_denom = formulas.outs(changes.AB, changes.H, changes.CS)
        if rc_denom != 0:
            changes.RC = formulas.runs_created(
                changes.AB, changes.H, changes._2B, changes._3B, changes.HR,
                changes.BB, changes.HP, changes.SB, changes.CS)
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
@require_recent_date(HitterStats, "No hitter data available")
def hitter_analysis(most_recent_date):
    players_query = db.session.query(HitterStats.Player).filter(
        HitterStats.Date == most_recent_date,
        HitterStats.AB > 0
    ).distinct().order_by(HitterStats.Player).all()
    players = [p[0] for p in players_query]

    selected_player_name = request.args.get('player_name')
    plot_url = None

    season_year = _get_season_year()
    x_min = date(season_year, 4, 1)
    x_max = most_recent_date + timedelta(days=1)

    if selected_player_name:
        date_filter = _year_filter(HitterStats.Date)
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
            x_min=x_min, x_max=x_max,
            window=MOVING_AVG_WINDOW
        )

    return render_template('HitterAnalysis.html', players=players, plot_url=plot_url,
                           selected_player_name=selected_player_name, date=most_recent_date, now=datetime.now())


@main.route('/pitcher-analysis', methods=['GET'])
@require_recent_date(PitcherStats, "No pitcher data available")
def pitcher_analysis(most_recent_date):
    players_query = db.session.query(PitcherStats.Player).filter(
        PitcherStats.Date == most_recent_date,
        PitcherStats.INN > 0
    ).distinct().order_by(PitcherStats.Player).all()
    players = [p[0] for p in players_query]

    selected_player_name = request.args.get('player_name')
    plot_url = None

    season_year = _get_season_year()
    x_min = date(season_year, 4, 1)
    x_max = most_recent_date + timedelta(days=1)

    if selected_player_name:
        date_filter = _year_filter(PitcherStats.Date)
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
            x_min=x_min, x_max=x_max,
            window=MOVING_AVG_WINDOW
        )

    return render_template('PitcherAnalysis.html', players=players, plot_url=plot_url,
                           selected_player_name=selected_player_name, date=most_recent_date, now=datetime.now())


@main.route('/hitleadersyest')
@require_recent_date(HitterStats_yest, "No data available in HitterStats_yest table")
def hit_leaders_yest(most_recent_date):
    return _render_hit_leaders(HitterStats_yest, most_recent_date, 'hitleadersyest.html',
                               min_ab=None, set_clean_name=True)


@main.route('/pitchleadersyest')
@require_recent_date(PitcherStats_yest, "No data available in pitcherStats_yest table")
def pitch_leaders_yest(most_recent_date):
    return _render_pitch_leaders(PitcherStats_yest, most_recent_date, 'pitchleadersyest.html',
                                 min_inn=PITCHER_MIN_INNINGS)


@main.route('/games')
@require_recent_date(Games, "No data available in games table")
def games(most_recent_date):
    games_data = db.session.query(Games).filter(
        Games.Date == most_recent_date
    ).order_by(Games.BUTeam).all()

    return render_template('games.html', games=games_data, date=most_recent_date, now=datetime.now())


@main.route('/my-team-hit/<team_name>')
def my_team_hit_stats(team_name):
    most_recent_date = _max_date_for_model(Team)
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
    most_recent_date = _max_date_for_model(Team)
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


# ---------------------------------------------------------------------------
# Trade Analyzer
# ---------------------------------------------------------------------------

def _players_by_team(most_recent_date):
    """Return a dict mapping each BUteam to a sorted list of player dicts
    {name, raw, role} for every hitter and pitcher on that team.

    `name` is the cleaned display name; `raw` is the original DB value used
    for exact lookups (it may contain non-breaking spaces)."""
    roster = {}

    hitters = db.session.query(HitterStats.BUTeam, HitterStats.Player).filter(
        HitterStats.Date == most_recent_date
    ).distinct().all()
    for team, player in hitters:
        roster.setdefault(team, {})[clean_player_name(player)] = {'raw': player, 'role': 'H'}

    pitchers = db.session.query(PitcherStats.BUTeam, PitcherStats.Player).filter(
        PitcherStats.Date == most_recent_date
    ).distinct().all()
    for team, player in pitchers:
        # A player listed as a pitcher takes the pitcher role
        roster.setdefault(team, {})[clean_player_name(player)] = {'raw': player, 'role': 'P'}

    # Hitters first (role 'H'), then pitchers (role 'P'); alphabetical within each group
    def _role_then_name(item):
        name, info = item
        return (0 if info['role'] == 'H' else 1, name)

    return {
        team: [{'name': name, 'raw': info['raw'], 'role': info['role']}
               for name, info in sorted(players.items(), key=_role_then_name)]
        for team, players in roster.items()
    }


TEAMSTAT_WP_COLS = ['BUTeam', 'AB', 'H', '2B', '3B', 'HR', 'BB', 'HP', 'SB', 'CS', 'E', 'ER', 'INN', 'BUGames']


def _league_team_rows(date):
    """Return a list of dicts (one per BUteam) with the raw stats WP depends on."""
    quoted = ', '.join(f'"{c}"' for c in TEAMSTAT_WP_COLS)
    rows = db.session.execute(
        db.text(f'SELECT {quoted} FROM teamstat WHERE "Date" = :d'), {'d': date}
    ).fetchall()
    return [dict(zip(TEAMSTAT_WP_COLS, r)) for r in rows]


def _trade_player_lookup(date, team, raw_name):
    """Look up a player's display stats, role, and WP-relevant raw stats.

    Returns {player, role, stats, wp_raw} or None if the player is not found.
    `stats` is for display (hitters: PA/E/RC, pitchers: IP/ERA); `wp_raw` holds
    the raw counting stats (keyed by teamstat column) that feed the WP formula.
    """
    h = db.session.query(HitterStats).filter(
        HitterStats.Date == date,
        HitterStats.BUTeam == team,
        HitterStats.Player == raw_name
    ).first()
    if h:
        pa = (h.AB or 0) + (h.BB or 0) + (h.HP or 0)
        return {
            'player': clean_player_name(h.Player),
            'role': 'H',
            'stats': {'PA': round(pa), 'E': round(h.E or 0), 'RC': round(h.RC or 0, 1)},
            'wp_raw': {
                'AB': h.AB or 0, 'H': h.H or 0, '2B': h._2B or 0, '3B': h._3B or 0,
                'HR': h.HR or 0, 'BB': h.BB or 0, 'HP': h.HP or 0, 'SB': h.SB or 0,
                'CS': h.CS or 0, 'E': h.E or 0,
            },
        }

    p = db.session.query(PitcherStats).filter(
        PitcherStats.Date == date,
        PitcherStats.BUTeam == team,
        PitcherStats.Player == raw_name
    ).first()
    if p:
        return {
            'player': clean_player_name(p.Player),
            'role': 'P',
            'stats': {'IP': round(p.INN or 0, 1), 'ERA': round(p.ERA or 0, 2)},
            'wp_raw': {'ER': p.ER or 0, 'INN': p.INN or 0},
        }

    return None


@main.route('/trade-analyzer')
@require_recent_date(Team, "No team data available")
def trade_analyzer(most_recent_date):
    teams = [t[0] for t in db.session.query(Team.BUTeam).filter_by(
        Date=most_recent_date).distinct().order_by(Team.BUTeam).all()]
    roster = _players_by_team(most_recent_date)

    return render_template('TradeAnalyzer.html', teams=teams, roster=roster,
                           date=most_recent_date, now=datetime.now())


@main.route('/trade-analyzer/analyze', methods=['POST'])
def analyze_trade():
    """Compute the WP impact of a proposed trade.

    Request JSON:
        {
          "teamA": "<name>", "teamB": "<name>",
          "teamA_gives": ["raw player name", ...],   # leave A, join B
          "teamB_gives": ["raw player name", ...]    # leave B, join A
        }

    For each team, returns:
      - leaving / joining: per-player rows with each player's individual marginal
        WP effect on that team (remove if leaving, add if joining)
      - current_wp / projected_wp / net_wp_delta: the team's WP before and after
        the entire trade applied at once
    """
    data = request.get_json(silent=True) or {}
    team_a = data.get('teamA')
    team_b = data.get('teamB')
    a_gives = data.get('teamA_gives', [])
    b_gives = data.get('teamB_gives', [])

    if not team_a or not team_b:
        return jsonify({'error': 'Both teams must be selected.'}), 400
    if team_a == team_b:
        return jsonify({'error': 'Please select two different teams.'}), 400
    if not a_gives and not b_gives:
        return jsonify({'error': 'Select at least one player to trade.'}), 400

    date = _max_date_for_model(Team)
    if not date:
        return jsonify({'error': 'No team data available.'}), 400

    league = _league_team_rows(date)
    team_names = {t['BUTeam'] for t in league}
    if team_a not in team_names or team_b not in team_names:
        return jsonify({'error': 'Unknown team selected.'}), 400

    # Resolve each traded player on their current team
    a_players = [_trade_player_lookup(date, team_a, p) for p in a_gives]
    b_players = [_trade_player_lookup(date, team_b, p) for p in b_gives]
    if None in a_players or None in b_players:
        return jsonify({'error': 'One or more players could not be found on their team.'}), 400

    base_wp_a = trade.team_wp(league, team_a)
    base_wp_b = trade.team_wp(league, team_b)

    def _bugames(team_name):
        return next(t['BUGames'] for t in league if t['BUTeam'] == team_name) or 0

    def player_row(info, team_name, base_wp, bugames, sign):
        """Build a display row with this player's individual WP and wins effect."""
        delta_stats = trade.player_delta_stats(info['wp_raw'], sign)
        new_wp = trade.wp_with_change(league, team_name, delta_stats)
        wp_delta = new_wp - base_wp
        return {
            'player': info['player'],
            'role': info['role'],
            'stats': info['stats'],
            'wp_delta': round(wp_delta, 4),
            'wins_delta': round(wp_delta * bugames, 2),
        }

    def combined_delta(players, sign):
        """Sum the signed WP-raw contributions of several players into one dict."""
        total = {}
        for info in players:
            for col, val in trade.player_delta_stats(info['wp_raw'], sign).items():
                total[col] = total.get(col, 0) + val
        return total

    def build_side(team_name, leaving_players, joining_players, base_wp):
        bugames = _bugames(team_name)
        # leaving players are removed (sign -1), joining players are added (sign +1)
        leaving = [player_row(p, team_name, base_wp, bugames, -1) for p in leaving_players]
        joining = [player_row(p, team_name, base_wp, bugames, +1) for p in joining_players]

        # Entire trade: remove all leaving and add all joining at once
        whole = combined_delta(leaving_players, -1)
        for col, val in combined_delta(joining_players, +1).items():
            whole[col] = whole.get(col, 0) + val
        projected = trade.wp_with_change(league, team_name, whole)
        net_wp = projected - base_wp

        return {
            'name': team_name,
            'leaving': leaving,
            'joining': joining,
            'games_played': bugames,
            'current_wp': round(base_wp, 4),
            'projected_wp': round(projected, 4),
            'net_wp_delta': round(net_wp, 4),
            'current_wins': round(base_wp * bugames, 2),
            'projected_wins': round(projected * bugames, 2),
            'net_wins_delta': round(net_wp * bugames, 2),
        }

    return jsonify({
        'teamA': build_side(team_a, a_players, b_players, base_wp_a),
        'teamB': build_side(team_b, b_players, a_players, base_wp_b),
    })
