# Sprint 120 — sprint50_66_retro.md 方法論萃取 + 階段 A 完成

**日期**：2026-05-17
**類型**：autonomous docs sprint（roadmap 階段 A 行 7 — **階段 A 最後一個 sprint**）
**規畫書對應**：§11.2 行 5

---

## Hypothesis

Sprint 50-66 已有 [sprint50_72_retro.md](sprint50_72_retro.md)（23 sprint 橫向高層數字）但無**方法論萃取**：

- Cache 五連發（Sprint 51-58）為什麼 8 sprint 加 5 cache 而 VR mean 不動還算成功？
- FontMetricsAdapter（Sprint 60-65）為什麼 6 sprint 才命中 -1.7%？這 6 階段是必要的嗎？

Sprint 120 補：寫 [sprint50_66_retro.md](sprint50_66_retro.md) 把兩個 cluster 的**做事方式** explicit、供未來新 cluster 套用。完成後階段 A（Sprint 113-120 共 8 sprint）全部 ✅、進入階段 B。

---

## Method

### 1. Scope 對齊（紀律 #18）

- roadmap 階段 A 行 7：「Sprint 50-66 retro：`sprint50_66_retro.md` 萃取 cache 五連發 + FontMetricsAdapter 學到的方法論」
- 規畫書 §11.2 行 5 autonomous docs sprint
- SOP「docs only」
- 純 docs（紀律 #18 PR-size 內）

### 2. 與既有 sprint50_72_retro.md 區隔

| 文件 | 範圍 | 性質 | 角度 |
|---|---|---|---|
| sprint50_72_retro.md（Sprint 74 落地）| 23 sprint（50-72）| 橫向高層數字 | 收益曲線、test 累積、紀律生成軌跡 |
| **sprint50_66_retro.md（Sprint 120 落地）** | 17 sprint（50-66）| **方法論萃取** | **做事方式、cluster 內部 SOP、未來 cluster 套用 checklist** |

兩文件互補、不重複。新文件聚焦：

1. Cache 五連發方法論（§1）：Stable platform → 高風險改造、Sprint 57 翻車的紀律意義、未來適用條件
2. FontMetricsAdapter 方法論（§2）：Probe → Negative → Positive → Delta → Drift → Promote 6 階段、為什麼剪掉任一階段都有風險、揭示鏈 meta 收益
3. 兩 cluster 互動（§3）：cache stable → 才能歸因 metric
4. 套用到 Sprint 113-118（§4）：方法論跨 cluster 通用驗證
5. 紀律生成總圖（§5）+ 未來 cluster checklist（§6）

### 3. 方法論萃取的判斷標準

「方法論」≠「事件清單」。本 retro 對每個方法論元素回答 3 個問題：

- 是什麼？（define）
- 為什麼這樣做有效？（justify）
- 對未來什麼類型的 cluster 適用 / 不適用？（generalize）

### 4. 階段 A 完成同步

Sprint 113 起 8 sprint（113 / 114 / 115 / 116 / 117 / 118 / 119 / 120）全 ✅、roadmap 階段 A 表全綠。Sprint 120 同步把 roadmap 標 **階段 A 完成、進入階段 B**。

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**（純 docs）|
| L2 VR v14 | **跳過**（純 docs）|
| L3 Spot check | ✅ 17 個 sprint audit doc 名稱對齊（51-58 + 60-65 + 66）/ retro 數據對齊 sprint50_72_retro.md §4.1 §4.2 |
| L4 Odoo backend | **跳過**（純 docs）|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `docs/sprint50_66_retro.md` | +260 行（新檔）| Cache 五連發 + FontMetricsAdapter 方法論萃取 |
| `docs/sprint120_sprint50_66_retro_creation.md` | 本 audit doc | 紀錄萃取方式與階段 A 完成 |
| `docs/autonomous_roadmap.md` | 階段 A 行 7 ⏳→✅ + 進度表 Sprint 120 + 階段 A 完成註記 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新（階段 A 完成）| 同步 |

### 階段 A（Sprint 113-120）完成狀態

| Sprint | 工作 | 狀態 |
|---|---|---|
| 113 | autonomous_roadmap.md 建立 | ✅ |
| 114 | CI 加 backend-tests job + 漸進 gate 模式 | ✅ |
| 115 | doc_controller security boundary 6 HttpCase | ✅ |
| 116 | i18n 7 補完 + null byte sanitize fix | ✅ |
| 117 | Sprint 78 Finding B portal company rule 收口 | ✅ |
| 118 | architecture_decision.md 彙整 + ADR-021 | ✅ |
| 119 | glossary.md 擴 Sprint 118 era | ✅ |
| 120 | sprint50_66_retro.md 方法論萃取 | ✅ |

