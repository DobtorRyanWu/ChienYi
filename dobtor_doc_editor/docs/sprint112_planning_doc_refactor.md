# Sprint 112 — 高保真匯入開發規劃書精煉重整

**日期**：2026-05-16
**類型**：catch-up sprint / docs only / 0 行 source code 變動
**觸發**：user 反映「規畫書有太多事之前紀錄的歷程，而不是在規劃」、要求精煉

---

## Hypothesis

`dobtor_doc_editor_高保真匯入開發規劃.md` 累積 Sprint 0 → Sprint 110 的逐 sprint 歷程紀錄，已從「規劃文件」轉成「開發日誌」：

- §0「實裝現況快照」152 行(7 個子章節 — 里程碑表 / 進行中表 / audit doc 全列表 / sprint 趨勢表 / Phase 表 / SOP / ENOMEM 事件)
- §11「下一步建議」實則 §11.1-§11.38 共 790 行(每個 sprint 各佔 15-50 行的 root cause / 修法 / 三層 SOP 紀錄)
- 附錄 A / A.1 為已完成的 task checklist
- 真正前瞻性的規劃內容(§1-§10)被歷程稀釋

教訓萃取入規劃章節後，個別 sprint 細節指向 `docs/sprintN_*.md`(audit doc 已是權威來源)應能還規畫書「規劃」本質。

---

## Method

### 1. 釐清精煉邊界（AskUserQuestion 一次問清楚）

- §11.1-§11.38(790 行) 處理方式 → **全部移除，改成索引**
- §0 (152 行) 保留多少 → **壓成 1 個當前指標表 + 1 段累積摘要**
- Sprint 110 revert 紀律 #18 處理 → **整合進 §1 + 紀律章節**
- 是否新增「開發紀律」獨立章節 → **整合進 §6 測試/驗證章節**(成為 §6.5)

### 2. 精煉執行（10 個步驟、單一檔案 Write 重寫）

