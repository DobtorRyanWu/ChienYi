# Sprint 118 — architecture_decision.md 彙整（ADR §0 索引 + §0.5 §3 對映 + ADR-021）

**日期**：2026-05-17
**類型**：autonomous docs sprint（roadmap 階段 A 行 5）
**規畫書對應**：§11.2 行 5 + §附錄 A 殘餘

---

## Hypothesis

`architecture_decision.md` 累積 20 個 ADR、無索引、無 §3 規畫書對映、Sprint 117 揭示的新決策未進文件。讀者需從頭往下掃才知道有什麼 ADR、找不到某層架構由哪個 ADR 決定。

Sprint 118 補三件：

1. §0 ADR 索引（21 條一句話 + 編號 004-007 歷史缺口註解）
2. §0.5 規畫書 §3 6-layer 架構 ↔ ADR 對映表（Owl Component / Layer 1-6 / 横切產品化）
3. ADR-021 寫入 Sprint 117 cross-company portal collaboration 決策（含設計選擇、後果、可逆性）

---

## Method

### 1. Scope 對齊（紀律 #18）

- roadmap 階段 A 行 5：「`architecture_decision.md` 補完（規畫書 §3 對映 + ADR 20 個彙整）」
- 規畫書 §11.2 行 5 含 i18n + autonomous docs sprint
- SOP「docs only」
- 純文件變動、不打 code（紀律 #18 PR-size 內）

### 2. 編號 004-007 缺口處理

`grep '^## ADR-' architecture_decision.md` 顯示連續編號 001 → 002 → 003 → 008 → 009 → ... → 020。004-007 跳號。

兩個處理選擇：

| 選項 | 評估 |
|---|---|
| 補編號 004-007（fill in gaps） | 假造歷史、不真實；早期沒寫 ADR 就是事實 |
| **索引明示「歷史缺口」** | 真實、讀者不會以為被刪改 |

選後者。索引行 `004-007 | （歷史缺口） | — | 早期未編 ADR 文件、僅留 audit doc`。

### 3. §3 對映設計

規畫書 §3 列 6 層 + Owl Component。Sprint 118 對映表的設計取捨：

- 對映「ADR 落地紀錄」、不是「ADR 對 §3 一對一」（多對多關係：ADR-008 涵蓋 Layer 2+3、ADR-001 涵蓋 Owl Component+Layer 5+6）
- 加「横切：產品化」列、容納 ADR-016+017+018+019+020+021 等不屬 §3 6-layer 的決策（屬 §Phase 4.5 產品化基礎建設）
- 避免假裝每個 ADR 都在 §3 有對應（這會誤導未來讀者）

### 4. ADR-021 內容

Sprint 117 audit doc 已有完整 rationale。ADR-021 是 condensed 版（背景 / 決策 / 後果 / 參考），不重複 audit doc 全文、reference 過去。

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**（純 docs、0 行 source code 變動）|
| L2 VR v14 | **跳過**（純 docs、0 行 pipeline 變動）|
| L3 Spot check | ✅ wc/diff 驗證、§0 索引 21 列對齊 ADR 數量 / ADR-021 reference link 正確 |
| L4 Odoo backend | **跳過**（純 docs、ACL / model / controller / rule 0 變動）|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `docs/architecture_decision.md` | +54 行（§0 索引 + §0.5 §3 對映 + ADR-021） | 21 ADR 全索引、規畫書 §3 layer ↔ ADR 對映、Sprint 117 決策 ADR 化 |
| `docs/sprint118_architecture_decision_consolidation.md` | 本 audit doc | 紀錄彙整方式與設計取捨 |
| `docs/autonomous_roadmap.md` | 階段 A 行 5 ⏳→✅ + 進度表 Sprint 118 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

### Test 數變動

- Sprint 117 結尾：Odoo backend 31 passed
- Sprint 118 結尾：**31 不變**（純 docs sprint）

### 規畫書 §0.2 Phase 完成度

無變動（純 docs）。

### ADR 數變動

