"""Unit tests for app.services.stats helpers."""

import sys
import os
import types
import importlib.util
import pytest

# Load stats.py directly without triggering app/__init__.py
_stats_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'stats.py')
_spec = importlib.util.spec_from_file_location('stats', _stats_path)
stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stats)

calc_hitting_stats = stats.calc_hitting_stats
calc_pitching_stats = stats.calc_pitching_stats
clean_player_name = stats.clean_player_name


class FakeObj:
    """Minimal stand-in for a SQLAlchemy model row."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# calc_hitting_stats
# ---------------------------------------------------------------------------

class TestCalcHittingStats:
    def test_basic_calculation(self):
        obj = FakeObj(AB=100, H=30, BB=10, HP=2, _2B=5, _3B=2, HR=3)
        calc_hitting_stats(obj)
        assert obj.AVG == pytest.approx(0.3)
        assert obj.OBP == pytest.approx(42 / 112)
        assert obj.SLG == pytest.approx((30 + 5 + 4 + 9) / 100)
        assert obj.OPS == pytest.approx(obj.OBP + obj.SLG)

    def test_zero_at_bats(self):
        obj = FakeObj(AB=0, H=0, BB=0, HP=0, _2B=0, _3B=0, HR=0)
        calc_hitting_stats(obj)
        assert obj.AVG == 0.0
        assert obj.OBP == 0.0
        assert obj.SLG == 0.0
        assert obj.OPS == 0.0

    def test_none_fields_treated_as_zero(self):
        obj = FakeObj(AB=None, H=None, BB=None, HP=None, _2B=None, _3B=None, HR=None)
        calc_hitting_stats(obj)
        assert obj.AVG == 0.0
        assert obj.OPS == 0.0


# ---------------------------------------------------------------------------
# calc_pitching_stats
# ---------------------------------------------------------------------------

class TestCalcPitchingStats:
    def test_basic_calculation(self):
        obj = FakeObj(INN=90, BBI=30, K=80, HA=70)
        calc_pitching_stats(obj)
        assert obj.BB9 == pytest.approx(30 * 9 / 90)
        assert obj.K9 == pytest.approx(80 * 9 / 90)
        assert obj.WHIP == pytest.approx((30 + 70) / 90)

    def test_zero_innings(self):
        obj = FakeObj(INN=0, BBI=5, K=10, HA=8)
        calc_pitching_stats(obj)
        assert obj.BB9 == 0.0
        assert obj.K9 == 0.0
        assert obj.WHIP == 0.0

    def test_none_fields(self):
        obj = FakeObj(INN=None, BBI=None, K=None, HA=None)
        calc_pitching_stats(obj)
        assert obj.WHIP == 0.0


# ---------------------------------------------------------------------------
# clean_player_name
# ---------------------------------------------------------------------------

class TestCleanPlayerName:
    def test_normal_name(self):
        assert clean_player_name("John Smith") == "John Smith"

    def test_non_breaking_spaces(self):
        assert clean_player_name("John\xa0Smith") == "John Smith"

    def test_extra_whitespace(self):
        assert clean_player_name("  John   Smith  ") == "John Smith"

    def test_none_returns_empty(self):
        assert clean_player_name(None) == ''

    def test_empty_returns_empty(self):
        assert clean_player_name('') == ''
