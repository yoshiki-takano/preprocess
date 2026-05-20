from __future__ import annotations

CANONICAL_COLUMNS = {
    "application_number": ["application_number", "出願番号", "出願No", "APPLN_NR"],
    "application_date": ["application_date", "出願日", "出願日付", "application date"],
    "publication_number": [
        "publication_number",
        "PUBLICATION NUMBER",
        "公報番号",
        "公開番号",
    ],
    "registration_number": ["registration_number", "登録番号", "特許番号"],
    "publication_date": ["publication_date", "公開日", "公開日付", "公報発行日"],
    "registration_date": ["registration_date", "登録日", "登録日付"],
    "legal_status": [
        "legal_status",
        "法的状況",
        "法的状態",
        "status",
        "無効/有効",
        "有効/無効",
    ],
    "kind": ["kind", "種別", "権利種別"],
    "accession_number": [
        "accession_number",
        "DWPI accession number",
        "dwpi accession number",
        "DWPIアクセッション番号",
    ],
    "family_id": ["family_id", "ファミリID", "ファミリーID"],
    "country_code": ["country_code", "国コード", "country"],
    "title_english": ["title_english", "title(english)", "タイトル（英語）", "Title (English)"],
    "title_dwpi": ["title_dwpi", "title-dwpi", "タイトル - DWPI", "Title - DWPI"],
    "assignee_standardized": ["assignee_standardized", "譲受人 - 標準化", "Assignee Standardized"],
    "assignee_applicant": ["assignee_applicant", "譲受人/出願人", "Assignee/Applicant"],
    "assignee_dwpi": ["assignee_dwpi", "譲受人 - DWPI", "Assignee - DWPI"],
    "priority_number": ["priority_number", "prioritynumber", "優先権主張番号", "Priority Number"],
    "priority_date": ["priority_date", "prioritydate", "優先権主張日", "Priority Date"],
    "dwpi_family_members": ["dwpi_family_members", "DWPI ファミリーメンバー", "DWPI Family Members"],
    "dwpi_family_members_status": [
        "dwpi_family_members_status",
        "DWPI ファミリーメンバー 有効/無効",
        "DWPI Family Members Alive/Dead",
    ],
}

EXCLUDE_STATUS_TOKENS = {"失効", "無効", "expired", "invalid", "dead"}
EXCLUDE_KIND_TOKENS = {"実案", "utility"}
NO_ACC_TOKENS = {"", "-", "null", "none", "nan"}
