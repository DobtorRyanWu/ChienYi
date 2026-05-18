# Sprint 143 — 紀律 #1.b 正式升格 + #1.a/#21/#22 補完同步(docs-only)

**日期**:2026-05-18
**類型**:docs sprint(0 production code、純紀律文件同步)
**規畫書對應**:§6.5 + autonomous_roadmap §後續紀律維護
**前置 sprint**:Sprint 142(C Phase 5 DEFER user GO、紀律 #1.b 候選 v2 第 8 次跨 sprint 驗證可升正式)

---

## Hypothesis(驗證對象)

Sprint 142 audit §後續 D-1 推薦:

> 紀律 #1.b 正式升格(docs-only):跨 8 sprint 驗證已成熟、紀律維護需求

驗證:
1. 紀律 #1.b 候選 v2 是否充分驗證可升正式?
2. CONTRIBUTING.md 是否需同時補完歷史升正(#1.a / #21 / #22)?
3. glossary.md 索引是否需更新?

---

## Method

### 1. Scope 對齊(紀律 #18 + #14.a)

- 紀律 #14.a:「集中索引(CONTRIBUTING / glossary)新紀律確立即更新、不是事後 catch-up」
- 本 sprint = catch-up 補 Sprint 121-142 多次升正未同步的紀律到集中索引
- scope = 純 docs(CONTRIBUTING + glossary + roadmap + 規畫書標頭)、0 production code

### 2. 紀律 #1.b 跨 sprint 驗證總結

| Sprint | 類型 | 結果 |
|---|---|---|
| 110 | 全 revert | esign UI 全 Sprint 90-109 revert byte-identical(第 1 次)|
| 136 | 全 revert | isInTableCell 翻車 revert byte-identical(第 2 次)|
| 137 | 預防 scope-down | probe 確認 mapper wire-up 破 VR、scope down 到「純函式新模組」(第 3 次)|
| 138 | 實作(probe 確認可行)| mapper wire-up 安全(VR 不走 mapper)、實作完成(第 4 次)|
| 139 | Strategy C 折衷 | layout wire-up + VR opt-in、保 baseline byte-identical 同時完成 wire-up(第 5 次)|
| 140 | 預防 DEFER | A 候選 textAlignment/framePr scope-down 100%(第 6 次)|
| 141 | 預防 DEFER user GO | B 候選階段 C 重生 goldens、autonomous 邊界揭示(第 7 次)|
| 142 | 預防 DEFER user GO | C 候選 Phase 5 fixture 0 覆蓋(第 8 次)|

**3 類型完整光譜**:
- 全 revert × 2(Sprint 110、136)
- 預防 scope-down × 4(Sprint 137、140、141、142)
- 實作 / 折衷 × 2(Sprint 138、139)

**「需 user GO 的預防 DEFER」次類型 × 3**(Sprint 141、142 + Sprint 140 雖 autonomous DEFER 但仍可 user GO trigger)

### 3. 文件更新範圍

#### 3.1 CONTRIBUTING.md(§5 Sprint 紀律段)

補完 4 條紀律(從 #18 後接續):
- **#1.a**(Sprint 123 升正、含 Sprint 138 子原則):parser/style/layout 任一層變動跑全 VR
- **#21**(Sprint 131 升正):optional 欄位空集合不掛 key
- **#22**(Sprint 135 升正、第 9 次應用 Sprint 142):probe sprint 確認 mental model
- **#1.b**(本 sprint 升正):spike 後遇結構性問題、scope-down 或完整 revert

#### 3.2 glossary.md(§2.1 紀律表)

- §0 索引:「紀律 18 條 + 6 子 + 1 候選」→ **「紀律 22 條 + 6 子 + 1 候選」**(Sprint 143 升正 4 條)
- 紀律表加 #1.a / #1.b 在 #1 之下(視覺對齊)
- 紀律表加 #21 / #22 在 #20 候選之後

#### 3.3 autonomous_roadmap.md

Sprint 143 ✅ docs sprint(紀律升正完工)、更新進度追蹤表

#### 3.4 規畫書 §0.1 標頭

最後更新時間 + Sprint 143 註記

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**(0 code、誠實聲明、純 docs)|
| L2 VR v14 | **跳過**(同上)|
| L3 Spot check | 紀律文件 grep 對齊驗證(CONTRIBUTING / glossary 兩處)|
| L4 Odoo backend | **跳過** |

---

## Result

### 紀律總數變動

| 維度 | 起點(Sprint 142)| 終點(Sprint 143)|
|---|---|---|
| 正式紀律 | 18 條 | **22 條**(+4: #1.a / #21 / #22 / #1.b)|
| 子原則 | 6 條 | 6 條(未變)|
| 候選 | 1 條(#20)| 1 條(未變)|

註:autonomous_roadmap 中提到的紀律總數(Sprint 131「19→20 條」/ Sprint 135「20→21 條」)是 roadmap-local 計數、與 CONTRIBUTING/glossary 集中索引不同步、本 sprint 統一對齊到 **22 條**。

### Sprint 143 產出

| 產出 | 變動 |
|---|---|
| `CONTRIBUTING.md` | +~80 行(§5 加 4 條紀律)|
| `docs/glossary.md` | +3 行(§2.1 紀律表加 #1.a/#1.b/#21/#22、§0 索引總數 18→22)|
| `docs/autonomous_roadmap.md` | Sprint 143 ✅ |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 |
| `docs/sprint143_discipline_1b_promote.md` | 本 audit doc |

### 紀律 #1.b 正式定義(摘自 CONTRIBUTING.md)

```
紀律 #1.b(Sprint 143 升正):
  Spike 後遇結構性問題、必須 scope-down 或完整 revert byte-identical、
  不嘗試「微調 + retry」(避免 fitting noise)。

  操作原則:
  1. 不堆 hack:fitting noise 風險高(Sprint 136 教訓)
  2. scope-down 維度可大可小:
     - 全 revert(100%)= Sprint 110/136 模式
     - 部分 revert(1 維度)= Sprint 139 Strategy C 模式
     - 預防 DEFER(probe 階段 100%)= Sprint 137/140/141/142 模式
  3. 若 scope-down 跨 autonomous 決策邊界(換 baseline / 大依賴 / user 業務優先)
     → probe-only sprint + DEFER user GO + 完整推薦路徑 ready
```

---

## 紀律

### 紀律 #14 + #14.a 應用(catch-up 同步)

> docs / audit / ADR / glossary 必須即時同步(不是事後 catch-up)
> 14.a 集中索引(CONTRIBUTING / glossary)新紀律確立即更新

本 sprint 是 #14.a 的**反例 catch-up**:Sprint 121-142 共 22 個 sprint 內升正 4 條紀律未即時同步到集中索引、本 sprint 補做。

→ 教訓:當紀律升正在 autonomous_roadmap 進度表中宣告時、應同 sprint 更新 CONTRIBUTING / glossary,而非延後到下個專屬 docs sprint。

### 紀律 #18 守護(docs-only sprint scope-down)

本 sprint scope = 純紀律維護、不混入其他工作(如 cluster retro 或新 feature scope assessment)。即使是 docs sprint 也守 PR-size 紀律。

---

## 後續

### Sprint 144 候選(autonomous 推薦)

| 候選 | 預期 | 理由 |
|---|---|---|
| D-2. Sprint 121-142 cluster retro(autonomous docs sprint)| 1 sprint docs-only | 沿用 Sprint 120 retro 模式、整理 22 sprint 累積方法論 |
| D-3. 等 user 決策(階段 C / Phase 5 / textAlignment GO 三選一)| 0 sprint | session 自然停止點 |
| E. autonomous 找其他規畫書 §11.2 backlog | 待 probe | scope 不確定 |

**autonomous 推薦 D-2 cluster retro**(若 user 不主動指示):
- 沿用 Sprint 120 retro 模式
- Sprint 121-142 共 22 個 sprint 累積:5 條紀律升正 / numbering wire-up 3-sprint cluster / abc 三連 probe / Strategy C 折衷 / VR byte-identical 16 連
- 整理為下個 cluster 開工前的「方法論 catch-up」

或等 user 決策(session 自然停止點)。

---

## Sprint 143 結尾累積指標

- vitest **1176 passed + 1 skipped**(未動、純 docs)
- VR mean **0.073191** / failed 0 / compared 126(未動、**第 15 次連續 byte-identical 維持**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 4 Style **90%**(未變)
- 22 ADR / 紀律 **22 條** + 6 子 + **1 候選**(#20 集中索引、#1.b 候選升正完成)
- Sprint audit doc 142 → **143**

---

## File-level summary

```
M  addons/dobtor_doc_editor/CONTRIBUTING.md  (+~80 行:§5 補 #1.a / #21 / #22 / #1.b)
M  addons/dobtor_doc_editor/docs/glossary.md  (+3 行:§2.1 + §0 索引、紀律 18→22)
A  addons/dobtor_doc_editor/docs/sprint143_discipline_1b_promote.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 143 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

**淨 production code 變動 = 0**(pure docs)、紀律總數正式從 **18 → 22 條**(catch-up Sprint 121-142 期間 4 次升正)、紀律 #1.b 正式定義完成、後續 cluster retro 候選 ready。
