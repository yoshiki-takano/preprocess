import pandas as pd
from datetime import date
from src.patent_app.pipeline import run_selection_pipeline
from src.patent_app.models import SelectionConfig

data = [
    {"accession": "202094334X", "pub": "WO2020189179A1", "app_date": "2020-02-21", "app_no": "WO2020JP7047A", "pub_date": "2020-09-24", "country": "WO"},
    {"accession": "202094334X", "pub": "US20220165896A1", "app_date": "2021-09-20", "app_no": "US17440939A", "pub_date": "2022-05-26", "country": "US"},
    {"accession": "202094334X", "pub": "US11804561B2", "app_date": "2021-09-20", "app_no": "US17440939A", "pub_date": "2023-10-31", "country": "US"},
    {"accession": "202094334X", "pub": "JP2020189179A1", "app_date": "2020-02-21", "app_no": "JP2021507126A", "pub_date": "2020-09-24", "country": "JP"},
    {"accession": "202094334X", "pub": "JP07524160B2", "app_date": "2020-02-21", "app_no": "JP2021507126A", "pub_date": "2024-07-29", "country": "JP"},
]

df = pd.DataFrame(data)
df['application_date'] = pd.to_datetime(df['app_date'])
df['publication_date'] = pd.to_datetime(df['pub_date'])
df['registration_date'] = pd.NaT
df['registration_number'] = None
df['legal_status'] = 'active'
df['kind'] = df['pub'].str.extract(r'([A-Z]\d)$')[0]
df['family_id'] = df['accession']
df['publication_number'] = df['pub']
df['application_number'] = df['app_no']
df['country_code'] = df['country']

modes = ["family", "application"]
bases = ["registration", "publication"]
policies = ["latest", "earliest"]
country_priority = ["JP", "US", "EP", "WO", "CN", "KR"]

results = []
for m in modes:
    for b in bases:
        for p in policies:
            config = SelectionConfig(
                mode=m,
                priority_basis=b,
                date_policy=p,
                country_priority=country_priority,
                treat_wo_republication_as_jp=True,
                treat_wo_prior_republication_as_jp=True
            )
            selected, _ = run_selection_pipeline(df, config)
            # Find selected patent number (or identifier)
            for _, row in selected.iterrows():
                results.append({
                    "mode": m,
                    "priority_basis": b,
                    "date_policy": p,
                    "selected_patent_number": row.get('patent_number', row['publication_number']),
                    "publication_number": row['publication_number'],
                    "registration_number": row['registration_number'],
                    "application_number": row['application_number'],
                    "application_date": row['application_date'].strftime('%Y-%m-%d'),
                    "publication_date": row['publication_date'].strftime('%Y-%m-%d')
                })

res_df = pd.DataFrame(results)
print("Full Results Table:")
print(res_df.to_string(index=False))

print("\nDeduplicated Summary:")
# Group by everything except date_policy
summary = []
for (m, b), group in res_df.groupby(['mode', 'priority_basis']):
    # Compare identifying columns
    ids = ['publication_number', 'registration_number', 'application_number', 'application_date', 'publication_date']
    v_groups = [g for _, g in group.groupby(ids)]
    if len(v_groups) == 1:
        row = group.iloc[0].to_dict()
        row['date_policy'] = 'both'
        summary.append(row)
    else:
        for v_g in v_groups:
            row = v_g.iloc[0].to_dict()
            summary.append(row)

summary_df = pd.DataFrame(summary)
print(summary_df[['mode', 'priority_basis', 'date_policy', 'publication_number', 'application_number']].to_string(index=False))
