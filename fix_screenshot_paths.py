#!/usr/bin/env python3
"""Fix screenshot records with incorrect paths"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from web.app import app
from web.models import db, Screenshot
import shutil

with app.app_context():
    from web.app import app as flask_app
    
    # Get correct base directory
    app_root = os.path.dirname(flask_app.root_path)  # web -> ServerMonitor
    correct_base_dir = os.path.join(app_root, 'data', 'screenshots')
    
    print(f"Correct base directory: {correct_base_dir}")
    print()
    
    # Find all screenshots with incorrect paths or missing local_file_path
    all_shots = Screenshot.query.all()
    fixed_shots = []
    
    for shot in all_shots:
        if not shot.filename and not shot.local_file_path:
            print(f"ID {shot.id}: No filename or local_file_path available - skipping")
            continue

        fname = os.path.basename(shot.filename or shot.local_file_path)
        correct_path = os.path.abspath(os.path.join(correct_base_dir, fname))
        current_path = (shot.local_file_path or '').strip()

        current_exists = os.path.isfile(current_path) if current_path else False
        correct_exists = os.path.isfile(correct_path)

        if correct_exists and current_path != correct_path:
            print(f"ID {shot.id}: Updating db path to current screenshots folder")
            shot.local_file_path = correct_path
            db.session.add(shot)
            fixed_shots.append(shot)
            continue

        if current_exists and not correct_exists and current_path != correct_path:
            print(f"ID {shot.id}: Copying file from old location to correct screenshots folder")
            try:
                os.makedirs(correct_base_dir, exist_ok=True)
                shutil.copy2(current_path, correct_path)
                shot.local_file_path = correct_path
                db.session.add(shot)
                fixed_shots.append(shot)
                print(f"          Copied to {correct_path}")
            except Exception as e:
                print(f"ID {shot.id}: FAILED to copy - {e}")
            continue

        if current_exists and current_path == correct_path:
            print(f"ID {shot.id}: Path already correct")
            continue

        if not current_exists and correct_exists:
            print(f"ID {shot.id}: Current path missing, but correct screenshot exists. Updating path.")
            shot.local_file_path = correct_path
            db.session.add(shot)
            fixed_shots.append(shot)
            continue

        if current_exists:
            print(f"ID {shot.id}: File exists at current path but correct path not available: {current_path}")
            continue

        print(f"ID {shot.id}: No screenshot file found for {fname}. Expected {correct_path}")
    
    print()
    print(f"Summary:")
    print(f"  Total screenshots: {len(all_shots)}")
    print(f"  Fixed: {len(fixed_shots)}")
    
    if fixed_shots:
        try:
            db.session.commit()
            print(f"\nSuccessfully committed {len(fixed_shots)} record updates")
        except Exception as e:
            print(f"\nFailed to commit: {e}")
            db.session.rollback()
            sys.exit(1)
    else:
        print("\nNo fixes needed")
        sys.exit(0)
