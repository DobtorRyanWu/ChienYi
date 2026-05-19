# Sprint 13 docProps 自動讀取 + Knuth-Plass 斷行器

**狀態**：W11+ 主線 Sprint 13 — 文件 metadata 自動接通 + 進階斷行算法
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §3.1 / §5.6](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint12_field_metadata_ops_fingerprint.md](sprint12_field_metadata_ops_fingerprint.md)

---

## 1. 範圍

Sprint 12 完成完整 field 系統 + fingerprint regression baseline 後，Sprint 13 收兩個獨立但同等重要的工作：

1. **A. OOXML core.xml docProps 自動讀取**
   - `DocumentNode.docProps`（title / creator / subject / description / keywords / lastModifiedBy / created / modified）
   - `DocPropsParser`：解析 `docProps/core.xml` （走 root .rels 找 `core-properties` 關聯，找不到時 fallback 慣例路徑）
   - 容錯：缺檔 / 解析失敗 / 純文字輸入 → 空 docProps `{}`，不 throw
   - 真實 fixture 整合測試：01_simple 第一份 docx 的 docProps 至少含一欄
2. **B. Knuth-Plass 斷行器（opt-in）**
   - `LineBreakOptions.algorithm: 'greedy' | 'knuth-plass'`，預設 `'greedy'` 維持 Sprint 2-12 行為
   - K-P 完整實作：prefix sum / adjustment ratio / badness / demerits / DP backtrack
   - 自動 fallback：當 `getLineWidth` callback 提供時走 greedy（K-P 不支援 per-line 動態行寬）
   - 中文避頭尾 post-pass（共用 greedy 的 PROHIBITED_LINE_START / END 規則）
   - forced break（page / column）透傳 `Line.forcedBreakAfter`

