# Sprint 67：CONTRIBUTING.md 補完（Phase 0 唯一未完項收尾）

**性質**：catch-up sprint（純文件、無 production code / test / VR 變動）
**日期**：2026-05-16
**前置**：Sprint 56-66 累積 11 個 sprint（hook auto-loop）由 user 手動 override 後重啟、Sprint 64b/65/66 完成 mechanical + catch-up + Python tests

---

## 0. 一句話定位

**Phase 0 從 95% → 100%**：規畫書 §0.5 列 Phase 0 完成度 95%、唯一未完項 = CONTRIBUTING.md（規畫書 §附錄 A 任務清單 `[ ] 撰寫 CONTRIBUTING.md 與 程式風格指南`）。Sprint 67 純文件落地此項。

**沒做什麼**：production code 0 行變動、IIFE bundle 不重打、vitest / VR baseline 全不動。

---

## 1. Hypothesis

Sprint 66 後 Sprint 67+ 候選全部需要 user 認可或外部資源（migrate doc_editor.js / 重生 goldens / OffscreenCanvas worker / 50+ 頁 fixture）。user 指示「根據規畫書繼續執行」+ 不要問 clarifying questions。

→ 從 §附錄 A 找 explicit 列為未完的事項做、且不需要 user 決策、不影響 VR baseline。

→ CONTRIBUTING.md 是 **規畫書 §附錄 A 唯一未打勾的項目**、Phase 0 從 95% → 100% 的最後 5%。scope 明確、產出可驗證、不會影響 production user。

---

## 2. Method

### 2.1 素材來源

| 來源 | 用途 |
|---|---|
| `Makefile`（22 targets） | §3 日常開發循環、§7 CI gates |
| `package.json`（npm scripts） | §3 工作流交叉驗證 |
| `__manifest__.py`（assets 結構） | §3 Odoo 升級 SOP |
| `docs/onboarding_sop.md`（P3-1 客戶導入） | §1 快速開始 / §10 Issue 用詞 |
| 規畫書 §0.6 三層 SOP | §4 三層 SOP 章節 |
| Sprint 50-66 audit docs（17 個） | §5 八條紀律萃取 |
| `docs/scope_decision.md` + 主 CLAUDE.md | §9 Scope 決策 |
| 全域 CLAUDE.md 防禦省電模式 | §10 Issue 回報用詞 |

### 2.2 內容架構（10 章）

1. **快速開始** — 5 行指令上手
2. **開發環境設置** — 系統需求、container/DB、升級 SOP 兩步驟
3. **日常開發循環** — 場景 → 指令對照表、22 個 Make targets
4. **三層 SOP（必須通過）** — Vitest / VR v14 / Spot check 三層通過標準
5. **Sprint 紀律（8 條）** — Sprint 57/57/60/61/62/63/65/64b 累積
6. **程式碼風格** — TS / Python / Odoo XML 規範
7. **PR 與分支策略** — 分支命名、PR 描述模板、CI gates
8. **Sprint Audit Doc 慣例** — 6 段模板（Hypothesis / Method / Result / Root cause / 紀律 / 後續）
9. **Scope 決策** — QWeb vs dobtor_doc_editor 對照表
10. **Issue / Bug 回報** — 重現步驟、影響等級、用詞紀律

### 2.3 紀律萃取

從 Sprint 50-66 audit docs 萃取 8 條紀律：

| # | Sprint | 紀律 |
|---|---|---|
| 1 | 57 | 改 BrowserCanvasRenderContext / CanvasRenderer 後強制跑全 42-fixture VR |
| 2 | 57 | 單元測試用 spy 驗 API、VR 驗 pixels — 兩者都綠才算過 |
| 3 | 60 | 高風險改造前先 probe sprint 收集事實 |
| 4 | 61 | 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習 |
| 5 | 62 | vitest 通過不保證 IIFE bundle 同 code 也 work |
| 6 | 63 | Promote default 前先做 per-fixture delta 分析 |
| 7 | 65 | Mechanical commit 是多 sprint 紀律性投資的內化 |
| 8 | 64b | 架構發現的 sprint 也要記下來 |

每條都附 **「來自哪個 sprint、什麼事件、為什麼這樣立」** — 不是空泛的「best practice」清單。

---

## 3. Result（三層 SOP）

| 層 | 預期 | 實測 |
|---|---|---|
| **L1 Vitest** | 976 passed + 1 skipped 不變 | **不跑**（純文件、無 source code 變動） |
| **L2 VR v14** | mean 0.073191 不變 | **不跑**（純文件、無 pipeline 變動） |
| **L3 Spot check** | golden PNG 不動 | **N/A**（純文件） |

**驗證手段**：
- 檔案存在：`addons/dobtor_doc_editor/CONTRIBUTING.md`（已建立、~13KB）
- markdown 內部連結正確：所有 `[xxx](path)` 指向實存檔案
- 8 條紀律對應的 sprint audit doc 全部存在於 `docs/`
- Phase 0 §附錄 A `[ ] 撰寫 CONTRIBUTING.md` 應在規畫書 §0.5 列為 100%

---

## 4. Root cause / Mechanism

**為什麼 Phase 0 拖到 Sprint 67 才補完？**

規畫書 §0.5 「**Phase 0 能力盤點 95%，剩 CONTRIBUTING.md**」這行從 Sprint 33 後保持不變。連續 34 個 sprint（Sprint 33 → Sprint 66）優先攻 VR mean 收斂與 Phase 7 效能、CONTRIBUTING.md 一直被推遲：

