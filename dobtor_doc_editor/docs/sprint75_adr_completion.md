# Sprint 75：architecture_decision.md 補完（ADR-013 - ADR-020）

**性質**：autonomous docs sprint（系列補完）
**日期**：2026-05-16

## 0. 一句話

`docs/architecture_decision.md` 已有 ADR-001 - ADR-012（Phase 0-4）、Sprint 50-72 期間衍生的 8 個架構決策**沒有對應 ADR**。Sprint 75 補完 ADR-013 - ADR-020。

## 1. 補的 ADR 列表

| ADR | 對應 Sprint | 主題 |
|---|---|---|
| ADR-013 | Sprint 50 | 轉路線 A（商業化先行 + Phase 7 效能）|
| ADR-014 | Sprint 62 | FontMetricsAdapter 用 LO 系統 fallback fonts |
| ADR-015 | Sprint 64b → 69 | Strategy B portal lazy load + IDB cache（+ Sprint 69 修為 candidate fallback）|
| ADR-016 | Sprint 70 | `fill_template` PDF graceful fallback（紀律 #11 第一應用）|
| ADR-017 | Sprint 71 | `doc_zip_guard.py` 設計上避開 filesystem（紀律 #11 例外）|
| ADR-018 | Sprint 67 | CONTRIBUTING.md 補完（Phase 0 唯一未完項）|
| ADR-019 | Sprint 72 | `run_backend_tests.sh` 統一 21 個 Odoo backend tests |
| ADR-020 | Sprint 73-74 | autonomous docs sprint 範式 |

## 2. 揭示

### 2.1 ADR 與 sprint audit doc 的角色分工

| 文件 | 角色 |
|---|---|
| Sprint audit doc（`sprint<N>_*.md`）| sprint 內部 — hypothesis / method / result / 紀律 |
| ADR（`architecture_decision.md`）| 跨 sprint 的架構決策、長期參考 |

ADR 不是 sprint audit 的重複、是「**這個決策為何成立、影響範圍多大**」的精煉。

### 2.2 ADR 條目的健康節奏

Sprint 0-49（50 sprint）= 12 個 ADR ≈ 1 ADR / 4 sprint
Sprint 50-72（23 sprint）= 8 個 ADR ≈ 1 ADR / 2.9 sprint

→ **Sprint 50-72 ADR 密度比前期高**、反映 hook autonomous loop 的揭示密度。

## 3. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑（純文件）|
| L2 VR | 0.073191 不變 |
| L3 markdown sanity | 8 個 ADR 結構一致（標題 / 背景 / 決策 / 揭示 / 後果）|

## 4. 紀律與啟示

### 4.1 紀律 #14 候選（Sprint 73-75 揭示）

> 規畫書 / audit doc / CONTRIBUTING / glossary / ADR 必須在每個重要 sprint 之後同步、否則文件 drift。

→ Sprint 74 retro 顯示 Sprint 50-72 期間 ADR 漏寫 8 個、回頭補不夠經濟（每個 ADR 都要重讀 audit doc）。**未來 sprint 應該在 audit doc 寫完當下就決定要不要升級為 ADR**、不是事後 catch-up。

## 5. 一句話結論

**Sprint 75 把 Sprint 50-72 期間 8 個架構決策升級為 ADR-013 - ADR-020**、ADR doc 從 957 行 → ~1200 行；揭示紀律 #14 候選（sprint 同步 ADR 應即時、不是 catch-up）。
