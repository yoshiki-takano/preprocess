from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Callable

import pandas as pd

from .config import EXCLUDE_KIND_TOKENS, EXCLUDE_STATUS_TOKENS, NO_ACC_TOKENS
from .models import SelectionConfig

ProgressCallback = Callable[[int, str], None]

FIVE_OFFICE_COUNTRIES = {"JP", "US", "EP", "CN", "KR"}


@lru_cache(maxsize=1)
def _load_kind_code_lookup_pipeline() -> dict[tuple[str, str], str]:
    """kind_code.csv から (COUNTRY_CODE, DWPI_KIND) → PUAB のルックアップを返す。"""
    csv_path = Path(__file__).resolve().parents[2] / "data" / "kind_code.csv"
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    if not {"COUNTRY_CODE", "DWPI_KIND", "PUAB"}.issubset(set(df.columns)):
        return {}
    lookup: dict[tuple[str, str], str] = {}
    for _, row in df.iterrows():
        country = str(row["COUNTRY_CODE"]).strip().upper()
        kind = str(row["DWPI_KIND"]).strip().upper()
        puab = str(row["PUAB"]).strip().upper()
        if country and kind and puab:
            lookup[(country, kind)] = puab
    return lookup


def _resolve_puab_for_row(row: pd.Series) -> str:
    """行の公報番号/登録番号から PUAB 値を返す。"""
    lookup = _load_kind_code_lookup_pipeline()
    if not lookup:
        return ""
    pub_no = str(row.get("publication_number", "") or "").strip()
    reg_no = str(row.get("registration_number", "") or "").strip()
    doc_no = pub_no or reg_no
    if not doc_no:
        return ""
    value = doc_no.strip().upper().replace(" ", "")
    cc_match = re.match(r"^([A-Za-z]{2})", value)
    country = cc_match.group(1).upper() if cc_match else ""
    kind_match = re.search(r"([A-Z]{1,2}\d{0,2})$", value)
    kind_code = kind_match.group(1) if kind_match else ""
    return lookup.get((country, kind_code), "")


SOURCE_HELPER_COLUMNS = [
    "title_english",
    "title_dwpi",
    "assignee_standardized",
    "assignee_applicant",
    "assignee_dwpi",
    "priority_number",
    "priority_date",
    "dwpi_family_members",
    "dwpi_family_members_status",
]


def _notify_progress(progress_callback: ProgressCallback | None, value: int, message: str) -> None:
    if progress_callback is not None:
        progress_callback(value, message)


