from __future__ import annotations

from datetime import date
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from patent_app.models import SelectionConfig
from patent_app.pipeline import run_selection_pipeline
from patent_app.io_ops import INTERNAL_PUBLICATION_URL_COLUMN, INTERNAL_RAW_PUBLICATION_COLUMN


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "application_number": "A1",
                "application_date": pd.Timestamp("2023-12-01"),
                "publication_number": "JP20240001",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DW1",
                "family_id": "F1",
                "country_code": "JP",
            },
            {
                "application_number": "A2",
                "application_date": pd.Timestamp("2024-01-15"),
                "publication_number": "US20240002",
                "registration_number": "USR2",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.Timestamp("2025-02-01"),
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DW1",
                "family_id": "F1",
                "country_code": "US",
            },
            {
                "application_number": "A3",
                "application_date": pd.Timestamp("2024-02-10"),
                "publication_number": "JP20240003",
                "registration_number": "JPR3",
                "publication_date": pd.Timestamp("2024-03-01"),
                "registration_date": pd.Timestamp("2025-03-01"),
                "legal_status": "失効",
                "kind": "特許",
                "accession_number": "",
                "family_id": "F2",
                "country_code": "JP",
            },
            {
                "application_number": "A4",
                "application_date": pd.Timestamp("2024-03-10"),
                "publication_number": "CN20240004U",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-04-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "実案",
                "accession_number": "-",
                "family_id": "F3",
                "country_code": "CN",
            },
        ]
    )


def test_exclusion_and_no_acc_order() -> None:
    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US"],
        exclude_invalid=True,
        exclude_utility=True,
    )
    selected, no_acc = run_selection_pipeline(_df(), cfg)

    assert "A3" not in selected["application_number"].values
    assert "A4" not in selected["application_number"].values
    assert len(no_acc) == 0


def test_default_exclusion_is_off() -> None:
    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US"],
    )
    selected, _ = run_selection_pipeline(_df(), cfg)

    assert "A3" in selected["application_number"].values


def test_date_exclusion_default_is_off() -> None:
    default_cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US"],
    )
    explicit_no_filter_cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US"],
        start_date_field="application_date",
        end_date_field="publication_date",
        start_date=None,
        end_date=None,
    )

    selected_default, _ = run_selection_pipeline(_df(), default_cfg)
    selected_explicit, _ = run_selection_pipeline(_df(), explicit_no_filter_cfg)

    assert selected_default["application_number"].tolist() == selected_explicit["application_number"].tolist()


def test_date_exclusion_independent_start_and_end_fields() -> None:
    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US"],
        start_date_field="application_date",
        start_date=date(2024, 1, 1),
        end_date_field="publication_date",
        end_date=date(2024, 3, 15),
    )
    selected, _ = run_selection_pipeline(_df(), cfg)

    assert set(selected["application_number"].tolist()) == {"A2", "A3"}


def test_country_priority_then_registration_priority() -> None:
    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["US", "JP"],
        exclude_invalid=True,
        exclude_utility=True,
    )
    selected, _ = run_selection_pipeline(_df(), cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["application_number"] == "A2"
    assert selected.iloc[0]["selected_patent_number"] == "USR2"


def test_date_policy_earliest_with_publication_priority() -> None:
    df = _df()
    extra = {
        "application_number": "A5",
        "publication_number": "US20230001",
        "registration_number": "",
        "publication_date": pd.Timestamp("2023-01-01"),
        "registration_date": pd.NaT,
        "legal_status": "active",
        "kind": "特許",
        "accession_number": "DW1",
        "family_id": "F1",
        "country_code": "US",
    }
    df = pd.concat([df, pd.DataFrame([extra])], ignore_index=True)

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="earliest",
        country_priority=["US", "JP"],
        exclude_invalid=True,
        exclude_utility=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert selected.iloc[0]["application_number"] == "A2"
    assert selected.iloc[0]["selected_patent_number"] == "US20240002"


def test_pairs_publication_and_registration_by_application_number() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP1",
                "publication_number": "JP20240001A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
            },
            {
                "application_number": "APP1",
                "publication_number": "",
                "registration_number": "JP7654321B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2025-06-01"),
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "JP20240001A"
    assert selected.iloc[0]["registration_number"] == "JP7654321B2"


def test_selected_registration_uses_registration_hyperlink_url() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP1",
                "publication_number": "US20250299024A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2025-09-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "US",
                INTERNAL_PUBLICATION_URL_COLUMN: "https://example.com/pub/US20250299024A1",
            },
            {
                "application_number": "APP1",
                "publication_number": "",
                "registration_number": "US12619815B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2026-03-01"),
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "US",
                INTERNAL_PUBLICATION_URL_COLUMN: "https://example.com/reg/US12619815B2",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["US"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "US12619815B2"
    assert selected.iloc[0][INTERNAL_PUBLICATION_URL_COLUMN] == "https://example.com/reg/US12619815B2"


def test_selected_registration_uses_registration_pdf_copy_text() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP1",
                "publication_number": "US20250299024A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2025-09-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "US",
                "PDF コピー": "https://example.com/pdf/pub/US20250299024A1",
            },
            {
                "application_number": "APP1",
                "publication_number": "",
                "registration_number": "US12619815B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2026-03-01"),
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "US",
                "PDF コピー": "https://example.com/pdf/reg/US12619815B2",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["US"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "US12619815B2"
    assert selected.iloc[0]["PDF コピー"] == "https://example.com/pdf/reg/US12619815B2"


def test_selected_registration_uses_registration_front_page_urls() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP1",
                "publication_number": "US20250299024A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2025-09-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "US",
                "フロントページ イメージ": "https://example.com/front-image/pub/US20250299024A1",
                "フロントページ図": "https://example.com/front-figure/pub/US20250299024A1",
            },
            {
                "application_number": "APP1",
                "publication_number": "",
                "registration_number": "US12619815B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2026-03-01"),
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "US",
                "フロントページ イメージ": "https://example.com/front-image/reg/US12619815B2",
                "フロントページ図": "https://example.com/front-figure/reg/US12619815B2",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["US"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "US12619815B2"
    assert selected.iloc[0]["フロントページ イメージ"] == "https://example.com/front-image/reg/US12619815B2"
    assert selected.iloc[0]["フロントページ図"] == "https://example.com/front-figure/reg/US12619815B2"


def test_selected_registration_uses_registration_abstract_english() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP1",
                "publication_number": "JP2023545994A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2023-11-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
                "抄録（英語）": "",
            },
            {
                "application_number": "APP1",
                "publication_number": "",
                "registration_number": "JP07807441B2",
                "publication_date": pd.Timestamp("2026-01-27"),
                "registration_date": pd.Timestamp("2026-01-27"),
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
                "抄録（英語）": "Registration-side abstract text",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "JP07807441B2"
    assert selected.iloc[0]["抄録（英語）"] == "Registration-side abstract text"


def test_blank_value_is_filled_from_paired_counterpart_row() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP1",
                "publication_number": "JP2023545994A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2023-11-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
                "請求項 (英語)": "Claim text from publication row",
            },
            {
                "application_number": "APP1",
                "publication_number": "",
                "registration_number": "JP07807441B2",
                "publication_date": pd.Timestamp("2026-01-27"),
                "registration_date": pd.Timestamp("2026-01-27"),
                "legal_status": "active",
                "kind": "特許",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
                "請求項 (英語)": "",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "JP07807441B2"
    assert selected.iloc[0]["請求項 (英語)"] == "Claim text from publication row"


def test_selected_column_order_starts_with_requested_fields() -> None:
    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["US", "JP"],
    )
    selected, _ = run_selection_pipeline(_df(), cfg)

    assert list(selected.columns[:3]) == [
        "country_code",
        "accession_number",
        "selected_patent_number",
    ]
    assert "_has_primary" not in selected.columns
    assert "_rank_date" not in selected.columns
    assert "registration_date" not in selected.columns


