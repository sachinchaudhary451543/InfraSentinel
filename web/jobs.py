"""
Background Jobs for ServerMonitor
Handles periodic tasks like SharePoint data syncing and metric aggregation
"""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from web.models import db, Tenant
from web.services.sharepoint_sync import sync_all_tenants

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def init_scheduler(app):
    """Initialize background job scheduler"""
    global scheduler
    
    if scheduler is None:
        scheduler = BackgroundScheduler()
        scheduler.start()
        logger.info('Background job scheduler initialized')
    
    # Register jobs
    with app.app_context():
        register_sharepoint_sync_job(app)
        register_metric_cleanup_job(app)
        register_azure_inventory_sync_job(app)


def register_sharepoint_sync_job(app):
    """Register SharePoint sync job - runs every 5 minutes"""
    
    def sync_job():
        """Periodic SharePoint sync for all connected tenants"""
        try:
            with app.app_context():
                logger.info(f'[SharePoint Sync] Starting scheduled sync at {datetime.now()}')
                
                # Call the main sync function
                results = sync_all_tenants()
                
                if results:
                    total_syncs = len(results)
                    total_servers = sum(r.get('servers_synced', 0) for r in results)
                    total_metrics = sum(r.get('metrics_synced', 0) for r in results)
                    logger.info(f'[SharePoint Sync] Completed: {total_syncs} tenants, {total_servers} servers, {total_metrics} metrics synced')
                else:
                    logger.info('[SharePoint Sync] No tenants to sync')
                    
        except Exception as e:
            logger.error(f'[SharePoint Sync] Error during scheduled sync: {str(e)}', exc_info=True)
    
    # Check if job already exists
    existing_job = scheduler.get_job('sharepoint_sync')
    if existing_job:
        existing_job.remove()
    
    # Schedule job to run every 5 minutes
    scheduler.add_job(
        sync_job,
        IntervalTrigger(minutes=5),
        id='sharepoint_sync',
        name='SharePoint Sync Task',
        misfire_grace_time=10,
        coalesce=True,
        max_instances=1
    )
    logger.info('SharePoint sync job scheduled: every 5 minutes')


def register_metric_cleanup_job(app):
    """Register metric data cleanup job - runs daily at 2 AM"""
    
    def cleanup_job():
        """Clean up old metrics and aggregate historical data"""
        try:
            with app.app_context():
                logger.info(f'[Metric Cleanup] Starting cleanup at {datetime.now()}')
                
                # Keep only last 30 days of metrics
                cutoff_date = datetime.utcnow() - timedelta(days=30)
                
                from web.models import Metric
                deleted_count = db.session.query(Metric).filter(
                    Metric.timestamp < cutoff_date
                ).delete()
                
                db.session.commit()
                
                logger.info(f'[Metric Cleanup] Cleaned up {deleted_count} old metric records')
                
        except Exception as e:
            logger.error(f'[Metric Cleanup] Error during cleanup: {str(e)}', exc_info=True)
    
    # Check if job already exists
    existing_job = scheduler.get_job('metric_cleanup')
    if existing_job:
        existing_job.remove()
    
    # Schedule job to run daily at 2 AM
    scheduler.add_job(
        cleanup_job,
        'cron',
        hour=2,
        minute=0,
        id='metric_cleanup',
        name='Metric Cleanup Task',
        misfire_grace_time=300,
        max_instances=1
    )
    logger.info('Metric cleanup job scheduled: daily at 2:00 AM')


def shutdown_scheduler():
    """Shutdown the scheduler"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info('Background job scheduler shut down')


def get_scheduler():
    """Get the global scheduler instance"""
    return scheduler


# Manual job functions that can also be called directly

def manual_sharepoint_sync():
    """Manually trigger SharePoint sync for all tenants"""
    try:
        logger.info(f'[Manual SharePoint Sync] Starting manual sync at {datetime.now()}')
        results = sync_all_tenants()
        
        if results:
            total_syncs = len(results)
            total_servers = sum(r.get('servers_synced', 0) for r in results)
            total_metrics = sum(r.get('metrics_synced', 0) for r in results)
            message = f'Manual sync completed: {total_syncs} tenants, {total_servers} servers, {total_metrics} metrics synced'
        else:
            message = 'Manual sync completed: No tenants to sync'
        
        logger.info(f'[Manual SharePoint Sync] {message}')
        return {'success': True, 'message': message}
        
    except Exception as e:
        error_msg = f'Manual sync failed: {str(e)}'
        logger.error(f'[Manual SharePoint Sync] {error_msg}', exc_info=True)
        return {'success': False, 'message': error_msg}


def register_azure_inventory_sync_job(app):
    """Register Azure AD device inventory sync job - runs every 6 hours"""

    def azure_sync_job():
        """Pull Azure AD devices into local AzureDevice table for all tenants"""
        try:
            with app.app_context():
                logger.info(f'[Azure Inventory Sync] Starting at {datetime.now()}')
                from web.models import AzureDevice, Tenant
                from core import azure_graph

                tenants = Tenant.query.filter(
                    Tenant.azure_client_id.isnot(None),
                    Tenant.azure_client_id != ''
                ).all()

                total_synced = 0
                for t in tenants:
                    try:
                        devices = azure_graph.get_devices(t)
                        synced = 0
                        for d in (devices or []):
                            did = d.get('id')
                            name = d.get('displayName')
                            if not did or not name:
                                continue
                            ad = AzureDevice.query.filter_by(device_id=did, tenant_id=t.id).first()
                            if not ad:
                                ad = AzureDevice()
                                ad.tenant_id = t.id
                                ad.device_id = did
                                db.session.add(ad)
                            ad.display_name = name
                            ad.os_platform = d.get('operatingSystem', '')
                            ad.os_version = d.get('operatingSystemVersion', '')
                            synced += 1
                        db.session.commit()
                        total_synced += synced
                        logger.info(f'[Azure Inventory Sync] {t.name}: {synced} devices synced')
                    except Exception as e:
                        logger.error(f'[Azure Inventory Sync] Failed for {t.name}: {e}')
                        db.session.rollback()

                logger.info(f'[Azure Inventory Sync] Complete: {total_synced} devices across {len(tenants)} tenants')
        except Exception as e:
            logger.error(f'[Azure Inventory Sync] Error: {e}', exc_info=True)

    existing_job = scheduler.get_job('azure_inventory_sync')
    if existing_job:
        existing_job.remove()

    scheduler.add_job(
        azure_sync_job,
        IntervalTrigger(hours=6),
        id='azure_inventory_sync',
        name='Azure Inventory Sync',
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1
    )
    logger.info('Azure inventory sync job scheduled: every 6 hours')


def get_queued_jobs():
    """Get list of scheduled jobs"""
    if not scheduler:
        return []
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'func': str(job.func),
            'next_run_time': str(job.next_run_time),
            'misfire_grace_time': job.misfire_grace_time
        })
    
    return jobs
