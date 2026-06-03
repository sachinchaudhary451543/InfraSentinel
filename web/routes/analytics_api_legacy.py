"""
Workforce Analytics / Intelligence Routes
Restores the workforce intelligence dashboard nav item and reuses the existing
productivity overview data pipeline without duplicating business logic.
"""

import logging
from datetime import datetime
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from web.routes.asset_management import _build_productivity_rows

logger = logging.getLogger("[ANALYTICS_API]")
analytics_api_bp = Blueprint('analytics_api', __name__, url_prefix='/analytics')


@analytics_api_bp.route('/workforce')
@login_required
def workforce_dashboard():
    """Render the Workforce Intelligence dashboard using existing productivity data."""
    try:
        date_str = (request.args.get('date') or '').strip()
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except ValueError:
            target_date = datetime.utcnow().date()

        emp_rows = _build_productivity_rows(current_user.tenant_id, target_date)

        return render_template(
            'productivity_overview.html',
            employees=emp_rows,
            selected_date=target_date.strftime('%Y-%m-%d'),
            page_title='Workforce Intelligence',
            page_description='Monitor employee productivity and system activity linked through Azure and local assignments.',
            workforce_mode=True
        )
    except Exception as e:
        logger.error(f"Error loading workforce intelligence dashboard: {e}")
        return render_template(
            'productivity_overview.html',
            employees=[],
            selected_date=datetime.utcnow().strftime('%Y-%m-%d'),
            page_title='Workforce Intelligence',
            page_description='Unable to load workforce analytics at this time.',
            workforce_mode=True,
            error=str(e)
        )
