from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent / "src"))

from patent_app.exporter import build_xlsx_bytes
from patent_app.io_ops import (
    canonicalize_dataframe,
    load_dataframe,
    parse_country_priority,
    resolve_column_mapping,
)
from patent_app.models import SelectionConfig
from patent_app.pipeline import run_selection_pipeline

st.set_page_config(page_title="Patent Extractor", layout="wide")
st.title("特許データ抽出アプリ (MVP)")
st.caption("Excel/CSVを読み込み、業務ルールで調査対象を抽出します。")

first_day_this_month = date.today().replace(day=1)
default_end_date = first_day_this_month - timedelta(days=1)
start_year = default_end_date.year - 20
start_month = default_end_date.month + 1
if start_month == 13:
    start_month = 1
    start_year += 1
default_start_date = date(start_year, start_month, 1)

uploaded = st.file_uploader("入力ファイル (.xlsx/.xlsm/.csv)", type=["xlsx", "xlsm", "csv"])
template = st.file_uploader("出力テンプレート (.xlsx/.xlsm, 任意)", type=["xlsx", "xlsm"])

st.subheader("除外条件")
ex1, ex2 = st.columns(2)
exclude_invalid = ex1.checkbox("失効を除外", value=False)
exclude_utility = ex2.checkbox("実案を除外", value=False)

st.caption("日付除外 (デフォルト: なし)")
enable_start_date = st.checkbox("開始日で除外", value=False)
with st.expander("開始日条件の設定", expanded=enable_start_date):
    date_start_col1, date_start_col2 = st.columns(2)
    start_date_field = date_start_col1.selectbox(
        "開始日の基準",
        ["publication_date", "application_date"],
        format_func=lambda x: "公開日" if x == "publication_date" else "出願日",
        disabled=not enable_start_date,
    )
    start_date_value = date_start_col2.date_input("開始日", value=default_start_date, disabled=not enable_start_date)

enable_end_date = st.checkbox("終了日で除外", value=False)
with st.expander("終了日条件の設定", expanded=enable_end_date):
    date_end_col1, date_end_col2 = st.columns(2)
    end_date_field = date_end_col1.selectbox(
        "終了日の基準",
        ["publication_date", "application_date"],
        format_func=lambda x: "公開日" if x == "publication_date" else "出願日",
        disabled=not enable_end_date,
    )
    end_date_value = date_end_col2.date_input("終了日", value=default_end_date, disabled=not enable_end_date)

st.subheader("選択条件")
treat_wo_republication_as_jp = st.checkbox("再公表(元WO)をJPとして扱う", value=True)
treat_wo_prior_republication_as_jp = st.checkbox("先行再公表(WO)をJPとして扱う", value=True)
country_priority_raw = st.text_input("国優先順位 (カンマ区切り)", value="JP,US,EP,WO,CN,KR")


def _sync_date_policy_from_priority_basis() -> None:
    st.session_state["date_policy"] = (
        "earliest" if st.session_state.get("priority_basis") == "publication" else "latest"
    )


if "priority_basis" not in st.session_state:
    st.session_state["priority_basis"] = "registration"
if "date_policy" not in st.session_state:
    _sync_date_policy_from_priority_basis()


col1, col2, col3 = st.columns(3)
mode = col1.selectbox("処理単位", ["family", "application"], format_func=lambda x: "ファミリ単位" if x == "family" else "出願単位")
priority_basis = col2.selectbox(
    "優先ロジック",
    ["registration", "publication"],
    format_func=lambda x: "登録優先" if x == "registration" else "公開優先",
    key="priority_basis",
    on_change=_sync_date_policy_from_priority_basis,
)
date_policy = col3.selectbox(
    "日付方針",
    ["latest", "earliest"],
    format_func=lambda x: "最新" if x == "latest" else "最先",
    key="date_policy",
)

if uploaded:
    raw_df = load_dataframe(uploaded.name, uploaded.getvalue())
    st.subheader("入力プレビュー")
    st.write(f"Rows: {len(raw_df):,} / Cols: {len(raw_df.columns)}")
    st.dataframe(raw_df.head(100), width='stretch')

    source_columns = list(raw_df.columns)

    run_clicked = st.button("抽出実行", type="primary")
    if run_clicked:
        try:
            mapping = resolve_column_mapping(source_columns)
            canonical_df = canonicalize_dataframe(raw_df, mapping)
            cfg = SelectionConfig(
                mode=mode,
                priority_basis=priority_basis,
                date_policy=date_policy,
                country_priority=parse_country_priority(country_priority_raw),
                treat_wo_republication_as_jp=treat_wo_republication_as_jp,
                treat_wo_prior_republication_as_jp=treat_wo_prior_republication_as_jp,
                exclude_invalid=exclude_invalid,
                exclude_utility=exclude_utility,
                start_date_field=start_date_field,
                start_date=start_date_value if enable_start_date else None,
                end_date_field=end_date_field,
                end_date=end_date_value if enable_end_date else None,
            )
            selected_df, no_acc_df = run_selection_pipeline(canonical_df, cfg)

            st.success("抽出が完了しました。")
            m1, m2 = st.columns(2)
            m1.metric("抽出件数", f"{len(selected_df):,}")
            m2.metric("no_acc件数", f"{len(no_acc_df):,}")

            st.subheader("抽出結果")
            st.dataframe(selected_df.head(300), width='stretch')

            output_bytes = build_xlsx_bytes(
                selected_df,
                no_acc_df,
                template.getvalue() if template else None,
            )
            output_file_name = f"{date.today():%Y%m%d}_selected_patents.xlsx"
            st.download_button(
                label="結果をダウンロード (.xlsx)",
                data=output_bytes,
                file_name=output_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as exc:
            st.error(f"処理に失敗しました: {exc}")
else:
    st.info("入力ファイルを選択してください。")
