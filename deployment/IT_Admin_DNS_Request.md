# ServerMonitor Platform - DNS Configuration Request

**To:** IT Administration / Infrastructure Team
**Subject:** Request for Internal DNS "A Record" for ServerMonitor Dashboard

Hello Team,

We are deploying a new internal ServerMonitor platform and need a friendly internal domain name routed to the dashboard server so that our endpoint VMs can securely communicate with it without hardcoding IP addresses. 

Could you please create a new DNS "A Record" in the Windows DNS Manager? 

### Requested Details:
* **Record Type:** Host (A)
* **Requested Host Name:** `monitor` *(This will make the FQDN monitor.yourdomain.local)*
* **Target IP Address:** `[INSERT_DASHBOARD_SERVER_IP_HERE]`

---

### Step-by-Step Instructions (Windows DNS Manager):
If helpful, here are the steps to add this record via the Windows Server DNS interface:

1. Open the **Start Menu** on the DNS Server, type `dnsmgmt.msc`, and press Enter to open the **DNS Manager**.
2. In the left-hand navigation pane, expand the server name, and then expand **Forward Lookup Zones**.
3. Click on our organization's primary local domain name.
4. Right-click in the empty white space in the main (right) panel and select **New Host (A or AAAA)...**
5. In the **Name** box, type `monitor` (or your chosen prefix).
6. In the **IP address** box, type the Target IP Address provided above.
7. Click **Add Host**, then click **Done**.

### Verification:
Once completed, we should be able to ping `monitor` from any domain-joined computer and see it successfully resolve to the target IP address.

Please let me know once this is completed or if you need any additional details.

Thank you!
