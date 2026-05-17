# Sprint 134 — w:textAlignment + w:framePr 解析（Phase 4.4 收尾）

**日期**：2026-05-17
**類型**：code change（ParagraphParser API 補完 / Phase 4.4 收尾）
**規畫書對應**：§Phase 4.4「`<w:frame>` 段落框、`<w:textAlignment>`」+ autonomous_roadmap.md 階段 B cluster 6 行 2
**前置 sprint**：Sprint 133 paragraph pBdr + shd（cluster 6 第 1 個）

---

## Hypothesis（驗證對象）

`ParagraphParser.parseParagraphProps` 完全沒處理：
- `<w:textAlignment>`（OOXML §17.3.1.36 文字行內垂直對齊）
- `<w:framePr>`（OOXML §17.3.1.11 段落框基礎屬性）

兩者在 ParagraphProps 也都沒型別定義（不像 borders/shading 至少 shape 已有預留）。實務影響：
- textAlignment：行內混合不同字型大小 / 圖示時 baseline 對齊資訊遺失
- framePr：drop cap / 邊欄注釋 / 浮動段落整個資訊掉、layout 階段無資料可用

**Hypothesis A（功能正確性）**：新增 ParagraphProps.textAlignment + framePr 欄位、parser 補完 capture；無效列舉值 silent drop（不污染 AST），空集合不掛 key（紀律 #21）。

**Hypothesis B（VR 穩定性）**：42 fixture 多為政府表格、無 drop cap、無浮動段落、textAlignment 罕見指定；預期 byte-identical（紀律 #1.a 第 11 次連續驗證機會）。

**Hypothesis C（scope 釐清）**：「tab stop leader 渲染」屬 Layout/Renderer wire-up、parser 已 Sprint 1 capture leader 屬性；本 sprint 不動 Layout、待 Phase 5+ Layout sprint。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B cluster 6 第 2 個：「134 | Phase 4 Style | 4.4 剩餘：`<w:textAlignment>` + tab stop leader 渲染 + frame 基礎」（Sprint 133 audit decided）
- 規畫書 §Phase 4.4：「`<w:frame>` 段落框、`<w:pBdr>` 段落邊框 + 陰影、`<w:tab>` tab stop 進階、`<w:textAlignment>`」
- 本 sprint scope = **textAlignment capture + framePr capture**
- 不在 scope（留未來 sprint）：
  - tab stop leader 渲染 wire-up（parser 已 Sprint 1 capture、屬 Layout 階段）
  - drop cap 進階屬性（`w:dropCap` / `w:lines`、罕用、defer）
  - framePr `w:anchorLock`（罕用、defer）
  - tab stop decimal align 真實對齊（屬 Layout 階段）
- PR-size：types.ts +45 行（2 新欄位 + 完整 enum 定義）/ ParagraphParser.ts +85 行（10 行 inline + parseFramePr +75 行）/ test +130 行 / 15 新 test / 1 audit / 1 bundle rebuild

### 2. 設計決策

#### 2.1 textAlignment 為何採完整 enum 嚴格篩選

OOXML §17.3.1.36 列 5 值：auto / top / center / baseline / bottom。解析時嚴格 enum check：

```ts
if (v === 'auto' || v === 'top' || v === 'center' || v === 'baseline' || v === 'bottom') {
  props.textAlignment = v;
}
```

無效值 silent drop（不 default to 'auto'）：避免污染 AST、保留「未指定」與「明示 auto」的語意差。

#### 2.2 framePr 為何只 capture 主流屬性

OOXML §17.3.1.11 framePr 完整屬性集合 15+：
- 大小：`w` / `h` / `hRule`
- 間距：`hSpace` / `vSpace`
- 環繞：`wrap`
- 錨點：`hAnchor` / `vAnchor` / `xAlign` / `yAlign` / `x` / `y`
- 進階：`dropCap` / `lines` / `anchorLock`

Sprint 134 capture 前 11 項（大小 + 間距 + 環繞 + 錨點），defer 後 3 項（drop cap 罕用 + 鎖點）。

理由：drop cap 需 Layout 階段特殊處理（lines 屬性決定字母佔幾行高、影響 line break 計算）、屬獨立 feature；本 sprint 限於 capture、不擴大 Layout 影響範圍。

#### 2.3 為什麼 attrTwip 直接信任 ParagraphParser 既有 helper

`attrTwip(el, name)` 已是 ParagraphParser 內部 helper（Sprint 1 起穩定）、用 `twipToPt(parseInt(...))` 將 twip 轉 pt。直接 reuse、不另做包裝。

### 3. 修法

#### 3.1 types.ts ParagraphProps 擴 2 欄位（+45 行）

