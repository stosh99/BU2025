"""Unit tests for the trade WP engine (app/services/trade.py)."""

import os
import importlib.util
import pytest

# Load trade.py directly without triggering app/__init__.py (which needs a DB)
_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'trade.py')
_spec = importlib.util.spec_from_file_location('trade', _path)
trade = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trade)


def _team(name, **kw):
    base = {'BUTeam': name, 'AB': 2000, 'H': 520, '2B': 90, '3B': 8, 'HR': 80,
            'BB': 230, 'HP': 30, 'SB': 40, 'CS': 10, 'E': 20, 'ER': 200, 'INN': 500}
    base.update(kw)
    return base


@pytest.fixture
def league():
    # Two-team league with differing strengths
    return [
        _team('Strong', H=560, HR=100, ER=180),
        _team('Weak', H=480, HR=60, ER=240),
    ]


class TestTeamWp:
    def test_wp_between_zero_and_one(self, league):
        for t in league:
            wp = trade.team_wp(league, t['BUTeam'])
            assert 0.0 < wp < 1.0

    def test_stronger_team_has_higher_wp(self, league):
        assert trade.team_wp(league, 'Strong') > trade.team_wp(league, 'Weak')


class TestWpWithChange:
    def test_no_change_returns_baseline(self, league):
        base = trade.team_wp(league, 'Strong')
        assert trade.wp_with_change(league, 'Strong', {}) == pytest.approx(base)

    def test_add_then_remove_is_symmetric(self, league):
        """Adding a player's stats then removing the same stats returns baseline."""
        base = trade.team_wp(league, 'Strong')
        wp_raw = {'AB': 150, 'H': 55, '2B': 12, '3B': 1, 'HR': 10,
                  'BB': 20, 'HP': 3, 'SB': 5, 'CS': 1, 'E': 2}

        add = trade.player_delta_stats(wp_raw, +1)
        wp_after_add = trade.wp_with_change(league, 'Strong', add)

        # Build a league where the player was added, then remove them
        boosted = [dict(t) for t in league]
        s = next(t for t in boosted if t['BUTeam'] == 'Strong')
        for c, v in add.items():
            s[c] += v
        remove = trade.player_delta_stats(wp_raw, -1)
        wp_back = trade.wp_with_change(boosted, 'Strong', remove)

        assert wp_after_add != pytest.approx(base)   # adding a hitter changes WP
        assert wp_back == pytest.approx(base)         # round-trip restores it

    def test_removing_good_hitter_lowers_wp(self, league):
        base = trade.team_wp(league, 'Strong')
        good_hitter = {'AB': 150, 'H': 60, '2B': 15, '3B': 2, 'HR': 15,
                       'BB': 25, 'HP': 3, 'SB': 8, 'CS': 1, 'E': 1}
        remove = trade.player_delta_stats(good_hitter, -1)
        assert trade.wp_with_change(league, 'Strong', remove) < base

    def test_removing_bad_pitcher_raises_wp(self, league):
        """Removing a high-ERA pitcher (lots of ER per inning) should help."""
        base = trade.team_wp(league, 'Strong')
        bad_pitcher = {'ER': 60, 'INN': 40}  # 13.5 ERA, drags team RA up
        remove = trade.player_delta_stats(bad_pitcher, -1)
        assert trade.wp_with_change(league, 'Strong', remove) > base


class TestPlayerDeltaStats:
    def test_sign_negative_removes(self):
        d = trade.player_delta_stats({'AB': 100, 'H': 30}, -1)
        assert d == {'AB': -100, 'H': -30}

    def test_sign_positive_adds(self):
        d = trade.player_delta_stats({'ER': 20, 'INN': 50}, +1)
        assert d == {'ER': 20, 'INN': 50}


# Real teamstat rows for 2026-06-09 in bu2025 (a full 12-team league day).
# Columns: BUTeam, AB, H, 2B, 3B, HR, BB, HP, SB, CS, E, ER, INN
_REAL_LEAGUE_ROWS = [
    ('Awobs',         2193, 539, 116, 14,  77, 247, 19, 41, 13, 29, 279, 613.0),
    ('Big Units',     2131, 508, 108,  6,  60, 256, 31, 62, 16, 24, 259, 568.0),
    ('Doorights',     2494, 620, 110,  9,  82, 245, 23, 66, 17, 22, 254, 612.3),
    ('Islanders',     2256, 549, 102,  8,  75, 260, 36, 66, 28, 31, 254, 559.7),
    ('Keggers',       2629, 660, 111, 11, 102, 273, 40, 51,  7, 10, 253, 622.7),
    ('Leemos',        2439, 570, 124, 13,  88, 272, 27, 36, 10, 39, 223, 443.0),
    ('Low Life',      2132, 517,  89,  6,  85, 195, 34, 30, 10, 31, 181, 552.7),
    ('Money Ballers', 2462, 606, 117, 17,  82, 227, 24, 46, 15, 35, 267, 646.7),
    ('Ramrods',       2262, 568, 106,  5,  78, 198, 25, 46, 16, 26, 301, 618.3),
    ('Shaggers',      2703, 704, 147, 14,  81, 288, 30, 57, 17, 33, 276, 587.7),
    ('Stiefels',      2775, 708, 138, 15, 103, 277, 35, 63, 19, 38, 258, 609.0),
    ('Wobblies',      2180, 542, 105,  9,  62, 229, 21, 45,  8, 19, 254, 573.0),
]
_REAL_COLS = ['BUTeam', 'AB', 'H', '2B', '3B', 'HR', 'BB', 'HP', 'SB', 'CS', 'E', 'ER', 'INN']


@pytest.fixture
def real_league():
    return [dict(zip(_REAL_COLS, row)) for row in _REAL_LEAGUE_ROWS]


class TestRealDataParity:
    """Parity guard: the refactored formulas must reproduce the exact WP/X-factor
    the pre-refactor code produced for real teamstat rows. These expected values
    were computed with the OLD trade.py code and match the WP/X_factor stored in
    the database by the scrape, locking in the single-source-of-truth behavior."""

    def test_x_factor_matches_stored(self, real_league):
        assert trade._x_factor(real_league) == pytest.approx(0.9096365639804324, abs=1e-12)

    def test_wp_matches_old_values(self, real_league):
        expected = {
            'Awobs': 0.49616127236842383,
            'Keggers': 0.5711839074099414,
            'Low Life': 0.5961889603055411,
        }
        for name, exp in expected.items():
            assert trade.team_wp(real_league, name) == pytest.approx(exp, abs=1e-12)
