# Phase 8 Sprint T — HTML-imported 多字元元素衝突發現 + 限制文件化（2026-05-24）

**性質**：嘗試修補 → 發現 canvas-editor 架構性衝突 → 誠實 revert + 文件化限制。
**範圍**：scanner 新增 2 個 normalize helper（保留供未來重啟）；handler 內 normalize-and-rescan 路徑 revert；E2E HN.1/J.1 skip + 加註解。

---

## 1. 問題：「你自己驗證」E2E 跑出的真相

跑 Sprint R/S E2E：

| Test | 結果 | 細節 |
|---|---|---|
| G.1 — 掃描變數建 record | ✅ PASS | scanJinja2Variables 用 flattenElementsToText、容 multi-char element、後端 3 record OK |
| HN.1 — 掃描並替換 + 復原 | ❌ FAIL | 後端 0 record（expected 3）|
| J.1 — 掃描並替換 table cell | ❌ FAIL | 後端 0 record（expected 4）|

probe 一路追下去發現：

```
canvas-editor data.main = [
  { value: "專案：{{ project_name }}",  valueLen: 21 },  ← multi-char！
  { value: "\n",                          valueLen: 1 },
  { value: "承包商：{{ contractor }}",   valueLen: 20 },  ← multi-char！
]
```

HTML import 把整個 `<p>text</p>` 塞成**單一 IElement**。Sprint H 的 `scanJinja2VariablesWithPositions` 對 multi-char element 視為 unsafe sentinel（沒辦法精確 setRange 對齊字元邊界），結果整段 `{{ var }}` 都被略過 → handler 早退 → 0 record。

---

## 2. 嘗試的修補（normalize → setValue → re-scan）

新增 scanner 純函式：

```js
export function normalizeMultiCharElements(elements);
// 把 value 多字元元素拆成單字元 element 陣列、保留其他屬性

export function normalizeMultiCharElementsInTables(mainElements);
// 對 table.tr[].td[].value 也跑同樣 normalize、table 結構保留
```

11 個 vitest 涵蓋（拆分正確性、屬性保留、巢狀遞迴、防禦邊界）。

Handler 加入「偵測 + 修補」path：

```js
if (scannedAll.length > 0 && mainPositions.length === 0 && tablePositions.length === 0) {
    // normalize → executeSetValue(normalizedData) → 等 300ms → re-scan
    const normalizedMain = normalizeMultiCharElementsInTables(
        normalizeMultiCharElements(data.main || [])
    );
    this.editor.command.executeSetValue({ ...data, main: normalizedMain });
    await new Promise(r => setTimeout(r, 300));
    data = this.editor.command.getValue().data;
    mainPositions = scanJinja2VariablesWithPositions(data.main || []);
    tablePositions = scanJinja2VariablesInTables(data.main || []);
}
```

---

## 3. 修補失敗：canvas-editor 的 auto-merge

加 debug log 跑 E2E：

```
[DocEditor.Sprint T] normalize-and-rescan triggered
[DocEditor.Sprint T] normalizedMain len=42, first 3=["專","案","："]   ← normalize 正確
[DocEditor.Sprint T] after setValue, getValue.data.main len=3          ← 還是 3 ！？
[DocEditor.Sprint T] after normalize: mainPos=0, tablePos=0
```

42 個 single-char 傳進去、出來還是 3 個 multi-char。

**直接驗證 hypothesis**：probe 直接呼叫

```js
ed.command.executeSetValue({ main: [
    { value: 'X' }, { value: 'Y' }, { value: 'Z' }
] });
ed.command.getValue().data
// → main: [{ valueLen: 3, value: "XYZ" }]
```

→ **canvas-editor 的 setValue 會把連續同樣式的 single-char element 自動合併回 multi-char run**。這是它的內建優化（reduce element count for rendering perf）。

normalize → setValue 路徑根本性不可行。

---

## 4. 探討過的替代方案（都暫不採用）

| 方案 | 評估 |
|---|---|
| 各 char 加唯一 `extension` 防 merge | canvas-editor 仍可能合併（spec 不保證） |
| `insertElementList` 替代 `setValue` | 同樣會觸發 merge |
| 用 `search()` + `replace(text)` 把 `{{ var }}` 改成獨特 marker、再 navigate 替換 control | 可行但複雜、需要 2 階段 + iterate searchNavigateNext |
| 在 backend Python 預處理 content_html | 大重構、跨層、改變 dobtor 整體 architecture |
| 改 scanner：multi-char 內回傳 `{elementIdx, charStart, charEnd}` + handler 自己拆 element | setRange 仍然只能對 element index 操作、setValue 自動 merge 又把拆好的合回去 |

所有方案要嘛複雜、要嘛打不過 canvas-editor 內建行為。Sprint T 不做。

---

## 5. 落地結論（Sprint T 真正交付）

### 5.1 程式碼狀態

| 檔案 | 改動 |
|---|---|
| `jinja2_scanner.js` | 加 `normalizeMultiCharElements` + `normalizeMultiCharElementsInTables` 純函式 + 11 個 vitest test。**保留**供未來找到突破口時複用 |
| `doc_editor.js` | import 兩 helper（註解標未用、保留 reference）；handler 內 normalize-and-rescan 路徑 **revert** 並加 6 行註解說明為何 |
| `tests/playwright/.../sprint-ghn.spec.ts` | HN.1 + J.1 加 `test.skip` + 完整原因註解 |

### 5.2 verification 狀態

| 層級 | 結果 |
|---|---|
| vitest (scanner + manifest hygiene) | **65 passed** (51 G/H/J/Q + 11 Sprint T normalize + 3 hygiene) |
| 模組升級 | `Registry loaded in 10.352s`、0 dobtor 相關 ERROR |
| Playwright E2E | G.1 ✅ pass（user 截圖痛點 Sprint G 路徑驗證）；HN.1 / J.1 skip 待 workaround |

### 5.3 已知限制（要寫進 user-facing 文件）

| 情境 | 結果 |
|---|---|
| 在 canvas-editor 內**手動 type** `{{ var }}` 變數 | Sprint H/J 可正常替換（per-keystroke 是 single-char element）|
| 從 `template.content_html` **HTML import** 的 `{{ var }}` | Sprint H/J 早退 → 0 record；要改用 Sprint G「掃描變數」(只建 record、不替換) |
| 已建 record 後手動 Del `{{ var }}` 純文字、再用 Sprint E「Odoo 欄位」按鈕重插 | 視覺等同 Sprint H/J replace 結果 |

---

## 6. 後續可能突破口（留給未來 Sprint）

- **U+**：用 canvas-editor 的 `search()` + `replace(text)` API 做 2 階段替換（text → unique marker → 再 navigate 換 control）。complexity 中等、值得試
- **V+**：backend pre-process `content_html`：把 `{{ var }}` 轉成 dobtor 內部 control 標記語法（如 `<doc-control name="var"/>`），canvas-editor 載入時就是 control 而非純文字
- **W+**：fork / patch canvas-editor 加 `noMerge` flag 給 setValue
- 都需要更多時間 + 架構討論。Sprint T 先誠實 revert + 文件化

---

## 7. 進度更新

| Sprint | 狀態 |
|---|---|
| G-S | ✅ |
| **T 多字元元素衝突發現 + revert + 文件化** | ✅（含 11 個 vitest 保留 + 限制文件 + E2E skip 註解）|

**Sprint H/J 對 typed content 仍有效；對 HTML imported content 用 Sprint G 即可解 user 截圖痛點。**
