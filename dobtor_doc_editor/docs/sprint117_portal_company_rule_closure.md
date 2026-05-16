# Sprint 117 — Sprint 78 Finding B 收口：doc.document portal company rule

**日期**：2026-05-17
**類型**：autonomous decision + lock-in test（roadmap 階段 A 行 4）
**規畫書對應**：§11.1 行 5（Sprint 78 Finding B）
**Sprint 116 後接手**：i18n 補完 + null byte fix 已落地、轉入廣域 audit 候選

---

## Hypothesis

Sprint 78 audit 揭示 Finding B：`rule_doc_document_portal` 只過濾 `collaborator_ids in user.id`、**沒有**搭配 `company_id in company_ids` 過濾，而 internal editor 的 `rule_doc_document_company` 有。形成不對稱：

- group_doc_editor：rule 1（owner / collab）AND rule 3（company）→ company-isolated
- group_doc_portal：rule 4（collab only）→ 跨公司可讀寫

Sprint 78 audit 評估為「medium 嚴重度、需 user 認可」。Sprint 117 作為 autonomous 範圍 enforce 收口：**讀 group 設計意圖 → 決定保留 / 加 filter → 加 lock-in test 防回歸**。

---

## Method

### 1. Scope 對齊（紀律 #18）

- roadmap 階段 A 行 4：「Sprint 78 Finding B portal company rule audit 收口」
- SOP 列「backend test + ir.rule check」
- User 已授權 §11.1 候選 Claude 自主決策（autonomous_roadmap.md §授權範圍）
- 不打 production code 主幹、只動 security + test + docs（紀律 #18 PR-size 內）

### 2. 設計意圖溯源

Read `security/doc_groups.xml` `group_doc_portal` 註解原文：

> **設計目的：讓 ChienYi 承包商 / 業主代表能線上編輯被授權的文件**

ChienYi 系統內：
- 監造公司 = 文件 author / company_id
- 承包商 / 業主代表 = portal collaborator、**屬於不同公司**

→ Sprint 78 Finding B 描述的「cross-company 風險」**正是此模組的目標流程**。
若加 `company_id in company_ids` 過濾、會直接 break 承包商跨公司編輯。

### 3. Autonomous 決策

**決策：保留現狀（不加 company filter）、加 lock-in test 鎖定設計、文件化 trade-off**。

理由：

| 選項 | 收益 | 代價 |
|---|---|---|
| A. 加 company filter | 對稱、default-secure、portal 不可跨公司 leak | 破壞 ChienYi 承包商 / 業主代表跨公司編輯流程；admin 須改為每個 portal user 加多 company_ids，操作繁瑣 |
| **B. 保留 + lock-in test + 文件化** | 設計意圖明示、未來不會誤改、tests fail 會逼讀 rationale | 仍依賴 admin 不誤邀 cross-company portal user（操作層風險、非安全邊界 bug） |

選 B。Hypothesis：admin 誤邀風險屬「業務流程紀律」，不是「access control 漏洞」；`collaborator_ids` 是 explicit access grant、足以承擔授權邊界。若未來 ChienYi 業務改為「跨公司協作 disallow by default」，本決策可逆（加回 filter + 改 lock-in test 為反向）。

### 4. 實作

#### 4.1 `security/doc_security.xml`

在 `rule_doc_document_portal` 前面的註解區塊加 Sprint 117 段：

```
Sprint 117 — Sprint 78 Finding B 收口（cross-company 設計決策）：
本 rule 刻意「不加」 company_id in company_ids 過濾、與
rule_doc_document_company（only 給 group_doc_editor）形成不對稱。
理由：group_doc_portal 設計目的（見 doc_groups.xml）= 讓 ChienYi
承包商 / 業主代表跨公司編輯被授權的文件。承包商通常屬於自家公司、
被監造公司（不同公司）邀請為 collaborator 才看得到該文件。
若加 company 過濾、會 break 此跨公司協作流程。
collaborator_ids 本身就是 explicit access grant、足以承擔授權邊界。
測試見 tests/test_security.py 的 cross_company_invited 系列、
審計紀錄見 docs/sprint117_portal_company_rule_closure.md。
```

不動 rule 本體（domain_force / groups / perm_*），只擴註解。

#### 4.2 `tests/test_security.py`

新增 `TestPortalCrossCompanyCollaboration`（4 tests）：

| Test | 鎖定行為 |
|---|---|
| `test_portal_can_read_cross_company_invited_doc` | portal user（承包商公司）讀被邀的監造公司文件 ✅ |
| `test_portal_can_write_cross_company_invited_doc` | portal user 寫被邀的跨公司文件 ✅ |
| `test_portal_cannot_read_uninvited_cross_company_doc` | sanity：沒邀就讀不到、collaborator_ids 仍是必要邊界 |
| `test_portal_search_includes_cross_company_invited` | search 不帶 domain 時、跨公司受邀文件出現在結果 |

Setup 建兩家 res.company（監造 + 承包商）、各自 user，把承包商 portal user 加為監造文件 collaborator。

防回歸機制：test_can_read 的 assertion message 寫「若 fail 請先讀 sprint117 audit」、強迫加 company filter 的人面對 trade-off。

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**（0 行 frontend / source code 變動、必然 = 976+1）|
| L2 VR v14 | **跳過**（0 行 pipeline / fixture 變動、必然 = 0.073191）|
| L3 Spot check | ✅ `xmllint --noout` PASS / strict flake8 (E9/F63/F7/F82) PASS / `ast.parse` PASS |
| L4 Odoo backend test | ✅ **10/10 passed**（`TestPortalSecurity` 6 + `TestPortalCrossCompanyCollaboration` 4，10.34s）|
| L5 Module upgrade | ✅ Registry loaded in 12.433s、無 rule 載入錯誤 |

