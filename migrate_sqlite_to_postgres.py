"""
Helper script to copy schema + data from the local SQLite DB to a Postgres target.

Usage:
  - Set environment variable DATABASE_URL to the target Postgres SQLAlchemy URL.
  - Example: export DATABASE_URL=postgresql+psycopg[binary]://user:pass@host:5432/servermonitor
  - Then run: python migrate_sqlite_to_postgres.py

This script is best-effort: it will reflect tables from the source SQLite DB and
copy rows to Postgres preserving column names. Complex types, constraints or
custom SQLite-only constructs may require manual attention.
"""
import os
import sys
from sqlalchemy import create_engine, MetaData, Table, text
import json
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError


def main():
    src = os.environ.get('SQLITE_SOURCE_URL')
    if not src:
        # default to project's data/central.db
        here = os.path.dirname(os.path.abspath(__file__))
        src = f"sqlite:///{os.path.join(here, 'data', 'central.db')}"

    dst = os.environ.get('DATABASE_URL')
    if not dst:
        print("Please set DATABASE_URL to the target Postgres database and retry.")
        sys.exit(1)

    print(f"Source (SQLite): {src}")
    print(f"Destination (Postgres): {dst}")

    src_engine = create_engine(src)
    dst_engine = create_engine(dst)

    src_meta = MetaData()
    dst_meta = MetaData()

    print("Reflecting source schema...")
    src_meta.reflect(bind=src_engine)

    # Ensure destination has tables/columns for each source table
    from sqlalchemy import inspect
    dst_inspector = inspect(dst_engine)
    src_conn = src_engine.connect()
    dst_conn = dst_engine.connect()

    for name, table in src_meta.tables.items():
        print(f"Preparing table: {name}")
        # Create table in dest if not exists using source DDL mapping
        if not dst_engine.dialect.has_table(dst_conn, name):
            # attempt to create minimal table (columns mapped conservatively)
            cols = []
            try:
                # use PRAGMA to get column declarations and types
                pragma = src_conn.execute(text(f"PRAGMA table_info('{name}')")).fetchall()
            except Exception:
                pragma = []

            create_cols_defs = []
            for col in pragma:
                # pragma columns: (cid, name, type, notnull, dflt_value, pk)
                col_name = col[1]
                col_type = (col[2] or '').upper()
                if 'INT' in col_type:
                    mapped = 'INTEGER'
                elif 'CHAR' in col_type or 'TEXT' in col_type or 'CLOB' in col_type or 'VARCHAR' in col_type:
                    mapped = 'TEXT'
                elif 'DOUBLE' in col_type or 'REAL' in col_type or 'FLOA' in col_type:
                    mapped = 'DOUBLE PRECISION'
                elif 'BOOLEAN' in col_type:
                    mapped = 'BOOLEAN'
                elif 'DATETIME' in col_type or 'TIMESTAMP' in col_type:
                    mapped = 'TIMESTAMP'
                else:
                    mapped = 'TEXT'

                default = ''
                if col[4] is not None:
                    raw_def = str(col[4])
                    if mapped == 'BOOLEAN':
                        if raw_def.strip() in ('0', '0', 'FALSE', 'False'):
                            default = ' DEFAULT FALSE'
                        elif raw_def.strip() in ('1', 'TRUE', 'True'):
                            default = ' DEFAULT TRUE'
                        else:
                            # fallback: do not set default for ambiguous values
                            default = ''
                    else:
                        default = f" DEFAULT {raw_def}"

                pk = ' PRIMARY KEY' if col[5] else ''
                create_cols_defs.append(f'"{col_name}" {mapped}{default}{pk}')

            if create_cols_defs:
                create_sql = f'CREATE TABLE IF NOT EXISTS "{name}" ({", ".join(create_cols_defs)})'
                try:
                    dst_conn.execute(text(create_sql))
                except Exception as e:
                    print(f"  failed creating table {name}: {e}")
                    try:
                        dst_conn.execute(text('ROLLBACK'))
                    except Exception:
                        pass

    # Determine dependency-aware table order: copy common parent tables first
    preferred_order = ['tenant', 'user', 'azure_user', 'azure_device', 'server', 'employee']
    remaining = [n for n in src_meta.tables.keys() if n not in preferred_order]
    table_order = [n for n in preferred_order if n in src_meta.tables] + remaining

    # Now copy data table-by-table using column intersection
    for name in table_order:
        table = src_meta.tables[name]
        print(f"Copying data for table: {name}")
        try:
            src_res = src_conn.execute(table.select()).fetchall()
        except Exception as e:
            print(f"  failed reading source table {name}: {e}")
            continue

        if not src_res:
            print("  (no rows)")
            continue

        # Determine columns in destination
        try:
            dst_cols = [c['name'] for c in dst_inspector.get_columns(name)]
        except Exception:
            dst_cols = [c.name for c in table.columns]

        cols = [c for c in table.columns.keys() if c in dst_cols]
        if not cols:
            print("  no matching columns in destination; skipping")
            continue

        rows = []
        for row in src_res:
            mapped = {}
            for idx, col in enumerate(table.columns.keys()):
                if col not in cols:
                    continue
                val = row[idx]
                # Convert dict-like values to JSON strings for safe insertion into Postgres JSONB/JSON columns
                if isinstance(val, dict):
                    mapped[col] = json.dumps(val)
                else:
                    mapped[col] = val
            rows.append(mapped)
        # build insert SQL
        col_list = ','.join(f'"{c}"' for c in cols)
        param_list = ','.join([f':{c}' for c in cols])
        insert_sql = f'INSERT INTO "{name}" ({col_list}) VALUES ({param_list})'
        try:
            dst_conn.execute(text('BEGIN'))
            for r in rows:
                dst_conn.execute(text(insert_sql), r)
            dst_conn.execute(text('COMMIT'))
            print(f"  copied {len(rows)} rows")
        except SQLAlchemyError as e:
            try:
                dst_conn.execute(text('ROLLBACK'))
            except Exception:
                pass
            print(f"  failed inserting rows into {name}: {e}")

    src_conn.close()
    dst_conn.close()
    print("Migration attempt complete. Verify constraints, indexes, and types in Postgres.")


if __name__ == '__main__':
    main()
