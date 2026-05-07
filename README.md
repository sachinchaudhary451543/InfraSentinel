# InfraSentinel Enterprise Edition

A production-ready Server, Network & VM Monitoring application featuring Real-Time WebSockets, active Remote Command Execution, and scalable containerization.

## Architecture Upgrades
- **Phase 1**: Real-Time Metrics via WebSockets (Socket.IO + Gevent)
- **Phase 2**: Push-based Python Agent metrics polling.
- **Phase 3**: Remote Command task queue via Push-to-Agent fetching.
- **Phase 4**: Advanced Threshold Alert Evaluation Engine.
- **Phase 5**: Secure API logic enforcing Agent API Tokens and RBAC.
- **Phase 6/7**: Scalability via asynchronous worker patterns & Docker.
- **Phase 8**: Detailed platform Audit Logs.

## 🚀 Quick Start (Local Run - Simple)

If you just want to run the system securely on your local PC across one machine:

### 1. Start the Backend
The backend utilizes SQLite by default if no configuration is provided.
```powershell
# Activate the virtual environment
.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install -r requirements.txt

# Start Server on http://localhost:8080
python web/app.py
```

### 2. Login
Navigate to `http://localhost:8080`.
The default credentials are:
- **Username:** `admin`
- **Password:** `admin`

### 3. Generate Agent Key
Inside the portal, go to **Agent API Keys** on the sidebar.
Generate a new Key. Take note of the raw value.

### 4. Start the Agent
In a new terminal window, load the virtual environment and insert your key into `agent.py` or modify the `$AGENT_KEY` environment variable.
```powershell
.venv\Scripts\Activate.ps1
python agent.py
```
You will instantly see Live Telemetry streaming into the WebSockets Dashboard!


## 🐳 Quick Start (Docker - Enterprise)
For a heavy production setup featuring PostgreSQL and Redis integration:

```bash
# Launch the full enterprise stack
docker-compose up -d --build
```
This provisions:
- `db`: PostgreSQL Database
- `redis`: Redis Queue Layer
- `web`: The Flask+SocketIO Core Application Server
- `nginx`: Reverse Proxy Load Balancer handling websockets

Your application is now externally accessible on Port `80`.

## 🛠 Features

- **Live Dashboard**: See CPU, RAM, and Disk update in real time globally.
- **Remote Execution**: Administrators can query the `/api/v2/commands` API to tell distributed systems to run tasks. Agents fetch and return standard output reliably.
- **Alert Engine**: Triggers dynamically whenever critical thresholds are crossed (`> 90% CPU`, etc), managing deductive caching and auto-resolution natively.

---
