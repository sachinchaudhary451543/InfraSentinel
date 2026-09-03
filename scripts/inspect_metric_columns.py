import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app
from web.models import db

with app.app_context():
    insp = db.inspect(db.engine)
    cols = insp.get_columns('metric')
    print('Metric columns:')
    for c in cols:
        print(' -', c['name'], c.get('type'))
