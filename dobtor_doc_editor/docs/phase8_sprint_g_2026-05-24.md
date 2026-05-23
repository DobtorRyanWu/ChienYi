# Phase 8 Sprint G — 批次掃描 `{{ var }}` 自動建 Odoo 欄位 record（2026-05-24）

**性質**：user-directed 衝刺，直接消除 Sprint E 留下的痛點。
**範圍**：新增 [jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js) + [doc_editor.js](../static/src/components/doc_editor/doc_editor.js) `onScanVariablesClick`，工具列加「掃描變數」按鈕。

---

## 1. 痛點：Sprint E 留下的「手動逐個重插」尾巴

Sprint E（[phase8_sprint_e_2026-05-23.md](phase8_sprint_e_2026-05-23.md) §6）已標註：

> **舊文件內既有 `{{ var }}` 文字無法自動轉**：須手動 Del 後重插。批次轉換工具留未來 sprint。

user 截圖中那 5 個紅圈變數（`{{ project_name }}` / `{{ contractor }}` / `{{ estimate_date }}` / 等）就是這類情況——文件本身是從外部範本匯入或從 Sprint 89 舊路徑插入的純文字，inspector 看不到、無法編輯填寫者/必填/字型大小。

**Sprint E 之後的操作流程**（爛）：
1. 選取 `{{ project_name }}` → Del
2. 點工具列「Odoo 欄位」
3. 對話框搜尋 / 樹狀展開 → 選欄位
4. 重複 5 次

**Sprint G 之後**（一鍵）：
1. 點工具列「掃描變數」按鈕
2. 對話框顯示找到的 5 個變數、確認
3. 後端自動批次建 5 個 `doc.template.field` record（field_type='odoo_field'）
4. user 在右側 inspector 編輯詳細屬性

---

## 2. 設計取捨

### 2.1 為什麼 MVP 不做 in-place 文字 → control 替換？

| 選項 | 優點 | 缺點 |
|---|---|---|
| **(A) 只建 record（本 Sprint）** | 簡單、零文件結構風險、user 仍看得到原 `{{ var }}` 文字 | 文件內仍是純文字、inspector 點 control 才能進編輯模式（user 要靠 fill_template 端點看真值） |
| (B) 同時做 in-place 替換 | 視覺最一致（plain text → control） | canvas-editor 的 IElement 位置操作易碎（單字元 chunked、含 table/list 巢狀），替換失敗會破壞文件結構；reverse-order 操作配合 `setRange`+`backspace`+`executeInsertControl` 在 5+ matches 場景中有 race condition |

**決定**：選 (A) MVP。in-place 替換留 Sprint H/I 視 user 回饋決定。**核心是「自動建 record」這件事——5 → 1 次點擊**，足以解決 user 截圖痛點。

### 2.2 為什麼用 regex 不用 AST？

docxtpl / jinja2 變數實務上都是單行 `{{ ident }}` 形式，不會跨行（除非已 broken）。Regex `/\{\{\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*\}\}/g` 對 5-50 個變數的場景過殺、但維護性最好、邊界條件最少。**故意不收** `{{ name|upper }}` 這類帶 filter 的——Sprint E 的 `odoo_field_name` 也不收這種格式。

### 2.3 為什麼 N 次 `save_field` 而非 batch 端點？

5-10 個變數 × 序列化 RPC ≈ 0.3-0.6s，user 可接受。新增後端 batch 端點要動 `template_field_controller.py` + 寫 ALLOWED + 寫測試，ROI 不划算。**未來若需掃 50+ 變數頻繁卡頓**再加 batch。

### 2.4 為什麼用 `window.confirm` 而非自訂 dialog？

| 選項 | 用本 sprint | 理由 |
|---|---|---|
| `window.confirm` | ✅ | portal env 連 dialog service 都可能 try/catch fallback；確認動作只要 yes/no，多預覽行用 `\n` 排版足夠 |
| `DocFieldPickerDialog`-style | ❌ | 過度工程化、UI 複雜度沒換來功能 |

---

## 3. 程式碼變動

### 3.1 新增 [jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js)（純函式 util）

兩個 export：

```js
// 把 IElement[] 攤平成 text（遞迴 table.trList[].tdList[].value、list/title 的 valueList）
export function flattenElementsToText(elements);

// 掃描 editorData 的 main/header/footer，回傳 [{varName, occurrences}]
// 已去重、按 occurrences 降冪 → 字母升冪排序
export function scanJinja2Variables(editorData);
```

關鍵設計細節：
- **跳過 control 元素**：Sprint E 已註冊欄位用 CONTROL 表示、placeholder 雖顯示 `{{ ... }}` 但**不應**再被掃到
- **剝 `object.` 前綴**：`{{ object.partner_id.name }}` 與 `{{ partner_id.name }}` 自動合併計次（與 Sprint E `odoo_field_name` 對齊）
- **同時掃 main / header / footer**：頁首頁尾的變數也批次建檔
- **regex 只允許純識別字**：故意不收 `{{ name|upper }}` 這類帶 filter 的

### 3.2 修改 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

加 import：
```js
import { scanJinja2Variables } from "./jinja2_scanner";
```

