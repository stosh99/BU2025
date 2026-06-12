from app.extensions import db


class PitcherStatsMixin:
    Date   = db.Column(db.Date,        primary_key=True)
    BUTeam = db.Column(db.String(64),  primary_key=True)
    Player = db.Column(db.String(64),  primary_key=True)
    PlayerID = db.Column(db.String)   # stable CBS fantasy id; nullable (NULL until backfilled)
    Salary = db.Column(db.Float)
    APP    = db.Column(db.Float)
    GS     = db.Column(db.Float)
    QS     = db.Column(db.Float)
    INN    = db.Column(db.Float)
    ER     = db.Column(db.Float)
    RA     = db.Column(db.Float)
    ERA    = db.Column(db.Float)
    HA     = db.Column(db.Float)
    K      = db.Column(db.Float)
    BBI    = db.Column(db.Float)
    W      = db.Column(db.Float)
    L      = db.Column(db.Float)
    S      = db.Column(db.Float)

    def __repr__(self):
        return f'<Pitcher {self.Player} ({self.BUTeam}) on {self.Date}>'


class PitcherStats(PitcherStatsMixin, db.Model):
    __tablename__ = 'pitcherstats'


class PitcherStats_yest(PitcherStatsMixin, db.Model):
    __tablename__ = 'pitcherstats_yest'
