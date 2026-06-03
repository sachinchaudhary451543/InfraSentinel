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
    
    # Find all screenshots with incorrect paths
    all_shots = Screenshot.query.all()
    broken_shots = []
    fixed_shots = []
    
    for shot in all_shots:
        if not shot.local_file_path:
            print(f"ID {shot.id}: No local_file_path set - skipping")
            continue
        
        # Check if path is in the wrong location
        if shot.local_file_path.startswith('C:\\data\\') or shot.local_file_path.startswith('C:/data/'):
            broken_shots.append(shot)
            
            # Check if file exists at that location
            if os.path.isfile(shot.local_file_path):
                # Compute the correct path
                fname = os.path.basename(shot.local_file_path)
                correct_path = os.path.join(correct_base_dir, fname)
                correct_path = os.path.abspath(correct_path)
                
                # Copy file to correct location if not already there
                if not os.path.isfile(correct_path):
                    try:
                        os.makedirs(correct_base_dir, exist_ok=True)
                        shutil.copy2(shot.local_file_path, correct_path)
                        print(f"ID {shot.id}: Copied file from {shot.local_file_path}")
                        print(f"          to {correct_path}")
                    except Exception as e:
                        print(f"ID {shot.id}: FAILED to copy - {e}")
                        continue
                else:
                    print(f"ID {shot.id}: File already exists at correct location")
                
                # Update database record
                shot.local_file_path = correct_path
                db.session.add(shot)
                fixed_shots.append(shot)
                print(f"          Database updated")
            else:
                print(f"ID {shot.id}: File NOT FOUND at {shot.local_file_path} - updating DB only")
                fname = os.path.basename(shot.local_file_path)
                correct_path = os.path.join(correct_base_dir, fname)
                correct_path = os.path.abspath(correct_path)
                shot.local_file_path = correct_path
                db.session.add(shot)
                fixed_shots.append(shot)
        else:
            # Check if it's already in the correct location or if it's valid
            if shot.local_file_path.lower().find('servermonitor') != -1:
                print(f"ID {shot.id}: Already correct path")
            else:
                print(f"ID {shot.id}: Unexpected path format - {shot.local_file_path[:50]}")
    
    print()
    print(f"Summary:")
    print(f"  Total screenshots: {len(all_shots)}")
    print(f"  Broken (wrong path): {len(broken_shots)}")
    print(f"  Fixed: {len(fixed_shots)}")
    
    if fixed_shots:
        try:
            db.session.commit()
            print(f"\n✓ Successfully committed {len(fixed_shots)} record updates")
        except Exception as e:
            print(f"\n✗ Failed to commit: {e}")
            db.session.rollback()
            sys.exit(1)
    else:
        print("\nNo fixes needed")
        sys.exit(0)
