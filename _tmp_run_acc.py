import sys, pathlib
sys.path.insert(0, "src")
import pandas as pd
from patent_app.io_ops import load_dataframe, resolve_column_mapping, canonicalize_dataframe
from patent_app.models import SelectionConfig
from patent_app.pipeline import run_selection_pipeline

p = pathlib.Path.home() / "Downloads" / "母集団2_3186rec_forApp_excel2026-08-27-18-31-00.xlsx"
raw = load_dataframe(p.name, p.read_bytes())
df = canonicalize_dataframe(raw, resolve_column_mapping(list(raw.columns)))

ACC = "2025855185"
for prio in ["JP,US,EP,WO,CN,KR", "JP,US,EP,WO,CN,KR,BASIC", "BASIC,JP,US,EP,WO,CN,KR"]:
    for mode in ["family", "application"]:
        cfg = SelectionConfig(
            mode=mode,
            priority_basis="registration",
            date_policy="latest",
            country_priority=[v.strip().upper() for v in prio.split(",") if v.strip()],
            treat_wo_republication_as_jp=True,
            treat_wo_prior_republication_as_jp=True,
        )
        selected, _ = run_selection_pipeline(df, cfg)
        acc_col = next(c for c in selected.columns if "accession" in c.lower() or c in {"DWPI アクセッション番号", "アクセッション番号"})
        hit = selected[selected[acc_col].astype(str).str.contains(ACC, regex=False)]
        num_col = "selected_patent_number" if "selected_patent_number" in selected.columns else selected.columns[0]
        print(f"{prio:28s} {mode:12s} rows={len(hit)} ->", hit[num_col].tolist() if len(hit) else "-")
