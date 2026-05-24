# Phase 8 Sprint X — table cell `{{ var }}` 替換解鎖（J.1 unskip）+ Sprint W safe-guard 補洞（2026-05-25）

**性質**：Sprint W 主流路徑完成後解 J.1 最後一個 skip；途中順手抓出 Sprint W safe-guard loop 的 table-blind 漏洞。
**範圍**：[jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js)、[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)、[jinja2_scanner.test.ts](../tests/unit/jinja2_scanner.test.ts)、[admin-dobtor-doc-editor-sprint-ghn.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-ghn.spec.ts)、新建 [probe-sprint-x-table.spec.ts](../../../tests/playwright/tests/probe-sprint-x-table.spec.ts)。

---

## 1. probe 發現：table cell 內 `setRange + executeBackspace + executeInsertControl` 第二次 insert 後 stuck range

Sprint W 對 main 流的成功路徑（setRange + executeBackspace + executeInsertControl）搬到 table cell 跑出：

```
ok    __CYXMARKER__td_d__ td=1,1
FAIL  __CYXMARKER__td_c__ phase=backspace:
      Cannot read properties of undefined (reading 'controlId')
FAIL  __CYXMARKER__td_b__ phase=backspace: ...
FAIL  __CYXMARKER__td_a__ phase=backspace: ...
```

第一個 cell 成功、後面三個都炸。試了：
- 中間 `executeSetRange(0, 0)` reset → 不行（後續仍 fail at backspace）
- 跳過 backspace、只 setRange + insertControl → 不行（fail at insertControl 同樣 controlId undefined）

結論：canvas-editor 在 table cell 第一次 insertControl 後內部 range tracking 進入 stuck state、後續 setRange 即使設到不同 td 也帶著舊 control 的 controlId 引用、backspace/insertControl 都炸。沒找到 reset state 的官方 API。

---

## 2. 突破：直接 mutate td.value 陣列 + executeSetValue

不走 canvas-editor 的指令式 API，改直接修改 IElement 樹然後 setValue：

```js
// 對每 table cell 的 value 陣列做：
// "頭__CYSWM__td_a__尾" → [
//   {value: "頭", size: 20, ...},
//   {type: "control", value: null, control: {type: "text", conceptId: fieldId, ...}},
//   {value: "尾", size: 20, ...},
// ]
// 完整 main 處理完、深拷一份純 POJO、cmd.executeSetValue(newData)
```

probe-sprint-x-table 第二版實作後：**4/4 OK**、`getControlList` 立刻看到 4 個 control。

### 為什麼這條路安全（破除 Sprint T 的 setValue 恐懼）

Sprint T 撞到的 auto-merge 問題：把 `[{X},{Y},{Z}]` 連續同樣式 single-char text element 餵 setValue → 出來 `[{XYZ}]`。

但 control element（`type:'control'`）**結構不同於 text**、不會與相鄰 text 合併。Probe 證明：
- input：`[{value:"頭"}, {type:'control',control:{...}}, {value:"尾"}]`
- output（setValue 後 getValue）：完全一樣的三 element、control 保持獨立

所以 setValue 對「text + control 交錯」路徑安全；只對「連續同樣式 text」做 auto-merge。

---

## 3. 新 scanner helper：`rewriteTdValueWithControls`

純函式、處理單一 td.value 陣列：

```
input:  tdValue: IElement[]
        markerToField: Map<markerText, {fieldId, varName}>
        buildControlElement: (varName, fieldId) → controlElement
output: { newValue: IElement[], replaced: number }
```

實作：對每個 text element 找最早的 marker、切前段 text、插 control、剩下 text 進入下一輪。非 text element 原樣保留。沒 marker 的 element 也原樣返。

vitest 7 個新測蓋：marker 在 element 開頭 / 中間、同 element 多 marker、control element 跳過、空 input / 空 map / 樣式屬性保留。

---

## 4. handler Stage 2b：搭主流 Stage 2a 之後跑

`_sprintWScanAndReplace` 流程現在：

```
Stage 1：search/replace `{{ var }}` → unique marker（在 main + table cells 都會被 search 找到）
Stage 2a：main 流 marker → setRange + executeBackspace + executeInsertControl（Sprint W）
Stage 2b：table cell marker → 直接 mutate td.value + executeSetValue（Sprint X 新加）
Stage 3：snapshot for rollback
```

關鍵實作細節：
- Stage 2b 用 `cmd.getValue()` 拿 **Stage 2a 完成後**的最新 data 為基礎、不能 reuse `preReplaceSnapshot`（那是掃描前狀態、會丟掉 Stage 2a 已插的 control）
- mutate 時用 `JSON.parse(JSON.stringify(...))` 深拷 → 避免 OWL state Proxy + canvas-editor 內部 `structuredClone` DataCloneError（Sprint W 教訓）
- Stage 2a 跟 Stage 2b 兩者都成功的 case：main 控件 + table 控件並存，replaced 累加