L4 完整指令：
```
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  --test-tags=/dobtor_doc_editor:TestPortalSecurity,/dobtor_doc_editor:TestPortalCrossCompanyCollaboration \
  --stop-after-init --http-port=8169
```

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `security/doc_security.xml` | +11 行（純註解、rule 本體不動）| 設計決策永久化、Sprint 78 Finding B 收口 |
| `tests/test_security.py` | +94 行 / 1 新 class / 4 新 test | Lock-in cross-company collaboration |
| `docs/sprint117_portal_company_rule_closure.md` | 本 audit doc | 紀錄 autonomous 決策 rationale |
| `docs/autonomous_roadmap.md` | 階段 A 行 4 ⏳→✅ + 進度表 + Sprint 117 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

### Test 數變動

- Sprint 116 結尾：Odoo backend local **27 passed**（font_serve 12 + zip_guard 9 + controller boundary 6）
- Sprint 117 結尾：Odoo backend local **31 passed**（+ TestPortalCrossCompanyCollaboration 4；TestPortalSecurity 6 既有未計入 sprint count，本 sprint 一併重跑確認綠）
- 真實變動：+1 test class、+4 test、ir.rule 本體 0 change

### 規畫書 §0.2 Phase 完成度

無變動（本 sprint 屬產品化 / security 邊界 lock-in、不打 Phase 1-7 主軸）。

---

## Root cause

**為什麼 Sprint 78 Finding B 留到 Sprint 117 才收口**：

1. Sprint 78 audit 明確標「需 user 確認業務流程」、屬 §11.1「待 user 決策」
2. Sprint 79-89 autonomous batch focus 在無爭議 fix（Finding A 寫入隔離）
3. Sprint 113 roadmap 把 Finding B 安排在階段 A 行 4、確認可 autonomous 決策（讀 group_doc_portal 設計意圖即可決）
4. Sprint 117 真正讀 group_doc_portal 註解的「ChienYi 承包商 / 業主代表」設計目的 → 確認保留是正解

**為什麼 lock-in test 是必要的**：

- Sprint 78 是「audit-only」、發現 gap 但沒鎖定行為
- 無 test 時、未來「security review」型 sprint 可能直覺加 company filter、無聲 break 業務流程
- Lock-in test 強制 fail-loud、配合 audit doc 形成 trade-off 文件鏈

---

## 紀律

### 紀律 #18 子原則（Sprint 117 揭示）

> **「待 user 決策」候選的 autonomous 收口、必須讀原始設計意圖（group 註解、模組目的、業務脈絡）後才下決定，不能憑「default-secure 直覺」加邊界**。
>
> **Why**：Sprint 117 若 default-secure 加 company filter、會 break group_doc_portal 註解明示的設計目的（承包商跨公司編輯）。設計意圖在 source code comment 裡、不在 audit doc 裡。
>
> **How to apply**：
> - 對 §11.1 候選做 autonomous 決策前、grep 該功能相關的 group / model / view 註解
> - 決策方向若與既有註解衝突、必須在 audit doc 明示「為什麼覆蓋既有設計」
> - 不覆蓋既有設計時、加 lock-in test 防未來「security review」誤改

### 紀律 #15 廣域應用持續（Sprint 117）

紀律 #15「security 邊界 test 廣域應用」在 Sprint 117 從「補 missing test」延伸為 **lock-in existing-by-design behavior**。Cross-company collaboration 是「by design 行為」、非 missing security；test 用於防回歸、不是修 bug。

---

## 後續

### Sprint 118（roadmap 階段 A 行 5）

`architecture_decision.md` 補完：規畫書 §3 對映 + ADR 20 個彙整（純 docs）。Sprint 117 本身也應列為新 ADR：「ADR-21：portal cross-company collaboration by collaborator_ids，不加 company filter」（在 Sprint 118 統一整入）。

### Sprint 117+ 候選（本 sprint 揭示延伸）

- 若未來 ChienYi 改為「跨公司協作 disallow by default」、需逆轉本決策：移除 lock-in test 的 can_read_cross_company assertion、加 company filter 進 rule、寫 Sprint NN_portal_company_rule_reversal.md
- grep `group_doc_portal` 使用點、確認 controller 層沒有額外的 cross-company 假設衝突（initial scan：`doc_controller.py` 對 portal user 只走 ACL + record rule、無 company 額外 check）

---

## Sprint 117 結尾累積指標

- vitest 976 + 1 skipped（未跑、必然一致）
- VR mean 0.073191（未跑、必然一致）
- Odoo backend local **31 passed**（+4 cross-company lock-in；含 TestPortalSecurity 6 + Cross-company 4 + font_serve 12 + zip_guard 9）
- CI gate v1 12 passed（font_serve、未動）
- Phase 0 100% / Phase 3 93% / 20 ADR（Sprint 118 將升至 21）/ **18 條紀律 + 6 子原則**（+ #18 子 Sprint 117 read-design-intent-first）
- Sprint audit doc 數 116 → **117**
- Security rule 變動：**0**（純註解 + lock-in test）

---

## File-level summary

```
M  addons/dobtor_doc_editor/security/doc_security.xml  (+11 行 註解，rule 本體不動)
M  addons/dobtor_doc_editor/tests/test_security.py  (+94 行，TestPortalCrossCompanyCollaboration × 4)
A  addons/dobtor_doc_editor/docs/sprint117_portal_company_rule_closure.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 A 行 4 ⏳→✅ + 進度表 Sprint 117)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

無 VR fixture 變動、無 model schema 變動、無 ACL CSV 變動、無 controller / Python 邏輯變動。
