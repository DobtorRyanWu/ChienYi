# Sprint 22 — ChienYi mixin 第二輪整合

**期間**：2026-05-09
**主軸**：把 Sprint 21 建立的 bridge module 從「1 個 model」擴展到「4 個 model」
**結論**：`reservation.self.inspection` / `supervision.defect` / `payment.estimate` 三個 model 全部接入 `doc.linked.mixin`；bridge integration test 14 → 30；全套 dobtor regression 75 → 91 全綠；同時把 Sprint 21 後記踩到的「`-i` 後忘記 `docker restart`」事故當 SOP 規矩封進每次升級命令。

---

## 0. 入工前狀態

| 項目 | Sprint 21 後 |
|---|---|
| Bridge module 已建 | ✅ `addons/dobtor_doc_editor_chienyi/` |
| 已 inherit mixin 的 ChienYi model | 1（`general.self.inspection`）|
| Sprint 21 整合 test | 14 case |
| Phase 4.5 完成度 | 100%（13/13）|

---

## 1. 三個 model 整合

### 1.1 `reservation.self.inspection`（預約式自主檢查）

| 屬性 | 設定 |
|---|---|
| 樣板 | `dobtor_doc_editor.template_self_inspection`（與一般式共用）|
| 文件命名 | `<inspection_no> - <sub_project_name>`，缺欄位 fallback `'預約式自主檢查'` |
| Collaborators | `inspector_id ∪ env.user`（無 supervisor / contractor 欄位）|
| Render context | 13 keys（含 `slip_no`：通報單編號 / `subcontractor`：協力廠商）|
| View 擴充 | header 主按鈕 `state != 'confirmed'` 顯示；button_box stat |

關鍵差異 vs 一般式：模型 `_inherit = ['mail.thread', 'photo.sync.mixin']`（無 `mail.activity.mixin`）；多 `slip_id` 通報單關聯欄位；`name` 欄位叫 `inspection_no`。

### 1.2 `supervision.defect`（缺失改善）

| 屬性 | 設定 |
|---|---|
| 樣板 | `dobtor_doc_editor.template_defect_improvement` |
| 文件命名 | `<name> - <description[:40]>`（描述截短）|
| Collaborators | `responsible_user_id ∪ create_uid ∪ env.user` |
| Render context | 12 keys（含 `defect_type` / `severity` 從 selection label / `found_date` / `deadline` / `responsible`）|
| View 擴充 | header 主按鈕 `state != 'closed'` 顯示 |

注意 `severity` 欄位**模型實際沒有**（CLAUDE.md §「常用模型欄位參考表」標的是該欄已被刪除的舊狀態）；以 `if 'severity' in self._fields` guard 起來，永遠 fallback 空字串。

### 1.3 `payment.estimate`（估驗計價）

| 屬性 | 設定 |
|---|---|
| 樣板 | `dobtor_doc_editor.template_payment_estimate` |
| 文件命名 | `<name> - <project.name>`，name 預設「第N次估驗計價」|
| Collaborators | `submitted_by_id ∪ approved_by_id ∪ env.user`（不含 line 內 task assignees 避噪音）|
| Render context | 13 keys（含 `estimate_no` / `subtotal` / `submitted_*` / `approved_*` / `state_label` / `line_count`）|
| View 擴充 | header 主按鈕 `state != 'archived'` 顯示 |

實際 state Selection（`draft/pending_approval/approved/archived`）與 CLAUDE.md 文件記錄的舊版（7 狀態）**不同**；以實際 model 為準。

### 1.4 Bridge manifest 變動

```diff
 'depends': [
     'dobtor_doc_editor',
     'construction_quality',
+    'construction_payment',
 ],
 'data': [
     'views/general_self_inspection_views.xml',
+    'views/reservation_self_inspection_views.xml',
+    'views/supervision_defect_views.xml',
+    'views/payment_estimate_views.xml',
 ],
```

---

## 2. 測試 [tests/test_chienyi_bridge_round2.py](../../dobtor_doc_editor_chienyi/tests/test_chienyi_bridge_round2.py)

3 個 TestClass，每個 5-6 個 case：

| Class | Cases | 主要驗證 |
|---|---|---|
| `TestReservationSelfInspectionBridge` | 5 | mixin fields / template / 含內容建立 / collaborators / render ctx |
| `TestSupervisionDefectBridge` | 5 | 同上 + `defect_no` / `description` 截短 |
| `TestPaymentEstimateBridge` | 6 | 同上 + `state_label='草稿'` / `estimate_no` / 命名含 project |

合計 16 cases。

### 2.1 兩個 setUp 陷阱（Sprint 22 踩到）

