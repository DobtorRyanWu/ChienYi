# Sprint 20 — CI/CD 上線（補上唯一 P0 缺口）

**期間**：2026-05-09
**主軸**：把延宕 13 sprint 的 P0-3（CI/CD）真正轉綠
**結論**：CI workflow 早已存在但 typecheck job 因 1 個檔案 8 條 TS error 而紅燈；本 sprint 修復 typecheck blocker、補強 CI gates、釐清規劃書 §0.6.1 與 §0.6.10 的 audit 誤判（CI 檔在但 typecheck 紅）。

---

## 0. 入工前 audit 誤判更正

| 項目 | 規劃書 §0.5/§0.6 原認定 | **2026-05-09 實測** |
|---|---|---|
| `.github/workflows/` 存在性 | ❌ 不存在 | ✅ **`addons/.github/workflows/dobtor_doc_editor_ci.yml` 已 154 行** |
| CI 是否能綠 | n/a | ❌ **typecheck job 因 DocPropsParser.ts 8 條 TS error 紅燈**（本機 `npm run typecheck` 同樣紅） |
| 結論 | 缺 CI | **CI 結構在、缺 typecheck 修復 + 強化 gates** |

§0.6.1 / §0.6.6 P0-3 / §0.6.10 W1 / §0.6.13 等三處 audit 漏看 `addons/.github/`（驗證者只查了 `addons/dobtor_doc_editor/.github/` 子目錄；workflow 應放在 git repo root，即 `addons/`）；此為 §0.6 第 4 項 audit 誤判（前 3 項為 partner_ids/bookmark/8 docs）。

---

## 1. typecheck blocker 修復

### 1.1 症狀

`npm run typecheck` 8 條 error，全部集中在 `static/src/core/ooxml/DocPropsParser.ts`：

```
DocPropsParser.ts(64-78,*): error TS2345: Argument of type 'import("@xmldom/xmldom").Element'
  is not assignable to parameter of type 'Element'.
  Type 'Element' is missing the following properties from type 'Element':
  classList, className, clientHeight, clientLeft, and 110 more.
```

### 1.2 根因

DocPropsParser 與其他 Parser 慣例不同：

| 檔案 | DOMParser 取得方式 | TS 推論 Element 型別 |
|---|---|---|
| `ParagraphParser.ts` / `SectionParser.ts` / `TableParser.ts` | global `DOMParser`（DOM lib 提供） | DOM lib `Element`（與 caller 介面一致）|
| `HeaderFooterParser.ts` | `if (typeof DOMParser === 'undefined') throw` 後使用 global | 同上 |
| **`DocPropsParser.ts`** | **`import { DOMParser } from '@xmldom/xmldom'`** | **xmldom 自己宣告的 `Element`**（少 110 個 DOM 屬性，與 `pickText(root: Element, ...)` 簽名衝突） |

vitest 由 `tests/setup.ts` 把 xmldom 的 DOMParser 注入 globalThis，所有其他 Parser 直接用 global 即可；DocPropsParser 是 Sprint 13 新增時忘了沿用慣例。

### 1.3 修法

對齊 HeaderFooterParser 慣例：

- 移除 `import { DOMParser } from '@xmldom/xmldom'`
- 加 runtime `typeof DOMParser === 'undefined'` 檢查（throw with 提示訊息）
- `let doc: Document | null` 顯式型別

```diff
-import { DOMParser } from '@xmldom/xmldom';
 import type { DocProps } from './ast/types';
 import type { OoxmlPackage } from './package/PackageReader';
+
+// 慣例：使用 global DOMParser（瀏覽器原生；vitest 由 tests/setup.ts 注入 @xmldom/xmldom）
+// 避免直接 import @xmldom/xmldom 造成 Element 型別與 DOM lib 衝突

 export function parseDocPropsXml(xml: string): DocProps {
   if (!xml || !xml.trim()) return {};
-  let doc;
+  if (typeof DOMParser === 'undefined') {
+    throw new Error(
+      'DocPropsParser: DOMParser not available — Node tests must use vitest setup with @xmldom/xmldom',
+    );
+  }
+  let doc: Document | null;
   try {
     doc = new DOMParser().parseFromString(xml, 'text/xml');
```

### 1.4 驗證

| 指標 | 修前 | 修後 |
|---|---|---|
| `npm run typecheck` | ❌ 8 errors | ✅ 0 errors |
| `npm test` | 47 files / 735 tests pass + 1 skipped | **47 files / 735 tests pass + 1 skipped**（unchanged）|
| `npm run build:frontend` | ✅（197KB bundle） | ✅（197KB bundle，size +13KB vs Sprint 14 因 Sprint 15-19 累積）|
| `flake8 --select=E9,F63,F7,F82` | ✅ exit 0 | ✅ exit 0 |
| `xmllint --noout` 全 XML | ✅ 0 fails | ✅ 0 fails |

DocPropsParser 既有 11 個 unit test（`tests/unit/DocPropsParser.test.ts`）行為驗證 + 真 fixture smoke 全綠，無行為變更。

---

## 2. CI workflow 強化

### 2.1 補入的 step

| Step | 位置 | 效益 |
|---|---|---|
| **Vitest junit reporter** | frontend job | PR 失敗時可下載 junit XML 看哪個 case 紅 |
| **Upload vitest report on failure** | frontend job | `actions/upload-artifact@v4` 保留 14 天 |
| **Pytest collect-only** | python job | Odoo runtime 在 CI 不存在無法跑測試，但 collect-only 可抓 SyntaxError/IndentationError；不是 syntax error 就視為 PASS |
| **Bash scripts syntax check** | python job | `bash -n tests/scripts/*.sh`，避免 visual_regression / generate_golden 改動有 syntax bug 才在生產環境炸 |

