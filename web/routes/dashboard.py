from flask import Blueprint

dashboard_bp = Blueprint('dashboard', __name__)

# Minimal placeholder routes
@dashboard_bp.route('/')
def index():
    return "Dashboard placeholder"
