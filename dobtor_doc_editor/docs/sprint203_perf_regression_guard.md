# Sprint 203 — Phase 7 大檔 perf regression guard（49p synthetic、vitest 內 parse + layout 閾值守門）

**日期**：2026-05-24（週日）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§Phase 7 perf 殘項追蹤、Sprint 197 final audit「benchmark harness」中 ROI 殘項
**前置**：Sprint 202（49p 1375 段落 synthetic fixture 入庫、puppeteer 一次性量測 cold 1577ms / warm 758ms）

---

## Hypothesis

Sprint 202 落地 49p 大檔 synthetic fixture + 一次性量測、但**沒有 CI-runnable
的 perf regression alarm**——若後續 sprint 不小心引入 parse/layout 退化、
要等下次手動跑 `perf_baseline.mjs` 才會發現。

本 sprint 補 **vitest 內可跑的 parse + layout 階段 timing guard**、把
「parse / layout 時間漂移」變成 `npm test` 出口會抓的 regression alarm、
收口 Sprint 197 ROI「benchmark harness」殘項。

**Scope：**
- ✅ parse time guard
- ✅ layout time guard
- ✅ 結構斷言（段落數 1375 + 頁數 45-55）
- ❌ render time guard（需 browser canvas、留 perf_baseline.mjs puppeteer）

---

## 修法

新檔 `tests/integration/sprint203_perf_regression_guard.test.ts`（+109 行）：

### 2 個閾值守門 test

1. **cold parse + layout 一次量測**：
   - `OoxmlParser.parse(arr)` 量 parseMs
   - `layoutDocument(doc.sections)` 量 layoutMs
   - 斷言：parseMs < 600 / layoutMs < 1500 / totalMs < 2000

2. **warm 3-sample 平均**：
   - 預熱 1 次（JIT compile + 模組載入）
   - 連量 3 次 parse、取平均
   - 斷言：avg < 600（CI 多核共用 / GC 抖動 safety margin）

### 4 個具名常數（紀律 #2）

- `EXPECTED_PARAGRAPH_COUNT = 1375`（Sprint 202 規格）
- `EXPECTED_PAGE_COUNT_MIN = 45` / `EXPECTED_PAGE_COUNT_MAX = 55`（±10% 容忍）
- `PARSE_TIME_THRESHOLD_MS = 600`、`LAYOUT_TIME_THRESHOLD_MS = 1500`、
  `TOTAL_TIME_THRESHOLD_MS = 2000`

---

## Result — Sprint 203 量測（本機 Node 環境）

| 階段 | 量得（ms） | 閾值（ms） | 安全係數 |
|---|---|---|---|
| parse cold | 265.9 | 600 | 2.3× |
| parse warm 3-sample 平均 | 95.3（97.8/90.3/97.8） | 600 | 6.3× |
| layout cold | 228.3 | 1500 | 6.6× |
| total cold | 494.2 | 2000 | 4.0× |

結構斷言：**段落數 1375 ✅ / 頁數 49 ✅**（落在 [45, 55] 容忍區間）

---

## 為何 parse cold 265ms（vs Sprint 202 puppeteer 量測 42.3ms）

| 環境 | parse 量得 | 差異原因 |
|---|---|---|
| Sprint 202 puppeteer（V8 in browser） | 42.3 ms | 含 JIT warm-up、跑了多次取 median |
| Sprint 203 vitest（Node 純）| 265.9 ms | cold 第 1 次跑、含 OoxmlParser class JIT |
| Sprint 203 warm 3-sample 平均 | 95.3 ms | JIT 後仍比 puppeteer 慢 ~2.3× |

差異來自：
1. **Sprint 202 puppeteer 是 median of 3**、Sprint 203 cold 是第 1 次（含 JIT）
2. **Node 啟動成本**：每 test 重新載入 module、cache miss
3. **vitest worker 多執行緒 GC pressure**：full vitest sweep 99 個 test file
   並行跑、GC pause 可能拉長 parse 量測

Sprint 203 thresholds **不直接對應** Sprint 202 puppeteer 數據、而是針對
vitest 環境抓 regression。兩個量測點各自為政、互補完整 perf 監控覆蓋。

---

## 為何不量 render

- render 需要 `OffscreenCanvas` / `HTMLCanvasElement.getContext('2d')`
- Node 環境**無 browser canvas**、`canvas` npm 套件需 native 編譯（增加依賴重）
- render 量測仍由 `scripts/perf_baseline.mjs --filter 11_` puppeteer harness 跑、
  屬手動 / nightly 量測、不入 `npm test`

**分工**：
- `npm test` → 抓 parse + layout regression（vitest 即時 alarm）
- `node scripts/perf_baseline.mjs --filter 11_` → 抓 render regression（手動 / nightly）

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1946 passed + 1 skipped**（+2 sprint203）；單跑 sprint203 2/2 綠 |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | sprint203 不入 VR pipeline、layout/render 不變動 → 42 fixture VR 結構性 unchanged |
| L3 perf | ✅ 雙 anchor 量測點維持 | Sprint 202 puppeteer baseline + Sprint 203 vitest guard 互補 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**（OoxmlParser /
  layoutDocument 皆不改）、純 test 加 perf guard
- **#2 magic number**：6 個具名閾值常數、無 magic
- **#14.b clean scope**：commit = sprint203 test + audit doc + INDEX/snapshot；
  不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：
  - 不量 render（需 browser canvas、留 puppeteer）
  - 閾值用 3× safety margin、不追求精準（CI 環境抖動容忍）
  - 不寫複雜 JSON 趨勢追蹤、簡單 console.log 即可
- **#21**：fixture 不入 VR / ast snapshot / page count baseline（Sprint 202 排除集已含 11_）

---

## Phase 7 完成度更新

- Sprint 202 後 ~91%
- **Sprint 203 補 vitest 內 parse + layout regression guard**、Sprint 197 ROI
  「benchmark harness」中 ROI 殘項收口（render harness 仍由 puppeteer 跑）
- → **~92%**

剩餘 cluster（每個 2-3 sprint、合計 ~6 sprint）：
- OffscreenCanvas worker render（Sprint 197 + 201 雙驗不建議、不取）
- Web Worker parse（同上）
- 50+ 頁真實 ChienYi fixture audit（synthetic 已驗結構正確、真實 fixture 補 edge case）
- WPS 來源 fixture audit（低 ROI、需另尋來源）

---

## File-level summary

```
A  tests/integration/sprint203_perf_regression_guard.test.ts   +109 行
A  docs/sprint203_perf_regression_guard.md                     本 audit
M  docs/INDEX.md                                               +Sprint 203 entry
M  docs/progress_snapshot.md                                   Sprint 203 區塊 + Phase 7 ~91%→~92%
```

**淨 production code 變動 = 0 行**、vitest 1944→**1946**（+2 sprint203）、
VR byte-identical 第 58 連 unchanged、parse cold 266ms / warm avg 95ms /
layout cold 228ms（全部 <閾值、3-6× safety margin）、**Phase 7 完成度 ~91%→~92%**、
vitest perf regression alarm 自此入庫。
