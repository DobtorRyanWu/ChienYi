# Phase 8 Sprint K — 預覽變數（高亮 toggle，純讀）（2026-05-24）

**性質**：補位 Sprint H/J 破壞性操作的可見性缺口。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js) 新增 `onPreviewVariablesClick`，工具列加「預覽變數」按鈕（中性灰）。

---

## 1. Sprint K 為什麼從「重建 controls」改成「預覽變數」

原規劃 K = 從 `_templateFieldsCache` 重建 control（用 `executeSetValue` 一次插所有 control，繞過 reverse-replace 風險）。實際審視發現：

> Sprint H/J 的 dedup 路徑已 cover 此情境。若 record 已存在、`existingNames` 過濾後 `toCreate` 為空，Phase 1 不打 save_field、Phase 2 從 cache 取 fieldId 直接執行替換。

→ 原 K 是 H/J 已有功能的「另一種實作」、無新使用者價值。

**改做的 K = 預覽變數**：在按破壞性按鈕前提供讀模式可見性。

| 工具列鍵 | 顏色 | 性質 |
|---|---|---|
| 掃描變數（G） | 藍 | 寫，安全（只建 record）|
| 掃描並替換（H/J） | 警示橙 | 寫，**不可回復** |
| **預覽變數（K）** | **中性灰** | **讀**，toggle |

---

## 2. 行為

點「預覽變數」：
- **未高亮**：用 `editor.command.search(regex, { isRegEnable: true })` 標註所有 `{{ var }}`；toast 印「找到 N 個變數（共 M 處）已高亮」
- **已高亮**：`editor.command.search(null)` 清除；toast 印「已清除變數高亮」

`_previewVarsActive` 旗標記住目前狀態，避免依賴 canvas-editor 內部狀態探查。

---

## 3. 程式碼變動

### 3.1 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js) `onPreviewVariablesClick`

關鍵：
- regex 與 `scanJinja2Variables` 一致（`[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*`）
- search 失敗時退化通知，不擋使用者
- 同時呼叫 `scanJinja2Variables` 把 unique 數量 + 總處數塞進 toast

### 3.2 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

「掃描並替換」按鈕後加：

```xml
<button class="doc-field-btn doc-field-btn-preview-vars"
        t-on-click="onPreviewVariablesClick"
        title="在文件內高亮所有 {{ }} 變數（toggle、純讀、不修改文件）"
        aria-label="預覽變數">
    <i class="fa fa-search" aria-hidden="true"/>
    預覽變數
</button>
```

### 3.3 [doc_editor.css](../static/src/css/doc_editor.css)

`.doc-field-btn-preview-vars` 配色 = 中性灰 `#64748b`，與「掃描變數」藍、「掃描並替換」警示橙形成三色語意：
- 藍 = 寫但安全
- 橙 = 寫且不可回復
- 灰 = 純讀

---

## 4. 驗證

### L1 vitest

scanner + manifest hygiene 維持 40 tests 全綠（Sprint K 不動 scanner 邏輯，只是 search API wire-up）。

### L0 模組升級

```
Registry loaded in 14.243s
```

0 dobtor 相關 ERROR。

### L1.5 靜態檢查

```
$ node --check doc_editor.js  → OK
$ xmllint --noout doc_editor.xml → well-formed
```

### 手動驗證（待 user 開瀏覽器確認）

1. 開含 `{{ var }}` 的文件
2. 點「預覽變數」→ 應該所有變數加上 canvas-editor 預設搜尋高亮
3. 通知顯示找到的數量
4. 再點一次 → 高亮清除

---

## 5. 設計取捨

### 5.1 為什麼用 `search()` 不另實作高亮層？

canvas-editor 內建搜尋會在 canvas 上畫黃色背景高亮（也可定位下一筆）。重新實作 highlight layer 需畫覆蓋層 + 自行管理位置同步，成本 10×，收益相同。

### 5.2 為什麼是 toggle 而非「按一次顯示、自動消失」？

如果 user 想對照「哪些是動態變數」逐處 review，希望高亮持續一陣子；同時 navigate 編輯時不想被殘留高亮干擾。Toggle 給他們明確控制。

### 5.3 為什麼 regex 字串用 `\\{\\{` 雙跳脫？

`search(payload, { isRegEnable: true })` 的 payload 是 string、會在 canvas-editor 內部 `new RegExp(payload)`。JS 字串字面值內 `\\{` → `\{`，給 RegExp 看到的是 `\{`（escape `{` 字面字元）。

---

## 6. 進度更新

| Sprint | 狀態 |
|---|---|
| G 掃描 → 建 record | ✅ |
| H 掃描 → 替換為 control（main 流） | ✅ |
| I manifest hygiene | ✅ |
| J 掃描 → 替換為 control（main + table）| ✅ |
| **K 預覽變數（高亮 toggle）** | ✅ |
| L inspector field list + click-to-locate | 待做 |
