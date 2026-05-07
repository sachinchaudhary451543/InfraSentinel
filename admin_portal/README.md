# Multi-Tenant Admin Portal for ServerMonitor

This is a Flask-based admin portal for managing multiple clients (tenants), their servers, VMs, and metrics. Each client has their own secure admin login and dashboard. Super-admins can manage all clients.

## Features

- Multi-tenant login (client and super-admin)
- Dashboard: view servers, VMs, metrics per client
- User management
- Secure API for agent registration
- Modern UI (Flask + Bootstrap)

## Setup

1. Install requirements: `pip install -r requirements.txt`
2. Run: `python app.py`

## Note

- This is a scaffold. Add your own authentication, database, and SharePoint integration as needed.
