# Sprint 1 OOXML Parser 補完 Audit（W11+ 主線起點）

**狀態**：W11+ 主線 Sprint 1 — Phase 1 子模組 audit  
**完成日期**：2026-05-07  
**對應計畫**：[federated-swimming-creek.md](/home/chichi/.claude/plans/federated-swimming-creek.md) §「W11+ 進入主線 Sprint 1（OOXML Parser 補完）」  
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.2 Phase 1](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)

---

## 1. 範圍與動機

W1-W10 補強衝刺已把產品化基礎（CI/CD、portal、安全、樂觀鎖、遙測、a11y 等）打穩。W11+ 進入既有規劃 Sprint 1 主線：把 OOXML Parser 從「半實裝有 unit test」升級為「fixture-driven 回歸保護」。

不在本 Sprint 範圍：
- 全 Layout Engine 重寫（屬 Sprint 2-3）
- Canvas Renderer 重做（Sprint 4-5）
- HarfBuzz 整合產品化（Sprint 6+）

本 Sprint **只動測試與 audit doc**，不改 parser 邏輯。理由：14 個子目錄的 unit test 已 333 個，再用合成 XML 加項目邊際效益遞減；該補的是「對 42 份真實 fixture 的回歸保護」。

---

## 2. 子模組覆蓋現況（從 unit test 數量回推）

| 子模組 | 檔案 | 行數 | Unit test 案 | 真 fixture 覆蓋 | Sprint 1 補強 |
|---|---|---|---|---|---|
| package/ | PackageReader.ts | — | 5 | ✅ 全 fixture | 已通 |
| document/ | DocumentParser + ParagraphParser | — | 8 + 23 | ✅ 03_e2e_mapper | 已通 |
| table/ | TableParser + GridResolver + BorderConflictResolver | — | 8 + 9 + 14 | ✅ 03_complex_table | **新加 vMerge audit**（05） |
| styles/ | StyleResolver + ThemeResolver + TableStyleApplicator + colorResolver | 301+275+230+51 | 12 + 多 | ⚠️ 部分 | **新加 fixture audit**（05） |
| numbering/ | NumberingResolver | 296 | 25 | ⚠️ 透過 e2e | 已驗證 numFmt 全套 |
| section/ | SectionParser | 180 | 14 | ✅ 04_ast_snapshot | **新加 A4 portrait audit**（05） |
| header-footer/ | HeaderFooterParser | — | 6 | ✅ 部分（01_simple 有 hdr/ftr part）| **新加 audit**（05） |
| drawing/ | DrawingParser | — | 11 | ✅ 04_with_image | **新加 fixture audit**（05） |
| font/ | FontMetrics + ShapingEngine | — | 8 + 5 | n/a（runtime） | 已通 |
| ast/ | types.ts | — | n/a | — | — |
| mapper/ | ToCanvasEditor.ts | — | 19 | ✅ 03_e2e_mapper | 已通 |
| units/ | units.ts | — | n/a（型別） | — | — |
| utils/ | dom.ts | — | n/a | — | — |
| OoxmlParser（root） | OoxmlParser.ts | 322 | — | ✅ 全 fixture | **新加 AST snapshot**（04） |

新加 (04) (05) 指：

- `tests/integration/04_ast_snapshot.test.ts` — 42 fixture 結構指紋 snapshot
- `tests/integration/05_parser_audit.test.ts` — 各子模組對真實 fixture 的 audit

---

## 3. 新測試說明

### 3.1 04_ast_snapshot — AST 結構指紋回歸

對 42 份 fixture 各算一份指紋，用 vitest snapshot 釘住：

```ts
{
  category, filename,
  totalElements, paragraphTerminators, tableCount, imageCount, hyperlinkCount,
  colWidthSum: number[],   // 每張表 colgroup 寬度總和
  tableShapes: string[],   // "rowsxcols"
  textLength, textHead,    // 前 80 字
  textSha1,                // 完整文字 SHA1
}
```

**不取整個 IElement[] dump 的理由**：
- 完整 dump 太大，diff 噪音掩蓋真實 regression
- 文字內容夾在 valueList / trList，平面比對失真

**何時要 `vitest -u`**：
- 新增 fixture
- Parser 已知行為變更（PR review 通過後）
- **不可在「不知道為什麼變」的時候 -u**

### 3.2 05_parser_audit — 子模組 fixture-driven audit

8 個 audit case：

| Case | 子模組 | Fixture | 驗證點 |
|---|---|---|---|
| StyleResolver 解出非空 StyleMap | styles/ | 01_simple | size > 0 + 至少一筆有 pPr/rPr |
| 02_std_table StyleMap 有 conditional 路徑 | styles/ | 02_std_table | pProps/rProps 存在 |
| 每份 fixture 至少一節 page > 0 | section/ | 4 份代表 | width/height/orientation |
| A4 portrait 595×842pt（±5pt） | section/ | 01_simple | EMU/twips 換算正確 |
| 04_with_image 至少抽出一張圖 | drawing/ | 04_with_image | inlineImage/floatImage |
| 03_complex_table 14 欄 | table/ | 03_complex_table | grid.length >= 14 |
| Cell gridSpan/rowSpan/gridCol 正常 | table/ | 03_complex_table | 無 NaN/負數 |
| Header/Footer 至少存一個 | header-footer/ | 01_simple | headers.size + footers.size > 0 |

### 3.3 visual_regression.mjs — 像素級回歸（手動觸發）

