# Sprint 155 — Glossary catch-up to Sprint 154 era

**落地 / 2026-05-19**
**性質**:autonomous docs sprint（方向 C、Sprint 154 retro §8 三方向決策框架推薦選項之一）
**範圍**:`docs/glossary.md` Sprint 118 era → Sprint 154 era 同步;0 production code 變動
**關聯**:[sprint119_glossary_expansion_to_sprint118_era.md](sprint119_glossary_expansion_to_sprint118_era.md)、[sprint143_148_retro.md](sprint143_148_retro.md)、[sprint145_153_retro.md](sprint145_153_retro.md)

---

## 1. Hypothesis（假設）

Sprint 154 retro §8 三方向決策框架明示:
- 方向 A wire-up（Strategy C 折衷）→ **破 baseline byte-identical 連續紀錄**、需 user 同意
- 方向 B 等 user 決策 → **預設路徑**、解鎖階段 C / D
- 方向 C autonomous docs → **報酬遞減顯著**、Sprint 149 + 154 retro 已覆蓋大部分

但 retro §8 同時列出 docs 仍可做的具體工作:
- glossary 擴充（Sprint 145-153 新概念整合）
- 跨 cluster 對照表整合
- archive 老 sprint doc 索引

**Hypothesis**:`glossary.md` 上次更新是 Sprint 119（catch-up to Sprint 118 era）、距今 35 sprint 未同步。期間累積:
- 4 條紀律升正（#1.a / #1.b / #21 / #22）
- 1 條潛在子原則候選（#21.a）
- 8 個 capture-only parser 新模組（Sprint 145-153）
- 8 個 Process 模式（Sprint 119-154 era 新增）
- 整數里程碑（Phase 1 OOXML 90%）+ byte-identical 23 連

若不 catch-up、新貢獻者讀 glossary 會誤判紀律總數（仍寫 18 條 header）、不知 §8 Process 模式已從 8 條擴成 16 條、不知 8 個新 parser 模組存在;Sprint 119 揭示的「Sprint 119 vs Sprint 143 catch-up 規模對照」紀律 #14.a 案例會持續累積。

→ Sprint 155 應做 glossary 同步、避免 Sprint 119 揭示的反例（紀律確立 8 sprint 後才補）擴大。

---

## 2. Method（方法）

### 2.1 修改範圍

| 章節 | 修改類型 | 條目數 |
|---|---|---|
| § 0 索引 | 重寫:紀律數 / Process 模式數 / 子系統數 / vitest baseline 同步 | 1 整段 |
| § 1 VR 與衡量指標 | +2 新術語（byte-identical streak / Phase 1 整數里程碑）+ VR mean 加註 Sprint 145-153 第 23 連 | +2 條 |
| § 2.1 紀律表 | 標題 18 → 22 條 + Sprint 50-118 累積 → Sprint 50-154 累積;#1.b / #22 描述更新累計次數;末尾加 1 潛在子原則 #21.a 候選 | 1 標題 + 3 列 |
| § 3.1 核心模組 | +9 個 Sprint 137 / 145-153 新模組 | +9 條 |
| § 5 工具鏈 | vitest baseline 976 → 1331 + 1 skipped | 1 列 |
| § 8 Process 模式 | 從 8 → 16 條（+8 條 Sprint 119-154 era 新模式） | +8 條 |

### 2.2 工作原則

- 紀律 #14.a:本 sprint 不擴張 ADR / CONTRIBUTING、僅集中索引 glossary 同步;ADR-021 + CONTRIBUTING.md §5 已於 Sprint 117 / 143 即時同步、無 catch-up 需求
- 紀律 #18 PR-size:純 docs sprint、單一檔案 + 1 個 audit doc + 1 row roadmap;不混入其他任何工作
- 紀律 #18.a「根據計劃書繼續執行」是 scope 限制詞:本 sprint 不發明新模式、不延伸 retro、只把 Sprint 154 已 explicit 的內容轉到 glossary

### 2.3 不做的事

- ❌ 不做第 5 次 cluster retro（距 Sprint 154 retro 僅 1 sprint、違反 cluster checklist #8「短週期 retro 觸發 ≥ 5 sprint 間隔」）
- ❌ 不發明 #21.a 之外的潛在新紀律（mental model 主導應用、不機械式套用）
- ❌ 不擴張 §11.2 backlog 邊界（Sprint 154 retro 已明示 autonomous-friendly 真的耗盡）
- ❌ 不更新 architecture_decision.md / CONTRIBUTING.md（兩者已 Sprint 117 / 143 同步、無 lag）

---

## 3. Verification（驗證）

### 3.1 三層 SOP

| 層 | 狀態 | 說明 |
|---|---|---|
| L1 vitest | **跳過誠實聲明** | 0 production code 變動、無需跑 |
| L2 VR v14 | **跳過誠實聲明** | 0 parser / layout / render 變動、baseline byte-identical 維持第 23 連無需重跑 |
| L3 spot check | ✅ | glossary § 0-8 結構 / 連結 / 章節編號完整;§0 索引內外一致（§1 → 13 / §2 → 22 條 + 6 子 + 1 候選 + 1 潛在子 / §3 → 17 模組 / §8 → 16 條 Process）|
| L4 Odoo HttpCase | **跳過誠實聲明** | 純前端 docs、無 backend 變動 |

### 3.2 內外一致性檢查

- ✅ glossary § 2.1 標題與紀律表內容一致（22 條 + 6 子 + 1 候選 + 1 潛在子）
- ✅ glossary § 0 索引 § 3 子系統數 17 = 既有 9 + 新增 8（Sprint 137 NumberingCounterState + Sprint 145/146/147/148/150/151/152/153 八個 capture-only parser）
- ✅ glossary § 0 索引 § 8 Process 模式 16 條 = 既有 8 條（Sprint 113-118）+ 新增 8 條（Sprint 119-154 era）
- ✅ glossary § 5 vitest baseline 1331 與 Sprint 153 audit doc 結尾累積指標一致
- ✅ glossary § 1 byte-identical streak 23 連與 Sprint 153 audit doc 一致

