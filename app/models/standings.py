from app.extensions import db
from datetime import datetime


class Standings(db.Model):
    __tablename__ = 'teamstat'

    BUTeam = db.Column(db.String(64), unique=True, nullable=False)
    RC = db.Column(db.Float, default=0.0)
    RA = db.Column(db.Float, default=0.0)
    WP = db.Column(db.Float, default=0.0)
    Wins = db.Column(db.Float, default=0.0)
    Losses = db.Column(db.Float, default=0.0)
    GamesBack = db.Column(db.Float, default=0.0)
    Last6W = db.Column(db.Float, default=0.0)
    Last6L = db.Column(db.Float, default=0.0)


    def __repr__(self):
        return f''