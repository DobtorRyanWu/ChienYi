# Sprint 153 — styles.xml `<w:latentStyles>` capture-only(autonomous-friendly §11.2 backlog 最後一塊)

**落地 / 2026-05-19**
**性質**:Phase 1 capture-only、styles/ 子目錄延伸(與 StyleResolver 平行運作)
**範圍**:styles.xml `<w:latentStyles>` + `<w:lsdException>`(OOXML §17.7.4.6)

---

## Hypothesis

Sprint 152 §後續 E-15:latentStyles capture-only 是「§11.2 backlog 剩下唯一適合 capture-only 的切入點」。其他剩餘候選:
- `stylesWithEffects.xml`:legacy IE compat(retro 明示 defer)
- `customXml/item*.xml`:SDT databind(Sprint 124 已 unwrap、wire-up 才用)
- `theme1.xml` 子元素:結構極複雜不適 capture-only

**假設**:
1. latentStyles 在 41/42 fixture(平均 ~147 lsdException、Word 預設骨架)
2. 與 StyleResolver 平行不衝突(StyleResolver 處理 `<w:style>`、本 parser 處理 `<w:latentStyles>`、互不影響 active styles)
3. capture-only 不破 VR baseline、第 23 連 byte-identical
4. 紀律 #18 scope-down 嚴守:Map<name, exception> 結構、不展開為陣列

---

## Method

### 9-step archetype 應用(沿用 Sprint 145-152)

**Step 1 - probe**:
- styles.xml 大小 ~21KB(typical Word 14 預設骨架)
- latentStyles root 屬性:5 個 default toggle/integer + 1 個 count
- lsdException 屬性:name(必、key)+ 5 個 optional(locked / uiPriority / semiHidden / unhideWhenUsed / qFormat)
- 樣本(會議記錄 fixture):147 lsdException 全部用 w: prefix

**Step 2 - 新檔** `static/src/core/ooxml/styles/LatentStylesParser.ts` +156 行:
- `parse(xml)` 入口、與 StyleResolver 平行
- 5 個 toggle 用 OOXML 寬鬆規格("0"/"false" = false、否則 true)
- 嚴格整數(uiPriority / count)`/^-?\d+$/`
- 紀律 #21:屬性不存在 → 不掛 key、無 name 的 exception 跳過
- 重複 name → 後者覆蓋前者(Map.set 行為、不 throw)
- 4 個防禦邊界(undefined / 空 / 壞 XML / 無 latentStyles 元素)

