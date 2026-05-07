# ServerMonitor Deployment Steps

This folder contains the files needed to deploy the ServerMonitor platform into your production organization. 
These steps are designed to be secure and scalable.

## 1. Setting up the Production Web Server (`run_waitress.py`)

Do not run the application using `flask run` or `python web/app.py` in production, as the built-in Flask development server is not designed to handle concurrent load or production traffic securely.

1. Ensure the `waitress` package is installed:
   ```cmd
   pip install waitress
   ```
2. Run the application using the included runner:
   ```cmd
   python deployment/run_waitress.py
   ```
   *This starts the server on port `8080` with multiple threads, capable of handling hundreds of concurrent agents.*
3. **Important:** Create a Windows Task Scheduler task to run this script on boot (Run whether user is logged on or not).

## 2. Setting up IIS as a Reverse Proxy (Recommended)

To provide SSL (HTTPS) and serve the app on port 443, you should place Waitress behind IIS.

1. Open **Server Manager** and install the **Web Server (IIS)** role.
2. Download and install [URL Rewrite Module 2.1](https://www.iis.net/downloads/microsoft/url-rewrite) and [Application Request Routing (ARR) 3.0](https://www.iis.net/downloads/microsoft/application-request-routing).
3. In IIS Manager, click on the server node and open **Application Request Routing Cache**. Click **Server Proxy Settings** and check **Enable proxy**.
4. Select your Website (e.g., Default Web Site).
5. Open **URL Rewrite** and click **Add Rule(s)** -> **Reverse Proxy**.
6. Enter `127.0.0.1:8080` as the destination server.
7. Bind your SSL certificate to port 443 on the site.

## 3. Deploying Agents via GPO (`agent_install_gpo.ps1`)

For large organizations, Active Directory Group Policy is the most reliable way to push the agent.

1. Review `deployment/agent_install_gpo.ps1`.
2. Update the `$DeployShare` variable to point to a network share containing `agent.py` and `nssm.exe` (The Non-Sucking Service Manager).
3. Update `$ApiUrl` to your production URL.
4. **Security Note:** Replace `YOUR_TENANT_AGENT_KEY` with your actual key in your private deployment environment. **DO NOT commit the key to GitHub or source control.**
5. Link the GPO to your desired Organizational Units (OUs) under `Computer Configuration -> Policies -> Windows Settings -> Scripts -> Startup`.

## 4. Environment Variables (.env)

Ensure you create a `.env` file in the root directory containing your sensitive configuration:

```env
SECRET_KEY=generate-a-secure-random-string-here
PORT=8080
FLASK_ENV=production
# Add SharePoint and Azure client secrets here
```
*(Do not share or commit the `.env` file).*
