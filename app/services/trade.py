"""Trade analysis: recompute team Winning Percentage (WP) when players move.

The WP model mirrors calc_wp() in scripts/CBS_Scrape.py:

    RC  = (2*(TB + BB + HP) + H + SB - 0.61*outs) * 4.12 / outs
    RA  = (ER + 0.57*E) * 9 / INN
    X   = 0.5 * ((R^2 + 1) / R^2)      where R = leagueRC / leagueRA
    WP  = X * (RC/RA)^2 / ((RC/RA)^2 + 1)

A team's WP depends on its own RC and RA plus the league-wide X factor, so any
change to a team's raw totals requires recomputing the league to get the new WP.
Team rows are plain dicts keyed by the teamstat column names (note '2B'/'3B').

The RC/RA/X/WP formulas themselves live in app/services/formulas.py (the single
source of truth shared with the scrape and routes); this module only adds the
None-coalescing and zero-guards needed for the trade-analyzer's scalar use.
"""

from app.services import formulas

# Raw hitting columns a hitter contributes (teamstat column names)
HITTER_WP_COLS = ['AB', 'H', '2B', '3B', 'HR', 'BB', 'HP', 'SB', 'CS', 'E']
# Raw pitching columns a pitcher contributes
PITCHER_WP_COLS = ['ER', 'INN']


def _team_rc(t):
    if formulas.outs(t['AB'] or 0, t['H'] or 0, t['CS'] or 0) <= 0:
        return 0.0
    return formulas.runs_created(
        t['AB'] or 0, t['H'] or 0, t['2B'] or 0, t['3B'] or 0, t['HR'] or 0,
        t['BB'] or 0, t['HP'] or 0, t['SB'] or 0, t['CS'] or 0)


def _team_ra(t):
    inn = t['INN'] or 0
    if inn <= 0:
        return 0.0
    return formulas.runs_allowed(t['ER'] or 0, t['E'] or 0, inn)


def _x_factor(teams):
    sums = {col: sum(t[col] or 0 for t in teams)
            for col in ['AB', 'H', '2B', '3B', 'HR', 'BB', 'HP', 'SB', 'CS', 'ER', 'E', 'INN']}
    if formulas.outs(sums['AB'], sums['H'], sums['CS']) <= 0 or sums['INN'] <= 0:
        return 0.0
    sum_rc = formulas.runs_created(sums['AB'], sums['H'], sums['2B'], sums['3B'],
                                   sums['HR'], sums['BB'], sums['HP'], sums['SB'], sums['CS'])
    sum_ra = formulas.runs_allowed(sums['ER'], sums['E'], sums['INN'])
    if sum_ra <= 0:
        return 0.0
    return formulas.x_factor(sum_rc, sum_ra)


def team_wp(teams, target_name):
    """Winning percentage for target_name given the current league `teams`."""
    x = _x_factor(teams)
    t = next(x_ for x_ in teams if x_['BUTeam'] == target_name)
    ra = _team_ra(t)
    if ra <= 0:
        return 0.0
    return formulas.winning_pct(_team_rc(t), ra, x)


def wp_with_change(base_teams, target_name, delta_stats):
    """WP for target_name after applying signed `delta_stats` to its row.

    `delta_stats` maps teamstat column -> signed amount (negative to remove a
    player's contribution, positive to add it). The league is recomputed.
    """
    teams = [dict(t) for t in base_teams]
    t = next(x for x in teams if x['BUTeam'] == target_name)
    for col, amt in delta_stats.items():
        t[col] = (t[col] or 0) + amt
    return team_wp(teams, target_name)


def player_delta_stats(wp_raw, sign):
    """Signed contribution dict for a player. sign = -1 to remove, +1 to add."""
    return {col: sign * (val or 0) for col, val in wp_raw.items()}
