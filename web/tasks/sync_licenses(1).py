import logging

logger = logging.getLogger('web.tasks.sync_licenses')


def run_license_sync():
    """Stub license sync implementation.

    The ServerMonitor starter app may optionally schedule weekly license sync.
    If the real sync module is not available in this deployment, this stub
    prevents import failures and keeps the scheduler from crashing.
    """
    logger.info('License sync stub called; no license sync implementation available.')
    return 'stubbed'
