# Phase 8 Sprint S — E2E spec 擴展：Sprint J table cell 覆蓋（2026-05-24）

**性質**：補 Sprint R §5 列為 deferred 的 table cell E2E 覆蓋。
**範圍**：在 [admin-dobtor-doc-editor-sprint-ghn.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-ghn.spec.ts) 加 J.1 test。

---

## 1. 為什麼

Sprint R 的 2 個 E2E test（G.1 / HN.1）都用 `<p>...</p>` 純段落 bootstrap、只覆蓋 main 流。Sprint J 加的「table cell 替換」是**最容易破的特性**：

- main 流 setRange 是 `(s, e)` 兩參數
- table 流 setRange 是 `(s, e, tableId, tdIdx, tdIdx, trIdx, trIdx)` 七參數
- canvas-editor 版本升級時、後者最先壞

Sprint J 沒 vitest 直接驗證（位置 scanner 有測但 setRange 呼叫沒測）。Sprint S 補 E2E。

---

## 2. 程式碼變動

新增 J.1 test，bootstrap content 是 2×2 table，4 個 td 各含一個 jinja2 變數：

```html
<p>標頭：純文字</p>
<table border="1"><tbody>
  <tr><td>{{ td_a }}</td><td>{{ td_b }}</td></tr>
  <tr><td>{{ td_c }}</td><td>{{ td_d }}</td></tr>
</tbody></table>
```

驗證鏈：
1. 動工前：`doc.template.field` count = 0
2. 點 `.doc-field-btn-scan-replace` → auto-confirm
3. 等待 5500ms（4 × save_field + 4 × setRange+backspace+insertControl + autoSave；比 HN.1 的 4500ms 多 1s 因 table 路徑稍慢）
4. 後端：4 個 odoo_field record，`odoo_field_name = [td_a, td_b, td_c, td_d]`
5. canvas-editor：`getControlList().length === 4`
6. Sprint N 復原按鈕可見（snapshot 也涵蓋 table 替換）

---

## 3. 設計取捨

### 3.1 為什麼只驗 count 不驗 control 在哪個 td？

E2E smoke 層級只驗「結果數量正確」夠了。「control 確實坐落於對應 td」屬於更細的 unit 層級、由 Sprint J 的 vitest 位置 scanner 涵蓋（reconstruct === fullMatch 對齊測試）。E2E 太細會 flaky 又難維護。

### 3.2 為什麼合在同一 spec 檔不另起 `-sprint-j.spec.ts`？

3 個 test 共用 `loginAsAdmin / callKw / bootstrap / openEditor / autoAcceptDialogs` 幾乎所有 helper。拆檔要複製這些（或抽 module、又是一輪 refactor）。3 test 一檔還能跑得快、維護簡單。

### 3.3 為什麼 J.1 不另獨立做 rollback 路徑？

HN.1 已驗證主 rollback 流程（main 流）。table 場景的 rollback 走同一條 `executeSetValue(snapshot)` + 批次 `delete_field`、邏輯一致。重複測 ROI 低。

### 3.4 為什麼 timeout 設 150000ms？

table 處理較慢（4 個 cell × 7-arg setRange + autoSave 連續觸發）。Sprint F E2E baseline 60-90s 沒 table、本 test 要含 cold start + bootstrap + 4 個替換、150s 安全範圍。

---

## 4. 驗證

### Spec 靜態驗證

```
$ npx playwright test admin-dobtor-doc-editor-sprint-ghn --list
3 tests in 1 file
  G.1 ...
  HN.1 ...
  J.1 — 掃描並替換：table cell 內 {{ var }} 也應替換
```

### Live run

仍卡在 Sprint R §2 提到的 Docker port mapping 問題。同樣由 user 端 `docker-compose up -d odoo` recreate 容器後執行：

```bash
cd /mnt/d/work/odoo18-docker/tests/playwright
npx playwright test admin-dobtor-doc-editor-sprint-ghn --project=admin
# 三個 test 全綠 → Sprint G/H/J/L/M/N 端到端 OK
```

---

## 5. 已知限制

- **沒做 list / title 內變數**：scanner 本身就不收（Sprint J §2.2），E2E 也不該測
- **沒做 nested table**：Sprint J §5 已標 deferred；實務 ChienYi 範本不會有 nested table

---

## 6. 進度更新

| Sprint | 狀態 |
|---|---|
| G-Q | ✅ |
| R Playwright E2E (G + HN round-trip) | ✅ spec 完成、待 port fix |
| **S E2E spec J.1 (table cell)** | ✅ spec 完成、待 port fix |
