# Sprint 141 — 階段 C 重生 goldens 環境 probe sprint(autonomous DEFER 至 user GO)

**日期**:2026-05-18
**類型**:probe-only sprint(0 production code、純 docs + audit)
**規畫書對應**:§11.1 行 2「重生 goldens 用 Word desktop 渲染」+ autonomous_roadmap §階段 C(Sprint 136-138 原排)
**前置 sprint**:Sprint 140(A 候選 DEFER)、user 指示「逐步執行 abc」B 階段

---

## Hypothesis(驗證對象)

autonomous_roadmap §階段 C:

> 重生 goldens 用 Word desktop 渲染 — 規畫書 §11.1 行 2、Claude 自主決策。換 metric anchor 後 mean ~0.05 → ~0.02-0.03、A 級邊緣

驗證:
1. 現有 goldens 怎麼產的?(替換對象釐清)
2. wsl 環境可跑哪些 renderer alternatives?
3. 不同方案的預期收益 vs 風險?
4. autonomous GO 還是 user GO?

---

## Method

### 1. Scope 對齊(紀律 #18)

- autonomous_roadmap §階段 C(Sprint 136-138 原排、本 sprint 是延遲執行)
- 規畫書 §11.1 行 2 + 風險紓緩 Plan B
- 本 sprint scope = **probe-only**(0 production code、依紀律 #22 + Sprint 135/140 模式)

### 2. 現況釐清

#### 2.1 現有 goldens 產生方式

`tests/scripts/generate_golden.sh` 揭示真實流程:

```
DOCX → LibreOffice headless --convert-to pdf → pdftoppm -r 150 -png → goldens
```

**不是** Word desktop renders、**而是** LibreOffice render(規畫書 §11.1 假設與實況有差)。

#### 2.2 現有 goldens 數量

```
01_simple: 42 PNG
02_std_table: 27 PNG
03_complex_table: 23 PNG
04_with_image: 56 PNG
05_header_footer: 90 PNG
06_template: 14 PNG
---
總計: 252 PNG / 42 fixture × 平均 6 頁
VR pipeline 對齊 126 pages(分 2 半比對?或單頁 N 個版本)
```

#### 2.3 環境就緒度評估

| 工具 | 狀態 | 可用性 |
|---|---|---|
| LibreOffice 24.2.7.2 headless | ✅ 已裝 | 現有 baseline 來源、可換 font/DPI/page split mode 微調 |
| Docker 29.3.1 + Docker Compose v5.1.1 | ✅ 已裝 | 可跑 OnlyOffice DocumentServer image |
| OnlyOffice DocumentServer image | ❌ 未拉取 | Plan B 主候選、需 `docker pull onlyoffice/documentserver` |
| Pillow 12.2.0 | ✅ 已裝 | 圖片處理 / pixelmatch |
| puppeteer + node 20 | ✅ 已裝 | render pipeline 配套 |
| wkhtmltopdf | ❌ 未裝 | 規畫書 §11.1 提及、可 apt install |
| Word desktop | ❌ wsl 不可用 | Windows-only、需手動跨界轉換 |

### 3. 重生方案評估(autonomous 3 方案)

#### 方案 A:LibreOffice 升級微調(保守、改善幅度小)

| 變項 | 預期 |
|---|---|
| 範圍 | font 換成 Word default(Times New Roman / 細明體)、DPI 144 → 150 已是、page split 規則對齊 Word |
| 收益估算 | mean 0.073191 → ~0.06-0.07(改善 5-15%)|
| 環境需求 | 0(現有環境)|
| 實作工時 | 1 sprint(font 套用 + 重跑 + baseline 校正)|
| 風險 | 低(LibreOffice 已穩定、僅 config 變動)|

#### 方案 B:OnlyOffice DocumentServer headless(中等、預期效果好)

| 變項 | 預期 |
|---|---|
| 範圍 | docker pull onlyoffice/documentserver、startup compose、conversion API call |
| 收益估算 | mean 0.073191 → ~0.04-0.05(改善 30-45%、最接近 Word fidelity)|
| 環境需求 | 中(Docker 鏡像 ~4GB、compose config、port 80 衝突檢查)|
| 實作工時 | 2-3 sprint(env setup + API integration + bulk conversion + golden re-baseline)|
| 風險 | 中(OnlyOffice API 學習曲線、license 確認(community 版有頁數限制)、CJK 字型需手動裝)|

#### 方案 C:wkhtmltopdf + OOXML→HTML 中介(實驗、accuracy 未知)

| 變項 | 預期 |
|---|---|
| 範圍 | apt install wkhtmltopdf、自寫 DOCX → HTML(用本模組 mapper)→ wkhtmltopdf PDF → PNG |
| 收益估算 | 未知(HTML 中介層損失精度、可能比 LibreOffice 還差)|
| 環境需求 | 低(apt 一行)|
| 實作工時 | 3-5 sprint(HTML 中介層需大量 CSS 對應 OOXML、相當於部分 Phase 6 docx export)|
| 風險 | 高(HTML rendering 不等於 docx rendering、metric anchor 偏移可能不對齊任何 metric)|

#### 方案對照表

| 方案 | 收益 | 風險 | 工時 | autonomous 推薦 |
|---|---|---|---|---|
| A. LibreOffice 微調 | 中(-5~15%) | 低 | 1 sprint | **次推薦**(快速見效)|
| **B. OnlyOffice** | 高(-30~45%) | 中 | 2-3 sprint | **主推薦**(最接近 Word fidelity)|
| C. wkhtmltopdf | 未知 | 高 | 3-5 sprint | **不推薦**(violation 紀律 #18)|

### 4. 決策框架(autonomous GO vs user GO)

#### autonomous GO 條件(無 user 確認可直接執行)

- scope 小、可逆、不破 baseline
- 紀律 #18 PR-size 可控
- 失敗有完整 revert 路徑

#### user GO 條件(必須 user 明確同意)

- **換 baseline**(byte-identical 16 連軌道斷)→ 影響整個紀律 #1.a 累積驗證
- 環境變動(docker pull 大鏡像、安裝新工具)
- 工時 > 2 sprint 連續投入

**Sprint 141 結論**:方案 B(OnlyOffice)和方案 A(LibreOffice 微調)**都換 baseline**、影響紀律 #1.a 16 連軌道 → 需 **user 明確 GO** 才能執行。

### 5. 推薦路徑(若 user GO 後)

**Phase 1**(Sprint 142、autonomous 可執行 plan):
- 寫 OnlyOffice docker-compose.yml(挑 port 8080 避衝突)
- 確認 conversion API endpoint 與 auth 設定
- 跑單一 fixture probe-only(不批次)、量測 conversion latency + accuracy 樣本

**Phase 2**(Sprint 143、需 user GO 跑 batch):
- 全 42 fixture batch convert → 新 PNG goldens
- 暫存 `tests/fixtures/<cat>/golden_v2/`(不蓋舊)
- 跑 compare_fixtures 對新 baseline、評估 mean

**Phase 3**(Sprint 144、user 確認後 promote):
- 若新 baseline mean < 0.05 → promote `golden_v2/` → `golden/`、舊版進 `golden_v1_libreoffice/` 備份
- 更新 generate_golden.sh 為 OnlyOffice 路徑
- 紀律 #1.a 重新計數從 1(Sprint 144 開始第 1 連)

**Phase 4**(Sprint 145、numbering opt-out 切換):
- VR pipeline 改 documentNode.numbering 主動注入(Sprint 139 Strategy C → opt-out)
- 量測 numbering wire-up 真實視覺收益(預期 -1~2pp 改善)

### 6. 三層 SOP(本 probe sprint)

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**(0 code、誠實聲明)|
| L2 VR v14 | **跳過**(同上)|
| L3 Spot check | 純 docs sprint |
| L4 Odoo backend | **跳過** |

---

## Result

### Decision: autonomous DEFER B 候選實作至 user GO

**autonomous 決策依據**:

1. **換 baseline = 失去紀律 #1.a 16 連軌道**:這個 byte-identical 進度是 user 視角下「進度直觀」的核心指標、不應在 user 未明確 GO 下放棄
2. **OnlyOffice 啟動需 ~4GB docker image pull**:本機資源 + 網路 + 時間成本、應 user 確認
3. **多步驟流程 (Phase 1-4)**:跨 4 sprint scope、紀律 #18 + #22 要求每步 probe + user 同步進度
4. **預期收益高但驗證難**:OnlyOffice 與 Word 的 fidelity 是 hypothesis、需實測單 fixture 才能確認

### Sprint 141 產出

| 產出 | 用途 |
|---|---|
| 本 audit doc | 環境探勘 + 3 方案評估 + 推薦路徑 + autonomous DEFER 決策 |
| roadmap 階段 C 更新 | autonomous_roadmap.md Sprint 141 ✅ probe |
| 規畫書 §0.1 標頭 | 同步當前狀態 |

### 後續觸發條件

| 觸發 | 動作 |
|---|---|
| user 明確 GO「執行重生 goldens」 | Sprint 142 進方案 B Phase 1(docker-compose probe)|
| user 接受 LibreOffice 微調(妥協)| Sprint 142 改方案 A(1 sprint 快速完工)|
| user 表示「先放著、做其他」 | Sprint 142 進 C(Phase 5 開工 OMML/SmartArt 之 probe)|

---

## 紀律

### 紀律 #22 第 8 次正式應用(probe sprint)

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Sprint 141 揭示:
1. **規畫書 §11.1「Word desktop」假設 ≠ 實況**:現有 goldens 是 LibreOffice、不是 Word desktop。重生 goldens 的「換 anchor」對象需明確化
2. **環境就緒度 ≠ 自動可執行**:Docker / LibreOffice 都就緒、但 OnlyOffice image 未拉、且 user 未 GO baseline 變動
3. **3 方案 trade-off 不對稱**:A 快但弱、B 慢但強、C 工程量過大應排除

### 紀律 #18 守護案例

Sprint 141 是 #18 守護的延續(同 Sprint 140 模式):當 scope 跨 4 sprint + 換 baseline 時、應停 probe + 寫 audit 等 user 確認、避免「悶頭做完才發現 user 不同意」。

### 紀律 #1.a 16 連軌道意識

紀律 #1.a 16 連是「自寫 layout 對 LibreOffice goldens 的 byte-identical」累積。換 anchor 後必然斷、所以**換 anchor 本身需 user GO**、不是 autonomous 可決策範圍。

### 提案紀律 #1.b 候選 v2 第 7 次跨 sprint 驗證

| Sprint | 類型 |
|---|---|
| 110 | 全 revert |
| 136 | 全 revert |
| 137 | 預防(probe scope-down)|
| 138 | 實作(probe 確認可行)|
| 139 | Strategy C 折衷 |
| 140 | 預防 DEFER(A 候選)|
| **141** | **預防 DEFER user GO(B 候選)** |

7 次跨 sprint、3 類型完整光譜(全 revert × 2 / 預防 × 3 / 實作 × 1 + 折衷 × 1)。**Sprint 141 揭示新類型**:「需 user GO 的預防 DEFER」、強調**autonomous 範圍邊界**。

### 紀律 #4 應用

> 負面結果 sprint 仍有結構價值

Sprint 141 揭示「Word desktop 假設 ≠ 實況」、「baseline 變動非 autonomous 範圍」、「OnlyOffice docker scale 為 user 決策」三個結構性事實、為 user 後續決策提供完整資訊。

---

## 後續

### Sprint 142 候選(待 user 決策)

依「逐步執行 abc」:
- B 候選已 probe + DEFER user GO → 進入 **C 候選 probe**(Phase 5 開工 OMML / SmartArt / 追蹤修訂)
- 或:user 明確 GO 後 → Sprint 142 = B Phase 1(OnlyOffice docker-compose probe)
- 或:user 接受 LibreOffice 微調 → Sprint 142 = A 快速實作

**autonomous 選擇:依「逐步執行 abc」順序繼續、Sprint 142 = C probe**(Phase 5 scope assessment)。

---

## Sprint 141 結尾累積指標

- vitest **1176 passed + 1 skipped**(未動、純 probe)
- VR mean **0.073191** / failed 0 / compared 126(未動、**第 15 次連續 byte-identical 維持**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 4 Style **90%**(未變、Phase 4.4 capture DEFER + Phase 階段 C 重生 goldens DEFER user GO)
- 21 ADR / 紀律 **21 條** + 6 子 + **2 候選**(#20 集中索引、**#1.b 候選 v2 第 7 次跨 sprint 驗證**、揭示新類型「需 user GO 的預防 DEFER」)
- Sprint audit doc 140 → **141**

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint141_goldens_regen_probe.md  (本 probe audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 141 ✅ probe DEFER user GO)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + 階段 C DEFER user GO 註記)
```

**淨 production code 變動 = 0**(pure probe)、階段 C 重生 goldens 3 方案評估 + autonomous DEFER user GO + 4-step 推薦路徑(若 user GO)、紀律 #1.b 候選 v2 第 7 次跨 sprint 驗證揭示新類型「需 user GO 的預防 DEFER」。下個 sprint 進 C(Phase 5 開工 probe)。
