from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from patent_app.exporter import TEMPLATE_OUTPUT_COLUMNS, build_xlsx_bytes
from patent_app.io_ops import canonicalize_dataframe, load_dataframe, resolve_column_mapping


def test_excel_header_is_detected_from_second_row() -> None:
    source = pd.DataFrame(
        [
            ["Patent Export, 2026-05-13 02:09:46 +0000", None, None, None],
            ["DWPI アクセッション番号", "公報番号", "出願日", "出願番号"],
            ["1991325232", "JP8500001A", "1991-04-11", "JP1991508026A"],
        ]
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        source.to_excel(writer, index=False, header=False)

    df = load_dataframe("sample.xlsx", buf.getvalue())

    assert list(df.columns)[:4] == [
        "DWPI アクセッション番号",
        "公報番号",
        "出願日",
        "出願番号",
    ]
    assert df.iloc[0]["公報番号"] == "JP8500001A"


def test_country_code_is_generated_from_publication_number() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["EP1234567A1"],
            "国コード": ["JP"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    assert out.iloc[0]["country_code"] == "EP"


def test_publication_date_is_mapped_from_koho_hakkobi() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["JP8500001A"],
            "公報発行日": ["1996-01-09"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    assert out.iloc[0]["publication_date"] == date(1996, 1, 9)


def test_legal_status_is_binary_valid_invalid() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["JP8500001A", "JP6000001B2"],
            "法的状況": ["active", "失効"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    # 元の表記をそのまま保持する
    assert out.iloc[0]["legal_status"] == "active"
    assert out.iloc[1]["legal_status"] == "失効"


def test_dead_status_is_normalized_to_invalid() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["JP2008293226A"],
            "法的状況": ["Dead"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    # 元の表記「Dead」をそのまま保持する
    assert out.iloc[0]["legal_status"] == "Dead"


def test_mukou_yukou_column_is_mapped_to_legal_status() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["JP5502366A"],
            "無効/有効": ["Dead"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    # 元の表記「Dead」をそのまま保持する
    assert out.iloc[0]["legal_status"] == "Dead"


def test_kind_is_kind_code_suffix() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["JP8500001A", "JP6000001B2"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    assert out.iloc[0]["kind"] == "A"
    assert out.iloc[1]["kind"] == "B2"


def test_kind_code_routes_registration_from_publication_column() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["JP6000001B2"],
            "出願番号": ["JP1984258790A"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    assert out.iloc[0]["publication_number"] == ""
    assert out.iloc[0]["registration_number"] == "JP6000001B2"


def test_kind_code_routes_publication_from_registration_column() -> None:
    source = pd.DataFrame(
        {
            "登録番号": ["JP8500001A"],
            "出願番号": ["JP1991508026A"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    assert out.iloc[0]["publication_number"] == "JP8500001A"
    assert out.iloc[0]["registration_number"] == ""


def test_kr_publication_application_number_07_is_converted_to_70_after_1998() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["KR2001123456A"],
            "出願番号": ["KR200107123456"],
            "出願日": ["2001-10-01"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    assert out.iloc[0]["application_number"] == "KR200170123456"


def test_kr_registration_application_number_70_is_converted_to_07_before_1998() -> None:
    source = pd.DataFrame(
        {
            "公報番号": ["KR1995123456B"],
            "出願番号": ["KR199570123456"],
            "出願日": ["1995-03-20"],
        }
    )

    mapping = resolve_column_mapping(list(source.columns))
    out = canonicalize_dataframe(source, mapping)

    assert out.iloc[0]["application_number"] == "KR199507123456"


def test_template_export_uses_screener_column_schema() -> None:
    selected = pd.DataFrame(
        [
            {
                "selected_patent_number": "JP20240001A1",
                "publication_number": "JP20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "application_number": "JP20230001",
                "application_date": pd.Timestamp("2023-01-15"),
                "priority_number": "PRIO-1",
                "priority_date": pd.Timestamp("2022-12-01"),
                "dwpi_family_members": "JP20240001A1|US20240001A1",
                "accession_number": "ACC-001",
                "language_of_publication": "JA",
                "title_english": "Sample title",
                "title_dwpi": "DWPI title",
                "assignee_applicant": "Applicant A",
                "source_file": "sample.xlsx",
            }
        ]
    )

    template_buffer = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "SearchData"
    ws.append(["placeholder"])
    wb.save(template_buffer)

    output_bytes = build_xlsx_bytes(selected, template_bytes=template_buffer.getvalue())
    result_wb = load_workbook(io.BytesIO(output_bytes))
    result_ws = result_wb["SearchData"]

    headers = [cell.value for cell in result_ws[1]]
    assert headers == TEMPLATE_OUTPUT_COLUMNS

    values = [cell.value for cell in result_ws[2]]
    assert values[0] == 1
    assert values[1] is None
    assert values[4] == "JP20240001A1"
    assert values[11] == "JP20240001A1"
    assert values[14] == "JA"
    assert values[15] == "Sample title"
    assert values[16] == "DWPI title"
    assert values[17] == "Applicant A"
    assert values[28] == "ACC-001"
    assert values[29].date() == date(2024, 2, 1)
    assert values[30] == "JP20230001"
    assert values[31].date() == date(2023, 1, 15)
    assert values[32] == "PRIO-1"
    assert values[33].date() == date(2022, 12, 1)
    assert values[34] == "JP20240001A1|US20240001A1"
    assert values[37] == "sample.xlsx"
    assert values[2] is None
    assert values[12] is None
    assert values[18] is None
