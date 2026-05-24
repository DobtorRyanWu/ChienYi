# Phase 8 Sprint M — 孤兒 record 標示 + 批次清理（2026-05-24）

**性質**：補位 Sprint L 列表的可見性與維護缺口。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js) 加 `orphanRecordIds` getter + `onCleanupOrphansClick`，inspector 列表加 ⚠️ 標 + 清理按鈕。

---

## 1. 痛點

Sprint L 完成後 user 可以在 inspector 看到所有 fields，但有個盲點：

> 「這個 row 對應的 control 還在文件裡嗎？還是只是個孤兒 record？」

孤兒 record 形成原因：
1. **Sprint G 用法**：「掃描變數」只建 record、文件仍是純 `{{ var }}` 文字 → 所有 record 都是孤兒（這是預期狀態）
2. **手刪 control + Del 同步 race**：user 把 control 反白 backspace、Phase 8 Del 同步因故沒同步（極罕見但可能）
3. **inspector 刪 record + control 還在**：反向 race

Sprint L 之前沒辦法看出，user 點 row 跳 location 時會 silent fail（locationControl throw、靜默 catch）但不知道為何。

Sprint M 視覺化標示 + 提供批次清理入口。

---

## 2. 程式碼變動

### 2.1 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

新增 getter + 清理 handler（在 `onFieldListRowClick` 之前）：

#### `get orphanRecordIds()` getter

```js
get orphanRecordIds() {
    // 取 canvas-editor 當前 control list 的 conceptId 集合
    // 與 _templateFieldsCache 中所有 id 比對
    // 在 cache、不在 controlIds 的 = 孤兒
    ...
}
```

容錯：`getControlList()` 在某些 canvas-editor 版本可能 throw → 退化（不標孤兒，避免假警報）。

#### `onCleanupOrphansClick()` handler

- 列出孤兒（top 5 + ... 還有 N）
- `window.confirm` 確認
- `Promise.all` 並行 `delete_field`
- 結果通知（全成功 / 部分失敗）
- 從 cache / `_lastControlIds` / `selectedFieldId` 同步移除

### 2.2 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

inspector 列表變動：

**header 加清理按鈕**（只在 orphan > 0 時顯示）：
```xml
<t t-if="orphanRecordIds.size > 0">
    <button class="doc-inspector-cleanup-orphans-btn"
            t-on-click="onCleanupOrphansClick">
        <i class="fa fa-trash-o"/>
        清理孤兒 (<t t-esc="orphanRecordIds.size"/>)
    </button>
</t>
```

**row 加孤兒標**：
- `is-orphan` class（CSS 警示橙底）
- 行首加 ⚠️ icon
- title 改成 `'⚠️ 孤兒：record 存在但文件內沒對應 control。'`

### 2.3 [doc_editor.css](../static/src/css/doc_editor.css)

- `.doc-inspector-fields-list-header` 改 `display: flex` 讓按鈕靠右
- `.doc-inspector-cleanup-orphans-btn`：警示橙 `#f59e0b`（與「掃描並替換」同語意）
- `.doc-inspector-fields-list-item.is-orphan`：淺橙底 `#fef3c7`、文字深棕 `#92400e`
- `.is-orphan.is-selected`：選中時轉深橙底白字，保持選中視覺對比
- `.doc-inspector-fields-list-item-orphan-icon`：橙色 `#f59e0b` ⚠️

---

## 3. 使用流程

### 情境 A：Sprint G 用法後想視覺化所有「待轉換」變數

1. 用「掃描變數」（Sprint G）建好 5 個 record（文件還是純文字）
2. 開 inspector → 列表 5 個 row 全部標 ⚠️（淺橙底）
3. user 一眼看出「這 5 個都還沒轉成 control」
4. 可選：按「掃描並替換」（H/J）一鍵轉、或手動逐個處理

### 情境 B：誤刪 control 後想清孤兒

1. user 手動 backspace 刪掉文件內某個 control
2. Phase 8 Del 同步沒抓到（極罕見 race）
3. inspector 列表中該 row 變 ⚠️
4. 按 header 「清理孤兒 (1)」→ 確認 → 後端 delete_field、cache 同步

### 情境 C：純探索用

1. 開 inspector、看到「清理孤兒 (3)」按鈕
2. 點 row 確認哪些是孤兒
3. 不想清掉 → 不按按鈕，視覺標示不擾人（淺橙、非紅警）

---

## 4. 驗證

### L1 vitest

scanner + manifest hygiene 維持 40 tests 全綠（Sprint M 不動 scanner、純 UI）。

### L0 模組升級

```
Registry loaded in 9.697s
```

0 dobtor 相關 ERROR。

### L1.5 靜態檢查

```
$ node --check doc_editor.js → OK
$ xmllint --noout doc_editor.xml → well-formed
```

### Bundle 驗證

```
$ docker exec odoo18 curl -s /web/assets/debug/web.assets_backend.js | \
    grep -c "onCleanupOrphansClick\|orphanRecordIds\|is-orphan"
8
```

---

## 5. 設計取捨

### 5.1 為什麼 getter 每次 render 都呼叫 getControlList？

簡潔勝於早期優化（KISS）。10-50 個 control 的常態下 < 1ms。> 500 個時可改用 `state.controlListRev` memoize（每次 contentChange ++）。

### 5.2 為什麼不自動清孤兒？

- Sprint G 的 user 故意只建 record、不要替換 → 全部都是「孤兒」是預期狀態、不該被自動清掉
- 自動清會吞掉 inspector 編輯中的草稿 record
- 清理是破壞性操作、要 user 確認

### 5.3 為什麼用「警示橙」而非「錯誤紅」？

- 孤兒 record **不是錯誤**、只是「未對應」
- 紅色會給 user 焦慮、橙色提示「值得注意但不緊急」
- 對齊 Sprint H/J「掃描並替換」按鈕的警示橙語意

### 5.4 為什麼不顯示「正常」rows 的 ✓ icon？

避免視覺噪音。orphan 是少數 / 例外、用 ⚠️ 標出例外更乾淨。

---

## 6. 進度更新

| Sprint | 狀態 |
|---|---|
| G 掃描 → 建 record | ✅ |
| H 掃描 → 替換為 control（main 流） | ✅ |
| I manifest hygiene | ✅ |
| J 掃描 → 替換為 control（main + table） | ✅ |
| K 預覽變數（高亮 toggle） | ✅ |
| L Inspector 欄位列表 + click-to-locate | ✅ |
| **M 孤兒 record 標示 + 批次清理** | ✅ |
