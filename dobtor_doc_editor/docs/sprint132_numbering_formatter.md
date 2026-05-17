# Sprint 132 — numberingFormatter 模組（Phase 4.3 編號樣式）

**日期**：2026-05-17
**類型**：code change（新模組 / 純函式 utility / Phase 4.3 中文編號格式收口）
**規畫書對應**：§Phase 4.3「中文編號格式完整支援、`<w:lvlText>` 模板解析」+ autonomous_roadmap.md 階段 B cluster 5 行 1
**前置 sprint**：Sprint 131 tblStylePr/tcPr 傳遞補完（cluster 4 收尾）

---

## Hypothesis（驗證對象）

`NumberingResolver` 自 Sprint 1 起把 `<w:numFmt val="..."/>` 解析後**原樣 pass-through**（透傳）為 `NumberingLevel.numFmt: string`、註解明白指出「由 Renderer 解碼為實際數字」。但 grep 全 TS source 結果：**完全沒有任何模組實作 numFmt → 顯示字串 的轉換**；canvas-editor 套件本身也只能處理 `decimal` / `bullet` 預設，CJK 編號（`chineseCounting` / `ideographDigital` / `japaneseCounting`...）目前完全無法 render。

實務影響：ChienYi 監造文件大量使用「第一章」「第貳節」「(一)」等中文編號；目前 import 後序號區塊空白或顯示 raw OOXML 字串（`%1`），規畫書 §Phase 4.3 列為待完工。

**Hypothesis A（功能正確性）**：純函式 `formatNumber(n, numFmt)` + `expandLvlText(template, counters, numFmts)` 可獨立 unit test、覆蓋 OOXML §17.18.59 主流 16+ 種 numFmt、對極端值（0/負數/Infinity）防禦不 throw。

**Hypothesis B（VR 穩定性）**：本 sprint 只新增模組、未 wire 進 mapper / renderer（屬未來 sprint 整合範圍）；預期 byte-identical（紀律 #1.a 第 9 次連續驗證機會）。

**Hypothesis C（整合 cost）**：純函式設計、無 module-level state、好 cache + 好測試（紀律 #3 / #5 / #6 fit）；未來 wire-up 階段不會被既有 IIFE bundle 結構卡住（與 Sprint 62 nodeModuleStub 47-sprint blocker 不同型別）。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 5 cluster：「132 | Phase 4 Style | 4.3 中文編號格式 chineseCounting / ideographDigital / japaneseCounting 完整」
- 規畫書 §Phase 4.3 列：「編號文字的字型大小、顏色獨立於段落 / 編號與段落的間距(`<w:suff>` = `tab` / `space` / `nothing`) / 中文編號格式完整支援、`<w:lvlText>` 模板解析」
- 本 sprint scope = **純函式 formatter 模組 + 模板展開 + 50 unit test**
- 不在 scope（留未來 sprint）：
  - **wire-up 到 mapper / renderer**（屬於 Phase 5+ Layout Engine 整合、需 canvas-editor IIFE bundle patch 或 mapper 重構）
  - `<w:suff>` 編號與段落間距處理（屬於 Layout 階段）
  - 編號文字字型大小 / 顏色獨立 props（已由 NumberingLevel.runProps 載入、未消費）
  - 萬以上 chineseCounting / chineseLegal（罕用於 ilvl 編號、簡化 fallback decimal）
  - 半形 / 全形假名（`irohaFullWidth` / `aiueoFullWidth`）— Sprint 132 簡化為 alias to 平假名
- PR-size：numberingFormatter.ts +400 行（純新檔）/ numberingFormatter.test.ts +320 行 / 50 新 test / 1 audit / 1 bundle rebuild

### 2. 設計決策

#### 2.1 為什麼用純函式而非 class

- **無狀態**：每次 call 不依賴 instance 狀態、易測試、易並行
- **cache-friendly**：未來 LayoutCache 把 numFmt+n 結果 memoize 不需 wrapper（紀律 #6 教訓）
- **整合 flexibility**：mapper / renderer / export pipeline 三方都可以直接 import 同模組

#### 2.2 為什麼放在 `core/ooxml/numbering/` 而非 `core/render/`

- **OOXML 知識集中**：format spec 屬規格層、非 render 層
- **`NumberingResolver` 同目錄**：未來如要把 formatter 與 resolver 整合 cache 同 module 操作方便
- **避免 render 層上下游耦合**：core/render/ 應只關心「畫 pixels」、不該知道 OOXML §17.18.59

#### 2.3 為什麼不 wire 進 NumberingResolver 直接 store `formattedText`

