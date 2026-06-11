from app.extensions import db


class CubsSchedule(db.Model):
    """The cubsschedule table: one row per Cubs game date with the number of
    games and the league X-factor stored for that date.

    Columns are lowercase/unquoted (created by scripts/load_cubs_schedule.py),
    so Postgres folds them to lowercase — the attribute names match directly.
    """
    __tablename__ = 'cubsschedule'

    date = db.Column(db.Date, primary_key=True)
    games = db.Column(db.Integer)
    xfactor = db.Column(db.Float)

    def __repr__(self):
        return f'<CubsSchedule {self.date}>'
