# Phase 8 Sprint N — 復原最近一次「掃描並替換」（snapshot rollback）（2026-05-24）

**性質**：直接緩解 Sprint H/J「實驗性、不可回復」警告的最大用戶恐懼。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js) 加 snapshot 捕捉 + `onRollbackScanReplaceClick`，工具列加「復原」按鈕（只在 snapshot 存在時顯示）。

---

## 1. 為什麼做這個

Sprint H/J confirm dialog 必須警告「⚠️ 替換為不可回復操作（無 transaction）」。實務上 user 看到這句會猶豫——明明只想「試試看」、卻要先 commit 到不可逆操作。雖然 canvas-editor 有 Ctrl+Z undo stack，但：
- 替換 5 處要按 5 次 Ctrl+Z
- 而且 Ctrl+Z 不刪後端新建的 record（會留下孤兒 record）

Sprint N 提供「**一鍵復原**」按鈕：
- 一步 setValue 還原文件（不論替換幾處）
- 自動刪掉本次新建的 record（不留孤兒）

---

## 2. 程式碼變動

### 2.1 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

#### state 加 `lastScanReplaceSnapshot`

```js
lastScanReplaceSnapshot: null,
// null = 沒可復原；object = {docData, createdFieldIds, replacedCount, timestamp}
// 覆蓋式單層 undo
```

#### `onScanAndReplaceClick` 動工前捕捉 snapshot

```js
let preReplaceSnapshot = null;
try {
    preReplaceSnapshot = JSON.parse(JSON.stringify(data));
} catch (e) {
    console.warn(...); // 失敗不擋流程、rollback 按鈕不會出現
}
```

JSON 序列化深拷貝避免後續操作意外動到 snapshot。

#### `onScanAndReplaceClick` 完成後存 snapshot

只在「至少 replaced 或 toCreate 有變動」時才存（避免反覆按沒變動的按鈕把有效 snapshot 覆寫掉）：

```js
if (preReplaceSnapshot && (replaced > 0 || toCreate.length > 0)) {
    this.state.lastScanReplaceSnapshot = {
        docData: preReplaceSnapshot,
        createdFieldIds: createdIds,  // 本輪新建的 id 列表（已存在的不包含）
        replacedCount: replaced,
        timestamp: Date.now(),
    };
}
```

注意 `createdFieldIds` **只**收**本輪新建**的 id；Sprint H/J dedup 用到的「已存在的 record」**不**會被刪掉。這樣 rollback 不會吞掉 user 之前手動建好的 record。

#### `onRollbackScanReplaceClick` 兩步驟

```js
async onRollbackScanReplaceClick() {
    const snap = this.state.lastScanReplaceSnapshot;
    // confirm dialog 顯示 N 秒前的操作 + 將還原 X 處 + 刪 Y 個 record
    // Step 1: editor.command.executeSetValue(snap.docData) 還原文件
    // Step 2: 序列化 delete_field 每個 createdFieldIds、累積 lastSuccess
    // 同步移除 cache / _lastControlIds / selectedFieldId
    // 清 snapshot（不可再次 rollback）
    // 通知
}
```

### 2.2 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

「預覽變數」按鈕後加：

```xml
<t t-if="state.lastScanReplaceSnapshot">
    <button class="doc-field-btn doc-field-btn-rollback"
            t-on-click="onRollbackScanReplaceClick"
            title="復原最近一次「掃描並替換」（還原文件 + 刪除本次新建的 record）"
            aria-label="復原掃描並替換">
        <i class="fa fa-undo" aria-hidden="true"/>
        復原
    </button>
</t>
```

只在 snapshot 存在時顯示——平常隱藏、user 看不到、不增加認知負擔。

### 2.3 [doc_editor.css](../static/src/css/doc_editor.css)

`.doc-field-btn-rollback`：綠色 `#10b981`（與其他按鈕語意分層）：
- 藍（掃描變數）= 寫但安全
- 警示橙（掃描並替換）= 寫且不可回復
- 灰（預覽變數）= 純讀
- **綠（復原）= 可逆、寬慰**

---

## 3. 使用流程

### 情境 A：試一下、不滿意、復原

