# Sprint 142 — Phase 5 開工 scope probe sprint(autonomous DEFER user GO)

**日期**:2026-05-18
**類型**:probe-only sprint(0 production code、純 docs + audit)
**規畫書對應**:§5 Phase 5 進階功能(2-3 個月、6 子功能)+ autonomous_roadmap §階段 D(Sprint 146-160 原排)
**前置 sprint**:Sprint 140(A DEFER)、Sprint 141(B DEFER user GO)、user 指示「逐步執行 abc」C 階段

---

## Hypothesis(驗證對象)

autonomous_roadmap §階段 D + 規畫書 §5 Phase 5:

> Phase 5:進階功能(OMML 3-4 週 / SmartArt 1-2 月 / Charts 1-2 月 / 追蹤修訂 1 週 / 註解 1 週 / 浮水印 3-5 天)

驗證:
1. 現有 fixture 對 Phase 5 6 子功能的覆蓋率?
2. autonomous 可單獨完成哪些子功能?(無 user fixture 仍可有意義 wire-up)
3. 預期收益 vs 工時 vs ROI?
4. autonomous GO 還是 user GO?

---

## Method

### 1. Scope 對齊(紀律 #18)

- 規畫書 §5 Phase 5 + autonomous_roadmap §階段 D 候選
- 本 sprint scope = **probe-only**(0 production code、依紀律 #22 + Sprint 135/140/141 模式)

### 2. 紀律 #22 第 9 次正式應用 — Fixture 覆蓋 probe

```bash
for f in tests/fixtures/*/*.docx; do
  unzip -p "$f" word/document.xml | grep -oc "<m:"     # OMML
  unzip -p "$f" word/document.xml | grep -oc "<w:ins"  # 追蹤修訂
  ...
done
```

#### 結果 — **6 子功能 0 fixture 覆蓋**

| Phase 5 子功能 | XML 標籤 | Fixture 命中 | 覆蓋率 |
|---|---|---|---|
| 5.1 OMML(數學公式)| `<m:oMath>` 等 m: 命名空間 | **0/42** | **0%** |
| 5.2 SmartArt | `diagram*.xml` 或 SmartArt | **0/42** | **0%** |
| 5.3 Charts | `chart*.xml` part | **0/42** | **0%** |
| 5.4 追蹤修訂 | `<w:ins>` / `<w:del>` | **0/42** | **0%** |
| 5.5 註解 | `<w:commentRangeStart>` | **0/42** | **0%** |
| 5.6 浮水印 / 背景 | `<w:background>` / watermark | **0/42** | **0%** |

**重大結論**:當前 42 fixture 完全不含任何 Phase 5 feature → 即使實作、VR pipeline 視覺收益 = **0**。

### 3. autonomous 可獨立完成度評估

| 子功能 | 規畫書估時 | autonomous 獨立可行性 | 評估 |
|---|---|---|---|
| 5.1 OMML | 3-4 週 | **低**:需 KaTeX/MathJax 整合(大依賴 + bundle size)| 推薦 user 決策 |
| 5.2 SmartArt | 1-2 個月 | **低**:fallback 機制 + 5 種 layout 原生渲染、scope 巨大 | 推薦 user 決策 |
| 5.3 Charts | 1-2 個月 | **低**:同 5.2 | 推薦 user 決策 |
| 5.4 追蹤修訂 | 1 週 | **高**:parser + UI 顯示、scope 可控、無外部依賴 | autonomous 可單獨 GO |
| 5.5 註解 | 1 週 | **高**:parser + side panel、scope 可控 | autonomous 可單獨 GO |
| 5.6 浮水印 | 3-5 天 | **中**:VML 浮水印 parser + 背景 layer renderer | autonomous 可單獨 GO |

### 4. ROI 評估

| 子功能 | 工時(sprint)| 預期 VR 改善 | unit test 可獨立? | ROI 排序 |
|---|---|---|---|---|
| 5.6 浮水印 | 1 | 0(無 fixture)| ✅ | 1 |
| 5.4 追蹤修訂 | 1-2 | 0(無 fixture)| ✅ | 2 |
| 5.5 註解 | 1-2 | 0(無 fixture)| ✅ | 3 |
| 5.1 OMML | 6-8 | 0(無 fixture)| ✅ | 4 |
| 5.2 SmartArt | 8-15 | 0(無 fixture)| ✅ | 5 |
| 5.3 Charts | 8-15 | 0(無 fixture)| ✅ | 6 |

**所有 6 個子功能的 VR ROI 都是 0(因 fixture 0 覆蓋)**。Unit test ROI 是「parser 完整性提升 + AST 屬性覆蓋」、可量化但不在 VR 系統中體現。

### 5. autonomous GO vs user GO 框架

#### autonomous 可單獨 GO(無需 user fixture)
- **5.6 浮水印**(scope 最小、3-5 天工時)
- **5.4 追蹤修訂**(scope 小、1 週工時)
- **5.5 註解**(scope 小、1 週工時)

但即使 autonomous GO、缺乏 fixture 驗證真實視覺收益、屬於「parser 寫好等 fixture」模式。

#### 必須 user GO
- **5.1 OMML / 5.2 SmartArt / 5.3 Charts**:scope 巨大、依賴選擇、優先順序需 user 決定
- **任何 5.x 開工**:user 決策「現在優先 Phase 5 vs 階段 C 重生 goldens vs 其他」

---

## Result

### Decision: autonomous DEFER 全 Phase 5 至 user GO

**autonomous 決策依據**:

1. **Fixture 0 覆蓋**:6 子功能無一在 42 fixture 中、VR 系統無法驗證任何 Phase 5 wire-up 的真實視覺收益
2. **user 優先順序未知**:Phase 5 6 子功能順序、規畫書未強制、應由 user 業務需求決定(如 ChienYi 監造系統 = 追蹤修訂 + 註解優先 vs OMML 不需)
3. **fixture 取得 = user 行動**:autonomous 無法生成「真實 user docx 含 Phase 5 features」、需 user 提供範本
4. **autonomous_roadmap 階段 D 排在階段 C 之後**:Sprint 146-160 在重生 goldens 之後、本 sprint 跨階段執行違反 roadmap 既有順序

### Sprint 142 產出

| 產出 | 用途 |
|---|---|
| 本 audit doc | Phase 5 scope 評估 + 6 子功能 ROI + autonomous DEFER 決策 + user 決策依據 |
| roadmap 階段 D Phase 5 註記 | 標 「fixture 0 覆蓋、待 user GO + fixture 補充」|
| 規畫書 §0.1 標頭 | 同步當前狀態 |

### 後續觸發條件

| 觸發 | 動作 |
|---|---|
| user 提供 1+ 個含 Phase 5 feature 的 docx fixture | autonomous 可開始對應子功能 implementation |
| user 明確指定「先做 X(如追蹤修訂)」 | autonomous 進入 Sprint 143 = X 的 Phase 5 sub-sprint |
| user 表示「先回頭做階段 C 重生 goldens」 | 跳回 Sprint 141 §後續、autonomous 等 user GO |
| user 表示「先做 A 候選(textAlignment)」 | 重新評估 Sprint 140 DEFER(可能仍 DEFER、或 user 接受 < 1pt 視覺差)|

---

## 紀律

### 紀律 #22 第 9 次正式應用(probe sprint)

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Sprint 142 揭示:
1. **規畫書 §5 Phase 5 各子功能估時 ≠ ROI**:估時是「實作工時」、ROI 取決於 fixture 覆蓋 + user 優先順序
2. **「fixture 全 0 覆蓋」是結構性 blocker**:不是工時問題、是驗證對象缺失問題
3. **autonomous_roadmap §階段 D Sprint 146-160 順序前提 = 階段 C 完成**:跨階段執行破壞 roadmap 一致性

### 紀律 #18 守護案例(連續第 3 次)

Sprint 140(textAlignment DEFER)→ 141(階段 C DEFER user GO)→ **142(Phase 5 DEFER user GO)** 三連 probe + DEFER 揭示:autonomous 已到達**規畫書既有 backlog 邊緣**、剩餘候選都需要 user 端輸入(fixture / 優先順序 / baseline 變動同意)。

### 紀律 #1.a 16 連軌道意識(維持)

Sprint 140/141/142 全 probe-only、0 production code → 紀律 #1.a 仍是 **16 連 byte-identical**(三個 probe sprint 不破軌道)。

### 提案紀律 #1.b 候選 v2 第 8 次跨 sprint 驗證

| Sprint | 類型 |
|---|---|
| 110 | 全 revert |
| 136 | 全 revert |
| 137 | 預防(probe scope-down)|
| 138 | 實作(probe 確認可行)|
| 139 | Strategy C 折衷 |
| 140 | 預防 DEFER(A 候選)|
| 141 | 預防 DEFER user GO(B 候選)|
| **142** | **預防 DEFER user GO(C 候選、fixture 0 覆蓋)** |

8 次跨 sprint、3 類型完整光譜 + 「需 user GO 的預防 DEFER」次類型 3 次驗證(140/141/142)。**紀律 #1.b 候選 v2 已穩定可升正式紀律**:

```
紀律 #1.b(候選升正式 candidate):
  Spike 實作後遇結構性問題、必須 scope-down 或完整 revert byte-identical、
  不嘗試「微調 + retry」(避免 fitting noise);
  若 scope-down 維度跨越 autonomous 決策邊界(換 baseline / 大依賴 / user 業務優先)、
  則 probe-only sprint + DEFER user GO + 完整推薦路徑準備就緒。
```

跨 8 sprint × 3 類型驗證、可考慮 Sprint 143+ 第 9 次直接升正式 #1.b。

---

## 後續

### Sprint 143 候選

user 指示「逐步執行 abc」abc 三輪皆完成 probe:
- A: Sprint 140 textAlignment / framePr autonomous DEFER
- B: Sprint 141 階段 C 重生 goldens autonomous DEFER user GO
- C: Sprint 142 Phase 5 autonomous DEFER user GO

**autonomous 推薦 Sprint 143 候選**:

| 候選 | 預期 | 理由 |
|---|---|---|
| **D-1. 紀律 #1.b 正式升正格 + glossary 同步** | 1 sprint docs-only | 跨 8 sprint 驗證已成熟、紀律維護需求 |
| D-2. Sprint 113-118 sprint cluster retro (autonomous 可做) | 1 sprint docs-only | 沿用 Sprint 120 retro 模式 |
| D-3. 等 user 決策 | 0 sprint | session 自然停止點 |

**autonomous 推薦 D-1**(紀律 #1.b 升正式 + glossary 同步):
- 符合 Sprint 120 retro / Sprint 123 紀律 #1.a 升正式模式
- 純 docs sprint、無 production code 變動、不破 baseline
- 規範化已驗證 8 次的候選紀律、未來 sprint 引用方便

---

## Sprint 142 結尾累積指標

- vitest **1176 passed + 1 skipped**(未動、純 probe)
- VR mean **0.073191** / failed 0 / compared 126(未動、**第 15 次連續 byte-identical 維持**、含 140/141/142 三個 probe sprint)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 4 Style **90%** / Phase 5 **0%**(fixture 0 覆蓋、未變)
- 21 ADR / 紀律 **21 條** + 6 子 + **2 候選**(#20 集中索引、**#1.b 候選 v2 第 8 次跨 sprint 驗證、可升正式**)
- Sprint audit doc 141 → **142**
- 階段 A 完工 / 階段 B 完工 / 階段 C user GO 待定 / 階段 D user GO 待定(fixture 0 覆蓋)

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint142_phase5_scope_probe.md  (本 probe audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 142 ✅ probe DEFER user GO + 階段 D 註記)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 5 fixture 0 覆蓋註記)
```

**淨 production code 變動 = 0**(pure probe + audit)、Phase 5 6 子功能 fixture 0 覆蓋揭示 + autonomous DEFER user GO 完整 rationale + 4 個後續觸發條件、紀律 #1.b 候選 v2 第 8 次跨 sprint 驗證可升正式。Sprint 143 推薦 = 紀律 #1.b 正式升正格(docs-only)、user 介入點 = Phase 5 優先順序決策 + fixture 提供。
