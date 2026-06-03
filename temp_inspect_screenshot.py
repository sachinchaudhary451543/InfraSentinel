import os
from web.app import app as flask_app
from web.models import db, Screenshot
with flask_app.app_context():
    shot = Screenshot.query.order_by(Screenshot.id.desc()).first()
    if not shot:
        print('no screenshot records')
    else:
        print('id:' + str(shot.id))
        print('filename:' + str(shot.filename))
        print('local_file_path:' + str(shot.local_file_path))
        print('sharepoint_url:' + str(shot.sharepoint_url))
        print('captured_at:' + str(shot.captured_at))
        print('uploaded_at:' + str(shot.uploaded_at))
        print('app_root:' + os.path.dirname(flask_app.root_path))
        print('file_exists:' + str(bool(shot.local_file_path and os.path.isfile(shot.local_file_path))))
        candidate = os.path.abspath(os.path.join(os.path.dirname(flask_app.root_path), 'data', 'screenshots', shot.filename)) if shot and shot.filename else None
        print('candidate:' + str(candidate))
        print('candidate_exists:' + str(os.path.isfile(candidate)) if candidate else 'candidate_exists:None')
