# Architecture Decision Records — dobtor_doc_editor Track B

**建立日期**：2026-04-21  
**適用範圍**：Track B（Canvas OOXML 完整渲染引擎），Phase 0 架構基準  
**狀態**：Phase 0 確定，Phase 1+ 執行中持續更新

---

## ADR-001：canvas-editor 修改策略 — npm Build Pipeline + patch-package

### 背景

Track B 需要對 `@hufe921/canvas-editor` 的核心模組進行深度修改：

- **Layout Engine**（`editor/core/draw/`）：完全不支援 Word 表格模型
- **Table Renderer**：不計算 gridSpan / vMerge
- **Section/Page 管理**：單節架構，不支援多節 sectPr
- **Text Shaping Pipeline**：使用 `ctx.measureText()`，精度不足
- **Float Manager**：無浮動元素管理

**Phase 0 發現**：canvas-editor 目前以 **UMD bundle 形式 vendor 在 `static/src/lib/canvas_editor/`**，
並非透過 npm 安裝，`patch-package` 的前提條件（npm node_modules）不存在。
直接修改 minified UMD（方案 A）更不可行——無法在混淆程式碼上實作複雜的 AST Parser。

評估方案：

| 方案 | 說明 | 可行性 |
|------|------|--------|
| A. 直接修改 vendor UMD | 最簡單 | ❌ minified 程式碼無法實作 Parser / Layout Engine |
| B. 完整 fork npm 倉庫 | 乾淨但獨立 | ⚠️ 需維護獨立 repo，upstream 更新難合併 |
| **C. 模組內 npm pipeline + patch-package** | **版控追蹤 diff，build 出新 UMD** | **✅ 推薦** |

### 決策：在模組根目錄建立 npm Build Pipeline

**架構**：
1. `dobtor_doc_editor/package.json` — 宣告 `@hufe921/canvas-editor` 為 npm dependency
2. `patch-package` 修改 node_modules 內的 canvas-editor 原始碼，diff 存入 `patches/`
3. **Rollup**（非 Vite）將我們的 OOXML TypeScript Parser + 修改後的 canvas-editor 打包成一個 UMD
4. 輸出 `static/src/lib/canvas_editor/canvas-editor-custom.umd.js`，由 Odoo 靜態資源系統載入

> **為何選 Rollup 而非 Vite**：我們要的是 library bundle（UMD 格式），不是 web app 開發伺服器。
> Rollup 輕量、專為 library 設計，Vite 底層 production build 本身也是用 Rollup。

**Git 追蹤策略**：

| 項目 | 追蹤方式 |
|------|---------|
| `package.json` / `package-lock.json` | ✅ 進 git |
| `static/src/core/ooxml/**/*.ts`（我們的原始碼）| ✅ 進 git |
| `patches/*.patch`（canvas-editor 修改 diff）| ✅ 進 git |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js`（build 產出）| ✅ 進 git（Odoo 需要靜態檔案）|
| `node_modules/`                         | ❌ `.gitignore` |

### Build Pipeline 設定檔

詳見專案根目錄的 `package.json`、`rollup.config.js`、`tsconfig.json`。

### 日常工作流程

```bash
# 初始設定（只需一次）
cd e:/work/system/addons/dobtor_doc_editor
npm install

# 修改 canvas-editor 後記錄 patch
npx patch-package @hufe921/canvas-editor

# 重新 build（修改 OOXML Parser 或 patch 後執行）
npm run build:frontend