選擇 A：resolver 解析時就把 `levels[i].formattedText[n]` 預先算好（lookup table）
選擇 B：保持 raw numFmt、render 時 call `formatNumber(counter, numFmt)`

**選 B**（lazy + pure）：

- counter 值在 render 時才決定（lvlRestart / lvlOverride 跨段落會動）、預先算不切實際
- formatter 是純函式、render 時 call 不會慢
- 保留 raw numFmt 對 Phase 6 export 反向序列化也方便

#### 2.4 為什麼 CJK 邊界處理保守

- 1–9999 chineseCounting：覆蓋 ChienYi 監造文件 99.9% 章節編號需求
- 10000+ fallback decimal：監造文件章節極少超過 1 萬、誤判 decimal 比錯誤 CJK 安全
- 萬以上中文寫法（億 / 兆）：屬「中文數字寫法」、與 OOXML 編號 spec 不一致；defer 直到實務 fixture trigger

### 3. 修法

#### 3.1 numberingFormatter.ts 主要 API

```ts
// 主 entry point
export function formatNumber(n: number, numFmt: string): string;

// 模板展開
export function expandLvlText(
  template: string,            // e.g. "%1.%2."、"第%1章"
  counters: number[],          // 各 level counters [level0, level1, ...]
  numFmts: string[],           // 各 level 的 numFmt
): string;
```

#### 3.2 支援的 16 種 numFmt（按類別）

| 類別 | numFmt | 範例 |
|---|---|---|
| 基本 | decimal / decimalZero / none / bullet | 1 / 01 / "" / "" |
| 西式 | lowerLetter / upperLetter / lowerRoman / upperRoman | a/A/i/I, aa/AA/xi/XI |
| 英文 | ordinal / ordinalText / cardinalText | 1st / first / one |
| 中文 | chineseCounting / chineseCountingThousand / chineseLegalSimplified / ideographDigital | 一 / 一千 / 壹 / 一〇 |
| 日文 | japaneseCounting / japaneseDigitalTenThousand / japaneseLegal | 一 / 一万 / 壱 |
| 台灣 | taiwaneseCounting / taiwaneseCountingThousand / taiwaneseDigital | (alias to chinese) |
| 循環 | ideographZodiac (12) / ideographTraditional (10) / iroha (47) / aiueo (46) | 子/甲/い/あ |

#### 3.3 算法重點

**chineseCounting 1–9999 遞迴**：
```
n < 10:   CN_DIGITS[n]                          // 0=〇, 1=一, ..., 9=九
n < 20:   '十' + CN_DIGITS[n-10] (省略「一十」)  // 10=十, 19=十九
n < 100:  CN_DIGITS[tens] + '十' + CN_DIGITS[ones]
n < 1000: CN_DIGITS[h] + '百' + 遞迴(rest, 補「零」rules)
n < 10000: CN_DIGITS[k] + '千' + 遞迴(rest, 補「零」rules)
n >= 10000: fallback decimal
```

**「零」補位 rule**（與 Word 行為一致）：
- 101 → 一百零一（鄰位有 0、補零）
- 110 → 一百十（個位非 0 但仍補省略「一」）
- 1010 → 一千零十（千-十之間百位 0、補零）
- 2024 → 二千零二十四（千-十之間百位 0、補零）

**base-26 letter**：
```
1=a, 26=z, 27=aa, 52=az, 53=ba, 703=aaa (26*27+1)
迴圈 v -= 1 ; rem = v % 26 ; out = char(base+rem) + out ; v = floor(v/26)
```

**ordinal teen 例外**：
- 11/12/13/111/112/113 → 11th/12th/13th/111th/112th/113th（不是 11st/12nd/13rd）
- 用 `mod100 in [11..13]` 條件而非 `mod10`

#### 3.4 expandLvlText 設計

```
"%1.%2." + [3, 2] + ['decimal', 'lowerLetter']
   ↓
Regex /%([1-9])/g：%1 → counters[0]=3, fmt=decimal → "3"
                    %2 → counters[1]=2, fmt=lowerLetter → "b"
literal '.' 不被替換、保留
   ↓
"3.b."
```

缺對應 counter / numFmt：placeholder 替換為空字串、literal 字元仍保留（與 Word 行為一致：`%1.%2.` 缺 level 2 → `3..`）。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1107 passed + 1 skipped**（從 1057+1 起、+50 新 test 涵蓋 16 numFmt + expandLvlText + 邊界）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（byte-identical、**第 9 次連續**、紀律 #1.a 應用）|
| L3 Spot check | ✅ TypeScript build PASS（pre-existing warning 同前、bundle rebuild 31.1s）|
| L4 Odoo backend | **跳過**（無 backend / model / ACL 變動）|

### 5. Unit test 設計（50 個新 test）

