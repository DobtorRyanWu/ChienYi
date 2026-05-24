# Phase 8 Sprint J — 掃描並替換擴展至 table cell（2026-05-24）

**性質**：Sprint H 的範圍擴張。
**範圍**：擴充 [jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js) 加 `scanJinja2VariablesInTables`，調整 `onScanAndReplaceClick` 處理 table 位置。

---

## 1. 為什麼擴張

Sprint H §6 列為已知限制：

> **只處理 main 流**：table/list/title 的 setRange 簽名複雜（tableId/trIndex/tdIndex），reverse-replace 易破壞表格結構。巢狀變數仍走 Sprint G「掃描變數」+ 手動 Del 重插

實務上 ChienYi 範本（通報單、估驗單）大量用 table 排列變數欄位，純 main 流覆蓋率不足。Sprint J 把 table cell 納入替換範圍，list/title 仍保留 deferred 狀態（罕用）。

---

## 2. 設計取捨

### 2.1 為什麼 main 與 table 分兩段處理？

```
table 改動 → 不影響 main element index
main 改動 → 不影響 table 內部 td.value index
但 main 改動 → 可能改變 table 元素本身的 index（tableElementIdx 失效）
```

→ 先處理 table（內部）、再處理 main 是**單向安全**的順序。

| 階段 | 排序 | 改變 |
|---|---|---|
| 2a. table cell | `(tableElementIdx, trIdx, tdIdx, startIdx)` 全字典序倒排 | 只影響該 td.value 內部 |
| 2b. main 流 | `startIdx` 倒排 | 影響 main 元素 index（已不會再用到 table 座標）|

### 2.2 為什麼 list / title 仍然不做？

| 結構 | setRange 簽名 | 罕用程度 |
|---|---|---|
| table.td.value | `setRange(s, e, tableId, tdIdx, tdIdx, trIdx, trIdx)` | 常用（90%+ 範本）|
| list.valueList | 無公開 multi-arg、要 patch | 罕（範本不會在 list 內塞變數）|
| title.valueList | 同上 | 罕 |

Sprint J 收 90% 案例、留 10% 罕例不做。

### 2.3 為什麼 table id 必要？

`setRange(s, e, tableId, tdIdx, tdIdx, trIdx, trIdx)` 第三參數是 string。canvas-editor 在 imported table 通常都帶 `id`/`tableId`；若沒有，本實作會把該 match 標 `no_table_id` 失敗、不嘗試替換（**不**用 fallback 強行 setRange，會誤觸 main 範圍）。

---

## 3. 程式碼變動

### 3.1 [jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js)

新增 export：

```js
export function scanJinja2VariablesInTables(mainElements);
// 回傳：[{varName, fullMatch, startIdx, endIdx, tableElementIdx, trIdx, tdIdx, tableId}, ...]
// 對 main[].type === 'table' 元素遞迴，把 Sprint H scanJinja2VariablesWithPositions
// 的 main flow 邏輯套用到每個 td.value 上
```

重點：直接複用 `scanJinja2VariablesWithPositions`，每個 td.value 跑一次、加上 table 座標 metadata。

### 3.2 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

`onScanAndReplaceClick` 變動：

```js
const mainPositions = scanJinja2VariablesWithPositions(data.main || []);
const tablePositions = scanJinja2VariablesInTables(data.main || []);
const positions = [...mainPositions, ...tablePositions];
```

替換階段 split 為 2a (table) + 2b (main)，table 用 7-arg setRange。

確認 dialog 加註：`包含：main 流 N 處、table 內 M 處。`

---

## 4. 驗證

### L1 vitest

```
Test Files  97 passed | 1 skipped (98)
     Tests  1920 passed | 1 skipped (1921)
```

Sprint I baseline 1912 + 7 新 Sprint J 測試 + 1 ambient = 1920，**0 regression**。

新增測試（`scanJinja2VariablesInTables` describe）涵蓋：
- 找到 table cell 內變數含 table/tr/td 座標
- 多列多欄 table 座標正確
- table 無 id → tableId=null（呼叫者要 fallback）
- td.value 內 control 的 match 作廢
- 非 table 元素跳過、不影響其他 table 處理
- 空 / 缺失 trList / tdList 防禦
- 非陣列回空

### L0 模組升級

```
Registry loaded in 19.195s
```

0 dobtor 相關 ERROR。

---

## 5. 已知限制與後續

- **list / title 不做**：見 §2.2，罕用、deferred
- **table 無 id 跳過**：理論上 imported docx table 都有 id；若碰到沒有，標 `no_table_id` 通知 user
- **不處理 nested table（table 內 table）**：scanJinja2VariablesInTables 不遞迴到 td.value 內的 table 元素。實務上 ChienYi 範本不會有 nested table，先不做

---

## 6. 進度更新

| Sprint | 狀態 |
|---|---|
| G 掃描 → 建 record | ✅ |
| H 掃描 → 替換為 control（main 流） | ✅ |
| I manifest hygiene | ✅ |
| **J 掃描 → 替換為 control（main + table）** | ✅ |
| K 重建 controls from cache | 待做 |
| L inspector field list + click-to-locate | 待做 |
