from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Literal

Mode = Literal["family", "application"]
PriorityBasis = Literal["registration", "publication"]
DatePolicy = Literal["earliest", "latest"]
DateFilterField = Literal["publication_date", "application_date"]


@dataclass(frozen=True)
class SelectionConfig:
    mode: Mode
    priority_basis: PriorityBasis
    date_policy: DatePolicy
    country_priority: list[str]
    use_basic_selection: bool = False
    treat_wo_republication_as_jp: bool = False
    treat_wo_prior_republication_as_jp: bool = False
    exclude_invalid: bool = False
    exclude_utility: bool = False
    start_date_field: DateFilterField = "publication_date"
    start_date: date | None = None
    end_date_field: DateFilterField = "publication_date"
    end_date: date | None = None
