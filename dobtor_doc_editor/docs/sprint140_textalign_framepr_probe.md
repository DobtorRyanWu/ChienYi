# Sprint 140 — textAlignment / framePr wire-up probe sprint（autonomous DEFER 決策）

**日期**:2026-05-18
**類型**:probe-only sprint(0 production code、純 docs + audit)
**規畫書對應**:§Phase 4.4「文件外觀正確性」剩餘 capture-without-consumer 收口評估
**前置 sprint**:Sprint 134(textAlignment + framePr capture)、Sprint 139(numbering wire-up cluster 完工)

---

## Hypothesis(驗證對象)

Sprint 138/139 audit §後續候選 A:

> textAlignment / framePr wire-up — Sprint 134 capture 後 100% 沒人消費、與 numbering 同類別「capture-without-consumer」結構性技術債

驗證:
1. textAlignment / framePr 在 fixture 中的使用分布?
2. canvas-editor / layout 對應評估 — 有 wire-up target 嗎?
3. 預期收益 vs 風險?

---

## Method

### 1. Scope 對齊(紀律 #18)

- 規畫書 Phase 4.4 剩餘 capture 收口
- Sprint 138/139 audit §後續候選 A
- 本 sprint scope = **probe-only**(0 production code、依紀律 #22 + Sprint 135 模式)
- 預估產出:1 個 audit doc + roadmap 更新 + commit

### 2. 紀律 #22 第 7 次正式應用 — probe 5 維度

#### 2.1 Fixture 使用分布

```bash
for f in tests/fixtures/*/*.docx; do
  cnt=$(unzip -p "$f" word/document.xml | grep -oc "w:textAlignment")
  [ "$cnt" -gt 0 ] && echo "$(basename $f): $cnt"
done
```

| 屬性 | Fixture | 出現次數 | 分布 |
|---|---|---|---|
| `<w:textAlignment>` | `04_with_image/06.環清表安全衛生抽查照片(再造)-(112.10.23.-10.27).docx` | 18 | center(全部)|
| | `04_with_image/06.環清表安全衛生抽查照片(再造)-(112.10.9.-10.13).docx` | 18 | center(全部)|
| | `04_with_image/6.環清表安全衛生抽查照片(再造)-(112.10.2.-10.6).docx` | 18 | center(全部)|
| | `04_with_image/6.環清表安全衛生抽查照片(再造)-(112.9.25.-9.29).docx` | 18 | center(全部)|
| | **覆蓋 4/42 fixture(~9.5%)** | | |
| `<w:framePr>` | `06_template/檢(試)驗管制(預設樣板).docx` | 2 | `hSpace=181 wrap=around vAnchor=text hAnchor=margin y=166` |
| | **覆蓋 1/42 fixture(~2.4%)** | | |

#### 2.2 canvas-editor 對應評估(mapper 路徑)

| 屬性 | IElement 對應 | 評估 |
|---|---|---|
| textAlignment="center" | **無** — IElement.d.ts 搜不到 vertical-align / baseline 屬性 | wire-up = no-op、需自訂 Renderer + IElement extension |
| framePr | **無** — canvas-editor 文字段落不支援浮動 frame | wire-up = no-op、屬 Phase 5+ floatTextBox 類別 |

#### 2.3 Layout 對應評估(Paginator + LineBreaker)

| 屬性 | Layout 對應 | 評估 |
|---|---|---|
| textAlignment="center" | LineBreaker baseline 固定 = `height × 0.8`(line 313)、無 paragraph-level vertical alignment 計算 | 可能 wire-up 為「`center` → baseline = height/2」、但影響微小且 LineBreaker 全域 baseline 約定變動 |
| framePr | **無** — Paginator 處理 inline paragraph + table、無浮動 paragraph 機制 | 屬 Phase 5+ scope、需與 floatTextBox 一起設計 |

#### 2.4 預期收益(若強行 wire-up)

| 屬性 | 預期 VR 改善 | 預期風險 |
|---|---|---|
| textAlignment | **微小**:4 fixture × center 影響照片+文字共行的 baseline、視覺差異 < 1pt(小於 pixelmatch resolution) | 中:LineBreaker 約定變動可能影響非 center fixture(全 38 fixture 未顯式設 textAlignment、預設 'auto') |
| framePr | **微小**:1 fixture × 2 framePr 段落、影響 floating 段落位置 | 高:Paginator 需新增浮動段落路徑、Sprint 110 模式風險 |

#### 2.5 Sprint 138/139 對照

| 對照 | numbering wire-up | textAlignment / framePr wire-up |
|---|---|---|
| canvas-editor 對應 | 簡單(emit 字串 + tab) | 無對應(需擴 IElement type) |
| Layout 對應 | 中等(buildParagraph 加 prefix Boxes) | 無對應或需重構 LineBreaker |
| Fixture 覆蓋率 | 8/42(19%) | textAlignment 4/42(9.5%)/ framePr 1/42(2.4%)|
| 預期 VR 收益 | 微小(+0.001pp Strategy C) | 更微小(無 paragraph-level 視覺差) |
| 紀律 #22 probe 階段建議 | GO(Sprint 137-139 已完成) | **DEFER**(本 sprint 結論) |

---

## Result

### Decision: DEFER A 候選(textAlignment / framePr wire-up)

**autonomous 決策依據**:

1. **canvas-editor 無對應**:mapper 路徑 wire-up = no-op、需擴 IElement type + 自寫 Renderer(屬 canvas-editor fork 級別變動、紀律 #18 PR-size 嚴重違反)
2. **Layout 對應微弱**:textAlignment 改 baseline 公式影響全域 38 fixture、framePr 屬 Phase 5+ floatTextBox 類別
3. **預期收益微小**:4+1 fixture × 視覺差 < 1pt < pixelmatch resolution
4. **紀律 #22 + Sprint 135 對照**:probe 找到「強行 wire-up 違反 #18 + 預期 < pixelmatch resolution」結論、應 defer

### 後續觸發條件(可重新評估的時機)

| 觸發 | Sprint | 動作 |
|---|---|---|
| 階段 C 重生 goldens 完成後 | 141-145 | numbering opt-in→opt-out 切換、可再 probe textAlignment 影響 |
| Phase 5 開工 floatTextBox 整合 | 146+ | framePr 可與 floatTextBox 一起設計(同類別) |
| canvas-editor 升級含 verticalAlign IElement | future | mapper 才有 wire-up target |
| user 手動指定 fixture | any | 若特定 fixture 視覺差確認 > 1pt 才 GO |

### 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**(0 code change、誠實聲明)|
| L2 VR v14 | **跳過**(同上)|
| L3 Spot check | 純 docs sprint、無 build 變動 |
| L4 Odoo backend | **跳過** |

---

## 紀律

### 紀律 #22 第 7 次正式應用(probe sprint)

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Probe 5 維度:
1. Fixture 使用分布(4/42 + 1/42、< 25% 覆蓋)
2. canvas-editor 對應(無)
3. Layout 對應(微弱 / 屬 Phase 5+)
4. 預期收益(< pixelmatch resolution)
5. Sprint 138/139 對照(明確差異)

→ Probe 結論:「強行 wire-up 違反 #18 + 預期 < pixelmatch resolution」、應 **DEFER**。

### 紀律 #18 守護

DEFER 是 #18 PR-size 守護的勝利:避免為 4+1 fixture 預估 < 1pt 視覺差、實作 IElement extension + canvas-editor fork(scope 爆炸)。

### 紀律 #4 應用(負面結果有結構價值)

> 負面結果 sprint 仍有結構價值;揭示隱性 assumption 是真實學習

Sprint 140 揭示:
1. **「capture-without-consumer」不等於「該 wire-up」**:Sprint 134 capture 是 correct(parser 完整性)、但 wire-up target 缺失才是真實 blocker
2. **Wire-up 可行性 = caller 端對應 × 預期收益 × 紀律 #18 PR-size 三維評估**:Sprint 137-139 numbering 三維皆過 → GO;Sprint 140 textAlignment / framePr 三維皆弱 → DEFER

### 提案紀律 #1.b 候選 v2 跨 sprint 驗證(第 6 次)

> spike 翻車必完整 revert byte-identical / 部分翻車 scope-down

Sprint 140 = **預防範例第 2 次**(Sprint 137 第 1 次):probe 主動 DEFER、避免實作後 revert。

跨 sprint 驗證進展:
- 110 全 revert / 136 全 revert / 137 預防 / 138 實作 / 139 Strategy C / **140 預防 DEFER**
- 6 次驗證、3 類型(全 revert × 2 / 預防 × 2 / 實作 + 折衷 × 2)
- → 紀律 #1.b 候選 v2 完整光譜已覆蓋、Sprint 141+ 可正式升正式紀律 #1.b

---

## 後續

### Sprint 141 候選(autonomous 推薦)

接續 user 指示「逐步執行 abc」、A 已 DEFER → 進入 B(階段 C 重生 goldens probe):

| 候選 | 預期收益 | 風險 |
|---|---|---|
| **B-probe. 階段 C 重生 goldens 環境設置 probe**(autonomous_roadmap 原排 Sprint 136-138)| 高(換 metric anchor、Sprint 139 numbering opt-in→opt-out 解鎖)| 中(需 Word/OnlyOffice/LibreOffice headless 環境)|
| C. Phase 5 開工(OMML / SmartArt / 追蹤修訂、autonomous_roadmap Sprint 146-160)| 高(規畫書 §11.1 進階功能)| 高(大 scope、單 sprint 做不完)|

**autonomous 推薦 Sprint 141 = B-probe**(階段 C 環境 probe):
1. user 指示「逐步執行 abc」,順序 A → B → C
2. Sprint 141 = probe 評估環境(LibreOffice / OnlyOffice headless / wkhtmltopdf 可用性)
3. 若環境就緒 → Sprint 142+ 進 B 實作
4. 若環境受限 → 寫 audit defer 進入 C

---

## Sprint 140 結尾累積指標

- vitest **1176 passed + 1 skipped**(未動、純 probe)
- VR mean **0.073191** / failed 0 / compared 126(未動、純 probe、**第 15 次連續 byte-identical 維持**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 4 Style **90%**(未變、Phase 4.4 textAlignment/framePr capture-without-consumer 已 probe DEFER)
- 21 ADR / 紀律 **21 條** + 6 子 + **2 候選**(#20 集中索引、**#1.b 候選 v2 第 6 次跨 sprint 驗證、3 類型完整光譜**)
- Sprint audit doc 139 → **140**
- 階段 B cluster 「numbering wire-up」(137-138-139)完成 + 階段 B probe「Phase 4.4 wire-up」(140)結論 = DEFER

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint140_textalign_framepr_probe.md  (本 probe audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 140 ✅ DEFER)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 4.4 DEFER 註記)
```

**淨 production code 變動 = 0**(pure probe + audit)、Phase 4.4 wire-up DEFER 結論 + 後續觸發條件明確化、紀律 #1.b 候選 v2 6 次跨 sprint 驗證完整光譜。下個 sprint 進 B(階段 C 重生 goldens probe)。
