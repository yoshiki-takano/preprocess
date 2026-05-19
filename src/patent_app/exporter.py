from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows


def build_xlsx_bytes(
    selected_df: pd.DataFrame,
    no_acc_df: pd.DataFrame,
    template_bytes: bytes | None = None,
) -> bytes:
    if template_bytes:
        wb = load_workbook(io.BytesIO(template_bytes))
    else:
        wb = Workbook()

    results_ws = _get_or_create_sheet(wb, "Results")
    _write_dataframe(results_ws, selected_df)

    no_acc_ws = _get_or_create_sheet(wb, "NoAcc")
    _write_dataframe(no_acc_ws, no_acc_df)

    if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 2:
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