**階段 A 全綠**。階段 A 收益總結（roadmap 預估 vs 實際）：

| 指標 | 預估 | 實際 |
|---|---|---|
| VR mean | 不變 | 不變（0.073191）|
| Test 數 | +30~50 | +10 backend（27 → 31，<預估、scope drift 避開）|
| ir.rule | +1~2 | +0 rule body 變動（Sprint 117 純 lock-in test、Sprint 79 已落地 2 rule）|
| docs | +3 份 | **+4 份**（autonomous_roadmap + sprint117/118/119/120 + sprint50_66_retro = 6 個新檔）|
| CI 嚴謹度 | 大幅升級 | ✅（CI gate v1 落地、紀律 #15.a 揭示漸進模式）|

額外收益（roadmap 未預估）：

- 紀律 #18 子原則 +2（#18.c critical-fix cooldown、#18.d read-design-intent-first）
- 紀律 #14 子原則 +2（#14.a 集中索引即時更新、#14.b roadmap 外部化）
- 紀律 #15 子原則 +2（#15.a CI gate、#15.b 廣域應用）
- 紀律 #20 候選新（集中索引 §0 段）
- ADR 20 → 21

### 規畫書 §0.2 Phase 完成度

無變動（純 docs sprint cluster）。

---

## Root cause

**為什麼 Sprint 50-66 方法論萃取留到 Sprint 120 才做**：

1. Sprint 74 寫 sprint50_72_retro.md 時 focus 是「橫向高層數字」（收益曲線、test 累積）
2. 當時 cluster 內方法論還沒被當「可以萃取的東西」、被視為「reflexive doing」
3. Sprint 117-119 累積經驗（lock-in test / §0 索引 / glossary 擴 era）後、發現「方法論可萃取」的價值
4. Sprint 120 作為階段 A 收尾 sprint、補方法論萃取讓階段 A 的 docs 體系完整

---

## 紀律

### 紀律 #14 持續（Sprint 120）

retro 也屬「集中索引」型 doc。Sprint 120 寫 retro 同 sprint 沒加 §0 索引、因為本 retro § 內表都 < 10 entry（不觸發紀律 #20 候選的「超過 10 entry」門檻）。**這驗證紀律 #20 候選的「門檻是必要的」**—不是所有索引型 doc 都必須加 §0。

### 紀律 #20 候選驗證進展

- Sprint 118：ADR §0 索引（首次）
- Sprint 119：glossary §0 索引（第二）
- Sprint 120：本 retro 不加（門檻判斷正確、紀律 #20 候選包含「<10 entry 不必加」的細節）

跨 3 sprint 仍未集滿（CONTRIBUTING.md 沒在階段 A 範圍）。紀律 #20 候選保留為候選、等 Sprint 121+ 自然觸發。

---

## 後續

### Sprint 121（進入階段 B）

Sprint 121-135 階段 B：Phase 1-4 剩餘漏項。第一個 sprint = Phase 1 OOXML（1.5 進階 row height）。

階段 B 性質與階段 A 不同：

- 階段 A 多為 docs / catch-up / security / process（純 docs 4 個、product code 1 個）
- 階段 B 預期多 code change（OOXML parser、字型、style、layout）
- 三層 SOP 在階段 B 會跑全（L1 vitest + L2 VR + L3 spot + L4 backend）

### Sprint 120+ 候選

- CONTRIBUTING.md §0 索引補（完成紀律 #20 候選跨 3 sprint 驗證）
- sprint50_66_retro 方法論套用到階段 B（Sprint 121-135）每個 cluster 開工前 grep checklist

---

## Sprint 120 結尾累積指標

- vitest 976 + 1 skipped（未跑、必然一致）
- VR mean 0.073191（未跑、必然一致）
- Odoo backend local 31 passed（未跑、必然一致）
- CI gate v1 12 passed（font_serve、未動）
- Phase 0 100% / Phase 3 93% / 21 ADR / **18 條紀律 + 6 子 + 1 候選**（無變）
- Sprint audit doc 數 119 → **120**
- 階段 A 8 sprint 全 ✅、roadmap 進入階段 B
- 新增 retro doc：1（sprint50_66_retro.md）

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint50_66_retro.md  (+260 行方法論 retro)
A  addons/dobtor_doc_editor/docs/sprint120_sprint50_66_retro_creation.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 A 行 7 ✅ + Sprint 120 進度表 + 階段 A 完成標記)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

無 code / model / view / ACL / rule / test 變動。純 docs sprint、階段 A 收尾。