1. 點「掃描並替換」→ confirm → 5 處文字變成 control + 建 5 個 record
2. user 不喜歡（或想保留純文字版）→ 點工具列「**復原**」按鈕（綠色，只在剛操作後出現）
3. confirm: 「將復原最近一次「掃描並替換」：還原文件內容（5 處 control 變回 {{ var }}）、刪除本次新建的 5 個 record。（執行於 12 秒前）確定要復原嗎？」
4. 按確定 → setValue + 5× delete_field
5. 通知「已復原：文件還原 + 5 個 record 刪除。」
6. 復原按鈕消失（snapshot 清掉、不可再復原）

### 情境 B：snapshot 被覆蓋

1. 跑「掃描並替換」第一次 → snapshot A 建立、復原按鈕出現
2. **沒按復原**，又改了文件其他地方、又跑第二次「掃描並替換」 → snapshot B 覆蓋 A
3. 復原只能還原到 snapshot B 對應的「第二次掃描前」狀態

（單層 undo，不存歷史。多層 undo 屬大型重構、留未來）

### 情境 C：snapshot 捕捉失敗

1. JSON 深拷貝失敗（例如文件包含循環引用、超大 binary）
2. console.warn 警告、流程繼續
3. 「掃描並替換」仍會成功，但**復原按鈕不會出現**（user 從 toast 提示中知道）

---

## 4. 驗證

### L0 模組升級

```
Registry loaded in 9.617s
```

0 dobtor 相關 ERROR。

### L1 manifest hygiene

3 tests 全綠（Sprint N 純 JS/XML/CSS、無新檔）。

### L1.5 靜態檢查

```
$ node --check doc_editor.js → OK
$ xmllint --noout doc_editor.xml → well-formed
```

---

## 5. 設計取捨

### 5.1 為什麼只支援單層 undo？

完整 undo stack 需要：
- snapshot 排程清理（防 OOM）
- redo 邏輯
- 與 canvas-editor undo stack 衝突處理

ROI 不划算。**user 想 try 一次 → undo 一次** 的 90% 場景已 cover。多層留待真的有需求時做。

### 5.2 為什麼 rollback 後就清 snapshot？

避免 user 誤按復原兩次：第二次按時文件已是 snapshot A 狀態，再 setValue(snapshot A) 是無效操作但會引發混淆。清掉、隱藏按鈕、明確一次性。

### 5.3 為什麼用 JSON deep clone 而非 structuredClone？

`structuredClone` 不在所有支援的瀏覽器（Chrome 98+/Firefox 94+）穩定。canvas-editor data 不含 DOM/Function/Symbol，JSON 來回足夠。如果未來文件需要含 Map/Set，再換 structuredClone。

### 5.4 為什麼 createdFieldIds 只收新建、不收沿用的？

避免 rollback 吞掉之前已建好的 record。例如：
- 第一次掃描並替換建 record 1, 2, 3
- 改文件、新增 `{{ x }}` 文字
- 第二次掃描並替換建 record 4（1-3 沿用）
- 復原 → 只應該刪 record 4、保留 1-3

### 5.5 為什麼用綠色不用藍色？

藍色已被「掃描變數」（Sprint G）佔用、語意「寫但安全」。綠色獨家代表「可逆寬慰」，與整體警示色系區分。

---

## 6. 已知限制

- **canvas-editor 的 undo stack 被 setValue 清空**：rollback 後 user 無法用 Ctrl+Z 回到 rollback 前的狀態。這是 canvas-editor 行為、不在控制範圍
- **snapshot 不持久化**：editor reload / 換頁就消失。snapshot 屬「操作 atomic boundary」、不該跨 session
- **不抓 header / footer 的 data**：snapshot 只存 `editor.command.getValue().data`，這包含 main 但 header/footer 取決於 canvas-editor 版本。實務上掃描並替換也只動 main 流（Sprint H/J），對齊安全
- **失敗 fault tolerance 偏 best-effort**：setValue 成功但部分 delete_field 失敗時，文件已還原、孤兒 record 殘留。可用 Sprint M「清理孤兒」收尾

---

## 7. 進度更新

| Sprint | 狀態 |
|---|---|
| G 掃描 → 建 record | ✅ |
| H 掃描 → 替換為 control（main 流） | ✅ |
| I manifest hygiene | ✅ |
| J 掃描 → 替換為 control（main + table） | ✅ |
| K 預覽變數（高亮 toggle） | ✅ |
| L Inspector 欄位列表 + click-to-locate | ✅ |
| M 孤兒 record 標示 + 批次清理 | ✅ |
| **N 復原最近一次掃描並替換** | ✅ |
