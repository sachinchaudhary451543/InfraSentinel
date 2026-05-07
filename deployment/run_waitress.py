from waitress import serve
import logging
import os
import sys

# Add parent directory to path to allow importing web
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - waitress - %(levelname)s - %(message)s'
)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    host = os.environ.get('HOST', '0.0.0.0')
    
    logging.info(f"Starting ServerMonitor production server on {host}:{port}")
    
    # Run the Waitress WSGI server
    serve(
        app, 
        host=host, 
        port=port,
        threads=8,          # Handle multiple concurrent requests
        connection_limit=500 # Support many agent connections
    )
