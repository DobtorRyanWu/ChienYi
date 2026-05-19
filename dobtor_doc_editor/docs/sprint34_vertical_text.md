# Sprint 34 — Vertical CJK Text 初探（OOXML §17.18.93 ST_TextDirection V-suffix）

> **狀態**：⚠️ **規格誤解事件**：第一輪實作把 OOXML V-suffix 當「字符旋轉」處理（用 ctx.rotate）；
>   實測發現 V-suffix 規格實意為「**glyph orientation preserved**」= CJK 直書（字符正向 + 排列方向變直）。
>   渲染器層 ctx.rotate 反而把字符旋轉成橫躺，與 golden 不符。
> **日期**：2026-05-13
> **保留產出**：parser / AST / RenderContext API（save/restore/translate/rotate）擴充
> **撤回產出**：Layout 旋轉維度交換、CanvasRenderer canvas rotation 路徑
> **視覺收斂**：總體 mean 0.1156 → **0.1155**（無收斂，與 Sprint 33 等效）

## 1. 目標（與最終結果不符）

Sprint 33 spot check 確認 03_complex_table 全套管 5 fixture × 0.30 mean 主因是
`<w:textDirection w:val="tbRlV"/>` 垂直 cell 沒被正確渲染。
Sprint 34 目標：實作 tbRlV / lrTbV / tbLrV 渲染，預估 03 整體 0.166→0.108、總體 0.116→0.108。

## 2. 第一輪實作（已 revert）

四層改動：
1. **AST + Parser**：擴充 `CellNode.props.textDirection` union 接受 V-suffix variant ✅ 保留
2. **Layout**：vertical cell 用 rowHeight 當 lineWidth、cell.height = max line.width ❌ 已 revert
3. **RenderContext API**：新增 `save / restore / translate / rotate` ✅ 保留
4. **CanvasRenderer**：偵測 V-variant 套 `ctx.translate(x+width, y) + ctx.rotate(π/2)` ❌ 已 revert

## 3. 為何 revert

### 3.1 OOXML §17.18.93 V-suffix 規格實意

ST_TextDirection 6 種值的字符（glyph）渲染方向：

| Value | 流向 | Glyph 是否旋轉 |
|---|---|---|
| `lrTb` | 左→右、上→下 | 不旋轉（horizontal） |
| `tbRl` | 上→下、右→左 | **旋轉 90° CW**（Latin 直書） |
| `btLr` | 下→上、左→右 | **旋轉 90° CCW** |
| `lrTbV` | 左→右、上→下 | **不旋轉（V 表示 preserve）** |
| **`tbRlV`** | **上→下、右→左** | **不旋轉（CJK 直書）** |
| `tbLrV` | 上→下、左→右 | **不旋轉** |

**V 表示 "Vertical (glyph orientation preserved)"**，意即字符保持「正向」，只是排列方向變垂直。
這是 CJK 直書（中日韓垂直文字）的正確意義。

### 3.2 我做反了

第一輪 CanvasRenderer 用 `ctx.rotate(π/2)`：
- 整個 cell 內容旋轉 90° CW
- **每個字符也跟著旋轉**（變橫躺）
- 結果：「工程名稱」每個字躺著向右倒，golden「工程名稱」每個字正向垂直堆疊

Spot check render PNG vs golden 立刻發現視覺更糟（雖然 pixel diff 數字差不多）。

### 3.3 為何 pixel diff 沒改變

| 版本 | 視覺 | pixel diff |
|---|---|---|
| Sprint 33（原本） | 每字 1 行垂直堆疊（看起來像簡陋直書） | 0.3078 |
| Sprint 34 第一輪（rotate） | 每字 90° 橫躺成一橫線 | 0.3079 |
| golden | 每字正向垂直堆疊（標準 CJK 直書） | — |

兩個錯誤方向的 pixel 差異量級接近 — pixelmatch 對「位置錯誤」與「方向錯誤」評分相當。

### 3.4 正確 CJK 直書渲染（留 Sprint 35+）

需要 **char-level 垂直擺放**：

```ts
// 概念實作（Sprint 35+ TODO）
for (const ch of line.text) {
  // 字符保持正向（不 rotate），但位置往下推
  ctx.fillText(ch, columnX, charY + fontSize * 0.8);
  charY += metrics.charHeight(ch);
}
// 多列時 columnX 向左推（tbRlV）或向右推（tbLrV）
```

這需要 renderLine / renderBox 分支處理（從「box-level」改「char-level」），是 Sprint 35+ 的明確任務。

## 4. 保留的基礎建設（Sprint 35+ 直接用）

| 改動 | 檔案 | 用途 |
|---|---|---|
| AST `CellNode.props.textDirection` 擴充 V-suffix union | [`ast/types.ts`](static/src/core/ooxml/ast/types.ts) | 為 char-level vertical render 提供 cell-level 訊號 |
| `TableParser` 接受 lrTbV/tbRlV/tbLrV | [`TableParser.ts:254`](static/src/core/ooxml/table/TableParser.ts) | 讓 docx 的 V-suffix value 進入 AST，不再被靜默丟棄 |
| RenderContext 新增 `save / restore / translate / rotate` | [`render/types.ts`](static/src/core/render/types.ts) | 為未來純座標變換（如 Latin tbRl 字符旋轉）提供 API |
| MockRenderContext / BrowserCanvasRenderContext 實作這 4 個方法 | 同上 | 兩 Context 都支援 |
| `CellLayout.textDirection` 透傳欄位 | [`layout/types.ts`](static/src/core/layout/types.ts) | Renderer 偵測 V-variant 用 |