# 監聽模式（開發中使用）
npm run build:watch
```

### patch 目錄結構

```
patches/
└── @hufe921+canvas-editor+0.9.128.patch   # canvas-editor 修改 diff（自動產生）
```

### 注意事項

- canvas-editor 升版時（0.9.128 → 新版），需重新 `npm install`、套用 patch、確認衝突
- **不需替換的模組**（保留原始）：IME 處理、游標 hit-testing、Undo/Redo、Copy/Paste、基本 Canvas 渲染基礎設施
- build 產出的 `canvas-editor-custom.umd.js` 要同步更新 `__manifest__.py` 的靜態資源參照

---

## ADR-002：OOXML Parser 設計 — 獨立 TypeScript 模組

### 背景

canvas-editor 目前走 `mammoth.js → HTML → canvas-editor 內部格式` 的轉換路徑，在複雜表格（gridSpan/vMerge）、多節頁面、浮動圖片上嚴重失真。

需要一個能直接解析 OOXML（`.docx` ZIP 結構）並輸出精確 AST 的 Parser，作為 Track B 的資料層。

### 決策：獨立 TypeScript 模組，輸出標準 AST

**模組位置**：`static/src/core/ooxml/`

**核心原則**：Parser 與 Renderer 完全解耦——Parser 只負責將 OOXML 轉為 AST，不接觸任何 Canvas API。

### 模組結構

```
static/src/core/ooxml/
├── index.ts                  # 主入口：OoxmlParser class
├── package/
│   ├── PackageReader.ts      # ZIP 解包，[Content_Types].xml, _rels/ 解析
│   └── PartResolver.ts       # 部件路徑解析（相對 → 絕對）
├── units/
│   └── Units.ts              # EMU → px, twips → pt, half-pt → pt
├── styles/
│   ├── StyleResolver.ts      # styles.xml 繼承鏈（docDefaults → style → direct format）
│   └── ThemeResolver.ts      # theme/theme1.xml 色彩/字型映射
├── document/
│   ├── DocumentParser.ts     # word/document.xml 主解析器
│   ├── ParagraphParser.ts    # <w:p> → ParagraphNode
│   ├── RunParser.ts          # <w:r> → RunNode（含 rPr 格式）
│   └── FieldParser.ts        # fldChar / instrText → FieldNode（PAGE, DATE 等）
├── table/
│   ├── TableParser.ts        # <w:tbl> → TableNode（含 gridCol 計算）
│   ├── RowParser.ts          # <w:tr> → RowNode（含 tblHeader, cantSplit）
│   ├── CellParser.ts         # <w:tc> → CellNode（含 gridSpan, vMerge 解析）
│   └── GridResolver.ts       # 計算每個 Cell 的 (gridCol, gridSpan, rowSpan)
├── numbering/
│   └── NumberingResolver.ts  # numbering.xml → lvl 格式 + lvlRestart 支援
├── section/
│   └── SectionParser.ts      # sectPr → SectionNode（頁面尺寸、頁距、多欄）
├── drawing/
│   ├── InlineDrawingParser.ts  # <wp:inline> → InlineImageNode
│   └── AnchorDrawingParser.ts  # <wp:anchor> → FloatImageNode（含位置/繞排策略）
├── header-footer/
│   └── HeaderFooterParser.ts   # header1.xml / footer1.xml（奇偶頁/首頁）
└── ast/
    └── types.ts              # 完整 AST 型別定義（所有 Node 介面）
```

### AST 型別設計原則

```typescript
// ast/types.ts（節錄關鍵型別）

/** 文件根節點 */
interface DocumentNode {
  type: 'document';
  sections: SectionNode[];
  styles: StyleMap;
  numbering: NumberingMap;
}

/** 表格節點（含已解算的 grid 資訊） */
interface TableNode {
  type: 'table';
  grid: number[];          // 每欄寬度（EMU）
  rows: RowNode[];
  style?: string;          // tblStyle 引用
}

/** 儲存格節點（gridSpan / rowSpan 已計算） */
interface CellNode {
  type: 'cell';
  gridCol: number;         // 起始 grid column（0-indexed，累計 gridSpan 後）
  gridSpan: number;        // 橫向佔格數
  rowSpan: number;         // 縱向佔格數（由 vMerge 推算）
  isContinuation: boolean; // true = 此格是上方 vMerge 的延續（渲染時跳過）
  content: ParagraphNode[];
  borders: CellBorders;
}

/** 行高度量介面（Phase 1 預留，Phase 2 由 HarfBuzz WASM 實作） */
interface LineMetrics {
  ascender: number;    // 字型 ascender（pt）
  descender: number;   // 字型 descender（pt）
  lineGap: number;     // 字型建議行距（pt）
  // 注意：不依賴 ctx.measureText()，由字型檔案直接讀取
  // Phase 1 暫用 ctx.measureText() 佔位，但必須透過此介面封裝
  // 確保 Phase 2 引入 HarfBuzz WASM 時 Layout Engine 無需重寫
}
```

### GridResolver 演算法（vMerge 核心）

vMerge 的欄位索引不能用一般陣列索引，因為 gridSpan 會打亂對應關係。必須累計 grid 位置：

```typescript
// GridResolver.ts（虛擬碼）
// 注意：需要兩次 pass
// Pass 1：掃描所有 vMerge=restart 的 Cell，計算各自的 rowSpan
// Pass 2：根據 Pass 1 結果，標記所有 isContinuation = true 的 Cell

