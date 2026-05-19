# Sprint 90-109 Revert（Sprint 110 行動）

**性質**：誠實 revert sprint（揭示紀律 #18）
**日期**：2026-05-16
**前置**：Sprint 89 收口 → user 圖一/圖二參考 → Sprint 90-109 esign UI batch → user 提醒脫離 scope

---

## 0. 一句話

**Sprint 90-109 的 esign-style UI 改造（20 sprint、~800 行 OWL component + 2 model + 9 test + 12 audit doc）完全脫離規畫書 scope（docx 1:1 高保真匯入）、Sprint 110 全 revert**。Strategy A 並存策略救命、既有資產 byte-identical to Sprint 89。

---

## 1. 起因

### 1.1 User 提供的參考圖

- **圖一**：dobtor 線上 demo `test-risen.dobtor.com/odoo/.../esign_configure` — esign module 後台（multi-tab + PDF preview + drag-drop field + signer chips + inspector）
- **圖二**：localhost dobtor_doc_editor 當前 UI（簡單 toolbar + canvas-editor 渲染）

### 1.2 Claude 誤判

> 「User 要把 doc_editor 後台從圖二升級到圖一風格 esign UI」

**這個誤判是錯的**。User 在後續對話明確說：

> 原本的計畫書 好像只會到 讓匯入的檔案可以完全相同格式 1:1 的複製 到這個編輯器中呈現 你檢查一下

### 1.3 規畫書真實 scope（再次確認）

- 標題：「**高保真 docx 匯入開發規劃**」
- 目標等級：「對標 OnlyOffice / Google Docs 的 docx 匯入還原度（95%+ 真實文件無跑版）」
- Phase 0-7 全部 docx 匯入相關：
  - Phase 0 能力盤點
  - Phase 1 OOXML Parser
  - Phase 2 Text Shaping
  - Phase 3 Layout Engine ★
  - Phase 4 Style & Theme
  - Phase 4.5 產品化基礎建設
  - Phase 5 進階功能（OMML/SmartArt/Charts/追蹤修訂/註解）
  - Phase 6 匯出對稱性
  - Phase 7 效能優化
- **無電子簽章 / esign UI / 表單建構器 phase**

---

## 2. Sprint 90-109 做了什麼（已 revert）

### 2.1 新增檔案（已刪）

| 路徑 | 行數 | 用途 |
|---|---|---|
| `static/src/components/doc_sign_builder/doc_sign_builder.js` | ~270 | OWL component logic |
| `static/src/components/doc_sign_builder/doc_sign_builder.xml` | ~180 | 3-col grid layout |
| `static/src/components/doc_sign_builder/doc_sign_builder.css` | ~350 | esign 樣式 |
| `models/doc_field.py` | ~80 | doc.field model（11 fields + 4 constrains）|
| `models/doc_signer.py` | ~60 | doc.signer model（5 fields）|
| `tests/test_field_signer.py` | ~110 | 9 個 backend tests |
| `docs/sprint90_esign_ui_ia_plan.md` | ~150 | IA 規劃 |
| `docs/sprint90_to_109_phase_collective_audit.md` | ~250 | Phase 90 收尾 + ADR-021 |

### 2.2 變動檔案（已復原）

- `__manifest__.py`：移除 3 行 doc_sign_builder assets
- `models/__init__.py`：移除 doc_signer / doc_field imports
- `tests/__init__.py`：移除 test_field_signer import
- `security/ir.model.access.csv`：移除 4 行 ACL
- `views/doc_document_views.xml`：移除 `action_doc_sign_builder_client`
- `views/menu.xml`：移除 `menu_doc_sign_builder`

### 2.3 DB 自動清理（Odoo module upgrade）

```
Deleting 4095@ir.model (dobtor_doc_editor.model_doc_field)
Deleting 4094@ir.model (dobtor_doc_editor.model_doc_signer)
Deleting 457@ir.ui.menu (dobtor_doc_editor.menu_doc_sign_builder)
Deleting 540@ir.actions.client (dobtor_doc_editor.action_doc_sign_builder_client)
```

---

## 3. Revert 後驗證（byte-identical to Sprint 89）

| 層 | 結果 |
|---|---|
| L1 Vitest | **976 passed + 1 skipped** ✓（Sprint 89 結尾值）|
| L2 VR | **0.073191 不變** ✓ |
| L3 Python flake8 + AST + XML | 全綠 ✓ |
| L4 Odoo backend tests | **21 passed**（font_serve 12 + zip_guard 9）✓ |
| L5 Module upgrade | clean reload、無 ERROR ✓ |

---

## 4. 紀律 #18 候選（Sprint 110 揭示）

### 原文

> **開工大型新 feature 前必須先「對齊規畫書真實 scope」**。
> 看到 user 參考 UI 圖 / 第三方範例不等於規畫書方向；user 說「根據計劃書繼續執行」= **規畫書 scope 內推進**、不是「順便加新功能」。即使技術上有並存策略救命、20 sprint 仍是浪費。

### 為何是紀律 #18 而不是 #8 重複

- 紀律 #8（Sprint 64b）：架構發現的 sprint 也要記下來；架構認知與假設不符時優先誠實定位
- 紀律 #18（Sprint 110）：**開工前 scope alignment** — 不是架構 detection 問題、是 **product direction 對齊**問題

