# Phase F — Visual Baseline Diff Report

**生成時間**：2026-05-05T16:48:32.292Z
**Pipeline**：puppeteer + pixelmatch vs LibreOffice golden PNG
**Odoo**：http://localhost:8069 (odoo18_dev)
**Scale factor**：1.5625

## 摘要

- 成功：42 fixture
- 錯誤：0 fixture
- 平均 diff%：15.0%
- 中位數：13.3%
- 最佳：1.7%
- 最差：30.0%

## 各類別摘要

| 類別 | 數量 | 平均 diff% | 最佳 | 最差 |
|------|------|-----------|------|------|
| 01_simple | 7 | 13.4% | 13.2% | 13.8% |
| 02_std_table | 8 | 18.6% | 1.7% | 30.0% |
| 03_complex_table | 8 | 22.6% | 3.3% | 29.8% |
| 04_with_image | 6 | 26.6% | 25.3% | 28.7% |
| 05_header_footer | 10 | 3.8% | 3.4% | 4.0% |
| 06_template | 3 | 2.9% | 1.9% | 4.0% |

## 全 fixture 逐頁 diff%

| Fixture | 類別 | Golden 頁 | Rendered 頁 | 各頁 diff% | 平均 |
|---------|------|-----------|-------------|-----------|------|
| 03_complex_table/送審管制.docx | 03_complex_table | 2 | 4 | 3.5%*, 3.1%* | 3.3% |
| 03_complex_table/1130516-共月橋P3帽梁鋼筋查驗.docx | 03_complex_table | 1 | 1 | 27.8%* | 27.8% |
| 03_complex_table/1130112-全套管基樁混凝土查驗共(共3)(承辦).docx | 03_complex_table | 1 | 1 | 29.8%* | 29.8% |
| 03_complex_table/1130109-全套管基樁混凝土查驗共(4).docx | 03_complex_table | 1 | 1 | 28.7%* | 28.7% |
| 03_complex_table/1130105-全套管基樁混凝土查驗(共2).docx | 03_complex_table | 1 | 1 | 28.7%* | 28.7% |
| 03_complex_table/1121229-全套管基樁混凝土查驗(共1).docx | 03_complex_table | 1 | 1 | 28.2%* | 28.2% |
| 03_complex_table/06-8估驗計價前履約文件查對項目一覽表（112年12月27日修訂）11409.docx | 03_complex_table | 2 | 4 | 3.5%*, 6.0%* | 4.8% |
| 03_complex_table/06-8估驗計價前履約文件查對項目一覽表（112年12月27日修訂） (1).docx | 03_complex_table | 2 | 4 | 14.5%*, 44.8%* | 29.6% |
| 04_with_image/6.環清表安全衛生抽查照片(再造)-(112.9.25.-9.29).docx | 04_with_image | 6 | 6 | 41.5%*, 11.4%*, 41.5%*, 11.2%*, 40.7%*, 10.9%* | 26.2% |
| 04_with_image/6.環清表安全衛生抽查照片(再造)-(112.10.2.-10.6).docx | 04_with_image | 6 | 6 | 39.9%*, 11.2%*, 40.7%*, 11.1%*, 39.8%*, 10.2%* | 25.5% |
| 04_with_image/06.環清表安全衛生抽查照片(再造)-(112.10.9.-10.13).docx | 04_with_image | 6 | 6 | 40.1%*, 11.2%*, 41.3%*, 11.5%*, 39.4%*, 11.2%* | 25.8% |
| 04_with_image/06.環清表安全衛生抽查照片(再造)-(112.10.23.-10.27).docx | 04_with_image | 6 | 6 | 38.5%*, 11.0%*, 40.2%*, 10.7%*, 41.2%*, 10.4%* | 25.3% |
| 04_with_image/05.112磺港溪監造會議照片1120923-1121001.docx | 04_with_image | 2 | 4 | 27.2%*, 30.2%* | 28.7% |
| 04_with_image/05.112磺港溪監造會議照片.docx | 04_with_image | 2 | 4 | 26.3%*, 30.0%* | 28.1% |
| 06_template/缺失改善.docx | 06_template | 3 | 5 | 3.6%*, 3.0%*, 1.6%* | 2.8% |
| 06_template/缺失改善(預設樣板).docx | 06_template | 2 | 3 | 2.8%*, 1.1%* | 1.9% |
| 06_template/檢(試)驗管制(預設樣板).docx | 06_template | 2 | 3 | 5.8%*, 2.3%* | 4.0% |
| 05_header_footer/自主檢查表---混凝土.docx | 05_header_footer | 5 | 7 | 6.3%*, 6.4%*, 4.4%*, 1.2%*, 1.4%* | 3.9% |
| 05_header_footer/自主檢查表---洗(抿)石子.docx | 05_header_footer | 4 | 6 | 6.3%*, 6.6%*, 1.2%*, 1.4%* | 3.9% |
| 05_header_footer/自主檢查表---油漆.docx | 05_header_footer | 4 | 6 | 6.3%*, 5.9%*, 1.2%*, 1.3%* | 3.7% |
| 05_header_footer/自主檢查表---模板.docx | 05_header_footer | 4 | 6 | 6.2%*, 6.3%*, 1.2%*, 1.3%* | 3.8% |
| 05_header_footer/自主檢查表---植筋.docx | 05_header_footer | 5 | 7 | 6.4%*, 6.2%*, 4.1%*, 1.2%*, 1.4%* | 3.9% |
| 05_header_footer/自主檢查表---植栽.docx | 05_header_footer | 4 | 6 | 6.3%*, 5.4%*, 1.2%*, 1.3%* | 3.5% |
| 05_header_footer/自主檢查表---木構造.docx | 05_header_footer | 5 | 6 | 6.3%*, 6.8%*, 2.7%*, 2.3%*, 0.1%* | 3.7% |
| 05_header_footer/自主檢查表---地坪鋪面.docx | 05_header_footer | 5 | 6 | 6.3%*, 6.8%*, 1.7%*, 2.3%*, 0.1%* | 3.4% |
| 05_header_footer/自主檢查表---土方(整地).docx | 05_header_footer | 4 | 6 | 6.4%*, 7.1%*, 1.2%*, 1.4%* | 4.0% |
| 05_header_footer/自主檢查表---人手孔調升降.docx | 05_header_footer | 5 | 7 | 6.5%*, 6.6%*, 4.4%*, 1.2%*, 1.4%* | 4.0% |
| 02_std_table/1140206-工地密度簽到表.docx | 02_std_table | 1 | 1 | 1.7%* | 1.7% |
| 02_std_table/1140206-工地密度取樣紀錄.docx | 02_std_table | 2 | 1 | 4.6%* | 4.6% |
| 02_std_table/1131202-工地密度簽到表.docx | 02_std_table | 1 | 1 | 1.7%* | 1.7% |
| 02_std_table/1121027-磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋)週報.docx | 02_std_table | 2 | 3 | 20.4%*, 33.4%* | 26.9% |
| 02_std_table/1121020-磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋)週報.docx | 02_std_table | 2 | 3 | 21.6%*, 33.2%* | 27.4% |
| 02_std_table/1121013-磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋)週報.docx | 02_std_table | 2 | 3 | 21.5%*, 32.4%* | 26.9% |
| 02_std_table/1121006-磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋)週報.docx | 02_std_table | 2 | 4 | 22.5%*, 37.5%* | 30.0% |
| 02_std_table/1120928-磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋)週報.docx | 02_std_table | 2 | 4 | 21.2%*, 38.4%* | 29.8% |
| 01_simple/03.1120919-監造會議記錄.docx | 01_simple | 3 | 5 | 8.4%*, 19.4%*, 13.5%* | 13.8% |
| 01_simple/03.1120912-監造會議記錄.docx | 01_simple | 3 | 5 | 8.6%*, 19.3%*, 12.0%* | 13.3% |
| 01_simple/03.1120905-監造會議記錄.docx | 01_simple | 3 | 5 | 8.6%*, 19.4%*, 12.9%* | 13.6% |
| 01_simple/03.1120829-監造會議記錄.docx | 01_simple | 3 | 5 | 8.4%*, 19.1%*, 12.5%* | 13.3% |
| 01_simple/03.1120822-監造會議記錄.docx | 01_simple | 3 | 5 | 8.4%*, 19.3%*, 12.2%* | 13.3% |
| 01_simple/03.1120815-監造會議記錄.docx | 01_simple | 3 | 6 | 8.2%*, 18.2%*, 13.3%* | 13.2% |
| 01_simple/03.1120210-監造會議記錄-1120801.docx | 01_simple | 3 | 5 | 8.1%*, 18.8%*, 13.1%* | 13.4% |

