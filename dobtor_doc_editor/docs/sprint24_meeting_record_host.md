# Sprint 24 — ChienYi mixin 第三輪：監造會議記錄 host 補完

**期間**：2026-05-10
**主軸**：把唯一沒 host model 的 dobtor 預設樣板 `template_meeting_record` 真實接起來
**結論**：新建 `construction_meeting_record` 模組（純 ChienYi 端）+ bridge 加第 4 個 host inheritance；4 個 dobtor 預設樣板**全部 100% 有 host 引用**；105/105 Python regression + 6/6 Playwright admin E2E + 視覺 spot check 全綠。

---

## 0. 入工前狀態

| 項目 | Sprint 23 後 |
|---|---|
| Bridge inherit mixin 的 host model | 4（general / reservation self-inspection、defect、payment）|
| Bridge integration test | 30 case |
| ChienYi 預設樣板引用率 | 75%（4 個樣板中 3 個有 host） |
| **未補完的樣板** | `template_meeting_record`（無對應 ChienYi model 引用）|

`addons/construction_supervision_base/models/` 沒有 meeting record 相關 model；CLAUDE.md 記載「監造會議記錄」是「假想新模組」。Sprint 24 把它做出來。

---

## 1. 新模組 `construction_meeting_record`（純 ChienYi 端）

### 1.1 檔案結構

```
addons/construction_meeting_record/
├── __manifest__.py             # depends: ['construction_supervision_base', 'mail']
├── __init__.py
├── models/
│   ├── __init__.py
│   └── meeting_record.py
├── views/
│   ├── meeting_record_views.xml
│   └── menu.xml
├── security/
│   └── ir.model.access.csv
└── tests/
    ├── __init__.py
    └── test_meeting_record.py
```

### 1.2 模型 `construction.meeting.record`

| 欄位 | 型別 | 說明 |
|---|---|---|
| name | Char required | 會議名稱 |
| meeting_date | Date required, default today | 會議日期 |
| location | Char | 地點 |
| chairperson_id | Many2one(res.users) | 主席 |
| recorder_id | Many2one(res.users) default env.user | 紀錄人 |
| attendee_ids | Many2many(res.partner) | 出席者 |
| project_id | Many2one(supervision.project) | 關聯工程（可選）|
| company_id | Many2one(res.company) | 公司 |
| agenda | Html | 議程 |
| note | Text | 備註 |
| state | Selection (draft / confirmed / closed) | 狀態 |

繼承 `mail.thread` + `mail.activity.mixin`，自帶 chatter / 跟蹤通知。

### 1.3 View

- **list view**：日期 / 名稱 / 地點 / 主席 / 工程 / 狀態 badge
- **form view**：header（確認 / 結案 / 重設）+ statusbar；group（基本資訊 / 人員）；notebook（出席者 / 議程 / 備註）；chatter
- **search view**：name / project / chairperson 搜尋 + 狀態 filter + 工程/狀態 group_by
- **menu**：掛在 `construction_supervision_base.menu_document_management` 下，sequence=20

### 1.4 設計原則

- **獨立可裝**：不裝 dobtor_doc_editor_chienyi 仍可正常 CRUD（bridge 是 opt-in 增強）
- **欄位放在 ChienYi 端**：mixin 提供的欄位 `linked_doc_id` / `linked_doc_count` 由 bridge 注入，原模組保持輕量
- 簡化 state flow（3 個）：避免 over-engineering；後續真實業務需求可加 cancel / archived

### 1.5 測試（5 case）

`test_meeting_record.py`：
- `test_create_minimum` — 最小必填欄位建立
- `test_state_flow` — draft → confirmed → closed → draft 雙向
- `test_with_attendees_and_project` — 完整欄位 + Many2many
- `test_mail_thread_inherit` — message_ids 欄位繼承
- `test_no_doc_linked_mixin_without_bridge` — 偵測 bridge 是否裝（裝了則驗 mixin 共存；未裝則驗 fields 不存在）

---

## 2. Bridge 第 4 host inheritance

### 2.1 manifest 變動

