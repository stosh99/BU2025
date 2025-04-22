from app.extensions import db
from datetime import datetime


class Team(db.Model):
    __tablename__ = 'teamstat'

    # Use composite primary key since your table doesn't have an id column
    Date = db.Column(db.Date, primary_key=True)
    BUTeam = db.Column(db.String(64), primary_key=True)

    # Hitting stats
    G = db.Column(db.Float)
    AB = db.Column(db.Float)
    H = db.Column(db.Float)
    _2B = db.Column('2B', db.Float)  # Note the special naming for column starting with number
    _3B = db.Column('3B', db.Float)
    HR = db.Column(db.Float)
    BB = db.Column(db.Float)
    HP = db.Column(db.Float)
    SB = db.Column(db.Float)
    CS = db.Column(db.Float)
    E = db.Column(db.Float)
    KO = db.Column(db.Float)
    RC = db.Column(db.Float)
    OPS = db.Column(db.Float)

    # Pitching stats
    APP = db.Column(db.Float)
    GS = db.Column(db.Float)
    QS = db.Column(db.Float)
    INN = db.Column(db.Float)
    ER = db.Column(db.Float)
    RA = db.Column(db.Float)
    ERA = db.Column(db.Float)
    HA = db.Column(db.Float)
    K = db.Column(db.Float)
    BBI = db.Column(db.Float)
    W = db.Column(db.Float)
    L = db.Column(db.Float)
    S = db.Column(db.Float)

    # Team info
    Salary = db.Column(db.Float)
    X_factor = db.Column(db.Float)
    WP = db.Column(db.Float)
    BUGames = db.Column(db.Integer)
    Wins = db.Column(db.Float)
    Losses = db.Column(db.Float)
    GamesBack = db.Column(db.Float)
    Last6W = db.Column(db.Float)
    Last6L = db.Column(db.Float)

    def __repr__(self):
        return f'<Team {self.BUTeam} on {self.Date}>'