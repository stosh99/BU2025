from app.extensions import db


class HitterStats(db.Model):
    __tablename__ = 'hitterStats'

    # Use composite primary key
    Date = db.Column(db.Date, primary_key=True)
    BUTeam = db.Column(db.String(64), primary_key=True)
    Player = db.Column(db.String(64), primary_key=True)

    # Hitter stats
    Salary = db.Column(db.Float)
    G = db.Column(db.Float)
    AB = db.Column(db.Float)
    H = db.Column(db.Float)
    _2B = db.Column('2B', db.Float)  # Special naming for column starting with number
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

    def __repr__(self):
        return f'<Player {self.Player} ({self.BUTeam}) on {self.Date}>'