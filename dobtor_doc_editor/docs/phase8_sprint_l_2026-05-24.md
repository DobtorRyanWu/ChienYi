# Phase 8 Sprint L — Inspector 欄位列表 + 點 row 跳到 document control（2026-05-24）

**性質**：補位 Sprint G-K 後留下的 navigation 缺口。
**範圍**：[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml) inspector 頂部加欄位列表 + [doc_editor.js](../static/src/components/doc_editor/doc_editor.js) 加 `fieldsList` getter + `onFieldListRowClick` handler + CSS。

---

## 1. 痛點

Sprint G/H/J 把欄位 record 與 document control 雙向同步做好，但「**點 inspector 跳到 document**」這條反向 navigation **沒做**：

- ✅ 點 document control → inspector 顯示該 field（Phase 2.1 `rangeStyleChange` listener）
- ❌ 在 inspector 想跳到 document 內某個 control → **沒入口**

文件超過 5-10 個 control 後、user 要找「我剛建的 project_name control 在文件第幾頁哪裡」就只能拉捲軸目視找。

Sprint L 加 inspector 頂部欄位列表，每個 row 點下去：
1. 設 `selectedFieldId`（讓下方屬性區顯示該 field）
2. 呼叫 canvas-editor `locationControl(conceptId)`，把游標 + 視窗跳到對應 control

---

## 2. 程式碼變動

### 2.1 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

新增兩個方法（在 `selectedFieldLabel` 之前）：

#### `get fieldsList()` getter

```js
get fieldsList() {
    const list = this._templateFieldsCache || [];
    return [...list].sort((a, b) => {
        const pa = a.page_no || 1;
        const pb = b.page_no || 1;
        if (pa !== pb) return pa - pb;
        return (a.id || 0) - (b.id || 0);
    });
}
```

排序穩定：
- 主排序：`page_no` 升冪（跨頁範本對齊瀏覽順序）
- 次排序：`id` 升冪（同頁照建檔順序）

不做 dedup：每個 record 即便 `odoo_field_name` 相同也是獨立欄位（代表文件內多處對應）。

#### `onFieldListRowClick(fieldId)` handler

```js
onFieldListRowClick(fieldId) {
    if (!fieldId) return;
    if (this.state.selectedFieldId !== fieldId) {
        this.state.selectedFieldId = fieldId;
    }
    try {
        this.editor?.command?.locationControl?.(String(fieldId));
    } catch (e) {
        console.debug("[DocEditor] locationControl skipped for field", fieldId, e?.message);
    }
}
```

容錯：`locationControl` 在某些 canvas-editor 版本可能不存在或 throw（如 fieldId 在文件內沒對應 control——record 存在但 control 未插入 / 已被刪），靜默 catch、但 `selectedFieldId` 仍會被設好（inspector 編輯功能不受影響）。

### 2.2 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

inspector panel 最上面（`<aside class="doc-inspector-panel">` 內、`<t t-if="selectedField">` 之前）插入：

```xml
<t t-if="fieldsList.length > 0">
    <div class="doc-inspector-fields-list">
        <div class="doc-inspector-fields-list-header">
            <i class="fa fa-list me-1"/>
            <span>所有欄位 (<t t-esc="fieldsList.length"/>)</span>
        </div>
        <ul class="doc-inspector-fields-list-items" role="listbox">
            <t t-foreach="fieldsList" t-as="fl" t-key="fl.id">
                <li t-attf-class="doc-inspector-fields-list-item #{state.selectedFieldId === fl.id ? 'is-selected' : ''}"
                    role="option"
                    t-on-click="() => this.onFieldListRowClick(fl.id)"
                    t-attf-title="點擊：跳到文件內對應 control 並選取此欄位">
                    <span class="doc-inspector-fields-list-item-name"
                          t-esc="fl.odoo_field_name or fl.placeholder_text or fl.field_type"/>
                    <span class="doc-inspector-fields-list-item-id">#<t t-esc="fl.id"/></span>
                </li>
            </t>
        </ul>
    </div>
</t>
```

顯示優先：`odoo_field_name` →`placeholder_text` → `field_type`（盡量給 user 一眼能識別的標籤）。

### 2.3 [doc_editor.css](../static/src/css/doc_editor.css)

