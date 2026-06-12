"""Single source of truth for the BU league's team-rating formulas.

These pure functions implement the league's Runs Created (RC), Runs Allowed (RA),
league X-factor, and Winning Percentage (WP) model. They are the canonical
definition shared by:

  - app/services/trade.py    (trade-analyzer WP recomputation)
  - scripts/CBS_Scrape.py    (nightly teamstat WP/X-factor calculation)
  - app/routes/main.py       (teamstatsyest day-over-day RC deltas)

The model:

    TB  = H + 2B + 2*3B + 3*HR
    OUT = AB - H + CS
    RC  = (2*(TB + BB + HP) + H + SB - 0.61*OUT) * 4.12 / OUT
    RA  = (ER + 0.57*E) * 9 / INN
    X   = 0.5 * ((R^2 + 1) / R^2)        where R = leagueRC / leagueRA
    WP  = X * (RC/RA)^2 / ((RC/RA)^2 + 1)

Functions take plain numeric values so they work equally with Python scalars
(trade analyzer, route deltas) and pandas Series (vectorized scrape). They do
NOT guard against division by zero: scalar callers guard before calling, and
the scrape relies on pandas producing inf and replacing it afterward. Keeping
these pure preserves both behaviors exactly.
"""

# Named constants for the league formulas (previously hard-coded magic numbers).
RC_OUT_FACTOR = 0.61          # subtracted weight per out in Runs Created
RC_MULTIPLIER = 4.12          # Runs Created scaling factor
RA_ERROR_FACTOR = 0.57        # weight applied to errors in Runs Allowed
INNINGS_PER_GAME = 9          # innings used to scale Runs Allowed
PYTHAGOREAN_EXPONENT = 2      # exponent in the Pythagorean win-expectancy model


def total_bases(h, _2b, _3b, hr):
    """Total bases: singles + 2*doubles + 3*triples + 4*home runs."""
    return h + _2b + 2 * _3b + 3 * hr


def outs(ab, h, cs):
    """Outs made: at-bats minus hits plus caught stealing."""
    return ab - h + cs


def runs_created(ab, h, _2b, _3b, hr, bb, hp, sb, cs):
    """Runs Created from raw counting stats. Caller guards outs == 0."""
    o = outs(ab, h, cs)
    tb = total_bases(h, _2b, _3b, hr)
    return (2 * (tb + bb + hp) + h + sb - RC_OUT_FACTOR * o) * RC_MULTIPLIER / o


def runs_allowed(er, e, inn):
    """Runs Allowed from earned runs, errors, and innings. Caller guards INN == 0."""
    return (er + RA_ERROR_FACTOR * e) * INNINGS_PER_GAME / inn


def x_factor(league_rc, league_ra):
    """League X-factor from league-wide RC and RA. Caller guards league_ra == 0."""
    r = league_rc / league_ra
    return 0.5 * ((r ** PYTHAGOREAN_EXPONENT + 1) / r ** PYTHAGOREAN_EXPONENT)


def winning_pct(rc, ra, x):
    """Pythagorean Winning Percentage for a team given its RC, RA, and the league X."""
    r = rc / ra
    return x * r ** PYTHAGOREAN_EXPONENT / (r ** PYTHAGOREAN_EXPONENT + 1)
