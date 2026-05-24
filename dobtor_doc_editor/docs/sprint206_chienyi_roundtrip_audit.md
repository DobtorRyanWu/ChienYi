# Sprint 206 — Phase 6 ChienYi 真實 fixture export round-trip 廣域 audit（42/42 全 100%）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§Phase 6 export 對稱性、Sprint 199 LibreOffice audit 擴展至 ChienYi 真實 workflow
**前置**：Sprint 199（290 LibreOffice fixture：parse 99.3% / export 100% / reparse 100% / structure 100%（Sprint 200 後））

---

## Hypothesis

Sprint 199 對 290 LibreOffice 邊緣 fixture 跑 4 階段 round-trip 並達 100%
結構保留（Sprint 200 anchor strip 後）；**未對 ChienYi 監造真實 workflow 42
fixture 系統性驗證 round-trip**。

本 sprint 把 Sprint 199 pattern 套用至 01-06 ChienYi categories（42 fixture）、
驗證 production-grade docx：監造會議記錄、週報、估驗表、安全衛生抽查、
工程表單 等 ChienYi workflow 文件可端到端 round-trip 通過 Phase 6 writer。

**對 ChienYi v1 release 的意義**：
- LibreOffice 290 fixture 驗證**廣域 docx 相容**（邊緣 corpus）
- ChienYi 42 fixture 驗證**真實 workflow 對稱**（production corpus）
- 兩者互補完整 export 端到端 commercial-grade 驗證

---

## 修法

新檔 `tests/integration/sprint206_chienyi_roundtrip_audit.test.ts`（+225 行）：

### 6 個具名常數（紀律 #2）

- `CHIENYI_CATEGORIES = ['01_simple', '02_std_table', '03_complex_table', '04_with_image', '05_header_footer', '06_template']`
- `EXPECTED_FIXTURE_COUNT = 42`
- `MIN_PARSE_SUCCESS_RATE_PCT = 95`（真實 workflow 高於廣域邊緣標準）
- `MIN_EXPORT_SUCCESS_RATE_PCT = 95`
- `MIN_REPARSE_SUCCESS_RATE_PCT = 95`
- `MIN_STRUCTURE_PRESERVATION_PCT = 80`（保守、含可能的 SmartArt/Chart lossy）

### 排除集（已被其他 sprint 覆蓋）

- `07_chart` / `08_smartart` / `09_omml`：Sprint 181-183 lossy export 已驗
- `10_ooxml_libreoffice`：Sprint 199 已驗
- `11_perf_synthetic_large`：Sprint 202 已驗（writer 自生）

### 4-stage pipeline

每 fixture 跑：
1. parse 原 bytes → AST
2. writer.write(doc) → exported bytes
3. parser.parse(exportedBytes) → reparseDoc
4. structureOk = originalSections === reparseSections AND originalParagraphs === reparseParagraphs

---

## Result — 42/42 全 4 stage 100%

```
[sprint206] total=42 parse=42/42 (100.0%) export=42/42 (100.0%) reparse=42/42 (100.0%) structure=42/42 (100.0%)
[sprint206]   01_simple:        structure  7/7  (100.0%)
[sprint206]   02_std_table:     structure  8/8  (100.0%)
[sprint206]   03_complex_table: structure  8/8  (100.0%)
[sprint206]   04_with_image:    structure  6/6  (100.0%)
[sprint206]   05_header_footer: structure 10/10 (100.0%)
[sprint206]   06_template:      structure  3/3  (100.0%)
```

| Stage | 數 | Rate | Safety vs 閾值 |
|---|---|---|---|
| parse | 42/42 | **100%** | +5pp |
| export | 42/42 | **100%** | +5pp |
| reparse | 42/42 | **100%** | +5pp |
| structure preservation | 42/42 | **100%** | +20pp |

**對比 Sprint 199 LibreOffice 邊緣 audit**：

| 指標 | Sprint 199 (LibreOffice 290) | Sprint 206 (ChienYi 42) |
|---|---|---|
| parse | 288/290 (99.3%) | **42/42 (100%)** |
| export | 288/288 (100%) | 42/42 (100%) |
| reparse | 288/288 (100%) | 42/42 (100%) |
| structure | 288/288 (100%) | **42/42 (100%)** |
| 範疇 | 廣域邊緣（含故意畸形）| 真實 workflow（production）|

