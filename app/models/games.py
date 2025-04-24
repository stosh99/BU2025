from app.extensions import db


class Games(db.Model):
    __tablename__ = 'games'

    # Assuming Date and BUTeam together form the primary key
    Date = db.Column(db.Date, primary_key=True)
    BUTeam = db.Column(db.String(64), primary_key=True)

    # Game position fields
    GPC = db.Column(db.String(64))
    GP1B = db.Column(db.String(64))
    GP2B = db.Column(db.String(64))
    GPSS = db.Column(db.String(64))
    GP3B = db.Column(db.String(64))
    GPOF = db.Column(db.String(64))

    # Stats fields
    E = db.Column(db.String(64))
    AB = db.Column(db.String(64))
    RC = db.Column(db.String(64))
    BA = db.Column(db.String(64))
    OBP = db.Column(db.String(64))
    SLG = db.Column(db.String(64))

    def __repr__(self):
        return f'<Game for {self.BUTeam} on {self.Date}>'