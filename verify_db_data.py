#!/usr/bin/env python3
"""
verify_db_data.py - Data Persistence Verification
===================================================
Checks if agent data is being stored correctly in the database
"""

import sqlite3
from datetime import datetime, timedelta
import sys

def main():
    db_path = "admin_portal/admin_portal.db"
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        print("\n" + "="*70)
        print("  DATABASE DATA VERIFICATION REPORT")
        print("="*70)
        
        # 1. Check servers
        print("\n📋 SERVER INVENTORY:")
        print("-" * 70)
        c.execute("SELECT id, hostname, ip, status, last_seen FROM server ORDER BY hostname")
        servers = c.fetchall()
        
        if not servers:
            print("❌ No servers registered yet")
        else:
            for s in servers:
                print(f"  {s['hostname']:30} {s['ip']:15} {s['status']:10} {s['last_seen']}")
        
        # 2. Check metrics
        print("\n📊 METRICS STATISTICS:")
        print("-" * 70)
        
        c.execute("SELECT COUNT(*) as total FROM metric")
        total_metrics = c.fetchone()['total']
        
        c.execute("""
            SELECT COUNT(*) as last_hour FROM metric 
            WHERE timestamp > datetime('now', '-1 hour')
        """)
        last_hour = c.fetchone()['last_hour']
        
        c.execute("""
            SELECT COUNT(*) as last_24h FROM metric 
            WHERE timestamp > datetime('now', '-24 hours')
        """)
        last_24h = c.fetchone()['last_24h']
        
        print(f"  Total metrics stored:        {total_metrics:>10}")
        print(f"  Metrics last 1 hour:         {last_hour:>10}")
        print(f"  Metrics last 24 hours:       {last_24h:>10}")
        
        # 3. Metrics per server
        print("\n📈 METRICS BY SERVER:")
        print("-" * 70)
        
        c.execute("""
            SELECT 
                s.hostname,
                COUNT(m.id) as metric_count,
                MAX(m.timestamp) as last_metric,
                AVG(m.cpu_util_percent) as avg_cpu,
                AVG(m.ram_util_percent) as avg_ram
            FROM server s
            LEFT JOIN metric m ON s.id = m.server_id
            GROUP BY s.id
            ORDER BY metric_count DESC
        """)
        
        for row in c.fetchall():
            hostname = row['hostname']
            count = row['metric_count'] or 0
            last = row['last_metric']
            cpu = row['avg_cpu'] or 0
            ram = row['avg_ram'] or 0
            
            print(f"  {hostname:25} {count:>6} metrics | CPU: {cpu:>5.1f}% RAM: {ram:>5.1f}% | Last: {last}")
        
        # 4. Check VMs
        print("\n🖥️  VIRTUAL MACHINES:")
        print("-" * 70)
        
        c.execute("""
            SELECT 
                s.hostname as host_name,
                COUNT(v.id) as vm_count
            FROM server s
            LEFT JOIN vm v ON s.id = v.server_id
            GROUP BY s.id
            HAVING COUNT(v.id) > 0
            ORDER BY vm_count DESC
        """)
        
        vms = c.fetchall()
        if not vms:
            print("  No VMs registered")
        else:
            for row in vms:
                print(f"  {row['host_name']:30} {row['vm_count']:>3} VMs")
        
        # 5. Check screenshots
        print("\n📸 SCREENSHOTS:")
        print("-" * 70)
        
        c.execute("SELECT COUNT(*) as total FROM screenshot")
        ss_count = c.fetchone()['total']
        
        c.execute("""
            SELECT COUNT(*) as last_24h FROM screenshot 
            WHERE timestamp > datetime('now', '-24 hours')
        """)
        ss_24h = c.fetchone()['last_24h']
        
        print(f"  Total screenshots:           {ss_count:>10}")
        print(f"  Screenshots last 24h:        {ss_24h:>10}")
        
        # 6. Data freshness
        print("\n⏱️  DATA FRESHNESS:")
        print("-" * 70)
        
        c.execute("SELECT MAX(last_seen) as newest FROM server")
        newest_server = c.fetchone()['newest']
        
        c.execute("SELECT MAX(timestamp) as newest FROM metric")
        newest_metric = c.fetchone()['newest']
        
        print(f"  Newest server update:  {newest_server}")
        print(f"  Newest metric entry:   {newest_metric}")
        
        # 7. Summary
        print("\n" + "="*70)
        print("  SUMMARY")
        print("="*70)
        
        if last_24h > 0:
            print("✅ Data is being collected and stored successfully!")
            print(f"   Current metrics rate: ~{last_24h / 24:.1f} metrics/hour")
        elif total_metrics > 0:
            print("⚠️  Data was collected in the past but nothing recent")
            print("   Check if agent is running")
        else:
            print("❌ No data found in database")
            print("   Ensure agent is running and configured properly")
        
        print("="*70 + "\n")
        
        conn.close()
        return 0
    
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