---

## 4. Discipline（紀律）

### 4.1 應用本 sprint 的紀律

| 紀律 | 應用 |
|---|---|
| #14 即時 docs 同步 | **反例 catch-up**:glossary 上次 Sprint 119、距今 35 sprint 才同步;對照 Sprint 119（Sprint 118-era 即時跟）、Sprint 143（4 條紀律升正即時 catch-up CONTRIBUTING）|
| #14.a 集中索引 | glossary 是集中索引文件、§ 0 / § 2.1 / § 8 各自有獨立索引;本 sprint 確保各段內外一致 |
| #18 PR-size + scope-down | 單一檔案 + 6 個明確 § 段更新 + audit doc + roadmap 1 row;不混入 ADR / CONTRIBUTING / retro |
| #18.a「根據計劃書繼續執行」 | 本 sprint 不發明新紀律、不擴新 retro、僅 catch-up |
| #22 probe before action | Sprint 154 retro §8 三方向決策框架 = 本 sprint 的 probe;預設方向 C autonomous docs、glossary catch-up 是 retro §8 推薦的具體工作之一 |

### 4.2 揭示 / 候選

- 紀律 #14.a **第 2 次反例 catch-up**(35 sprint lag、比 Sprint 119 的 8 sprint lag 更嚴重)、揭示應建立「**集中索引同步檢查**節律」:每 5 cluster retro 後 1 sprint 強制 glossary catch-up（候選紀律 #14.b 子原則、Sprint 156+ 跨類型驗證可升正）
- 但本 sprint 不立即升正、留待 Sprint 156+ 觀察是否 user 介入打斷 cluster 節律

---

## 5. Result（結果）

### 5.1 檔案變動

```
M  addons/dobtor_doc_editor/docs/glossary.md
  - § 0 索引段:+1 行更新註記、§ 1/2/3/8 數字同步
  - § 1 VR 與衡量指標:+2 新術語 + 1 條既有更新
  - § 2.1 紀律表:標題更新 + #1.b/#22 描述累計次數 + #21.a 潛在子原則候選
  - § 3.1 核心模組:+9 個 Sprint 137 + 145-153 新模組
  - § 5 工具鏈:vitest baseline 976 → 1331
  - § 8 Process 模式:從 8 → 16 條
A  addons/dobtor_doc_editor/docs/sprint155_glossary_catchup_to_sprint154.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 155 ✅)
```

### 5.2 三層 SOP 結果

- vitest **1331 passed + 1 skipped**(未跑、純 docs)
- VR mean **0.073191**(未跑、第 23 次連續 byte-identical 維持)
- Odoo backend local 31 passed(未跑、純前端 docs)
- glossary lines 220 → ~265(估算、+45 行)
- L3 spot check: § 0 索引 / § 2.1 / § 3.1 / § 5 / § 8 內外一致

### 5.3 累積指標

- 紀律 22 條 + 6 子 + 1 候選 + 1 潛在子原則(#21.a)
- ADR 22 個(無變動)
- Process 模式 16 條(Sprint 113-154 累計、+8 from Sprint 118-era)
- 核心模組 17 個(+8 capture-only parser + 1 NumberingCounterState、from Sprint 118-era 8 個)
- vitest baseline 1331 passed + 1 skipped
- VR mean baseline 0.073191(byte-identical 第 23 次連續)
- Phase 1 OOXML 90%(整數里程碑、Sprint 153 達成)
- Sprint audit doc 154 → **155**

---

## 6. 後續

### 6.1 Sprint 156+ 候選評估

Sprint 154 retro §8 + 本 sprint 同步後、Sprint 156+ 候選收斂為:

| 方向 | 評估 | 條件 |
|---|---|---|
| A. wire-up(Strategy C) | ⚠️ 需 user 同意破 baseline | user 顯式 GO |
| B. 等 user 決策 | ✅ 預設、無 token 消耗 | 三個決策模板已 ready |
| C-1. 跨 cluster 對照表整合 | ⚠️ 報酬遞減進一步 | retro §6 已有 Sprint 120/144/149/154 4 次對照表 |
| C-2. archive 老 sprint doc 索引 | ⚠️ 報酬中等 | 132 個 sprint doc、可建索引但價值有限 |
| C-3. **本 sprint glossary catch-up** | ✅ 已完成 | — |

→ 預期 Sprint 156 仍預設方向 B(等 user)、若 user 仍未回應、autonomous 可做 C-1 跨 cluster 對照表整合 OR 自然停。

### 6.2 紀律 #14.b 子原則候選追蹤

本 sprint 揭示「集中索引 35 sprint lag」、若 Sprint 156+ 再出現類似 lag 或反例（ADR / CONTRIBUTING / glossary 任一文件 ≥ 20 sprint 未同步），可升正:
- 紀律 #14.b 子原則候選:每 5 cluster retro 後 1 sprint 強制集中索引同步檢查

候選追蹤至 Sprint 158+。

---

## 7. File-level summary

```
M  addons/dobtor_doc_editor/docs/glossary.md  (+~45 行、6 個 § 段同步)
A  addons/dobtor_doc_editor/docs/sprint155_glossary_catchup_to_sprint154.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 155 ✅)
```

**淨 production code 變動 = 0**(pure docs sync)、glossary catch-up to Sprint 154 era、為 Sprint 156+ 必須改變方向(user 介入 OR autonomous 進一步遞減)提供清晰 baseline。
