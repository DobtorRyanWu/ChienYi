# Phase 8 Sprint V — Bundle 復活 + E2E URL fallback + canvas-editor search/replace 突破（2026-05-25）

**性質**：找出並修 Sprint T 引入的 bundle parse 致死 bug、加 client action URL fallback 讓 E2E 真的能跑、完成 Sprint T/U 留下的 search/replace 探路。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)、[admin-dobtor-doc-editor-sprint-ghn.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-ghn.spec.ts)、新建 [probe-canvas-search-replace.spec.ts](../../../tests/playwright/tests/probe-canvas-search-replace.spec.ts)。

---

## 1. 真正 root cause：Sprint T 在 import {} 內寫的註解把 web.assets_web bundle 整個炸掉

Sprint U 卡在「editor URL 開不了」。當時的 hypothesis 是 client action context 不接 URL query param。所以本 Sprint 先加 URL fallback（見 §2）—— 加了之後 Playwright 跑 G.1 截圖仍然空白。

進一步排查瀏覽器內 console + 載入的 bundle 內容才發現真相：

```
window.odoo.loader.modules.size === 0
console: "Unexpected token ')'"
loaded only: web.assets_web.min.js (沒有任何 dobtor 模組註冊)
```

但 dobtor 程式碼**有**進 bundle —— curl 撈 bundle.js grep `dobtor_doc_editor` 有 34 處。問題是 bundle 整個 parse fail。

`node --check` 撈下來的 bundle，發現編譯結果裡有：

```js
const{DocFieldPickerDialog}=require("@dobtor_doc_editor/components/doc_field_picker/doc_field_picker");
require({)   ← 這個！
```

對源頭找出來：Sprint T 為了文件化「為何 normalize helper 還在 scanner module 內但 doc_editor.js 沒實際引用」，把註解寫進了 `import { ... }` 的解構賦值內：

```js
// Sprint T 寫成這樣 ↓（看似合理但會炸）
import {
    scanJinja2Variables,
    scanJinja2VariablesWithPositions,
    scanJinja2VariablesInTables,
    analyzeScanResults,
    computeOrphanRecordIds,
    // normalizeMultiCharElements{,InTables} 留在 scanner module 內供未來重啟此方向時使用
    // （目前 Sprint T 因 canvas-editor auto-merge 無法用、見 doc_editor.js
    // onScanAndReplaceClick 內註解與 docs/phase8_sprint_t_2026-05-24.md）
} from "./jinja2_scanner";
```

Odoo asset compiler 把 ES module `import` 轉成 `odoo.define(..., function(require){ const {X} = require("..."); ... })`，**轉換時不會 strip import 解構內的行內註解**，出來變成 `require({)` —— 整個 bundle parse fail，所有 backend SPA 都不啟動。

`node --check doc_editor.js` 在 source 上 pass（ES module 認得這種註解），但 Odoo compiler 不認。Vitest 也不會撞 —— vitest 直接吃源碼。**唯一會炸的是運行時 SPA**，所以 Sprint T 跑 vitest 全綠通過、Sprint U 跑 login E2E 看到 form-fill timeout 以為是 construction_portal 客製 login 問題、實際是 SPA 根本沒啟動。

**修法**：註解搬到 import 區塊**外部**（前面）：