### 2.2 維持原樣的 gates

- **TypeScript strict typecheck**（`npm run typecheck`）— 本 sprint 修綠
- **Vitest 47 files / 735 tests**（含 Sprint 12 fingerprint snapshot / Sprint 16 page count baseline / Sprint 18 grid search env-gated）
- **Rollup build**（產 `canvas-editor-custom.umd.js`，size > 50KB 守門）
- **Flake8 errors-only**（`E9, F63, F7, F82` — syntax/critical 等級）
- **Manifest literal check**
- **XML well-formed (xmllint)**
- **Visual regression** 仍維持 `workflow_dispatch` 手動／nightly（需要 Odoo + LibreOffice + Chromium runtime，CI runner 起一套成本太高，留 Phase F 再做）

### 2.3 .gitignore 補入

```
tests/vitest-junit.xml                          # CI 失敗才上傳，本機 npm test 也會生
tests/fixtures/sprint18_ratio_grid_report.json  # Sprint 18 grid search 產物
```

### 2.4 Trigger 規則

| 事件 | frontend | python | xml | visual-regression |
|---|---|---|---|---|
| `push` to main/master/develop（且改到 `dobtor_doc_editor/**`） | ✅ | ✅ | ✅ | ❌ |
| `pull_request`（同 path filter） | ✅ | ✅ | ✅ | ❌ |
| `workflow_dispatch` 手動 | ✅ | ✅ | ✅ | ✅ |

path filter 確保改 ChienYi 其他模組不會無謂跑 CI。

---

## 3. 為什麼不在這一輪做更多

| 候選擴張 | 為什麼留 Sprint 21+ |
|---|---|
| **Visual regression 自動跑** | 需要 CI runner 起 Odoo + LibreOffice + Chromium 容器，工程量 ≥ 1 sprint；nightly 即可 |
| **Pytest 真實執行** | 需要 Odoo 18 完整安裝（base addons + db），CI 時間從 5min 變 25min；待 Phase F 整合測試環境 |
| **Coverage tracking（c8/istanbul）** | 加碼預期但無迫切；先確保 typecheck/vitest/build 不退化 |
| **Sprint 19 留下的 7 個 -1 偏差個別擊破** | 這是不同 sprint 的 scope，與 CI 上線無關 |
| **ChienYi mixin 真實植入**（P1-2 second leg） | 屬下一個 P1 缺口，獨立 sprint 處理 |

---

## 4. 與規劃書 §0.6 的對應修正

本 sprint 結束後 §0.6 應更新項目：

| 段落 | 原狀 | **Sprint 20 後** |
|---|---|---|
| §0.6.1 Phase 0 / **CI/CD（github workflow）** | ❌ `.github/workflows/` 不存在 | ✅ **存在於 `addons/.github/workflows/dobtor_doc_editor_ci.yml`，typecheck 已修綠**；只剩 visual-regression 自動跑 + pytest 真執行 留 Sprint 21+ |
| §0.6.6 P0-3 CI/CD 上線 | ❌ | ✅ **frontend / python / xml 三 job 全綠；visual-regression 手動觸發** |
| §0.6.10 W1 CI/CD 上線 | ❌ | ✅ |
| §0.6.13 Sprint 20+ 第 1 順位 🔴 | CI/CD 上線 | **✅ 已完成**；改第 2 順位「ChienYi mixin 真實植入」上推 |
| §0.6.13 各 Phase 完成度 | Phase 0 = 90% / Phase 4.5 = 92% | **Phase 0 = 95%**（補入 CI 後僅缺 CONTRIBUTING.md）; Phase 4.5 = **96%**（13 項剩 P1-2 second leg ❌）|

---

## 5. 量化結果

| 指標 | 修前 | 修後 | Δ |
|---|---|---|---|
| `npm run typecheck` errors | 8 | **0** | -8 ✅ |
| Vitest tests | 735 pass + 1 skip | 735 pass + 1 skip | 0（不退化）|
| CI gates | 6（typecheck/vitest/build/flake8/manifest/xml） | **9**（+junit upload, +pytest collect, +bash syntax） | +3 |
| §0.6 audit 誤判清單 | 3（partner_ids / bookmark / 8 docs） | 4（+ CI workflow 存在性） | +1 audit 經驗 |

---

## 6. Sprint 20 後 Sprint 21+ 新優先級（修正）

依 §0.6.13 順序減去本 sprint 完成項：

1. ~~🔴 CI/CD 上線~~（**Sprint 20 完成**）
2. **🟡 ChienYi mixin 實際植入**（P1-2 second leg）— 至少 1 個 construction_\* 模型 inherit `doc.linked.mixin`
3. 🟡 7 個剩 -1 偏差 fixture 個別擊破（Sprint 19 留下；含 R6 keepNext act-on）
4. 🟡 Phase 3.6 註腳 / 尾註
5. 🟢 lazy_loader / pagination_engine.js 評估清理
6. 🟢 HarfBuzz 真接 Layout
7. 🟢 Phase 5 子項按使用量排序

---

**Sprint 20 一句話總結**：CI 不是「沒架」，是 typecheck 紅燈 13 sprint 沒人發現；改 1 個檔 8 行 + 補 3 個 gate，13 sprint 阻塞鬆綁。
