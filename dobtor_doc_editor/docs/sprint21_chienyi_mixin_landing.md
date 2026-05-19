# Sprint 21 — ChienYi mixin 真實植入（補上唯一 P1 缺口）

**期間**：2026-05-09
**主軸**：把 `doc.linked.mixin` 真實接入第一個 ChienYi 模型，把 §0.6.6 P1-2 從 △ 翻 ✅
**結論**：建 bridge 模組 `dobtor_doc_editor_chienyi`、`general.self.inspection` 透過 `_inherit` 加 mixin、14 個 integration test 全綠 + 75/75 全套 Python regression 不退化；同時修一個沉睡的 mixin bug（`template.body` → 應為 `template_id`）。

---

## 0. 入工前狀態

| 項目 | Sprint 20 後 |
|---|---|
| `doc.linked.mixin` 程式碼 | ✅ 完整（[doc_linked_mixin.py](../models/doc_linked_mixin.py) 217 行）|
| `tests/test_doc_linked_mixin.py` | ✅ 8 case 全綠（但全部用 dummy model `doc.linked.test.fake`）|
| 整合範例文件 | ✅ [chienyi_integration_examples.md](chienyi_integration_examples.md) 寫得很完整 |
| **實際 construction_\* 模組植入** | ❌ **0 個** — Sprint 21 要補 |
| 預設樣板 | ✅ 4 個（`template_self_inspection` / `template_meeting_record` / `template_defect_improvement` / `template_payment_estimate` 在 `data/doc_template_data.xml`）|
| candidates | `general.self.inspection`（construction_quality）/ `reservation.self.inspection` / `supervision.defect` / `payment.estimate` / 假想的 `construction.meeting.record` |

選 `general.self.inspection` 是因為：
1. 它是 `construction_quality` 內最成熟、欄位最齊的模型（已有 inspector / supervisor / contractor / project 完整關聯）
2. 對應樣板 `template_self_inspection` 已 ready
3. ChienYi 規劃 docs 列為 P1 candidate（前次規劃 §0.6.13 第 2 順位）

---

## 1. Bridge 模組設計

### 1.1 為什麼是獨立 bridge 而不是直接改 construction_quality

| 方案 | 優 | 劣 |
|---|---|---|
| **A. 直接改 `construction_quality/models/general_self_inspection.py`** | 一個檔案改完 | construction_quality 從此硬依賴 dobtor_doc_editor，違反「兩邊單獨可裝」原則 |
| **B. 獨立 bridge 模組（採用）** | construction_quality / dobtor_doc_editor 雙方乾淨；可 opt-in；未來新增整合（reservation / defect / payment）走同一個 bridge | 多一個模組目錄 |

採 B。模組結構：

```
addons/dobtor_doc_editor_chienyi/
├── __manifest__.py             # depends: ['dobtor_doc_editor', 'construction_quality']
├── __init__.py
├── models/
│   ├── __init__.py
│   └── general_self_inspection.py   # _inherit = [本身, 'doc.linked.mixin']
├── views/
│   └── general_self_inspection_views.xml   # 加「開啟線上文件」按鈕 + stat button
└── tests/
    ├── __init__.py
    └── test_chienyi_bridge.py    # 14 case
```

### 1.2 Hook overrides

依 `chienyi_integration_examples.md §3` 的 self-inspection 範例：

| Hook | 覆寫內容 |
|---|---|
| `_doc_default_template_xml_id()` | `'dobtor_doc_editor.template_self_inspection'` |
| `_doc_initial_name()` | `<檢查編號> - <分項工程名稱>`，缺欄位 fallback `'自主檢查'` |
| `_doc_collaborators()` | `inspector_id ∪ supervisor_id ∪ contractor_company_id.user_ids ∪ env.user`（永遠至少含 current user，避免空集合）|
| `_doc_render_context()` | 13 個 key：record_id / record_model / record_name / project_name / inspection_no / inspection_date / inspection_type / sub_project_name / inspection_location / timing / inspector / supervisor / contractor。timing 從 selection label 取顯示文字 |

### 1.3 View 擴展

`construction_quality.view_general_self_inspection_form` 三處 inject：

```xml
<xpath expr="//header" position="inside">
    <button name="action_open_linked_doc" string="開啟線上文件"
            type="object" class="oe_highlight" icon="fa-file-text-o"
            invisible="state == 'closed'"/>
</xpath>

<xpath expr="//sheet" position="inside">
    <field name="linked_doc_id" invisible="1"/>
    <field name="linked_doc_count" invisible="1"/>
</xpath>

<xpath expr="//div[@class='oe_title']" position="before">
    <div class="oe_button_box" name="dobtor_button_box">
        <button name="action_open_linked_doc" type="object"
                class="oe_stat_button" icon="fa-file-text-o"
                invisible="linked_doc_count == 0">
            <field name="linked_doc_count" widget="statinfo" string="線上文件"/>
        </button>
    </div>
</xpath>
```

`closed` 狀態時隱藏主按鈕（檢查已結案不再開新編輯入口）；stat button 永遠存在但 count=0 時隱藏。

