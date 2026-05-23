# Phase 8 Sprint A — Sub-nav 解封 + 預覽接後端（2026-05-23）

**性質**：user-directed 衝刺（auto 模式、執行方案 1 起手）。
**範圍**：規畫書 §Phase 8 Sub-nav 三分頁（dashboard / requests / settings）+ Header 預覽鈕的 Phase 2 殘留收口（plan：[purring-whistling-noodle.md](file:///home/chichi/.claude/plans/purring-whistling-noodle.md) Sprint A）。
**依據**：[ADR-022](architecture_decision.md)、[phase8_verification_2026-05-20.md](phase8_verification_2026-05-20.md)、user 2026-05-23 截圖揭示「介面 phase 2 還有許多沒做」、user 選定方案 1。

---

## 1. 背景：8 個 Phase 2 殘留缺口

2026-05-20 Phase 8 Phase 1+2.1 收口後，user 報告「介面還有許多未完成」。Plan 階段對 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml) / [doc_editor.js](../static/src/components/doc_editor/doc_editor.js) 全文 grep `Phase` / `disabled` / `placeholder`，盤點出 8 個明文殘留缺口：

| # | 區塊 | 殘留標記 |
|---|---|---|
| 1 | Sub-nav 儀表板 | `disabled` + title「Phase 8 路線圖未開放」 |
| 2 | Sub-nav 請求 | 同上 |
| 3 | Sub-nav 設定 | 同上 |
| 4 | Header 預覽鈕 | title「（Phase 2）」+ 點擊只彈 toast |
| 5 | Main grid 縮圖 panel | 註解「Phase 2 接 canvas-editor 縮圖 API」+ 寫死 1 個 dummy |
| 6 | 頁碼導航 | 「Phase 1 placeholder」、不真換頁 |
| 7 | 縮放 fit | 「Phase 1 只是視覺、不接 executePageScale」 |
| 8 | Phase 8.2.2 overlay 絕對定位 | ADR-022 條件啟動項、未動工 |

本 Sprint A 範圍：**缺口 1-4**。缺口 5-7 留 Sprint B/C，缺口 8 留 Sprint D。

---

## 2. 程式碼變動

| 層 | 檔案 | 變動摘要 |
|---|---|---|
| Template | [`static/src/components/doc_editor/doc_editor.xml`](../static/src/components/doc_editor/doc_editor.xml) | 移除 3 個 sub-nav `disabled` + 改 title；預覽鈕 title 改寫；Row 4 (field toolbar) / Row 5 (signer bar) 包 `t-if="state.activeSubNav === 'templates'"`；Row 6 (main grid) 改 inline `t-att-style` 隱藏（canvas-editor 不能被 t-if unmount）；後方新增 3 個 `doc-subnav-panel`（儀表板 / 請求 / 設定）殼 |
| Component JS | [`static/src/components/doc_editor/doc_editor.js`](../static/src/components/doc_editor/doc_editor.js) | `onSubNavClick` 重寫（4 tab whitelist + lazy-load requests）；`onPreviewClick` 接 `/dobtor_doc/template_preview` 並 `window.open` 新分頁顯示；新增 `_loadRequests` / `onDefaultSignerChange` / `onAutoSaveToggle`；state 加 `autoSaveEnabled` / `requests` / `requestsLoading` |
| CSS | [`static/src/css/doc_editor.css`](../static/src/css/doc_editor.css) | 新增 `.doc-subnav-panel*` / `.doc-dashboard-*` / `.doc-requests-*` / `.doc-settings-*` 共約 200 行 esign 風格樣式 |
| Controller | [`controllers/doc_controller.py`](../controllers/doc_controller.py) | 新增 `/dobtor_doc/template_preview`（jinja2 sandbox 渲染 content_html、StrictUndefined 缺變數列警告但不中斷）+ `/dobtor_doc/template_requests/list`（doc.fill.request model 缺席時回空陣列；未來實作後自動切真實 search_read） |

**未動範圍**：canvas-editor 函式庫；Phase 8.2.1 inline 拖曳邏輯；OOXML parser；既有 fill_template / render_preview / export_document 端點。

---

## 3. 驗證結果

### L1 vitest（TS 單元 / 整合）

```
Test Files  93 passed | 1 skipped (94)
     Tests  1699 passed | 1 skipped (1700)
Duration    94.09s
```

對照 Sprint 186 baseline 1699 — **0 regression**。

### L4 Odoo backend test

`docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev --test-tags /dobtor_doc_editor --stop-after-init --http-port=8189`：

```
0 failed, 0 error(s) of 92 tests when loading database 'odoo18_dev'
```

92 個 dobtor_doc_editor 後端 test 全綠，含 Phase 8 既有的 6 個 `test_template_field` 全通過。

### L0 模組升級

```
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev -u dobtor_doc_editor --stop-after-init
```

升級耗時 ~34s，無新 ERROR/WARNING（既有 warning 全為 pre-existing：construction_portal_v2 not installable / audit.trail 翻譯欄位等，與 dobtor_doc_editor 無關）。

### L0a 語法檢查

- `xmllint --noout doc_editor.xml`：**OK**
- `python3 -c "compile(open('doc_controller.py').read(), ...)"`：**OK**

---

## 4. 缺口收口狀態

| # | 缺口 | Sprint A 後狀態 |
|---|---|---|
| 1 | Sub-nav 儀表板 | ✅ 解封 + 顯示 4 卡片（總欄位 / 簽約人 / 頁數 / 文件狀態）+ 簽約人分配表 |
| 2 | Sub-nav 請求 | ✅ 解封 + 殼（空態時顯示 inbox 圖示；doc.fill.request model 缺席時回空陣列） |
| 3 | Sub-nav 設定 | ✅ 解封 + 4 個設定（紙張 / 自動儲存 / 預設簽約人 / 文件 ID） |
| 4 | Header 預覽鈕 | ✅ 接 `/dobtor_doc/template_preview` + 開新分頁顯示渲染後 HTML（含 print styles） |
| 5 | 縮圖 panel | ⏸ Sprint B/C |
| 6 | 頁碼換頁 | ⏸ Sprint B |
| 7 | 縮放 fit | ⏸ Sprint B |
| 8 | Phase 8.2.2 overlay | ⏸ Sprint D |

UI 上「Phase 8 路線圖未開放」/「Phase 2」字樣**從程式碼移除**；plan、ADR-022、本檔仍保留作為歷史紀錄。

---

## 5. 未涵蓋 / 後續

- **缺口 5-7 Sprint B/C**：需要先讀 `static/src/lib/canvas_editor/canvas-editor.umd.min.js` 確認 `executePageNo` / `executePageScale` / `getPageThumbnail` 三 API 是否存在；若無需走 shim。
- **缺口 8 Sprint D**：依 ADR-022 條件啟動，工時 3-4 週、需另起 sprint。
- **doc.fill.request model**：請求分頁的殼已就位，後端 model 是否新增由 Phase 8 進度決定。
- **Sprint A Exit Criteria**：技術驗證通過；視覺最終驗收待 user 用實際範本測試「儀表板/請求/設定」3 個分頁 + 預覽新分頁。

---

## 6. 規畫書 / 進度同步

- [progress_snapshot.md §3](progress_snapshot.md) Phase 8 列加註「Sprint A 收口 4 個 Phase 2 殘留 UI 缺口」。
- 規畫書 §Phase 8 Sub-nav 不再標 disabled。
