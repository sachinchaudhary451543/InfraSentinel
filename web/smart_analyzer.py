# web/smart_analyzer.py
import os, io, uuid
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, send_file, redirect, url_for, flash
import sqlite3
import base64
from functools import wraps

# ✅ Define blueprint (no route decorator errors)
smart_analyzer = Blueprint("smart_analyzer", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_META_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_META_DIR, exist_ok=True)

# Add these constants
METRICS_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ServerMetrics.db")
METRICS_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ServerMetrics_All.csv")

# ---------------- Utility Functions ----------------
def safe_save_df(df):
    """Save DataFrame using pickle (requires pandas)."""
    uid = str(uuid.uuid4())
    path = os.path.join(UPLOAD_META_DIR, f"{uid}.pkl")
    df.to_pickle(path)  # to_pickle is from pandas.io.api
    return uid, path

def read_uploaded_file(path):
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    elif ext in [".xls", ".xlsx"]:
        return pd.read_excel(path)
    raise ValueError("Unsupported file type")

def detect_types_simple(df):
    import pandas as pd
    datetime_cols, numeric_cols, categorical_cols, text_cols = [], [], [], []
    for col in df.columns:
        ser = df[col]
        if pd.api.types.is_datetime64_any_dtype(ser):
            datetime_cols.append(col)
            continue
        try:
            sample = ser.dropna().astype(str).head(50)
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().sum() > 0.5 * len(sample):
                datetime_cols.append(col)
                continue
        except Exception:
            pass
        if pd.api.types.is_numeric_dtype(ser):
            numeric_cols.append(col)
        elif ser.nunique(dropna=True) / max(1, len(ser)) < 0.05:
            categorical_cols.append(col)
        else:
            text_cols.append(col)
    return {
        "datetime": datetime_cols,
        "numeric": numeric_cols,
        "categorical": categorical_cols,
        "text": text_cols,
    }

def recommend_charts_simple(types):
    recs = []
    dt, num, cat = types["datetime"], types["numeric"], types["categorical"]
    if dt and num:
        recs.append({
            "type": "line_time",
            "x": dt[0],
            "ys": num[:3],
            "title": f"Trend of {', '.join(num[:3])}"
        })
    for n in num[:4]:
        recs.append({"type": "hist", "col": n, "title": f"Distribution of {n}"})
    for c in cat[:3]:
        recs.append({"type": "bar_count", "col": c, "title": f"Counts of {c}"})
    if len(num) >= 2:
        recs.append({"type": "scatter", "x": num[0], "y": num[1], "title": f"{num[0]} vs {num[1]}"})
    return recs

# ---------------- Upload and Analysis ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@smart_analyzer.route("/")
@login_required
def analyzer_home():
    from flask_login import current_user
    if not current_user.is_authenticated:
        flash("Please log in first.", "warning")
        return redirect(url_for("auth.login"))
    return render_template("smart_analyzer.html")

def _to_float(s):
    if s is None: 
        return None
    s = str(s).strip().replace('"','').replace(',', '')
    if s == "":
        return None
    for u in ["GB","TB","%"]:
        s = s.replace(u, "")
    try:
        return float(s)
    except:
        return None

def _parse_int(v):
    try:
        if v is None or str(v).strip() == "":
            return None
        return int(float(str(v)))
    except:
        return None

def _parse_timestamp(v):
    import pandas as pd
    try:
        if pd.isna(v):
            return None
        if isinstance(v, str):
            # try common formats
            v2 = v.replace(".", ":") if v.count(":") == 0 and v.count(".") >= 1 else v
            return pd.to_datetime(v2, errors="coerce")
        return pd.to_datetime(v, errors="coerce")
    except:
        return None

