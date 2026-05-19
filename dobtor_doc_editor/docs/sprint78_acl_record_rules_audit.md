# Sprint 78：security/ ACL + record rules audit

**性質**：純診斷（紀律 #11 應用到 ACL 層）
**日期**：2026-05-16

## 0. 一句話

Sprint 70-77 audit filesystem 暴露面；Sprint 78 audit ACL / record rule 暴露面。發現 2 個 gap：
- error_log / perf_metric 無 user-isolation rule（log 偽造風險、low-medium）
- doc.document portal rule 無 company 限制（cross-company leak 風險、medium、需 user 認可）

## 1. Method

### 1.1 grep & read

| 檔案 | 內容 |
|---|---|
| `security/ir.model.access.csv` | 17 個 ACL 條目（8 model × 3 group 部分覆蓋）|
| `security/doc_security.xml` | 4 個 ir.rule |
| `security/doc_groups.xml` | group 定義 |

### 1.2 ACL matrix

| Model | Editor | Manager | Portal | base.group_user |
|---|---|---|---|---|
| doc.document | R/W/C | R/W/C/U | R/W | - |
| doc.template | R | R/W/C/U | R | - |
| doc.render.mixin | - | - | R | R |
| doc.sanitizer | - | - | - | R |
| doc.field.picker.wizard | R/W/C/U | - | - | - |
| **doc.editor.error.log** | **-/W/C/-** | R/W/C/U | **-/W/C/-** | -/W/C/- |
| **doc.editor.perf.metric** | **-/W/C/-** | R/W/C/U | **-/W/C/-** | -/W/C/- |
| doc.bulk.import.wizard | - | R/W/C/U | - | - |

### 1.3 4 個 ir.rule

| Rule | Scope | Group |
|---|---|---|
| `rule_doc_document_owner_or_collab` | `create_uid=user.id OR collaborator_ids in user.id` | group_doc_editor |
| `rule_doc_document_manager_all` | `1=1` | group_doc_manager |
| `rule_doc_document_company` | `company_id in company_ids` | group_doc_editor **only** |
| `rule_doc_document_portal` | `collaborator_ids in user.id` | group_doc_portal |

## 2. Findings

### 2.1 ✓ doc.document 主流程設計乾淨

- editor 只看自己建/被邀的 + company 隔離（rule 1 + rule 3 AND）
- manager 全存取（rule 2）
- portal 只看被邀的（rule 4）

### 2.2 ⚠️ Finding A：error_log / perf_metric 無 user-isolation rule（low-medium）

`doc.editor.error.log` ACL = W/C only（no R）給所有 user/portal。**沒有 record rule 限 `('create_uid','=',user.id)`**。

風險：
- portal user 可以寫 `error_log` 裡 `user_id = <某 internal user>`（偽造 user_id）→ audit trail 被污染
- portal user 可以大量寫 log → DB 膨脹（DoS 弱 surface）

**Severity 評估**：low-medium
- 沒有 R → 無 info leak
- 偽造 user_id 需要知道 internal user id（externally guessable from URL / partner records）
- DB 膨脹有 rate-limit / Odoo quota 緩衝

**修法**（Sprint 79 候選、autonomous）：
```xml
<record id="rule_error_log_self" model="ir.rule">
    <field name="name">error_log: 只能寫自己的</field>
    <field name="model_id" ref="model_doc_editor_error_log"/>
    <field name="domain_force">[('create_uid', '=', user.id)]</field>
    <field name="groups" eval="[(4, ref('base.group_user')),
                                (4, ref('group_doc_portal'))]"/>
    <field name="perm_read" eval="False"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_create" eval="True"/>
</record>
```

### 2.3 ⚠️ Finding B：doc.document portal rule 無 company 限制（medium，需 user 認可）

`rule_doc_document_portal` (line 51-60) 只限 `collaborator_ids in user.id`、沒加 `('company_id', 'in', company_ids)`。

風險：
- 如果 partner A 在 company X、被加為 company Y 文件的 collaborator → portal user 看到 cross-company 文件
- multi-company 隔離設計被 collaborator_ids 突破

**Severity 評估**：medium
- 取決於 partner.company_id 設定習慣 — ChienYi 多公司架構下、portal partner 通常綁定單一公司、跨公司協作場景不明確
- 如果業務流程 *允許* 跨公司協作（外部承包商跨多家業主），加 company 限制反而 break 功能

→ **需 user 確認業務流程**：跨公司協作是允許還是不允許？再決定是否修。

### 2.4 ✓ 其他 model

- `doc.template` / `doc.field.picker.wizard` / `doc.bulk.import.wizard` 都是 manager-only 或 editor-only、不需 record rule
- `doc.render.mixin` / `doc.sanitizer` 是 helper、無資料、不需

## 3. 紀律啟示

### 3.1 紀律 #11 應用到 ACL 層

紀律 #11 原始 scope = filesystem path。**ACL / record rule 也是「資料存取的 path」**、同樣需 audit。Sprint 78 揭示這個延伸：

- Filesystem: controller 假設 X 路徑存在 → cross-check container
- ACL: controller 假設 user X 只能存 Y → cross-check ir.rule + ir.model.access.csv 是否真的限制
- 兩者都是「**沒明示驗證的 assumption 就是 bug 種子**」

→ 紀律 #11 廣域版（Sprint 77 已揭示）= **任何 X-assumes-Y 都需 cross-check**。Sprint 78 對 ACL 應用。

### 3.2 對「Write-only model」的 audit pattern

`doc.editor.error.log` / `doc.editor.perf.metric` 是 telemetry 寫入 sink。**write-only model 的 audit 重點 = create_uid 偽造 / 大量寫入 DoS**，不是 read leak。

→ 新 audit pattern：每個 W/C-only model 必須驗：
1. record rule 限 create_uid = user.id（防偽造）
2. 有 rate limit / log rotation（防膨脹）

## 4. Result（三層 SOP）

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑 |
| L2 VR | 0.073191 不變 |
| L3 Python lint | N/A |
| L4 grep audit | 17 ACL + 4 rules、2 gap 揭示 |

## 5. 後續 sprint 候選

- 🟢 **Sprint 79 autonomous**：加 error_log / perf_metric user-isolation rule（Finding A）
- 🔴 **Sprint 80+ 需 user 認可**：doc.document portal company rule（Finding B、可能 break 跨公司協作）

## 6. 一句話結論

**Sprint 78 audit 揭示 ACL 2 個 gap**：紀律 #11 從「filesystem」延伸到「access path」、write-only model 的 audit pattern 形成；Finding A autonomous 可修、Finding B 需 user 確認業務流程。
