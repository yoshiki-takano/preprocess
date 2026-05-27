# 公報選択フロー資料

この資料は、入力データから最終的に公報が選択されるまでの処理フローを、現行実装に基づいて整理したものです。

## 1. 全体フロー

```mermaid
flowchart TD
  A[入力ファイル読込] --> B[canonicalize_dataframe]
  B --> C[run_selection_pipeline開始]
  C --> D[WO再公表ルール適用]
  D --> E[先行再公表ルール適用]
  E --> F[JP X/S5除外]
  F --> G[除外条件適用
  失効除外 / 実案除外(PUAB=UA,UB) / 日付]
  G --> H[ペアリングとlookup準備]
  H --> I{Basic選択モード?}

  I -- Yes --> J[Basic候補絞り込み]
  J --> K[family単位で代表選択]

  I -- No --> L[国優先で候補絞り込み]
  L --> M[modeごとにグループ化
  family or application]
  M --> N[代表選択]

  K --> O[selected_patent_number解決]
  N --> O
  O --> P[application_date/publication_date解決]
  P --> Q[出力列整形]
```

## 2. 前処理と除外

1. 入力を正規化
- 列マッピングと型変換を実施
- publication_number / registration_number / legal_status / kind などを正規化

2. 選択前の業務ルールを適用
- 再公表(元WO)をJP扱いにする処理
- 先行再公表(WO)をJP扱いにする処理
- JPの kind が X / S5 の行を除外

3. selectable 行を作成
- 失効除外: legal_status に失効系トークンが含まれる行を除外
- 実案除外: 公報番号または登録番号から解決した PUAB が UA / UB の行を除外
- 日付除外: 開始日/終了日による範囲判定

## 3. Basic選択モードの詳細

Basic選択時は、国優先ロジックを使わず、ファミリー内でBasic候補を絞り込みます。

### 3.1 Basic候補判定
- familyごとに dwpi_family_members の先頭メンバーを取得
- publication_number がその先頭メンバーと一致する行を Basic候補 と判定

### 3.2 フォールバック規則
先頭メンバーが selectable に存在しない場合は、以下の順でフォールバックします。

1. DWPI順フォールバック
- dwpi_family_members の並び順を使い、selectable に残っている publication_number のうち順位が最小のものを採用
- つまり、先頭が除外済みなら「次点」、さらに不在なら「次々点」を採用

2. publication_number最小フォールバック
- dwpi_family_members 情報が欠けて順位を計算できない場合のみ適用
- 正規化後の publication_number を辞書順比較し最小を採用

3. publication_number自体がない場合
- そのfamilyの候補を保持して後段選択へ

## 4. 非Basicモードの詳細

1. 国優先で候補を narrowing
- country_priority に基づいて familyごとに候補国を絞り込み

2. グループ化
- mode=family: familyキー(+同順位国グループ考慮)
- mode=application: application_number系キー

3. 代表選択
- 特許番号の優先基準(公開基準/登録基準)
- 日付方針(earliest/latest)
- 実案より特許を優先するため PUAB=UA/UB を低優先化

## 5. selected_patent_number の決定

最終行が決まった後、selected_patent_number を解決します。

- Basicモード:
  - publication_number を優先
  - publication_number が空なら registration_number

- 非Basicモード:
  - priority_basis に応じて primary(公開 or 登録) を優先
  - primaryが失効/日付外で fallback が有効な場合は fallback へ切替

## 6. 例: accession 202183125B (失効除外ON + Basic)

- DWPI先頭: WO2021145254A1
- 先頭行は Dead のため selectable から除外
- 新仕様では DWPI順次点を探索し、JP2021114643A を採用

## 7. 運用上の確認ポイント

1. dwpi_family_members の品質
- 区切りは | 前提
- 先頭からの並び順が選択結果へ影響

2. 除外条件の影響
- 失効除外や実案除外で先頭候補が落ちると、結果は次点へ変わる

3. データ欠損時
- dwpi_family_members が欠損しているfamilyは publication_number最小フォールバックに入る