---

## 2. 沉睡 bug 修正：`template.body` → `template_id`

### 2.1 發現

第一輪測試 13/14 綠，1 個失敗：

```
FAIL: test_created_doc_has_template_content
AssertionError: False is not true : content_html 不應為空（應從樣板複製）
```

### 2.2 根因

`doc.linked.mixin._create_linked_doc()` 原本寫：

```python
if template_xml_id:
    template = self.env.ref(template_xml_id, raise_if_not_found=False)
    if template:
        if hasattr(template, 'body'):
            vals['content_html'] = template.body
```

但 `doc.template` 的欄位是 `content_html`，**根本沒有 `body`**：

```python
# models/doc_template.py:11
content_html = fields.Html(...)
```

`hasattr(recordset, 'body')` 在 Odoo 上不會 raise（每個 model 都有大量 inherited fields），但 `.body` 取出來的不是樣板內容。修前的 inspection 即使指定樣板，**`vals['content_html']` 從沒真的被填**——但 `tests/test_doc_linked_mixin.py` 用的 dummy template 也沒 body 欄位，從沒測到過這條路徑，bug 沉睡至今。

### 2.3 修法

走 `vals['template_id']` 即可，因為 `doc.document.create()` 早就有 auto-fill 邏輯（[doc_document.py:375-381](../models/doc_document.py#L375-L381)）：

```python
# 範本自動填充：template_id 有給但 content_html 沒給（或空）
if vals.get('template_id') and not vals.get('content_html'):
    template = self.env['doc.template'].browse(vals['template_id'])
    if template.content_html:
        vals['content_html'] = template.content_html
```

修後的 mixin：

```python
template_xml_id = self._doc_default_template_xml_id()
if template_xml_id:
    template = self.env.ref(template_xml_id, raise_if_not_found=False)
    if template and 'template_id' in Doc._fields:
        vals['template_id'] = template.id
```

效益：
- 修正 content_html 從未真填的 sleeping bug
- 讓 `doc.document.template_id` 反向指回樣板，後台 UI 看得到「此文件源自哪個樣板」
- 觸發 doc.document 既有 `_onchange_template_id` 寫回邏輯（page_format 也會跟著套）

### 2.4 影響面

- 既有 8 個 mixin unit test（用 dummy fake model + 不指定 template_xml_id）→ 不受影響
- Sprint 19 baseline Python 61 case → 全綠不退化
- Sprint 21 新增 14 case → 全綠（含 `test_created_doc_has_template_content`）

---

## 3. 測試覆蓋（14 case）

| # | Test | 驗證項 |
|---|---|---|
| 1 | `test_mixin_fields_present` | linked_doc_id / linked_doc_count 兩個欄位都繼承到 |
| 2 | `test_mixin_methods_present` | action_open_linked_doc / 4 個 hook 都繼承到 |
| 3 | `test_initial_linked_doc_count_is_zero` | 新建記錄 count=0 |
| 4 | `test_action_open_linked_doc_creates_doc` | 第一次點 action 觸發建立 doc.document |
| 5 | `test_action_open_linked_doc_idempotent` | 第二次點不再 create |
| 6 | `test_doc_uses_self_inspection_template` | xml_id 指向 template_self_inspection 且能 ref |
| 7 | `test_created_doc_has_template_content` | content_html 從樣板複製到位（**捕到 sleeping bug**）|
| 8 | `test_collaborators_include_inspector_and_current_user` | inspector + env.user 都在 |
| 9 | `test_created_doc_has_collaborators` | doc.collaborator_ids 寫入正確 |
| 10 | `test_render_context_contains_key_fields` | 9 個 key 都在 + record_model 正確 |
| 11 | `test_render_context_handles_missing_optional_fields` | contractor / supervisor 空時不 crash |
| 12 | `test_initial_name_combines_no_and_subproject` | 文件名組裝邏輯 |
| 13 | `test_reverse_lookup_doc_to_record` | doc.model_id + doc.res_id 寫對 + `_get_record_from_linked_doc()` 反查 |
| 14 | `test_doc_deletion_clears_linked_doc_id` | mixin 的 `ondelete='set null'` 守則生效 |

執行時間：14 case / 0.56s / 537 queries。

---

## 4. 量化結果

| 指標 | Sprint 20 後 | **Sprint 21 後** |
|---|---|---|
| 安裝可用 ChienYi mixin 整合模組 | 0 | **1**（`dobtor_doc_editor_chienyi`）|
| 實際 inherit `doc.linked.mixin` 的 ChienYi model | 0 | **1**（`general.self.inspection`）|
| Python 測試 case 數 | 61 | **75**（+14 bridge case）|
| 全套 dobtor regression | 61/61 pass | **75/75 pass** |
| Vitest | 735/735 pass + 1 skip | **735/735 pass + 1 skip**（不退化）|
| Sleeping bug 修正 | n/a | **1**（template.body → template_id，修法觸動 doc.document 既有 auto-fill 鏈）|
| Phase 4.5 (產品化) 完成度 | 96% | **100%**（13/13 全部完成）|

---

## 5. 與規劃書 §0.6 的對應修正

| 段落 | Sprint 20 後 | **Sprint 21 後** |
|---|---|---|
| §0.6.6 P1-2 與 ChienYi 整合 mixin | △（mixin / docs / templates 在但無實際 inherit）| **✅** `dobtor_doc_editor_chienyi` bridge + `general.self.inspection` inherit + 14 test 全綠 |
| §0.6.10 W5-6 共存策略 + ChienYi mixin | △（mixin 在但無實際 construction_\* 引用）| **✅** |
| §0.6.12 與 ChienYi 整合 hook | △ | **✅** |
| §0.6.13 Phase 4.5 完成度 | 96% | **100%** |
| §0.6.13 Sprint 22+ 第 1 順位 | 🔴 ChienYi mixin 真實植入 | ~~已完成~~；改第 2 順位「7 個 -1 偏差個別擊破」上推 |

---

## 6. Sprint 21 後 Sprint 22+ 新優先級

| 順位 | 主題 | 屬性 |
|---|---|---|
| 1 | **🟡 7 個剩 -1 偏差 fixture 個別擊破**（Sprint 19 留下；含 R6 keepNext） | Layout 品質 |
| 2 | **🟡 Phase 3.6 註腳 / 尾註**（佔 30% 政府文件需求） | Parser + Layout |
| 3 | **🟡 ChienYi mixin 第二輪整合**（reservation.self.inspection / supervision.defect / payment.estimate） | 整合面擴展（同 bridge 模組）|
| 4 | **🟢 CONTRIBUTING.md + 程式風格指南**（Phase 0 最後 5%）| 非阻塞 |
| 5 | **🟢 lazy_loader / pagination_engine.js 評估清理** | 程式碼 hygiene |
| 6 | **🟢 HarfBuzz 真接 Layout** | CJK 字距 |
| 7 | **🟢 Phase 5 子項按使用量排序** | 進階功能 |

---

**Sprint 21 一句話總結**：把 mixin 從「設計完備、無人引用」翻成「裝得上、跑得通、抓出沉睡 bug」，**Phase 4.5 全部 13 項補完，原規劃唯一剩下的 P 級缺口收攤。**

---

## 7. Sprint 21 後記：500 Internal Server Error 事故

### 7.1 症狀

Sprint 21 收尾後使用者點開 dobtor_doc_editor 編輯器，瀏覽器吐 `Internal Server Error`；Odoo log 顯示：

```
KeyError: 'assets'
File "/usr/lib/python3/dist-packages/odoo/addons/base/models/ir_asset.py", line 186
    for command in odoo.modules.module._get_manifest_cached(addon)['assets'].get(bundle, ())
```

URL：`GET /odoo/action-dobtor_doc_editor.action_doc_editor → 500`

### 7.2 根因

**安裝新 bridge 模組 `dobtor_doc_editor_chienyi` 後沒跟著 `docker restart odoo18`**。

Odoo 18 升級 SOP（odoo18-docker/CLAUDE.md 已寫）兩步驟缺一不可：

```bash
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev -i <module> --stop-after-init  # 1) 更新 DB
docker restart odoo18                                                                          # 2) 重啟主進程
```

`--stop-after-init` 只更新 DB 內容（templates / assets / records），**不重啟主進程**。Python 端的：
- `_get_manifest_cached` LRU cache（per-process）
- model registry（addons 列表）
- ir.qweb compiled template cache

都還是 init 前的舊版本，新模組 `dobtor_doc_editor_chienyi` 對 cache 而言是「不認識的 addon」，render `web.assets_web_print` 時遞迴展 bundle，呼叫 `_get_manifest_cached('dobtor_doc_editor_chienyi')` 走到 `load_manifest` 的 `if not manifest_file: return {}` 分支（mod_path 解析失敗或快取 race），取空 dict 後 `['assets']` 直接 KeyError。

### 7.3 修法

```bash
docker restart odoo18
```

ARM 8 秒後 cache 重建、registry 完整，所有 URL 200 OK。

### 7.4 Lesson learned + 預防

1. **CLAUDE.md 升級 SOP 不是建議是律令**：每次 `-i` / `-u` 後立刻 `docker restart`
2. **Sprint 21 docker exec install 命令本就應該寫成 `... --stop-after-init && docker restart odoo18`**（複合指令）；下次寫成 helper script 避免遺漏
3. **`tests/scripts/` 後續可以加一支 `install_and_restart.sh`** 包裝兩步驟
4. **Sprint 21 init 階段 audit 漏寫此 step** 是疏忽；本後記補入規劃書 §0.5 對應 entry

### 7.5 影響面

- **Python regression**：跑 test 有 `--stop-after-init`，但 test runner 在 init 後立即 run-and-exit，不依賴 long-running cache，所以 75/75 仍綠（test 期間沒踩到）
- **生產 / 互動式 UI**：踩到，500
- **CI**：CI 不跑互動式 UI，沒檢測到此類問題；Sprint 22+ 可考慮加 smoke test 「-i 後 GET /odoo/action-... 回 200」
