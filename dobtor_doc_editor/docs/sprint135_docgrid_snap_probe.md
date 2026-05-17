# Sprint 135 — docGrid snap 段落層級判別子 probe sprint（Phase 3 漏項）

**日期**：2026-05-17
**類型**：**probe sprint**（紀律 #3）— 純診斷 / 純 docs / 無 production code 變動
**規畫書對應**：§0.1 長期 backlog「docGrid snap 段落層級判別子」+ autonomous_roadmap.md 階段 B cluster 7 行 1
**前置 sprint**：Sprint 134 textAlignment + framePr capture（cluster 6 收尾、Phase 4 capture 85% 完工）

---

## Hypothesis（驗證對象）

Sprint 46 與 Sprint 49 兩次嘗試修 docGrid snap 規則都翻車：

| Sprint | 嘗試 | 翻車 | 真根因 |
|---|---|---|---|
| 46 | exact 行不 snap（全域）| 04_with_image +19.86pp | 環清表 exact 行需 snap 才不 under-paginate |
| 49 | 無 spacing.line 段落 snap（全域、移除 guard）| 02_std_table +3.61pp | 02 in-cell 段落 snap 後高度漂移、累積破頁 |

兩次結論一致：**snap 規則需段落層級條件式、無乾淨全域開關**，且「判別子尚未找到」（Sprint 49 §8 心得）。Sprint 135 為此「找判別子」工作的 probe sprint。

**Hypothesis A（核心）**：Sprint 49 03 全套管 title 段落（outside-table、無 spacing.line、無 explicit snapToGrid）**該** snap、02 同條件段落（inside-cell、無 spacing.line、無 explicit snapToGrid）**不該** snap 的差異 = **「段落是否在 table cell 內」**。

**Hypothesis B（影響量）**：實作此判別子後、預期 03 全套管系列 -1~2pp 改善（Sprint 49 §3 觀察值）、02_std_table 約 +0.1~0.5pp 退化（少數 body placeholder 仍被影響、但非主要破壞源）、total -0.5~1pp 收斂。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B cluster 7 行 1：「135 | Phase 3 漏項 | docGrid snap 段落層級判別子（規畫書 §0.1 列為長期 backlog；Sprint 46+49 全域翻車、需段落條件式）」
- Sprint 128 audit + Sprint 134 audit 後續段都明示 cluster 7 為 spike sprint
- 本 sprint scope = **純 probe**：
  - 讀 Sprint 46 / 49 audit 完整理解翻車模式
  - 結構化分析 42 fixture 的「snap 候選段落」分布
  - 找結構差異（OOXML attribute level）區分「該 snap」vs「不該 snap」段落
  - 寫 audit doc + autonomous Sprint 136 GO/NO-GO 決策
- **不在 scope**：production code 變動、prep test、實作判別子（屬 Sprint 136 範圍）
- PR-size：1 audit doc + 1 roadmap update / 0 production code 變動

### 2. 歷史回顧（Sprint 46 + 49）

#### Sprint 46（exact 行 snap 全域實驗翻車）

監造會議記錄 row1 `line=460 exact`（23pt）被 snap 成 36pt、row4 `2×line=400 exact`（40pt）被 snap 成 72pt。Sprint 43 §5 假設 A2：exact = 精確行高、不該 snap。實驗 + 3 prep test、trace 確認 row4 72.0 → 44.9（精確命中 golden）。

**VR 全 42 fixture 災難退化**：
- 04_with_image 0.1250 → 0.3236（+19.86pp）
- TOTAL 0.0774 → 0.1025（+2.51pp）

教訓：「prep test 通過、trace 命中、但全域 VR 翻車」= 第八層紀律「全 fixture VR 才算數」誕生。

#### Sprint 49（無 spacing.line snap 全域實驗翻車）

03 全套管照片 row 內 title 段落（22pt + 18pt、無 spacing.line）Pillow 量測 golden = 36pt（= 2 × pitch 18pt），但 render natural 26.4 / 21.6pt 未被 snap → 標題塊矮 ~26pt → 整個 table 起點上移 → 照片 Y 偏高 26pt。

實驗：移除 Sprint 29 的 `if (!para.props.spacing?.line) return` guard。VR：
- 02_std_table 0.0915 → 0.1276（+3.61pp）退化
- 03_complex_table 0.1316 → 0.1194（-1.22pp）收斂
- TOTAL +0.27pp 淨退化

→ revert。**Sprint 49 §8 結論**：snap 的正確規則是段落層級條件式、判別子尚未找到。

### 3. 42 Fixture 結構化分析

