"""
Generate an Alembic autogenerate revision using the project's alembic.ini and models.

Usage:
  python scripts/generate_alembic_migration.py "postgresql://user:pass@host:5432/dbname" "message"

If no message provided, uses 'autogen'.
"""
import sys
import os
from alembic import command
from alembic.config import Config


def url_safe(db_url: str) -> str:
    # If password contains @ characters, user should URL-encode; try to be helpful by encoding lone @ in password
    # This is a best-effort; if the URL already contains %40, we leave it.
    if '%40' in db_url:
        return db_url
    # Split scheme://user:pass@host...
    try:
        scheme, rest = db_url.split('://', 1)
        userinfo, hostpart = rest.split('@', 1)
        if ':' in userinfo:
            user, password = userinfo.split(':', 1)
            if '@' in password:
                password = password.replace('@', '%40')
                return f"{scheme}://{user}:{password}@{hostpart}"
    except Exception:
        return db_url
    return db_url


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/generate_alembic_migration.py <DATABASE_URL> [message]')
        sys.exit(1)

    db_url = sys.argv[1]
    message = sys.argv[2] if len(sys.argv) > 2 else 'autogen'

    db_url = url_safe(db_url)
    os.environ['DATABASE_URL'] = db_url

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(here, 'alembic.ini')
    cfg = Config(alembic_ini)
    cfg.set_main_option('sqlalchemy.url', db_url)

    # Ensure versions directory exists
    versions_dir = os.path.join(here, 'alembic', 'versions')
    os.makedirs(versions_dir, exist_ok=True)

    print(f"Generating alembic revision (autogenerate) with DB URL: {db_url}")
    command.revision(cfg, message=message, autogenerate=True)
    print('Revision generation complete. Check alembic/versions for the new file.')


if __name__ == '__main__':
    main()
