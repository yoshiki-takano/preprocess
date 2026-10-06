import sys, pathlib
sys.path.insert(0, "src")
from patent_app.io_ops import load_dataframe, resolve_column_mapping, canonicalize_dataframe

for p in sorted(pathlib.Path("data").glob("*.xls*")) + sorted(pathlib.Path(".").glob("*.xls*")):
    try:
        raw = load_dataframe(p.name, p.read_bytes())
        df = canonicalize_dataframe(raw, resolve_column_mapping(list(raw.columns)))
    except Exception as e:
        print("ERR", p.name, type(e).__name__, flush=True)
        continue
    hit = df.astype(str).apply(lambda s: s.str.contains("2025855185", regex=False)).any(axis=1).sum()
    print("SCAN", p.name, len(df), "hit=", hit, flush=True)