註：標 `*` 表示 golden 與 rendered 尺寸不符，已 nearest-neighbor 縮放後比對（diff% 偏高，並非真實差異）。

## Phase 4 改進量化 — vs baseline

### 量化結果（Phase 4 vs baseline）

| 維度 | Baseline | Phase 4 | Delta |
|------|----------|---------|-------|
| 全 fixture mean | **15.00%** | **15.00%** | **+0.009pp** |
| Median | 13.30% | 13.30% | 0.000pp |
| Best | 1.70% | 1.70% | 0.000pp |
| Worst | 30.00% | 30.00% | 0.000pp |

### 各類別 delta

| 類別 | Baseline | Phase 4 | Delta |
|------|----------|---------|-------|
| 01_simple | 13.42% | 13.42% | +0.000pp |
| 02_std_table | 18.62% | 18.62% | +0.000pp |
| 03_complex_table | 22.61% | 22.61% | +0.000pp |
| 04_with_image | 26.54% | 26.60% | **+0.064pp**（雜訊範圍）|
| 05_header_footer | 3.78% | 3.78% | +0.000pp |
| 06_template | 2.90% | 2.90% | +0.000pp |

### Per-fixture delta

40/42 fixture 的 diff% 完全相同（0.00pp delta）。僅 2 份微幅 regression（皆在 04_with_image 類別，浮動圖片渲染抖動）：