```ts
export interface ParagraphProps {
  // ... existing ...
  textAlignment?: 'auto' | 'top' | 'center' | 'baseline' | 'bottom';
  framePr?: {
    width?: Pt; height?: Pt;
    hRule?: 'auto' | 'atLeast' | 'exact';
    hSpace?: Pt; vSpace?: Pt;
    wrap?: 'around' | 'notBeside' | 'through' | 'tight' | 'none';
    hAnchor?: 'margin' | 'page' | 'text';
    vAnchor?: 'margin' | 'page' | 'text';
    xAlign?: 'left' | 'center' | 'right' | 'inside' | 'outside';
    yAlign?: 'top' | 'center' | 'bottom' | 'inside' | 'outside' | 'inline';
    x?: Pt; y?: Pt;
  };
}
```

#### 3.2 ParagraphParser.ts inline textAlignment + parseFramePr helper（+85 行）

textAlignment 寫 inline（10 行）— 簡單 enum check 不需 helper。

framePr 抽 parseFramePr helper（75 行）— 11 個屬性嚴格 enum check + 紀律 #21 空集合不掛 key。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1133 passed + 1 skipped**（從 1118+1 起、+15 新 test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（byte-identical、**第 11 次連續**、紀律 #1.a 應用）|
| L3 Spot check | ✅ TypeScript build PASS（pre-existing warning 同前、bundle rebuild 30.0s）|
| L4 Odoo backend | **跳過**（無 backend / model / ACL 變動）|

### 5. Unit test 設計（15 個新 test）

#### textAlignment 8 個（含 it.each 展開 5 enum）

| Test | 鎖定行為 |
|---|---|
| auto / top / center / baseline / bottom（5 個 it.each）| 每個 enum 值正確 capture |
| garbage 無效值 → silent drop | 不污染 AST |
| 缺 w:val → silent drop | 防禦缺屬性 |
| 普通段落（無 textAlignment）→ 不掛 key | 回歸驗證 |

#### framePr 7 個

| Test | 鎖定行為 |
|---|---|
| 完整 framePr（w/h/hRule/hSpace/vSpace/wrap/hAnchor/vAnchor/xAlign/yAlign）| 主路徑 11 屬性 capture |
| 絕對位置 x/y（替代 xAlign/yAlign）| x/y 與 align 兩種定位法都 work |
| 部分屬性 → 其他 key 不掛 | 紀律 #21 |
| 全空 → 整 framePr 不掛 | 紀律 #21 |
| 無效列舉值（hRule="garbage"/wrap="invalid"）→ silent drop、其他屬性保留 | 嚴格 enum + 部分 salvage |
| 普通段落（無 framePr）→ 不掛 | 回歸 |
| framePr + textAlignment + pBdr + shd 同存 → 互不干擾 | 跨欄位 isolation |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | +45 行（ParagraphProps textAlignment + framePr 欄位 + 完整 JSDoc）| 型別擴充 |
| `static/src/core/ooxml/document/ParagraphParser.ts` | +85 行（textAlignment inline + parseFramePr helper）| 解析補完 |
| `tests/unit/ParagraphParser.test.ts` | +130 行 / 15 新 test（含 it.each 5 enum）| 鎖定行為 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、byte-identical | VR confirm |
| `docs/sprint134_text_alignment_frame_pr.md` | 本 audit doc | 紀錄補完設計 |
| `docs/autonomous_roadmap.md` | Sprint 134 ✅ + 階段 B cluster 6 完成 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | §0.2 Phase 4 84% → 85% + §Phase 4.4 註記 | 同步 |

### Test 數變動

- Sprint 133 結尾：vitest 1118 + 1 skipped
- Sprint 134 結尾：vitest **1133 + 1 skipped**（+15）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 133 結尾：mean 0.073191（byte-identical）
- Sprint 134 結尾：mean **0.073191**（byte-identical、**第 11 次連續** 121→126→130→131→132→133→134）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style Theme：84% → **85%**（+1%、4.4 textAlignment + framePr capture 補完；剩 tab leader 渲染 wire-up（Layout）、drop cap 進階）

---

## Root cause

**為什麼 textAlignment / framePr 一直沒做**：

1. ParagraphProps shape 中根本沒這兩個欄位 → 沒有「半實作」狀態觸發注意
2. 42 fixture 0 個 textAlignment / framePr trigger → 無 VR signal
3. 規畫書 §Phase 4.4 列為「進階」、Phase 1-3 OOXML/Layout 主軸優先、Phase 4 排在後段
4. autonomous_roadmap.md 階段 B cluster 6 才正式啟動 Phase 4.4

**為什麼 VR byte-identical**：

新增 capture 路徑、現有 fixture 不 trigger 新 if 分支 → render path 完全等價、PNG byte-identical。未來如 fixture 含 drop cap 或浮動段落、capture 後仍需 Layout 階段消費才會 render 出來、屬整合 sprint 範圍。

