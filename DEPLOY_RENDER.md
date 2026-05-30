# Deploying ServerMonitor to Render (Free Tier)

This repository is fully configured for a 1-click deployment to [Render](https://render.com) using the free tier, which is perfect for temporary deployments (e.g. "till Monday").

## What will be deployed?

The `render.yaml` Blueprint automatically deploys 4 fully managed services:
1. **PostgreSQL Database** (Free Plan - 30 days)
2. **Redis KeyValue Store** (Free Plan)
3. **Main Web Application** (Free Plan)
4. **Admin Portal** (Free Plan)

*Note: The Admin Portal has been updated to seamlessly share the exact same PostgreSQL database with the Main Web Application when deployed on Render.*

## 🚀 1-Click Deployment Steps

1. **Commit these changes** to your GitHub repository (`sachinchaudhary451543/InfraSentinel`).
   ```bash
   git add render.yaml admin_portal/app.py DEPLOY_RENDER.md
   git commit -m "Add Render deployment blueprint"
   git push origin main
   ```

2. **Log into Render**: Go to [dashboard.render.com](https://dashboard.render.com).

3. **Deploy the Blueprint**:
   - Click the **New +** button in the top right.
   - Select **Blueprint** from the dropdown menu.
   - Connect your GitHub account (if not already connected) and select the `InfraSentinel` repository.
   - Render will automatically detect the `render.yaml` file.
   - Click **Apply** or **Deploy**.

4. **Wait for deployment**:
   - Render will provision the Database and Redis instance first.
   - Then it will build the Docker containers for the Web App and Admin Portal.
   - Once all services turn **Green (Live)**, your deployment is ready!

## 🔐 First-Time Login

When the deployment finishes, you can access your two portals using the Render-provided `.onrender.com` URLs:

1. **Admin Portal**: Open the URL for `servermonitor-admin`.
   - The database automatically initializes on startup.
   - **Default Login**: Username: `admin` / Password: `admin`
   - *Important: Change this password immediately after logging in!*

2. **Main Dashboard**: Open the URL for `servermonitor-web`.
   - Log in using the same `admin` credentials.

## ⚠️ Important Free Tier Limitations
- The **Free PostgreSQL Database** will automatically expire and be deleted after **30 days**. This is perfect for your "till Monday" use case, but not suitable for long-term production storage without an upgrade.
- Free web services **spin down** after 15 minutes of inactivity and take about 30-60 seconds to spin back up on the next request.
