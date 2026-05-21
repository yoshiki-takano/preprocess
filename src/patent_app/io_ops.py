from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .config import CANONICAL_COLUMNS, EXCLUDE_STATUS_TOKENS

HEADER_HINTS = {
    "dwpiaccessionnumber",
    "dwpiアクセッション番号",
    "publicationnumber",
    "公報番号",
    "公開番号",
    "applicationnumber",
    "出願番号",
    "applicationdate",
    "出願日",
    "publicationdate",
    "公報発行日",
    "公開日",
    "prioritydate",
    "優先権主張日",
    "prioritynumber",
    "優先権主張番号",
    "title(english)",
    "タイトル（英語）",
    "title-dwpi",
    "譲受人 - 標準化",
    "譲受人/出願人",
    "譲受人 - dwpi",
    "dwpiファミリーメンバー",
    "dwpiファミリーメンバー有効/無効",
}


def load_dataframe(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    lower_name = file_name.lower()
    if lower_name.endswith(".csv"):
        for encoding in ("utf-8-sig", "cp932", "utf-8"):
            try:
                raw_df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding, header=None)
                return _promote_detected_header(raw_df)
            except UnicodeDecodeError:
                continue
        raise ValueError("CSV encoding could not be decoded.")
    if lower_name.endswith(".xlsx") or lower_name.endswith(".xlsm"):
        raw_df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl", header=None)
        return _promote_detected_header(raw_df)
    raise ValueError("Unsupported file type. Use .xlsx, .xlsm, or .csv")


def resolve_column_mapping(
    source_columns: list[str],
    user_mapping: dict[str, str] | None = None,
) -> dict[str, str]:
    user_mapping = user_mapping or {}
    normalized_lookup = {_normalize_name(c): c for c in source_columns}
    resolved: dict[str, str] = {}

    for canonical, aliases in CANONICAL_COLUMNS.items():
        user_selected = user_mapping.get(canonical)
        if user_selected and user_selected in source_columns:
            resolved[canonical] = user_selected
            continue

        for alias in aliases:
            key = _normalize_name(alias)
            if key in normalized_lookup:
                resolved[canonical] = normalized_lookup[key]
                break

    return resolved


def canonicalize_dataframe(
    df: pd.DataFrame,
    mapping: dict[str, str],
) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)

    for canonical in CANONICAL_COLUMNS:
        source = mapping.get(canonical)
        out[canonical] = df[source] if source else pd.NA

    for col in [
        "application_number",
        "publication_number",
        "registration_number",
        "legal_status",
        "kind",
        "accession_number",
        "family_id",
        "title_english",
        "title_dwpi",
        "assignee_standardized",
        "assignee_applicant",
        "assignee_dwpi",
        "priority_number",
        "priority_date",
        "dwpi_family_members",
        "dwpi_family_members_status",
    ]:
        out[col] = out[col].map(_normalize_text)

    # Country code is always generated from the publication number prefix.
    out["country_code"] = out["publication_number"].map(_extract_country_from_publication)

    out["application_date"] = pd.to_datetime(out["application_date"], errors="coerce").dt.date
    out["publication_date"] = pd.to_datetime(out["publication_date"], errors="coerce").dt.date

    out["family_id"] = out["family_id"].mask(
        out["family_id"].isna() | (out["family_id"] == ""), out["accession_number"]
    )

    out = _classify_pub_reg_by_kind_code(out)
    # legal_status は元の表記（Dead/Alive/Indeterminate 等）を保持するためバイナリ変換しない
    out["kind"] = out.apply(_derive_kind_code, axis=1)
    out = _normalize_kr_application_numbers(out)

    return out


def parse_country_priority(raw_value: str) -> list[str]:
    tokens = [v.strip().upper() for v in raw_value.split(",")]
    return [v for v in tokens if v]


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", str(value)).strip().lower()


def _normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _extract_country_from_publication(pub_number: str) -> str:
    if not pub_number:
        return ""
    match = re.match(r"^([A-Za-z]{2})", pub_number)
    return match.group(1).upper() if match else ""


@lru_cache(maxsize=1)
def _load_kind_code_lookup() -> dict[tuple[str, str], str]:
    csv_path = Path(__file__).resolve().parents[2] / "data" / "kind_code.csv"
    if not csv_path.exists():
        return {}

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    required = {"COUNTRY_CODE", "DWPI_KIND", "PUAB"}
    if not required.issubset(set(df.columns)):
        return {}

    lookup: dict[tuple[str, str], str] = {}
    for _, row in df.iterrows():
        country = str(row["COUNTRY_CODE"]).strip().upper()
        kind = str(row["DWPI_KIND"]).strip().upper()
        puab = str(row["PUAB"]).strip().upper()
        if not country or not kind or not puab:
            continue
        lookup[(country, kind)] = puab

    return lookup