## 5. SOP 三層

### 5.1 Vitest（layer 1）

- **Parser**（[`TableParser.test.ts`](tests/unit/TableParser.test.ts)）：it.each 6 種 ST_TextDirection 值 + 未知值忽略 → **6+1 新 test 通過**
- **Renderer**（[`CanvasRenderer.test.ts`](tests/unit/render/CanvasRenderer.test.ts)）：
  - tbRlV cell 走 horizontal 路徑（不呼叫 ctx.rotate）
  - V-variant 與水平 cell 的 fillText 數量相同
  - save/restore 數量永遠相等
  - **4 新 test 通過**
- **整合**：Sprint 12 fingerprint snapshot 更新（無 rotate ops 加入）；Sprint 16 page count baseline 仍 **0 mismatched**
- **結果**：**vitest 788/788 + 1 skipped**

### 5.2 Visual Regression v14（layer 2）

| Category | Sprint 33 | Sprint 34 | 變化 |
|---|---|---|---|
| 01_simple | 0.0700 | 0.0698 | -0.0002（噪音） |
| 02_std_table | 0.1241 | 0.1241 | 0 |
| 03_complex_table | 0.1659 | 0.1657 | -0.0002 |
| 04_with_image | 0.2773 | 0.2773 | 0 |
| 05_header_footer | 0.0357 | 0.0357 | 0 |
| 06_template | 0.0222 | 0.0220 | -0.0002 |
| **總體 mean** | **0.1156** | **0.1155** | **-0.0001** |

零收斂（與 Sprint 33 等效）。

### 5.3 Visual spot check（layer 3）

`1121229-全套管(共1)` page 1 確認：
- 第一輪 ctx.rotate 版本：c0「工程名稱」chars 90° 橫躺 → revert
- Revert 後（當前）：c0 chars 每字 1 行垂直堆疊（與 Sprint 33 等效）

## 6. 教訓

1. **Sprint 33 教訓延伸**：spot check PNG 找根因 ✅；但**根因找到後還要查 OOXML spec 對該值的精確意義**
2. **V-suffix 不是「More Vertical」**：「V 表示 glyph orientation preserved」是反直覺的命名
3. **canvas rotate ≠ CJK 直書**：CJK 直書需要 char-level 渲染（每字獨立正向放置），不是整體 rotate
4. **Sprint 30/31/32/33/34 教訓共通點**：每個「明顯該修的東西」前都要先 verify 改完之後 visual 變化方向，而非單靠 pixel diff metric 判斷

## 7. 工作量 vs 收斂

| 項目 | 投入 | 產出 |
|---|---|---|
| Parser V-suffix 擴充 | ~10 行 | ✅ 基礎建設 |
| AST type 擴充 | ~1 行 | ✅ 基礎建設 |
| RenderContext API 擴充 + 兩 Context 實作 | ~30 行 | ✅ 基礎建設（含 Mock 測試輔助） |
| Layout vertical 維度交換 | ~30 行 | ❌ revert |
| Renderer canvas rotate | ~30 行 | ❌ revert |
| Unit tests | ~150 行 | ✅ 10 新 test |
| audit doc | ~250 行 | ✅ 留教訓給後人 |
| 視覺收斂 | — | **0%** |

## 8. 距離 mean ≤ 0.10 終點預估（Sprint 34 後修正）

| Sprint | 主軸 | 實際 mean |
|---|---|---|
| Sprint 30 | DPI 150 | 0.1386 |
| Sprint 31 | R1 overflow gating | 0.1176 |
| Sprint 32 | Paragraph alignment | 0.1156 |
| Sprint 33 | vMerge anchor render（零收斂） | 0.1156 |
| **Sprint 34（本）** | **Vertical text 基礎建設 + 第一輪實作失敗 revert** | **0.1155** |
| Sprint 35（預測） | **CJK 直書 char-level 渲染**（修 03 全套管 5 fixture × 0.30） | ~0.105 |
| Sprint 36（候選） | 04_with_image photo size + content | ~0.095 ← 達標 |

**修正預估剩 1-2 個 Sprint（Sprint 35-36）**達 mean ≤ 0.10。Sprint 33 + Sprint 34 連續兩次「找到了根因但選錯修法」，付出的代價是兩個 sprint 的 metric 停滯。Sprint 35 工作方向已**明確**（char-level CJK 直書渲染），但實作成本比預期高。

## 9. Sprint 35 工作大綱

### 9.1 Renderer renderLine vertical path

新增 `renderLineVertical(line, columnX, baseY, columnWidth)`：
- 把 line.items 中每個 box.text 拆成單字符
- 每字符獨立 fillText，位置 = `(columnX + columnWidth/2 - fontSize/2, charY + fontSize × 0.8)`
- charY 累積（advance = fontSize）

### 9.2 Layout cell vertical 排版（重新設計）

- innerWidth = cell.width - padding.left - padding.right = 單列寬（容納單字寬 + 字距）
- innerHeight = cell.height - padding.top - padding.bottom = 字符流向（多字符垂直堆疊）
- 多段 paragraph 各自一列，列數 = paragraph count
- LineBreaker 不適用（vertical 是 char-by-char，不是 box 拆解）

### 9.3 預估視覺收斂

- 03 全套管 5 fixture × 0.30 → ~0.15（-50%）✅
- 03_complex_table 0.166 → 0.10
- 總體 mean 0.116 → 0.105（接近達標）

工作量：1 個 sprint（renderLineVertical 新函式 + layoutCell vertical 路徑 + ~6 個 unit test）。
