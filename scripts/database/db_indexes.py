"""
PHASE 18: DATABASE OPTIMIZATION
Create indexes for frequently queried columns
Optimize query performance
"""

import logging
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)


def create_indexes(app, db: SQLAlchemy):
    """Create all necessary database indexes"""
    
    with app.app_context():
        # Get database connection
        engine = db.engine
        
        # Index definitions: (table, columns, index_name, unique=False)
        indexes = [
            # User queries
            ("user", ["tenant_id"], "idx_user_tenant_id"),
            ("user", ["username"], "idx_user_username", True),
            
            # Server queries
            ("server", ["tenant_id"], "idx_server_tenant_id"),
            ("server", ["hostname"], "idx_server_hostname"),
            ("server", ["tenant_id", "hostname"], "idx_server_tenant_hostname", False),
            ("server", ["last_heartbeat"], "idx_server_last_heartbeat"),
            
            # Metric queries (most frequent)
            ("metric", ["server_id"], "idx_metric_server_id"),
            ("metric", ["server_id", "timestamp"], "idx_metric_server_timestamp"),
            ("metric", ["timestamp"], "idx_metric_timestamp"),
            ("metric", ["created_at"], "idx_metric_created_at"),
            
            # Alert queries
            ("system_alert", ["server_id"], "idx_alert_server_id"),
            ("system_alert", ["is_active"], "idx_alert_active"),
            ("system_alert", ["server_id", "is_active"], "idx_alert_server_active"),
            ("system_alert", ["created_at"], "idx_alert_created_at"),
            
            # Agent key queries
            ("agent_key", ["key"], "idx_agent_key_unique", True),
            ("agent_key", ["tenant_id"], "idx_agent_key_tenant_id"),
            ("agent_key", ["is_active"], "idx_agent_key_active"),
            
            # Deployment job queries
            ("deployment_job", ["tenant_id"], "idx_deployment_tenant_id"),
            ("deployment_job", ["server_id"], "idx_deployment_server_id"),
            ("deployment_job", ["status"], "idx_deployment_status"),
            ("deployment_job", ["created_at"], "idx_deployment_created_at"),
            
            # Tenant queries
            ("tenant", ["name"], "idx_tenant_name", True),
        ]
        
        # Create indexes
        for index_def in indexes:
            table_name = index_def[0]
            columns = index_def[1]
            index_name = index_def[2]
            unique = index_def[3] if len(index_def) > 3 else False
            
            try:
                # Build CREATE INDEX statement
                column_str = ", ".join(columns)
                unique_str = "UNIQUE " if unique else ""
                
                sql = f"CREATE {unique_str}INDEX IF NOT EXISTS {index_name} ON {table_name}({column_str})"
                
                with engine.connect() as conn:
                    conn.execute(sql)
                    conn.commit()
                
                logger.info(f"✓ Created index: {index_name} on {table_name}({column_str})")
            
            except Exception as e:
                logger.warning(f"Index creation skipped: {index_name} | Error: {e}")


def analyze_table_stats(app, db: SQLAlchemy):
    """Analyze table statistics for query optimization (PostgreSQL)"""
    
    with app.app_context():
        engine = db.engine
        
        # List of tables to analyze
        tables = [
            'metric', 'server', 'system_alert', 'deployment_job',
            'user', 'tenant', 'agent_key'
        ]
        
        for table in tables:
            try:
                # PostgreSQL ANALYZE command
                sql = f"ANALYZE {table}"
                
                with engine.connect() as conn:
                    conn.execute(sql)
                    conn.commit()
                
                logger.info(f"✓ Analyzed table: {table}")
            
            except Exception as e:
                logger.warning(f"Table analysis skipped: {table} | Error: {e}")


def optimize_database(app, db: SQLAlchemy):
    """Run all database optimizations"""
    logger.info("Starting database optimization...")
    
    try:
        create_indexes(app, db)
        analyze_table_stats(app, db)
        logger.info("✓ Database optimization completed")
    except Exception as e:
        logger.error(f"Database optimization error: {e}")


# Usage in main app:
# from db_indexes import optimize_database
# 
# if __name__ == '__main__':
#     with app.app_context():
#         optimize_database(app, db)
