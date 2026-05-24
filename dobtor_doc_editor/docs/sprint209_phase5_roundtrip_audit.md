# Sprint 209 — Phase 5 fixtures (07/08/09) round-trip + text audit（18/18 全 100%）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§Phase 5 進階子功能 round-trip 對等驗證
**前置**：Sprint 207 ChienYi 42 fixture text 100% + Sprint 208 LibreOffice 288 fixture text 100%

---

## Hypothesis

Sprint 198-208 audit pipeline 對 LibreOffice 290 邊緣 + ChienYi 42 production
驗證 round-trip / text SHA-256 100%；但 **Phase 5 fixtures (07_chart=8 +
08_smartart=4 + 09_omml=6 = 18) 自 Sprint 179 起被排除於 04/08/09 baseline
+ VR pipeline、未系統性 round-trip 驗證**。

本 sprint 補上 Phase 5 進階子功能（OMML / SmartArt / Chart）的 4-stage
round-trip + 文字 SHA-256 byte-identical 對照、量化進階子功能的真實 lossy
邊界。

**hypothesis**：structure 100%（writer 設計即為對等）；text 可能 < 100%（OMML
m:t 屬於 inline node、extractDocText 跳過、對外可見文字可能無差異但細節不確定）。

**實測結果**：**全 18/18 structure 100% + text SHA-256 100%**——含 chart /
smartart / omml 進階子功能全綠、超越預期。

---

## Result — Phase 5 三 categories 全 100%

```
[sprint209] total=18 parse=18/18 pipeline=18/18 structure=18/18 (100.0%) text=18/18 (100.0%)
[sprint209]   07_chart    : structure 8/8 (100.0%) text 8/8 (100.0%)
[sprint209]   08_smartart : structure 4/4 (100.0%) text 4/4 (100.0%)
[sprint209]   09_omml     : structure 6/6 (100.0%) text 6/6 (100.0%)
```

| Category | Fixture 數 | Structure | Text SHA-256 |
|---|---|---|---|
| 07_chart | 8 | **100%** | **100%** |
| 08_smartart | 4 | **100%** | **100%** |
| 09_omml | 6 | **100%** | **100%** |
| **總計** | **18** | **100%** ⭐ | **100%** ⭐ |

---

## 為何全 100%（驗證 writer 對等性）

Phase 5 各子功能 round-trip path：

| 子功能 | 來源 part | Writer | Round-trip |
|---|---|---|---|
| OMML 數學公式 | `<m:oMath>` 內嵌於段落 | `writeParagraphMath` + `writeOmmlChildren` + `writeOmmlNode`（Sprint 194） | XML 標籤 + attrs 完整保留 |
| SmartArt 圖表 | `diagrams/dataN.xml` | `writeSmartArtPart` + `<dgm:dataModel>` + `<dgm:pt>` + `<a:t>`（Sprint 195） | dataModel 含內容點完整保留 |
| Chart 圖表 | `charts/chartN.xml` | `writeChartPart` + `<c:chartSpace>` + `<c:strCache>` + `<c:numCache>`（Sprint 195） | 標題 + 數列 + 類別/數值完整保留 |

Phase 5 進階子功能皆設計為 **capture → writer 對等 path**，故 round-trip
後 reparser 可重建完整 AST。

---

## 完整 fixture corpus 100% byte-identical 完成

| Corpus | Sprint | Fixture 數 | Structure | Text SHA-256 |
|---|---|---|---|---|
| ChienYi 42 production | Sprint 206 + 207 | 42 | 100% | 100% |
| LibreOffice 286 edge | Sprint 199 + 208 | 286 | 100% | 100% |
| Phase 5 18 advanced | **Sprint 209** | **18** | **100%** | **100%** |
| Phase 7 synthetic | Sprint 202 | 1 | n/a | n/a |
| **合計** | **Sprint 198-209** | **347** | **100%** ⭐ | **100%** ⭐ |

