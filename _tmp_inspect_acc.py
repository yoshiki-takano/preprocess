import sys, pathlib
sys.path.insert(0, "src")
import pandas as pd
from patent_app.io_ops import load_dataframe, resolve_column_mapping, canonicalize_dataframe

dl = pathlib.Path.home() / "Downloads"
for name in ["母集団2_3186rec_forApp_excel2026-08-27-18-31-00.xlsx", "母集団2_3186rec_forApp_excel2026-08-27-18-31-00 -  コピー.xlsx"]:
    p = dl / name
    raw = load_dataframe(p.name, p.read_bytes())
    df = canonicalize_dataframe(raw, resolve_column_mapping(list(raw.columns)))
    hit = df[df["accession_number"].astype(str).str.contains("2025855185", regex=False)]
    print("FILE", name, len(df), "hits", len(hit))
    cols = [c for c in ["accession_number", "family_id", "publication_number", "registration_number", "country_code", "kind", "legal_status", "publication_date", "application_number", "dwpi_family_members", "__raw_publication_number__"] if c in df.columns]
    with pd.option_context("display.width", 300, "display.max_columns", 50, "display.max_colwidth", 120):
        print(hit[cols].to_string())