function resolveGrid(rows: RawRow[]): ResolvedRow[] {
  const pendingMerge: Map<number, number> = new Map(); // gridCol → 剩餘 rowSpan

  return rows.map(row => {
    let gridCol = 0;
    const cells = row.rawCells.map(rawCell => {
      // 跳過被 vMerge 佔用的 grid 位置
      while ((pendingMerge.get(gridCol) ?? 0) > 0) {
        pendingMerge.set(gridCol, pendingMerge.get(gridCol)! - 1);
        gridCol++;
      }

      const span = rawCell.gridSpan ?? 1;
      const isStart = rawCell.vMerge === 'restart';
      const isContinuation = rawCell.vMerge === 'continue';

      if (isStart) {
        for (let i = 0; i < span; i++) {
          pendingMerge.set(gridCol + i, /* rowSpan 由 Pass 1 計算 */ 0);
        }
      }

      const resolved = { gridCol, gridSpan: span, isContinuation };
      gridCol += span;
      return resolved;
    });
    return { cells };
  });
}
```

---

## ADR-003：Golden File 測試策略 — LibreOffice + pixelmatch

### 背景

Track B 的目標是 A- 級還原度（pixelmatch diff < 5%）。需要一個自動化的基準測試機制，在每次修改 Renderer 後量化還原度是否進步或退步。

### 決策：LibreOffice 作為 Ground Truth，pixelmatch 作為量化工具

**流程**：

```
DOCX fixture
    │
    ├─ LibreOffice headless ──→ PNG（Ground Truth / golden）  ← 在 Docker 執行
    │                                 │
    └─ canvas-editor render ──→ PNG ──┴──→ pixelmatch ──→ diff%  ← 在本機執行
                                                           │
                                              diff < 5%  ✅ Pass
                                              diff ≥ 5%  ❌ Fail（輸出 diff image）
```

### 執行環境分工（重要）

| 腳本 | 執行環境 | 原因 |
|------|---------|------|
| `generate_golden.sh`（LibreOffice）| **Docker 容器**（system-odoo）| 已有 `/usr/bin/soffice` + Noto CJK |
| `compare_fixtures.js`（Puppeteer）| **本機 Windows**（開發者機器）| Puppeteer 在無 GUI 的 Docker 容器執行需要 X11 / Xvfb / sandbox 權限，維護成本極高；本機有 Chrome，開箱即用 |

> **不要在 Docker 容器中跑 Puppeteer。** 即使勉強跑起來，也需要 `--no-sandbox`
> 與一堆 X11 依賴庫，每次容器重建都要重新設定。

### 腳本位置

```
tests/
├── fixtures/
│   ├── 01_simple/
│   │   ├── *.docx
│   │   └── golden/          ← LibreOffice 產生的 PNG（進 git）
│   ├── 02_std_table/ ...
│   └── ...
└── scripts/
    ├── generate_golden.sh   ← 在 Docker 執行：生成 golden PNG
    ├── compare_fixtures.js  ← 在本機執行：pixelmatch 比對
    └── report.html          ← 自動產生的視覺化報告
```

### Step 1：generate_golden.sh（Docker 執行）

```bash
#!/usr/bin/env bash
# 執行方式：docker exec system-odoo bash /addons/dobtor_doc_editor/tests/scripts/generate_golden.sh

set -e
FIXTURES_DIR="$(cd "$(dirname "$0")/../fixtures" && pwd)"

find "$FIXTURES_DIR" -name "*.docx" | while read -r docx; do
  dir=$(dirname "$docx")
  golden_dir="$dir/golden"
  mkdir -p "$golden_dir"

  echo "Generating golden: $(basename "$docx")"
  soffice --headless --convert-to png \
    --outdir "$golden_dir" "$docx" 2>/dev/null

  echo "  → $golden_dir/$(basename "${docx%.docx}").png"
done

echo "Done."
```

**多頁文件注意**：LibreOffice 對多頁 DOCX 輸出多個 PNG（`name_1.png`, `name_2.png`...），比對腳本需逐頁對應。

### Step 2：compare_fixtures.js（本機執行）

```javascript
// compare_fixtures.js
// 執行環境：本機 Node.js（非 Docker）
// 依賴：npm install puppeteer pixelmatch pngjs glob

const pixelmatch = require('pixelmatch');
const { PNG } = require('pngjs');
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const glob = require('glob');

const THRESHOLD = 0.05;  // 5% 為 Pass/Fail 邊界
const FIXTURES = glob.sync('tests/fixtures/**/*.docx');

async function renderDocxWithCanvasEditor(page, docxPath) {
  // 重要：等待字型載入完成後再截圖
  // 流程：
  // 1. document.fonts.ready — 等待所有 CSS @font-face 載入
  // 2. window.__canvasEditorReady — 等待 canvas-editor 渲染完成後設置的旗標
  //
  // canvas-editor 渲染完成後，需在程式碼中執行：
  //   window.__canvasEditorReady = true;
  // 否則 Puppeteer 可能在字型尚未載入時截圖，導致 CJK 字型退回 Arial，diff 爆表

  await page.goto(`http://localhost:10003/test-fixture?path=${encodeURIComponent(docxPath)}`);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => window.__canvasEditorReady === true, { timeout: 10000 });

  return page.screenshot({ encoding: 'binary' });
}

