# Sprint 119 — glossary.md 擴充到 Sprint 118 era

**日期**：2026-05-17
**類型**：autonomous docs sprint（roadmap 階段 A 行 6）
**規畫書對應**：§附錄 B 延伸

---

## Hypothesis

`glossary.md` 從 Sprint 73 落地、上次擴充到 Sprint 110 era（17 紀律 + 11.a/11.b/18.a/18.b 子）。Sprint 111-118 期間：

- 紀律 14 / 15 升級為正式紀律
- 14.a / 14.b / 15.a / 15.b / 18.c / 18.d 子原則加入
- 20 候選新揭示
- autonomous_roadmap.md / cross-company collaboration / lock-in test / null byte sanitize / CI gate 漸進模式 / autonomous 決策範式 等術語未進 glossary

Sprint 119 補：擴 §2.1 紀律表、加新術語進 §4、加 §8 Process 模式段、加 §0 索引段（驗證 Sprint 118 揭示的紀律 #20 候選）。

---

## Method

### 1. Scope 對齊（紀律 #18）

- roadmap 階段 A 行 6：「`glossary.md` 擴充到 Sprint 112 era 完整紀律與 OOXML 術語」
- 規畫書 §附錄 B 延伸（OOXML 術語在規畫書附錄 B、glossary 補 process / 紀律 / 衡量 / 工具鏈、不重複）
- SOP「docs only」
- 純 docs、不打 code（紀律 #18 PR-size 內）

### 2. 擴充範圍

#### 2.1 §2.1 紀律表

- 紀律 13/14/15 從「候選」升正式（Sprint 73+ 跨 sprint 驗證已過）
- 加 14.a（Sprint 111）/ 14.b（Sprint 113）
- 加 15.a（Sprint 114）/ 15.b（Sprint 115）
- 加 18.c（Sprint 116）/ 18.d（Sprint 117）
- 加 20 候選（Sprint 118）

紀律總數：17 → **18 + 6 子 + 1 候選**

#### 2.2 §4 後端 / Odoo 整合

加 4 新術語：null byte sanitize（Sprint 116）/ cross-company collaboration（Sprint 117）/ lock-in test（Sprint 117）/ autonomous_roadmap.md（Sprint 113）

#### 2.3 §5 工具鏈與 CI

加 CI gate 漸進模式 3 階段（v1 dispatch / v2 nightly / v3 push）— Sprint 114 揭示

#### 2.4 §8 Process 模式（新章節）

8 個 process 術語：autonomous 決策 / scope drift enforce / 三層 SOP / progressive CI gate / critical-fix cooldown / read-design-intent-first / §0 索引段 / lock-in test

#### 2.5 §0 索引段（驗證紀律 #20 候選）

加 §0 章節索引（章節 + 主要術語數），驗證 Sprint 118 揭示的紀律 #20 候選「集中索引文件超過 10 entry 應有 §0 索引段」在 glossary 是否也有效。

### 3. 紀律 #20 候選驗證

Sprint 118 在 ADR 文件加 §0 索引；Sprint 119 在 glossary 加 §0 索引。**跨 2 sprint 驗證**：

| 文件 | 加 §0 前 entry 數 | 讀者體驗 | 加 §0 後 |
|---|---|---|---|
| ADR | 20 → 21 ADR | 必 grep `^## ADR-` 才知有什麼 | 索引 21 行掃完即定位 |
| glossary | 148 → 149 表列 | 8 章節需逐個讀 | 章節 + 數量索引一行掃完 |

第 3 sprint 驗證：若 Sprint 120+ 或之後對 CONTRIBUTING.md 也加 §0 索引、則紀律 #20 候選可升正式紀律（紀律父原則升級條件 = 3 sprint 跨度驗證）。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**（純 docs、0 行 source code 變動）|
| L2 VR v14 | **跳過**（純 docs、0 行 pipeline 變動）|
| L3 Spot check | ✅ wc/grep 驗證、表列從 144 → 149 列、紀律表所有 sprint 來源 ≤ 118 |
| L4 Odoo backend | **跳過**（純 docs）|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `docs/glossary.md` | +44 行（172 → 216）/ +5 表列 / +1 章節（§8）| 擴充到 Sprint 118 era、§0 索引、§8 Process 模式 |
| `docs/sprint119_glossary_expansion_to_sprint118_era.md` | 本 audit doc | 紀錄擴充方式與紀律 #20 候選驗證 |
| `docs/autonomous_roadmap.md` | 階段 A 行 6 ⏳→✅ + 進度表 Sprint 119 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

