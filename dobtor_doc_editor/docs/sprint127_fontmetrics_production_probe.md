# Sprint 127 — FontMetricsAdapter production migration probe + autonomous decision

**日期**：2026-05-17
**類型**：probe sprint（紀律 #3）+ autonomous decision（紀律 #18 子）
**規畫書對應**：§11.1 行 1（migrate doc_editor.js 走 production canvas-editor 整合）+ autonomous_roadmap.md 階段 B 行 3 cluster 3
**前置**：Sprint 64b external 候選、Sprint 65 promote `--font-metrics` default-on（VR pipeline only）

---

## Hypothesis（待驗證）

roadmap 階段 B 行 3 寫：「127-128 | Phase 2 字型 | 把 FontMetricsAdapter 推到 production（目前 opt-in、Sprint 64b external 候選 — Claude 自主執行 migrate doc_editor.js 走自家 pipeline）」。

**假設**（待 probe 驗證）：產品化 = 把 VR pipeline 用的 FontMetricsAdapter「自家 pipeline」flag 在 doc_editor.js production 也打開即可、預期 VR mean -2.3%（Sprint 65 同等改善）落到 production user。

---

## Method

### 1. 三條 docx 處理路徑現況 audit

| 路徑 | 入口 | OoxmlParser | LayoutEngine | FontMetricsAdapter | CanvasRenderer |
|---|---|---|---|---|---|
| **Path 1：default import** | `doc_editor.js _handleImportFile` | ❌ | ❌ | ❌ | ❌ |
| **Path 2：TS engine（DevTools 觸發）** | `doc_editor.js importViaTsEngine` → `POST /dobtor_doc/import?engine=ts` → `parse_docx_cli.cjs` | ✅ | ❌ | ❌ | ❌ |
| **Path 3：VR pipeline（測試）** | `tools/visual_regression_pipeline.entry.ts` | ✅ | ✅ | ✅（Sprint 65 default-on）| ✅ |

關鍵發現：

- Path 1（default）完全走 @hufe921/canvas-editor 內建 docx plugin、我們的 parser / layout / metrics / renderer **全部不參與**
- Path 2（DevTools）只跑 parser → IElement[] → canvas-editor 渲染；layout / metrics / renderer 仍是 canvas-editor 內部
- Path 3（VR）跑完整自家 pipeline；**FontMetricsAdapter 只在這條路徑運作**

### 2. canvas-editor 對「metrics」的處理

@hufe921/canvas-editor 內部用 `ctx.measureText()` 算字寬、自家行高公式算行高（見 `lib/canvas_editor/canvas-editor.umd.min.js` `Draw.ts particle/text/TextParticle`）。它**不接受外部 metrics injection**。要讓 FontMetricsAdapter 影響 canvas-editor 的渲染，必須：

- 改 canvas-editor 內部（fork + patch）
- 或：在 IElement[] 階段預先計算位置（serialize 完整 layout 進 IElement）

### 3. 「promote to production」的 4 個候選策略

| 策略 | 範圍 | 收益 | 風險 |
|---|---|---|---|
| **A. Server-side layout pre-calc** | backend 跑 LayoutEngine + FontMetricsAdapter、output 預定位 IElement[] | 真實 -2.3% VR 收益落到 production | IElement schema 不帶 position；需擴 schema + canvas-editor consumer side patch；scope **5-8 sprint** |
| **B. 完全自家 renderer 取代 canvas-editor** | doc_editor.js 移除 canvas-editor、改用 BrowserCanvasRenderContext + LayoutEngine | 全套 OOXML 高保真渲染 | **15-25 sprint** 工程；canvas-editor 既有功能（IME / 游標 / Undo-Redo / 編輯互動）全部要重做（規畫書 §1.3 已警告） |
| **C. Hybrid metrics injection** | backend 預計算「line metrics map」、塞進 IElement custom field；canvas-editor 內部仍 measureText 但取我們的 cached metrics | 介於 A 與「不做」之間 | 需 fork canvas-editor 一些 measureText 呼叫；schema 半擴；**3-5 sprint** |
| **D. 維持現狀（不 migrate）** | production canvas-editor as-is、VR pipeline 仍是 quality benchmark | 0 risk；既有 production user UX 不變 | 不享受 -2.3% VR 改善；未來高保真需求需要 strategy A/B 才能達 |