#### 陷阱 1：`reservation.self.inspection.slip_id` NOT NULL

第一輪 test 全炸：

```
psycopg2.errors.NotNullViolation: null value in column "slip_id" violates not-null constraint
```

原因：`reservation.self.inspection` 必須關聯一個 `reservation.notification.slip`（schema 強制）。setUp 補建一個 slip。

#### 陷阱 2：`_check_slip_state` 與 `slip.state` Selection 不對齊

```
ValidationError: 只能在已核准、執行中或已完成的通報單中建立自主檢查
```

ChienYi 內部不一致：

```python
# construction_reservation/models/reservation_self_inspection.py:115
if record.slip_id.state not in ('approved', 'in_progress', 'completed'):
    raise ValidationError(...)

# construction_notification_slip/models/notification_slip.py:128
state = fields.Selection([
    ('draft', '草稿'),
    ('not_started', '未開始'),
    ('in_progress', '施工中'),
    ('closed', '已結案'),
])
```

constraint 接受的 3 個值與 selection 定義的 4 個值**只交集 `'in_progress'`**——`'approved'` / `'completed'` 在實際模型不存在會 ValueError。這是 ChienYi 既有的內部不一致（不是 Sprint 22 造成），暫以 `'in_progress'` 解 setUp，並在 test 註解記錄此陷阱供後續整合者參考。

---

## 3. SOP 落實：升級必跟 restart

Sprint 21 後記踩到「`-i` 後忘記 `docker restart`」導致 manifest cache stale `KeyError: 'assets'`。Sprint 22 全程改用複合命令：

```bash
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
    -u dobtor_doc_editor_chienyi --stop-after-init --no-http --xmlrpc-port 8099 \
    && docker restart odoo18
```

跑完接 8 秒 sleep + curl /web/database/selector 確認 200，未踩雷。

---

## 4. 量化結果

| 指標 | Sprint 21 後 | **Sprint 22 後** |
|---|---|---|
| Bridge inherit mixin 的 model 數 | 1 | **4** |
| Bridge integration test | 14 | **30**（+16，全綠）|
| 全套 dobtor regression | 75/75 | **91/91**（+16）|
| Vitest | 735/735 + 1 skip | **735/735 + 1 skip**（不退化）|
| ChienYi 預設樣板被 mixin 引用比例 | 1/4 (`self_inspection`) | **3/4**（`self_inspection` × 2 共用 + `defect_improvement` + `payment_estimate`；只剩 `meeting_record` 還無 host model 引用）|

---

## 5. 與規劃書 §0.6 的對應修正

| 段落 | Sprint 21 後 | **Sprint 22 後** |
|---|---|---|
| §0.6.6 P1-2 | ✅（1 model）| ✅（4 models — 強化）|
| §0.5 結論 | Sprint 21 完成 P1-2 single-leg | **Sprint 22 完成 second-leg：bridge 從 1 model → 4 models**；template 引用率從 25% → 75% |
| §0.6.13 Sprint 22+ 優先級第 5 順位 | 「ChienYi mixin 第二輪整合」 | **完成**（從清單剔除）|

Phase 4.5 仍維持 100%（無新欄位引入）；只是把 already-✅ 項目的 coverage 加深。

---

## 6. Sprint 23+ 候選

依 Sprint 22 後新優先級：

| 順位 | 主題 | 屬性 |
|---|---|---|
| 1 | **🟡 7 個剩 -1 偏差 fixture 個別擊破**（Sprint 19 留下；含 R6 keepNext） | Layout 品質 |
| 2 | **🟡 Phase 3.6 註腳 / 尾註**（佔 30% 政府文件需求） | Parser + Layout |
| 3 | **🟢 ChienYi mixin 第三輪**（引入 `meeting.record` host model 用 `template_meeting_record`；目前該樣板無 host） | 整合擴展 |
| 4 | **🟢 CONTRIBUTING.md + 程式風格指南**（Phase 0 最後 5%）| 非阻塞 |
| 5 | **🟢 lazy_loader / pagination_engine.js 評估清理** | 程式碼 hygiene |
| 6 | **🟢 HarfBuzz 真接 Layout** | CJK 字距 |
| 7 | **🟢 Phase 5 子項按使用量排序** | 進階功能 |

---

**Sprint 22 一句話總結**：Sprint 21 把 mixin 從「無人引用」翻成「1 個 model 引用」，Sprint 22 把它擴成「4 個 model 引用」+ 修兩個 ChienYi 既有不一致（slip_id required / `_check_slip_state` mismatch），並把 Sprint 21 學到的「`-i` 後 restart」鎖進 SOP。
