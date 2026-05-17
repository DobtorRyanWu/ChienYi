# Sprint 136 — isInTableCell 判別子實作翻車 + revert（Sprint 46/49 模式重演）

**日期**：2026-05-18
**類型**：code change → **VR 翻車 → revert（byte-identical Sprint 135）**
**規畫書對應**：§0.1 長期 backlog「docGrid snap 段落層級判別子」+ autonomous_roadmap.md 階段 B cluster 7 行 2
**前置 sprint**：Sprint 135 probe（找到候選判別子「段落是否在 table cell 內」+ Sprint 136 設計 sketch）

---

## Hypothesis（驗證對象）

Sprint 135 probe Hypothesis B：

> 預期 03 全套管系列 -1~2pp 改善（Sprint 49 §3 觀察值）、02_std_table 約 +0.1~0.5pp 退化、total -0.5~1pp 收斂。

實作 Sprint 135 §5 設計 sketch（ParagraphInput.isInTableCell 注入 + LineBreaker.applyDocGridSnap body 段落特例 snap）後跑全 42 fixture VR 驗證。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B cluster 7 行 2：Sprint 136 = 實作 Sprint 135 sketch
- 本 sprint scope = 完整實作 Sprint 135 §5 sketch + prep test + 全 42 fixture VR 驗證 + GO/REVERT 決策
- PR-size：types.ts +20 行 → revert / BoxBuilder.ts +5 行 → revert / TableLayout.ts +1 行 → revert / Paginator.ts +2 行 → revert / LineBreaker.ts +5 行 → revert / docGrid.test.ts +60 行 → 改為 lockdown +25 行 / 1 audit / 1 bundle rebuild → revert

### 2. 修法（已 revert、僅留 audit）

#### 2.1 ParagraphInput 加 isInTableCell?: boolean
#### 2.2 buildParagraph 加第 4 個 optional parameter（isInTableCell?: boolean）
#### 2.3 TableLayout L134 注入 true（in-cell）
#### 2.4 Paginator L381 + L703 注入 false（body）
#### 2.5 CanvasRenderer L374（textbox）未注入 = undefined（safety default）
#### 2.6 LineBreaker.applyDocGridSnap：
```ts
if (!para.props.spacing?.line && para.isInTableCell !== false) {
  return height;  // Sprint 29 guard 只對 cell 內或未注入段落生效
}
```

### 3. VR 全 42 fixture 實測 — 翻車

#### Per-fixture delta（>0.005pp）：

| 方向 | Fixture | prev | curr | Δ |
|---|---|---|---|---|
| **退化** | 03_complex_table/1121229-全套管 | 0.1853 | 0.2000 | **+1.468pp** ✗ |
| **退化** | 03_complex_table/1130105-全套管 | 0.2012 | 0.2126 | **+1.133pp** ✗ |
| **退化** | 03_complex_table/1130516-共月橋 | 0.1992 | 0.2105 | **+1.128pp** ✗ |
| **退化** | 03_complex_table/1130109-全套管 | 0.1994 | 0.2080 | **+0.862pp** ✗ |
| **退化** | 03_complex_table/1130112-全套管 | 0.2262 | 0.2348 | **+0.858pp** ✗ |
| 收斂 | 04_with_image/05.照片1120923 | 0.1960 | 0.1859 | -1.009pp ✓ |
| 收斂 | 04_with_image/05.照片 | 0.1898 | 0.1847 | -0.510pp ✓ |
| 微 | 01_simple 7 fixture | 0.064-0.075 | ±0.01-0.03pp | 噪音級 |
| 微 | 03 估驗計價 2 fixture | ≈0.05 | -0.01pp | 噪音級 |

#### 聚合：
- **aggregate VR mean +0.021pp 淨退化**（0.073191 → 0.073401）
- page count baseline mismatch **6 → 8（+2）**
- renderer ops fingerprint snapshot mismatch（預期、因 line height 改）

