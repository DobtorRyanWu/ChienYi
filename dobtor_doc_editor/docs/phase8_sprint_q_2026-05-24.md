# Phase 8 Sprint Q — 抽出 analyzeScanResults + computeOrphanRecordIds 純函式 + 測試（2026-05-24）

**性質**：refactor，增加測試覆蓋。0 新功能、0 UI 變動。
**範圍**：兩個 helper 從 `doc_editor.js` handler 抽到 `jinja2_scanner.js`，加 14 個 vitest test。

---

## 1. 為什麼

Phase 8 累計 16 sprint，doc_editor.js 接近 2700 行。掃描 / 替換 / 孤兒等核心邏輯散在多個 handler 內、混雜 IO 與純運算。pure 部分理論上可單測但形式上跟 `this.editor` / `this.notification` / `this.state` 綁在一起無法測。

兩個明顯可抽的 helper：
1. **analyzeScanResults** — 從掃描結果 + cache 算出 `{positions, uniqueVars, toCreate, ...}`，被 `onScanAndReplaceClick` 用
2. **computeOrphanRecordIds** — 從 cache + controlIds 算 set diff，被 `orphanRecordIds` getter 用

兩個都是純函式形式、無 IO、易測試。

---

## 2. 程式碼變動

### 2.1 [jinja2_scanner.js](../static/src/components/doc_editor/jinja2_scanner.js)

#### `analyzeScanResults({scannedAll, mainPositions, tablePositions, existingOdooFieldNames})`

```js
export function analyzeScanResults({...}) {
    const positions = [...safeMain, ...safeTable];
    const uniqueVars = Array.from(new Set(positions.map(p => p.varName))).sort();
    const toCreate = uniqueVars.filter(v => !existingSet.has(v));
    return {
        positions,
        uniqueVars,
        toCreate,
        cacheHitCount: uniqueVars.length - toCreate.length,
        skippedCount: Math.max(0, scannedAll.length - uniqueVars.length),
    };
}
```

防禦：所有輸入若非陣列退化為空陣列。

#### `computeOrphanRecordIds(cache, controlIds)`

```js
export function computeOrphanRecordIds(cache, controlIds) {
    const idSet = controlIds instanceof Set ? controlIds : new Set(controlIds || []);
    const orphans = new Set();
    for (const f of cache) {
        if (!f || typeof f.id === "undefined") continue;
        if (!idSet.has(f.id)) orphans.add(f.id);
    }
    return orphans;
}
```

接受 Set 或 Array 的 controlIds（呼叫端方便）。

### 2.2 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

#### `orphanRecordIds` getter

IO 部分（`getControlList` + 解析 conceptId）留在 getter 內，純 diff 改呼叫 `computeOrphanRecordIds`：

```js
get orphanRecordIds() {
    if (cache.length === 0) return new Set();
    let controlIds;
    try { controlIds = parseControlList(this.editor); } catch { return new Set(); }
    return computeOrphanRecordIds(cache, controlIds);
}
```

#### `onScanAndReplaceClick`

原本 ~15 行的 positions 合併 + uniqueVars 計算 + cache 過濾被一行取代：

```js
const analysis = analyzeScanResults({
    scannedAll,
    mainPositions,
    tablePositions,
    existingOdooFieldNames: existingNames,
});
const { positions, uniqueVars, toCreate } = analysis;
```

剩餘 handler 邏輯（confirm dialog / save_field 序列化 / setRange + backspace 替換 / 結果通知）保持原樣。

### 2.3 [tests/unit/jinja2_scanner.test.ts](../tests/unit/jinja2_scanner.test.ts)

新增兩個 describe block，共 14 個 case：

**analyzeScanResults (7 case)**：
- 合併 main + table、去重 + 排序
- toCreate 過濾掉 existingOdooFieldNames
- skippedCount = scannedAll − uniqueVars（粗略 list/title proxy）
- uniqueVars 只看 positions 不看 scannedAll
- 同變數 main + table 重複只算一次 uniqueVar
- 空輸入 → 空結果
- 防禦：非陣列退化

**computeOrphanRecordIds (7 case)**：
- 標準 diff（cache 有 / controlIds 無）
- 空 cache
- 空 controlIds → 全部孤兒
- 接受 Array 自動轉 Set
- cache 含無 id 元素跳過
- 防禦：非陣列 cache
- 防禦：非 Set/Array controlIds

---

## 3. 驗證

### L1 vitest

```
Test Files  97 passed | 1 skipped (98)
     Tests  1937 passed | 1 skipped (1938)
```

對齊 Sprint P baseline 1923 + 14 新 Sprint Q test = 1937，**0 regression**。

scanner test count: 37 → 51（+14）。

### L0 模組升級

```
Registry loaded in 13.143s
```

0 dobtor 相關 ERROR。

---

## 4. 設計取捨

### 4.1 為什麼只抽兩個 helper？

doc_editor.js 還有更多可抽的（如 `onCleanupOrphansClick` 的批次刪除邏輯、`onRollbackScanReplaceClick` 的 setValue + delete 流程）。但這些都涉及 await RPC，純函式抽法收益有限（測試仍要 mock RPC）。

`analyzeScanResults` 與 `computeOrphanRecordIds` 是**最容易抽且 ROI 最高的兩個**：純資料 in → 純資料 out，直接 vitest 測。

### 4.2 為什麼 handler 不徹底拆成「pure prep / RPC / UI」三段？

那是 hexagonal architecture refactor、跨多 sprint。Sprint Q 只做 surgical extraction，handler 主體不動。完整 architectural refactor 待 Phase 9 視需求。

### 4.3 為什麼 `analyzeScanResults` 收 `scannedAll` 也收 positions？

scannedAll 來自 `scanJinja2Variables`（含 header/footer/巢狀）、positions 來自 `*WithPositions` + `*InTables`（只可替換的）。兩者來源不同、合併計算 skippedCount 必須兩者都看。Helper 不主動跑掃描（避免重複掃），由呼叫端傳入。

---

## 5. 進度更新

| Sprint | 狀態 |
|---|---|
| G-P | ✅（見前 sprint docs）|
| **Q refactor：analyzeScanResults + computeOrphanRecordIds 純函式 + 14 test** | ✅ |
