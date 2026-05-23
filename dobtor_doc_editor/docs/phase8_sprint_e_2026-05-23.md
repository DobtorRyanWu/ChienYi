# Phase 8 Sprint E — Odoo 欄位按鈕改建可編輯 Control（2026-05-23）

**性質**：user-directed 衝刺（看截圖回饋後即時加碼）。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js) `onOdooFieldClick` 重寫 — 從「插入純 jinja2 文字」改為「建立 `doc.template.field` 紀錄 + 插入帶 conceptId 的 inline control」。

---

## 1. 背景：截圖揭示的功能空白

user 提供兩張截圖：

- **截圖 1**：當前範本含 5 個 `{{ project_name }}` / `{{ contractor }}` / `{{ estimate_date }}` 等 jinja2 變數（紅圈），箭頭指向「文字」工具列按鈕。
- **截圖 2**：對標 dobtor 線上版本 — Odoo 欄位呈現為**可編輯的浮動框**，右側 inspector 顯示「填寫者 / 必填 / 佔位符 / 字型大小 / ODOO 欄位」。

user 提問：「如何將紅圈 jinja2 變數**與工具列欄位連結**，做出截圖 2 那種可在 inspector 編輯的效果？」

---

## 2. 現況審計（Sprint E 開工前）

| 元件 | 狀態 |
|---|---|
| `doc.template.field.field_type` Selection | ✅ 已含 `('odoo_field', 'Odoo 欄位')` |
| `doc.template.field.odoo_field_name` Char | ✅ 已存在 |
| `/dobtor_doc/template_fields/save_field` controller | ✅ `ALLOWED` 已含 `odoo_field_name` |
| Inspector XML 「Odoo 欄位名稱」輸入框 | ✅ 已寫在 `t-if="selectedField.field_type === 'odoo_field'"` 區塊 |
| `DocFieldPickerDialog` | ✅ 完整可選 model + tree 展開 + 搜尋 |
| **`onOdooFieldClick` handler** | ❌ **舊邏輯**：只用 `executeInsertElementList` 插入 `{{ object.partner_id.name }}` 純文字、不建立 field 紀錄、不可編輯 |

結論：**後端 + UI + Dialog 都已就位，差 handler 沒接通。** 約 1 小時改完。

---

## 3. 程式碼變動

只動 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js) 兩處：

### 3.1 `onOdooFieldClick` 重寫（核心）

新流程：

```js
async onOdooFieldClick() {
    // 前置檢查（同 onFieldButtonClick）：editor / docId / hasTemplate
    this.dialog.add(DocFieldPickerDialog, {
        modelName: this._loadedModelName,
        docId: this.state.docId,
        onInsert: async (expression, label) => {
            // label = "partner_id.name"（從 dialog 直接取）
            const odooFieldName = label || expression.replace(/[{}]/g, "").replace(/^\s*object\.\s*/, "").trim();
            const signer = await this._ensureSignerExists(this.state.activeSignerId);
            const fieldPayload = {
                signer_id: signer.id,
                field_type: "odoo_field",
                page_no: this.state.pageNo || 1,
                placeholder_text: `{{ ${odooFieldName} }}`,
                font_size: 12,
                odoo_field_name: odooFieldName,
            };
            const saveResult = await rpc("/dobtor_doc/template_fields/save_field", { doc_id, field: fieldPayload });
            this._insertControlForField(saveResult.id, {
                key: "odoo_field",
                label: `Odoo: ${odooFieldName}`,
                ctrlType: "text",
                odooFieldName: odooFieldName,
            }, signer);
            // cache push + signer counts + selectedFieldId
        },
    });
}
```

差異重點：
- **建 field 紀錄**：呼叫 `save_field` 端點寫入 `doc.template.field` with `field_type='odoo_field'` + `odoo_field_name='partner_id.name'`
- **插帶 conceptId 的 inline control**：`executeInsertControl` 而非 `executeInsertElementList`，control 可被 inspector 反查
- **selectedFieldId 設定**：插入後右側 inspector 立刻顯示該欄位、user 可改填寫者/必填/字型/odoo_field_name
- **placeholder 用 `{{ partner_id.name }}` 風格**：與既有 jinja2 變數視覺一致、user 一眼看出是動態變數

