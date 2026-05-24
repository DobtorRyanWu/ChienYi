# Phase 8 Sprint W — HTML-imported `{{ var }}` in-place 替換解鎖 + Rollback Proxy 修補（2026-05-25）

**性質**：Sprint V probe 突破後的 handler 實作收割；HN.1 從 skip 恢復為 active 並 pass；途中順手發現 + 修兩個既有 bug。
**範圍**：[jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js)、[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)、[jinja2_scanner.test.ts](../tests/unit/jinja2_scanner.test.ts)、[admin-dobtor-doc-editor-sprint-ghn.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-ghn.spec.ts)。

---

## 1. 兩階段 in-place 替換路徑（接 Sprint V probe）

Sprint V 確認三件事：
- `executeSearch + executeReplace(text)` 在 multi-char element 內**原地替換不切割 element**（Probe A/B/C）
- `setRange + executeBackspace + executeInsertControl` 對 multi-char element 用 char-offset 範圍仍正確 backspace + 插入（Probe-search-control-insertion）
- `executeInsertControl` 需要 IElement-with-control 包裝結構（`{type:'control', control:{...}}`），不能直接傳 IControlBasic

Sprint W 把這三條組成 handler 路徑：

```
[ HTML-imported main：multi-char IElement[] ]
            │
            │ Stage 0: scanJinja2Variables({main: data.main}) → unique varNames
            ↓
[ 對每 varName 創/沿用 doc.template.field record（fieldId 反查 Map）]
            │
            │ Stage 1（每 var 一個 unique marker）:
            │   while flat string 還有 `{{ varName }}`：
            │     cmd.executeSearch('{{ varName }}')
            │     cmd.executeReplace('__CYSWM__<varName>__')
            ↓
[ main 字串內所有 `{{ var }}` → ASCII marker；element 結構未變 ]
            │
            │ Stage 2（findMarkerPositionsInMain + reverse-order setRange）:
            │   for each marker (sorted by startIdx desc):
            │     cmd.executeSetRange(startIdx, endIdx)
            │     cmd.executeBackspace()
            │     cmd.executeInsertControl({type:'control', control:{type:'text', conceptId:fieldId, ...}})
            ↓
[ main 內 marker → 真實 control element（getControlList 可見）]
            │
            │ Stage 3：存 lastScanReplaceSnapshot 給 Sprint N rollback 用
            ↓
[ user 可按右上「復原」按鈕回到掃描前狀態 ]
```

**dispatch 點**：`onScanAndReplaceClick` 在 `mainPositions.length + tablePositions.length === 0 && scannedAll.length > 0`（HTML-imported 情境）時呼叫 `_sprintWScanAndReplace(scannedAll)`。Sprint H 原路徑（typed content per-char element）不動。

---

## 2. 新 scanner helper：`findMarkerPositionsInMain`

純函式、放在 `jinja2_scanner.js` 末。差別於 Sprint H 的 `scanJinja2VariablesWithPositions`：

| | Sprint H scanJinja2VariablesWithPositions | Sprint W findMarkerPositionsInMain |
|---|---|---|
| 要求每 char 獨立 IElement | 要 | 不要 |
| 回傳 idx 意義 | IElement 索引 | flat char-offset |
| 對 multi-char element | 視為 unsafe sentinel、整段略過 | 完整參與 flat string，內部 char-offset 可被找到 |
| 複合 element（control/table/list）| sentinel | 占 1 char NUL placeholder（與 canvas-editor cursor step 對齊）|

vitest 7 個新測涵蓋：單 multi-char element、跨 element 邊界、多 marker、同 marker 多次、control 元素占位、空 input、marker 不存在。

---

## 3. 順手抓到的兩個既有 bug

### 3.1 Sprint T 留下的 import 順序問題（編譯成功，runtime 死）

Sprint W handler 第一次 commit 時 console.log 寫在 `const markerByVar` **之前**：

```js
console.log("[Sprint W] start stage 1: ...", markerByVar);   // ← ReferenceError TDZ
const markerByVar = new Map();
```

`node --check` pass、bundle parse pass，**runtime hit TDZ 才炸**。Stage 1 整段沒跑、handler 半途死。HN.1 在 `record 創建 3 個` 通過但 `控制 3 個` fail = 0。

**修法**：把 log 搬到宣告之後。教訓：以後 console.log 加在 hot path 開頭，**先確認所有 const 都已宣告**；TDZ 在 prod build 完全靜默。

### 3.2 OWL state 把 snapshot 包成 Proxy、`structuredClone` 不接受 → rollback 死