---

## 5. 順手抓的 Sprint W safe-guard bug

J.1 第一輪跑完 `0 control`（records 4 個建出來、但 0 控件）。debug：

Sprint W Stage 1 的 safe-guard loop：

```js
for (let i = 0; i < REPLACE_SAFE_GUARD; i++) {
    const curMain = cmd.getValue().data.main || [];
    let flat = "";
    for (const el of curMain) {
        if (el && typeof el.value === "string") flat += el.value;   // ← bug
    }
    if (flat.indexOf(searchText) < 0) break;
    cmd.executeSearch(searchText);
    cmd.executeReplace(marker);
}
```

`flat` 只 concat 了 **top-level** main IElement 的 `.value` 字串。但 table 元素的 `.value` 是 undefined（它有 `.trList`），cells 內的文字根本沒進 flat。

J.1 整個 doc 結構：`main = [{value:"標頭：純文字"}, {type:"table", trList:[...]}]`。Top-level flat = `"標頭：純文字"` — 不含 `{{ td_a }}` 等。Loop 第一輪 `indexOf("{{ td_a }}") === -1` 直接 break、`executeReplace` 從未呼叫 → table cells 內的 `{{ var }}` 完全沒換成 marker → Stage 2b 用 `rewriteTdValueWithControls` 找 marker 找不到 → 0 control。

**修法**：改用既有 `flattenElementsToText` 純函式（會遞迴 table.trList.tdList.value）：

```js
const flat = flattenElementsToText(curMain);
if (flat.indexOf(searchText) < 0) break;
```

`flattenElementsToText` 是 Sprint G 寫的、`scanJinja2Variables` 內部用、vitest 涵蓋齊。

教訓：Sprint W safe-guard 的「還有沒有 search target」檢查邏輯與「scan 哪些 buckets 算 var」應該共用同一個 flatten path。原本因為 Sprint W 只測試 HN.1（純 main 流）所以沒撞，到 Sprint X J.1 才出現。

---

## 6. 驗證

### Playwright E2E（全 3 test pass）

```
Phase 8 Sprint R — Sprint G/H/M/N E2E smoke
  ✓ G.1 — 掃描變數：建 3 個 odoo_field record + inspector 列表顯示 + 全部標孤兒 (14.1s)
  ✓ HN.1 — 掃描並替換 + 復原：round-trip 還原文件 + 刪 record (19.2s)
  ✓ J.1 — 掃描並替換：table cell 內 {{ var }} 也應替換 (15.1s)
3 passed (58.2s)
```

J.1 一次跑通：4 個 record + 4 個 control（皆 in table cell）。

### vitest baseline（79/79，+7 from Sprint W 72）

```
✓ tests/unit/jinja2_scanner.test.ts (76 tests)
  ↳ scanJinja2Variables / WithPositions / InTables / normalize / analyzeScanResults /
    computeOrphanRecordIds / findMarkerPositionsInMain (Sprint W) /
    rewriteTdValueWithControls × 7 ← Sprint X 新增
✓ tests/unit/manifest_assets_hygiene.test.ts (3 tests)
```

---

## 7. 進度更新

| Sprint | 狀態 |
|---|---|
| G-W | ✅ |
| **X — table cell 替換解鎖 + Sprint W safe-guard 補洞** | ✅ |

**Phase 8 截至 Sprint X**：HTML-imported `{{ var }}` 文件對 main 流 + table cell 都能完整跑 G.1 / HN.1 / J.1。後續 sprint 可挑：
- header / footer / list / title 內變數（次要、user 痛點未驗證）
- `_insertControlForField`（Sprint E 既有 helper）的 IElement-with-control wrapping 對齊（風險中：影響歷史文件）
- 文件統整：合 21 個 sprint doc 為 PHASE_8_PLAYBOOK.md

---

## 8. 教訓記錄

1. **canvas-editor 對 table cell 的 control insertion 有 stuck-range bug**：第二次以後 setRange + insertControl 會炸 `controlId undefined`。沒找到 reset state 的官方 API；改走直接 IElement mutate + setValue 路徑解決。
2. **setValue 對混合 text+control 的 IElement 路徑安全**：Sprint T 撞的 auto-merge 限於連續同樣式 text；control element 不會被合併。直接 mutate + setValue 是有效的 fallback。
3. **flatten helper 要共用**：Stage 1 safe-guard loop 的 "還有沒有 target" check 必須跟「scan 哪些 buckets」共用同一個 recursive flatten 路徑、不能各寫一份偷工的 top-level loop。