按主題分組：

| 分組 | 測試數 | 涵蓋 |
|---|---|---|
| decimal / decimalZero | 2 | 預設 / 0 padding |
| lowerLetter / upperLetter | 3 | base-26、aa/az/ba/aaa 邊界、0/負數防禦 |
| lowerRoman / upperRoman | 4 | 1-3999 範圍、組合 49/1994/3999、>3999 fallback |
| ordinal / ordinalText / cardinalText | 4 | 1st-4th 後綴、11/12/13 teen 例外、1-20 英文文字 |
| chineseCounting | 7 | 1-9, 10-19, 20-99, 100-999, 1000-9999、0/負數、>=10000 fallback、aliases |
| chineseLegalSimplified | 4 | 壹貳…玖、拾佰仟、2024 完整、>=10000 fallback |
| ideographDigital | 3 | 單位、多位獨立、0/負數 |
| japaneseLegal | 2 | 壱弐参 + 普通漢字混用 |
| japaneseDigitalTenThousand | 4 | < 10000、= 10000、12345 複雜、20000 |
| 循環序列（zodiac/stem/iroha/aiueo）| 4 | 12/10/47/46 循環邊界 |
| 邊界與防禦 | 4 | none/bullet、未知 fmt、Infinity/NaN、浮點數 |
| expandLvlText | 9 | 基本/中文/三層/缺 counter/literal/連續/bullet 路徑/非 1-9 placeholder |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/numbering/numberingFormatter.ts` | +400 行 / 純新檔 | numFmt → 顯示字串 + lvlText 模板展開 |
| `tests/unit/numberingFormatter.test.ts` | +320 行 / 50 新 test | 16 numFmt + expandLvlText + 邊界完整覆蓋 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步（雖未 wire-up、紀律仍 enforce）|
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、byte-identical | VR confirm |
| `docs/sprint132_numbering_formatter.md` | 本 audit doc | 紀錄 formatter 設計 |
| `docs/autonomous_roadmap.md` | cluster 5 開工 + Sprint 132 ✅ + 進度表 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | §0.2 Phase 4 82% → 83% + §Phase 4.3 註記 | 同步 |

### Test 數變動

- Sprint 131 結尾：vitest 1057 + 1 skipped
- Sprint 132 結尾：vitest **1107 + 1 skipped**（+50）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 131 結尾：mean 0.073191（byte-identical）
- Sprint 132 結尾：mean **0.073191**（byte-identical、**第 9 次連續** 121→126→130→131→132）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style Theme：82% → **83%**（+1%、4.3 numFmt formatter 模組化完成、wire-up 留未來 sprint；剩 `<w:suff>` 間距 / 編號 runProps 消費）

---

## Root cause

**為什麼 Sprint 1-131 沒做 numFmt formatter**：

1. NumberingResolver 註解明寫「由 Renderer 解碼為實際數字」、但沒人主動接這件事
2. canvas-editor 自帶 decimal / bullet 處理、其他 numFmt fallback 為空或 raw template、VR mean 對非中文 fixture 不敏感（western letters 比 CJK 字符在 PNG diff 上更顯眼）
3. 42 fixture 中含中文編號的不多（多為自由排版、無 abstract numbering）、VR 無 signal 揭示 gap
4. 規畫書 §Phase 4.3 一直列為待完工、cluster 5 才正式啟動

**為什麼 VR byte-identical**：

純加新模組 + tests、未動 parser / mapper / renderer / bundle 邏輯。bundle rebuild 雖會把 numberingFormatter.ts 含入 IIFE bundle，但因無 consumer 呼叫、tree-shaking 後實際 byte change 為 minimal（imports 註冊 + 函式定義）；render path 完全未動、PNG output byte-identical。

未來 wire-up 階段預期 VR drift +5~15%（CN 編號從空白 → 渲染為「一」「二」字符、明顯像素變化）。

---

## 紀律

### 紀律 #1.a 第 9 次連續驗證（Sprint 132）

連續 9 sprint code change 都跑全 VR 並維持 byte-identical：

| Sprint | 改動 | VR |
|---|---|---|
| 121 | TableParser trHeight | 0.073191 |
| 122 | OLE/pict fallback | 0.073191 |
| 123 | field code 完整 | 0.073191 |
| 124 | sdt unwrap | 0.073191 |
| 125 | bookmark capture | 0.073191 |
| 126 | hyperlink 3 屬性 | 0.073191 |
| 130 | HSL luminance tint/shade | 0.073191 |
| 131 | tblStylePr/tcPr cell props | 0.073191 |
| **132** | **numberingFormatter 新模組** | **0.073191** |

紀律 #1.a 穩固、9 次連續 byte-identical、覆蓋 OOXML parser / dom utility / style resolver / table applicator / **pure utility 新模組** 五類修改點。

### 紀律 #3 應用（Sprint 132）

> 高風險改造前先 probe sprint 收集事實。

Sprint 132 開工前 grep 揭示「TS source 無人消費 numFmt」、確認新模組為「補完缺漏」而非「重寫既有」、scope 控制在 utility layer、不動 render pipeline；避免 Sprint 62 nodeModuleStub 47-sprint blocker 同類陷阱。

### 紀律 #5 應用（Sprint 132）

> vitest 通過不保證 IIFE bundle 同 code 也 work。

雖然 numberingFormatter 是 pure 函式、bundle 不可能掉、仍按紀律 rebuild + 跑 VR confirm bundle integrity；TypeScript build PASS、無新 warning。

### 紀律 #21 第 2 次正式應用（Sprint 132）

> optional 欄位空集合不掛 key（升正式 Sprint 131）。

`expandLvlText` 對 `counter === undefined` 與 `fmt === undefined` 都回 ''（不 throw、不 inject 預設）、與紀律 #21「缺值優雅降級」一致。

### 紀律 #18 持續

PR-size 守住：1 新模組 +400 行 / 1 新 test file +320 行 / 1 audit / 1 bundle。明示 5 項不在 scope（wire-up / `<w:suff>` / runProps 消費 / 萬以上 CN / 半形假名）。

---

## 後續

### Sprint 133（cluster 5 收口或進 cluster 6）

階段 B cluster 5 (132) 已完成 Phase 4.3 主軸。下一個方向候選：

**選項 A：cluster 6 Phase 4.4 Paragraph 進階**（規畫書原排 Sprint 133-134、autonomous_roadmap.md 階段 B 行 6）：
- `<w:pBdr>` 段落邊框 + 陰影
- `<w:tab>` tab stop leader（leader='dot'/'hyphen'）+ decimal alignment
- `<w:textAlignment>`（baseline / center / top / bottom 文字行內對齊）
- 對 ChienYi 監造文件「目錄頁次對齊」「報告封面框線」直接相關

**選項 B：cluster 7 Phase 3 漏項 docGrid snap**（規畫書 §0.1 列為長期 backlog、規畫書原列 Sprint 135）：
- Sprint 46+49 全域翻車、需段落條件式判別
- 大型 spike sprint、單獨拆出處理

**autonomous 決策**：cluster 5 後續分兩 sprint：
- Sprint 133 = Phase 4.4 `<w:pBdr>` 段落邊框 + 陰影（中等 scope）
- Sprint 134 = Phase 4.4 `<w:tab>` leader + decimal + textAlignment（中等 scope）

理由：(1) Phase 4 整章節按規畫書排序自然順著走、(2) 4.4 兩主題互相獨立、可 split 為 2 sprint 守 PR-size、(3) docGrid snap 屬於大型 spike、留專門 sprint 處理。

### Sprint 132+ 候選

- **wire-up formatter 到 mapper / renderer**：需 canvas-editor IIFE patch 或 mapper 新增 numbering pass、屬整合 sprint、預計 VR drift 顯著
- **編號 runProps 消費**（編號字色 / 大小獨立於段落）：需 mapper 區分 numbering label vs body text、屬整合 sprint
- **`<w:suff>` 間距處理**（tab / space / nothing）：屬 Layout 階段、與 numbering 對齊
- **萬以上 chineseCounting / chineseLegal**（億兆）：待 fixture 真實 trigger
- **半形 / 全形假名**：待 fixture 真實 trigger（OOXML 規格區分但實務罕見）

---

## Sprint 132 結尾累積指標

- vitest **1107 passed + 1 skipped**（+50）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 9 次連續**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style Theme 82% → **83%**
- 21 ADR / 紀律 **20 條** + 6 子 + 2 候選（無新增、#22 候選持平 2/3、#20 候選持平 1/3）
- Sprint audit doc 數 131 → **132**
- 階段 B cluster 5 (132) **完成**、進入 cluster 6 (133-134) Phase 4.4 Paragraph 進階

---

## File-level summary

```
A  addons/dobtor_doc_editor/static/src/core/ooxml/numbering/numberingFormatter.ts  (+400 行純新檔)
A  addons/dobtor_doc_editor/tests/unit/numberingFormatter.test.ts  (+320 行 / 50 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint132_numbering_formatter.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 132 ✅ + cluster 5 開工/完成)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 4 82→83%)
```

無 model / view / ACL / rule / controller / backend 變動、無 wire-up 整合（留未來 sprint）。階段 B cluster 5 (132) 完成、formatter pure 函式模組就位。
