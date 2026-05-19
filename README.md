# Patent Extractor MVP

## Setup

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
streamlit run app.py
```

## Current rules

- Exclude legal status containing: invalid/expired/無効/失効
- Exclude kind containing: utility/実案
- one-family-one-country by country priority list
- Selection policy:
  - registration priority or publication priority
  - latest or earliest date
- no_acc is detected after exclusions (empty/NULL/-)

## Input notes

- Supports .xlsx, .xlsm, .csv
- Country code can be derived from publication number prefix (e.g., JP... -> JP)
- Family ID falls back to accession number when missing