加 `onScanVariablesClick()` 方法（約 120 行）：
1. 前置檢查：editor / docId / hasTemplate
2. `getValue().data` → `scanJinja2Variables(data)`
3. 與 `_templateFieldsCache` 的 `odoo_field_name` 對比，**跳過已註冊**
4. `window.confirm` 列出將建檔的變數名（含出現次數）讓 user 確認
5. `_ensureSignerExists` 確保 signer 存在
6. **序列化** 逐個呼叫 `/dobtor_doc/template_fields/save_field`（避免 race）
7. 用最後一次 response 的 `signer_field_counts` 更新 chip
8. 結果通知：全成功 / 全失敗 / 部分成功 三種 toast

### 3.3 修改 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

工具列「Odoo 欄位」按鈕後加：
```xml
<button class="doc-field-btn doc-field-btn-scan"
        t-on-click="onScanVariablesClick"
        title="掃描文件內所有 {{ }} 變數、批次建立 Odoo 欄位 record"
        aria-label="掃描變數">
    <i class="fa fa-magic" aria-hidden="true"/>
    掃描變數
</button>
```

### 3.4 修改 [doc_editor.css](../static/src/css/doc_editor.css)

新增 `.doc-field-btn-scan`：藍色配色（`#0284c7`），視覺次於 Odoo 欄位的紫色（`#714B67`），暗示「自動化輔助」性質。

---

## 4. 使用流程（user-facing）

### 情境：取代既有 5 個 jinja2 變數（user 截圖場景）

1. 開啟含 `{{ project_name }}` / `{{ contractor }}` / `{{ estimate_date }}` / `{{ amount }}` / `{{ remark }}` 的範本文件
2. 點工具列「掃描變數」按鈕
3. 對話框：
   ```
   將為以下 5 個 jinja2 變數建立 Odoo 欄位 record：

     • project_name（1 次）
     • amount（1 次）
     • contractor（1 次）
     • estimate_date（1 次）
     • remark（1 次）

   建立後可在右側 Inspector 編輯填寫者、必填、字型大小等屬性。

   確定要繼續嗎？
   ```
4. 按確定 → 後端建 5 個 `doc.template.field` record
5. 右側 inspector 立刻列出 5 個新欄位、user 逐一 click 編輯
6. **文件內原 `{{ var }}` 純文字仍保留**（讓 user 自行決定是否手動刪除替換為 control）

### 已存在的欄位自動略過

若 user 第二次點「掃描變數」按鈕、且部分變數上次已建檔：
```
找到 5 個變數，但全部已是 Odoo 欄位 record（在 Inspector 中可編輯）。
```
或部分混合：
```
將為以下 2 個 jinja2 變數建立 Odoo 欄位 record：

  • new_var_a（1 次）
  • new_var_b（1 次）

（3 個已是 Odoo 欄位、自動略過）
```

---

## 5. 驗證

### L1 vitest

```
Test Files  94 passed | 1 skipped (95)
     Tests  1883 passed | 1 skipped (1884)
Duration    118.00s
```

對齊 Sprint F baseline 1817 + 期間其他 sprint 新增 = 1866，本 Sprint G 新增 17 個測試（jinja2_scanner.test.ts），**0 regression**。

新增測試涵蓋：
- 主流單一變數
- user 截圖那 5 個變數場景（去重 + 計次）
- 變數內空白容錯（`{{name}}` / `{{ name }}` / `{{  name  }}`）
- 帶點路徑（`partner_id.name`）
- `object.` 前綴剝除（兩個變體合併計次）
- 跳過 control 元素（Sprint E 已註冊欄位不重複偵測）
- 遞迴 table 內 td.value
- 遞迴 list/title 的 valueList
- 同時掃 main / header / footer
- 沒找到變數時回空陣列
- 變數內含非法字元（如 `|filter`）不收
- 防禦：editorData 為 null / undefined / 空物件
- 防禦：main 不是陣列
- flattenElementsToText 純 text 字元串接 / 跳過 control / 非陣列 → 空字串 / table 巢狀遞迴

### L0 模組升級

```
Registry loaded in 27.452s
```

0 dobtor_doc_editor 相關 ERROR。docker restart odoo18 完成、werkzeug + bus.loop 正常運轉。

### L4 後端 test

未跑（Sprint G 0 行 Python 變動；複用 Sprint E 已驗證的 `/dobtor_doc/template_fields/save_field` 端點與 ALLOWED 邏輯）。

---

## 6. 已知限制與後續

- **不做 in-place 文字 → control 替換**：見 §2.1。文件內既有 `{{ project_name }}` 純文字仍保留；user 在 inspector 編輯欄位屬性後、若想視覺上變成 control，仍需手動 Del 原文字、再用「Odoo 欄位」按鈕重插。完整自動替換留 Sprint H+。
- **placeholder 與真實渲染分離**：與 Sprint E 同——control placeholder 顯示為 `{{ partner_id.name }}` 但這不是真 jinja2 變數；必須走 `fill_template` / `template_preview` 端點才會代入真值。
- **批次失敗的部分成功語意**：若 5 個變數中 3 個 save_field 成功、2 個失敗，前端 cache 只 push 成功的 3 個、失敗的會在 toast 顯示變數名供 user retry。整批不會 rollback。
- **不掃 textbox / shape 內變數**：canvas-editor 的 textbox 為獨立 element 結構，當前 scanner 只遞迴 table / list / title。實務上 docxtpl 範本變數放在 textbox 的場景少，先不處理。

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
| – | **批次掃描 `{{ var }}` 自動建 Odoo 欄位 record** | **G** | ✅ |