def _extract_kind_code(doc_number: str) -> str:
    value = str(doc_number).strip().upper().replace(" ", "")
    if not value:
        return ""
    match = re.search(r"([A-Z]{1,2}\d{0,2})$", value)
    return match.group(1) if match else ""


def _derive_kind_code(row: pd.Series) -> str:
    pub_no = str(row.get("publication_number", "") or "").strip()
    reg_no = str(row.get("registration_number", "") or "").strip()
    base = pub_no or reg_no
    return _extract_kind_code(base)


def _to_binary_legal_status(value: Any) -> str:
    text = _normalize_text(value).lower()
    if any(token in text for token in EXCLUDE_STATUS_TOKENS):
        return "無効"
    return "有効"


def _classify_pub_reg_by_kind_code(df: pd.DataFrame) -> pd.DataFrame:
    lookup = _load_kind_code_lookup()
    if not lookup or df.empty:
        return df

    out = df.copy()

    for idx, row in out.iterrows():
        pub_num = row.get("publication_number", "")
        reg_num = row.get("registration_number", "")

        pub_num = str(pub_num).strip() if pd.notna(pub_num) else ""
        reg_num = str(reg_num).strip() if pd.notna(reg_num) else ""

        # If source contains only one number column, re-route by PUAB meaning.
        if pub_num and not reg_num:
            country = _extract_country_from_publication(pub_num)
            kind_code = _extract_kind_code(pub_num)
            puab = lookup.get((country, kind_code), "")
            if puab in {"PB", "UB"}:
                out.at[idx, "registration_number"] = pub_num
                out.at[idx, "publication_number"] = ""

        elif reg_num and not pub_num:
            country = _extract_country_from_publication(reg_num)
            kind_code = _extract_kind_code(reg_num)
            puab = lookup.get((country, kind_code), "")
            if puab in {"PA", "UA"}:
                out.at[idx, "publication_number"] = reg_num
                out.at[idx, "registration_number"] = ""

    return out


def _normalize_kr_application_numbers(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    country = out["country_code"].fillna("").astype(str).str.upper()
    kr_mask = country.eq("KR")
    if not kr_mask.any():
        return out

    app_year = pd.to_datetime(out["application_date"], errors="coerce").dt.year

    for idx in out.index[kr_mask]:
        app_no = str(out.at[idx, "application_number"] or "").strip().upper().replace(" ", "")
        if not app_no:
            continue

        puab = _resolve_row_puab(out.loc[idx])
        year = app_year.at[idx]
        if pd.isna(year):
            continue

        if puab in {"PA", "UA"} and int(year) >= 1998:
            out.at[idx, "application_number"] = re.sub(r"^(KR\d{4})07(\d{6,})$", r"\g<1>70\g<2>", app_no)
        elif puab in {"PB", "UB"} and int(year) <= 1997:
            out.at[idx, "application_number"] = re.sub(r"^(KR\d{4})70(\d{6,})$", r"\g<1>07\g<2>", app_no)

    return out


def _resolve_row_puab(row: pd.Series) -> str:
    lookup = _load_kind_code_lookup()
    if not lookup:
        return ""

    pub_no = str(row.get("publication_number", "") or "").strip()
    reg_no = str(row.get("registration_number", "") or "").strip()
    doc_no = pub_no or reg_no
    if not doc_no:
        return ""

    country = _extract_country_from_publication(doc_no)
    kind_code = _extract_kind_code(doc_no)
    return lookup.get((country, kind_code), "")


def _promote_detected_header(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return raw_df

    header_idx = _detect_header_row(raw_df)
    if header_idx is None:
        header_idx = 0

    header_values = raw_df.iloc[header_idx].tolist()
    columns = _build_unique_columns(header_values)

    data_df = raw_df.iloc[header_idx + 1 :].copy().reset_index(drop=True)
    data_df.columns = columns
    data_df = data_df.dropna(how="all").reset_index(drop=True)
    return data_df


def _detect_header_row(raw_df: pd.DataFrame) -> int | None:
    alias_hints = set(HEADER_HINTS)
    for aliases in CANONICAL_COLUMNS.values():
        alias_hints.update(_normalize_name(alias) for alias in aliases)

    best_idx: int | None = None
    best_score = 0
    scan_limit = min(len(raw_df), 20)

    for idx in range(scan_limit):
        row = raw_df.iloc[idx]
        score = 0
        for value in row.tolist():
            norm = _normalize_name(value)
            if not norm or norm == "none" or norm == "nan":
                continue
            if norm in alias_hints:
                score += 1
        if score > best_score:
            best_score = score
            best_idx = idx

    if best_score >= 1:
        return best_idx
    return None


def _build_unique_columns(header_values: list[Any]) -> list[str]:
    columns: list[str] = []
    seen: dict[str, int] = {}

    for idx, value in enumerate(header_values):
        name = _normalize_text(value)
        if not name or name.lower() in {"none", "nan"}:
            name = f"Unnamed: {idx}"

        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0

        columns.append(name)

    return columns
