# Sprint 111：CONTRIBUTING.md + glossary.md 紀律同步（Sprint 110 後）

**性質**：catch-up（紀律 #14 應用 — docs 即時同步）
**日期**：2026-05-16
**前置**：Sprint 110 revert + 規畫書清理 → 揭示 CONTRIBUTING.md 與 glossary.md 紀律列表停在 Sprint 67 era（只到 #1-8）

---

## 0. 一句話

清理規劃時揭示 [CONTRIBUTING.md](../CONTRIBUTING.md) §5 紀律列表是 Sprint 67 寫的、只到 #1-#8；[glossary.md](glossary.md) §2.1 是 Sprint 73 寫的、到 #1-#13。Sprint 68-83 + Sprint 110 衍生的紀律 #9-#18 沒同步進去。**紀律 #14（docs 即時同步）的自身應用**。

## 1. Method

### 1.1 CONTRIBUTING.md §5 補完

| 之前 | 之後 |
|---|---|
| 紀律 #1-#8（Sprint 67 寫）| 紀律 #1-#18（含 #11.a / #11.b 子原則 + #18.a / #18.b）|
| 健康紀律分布 Sprint 50-66 | 健康紀律分布 Sprint 50-89（Sprint 90-109 已 revert 不計入）|

每條紀律附 Sprint 來源 + 一句話原文 + 應用提示。

### 1.2 glossary.md §2.1 補完

| 之前 | 之後 |
|---|---|
| 「8 + 3 條紀律（Sprint 50-72）」 | 「17 條紀律（Sprint 50-89 + Sprint 110）」 |
| 13 row（含 1 候選）| 22 row（含 5 候選 + 1 已回收 + 18.a/18.b 子原則）|

### 1.3 §2.2 Sprint 類型表更新

從「Sprint 50-72 比例」改成「Sprint 50-89 比例」、加 Revert 類型 row。

## 2. Result（三層 SOP）

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑（純文件 sprint）|
| L2 VR | 0.073191 不變 |
| L3 Python lint | 不適用 |
| 文件 sanity | markdown 連結正確、紀律編號連續、無斷層 |

## 3. 紀律啟示

### 3.1 紀律 #14 自身應用（meta）

紀律 #14（候選）原文：「docs / audit / ADR / glossary 必須即時同步、不是事後 catch-up」。**Sprint 111 是這條紀律的自身應用** — 同步 docs 不是因為被外部觸發、是發現自己沒同步就先補。

→ 紀律 #14 + 紀律 #10（catch-up 不停最低限度）合用 = catch-up 鏈條應該主動收口、不是等下個 sprint 才被動補。

### 3.2 為何 Sprint 67 / 73 寫完後沒同步紀律 #9+

當時紀律 #1-#8 已穩定、Sprint 68+ 衍生的 #9-#18 是 audit doc 各自寫的、沒回頭更新「集中索引」（CONTRIBUTING.md / glossary.md）。

→ 紀律 #14 子原則（Sprint 111 揭示）：**集中索引（CONTRIBUTING / glossary）必須在新紀律確立時即時更新、不是等多個 sprint 累積後 catch-up**。

## 4. 後續 sprint 候選

Sprint 90+ 真正候選不變（需 user 決策）：
- 🔴 Migrate doc_editor.js
- 🔴 重生 goldens
- 🔴 OffscreenCanvas worker
- 🔴 50+ 頁 fixture
- 🔴 Sprint 78 Finding B
- 🟡 i18n 7 missing translations
- 🟢 autonomous docs sprint 候選大致耗盡

## 5. 一句話結論

**Sprint 111 用紀律 #14 自身應用、把 CONTRIBUTING.md + glossary.md 紀律列表從停在 Sprint 67/73 同步到 Sprint 110**。揭示紀律 #14 子原則：集中索引應即時更新、不是事後 catch-up。Sprint 50-89 + 110 + 111 真實累積：**41 sprints / 17 條紀律（含 5 候選 + 2 子原則）**。
