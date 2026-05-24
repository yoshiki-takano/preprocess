from __future__ import annotations

import io

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
        wb = load_workbook(io.BytesIO(template_bytes), keep_vba=keep_vba)
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
