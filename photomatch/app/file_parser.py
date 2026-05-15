import csv
import io
from typing import Dict, List, Any

import pandas as pd


def parse_uploaded_file(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """
    Reads xlsx/xls/csv and returns:
    - columns
    - rows
    - preview_rows
    """

    lower_filename = filename.lower()

    if lower_filename.endswith(".csv"):
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("cp1253", errors="ignore")

        sample = text[:2048]
        sniffer = csv.Sniffer()

        try:
            dialect = sniffer.sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";"

        df = pd.read_csv(io.StringIO(text), delimiter=delimiter, dtype=str).fillna("")

    elif lower_filename.endswith(".xlsx") or lower_filename.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna("")

    else:
        raise ValueError("Υποστηρίζονται μόνο αρχεία Excel ή CSV.")

    df.columns = [str(col).strip() for col in df.columns]

    rows = df.to_dict(orient="records")

    return {
        "columns": list(df.columns),
        "rows": rows,
        "preview_rows": rows[:10],
        "total_rows": len(rows)
    }