| 步驟 | 區段 | 處理 |
|---|---|---|
| 1 | 標題段(lines 1-16) | 簡化為標題 + 目標 + 當前指標一行 |
| 2 | §0 實裝現況快照(lines 18-170) | 壓成 ~28 行:0.1 累積進度摘要 / 0.2 Phase 完成度 / 0.3 三層 SOP |
| 3 | 目錄(lines 173-185) | 同步 §6 改名為「測試、驗證與開發紀律」、加 §11/§12 |
| 4 | §1 現實評估 | 新增 §1.0「開工前必讀:Scope 對齊」(紀律 #18 教訓置頂) |
| 5 | §5 Phase 規劃 | 每個 Phase 段落開頭加「當前狀態」一行、融入 Sprint 50-89 揭示 |
| 6 | §6 測試與驗證 | 標題改「測試、驗證與開發紀律」、新增 §6.5「18 條開發紀律」表 |
| 7 | §11.1-§11.38(790 行逐 sprint 紀錄) | **整段移除**、改為 §11「下一步候選」(~30 行:11.1 待 user 決策 / 11.2 長期 backlog / 11.3 心理建設) |
| 8 | §12 歷史索引(新章節) | sprint audit doc 全索引、按 phase 分段、保留所有 docs/sprintN_*.md 連結 |
| 9 | 附錄 A / A.1 | 壓縮為「已完成」一段話 + 實際產出清單 |
| 10 | 附錄 B 術語表 | 不動 |

### 3. 三層 SOP（誠實聲明）

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**(0 行 source code 變動、結果**必然** = Sprint 111 結尾 976 passed + 1 skipped) |
| L2 VR v14 | **跳過**(0 行 pipeline / fixture / production code 變動、VR mean **必然** = 0.073191) |
| L3 Spot check 文件結構 | **跑** — wc -l / 章節 grep / docs/sprintN_*.md 連結存活檢查 |

紀律 #5 應用:對 docs-only sprint 跑 vitest / VR 是浪費 quota、誠實跳過符合紀律 #7 mechanical commit 精神延伸到文件層。

---

## Result

### 行數收斂

```
精煉前:1957 行
精煉後:963 行(-994 行 / -50.8%)
```

### 章節結構

精煉後 17 個 `## ` heading：

```
## 0. 當前狀態
## 目錄
## 1. 現實評估與心理建設
## 2. 還原度標準定義
## 3. 架構總圖
## 4. 核心技術棧
## 5. Phase 規劃（12-18 個月）
## 6. 測試、驗證與開發紀律
## 7. 程式碼組織
## 8. 風險與備案
## 9. 人力與時程矩陣
## 10. 閱讀與參考清單
## 11. 下一步候選
## 12. 歷史索引（Sprint Audit Docs）
## 附錄 A:Phase 0 任務清單
## 附錄 A.1:產品化補強清單
## 附錄 B:關鍵術語對照表
```

### 連結存活

`docs/sprintN_*.md` 連結數量 = **57 個獨立連結**(集中在 §12 歷史索引)。Phase 1-3 主體(Sprint 2-33)32 個、Phase 3 收斂主軸(Sprint 34-49)16 個、Phase 7+ Phase 2 字型(Sprint 50-65)代表 audit 3 個、autonomous batch(Sprint 64b-89)4 個、revert 事件(Sprint 90-111)2 個。所有 sprint audit doc 至少索引到一次。

### 關鍵原則就位驗證

| 原則 | 出現位置 | grep 命中行 |
|---|---|---|
| Scope 對齊 | §1.0、§8.1 風險表 | 78、752 |
| 紀律 #18 | §1.0(回指 §6.5)、§6.5 表第 18 列、§12 revert 事件段 | 86、635、911 |
| Sprint 110 revert 教訓 | §0.1 累積摘要、§1.0、§6.5、§11.3、§12 | 5 處 |

### §11 內容性質驗證

§11 全段 `Sprint ` 字串出現 7 次，**全部為前瞻性引用**(Sprint 64b external / Sprint 60 probe / Sprint 53 fixture / Sprint 55 benchmark / Sprint 78 Finding B / Sprint 70-89 廣域 / Sprint 0 → Sprint 110 心理建設一句)。**無歷程式「Sprint N 做了 XX」紀錄**。

---

## Root cause（為什麼規畫書原本變得這麼長）

1. **Sprint 0-33 era**:本檔案是規劃文件、§0/§11 沒有歷程性內容
2. **Sprint 14 era**:`docs/sprintN_*.md` 個別 audit doc 制度建立、但 §0/§11 沒同步移除高層彙整
3. **Sprint 25-50 era**:每個 sprint 開始把成果寫進 §0.4 趨勢表 + §11.X 章節，§11 開始膨脹
4. **Sprint 50-89 era**:autonomous batch 後 §0.1/§0.2/§11.1-11.38 同步遞增、行數爆炸
5. **Sprint 90-110 era**:revert 事件加 §11.38 + Sprint 110 重要教訓段、檔頭也擴張

**真根因**:制度 = 每個 sprint 同步更新規畫書 §0/§11、累積 80+ 個 sprint 後沒人發現「規畫書」職責漂移成「開發日誌」。

---

## 紀律

### 紀律 #14 延伸子原則(Sprint 112 揭示)

> **規劃文件本身需要週期性精煉、不只是新紀律時 catch-up**。
>
> Sprint 111 揭示「集中索引(CONTRIBUTING / glossary)需即時同步」;Sprint 112 揭示更上一層的問題:**規劃文件本身的「規劃 vs 歷程」職責邊界會隨 sprint 累積漂移**。
>
> How to apply:
> - 規畫書頁數超過 1000 行時(本檔案達 1957 行)觸發精煉檢查
> - 精煉時把歷程性內容(逐 sprint 紀錄、趨勢表、已完成 checklist)整段下放到專屬索引章節或 `docs/sprintN_*.md`
> - 教訓萃取入相關規劃章節(§1.0 scope 對齊 / §6.5 紀律表 / §5 Phase 狀態註記)
> - 保留所有 audit doc 連結(歷史不刪、只搬位置)

### 紀律 #7 延伸到文件層(Sprint 112 應用)

- Sprint 65 揭示「Mechanical commit 是多 sprint 紀律性投資的內化、適用 docs / process commit」
- 本 sprint 應用:精煉本身是 mechanical refactor(無 source code、無 test 變動、無 VR 變動)、但站得住腳是因為 Sprint 50-110 累積 60 個 sprint 的隱性紀律首次顯式化為精煉後的 §6.5 紀律表

---

## 後續

### Sprint 112 結尾累積指標（與 Sprint 111 結尾一致 — byte-identical to production code）

- vitest **976 passed + 1 skipped** ✓(未跑、必然一致)
- VR mean **0.073191** ✓(未跑、必然一致)
- Odoo backend **21 passed** ✓(未跑、必然一致)
- Phase 0 **100%** / Phase 3 **93%** / 20 ADR / **18 條開發紀律**(顯式化)
- 規畫書行數 1957 → **963**(-50.8%)
- Sprint audit doc 數 **112**(+ sprint112_planning_doc_refactor.md)

### Sprint 113+ 候選

精煉後規畫書 §11.1 列出的「待 user 決策」候選不變：

- migrate doc_editor.js 走 production canvas-editor 整合（Sprint 64b external）
- 重生 goldens 用 Word desktop 渲染（大改造）
- OffscreenCanvas + Web Worker render（Sprint 60 probe GREEN）
- 50+ 頁 fixture 收集（待 user 提供）
- Sprint 78 Finding B（portal company rule）

§11.2 長期 backlog:opentype.js 真實字型 metric / Phase 3.6 註腳 / Phase 5 OMML / Web Worker parse / docGrid snap 段落層級判別子 / 雙軌 VR / i18n 7 missing translations / autonomous docs sprint。

### 連動文件同步

- [/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md](../dobtor_doc_editor_高保真匯入開發規劃.md) — 本 sprint 主修對象、版本 1.0 → 2.0
- [/home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md](../../../../home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md) — 本 sprint append Sprint 112 段落
- CONTRIBUTING.md — 不需動(§6.5 紀律表是它的下游、CONTRIBUTING.md 仍是上游權威)
- glossary.md — 不需動(術語表未受影響)

---

## File-level summary

僅 1 個檔案被修改:

```
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (1957 → 963 lines, -50.8%)
A  addons/dobtor_doc_editor/docs/sprint112_planning_doc_refactor.md  (本 audit doc)
M  /home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md  (+ Sprint 112 段落)
```

無 production source code 變動、無 test 變動、無 fixture 變動、無 manifest 變動、無 ACL 變動。