### 4. Autonomous decision（紀律 #18.d：read-design-intent-first）

讀 `_handleImportFile` 與 `importViaTsEngine` 註解 + ChienYi production user 場景：

- production user = 監造主管 / 工程師 / 承包商；主用途 = 編輯監造會議記錄 / 施工計畫書（規畫書 [scope_decision.md](scope_decision.md) 定義邊界）
- @hufe921/canvas-editor 的編輯互動（IME / 游標 / Undo-Redo / 多人協作預備）是 production user 的核心 UX
- strategy B 會打斷既有 production；strategy A 需要 schema 工程跨 5-8 sprint
- VR pipeline 0.073191 已達 A- 級邊緣、A 級需 Phase 3+ goldens 重生（屬 §11.1 待 user 決策另一條候選）

**autonomous 決策：採 Strategy D（維持現狀）**。理由：

1. **架構不對齊**：Sprint 64b external 候選的「migrate」假設 == 「flag flip 即可」、實際 == 「需重寫 production render 層」；超出 cluster 2 sprint scope
2. **scope alignment**（紀律 #18）：Sprint 127-128 budget 2 sprint、無法承擔 A/B/C 任一策略；強行做會走 Sprint 90-109 esign UI revert 教訓
3. **production user 風險**：canvas-editor 既有編輯互動是 production 核心、不該因「VR -2.3% 收益」打斷
4. **VR pipeline 仍是有效 quality benchmark**：VR mean 收斂不需依賴 production migration、規畫書 §2.2 A- 級量化標準仍可達

**這個決策可逆**：未來如 user 需要 production 真正高保真、可重啟 Strategy A（IElement schema 擴 position）作為獨立 phase（5-8 sprint）。

### 5. Roadmap 影響

Sprint 127-128 原排：「Phase 2 字型 — FontMetricsAdapter production migration」。

**修正後**：

- **Sprint 127**：本 probe sprint + autonomous decision Strategy D + defer to user（無 code 變動、純 docs）
- **Sprint 128**：原排 Sprint 129「HarfBuzz WASM 整合 spike」**前移**作為 Phase 2 字型替代候選（也是 probe sprint、自然 pair；屬規畫書原列 1-2 週的 spike、不需 production migration）
- **Sprint 129+**：照 roadmap 走 Phase 4 Style（原 130 起）

不擾動 Sprint 130-175 排程。階段 B 從 15 sprint 仍 15 sprint。

### 6. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**（純 docs probe、0 行 source code 變動）|
| L2 VR v14 | **跳過**（無 pipeline 變動）|
| L3 Spot check | ✅ grep / read 確認三條路徑現況、autonomous 決策有 rationale |
| L4 Odoo backend | **跳過**（無 backend 變動）|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `docs/sprint127_fontmetrics_production_probe.md` | 本 audit doc | 紀錄 probe findings + autonomous decision + roadmap 修正 |
| `docs/autonomous_roadmap.md` | Sprint 127 ✅（probe）+ Sprint 128 改為 HarfBuzz spike + 進度表 Sprint 127 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + §11.1 行 1 加註「已 probe 確認非 flag-flip、defer to user」 | 同步 |

### Test 數變動

無變動（純 docs probe）。
- vitest 1028 + 1 skipped
- VR mean 0.073191
- Odoo backend local 31

### 規畫書 §0.2 Phase 完成度

無變動（Phase 2 仍部分；本 sprint 是策略決策、不打 Phase 2 主軸）。

---

## Root cause（為什麼原假設與實況不符）

**Sprint 64b external 候選的 mental model**：

當時（Sprint 64b）只看到 VR pipeline 用 FontMetricsAdapter、預設沒打開；以為 production 也有「FontMetricsAdapter flag」可以 default-on。

**實況**：

production canvas-editor **完全沒整合 FontMetricsAdapter**。Sprint 64b external 候選的「migrate」是 architectural change（重寫 production render 路徑）、不是「flag flip」。Sprint 127 probe 第一次正式 audit 整條路徑後揭示。

