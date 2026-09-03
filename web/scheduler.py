"""Compatibility wrapper for scheduler implementations.

This module delegates to the primary job scheduler implementation in
`web.jobs`. It exists so older imports that reference `web.scheduler`
continue to work while consolidating scheduling logic in `web.jobs`.
"""

from importlib import import_module
import logging

logger = logging.getLogger("[SCHEDULER_WRAPPER]")

try:
    jobs_mod = import_module('web.jobs')
    init_scheduler = getattr(jobs_mod, 'init_scheduler')
    shutdown_scheduler = getattr(jobs_mod, 'shutdown_scheduler') if hasattr(jobs_mod, 'shutdown_scheduler') else lambda: None
    # Expose any useful helper functions if present on jobs_mod
    sync_azure_weekly = getattr(jobs_mod, 'register_weekly_license_sync_job', None)
    detect_inactive_changes = None
    logger.info('web.scheduler: delegated to web.jobs')
except Exception as e:
    # Minimal fallback implementations
    logger.exception('Failed to import web.jobs for scheduler delegation; providing fallbacks')

    def init_scheduler(app):
        logger.warning('No scheduler available; init_scheduler is a no-op')

    def shutdown_scheduler():
        logger.warning('No scheduler available; shutdown_scheduler is a no-op')

    def sync_azure_weekly():
        logger.warning('sync_azure_weekly fallback called; no-op')

__all__ = ['init_scheduler', 'shutdown_scheduler', 'sync_azure_weekly', 'detect_inactive_changes']