---

## 紀律

### 紀律 #1.a 第 11 次連續驗證（Sprint 134）

連續 11 sprint code change 都跑全 VR 並維持 byte-identical：

| Sprint | 改動 | VR |
|---|---|---|
| 121 | trHeight | 0.073191 |
| 122 | OLE/pict fallback | 0.073191 |
| 123 | field code | 0.073191 |
| 124 | sdt unwrap | 0.073191 |
| 125 | bookmark capture | 0.073191 |
| 126 | hyperlink 3 屬性 | 0.073191 |
| 130 | HSL luminance | 0.073191 |
| 131 | tblStylePr/tcPr | 0.073191 |
| 132 | numberingFormatter | 0.073191 |
| 133 | pBdr/shd + DRY | 0.073191 |
| **134** | **textAlignment + framePr** | **0.073191** |

紀律 #1.a **11 次連續 byte-identical**、覆蓋 6 類修改點 + 「型別擴充 + parser capture」第 7 類。

### 紀律 #21 第 4 次正式應用（Sprint 134）

> optional 欄位空集合不掛 key（升正式 Sprint 131）。

Sprint 134 嚴格 enforce：
- textAlignment 無效列舉 → 不掛
- framePr 全空 → 不掛
- framePr 部分屬性 → 其他 key 不掛
- framePr 無效列舉值（hRule="garbage"）→ 該 key 不掛、其他屬性 salvage

### 紀律 #18 持續

PR-size 守住：types +45 / parser +85 / test +130 / 1 audit / 1 bundle。明示 3 項不在 scope（tab leader 渲染 wire-up / drop cap 進階 / anchorLock）。

### 紀律 #4 驗證（Sprint 134）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

對比 Sprint 133（pBdr/shd 是「ParagraphProps shape 已有、parser 沒接」的結構性技術債）、Sprint 134 是「ParagraphProps shape 也沒有、完全 ground-up 新增」。兩種 gap 都對 Phase 完成度有影響、需 spec compliance audit 才能找出（VR signal 不會揭示）。

---

## 後續

### Sprint 135（cluster 6 完成、進 cluster 7）

階段 B cluster 6 (133-134) 已完成 Phase 4.4 capture 部分。**Phase 4 整章 85% 達標**（剩餘 wire-up 屬 Layout 階段）。

**下一個方向**：cluster 7 Phase 3 漏項 docGrid snap 段落層級判別子（autonomous_roadmap.md 階段 B 行 7）：

- 規畫書 §0.1 列為長期 backlog
- Sprint 46+49 全域 docGrid snap 翻車過、需段落條件式
- **屬大型 spike sprint**、需 probe 收集事實 + per-fixture delta 分析
- 預計 PR-size 中大、可能拆 2-3 sprint（probe → 整合 → 收尾）

**autonomous 決策**：先做 Sprint 135 = docGrid snap probe sprint（紀律 #3）— 收集 42 fixture 真實使用狀況 + ChienYi 監造文件對 docGrid 的依賴度、再決策後續實作 sprint 數。

### Sprint 134+ 候選

- **tab stop decimal align 真實渲染**：Layout 階段、屬 Phase 3 Layout Engine 範圍
- **drop cap 進階屬性**（dropCap / lines）：framePr 配套、罕用、defer
- **wire-up framePr 到 Layout**：浮動段落渲染、屬 §Phase 3.4 wrapTight 同範圍
- **wire-up textAlignment 到 Layout**：baseline 計算、屬 §Phase 2 字型範圍

---

## Sprint 134 結尾累積指標

- vitest **1133 passed + 1 skipped**（+15）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 11 次連續**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style Theme 84% → **85%**（cluster 6 完成、Phase 4 capture 部分完工）
- 21 ADR / 紀律 **20 條** + 6 子 + 2 候選（無新增、#22 候選持平 2/3、#20 候選持平 1/3）
- Sprint audit doc 數 133 → **134**
- 階段 B cluster 6 (133-134) **完成**、進入 cluster 7 (135) Phase 3 docGrid probe

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/ast/types.ts  (+45 行 textAlignment + framePr 欄位)
M  addons/dobtor_doc_editor/static/src/core/ooxml/document/ParagraphParser.ts  (+85 行 textAlignment inline + parseFramePr helper)
M  addons/dobtor_doc_editor/tests/unit/ParagraphParser.test.ts  (+130 行 / 15 新 test 含 it.each 5 enum)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint134_text_alignment_frame_pr.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 134 ✅ + cluster 6 完成)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 4 84→85%)
```

無 model / view / ACL / rule / controller / backend 變動。階段 B cluster 6 完成、Phase 4 capture 部分 85% 達標、紀律 #1.a 11 次連續 byte-identical 穩固。
