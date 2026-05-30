import sys
from pathlib import Path
sys.path.insert(0, str(Path('c:/Users/SachinKumar/OneDrive - BaffleSol Technologies Pvt Ltd/ServerMonitor')))
from web.app import app, db
from web.models import User

with app.app_context():
    users = db.session.query(User).all()
    print(f'Total users: {len(users)}')
    for user in users:
        print(f'  Username: {user.username}, Email: {getattr(user, "email", "N/A")}')