#### 預期 vs 實際對照：
| 維度 | Sprint 135 Hypothesis B 預期 | 實際 |
|---|---|---|
| 03 全套管 | **-1~2pp 收斂** | **+0.86~1.47pp 退化**（方向相反） |
| 02_std_table | +0.1~0.5pp 退化 | ≈ 0（無 docGrid trigger）|
| 04 照片 | 無提及 | -0.51~1.01pp 收斂（非預期收益） |
| total | -0.5~1pp 收斂 | +0.021pp 退化（方向相反） |

### 4. Root cause（hypothesis 為何錯）

#### 4.1 Sprint 49 §2 Pillow 量測 ≠ snap 公式自動結果

Sprint 49 §2 量測 03 全套管 title block：
- p0（22pt）golden = 35.8pt（非 36 整數倍）
- p1 line1（18pt）golden = 36.0pt
- p1 line2（18pt）golden = 36.0pt
- Total title block 高度差 = render 69.6 vs golden ~96 → **應補 26.4pt**

Sprint 136 snap 公式套用結果：
- p0：26.4 → ceil(26.4/18)×18 = **36** = +9.6pt（golden 35.8、誤差 0.2pt、可接受）
- p1 line1：21.6 → **36** = +14.4pt
- p1 line2：21.6 → **36** = +14.4pt
- Total push = **+38.4pt**（vs Sprint 49 §2 差 26.4 → overshoot **+12pt**）

→ snap 公式對 p1 兩行各補 14.4pt（合理 per spec），但累積後 title block 比 golden 高 12pt → 後續 table / photo Y 整體下推 12pt → 與 golden 對齊度更差。

#### 4.2 golden 的 snap 行為非「乾淨 ceil to pitch」

實證：golden p0 = 35.8pt（非 36 整數倍）暗示 Word 的 snap 演算法可能不是純 `ceil(h/p)×p`、而是更複雜（如 baseline-aware snap、leading-only snap）。Sprint 136 用 spec-naive ceil 公式無法重現 golden 精確值。

#### 4.3 03 全套管 5 fixture 全退化非偶然

5 fixture 共享同一份模板（title block 結構相同：1 行 22pt + 2 行 18pt），同一 snap 公式對全部產生 +12pt overshoot → VR 全 +0.86~1.47pp 退化。**結構性翻車、非雜訊**。

#### 4.4 04 照片改善的非預期收益

04 監造會議照片改善 -0.51~1.01pp。原因猜測：照片下方有 body 段落（如註腳、頁尾文字），這些段落 snap 後高度增加 → page break 位置改變 → 照片在頁面內位置改變，恰好較接近 golden。屬「另一條 fixture 路徑的副作用」、非 Sprint 135 Hypothesis 提及。

### 5. 三層 SOP（revert 後）

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1136 passed + 1 skipped**（revert 後從 1141 起、-5 個 hypothesis test + 改寫 -7 + lockdown +3 = -1 net）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（byte-identical Sprint 135）|
| L3 Spot check | ✅ TypeScript build PASS、bundle rebuild 27.2s + VR pipeline rebuild 29.6s |
| L4 Odoo backend | **跳過**（無 backend 變動）|

**Revert 確認**：production code 完全 byte-identical Sprint 135（applyDocGridSnap / ParagraphInput / buildParagraph 簽章 / TableLayout / Paginator 全部回到 Sprint 135 狀態）。

### 6. 紀律 Strategy A 救命模式應用

