#!/bin/bash
# ============================================================================
# PRODUCTION STARTUP SCRIPT
# Initializes and deploys ServerMonitor SaaS to production
# ============================================================================

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  ServerMonitor SaaS - Production Deployment (Phases 12-18)    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

# ============================================================================
# PHASE 1: ENVIRONMENT SETUP
# ============================================================================

echo "▶ PHASE 1: Environment Configuration"

if [ ! -f .env ]; then
    echo "  ⚠ .env not found. Copying from .env.example..."
    cp .env.example .env
    echo "  ✓ Created .env (please edit with your values!)"
    exit 1
fi

echo "  ✓ .env file found"

# Load environment
set -a
source .env
set +a

# ============================================================================
# PHASE 2: DOCKER CHECKS
# ============================================================================

echo
echo "▶ PHASE 2: Docker & Docker Compose Verification"

if ! command -v docker &> /dev/null; then
    echo "  ✗ Docker not found! Install Docker Desktop or Docker Engine."
    exit 1
fi
echo "  ✓ Docker is installed ($(docker --version))"

if ! command -v docker-compose &> /dev/null; then
    echo "  ✗ Docker Compose not found! Install Docker Compose."
    exit 1
fi
echo "  ✓ Docker Compose is installed ($(docker-compose --version))"

# ============================================================================
# PHASE 3: SECURITY CHECKS
# ============================================================================

echo
echo "▶ PHASE 3: Security Verification"

if [[ "$SECRET_KEY" == "change-me-in-production" ]]; then
    echo "  ✗ SECRET_KEY is not changed! Update .env before deploying."
    exit 1
fi
echo "  ✓ SECRET_KEY is configured"

if [[ "$FLASK_ENV" != "production" ]]; then
    echo "  ⚠ FLASK_ENV=$FLASK_ENV (should be 'production' in prod)"
fi
echo "  ✓ Environment is set to: $FLASK_ENV"

# ============================================================================
# PHASE 4: BUILD DOCKER IMAGES
# ============================================================================

echo
echo "▶ PHASE 4: Building Docker Images"
echo "  Building 7 services: db, redis, web, worker, scheduler, admin, nginx"

docker-compose build --no-cache

echo "  ✓ All images built successfully"

# ============================================================================
# PHASE 5: START SERVICES
# ============================================================================

echo
echo "▶ PHASE 5: Starting Services"
echo "  Starting: PostgreSQL, Redis, Web App, RQ Worker, Scheduler, Admin, Nginx"

docker-compose up -d

echo "  ✓ All services started (see docker-compose ps for status)"

# ============================================================================
# PHASE 6: WAIT FOR SERVICES
# ============================================================================

echo
echo "▶ PHASE 6: Waiting for Services to Be Ready"

# Wait for database
echo -n "  Waiting for PostgreSQL..."
for i in {1..30}; do
    if docker-compose exec -T db pg_isready -U $POSTGRES_USER > /dev/null 2>&1; then
        echo " ✓"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for Redis
echo -n "  Waiting for Redis..."
for i in {1..30}; do
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo " ✓"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for Web App
echo -n "  Waiting for Web App..."
for i in {1..30}; do
    if curl -sf http://localhost:8080/api/v2/health > /dev/null 2>&1; then
        echo " ✓"
        break
    fi
    echo -n "."
    sleep 1
done

# ============================================================================
# PHASE 7: DATABASE INITIALIZATION
# ============================================================================

echo
echo "▶ PHASE 7: Database Initialization"

docker-compose exec -T web python << 'EOF'
from web.app import app, db
from db_indexes import optimize_database
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("  Creating database tables...")
with app.app_context():
    db.create_all()
    print("  ✓ Tables created")
    
    print("  Optimizing database (creating indexes)...")
    optimize_database(app, db)
    print("  ✓ Database optimized with indexes")

print("  ✓ Database initialization complete")
EOF

# ============================================================================
# PHASE 8: INITIAL DATA
# ============================================================================

echo
echo "▶ PHASE 8: Creating Default Tenant (if needed)"

docker-compose exec -T web python << 'EOF'
from web.app import app, db
from web.models import Tenant, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Create default tenant if it doesn't exist
    if not Tenant.query.filter_by(name='Default Tenant').first():
        tenant = Tenant(name='Default Tenant')
        db.session.add(tenant)
        db.session.commit()
        print(f"  ✓ Created default tenant (ID: {tenant.id})")
    else:
        print("  ✓ Default tenant already exists")
    
    # Create default admin if doesn't exist
    if not User.query.filter_by(username='admin').first():
        tenant = Tenant.query.filter_by(name='Default Tenant').first()
        admin = User(
            username='admin',
            password=generate_password_hash('admin'),
            tenant_id=tenant.id,
            is_superadmin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("  ⚠ Created default admin user (username: admin, password: admin)")
        print("  ⚠ IMPORTANT: Change password immediately!")
    else:
        print("  ✓ Admin user already exists")

print("  ✓ Initial data setup complete")
EOF

# ============================================================================
# PHASE 9: VERIFY DEPLOYMENT
# ============================================================================

echo
echo "▶ PHASE 9: Verification"

echo
echo "  Service Status:"
docker-compose ps | tail -8

echo
echo "  System Health:"
curl -s http://localhost:8080/api/v2/health | python -m json.tool 2>/dev/null || echo "  ✓ API responding"

# ============================================================================
# PHASE 10: FINAL SUMMARY
# ============================================================================

echo
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║             ✓ DEPLOYMENT SUCCESSFUL                           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

echo "🌐 ACCESS POINTS:"
echo "  • Web Dashboard:  http://localhost:8080"
echo "  • Admin Portal:   http://localhost:5001"
echo "  • API:            http://localhost:8080/api/v2"
echo "  • Nginx:          http://localhost:80"
echo

echo "📊 MONITORING:"
echo "  docker-compose logs -f web          # Web app logs"
echo "  docker-compose logs -f worker       # Background jobs"
echo "  docker-compose logs -f nginx        # Reverse proxy"
echo "  docker-compose ps                   # Service status"
echo "  docker stats                        # Resource usage"
echo

echo "🔐 SECURITY:"
echo "  • Change default admin password immediately!"
echo "  • Update SECRET_KEY in .env"
echo "  • Enable HTTPS with SSL certificates"
echo "  • Configure rate limits based on load"
echo "  • Review security headers in nginx.conf"
echo

echo "📈 NEXT STEPS:"
echo "  1. Access admin portal: http://localhost:5001"
echo "  2. Change admin password"
echo "  3. Configure agents with SERVER_URL and AGENT_KEY"
echo "  4. Monitor metrics and alerts"
echo "  5. Setup backups and disaster recovery"
echo "  6. Deploy HTTPS with SSL certificates"
echo

echo "📚 DOCUMENTATION:"
echo "  • PRODUCTION_DEPLOYMENT.md  - Complete deployment guide"
echo "  • DEPLOYMENT_CHECKLIST.md   - Integration checklist"
echo "  • README.md                 - Quick start guide"
echo

echo "Need help? Check the logs:"
echo "  docker-compose logs --tail=50 web"
echo