→ **教訓**：「external 候選」標記不等於「scope 小」、需 probe 後才知。

---

## 紀律

### 紀律 #3 應用（Sprint 127）

> 高風險改造前先 probe sprint 收集事實。

Sprint 127 完整應用此紀律 — 沒有貿然動 code、先 audit 三條 docx 路徑、發現實況與假設不符、autonomous 決策 defer。**這正是紀律 #3 的範例 case**。

### 紀律 #4 應用（Sprint 127）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

本 sprint 0 code 變動、結果「不 migrate」。但揭示了：

- production canvas-editor 與 VR pipeline 是兩條獨立 render 路徑
- FontMetricsAdapter only-on-VR 是設計 by design、不是漏設定
- 「promote to production」需重新 scope（5-25 sprint 依策略）
- Sprint 64b external 候選的 mental model 需修正

這些是隱性 assumption explicit 化、屬紀律 #4 結構性產出。

### 紀律 #18.d 應用（Sprint 117 揭示）

> 「待 user 決策」候選的 autonomous 收口必須讀原始設計意圖後才決、不能憑 default-secure 直覺。

Sprint 127 應用 #18.d：讀 `_handleImportFile` / `importViaTsEngine` / scope_decision.md 後、autonomous 決策 Strategy D。decision rationale 寫進 audit doc、user 事後可審 / 改方向。

### 新紀律候選（Sprint 127 揭示）

> **紀律 #22 候選**：**「external 候選」標記不代表 scope 小 — 任何 production migration 開工前先 probe**。
>
> **Why**：Sprint 64b external 候選的「migrate」被 mental model 簡化為「flag flip」、實際 Sprint 127 audit 發現是 5-25 sprint scope。external 標記只代表「outside autonomous 範圍」、不代表「執行成本低」。
>
> **How to apply**：規畫書 §11.1「待 user 決策」標記 external / autonomous 的候選、開工前先做 probe sprint 確認 mental model 與實況對齊。

候選未升正式紀律、需跨 3 sprint 驗證（Sprint 128 HarfBuzz spike 屬同類 external 候選、可同樣應用 probe-first 模式驗證）。

---

## 後續

### Sprint 128（修正後）

**HarfBuzz WASM 整合 spike**（原 Sprint 129、前移為 Sprint 128）。同樣是 probe sprint 性質、確認 HarfBuzz 在 OOXML 字型 metric / 字距 pipeline 的技術可行性。屬規畫書原列 1-2 週的 spike。

### Sprint 127+ 候選（defer to user）

以下三項屬 user 決策範圍、本 sprint 不 commit：

- **Strategy A**：IElement schema 擴 position field + backend layout pre-calc（5-8 sprint）
- **Strategy B**：完全自家 renderer 取代 canvas-editor（15-25 sprint、不建議）
- **Strategy C**：Hybrid metrics injection（3-5 sprint、技術細節較多、需先 fork 評估）

User 若決定執行任一、可開新 phase。Sprint 130-175 排程不變。

### 規畫書 §11.1 修正

行 1 候選「migrate doc_editor.js 走 production canvas-editor 整合」**狀態更新**：

- Sprint 127 probe 已揭示 = architectural migration、非 flag flip
- autonomous 範圍：**已決策 Strategy D（維持現狀）**
- user 決策範圍：策略 A/B/C 是否啟動、何時啟動

---

## Sprint 127 結尾累積指標

- vitest 1028 + 1 skipped（未跑、必然一致）
- VR mean 0.073191（未跑、必然一致）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 78% / Phase 2 仍部分（不動）
- 21 ADR / 19 條紀律 + 6 子 + **3 候選**（+ #22 候選 Sprint 127「external 候選 ≠ scope 小、開工前 probe」）
- Sprint audit doc 數 126 → **127**
- 階段 B cluster 3 (127-128) probe sprint 1/2 完成、Sprint 128 改為 HarfBuzz spike

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint127_fontmetrics_production_probe.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 127 ✅ probe / Sprint 128 改 HarfBuzz spike + 進度表)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + §11.1 行 1 加註)
```

無 code / model / view / ACL / rule / test / bundle 變動。純 probe + autonomous decision sprint。