### 紀律狀態變化

- Sprint 118 結尾：17 條 + 11.a 11.b 14.a 14.b 18.a 18.b 6 子 + 1 候選（#20）
- Sprint 119 結尾（glossary 同步）：**18 條 + 6 子（11.a 11.b 14.a 14.b 15.a 15.b 18.a 18.b 18.c 18.d）+ 1 候選（#20）**
- 變化：13/14/15 從「候選」升正式（追認過去 sprint 累積結論）；加 15.a/15.b/18.c/18.d 子（既有 sprint 已落地、glossary 補同步）

### 規畫書 §0.2 Phase 完成度

無變動（純 docs）。

---

## Root cause

**為什麼 glossary 落後 Sprint 110→118 8 sprint 才補**：

1. Sprint 73 glossary 落地後、Sprint 75/77/78/79 都有「14/15/15.b 揭示」、各自進 audit doc 但沒同步 glossary（紀律 #14 候選還沒成正式紀律時的痛點）
2. Sprint 111 紀律 #14.a 揭示「集中索引必須即時更新」、補了 CONTRIBUTING.md、但 glossary 漏網
3. Sprint 118 補 ADR 索引後、發現 glossary 結構同樣 stale、Sprint 119 順手補

**為什麼 §0 索引段是有用的**：

- 21 ADR / 149 表列、未來只會更多
- 沒索引時、讀者必 grep 才知有什麼術語、進階問「§3 有幾個術語」也答不出
- §0 一行掃完 + 章節定位是 incremental cost、值得

---

## 紀律

### 紀律 #20 候選跨 2 sprint 驗證進展（Sprint 118 → 119）

- Sprint 118：ADR §0 索引（首次應用、ADR 21 條）
- Sprint 119：glossary §0 索引（第二次應用、148→149 表列）
- 待第 3 次：CONTRIBUTING.md 加 §0 索引（Sprint 120+ 候選），完成跨 3 sprint 驗證即可升正式紀律

### 紀律 #14 廣域應用（Sprint 119）

紀律 #14「docs / audit / ADR / glossary 必須即時同步」在 Sprint 119 從「ADR」延伸到 glossary 本身。Sprint 119 是「補同步」性質（catch-up），未來新紀律確立時應同 sprint 同步 glossary、不再 8 sprint 後補。

---

## 後續

### Sprint 120（roadmap 階段 A 行 7）

Sprint 50-66 retro：萃取 cache 五連發 + FontMetricsAdapter 學到的方法論。可同時驗證紀律 #20 候選對 CONTRIBUTING.md 是否適用（若 Sprint 120 結尾發現 CONTRIBUTING 也需 §0 索引、紀律 #20 即可升正式）。

### Sprint 119+ 候選

- glossary §1 補 Sprint 113+ 衡量指標（若有新加 baseline）
- glossary §3 前端子系統若有 Sprint 119+ 新 module 進場、同步加
- 規畫書附錄 B 與 glossary 跨 doc 重疊區（OOXML 術語）可考慮統一指向附錄 B、glossary 只放 process / 紀律 / 子系統

---

## Sprint 119 結尾累積指標

- vitest 976 + 1 skipped（未跑、必然一致）
- VR mean 0.073191（未跑、必然一致）
- Odoo backend local 31 passed（未跑、必然一致）
- CI gate v1 12 passed（font_serve、未動）
- Phase 0 100% / Phase 3 93% / 21 ADR / **18 條紀律 + 6 子 + 1 候選**（紀律狀態正式 sync 進 glossary）
- Sprint audit doc 數 118 → **119**
- glossary.md：172 → 216 行（+44）
- 紀律 #20 候選跨 sprint 驗證：1 → **2**（Sprint 120 = 3 即可升正式）

---

## File-level summary

```
M  addons/dobtor_doc_editor/docs/glossary.md  (+44 行、+5 表列、+1 §8 章節、§0 索引)
A  addons/dobtor_doc_editor/docs/sprint119_glossary_expansion_to_sprint118_era.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 A 行 6 ⏳→✅ + 進度表 Sprint 119)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

無 code / model / view / ACL / rule / test 變動。純 docs sprint。