def run_selection_pipeline(
    canonical_df: pd.DataFrame,
    config: SelectionConfig,
    progress_callback: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = canonical_df.copy()
    _notify_progress(progress_callback, 38, "再公表(元WO)ルールを適用しています...")
    working, repub_applied_mask = _apply_wo_republication_as_jp(
        working,
        treat_wo_republication_as_jp=config.treat_wo_republication_as_jp,
    )
    _notify_progress(progress_callback, 44, "先行再公表(WO)ルールを適用しています...")
    working = _apply_wo_prior_republication_as_jp(
        working,
        treat_wo_prior_republication_as_jp=config.treat_wo_prior_republication_as_jp,
        skip_mask=repub_applied_mask,
    )
    _notify_progress(progress_callback, 50, "JP X種の除外を適用しています...")
    working = _exclude_jp_x_s5(working)
    _notify_progress(progress_callback, 56, "選択対象の除外条件を判定しています...")
    selectable = _apply_exclusions(
        working,
        exclude_invalid=config.exclude_invalid,
        exclude_utility=config.exclude_utility,
        start_date_field=config.start_date_field,
        start_date=config.start_date,
        end_date_field=config.end_date_field,
        end_date=config.end_date,
    )
    selectable_index = set(selectable.index)

    _notify_progress(progress_callback, 56, "関連データを準備しています...")
    no_acc_df = _extract_no_acc(selectable)
    patent_status_lookup = _build_legal_status_lookup(working)
    legal_status_lookup = _build_legal_status_lookup(selectable)
    paired = _pair_publication_registration_by_application(working)
    patent_application_date_lookup = _build_patent_application_date_lookup(working)
    patent_date_lookup = _build_patent_publication_date_lookup(working)
    patent_application_number_lookup = _build_patent_application_number_lookup(working)

    if not paired.empty and selectable_index:
        paired = paired.loc[paired.index.isin(selectable_index)].copy()

    _notify_progress(progress_callback, 60, "国優先順位で候補を絞り込んでいます...")
    narrowed = _apply_one_family_one_country(paired, config.country_priority)
    if not narrowed.empty:
        narrowed = narrowed.copy()
        if config.priority_basis == "registration":
            selected_no = narrowed["registration_number"].fillna("").astype(str).str.strip()
            fallback_no = narrowed["publication_number"].fillna("").astype(str).str.strip()
        else:
            selected_no = narrowed["publication_number"].fillna("").astype(str).str.strip()
            fallback_no = narrowed["registration_number"].fillna("").astype(str).str.strip()
        selected_no = selected_no.mask(selected_no == "", fallback_no)

        rank_app_no = selected_no.map(patent_application_number_lookup)
        narrowed["_rank_application_date"] = selected_no.map(patent_application_date_lookup)
        narrowed["_rank_publication_date"] = selected_no.map(patent_date_lookup)
        narrowed["_rank_application_number_numeric"] = rank_app_no.map(_extract_application_number_numeric)

    if config.mode == "family":
        grouped = _assign_group_key(narrowed, "family_id")
    else:
        grouped = _assign_group_key(narrowed, "application_number")

    _notify_progress(progress_callback, 64, "代表公報を選定しています...")
    selected_rows: list[pd.Series] = []
    grouped_items = list(grouped.groupby("_group_key", dropna=False))
    total_groups = len(grouped_items)
    step = max(1, total_groups // 8) if total_groups > 0 else 1
    for idx, (_, group) in enumerate(grouped_items, start=1):
        selected_rows.append(_select_representative(group, config))
        if total_groups > 0 and (idx == 1 or idx == total_groups or idx % step == 0):
            value = 64 + int((idx / total_groups) * 24)
            _notify_progress(progress_callback, value, f"代表公報を選定しています... ({idx}/{total_groups})")

    if not selected_rows:
        _notify_progress(progress_callback, 90, "抽出結果を整形しています...")
        return pd.DataFrame(columns=canonical_df.columns), no_acc_df

    _notify_progress(progress_callback, 90, "抽出結果を整形しています...")
    selected = pd.DataFrame(selected_rows).drop(
        columns=[
            "_group_key",
            "family_id",
            "registration_date",
            "_is_utility",
            "_has_primary",
            "_rank_date",
            "_pairing_application_key",
            "_pairing_key_override",
            "_pairing_date_override",
            "_rank_application_date",
            "_rank_publication_date",
            "_rank_application_number_numeric",
            "_country_matches_selected",
            "_pub_base",
            "_pub_revision",
            "_pub_raw",
            "_reg_base",
            "_reg_revision",
            "_reg_raw",
        ],
        errors="ignore",
    )
    selected["selected_patent_number"] = selected.apply(
        lambda row: _resolve_selected_patent_number(
            row,
            config.priority_basis,
            exclude_invalid=config.exclude_invalid,
            status_lookup=patent_status_lookup,
        ),
        axis=1,
    )
    selected = _resolve_application_date_from_selected_patent(selected, patent_application_date_lookup)
    selected = _resolve_publication_date_from_selected_patent(selected, patent_date_lookup)
    selected["legal_status"] = selected.apply(
        lambda row: _resolve_selected_legal_status(row, legal_status_lookup),
        axis=1,
    )
    selected = _append_additional_output_columns(selected, canonical_df)
    selected = selected.drop(columns=SOURCE_HELPER_COLUMNS, errors="ignore")
    selected = _reorder_selected_columns(selected)
    selected = selected.reset_index(drop=True)
    no_acc = no_acc_df.drop(columns=["family_id", "registration_date"], errors="ignore").reset_index(drop=True)
    return selected, no_acc


def _apply_exclusions(
    df: pd.DataFrame,
    exclude_invalid: bool,
    exclude_utility: bool,
    start_date_field: str,
    start_date,
    end_date_field: str,
    end_date,
) -> pd.DataFrame:
    if not exclude_invalid and not exclude_utility and start_date is None and end_date is None:
        return df.copy()

    status_series = df["legal_status"].fillna("").str.lower()
    kind_series = df["kind"].fillna("").str.lower()

    status_mask = ~status_series.apply(_contains_exclude_status) if exclude_invalid else pd.Series(True, index=df.index)
    kind_mask = ~kind_series.apply(_contains_exclude_kind) if exclude_utility else pd.Series(True, index=df.index)
    date_mask = _build_date_range_mask(df, start_date_field, start_date, end_date_field, end_date)

    return df[status_mask & kind_mask & date_mask].copy()


def _build_date_range_mask(
    df: pd.DataFrame,
    start_date_field: str,
    start_date,
    end_date_field: str,
    end_date,
) -> pd.Series:
    mask = pd.Series(True, index=df.index)

    if start_date is not None:
        start_series = _to_date_series(df, start_date_field)
        mask = mask & start_series.ge(start_date)

    if end_date is not None:
        end_series = _to_date_series(df, end_date_field)
        mask = mask & end_series.le(end_date)

    return mask.fillna(False)


def _to_date_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(pd.NaT, index=df.index)
    return pd.to_datetime(df[column], errors="coerce").dt.date


def _pair_publication_registration_by_application(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    match_keys = _build_pairing_match_keys(out)
    if "_pairing_key_override" in out.columns:
        override = out["_pairing_key_override"].fillna("").astype(str).str.strip()
        match_keys = match_keys.mask(override.ne(""), override)
    out["_pairing_application_key"] = match_keys

    for match_key, idx in match_keys.groupby(match_keys).groups.items():
        if not match_key:
            continue

        group = out.loc[idx]
        best_pub = _pick_best_record(group, "publication_number", "publication_date")
        best_reg = _pick_best_record(group, "registration_number", "registration_date")

        if best_pub is not None:
            out.loc[idx, "publication_number"] = out.loc[idx, "publication_number"].mask(
                out.loc[idx, "publication_number"].fillna("").astype(str).str.strip() == "",
                best_pub["publication_number"],
            )
            out.loc[idx, "publication_date"] = out.loc[idx, "publication_date"].mask(
                out.loc[idx, "publication_date"].isna(),
                best_pub["publication_date"],
            )

        if best_reg is not None:
            out.loc[idx, "registration_number"] = out.loc[idx, "registration_number"].mask(
                out.loc[idx, "registration_number"].fillna("").astype(str).str.strip() == "",
                best_reg["registration_number"],
            )
            out.loc[idx, "registration_date"] = out.loc[idx, "registration_date"].mask(
                out.loc[idx, "registration_date"].isna(),
                best_reg["registration_date"],
            )

    return out


def _build_pairing_match_keys(df: pd.DataFrame) -> pd.Series:
    if "application_number" in df.columns:
        app_series = df["application_number"].fillna("").astype(str).str.strip()
    else:
        app_series = pd.Series("", index=df.index)

    country_series = _resolve_pairing_country_series(df)
    if "application_date" in df.columns:
        app_date_series = pd.to_datetime(df["application_date"], errors="coerce")
    else:
        app_date_series = pd.Series(pd.NaT, index=df.index)

    if "_pairing_date_override" in df.columns:
        override = pd.to_datetime(df["_pairing_date_override"], errors="coerce")
        app_date_series = app_date_series.mask(override.notna(), override)

    keys = app_series.copy()
    us_mask = country_series.eq("US")
    if not us_mask.any():
        return keys

    us_app = app_series.loc[us_mask].map(_extract_us_application_last_six)
    us_date = app_date_series.loc[us_mask].dt.strftime("%Y%m%d").fillna("")
    composite = "US|" + us_app + "|" + us_date
    valid = us_app.ne("") & us_date.ne("")
    keys.loc[us_mask] = keys.loc[us_mask].where(~valid, composite)
    return keys


def _resolve_pairing_country_series(df: pd.DataFrame) -> pd.Series:
    if "country_code" in df.columns:
        country = df["country_code"].fillna("").astype(str).str.upper()
    else:
        country = pd.Series("", index=df.index)

    if country.eq("").any():
        if "publication_number" in df.columns:
            pub_country = df["publication_number"].map(_extract_country_from_number)
        else:
            pub_country = pd.Series("", index=df.index)

        if "registration_number" in df.columns:
            reg_country = df["registration_number"].map(_extract_country_from_number)
        else:
            reg_country = pd.Series("", index=df.index)

        country = country.mask(country.eq(""), pub_country)
        country = country.mask(country.eq(""), reg_country)
    return country


def _extract_country_from_number(value: object) -> str:
    text = str(value or "").strip().upper()
    match = re.match(r"^([A-Z]{2})", text)
    return match.group(1) if match else ""


def _extract_us_application_last_six(value: object) -> str:
    digits = "".join(re.findall(r"\d", str(value or "")))
    if not digits:
        return ""
    return digits[-6:]


def _exclude_jp_x_s5(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    country = df["country_code"].fillna("").astype(str).str.upper()
    kind = df["kind"].fillna("").astype(str).str.upper()
    drop_mask = country.eq("JP") & kind.isin({"X", "S5"})
    return df[~drop_mask].copy()


def _apply_wo_republication_as_jp(
    df: pd.DataFrame,
    treat_wo_republication_as_jp: bool,
) -> tuple[pd.DataFrame, pd.Series]:
    if df.empty:
        out = _ensure_country_priority_code(df)
        return out, pd.Series(False, index=out.index)

    out = _ensure_country_priority_code(df)
    if not treat_wo_republication_as_jp:
        return out, pd.Series(False, index=out.index)

    country = out["country_code"].fillna("").astype(str).str.upper()
    kind = out["kind"].fillna("").astype(str).str.upper()
    publication = out["publication_number"].map(_normalize_publication_number)
    republish_set = _load_republish_pct_set()

    repub_mask = country.eq("WO") & publication.isin(republish_set)
    if not repub_mask.any():
        return out, repub_mask

    # R behavior: supplement publication_date/application_number from JP X by accession_number + application_date.
    jpx_mask = country.eq("JP") & kind.eq("X")
    if jpx_mask.any():
        jpx_lookup = (
            out.loc[jpx_mask, ["accession_number", "application_date", "publication_date", "application_number"]]
            .sort_values(by=["publication_date", "application_number"], ascending=[True, True], na_position="last")
            .drop_duplicates(subset=["accession_number", "application_date"], keep="first")
            .rename(
                columns={
                    "publication_date": "publication_date_jpx",
                    "application_number": "application_number_jpx",
                }
            )
        )

        targets = out.loc[repub_mask, ["accession_number", "application_date"]].copy()
        targets["_row_index"] = targets.index
        merged = targets.merge(jpx_lookup, on=["accession_number", "application_date"], how="left").set_index("_row_index")

        has_pub = merged["publication_date_jpx"].notna()
        if has_pub.any():
            out.loc[merged.index[has_pub], "publication_date"] = merged.loc[has_pub, "publication_date_jpx"]

        has_app = merged["application_number_jpx"].fillna("").astype(str).str.strip().ne("")
        if has_app.any():
            target_idx = merged.index[has_app]
            wo_empty = out.loc[target_idx, "application_number"].fillna("").astype(str).str.strip().eq("")
            fill_idx = target_idx[wo_empty.values]
            if len(fill_idx) > 0:
                out.loc[fill_idx, "application_number"] = merged.loc[fill_idx, "application_number_jpx"]

            # ペアリング補完: JP X の出願番号を _pairing_key_override として設定し、
            # WO の公報番号と JP の登録特許をペアリング可能にする
            if "_pairing_key_override" not in out.columns:
                out["_pairing_key_override"] = ""
            out.loc[target_idx, "_pairing_key_override"] = merged.loc[target_idx, "application_number_jpx"].values

            # マッチング用の内部出願日を保持する（表示列の application_date は更新しない）
            if "_pairing_date_override" not in out.columns:
                out["_pairing_date_override"] = pd.NaT
            out.loc[target_idx, "_pairing_date_override"] = pd.to_datetime(
                merged.loc[target_idx, "application_date"], errors="coerce"
            ).values

    out.loc[repub_mask, "_country_priority_code"] = "JP"
    return out, repub_mask


def _apply_wo_prior_republication_as_jp(
    df: pd.DataFrame,
    treat_wo_prior_republication_as_jp: bool,
    skip_mask: pd.Series | None = None,
) -> pd.DataFrame:
    if df.empty:
        return _ensure_country_priority_code(df)

    out = _ensure_country_priority_code(df)
    if not treat_wo_prior_republication_as_jp:
        return out

    country = out["country_code"].fillna("").astype(str).str.upper()
    kind = out["kind"].fillna("").astype(str).str.upper()
    pub_body = out["publication_number"].map(_extract_publication_numeric_body)
    accession = out["accession_number"].fillna("").astype(str).str.strip()

    effective_skip = pd.Series(False, index=out.index)
    if skip_mask is not None:
        effective_skip = skip_mask.reindex(out.index, fill_value=False)

    wo_a1_all_mask = country.eq("WO") & kind.eq("A1") & pub_body.ne("") & accession.ne("")
    wo_a1_mask = wo_a1_all_mask & ~effective_skip
    jp_a1_mask = country.eq("JP") & kind.eq("A1") & pub_body.ne("") & accession.ne("")
    if not wo_a1_all_mask.any() or not jp_a1_mask.any():
        return out

    jp_lookup = out.loc[
        jp_a1_mask, ["accession_number", "application_number", "application_date", "publication_date"]
    ].copy()
    jp_lookup["_pub_body"] = pub_body.loc[jp_a1_mask]
    jp_lookup["_matched_jp"] = True
    jp_lookup = (
        jp_lookup.sort_values(by=["publication_date", "application_number"], ascending=[True, True], na_position="last")
        .drop_duplicates(subset=["accession_number", "_pub_body"], keep="first")
        .rename(
            columns={
                "application_number": "application_number_jp",
                "application_date": "application_date_jp",
            }
        )
    )

    targets = out.loc[wo_a1_all_mask, ["accession_number", "application_number"]].copy()
    targets["_pub_body"] = pub_body.loc[wo_a1_all_mask]
    targets["_row_index"] = targets.index

    merged = targets.merge(jp_lookup, on=["accession_number", "_pub_body"], how="left").set_index("_row_index")
    matched = merged["_matched_jp"].fillna(False)
    if not matched.any():
        return out

    matched_index = merged.index[matched]
    matched_rows = merged.loc[matched, ["application_number_jp"]].copy()
    jp_has = matched_rows["application_number_jp"].fillna("").astype(str).str.strip().ne("")
    wo_empty = out.loc[matched_rows.index, "application_number"].fillna("").astype(str).str.strip().eq("")
    fill_index = matched_rows.index[jp_has & wo_empty.values]
    if len(fill_index) > 0:
        out.loc[fill_index, "application_number"] = matched_rows.loc[fill_index, "application_number_jp"]

    # WO の表示用出願番号は保持しつつ、マッチングキーは JP 側出願番号に寄せる
    if "_pairing_key_override" not in out.columns:
        out["_pairing_key_override"] = ""
    override_index = matched_rows.index[jp_has]
    if len(override_index) > 0:
        out.loc[override_index, "_pairing_key_override"] = matched_rows.loc[override_index, "application_number_jp"].values

    if "_pairing_date_override" not in out.columns:
        out["_pairing_date_override"] = pd.NaT
    matched_dates = pd.to_datetime(merged.loc[matched, "application_date_jp"], errors="coerce")
    has_date = matched_dates.notna()
    if has_date.any():
        out.loc[matched_dates.index[has_date], "_pairing_date_override"] = matched_dates.loc[has_date].values

    matched_effect_mask = matched & ~effective_skip.reindex(merged.index, fill_value=False)

    # 常に全マッチ対象の JP A1 を削除する（WO がすでに再公表ルールで処理済みでも同様）
    matched_pairs_all = set(
        zip(merged.loc[matched, "accession_number"], merged.loc[matched, "_pub_body"])
    )
    jp_a1_indices = out.index[jp_a1_mask]
    jp_pub_body_vals = pub_body.reindex(jp_a1_indices)
    jp_accession_vals = out.loc[jp_a1_indices, "accession_number"]
    jp_to_drop = [
        idx
        for idx in jp_a1_indices
        if (jp_accession_vals.loc[idx], jp_pub_body_vals.loc[idx]) in matched_pairs_all
    ]
    if jp_to_drop:
        out = out.drop(index=jp_to_drop)

    # _country_priority_code は再公表ルール未適用の WO 行のみ更新する
    if not matched_effect_mask.any():
        return out

    matched_effect_index = merged.index[matched_effect_mask]
    out.loc[matched_effect_index, "_country_priority_code"] = "JP"

    return out


def _ensure_country_priority_code(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    country_upper = out["country_code"].fillna("").astype(str).str.upper()
    if "_country_priority_code" not in out.columns:
        out["_country_priority_code"] = country_upper
    else:
        out["_country_priority_code"] = out["_country_priority_code"].fillna("").astype(str).str.upper()
        empty_mask = out["_country_priority_code"].eq("")
        out.loc[empty_mask, "_country_priority_code"] = country_upper[empty_mask]
    return out


@lru_cache(maxsize=1)
def _load_republish_pct_set() -> set[str]:
    csv_path = Path(__file__).resolve().parents[2] / "data" / "republish.csv"
    if not csv_path.exists():
        return set()

    try:
        republish_df = pd.read_csv(csv_path, dtype=str).fillna("")
    except Exception:
        return set()

    if "repub_PCT" not in republish_df.columns:
        return set()

    values = republish_df["repub_PCT"].map(_normalize_publication_number)
    return {value for value in values if value}


def _normalize_publication_number(value: object) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _extract_publication_numeric_body(value: object) -> str:
    text = _normalize_publication_number(value)
    if len(text) < 3:
        return ""

    if text[:2] in {"JP", "WO"}:
        text = text[2:]

    text = re.sub(r"([A-Z]{1,2}\d{0,2})$", "", text)
    return "".join(re.findall(r"\d+", text))


def _pick_best_record(group: pd.DataFrame, number_col: str, date_col: str) -> pd.Series | None:
    candidates = group[group[number_col].fillna("").astype(str).str.strip() != ""]
    if candidates.empty:
        return None

    number_sort = _build_revision_sort_columns(candidates[number_col], "num")
    ranked_candidates = candidates.join(number_sort)

    ranked = ranked_candidates.sort_values(
        by=[date_col, "_num_base", "_num_revision", "_num_raw"],
        ascending=[False, True, True, True],
        na_position="last",
    )
    return ranked.iloc[0]


def _extract_no_acc(df: pd.DataFrame) -> pd.DataFrame:
    value_series = df["accession_number"].fillna("").astype(str).str.strip().str.lower()
    mask = value_series.isin(NO_ACC_TOKENS)
    return df[mask].copy()


def _apply_one_family_one_country(df: pd.DataFrame, country_priority: list[str]) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    country_col = "_country_priority_code" if "_country_priority_code" in df.columns else "country_code"

    family_key = df["family_id"].fillna("").replace("", pd.NA)
    with_key = df.copy()
    with_key["_family_key"] = family_key
    missing_mask = with_key["_family_key"].isna()
    with_key.loc[missing_mask, "_family_key"] = with_key.index.astype(str)[missing_mask]

    selected_frames: list[pd.DataFrame] = []
    for _, group in with_key.groupby("_family_key", dropna=False):
        countries = [c for c in group[country_col].fillna("").astype(str).str.upper().unique() if c]
        target_country = _choose_country(countries, country_priority)
        if not target_country:
            selected_frames.append(group)
            continue
        selected_frames.append(group[group[country_col].fillna("").astype(str).str.upper() == target_country])

    out = pd.concat(selected_frames, ignore_index=True)
    return out.drop(columns=["_family_key", "_country_priority_code"], errors="ignore")


def _assign_group_key(df: pd.DataFrame, column: str) -> pd.DataFrame:
    out = df.copy()
    if column == "application_number" and "_pairing_application_key" in out.columns:
        key = out["_pairing_application_key"].fillna("").astype(str).str.strip()
        raw_app = out["application_number"].fillna("").astype(str).str.strip()
        key = key.mask(key == "", raw_app)
    else:
        key = out[column].fillna("").astype(str).str.strip()

    fallback = out["family_id"].fillna("").astype(str).str.strip()
    key = key.mask(key == "", fallback)
    key = key.mask(key == "", out.index.astype(str))
    out["_group_key"] = key
    return out


def _select_representative(group: pd.DataFrame, config: SelectionConfig) -> pd.Series:
    primary_number_col = "registration_number" if config.priority_basis == "registration" else "publication_number"

    ranked = group.copy()
    has_primary = ranked[primary_number_col].fillna("").astype(str).str.strip() != ""
    ranked["_has_primary"] = has_primary.astype(int)
    # selected_patent_number と同じ国コードの行を優先する。
    # 例: selected_patent_number が JP... の場合は JP 行を優先。
    if config.priority_basis == "registration":
        selected_no = ranked["registration_number"].fillna("").astype(str).str.strip()
        fallback_no = ranked["publication_number"].fillna("").astype(str).str.strip()
    else:
        selected_no = ranked["publication_number"].fillna("").astype(str).str.strip()
        fallback_no = ranked["registration_number"].fillna("").astype(str).str.strip()
    selected_no = selected_no.mask(selected_no == "", fallback_no)
    selected_country = selected_no.map(_extract_country_from_number)
    row_country = ranked["country_code"].fillna("").astype(str).str.upper().str.strip()
    ranked["_country_matches_selected"] = (row_country == selected_country).astype(int)

    if "_rank_application_date" in ranked.columns:
        ranked["_rank_application_date"] = pd.to_datetime(ranked["_rank_application_date"], errors="coerce")
    else:
        ranked["_rank_application_date"] = pd.NaT

    if "_rank_publication_date" in ranked.columns:
        ranked["_rank_publication_date"] = pd.to_datetime(ranked["_rank_publication_date"], errors="coerce")
    else:
        ranked["_rank_publication_date"] = pd.to_datetime(ranked["publication_date"], errors="coerce")

    if "_rank_application_number_numeric" in ranked.columns:
        ranked["_rank_application_number_numeric"] = pd.to_numeric(
            ranked["_rank_application_number_numeric"], errors="coerce"
        )
    else:
        ranked["_rank_application_number_numeric"] = pd.NA

    ranked = ranked.join(_build_revision_sort_columns(ranked["publication_number"], "pub"))
    ranked = ranked.join(_build_revision_sort_columns(ranked["registration_number"], "reg"))
    # Kind codeリビジョンは比較キーに使わず、同一ベース番号内で最小のみ残す
    ranked = _filter_min_revision(ranked, "_pub_base", "_pub_revision")
    ranked = _filter_min_revision(ranked, "_reg_base", "_reg_revision")
    # 特許(0)を実案(1)より常に優先する
    ranked["_is_utility"] = ranked.apply(lambda row: 1 if _resolve_puab_for_row(row) in {"UA", "UB"} else 0, axis=1)

    ascending_date = config.date_policy == "earliest"

    ranked = ranked.sort_values(
        by=[
            "_is_utility",
            "_has_primary",
            "_country_matches_selected",
            "_rank_application_date",
            "_rank_publication_date",
            "_rank_application_number_numeric",
        ],
        ascending=[True, False, False, ascending_date, ascending_date, ascending_date],
        na_position="last",
    )

    return ranked.iloc[0]


def _build_revision_sort_columns(series: pd.Series, prefix: str) -> pd.DataFrame:
    normalized = series.fillna("").astype(str).str.strip().str.upper().str.replace(" ", "", regex=False)
    parsed = normalized.map(_parse_revision_sort_parts)

    out = pd.DataFrame(index=series.index)
    out[f"_{prefix}_base"] = parsed.map(lambda item: item[0])
    out[f"_{prefix}_revision"] = parsed.map(lambda item: item[1])
    out[f"_{prefix}_raw"] = normalized
    return out


def _parse_revision_sort_parts(value: str) -> tuple[str, int]:
    text = _normalize_publication_number(value)
    if text == "":
        return "", 999

    match = re.match(r"^(.*?)([A-Z]+)(\d+)$", text)
    if not match:
        return text, 999

    head, kind_symbol, revision = match.groups()
    if not re.search(r"\d", head):
        return text, 999

    return f"{head}{kind_symbol}", int(revision)


def _filter_min_revision(df: pd.DataFrame, base_col: str, rev_col: str) -> pd.DataFrame:
    """同一ベース番号内でリビジョン番号が最小の行のみを残す（ベース番号が空の行は対象外）。"""
    has_base = df[base_col].ne("")
    if not has_base.any():
        return df
    has_base_idx = df.index[has_base]
    min_rev = df.loc[has_base_idx, base_col].map(
        df.loc[has_base_idx].groupby(base_col)[rev_col].min()
    )
    keep_mask = pd.Series(True, index=df.index)
    keep_mask.loc[has_base_idx] = df.loc[has_base_idx, rev_col] == min_rev
    return df[keep_mask]


def _contains_exclude_status(value: str) -> bool:
    return any(token in value for token in EXCLUDE_STATUS_TOKENS)


def _contains_exclude_kind(value: str) -> bool:
    return any(token in value for token in EXCLUDE_KIND_TOKENS)


def _choose_country(countries: list[str], priority: list[str]) -> str:
    if not countries:
        return ""
    normalized = [c.upper() for c in countries]
    for candidate in [p.upper() for p in priority]:
        if candidate in normalized:
            return candidate
    return sorted(normalized)[0]


def _resolve_selected_patent_number(
    row: pd.Series,
    priority_basis: str,
    exclude_invalid: bool = False,
    status_lookup: dict[str, str] | None = None,
) -> str:
    reg_no = str(row.get("registration_number", "") or "").strip()
    pub_no = str(row.get("publication_number", "") or "").strip()

    if priority_basis == "registration":
        primary_no = reg_no
        fallback_no = pub_no
    else:
        primary_no = pub_no
        fallback_no = reg_no

    if exclude_invalid and primary_no:
        status_lookup = status_lookup or {}
        primary_status = str(status_lookup.get(primary_no, "") or "").strip().lower()
        fallback_status = str(status_lookup.get(fallback_no, "") or "").strip().lower()
        if _contains_exclude_status(primary_status) and fallback_no and not _contains_exclude_status(fallback_status):
            return fallback_no

    return primary_no or fallback_no


def _reorder_selected_columns(df: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        "country_code",
        "accession_number",
        "selected_patent_number",
        "publication_number",
        "registration_number",
        "タイトル（英語）",
        "タイトル - DWPI",
        "出願人/権利者",
        "譲受人 - DWPI",
        "publication_date",
        "application_number",
        "application_date",
        "優先権情報",
        "legal_status",
        "DWPI ファミリーメンバー",
        "五庁有効ファミリ",
        "五庁失効ファミリ",
        "その他ファミリ",
        "source_file",
        "language_of_publication",
    ]
    # kind 列は出力不要
    drop_cols = [c for c in ["kind"] if c in df.columns]
    df = df.drop(columns=drop_cols, errors="ignore")
    leading = [c for c in preferred if c in df.columns]
    trailing = [c for c in df.columns if c not in leading]
    return df[leading + trailing]


def _build_legal_status_lookup(df: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}

    for _, row in df.iterrows():
        status = str(row.get("legal_status", "") or "").strip()
        if not status:
            continue

        for col in ["publication_number", "registration_number"]:
            patent_no = str(row.get(col, "") or "").strip()
            if not patent_no:
                continue

            # 失効/Dead 状態は上書きしない（より強いシグナルとして保持）
            prev = lookup.get(patent_no)
            if prev is not None and _contains_exclude_status(prev.lower()):
                continue
            if _contains_exclude_status(status.lower()) or prev is None:
                lookup[patent_no] = status

    return lookup


def _build_publication_number_date_lookup(df: pd.DataFrame) -> dict[str, object]:
    lookup: dict[str, object] = {}
    if df.empty:
        return lookup

    publication_numbers = df["publication_number"].fillna("").astype(str).str.strip()
    publication_dates = pd.to_datetime(df["publication_date"], errors="coerce")

    for idx in df.index:
        publication_no = publication_numbers.at[idx]
        if not publication_no:
            continue

        publication_date = publication_dates.at[idx]
        prev_date = lookup.get(publication_no)
        if prev_date is None or pd.isna(prev_date):
            lookup[publication_no] = publication_date
            continue

        if publication_date is not None and not pd.isna(publication_date) and publication_date > prev_date:
            lookup[publication_no] = publication_date

    return lookup


def _build_patent_application_number_lookup(df: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}

    for _, row in df.iterrows():
        application_number = str(row.get("application_number", "") or "").strip()
        if not application_number:
            continue

        for col in ["publication_number", "registration_number"]:
            patent_no = str(row.get(col, "") or "").strip()
            if not patent_no:
                continue
            if patent_no not in lookup:
                lookup[patent_no] = application_number

    return lookup


def _extract_application_number_numeric(value: object) -> int | None:
    digits = "".join(re.findall(r"\d", str(value or "")))
    if not digits:
        return None
    return int(digits)


def _build_patent_publication_date_lookup(df: pd.DataFrame) -> dict[str, object]:
    lookup: dict[str, object] = {}

    for _, row in df.iterrows():
        publication_date = row.get("publication_date")
        for col in ["publication_number", "registration_number"]:
            patent_no = str(row.get(col, "") or "").strip()
            if not patent_no:
                continue

            prev_date = lookup.get(patent_no)
            if prev_date is None or pd.isna(prev_date):
                lookup[patent_no] = publication_date
                continue

            if publication_date is not None and not pd.isna(publication_date) and publication_date > prev_date:
                lookup[patent_no] = publication_date

    return lookup


def _build_patent_application_date_lookup(df: pd.DataFrame) -> dict[str, object]:
    lookup: dict[str, object] = {}

    for _, row in df.iterrows():
        application_date = row.get("application_date")
        for col in ["publication_number", "registration_number"]:
            patent_no = str(row.get(col, "") or "").strip()
            if not patent_no:
                continue

            prev_date = lookup.get(patent_no)
            if prev_date is None or pd.isna(prev_date):
                lookup[patent_no] = application_date
                continue

            if application_date is not None and not pd.isna(application_date) and application_date > prev_date:
                lookup[patent_no] = application_date

    return lookup


def _resolve_application_date_from_selected_patent(selected: pd.DataFrame, lookup: dict[str, object]) -> pd.DataFrame:
    out = selected.copy()

    def _resolve(row: pd.Series) -> object:
        own_date = row.get("application_date")
        if own_date is not None and not pd.isna(own_date):
            return own_date
        selected_no = str(row.get("selected_patent_number", "") or "").strip()
        if selected_no and selected_no in lookup:
            return lookup[selected_no]
        return own_date

    out["application_date"] = out.apply(_resolve, axis=1)
    return out


def _resolve_publication_date_from_selected_patent(selected: pd.DataFrame, lookup: dict[str, object]) -> pd.DataFrame:
    out = selected.copy()

    def _resolve(row: pd.Series) -> object:
        selected_no = str(row.get("selected_patent_number", "") or "").strip()
        if selected_no and selected_no in lookup:
            return lookup[selected_no]
        return row.get("publication_date")

    out["publication_date"] = out.apply(_resolve, axis=1)
    return out


def _append_additional_output_columns(selected: pd.DataFrame, canonical_df: pd.DataFrame) -> pd.DataFrame:
    out = selected.copy()
    if out.empty or canonical_df.empty:
        for col in [
            "タイトル（英語）",
            "タイトル - DWPI",
            "出願人/権利者",
            "譲受人 - DWPI",
            "優先権情報",
            "DWPI ファミリーメンバー",
            "五庁有効ファミリ",
            "五庁失効ファミリ",
            "その他ファミリ",
        ]:
            out[col] = ""
        return out

    patent_lookup, accession_app_lookup = _build_source_row_lookup(canonical_df)

    title_en: list[str] = []
    title_dwpi: list[str] = []
    assignee_dwpi: list[str] = []
    applicant_rights: list[str] = []
    priority_info: list[str] = []
    family_members: list[str] = []
    five_alive: list[str] = []
    five_dead: list[str] = []
    family_other: list[str] = []

    for _, row in out.iterrows():
        source_row = _resolve_source_row(row, patent_lookup, accession_app_lookup)
        if source_row is None:
            title_en.append("")
            title_dwpi.append("")
            assignee_dwpi.append("")
            applicant_rights.append("")
            priority_info.append("")
            family_members.append("")
            five_alive.append("")
            five_dead.append("")
            family_other.append("")
            continue

        title_en.append(_as_text(source_row.get("title_english", "")))
        title_dwpi.append(_as_text(source_row.get("title_dwpi", "")))
        assignee_dwpi.append(_as_text(source_row.get("assignee_dwpi", "")))
        applicant_rights.append(_compose_applicant_rights_holder(source_row))
        priority_info.append(_pair_priority_info(source_row.get("priority_number", ""), source_row.get("priority_date", "")))
        family_members.append(_as_text(source_row.get("dwpi_family_members", "")))

        alive_text, dead_text, other_text = _split_family_members_by_status(
            source_row.get("dwpi_family_members_status", "")
        )
        five_alive.append(alive_text)
        five_dead.append(dead_text)
        family_other.append(other_text)

    out["タイトル（英語）"] = title_en
    out["タイトル - DWPI"] = title_dwpi
    out["出願人/権利者"] = applicant_rights
    out["譲受人 - DWPI"] = assignee_dwpi
    out["優先権情報"] = priority_info
    out["DWPI ファミリーメンバー"] = family_members
    out["五庁有効ファミリ"] = five_alive
    out["五庁失効ファミリ"] = five_dead
    out["その他ファミリ"] = family_other
    return out


def _build_source_row_lookup(canonical_df: pd.DataFrame) -> tuple[dict[str, dict[str, object]], dict[tuple[str, str], dict[str, object]]]:
    patent_lookup: dict[str, dict[str, object]] = {}
    accession_app_lookup: dict[tuple[str, str], dict[str, object]] = {}

    for _, row in canonical_df.iterrows():
        row_dict = row.to_dict()
        accession = _as_text(row_dict.get("accession_number", ""))
        app_no = _as_text(row_dict.get("application_number", ""))
        if accession or app_no:
            key = (accession, app_no)
            if key not in accession_app_lookup:
                accession_app_lookup[key] = row_dict

        for col in ["publication_number", "registration_number"]:
            patent_no = _as_text(row_dict.get(col, ""))
            if patent_no and patent_no not in patent_lookup:
                patent_lookup[patent_no] = row_dict

    return patent_lookup, accession_app_lookup


def _resolve_source_row(
    selected_row: pd.Series,
    patent_lookup: dict[str, dict[str, object]],
    accession_app_lookup: dict[tuple[str, str], dict[str, object]],
) -> dict[str, object] | None:
    selected_no = _as_text(selected_row.get("selected_patent_number", ""))
    if selected_no and selected_no in patent_lookup:
        return patent_lookup[selected_no]

    for col in ["publication_number", "registration_number"]:
        patent_no = _as_text(selected_row.get(col, ""))
        if patent_no and patent_no in patent_lookup:
            return patent_lookup[patent_no]

    accession = _as_text(selected_row.get("accession_number", ""))
    app_no = _as_text(selected_row.get("application_number", ""))
    key = (accession, app_no)
    return accession_app_lookup.get(key)


def _compose_applicant_rights_holder(source_row: dict[str, object]) -> str:
    for col in ["assignee_standardized", "assignee_applicant", "assignee_dwpi"]:
        raw = _as_text(source_row.get(col, ""))
        if not raw:
            continue

        candidates = _split_pipe_values(raw)
        cleaned: list[str] = []
        for candidate in candidates:
            core = candidate.split(",", 1)[0].strip()
            if not core:
                continue
            if _contains_cjk(core):
                continue
            cleaned.append(core)

        joined = _join_unique_non_empty(cleaned)
        if joined:
            return joined

    return ""


def _pair_priority_info(priority_numbers: object, priority_dates: object) -> str:
    numbers = _split_pipe_values(priority_numbers)
    dates = _split_pipe_values(priority_dates)
    if not numbers or not dates:
        return ""

    pairs: list[str] = []
    for number, date_text in zip(numbers, dates):
        date_value = pd.to_datetime(date_text, errors="coerce")
        normalized_date = date_value.strftime("%Y-%m-%d") if not pd.isna(date_value) else date_text
        pairs.append(f"{number}({normalized_date})")

    return _join_unique_non_empty(pairs)


def _split_family_members_by_status(status_text: object) -> tuple[str, str, str]:
    alive_members: list[str] = []
    dead_members: list[str] = []
    other_members: list[str] = []

    for token in _split_pipe_values(status_text):
        member_no, status = _extract_family_member_and_status(token)
        if not member_no:
            continue

        country = _extract_country_from_number(member_no)
        status_lower = status.lower()
        if country in FIVE_OFFICE_COUNTRIES and status_lower in {"alive", "indeterminate"}:
            alive_members.append(member_no)
        elif country in FIVE_OFFICE_COUNTRIES and status_lower == "dead":
            dead_members.append(member_no)
        else:
            other_members.append(member_no)

    return (
        _join_unique_non_empty(alive_members),
        _join_unique_non_empty(dead_members),
        _join_unique_non_empty(other_members),
    )


def _extract_family_member_and_status(token: str) -> tuple[str, str]:
    text = str(token or "").strip()
    if not text:
        return "", ""

    match = re.match(r"^(.*?)\s+([A-Za-z]+)$", text)
    if match:
        member_no = match.group(1).strip()
        status = match.group(2).strip()
        return member_no, status

    return text, ""


def _split_pipe_values(value: object) -> list[str]:
    text = _as_text(value)
    if not text:
        return []
    return [item.strip() for item in text.split("|") if item.strip()]


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]", value))


def _join_unique_non_empty(values: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        v = str(value or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        ordered.append(v)
    return " | ".join(ordered)


def _resolve_selected_legal_status(row: pd.Series, lookup: dict[str, str]) -> str:
    selected_no = str(row.get("selected_patent_number", "") or "").strip()
    if selected_no and selected_no in lookup:
        return lookup[selected_no]
    return str(row.get("legal_status", "") or "").strip()