對所有 42 fixture 走訪段落、按四維度分類：

```python
key = (in_table_cell, has_spacing_line, has_explicit_snapToGrid_off, has_pStyle)
```

**Sprint 49 受影響的段落集合** = `(_, False, False, _)`（無 spacing.line + 無 explicit snapToGrid=0 → Sprint 49 實驗會 snap 它）。

#### 42 fixture per-fixture「sprint 49 候選段落數」分布

格式：`in_cell_candidates / body_candidates`（受 Sprint 49 影響的段落數、按 in-cell vs body 分）

| Fixture | in-cell | body |
|---|---|---|
| 01_simple 監造會議記錄 7 系列 | 59-95 | 1-2 |
| 02_std_table 1120928-1121027 週報 5 個 | 14-21 | 2-4 |
| 02_std_table 1131202-1140206 簽到/取樣 3 個 | 0 | 0 |
| 03_complex_table 估驗計價 2 系列 | 7 | 1 |
| **03_complex_table 全套管 4 系列 + 共月橋** | **5** | **3** |
| 03_complex_table 送審管制 | 78 | 8 |
| 04_with_image 監造會議照片 2 系列 | 10-11 | 4 |
| 04_with_image 環清表照片 4 系列 | 0 | 1 |
| 05_header_footer 自主檢查表 10 系列 | 70-118 | 2 |
| 06_template 檢試驗管制 | 69 | 9 |
| 06_template 缺失改善 預設樣板 | 25 | 4 |
| 06_template 缺失改善 | 0 | 1 |

#### 核心觀察

**02_std_table 週報系列**（Sprint 49 翻車元兇）：
- in-cell candidates **14-21**、body candidates 2-4
- in-cell 多為 `<w:pStyle w:val="TableParagraph"/>`（樣板段落）或 cell 內標題、Sprint 49 snap 後高度 +1.4~2pt 累積破頁
- body 4 個為 `<w:widowControl/>` + `<w:sz w:val="2"/>` 的 placeholder 段落（sz=1pt、僅 layout 用、snap 影響很小）

**03_complex_table 全套管系列**（Sprint 49 想救的 fixture）：
- body candidates **3**（這 3 個就是 Pillow 證實該 snap 到 36pt 的標題段落）
- in-cell candidates 5（少量、不是主流）
- 對比 02：03 全套管「body 該 snap、in-cell 不該」結構區分明確

#### 結構差異（決定性）

抽 02_std_table 與 03 全套管「outside-table no-spacing.line no-explicit-snapToGrid」段落樣本對比：

| 維度 | 02_std_table body 4 個 | 03 全套管 body 3 個 |
|---|---|---|
| `<w:widowControl/>` | 全部有 | 全部無 |
| 字型 sz | 2（= 1pt）| 32-44（= 16-22pt） |
| 文字內容 | 空 / 僅 `<w:br w:type="page"/>` | 真實 title 文字（如「任泰技術顧問有限公司」）|
| jc | 無 | center |
| bold | 無 | 全部 b=true |

**結論**：03 全套管 body 段落是「真實內容標題」、02 body 段落是「layout placeholder」。

### 4. 判別子候選評估

| 候選判別子 | 區分能力 | 實作複雜度 | 風險 |
|---|---|---|---|
| **「段落在 table cell 內」**（核心 hypothesis）| 隔離主要傷害源（02 in-cell 14-21 段落）；保留 03 body title snap 修正 | 中（ParagraphInput 加 isInTableCell flag、TableParser 設值）| 低（明確結構判別子）|
| 「段落字型 sz ≥ 12pt」 | 過濾 02 body placeholder（sz=1pt）；保留 03 body title（22pt）| 低（讀 run/style sz）| 中（多 run 字型不同時取哪個？）|
| 「段落含實際文字內容（非空 + 非僅 page break）」 | 過濾 02 placeholder；保留 03 title | 低 | 中（如何定義「實際內容」需多 case 測）|
| 「`<w:widowControl/>` 存在」 | 反向：02 placeholder 有此 element、03 title 無 | 低（attr 解析）| 高（widowControl 語意是「寡行控制」、跟 snap 無因果） |
| 「段落有 jc / bold rPr」 | 03 title 有、02 placeholder 無 | 低 | 高（jc/bold 是樣式偏好、跟 snap 無因果）|

**autonomous 評估**：

