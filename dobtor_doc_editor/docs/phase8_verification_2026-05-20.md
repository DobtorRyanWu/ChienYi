# Phase 8 Template UI Builder — 端到端驗證報告（2026-05-20）

**性質**：user-directed 驗證 session（非 autopilot sprint）。
**範圍**：規劃書 §Phase 8 之 Phase 1（視覺風格靠攏）+ Phase 2.1（inline control 拖曳）。
**依據**：[ADR-022](architecture_decision.md)、[snappy-nova plan](file:///home/chichi/.claude/plans/d-dobtor-doc-editor-md-snappy-nova.md)、[sharded-sedgewick plan](file:///home/chichi/.claude/plans/mnt-d-work-odoo18-docker-addons-dobtor-sharded-sedgewick.md)。

---

## 1. 背景：Phase 8 程式碼已存在、但從未驗證

開工前 audit 發現 Phase 8（Phase 1 + Phase 2.1）的**全部程式碼已實作並 commit**，並非待開發：

| 層 | 檔案 | 狀態 |
|---|---|---|
| Model | `models/doc_template.py`（signer_ids / field_ids / 計數）、`doc_template_field.py`、`doc_template_signer.py` | 已建 |
| Security | `security/ir.model.access.csv`（3 model × editor/manager/portal 共 9 列 ACL） | 已建 |
| View | `views/doc_template_views.xml`（簽約人角色 / 範本欄位 notebook page） | 已建 |
| Controller | `controllers/doc_controller.py` L1536-1701（`/dobtor_doc/template_fields/` load / save_field / delete_field / save_signer 4 端點） | 已建 |
| 前端版面 | `static/src/components/doc_editor/doc_editor.xml`（header bar / sub-nav / field toolbar / signer chip / 三欄式 grid / inspector） | 已建 |
| 前端邏輯 | `doc_editor.js`（`FIELD_TYPES`、`onFieldButtonClick`、HTML5 drag&drop、`executeInsertControl`、inspector 雙向綁定 getter、`_syncDeletedControls` Del 同步） | 已建 |
| CSS | `static/src/css/doc_editor.css`（46 處 esign 樣式 class） | 已建 |
| 後端測試 | `tests/test_template_field.py`（6 test：CRUD / constrains / ACL / cascade） | 已建 |

**為何從未驗證**：Phase 8 程式碼於 ADR-022 落地當日（2026-05-19）寫完，被掃進 `bd75de9 Sprint 158: working tree backfill 收口` commit。autopilot snappy-nova 排程把正式 Phase 8 sprint 排在 Sprint 219-223、目前進度僅 Sprint 161-162，從未跑到——故規劃書 §5 Phase 8 的 `[ ]` 一直未打勾、Exit Criteria（「Phase 1 視覺 + Phase 2.1 inline control user accept」）從未執行。

→ 本 session 的工作 = **驗證 + 收口**，非新實作。0 行 Phase 8 production code 變動。

---

## 2. 驗證結果

### L1 vitest（TS 單元 / 整合）

```
Test Files  80 passed | 1 skipped (81)
     Tests  1358 passed | 1 skipped (1359)
```

Phase 8 前端為 OWL component JS、不在 vitest（OOXML parser TS）覆蓋範圍；vitest 全綠確認 Phase 8 不影響既有 docx 匯入體系。

### L4 Odoo backend test

`docker exec odoo18 odoo ... -u dobtor_doc_editor --test-tags /dobtor_doc_editor:TestTemplateField`：

```
0 failed, 0 error(s) of 6 tests when loading database 'odoo18_dev'
```

6 test 全過：signer 建立關聯、field_count compute、cross-template constrains、editor ACL 唯讀、manager 全 CRUD、signer unlink cascade。

### L3 瀏覽器實機驗證（Playwright）

環境：`odoo18` 容器升級 `dobtor_doc_editor` + restart；`odoo18_dev`；doc 1053（關聯範本 5「估驗計價單樣板」）。

| 驗證項 | 結果 |
|---|---|
| 編輯器渲染 Phase 8 esign 版面（header / sub-nav / field toolbar 10 鈕 / signer chip / 三欄式 / inspector / statusbar） | ✅ 完整渲染、0 console error |
| `action_open_editor` 帶入 `context.doc_id` → `_loadDocument` + `_loadTemplateFields` | ✅ 狀態「已載入」、簽約人 chip「簽約人 8」、statusbar「8 欄位」 |
| 點「文字」欄位鈕 → `save_field` 建紀錄 + `executeInsertControl` + 計數更新 + `selectedFieldId` 設定 | ✅ chip 8→9、statusbar 9 欄位、field id=47 建立、0 console error |
| Inspector 雙向綁定（header「文字 #47」/ 填寫者下拉 / 必填 / 佔位符 / 字型大小） | ✅ 全部綁定顯示 |
| DB 持久化 | ✅ `doc_template_field` id=47（field_type=text, signer_id=15）落地 |
| Inspector「刪除欄位紀錄」→ `delete_field` unlink + 計數回退 | ✅ id=47 刪除、template 5 回 8 筆、0 console error |

---

## 3. 未涵蓋 / 後續

- **Phase 2.2（overlay 絕對定位）**：依 ADR-022 為條件啟動項——「僅當 Phase 2.1 實測明確不滿意才啟動」。本次未動工，規劃書 §5 該項維持 `[ ]`。是否啟動需 user 在實測 Phase 2.1 後決定（ENGINEER-RULES §2 例外 2）。
- **HTML5 drag&drop 拖曳路徑**：`onWorkspaceDrop` 邏輯與點擊插入共用 `onFieldButtonClick`；點擊路徑已實測通過，拖曳路徑差異僅在 `_moveCaretToPoint`（dispatch synthetic mouse event 定位游標），未做 Playwright 拖曳模擬。
- **Phase 8 Exit Criteria**：ENGINEER-RULES 定義為「Phase 1 視覺 + Phase 2.1 inline control **user accept**」。技術驗證已通過；最終視覺驗收待 user 確認。

---

## 4. 規劃書 / 進度同步

- 規劃書 §Phase 8：Phase 1、Phase 2.1 之 `[ ]` → `[x]`；Phase 2.2 維持 `[ ]`。
- `docs/progress_snapshot.md` §3 Phase 8 列更新為「Phase 1 + 2.1 已驗證 / 2.2 未啟動」。
