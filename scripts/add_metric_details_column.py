import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app
from web.models import db

with app.app_context():
    try:
        # Use IF NOT EXISTS where supported; fallback for older SQLite versions
        try:
            db.session.execute('ALTER TABLE metric ADD COLUMN IF NOT EXISTS details TEXT')
        except Exception:
            # Older SQLite may not support IF NOT EXISTS: attempt and ignore duplicate column error
            try:
                db.session.execute('ALTER TABLE metric ADD COLUMN details TEXT')
            except Exception:
                pass
        db.session.commit()
        print('✅ Ensured metric.details column exists')
    except Exception as e:
        print('❌ Failed to add details column:', e)
        db.session.rollback()