```
[Rollback] click handler fired
[Rollback] snap exists, ids= Proxy(Array)
[Rollback] confirm result: true
[Rollback] executeSetValue threw:
  Failed to execute 'structuredClone' on 'Window':
  #<Object> could not be cloned. DataCloneError
```

`this.state.lastScanReplaceSnapshot` 在 OWL `useState` 包裝下，所有讀取都是 Proxy。canvas-editor 的 `executeSetValue` 內部會 `structuredClone()`，DataCloneError 直接 throw、catch 不顯示 toast（被 Sprint N 既有 catch 吞並 notification 沒被 E2E 抓）。

**修法**：rollback handler 在傳 `snap.docData` 給 `executeSetValue` 前先 `JSON.parse(JSON.stringify(...))` 深拷：

```js
let plainDocData;
try {
    plainDocData = JSON.parse(JSON.stringify(snap.docData));
} catch (e) {
    /* 通知 + return */
}
this.editor.command.executeSetValue(plainDocData);
```

教訓：所有「跨界 API」（canvas-editor / 後端 RPC / 第三方 library）的 input 都應該假設要純 POJO，不要直接餵 OWL state。

### 3.3 `_insertControlForField` 一直在創 type:"text" 不是 type:"control"（既有設計缺陷、Sprint W 不直接修）

probe 發現 `executeInsertControl({type:'text', conceptId, placeholder})` 創出來的 element 是 `{type:'text', value:null, conceptId:X}`、**不是真實 control**、`getControlList` 看不到。

正確結構是 IElement-with-control wrapper：

```js
{
    type: 'control',
    value: null,
    control: {
        type: 'text',         // ControlType
        value: null,
        placeholder: '...',
        conceptId: 'fieldId',
        deletable: true, disabled: false,
    },
}
```

**Sprint W 處理範圍**：handler 內 inline 用正確結構（不過既有 `_insertControlForField`）。Sprint E 既有 onOdooFieldClick 暫不動 — 怕影響 user 手動點按鈕生產的歷史文件，留 Sprint X 對齊。

留個 [`docs/sprint_w_known_issue_existing_control_insert.md`] TODO（本 sprint 不寫，免分散焦點）。

---

## 4. E2E：HN.1 從 skip 恢復

```
Phase 8 Sprint R — Sprint G/H/M/N E2E smoke
  ✓ G.1 — 掃描變數：建 3 個 odoo_field record + inspector 列表顯示 + 全部標孤兒 (23.4s)
  ✓ HN.1 — 掃描並替換 + 復原：round-trip 還原文件 + 刪 record (18.6s)
  - J.1 — 掃描並替換：table cell 內 {{ var }} 也應替換 (skip Sprint W；留 Sprint X)
```

HN.1 完整路徑：建 3 record → 替 3 個 control（getControlList 見） → 復原按鈕出現 → 點 → setValue 還原 + delete 3 record → control 0 + record 0 + 復原按鈕隱藏。

---

## 5. 留下給 Sprint X 的工作

| 項目 | 難度 |
|---|---|
| J.1 — table cell 內 `{{ var }}` 替換 | 中：要研究 setRange 對 td 的多參簽名，char-offset 是 td-internal 還是全域？|
| Sprint E `_insertControlForField` 結構對齊（type:control 包裝） | 中：要驗證歷史文件 backwards-compatibility、不能讓 user 手動建的舊「假 control」丟失 |
| header / footer / list / title 內變數 | 低-中：scanner 函式擴充、setRange 簽名要 spec 看一下 |

---

## 6. 驗證

### vitest baseline

```
✓ tests/unit/jinja2_scanner.test.ts (69 tests)
  ↳ scanJinja2Variables (12), scanJinja2VariablesWithPositions (10), …,
    findMarkerPositionsInMain × 7 ← 本 sprint 新增
✓ tests/unit/manifest_assets_hygiene.test.ts (3 tests)
Test Files 2 passed | Tests 72 passed
```

### Playwright E2E

| Test | Status |
|---|---|
| G.1 | ✓ (23.4s) |
| HN.1 | ✓ (18.6s)（從 Sprint T skip 解鎖）|
| J.1 | skip per Sprint W 留 Sprint X |
| Probe sprint W internal | ✓ desktop |
| Probe search/control insertion | ✓ desktop |

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-V | ✅ |
| **W — HTML-imported in-place 替換 + rollback Proxy 修 + 新 marker scanner** | ✅ |

預期 Sprint X：J.1 table cell 路徑 + 對齊 `_insertControlForField` 結構 + scanner 擴 header/footer/list/title。
