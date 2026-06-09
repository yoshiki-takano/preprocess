from __future__ import annotations

import re

import pandas as pd

from .config import NO_ACC_TOKENS


def annotate_no_acc_family_possibility_memo(
    selected_df: pd.DataFrame,
    reference_df: pd.DataFrame,
) -> pd.DataFrame:
    """Annotate MEMO1 for no-accession selected rows when a likely family accession exists."""
    if selected_df.empty:
        return selected_df.copy()

    out = selected_df.copy()
    if "MEMO1" not in out.columns:
        out["MEMO1"] = ""

    if reference_df.empty or "publication_number" not in out.columns or "accession_number" not in out.columns:
        return out

    accession_lookup = _build_accession_lookup_by_pub_key(reference_df)
    if not accession_lookup:
        return out

    accession_series = out["accession_number"].fillna("").astype(str).str.strip().str.lower()
    no_acc_mask = accession_series.isin(NO_ACC_TOKENS)
    if not no_acc_mask.any():
        return out

    publications = out["publication_number"].fillna("").astype(str)
    memo_values: list[str] = []
    for idx, publication in publications.items():
        if not bool(no_acc_mask.loc[idx]):
            memo_values.append(out.at[idx, "MEMO1"])
            continue

        country, numeric, kind = _extract_publication_parts(publication)
        if not country or not numeric or not kind:
            memo_values.append(out.at[idx, "MEMO1"])
            continue

        candidates = accession_lookup.get((country, numeric), [])
        matched_accession = ""
        for candidate_kind, candidate_accession in candidates:
            if not candidate_kind or candidate_kind == kind:
                continue
            matched_accession = candidate_accession
            break

        if matched_accession:
            memo_values.append(f"アクセッション番号 {matched_accession} のファミリの可能性あり")
        else:
            memo_values.append(out.at[idx, "MEMO1"])

    out["MEMO1"] = pd.Series(memo_values, index=out.index)
    return out


def _build_accession_lookup_by_pub_key(reference_df: pd.DataFrame) -> dict[tuple[str, str], list[tuple[str, str]]]:
    if "publication_number" not in reference_df.columns or "accession_number" not in reference_df.columns:
        return {}

    publication_series = reference_df["publication_number"].fillna("").astype(str)
    accession_series = reference_df["accession_number"].fillna("").astype(str).str.strip()

    out: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for publication, accession in zip(publication_series, accession_series):
        if not accession or accession.lower() in NO_ACC_TOKENS:
            continue

        country, numeric, kind = _extract_publication_parts(publication)
        if not country or not numeric:
            continue

        key = (country, numeric)
        if key not in out:
            out[key] = []
        out[key].append((kind, accession))

    return out


def _extract_publication_parts(publication_number: object) -> tuple[str, str, str]:
    text = str(publication_number or "").strip().upper().replace(" ", "")
    if len(text) < 3:
        return "", "", ""

    country_match = re.match(r"^([A-Z]{2})", text)
    country = country_match.group(1) if country_match else ""
    body = text[2:] if country else text

    kind_match = re.search(r"([A-Z]{1,2}\d{0,2})$", body)
    kind = kind_match.group(1) if kind_match else ""
    if kind:
        body = body[: -len(kind)]

    numeric = "".join(re.findall(r"\d+", body))
    return country, numeric, kind