### 3.2 `_insertControlForField` 加 odoo_field placeholder 分支

```js
let placeholder = `[${signer.name}/${field.label}]`;
if (field.key === "odoo_field" && field.odooFieldName) {
    placeholder = `{{ ${field.odooFieldName} }}`;
}
```

舊版固定 `[簽約人/標籤]`，對 Odoo 欄位改用 jinja2 風格的 `{{ x.y.z }}` placeholder。

---

## 4. 使用流程（user-facing）

### 情境 A：取代既有 `{{ project_name }}` jinja2 變數

1. 選取現有 `{{ project_name }}` 文字 → Del 刪除
2. 點工具列「Odoo 欄位」按鈕 → 對話框開啟（已列出當前 model 的所有欄位）
3. 搜尋或樹狀展開 → 選「name」（或對應的 Odoo 欄位）
4. 自動插入 control，placeholder 顯示為 `{{ name }}`
5. 右側 inspector 自動切到該欄位：
   - 填寫者：可從 dropdown 改
   - 必填：勾選框
   - 佔位符：可改
   - 字型大小：可改
   - **Odoo 欄位名稱**：可改成 `partner_id.name` / `project_id.code` 等任意 model 欄位路徑

### 情境 B：新建 Odoo 欄位（不取代既有變數）

1. 點要插入位置 → 工具列「Odoo 欄位」 → 選欄位 → 完成

### 情境 C：批次轉換既有 `{{ }}` 變數（**未實作、未來功能**）

目前要手動逐個刪掉舊 `{{ project_name }}` 文字再插 Odoo 欄位 control。
未來可加「掃描全文 → 批次轉換為 Odoo 欄位 control」工具按鈕。

---

## 5. 驗證

### L1 vitest

```
Test Files  93 passed | 1 skipped (94)
     Tests  1737 passed | 1 skipped (1738)
Duration    123.38s
```

對齊 autopilot Sprint 188 baseline 1737 — **0 regression**。

### L0 模組升級

```
Registry loaded in 25.677s
```

0 dobtor 相關 ERROR。docker restart odoo18 完成。

### L4 後端 test

未跑（Sprint E 0 行 Python 變動；save_field 端點與 ALLOWED 邏輯均無動）。Sprint A 已驗證後端 92 test 全綠未受影響。

---

## 6. 已知限制與後續

- **舊文件內既有 `{{ var }}` 文字無法自動轉**：須手動 Del 後重插。批次轉換工具留未來 sprint。
- **placeholder 與真實渲染分離**：control placeholder 顯示為 `{{ partner_id.name }}` 但**這不是真 jinja2 變數** — 必須走 `fill_template` 或 `template_preview` 端點（Sprint A 的渲染端點）才會代入真值；canvas-editor 上看到的是固定 placeholder。
- **inspector 「Odoo 欄位名稱」改完即時持久化**：依賴既有 `onInspectorFieldChange` → `save_field` 路徑（Phase 2.1 已完成）。Sprint E 沒改這條鏈、靠它運作。
- **Phase 8.2.2 overlay（缺口 8）仍未動工**：截圖 2 dobtor 線上的「絕對定位浮動框」需 overlay；Sprint E 走的是 inline control 路線。

---

## 7. 方案 1 整體進度更新

| # | 缺口 | Sprint | 狀態 |
|---|---|---|---|
| 1-3 | Sub-nav 三分頁解封 | A | ✅ |
| 4 | 預覽鈕接後端 | A | ✅ |
| 5 | 縮圖 panel 真實 | C | ✅ |
| 6 | 頁碼真換頁 | B | ✅ |
| 7 | 縮放 fit 真實計算 | B | ✅ |
| – | **Odoo 欄位按鈕連結 inspector**（user 截圖揭示） | **E** | ✅ |
| 8 | Phase 8.2.2 overlay 絕對定位 | D | ⏸ 下次 session |
