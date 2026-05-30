"""
Verify schema and data migration between SQLite source and Postgres destination.

Usage:
  Ensure DATABASE_URL env var points to Postgres destination.
  Optionally set SQLITE_SOURCE_URL to the source SQLite URL (defaults to data/central.db).
  python scripts/migration_verify.py

This script compares table lists, column sets, and row counts and writes a report to migration_report.txt
"""
import os
import sys
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path


def get_engine(url):
    return create_engine(url)


def reflect_tables(engine):
    insp = inspect(engine)
    tables = {}
    for tbl in insp.get_table_names():
        cols = [c['name'] for c in insp.get_columns(tbl)]
        tables[tbl] = cols
    return tables


def row_counts(engine, tables):
    counts = {}
    with engine.connect() as conn:
        for t in tables:
            try:
                r = conn.execute(text(f"SELECT COUNT(*) as c FROM \"{t}\""))
                counts[t] = int(r.scalar() or 0)
            except Exception:
                counts[t] = None
    return counts


def main():
    report_lines = []
    dest_url = os.environ.get('DATABASE_URL')
    if not dest_url:
        print('Please set DATABASE_URL to the Postgres destination and retry.')
        sys.exit(1)

    src_url = os.environ.get('SQLITE_SOURCE_URL')
    if not src_url:
        here = Path(__file__).resolve().parents[1]
        src_url = f"sqlite:///{os.path.join(here, 'data', 'central.db')}"

    report_lines.append(f"Source (SQLite): {src_url}")
    report_lines.append(f"Destination (Postgres): {dest_url}")

    src_engine = get_engine(src_url)
    dst_engine = get_engine(dest_url)

    report_lines.append('\nReflecting source schema...')
    src_tables = reflect_tables(src_engine)
    report_lines.append(f"Source tables ({len(src_tables)}): {sorted(src_tables.keys())}")

    report_lines.append('\nReflecting destination schema...')
    dst_tables = reflect_tables(dst_engine)
    report_lines.append(f"Destination tables ({len(dst_tables)}): {sorted(dst_tables.keys())}")

    # Compare table sets
    src_set = set(src_tables.keys())
    dst_set = set(dst_tables.keys())
    only_src = sorted(list(src_set - dst_set))
    only_dst = sorted(list(dst_set - src_set))

    report_lines.append('\nTable differences:')
    report_lines.append(f"  Only in source: {only_src}")
    report_lines.append(f"  Only in dest: {only_dst}")

    # Compare columns for common tables
    report_lines.append('\nColumn differences (common tables):')
    for tbl in sorted(src_set & dst_set):
        src_cols = set(src_tables.get(tbl, []))
        dst_cols = set(dst_tables.get(tbl, []))
        added = sorted(list(dst_cols - src_cols))
        removed = sorted(list(src_cols - dst_cols))
        if added or removed:
            report_lines.append(f"  Table {tbl}: +{added}  -{removed}")

    report_lines.append('\nRow counts (source -> dest):')
    src_counts = row_counts(src_engine, src_tables.keys())
    dst_counts = row_counts(dst_engine, src_tables.keys())
    for tbl in sorted(src_tables.keys()):
        s = src_counts.get(tbl)
        d = dst_counts.get(tbl)
        report_lines.append(f"  {tbl}: source={s} dest={d}")

    # Summary
    report_lines.append('\nSummary:')
    if only_src or only_dst:
        report_lines.append('  Schema mismatch detected. Please review differences above.')
    else:
        report_lines.append('  Table sets match between source and destination.')

    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migration_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    print('Migration verification complete. Report written to', report_path)


if __name__ == '__main__':
    main()
