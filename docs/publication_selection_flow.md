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

### 2.1 失効除外方針の詳細

1. 発動条件
- exclude_invalid=True のときのみ有効
- False の場合は legal_status に関係なく除外しない

2. 判定方法
- legal_status を小文字化して部分一致で判定
- 除外トークン: dead / 失効 / 無効
- 例: "Dead", "Partly dead", "無効審判" は除外対象

3. 欠損・空文字の扱い
- legal_status が欠損/空文字の行は、失効トークンに一致しないためこの条件だけでは除外されない

4. selected_patent_number 解決時の再判定
- 非Basicモードでは、priority_basis で選んだ primary 番号が失効扱いなら fallback 番号へ切替
- fallback も失効扱い、または fallback が空の場合は primary のまま

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

### 4.1 日付方針の詳細

非Basicモードの代表選択では、日付は次の順で比較キーとして使われます。

1. application_date
- 選択対象の特許番号(selected_patent_number候補)にひも付く出願日を比較

2. publication_date
- 同点時に、同じく選択対象特許番号にひも付く公報日を比較

3. application_number の数値部
- さらに同点のときだけ、出願番号の数値部で最終比較

### 4.2 earliest / latest の意味

1. earliest
- 日付キーは昇順(古い日付を優先)
- 例: application_date が 2021-01-01 と 2022-01-01 なら 2021-01-01 側を優先

2. latest
- 日付キーは降順(新しい日付を優先)
- 例: application_date が 2021-01-01 と 2022-01-01 なら 2022-01-01 側を優先

### 4.3 日付欠損時の扱い

- 比較時の欠損値は常に末尾扱い(na_position="last")になるため、同条件なら日付あり行が優先
- earliest/latest の向きに関係なく、日付欠損は不利

### 4.4 日付範囲フィルタとの関係

代表選択の前段で selectable を作る際、開始日/終了日による範囲判定を実施します。

1. 判定条件
- start_date がある場合: 指定列(start_date_field)の日付が start_date 以上
- end_date がある場合: 指定列(end_date_field)の日付が end_date 以下
- 両方指定時は AND 条件

2. 境界の扱い
- 開始日・終了日はともに境界を含む(以上/以下)

3. 欠損日付の扱い
- 範囲判定に使う日付が欠損/変換不可の行は除外

4. selected_patent_number 解決時の再チェック
- 非Basicモードでは、優先基準で選んだ primary 番号が日付範囲外なら fallback 番号へ切替
- fallback も範囲外なら primary のままになる(ここでは番号の解決のみ行う)

### 4.5 国優先の同順位解決ルール

1. country_priority の同順位指定
- country_priority の1要素内で = を使うと同順位として扱う
- 例: US=WO=EP は US/WO/EP が同一ランク

2. 同順位時の絞り込み
- family 内の最小ランク国を採用
- 最小ランクに複数国がある場合は、その国をすべて残す(1国に決め打ちしない)

3. familyモードでの出力形
- group key は family + country 単位になるため、同順位で残った各国から代表行が1行ずつ出力される

4. 重複指定の扱い
- 同じ国コードが複数回出た場合、最初に出現した順位のみ有効

5. BASIC 指定の扱い
- country_priority に BASIC を入れると、DWPI先頭メンバー行(Basic行)に BASIC 順位を適用
- ただし、優先リストに存在する通常国が family 内にある場合は、そちらのランク解決が先に効く

6. 優先リスト非該当時のフォールバック
- family 内に優先リスト該当国がない場合、以下の順で残す
- Basic行があれば Basic行を残す
- Basic行もなければ publication_number 最小を残す
- publication_number も無ければ全候補を残す

7. 国コード欠損時
- family 内の国コードがすべて空なら、その family は全候補を残す

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