1. **「在 table cell 內」**（候選 1）= **最強候選**：
   - 對 Sprint 49 翻車主要源頭（02_std_table in-cell 14-21 段落）有明確隔離
   - 結構判別子有 OOXML 語意基礎（table cell 內段落 layout 行為與 body 段落本質不同）
   - 實作清楚（ParagraphInput 加 boolean flag、Paginator / TableLayout 註入）
   - 不需推測「實際內容」「字型偏好」等模糊條件

2. **「字型 sz ≥ 12pt」**（候選 2）= **輔助候選**：
   - 可作為候選 1 之上的二次過濾（in-body && sz>=12 → snap）
   - 但本 sprint 觀察「02 body 4 個都是 sz=2」純屬 fixture 巧合、其他 fixture 可能有 sz=8 placeholder 仍被影響
   - 風險中、defer 到 Sprint 137 視 Sprint 136 結果再評估

3. **其他候選 3-5** = 拒絕：缺乏 OOXML 語意基礎、屬「巧合 correlations」

### 5. Sprint 136 設計 sketch（autonomous 提案）

#### 5.1 修法

```ts
// ParagraphInput 加：
export interface ParagraphInput {
  // ... 既有 ...
  /** Sprint 136：段落是否在 table cell 內（由 Paginator/TableLayout 註入）。
   *  影響 docGrid snap 決策：body 段落（false）即使無 spacing.line 也 snap；
   *  cell 內段落（true）保持 Sprint 29 行為（無 spacing.line 不 snap）。 */
  isInTableCell?: boolean;
}

// LineBreaker.applyDocGridSnap：
function applyDocGridSnap(height: Pt, para: ParagraphInput, linePitch: Pt): Pt {
  if (!Number.isFinite(linePitch) || linePitch <= 0) return height;
  if (para.props.snapToGrid === false) return height;

  // Sprint 136：body 段落（不在 cell 內）即使無 spacing.line 也 snap；
  // cell 內段落保持 Sprint 29 的「無 spacing.line → 不 snap」guard
  if (!para.props.spacing?.line && para.isInTableCell !== false) {
    return height;
  }

  if (!Number.isFinite(height) || height <= 0) return height;
  const grids = Math.ceil(height / linePitch);
  return grids * linePitch;
}
```

注意條件：`para.isInTableCell !== false` 意思是「未明示 false 就視為 cell 內」、預設保守。Paginator 走 body 段落時主動 set `isInTableCell = false`，這時新規則才生效。

#### 5.2 prep test（嚴格紀律 #3 enforcement）

- 02_std_table body 4 個 placeholder：set isInTableCell=false → render 應 snap、高度從 sz=1pt 變 grid pitch（~18pt）→ **預期 VR 退化**（可接受）
- 03 全套管 body 3 個 title：set isInTableCell=false → render 應 snap、22pt → 36pt（= 2×pitch）= golden 行為 → **預期 VR 改善**
- 全 42 fixture VR 跑：閾值「03_complex_table 收斂 > 02_std_table 退化」才接受

#### 5.3 風險與紓緩

| 風險 | 機率 | 紓緩 |
|---|---|---|
| 02_std_table 仍退化（body placeholder snap 後）| 高 | 接受小退化（< +0.5pp）換 03 收斂；若 > +1pp 則加入「sz ≥ 12pt」二次判別 |
| 05_header_footer 自主檢查表 70-118 in-cell 段落不變、但 2 個 body 段落新 snap → 可能小退化 | 中 | 與 02 同邏輯 |
| 01_simple 監造會議記錄 59-95 in-cell 不變、1-2 body 新 snap | 中 | 同上 |
| Paginator/TableLayout 注入 isInTableCell 漏 set | 中 | 預設 undefined ≠ false、行為與 Sprint 29 相同（safety net）|
| 整合層級多、Sprint 62 IIFE bundle 同類陷阱 | 低 | 純 parser/layout 邏輯、不動 render canvas API |

### 6. Autonomous GO/NO-GO 決策

候選決策：

| 決策 | scope | 收益 | 風險 |
|---|---|---|---|
| **GO-1：Sprint 136 實作「isInTableCell」判別子** | 1 sprint（types +1 / LineBreaker +5 / Paginator+TableLayout 注入 +20 / prep test +30 / VR 驗證）| 預期 03 全套管 -1~2pp、total -0.5~1pp | 02 小退化、整合風險 |
| **GO-2：Sprint 136-137 cluster：判別子 + 二次 sz 過濾** | 2 sprint | 預期 total -1~1.5pp、雙保險 | scope creep、二次過濾可能 over-engineering |
| **NO-GO：永遠 defer**（接受 Sprint 49 §5 路線 B「轉商業化」結論）| 0 sprint | 0 | 規畫書 §0.1 backlog 永遠不解決 |
| **DEFER-1：寫此 audit、留 GO 決策給 user**（標 Sprint 136 候選但不主動執行） | 0 sprint | 0 | 同上 |

