# Sprint 73：docs/glossary.md 建立

**性質**：autonomous docs sprint
**日期**：2026-05-16
**前置**：Sprint 67 揭示 autonomous docs sprint 候選；Sprint 73 走 glossary

---

## 0. 一句話定位

新貢獻者進來、Sprint audit doc / pull request / sprint retro 散落用語多。Sprint 73 用一份 [docs/glossary.md](glossary.md) 集中：VR 衡量指標 / sprint 紀律（13 條）/ 前端子系統 / 後端整合 / 工具鏈 / 角色權限 / 縮寫 7 大類。

---

## 1. Method

### 1.1 Coverage

7 大段：

| 段 | 範圍 | 條目數 |
|---|---|---|
| VR 與衡量指標 | VR mean / failed pages / goldens / LO anchor / fingerprint / 等 | 11 |
| Sprint 紀律與類型 | 13 條紀律（Sprint 57-72） + 5 種 sprint 類型 + 比例 | 18 |
| 前端子系統與術語 | OOXML Parser / LayoutEngine / CanvasRenderer / 5 種 cache / 衡量單位 | 14 |
| 後端 / Odoo 整合 | doc.document / doc.linked.mixin / doc_zip_guard / `/dobtor/fonts/*` / etc | 11 |
| 工具鏈與 CI | rollup / vitest / pixelmatch / puppeteer / HttpCase / make dev / run_backend_tests.sh | 12 |
| 角色與權限 | group_doc_editor / group_doc_manager / group_doc_portal | 3 |
| 縮寫 | 16 個（ADR / AST / CJK / CRDT / OOXML / etc） | 16 |

合計 **85 個術語**。

### 1.2 與規畫書附錄 B 的關係

規畫書附錄 B 已有「OOXML → canvas-editor 對映表」（12 個 OOXML 元素）— Sprint 73 glossary **不重複**這些、補完規畫書缺的部分（衡量指標 / sprint 紀律 / 工具鏈）。

---

## 2. Result（三層 SOP）

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑（純文件）|
| L2 VR | 0.073191 不變 |
| L3 Python / lint | 不適用（無 code 變動）|
| 文件 sanity | markdown 可讀、85 個術語有 source sprint 對應 |

---

## 3. 紀律與啟示

### 3.1 紀律 #9 第二應用實例

紀律 #9（Sprint 67）：「§附錄 A `[ ]` 項是 autonomous sprint 優先選擇」。Sprint 73 是其延伸 — **autonomous docs sprint 從 audit doc 散落用語中萃取**、同樣不需 user 決策。

### 3.2 紀律 #13 候選的另一面（docs alignment）

Sprint 72 揭示紀律 #13（test 必須定期跑才算 coverage）。Sprint 73 揭示對應的 docs 版本：**glossary 必須定期同步**、否則術語 drift。

→ 紀律 #14 候選：**規畫書 / audit doc / CONTRIBUTING / glossary 必須在每個重要 sprint 之後同步**（mechanical commit 概念延伸）。

---

## 4. 後續 sprint 候選

- Sprint 74：docs/sprint50_66_retro.md
- Sprint 75：docs/architecture_decision.md 補完

---

## 5. 一句話結論

**Sprint 73 把 23 sprint 累積的 85 個術語固化為單一 glossary**：規畫書附錄 B 既有 OOXML 表 + glossary 7 大段、新貢獻者 onboarding 時間從 reading 30 個 audit doc 縮到讀 CONTRIBUTING.md + glossary.md 兩份。
