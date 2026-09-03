# export_excel.py
import os
def export(csv_path, out_xlsx):
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas required")
    df = pd.read_csv(csv_path)
    df.to_excel(out_xlsx, index=False)
