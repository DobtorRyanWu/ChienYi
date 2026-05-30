# Sprint Y58 — FloatTextBox + AnchorMetadata mapper integration (A)

- **建立日期**：2026-05-30
- **前置**：Sprint Y57 真實 gap 驗證（[sprint_y57_real_gap_verification.md](./sprint_y57_real_gap_verification.md)）落定 user 決策：25/25 ChienYi 監造文件含 wp:anchor + w:txbxContent、產品端丟失、啟動仿 Sprint 358-360 SVG 真實路徑整合模式
- **狀態**：Sprint A 完成、停下待 user review；未 commit、未進 Sprint B
- **總改動**：1 個 mapper 檔案 + 1 個新 unit test 檔；無 production runtime 行為變化（預設 flag = false）

---

## 1. 規格

完整 4-sprint 大綱（user 指定）：

| Sprint | 範圍 |
|---|---|
| **A（本次）** | mapper 加 `case 'floatTextBox'` + AnchorMetadata 透傳；兩個 options flag 預設 false |
| B | controller `_ts_parse_docx_to_elements` 加 `--float-textbox` / `--anchored-image` CLI flag（opt-in、不改現有匯入行為） |
| C | 15 份 ChienYi（5 監造會議 + 5 週報 + 5 查驗）端對端真實驗證（parse + canvas-editor UMD headless render + 截圖比對） |
| D | commit-lock 整合測試 `tests/integration/sprint_y58_real_path.test.ts` |

VR mean 不退步 + 15 份真實 docx 全綠 → 推進 multi-section sprint。

## 2. Sprint A 落地內容

### 2.1 改動檔案

| 檔案 | 性質 | 改動摘要 |
|---|---|---|
| `static/src/core/ooxml/mapper/ToCanvasEditor.ts` | 既有 | options 加 2 個 flag、CEElement 加 `anchor` extension 欄位、`appendInlineNode` 加 `floatTextBox` case + 改寫 `floatImage` case、新增 `appendFloatTextBox()`、新增 `AnchorExtension` interface、新增 3 個 helper functions、改 `appendInlineNode` 簽名加 numbering/counter |
| `tests/unit/sprint_y58_float_textbox_anchor.test.ts` | 新檔 | 9 個 test 覆蓋 A/B/C/D/E/F 6 個矩陣 case |

### 2.2 Options 介面

```ts
export interface ToCanvasEditorOptions {
  renderGraphicsAsSvg?: boolean;       // Sprint 358-359 既有
  renderCommentsAsGroups?: boolean;    // Sprint 184/361 既有
  renderFloatTextBox?: boolean;        // Sprint Y58 新增：展平 textbox paragraphs
  preserveAnchorMetadata?: boolean;    // Sprint Y58 新增：透傳 wp:anchor 屬性
}
```

兩個新 flag **預設 false** → VR byte-identical 不變、不影響既有 `engine=ts` 匯入路徑。

### 2.3 行為定義

| flag 組合 | floatTextBox 行為 | floatImage 行為 |
|---|---|---|
| 預設（皆 false） | drop（與 Sprint 38 mapper 行為一致） | 降級 inline image（既有） |
| `renderFloatTextBox=true` | 展平 paragraphs（獨立 NumberingCounterState、不污染外部 counter） | 不變（仍降級 inline） |
| `preserveAnchorMetadata=true` | textbox drop 故無透傳 | image 元素掛 `anchor.source='floatImage'` + metadata |
| 兩個都 true | textbox 展平 + 第一個元素掛 `anchor.source='floatTextBox'` | 同上 + 第一個元素掛 anchor |

### 2.4 AnchorExtension schema

```ts
export interface AnchorExtension {
  source: 'floatImage' | 'floatTextBox';
  width?: number;
  height?: number;
  posH?: FloatImageNode['posH'];          // wp:positionH
  posV?: FloatImageNode['posV'];          // wp:positionV
  wrapType?: FloatImageNode['wrapType'];  // none/square/tight/...
  behindDoc?: boolean;
  allowOverlap?: boolean;
  metadata?: AnchorMetadata;              // dist / relativeHeight / locked / ...
  wrapText?: AnchorWrapText;
}
```

canvas-editor runtime **不消費** `IElement.anchor`；前端 plugin / round-trip writer / 排版 layer 才會讀。Sprint Y58 純 capture-only。

### 2.5 設計決策（why）

- **獨立 counter（textbox 內 numbering）**：textbox paragraphs 走 `appendParagraph` 完整流程能拿到段落樣式/行距/numbered list，但 textbox 內若 advance numId 不該污染外部 counter（textbox 是浮動容器、不屬主流文）
- **anchor 只掛第一個 emit 出來的 IElement**：避免每個字元都帶 anchor 帶來 JSON 膨脹；前端 plugin 用「找第一個帶 anchor 的元素 → 該段落屬於 anchor」即可
- **空 paragraphs textbox 即使 flag=true 也不 emit**：Sprint Y57 fixture 內 anchor[3] 是空 textbox（真實 Word 行為），不該插占位
- **floatImage anchor 透傳不換 emit 路徑**：仍走 `appendImage`（既有降級 inline），只在已 emit 元素掛 metadata，向後相容
- **改 `appendInlineNode` 簽名加 numbering/counter**：唯一 1 處 caller（appendParagraph），改動最小、type-safe
- **不依賴 production runtime 行為改變**：所有 flag 預設 false → controller 不傳 flag → IElement 樹 byte-identical → VR 與既有匯入路徑均不受影響