```diff
 'depends': [
     'dobtor_doc_editor',
     'construction_quality',
     'construction_payment',
+    'construction_meeting_record',
 ],
 'data': [
     ...
+    'views/meeting_record_views.xml',
 ],
```

### 2.2 hook 覆寫

[`models/meeting_record.py`](../../dobtor_doc_editor_chienyi/models/meeting_record.py)：

| Hook | 覆寫內容 |
|---|---|
| `_doc_default_template_xml_id` | `'dobtor_doc_editor.template_meeting_record'` |
| `_doc_initial_name` | `<會議名稱>（<會議日期>）` |
| `_doc_collaborators` | `chairperson_id ∪ recorder_id ∪ attendee_ids.user_ids ∪ env.user` |
| `_doc_render_context` | 11 keys（含 `attendees: list[name]` / `attendee_count` / `chairperson` / `recorder` / `meeting_date` / `location` / `project_name`）|

關鍵設計：`attendee_ids` 是 `res.partner` Many2many，要 `.mapped('user_ids')` 才能轉 `res.users` 給 mixin 用——對應規劃書 [chienyi_integration_examples.md §2.1](chienyi_integration_examples.md) 的範例 A 寫法。

### 2.3 view 擴充

`view_construction_meeting_record_form_dobtor` 三處 inject（同 Sprint 21 pattern）：
- `<header>` 內加主按鈕（state ≠ closed 顯示）
- `<sheet>` 內加 `linked_doc_id` / `linked_doc_count` 隱藏欄位
- `<div class="oe_title">` 前加 `oe_button_box` 含 stat button（count > 0 顯示）

---

## 3. 測試（bridge round 3 — 9 case）

[`test_chienyi_bridge_round3.py`](../../dobtor_doc_editor_chienyi/tests/test_chienyi_bridge_round3.py)：

| # | Test | 驗證 |
|---|---|---|
| 1 | `test_mixin_fields_present` | linked_doc_id / linked_doc_count 繼承 |
| 2 | `test_uses_meeting_record_template` | xml_id 對應 template_meeting_record + 樣板真存在 |
| 3 | `test_action_creates_doc_with_template_content` | 點 action → doc.document 建立 + content_html 從樣板複製 |
| 4 | `test_initial_name_combines_name_and_date` | 命名包含名稱與日期 |
| 5 | `test_collaborators_include_chair_attendee_user_and_creator` | 主席 / 出席者 user / 當前 user 全在 |
| 6 | `test_collaborators_skip_partners_without_user` | partner 無對應 user 不 crash |
| 7 | `test_render_context_has_meeting_keys` | 11 keys 完整 + record_model 正確 |
| 8 | `test_doc_deletion_clears_linked_doc_id` | ondelete=set null 守則 |
| 9 | `test_template_coverage_100_percent_after_sprint24` | **4 個樣板全部有 host 引用**（**Sprint 24 主軸 assertion**）|

第 9 個 case 用 `assertIn(host, self.env)` 而非 `assertTrue(self.env.get(host))`（empty recordset 是 falsy 會 false negative，Sprint 24 第一輪曾踩到）。

---

## 4. 三層 SOP 全跑

### 4.1 Python regression（第 1 層）

```bash
docker exec odoo18 odoo -d odoo18_dev \
    --test-tags dobtor_doc_editor,construction_meeting_record \
    --stop-after-init --no-http --xmlrpc-port 8099
```

→ **0 failed, 0 error(s) of 105 tests**（Sprint 22 baseline 91 + meeting_record 5 + bridge round3 9 = 105）。

### 4.2 Playwright admin E2E（第 2 層）

```bash
cd /mnt/d/work/odoo18-docker/tests/playwright
npx playwright test --project=admin
```

→ **6 passed (1.6m)**（Sprint 23 5 case + Sprint 24 1 case = 6）：

| # | Test | Time |
|---|---|---|
| 1 | general.self.inspection 出現按鈕 | 27.6s（首次 cold start 較慢）|
| 2 | reservation.self.inspection 出現按鈕 | 9.6s |
| 3 | supervision.defect 出現按鈕 | 9.9s |
| 4 | payment.estimate 出現按鈕 | 9.9s |
| 5 | **construction.meeting.record 出現按鈕（Sprint 24）** | **9.5s** |
| 6 | 點按鈕 end-to-end 開 doc.document | 12.7s |

