# InfraMonitor Platform: External Access Architecture Proposal

## Executive Summary

As part of the deployment of the InfraMonitor platform on our internal Hyper-V infrastructure, we require a strategy to make the central dashboard securely accessible from outside the corporate network. This will allow remote administrators to monitor infrastructure, and allow roaming endpoint agents (e.g., laptops operating outside the corporate Wi-Fi) to report their telemetry back to the central server.

Below are the two proposed architectural models for management review and approval, including the exact implementation steps required by the IT team for each.

---

## Option A: Traditional Hardware NAT & Reverse Proxy

This is the legacy enterprise approach. It involves exposing our internal Hyper-V VM to the public internet by modifying our corporate edge firewall/router to allow inbound connections.

### Architecture Flow:

`Remote Agent -> Public Static IP -> Hardware Firewall (NAT) -> Internal Hyper-V VM (IIS Reverse Proxy) -> InfraMonitor App`

### Implementation Steps:

1. **Allocate Public IP:** IT must reserve or identify an unused Static Public IP address from our Internet Service Provider (ISP).
2. **Configure Public DNS:** Log into your public domain registrar (e.g., GoDaddy, Azure DNS) and create an `A Record` for `monitor.example.com`, pointing to the reserved Public IP.
3. **Modify Edge Firewall (Network Risk):** Log into the corporate hardware firewall (e.g., Cisco, FortiGate, SonicWall).
   - Create a NAT (Network Address Translation) rule forwarding inbound traffic on Ports `80` (HTTP) and `443` (HTTPS) to the internal IP address of the Hyper-V VM.
   - Create an inbound security policy (ACL) explicitly allowing this traffic from the open internet.
4. **Install IIS Reverse Proxy:** On the Hyper-V VM, install the **IIS Web Server** role, along with the **Application Request Routing (ARR)** and **URL Rewrite** modules.
5. **Configure IIS Routing:** Set up an IIS Reverse Proxy rule to capture inbound Port 443 traffic and route it internally to `127.0.0.1:8080` (where the InfraMonitor Waitress app is running).
6. **Provision SSL Certificates:** Download and run a tool like Win-ACME (Let's Encrypt) on the Hyper-V VM to generate a free SSL certificate, and manually bind it to the IIS site. _Note: IT will be responsible for ensuring this certificate renews successfully every 90 days._

### Pros & Cons

- **Pros:** Standardized legacy IT approach; full traffic control remains on our hardware router.
- **Cons:** **High Security Risk.** Opening inbound firewall ports exposes our internal network to automated public internet scanners and DDoS attacks. It also requires significant IT overhead to configure, maintain SSL certificates, and monitor firewall logs.

---

## Option B: Zero-Trust Secure Tunnel (Recommended)

This is the modern, cloud-native approach used by modern enterprises. It utilizes a secure tunnel (e.g., Cloudflare Zero Trust) to expose the application to the internet **without opening any inbound firewall ports**.

### Architecture Flow:

`Remote Agent -> Cloudflare Edge Network -> Secure Encrypted Tunnel -> Internal Hyper-V VM -> InfraMonitor App`

### Implementation Steps:

1. **Cloudflare Setup:** Add your organization domain to a Cloudflare account (if not already present).
2. **Create the Tunnel:** Log into the Cloudflare Zero Trust dashboard, navigate to Networks -> Tunnels, and create a new tunnel named `InfraMonitor`.
3. **Install the Daemon (No Firewall Changes):** Cloudflare will provide a single installation command. Run this command on the internal Hyper-V VM:
   ```cmd
   cloudflared.exe service install [UNIQUE_TOKEN]
   ```
   _This creates a background Windows Service that establishes a secure, outbound-only connection to Cloudflare. Because it is outbound, it completely bypasses the need to modify the corporate firewall._
4. **Route the Traffic:** In the Cloudflare dashboard, add a "Public Hostname" route that tells Cloudflare: "When someone visits `monitor.example.com`, route the traffic through the tunnel to `http://localhost:8080`".
5. **Automatic SSL:** Done. Cloudflare automatically provisions, attaches, and endlessly auto-renews the SSL certificates on their edge network.

### Pros & Cons

- **Pros:** **Maximum Security.** Zero inbound firewall ports are opened. The Hyper-V VM remains completely invisible to internet scanners. Built-in DDoS protection. SSL certificates are managed automatically for free. Implementation takes less than 15 minutes.
- **Cons:** Traffic routes through a third-party edge provider (Cloudflare) before hitting our internal network.

---

## Recommendation

We strongly recommend **Option B (Zero-Trust Secure Tunnel)**. It significantly reduces the attack surface of our corporate network by keeping all inbound firewall ports strictly closed. It also eliminates the administrative burden of manually renewing SSL certificates and modifying edge router configurations, while achieving a faster time-to-deployment.

Please review the proposed options and provide approval on the preferred architecture so we can proceed with the production rollout.
