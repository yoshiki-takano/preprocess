import sys, pathlib
sys.path.insert(0, "src")
import pandas as pd
from patent_app.io_ops import load_dataframe, resolve_column_mapping, canonicalize_dataframe
from patent_app.models import SelectionConfig
from patent_app.pipeline import run_selection_pipeline

p = pathlib.Path.home() / "Downloads" / "母集団2_3186rec_forApp_excel2026-08-27-18-31-00.xlsx"
raw = load_dataframe(p.name, p.read_bytes())
df = canonicalize_dataframe(raw, resolve_column_mapping(list(raw.columns)))

norm = lambda v: str(v or "").strip().upper().replace(" ", "")
first = df["dwpi_family_members"].map(lambda v: norm(str(v).split("|", 1)[0]) if pd.notna(v) else "")
raw_pub = df["__raw_publication_number__"].map(norm) if "__raw_publication_number__" in df.columns else df["publication_number"].map(norm)
df_basic_acc = set(df.loc[raw_pub.ne("") & raw_pub.eq(first), "accession_number"].astype(str))
multi = df["accession_number"].astype(str).value_counts()
target = {a for a in df_basic_acc if multi.get(a, 0) > 1}
basic_no = dict(zip(df["accession_number"].astype(str), first))
print("families with BASIC row in population:", len(df_basic_acc), "multi-row:", len(target))

for prio in ["JP,US,EP,WO,CN,KR", "BASIC,JP,US,EP,WO,CN,KR"]:
    cfg = SelectionConfig(
        mode="family", priority_basis="publication", date_policy="earliest",
        country_priority=prio.split(","),
        treat_wo_republication_as_jp=True, treat_wo_prior_republication_as_jp=True,
    )
    sel, _ = run_selection_pipeline(df, cfg)
    acc_col = next(c for c in sel.columns if "アクセッション" in c or "accession" in c.lower())
    sub = sel[sel[acc_col].astype(str).isin(target)]
    ok = sub.apply(lambda r: norm(r["selected_patent_number"]) == basic_no[str(r[acc_col])], axis=1)
    print(f"{prio:26s} selected rows={len(sub)} basic_selected={int(ok.sum())}")
    if prio.startswith("BASIC"):
        bad = sub[~ok]
        print(bad[[acc_col, "selected_patent_number"]].assign(basic=bad[acc_col].astype(str).map(basic_no)).head(10).to_string())
