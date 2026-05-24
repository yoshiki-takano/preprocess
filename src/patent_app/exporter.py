from __future__ import annotations

import io
import re
import posixpath
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows

OUTPUT_COLUMN_RENAME: dict[str, str] = {
    "country_code": "国名コード",
    "accession_number": "ファミリ番号",
    "selected_patent_number": "公報番号",
    "publication_number": "公開番号",
    "registration_number": "登録番号",
    "publication_date": "公報発行日",
    "application_number": "出願番号",
    "application_date": "出願日",
    "legal_status": "無効/有効",
    "source_file": "ソースファイル",
    "language_of_publication": "公報言語",
}


def build_xlsx_bytes(
    selected_df: pd.DataFrame,
    no_acc_df: pd.DataFrame | None = None,
    template_bytes: bytes | None = None,
    keep_vba: bool = False,
) -> bytes:
    if template_bytes:
        wb = _load_template_workbook(template_bytes, keep_vba)
    else:
        wb = Workbook()

    results_ws = _get_or_create_sheet(wb, "SearchData")
    _write_dataframe(results_ws, selected_df.rename(columns=OUTPUT_COLUMN_RENAME))

    if "NoAcc" in wb.sheetnames:
        del wb["NoAcc"]

    if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
        del wb["Sheet"]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()


def _get_or_create_sheet(wb: Workbook, title: str):
    if title in wb.sheetnames:
        return wb[title]
    return wb.create_sheet(title)


def _write_dataframe(ws, df: pd.DataFrame) -> None:
    ws.delete_rows(1, ws.max_row)
    for row in dataframe_to_rows(df, index=False, header=True):
        ws.append(row)


def _load_template_workbook(template_bytes: bytes, keep_vba: bool) -> Workbook:
    try:
        return load_workbook(io.BytesIO(template_bytes), keep_vba=keep_vba)
    except KeyError as exc:
        missing_item = _extract_missing_archive_item(str(exc))
        if not missing_item:
            raise

        repaired_bytes = _remove_broken_relationships(template_bytes, missing_item)
        try:
            return load_workbook(io.BytesIO(repaired_bytes), keep_vba=keep_vba)
        except Exception:
            # Some templates contain chained drawing/image relationship corruption.
            # Fall back to a clean workbook so export can still complete.
            return Workbook()


def _extract_missing_archive_item(error_message: str) -> str:
    match = re.search(r"'([^']+)'", error_message)
    if not match:
        return ""
    return match.group(1).lstrip("/")


def _remove_broken_relationships(template_bytes: bytes, missing_item: str) -> bytes:
    missing_norm = missing_item.lstrip("/")
    in_buffer = io.BytesIO(template_bytes)
    out_buffer = io.BytesIO()

    with zipfile.ZipFile(in_buffer, "r") as zin, zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)

            if not info.filename.endswith(".rels"):
                zout.writestr(info, data)
                continue

            fixed = _strip_invalid_relationship_entries(data, info.filename, missing_norm)
            zout.writestr(info, fixed)

    out_buffer.seek(0)
    return out_buffer.read()


def _strip_invalid_relationship_entries(xml_bytes: bytes, rels_path: str, missing_item: str) -> bytes:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return xml_bytes

    namespace = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    base_dir = _resolve_relationship_base_dir(rels_path)
    removed = False

    for rel in list(root.findall(f"{namespace}Relationship")):
        if rel.get("TargetMode") == "External":
            continue

        target = str(rel.get("Target", "") or "").strip()
        if not target:
            continue

        resolved = _resolve_target_path(base_dir, target)
        if resolved == missing_item or target.upper().endswith("/NULL") or target.upper() == "NULL":
            root.remove(rel)
            removed = True

    if not removed:
        return xml_bytes

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _resolve_relationship_base_dir(rels_path: str) -> str:
    parent = posixpath.dirname(rels_path)
    if parent.endswith("/_rels"):
        parent = parent[: -len("/_rels")]

    filename = posixpath.basename(rels_path)
    if filename.endswith(".rels"):
        source_part = filename[: -len(".rels")]
    else:
        source_part = filename

    source_path = posixpath.join(parent, source_part)
    return posixpath.dirname(source_path)


def _resolve_target_path(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(base_dir, target)).lstrip("/")
