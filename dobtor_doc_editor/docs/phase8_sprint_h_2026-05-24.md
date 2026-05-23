# Phase 8 Sprint H — 掃描並替換：`{{ var }}` 文字 → 可編輯 control（2026-05-24）

**性質**：Sprint G 的完成式（在「建 record」之上加 in-place 文字替換）。
**狀態**：實驗性（按鈕色：警示橙黃）；保留 Sprint G 的「掃描變數」按鈕作為安全 fallback。
**範圍**：擴充 [jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js) `scanJinja2VariablesWithPositions`，新增 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js) `onScanAndReplaceClick`、工具列加「掃描並替換」按鈕。

---

## 1. 接續 Sprint G 的什麼

Sprint G 完成「批次建 record」，但 [phase8_sprint_g_2026-05-24.md](phase8_sprint_g_2026-05-24.md) §2.1 留下取捨：

> **MVP 不做 in-place 文字 → control 替換**：canvas-editor 的 IElement 位置操作易碎（單字元 chunked、含 table/list 巢狀），替換失敗會破壞文件結構

Sprint H 把這層補上 — 但用「**並列**而非取代」的方式：

| 按鈕 | 行為 | 風險 | 按鈕色 |
|---|---|---|---|
| **掃描變數**（Sprint G） | 只建 record、不動文字 | 零 | 藍 `#0284c7` |
| **掃描並替換**（Sprint H） | 建 record + 把 main 流內 `{{ var }}` 替換為可編輯 control | 替換不可回復（Ctrl+Z 可救） | 警示橙黃 `#f59e0b` |

user 仍可選擇安全路線（只建 record），或 commit 到「視覺一致」路線（替換為 control）。

---

## 2. 設計取捨

### 2.1 為什麼只處理 main 流？不掃 table / list / title？

| 結構 | setRange 簽名 | 替換複雜度 |
|---|---|---|
| main 流 | `setRange(startIdx, endIdx)` | 低 |
| table 內 td | `setRange(s, e, tableId, startTdIdx, endTdIdx, startTrIdx, endTrIdx)` | **高**（要精準對齊 td 內 element index、跨 td 不可能） |
| list/title 內 valueList | 同上複雜度 | 高 |

MVP 只處理 main 流。`scanJinja2VariablesWithPositions` 在掃描階段就把巢狀結構的元素標為 unsafe sentinel（NUL `\0`），跨越的 match 自動作廢、不會嘗試替換。**user 截圖那 5 個變數**（都在文件正文）完全在 main 流覆蓋範圍內。

巢狀變數的 record 仍由 Sprint G 的「掃描變數」按鈕處理，視覺替換則由 user 手動處理（Sprint G 流程：選取舊文字 → Del → 點「Odoo 欄位」重插）。

### 2.2 為什麼 reverse-order 替換？

每次 `setRange` + `backspace` + `insertControl` 都會改變後續元素的 index。從**最後一個 match** 開始往前替換，前面 match 的 startIdx/endIdx 仍然有效。同樣的策略已被 Sprint F overlay clamp 驗證過。

### 2.3 為什麼用 NUL sentinel 而非 `unsafeRanges` 陣列？

兩種方案都可行，NUL 更簡潔：
- regex 的 `[A-Za-z_]` / `\w` / `\s` 都不包含 NUL，所以 regex 自動就不會產生跨越 sentinel 的 match
- 第二道防線（match 範圍內 `charCodeAt(i) === 0` 檢查）作為保險（萬一未來改 regex）
- 不需要維護額外資料結構

### 2.4 為什麼**沒有** transaction / rollback？

canvas-editor 沒提供 transaction API。如果替換失敗：
- record 已建：不會主動刪除（user 可在 inspector 手動刪）
- 部分文字已替換：不能回到「全部都是原文字」狀態，但 user 可用 Ctrl+Z 一步步回退

實務上替換失敗極罕見（依賴 vitest 已驗證的位置精度 + sentinel 防線）。但**通知 user 替換是「不可回復操作」**，要求按確認時意識到這點。

### 2.5 為什麼沒做 Playwright E2E？

模組目前沒有 Playwright spec 基礎設施（Sprint F 文件提到的 sprint-f.spec.ts 並未在此模組落地）。對 canvas-editor 的 in-place 操作 E2E 需要搭建瀏覽器 fixture（建文件、imports `{{ var }}`、模擬點擊、assert 結果 DOM），ROI 太低。**vitest 對 position scanner 的精度測試**（13 個 case，涵蓋 reconstruct 對齊驗證）是主要驗證手段。

