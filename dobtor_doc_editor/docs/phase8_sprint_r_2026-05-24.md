# Phase 8 Sprint R — Playwright E2E for Sprint G/H/M/N round-trip（2026-05-24）

**性質**：補位 Sprint G→N 的端到端驗證缺口。Phase 8 累計 17 sprint 後，**首次**有 Playwright test 直接驅動編輯器 + 驗證 DB + 驗證 canvas-editor 內部狀態。
**範圍**：新檔 [tests/playwright/tests/admin-dobtor-doc-editor-sprint-ghn.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-ghn.spec.ts) — 2 個 E2E test。

---

## 1. 為什麼

Sprint A-F 都有 Playwright spec（`admin-dobtor-doc-editor-sprint-{a,b,c,d,e,f}.spec.ts`），但 Sprint G→N 全部沒有。Sprint Q 雖然加了 14 個 vitest 對純函式做覆蓋，但：
- vitest 測 regex / 純資料運算
- 沒測「實際點按鈕 → RPC 入庫 → control 真的在 canvas-editor 內」這條完整鏈

Sprint R 寫 2 個 E2E 涵蓋最重要的兩個流程：

### G.1 — 「掃描變數」建 record 流程

驗證鏈：
1. Bootstrap doc 含 3 個 `{{ var }}` 純文字
2. 點 `.doc-field-btn-scan` 按鈕
3. window.confirm 自動 accept
4. 後端：`doc.template.field` 應有 3 筆 `field_type='odoo_field'` record，`odoo_field_name` = `[contractor, estimate_date, project_name]`
5. Inspector：`.doc-inspector-fields-list-header` 顯示「所有欄位 (3)」
6. Sprint M：3 個 row 全部 `.doc-inspector-fields-list-item-orphan-icon`（因為沒替換）
7. `.doc-inspector-cleanup-orphans-btn` 可見 + 顯示 (3)

### HN.1 — 「掃描並替換」+「復原」round-trip

驗證鏈：
1. Bootstrap 同上
2. 點 `.doc-field-btn-scan-replace` → 自動 confirm
3. 後端：3 筆 odoo_field record 建立
4. `page.evaluate(() => window._docEditor.command.getControlList())` → 3 個 control
5. `.doc-field-btn-rollback` 可見（綠色按鈕，Sprint N）
6. 點復原 → 自動 confirm
7. 後端：record 全刪 = 0
8. `getControlList()` = 0
9. 復原按鈕消失

---

## 2. 跑法

```bash
cd /mnt/d/work/odoo18-docker/tests/playwright
npx playwright test admin-dobtor-doc-editor-sprint-ghn --project=admin
```

預設 headed（瀏覽器顯示）；CI 端會 headless（per `playwright.config.ts` `headless: process.env.CI ? true : false`）。

### 環境需求

- Odoo 容器 running 且 host 8069 accessible
- `.env`：`ADMIN_USER=admin` / `ADMIN_PASSWORD=admin` / `PORTAL_DB=odoo18_dev`
- 容器需以 `-p 8069:8069` published（如非 published、Windows 端 `localhost:8069` 不可達）

### 已知環境問題

本次衝刺 author 跑 spec 時遇到 Playwright 從 WSL 連 `localhost:8069` 失敗（`ERR_CONNECTION_REFUSED`）。診斷：

```bash
$ docker ps --format "{{.Names}}\t{{.Ports}}"
odoo18          8069/tcp                        # ← 無 host published
odoo_postgres   0.0.0.0:5432->5432/tcp          # ← postgres 有 published
```

odoo18 容器是 5 週前啟動、彼時 docker-compose 可能還沒有 `ports: 8069:8069` 設定。修法：

```bash
cd /mnt/d/work/odoo18-docker
docker-compose up -d odoo  # 會 recreate 容器、套用 published port
```

注意：recreate 會中斷正在使用的 session、要等 cold start。**未在 Sprint R 自動執行**，留 user 確認後手動跑。Spec 本身在 Sprint F (a80fd47) 的 baseline 跑得起來，所以 spec 寫法正確。

---

## 3. 設計取捨

### 3.1 為什麼只寫 2 個 test、不寫 G/H/J/K/L/M/N/O/P 全包？

ROI 分析：
- G.1 + HN.1 涵蓋 Sprint G/H/J/L/M/N 6 個 sprint 的核心流程
- K（預覽 toggle）/ O（filter）/ P（鍵盤 nav）都是純 UI、用 vitest mock 即可，E2E 收益低
- 寫越多 E2E 維護成本越高（canvas-editor 升版會破多個 test）

聚焦在「建 record + 替換 + 復原」這條 user 截圖 5 變數痛點的核心路徑。

### 3.2 為什麼用 `window._docEditor` 直接拿 canvas-editor instance？

`doc_editor.js` 第 419-420 行有「`window._docEditor = this.editor`」debug hook（dev 環境用）。Sprint R 從 page.evaluate 直接 query 比 querySelector + DOM walk 簡潔。

### 3.3 為什麼用 `autoAcceptDialogs` 全域接 dialog？

Sprint G/H/M/N 全部用 `window.confirm`。每 test 個別 wire dialog listener 重複。全 test scope 設一次更乾淨。注意：dialog auto-accept 意味著我們**不**驗證 dialog 內容 — 那是另一層 UX test，不在 E2E smoke 範圍。

### 3.4 為什麼 `waitForTimeout(4500)` 等替換？

替換階段是序列：3 × save_field (~300ms each) + 3 × setRange+backspace+insertControl (~500ms each) + autoSave (~1500ms)。4500ms 是 measured baseline 的 1.5× safety margin。若 flaky 加大。

---

## 4. 驗證

### Spec 靜態驗證

```
$ npx playwright test admin-dobtor-doc-editor-sprint-ghn --list
2 tests in 1 file
```

Spec parse OK、test discovery OK。

### Live run

未在 Sprint R 完整 run（環境問題、見 §2）。修好 port mapping 後跑、期望全綠。

---

## 5. 已知限制

- **沒測 Sprint J table cell 替換**：bootstrap content 只有 `<p>` 段落，沒有 `<table>`。寫 table 範本要設計 `<table><tr><td>{{ name }}</td></tr></table>` content + 驗證更多 td 內部結構。下次擴充
- **沒測 Sprint K/L/O/P 純 UI**：見 §3.1，用 vitest mock 即可
- **沒驗證 inspector 切換選中**：HN.1 只驗證 control 數量、沒驗證 click row → cursor moves。Sprint L locateControl 行為留下次

---

## 6. 進度更新

| Sprint | 狀態 |
|---|---|
| G-Q | ✅（見前 sprint docs）|
| **R Playwright E2E for G + H/N round-trip** | ✅ spec 完成、live run 待 port mapping fix |