落地：

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | M | `DocumentNode.docProps` + `DocProps` interface |
| `static/src/core/ooxml/DocPropsParser.ts` | A | `parseDocProps(pkg)` / `parseDocPropsXml(xml)` |
| `static/src/core/ooxml/OoxmlParser.ts` | M | Step 8: `parseDocProps(pkg)` 灌入 documentNode |
| `static/src/core/ooxml/document/DocumentParser.ts` | M | DocumentNode 字面值補 `docProps: {}` |
| `static/src/core/ooxml/index.ts` | M | export `parseDocProps` / `parseDocPropsXml` |
| `static/src/core/layout/LineBreaker.ts` | M | `LineBreakOptions.algorithm` + `breakParagraphKP` + `applyKinsokuAbs` |
| `tests/unit/ToCanvasEditor.test.ts` | M | makeDoc helper 補 `docProps: {}` |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/DocPropsParser.test.ts`（新檔） | 11 | 完整 metadata / 部分缺漏 / 錯誤輸入 / OoxmlPackage 整合 / fixture smoke |
| `tests/unit/layout/Sprint13_KnuthPlass.test.ts`（新檔） | 11 | K-P 基本行為 / forced break / fallback / 行寬均勻度 / 全字數保留 / 邊界 |

**全套**：vitest 45 files / **699 tests pass**（Sprint 12 後 43/677 → 45/699，+2 files +22 case）；Python 54 case 全綠。

**重要**：Sprint 12 的 fingerprint snapshot **完全不變**（greedy 預設未動），證明 Sprint 13 對 fixture-level Renderer 輸出零影響。

---

## 2. 關鍵設計決策

### 2.1 docProps post-pass 而非 lazy

OoxmlParser 內第 8 步直接呼叫 `parseDocProps(pkg)`。理由：
- 解析成本極低（XML < 1KB、單一文件）
- DocumentNode 是「檔案級不可變快照」，metadata 也應一次取齊
- 沒做 lazy 是因為使用者呼叫 `parser.parse()` 已心理預期會把整份檔讀完；省毫秒沒意義，反而多一個 path

### 2.2 docProps fallback 鏈

```
1. Try root .rels 中尋找 type='...core-properties' 的 target → 標準路徑
2. Fallback: 直接看 pkg.parts 是否有 'docProps/core.xml'
3. Fallback: 回 {}
```

實務上 fixture 多數走 (1)，但少數舊 Word 版本 .rels 沒列 core 卻仍把檔放在 `docProps/core.xml`，(2) 兜底。

### 2.3 K-P 為何 opt-in 而非預設

**Snapshot stability**：Sprint 12 已用 fingerprint snapshot 鎖住「結構性 regression」入口。若 K-P 改成預設，所有 42 fixture 的 fingerprint 都會變動 → 無法區分「故意改動」與「意外 regression」。

K-P 對「西文 justify」效果顯著，對 fixture 主流（中文監造文件 + 嚴格 cell 寬度）改善有限；當前先把 algorithm 開出來給特殊需求 caller 用，未來決定預設化時可一次性更新 snapshot 並專文記錄。

### 2.4 K-P 不支援 `getLineWidth` callback

K-P 的核心是「對所有 (a, b) 對配對計算 lineRatio」，假設 lineWidth 對所有 candidates 一致。`getLineWidth` 會讓 lineWidth 隨 (lineIndex, accumulatedHeight) 變化 → 同一個 b 對不同 a 會有不同 target → DP graph 無法用 prefix sum 加速。

當前選擇 fallback 而非堅持實作：wrapSquare 動態行寬本身就罕見（floatImage 邊上文字），與 K-P 主要效益（西文 justify）正交。

### 2.5 K-P 演算法精簡程度

完整 K-P 含「fitness class」（4 級鬆緊度懲罰），讓相鄰行有相近鬆緊。Sprint 13 簡化版只用基本 demerits 公式：
```
demerits = (1 + badness)² + penalty²
badness = 100 * |r|³，clamped to 10000
```
不加 fitness class 的代價：相鄰行可能一行很鬆、一行很緊，視覺上跳。實測 fixture 沒看到明顯案例，留 Sprint 14+ 決定要不要補。

### 2.6 K-P 的避頭尾仍用 post-pass

中文避頭尾（PROHIBITED_LINE_START / END）跟 K-P 的 demerits 是兩種不同最佳化目標：
- K-P：總 badness 最小
- 避頭尾：禁止某些字符出現在行首/行尾

要把避頭尾整合進 K-P 的 demerits 函式（給違規斷點 +∞ 懲罰）會讓代碼複雜化。當前用 post-pass：K-P 找出最佳斷點 → 對每個斷點套用 `applyKinsokuAbs` 微調。

代價：K-P 認為「最佳」的斷點可能因為避頭尾被推一格，導致行寬比 K-P 預期略不平均。實務上偏差通常 < 1 字寬，可接受。

### 2.7 為何沒把 docProps 自動接到 LayoutOptions.documentMetadata？

Caller 端（doc_editor.js / Python controller）拿到 `documentNode.docProps` 後可自由決定要不要餵進 `LayoutOptions.documentMetadata`。讓 OoxmlParser 自動串就會：
- 強迫 caller 接受 docProps 的 author 而非自己注入（例如 Odoo 想用 res.users.name）
- 多一個隱式 magic dependency

把資料供應與消費解耦：Parser 出 docProps，Layout 只看 LayoutOptions。Sprint 13 的測試也是分離地驗證兩端。

---

## 3. fixture 影響

| 類別 | Sprint 12 avgPages | Sprint 13 avgPages |
|---|---|---|
| 01_simple | 1.9 | 1.9 |
| 02_std_table | 1.6 | 1.6 |
| 03_complex_table | 1.1 | 1.1 |
| 04_with_image | 2.7 | 2.7 |
| 05_header_footer | 4.2 | 4.2 |
| 06_template | 2.3 | 2.3 |

完全不變（greedy 預設 + Sprint 12 fingerprint snapshot 也未變動）。

---

## 4. Sprint 13 已知限制

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| K-P fitness class 未實作 | Sprint 13 簡化版 | Sprint 14+ 視需求補 |
| K-P 不支援 `getLineWidth` 動態行寬 | DP 結構不適用 | Sprint 14+（不重要） |
| K-P 預設未啟用 | snapshot stability | 待 caller 累積信心後切換 |
| docProps 不含 docProps/app.xml（Application/Pages 等） | OOXML §22.3 範圍 | Sprint 14+（如有 fixture 需要） |
| Visual regression（PNG 像素級 vs 251 PNG） | 不在 Sprint 13 範圍 | Sprint 14+ |
| HarfBuzz async batch shape | 仍 estimate width | Sprint 14+ Phase 2 |
| 註腳 / 尾註 | Paginator 沒概念 | Sprint 14+ §3.6 |
| wrapTight polygon | 仍降級 square | Sprint 14+ §3.4 |

---

## 5. 對 Sprint 1-12 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | DocumentNode 加 docProps，但 mapper 不消費 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無（greedy 預設） | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（Sprint 12 fingerprint） | **完全不變** | 2 case 全綠 |
| Sprint 2-12 unit tests | 無 | 全綠 |
| Python integration | 無 | 54 case 全綠 |

**vitest 全套**：45 files / **699 tests pass**（Sprint 12 後 43/677 → 45/699，新增 22 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（43 → 45 files；677 → 699 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 13
npx vitest run tests/unit/DocPropsParser.test.ts \
              tests/unit/layout/Sprint13_KnuthPlass.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 14）建議

到 Sprint 13，Layout / Renderer / 完整 metadata + K-P opt-in 都已 stable。Sprint 14 主軸建議：

1. **Visual Regression（puppeteer + BrowserCanvasRenderContext）** — 真瀏覽器跑、PNG diff vs 251 份 golden；需要建立 browser-friendly TS bundle + 修改 `scripts/visual_regression.mjs` fork 一份用我們自家 pipeline
2. **HarfBuzz async batch shape** — BoxBuilder 改 async pre-shape，replaces estimate width
3. **註腳 / 尾註（footnote / endnote）** — 解析 footnotes.xml + Paginator 預留 footnote 區
4. **wrapTight polygon** — drawing.xml polygon path 解析 + per-y lineWidth
5. **K-P 預設化評估** — 跑 fingerprint snapshot 對比 greedy / K-P 差異，決定是否切預設
6. **OOXML core.xml + Layout.documentMetadata 自動串接** — caller helper（如 Odoo controller）

**建議優先順序**：1（用 fingerprint snapshot 篩選異常）→ 3 / 4（fixture 級還原度）→ 2 / 5（精度收尾）

---

**附註**：Sprint 1-13 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- Sprint 11：Page header / footer 渲染 + PAGE 在 header/footer 自動套真值
- Sprint 12：完整 field 系統（DATE/TIME/AUTHOR/FILENAME）+ Renderer ops fingerprint regression
- **Sprint 13：OOXML docProps/core.xml 自動讀取 + Knuth-Plass 斷行器（opt-in）**

到 Sprint 13，Parser 端能完整還原 OOXML 文件（內容 + metadata + style + 媒體 + header/footer），Layout 端有兩種斷行算法可選，Renderer 端能完整呈現所有欄位 / shading / 裝飾 / 多欄分隔。Sprint 14 起進入 Visual Regression（像素級驗證）+ HarfBuzz / 註腳 等高階收尾階段。