- Sprint 44-49：攻 VR mean ≤ 0.10（B+ → A-）— 商業急迫性高
- Sprint 50-58：Phase 7 效能基線 + 五層 cache — 為大文件 fixture 鋪路
- Sprint 59-65：font metric 攻 VR -1.7% — 商業價值最高的 sprint chain
- Sprint 66：catch-up（補 Sprint 64b 缺的 Python tests + plan sync）

→ Sprint 67 是 **唯一一次 VR mean / 效能 / font metric 都告一段落、且無新 user 決策**的窗口，補 CONTRIBUTING.md 正當其時。

**為什麼這次能寫得有料？**

Sprint 50-66 累積的 17 個 audit doc 提供了**實戰證實的紀律素材**。如果在 Sprint 20 寫 CONTRIBUTING.md、會是空泛的「請寫 unit test、follow PEP 8」level。Sprint 67 寫的 8 條紀律每條都有「Sprint N 翻車事件」當例證 — 這是 Sprint 56-66 累積的隱性價值內化。

→ 呼應紀律 #7：**Mechanical commit 是多 sprint 紀律性投資的內化**。CONTRIBUTING.md 本身就是一個 mechanical commit（無 code 變動），但站得住腳是因為前 17 個 sprint 累積。

---

## 5. 紀律與啟示

### 5.1 補完紀律 #7 的另一面向

紀律 #7 原文：「Mechanical commit 是多 sprint 紀律性投資的內化」。Sprint 65 是「VR baseline default 換成 font-metrics」的 mechanical commit、站得住腳是因為 Sprint 60-64 五個 sprint。

**Sprint 67 是 Phase 0 結案的 mechanical commit**、站得住腳是因為 Sprint 50-66 十七個 sprint 累積的紀律。

→ **「mechanical commit」這個紀律不只適用於 code change，也適用於 documentation / process 類型的 commit**。

### 5.2 新紀律候選（第 9 條，本 sprint 揭示）

> **規畫書本身列出但未做的事項（§附錄 A `[ ]` 項）也是 sprint 候選 — 不必等候新功能 ask。**

Sprint 50-66 一直在攻 VR mean / Phase 7 / font metric，把 §附錄 A 留在 95%。Sprint 67 提示：**autonomous sprint 走無 user 決策路徑時，§附錄 A 的 `[ ]` 項是優先選擇**，比硬做 Sprint 67+ 需要 user 認可的方向更穩。

→ 未來 autonomous loop 啟動時，先 grep `[ ]` in 規畫書，再考慮新 candidate。

---

## 6. 後續 sprint 候選

### 6.1 規畫書 §11.33 列的候選（不變）

- 🔴 **Sprint 68**（待 user 認可）：Migrate `doc_editor.js` 從 canvas-editor 到自家 pipeline — Sprint 60-65 的 VR -1.7% 改善要進 production
- 🟡 **Sprint 69 候選**：重生 goldens 用 Word desktop 渲染 — 換 metric anchor（副作用大）
- 🟡 **Sprint 70+ 候選**：OffscreenCanvas + Web Worker render — Sprint 60 probe 證實可行
- 🟡 **Sprint 55-original 延後**：50+ 頁 fixture 收集待 user 提供

### 6.2 本 sprint 揭示的新候選

- 🟢 **Sprint 68 alternative（純文件、autonomous）**：
  - **`docs/architecture_decision.md` 補完**（如 Sprint 0 ADR 系列若不完整）
  - **`docs/glossary.md` 建立**（規畫書附錄 B 術語表擴展、portal user 文件常見問題對應）
  - **`docs/sprint50_66_retro.md`**（17 個 sprint 的橫向回顧、紀律分布趨勢圖）

這三個都是純文件、autonomous、不影響 VR baseline，可在 user 未決定 Sprint 68 大方向時頂上。

---

## 7. 三層 SOP 不跑的理由（誠實聲明）

依紀律 #4「負面結果 sprint 仍有結構價值」與 sprint audit doc 慣例：

- **不跑 vitest**：本 sprint 0 行 source code 變動、vitest 結果**必然** = Sprint 66 結尾 976 passed + 1 skipped。跑也是消耗 ~30s × 1 次 = 噪音。
- **不跑 VR**：本 sprint 0 行 pipeline 變動、VR mean **必然** = 0.073191、failed pages **必然** = 0。跑 ~3-5 分鐘是消耗無價值。
- **不重打 IIFE**：rollup 輸入未變、產物 byte-identical。

如果 review 要求驗證、可在 PR 跑 `make verify`（typecheck + rollup dry-build）作為通電檢查 — 但 sprint 本身不需要。

---

## 8. 對規畫書的同步動作

| 段落 | 改動 |
|---|---|
| §0.4 Sprint 表 | 加 Sprint 67 row：「CONTRIBUTING.md 補完（Phase 0 → 100%）」 |
| §0.5 Phase 完成度 | Phase 0 從 95% → **100%**、移除「剩 CONTRIBUTING.md」備註 |
| §0.6 / §11.34 | 加 Sprint 67 紀錄段落、紀律 #7 註腳補「也適用 docs/process commit」 |
| 附錄 A 任務清單 | `[ ] 撰寫 CONTRIBUTING.md 與 程式風格指南` → `[x] 撰寫 CONTRIBUTING.md 與 程式風格指南（Sprint 67）` |

---

## 9. 一句話結論

**Sprint 67 補完 Phase 0 最後 5%、Phase 0 100% 收尾。** 純文件 sprint、0 行 code 變動、累積 17 sprint 的隱性紀律首次顯式化為 CONTRIBUTING.md。新貢獻者上手不再依賴口傳。