與 Sprint 110 同樣模式（並存 → 翻車 → byte-identical revert）：
1. 完整實作 + 全 VR 驗證
2. 結果不符 hypothesis → 立即 revert
3. 寫 audit 紀錄翻車 root cause + 留下 sprint 137+ candidate
4. 不嘗試「修補」現有實作（避免 sunk cost fallacy 持續鑽牛角尖）

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/layout/types.ts` | 0 行（暫時 +20 → revert）| 無淨變更 |
| `static/src/core/layout/BoxBuilder.ts` | 0 行（暫時 +5 → revert）| 無淨變更 |
| `static/src/core/layout/TableLayout.ts` | 0 行（暫時 +1 → revert）| 無淨變更 |
| `static/src/core/layout/Paginator.ts` | 0 行（暫時 +2 → revert）| 無淨變更 |
| `static/src/core/layout/LineBreaker.ts` | **+10 行**（applyDocGridSnap 註解擴 Sprint 136 翻車紀錄）| 文件級補 |
| `tests/unit/layout/LineBreaker.docGrid.test.ts` | **+30 行 / 3 新 lockdown test** | Sprint 29 行為鎖定（防範未來重蹈覆轍）|
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（byte-identical Sprint 135 內容）| 同步 |
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild（byte-identical Sprint 135 內容）| VR pipeline 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、數值 byte-identical | VR confirm |
| `docs/sprint136_isintablecell_revert.md` | 本 audit doc | 紀錄翻車設計 |
| `docs/autonomous_roadmap.md` | Sprint 136 ✅（標 「revert」）+ 紀律 #1 子原則候選 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + §0.1 註記 | 同步 |

**淨 production code 變動 = 10 行註解 + 30 行 test lockdown**。applyDocGridSnap byte-identical Sprint 135 + 16 字節 .map 變動屬於 timestamp。

### Test 數變動

- Sprint 135 結尾：vitest 1133 + 1 skipped
- Sprint 136 結尾：vitest **1136 + 1 skipped**（+3 從 lockdown test）

### VR 數變動

- Sprint 135 結尾：mean 0.073191（byte-identical）
- Sprint 136 結尾：mean **0.073191**（byte-identical Sprint 135、revert 確認）

### 規畫書 §0.2 Phase 完成度

- Phase 3 Layout Engine：93%（未變、革命未成 + revert）

---

## 紀律

### 紀律 #1 經典應用（Sprint 136）

> 改 BrowserCanvasRenderContext / CanvasRenderer 後強制跑全 42-fixture VR — 單元測試 spy 不反映 OOXML pixels

Sprint 136 嚴格遵守：unit test 7/7 通過（驗證新 snap 邏輯）、但 VR 全 42 fixture 揭示翻車 → revert。**Sprint 46/49 教訓再次驗證**：trace + prep test 命中 ≠ 全域正確。

### 紀律 #4 應用（Sprint 136）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

Sprint 136 揭示：

1. **Sprint 49 §2 Pillow 量測 ≠ snap 公式自動結果**：spec-naive ceil 公式對 p1 兩行各補 14.4pt（合理 per spec）、但累積後 overshoot golden 12pt。**snap 是 spec-defined 但 golden 行為 spec-undefined**
2. **Sprint 135 probe Hypothesis B 預期方向錯**：probe 找到結構判別子（in-cell vs body）正確、但「body 該 snap」hypothesis 對 03 全套管反向作用
3. **04 監造會議照片是非預期收益方**：probe 完全未提、實際 snap body 段落間接改善 photo Y。揭示「fixture 間 cascade effect 複雜性」
4. **「修補」誘惑 vs 「revert」紀律**：Sprint 110 教訓本可救（如「snap 比例縮 30%」「skip first paragraph」），但都屬 fitting noise、無 spec 基礎、應 revert 不要堆 hack

### 紀律 #1.a 第 12 次連續驗證（revert 後）

連續 12 sprint code change 都跑全 VR 並維持 byte-identical（含本 sprint revert 後）：

| Sprint | 改動 | VR |
|---|---|---|
| 121-126 | parser / utility 補完 | 0.073191 ×6 |
| 130-134 | Phase 4 補完 | 0.073191 ×5 |
| **135** | probe（no code）| 0.073191 |
| **136 (revert)** | revert byte-identical | **0.073191** |

紀律 #1.a **12 次連續 byte-identical**（含 revert 後）、Strategy A 救命模式有效。

### 紀律 #22 應用（Sprint 136 反例）

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Sprint 135 = 紀律 #22 標準 probe sprint。但本 sprint 仍翻車 → 紀律 #22 是必要條件、非充分條件。**probe 只能降低風險、不能消除實作翻車**。Sprint 137+ 需更深的 probe（如 Pillow 自動量測工具、per-fixture render vs golden delta 公式驗證）才可能避免重演。

### 紀律 #18 持續

PR-size 守住：本 sprint 最終 net = 1 audit doc + 10 行註解 + 30 行 test lockdown。完全符合「revert 後不留 dead scaffold」原則。

---

## 後續

### 紀律 #1 補強候選

> 提案紀律 #1.b：實作 backlog spike 後 VR 翻車時、必須完整 revert 至 baseline、不嘗試「微調 + retry」（避免 fitting noise）。

跨 sprint 驗證進展：
- Sprint 110（esign UI revert 全 Sprint 90-109）= 1
- Sprint 136（isInTableCell 全 revert byte-identical）= 2
- 待 Sprint 137+ 第 3 次驗證可升正式 #1.b

### Sprint 137 候選（**user 親自 GO 後執行**、autonomous DEFER）

**Sprint 137 = Phase 3 docGrid 議題長期 defer**（per Sprint 49 §5 路線 B「轉商業化」+ Sprint 136 翻車證據）：

| 候選方向 | 預期收益 | 風險 | autonomous 評估 |
|---|---|---|---|
| **A. 接受殘餘、defer docGrid**（路線 B）| 0 | 0 | **推薦** — Sprint 46/49/136 三次失敗證實此問題需大 spike |
| B. opentype.js 真實字型 metric（Sprint 49 §5 路線 C）| 中（mean -1~2pp）| 高（大工程、可能撞 IIFE bundle）| defer 階段 D |
| C. 重生 goldens 用 Word desktop（autonomous_roadmap 階段 C）| 高（換 anchor、mean -1~2pp）| 中（wsl 環境限制）| 階段 C 主軸、Sprint 138+ |
| D. snap 公式進階（baseline-aware / leading-only / fixture-specific 縮放）| 不確定 | 極高（fitting noise 風險）| **拒絕** — 違反紀律 #1.b 候選 |

**autonomous 推薦 A**：接受 docGrid snap 議題為長期 defer、轉進其他 phase。Sprint 136 已是第 3 次此類失敗、累積 hypothesis-space 已枯竭、需 metric anchor 換新（階段 C 重生 goldens）才有結構性突破。

### Sprint 136+ 候選總覽

- A. Phase 4 wire-up（numberingFormatter / textAlignment / framePr 整合到 mapper/renderer）
- B. Phase 5 開工（OMML / SmartArt / 追蹤修訂等大 scope）
- C. 階段 C 重生 goldens（Sprint 136-138 autonomous_roadmap.md 原排）
- D. Phase 6 docx export 對稱性（Sprint 161+）

---

## Sprint 136 結尾累積指標

- vitest **1136 passed + 1 skipped**（+3 lockdown test、淨增 + lockdown 結構）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical Sprint 135、**第 12 次連續**含 revert）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 3 Layout Engine 93%（未變）
- 21 ADR / 紀律 **21 條** + 6 子 + **2 候選**（#20 集中索引、新 #1.b 候選跨 sprint 驗證 1/3）
- Sprint audit doc 數 135 → **136**
- 階段 B cluster 7 (135-136) **完成**（135 probe、136 revert）；docGrid snap 議題 autonomous 推薦 defer 進階段 C

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/layout/LineBreaker.ts  (+10 行 applyDocGridSnap 註解擴 Sprint 136 翻車紀錄)
M  addons/dobtor_doc_editor/tests/unit/layout/LineBreaker.docGrid.test.ts  (+30 行 / 3 新 lockdown test，Sprint 136 hypothesis 7 test → revert)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild byte-identical)
M  addons/dobtor_doc_editor/tools/dist/visual_regression_pipeline.iife.js  (rebuild byte-identical)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint136_isintablecell_revert.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 136 ✅ revert)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

**production code byte-identical Sprint 135**（applyDocGridSnap / ParagraphInput / buildParagraph 簽章 / 所有 caller 全部 revert）。Sprint 46/49/136 三次 docGrid snap 議題失敗、autonomous 推薦長期 defer 並進階段 C 換 metric anchor。
