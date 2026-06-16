"""
Database Optimization Module - Add missing indexes and optimize queries
=======================================================================
Implements performance optimizations for dashboard and forecast endpoints.
Runs on startup to ensure all critical indexes exist for SQLite & PostgreSQL.
"""

import logging
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

logger = logging.getLogger("[DB_OPTIMIZATION]")


def create_critical_indexes(db: SQLAlchemy):
    """Create missing indexes for query performance on any database dialect"""
    connection = db.engine.connect()

    indexes = [
        # Metric table
        {
            "name": "idx_metric_server_timestamp",
            "table": "metric",
            "columns": ["server_id", "timestamp"],
            "unique": False
        },
        {
            "name": "idx_metric_timestamp",
            "table": "metric",
            "columns": ["timestamp"],
            "unique": False
        },

        # Server table
        {
            "name": "idx_server_tenant_status",
            "table": "server",
            "columns": ["tenant_id", "status"],
            "unique": False
        },
        {
            "name": "idx_server_agent_installed",
            "table": "server",
            "columns": ["agent_installed"],
            "unique": False
        },

        # AzureDevice
        {
            "name": "idx_azure_device_tenant",
            "table": "azure_device",
            "columns": ["tenant_id"],
            "unique": False
        },

        # SystemAlert
        {
            "name": "idx_system_alert_is_active",
            "table": "system_alert",
            "columns": ["is_active"],
            "unique": False
        },
        {
            "name": "idx_system_alert_server_active",
            "table": "system_alert",
            "columns": ["server_id", "is_active"],
            "unique": False
        },

        # VM
        {
            "name": "idx_vm_server",
            "table": "vm",
            "columns": ["server_id"],
            "unique": False
        },

        # SystemDiscovery
        {
            "name": "idx_system_discovery_tenant_status",
            "table": "system_discovery",
            "columns": ["tenant_id", "status"],
            "unique": False
        },

        # EmployeeAssetLog
        {
            "name": "idx_employee_asset_log_server",
            "table": "employee_asset_log",
            "columns": ["server_id"],
            "unique": False
        },
        {
            "name": "idx_employee_asset_log_tenant",
            "table": "employee_asset_log",
            "columns": ["tenant_id"],
            "unique": False
        },

        # AzureDeviceOwner
        {
            "name": "idx_azure_device_owner_tenant",
            "table": "azure_device_owner",
            "columns": ["tenant_id"],
            "unique": False
        },

        # EmployeeActivity table
        {
            "name": "idx_employee_activity_server_timestamp",
            "table": "employee_activity",
            "columns": ["server_id", "timestamp"],
            "unique": False
        },
        {
            "name": "idx_employee_activity_tenant_timestamp",
            "table": "employee_activity",
            "columns": ["tenant_id", "timestamp"],
            "unique": False
        },

        # ActivitySession table
        {
            "name": "idx_activity_session_tenant_start_time",
            "table": "activity_session",
            "columns": ["tenant_id", "start_time"],
            "unique": False
        },
        {
            "name": "idx_activity_session_employee_start_time",
            "table": "activity_session",
            "columns": ["employee_id", "start_time"],
            "unique": False
        }
    ]

    created_count = 0

    try:
        for idx_spec in indexes:
            try:
                columns_str = ", ".join(idx_spec["columns"])
                unique_str = "UNIQUE" if idx_spec.get("unique", False) else ""
                
                # Standard SQL statement supported natively by both PostgreSQL and SQLite
                create_sql = f"CREATE {unique_str} INDEX IF NOT EXISTS {idx_spec['name']} ON {idx_spec['table']} ({columns_str})"
                connection.execute(text(create_sql))
                connection.commit()
                logger.info(f"✓ Ensured index exists: {idx_spec['name']}")
                created_count += 1
            except Exception as e:
                connection.rollback()
                logger.warning(f"Failed to create index {idx_spec['name']}: {e}")
    finally:
        connection.close()

    logger.info(f"Database optimization complete. Ensured {created_count} indexes exist.")


def analyze_database(db: SQLAlchemy):
    """Analyze database for query optimization (PostgreSQL / SQLite)"""
    try:
        connection = db.engine.connect()
        connection.execute(text("ANALYZE"))
        connection.commit()
        connection.close()
        logger.info("✓ Database ANALYZE completed")
    except Exception as e:
        logger.warning(f"Failed to analyze database: {e}")


def enable_query_logging(app):
    """Enable SQL query logging"""
    if app.config.get('SQLALCHEMY_ECHO'):
        return

    import logging as py_logging
    py_logging.basicConfig()
    py_logging.getLogger('sqlalchemy.engine').setLevel(py_logging.INFO)
    logger.info("SQL query logging enabled")