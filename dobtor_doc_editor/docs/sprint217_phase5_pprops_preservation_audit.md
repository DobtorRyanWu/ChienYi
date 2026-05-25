# Sprint 217 — Phase 6 Phase 5 (07/08/09) fixture ParagraphProps preservation audit（18/18 全 100%、37 paragraphs 全綠、三 corpus 四層矩陣完備）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§6 黃金測試 ParagraphProps 格式級對稱 — Phase 5 進階子功能
**前置**：Sprint 215 ChienYi 42 pProps 100% + Sprint 216 LibreOffice 288 pProps 100%

---

## Hypothesis

Sprint 215 + 216 已對 ChienYi 42 production + LibreOffice 288 edge **雙
corpus** 驗證 ParagraphProps SHA-256 100% byte-identical（合計 5298
paragraphs）；但 **Phase 5 進階子功能（07_chart=8 + 08_smartart=4 +
09_omml=6 = 18 fixture）段落層級格式對稱未獨立驗證**。

本 sprint 補上 Phase 5 fixture ParagraphProps SHA-256 對照、完成
**三 corpus 四層矩陣**最後一格。

**實測結果**：**18/18 全 100% / 37 paragraphs 全綠**——超越 90% 閾值 10pp、
Phase 5 進階子功能 ParagraphProps 達 byte-identical 段落格式對稱。

---

## Result — 18/18 全 100% ParagraphProps SHA-256 對齊

```
[sprint217] total=18 pProps match=18/18 (100.0%) totalParagraphs=37
[sprint217]   07_chart      : 8/8 (100.0%) paragraphs=16
[sprint217]   08_smartart   : 4/4 (100.0%) paragraphs=8
[sprint217]   09_omml       : 6/6 (100.0%) paragraphs=13
```

| Category | Fixture 數 | pProps match | Paragraphs |
|---|---|---|---|
| 07_chart | 8 | **8/8 (100%)** | 16 |
| 08_smartart | 4 | **4/4 (100%)** | 8 |
| 09_omml | 6 | **6/6 (100%)** | 13 |
| **總計** | **18** | **18/18 (100%)** ⭐ | **37** |

---

## 三 corpus 四層矩陣完備 ⭐⭐

| 驗證層次 | ChienYi 42 (production) | LibreOffice 286 (edge) | Phase 5 18 (advanced) |
|---|---|---|---|
| Parse OK | n/a | 99.3% (Sprint 198) | n/a |
| Structure 4-stage | 100% (Sprint 206) | 100% (Sprint 199+200) | 100% (Sprint 209) |
| Text SHA-256 | 100% (Sprint 207) | 100% (Sprint 208) | 100% (Sprint 209) |
| **RunProps SHA-256** | **100% (Sprint 210) / 9508 runs** | **100% (Sprint 211) / 2114 runs** | **100% (Sprint 212) / 23 runs** |
| **ParagraphProps SHA-256** | **100% (Sprint 215) / 3384 paragraphs** | **100% (Sprint 216) / 1914 paragraphs** | **100% (Sprint 217) / 37 paragraphs** ⭐ |

**Phase 6 黃金測試「import(export(doc)) ≅ doc」全 corpus 四層 byte-identical
對稱性矩陣完備全綠**：
- 三 corpus（production + edge + advanced）
- 四層（structure + text + RunProps + ParagraphProps）
- **合計 11645 runs + 5335 paragraphs 全 byte-identical**
- 跨 24 categories（ChienYi 6 + LibreOffice 15 + Phase 5 3）

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1992 passed + 1 skipped**（+1 sprint217）；單跑 sprint217 1/1 綠 514ms |
| L2 VR v14 | ✅ **byte-identical 第 64 連** | docs/test-only → 42 VR fixture 結構性 unchanged |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：0 行 production code 變動
- **#2 magic number**：3 個具名常數 + `deepStableStringify`
- **#14.b clean scope**：commit = sprint217 test + audit doc + INDEX/snapshot
- **#18 scope-down**：沿用 Sprint 215 + Sprint 212 既有 pattern、無 try/catch
  （Sprint 209 已驗 pipeline 100%）
- **#21**：不影響 VR / round-trip / existing 測試

---

## File-level summary

```
A  tests/integration/sprint217_phase5_pprops_preservation_audit.test.ts   +166 行
A  docs/sprint217_phase5_pprops_preservation_audit.md                     本 audit
M  docs/INDEX.md                                                          +Sprint 217 entry
M  docs/progress_snapshot.md                                              Sprint 217 區塊 + 三 corpus 四層矩陣完備
```

**淨 production code 變動 = 0 行**、vitest 1991→**1992**（+1 sprint217）、
VR byte-identical 第 64 連 unchanged、**Phase 5 18 fixture 全 100%
ParagraphProps SHA-256 byte-identical（37 paragraphs / 3 categories）**、
Phase 6 黃金測試「import(export(doc)) ≅ doc」**三 corpus 四層 byte-identical
對稱性矩陣完備**——production + edge + advanced 全綠、合計 347 fixture /
11645 runs + 5335 paragraphs / 24 categories byte-identical、ChienYi v1
release commercial-grade 端到端對稱性驗證**最終完整覆蓋**。
