# Sprint 79：error_log / perf_metric user-isolation record rules

**性質**：code change（security fix、紀律 #11 ACL 延伸）
**日期**：2026-05-16

## 0. 一句話

Sprint 78 Finding A：write-only telemetry sink（`doc.editor.error.log` / `doc.editor.perf.metric`）無 user-isolation rule、portal user 可偽造 `create_uid`。Sprint 79 加 2 個 ir.rule 限 `create_uid = user.id`。

## 1. Method

```xml
<record id="rule_doc_editor_error_log_self_create" model="ir.rule">
    <field name="name">error_log: 只能寫 create_uid = self（防偽造）</field>
    <field name="model_id" ref="model_doc_editor_error_log"/>
    <field name="domain_force">[('create_uid', '=', user.id)]</field>
    <field name="groups" eval="[
        (4, ref('base.group_user')),
        (4, ref('dobtor_doc_editor.group_doc_portal')),
    ]"/>
    <field name="perm_read" eval="False"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_create" eval="True"/>
    <field name="perm_unlink" eval="False"/>
</record>

<record id="rule_doc_editor_perf_metric_self_create" model="ir.rule">
    (相同設計、target model_doc_editor_perf_metric)
</record>
```

**設計重點**：
- `domain_force = [('create_uid', '=', user.id)]` — 用 Odoo ORM 標準 user-isolation pattern
- `groups = [base.group_user, group_doc_portal]` — 涵蓋 internal user 與 portal user
- `manager` 不加 → 不受此 rule 限（manager 仍能跨 user 寫，符合管理員 audit 需求）
- `perm_read=False` 對應 ACL CSV 也是 0R（write-only sink）、rule 主要 enforce write/create

## 2. Result（三層 SOP）

### 2.1 XML validation
```bash
$ xmllint --noout security/doc_security.xml
XML OK
```

### 2.2 Module upgrade

```bash
$ docker exec odoo18 odoo -d odoo18_dev -u dobtor_doc_editor --stop-after-init
...
Modules loaded.
Registry loaded in 10.892s
```

→ 無 record rule 載入錯誤、registry 成功 reload。

### 2.3 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑（純 ACL / security 變動）|
| L2 VR | 0.073191 不變（無 frontend / pipeline 變動）|
| L3 XML / lint | XML well-formed ✓ |
| L4 Odoo module upgrade | ✓ 無錯誤、2 個新 rule 註冊 |
| L5 backend tests（font_serve + zip_guard）| 預期不受影響、Sprint 80 重跑驗證 |

## 3. 紀律啟示

### 3.1 紀律 #11 ACL 應用收口

Sprint 70-77 對 filesystem 應用紀律 #11、Sprint 78 audit ACL、Sprint 79 修 Finding A。**紀律 #11 在 dobtor_doc_editor 內部應用範圍已 explicit 收口**：

| 範圍 | Sprint | 結果 |
|---|---|---|
| Controller filesystem | 69 + 70 | 揭示 + 修 |
| Model filesystem | 76 | clean |
| Wizard filesystem | 76 | clean |
| Dev tool env（Makefile）| 77 | 揭示 |
| ACL / record rule | 78 + 79 | 揭示 + 修 |

Sprint 80+ 可以開始走「Sprint 78 Finding B（需 user 認可）」或新 sprint type。

### 3.2 「Manager 不受 rule 限」是有意設計、不是 gap

manager group 沒在 `groups` 列表 = rule 不適用 manager = manager 仍可跨 user 寫。**這對應 manager 是「telemetry 監控者」角色** — 需要看別人的 log/metric 並潛在修正。

→ 紀律 #11 子原則：**user-isolation rule 的 group scope 必須與 model 業務語意對齊**。

## 4. 後續 sprint 候選

- Sprint 80：跑 backend tests 確認 Sprint 79 rule 沒 break 既有 21 tests
- Sprint 81+：Sprint 78 Finding B（doc.document portal company rule、需 user 認可）
- Sprint 82+：其他 model 是否需 user-isolation（grep `create_uid` 用法）

## 5. 一句話結論

**Sprint 79 加 2 個 ir.rule 把 telemetry write 限到 self**：防 portal user 偽造 create_uid 污染 audit trail、紀律 #11 應用範圍 explicit 收口 5 個 sub-domain。
