"""
main.py – ServerMonitor Wrapper
===============================
This file now acts as a wrapper for the consolidated logic in web/app.py.
"""

import os
from web.app import app, socketio, run_platform_startup, log

def main():
    # Execute the unified startup sequence
    run_platform_startup()
    
    port = int(os.environ.get("PORT", 3000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    log(f"Starting server on port {port} (debug={debug})")
    
    from web.jobs import shutdown_scheduler
    try:
        socketio.run(
            app,
            host="0.0.0.0",
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=True
        )
    finally:
        shutdown_scheduler()

if __name__ == "__main__":
    main()