```js
// 注意：normalizeMultiCharElements{,InTables} 留在 scanner module 內供未來重啟此方向時使用
// （目前 Sprint T 因 canvas-editor auto-merge 無法用、見 onScanAndReplaceClick 內註解
//  與 docs/phase8_sprint_t_2026-05-24.md）
// IMPORTANT：不要把以上註解搬回 import {} 內部 — Odoo asset compiler 解析 import 解構
// 賦值時不會 strip 行內註解，會輸出 `require({)` 直接讓整個 web.assets_web bundle parse fail
// （Sprint V 才發現的；症狀 = SPA 完全不啟動、console 只有 "Unexpected token ')'"）。
import {
    scanJinja2Variables,
    scanJinja2VariablesWithPositions,
    scanJinja2VariablesInTables,
    analyzeScanResults,
    computeOrphanRecordIds,
} from "./jinja2_scanner";
```

升級後 bundle hash 從 `8088506` 變 `2ee1234`、`node --check bundle.js` 通過、`grep "dobtor_doc_editor" bundle.js` 還有 34 處。SPA 復活。

### 反思：bundle hash 沒變代表 bug 早就在了

Sprint T commit 後 bundle hash 應該就是 `8088506`、整個 SPA 從那刻開始就掛了。Sprint T/U 全靠 vitest + 用 admin 帳號開瀏覽器手動測（沒進 editor 也看不出來，因為 list view 是 server-side render、不靠 bundle）。**經驗教訓**：以後 doc_editor.js / 其他 backend bundle JS 改完，**必須跑一次 SPA 啟動 smoke test**，不能光靠 vitest 或模組升級沒爆。

---

## 2. URL query string `?doc_id=N` fallback（給 E2E / bookmark / share 用）

`doc_editor.js` `setup()` 原本三層 docId fallback：

1. `this.props.docId` — portal mount mode（`<owl-component>`）
2. `context.doc_id` — backend client action context
3. `sessionStorage` — F5 復原

加第三層 fallback（在 sessionStorage 前）：

```js
let _urlDocId = null;
try {
    const _v = new URLSearchParams(window.location.search).get("doc_id");
    const _n = _v ? parseInt(_v, 10) : 0;
    if (_n > 0) {
        _urlDocId = _n;
    }
} catch (e) {
    // ignore — fall through to next fallback
}
let _storedDocId = null;
const _stored = sessionStorage.getItem(_SESSION_KEY);
if (_stored) {
    _storedDocId = parseInt(_stored, 10);
}
const docId = this.props.docId || context.doc_id || _urlDocId || _storedDocId;
```

效果：`/odoo/action-dobtor_doc_editor.action_doc_editor?doc_id=N` 直接進編輯器、不必繞 list view 點按鈕。

E2E `openEditor()` 改一步打 URL：

```ts
async function openEditor(page: Page, docId: number) {
  await page.goto(`${BASE_URL}/odoo/action-dobtor_doc_editor.action_doc_editor?doc_id=${docId}`);
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('.o_dobtor_doc_editor')).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(4000);
}
```

順便支援 user 可以 bookmark / 分享編輯器連結，**不只 E2E 受益**。

---

## 3. G.1 E2E 真的跑通

```
[admin] Phase 8 Sprint R — Sprint G/H/M/N E2E smoke
  G.1 — 掃描變數：建 3 個 odoo_field record + inspector 列表顯示 + 全部標孤兒
  ✓ 1 passed (26.0s)
```

bootstrap 建 template+doc → openEditor URL → click scan-vars 按鈕 → assert 後端 3 record + inspector 列表 + 孤兒 icon 全綠。

HN.1 / J.1 仍 `test.skip`（Sprint T 文件化的 multi-char auto-merge 阻塞），但本 Sprint 的 search/replace probe（§4）為未來解這個阻塞鋪好路。

---

## 4. canvas-editor search/replace 探路 ✅ 突破

新建 `tests/playwright/tests/probe-canvas-search-replace.spec.ts`，三個 probe 全在 desktop project 通過：

### Probe A — multi-char element 內 search/replace

```
input:  [{ value: "專案：{{ project_name }}", size: 20, ... }]   ← 21-char element
exec:   cmd.executeSearch('{{ project_name }}')
        cmd.executeReplace('REPLACED_A')
output: [{ value: "專案：REPLACED_A", size: 20, ... }]            ← 同一個 element！
```

`executeReplace` **原地改 element value**、不切割 element、不觸發 setValue auto-merge。樣式（size/color/bold）全保留。

### Probe B — 同段內兩個變數依序替換

```
input:  [{ value: "{{ a }} 與 {{ b }} 並列" }]
exec:   search '{{ a }}' / replace 'AAA' → search '{{ b }}' / replace 'BBB'
output: [{ value: "AAA 與 BBB 並列" }]
```

順序執行 OK；index shift 由 canvas-editor 內部處理、外部不需要管。

### Probe C — table cell 內

```
input:  table → tr → td → value: [{ value: "{{ contractor }}" }]
exec:   search '{{ contractor }}' / replace 'REPLACED_C'
output: table → tr → td → value: [{ value: "REPLACED_C" }]   ← table 結構完整保留
```

跨 element/table 邊界都 work。**Sprint T 文件化的「canvas-editor 對 multi-char element 無法 in-place 替換」結論被本探路推翻**：透過 `search` + `replace` API，HTML-imported `{{ var }}` 完全可以原地替換。

### Probe spec 狀態

- 3 probes 在 `desktop` project 全 ✓
- `mobile` project Probe C 偶發 timeout（第三次 navigate 後 editor visible check 失敗）—— probe 性質的 spec，不阻 build。實際機制驗證已成立
- 留在 repo 內供 Sprint W 設計 in-place replace handler 時 reference 用

---

## 5. Sprint W 路徑解鎖

基於 §4 結果，Sprint H/J 對 HTML-imported 內容的 in-place 替換重新可行：

```
[ HTML-imported content ]
        │
        │ scanJinja2Variables (Sprint G 已有)
        ↓
[ 找到 {{ var }} 字串列表 ]
        │
        │ for each var:
        │   1. cmd.executeSearch('{{ var }}')
        │   2. cmd.executeReplace('<<<UNIQUE_MARKER_N>>>')
        ↓
[ 元素值內含 marker 字串，element 數量不變 ]
        │
        │ scan elements 找 marker、計算 element index + char offset
        │ cmd.command.executeSetRange(elementIdx, startChar, elementIdx, endChar)
        │ cmd.command.executeInsertControl({ type: 'text', name: var, ... })
        ↓
[ marker 被 control 取代、{{ var }} → odoo_field control ]
```

Sprint T 試的「normalize → setValue」路徑因 auto-merge 死路；search/replace 路徑因 API 在 element value 層級操作、不重建 element list，繞過了 auto-merge。

Sprint W 預計：實作 handler、開 HN.1 / J.1 兩 spec 的 skip、驗證 HTML-imported content 也能完整 round-trip。

---

## 6. 驗證

### Bundle 啟動

- 升級後 bundle hash `2ee1234`、`node --check bundle.js` ✓、`grep dobtor bundle.js` = 34 處
- 瀏覽器手動開 `/odoo`、SPA 正常啟動、`window.odoo.loader.modules.size > 0`

### vitest 基線（Sprint G-T baseline）

```
✓ tests/unit/jinja2_scanner.test.ts (62 tests) 35ms
✓ tests/unit/manifest_assets_hygiene.test.ts (3 tests) 388ms
 Test Files  2 passed (2)
      Tests  65 passed (65)
```

無退步。（full vitest suite 1962/1966 pass、3 失敗在 `08_render_ops_trace.test.ts` fixture snapshot、與本 sprint 無關 pre-existing）

### Playwright E2E

| Test | Status |
|---|---|
| G.1 — 掃描變數建 record + inspector + 孤兒 | ✓ pass (26s) |
| HN.1 / J.1 | test.skip per Sprint T（待 Sprint W 用本 sprint 的 search/replace 路徑重寫）|
| Probe A (multi-char) [desktop] | ✓ |
| Probe B (兩變數同段) [desktop] | ✓ |
| Probe C (table cell) [desktop] | ✓ |
| Probe C (table cell) [mobile] | flake（第三次 navigate timeout）|

---

## 7. 進度更新

| Sprint | 狀態 |
|---|---|
| G-S | ✅ |
| T 多字元元素衝突文件化 | ✅ |
| U E2E login JSON-RPC 修補 | ✅（但 editor 沒實際開到、留 Sprint V 修）|
| **V bundle 復活 + URL fallback + search/replace 突破** | ✅ |

預期 Sprint W：實作 search/replace-based in-place 替換 handler、解 HN.1 / J.1 skip、HTML-imported `{{ var }}` 也支援 round-trip。

---

## 8. 經驗教訓記錄

1. **`import { ... }` 解構內不可寫行內註解**——Odoo asset compiler 不 strip、會壞 bundle。註解寫外面
2. **bundle hash 不變不代表 bundle OK**——asset 內容若被快取的 hash 已 invalidate，但 hash 算法本身可能對某些變更不敏感。SPA smoke 是唯一可靠驗證
3. **vitest 綠不代表 SPA 會跑**——vitest 吃源碼、SPA 跑 compiled bundle，兩條路。修 backend JS 後**必須**手動或 E2E 跑 SPA
4. **Sprint T 文件化的「canvas-editor in-place 不可行」結論不對**——是 setValue 路徑不可行、search/replace 路徑可行。研究結論要留「目前用 X 路徑不行」的限制範圍、不要寫成「方向不可行」