新增 `.doc-inspector-fields-list*` 樣式：
- 容器 `max-height: 240px`（10-15 行可見、超過內滾）
- selected row 用主紫色 `#714B67`（與 inspector header 同色、形成視覺連續性）
- hover 用淺紫 `#f3eaf0`
- field id badge 維持灰底（selected 時改白底紫字）

---

## 3. 使用流程

### 情境 A：剛 Sprint H 建好 5 個欄位、想驗證位置

1. 跑 Sprint H「掃描並替換」→ 建好 5 個 odoo_field record + 替換 5 處文字為 control
2. 右側 inspector 頂部出現「所有欄位 (5)」清單
3. 點 `project_name` row → 文件捲到對應 control + inspector 屬性區顯示該 field 編輯
4. 同樣方式點 `contractor` row → 跳到另一處

### 情境 B：navigation 上想批次調整

1. 開長文件、有 20 個欄位
2. 想批次把某幾個欄位的「填寫者」改成同一個簽約人
3. 點 row → 改填寫者 dropdown → 點下一個 row → 改 → ...
4. （比目視找 control 快得多）

### 情境 C：locationControl 失敗的 graceful degrade

- 假設 record 存在但 control 已被 user backspace 刪除（Phase 8 Del 同步會自動跟著刪 record，但有 race 視窗）
- 點 row → `selectedFieldId` 設好、屬性區仍可編輯
- `locationControl` throw、靜默忽略、user 不會看到錯誤 toast

---

## 4. 驗證

### L1 vitest

scanner + manifest hygiene 維持 40 tests 全綠（Sprint L 不動 scanner，純 UI 加 getter + handler）。

### L0 模組升級

```
Registry loaded in 11.652s
```

0 dobtor 相關 ERROR。

### L1.5 靜態檢查

```
$ node --check doc_editor.js  → OK
$ xmllint --noout doc_editor.xml → well-formed
```

### Bundle 驗證

```
$ docker exec odoo18 curl -s /web/assets/debug/web.assets_backend.js | \
    grep -c "onFieldListRowClick\|onPreviewVariablesClick\|scanJinja2VariablesInTables"
9
```

Sprint J/K/L 的新 symbol 都在 bundled assets 內（live）。

---

## 5. 設計取捨

### 5.1 為什麼放 inspector 頂部、不另開分頁？

- 與 selected field 屬性編輯在同一 panel 視覺連續（user 不必跳分頁）
- 沒 record 時不顯示（`t-if="fieldsList.length > 0"`），不佔空間
- 240px max-height + 內滾，避免占去整個 inspector 高度

### 5.2 為什麼用 `locationControl` 不另用 `setRange`？

- `locationControl(conceptId)` 是 canvas-editor 官方 API、有跨頁滾動 + 視覺高亮
- `setRange` 只設游標位置、不負責 scroll、user 可能還看不到
- locationControl 自帶 fallback（找不到時 throw、不爆畫面）

### 5.3 為什麼不顯示 signer chip？

inspector 頂部空間有限。signer 資訊可以在 selected 後從屬性區看。Sprint L 列表只重點顯示「能辨識欄位身份」的最短資訊（name + id）。

---

## 6. 已知限制與後續

- **不支援 keyboard navigation**：↑/↓ 鍵還不能切換 row。aria 屬性有設、聚焦行為靠瀏覽器預設、未額外做。
- **列表不顯示「control 是否實際存在於文件」**：record 存在但 control 沒插入時，row 仍會顯示、locationControl 失敗也只是靜默。未來可加 ⚠️ 標記提示「孤兒 record」
- **超大文件（>100 欄位）效能**：`fieldsList` 是 getter、每次 render 都跑 sort。OWL 通常一個 state 變動 re-render 一次、100 個 item × N sort 仍小於 1ms，不擔心；> 500 個時可改 useMemo

---

## 7. 進度更新

| Sprint | 狀態 |
|---|---|
| G 掃描 → 建 record | ✅ |
| H 掃描 → 替換為 control（main 流） | ✅ |
| I manifest hygiene | ✅ |
| J 掃描 → 替換為 control（main + table） | ✅ |
| K 預覽變數（高亮 toggle） | ✅ |
| **L Inspector 欄位列表 + click-to-locate** | ✅ |