**autonomous 決策：DEFER-1（標 Sprint 136 候選但不主動執行）**

理由：

1. **Sprint 135 已是 spike + 階段 B cluster 7 預設「probe」**：roadmap 排「135 = spike sprint」、本 sprint 已完成最大價值的事（找判別子）；實作屬 Sprint 136 的 scope
2. **改 LineBreaker 是 high-attention 修改**：LineBreaker 是 Phase 3 Layout 核心、Sprint 33-49 持續 17 sprint 在此 thrash、應由 user 在 fresh context 親自 review prep test + VR delta 後再 GO
3. **Sprint 46 + 49 翻車教訓殷鑑不遠**：兩次都「實驗看起來對、VR 全域翻車」；Sprint 136 即使有 hypothesis-driven 設計仍有顯著風險（VR 是 noise-free 量化指標、user 應親自看 delta）
4. **規畫書 §11.3 心理建設 12-36 個月旅程**：本判別子已 backlog 數月、defer 1-2 sprint 待 user GO 不影響整體節奏
5. **autonomous_roadmap.md 階段 B 收益估算**：本 cluster 預期 0~-1pp、屬「邊緣優化」、與 Phase 4 capture 85% 主軸相比優先級低

**這個 DEFER 可逆**：本 audit doc 已完整列出 Sprint 136 設計 sketch + prep test 計畫 + 風險評估；user GO 後可一次完成。同型決策模式與 Sprint 127/128 一致（probe → autonomous DEFER 給 user）。

### 7. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**（本 sprint 無 production code 變動）|
| L2 VR v14 | **跳過**（同上）|
| L3 Spot check | ✅ 42 fixture 結構化 walk 完成、分類完備、判別子 hypothesis 確立 |
| L4 Odoo backend | **跳過** |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `docs/sprint135_docgrid_snap_probe.md` | 本 audit doc | probe findings + Sprint 136 設計 sketch + autonomous DEFER 決策 |
| `docs/autonomous_roadmap.md` | Sprint 135 ✅ + 進度表 + Sprint 136 候選註記 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + §0.1 註記 docGrid snap probe 完成 | 同步 |

**0 production code 變動**（純 docs probe sprint、紀律 #3 經典應用）。

### Test 數變動

- Sprint 134 結尾：vitest 1133 + 1 skipped
- Sprint 135 結尾：vitest **1133 + 1 skipped**（未變、純 probe）

### VR 數變動

- Sprint 134 結尾：mean 0.073191
- Sprint 135 結尾：mean **0.073191**（未跑、純 probe）

### 規畫書 §0.2 Phase 完成度

- Phase 3 Layout Engine：93%（未變、probe 不算實作）
- 但 §0.1 長期 backlog「docGrid snap 段落層級判別子」**probe 完成、Sprint 136 候選 ready**

---

## Root cause

**為什麼 Sprint 46 + 49 找不到判別子**：

1. Sprint 46 focus 「exact」概念、Sprint 49 focus 「無 spacing.line」概念 — 都是試從 OOXML attribute 找答案、忽略「段落上下文（context）」
2. 兩 sprint 都直接做「修改 + VR」、沒先做「結構分析 + 找判別子」的 probe sprint；Sprint 49 §5 雖建議「找判別子」但被 §8 路線 B（接受、轉商業化）覆蓋
3. autonomous_roadmap.md 階段 B cluster 7 才正式給此 spike 結構性空間

**為什麼 Sprint 135 找到了**：

1. Sprint 121-134 累積 14 個成功 sprint、建立紀律 #3 / #18 操作框架
2. 規畫書 §11 候選清單外部化（autonomous_roadmap.md）後、長期 backlog 有 cluster 7 結構性 placeholder
3. 結構化分析 42 fixture（四維度分類）= 跨 fixture 比較、找到「02 vs 03 全套管」這組對比的關鍵差異
4. Pythonic walk + tag-aware in_tc tracking = 工具層級進步、Sprint 46+49 era 沒有此 probe 工具

---

## 紀律

### 紀律 #3 經典應用（Sprint 135）

> 高風險改造前先 probe sprint 收集事實。

Sprint 135 = pure probe sprint、0 production code 變動、focus 在「找判別子」。與 Sprint 60（PhaseD performance probe）、Sprint 127（FontMetricsAdapter production migration probe）、Sprint 128（HarfBuzz spike）同類。

