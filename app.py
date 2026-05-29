from __future__ import annotations

import io
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent / "src"))

from patent_app.exporter import OUTPUT_COLUMN_RENAME, build_xlsx_bytes
from patent_app.io_ops import (
    canonicalize_dataframe,
    load_dataframe,
    parse_country_priority,
    resolve_column_mapping,
)
from patent_app.config import NO_ACC_TOKENS
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

uploaded_files = st.file_uploader(
    "入力ファイル (.xlsx/.xlsm/.csv)",
    type=["xlsx", "xlsm", "csv"],
    accept_multiple_files=True,
)
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
country_priority_raw = st.text_input(
    "国優先順位 (カンマ区切り)",
    value="JP,US,EP,WO,CN,KR",
    disabled=st.session_state.get("use_basic_selection", False),
)
use_basic_selection = st.checkbox(
    "Basicを選択（DWPIファミリー先頭メンバー）",
    key="use_basic_selection",
)
if use_basic_selection:
    st.caption("Basic選択時はファミリ単位でBasicを選択し、優先ロジック/日付方針/国優先順位は無効になります。")


def _sync_date_policy_from_priority_basis() -> None:
    st.session_state["date_policy"] = (
        "earliest" if st.session_state.get("priority_basis") == "publication" else "latest"
    )


def _render_paginated_dataframe(
    df,
    section_title: str,
    key_prefix: str,
    family_count: int | None = None,
    no_acc_count: int | None = None,
    before_search_controls_renderer=None,
) -> None:
    st.subheader(section_title)
    total_rows = len(df)
    parts = [f"Pubs: {total_rows:,}", f"Cols: {len(df.columns)}"]
    if family_count is not None:
        parts.append(f"family: {family_count:,}")
    if no_acc_count is not None:
        parts.append(f"no_acc: {no_acc_count:,}")
    st.write(" / ".join(parts))

    if before_search_controls_renderer is not None:
        before_search_controls_renderer()

    if total_rows == 0:
        st.dataframe(df, width="stretch")
        return  

    query_key = f"{key_prefix}_search_query"
    target_key = f"{key_prefix}_search_target"
    if query_key not in st.session_state:
        st.session_state[query_key] = ""

    search_cols = ["(全列)"] + list(df.columns)
    if target_key not in st.session_state or st.session_state[target_key] not in search_cols:
        st.session_state[target_key] = "(全列)"

    search_query = st.session_state[query_key]
    search_target = st.session_state[target_key]

    info_col, search_col = st.columns([5, 2])
    result_caption = info_col.empty()
    with search_col:
        s_query_col, s_target_col = st.columns([3, 2])
        s_query_col.text_input("検索", value=st.session_state[query_key], key=query_key, placeholder="キーワード")
        s_target_col.selectbox("対象", search_cols, key=target_key)

    search_query = st.session_state[query_key]
    search_target = st.session_state[target_key]

    filtered_df = df
    if str(search_query).strip():
        q = str(search_query).strip()
        normalized = df.fillna("").astype(str)
        if search_target == "(全列)":
            matched = normalized.apply(lambda c: c.str.contains(q, case=False, regex=False)).any(axis=1)
        else:
            matched = normalized[search_target].str.contains(q, case=False, regex=False)
        filtered_df = df.loc[matched]

    filtered_rows = len(filtered_df)
    result_caption.caption(f"検索結果: {filtered_rows:,} / {total_rows:,} 件")
    st.dataframe(filtered_df, width="stretch")


def _find_accession_series(df):
    candidates = [
        "accession_number",
        "DWPI accession number",
        "dwpi accession number",
        "DWPIアクセッション番号",
        "DWPI アクセッション番号",
    ]
    for name in candidates:
        if name in df.columns:
            return df[name]

    for col in df.columns:
        col_text = str(col).lower().replace(" ", "")
        if "dwpi" in col_text and "accession" in col_text:
            return df[col]

    return None


def _compute_family_no_acc_counts(df) -> tuple[int | None, int | None]:
    accession_series = _find_accession_series(df)
    if accession_series is None:
        return None, None

    cleaned = accession_series.fillna("").astype(str).str.strip()
    family_count = cleaned[cleaned.ne("")].nunique()
    no_acc_count = cleaned.str.lower().isin(NO_ACC_TOKENS).sum()
    return int(family_count), int(no_acc_count)