- Sprint 117 結尾：20 ADR
- Sprint 118 結尾：**21 ADR**（+1 = ADR-021 Sprint 117 收口）

---

## Root cause

**為什麼 ADR 索引到 Sprint 118 才補**：

1. Sprint 0-67 期間 ADR 累積 7 個（001-003 + 008、其餘缺）、規模小、無索引壓力
2. Sprint 70-89 autonomous batch 期 ADR 跳升到 20（一個 sprint 1-2 ADR）、累積壓力出現
3. Sprint 113 roadmap 把 ADR 彙整安排在階段 A 行 5、是 catch-up sprint 性質、不阻擋主軸
4. Sprint 117 揭示新決策（cross-company portal）、Sprint 118 同時補索引 + 新 ADR 一次到位

**為什麼編號 004-007 不補**：

- 歷史真實：早期沒寫；補等於假造
- 索引明示缺口 = 對未來讀者誠實
- 將來若有需要、可在 004-007 編號內寫「ADR-004: <某 Phase 0 決策回顧>」、但 Sprint 118 scope 不含此

---

## 紀律

### 紀律 #14 持續（Sprint 118）

紀律 #14「Docs 同步」延伸：ADR 集合也屬「集中索引」、新決策確立時需即時加 ADR（不是事後 catch-up）。Sprint 117 同 sprint 沒加 ADR、Sprint 118 補上、屬可接受 1-sprint cooldown（對映紀律 #18 子 critical-fix-cooldown ≤ 1 sprint）。

### 紀律 #20 候選（Sprint 118 揭示）

> **集中索引文件（ADR / glossary / CONTRIBUTING）應有 §0 索引段、不只依賴 grep**。
>
> **Why**：21 個 ADR 不加索引時、讀者只能 grep `^## ADR-` 才知道有什麼。索引行用一句話 + 編號 + sprint 對映、讀者掃 21 行就能定位、不需開檔。glossary（85 條）若無索引同樣痛。
>
> **How to apply**：
> - 集中索引文件超過 10 entry 時加 §0 索引
> - 索引行格式：`| # | 主題 | Sprint / Phase | 一句話 |`
> - 歷史缺口（如 ADR-004-007）保留編號 + 註明「歷史缺口」、不假造

候選未升正式紀律、需跨 3 sprint 驗證（glossary 與 CONTRIBUTING 是否也採用相同模式）。Sprint 119 glossary 擴充可驗證此候選。

---

## 後續

### Sprint 119（roadmap 階段 A 行 6）

`glossary.md` 擴充到 Sprint 112 era 完整紀律與 OOXML 術語。Sprint 118 揭示的紀律 #20 候選可在 Sprint 119 同時驗證（glossary §0 索引段）。

### Sprint 118+ 候選

- ADR-004 ~ 007 若需補（historical reconstruction）、可走獨立 sprint、不混在彙整 sprint
- ADR 大量 sprint exit report（009-012）內容稍弱於 001-003 / 014-021 的「決策」格式、可考慮統一為 audit doc + ADR 純決策摘要兩文件鏈

---

## Sprint 118 結尾累積指標

- vitest 976 + 1 skipped（未跑、必然一致）
- VR mean 0.073191（未跑、必然一致）
- Odoo backend local 31 passed（未跑、必然一致）
- CI gate v1 12 passed（font_serve、未動）
- Phase 0 100% / Phase 3 93% / **21 ADR**（+1 = ADR-021）/ **18 條紀律 + 6 子原則 + 1 候選**（+ #20 候選 Sprint 118 集中索引 §0 段）
- Sprint audit doc 數 117 → **118**
- architecture_decision.md：1146 → 1200 行（+54）

---

## File-level summary

```
M  addons/dobtor_doc_editor/docs/architecture_decision.md  (+54 行 §0 索引 + §0.5 §3 對映 + ADR-021)
A  addons/dobtor_doc_editor/docs/sprint118_architecture_decision_consolidation.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 A 行 5 ⏳→✅ + 進度表 Sprint 118)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

無 code / model / view / ACL / rule / test 變動。純 docs sprint。