未來 Sprint 136 GO 後 = probe-driven 實作、有結構化基礎、降低 Sprint 46/49 翻車重演風險。

### 紀律 #4 應用（Sprint 135）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

Sprint 135 揭示：

1. **Sprint 49 §8「判別子尚未找到」非永久結論**：Sprint 135 結構化分析找到了 — 但需累積 14 sprint 紀律 + 工具進化才有此能力（教訓：backlog 不要「永久 defer」、應留 cluster 結構讓未來 revisit）
2. **02 body 4 個 placeholder 與 03 body 3 個 title 都「無 spacing.line 無 explicit snapToGrid」**：純看 OOXML attribute 找不到差異、需看「段落上下文」（in cell vs body）
3. **Sprint 46+49 嘗試 OOXML attribute-level 規則都失敗**：判別子必然是 context-level（layout structure）、attribute alone 不夠

### 紀律 #18 持續

PR-size 守住：0 production code / 1 audit doc / 1 roadmap update / 1 planning doc 同步。明示 4 項不在 scope（prep test / 實作判別子 / 整合 / VR 驗證；皆 Sprint 136 範圍）。

### 紀律 #22 候選跨 sprint 驗證進展 2 → 3（升正式）

紀律 #22 候選（Sprint 127）：「external 候選 ≠ scope 小、開工前 probe」

- Sprint 127 應用（FontMetricsAdapter production migration probe）
- Sprint 128 應用（HarfBuzz WASM spike）
- **Sprint 135 應用**（docGrid snap 判別子 probe）

跨 3 sprint 驗證完成、**升正式紀律 #22**：

> **紀律 #22**（Sprint 135 升正式）：規畫書 §11 候選 / autonomous_roadmap 階段 backlog 項目開工前先 probe sprint 確認「mental model vs 實況」差距、收集結構化事實、避免直接做修改翻車（Sprint 46/49 教訓）。
> **Why**：autonomous sprint 在 absence of user guidance 下、容易把 backlog 當成「拿來就做」、忽略 scope 真實大小與技術前提
> **How to apply**：任何 backlog 開工前先 probe（讀規畫書 / autonomous_roadmap / 歷史 audit）+ 結構化收集事實（fixture 走訪 / spike test）+ 寫 audit doc 對齊 hypothesis；只有 probe 結果支持 implementation 才進實作 sprint

紀律 20 → **21 條**。

---

## 後續

### Sprint 136（user GO 後執行）

**Sprint 136 = docGrid snap 段落層級判別子實作**（待 user GO）：

按本 audit §5 sketch 實作：
1. ParagraphInput 加 `isInTableCell?: boolean`
2. LineBreaker.applyDocGridSnap 加 in-cell check
3. Paginator + TableLayout 注入 flag
4. prep test：02 body / 03 全套管 body 各驗證
5. VR 跑全 42 fixture、確認 03 收斂 > 02 退化

預期 PR-size 中等：types +5 / LineBreaker +5 / Paginator/TableLayout +20 / prep test +40 / 1 audit / 1 bundle rebuild。

### Sprint 135+ 候選

- **Sprint 137：二次判別「字型 sz ≥ 12pt」**（若 Sprint 136 結果 02 退化 > +0.5pp）
- **Sprint 138：opentype.js 真實字型 metric**（Sprint 49 §5 路線 C；屬 §Phase 2 字型範圍、defer）
- **更深 layout context 判別子探索**（如 paragraph 與 section 屬性、relative position）

### 階段 B cluster 7 規劃

cluster 7 (135) 為 probe；GO 後（user 決策）轉 cluster 8 (136) 為實作；若需二次判別則 cluster 9 (137)。整個 docGrid snap subproject scope ≤ 3 sprint。

---

## Sprint 135 結尾累積指標

- vitest **1133 passed + 1 skipped**（未變）
- VR mean **0.073191** / failed 0 / compared 126（未跑、純 probe）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 3 Layout Engine 93%（未變）
- 21 ADR / 紀律 **21 條**（+#22 升正式）+ 6 子 + 1 候選（#20 集中索引）
- Sprint audit doc 數 134 → **135**
- 階段 B cluster 7 (135) **完成 probe**、Sprint 136 候選 ready 等 user GO

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint135_docgrid_snap_probe.md  (本 audit doc + Sprint 136 設計 sketch)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 135 ✅ + 紀律 #22 升正式)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + §0.1 註記)
```

**0 production code 變動**。階段 B cluster 7 (135) probe 完成、紀律 #22 升正式（20 → 21 條）、Sprint 136 候選 ready 待 user GO。
