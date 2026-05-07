"""
SharePoint API Routes - For testing and managing SharePoint sync
Enhanced with detailed requirement checks and permission validation
"""

from flask import Blueprint, jsonify
from datetime import datetime
import logging

from web.models import Tenant
from web.services.sharepoint_sync import force_sync_tenant, get_sync_status

logger = logging.getLogger(__name__)

sharepoint_api = Blueprint('sharepoint_api', __name__, url_prefix='/api/v2/sharepoint')

# Required permissions for SharePoint integration
REQUIRED_PERMISSIONS = {
    'Sites.ReadWrite.All': {
        'display_name': 'Read and write SharePoint sites',
        'description': 'Required to read/write to SharePoint sites and document libraries',
        'api': 'Microsoft Graph',
        'type': 'Application'
    },
    'Files.ReadWrite.All': {
        'display_name': 'Read and write files in all site collections',
        'description': 'Required to upload and manage files in SharePoint',
        'api': 'Microsoft Graph',
        'type': 'Application'
    }
}

def parse_permission_error(error_msg):
    """Parse SharePoint/Graph error and return user-friendly message with requirements"""
    error_msg_lower = str(error_msg).lower()
    
    if '403' in str(error_msg) or 'access denied' in error_msg_lower:
        return {
            'error_type': 'permission_denied',
            'message': 'Azure AD app lacks required permissions',
            'required_permissions': REQUIRED_PERMISSIONS,
            'next_steps': [
                '1. Go to Azure Portal → Azure AD → App registrations',
                '2. Find and click the "ServerMonitor" app',
                '3. Go to API permissions',
                '4. Click "+ Add a permission"',
                '5. Select Microsoft Graph → Application permissions',
                '6. Search for and add: Sites.ReadWrite.All, Files.ReadWrite.All',
                '7. Click "Grant admin consent for [Organization]"',
                '8. Restart the application'
            ]
        }
    elif 'site not found' in error_msg_lower or '404' in str(error_msg):
        return {
            'error_type': 'site_not_found',
            'message': 'SharePoint site URL not found or misconfigured',
            'next_steps': [
                '1. Verify the SharePoint site URL is correct',
                '2. Ensure the site exists in your tenant',
                '3. Check that the Azure app has access to the site',
                '4. Update the site URL in tenant settings if needed'
            ]
        }
    elif 'token' in error_msg_lower or 'authentication' in error_msg_lower:
        return {
            'error_type': 'auth_failed',
            'message': 'Azure authentication failed',
            'next_steps': [
                '1. Verify Azure AD credentials are configured',
                '2. Check that client ID and secret are valid',
                '3. Ensure app hasn\'t been deleted from Azure AD',
                '4. Regenerate credentials if needed'
            ]
        }
    else:
        return {
            'error_type': 'unknown',
            'message': str(error_msg),
            'next_steps': ['Contact administrator for assistance']
        }

@sharepoint_api.route('/sync/<int:tenant_id>', methods=['POST'])
def force_sync(tenant_id):
    """Force immediate sync for a tenant with enhanced error reporting"""
    try:
        result = force_sync_tenant(tenant_id)
        
        # If failed, provide detailed requirements
        if not result.get('success'):
            error_details = parse_permission_error(result.get('error', ''))
            result['requirements'] = error_details
            return jsonify(result), 400
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Force sync API error: {e}", exc_info=True)
        error_details = parse_permission_error(str(e))
        return jsonify({
            'success': False,
            'error': str(e),
            'requirements': error_details
        }), 500

@sharepoint_api.route('/status/<int:tenant_id>', methods=['GET'])
def get_status(tenant_id):
    """Get detailed sync status for a tenant with enhanced error reporting"""
    try:
        status = get_sync_status(tenant_id)
        
        # If failed, provide detailed requirements
        if not status.get('success'):
            error_details = parse_permission_error(status.get('error', ''))
            status['requirements'] = error_details
            return jsonify(status), 400
        
        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Get status API error: {e}", exc_info=True)
        error_details = parse_permission_error(str(e))
        return jsonify({
            'success': False,
            'error': str(e),
            'requirements': error_details
        }), 500

@sharepoint_api.route('/requirements', methods=['GET'])
def get_requirements():
    """Get required permissions for SharePoint integration"""
    return jsonify({
        'success': True,
        'required_permissions': REQUIRED_PERMISSIONS,
        'setup_steps': [
            '1. Go to Azure Portal → Azure AD → App registrations',
            '2. Find and click the "ServerMonitor" app registration',
            '3. In the left sidebar, click "API permissions"',
            '4. Click the "+ Add a permission" button',
            '5. In the popup, select "Microsoft Graph"',
            '6. Choose "Application permissions" (not Delegated)',
            '7. In the search box, type "Sites.ReadWrite"',
            '8. Check the box for "Sites.ReadWrite.All"',
            '9. Click "Add permissions"',
            '10. Repeat steps 4-9 for "Files.ReadWrite.All"',
            '11. Back to API permissions page, click "Grant admin consent for [Organization]"',
            '12. Confirm the consent prompt',
            '13. Wait for the status checkmarks to appear (green checks)',
            '14. Restart the ServerMonitor application',
            '15. SharePoint sync should now work'
        ],
        'verification': {
            'check_permissions': 'Azure Portal → Azure AD → App registrations → ServerMonitor → API permissions',
            'should_show': 'Both Sites.ReadWrite.All and Files.ReadWrite.All with green checkmarks'
        }
    }), 200