def insert_df_into_db(df, db_path):
    """
    Normalize columns and insert rows into metrics table.
    Returns number of rows inserted.
    """
    import pandas as pd
    if df is None or df.shape[0] == 0:
        return 0

    # normalize column names
    cols = {c.strip(): c.strip() for c in df.columns}
    norm = {k.lower().replace(" ", "").replace("(", "").replace(")", "").replace("%",""): k for k in cols}

    def get_col(*candidates):
        for c in candidates:
            key = c.lower().replace(" ", "").replace("(", "").replace(")", "").replace("%","")
            if key in norm:
                return norm[key]
        return None

    ts_col = get_col("Timestamp", "Date", "Time", "datetime")
    host_col = get_col("Hostname", "Server", "Host")
    vc_col = get_col("VirtualCores", "Virtual Cores", "Cores")
    cpu_col = get_col("CPU_Util_Percent", "CPU Util (%)", "CPU")
    total_ram_col = get_col("TotalRAM_GB", "Total RAM (GB)", "TotalRAM")
    avail_ram_col = get_col("AvailableRAM_GB", "Available RAM (GB)", "AvailableRAM")
    used_ram_col = get_col("UsedRAM_GB", "Used RAM (GB)", "UsedRAM")
    ramutil_col = get_col("RAMUtil_Percent", "RAM Util (%)", "RAMUtil")
    total_ssd_col = get_col("TotalSSD_GB", "Total SSD (GB)", "TotalSSD")
    avail_ssd_col = get_col("AvailableSSD_GB", "Available SSD (GB)", "AvailableSSD")
    used_ssd_col = get_col("UsedSSD_GB", "Used SSD (GB)", "UsedSSD")
    total_ssd_tb_col = get_col("TotalSSD_TB", "Total SSD (TB)")
    avail_ssd_tb_col = get_col("AvailableSSD_TB", "Available SSD (TB)")
    used_ssd_tb_col = get_col("UsedSSD_TB", "Used SSD (TB)")
    ssdutil_col = get_col("SSDUtil_Percent", "SSD Util (%)", "SSDUtil")
    drives_checked_col = get_col("DriveLettersChecked", "DriveLettersChecked", "DriveLetters")
    drives_details_col = get_col("Drives_Details", "Drives Details", "Drives_Details")
    error_col = get_col("Error", "Errors")

    rows_to_insert = []
    for _, r in df.iterrows():
        ts = _parse_timestamp(r.get(ts_col)) if ts_col else None
        ts_txt = ts.strftime("%Y-%m-%d %H:%M:%S") if (ts is not None and not pd.isna(ts)) else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hostname = (r.get(host_col) or r.get("Hostname") or r.get("Server") or "")
        virtual_cores = _parse_int(r.get(vc_col))
        cpu_util = _to_float(r.get(cpu_col))
        total_ram_gb = _to_float(r.get(total_ram_col))
        avail_ram_gb = _to_float(r.get(avail_ram_col))
        used_ram_gb = _to_float(r.get(used_ram_col))
        ram_util = _to_float(r.get(ramutil_col))
        total_ssd_gb = _to_float(r.get(total_ssd_col))
        avail_ssd_gb = _to_float(r.get(avail_ssd_col))
        used_ssd_gb = _to_float(r.get(used_ssd_col))
        total_ssd_tb = _to_float(r.get(total_ssd_tb_col)) or (total_ssd_gb / 1024 if total_ssd_gb else None)
        avail_ssd_tb = _to_float(r.get(avail_ssd_tb_col)) or (avail_ssd_gb / 1024 if avail_ssd_gb else None)
        used_ssd_tb = _to_float(r.get(used_ssd_tb_col)) or (used_ssd_gb / 1024 if used_ssd_gb else None)
        ssd_util = _to_float(r.get(ssdutil_col))
        drives_checked = r.get(drives_checked_col) if drives_checked_col else ""
        drives_details = r.get(drives_details_col) if drives_details_col else ""
        error = r.get(error_col) if error_col else ""

        rows_to_insert.append((
            ts_txt, str(hostname), virtual_cores, cpu_util, total_ram_gb, avail_ram_gb, used_ram_gb, ram_util,
            total_ssd_gb, avail_ssd_gb, used_ssd_gb, total_ssd_tb, avail_ssd_tb, used_ssd_tb, ssd_util,
            str(drives_checked), str(drives_details), str(error)
        ))

    conn = sqlite3.connect(METRICS_DB)
    cur = conn.cursor()
    inserted = 0
    try:
        cur.executemany("""
            INSERT INTO metrics (
                Timestamp, Hostname, VirtualCores, CPU_Util_Percent, TotalRAM_GB, AvailableRAM_GB, UsedRAM_GB, RAMUtil_Percent,
                TotalSSD_GB, AvailableSSD_GB, UsedSSD_GB, TotalSSD_TB, AvailableSSD_TB, UsedSSD_TB, SSDUtil_Percent,
                DriveLettersChecked, Drives_Details, Error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows_to_insert)
        inserted = cur.rowcount if cur.rowcount is not None else len(rows_to_insert)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return inserted

# Initialize DB if not exists
def init_metrics_db():
    """Create metrics table if it doesn't exist."""
    os.makedirs(os.path.dirname(METRICS_DB), exist_ok=True)
    conn = sqlite3.connect(METRICS_DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Timestamp TEXT,
        Hostname TEXT,
        VirtualCores INTEGER,
        CPU_Util_Percent REAL,
        TotalRAM_GB REAL,
        AvailableRAM_GB REAL,
        UsedRAM_GB REAL,
        RAMUtil_Percent REAL,
        TotalSSD_GB REAL,
        AvailableSSD_GB REAL,
        UsedSSD_GB REAL,
        TotalSSD_TB REAL,
        AvailableSSD_TB REAL,
        UsedSSD_TB REAL,
        SSDUtil_Percent REAL,
        DriveLettersChecked TEXT,
        Drives_Details TEXT,
        Error TEXT
    )
    """)
    conn.commit()
    conn.close()

# Call on import
init_metrics_db()

@smart_analyzer.route("/upload-analyze", methods=["POST"])
@login_required
def upload_analyze():
    import pandas as pd
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file uploaded"}), 400

        ext = os.path.splitext(file.filename or "")[1].lower()
        tmp_path = os.path.join(UPLOAD_META_DIR, f"tmp_{uuid.uuid4().hex}{ext}")
        file.save(tmp_path)

        try:
            df = read_uploaded_file(tmp_path)
        except Exception as e:
            os.remove(tmp_path)
            return jsonify({"error": f"Read error: {e}"}), 400

        # normalize column names
        df.columns = [str(c).strip() for c in df.columns]

        # convert obvious datetime columns
        types = detect_types_simple(df)
        for c in types["datetime"]:
            try:
                df[c] = pd.to_datetime(df[c], errors="coerce")
            except Exception:
                pass

        # save preview and persist DataFrame for report generation
        uid, _ = safe_save_df(df)
        os.remove(tmp_path)

        # Insert into metrics DB
        inserted = 0
        try:
            init_metrics_db()  # ensure table exists
            inserted = insert_df_into_db(df, METRICS_DB)
        except Exception as e:
            print(f"DB insert warning: {e}")
            # continue anyway - don't fail the upload if DB insert fails
            pass

        preview = df.head(20).replace({pd.NA: None, pd.NaT: None}).to_dict(orient="records")
        numeric_summary = {
            c: {"count": int(df[c].count()), "mean": float(df[c].mean()) if pd.api.types.is_numeric_dtype(df[c]) else None}
            for c in df.select_dtypes(include=["number"]).columns
        }
        summary = {"rows": int(df.shape[0]), "columns": int(df.shape[1]), "numeric": numeric_summary, "inserted": inserted}

        recs = recommend_charts_simple(types)
        return jsonify({"id": uid, "preview": preview, "types": types, "summary": summary, "recommendations": recs})
    except Exception as e:
        print(f"upload_analyze error: {e}")
        return jsonify({"error": str(e)}), 500

# Add this route for direct server metrics analysis (no upload needed)
@smart_analyzer.route("/analyze-current-metrics", methods=["GET"])
@login_required
def analyze_current_metrics():
    """Analyze existing server metrics from database/CSV without upload."""
    import pandas as pd
    try:
        init_metrics_db()
        # Try loading from SQLite first
        if os.path.exists(METRICS_DB):
            conn = sqlite3.connect(METRICS_DB)
            df = pd.read_sql_query("""
                SELECT Timestamp, Hostname, CPU_Util_Percent, RAMUtil_Percent, SSDUtil_Percent, Error
                FROM metrics ORDER BY Timestamp DESC LIMIT 1000
            """, conn)
            conn.close()
        # Fallback to CSV if DB empty
        elif os.path.exists(METRICS_CSV):
            df = pd.read_csv(METRICS_CSV)
        else:
            return jsonify({"error": "No metrics data available. Upload a file or wait for data collection."}), 404

        if df.empty:
            return jsonify({"error": "No metrics data found in database"}), 404

        types = detect_types_simple(df)
        recs = recommend_charts_simple(types)
        
        stats = {
            "total_records": len(df),
            "columns": len(df.columns)
        }
        
        return jsonify({
            "stats": stats,
            "types": types,
            "recommendations": recs,
            "preview": df.head(10).replace({pd.NA: None, pd.NaT: None}).to_dict(orient="records")
        })
    except Exception as e:
        print(f"analyze_current_metrics error: {e}")
        return jsonify({"error": str(e)}), 500

# ---------------- Report Generation ----------------
@smart_analyzer.route("/generate-report/<uid>", methods=["GET"])
def generate_report_uid(uid):
    import pandas as pd
    import matplotlib.pyplot as plt
    
    pkl = os.path.join(UPLOAD_META_DIR, f"{uid}.pkl")
    if not os.path.exists(pkl):
        return jsonify({"error": "ID not found"}), 404

    df = pd.read_pickle(pkl)
    types = detect_types_simple(df)
    recs = recommend_charts_simple(types)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
        summary_df = pd.DataFrame([{
            "rows": len(df),
            "columns": len(df.columns),
            "missing": int(df.isna().sum().sum())
        }])
        summary_df.to_excel(writer, index=False, sheet_name="Summary")

        workbook = writer.book
        charts_ws = workbook.add_worksheet("Charts") # type: ignore[attr-defined]
        row = 0

        for i, rec in enumerate(recs[:6]):
            try:
                fig, ax = plt.subplots(figsize=(7, 3))
                if rec["type"] == "line_time":
                    for y in rec["ys"]:
                        if y in df.columns:
                            ax.plot(df[rec["x"]], pd.to_numeric(df[y], errors="coerce"), label=y)
                    ax.legend(); ax.set_title(rec["title"])
                elif rec["type"] == "hist":
                    vals = pd.to_numeric(df[rec["col"]], errors="coerce").dropna()
                    ax.hist(vals, bins=30); ax.set_title(rec["title"])
                elif rec["type"] == "bar_count":
                    vc = df[rec["col"]].astype(str).value_counts().head(10)
                    ax.bar(vc.index, vc.values)
                    ax.set_xticklabels(vc.index, rotation=45, ha="right")
                    ax.set_title(rec["title"])
                elif rec["type"] == "scatter":
                    ax.scatter(pd.to_numeric(df[rec["x"]], errors="coerce"),
                               pd.to_numeric(df[rec["y"]], errors="coerce"), alpha=0.6)
                    ax.set_xlabel(rec["x"]); ax.set_ylabel(rec["y"]); ax.set_title(rec["title"])

                buf = io.BytesIO()
                fig.tight_layout()
                fig.savefig(buf, format="png", dpi=150)
                plt.close(fig)
                buf.seek(0)
                charts_ws.insert_image(row, 0, f"chart_{i}.png", {"image_data": buf})
                row += 16
            except Exception:
                print("chart error")
                continue

    output.seek(0)
    filename = f"auto_report_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )

@smart_analyzer.route("/analyze-server-metrics", methods=["GET"])
def analyze_server_metrics():
    import pandas as pd
    import matplotlib.pyplot as plt
    try:
        # Try loading from SQLite first
        if os.path.exists(METRICS_DB):
            conn = sqlite3.connect(METRICS_DB)
            # OPTIMIZATION: Specify exact columns instead of SELECT * to reduce I/O
            df = pd.read_sql_query("""
                SELECT Timestamp, Hostname, CPU_Util_Percent, RAMUtil_Percent, SSDUtil_Percent, Error
                FROM metrics
            """, conn)
            conn.close()
        # Fallback to CSV if DB not found
        elif os.path.exists(METRICS_CSV):
            df = pd.read_csv(METRICS_CSV)
        else:
            return jsonify({"error": "No metrics data found"}), 404

        # Clean and prepare data
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns

        # Basic statistics
        stats = {
            "total_records": len(df),
            "date_range": {
                "start": df['Timestamp'].min().strftime("%Y-%m-%d %H:%M:%S"),
                "end": df['Timestamp'].max().strftime("%Y-%m-%d %H:%M:%S")
            },
            "servers": df['Hostname'].unique().tolist(),
            "metrics": {}
        }

        # Calculate statistics for each numeric metric
        for col in numeric_cols:
            if col in ['id']: continue
            stats["metrics"][col] = {
                "mean": float(df[col].mean()),
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "last": float(df[col].iloc[-1]) if len(df) > 0 else None
            }

        # Generate visualizations
        plots = []
        
        # CPU Utilization over time
        if 'CPU_Util_Percent' in df.columns:
            fig, ax = plt.subplots(figsize=(10, 4))
            for host in df['Hostname'].unique():
                host_data = df[df['Hostname'] == host]
                ax.plot(host_data['Timestamp'], host_data['CPU_Util_Percent'], label=host)
            ax.set_title('CPU Utilization Over Time')
            ax.set_xlabel('Time')
            ax.set_ylabel('CPU Utilization (%)')
            ax.legend()
            plots.append(save_plot_to_base64(fig))
            plt.close(fig)

        # RAM Usage over time
        if 'RAMUtil_Percent' in df.columns:
            fig, ax = plt.subplots(figsize=(10, 4))
            for host in df['Hostname'].unique():
                host_data = df[df['Hostname'] == host]
                ax.plot(host_data['Timestamp'], host_data['RAMUtil_Percent'], label=host)
            ax.set_title('RAM Utilization Over Time')
            ax.set_xlabel('Time')
            ax.set_ylabel('RAM Utilization (%)')
            ax.legend()
            plots.append(save_plot_to_base64(fig))
            plt.close(fig)

        # Storage Usage over time
        if 'SSDUtil_Percent' in df.columns:
            fig, ax = plt.subplots(figsize=(10, 4))
            for host in df['Hostname'].unique():
                host_data = df[df['Hostname'] == host]
                ax.plot(host_data['Timestamp'], host_data['SSDUtil_Percent'], label=host)
            ax.set_title('Storage Utilization Over Time')
            ax.set_xlabel('Time')
            ax.set_ylabel('Storage Utilization (%)')
            ax.legend()
            plots.append(save_plot_to_base64(fig))
            plt.close(fig)

        return jsonify({
            "stats": stats,
            "plots": plots
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def save_plot_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

@smart_analyzer.route("/download-analysis-report", methods=["GET"])
def download_analysis_report():
    import pandas as pd
    import matplotlib.pyplot as plt
    try:
        # Load data
        if os.path.exists(METRICS_DB):
            conn = sqlite3.connect(METRICS_DB)
            # OPTIMIZATION: Specify exact columns instead of SELECT * to reduce I/O
            df = pd.read_sql_query("""
                SELECT Timestamp, Hostname, CPU_Util_Percent, RAMUtil_Percent, SSDUtil_Percent, Error
                FROM metrics
            """, conn)
            conn.close()
        elif os.path.exists(METRICS_CSV):
            df = pd.read_csv(METRICS_CSV)
        else:
            return jsonify({"error": "No metrics data found"}), 404

        if df.empty:
            return jsonify({"error": "No metrics data found"}), 404

        # Ensure Timestamp is datetime
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        else:
            df["Timestamp"] = pd.NaT

        # Summary statistics (guard missing columns)
        def safe_mean(col):
            return float(pd.to_numeric(df[col], errors="coerce").dropna().mean()) if col in df.columns else None

        summary_data = []
        hosts = df['Hostname'].dropna().unique().tolist() if 'Hostname' in df.columns else []
        for host in hosts:
            host_df = df[df.get('Hostname') == host] if 'Hostname' in df.columns else df
            summary_data.append({
                'Hostname': host,
                'Avg CPU Util (%)': safe_mean('CPU_Util_Percent'),
                'Max CPU Util (%)': float(pd.to_numeric(host_df.get('CPU_Util_Percent', pd.Series()), errors="coerce").max()) if 'CPU_Util_Percent' in host_df else None,
                'Avg RAM Util (%)': safe_mean('RAMUtil_Percent'),
                'Max RAM Util (%)': float(pd.to_numeric(host_df.get('RAMUtil_Percent', pd.Series()), errors="coerce").max()) if 'RAMUtil_Percent' in host_df else None,
                'Avg Storage Util (%)': safe_mean('SSDUtil_Percent'),
                'Max Storage Util (%)': float(pd.to_numeric(host_df.get('SSDUtil_Percent', pd.Series()), errors="coerce").max()) if 'SSDUtil_Percent' in host_df else None,
                'Last Updated': host_df['Timestamp'].max() if 'Timestamp' in host_df and not host_df['Timestamp'].isna().all() else None
            })

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Raw data and summary sheets
            df.to_excel(writer, sheet_name='Raw Data', index=False)
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)

            workbook = writer.book
            charts_ws = workbook.add_worksheet('Charts')  # type: ignore[attr-defined]

            row = 0
            # Generate matplotlib plots and insert as images (more robust than xlsxwriter chart ranges)
            def insert_plot(fig, r):
                try:
                    buf = io.BytesIO()
                    fig.tight_layout()
                    fig.savefig(buf, format='png', dpi=150)
                    plt.close(fig)
                    buf.seek(0)
                    charts_ws.insert_image(r, 0, f"plot_{r}.png", {"image_data": buf})
                except Exception as e:
                    print("insert_plot error:", e)

            # CPU over time
            try:
                if 'CPU_Util_Percent' in df.columns and not df['CPU_Util_Percent'].dropna().empty:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    for host in hosts[:10]:
                        host_data = df[df['Hostname'] == host].sort_values('Timestamp')
                        if host_data.empty: continue
                        ax.plot(host_data['Timestamp'], pd.to_numeric(host_data['CPU_Util_Percent'], errors='coerce'), label=str(host))
                    ax.set_title('CPU Utilization Over Time')
                    ax.set_xlabel('Time'); ax.set_ylabel('CPU (%)'); ax.legend(loc='best', fontsize='small')
                    insert_plot(fig, row); row += 16
            except Exception as e:
                print("cpu plot error:", e)

            # RAM over time
            try:
                if 'RAMUtil_Percent' in df.columns and not df['RAMUtil_Percent'].dropna().empty:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    for host in hosts[:10]:
                        host_data = df[df['Hostname'] == host].sort_values('Timestamp')
                        if host_data.empty: continue
                        ax.plot(host_data['Timestamp'], pd.to_numeric(host_data['RAMUtil_Percent'], errors='coerce'), label=str(host))
                    ax.set_title('RAM Utilization Over Time')
                    ax.set_xlabel('Time'); ax.set_ylabel('RAM (%)'); ax.legend(loc='best', fontsize='small')
                    insert_plot(fig, row); row += 16
            except Exception as e:
                print("ram plot error:", e)

            # SSD over time
            try:
                if 'SSDUtil_Percent' in df.columns and not df['SSDUtil_Percent'].dropna().empty:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    for host in hosts[:10]:
                        host_data = df[df['Hostname'] == host].sort_values('Timestamp')
                        if host_data.empty: continue
                        ax.plot(host_data['Timestamp'], pd.to_numeric(host_data['SSDUtil_Percent'], errors='coerce'), label=str(host))
                    ax.set_title('Storage Utilization Over Time')
                    ax.set_xlabel('Time'); ax.set_ylabel('Storage (%)'); ax.legend(loc='best', fontsize='small')
                    insert_plot(fig, row); row += 16
            except Exception as e:
                print("ssd plot error:", e)

        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'server_metrics_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )

    except Exception as e:
        print(f"download_analysis_report error: {e}")
        return jsonify({"error": str(e)}), 500

logo_path = os.path.join(BASE_DIR, "static", "images", "BaffleSol.png")
if not os.path.exists(logo_path):
    logo_path = os.path.join(BASE_DIR, "static", "images", "BaffleSol.jpg")
@smart_analyzer.context_processor
def inject_logo():
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as img_file:
            encoded_string = base64.b64encode(img_file.read()).decode()
            ext = os.path.splitext(logo_path)[1][1:]  # get extension without dot
            logo_data = f"data:image/{ext};base64,{encoded_string}"
            return dict(logo_data=logo_data)
    return dict(logo_data=None)