def _detect_output_extension(output_bytes: bytes, template_is_xlsm: bool) -> str:
    if not template_is_xlsm:
        return "xlsx"

    try:
        with zipfile.ZipFile(io.BytesIO(output_bytes), "r") as archive:
            names = set(archive.namelist())
            has_vba_project = "xl/vbaProject.bin" in names
            content_types = archive.read("[Content_Types].xml")
            has_macro_content_type = b"application/vnd.ms-excel.sheet.macroEnabled.main+xml" in content_types
            return "xlsm" if has_vba_project or has_macro_content_type else "xlsx"
    except Exception:
        return "xlsx"


if "priority_basis" not in st.session_state:
    st.session_state["priority_basis"] = "registration"
if "date_policy" not in st.session_state:
    _sync_date_policy_from_priority_basis()
if "selected_df" not in st.session_state:
    st.session_state["selected_df"] = None
if "output_bytes" not in st.session_state:
    st.session_state["output_bytes"] = None
if "result_error" not in st.session_state:
    st.session_state["result_error"] = None
if "uploaded_files_key" not in st.session_state:
    st.session_state["uploaded_files_key"] = None
if "preview_df" not in st.session_state:
    st.session_state["preview_df"] = None
if "preview_family_count" not in st.session_state:
    st.session_state["preview_family_count"] = None
if "preview_no_acc_count" not in st.session_state:
    st.session_state["preview_no_acc_count"] = None
if "use_basic_selection" not in st.session_state:
    st.session_state["use_basic_selection"] = False


CACHE_SCHEMA_VERSION = "2026-05-29-pdf-link-extraction-v4"


if "cache_schema_version" not in st.session_state:
    st.session_state["cache_schema_version"] = CACHE_SCHEMA_VERSION


def _build_uploaded_files_key(files) -> tuple[tuple[str, int], ...] | None:
    if not files:
        return None
    return tuple(sorted((f.name, f.size) for f in files))


def _remove_basic_from_country_priority(groups: list[str]) -> list[str]:
    out: list[str] = []
    for group in groups:
        parts = [part.strip().upper() for part in str(group).split("=") if part.strip()]
        filtered = [part for part in parts if part != "BASIC"]
        if filtered:
            out.append("=".join(filtered))
    return out


@st.cache_data(show_spinner=False)
def _load_and_canonicalize_file(file_name: str, file_bytes: bytes, cache_version: str) -> pd.DataFrame:
    raw_file_df = load_dataframe(file_name, file_bytes)
    file_columns = list(raw_file_df.columns)
    mapping = resolve_column_mapping(file_columns)
    canonical_file_df = canonicalize_dataframe(raw_file_df, mapping)
    canonical_file_df["source_file"] = file_name
    return canonical_file_df


@st.cache_data(show_spinner=False)
def _build_preview_dataframe(file_payloads: tuple[tuple[str, bytes], ...], cache_version: str) -> pd.DataFrame:
    canonical_preview_dfs = [
        _load_and_canonicalize_file(name, content, cache_version)
        for name, content in file_payloads
    ]
    if not canonical_preview_dfs:
        return pd.DataFrame()
    return pd.concat(canonical_preview_dfs, ignore_index=True)


col1, col2, col3 = st.columns(3)
mode = col1.selectbox(
    "処理単位",
    ["family", "application"],
    format_func=lambda x: "ファミリ単位" if x == "family" else "出願単位",
    disabled=use_basic_selection,
)
priority_basis = col2.selectbox(
    "優先ロジック",
    ["registration", "publication"],
    format_func=lambda x: "登録優先" if x == "registration" else "公開優先",
    key="priority_basis",
    on_change=_sync_date_policy_from_priority_basis,
    disabled=use_basic_selection,
)
date_policy = col3.selectbox(
    "日付方針",
    ["latest", "earliest"],
    format_func=lambda x: "最新" if x == "latest" else "最先",
    key="date_policy",
    disabled=use_basic_selection,
)