**Step 3 - types.ts** +50 行:
- `LatentStyleException` interface(5 optional fields、紀律 #21)
- `DocumentLatentStyles` interface(6 root defaults + exceptions Map)
- DocumentNode 1 新欄位 `latentStyles: DocumentLatentStyles`

**Step 4 - OoxmlParser orchestrator** +8 行:
- `import { LatentStylesParser }`
- `private latentStylesParser = new LatentStylesParser()`
- Step 3.1:`const latentStyles = this.latentStylesParser.parse(stylesXml)`(重用既有 stylesXml 變數、紀律 #14 DRY)
- DocumentNode 構造加 `latentStyles`

**Step 5 - 5 個既有 DocumentNode constructor patch**(+5 行):
- DocumentParser.ts(makeEmpty 用 `{}`)
- 4 個 test fixture 同模式

**Step 6 - 新 unit test** `tests/unit/LatentStylesParser.test.ts` +198 行 / 19 test:
- 5 組:root defaults / lsdException 各屬性 / 真實 fixture / 防禦邊界
- 含 147 個 exception 大量 fixture 模擬(Word 預設骨架壓力測試)

**Step 7 - 三層 SOP**:見 Verification

**Step 8 - 三檔文件**:
- `docs/sprint153_latent_styles_capture.md`(本)
- `docs/autonomous_roadmap.md`(+1 列)
- 規畫書標頭

**Step 9 - commit**「Sprint 153: latentStyles capture-only Parser」

### 設計決策

**為何不合併到 StyleResolver**:
- StyleResolver 負責 active styles 解析 + 繼承鏈(docDefaults → basedOn → current)
- latentStyles 是 Word UI 'Style Gallery' 顯示用、與 active styles 無 wire-up
- 合併會違反 SRP(Single Responsibility)、且擴大 StyleResolver scope
- 紀律 #14:模組化、各司其職

**為何 exceptions 用 Map<name, exception> 不展開為陣列**:
- Map 查找 O(1)、export 端對稱性更自然
- 重複 name(理論不該發生)用 Map.set 行為簡單處理
- 紀律 #18:scope-down、不為「保留順序」而設計陣列(latent style name 是 string、有 Word 內建排序 spec)

**為何全空 exception 仍掛 key**:
- name 本身已是資訊(e.g. 區分「Word 已知 latent style」vs「未知 latent style」)
- 與 Sprint 151 custom.xml 「property 全空跳過」不同 — custom.xml 全空 = noise、latent 全空 = 「Word 已知但 user 沒改 properties」

**為何 toggle 接受寬鬆規格**:
- Word 寫 lsdException 時 `w:locked="1"` / `w:locked="0"` 為主、但 spec 允許 "true"/"false"
- 沿用 Sprint 146 SettingsParser / Sprint 147/148 同模式(`!== '0' && !== 'false'` 為 true)

### scope-down 維度(紀律 #18)

- ❌ 不解析 lsdException 屬性語意(locked 對 Word UI 行為的影響)
- ❌ 不對應 LatentStyleException 到 StyleMap(latent 不展開為 active style entry)
- ❌ 不寫反向 lookup(name → uiPriority 排序)、留 Phase 6 export

### 與 Sprint 145-152 對比

| 維度 | Sprint 145-148 (footnotes/settings/fontTable/webSettings)| Sprint 150-152 (app/custom/[Content_Types])| **Sprint 153 (latentStyles)** |
|---|---|---|---|
| 覆蓋率 | 42/42(全)| 25-42 | **41/42(只缺 1 fixture 純樣板)** |
| 新 Parser code | +135 到 +187 行 | +0 到 +189 行 | **+156 行** |
| 結構 | element bag | property/discriminated/Map | **root attrs + Map<name, exception>** |
| 紀律 #18 | scope-down enum / variant / MIME | scope-down value / fmtid / pid | **scope-down 不解 toggle 語意 / 不展開 active** |

Sprint 153 = 八連 cluster 後的「收尾」、最後一塊適合 capture-only。

---

## Verification

### L1 Vitest 全套

```
Test Files  78 passed | 1 skipped (79)
     Tests  1331 passed | 1 skipped (1332)
  Duration  160.76s
```

- 1312 → **1331 passed**(+19、本 sprint)
- 0 regression(既有 1312 全綠)

### L2 Visual Regression v14

```
[v14] rendered=42/42  bootFailed=0  comparedPages=126  failedPages=0
mean = 0.073191
runAt = 2026-05-19T03:50:03Z
```

- VR mean **0.073191**(byte-identical 第 **23** 次連續)
- 0 fail / 0 boot fail / 0 missing golden

### L3 spot check

- TypeScript build `npm run build:all`(rollup × 2)pass
- bundle byte-identical rebuild

### L4 Odoo backend test

跳過(本 sprint 0 Python 端變動)。

### 防禦覆蓋

| 防禦條件 | 結果 |
|---|---|
| undefined input | `{}` |
| 空字串 input | `{}` |
| 只有空白 | `{}` |
| 壞 XML(unclosed)| `{}`(不 throw)|
| 缺 latentStyles 元素 | `{}` |
| 完全空骨架 | `{}` |
| exception 無 name | 跳過該 exception(紀律 #21)|
| exception 全空屬性 | 仍掛 key(`{}` value、name 本身為資訊)|
| 重複 name | 後者覆蓋前者(Map.set)|
| 非整數於 uiPriority/count | undefined |
| toggle "0"/"false" | false |
| toggle 其他值 | true(OOXML 寬鬆) |

---

## Discipline

### 紀律 #1.a 第 23 連 byte-identical

> parser / layout 改完跑全 VR

連續第 23 個 sprint VR 不破 baseline、Sprint 145-153 九連 capture-only(跳過 149 retro)全部維持。

### 紀律 #14 模組化 + DRY 雙重應用

> 集中索引 + 避免重複實作

- 新 Parser 放 styles/ 子目錄(與 StyleResolver / ThemeResolver / ParagraphStyleMerger 聚集)
- 重用 OoxmlParser 已讀 `stylesXml` 變數(只 read 一次、紀律 #14 DRY)

### 紀律 #18 三維度 scope-down

PR-size:`+156 行 production / +198 行 test / +5 行 patch + 50 行 types + 8 行 OoxmlParser`(同 Sprint 145-148 範圍)

scope-down 維度應用:
- 不解析 toggle 屬性的 Word UI 行為語意(value-level)
- 不對應 latent → active StyleMap(structural-level)
- 不寫反向 lookup(API-level)

### 紀律 #21 應用(第 12 次)

> optional 欄位空集合不掛 key

雙層應用:
- root 級 defaults:屬性不存在 → undefined
- exception 級:無 name → 跳過該 exception

注意例外:全空屬性的 exception 仍掛 key — 因 name 本身已是資訊(紀律 #21 不機械式應用、有 mental model 判斷)

### 紀律 #22 第 17 次正式應用

> 不確定 mental model 先 probe sprint

probe 揭示:
- latentStyles root 屬性命名規律(全部 `def*` prefix)
- exception 屬性對應 root defaults(per-style override 模式)
- 147 lsdException 為 Word 14 預設骨架典型大小

### 紀律 #1.b 候選 v2 第 16 次正面驗證

連續第 8 個 capture-only sprint(145-153、跳過 149 retro)無翻車。

---

## Result

### Sprint 153 結尾累積指標

- vitest **1331 passed + 1 skipped**(+19)
- VR mean **0.073191** / failed 0 / compared 126(**第 23 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML **89.5% → 90%**(latentStyles capture 完成、styles.xml 100% capture)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 152 → **153**

### Phase 1 capture-only **九連** cluster(Sprint 145-153、跳過 149 retro)累積

| Sprint | Part | New parser code | Test | Phase 1 進度 |
|---|---|---|---|---|
| 145 | footnotes + endnotes | +135 | +12 | 80% → 82% |
| 146 | settings | +187 | +27 | 82% → 84% |
| 147 | fontTable | +150 | +20 | 84% → 86% |
| 148 | webSettings | +95 | +14 | 86% → 87% |
| 150 | app.xml | +189 | +20 | 87% → 88% |
| 151 | custom.xml | +179 | +29 | 88% → 89% |
| 152 | [Content_Types].xml | +0(internal expose)| +14 | 89% → 89.5% |
| **153** | **styles.xml latentStyles** | **+156** | **+19** | **89.5% → 90%** |
| **合計** | **9 parts** | **+1091** | **+155** | **+10pp** |

八連 → 九連、VR 第 22 → 23 連、Phase 1 +9.5pp → **+10pp**(80→90%、整數里程碑)。

---

## 後續

### Sprint 154 候選(autonomous 評估、§11.2 backlog 真的耗盡)

| 候選 | 預期 | 理由 |
|---|---|---|
| **F-1. session 自然停止 + 三度交班** | 0 | autonomous-friendly §11.2 backlog 已完全消化、九連 cluster 是收益曲線終點 |
| E-16. Sprint 145-153 cluster retro | 1 sprint docs | 9 sprint pattern 已成熟、可寫精煉版 retro(沿用 Sprint 120/144/149 模式)|
| E-17. 進入 wire-up 階段 GO | 1-2 sprint | 會破 VR baseline、需 user 明確 GO + Strategy C 折衷模式 |

**autonomous 推薦 E-16**(Sprint 145-153 cluster retro):
- 九連 capture-only 確認模式完整
- 純 docs sprint、第 23 連 byte-identical 維持
- 為 Sprint 154+ wire-up 階段提供方法論基礎

如 user 選 F-1 自然停止、autonomous 也已就緒。

### user 介入點(維持清單、無變化)

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 同意換 baseline + OnlyOffice docker |
| C Phase 5 任一子功能 | fixture + 優先順序 |
| A textAlignment 微弱 wire-up | 確認接受 < 1pt 視覺差 |
| 含 footnoteReference docx fixture | 觸發 Sprint 145 wire-up 升級 |
| Sprint 154+ wire-up 階段 GO | 接受首次破 baseline 風險(Strategy C 模式)|
| Phase 6 docx export | 9 個 capture-only part 的對稱性鏈接設計 |

---

## File-level summary

```
A  static/src/core/ooxml/styles/LatentStylesParser.ts  (+156 行 capture-only parser)
M  static/src/core/ooxml/ast/types.ts  (+50 行 LatentStyleException + DocumentLatentStyles + DocumentNode 1 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+8 行 import + private parser + Step 3.1 + DocumentNode 構造)
M  static/src/core/ooxml/document/DocumentParser.ts  (+1 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+1 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+1 行 constructor patch)
A  tests/unit/LatentStylesParser.test.ts  (+198 行 / 19 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  docs/sprint153_latent_styles_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 153 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 90% 整數里程碑)
```

**Phase 1 capture-only 九連 cluster(145-153、跳過 149 retro)完工**、合計 **+10pp Phase 1 進度(80→90% 整數里程碑)** / +155 test / **第 23 連 byte-identical**。autonomous-friendly §11.2 backlog **真的耗盡** — 剩餘候選不是「需 user GO」就是 ROI 過低不適。下個 sprint 推薦 = cluster retro(E-16)或 session 自然停止(F-1)。
