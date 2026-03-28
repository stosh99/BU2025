"""Shared stat calculation helpers for hitters, pitchers, and teams."""


def calc_hitting_stats(obj):
    """Calculate AVG, OBP, SLG, OPS on an object with raw hitting attributes.
    Mutates the object in place and returns it for convenience."""
    ab = obj.AB or 0
    h = obj.H or 0
    bb = obj.BB or 0
    hp = obj.HP or 0
    _2b = obj._2B or 0
    _3b = obj._3B or 0
    hr = obj.HR or 0

    if ab > 0:
        obj.AVG = h / ab
        obj.SLG = (h + _2b + 2 * _3b + 3 * hr) / ab
    else:
        obj.AVG = 0.0
        obj.SLG = 0.0

    denom = ab + bb + hp
    if denom > 0:
        obj.OBP = (h + bb + hp) / denom
    else:
        obj.OBP = 0.0

    obj.OPS = obj.OBP + obj.SLG
    return obj


def calc_pitching_stats(obj):
    """Calculate BB/9, K/9, WHIP on an object with raw pitching attributes.
    Mutates the object in place and returns it for convenience."""
    inn = obj.INN or 0.0
    bbi = obj.BBI or 0
    k = obj.K or 0
    ha = obj.HA or 0

    if inn > 0:
        obj.BB9 = bbi * 9 / inn
        obj.K9 = k * 9 / inn
        obj.WHIP = (bbi + ha) / inn
    else:
        obj.BB9 = 0.0
        obj.K9 = 0.0
        obj.WHIP = 0.0

    return obj


def clean_player_name(name):
    """Remove non-breaking spaces and non-printable characters from a player name."""
    if not name:
        return ''
    cleaned = name.replace('\xa0', ' ').replace('\u00A0', ' ')
    cleaned = ''.join(c if c.isprintable() else ' ' for c in cleaned)
    return ' '.join(cleaned.split())
