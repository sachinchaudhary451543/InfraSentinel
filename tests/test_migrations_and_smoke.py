import os
from pathlib import Path
import alembic.config
import alembic.command


def test_migrations_and_smoke(tmp_path):
    """Run alembic migrations against a temporary SQLite DB and perform
    lightweight smoke checks against the Flask app.
    """
    # Prepare temporary DB
    db_file = tmp_path / "ci_test.db"
    db_url = f"sqlite:///{db_file}"

    # Ensure environment variable used by alembic/env.py is set
    os.environ['DATABASE_URL'] = db_url

    # Run alembic upgrade head programmatically
    repo_root = Path(__file__).resolve().parents[1]
    cfg = alembic.config.Config(str(repo_root / 'alembic.ini'))
    # Make sure alembic uses our test DB
    cfg.set_main_option('sqlalchemy.url', db_url)
    alembic.command.upgrade(cfg, 'head')

    # Import the Flask app AFTER migrations are applied so ensure_initial_setup
    # will not attempt to modify schema at runtime.
    from web.app import app

    client = app.test_client()

    # Root should redirect to login or return 200
    r = client.get('/')
    assert r.status_code in (200, 301, 302)

    # Favicon should respond (200 or 404 depending on static files)
    r = client.get('/favicon.ico')
    assert r.status_code in (200, 404)

    # Ensure core blueprints are registered
    expected = ['auth', 'main', 'api', 'agents', 'users', 'tenants']
    missing = [b for b in expected if b not in app.blueprints]
    assert missing == [], f"Missing blueprints: {missing}"

def test_productivity_aggregation():
    from web.productivity import aggregate_productivity
    events = [
        {'duration_seconds': 3600 * 2, 'activity_type': 'active', 'application': 'code'},
        {'duration_seconds': 60 * 30, 'activity_type': 'idle', 'application': None},
        {'duration_seconds': 60 * 20, 'activity_type': 'active', 'application': 'teams'},
        {'duration_seconds': 60 * 15, 'activity_type': 'neutral', 'application': 'browser'},
    ]
    s = aggregate_productivity(events)
    assert s['total_seconds'] == 2 * 3600 + 30 * 60 + 20 * 60 + 15 * 60
    assert s['desk_seconds'] == 2 * 3600 + 20 * 60
    assert any(a['app'] == 'code' for a in s['most_used_apps'])

    # Cleanup environment
    del os.environ['DATABASE_URL']