## 3. 驗證

### 3.1 新 unit tests（9 個全綠）

```
tests/unit/sprint_y58_float_textbox_anchor.test.ts

A. 預設 options（VR byte-identical 保證）
  ✓ floatTextBox 不展平：textbox 文字不出現在 IElement
  ✓ floatImage 仍降級為 inline image（既有行為），未透傳 anchor

B. renderFloatTextBox=true
  ✓ 單行 textbox 文字展平到 inline stream
  ✓ 多 paragraph textbox：每段都有段尾 \n
  ✓ 空 paragraphs textbox（真實 fixture anchor[3]）：開 flag 也不 emit 字元

C. preserveAnchorMetadata=true（FloatTextBox）
  ✓ 開啟 flag 後 textbox 的第一個 IElement 帶 anchor.source=floatTextBox
  ✓ renderFloatTextBox=false + preserveAnchorMetadata=true → 無 textbox 元素故無 anchor 透傳

D. preserveAnchorMetadata=true（FloatImage）
  ✓ floatImage 仍降級 inline image，但 IElement 帶 anchor.source=floatImage
  ✓ media 找不到 rId → 用 [圖片缺失] 占位但 anchor 仍透傳
```

### 3.2 既有測試不退步

| 測試集 | 結果 |
|---|---|
| `tests/unit/ToCanvasEditor.test.ts`（既有 mapper unit） | 46 passed |
| `tests/unit/sprint331_overlay_touch_mapper.test.ts` | 19 passed |
| `tests/integration/03_e2e_mapper.test.ts`（67 個 fixture E2E） | 67 passed |
| **全 test suite** | **3150 passed / 8 skipped（既有）/ 0 failed**（247 test files） |

03_e2e_mapper 跑遍所有 67 份 fixture 不 throw、IElement 統計輸出與既有 baseline 完全一致：

```
01_simple: avg=6,  min=3,  max=6,  n=7   ← 與既有 baseline 一致
02_std_table: avg=104, min=40, max=342, n=8
03_complex_table: avg=137, min=49, max=308, n=8
04_with_image: avg=27, min=23, max=35, n=6
05_header_footer: avg=298, min=295, max=303, n=10
06_template: avg=280, min=208, max=339, n=3
07_chart: avg=604, min=312, max=1279, n=8
08_smartart: avg=153, min=123, max=231, n=4
09_omml: avg=34, min=23, max=43, n=6
11_perf_synthetic_large: avg=175528, min=69494, max=281562, n=2
```

### 3.3 typecheck

```
$ npx tsc --noEmit
static/src/core/ooxml/font/FontMetrics.ts(27,29): error TS7016: ...    [既有]
static/src/core/ooxml/settings/SettingsParser.ts(97,11): error TS2322: ... [既有]

total errors: 2（與 sprint A 改動無關，pre-existing）
```

Sprint Y58 mapper 改動本身無 TS 錯誤。

---

## 4. 範圍紀律

### 已做
- mapper `case 'floatTextBox'` opt-in 展平
- floatImage / floatTextBox anchor metadata opt-in 透傳
- 9 個新 unit test + 既有 mapper test 132 個全部不退步

### 沒做（留給 Sprint B+）
- **CLI flag**：`parse_docx_cli.ts` 仍只認得 `--ast` / `--elements` / `--svg-graphics`
- **Python controller flag**：`_ts_parse_docx_to_elements` 仍寫死 `['--elements', '--svg-graphics']`
- **端對端 15 docx 真實驗證**：Sprint C
- **canvas-editor 視覺呈現 floatTextBox**：本 sprint 只把資料塞進 IElement.anchor 透傳；canvas-editor runtime 不消費這欄位、視覺仍是 inline 降級。真正的浮動繞排 layout 要 Phase 6+ 才補
- **commit-lock integration test**：Sprint D

### 紀律 #21 capture-only 對齊
本 sprint 沿用 Sprint 287 / 289 的 capture-only 紀律 — parser 補完整 + mapper 提供 opt-in 透傳通道、writer 仍走既有降級路徑（acceptable lossy by design），保留 future sprint 升級到完整繞排 layout 的空間。

---

## 5. Sprint B 預告

Sprint B 改動範圍：

| 檔案 | 改動 |
|---|---|
| `tools/parse_docx_cli.ts` | 加 `--float-textbox` 與 `--anchored-image` 兩個 flag、透傳到 `ToCanvasEditor({ renderFloatTextBox, preserveAnchorMetadata })` |
| `controllers/doc_controller.py` `_ts_parse_docx_to_elements` | subprocess argv 條件性加 flag（caller 控制；預設不加、向後相容） |
| `controllers/doc_controller.py` `/dobtor_doc/import` route | 接收 query 參數 `float_textbox=1` / `anchored_image=1`，往下游透傳 |
| 重新 build CLI（`npm run build:cli`） | 必要 |
| 1 個 vitest integration test（sprint_y58_cli_flags） | 確認 CLI flag 正確透傳到 IElement |

預估 ~30 行 production change + 1 個 test。

---

## 6. 等待 user review

- [ ] Sprint A mapper 邏輯
- [ ] AnchorExtension schema 設計（後續前端 / round-trip 會直接讀 `IElement.anchor`）
- [ ] 是否要 commit 後再進 Sprint B（建議：是，便於分段 rollback）
- [ ] Sprint B 範圍是否如上預告

請 user 指示是否進 Sprint B。