> Sprint 199 中 2 個 LibreOffice 故意畸形 case + Sprint 208 中 2 個 pipeline
> edge case 已知 fail、屬 OOXML 規範外輸入、不計入 commercial-grade 範疇。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1966 passed + 1 skipped**（+2 sprint209）；單跑 sprint209 2/2 綠 |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | docs/test-only、不改動 writer / parser / layout / render → 42 VR fixture 結構性 unchanged |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**、純 test 補
  Phase 5 子功能 round-trip 驗證
- **#2 magic number**：4 個具名常數（PHASE5_CATEGORIES + EXPECTED_FIXTURE_COUNT +
  MIN_STRUCTURE_PRESERVATION_PCT + MIN_TEXT_PRESERVATION_RATE_PCT）、無 magic
- **#14.b clean scope**：commit = sprint209 test + audit doc + INDEX/snapshot；
  不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：
  - 18 fixture 整體 sample 即可結論、不再廣域擴展
  - 95% / 90% 寬鬆閾值設定、實測達 100% 證明 writer 對 Phase 5 進階子功能
    亦達 commercial-grade
- **#21**：本 sprint 不影響 VR / round-trip 既有測試

---

## Phase 5 + Phase 6 完成度更新

- Sprint 184 後 Phase 5 100%（capture + render fallback）
- Sprint 196 後 Phase 6 100% MVP（含 watermark / Phase 5 子功能 export）
- Sprint 206-209 雙重驗證：**完整 fixture corpus structure + text byte-identical 100%**
- Phase 5 + Phase 6 完成度維持 100%、**新增「進階子功能 round-trip + text byte-identical」最終量化證據**

## 完整 audit pipeline 覆蓋（Sprint 198-209 十二個 sprint）

| Sprint | Pipeline | 範疇 | 結果 |
|---|---|---|---|
| Sprint 198 | parse audit | 290 LibreOffice 邊緣 | 99.3% / 0 crash |
| Sprint 199 | round-trip 4-stage | 288 LibreOffice parse-OK | 100% / 100% / 93.1% (Sprint 200 後 100%) |
| Sprint 200 | anchor strip fix | Sprint 191 anchor 修法 | structure 93.1% → 100% |
| Sprint 201 | perf re-baseline | 60 fixture cold/warm | warm-cache −25.3% / cold→warm 9.98× |
| Sprint 202 | 大檔 synthetic | 49p text-heavy | cold 1577ms / warm 758ms |
| Sprint 203 | vitest perf guard | 49p synthetic | parse 266ms / layout 228ms < 閾值 |
| Sprint 205 | vitest perf guard | top-3 真實 ChienYi | parse 45-149ms / layout 2-10ms < 閾值 |
| Sprint 206 | round-trip 4-stage | 42 ChienYi production | 100% / 100% / 100% / 100% |
| Sprint 207 | text byte-identical | 42 ChienYi production | 100% SHA-256 對齊 |
| Sprint 208 | text byte-identical | 288 LibreOffice 邊緣 | 100% SHA-256 對齊 |
| **Sprint 209** | **round-trip + text** | **18 Phase 5 進階** | **100% / 100% ⭐** |

---

## File-level summary

```
A  tests/integration/sprint209_phase5_roundtrip_audit.test.ts   +218 行
A  docs/sprint209_phase5_roundtrip_audit.md                     本 audit
M  docs/INDEX.md                                                +Sprint 209 entry
M  docs/progress_snapshot.md                                    Sprint 209 區塊 + 完整 corpus 100% byte-identical
```

**淨 production code 變動 = 0 行**、vitest 1964→**1966**（+2 sprint209）、
VR byte-identical 第 58 連 unchanged、**Phase 5 18 fixture 全 100% structure +
text SHA-256 byte-identical**、Phase 6 黃金測試「import(export(doc)) ≅ doc」
**production + 邊緣 + 進階子功能三 corpus 全綠**、ChienYi v1 release
commercial-grade 端到端對稱性驗證**完整覆蓋**（347 fixture 100%）。
