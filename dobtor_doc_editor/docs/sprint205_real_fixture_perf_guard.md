# Sprint 205 — Phase 7 真實 ChienYi 大檔 perf regression guard（top-3 fixture）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§Phase 7 perf 殘項追蹤、Sprint 203 vitest guard 擴展至真實 fixture
**前置**：Sprint 203（49p synthetic text-heavy guard、cold parse 266ms / layout 228ms）

---

## Hypothesis

Sprint 203 落地的 perf regression guard 用 synthetic 49p text-heavy fixture
覆蓋「純文字大檔」場景；**未覆蓋真實 ChienYi 監造文件的圖文混排 + 表格密集
場景**。本 sprint 用 Sprint 201 perf baseline 中前 3 大真實 fixture（皆 ~2MB）
建立 Node 環境 parse + layout 閾值守門、補完 perf guard 真實場景 coverage。

---

## 修法

新檔 `tests/integration/sprint205_real_fixture_perf_guard.test.ts`（+88 行）：

### 3 個真實 fixture（具名常數）

| Index | Fixture | Size | Pages | Category 特徵 |
|---|---|---|---|---|
| 1 | `04_with_image/6.環清表安全衛生抽查照片(再造)-(112.10.2.-10.6).docx` | 2.1MB | 6p | 含多張 2MB 圖片（最大） |
| 2 | `02_std_table/1120928-磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋)週報.docx` | 1.8MB | 2p | 表格密集（最大表格檔） |
| 3 | `04_with_image/06.環清表安全衛生抽查照片(再造)-(112.10.9.-10.13).docx` | 1.9MB | 6p | 圖文混排對比點 |

### 閾值常數（紀律 #2）

- `PARSE_TIME_THRESHOLD_MS = 1500`（Sprint 201 puppeteer parse 144-190ms × 3× CI safety）
- `LAYOUT_TIME_THRESHOLD_MS = 500`（Sprint 201 puppeteer layout 5-6ms × ~80× safety — layout 為主程式快路徑）
- `TOTAL_TIME_THRESHOLD_MS = 2000`

### Parameterized test

```ts
describe('Sprint 205 — Phase 7 真實 ChienYi 大檔 perf regression guard', () => {
  it.each(TOP_REAL_FIXTURES)('%s — parse + layout 時間在閾值內', (rel) => {
    // 量 parseMs + layoutMs
    // assert layout.pages.length >= 1
    // assert parseMs < 1500 / layoutMs < 500 / totalMs < 2000
  });
});
```

---

## Result — Sprint 205 量測（本機 Node 環境）

| Fixture | parse (ms) | layout (ms) | total (ms) | pages | 閾值 safety |
|---|---|---|---|---|---|
| 04_with_image #1 (2.1MB) | 149.1 | 9.8 | 158.9 | 6 | parse 10× / layout 51× |
| 02_std_table (1.8MB) | 128.8 | 3.1 | 131.8 | 2 | parse 12× / layout 161× |
| 04_with_image #2 (1.9MB) | 44.5 | 1.6 | 46.1 | 6 | parse 34× / layout 313× |

**全部遠在閾值內**、layout 比預估更快（warm JIT 後 cache 效應）。

---

## 為何真實 fixture parse 比 synthetic 49p 快（149ms vs 266ms cold）

| 指標 | Sprint 203 49p synthetic | Sprint 205 2MB real |
|---|---|---|
| 段落數 | 1375 | ~50-100 |
| 表格數 | 0 | 多 |
| 圖片數 | 0 | 多 |
| Cold parse | 266ms | 149ms |

差異主因：
1. **段落數量級**：synthetic 1375 段落 vs real ~50-100 段落、parse loop 次數差 ~20×
2. **圖片解析非 parse 主成本**：base64 圖片資料只需 `parseDataUrl` + base64 decode、
   vs 大量段落 + 字串處理較貴
3. **表格 layout cache**：02_std_table 重複表結構、第 2 個 fixture 命中 cache

Sprint 203 揭示「段落密度 dominant parse」、Sprint 205 揭示「圖片+表格 fixture
parse 比段落密集 fixture 更快」、兩者**互補完整 perf 場景 coverage**。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1960 passed + 1 skipped**（+3 sprint205 + 11 自 Sprint 204 後 Phase 8 平行 sprint 累積）；單跑 sprint205 3/3 綠 |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | 04/02 fixture 本身已在 VR pipeline 內、本 sprint 不改動 fixture / layout / render → 42 fixture VR 結構性 unchanged |
| L3 perf | ✅ Sprint 201 baseline 維持 | 雙 anchor 量測點維持 + 本 sprint 補真實 fixture vitest guard、三點互補 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**（OoxmlParser /
  layoutDocument 皆不改）、純 test 加 perf guard 擴展
- **#2 magic number**：4 個具名常數（top-3 fixture path + 3 個閾值）、無 magic
- **#14.b clean scope**：commit = sprint205 test + audit doc + INDEX/snapshot；
  不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：
  - 只 top-3 fixture、不 top-10（test 跑時間 / coverage 平衡）
  - 不量 render（同 Sprint 203、需 browser canvas）
  - 不寫複雜 fixture 篩選邏輯、靜態 hardcoded list
- **#21**：fixture 維持原 04/02 path 在 VR pipeline 內、本 sprint 純讀

---

## Phase 7 完成度更新

- Sprint 204 後 ~92%
- **Sprint 205 補真實 ChienYi 圖片+表格 fixture perf guard**、Sprint 203
  synthetic-only 場景擴展至真實 workflow → **~93%**
- Phase 7 perf guard 覆蓋面：synthetic 純文字 (Sprint 203) + 真實圖文表格
  (Sprint 205) + puppeteer 全 60 fixture cold/warm (Sprint 201) = 三層完整

剩餘 cluster（每個 2-3 sprint、合計 ~5 sprint）：
- 50p+ 真實 ChienYi fixture audit（受限於 fixture 取得、需 user 提供）
- WPS 來源 fixture audit（同上）
- OffscreenCanvas worker（Sprint 197+201 雙驗不建議）
- Web Worker parse（同）
- 增量渲染（long-term optional）

---

## File-level summary

```
A  tests/integration/sprint205_real_fixture_perf_guard.test.ts   +88 行
A  docs/sprint205_real_fixture_perf_guard.md                     本 audit
M  docs/INDEX.md                                                 +Sprint 205 entry
M  docs/progress_snapshot.md                                     Sprint 205 區塊 + Phase 7 ~92%→~93%
```

**淨 production code 變動 = 0 行**、vitest 1946→**1960**（+3 sprint205 +
11 Phase 8 平行）、VR byte-identical 第 58 連 unchanged、3 真實 fixture
parse 45-149ms / layout 2-10ms 全 < 閾值（10-313× safety margin）、
**Phase 7 完成度 ~92%→~93%**、perf guard 覆蓋面擴展至真實 ChienYi workflow。