def test_no_acc_does_not_include_registration_date() -> None:
    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP"],
    )
    input_df = pd.DataFrame(
        [
            {
                "application_number": "N1",
                "publication_number": "JP20240001A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-01"),
                "registration_date": pd.Timestamp("2025-01-01"),
                "legal_status": "active",
                "kind": "A",
                "accession_number": "",
                "family_id": "F1",
                "country_code": "JP",
            }
        ]
    )

    _, no_acc = run_selection_pipeline(input_df, cfg)
    assert no_acc.empty


def test_no_acc_token_rows_are_not_collapsed_into_single_family() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_A",
                "application_date": pd.Timestamp("2024-01-10"),
                "publication_number": "JP20240001A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "-",
                "family_id": "-",
                "country_code": "JP",
            },
            {
                "application_number": "APP_B",
                "application_date": pd.Timestamp("2024-01-11"),
                "publication_number": "US20240002A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "-",
                "family_id": "-",
                "country_code": "US",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 2
    assert set(selected["application_number"].tolist()) == {"APP_A", "APP_B"}


def test_no_accession_row_gets_family_hint_memo1_when_kind_only_differs() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_NOACC",
                "application_date": pd.Timestamp("2024-01-10"),
                "publication_number": "JP20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "",
                "family_id": "F_NOACC",
                "country_code": "JP",
            },
            {
                "application_number": "APP_WITH_ACC",
                "application_date": pd.Timestamp("2024-01-11"),
                "publication_number": "JP20240001B2",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "ACC-123",
                "family_id": "F_WITH_ACC",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    no_acc_row = selected.loc[selected["application_number"] == "APP_NOACC"].iloc[0]
    assert no_acc_row["MEMO1"] == "ACC-123 のファミリの可能性あり"


def test_empty_family_id_rows_with_same_application_number_are_one_family() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_SHARED",
                "application_date": pd.Timestamp("2024-01-10"),
                "publication_number": "JP20240001A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "",
                "family_id": "",
                "country_code": "JP",
            },
            {
                "application_number": "APP_SHARED",
                "application_date": pd.Timestamp("2024-01-10"),
                "publication_number": "",
                "registration_number": "JP7654321B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2024-03-01"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "",
                "family_id": "",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["application_number"] == "APP_SHARED"


def test_legal_status_is_resolved_from_selected_patent_number() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APPX",
                "publication_number": "JP20240001A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "PUB_STATUS",
                "kind": "A",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
            },
            {
                "application_number": "APPX",
                "publication_number": "",
                "registration_number": "JP7654321B2",
                "publication_date": pd.Timestamp("2024-01-02"),
                "registration_date": pd.Timestamp("2025-06-01"),
                "legal_status": "REG_STATUS",
                "kind": "B2",
                "accession_number": "DWX",
                "family_id": "FX",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert selected.iloc[0]["selected_patent_number"] == "JP7654321B2"
    assert selected.iloc[0]["legal_status"] == "REG_STATUS"


def test_jp_a1_is_treated_as_jp_by_default_for_country_priority() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "JP1",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "DWZ",
                "family_id": "FZ",
                "country_code": "JP",
            },
            {
                "application_number": "US1",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20240002A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-15"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "DWZ",
                "family_id": "FZ",
                "country_code": "US",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["application_number"] == "JP1"


def test_republish_wo_can_be_treated_as_jp_and_complemented_from_jpx() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "WO1989000044A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2019-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_REPUB",
                "family_id": "F_REPUB",
                "country_code": "WO",
            },
            {
                "application_number": "APP_FROM_JPX_OLD",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "JP2017543435X",
                "registration_number": "",
                "publication_date": pd.Timestamp("2018-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "X",
                "accession_number": "ACC_REPUB",
                "family_id": "F_REPUB",
                "country_code": "JP",
            },
            {
                "application_number": "APP_FROM_JPX_NEW",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "JP2018543435X",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "X",
                "accession_number": "ACC_REPUB",
                "family_id": "F_REPUB",
                "country_code": "JP",
            },
            {
                "application_number": "US1",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "US20240002A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-15"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_REPUB",
                "family_id": "F_REPUB",
                "country_code": "US",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
        treat_wo_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO1989000044A1"
    assert selected.iloc[0]["application_number"] == "APP_FROM_JPX_OLD"
    assert pd.to_datetime(selected.iloc[0]["publication_date"]).date() == date(2018, 1, 1)


def test_republish_wo_can_pair_with_jp_registration_on_registration_priority() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "WO1989000044A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2019-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_REPUB_PAIR",
                "family_id": "F_REPUB_PAIR",
                "country_code": "WO",
            },
            {
                "application_number": "APP_FROM_JPX",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "JP2017543435X",
                "registration_number": "",
                "publication_date": pd.Timestamp("2018-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "X",
                "accession_number": "ACC_REPUB_PAIR",
                "family_id": "F_REPUB_PAIR",
                "country_code": "JP",
            },
            {
                "application_number": "APP_FROM_JPX",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "",
                "registration_number": "JP7654321B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2021-10-06"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "ACC_REPUB_PAIR",
                "family_id": "F_REPUB_PAIR",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
        treat_wo_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO1989000044A1"
    assert selected.iloc[0]["registration_number"] == "JP7654321B2"
    assert selected.iloc[0]["selected_patent_number"] == "JP7654321B2"


def test_republish_wo_with_own_appno_pairs_pub_with_jp_registration() -> None:
    """WO が自前の出願番号を持つ場合でも JP X 経由でペアリングが補完される（PCT 国内移行ケース）"""
    df = pd.DataFrame(
        [
            {
                "application_number": "WO2016JP78476A",
                "application_date": pd.Timestamp("2016-09-27"),
                "publication_number": "WO1989000044A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2017-04-06"),
                "registration_date": pd.NaT,
                "legal_status": "Dead",
                "kind": "A1",
                "accession_number": "ACC_PCT_PAIR",
                "family_id": "F_PCT_PAIR",
                "country_code": "WO",
            },
            {
                "application_number": "APP_FROM_JPX",
                "application_date": pd.Timestamp("2016-09-27"),
                "publication_number": "JP2017543435X",
                "registration_number": "",
                "publication_date": pd.Timestamp("2018-07-19"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "X",
                "accession_number": "ACC_PCT_PAIR",
                "family_id": "F_PCT_PAIR",
                "country_code": "JP",
            },
            {
                "application_number": "APP_FROM_JPX",
                "application_date": pd.Timestamp("2016-09-27"),
                "publication_number": "",
                "registration_number": "JP06945450B2",
                "publication_date": pd.Timestamp("2021-10-06"),
                "registration_date": pd.Timestamp("2021-10-06"),
                "legal_status": "Alive",
                "kind": "B2",
                "accession_number": "ACC_PCT_PAIR",
                "family_id": "F_PCT_PAIR",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
        treat_wo_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["registration_number"] == "JP06945450B2"
    assert selected.iloc[0]["publication_number"] == "WO1989000044A1"
    assert selected.iloc[0]["selected_patent_number"] == "JP06945450B2"
    assert selected.iloc[0]["application_number"] == "APP_FROM_JPX"


def test_excluded_rows_can_be_pairing_counterparts_but_are_not_selected() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_PAIR",
                "application_date": pd.Timestamp("2020-01-01"),
                "publication_number": "WO2020001234A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-08-01"),
                "registration_date": pd.NaT,
                "legal_status": "Dead",
                "kind": "A1",
                "accession_number": "ACC_EXCLUDED_PAIR",
                "family_id": "F_EXCLUDED_PAIR",
                "country_code": "WO",
            },
            {
                "application_number": "APP_PAIR",
                "application_date": pd.Timestamp("2020-01-01"),
                "publication_number": "",
                "registration_number": "JP7000000B2",
                "publication_date": pd.Timestamp("2023-05-01"),
                "registration_date": pd.Timestamp("2023-05-01"),
                "legal_status": "Alive",
                "kind": "B2",
                "accession_number": "ACC_EXCLUDED_PAIR",
                "family_id": "F_EXCLUDED_PAIR",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "WO"],
        exclude_invalid=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "JP7000000B2"
    assert selected.iloc[0]["publication_number"] == "WO2020001234A1"
    assert selected.iloc[0]["registration_number"] == "JP7000000B2"
    assert selected.iloc[0]["legal_status"] == "Alive"


def test_leading_republish_wo_can_be_treated_as_jp_and_get_application_number_from_jp_a1() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2024123456A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-03-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_LEADING",
                "family_id": "F_LEADING",
                "country_code": "WO",
            },
            {
                "application_number": "APP_FROM_JPA1",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP2024123456A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_LEADING",
                "family_id": "F_LEADING",
                "country_code": "JP",
            },
            {
                "application_number": "US1",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20240002A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-15"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_LEADING",
                "family_id": "F_LEADING",
                "country_code": "US",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
        treat_wo_prior_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO2024123456A1"
    assert selected.iloc[0]["application_number"] == "APP_FROM_JPA1"


def test_leading_republish_wo_application_number_is_preserved_when_original_exists() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "WO_ORIGINAL_APPNO",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2024123456A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-03-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_LEADING_OVERWRITE",
                "family_id": "F_LEADING_OVERWRITE",
                "country_code": "WO",
            },
            {
                "application_number": "APP_FROM_JPA1",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP2024123456A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_LEADING_OVERWRITE",
                "family_id": "F_LEADING_OVERWRITE",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
        treat_wo_prior_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO2024123456A1"
    assert selected.iloc[0]["application_number"] == "WO_ORIGINAL_APPNO"


def test_leading_republish_jp_a1_is_excluded_even_when_it_has_later_publication_date() -> None:
    """JP A1 should be dropped when its number body matches a WO A1, even if JP A1 has a later date."""
    df = pd.DataFrame(
        [
            {
                "application_number": "WO_APP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2024999999A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-01-15"),  # earlier
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_JP_DROP",
                "family_id": "F_JP_DROP",
                "country_code": "WO",
            },
            {
                "application_number": "JP_APP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP2024999999A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-06-01"),  # later — would win without dropping
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_JP_DROP",
                "family_id": "F_JP_DROP",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
        treat_wo_prior_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO2024999999A1"
    assert selected.iloc[0]["application_number"] == "WO_APP"


def test_republish_rule_takes_precedence_when_both_toggles_are_enabled() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "WO1989000044A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2019-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BOTH",
                "family_id": "F_BOTH",
                "country_code": "WO",
            },
            {
                "application_number": "APP_FROM_JPX",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "JP2017543435X",
                "registration_number": "",
                "publication_date": pd.Timestamp("2019-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "X",
                "accession_number": "ACC_BOTH",
                "family_id": "F_BOTH",
                "country_code": "JP",
            },
            {
                "application_number": "APP_FROM_JPA1",
                "application_date": pd.Timestamp("2017-05-01"),
                "publication_number": "JP1989000044A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2018-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BOTH",
                "family_id": "F_BOTH",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "WO"],
        treat_wo_republication_as_jp=True,
        treat_wo_prior_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO1989000044A1"
    assert selected.iloc[0]["application_number"] == "APP_FROM_JPX"


def test_prior_republish_overwrite_runs_even_when_republish_skip_applies() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "WO_ORIGINAL_APP",
                "application_date": pd.Timestamp("2019-11-22"),
                "publication_number": "WO2020137282A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-07-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_SKIP",
                "family_id": "F_SKIP",
                "country_code": "WO",
            },
            {
                "application_number": "US_APP",
                "application_date": pd.Timestamp("2021-06-18"),
                "publication_number": "US20220109017A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2022-04-07"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_SKIP",
                "family_id": "F_SKIP",
                "country_code": "US",
            },
            {
                "application_number": "JP_APP_A1",
                "application_date": pd.Timestamp("2019-11-22"),
                "publication_number": "JP2020137282A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2021-11-11"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_SKIP",
                "family_id": "F_SKIP",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="earliest",
        country_priority=["JP", "US"],
        treat_wo_republication_as_jp=True,
        treat_wo_prior_republication_as_jp=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    wo_row = selected.loc[selected["publication_number"].eq("WO2020137282A1")].iloc[0]
    assert wo_row["application_number"] == "WO_ORIGINAL_APP"


def test_jp_x_is_excluded_before_country_priority() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "JPAPP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP2017543435X",
                "registration_number": "",
                "publication_date": pd.Timestamp("2018-07-19"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "X",
                "accession_number": "ACC1",
                "family_id": "F1",
                "country_code": "JP",
            },
            {
                "application_number": "JPAPP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "",
                "registration_number": "JP06945450B2",
                "publication_date": pd.Timestamp("2021-10-06"),
                "registration_date": pd.Timestamp("2021-10-06"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "ACC1",
                "family_id": "F1",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "EP", "WO", "CN", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] != "JP2017543435X"
    assert selected.iloc[0]["selected_patent_number"] == "JP06945450B2"


def test_us_pairs_by_last_six_application_digits_and_application_date() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "US202017065173A",
                "application_date": pd.Timestamp("2020-10-07"),
                "publication_number": "US20210017434A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2021-01-21"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "DWUS1",
                "family_id": "FUS1",
                "country_code": "US",
            },
            {
                "application_number": "US17065173A",
                "application_date": pd.Timestamp("2020-10-07"),
                "publication_number": "",
                "registration_number": "US11306235B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2022-04-19"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "DWUS1",
                "family_id": "FUS1",
                "country_code": "US",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["US"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "US20210017434A1"
    assert selected.iloc[0]["registration_number"] == "US11306235B2"


def test_us_falls_back_to_raw_application_number_when_date_is_missing() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "US202017065173A",
                "application_date": pd.NaT,
                "publication_number": "US20210017434A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2021-01-21"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "DWUS2",
                "family_id": "FUS2",
                "country_code": "US",
            },
            {
                "application_number": "US17065173A",
                "application_date": pd.NaT,
                "publication_number": "",
                "registration_number": "US11306235B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2022-04-19"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "DWUS2",
                "family_id": "FUS2",
                "country_code": "US",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["US"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 2


def test_revision_prefers_smaller_publication_revision_for_all_selection_combinations() -> None:
    base_rows = [
        {
            "application_number": "APP_REV",
            "application_date": pd.Timestamp("2024-01-01"),
            "publication_number": "WO2024123456A10",
            "registration_number": "WO9999999B1",
            "publication_date": pd.Timestamp("2024-05-01"),
            "registration_date": pd.Timestamp("2025-01-01"),
            "legal_status": "active",
            "kind": "A10",
            "accession_number": "ACC_REV_PUB",
            "family_id": "F_REV_PUB",
            "country_code": "WO",
        },
        {
            "application_number": "APP_REV",
            "application_date": pd.Timestamp("2024-01-01"),
            "publication_number": "WO2024123456A2",
            "registration_number": "WO9999999B1",
            "publication_date": pd.Timestamp("2024-05-01"),
            "registration_date": pd.Timestamp("2025-01-01"),
            "legal_status": "active",
            "kind": "A2",
            "accession_number": "ACC_REV_PUB",
            "family_id": "F_REV_PUB",
            "country_code": "WO",
        },
    ]

    for mode in ["family", "application"]:
        for priority_basis in ["registration", "publication"]:
            for date_policy in ["latest", "earliest"]:
                cfg = SelectionConfig(
                    mode=mode,
                    priority_basis=priority_basis,
                    date_policy=date_policy,
                    country_priority=["WO", "JP", "US"],
                )
                selected, _ = run_selection_pipeline(pd.DataFrame(base_rows), cfg)

                assert len(selected) == 1
                assert selected.iloc[0]["publication_number"] == "WO2024123456A2"


def test_revision_prefers_smaller_registration_revision_for_all_selection_combinations() -> None:
    base_rows = [
        {
            "application_number": "APP_REV_REG",
            "application_date": pd.Timestamp("2024-01-01"),
            "publication_number": "WO2024123456A1",
            "registration_number": "WO7777777B10",
            "publication_date": pd.Timestamp("2024-05-01"),
            "registration_date": pd.Timestamp("2025-01-01"),
            "legal_status": "active",
            "kind": "B10",
            "accession_number": "ACC_REV_REG",
            "family_id": "F_REV_REG",
            "country_code": "WO",
        },
        {
            "application_number": "APP_REV_REG",
            "application_date": pd.Timestamp("2024-01-01"),
            "publication_number": "WO2024123456A1",
            "registration_number": "WO7777777B2",
            "publication_date": pd.Timestamp("2024-05-01"),
            "registration_date": pd.Timestamp("2025-01-01"),
            "legal_status": "active",
            "kind": "B2",
            "accession_number": "ACC_REV_REG",
            "family_id": "F_REV_REG",
            "country_code": "WO",
        },
    ]

    for mode in ["family", "application"]:
        for priority_basis in ["registration", "publication"]:
            for date_policy in ["latest", "earliest"]:
                cfg = SelectionConfig(
                    mode=mode,
                    priority_basis=priority_basis,
                    date_policy=date_policy,
                    country_priority=["WO", "JP", "US"],
                )
                selected, _ = run_selection_pipeline(pd.DataFrame(base_rows), cfg)

                assert len(selected) == 1
                assert selected.iloc[0]["registration_number"] == "WO7777777B2"


def test_pairing_prefers_smaller_registration_revision_when_dates_tie() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "PAIR_REV",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "",
                "registration_number": "WO8888888B10",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2025-01-01"),
                "legal_status": "active",
                "kind": "B10",
                "accession_number": "ACC_PAIR_REV",
                "family_id": "F_PAIR_REV",
                "country_code": "WO",
            },
            {
                "application_number": "PAIR_REV",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "",
                "registration_number": "WO8888888B2",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2025-01-01"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "ACC_PAIR_REV",
                "family_id": "F_PAIR_REV",
                "country_code": "WO",
            },
            {
                "application_number": "PAIR_REV",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2024999999A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-05-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_PAIR_REV",
                "family_id": "F_PAIR_REV",
                "country_code": "WO",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["WO"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["registration_number"] == "WO8888888B2"


def test_publication_date_is_resolved_from_selected_patent_number() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_DATE",
                "application_date": pd.Timestamp("2020-02-21"),
                "publication_number": "JP2020189179A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-09-24"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_DATE",
                "family_id": "F_DATE",
                "country_code": "JP",
            },
            {
                "application_number": "APP_DATE",
                "application_date": pd.Timestamp("2020-02-21"),
                "publication_number": "",
                "registration_number": "JP07524160B2",
                "publication_date": pd.Timestamp("2024-07-29"),
                "registration_date": pd.Timestamp("2024-07-29"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "ACC_DATE",
                "family_id": "F_DATE",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="earliest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "JP07524160B2"
    assert pd.to_datetime(selected.iloc[0]["publication_date"]) == pd.Timestamp("2024-07-29")


def test_exclude_invalid_avoids_dead_selected_patent_number() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "WO2020JP7047A",
                "application_date": pd.Timestamp("2020-02-21"),
                "publication_number": "WO2020189179A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-09-24"),
                "registration_date": pd.NaT,
                "legal_status": "Dead",
                "kind": "A1",
                "accession_number": "ACC_EX_INVALID_SEL",
                "family_id": "F_EX_INVALID_SEL",
                "country_code": "WO",
            },
            {
                "application_number": "JP2021507126A",
                "application_date": pd.Timestamp("2020-02-21"),
                "publication_number": "",
                "registration_number": "JP07524160B2",
                "publication_date": pd.Timestamp("2024-07-29"),
                "registration_date": pd.Timestamp("2024-07-29"),
                "legal_status": "Alive",
                "kind": "B2",
                "accession_number": "ACC_EX_INVALID_SEL",
                "family_id": "F_EX_INVALID_SEL",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "WO"],
        exclude_invalid=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "JP07524160B2"
    assert selected.iloc[0]["publication_number"] == ""
    assert selected.iloc[0]["registration_number"] == "JP07524160B2"


def test_date_filter_avoids_out_of_range_selected_patent_number() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_DATE_RANGE",
                "application_date": pd.Timestamp("2020-02-21"),
                "publication_number": "WO2020189179A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-09-24"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A1",
                "accession_number": "ACC_DATE_RANGE",
                "family_id": "F_DATE_RANGE",
                "country_code": "WO",
            },
            {
                "application_number": "APP_DATE_RANGE",
                "application_date": pd.Timestamp("2021-09-20"),
                "publication_number": "",
                "registration_number": "JP07524160B2",
                "publication_date": pd.Timestamp("2024-07-29"),
                "registration_date": pd.Timestamp("2024-07-29"),
                "legal_status": "Alive",
                "kind": "B2",
                "accession_number": "ACC_DATE_RANGE",
                "family_id": "F_DATE_RANGE",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "WO"],
        start_date_field="publication_date",
        start_date=date(2024, 1, 1),
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO2020189179A1"
    assert selected.iloc[0]["registration_number"] == "JP07524160B2"
    assert selected.iloc[0]["selected_patent_number"] == "JP07524160B2"


def test_application_date_is_resolved_from_selected_patent_number() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_DATE_APP",
                "application_date": pd.Timestamp("2020-02-21"),
                "publication_number": "JP2020189179A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-09-24"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_DATE_APP",
                "family_id": "F_DATE_APP",
                "country_code": "JP",
            },
            {
                "application_number": "APP_DATE_APP",
                "application_date": pd.Timestamp("2021-09-20"),
                "publication_number": "",
                "registration_number": "JP07524160B2",
                "publication_date": pd.Timestamp("2024-07-29"),
                "registration_date": pd.Timestamp("2024-07-29"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "ACC_DATE_APP",
                "family_id": "F_DATE_APP",
                "country_code": "JP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="earliest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["selected_patent_number"] == "JP07524160B2"
    assert pd.to_datetime(selected.iloc[0]["application_date"]) == pd.Timestamp("2020-02-21")


def test_additional_output_columns_are_generated_from_source_columns() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_NEW",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US202500001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2025-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_NEW",
                "family_id": "F_NEW",
                "country_code": "US",
                "title_english": "An optical spin injection structure",
                "title_dwpi": "Optical spin injection structure",
                "assignee_standardized": "ABC corporation,US | 艾比西公司,US",
                "assignee_applicant": "Fallback Applicant,US",
                "assignee_dwpi": "ABC corp DWPI",
                "priority_number": "GB201214619A | WO2013EP67161A",
                "priority_date": "2012-08-16 | 2013-08-16",
                "dwpi_family_members": "GB2504977A | WO2014027092A2 | EP2885820A2 | US20150187971A1",
                "dwpi_family_members_status": "GB2504977A Alive | US20150187971A1 Alive | CN104854709B Dead | EP2885820B1 Indeterminate | RU2672642C2 Alive",
            }
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["US", "JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    row = selected.iloc[0]
    assert row["タイトル（英語）"] == "An optical spin injection structure"
    assert row["タイトル - DWPI"] == "Optical spin injection structure"
    assert row["譲受人 - DWPI"] == "ABC corp DWPI"
    assert row["譲受人 - 標準化"] == "ABC corporation,US | 艾比西公司,US"
    assert row["出願人/権利者"] == "ABC corporation"
    assert row["優先権主張番号"] == "GB201214619A | WO2013EP67161A"
    assert row["優先権主張日"] == "2012-08-16 | 2013-08-16"
    assert row["優先権情報"] == "GB201214619A(2012-08-16) | WO2013EP67161A(2013-08-16)"
    assert row["DWPI ファミリーメンバー"] == "GB2504977A | WO2014027092A2 | EP2885820A2 | US20150187971A1"
    assert row["五庁有効ファミリ"] == "US20150187971A1 | EP2885820B1"
    assert row["五庁失効ファミリ"] == "CN104854709B"
    assert row["その他ファミリ"] == "GB2504977A | RU2672642C2"


def test_priority_info_pairs_up_to_shorter_length() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_PAIR",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP202500001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2025-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_PAIR",
                "family_id": "F_PAIR",
                "country_code": "JP",
                "priority_number": "P1 | P2 | P3",
                "priority_date": "2020-01-01 | 2020-02-01",
            }
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["優先権情報"] == "P1(2020-01-01) | P2(2020-02-01)"


def test_patent_is_preferred_over_utility_model_in_same_family() -> None:
    """同じファミリに特許と実案が混在する場合、特許(PB)を優先して選択する。"""
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_MIXED",
                "application_date": pd.Timestamp("2023-01-01"),
                "publication_number": "",
                "registration_number": "DE202300001U1",  # 実案 (DE U1 → UB)
                "publication_date": pd.Timestamp("2023-06-01"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "U1",
                "accession_number": "ACC_UTIL",
                "family_id": "F_MIXED",
                "country_code": "DE",
            },
            {
                "application_number": "APP_MIXED",
                "application_date": pd.Timestamp("2023-01-01"),
                "publication_number": "",
                "registration_number": "DE10202300001B4",  # 特許 (DE B4 → PB)
                "publication_date": pd.Timestamp("2024-01-01"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "B4",
                "accession_number": "ACC_UTIL",
                "family_id": "F_MIXED",
                "country_code": "DE",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["DE"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    # 特許 (B4) が選ばれ、実案 (U1) は選ばれないこと
    assert "B4" in str(selected.iloc[0]["selected_patent_number"])


def test_source_file_aggregates_by_application_when_accession_is_blank() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "JP2020552640A",
                "application_date": pd.Timestamp("2019-10-30"),
                "publication_number": "WO2020085513A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-04-30"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A1",
                "accession_number": "202035917C",
                "family_id": "F_SRC",
                "country_code": "WO",
                "source_file": "no_acc_eng.xlsx",
            },
            {
                "application_number": "JP2020552640A",
                "application_date": pd.Timestamp("2019-10-30"),
                "publication_number": "WO2020085513A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2020-04-30"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A1",
                "accession_number": "202035917C",
                "family_id": "F_SRC",
                "country_code": "WO",
                "source_file": "no_acc_jp.xlsx",
            },
            {
                "application_number": "JP2020552640A",
                "application_date": pd.Timestamp("2019-10-30"),
                "publication_number": "",
                "registration_number": "JP07858523B2",
                "publication_date": pd.Timestamp("2024-01-01"),
                "registration_date": pd.Timestamp("2024-01-01"),
                "legal_status": "Alive",
                "kind": "B2",
                "accession_number": "",
                "family_id": "F_SRC",
                "country_code": "JP",
                "source_file": "no_acc_jp.xlsx",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "WO"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    source_files = set(str(selected.iloc[0]["source_file"]).split(" | "))
    assert source_files == {"no_acc_eng.xlsx", "no_acc_jp.xlsx"}


def test_country_priority_equal_group_keeps_all_same_rank_countries_when_jp_absent() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_US",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ",
                "family_id": "F_EQ",
                "country_code": "US",
            },
            {
                "application_number": "APP_WO",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ",
                "family_id": "F_EQ",
                "country_code": "WO",
            },
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ",
                "family_id": "F_EQ",
                "country_code": "EP",
            },
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN20240001A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_EQ",
                "family_id": "F_EQ",
                "country_code": "CN",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US=WO=EP", "CN", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 3
    assert set(selected["country_code"].tolist()) == {"US", "WO", "EP"}


def test_country_priority_duplicate_uses_first_occurrence() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_JP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_DUP",
                "family_id": "F_DUP",
                "country_code": "JP",
            },
            {
                "application_number": "APP_US",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_DUP",
                "family_id": "F_DUP",
                "country_code": "US",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "KR", "JP"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["country_code"] == "JP"


def test_family_mode_outputs_multiple_rows_for_same_rank_country_group() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_US",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ_FAM",
                "family_id": "F_EQ_FAM",
                "country_code": "US",
            },
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ_FAM",
                "family_id": "F_EQ_FAM",
                "country_code": "EP",
            },
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN20240001A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_EQ_FAM",
                "family_id": "F_EQ_FAM",
                "country_code": "CN",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US=EP", "WO", "CN", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 2
    assert set(selected["country_code"].tolist()) == {"US", "EP"}


def test_family_mode_equal_group_still_collapses_same_country_to_one_row() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_US_1",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ_FAM_US",
                "family_id": "F_EQ_FAM_US",
                "country_code": "US",
            },
            {
                "application_number": "APP_US_2",
                "application_date": pd.Timestamp("2024-01-02"),
                "publication_number": "US20240002A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-10"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ_FAM_US",
                "family_id": "F_EQ_FAM_US",
                "country_code": "US",
            },
            {
                "application_number": "APP_EP_1",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP20240001A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_EQ_FAM_US",
                "family_id": "F_EQ_FAM_US",
                "country_code": "EP",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US=EP", "WO", "CN", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 2
    assert set(selected["country_code"].tolist()) == {"US", "EP"}


def test_basic_priority_selects_first_dwpi_family_member_when_higher_ranks_absent() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_BASIC_1",
                "family_id": "F_BASIC_1",
                "country_code": "CN",
                "dwpi_family_members": "US20160375671A1 | WO2016210366A1 | KR2018028457A | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP3314640A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_1",
                "family_id": "F_BASIC_1",
                "country_code": "EP",
                "dwpi_family_members": "US20160375671A1 | WO2016210366A1 | KR2018028457A | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_US_BASIC",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20160375671A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_1",
                "family_id": "F_BASIC_1",
                "country_code": "US",
                "dwpi_family_members": "US20160375671A1 | WO2016210366A1 | KR2018028457A | EP3314640A1 | CN108140599A",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "BASIC"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "US20160375671A1"


def test_basic_priority_falls_back_to_next_country_when_basic_member_row_missing() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_BASIC_2",
                "family_id": "F_BASIC_2",
                "country_code": "CN",
                "dwpi_family_members": "US20160375671A1 | WO2016210366A1 | KR2018028457A | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP3314640A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_2",
                "family_id": "F_BASIC_2",
                "country_code": "EP",
                "dwpi_family_members": "US20160375671A1 | WO2016210366A1 | KR2018028457A | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_WO",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2016210366A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_2",
                "family_id": "F_BASIC_2",
                "country_code": "WO",
                "dwpi_family_members": "US20160375671A1 | WO2016210366A1 | KR2018028457A | EP3314640A1 | CN108140599A",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "BASIC", "WO", "CN"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO2016210366A1"


def test_basic_priority_uses_next_dwpi_member_when_first_member_is_excluded() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_US",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20160375671A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "Dead",
                "kind": "A1",
                "accession_number": "ACC_BASIC_EXCL_1",
                "family_id": "F_BASIC_EXCL_1",
                "country_code": "US",
                "dwpi_family_members": "US20160375671A1 | JP2021114643A | WO2016210366A1 | CN108140599A",
            },
            {
                "application_number": "APP_JP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP2021114643A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A",
                "accession_number": "ACC_BASIC_EXCL_1",
                "family_id": "F_BASIC_EXCL_1",
                "country_code": "JP",
                "dwpi_family_members": "US20160375671A1 | JP2021114643A | WO2016210366A1 | CN108140599A",
            },
            {
                "application_number": "APP_WO",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2016210366A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A1",
                "accession_number": "ACC_BASIC_EXCL_1",
                "family_id": "F_BASIC_EXCL_1",
                "country_code": "WO",
                "dwpi_family_members": "US20160375671A1 | JP2021114643A | WO2016210366A1 | CN108140599A",
            },
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-04"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A",
                "accession_number": "ACC_BASIC_EXCL_1",
                "family_id": "F_BASIC_EXCL_1",
                "country_code": "CN",
                "dwpi_family_members": "US20160375671A1 | JP2021114643A | WO2016210366A1 | CN108140599A",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "KR"],
        exclude_invalid=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "JP2021114643A"


def test_jp_us_basic_priority_order_in_family_mode() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_BASIC_3",
                "family_id": "F_BASIC_3",
                "country_code": "CN",
                "dwpi_family_members": "CN108140599A | WO2016210366A1 | KR2018028457A",
            },
            {
                "application_number": "APP_US",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20160375671A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_3",
                "family_id": "F_BASIC_3",
                "country_code": "US",
                "dwpi_family_members": "CN108140599A | WO2016210366A1 | KR2018028457A",
            },
            {
                "application_number": "APP_JP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "JP2024001234A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_BASIC_3",
                "family_id": "F_BASIC_3",
                "country_code": "JP",
                "dwpi_family_members": "CN108140599A | WO2016210366A1 | KR2018028457A",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "BASIC"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["country_code"] == "JP"


def test_basic_does_not_override_ranked_country_when_listed_country_exists() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_US_BASIC",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20160375671A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_4",
                "family_id": "F_BASIC_4",
                "country_code": "US",
                "dwpi_family_members": "US20160375671A1 | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP3314640A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_4",
                "family_id": "F_BASIC_4",
                "country_code": "EP",
                "dwpi_family_members": "US20160375671A1 | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_BASIC_4",
                "family_id": "F_BASIC_4",
                "country_code": "CN",
                "dwpi_family_members": "US20160375671A1 | EP3314640A1 | CN108140599A",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "US", "WO", "CN", "EP", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["country_code"] == "US"


def test_family_registration_latest_prefers_us_over_ep_even_when_us_is_basic_row() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "US16814179A",
                "application_date": pd.Timestamp("2020-03-10"),
                "publication_number": "US20210288100A1",
                "registration_number": "US11251219B2",
                "publication_date": pd.Timestamp("2022-02-15"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "B2",
                "accession_number": "2021A6683Y",
                "family_id": "2021A6683Y",
                "country_code": "US",
                "dwpi_family_members": "US20210288100A1 | EP3879573A1 | EP3879573B1",
            },
            {
                "application_number": "EP2021161779A",
                "application_date": pd.Timestamp("2021-03-10"),
                "publication_number": "EP3879573A1",
                "registration_number": "EP3879573B1",
                "publication_date": pd.Timestamp("2022-12-21"),
                "registration_date": pd.NaT,
                "legal_status": "Indeterminate",
                "kind": "B1",
                "accession_number": "2021A6683Y",
                "family_id": "2021A6683Y",
                "country_code": "EP",
                "dwpi_family_members": "US20210288100A1 | EP3879573A1 | EP3879573B1",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US", "WO", "CN", "EP", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["country_code"] == "US"
    assert selected.iloc[0]["selected_patent_number"] == "US11251219B2"


def test_basic_is_used_as_last_resort_even_when_not_listed_in_country_priority() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_BASIC",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20160375671A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_LAST",
                "family_id": "F_BASIC_LAST",
                "country_code": "US",
                "dwpi_family_members": "US20160375671A1 | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP3314640A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_BASIC_LAST",
                "family_id": "F_BASIC_LAST",
                "country_code": "EP",
                "dwpi_family_members": "US20160375671A1 | EP3314640A1 | CN108140599A",
            },
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_BASIC_LAST",
                "family_id": "F_BASIC_LAST",
                "country_code": "CN",
                "dwpi_family_members": "US20160375671A1 | EP3314640A1 | CN108140599A",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "US20160375671A1"


def test_when_basic_unavailable_falls_back_to_publication_number_selection() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_B",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP3314640A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A1",
                "accession_number": "ACC_PUB_FALLBACK",
                "family_id": "F_PUB_FALLBACK",
                "country_code": "EP",
                "dwpi_family_members": "",
            },
            {
                "application_number": "APP_A",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.NaT,
                "legal_status": "active",
                "kind": "A",
                "accession_number": "ACC_PUB_FALLBACK",
                "family_id": "F_PUB_FALLBACK",
                "country_code": "CN",
                "dwpi_family_members": "",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="publication",
        date_policy="latest",
        country_priority=["JP", "KR"],
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "CN108140599A"


def test_basic_mode_forces_publication_number_even_if_registration_priority_selected() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_US",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "US20210288100A1",
                "registration_number": "US11251219B2",
                "publication_date": pd.Timestamp("2024-02-01"),
                "registration_date": pd.Timestamp("2025-01-10"),
                "legal_status": "active",
                "kind": "B2",
                "accession_number": "ACC_BASIC_MODE_1",
                "family_id": "F_BASIC_MODE_1",
                "country_code": "US",
                "dwpi_family_members": "US20210288100A1 | EP3879573A1",
            },
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP3879573A1",
                "registration_number": "EP3879573B1",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.Timestamp("2025-01-20"),
                "legal_status": "active",
                "kind": "B1",
                "accession_number": "ACC_BASIC_MODE_1",
                "family_id": "F_BASIC_MODE_1",
                "country_code": "EP",
                "dwpi_family_members": "US20210288100A1 | EP3879573A1",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["EP", "US"],
        use_basic_selection=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "US20210288100A1"
    assert selected.iloc[0]["selected_patent_number"] == "US20210288100A1"


def test_basic_mode_uses_publication_fallback_when_dwpi_members_are_empty() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_EP",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "EP3314640A1",
                "registration_number": "EP3314640B1",
                "publication_date": pd.Timestamp("2024-02-02"),
                "registration_date": pd.Timestamp("2025-01-10"),
                "legal_status": "active",
                "kind": "B1",
                "accession_number": "ACC_BASIC_MODE_2",
                "family_id": "F_BASIC_MODE_2",
                "country_code": "EP",
                "dwpi_family_members": "",
            },
            {
                "application_number": "APP_CN",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "CN108140599A",
                "registration_number": "CN108140599B",
                "publication_date": pd.Timestamp("2024-02-03"),
                "registration_date": pd.Timestamp("2025-01-11"),
                "legal_status": "active",
                "kind": "B",
                "accession_number": "ACC_BASIC_MODE_2",
                "family_id": "F_BASIC_MODE_2",
                "country_code": "CN",
                "dwpi_family_members": "",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="application",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US"],
        use_basic_selection=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "CN108140599A"
    assert selected.iloc[0]["selected_patent_number"] == "CN108140599A"


def test_basic_matching_uses_original_publication_number_before_pairing_fill() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_BASIC_PAIR",
                "application_date": pd.Timestamp("2023-12-31"),
                "publication_number": "",
                "registration_number": "KR2936749B1",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2026-03-11"),
                "legal_status": "Alive",
                "kind": "B1",
                "accession_number": "ACC_BASIC_PAIR",
                "family_id": "F_BASIC_PAIR",
                "country_code": "KR",
                "dwpi_family_members": "WO2026101178A1 | KR2936749B1",
            },
            {
                "application_number": "APP_BASIC_PAIR",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2026101178A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2026-05-15"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A1",
                "accession_number": "ACC_BASIC_PAIR",
                "family_id": "F_BASIC_PAIR",
                "country_code": "WO",
                "dwpi_family_members": "WO2026101178A1 | KR2936749B1",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US", "EP", "WO", "CN", "KR"],
        use_basic_selection=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["publication_number"] == "WO2026101178A1"
    assert selected.iloc[0]["country_code"] == "WO"


def test_basic_matching_uses_raw_excel_publication_snapshot_when_available() -> None:
    df = pd.DataFrame(
        [
            {
                "application_number": "APP_BASIC_PAIR",
                "application_date": pd.Timestamp("2023-12-31"),
                "publication_number": "",
                "registration_number": "KR2936749B1",
                "publication_date": pd.NaT,
                "registration_date": pd.Timestamp("2026-03-11"),
                "legal_status": "Alive",
                "kind": "B1",
                "accession_number": "ACC_BASIC_PAIR_RAW",
                "family_id": "F_BASIC_PAIR_RAW",
                "country_code": "KR",
                "dwpi_family_members": "KR2936749B1 | WO2026101178A1",
                INTERNAL_RAW_PUBLICATION_COLUMN: "KR2936749B1",
            },
            {
                "application_number": "APP_BASIC_PAIR",
                "application_date": pd.Timestamp("2024-01-01"),
                "publication_number": "WO2026101178A1",
                "registration_number": "",
                "publication_date": pd.Timestamp("2026-05-15"),
                "registration_date": pd.NaT,
                "legal_status": "Alive",
                "kind": "A1",
                "accession_number": "ACC_BASIC_PAIR_RAW",
                "family_id": "F_BASIC_PAIR_RAW",
                "country_code": "WO",
                "dwpi_family_members": "KR2936749B1 | WO2026101178A1",
                INTERNAL_RAW_PUBLICATION_COLUMN: "WO2026101178A1",
            },
        ]
    )

    cfg = SelectionConfig(
        mode="family",
        priority_basis="registration",
        date_policy="latest",
        country_priority=["JP", "US", "EP", "WO", "CN", "KR"],
        use_basic_selection=True,
    )
    selected, _ = run_selection_pipeline(df, cfg)

    assert len(selected) == 1
    assert selected.iloc[0]["country_code"] == "KR"
    assert selected.iloc[0]["registration_number"] == "KR2936749B1"
    assert selected.iloc[0]["selected_patent_number"] == "KR2936749B1"