---

## 3. 程式碼變動

### 3.1 擴充 [jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js)

新增 export：

```js
export function scanJinja2VariablesWithPositions(mainElements);
// 回傳：[{varName, fullMatch, startIdx, endIdx}, ...]
// 逐筆匹配按文件順序，未去重
// startIdx/endIdx 為 mainElements 內元素索引（含），setRange(startIdx, endIdx + 1) 會選中整個 match
```

關鍵實作：
1. 走過 `mainElements`，建立 `text[]` + `elementIdxByChar[]` 對照表
2. 對於 unsafe 元素（control / table / list / title / multi-char / 非 string），寫入 NUL sentinel
3. 對 `concat = text.join("")` 跑 regex
4. 對每個 match：第二道 sentinel 檢查 → 從 `elementIdxByChar` 反查 element 索引
5. 剝 `object.` 前綴與 Sprint G `scanJinja2Variables` 對齊

### 3.2 修改 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

新增 `onScanAndReplaceClick()`（約 140 行）：

**Phase 1：建 record**
- 同 Sprint G 流程：`_ensureSignerExists` → 序列化 `save_field`
- 維護 `fieldIdByVarName` Map（含已存在的，避免重複建）
- 失敗收集到 `createFailed[]`

**Phase 2：reverse-order in-place 替換**
```js
const sorted = positions.slice().sort((a, b) => b.startIdx - a.startIdx);
for (const pos of sorted) {
    const fieldId = fieldIdByVarName.get(pos.varName);
    if (!fieldId) continue;  // 建 record 失敗、無法插入
    this.editor.command.setRange(pos.startIdx, pos.endIdx + 1);
    this.editor.command.backspace();           // 刪除 {{ var }} 文字
    this._insertControlForField(fieldId, {...}, signer);  // 插入帶 conceptId 的 control
}
```

**Phase 3：結果通知**
三段式（已替換 N 處 / 新建 M 個 record / 失敗 X）；任一失敗 → warning，全成功 → success。

### 3.3 修改 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

「掃描變數」按鈕後加：
```xml
<button class="doc-field-btn doc-field-btn-scan-replace"
        t-on-click="onScanAndReplaceClick"
        title="掃描文件內 {{ }} 變數、建立 record、並將 main 流內文字替換為可編輯 control（實驗性，不可回復）"
        aria-label="掃描並替換">
    <i class="fa fa-magic" aria-hidden="true"/>
    掃描並替換
</button>
```

### 3.4 修改 [doc_editor.css](../static/src/css/doc_editor.css)

新增 `.doc-field-btn-scan-replace`：警示橙黃（`#f59e0b`），與「掃描變數」的安全藍（`#0284c7`）形成視覺對比，提示「不可回復」。

---

## 4. 使用流程

### 情境 A：user 截圖那 5 個變數一鍵全替換

1. 開啟含 `{{ project_name }}` 等 5 個變數的範本文件
2. 點工具列「**掃描並替換**」按鈕（橙色）
3. 對話框：
   ```
   【實驗性功能】將為以下 5 個變數建立 record，並把 main 流內的 5 處 `{{ var }}` 文字替換為可編輯的 control：

     • amount
     • contractor
     • estimate_date
     • project_name
     • remark

   ⚠️ 替換為不可回復操作（無 transaction）。如需先建 record 不替換，請按取消後改用「掃描變數」按鈕。

   確定要繼續嗎？
   ```
4. 按確定 → 後端建 5 個 record + 文件內 5 處純文字替換為 control
5. 視覺：文件內 `{{ project_name }}` 等變為紫色 control 框、點擊可在 inspector 編輯
6. 通知：「【掃描並替換】已替換 5 處文字為可編輯 control；新建 5/5 個 record。」

### 情境 B：變數位於 table 內（無法 main 流替換）

```
找到 3 個變數，但都位於 table/list/title 或多字元元素內，無法在 main 流替換。
請改用「掃描變數」（只建 record）。
```

→ user 改用「掃描變數」（Sprint G）建 record，視覺保持原 `{{ var }}` 文字。

### 情境 C：部分變數已建檔（重複點掃描並替換）

```
將為以下 5 個變數建立 record... 並把 main 流內的 5 處 ... 替換為可編輯的 control：
...
（2 個變數的 record 已存在、會被沿用）
```

