from app.models.team import Team
from app.extensions import db

def get_all_teams():
    """Get all teams from the database"""
    return Team.query.all()

def get_team_by_id(team_id):
    """Get a team by its ID"""
    return Team.query.get_or_404(team_id)

def create_team(name, owner, salary=0.0, contract=0.0):
    """Create a new team"""
    team = Team(name=name, owner=owner, salary=salary, contract=contract)
    db.session.add(team)
    db.session.commit()
    return team