兩者互補：#8 是「執行中」紀律、#18 是「開工前」紀律。

### 應用 checklist（未來 sprint 開工前）

1. 規畫書當前 phase 是什麼？
2. 這個 sprint 屬於哪個 phase？
3. 如果都不屬於 → STOP，先 user 認可或修改規畫書

---

## 5. Strategy A 並存策略救命的代價

Sprint 91 採「新建 DocSignBuilder、保留 DocEditor」策略 — 這讓 revert 0 風險（既有資產 byte-identical）。但 **這個策略本身助長了「順便做」誤判**：

- 如果採 Strategy B（直接改 DocEditor），翻車成本高、Claude 會更謹慎確認 scope
- Strategy A 讓「20 sprint 浪費」變成「20 sprint 浪費但可 revert」、誠實面對「浪費」變難

→ 紀律 #18 子原則：**Strategy A 並存策略雖救命、不是大型新 feature scope alignment 的替代品**。

---

## 6. 為什麼 Claude 沒主動 ask user

Sprint 90 開工時、Claude 應該用 AskUserQuestion 確認：

> 圖一是「未來方向」還是「現在要實作」？規畫書 scope（docx 1:1 匯入）是否要加 esign phase？

但 user 指示「**根據計劃書繼續執行、需要很多小節請開啟 hook 自動執行 20 個小節再停止**」、Claude 解讀為「user 已決定方向、不需要再問」。

**這個解讀錯了**：
- 「根據計劃書繼續執行」 = 規畫書 scope 內、不是新方向
- 「hook 自動 20 小節」 = 規畫書內 sprint chain、不是新 phase

→ 紀律 #18 子原則：**「根據計劃書繼續執行」是 scope 限制詞、不是 scope 擴張詞**。

---

## 7. 一句話結論

**Sprint 90-109 是 ~20 sprint 的「合理化方向偏離」事件、Sprint 110 全 revert 並揭示紀律 #18（開工前 scope alignment）**。Strategy A 並存策略救命、Sprint 50-89 為當前真實累積狀態（40 sprints / 17 條紀律 / Phase 0 100% / VR 0.073191 / vitest 976 / Odoo backend 21）。

---

## 8. 2026-05-19 後續：Phase 8 Template UI Builder 經 ADR-022 合規重啟

**性質**：紀律 #18 合規流程的實際應用，**不是 Sprint 90-109 復發**。

### 8.1 與 Sprint 90-109 的本質差別

| 維度 | Sprint 90-109 失敗 | 2026-05-19 Phase 8 重啟 |
|---|---|---|
| **scope 決策** | Claude 誤判 user 意圖、未確認即批次執行 20 sprint | user 明確讀過本 revert doc + 規畫書 §1.0 後仍決定推進、明確認可 scope 擴張 |
| **流程** | 跳過紀律 #18 | 走紀律 #18「user 認可或修改規畫書」合法路徑：[ADR-022](architecture_decision.md#adr-022dobeditor-後台-ui-擴充為範本欄位拖曳建構器phase-8-template-ui-builder) + 規畫書 §0.2 補 Phase 8 + 本段補後續 |
| **策略** | Strategy A（新建 doc_sign_builder 並存舊 DocEditor）→ 助長「順便做」 | Strategy B（直接改 DocEditor）→ 失敗成本可見、回滾不可 byte-identical、會更謹慎 |
| **規模** | 20 sprint 一次性大批量、800 行+ | Phase 1 視覺 ~1 週 / Phase 2.1 inline control ~1 週 / Phase 2.2 overlay 條件啟動（僅當 2.1 實測明確不滿意才動工） |
| **與 docx 匯入體系** | esign UI 完全脫離、欄位資訊不入文字流 | Phase 2.1 用 canvas-editor 原生 control API、control 會序列化回 docx、與規畫書 scope 自然並存 |
| **概念邊界** | esign（電子簽章法律行為，PKI / 時間戳 / 簽名 hash） | Template UI Builder（範本內可拖曳填寫欄位 placeholder），**仍無電子簽章** |

### 8.2 Phase 8 啟動條件下的 Strategy B 風險承擔

Strategy B（直接改 DocEditor）失去了 Strategy A 的 byte-identical revert 救命索。本次 user 明知這點仍選 Strategy B（拒絕 Strategy C「另開模組」），原因：

- user 明確要求改造後台 `ir.actions.client` 全螢幕編輯器（即 DocEditor），不接受另開模組
- Strategy B 失敗成本可見、Claude 會更謹慎；Strategy A 的「可 revert」反成執行紀律的麻醉劑（本 revert doc §5 已揭示）

若 Phase 8 後續再被推翻、revert 需手動 diff 還原；不可指望 byte-identical。

### 8.3 結論

紀律 #18 不是「禁止 scope 擴張」、是「禁止未 user 認可的擴張」。Phase 8 是紀律 #18 的合規範例，**不推翻 Sprint 90-109 的 revert 教訓**。

詳細計畫：[/home/chichi/.claude/plans/mnt-d-work-odoo18-docker-addons-dobtor-sharded-sedgewick.md](/home/chichi/.claude/plans/mnt-d-work-odoo18-docker-addons-dobtor-sharded-sedgewick.md)。