`scripts/visual_regression.mjs`：puppeteer + pixelmatch，比對 canvas-editor 渲染結果與 LibreOffice golden PNG（共 126 張）。

**為什麼不掛 npm test**：
- canvas-editor 需 WebGL / 字型，CI runner 跑不穩
- 字型 fallback 環境差異會放大像素差
- 設計為**手動觸發**：`node scripts/visual_regression.mjs --max-diff 0.02`

**輸出**：
- `tests/fixtures/visual_regression_report.json` — 全 fixture 報告
- `tests/fixtures/<cat>/golden/<name>-N_diff.png` — 每張差異圖
- 退出碼 0 = 全過、1 = 有 fixture 超過門檻、2 = parse/render fatal

**已知限制**：
- 字型：dev 機需裝 `fonts-noto-cjk`，否則中文 boxify
- DPI：harness 用 96 DPI；golden 也須相同 DPI
- Anti-alias：閾值預設 2%，吸收邊界抖動

---

## 4. Sprint 1 中發現的事實

### 4.1 fixture 命名與內容對不齊（小坑）

`tests/fixtures/05_header_footer/` 目錄收的是「自主檢查表---X.docx」共 7 份，但 `unzip -l` 顯示這些 docx 內**完全沒有** `word/header*.xml` 或 `word/footer*.xml` part。真正帶 header/footer 的 fixture 在 `01_simple/`（每份監造會議記錄都有 2 個 header/footer part）。

**結論**：05_header_footer 目錄名誤導，audit 改用 01_simple fixture。後續若要做 header/footer 專項回歸，應從 01_simple 抽 2-3 份移到 05_header_footer，或重命名 05 為「自主檢查表表格」。

### 4.2 StyleEntry 沒有 `type` 欄位

[ast/types.ts:342](../static/src/core/ooxml/ast/types.ts) 的 `StyleEntry` interface 只有 `pProps / rProps / basedOn / conditional`，**沒有** `type: 'paragraph' | 'character' | 'table'` 欄位。原本以為可以 audit「StyleMap 含 type=table」，實際上要看的是 `entry.conditional` 是否存在（只有 type='table' 的 style 才會展開 conditional）。

**規劃文件對應修正**：§5.2 Phase 1.3 提到的「每種 style type 各 5 個 fixture」其實已被 unit test 覆蓋；fixture 端的 type 區分要靠 `conditional` 欄位推斷。

### 4.3 AST snapshot 暴露的可觀察事實

從 snapshot data 一眼看出：

- **01_simple**（會議記錄）：1 張表格、~170 paragraph terminator、~1500 字、無圖
- **02_std_table**（週報）：2-5 張表格、平均 99 IElement/份、表格 colWidthSum 一致
- **03_complex_table**（送審管制）：100-300 IElement，14-18 欄寬表
- **04_with_image**（含照片會議記錄）：圖片 ~6-15 張，hyperlink count 帶值
- **05_header_footer**（自主檢查表）：表格密集（avg 298 IElement），都 0 圖
- **06_template**（樣板）：avg 280 IElement，2-3 張表

這些指紋一旦未來被 parser 改動意外影響（例：bullet 解析改變導致 paragraphTerminators 跳數），snapshot 立刻失敗，比 `expect(...).toBeGreaterThan(0)` 強得多。

---

## 5. Sprint 1 後 Phase 1 殘餘工作

不在本 Sprint，留給後續 sprint 處理：

| 項目 | Phase | 說明 |
|---|---|---|
| visual regression 自動化納入 CI | Phase 1.10（新增） | 解 CI runner 字型與 WebGL 問題；可考慮用 docker-in-docker + headless chromium |
| numbering 中文編號渲染對 vs 跑版 | Phase 5（renderer） | 編號文本展開（`%1.%2.`）目前 parser 透傳，由 renderer 解碼，需 fixture 比對 |
| `<m:oMath>` 數學公式 | Phase 1.9 進階結構 | parser 還沒有 OMML support，fixture 也沒有含公式的 |
| `<w:sdt>` 內容控制項 | Phase 1.9 進階結構 | 樣板系統會用到，目前 parser 跳過 |
| `<w:ins>/<w:del>` 追蹤修訂 | Phase 1.9 進階結構 | parser 目前不抽，留給 Sprint 8+（協作衝突合併） |

每項落單到 [d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md](/home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md) 對應 Sprint 即可。

---

## 6. 驗收

- 04_ast_snapshot.test.ts：42 snapshot 寫入並通過
- 05_parser_audit.test.ts：8 audit case 全綠
- visual_regression.mjs：dry-run 模式 8/8 fixture parse 通過
- 不破壞既有 333 vitest（驗證指令見 §7）

---

## 7. 驗證指令

```bash
# 全 vitest（含新加 50 個 case：42 snapshot + 8 audit）
cd addons/dobtor_doc_editor && npm test

# 只跑 audit
npx vitest run tests/integration/05_parser_audit.test.ts

# Visual regression dry-run（無需 puppeteer）
node scripts/visual_regression.mjs --dry-run --filter 02_std

# Visual regression 完整（需 puppeteer + 字型）
node scripts/visual_regression.mjs --max-diff 0.02
```

---

**附註**：Sprint 1 完成後即進入 Sprint 2（Layout Engine 起步）。屆時 04 + 05 兩支 test file 會作為「Layout Engine 改動沒打壞 Parser」的回歸護欄持續被引用。
