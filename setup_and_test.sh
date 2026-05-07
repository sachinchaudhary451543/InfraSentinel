#!/bin/bash
# Setup and test script for ServerMonitor system

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}ServerMonitor - Complete Setup & Test${NC}"
echo -e "${BLUE}============================================${NC}"

# Step 1: Activate virtual environment
echo -e "\n${YELLOW}[1/5] Activating virtual environment...${NC}"
if [ -f ".venv/Scripts/Activate.ps1" ]; then
    powershell -Command ". .\.venv\Scripts\Activate.ps1"
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
else
    echo -e "${RED}✗ Virtual environment not found${NC}"
    exit 1
fi

# Step 2: Install dependencies
echo -e "\n${YELLOW}[2/5] Installing dependencies...${NC}"
pip install flask flask-sqlalchemy flask-login pandas matplotlib requests xlsxwriter -q
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${RED}✗ Dependency installation failed${NC}"
    exit 1
fi

# Step 3: Initialize databases
echo -e "\n${YELLOW}[3/5] Initializing databases...${NC}"
python init_all_databases.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Databases initialized${NC}"
else
    echo -e "${RED}✗ Database initialization failed${NC}"
    exit 1
fi

# Step 4: Verify database files
echo -e "\n${YELLOW}[4/5] Verifying database files...${NC}"
files_ok=true

if [ ! -f "admin_portal/admin_portal.db" ]; then
    echo -e "${RED}✗ Missing: admin_portal/admin_portal.db${NC}"
    files_ok=false
else
    echo -e "${GREEN}✓ admin_portal/admin_portal.db exists${NC}"
fi

if [ ! -f "data/ServerMetrics.db" ]; then
    echo -e "${RED}✗ Missing: data/ServerMetrics.db${NC}"
    files_ok=false
else
    echo -e "${GREEN}✓ data/ServerMetrics.db exists${NC}"
fi

if [ ! -f "data/central_agents.db" ]; then
    echo -e "${RED}✗ Missing: data/central_agents.db${NC}"
    files_ok=false
else
    echo -e "${GREEN}✓ data/central_agents.db exists${NC}"
fi

if [ ! -f "web/config/credentials.json" ]; then
    echo -e "${RED}✗ Missing: web/config/credentials.json${NC}"
    files_ok=false
else
    echo -e "${GREEN}✓ web/config/credentials.json exists${NC}"
fi

if [ "$files_ok" = false ]; then
    echo -e "${RED}✗ Some required files are missing${NC}"
    exit 1
fi

# Step 5: System check
echo -e "\n${YELLOW}[5/5] Running system checks...${NC}"

# Check Flask
python -c "import flask; print(f'Flask {flask.__version__}')" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Flask installed${NC}"
else
    echo -e "${RED}✗ Flask import failed${NC}"
fi

# Check SQLAlchemy
python -c "import flask_sqlalchemy; print('SQLAlchemy OK')" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Flask-SQLAlchemy installed${NC}"
else
    echo -e "${RED}✗ SQLAlchemy import failed${NC}"
fi

# Check Pandas
python -c "import pandas; print('Pandas OK')" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Pandas installed${NC}"
else
    echo -e "${RED}✗ Pandas import failed${NC}"
fi

# Final summary
echo -e "\n${BLUE}============================================${NC}"
echo -e "${GREEN}✓ ALL SETUP COMPLETE!${NC}"
echo -e "${BLUE}============================================${NC}"

echo -e "\n${BLUE}📋 NEXT STEPS:${NC}"
echo -e "  1. Open terminal 1 and run:"
echo -e "     ${YELLOW}cd admin_portal && python app.py${NC}"
echo -e "\n  2. Open terminal 2 and run:"
echo -e "     ${YELLOW}cd web && python app.py${NC}"
echo -e "\n  3. Open your browser:"
echo -e "     Admin Portal:  ${YELLOW}http://localhost:5001${NC}"
echo -e "     Web Dashboard: ${YELLOW}http://localhost:5000${NC}"
echo -e "\n${BLUE}📖 LOGIN CREDENTIALS:${NC}"
echo -e "  Admin Portal:"
echo -e "     Username: ${YELLOW}admin${NC}"
echo -e "     Password: ${YELLOW}admin${NC}"
echo -e "\n  Web Dashboard (Admin):"
echo -e "     Username: ${YELLOW}admin${NC}"
echo -e "     Password: ${YELLOW}admin123${NC}"
echo -e "     Role: ${YELLOW}admin${NC}"
echo -e "\n  Web Dashboard (User):"
echo -e "     Username: ${YELLOW}user${NC}"
echo -e "     Password: ${YELLOW}user123${NC}"
echo -e "     Role: ${YELLOW}user${NC}"

echo -e "\n${BLUE}🧪 TESTING:${NC}"
echo -e "  After starting both services, follow the live testing guide:"
echo -e "  - TEST 1: Admin Portal Login (5001)"
echo -e "  - TEST 2: Create Tenant"
echo -e "  - TEST 3: Add User"
echo -e "  - TEST 4: Generate Agent Key"
echo -e "  - TEST 5: Domain Discovery"
echo -e "  - TEST 6: Web Dashboard Login (5000)"
echo -e "  - TEST 7: View Metrics"
echo -e "  - TEST 8: Smart Analyzer"
echo -e "  - TEST 9: Agent Monitoring"
echo -e "  - TEST 10: End-to-End Workflow"

echo -e "\n${BLUE}============================================${NC}"
