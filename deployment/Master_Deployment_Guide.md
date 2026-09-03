# InfraMonitor: Master Deployment Guide

This document outlines the complete, start-to-end process for deploying the InfraMonitor platform across your organization's Hyper-V infrastructure and endpoint devices.

---

## Phase 1: Central Server Preparation

The first step is setting up the "Brain" of the platform—the central dashboard server.

1. **Provision the VM:** Spin up a new Windows Server VM inside your Hyper-V environment (e.g., Windows Server 2019/2022).
2. **Assign a Static IP:** Ensure this VM has a permanent, internal static IP address on your network (e.g., `192.168.10.50`).
3. **Install Prerequisites:**
   - Install **Python 3.10+** on this VM. _(During installation, ensure the "Add Python to PATH" checkbox is checked)._
4. **Copy the Codebase:** Copy the entire `InfraMonitor` project folder to a permanent location on this VM (e.g., `C:\InfraMonitor`).

---

## Phase 2: Initializing the Dashboard Server

We must start the web application using a production-grade server (`Waitress`), rather than the default Flask development server.

1. Open the `deployment` folder inside your `InfraMonitor` directory.
2. Double-click the **`Start_Dashboard_Server.bat`** file.
   - _This script will automatically create a virtual environment, install all required dependencies (including Waitress), and launch the server on Port 8080._
3. Ensure the black console window remains open. Your dashboard is now locally active.

---

## Phase 3: Configuring Network & Public Access

For your endpoint agents to communicate with the dashboard, the server must be accessible over the network.

### Step 3.1: Windows Firewall

On the central Hyper-V VM, open **Windows Defender Firewall**, go to **Advanced Settings -> Inbound Rules**, and create a new rule allowing **TCP Port 8080**.

### Step 3.2: Choose Your Access Strategy

Choose **one** of the following strategies based on your management's approval:

#### Strategy A: Internal Access Only (Office Network)

If the platform will only be used inside the office:

- Submit the `IT_Admin_DNS_Request.md` file to your IT team.
- They will create an internal DNS record (e.g., `monitor.example.local`) pointing to the VM's static IP.

#### Strategy B: External Access (Cloudflare Tunnel - Recommended)

If laptops working from home need to report telemetry:

1. Create a free Cloudflare account and add your domain.
2. Go to **Zero Trust -> Networks -> Tunnels** and create a tunnel.
3. Run the provided `cloudflared.exe` installation command on your Hyper-V VM.
4. Route `monitor.example.com` to `http://localhost:8080`.
   _(This safely exposes the dashboard to the internet without opening corporate firewall ports)._

#### Strategy C: External Access (Hardware Firewall & IIS)

If management mandates traditional hardware routing:

1. IT must assign a Public IP and point `monitor.example.com` to it via public DNS.
2. IT must modify the physical edge firewall to Port Forward ports 80/443 to your Hyper-V VM.
3. Install IIS on the Hyper-V VM and configure a Reverse Proxy rule to forward incoming traffic to `localhost:8080`.

---

## Phase 4: Platform Configuration

Now that the dashboard is accessible via your chosen URL (e.g., `http://monitor.example.local:8080` or `https://monitor.example.com`):

1. **Log In:** Access the URL in your web browser. Log in using the default Super Admin credentials (or create them if prompted).
2. **Configure Tenant:** Go to the Admin Panel and set up your organization's Tenant profile (add your company name and logo).
3. **Generate Keys:** Navigate to **Agent Keys** and generate a Master Key. Copy this secret key—you will need it for Phase 5.

---

## Phase 5: Agent Rollout (The "Eyes")

Finally, you must deploy the tracking agent to the endpoints (VMs/Laptops) you wish to monitor.

### Testing on a Single VM

1. Copy `agent.py` and `deployment/Start_Agent.bat` to a target VM.
2. Right-click `Start_Agent.bat` -> Edit.
3. Replace `DASHBOARD_IP` with your URL (e.g., `monitor.example.com`).
4. Replace `AGENT_API_KEY` with the secret key you generated in Phase 4.
5. Save and double-click the script. The VM will immediately appear on your dashboard.

### Mass Organization Rollout (Group Policy)

For deploying to hundreds of machines simultaneously:

1. Open `deployment/agent_install_gpo.ps1`.
2. Update the `$ApiUrl` and `$ApiKey` variables inside the script.
3. Place the script, `agent.py`, and `nssm.exe` on a secure network share (e.g., `\\Server\Deploy$`).
4. Link this script as a Startup Script via Windows Active Directory Group Policy (GPO) to your target Organizational Units (OUs).
5. As computers restart, they will automatically install Python, register the agent as a resilient background Windows Service, and begin reporting.

---

**Deployment Complete!** You can now monitor live telemetry, capture screenshots, and track productivity across your entire organization.
