#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['WERKZEUG_RUN_MAIN'] = 'true'

from web.app import app
from web.models import db, RemoteCommand

with app.app_context():
    cmd = RemoteCommand.query.filter_by(id=13).first()
    if cmd:
        print(f'\n✓ COMMAND RESULT VERIFICATION')
        print(f'  ID: {cmd.id}')
        print(f'  Status: {cmd.status}')
        print(f'  Command: {cmd.command} {cmd.parameters}')
        print(f'  Output: {cmd.output[:150] if cmd.output else "(empty)"}')
        print(f'  Executed At: {cmd.executed_at}\n')
    else:
        print('Command not found\n')