### 4.3 視覺 spot check（第 3 層）

開 [test-results/admin-dobtor-bridge-Sprint-10c73-...png](../../../tests/playwright/test-results/) 的 PNG 看到：

- 頂層 menu：工程管理 / 工程總覽 / 契約管理 / **進度管理** / 送審管制表 / 資源管理 / 人機管理 / **文件管理** / 報表
- breadcrumb：監造會議記錄 / 新會議記錄
- header：[確認] [**開啟線上文件**]（單一按鈕，沒 zombie 重複）/ statusbar 草稿 → 已確認 → 已結案
- form 欄位：會議日期 2026年05月10日 / 主席 / 紀錄人 千溢工程師 / 地點 / 關聯工程
- notebook tabs：出席者 / 議程 / 備註
- chatter：發送訊息 / 備註 / 活動 + 訂閱按鈕

—— 完整新模組可見 / 可手動操作。

---

## 5. 量化結果

| 指標 | Sprint 23 後 | **Sprint 24 後** |
|---|---|---|
| Bridge inherit mixin 的 host model | 4 | **5**（+meeting.record）|
| ChienYi 預設樣板引用率 | 75%（3/4） | **100%**（4/4，**主軸達成**）|
| Python regression | 91/91 | **105/105**（+5 meeting CRUD +9 bridge round3）|
| Playwright admin E2E | 5/5 | **6/6**（+1 meeting button）|
| 視覺 spot check 截圖 | 5（4 host + 1 e2e） | **6** |
| typecheck / vitest / flake8 / xmllint | green | green（不退化）|
| ChienYi 端新模組 | n/a | **construction_meeting_record**（獨立可裝）|

---

## 6. 規劃書同步項

- §0.5 增 Sprint 24 entry（新模組 / bridge 第 4 host / 樣板引用率 75%→100% / 三層 SOP 全跑）
- §0.5 結論段：「Sprint 24 起聚焦…」改為「Sprint 24 完成 ChienYi mixin 第三輪」
- §0.5 文件清單補 [sprint24_meeting_record_host.md](sprint24_meeting_record_host.md)
- §0.6.6 P1-2 行：標 Sprint 21+22+24（5 host model + 100% 樣板覆蓋）
- §0.6.10 W5-6 行：標 Sprint 21+22+24
- §0.6.13 完成度表加 Sprint 24 欄；優先級剔除「ChienYi mixin 第三輪」
- 文件 header 最後更新日期

---

## 7. Sprint 25+ 候選（重排）

剩下全是 🟡 / 🟢，無 P 級：

| 順位 | 主題 | 三層 SOP 適用 |
|---|---|---|
| 1 | 🟡 **7 個剩 -1 偏差 fixture 個別擊破**（Sprint 19 留下；含 Paginator R6 keepNext） | Layout 測試（vitest 為主）+ Playwright 開編輯器看頁數 |
| 2 | 🟡 **Phase 3.6 註腳 / 尾註**（佔 30% 政府文件需求） | Layout + Playwright 看頁底渲染 |
| 3 | 🟢 **CONTRIBUTING.md + 程式風格指南**（Phase 0 最後 5%） | 文件 only |
| 4 | 🟢 **lazy_loader / pagination_engine.js 評估清理**（Paginator 已取代後者） | code review only |
| 5 | 🟢 **HarfBuzz 真接 Layout**（CJK 字距） | Layout + visual diff |
| 6 | 🟢 **Phase 5 子項按使用量排序** | 視子項 |

---

**Sprint 24 一句話總結**：把規劃書 chienyi_integration_examples.md §2.1 的「假想 meeting.record」變成裝得上、跑得通、按下去開文件、可肉眼看到 chatter / statusbar / 出席者 tab 的真實模組；4 個 dobtor 預設樣板 100% 覆蓋達成；三層 SOP（Python / Playwright / 視覺）全綠。
