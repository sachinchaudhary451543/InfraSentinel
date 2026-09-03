import requests, json
s = requests.Session()
s.post("http://localhost:3000/login", data={"username": "admin", "password": "admin"})
r = s.get("http://localhost:3000/api/v2/licenses/overview")
d = r.json()
print("=== LICENSE DASHBOARD DATA ===")
print(f"Total Licenses: {d['summary']['total_licenses']}")
print(f"Assigned: {d['summary']['assigned_licenses']}")
print(f"Available: {d['summary']['available_licenses']}")
print(f"\n--- Top License SKUs ---")
for l in d.get("licenses", [])[:15]:
    pct = l.get("utilization", 0)
    print(f"  {l['product_name']}: {l['assigned']}/{l['total']} ({pct}% used)")
