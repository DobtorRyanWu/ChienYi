# Sprint 113 — Autonomous Roadmap 外部化 + 紀律 #14.b 子原則延伸

**日期**:2026-05-16
**類型**:catch-up sprint / docs only / 0 行 source code 變動
**觸發**:user 於 Sprint 112 後授權 autonomous 推進規畫書到 A 級完成、§11.1 候選自主決策。終極目標 = docx/doc 1:1 與 Google Docs 同視覺 = A 級 VR mean <0.02。

---

## Hypothesis

**問題**:規畫書 §11.1 + §11.2 候選若全攤開展開為執行排程、規模 ~30-60 sprint。若全擠進規畫書 §11 內、會違反 Sprint 112 精煉精神(規畫書再度膨脹回 1957 行的歷史)。

**假設**:把詳細執行排程外部化為 `docs/autonomous_roadmap.md`、規畫書 §11 只保留高層次描述 + 一行指向 roadmap、職責分離(規畫書 = 規劃 / roadmap = 執行排程),既保留規畫書精煉成果(963 行)、又給 Sprint 114-175 一個明確排程根據。

**揭示新紀律候選**:**規畫書 §11 候選達 30+ sprint 規模時、應外部化為 roadmap doc**(紀律 #14.b)。

---

## Method

### 1. 規畫階段(plan mode)

- 讀 lazy-dazzling-shell.md(舊精煉 plan、Sprint 112 已完成)
- 讀規畫書 §11 + §6.5 紀律 #14、確認 user 授權邊界
- 用 AskUserQuestion 釐清兩個邊界:user 決策 gate 處理 / autonomous 停止條件
- User 回:「你就是 user 你自己做決策、我是老闆最後會看你的成果」+「整份規畫書所有內容完全完成才停止」
- 寫新 plan 蓋掉舊精煉 plan、ExitPlanMode

### 2. 執行階段

| 步驟 | 動作 | 檔案 |
|---|---|---|
| 1 | 新建 roadmap doc(階段 A-E 完整搬入 + 終點條件 + 風險紓緩) | `addons/dobtor_doc_editor/docs/autonomous_roadmap.md` |
| 2 | 規畫書 §11 加一行指向 roadmap | `dobtor_doc_editor_高保真匯入開發規劃.md` line 868 |
| 3 | 規畫書 §6.5 紀律表後加「紀律 #14 子原則」累積段(#14.a / #14.b) | `dobtor_doc_editor_高保真匯入開發規劃.md` line 635 |
| 4 | pure-duckling.md append Sprint 113 段(原 Sprint 113+ 候選改為 Sprint 114+) | `/home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md` |
| 5 | 寫本 audit doc(完整 6 段) | `addons/dobtor_doc_editor/docs/sprint113_autonomous_roadmap.md` |
| 6 | Append session log | `/mnt/d/work/.claude/logs/session_2026-05-16.md` |

### 3. 三層 SOP(誠實聲明)

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過** — 0 行 source code 變動、結果**必然** = Sprint 112 結尾 976 passed + 1 skipped |
| L2 VR v14 | **跳過** — 0 行 pipeline / fixture / production code 變動、VR mean **必然** = 0.073191 |
| L3 Spot check | **跑** — wc -l 規畫書 / 章節數 / 連結存活、roadmap 章節結構 / 階段 A-E 完整 |
| L4 Odoo HttpCase | 不適用(無 backend code 變動) |

紀律 #5 + #7 應用:純 docs sprint 跳過 vitest / VR 是浪費 quota、誠實跳過符合 mechanical commit 精神。

---

## Result

### 行數變動

| 檔案 | 前 | 後 | Δ |
|---|---|---|---|
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 963 | ~970 | +7(roadmap 指向 + 紀律 #14 子原則段) |
| `docs/autonomous_roadmap.md` | - | ~170 | +170(新建) |
| `docs/sprint113_autonomous_roadmap.md` | - | ~170 | +170(本 audit doc) |
| `/home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md` | 1135 | ~1160 | +25(Sprint 113 段) |

### Roadmap 階段結構

- **階段 A**(Sprint 113-120,8 sprint):autonomous catch-up — CI font_serve job / security 邊界廣域 / i18n / Sprint 78 Finding B / autonomous docs(architecture_decision / glossary / retro)
- **階段 B**(Sprint 121-135,15 sprint):Phase 1-4 剩餘漏項 — OOXML trHeight calcInternal / OLE / field code / SDT / bookmark / hyperlink / Theme tint+shade / tblStylePr 15 種 / 中文編號 / 段落進階 / docGrid snap 段落層級
- **階段 C**(Sprint 136-145,10 sprint):重生 goldens 換 metric anchor + Phase 3 收口(wrapTight / column balancing / 註腳尾註)
- **階段 D**(Sprint 146-160,15 sprint):Phase 5 進階(OMML / SmartArt fallback / Charts fallback / 追蹤修訂 / 註解 / 浮水印)
- **階段 E**(Sprint 161-175,15 sprint):Phase 6 docx export 對稱性 / Phase 7 OffscreenCanvas worker / 50+ 頁 fixture 替代品 / 大文件效能 / 邊緣相容 / A 級 final audit

**總計 ~63 sprint**(Sprint 113-175)、終點 = 規畫書 §11.1 + §11.2 候選全綠 + VR mean <0.02。

### 紀律 #14 子原則正式化

規畫書 §6.5 紀律 #14 段後新增「紀律 #14 子原則」累積段:

- **#14.a**(Sprint 111):集中索引(CONTRIBUTING / glossary)必須在新紀律確立時即時更新、不是事後 catch-up
- **#14.b**(Sprint 113):**規畫書 §11 候選達 30+ sprint 規模時、應外部化為 roadmap doc**;職責分離:規畫書 = 規劃、roadmap = 執行排程

---

## Root cause

**為什麼今天才揭示紀律 #14.b**:

1. Sprint 0-67:規畫書 §11 候選數 <10、單檔承受得住、不需 roadmap doc
2. Sprint 67-110:候選逐漸累積但 user 一直手動接、不需排程
3. Sprint 110 revert + Sprint 111 紀律 #18 + Sprint 112 精煉:規畫書 §11 重整為 §11.1(待 user 決策)+ §11.2(長期 backlog)、結構清楚但仍混雜「短期 autonomous」與「長期 backlog 6-12 個月」
4. Sprint 113:user 授權 autonomous loop + 終極 A 級目標 → 揭示**規畫書 §11 同時承載「短期排程」與「長期 backlog」會混亂**、應外部化短期排程為 roadmap

**真根因**:文件職責邊界。**規畫書 = 規劃**(長期不變 / 範圍 / 紀律 / Phase 結構)、**roadmap = 執行排程**(短期變動 / sprint 排序 / 進度追蹤)。把兩者擠進同一檔會周期性膨脹(Sprint 112 精煉就是踩過這個坑)。

---

## 紀律

### 紀律 #14 父原則(Sprint 111 揭示、Sprint 112 + 113 延伸)

> 文件職責邊界 — 規劃文件 vs 執行紀錄需要分檔管理、不能混在一起。

### 紀律 #14.a(Sprint 111)

> 集中索引(CONTRIBUTING / glossary)必須在新紀律確立時即時更新、不是事後 catch-up。

### 紀律 #14.b(Sprint 113)

> **規畫書 §11 候選達 30+ sprint 規模時、應外部化為 roadmap doc**。
>
> **Why**:Sprint 112 已揭示規畫書會周期性膨脹;若每次 §11 累積 30+ sprint 就再精煉一次、是循環戰役。外部化讓規畫書專注於「規劃」(Phase 結構 / 紀律 / 風險 / 還原度標準)、roadmap 專注於「執行排程」(sprint 排序 / 進度 / 終點條件)。
>
> **How to apply**:
> - §11 保持 <50 行(只列高層次候選分類 / 一行指向 roadmap)
> - 詳細排程 → `docs/autonomous_roadmap.md`(階段 A-E、每 sprint 1-3 PR-size、終點條件清楚)
> - Roadmap 進度追蹤段每 sprint append 一行(時間 / VR mean / Phase 變動 / 紀律新增)
> - 階段全綠時、回頭把規畫書 §0.2 Phase 完成度同步更新

### 紀律 #7 延伸到 roadmap 層(Sprint 113 應用)

Roadmap 是 Sprint 112 精煉 + Sprint 50-110 累積 60 個 sprint 隱性紀律的 mechanical commit:把「下一步該做什麼」的隱性共識顯式化成可被未來 sprint 引用的排程 doc。

---

## 後續

### Sprint 114(階段 A 第二步)

CI 加 `--test-tags font_serve` job — Sprint 69 揭示 HttpCase 12 tests 全綠但只能手動跑;Sprint 114 應改 `.github/workflows/ci.yml` 加 odoo container job 跑 font_serve test-tag、gate PR、紀律 #15 應用。

### Sprint 115-120(階段 A 收口)

階段 A 剩餘:security 邊界廣域 / i18n / Sprint 78 Finding B / autonomous docs(architecture_decision / glossary / sprint50_66_retro)。

### Sprint 121+(進階段 B)

Phase 1-4 剩餘漏項 — 開始進到實際 source code change、L1 vitest + L2 VR 都要跑。

### 累積指標(Sprint 113 結尾、與 Sprint 112 結尾 byte-identical to production code)

- vitest 976 passed + 1 skipped(未跑、必然一致)
- VR mean 0.073191(未跑、必然一致)
- Odoo backend 21 passed(未跑、必然一致)
- Phase 0 100% / Phase 3 93% / 20 ADR / **18 條紀律 + 2 子原則**(#14.a + #14.b 顯式化)
- Sprint audit doc 112 → **113**
- 新增 roadmap doc 1 份

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/autonomous_roadmap.md       (本 sprint 新建、~170 行)
A  addons/dobtor_doc_editor/docs/sprint113_autonomous_roadmap.md  (本 audit doc)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (+7 行:§11 加一行、§6.5 加紀律 #14 子原則段)
M  /home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md  (+25 行:Sprint 113 段、原 Sprint 113+ 候選改為 Sprint 114+)
M  /mnt/d/work/.claude/logs/session_2026-05-16.md  (append Sprint 113 段)
```

無 production source code 變動、無 test 變動、無 fixture 變動、無 manifest 變動、無 ACL 變動。Sprint 112 結尾的 vitest / VR / backend test 數字必然保持。
