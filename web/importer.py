import os
import csv
import logging
from datetime import datetime
from web.app import app, db
from web.models import Server, Metric, VM

def init_db():
    with app.app_context():
        db.create_all()

def to_float(s):
    if s is None:
        return None
    s = str(s).strip().replace('"', '').replace(',', '')
    if s == "":
        return None
    for u in ["GB", "TB", "%"]:
        s = s.replace(u, "")
    try:
        return float(s)
    except Exception:
        return None

def import_csv_to_sqlite(csv_path, tenant_id=None):
    if not os.path.exists(csv_path):
        logging.info(f"CSV not found: {csv_path}")
        return False
        
    if tenant_id is None:
        logging.error("Multi-tenant error: tenant_id is required for import.")
        return False
        
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return False

        inserted = 0
        with app.app_context():
            # Standardized: tenant_id passed from orchestrator
            for raw in rows:
                # normalize keys
                row = {}
                for k, v in raw.items():
                    if k is not None:
                        nk = k.lstrip('\ufeff').strip().replace('"', '')
                        row[nk] = (v.strip() if isinstance(v, str) else v)

                timestamp_str = row.get("Timestamp") or row.get("Date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except:
                    ts = datetime.now()

                hostname = row.get("Hostname") or row.get("Server") or "Unknown"
                
                # Find or create server within tenant boundary
                server = Server.query.filter_by(hostname=hostname, tenant_id=tenant_id).first()
                if not server:
                    server = Server()
                    server.hostname = hostname
                    server.tenant_id = tenant_id
                    server.status = "online"
                    server.last_seen = datetime.utcnow()
                    db.session.add(server)
                    db.session.commit()
                else:
                    server.status = "online"
                    server.last_seen = datetime.utcnow()

                # Classification Logic
                is_hyperv = int(row.get("IsHyperV_Enabled") or 0) == 1
                if is_hyperv:
                    server.is_hyperv_host = True
                    server.server_type = "Host"
                elif not server.server_type:
                    server.server_type = "Infrastructure"

                vc = row.get("VirtualCores") or row.get("Virtual Cores")
                virtual_cores = int(str(vc)) if vc not in (None, "") else None

                cpu_util = to_float(row.get("CPU_Util_Percent") or row.get("CPU Util (%)"))
                total_ram_gb = to_float(row.get("TotalRAM_GB") or row.get("Total RAM"))
                avail_ram_gb = to_float(row.get("AvailableRAM_GB") or row.get("Available RAM"))
                used_ram_gb = to_float(row.get("UsedRAM_GB") or row.get("Used RAM"))
                ram_util = to_float(row.get("RAMUtil_Percent") or row.get("RAM Util (%)"))
                total_ssd_gb = to_float(row.get("TotalSSD_GB") or row.get("Total SSD"))
                avail_ssd_gb = to_float(row.get("AvailableSSD_GB") or row.get("Available SSD"))
                used_ssd_gb = to_float(row.get("UsedSSD_GB") or row.get("Used SSD"))
                ssd_util = to_float(row.get("SSDUtil_Percent") or row.get("SSD Util (%)"))

                metric = Metric()
                metric.server_id = server.id
                metric.timestamp = ts
                metric.virtual_cores = virtual_cores
                metric.cpu_util_percent = cpu_util
                metric.total_ram_gb = total_ram_gb
                metric.available_ram_gb = avail_ram_gb
                metric.used_ram_gb = used_ram_gb
                metric.ram_util_percent = ram_util
                metric.total_ssd_gb = total_ssd_gb
                metric.available_ssd_gb = avail_ssd_gb
                metric.used_ssd_gb = used_ssd_gb
                metric.ssd_util_percent = ssd_util
                metric.drive_letters_checked = row.get("DriveLettersChecked", "")
                metric.drives_details = row.get("Drives_Details", "")
                metric.error = row.get("Error", "")
                db.session.add(metric)
                inserted += 1

            db.session.commit()
            logging.info(f"Imported {inserted} metric rows into central.db")
            return inserted > 0
    except Exception as e:
        logging.error(f"Import metrics failed: {e}")
        return False

def import_vm_csv_to_sqlite(csv_path, host_info, tenant_id=None):
    if not os.path.exists(csv_path):
        return False

    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        inserted = 0

        if tenant_id is None:
            logging.error("Multi-tenant error: tenant_id is required for VM import.")
            return False

        with app.app_context():
            for _, row in df.iterrows():
                vm_name = row.get('VMName') or row.get('Name')
                if not vm_name or pd.isna(vm_name):
                    continue
                
                host_name = str(row.get('Hostname', '')) if not pd.isna(row.get('Hostname')) else host_info.get('hostname', '')
                
                # Find or create server host within tenant boundary
                server = Server.query.filter_by(hostname=host_name, tenant_id=tenant_id).first()
                if not server:
                    server = Server()
                    server.hostname = host_name
                    server.tenant_id = tenant_id
                    server.ip = host_info.get('ip')
                    server.os_info = host_info.get('os')
                    server.status = "online"
                    server.last_seen = datetime.utcnow()
                    server.is_hyperv_host = True
                    server.server_type = "Host"
                    db.session.add(server)
                    db.session.commit()
                else:
                    server.status = "online"
                    server.last_seen = datetime.utcnow()
                    server.is_hyperv_host = True
                    server.server_type = "Host"

                # Upsert VM logic
                vm = VM.query.filter_by(server_id=server.id, vm_name=str(vm_name)).first()
                if not vm:
                    vm = VM()
                    vm.tenant_id = tenant_id
                    vm.server_id = server.id
                    vm.vm_name = str(vm_name)
                    db.session.add(vm)

                vm.state = str(row.get('State', '')) if not pd.isna(row.get('State')) else ""
                vm.cpu_usage = float(row.get('CPUUsage', 0)) if not pd.isna(row.get('CPUUsage')) else 0.0
                vm.memory_assigned = float(row.get('MemoryAssigned', 0)) if not pd.isna(row.get('MemoryAssigned')) else 0.0
                vm.uptime = str(row.get('Uptime', '')) if not pd.isna(row.get('Uptime')) else ""
                vm.path = str(row.get('Path', '')) if not pd.isna(row.get('Path')) else ""

                inserted += 1
            
            db.session.commit()
            logging.info(f"Imported {inserted} VMs into central.db")
            return inserted > 0
    except Exception as e:
        logging.error(f"Import VM failed: {e}")
        return False
