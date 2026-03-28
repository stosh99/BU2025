from app.extensions import db
from datetime import datetime


class Standings(db.Model):
    __tablename__ = 'teamstat'
    __table_args__ = {'extend_existing': True}

    BUTeam = db.Column(db.String(64), primary_key=True, nullable=False)
    Date = db.Column(db.Date, primary_key=True)
    RC = db.Column(db.Float, default=0.0)
    RA = db.Column(db.Float, default=0.0)
    WP = db.Column(db.Float, default=0.0)
    Wins = db.Column(db.Float, default=0.0)
    Losses = db.Column(db.Float, default=0.0)
    GamesBack = db.Column(db.Float, default=0.0)
    Last6W = db.Column(db.Float, default=0.0)
    Last6L = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f'<Standings {self.BUTeam} {self.Date}>'