if uploaded_files:
    if st.session_state.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
        st.session_state["uploaded_files_key"] = None
        st.session_state["preview_df"] = None
        st.session_state["preview_family_count"] = None
        st.session_state["preview_no_acc_count"] = None
        st.session_state["cache_schema_version"] = CACHE_SCHEMA_VERSION

    current_files_key = _build_uploaded_files_key(uploaded_files)
    if st.session_state["uploaded_files_key"] != current_files_key:
        st.session_state["uploaded_files_key"] = current_files_key
        st.session_state["selected_df"] = None
        st.session_state["output_bytes"] = None
        st.session_state["result_error"] = None
        file_payloads = tuple((uploaded_file.name, uploaded_file.getvalue()) for uploaded_file in uploaded_files)
        preview_df = _build_preview_dataframe(file_payloads, CACHE_SCHEMA_VERSION)
        raw_family_count, raw_no_acc_count = _compute_family_no_acc_counts(preview_df)
        st.session_state["preview_df"] = preview_df
        st.session_state["preview_family_count"] = raw_family_count
        st.session_state["preview_no_acc_count"] = raw_no_acc_count

    preview_df = st.session_state["preview_df"]
    raw_family_count = st.session_state["preview_family_count"]
    raw_no_acc_count = st.session_state["preview_no_acc_count"]

    if preview_df is None:
        st.warning("入力データの読み込みに失敗しました。ファイルを再選択してください。")
        st.stop()

    _render_paginated_dataframe(
        preview_df,
        "入力プレビュー",
        "raw_preview",
        family_count=raw_family_count,
        no_acc_count=raw_no_acc_count,
    )

    template_is_xlsm = bool(template and template.name.lower().endswith(".xlsm"))

    run_clicked = st.button("抽出実行", type="primary")
    if run_clicked:
        progress = st.progress(0, text="抽出処理を開始しています...")
        try:
            progress.progress(16, text="入力データを正規化しています...")
            canonical_df = preview_df.copy()

            progress.progress(24, text="抽出条件を準備しています...")
            parsed_country_priority = _remove_basic_from_country_priority(parse_country_priority(country_priority_raw))
            effective_mode = "family" if use_basic_selection else mode
            cfg = SelectionConfig(
                mode=effective_mode,
                priority_basis=priority_basis,
                date_policy=date_policy,
                country_priority=parsed_country_priority,
                use_basic_selection=use_basic_selection,
                treat_wo_republication_as_jp=treat_wo_republication_as_jp,
                treat_wo_prior_republication_as_jp=treat_wo_prior_republication_as_jp,
                exclude_invalid=exclude_invalid,
                exclude_utility=exclude_utility,
                start_date_field=start_date_field,
                start_date=start_date_value if enable_start_date else None,
                end_date_field=end_date_field,
                end_date=end_date_value if enable_end_date else None,
            )

            progress.progress(30, text="抽出ロジックを実行しています...")
            selected_df, _ = run_selection_pipeline(
                canonical_df,
                cfg,
                progress_callback=lambda value, message: progress.progress(value, text=message),
            )
            if "accession_number" in selected_df.columns:
                selected_df = selected_df.sort_values(
                    by="accession_number",
                    ascending=False,
                    na_position="last",
                    kind="stable",
                ).reset_index(drop=True)

            progress.progress(95, text="ダウンロード用ファイルを作成しています...")
            output_bytes = build_xlsx_bytes(
                selected_df,
                template_bytes=template.getvalue() if template else None,
                keep_vba=template_is_xlsm,
            )
            st.session_state["selected_df"] = selected_df
            st.session_state["output_bytes"] = output_bytes
            st.session_state["result_error"] = None
            progress.progress(100, text="抽出が完了しました。")
        except Exception as exc:
            st.session_state["result_error"] = str(exc)
            progress.progress(100, text="処理に失敗しました。")

    if st.session_state["result_error"]:
        st.error(f"処理に失敗しました: {st.session_state['result_error']}")

    if st.session_state["selected_df"] is not None:
        selected_df = st.session_state["selected_df"]
        st.success("抽出が完了しました。")
        st.metric("抽出件数", f"{len(selected_df):,}")

        output_extension = _detect_output_extension(st.session_state["output_bytes"], template_is_xlsm)
        output_file_name = f"{date.today():%Y%m%d}_selected_patents.{output_extension}"
        output_mime = (
            "application/vnd.ms-excel.sheet.macroEnabled.12"
            if output_extension == "xlsm"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        def _render_download_button() -> None:
            if template_is_xlsm and output_extension != "xlsm":
                st.warning("テンプレートの読み込み互換性問題により、出力形式を .xlsx に切り替えました。")
            st.download_button(
                label=f"結果をダウンロード (.{output_extension})",
                data=st.session_state["output_bytes"],
                file_name=output_file_name,
                mime=output_mime,
            )

        selected_family_count, _ = _compute_family_no_acc_counts(selected_df)
        _render_paginated_dataframe(
            selected_df.rename(columns=OUTPUT_COLUMN_RENAME),
            "抽出結果",
            "selected_preview",
            family_count=selected_family_count,
            before_search_controls_renderer=_render_download_button,
        )
else:
    st.info("入力ファイルを選択してください。")
