# Sprint 143-148 方法論回顧 — 紀律升正 + Phase 1 capture-only 四連模式成熟

**Sprint 149 落地 / 2026-05-18**
**範圍**:Sprint 143(紀律 #1.b 升正)→ Sprint 148(WebSettings capture)、6 sprint
**性質**:方法論 retro。和 [sprint121_142_retro.md](sprint121_142_retro.md)(22 sprint)互補,本文聚焦 6 sprint 內三個成熟模式 explicit。

---

## 0. 為什麼需要這份 retro

Sprint 144 retro(範圍 Sprint 121-142、22 sprint)留下三個 modes:
- probe-only sprint 例行化
- Strategy C 折衷模式
- autonomous 邊界揭示

Sprint 143-148 在更小範圍(6 sprint)內出現三個成熟模式、與 Sprint 144 retro 互補:

1. **紀律 #1.b 升正**(Sprint 143)— catch-up 集中索引,展示「紀律維護週期」
2. **Phase 1 capture-only 四連模式**(145-148)— 從零星 capture 變成系統化 cluster
3. **retro-after-retro 節奏**(Sprint 144 之後 Sprint 149 短週期 retro)— 6 sprint vs 24 sprint 對照

Sprint 149 把這三個模式 explicit,對應 Sprint 144 retro 提出的「未來 cluster checklist」實際應用。

---

## 1. 紀律 #1.b 升正 + catch-up 集中索引(Sprint 143)

### 1.1 升正歷程

紀律 #1.b 候選軌道:

| Sprint | 類型 | 累積驗證次數 |
|---|---|---|
| 110 | 全 revert | 1 |
| 136 | 全 revert | 2 |
| 137 | 預防 scope-down | 3 |
| 138 | 實作(probe 確認可行)| 4 |
| 139 | Strategy C 折衷 | 5 |
| 140 | 預防 DEFER | 6 |
| 141 | 預防 DEFER user GO | 7 |
| 142 | 預防 DEFER user GO | 8 |
| **143** | **正式升正** | **8 次跨 sprint × 3 類型完整光譜** |

升正定義(摘 CONTRIBUTING.md §5):

```
紀律 #1.b(Sprint 143 升正):
  Spike 後遇結構性問題、必須 scope-down 或完整 revert byte-identical、
  不嘗試「微調 + retry」(避免 fitting noise)。

  scope-down 維度光譜:
  - 全 revert(100%)= Sprint 110/136 模式
  - 部分 revert(1 維度)= Sprint 139 Strategy C 模式
  - 預防 DEFER(probe 階段 100%)= Sprint 137/140/141/142 模式
```

### 1.2 catch-up 集中索引

Sprint 143 同時補 4 條紀律(Sprint 121-142 期間累計升正但未即時同步):
- #1.a(Sprint 123 升正)
- #21(Sprint 131 升正)
- #22(Sprint 135 升正)
- #1.b(Sprint 143 升正)

紀律總數變動:18 → **22 條**(+4)。

### 1.3 教訓 — 「即時 catch-up」vs「事後 batch catch-up」

對照組:
- Sprint 119 對 Sprint 110-118 期間做 glossary catch-up(9 sprint 間隔)
- Sprint 143 對 Sprint 121-142 期間做 CONTRIBUTING + glossary catch-up(**22 sprint** 間隔)

→ Sprint 143 catch-up 規模比 Sprint 119 大 2.5x、揭示「紀律 #14.a 集中索引應即時同步、避免大批 catch-up」的反例價值。

未來改進(Sprint 149+ 適用):紀律升正同 sprint 更新 CONTRIBUTING/glossary,不要拖到下個專屬 docs sprint。

---

## 2. Phase 1 capture-only 四連模式(Sprint 145-148)

### 2.1 四連清單

| Sprint | Part | Elements | Test | Phase 1 進度 | 特殊 |
|---|---|---|---|---|---|
| 145 | footnotes + endnotes | 3 | 12 | 80% → 82% | 同 parser 雙 root |
| 146 | settings | 9 | 27 | 82% → 84% | probe 升級為跨 part 統計 |
| 147 | fontTable | 7 | 20 | 84% → 86% | 與 FontMetricsAdapter 互補 |
| 148 | webSettings | 5 | 14 | 86% → 87% | **紀律 #18 scope-down 案例** |
| **合計** | **5 parts** | **24 elements** | **73 test** | **+7pp** | **VR 第 16-19 連** |

### 2.2 模式架構(可複製)

每個 capture-only sprint 採同一結構:

```
1. probe(紀律 #22)
   - fixture 覆蓋率(跨 fixture 統計)
   - 單 part 內 elements 結構統計
   - 列舉值列表 + 出現頻率

2. 新模組 static/src/core/ooxml/<name>/
   - <Name>Parser.ts:parse(xml) → DocumentXxx
   - index.ts:export 公開 API
   - 紀律 #21 空集合不掛 key
   - 4-7 個防禦邊界(undefined / 空 / XML 失敗 / 未知列舉值降級)

3. types.ts 擴
   - 新 interface(field 全 optional、紀律 #21)
   - DocumentNode 加 1 新欄位

4. OoxmlParser orchestrator 串接
   - 新 REL_TYPE_XXX 常數
   - 新 parser 實例(class member)
   - 新 Step N.X capture
   - 新 collectXxx helper

5. 5 個既有 DocumentNode constructor patch
   - DocumentParser.ts(production)
   - 4 個 test fixture(AstCache / IdbAstCache / ParagraphStyleMerger / ToCanvasEditor)

6. 新 unit test 檔
   - 5-7 組 test:基本欄位 / 列舉 / 防禦 / 整合
   - 12-27 test per sprint

7. 三層 SOP
   - L1 vitest 全跑
   - L2 VR v14(預期 byte-identical)
   - L3 spot check(TypeScript build)
   - L4 backend 跳過

8. 三檔文件
   - sprint{N}_{name}_capture.md(audit)
   - autonomous_roadmap.md(+1 列)
   - dobtor_doc_editor_高保真匯入開發規劃.md(標頭)

9. commit「Sprint N: <name>.xml capture-only Parser」
```

### 2.3 模式收益

| 維度 | 收益 |
|---|---|
| **Phase 1 進度** | +7pp 在 4 sprint 內(平均 1.75pp/sprint)|
| **Test 增量** | +73 test(平均 18 test/sprint)|
| **VR 連續性** | 維持 byte-identical 第 16-19 連 |
| **紀律 #1.a 驗證** | 連 4 個 capture-only 不破 baseline、模式安全性已證 |
| **Wire-up 鋪路** | 5 個 part 都有 future wire-up 候選(留 hook)|
| **PR-size 守住** | 平均 ~200 行 code + ~150 行 test(紀律 #18 範圍內)|

### 2.4 「儀式性 part 三連完成」可用 scope-down(Sprint 148)

紀律 #18 新案例:

Sprint 147 §後續推薦 webSettings 完成 part 三連、但 probe 揭示:
- webSettings.xml 主要是 docx 匯出 HTML 時 hint
- import / layout / render 完全不消費
- divs 結構深層、ROI ≈ 0

選擇:
- A. 完整解析 divs 內部巢狀 → 違反紀律 #18(為 closure 而 over-parse)
- **B. scope-down 至 4 toggle + hasDivs boolean → 紀律 #18 守護**(本 sprint 選擇)

→ Sprint 148 成為紀律 #18 新案例:「儀式性 part 收尾不必為 closure 而 over-parse、scope-down 是工具」。

### 2.5 適用後續(Sprint 150+ wire-up 階段)

Phase 1 capture 已完整(80% → 87%)、剩下:
- stylesWithEffects.xml(6/42、legacy IE compat、defer)

下一個自然方向 = **wire-up 階段**(Phase 4 numbering wire-up 模式延伸):
- settings.defaultTabStop → BoxBuilder \\t(中改善、可能破 VR)
- settings.characterSpacingControl → LineBreaker CJK 壓縮策略(高改善、可能破 VR 大)
- fontTable.altName → FontMetricsAdapter fallback chain(中改善、與 Sprint 60-65 結合)
- footnotePr → footnote wire-up 配套(需 user 提供 footnoteReference fixture)

---

## 3. retro-after-retro 節奏(Sprint 149 / Sprint 144 / Sprint 120)

### 3.1 三次 retro 對照

| Retro Sprint | 範圍 | 間隔 | 主題 |
|---|---|---|---|
| Sprint 120 | Sprint 50-66(17 sprint)| 大週期 | cache 五連發 + FontMetricsAdapter 方法論 |
| Sprint 144 | Sprint 121-142(22 sprint)| 大週期 | probe-only 例行化 / Strategy C / autonomous 邊界 |
| **Sprint 149** | **Sprint 143-148(6 sprint)** | **小週期** | **紀律升正 + Phase 1 四連模式成熟 + retro 節奏對照** |

### 3.2 短週期 retro 的價值

Sprint 144 cluster checklist §6 建議「cluster 紀律新升正 → 同 sprint 更新集中索引」(紀律 #14.a 強化)、但 Sprint 145-148 未升正新紀律、所以 catch-up 需求 = 0。

但 Sprint 143-148 仍有方法論價值需提煉:
- Phase 1 capture-only 模式從零星變系統化(145-148 是「複製貼上」的 archetype)
- 紀律 #18 scope-down 新案例(Sprint 148)
- catch-up 規模對照(Sprint 119 vs Sprint 143)

→ **短週期 retro 在「cluster 模式成熟」時最有價值**、不必等大週期。

### 3.3 retro 觸發條件(從三次 retro 萃取)

| 觸發 | 對應 Sprint |
|---|---|
| cluster 5+ sprint 內三個新模式出現 | Sprint 120 / 144 |
| cluster 5+ sprint 內單一模式重複 ≥ 3 次成熟 | **Sprint 149**(capture-only 四連) |
| autonomous 邊界遇到、user 介入點累積 | Sprint 144 |
| 紀律升正 + catch-up 同 sprint 內完成 | Sprint 143 |
| 純 mechanical / 維護工作累積 ≥ 5 sprint | (未來)|

---

## 4. 數據總覽(Sprint 143-148)

### 4.1 累計指標變動

| 指標 | Sprint 142 終點 | Sprint 148 終點 | 變動 |
|---|---|---|---|
| vitest | 1176 + 1 skipped | 1249 + 1 skipped | **+73** |
| VR mean | 0.073191 | 0.073191 | **0(第 19 連 byte-identical)** |
| Phase 1 OOXML | ~80% | **87%** | **+7pp** |
| Phase 4 Style | 90% | 90% | 0(本 cluster 不動 Phase 4)|
| 正式紀律 | 21 條(未同步)| 22 條(集中索引同步) | +1(實質升正 4 條)|
| Sprint audit doc | 142 | 148 | +6 |

### 4.2 Sprint 類型分布(6 sprint)

| 類型 | 數量 | 比例 |
|---|---|---|
| Code change(capture-only)| 4 | 67% |
| Docs(retro + 紀律升正)| 2 | 33% |
| Revert / Probe-only / Mechanical | 0 | 0% |

→ Sprint 143-148 是「**穩定生產期**」:純 code 累積 + 紀律維護、無翻車無探索。

### 4.3 紀律驗證

| 紀律 | 應用次數(Sprint 143-148)| 累計次數(歷史總計)|
|---|---|---|
| #1.a(parser / layout 跑全 VR)| 4 次 | 19 次 |
| #21(optional 空集合不掛 key)| 4 次大量應用 | 9 次 |
| #22(probe sprint)| 4 次(probe + scope-down 升級)| 13 次 |
| #1.b(scope-down 或 revert)| 4 次正面驗證 | 12 次 |
| #18(PR-size + scope-down 新案例)| 持續、Sprint 148 新案例 | - |
| #14.a(集中索引即時同步)| 反例驗證(Sprint 143 catch-up)| - |

---

## 5. 跨 retro 對照

| 維度 | Sprint 120(50-66)| Sprint 144(121-142)| **Sprint 149(143-148)** |
|---|---|---|---|
| 範圍 | 17 sprint | 22 sprint | **6 sprint** |
| 主要主題 | cache / FontMetricsAdapter | wire-up + autonomous 邊界 | **capture-only 模式成熟** |
| 翻車次數 | 1(Sprint 57 memoize)| 1(Sprint 136 isInTableCell)| **0** |
| 紀律生成 | 6 條(#1-#6)| 4 條升正 | **0 條(維持 22 條)** |
| autonomous 邊界 | 未碰到 | 第一次碰到 | **延續 user 介入點清單** |
| 新模式 | Stable platform → 高風險改造 / Probe-Negative-Positive-Delta-Drift-Promote | probe-only 例行化 / Strategy C / autonomous 邊界 explicit | **capture-only 四連 archetype + scope-down 新案例 + retro 短週期觸發** |

→ Sprint 143-148 是「**模式收成期**」:Sprint 121-142 的方法論被實際應用、產生 +73 test / +7pp Phase 1 進度,但無新探索。

---

## 6. 未來 cluster checklist 更新(從 Sprint 143-148 補強)

新加 2 項到 Sprint 144 retro §7 既有 6 項:

```
原 6 項:
[ ] 1. 規畫書 scope 對齊?(紀律 #18)
[ ] 2. capture-without-consumer? → wire-up 三段式評估
[ ] 3. mental model 確定? → 不確定 → probe sprint(紀律 #22)
[ ] 4. probe 結論:autonomous GO / DEFER / user GO?(autonomous 邊界 3 維度)
[ ] 5. 實作後 VR:byte-identical / 改善 / 退化? → 退化走紀律 #1.b
[ ] 6. cluster 紀律新升正? → 同 sprint 更新集中索引(紀律 #14.a)

Sprint 149 新加:
[ ] 7. 「儀式性收尾」是否該 scope-down?(紀律 #18 + Sprint 148 案例)
       - 為了 cluster closure 而 over-parse → 違反 #18
       - scope-down 至「最小可用」+ 留 hook 給 future = 正解
[ ] 8. cluster 模式重複 ≥ 3 次成熟? → 寫短週期 retro(紀律 #14)
       - 不必等大週期(20+ sprint)、6 sprint 也可寫
       - 重點是「模式 archetype 提煉」不是「累積數據統計」
```

---

## 7. 結論

Sprint 143-148 6 sprint 累積:**紀律升正 + Phase 1 capture-only 四連模式成熟 + 紀律 #18 scope-down 新案例**。+73 test / +7pp Phase 1 進度 / 第 16-19 連 byte-identical / 0 翻車 / 0 探索。

下個 cluster(Sprint 150+)選項:
- **wire-up 階段**(Phase 4 numbering 模式延伸到 Phase 1 capture 後續):會破 baseline、走 Strategy C
- **autonomous 持續探索 §11.2 backlog**:已耗盡明列項目、需找新切入點
- **等 user 決策**(階段 C / Phase 5 / textAlignment / wire-up GO 等)

Sprint 144 已 explicit autonomous 邊界、Sprint 149 確認 Phase 1 capture 收尾、剩下幾乎都需 user 介入。**autonomous-friendly 工作累積已近上限**、後續 sprint 容量受限。

---

## Sprint 149 結尾累積指標

- vitest **1249 passed + 1 skipped**(未動、純 docs)
- VR mean **0.073191** / failed 0 / compared 126(未動、**第 19 次連續 byte-identical 維持**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML 87%(未變)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 148 → **149**

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint143_148_retro.md  (本 retro doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 149 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

**淨 production code 變動 = 0**(pure docs retro)、Sprint 143-148 三個成熟模式 explicit、cluster checklist 補強 2 項、為 Sprint 150+ 提供「進入 wire-up vs 等 user vs 持續 capture」決策框架。