async function runComparison() {
  const browser = await puppeteer.launch();
  const results = [];

  for (const docxPath of FIXTURES) {
    const goldenPath = path.join(
      path.dirname(docxPath), 'golden',
      path.basename(docxPath, '.docx') + '.png'
    );
    if (!fs.existsSync(goldenPath)) {
      console.warn(`⚠️  No golden for: ${docxPath}`);
      continue;
    }

    const page = await browser.newPage();
    const renderedBuffer = await renderDocxWithCanvasEditor(page, docxPath);
    await page.close();

    const golden = PNG.sync.read(fs.readFileSync(goldenPath));
    const rendered = PNG.sync.read(Buffer.from(renderedBuffer));
    const diff = new PNG({ width: golden.width, height: golden.height });

    const numDiff = pixelmatch(
      golden.data, rendered.data, diff.data,
      golden.width, golden.height,
      { threshold: 0.1 }
    );
    const diffRatio = numDiff / (golden.width * golden.height);

    // 輸出 diff image（供人工檢視）
    if (diffRatio >= THRESHOLD) {
      const diffPath = goldenPath.replace('.png', '_diff.png');
      fs.writeFileSync(diffPath, PNG.sync.write(diff));
    }

    results.push({
      fixture: path.relative('tests/fixtures', docxPath),
      diffRatio,
      pass: diffRatio < THRESHOLD,
    });
  }

  await browser.close();
  printReport(results);
}

function printReport(results) {
  console.log('\n=== Canvas-Editor 還原度報告 ===\n');
  results.forEach(r => {
    const icon = r.pass ? '✅' : '❌';
    console.log(`${icon} ${r.fixture.padEnd(50)} ${(r.diffRatio * 100).toFixed(1)}%`);
  });
  const passed = results.filter(r => r.pass).length;
  console.log(`\n${passed}/${results.length} 通過（目標：全部 < 5%）`);
}

runComparison().catch(console.error);
```

### `window.__canvasEditorReady` 旗標約定

在 `doc_editor.js` 的渲染完成回呼中，需設定此旗標：

```javascript
// doc_editor.js（Phase 1 實作 Renderer 時加入）
editor.on('rendered', () => {
  window.__canvasEditorReady = true;
});
```

> **字型問題的根因**：`document.fonts.ready` 只等待 CSS `@font-face` 宣告的字型。
> canvas-editor 透過 Canvas 2D `ctx.font` 指定字型時，瀏覽器在第一次實際繪製前
> 不保證字型已載入。必須等 canvas-editor 的 `rendered` 事件（實際繪製完成後），
> 才能確保 CJK 字型不退回 Arial。

### 目標還原度（Phase 別）

| Phase | 目標 diff% | 瓶頸 |
|-------|------------|------|
| Phase 0 基準（現況）| ~40-60%（估計）| 表格跑版、字距誤差 |
| Phase 1 完成後 | ~20-30% | Parser 正確，Renderer 仍用舊路徑 |
| Phase 2 完成後 | ~10-15% | HarfBuzz WASM 改善行高精度 |
| Phase 3 完成後 | **< 5%** | Layout Engine + TableLayout 完整 |

### 注意事項

1. **Golden PNG 進 git**：42 份 fixture × 平均 200KB ≈ 8MB，可接受
2. **字型一致性**：LibreOffice（Docker）與 canvas-editor（本機）需使用相同字型（Noto CJK），否則比對無意義
3. **跨頁 vMerge 的測試重點**：`03_complex_table/` 的多頁估驗表格是此問題的關鍵 fixture

---

## Phase 0 完成條件

| 條件 | 狀態 |
|------|------|
| 42 份 fixture DOCX 收集完成 | ✅ |
| `capability_audit.md` 完成（含兩個隱藏大魔王）| ✅ |
| `architecture_decision.md` 完成（本文件）| ✅ |
| `generate_golden.sh` 建立並執行，golden PNG 進 git | ❌ |
| `compare_fixtures.js` 建立，可輸出基準 diff% | ❌ |
| patch-package 安裝並建立 `patches/` 目錄 | ❌ |

**Phase 0 → Phase 1 的進入條件**：上表全部 ✅

---

## 附錄：Phase 1 開始前的自我檢查清單

- [ ] `LineMetrics` 介面的欄位定義是否涵蓋 Phase 2 HarfBuzz 的需求？
- [ ] `CellNode.isContinuation` 是否足以讓 Phase 3 TableLayout 處理跨頁 vMerge（連續渲染 + border 省略）？
- [ ] `SectionNode` 是否記錄了 headerReference / footerReference（奇偶頁/首頁切換）？
- [ ] `FloatImageNode` 的位置模型是否能表達 Word 所有 anchor 定位模式（絕對位置 / 相對欄 / 相對頁）？
- [ ] `window.__canvasEditorReady` 旗標約定是否已在 `doc_editor.js` 中預留？
