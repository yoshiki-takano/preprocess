from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from patent_app.memo import annotate_no_acc_family_possibility_memo
from patent_app.exporter import _build_template_output_dataframe


def test_annotate_no_acc_family_possibility_memo_uses_first_candidate_and_formats_message() -> None:
    selected_df = pd.DataFrame(
        [
            {
                "publication_number": "JP2026123456A",
                "accession_number": "",
                "selected_patent_number": "JP2026123456A",
            }
        ]
    )

    reference_df = pd.DataFrame(
        [
            {"publication_number": "JP2026123456A", "accession_number": "ACC-SAME-KIND"},
            {"publication_number": "JP2026123456B", "accession_number": "2026M0530"},
            {"publication_number": "JP2026123456C", "accession_number": "2026M9999"},
        ]
    )

    out = annotate_no_acc_family_possibility_memo(selected_df, reference_df)

    assert out.loc[0, "MEMO1"] == "アクセッション番号 2026M0530 のファミリの可能性あり"


def test_annotate_no_acc_family_possibility_memo_keeps_existing_for_non_no_acc_rows() -> None:
    selected_df = pd.DataFrame(
        [
            {
                "publication_number": "JP2026123456A",
                "accession_number": "ACC-EXISTING",
                "MEMO1": "existing",
                "selected_patent_number": "JP2026123456A",
            }
        ]
    )

    reference_df = pd.DataFrame(
        [
            {"publication_number": "JP2026123456B", "accession_number": "2026M0530"},
        ]
    )

    out = annotate_no_acc_family_possibility_memo(selected_df, reference_df)

    assert out.loc[0, "MEMO1"] == "existing"


def test_template_output_uses_memo1_column_when_present() -> None:
    selected_df = pd.DataFrame(
        [
            {
                "selected_patent_number": "JP2026123456A",
                "MEMO1": "アクセッション番号 2026M0530 のファミリの可能性あり",
            }
        ]
    )

    out = _build_template_output_dataframe(selected_df)

    assert out.loc[0, "MEMO1"] == "アクセッション番号 2026M0530 のファミリの可能性あり"