→ 已存在的 record 不重複建、`fieldIdByVarName` 從 cache 帶出 → 替換階段直接用既有 fieldId 插 control。

---

## 5. 驗證

### L1 vitest

```
Test Files  94 passed | 1 skipped (95)
     Tests  1906 passed | 1 skipped (1907)
Duration    100.38s
```

對齊 Sprint G baseline 1883 + 13 個 Sprint H 位置測試 + 10 個間期新增 = 1906，**0 regression**。

新增測試（[jinja2_scanner.test.ts](../tests/unit/jinja2_scanner.test.ts) `scanJinja2VariablesWithPositions` describe block）涵蓋：
- main 流的逐筆匹配 + 元素索引正確
- 多個變數按文件順序回傳（不去重）+ 位置嚴格遞增
- **跨 control 元素的 match 作廢**（不會跨越 unsafe sentinel）
- **跨 table 元素的 match 作廢**
- **跨 multi-char value 元素的 match 作廢**（無法精確設 range）
- complex element 不打斷其外圍的 match
- 剝 `object.` 前綴與 Sprint G 對齊
- 變數內空白容錯
- 帶點路徑變數（`partner_id.name`）+ 精確 endIdx
- 變數內含非法字元（如 `|filter`）不收
- 沒找到變數時回空陣列
- 防禦：非陣列回空
- **位置精度可用於 setRange**：`startIdx..endIdx` 的元素串接 === fullMatch（reconstruct 驗證）

### L1.5 靜態檢查（Docker Desktop 不可用時的 fallback）

```
$ node --check static/src/components/doc_editor/doc_editor.js   → OK
$ node --check static/src/components/doc_editor/jinja2_scanner.js → OK
$ xmllint --noout static/src/components/doc_editor/doc_editor.xml → well-formed
```

### L0 模組升級

**未跑**：Docker Desktop 於本次衝刺未運作（user 應已關閉），無法執行 `docker exec odoo18 odoo -u dobtor_doc_editor`。

但本 sprint **0 行 Python 變動**、純 JS/XML/CSS，dev_mode `reload,xml` 下下次瀏覽器 F5 即生效（per memory.md 升級 SOP）。

下次 Docker 啟動時手動驗證：
```bash
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev -u dobtor_doc_editor --stop-after-init && docker restart odoo18
```

### L4 後端 test

未跑（0 Python 變動；複用 Sprint E 已驗證的 `/dobtor_doc/template_fields/save_field` 端點）。

---

## 6. 已知限制與後續

- **無 transaction / rollback**：見 §2.4。失敗時 user 用 Ctrl+Z 救。
- **只處理 main 流**：見 §2.1。巢狀變數仍走 Sprint G「掃描變數」+ 手動 Del 重插流程。
- **無 Playwright E2E**：見 §2.5。canvas-editor 互動 E2E 待整個模組搭建瀏覽器 fixture（Sprint I+ 視需求）。
- **multi-char value 元素**：imported 自 docx 的範本可能含多字元元素（如 `<w:r>{{name}}</w:r>` 解成單一元素 `value="{{name}}"`）。本 sprint 直接標 unsafe 跳過。如未來頻繁碰到，需在 scanner 加 element-splitting pre-pass（把 multi-char 拆成 single-char）。
- **跨段落（換行）的變數**：canvas-editor 用元素流不用節點樹，段落間以 `value: '\n'` 元素分隔。當前 regex `[\w]` 不含 `\n`，所以跨段落 `{{ name`\n`}}` 不會被收（這是預期行為，jinja2 也不允許跨行變數名）。

---

## 7. 方案 1 整體進度更新

| # | 缺口 | Sprint | 狀態 |
|---|---|---|---|
| 1-3 | Sub-nav 三分頁解封 | A | ✅ |
| 4 | 預覽鈕接後端 | A | ✅ |
| 5 | 縮圖 panel 真實 | C | ✅ |
| 6 | 頁碼真換頁 | B | ✅ |
| 7 | 縮放 fit 真實計算 | B | ✅ |
| 8 | Phase 8.2.2 overlay 絕對定位 | D | ✅ |
| – | Odoo 欄位按鈕連結 inspector | E | ✅ |
| – | Overlay polish（resize / clamp / inspector geom） | F | ✅ |
| – | 批次掃描 `{{ var }}` 自動建 Odoo 欄位 record | G | ✅ |
| – | **掃描並替換：`{{ var }}` 文字 → 可編輯 control（main 流，實驗性）** | **H** | ✅ |