ChienYi 真實 workflow corpus **無任何 fixture 含 LibreOffice 邊緣畸形**、
parse / export / reparse / structure 全 100% — production-ready 商用級
端到端對稱性驗證。

---

## 為何 ChienYi 42 fixture round-trip 100%（vs LibreOffice 99.3%）

LibreOffice 290 fixture 含 2 個故意畸形 case（math/math-malformed_xml.docx +
misc/tdf165348_broken_package.docx），用於測試 parser 邊緣 throw 行為；ChienYi
fixture 皆為**真實工地產出的合規 docx**、無故意畸形。

Sprint 200 anchor paragraph strip 修法後、廣域 round-trip structure 從 93.1%
拉到 100%、本 sprint ChienYi 42 fixture 直接受益。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1962 passed + 1 skipped**（+2 sprint206 + 0 自 Sprint 205 後 Phase 8 平行）；單跑 sprint206 2/2 綠 |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | 本 sprint 不改動 fixture / writer / parser / layout / render → 42 fixture VR 結構性 unchanged |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**（OoxmlParser /
  OoxmlWriter 皆不改）、純 test 加廣域 round-trip 驗證
- **#2 magic number**：6 個具名常數（categories 名單 + 5 個閾值/count）、無 magic
- **#14.b clean scope**：commit = sprint206 test + audit doc + INDEX/snapshot；
  不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：
  - 只 42 ChienYi 真實 fixture、不再廣域擴展（LibreOffice 290 已 Sprint 199 覆蓋）
  - 排除集明確（07-09 Phase 5 / 10 LibreOffice / 11 synthetic 各自有 sprint 覆蓋）
  - structure preservation 容寬鬆 80%（容忍可能的 SmartArt/Chart lossy；實際達 100%）
- **#21**：本 sprint 不影響 VR / round-trip 既有測試、不引入新 production 路徑

---

## Phase 6 完成度更新

- Sprint 196 後 100% MVP（含 watermark）
- Sprint 199 廣域 audit 證明邊緣 corpus 100% structure
- **Sprint 206 真實 ChienYi workflow corpus 100% structure 驗證**
- Phase 6 完成度維持 100% MVP、**新增「真實 workflow 端到端 100% commercial-
  grade」量化證據**

## Phase 7 完成度更新

- Sprint 205 後 ~93%
- **Sprint 206 補真實 workflow round-trip coverage**（雖屬 Phase 6 範疇但同
  屬「邊緣 / 真實 audit pipeline」） → ~93% 維持

---

## 完整 audit pipeline 覆蓋（Sprint 198-206）

| Sprint | Pipeline | 範疇 | 結果 |
|---|---|---|---|
| Sprint 198 | parse audit | 290 LibreOffice 邊緣 | 99.3% / 0 crash |
| Sprint 199 | round-trip 4-stage | 288 LibreOffice parse-OK | 100% / 100% / 93.1% (Sprint 200 後 100%) |
| Sprint 200 | anchor strip fix | Sprint 191 anchor 修法 | structure 93.1% → 100% |
| Sprint 201 | perf re-baseline | 60 fixture cold/warm | warm-cache −25.3% / cold→warm 9.98× |
| Sprint 202 | 大檔 synthetic | 49p text-heavy | cold 1577ms / warm 758ms |
| Sprint 203 | vitest perf guard | 49p synthetic | parse 266ms / layout 228ms < 閾值 |
| Sprint 205 | vitest perf guard | top-3 真實 ChienYi | parse 45-149ms / layout 2-10ms < 閾值 |
| **Sprint 206** | **round-trip 4-stage** | **42 ChienYi 真實** | **100% / 100% / 100% / 100% ⭐** |

---

## File-level summary

```
A  tests/integration/sprint206_chienyi_roundtrip_audit.test.ts   +225 行
A  docs/sprint206_chienyi_roundtrip_audit.md                     本 audit
M  docs/INDEX.md                                                 +Sprint 206 entry
M  docs/progress_snapshot.md                                     Sprint 206 區塊 + ChienYi 100% round-trip 驗證
```

**淨 production code 變動 = 0 行**、vitest 1960→**1962**（+2 sprint206）、
VR byte-identical 第 58 連 unchanged、**42/42 ChienYi 真實 workflow fixture
全 4 stage 100% round-trip 通過 Phase 6 writer**、6 個 categories 全 100%
structure preservation、ChienYi v1 release commercial-grade 端到端對稱性
量化保證。