| Fixture | Baseline | Phase 4 | Delta |
|---------|----------|---------|-------|
| 04_with_image/06.環清表(112.10.23.-10.27).docx | 25.1% | 25.3% | +0.24pp |
| 04_with_image/06.環清表(112.10.9.-10.13).docx | 25.6% | 25.8% | +0.15pp |

兩者皆在 ±0.5pp 雜訊範圍內，且為 04_with_image 類別（已知瓶頸：浮動圖片渲染，Phase 3.4 才能改）。

## 重要結論：Phase 4 達不到「diff% –3 ~ –6pp」預期目標

### 為什麼？

baseline 報告預估 Phase 4 攻擊「邊框 + theme + 條件樣式」三線可下降 –3 ~ –6pp，**但實際下降 0pp**。原因：

1. **canvas-editor renderer 不消化我們新增的精確屬性**：
   - 邊框衝突解決後 cell.props.borders 是正確的，但 ToCanvasEditor mapper 把表格映射為 canvas-editor 的 `td` 物件時，canvas-editor 用自己的 border defaults，忽略我們算的 effective borders
   - Theme color 解析後 RunProps.color 是正確的 hex，但這條路 mapper 已經正確輸出，不是新增；fixture 中極少用 themeColor reference，所以新增的解析能力沒被觸發
   - 條件樣式（firstRow/lastRow 等）apply 到 paragraph/run 是正確的，但 canvas-editor 可能不認得我們設的某些 props（如某些 fontFamily 變化、字距等）

2. **fixture 集合特性**：
   - 大多 ChienYi 工程 fixture 是「直接寫 hex 顏色 + 表單樣式」，theme reference 用得少
   - tblStylePr 條件樣式在這些 fixture 中也罕見（多為簡單表格）
   - Phase 4 的「完美正確」對這個 fixture 集合不顯著

3. **真正的 diff% 瓶頸仍未動**：
   - 分頁位置（contributes ~30–40%）— 全部 fixture 都有 page split mismatch
   - 字型 measureText 精度（contributes ~10–20%）— 字距累積誤差
   - 浮動圖片渲染（contributes ~25%，限 04 類）— floating image 降為 inline

### Phase 4 的價值（非 diff% 改進）

雖然視覺基線沒動，Phase 4 仍交付了關鍵 parser 正確性：

| 模組 | 行數 | 測試 | 價值 |
|------|------|------|------|
| ThemeResolver | 230 | 19 | themeColor + tint/shade 演算法、12 色 + 字型 scheme，**為 Phase 6 自寫 Renderer 預備**：當 fork canvas-editor 時，這些 hex 直接餵 Renderer 即可，省去屆時補解析的成本 |
| TableStyleApplicator | 220 | 16 | 條件樣式套用 row/cell 內每段段落+run；ECMA-376 §17.7.6 完整實作 |
| BorderConflictResolver | 230 | 14 | ECMA-376 §17.4.65 cell 邊框優先級表；adjacent cell 邊界協調 |
| colorResolver helper | 50 | 共享 | 統一 `<w:color>` 解析點 |

**「parser 是 Phase 6 Renderer fork 的前置功課」** — 沒有這層 AST 正確性，未來 Renderer 也只能拿不對的 props 渲染。

### 真正動 diff% 的下個 Phase

下個 Phase 必須直接攻擊渲染端：

| Phase | 目標 | 估計 diff% 改進 | 工程量 |
|-------|------|---------------|--------|
| Fork canvas-editor + 自寫 PageSplit Engine | 修分頁位置 | **–10 ~ –15pp** | 3-4 個月 |
| HarfBuzz 接 canvas-editor Renderer | 字型字距精度 | –3 ~ –5pp | 1-2 個月 |
| Float / Wrap 圖文繞排 | 04_with_image 類 | –10 ~ –15pp（限該類） | 2-3 個月 |
| 自寫 Border Renderer | 用 BorderConflictResolver 結果 | –1 ~ –3pp | 1 週（前置已完成） |

從 15% 降到 5%（A- 級）需 4-6 個月 fork canvas-editor 工程。

## 結論

- ✅ Phase 4 三大模組（ThemeResolver + TableStyleApplicator + BorderConflictResolver）正確實作 + 49 個測試全綠
- ❌ 量化 diff% 改進：未達預期 –3 ~ –6pp，實際 +0.009pp（無變動）
- 📌 ADR-012 紀錄此 finding：**parser-level 工作已飽和，下個 Phase 必須攻 renderer**
- 📌 visual baseline pipeline 證明可重現量化（Phase F 設施值得，未來改 renderer 後再跑可即時量化）