@sharepoint_api.route('/diagnostics/<int:tenant_id>', methods=['GET'])
def run_diagnostics(tenant_id):
    """Run comprehensive diagnostics for a tenant with requirement details"""
    try:
        from core.azure_graph import _get_token_for_tenant
        from web.services.sharepoint_sync import SharePointSyncService
        
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        
        diagnostics = {
            'success': True,
            'tenant_name': tenant.name,
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {},
            'requirements': REQUIRED_PERMISSIONS
        }
        
        # Check 1: Configuration
        diagnostics['checks']['configuration'] = {
            'status': 'pass' if tenant.sharepoint_connected and tenant.sharepoint_auto_sync else 'warn',
            'sharepoint_connected': tenant.sharepoint_connected,
            'auto_sync_enabled': tenant.sharepoint_auto_sync,
            'site_url': tenant.sharepoint_site_url or '(not set)',
            'message': 'SharePoint is configured and auto-sync enabled' if (tenant.sharepoint_connected and tenant.sharepoint_auto_sync) else 'SharePoint not fully configured'
        }
        
        # Check 2: Token Generation
        token_error = None
        try:
            token = _get_token_for_tenant(tenant)
            diagnostics['checks']['token_generation'] = {
                'status': 'pass' if token else 'fail',
                'message': 'Azure authentication token generated successfully' if token else 'Token generation failed - check Azure credentials'
            }
        except Exception as e:
            token_error = str(e)
            diagnostics['checks']['token_generation'] = {
                'status': 'fail',
                'message': f'Authentication error: {token_error}',
                'help': 'Ensure Azure credentials (Client ID, Tenant ID, Secret) are properly configured'
            }
        
        # Check 3: Site ID Resolution
        site_error = None
        try:
            service = SharePointSyncService(tenant)
            if service.site_id:
                diagnostics['checks']['site_id_resolution'] = {
                    'status': 'pass',
                    'site_id': service.site_id,
                    'message': 'SharePoint site ID resolved successfully'
                }
            else:
                site_error = 'Site ID not resolved'
                diagnostics['checks']['site_id_resolution'] = {
                    'status': 'fail',
                    'message': 'Failed to resolve site ID',
                    'help': 'Verify SharePoint site URL and ensure permissions are granted'
                }
        except Exception as e:
            site_error = str(e)
            diagnostics['checks']['site_id_resolution'] = {
                'status': 'fail',
                'message': f'Error resolving site: {site_error}',
                'help': 'This is typically due to missing permissions. Ensure Sites.ReadWrite.All is granted.',
                'required_permission': 'Sites.ReadWrite.All'
            }
        
        # Check 4: Data Availability
        from web.models import Server, Metric, Screenshot
        diagnostics['checks']['data_availability'] = {
            'status': 'pass',
            'servers': Server.query.filter_by(tenant_id=tenant_id).count(),
            'metrics': Metric.query.join(Server).filter(Server.tenant_id == tenant_id).count(),
            'unsynced_screenshots': Screenshot.query.filter_by(tenant_id=tenant_id, sharepoint_url=None).count(),
            'total_screenshots': Screenshot.query.filter_by(tenant_id=tenant_id).count(),
            'message': 'Data is available in the system'
        }
        
        # Summary with recommendations
        check_statuses = [check.get('status') for check in diagnostics['checks'].values()]
        has_failures = 'fail' in check_statuses
        has_warnings = 'warn' in check_statuses
        
        if has_failures:
            diagnostics['overall_status'] = 'needs_attention'
            diagnostics['recommendation'] = 'Please check the failed checks above. Most commonly this requires granting Azure AD app permissions.'
            
            # Add specific remediation based on which checks failed
            if diagnostics['checks'].get('site_id_resolution', {}).get('status') == 'fail':
                diagnostics['fix_steps'] = parse_permission_error('403 Access Denied').get('next_steps', [])
        elif has_warnings:
            diagnostics['overall_status'] = 'partially_configured'
            diagnostics['recommendation'] = 'SharePoint integration is partially configured. Enable in tenant settings to activate sync.'
        else:
            diagnostics['overall_status'] = 'healthy'
            diagnostics['recommendation'] = 'SharePoint integration is healthy and ready to sync.'
        
        return jsonify(diagnostics), 200
        
    except Exception as e:
        logger.error(f"Diagnostics API error: {e}", exc_info=True)
        error_details = parse_permission_error(str(e))
        return jsonify({
            'success': False,
            'error': str(e),
            'requirements': REQUIRED_PERMISSIONS,
            'requirements_detail': error_details
        }), 500

@sharepoint_api.route('/sync-all', methods=['POST'])
def sync_all_tenants_api():
    """Force sync for all configured tenants (admin only)"""
    try:
        from web.services.sharepoint_sync import sync_all_tenants
        
        results = sync_all_tenants()
        
        return jsonify({
            'success': True,
            'tenants_processed': len(results),
            'results': results,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Sync all API error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
