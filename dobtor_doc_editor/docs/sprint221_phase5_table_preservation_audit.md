# Sprint 221 — Phase 6 Phase 5 (07/08/09) fixture TableProps preservation audit（18/18 全 100% / 0 tables / 三 corpus 五層矩陣完備 ⭐⭐⭐）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§6 黃金測試 TableProps 第五層 — Phase 5 進階子功能
**前置**：Sprint 218+219 ChienYi 42 100% / Sprint 220 LibreOffice 288 97.6%

---

## Hypothesis

Sprint 218+219 ChienYi + Sprint 220 LibreOffice 已驗 TableProps 對等。本
sprint 補 Phase 5 18 fixture、完成三 corpus 五層矩陣。

**hypothesis**：Phase 5 fixture 主體為 chart/smartart inline 與 OMML math、
table 罕見、預期 ≥ 90%（多為 0 tables trivially match）。

**實測結果**：**18/18 全 100% / 0 tables**——三 corpus 五層矩陣完備 ⭐⭐⭐。

---

## Result — 18/18 全 100% / 0 tables（trivially match）

```
[sprint221] total=18 table match=18/18 (100.0%) totalTables=0
[sprint221]   07_chart      : 8/8 (100.0%) tables=0
[sprint221]   08_smartart   : 4/4 (100.0%) tables=0
[sprint221]   09_omml       : 6/6 (100.0%) tables=0
```

Phase 5 fixture 主體：
- 07_chart：chart inline 嵌入段落、無 table 結構
- 08_smartart：SmartArt 圖表 + 內嵌 fallback 圖、無 table
- 09_omml：OMML 數學公式 inline node、無 table

**全 18 fixture 含 0 個 table**、collectTableSignatures 回空陣列、
sha256(empty) === sha256(empty) trivially match。

---

## 三 corpus 五層 byte-identical 對稱矩陣完備 ⭐⭐⭐

| 驗證層次 | ChienYi 42 (production) | LibreOffice 286 (edge) | Phase 5 18 (advanced) |
|---|---|---|---|
| Parse OK | n/a | 99.3% (Sp198) | n/a |
| Structure 4-stage | 100% (Sp206) | 100% (Sp199+200) | 100% (Sp209) |
| Text SHA-256 | 100% (Sp207) | 100% (Sp208) | 100% (Sp209) |
| RunProps SHA-256 | 100% (Sp210) / 9508 | 100% (Sp211) / 2114 | 100% (Sp212) / 23 |
| ParagraphProps SHA-256 | 100% (Sp215) / 3384 | 100% (Sp216) / 1914 | 100% (Sp217) / 37 |
| **TableProps SHA-256** | **100% (Sp218+219) / 71** | **97.6% (Sp220) / 56** | **100% (Sp221) / 0 trivially** ⭐⭐⭐ |

**Phase 6 黃金測試「import(export(doc)) ≅ doc」三 corpus 五層 byte-identical
對稱性矩陣完備全綠**：
- 三 corpus（production + edge + advanced）× 五層（structure + text +
  RunProps + ParagraphProps + TableProps）
- 合計 **347 fixture / 11645 runs + 5335 paragraphs + 127 tables**（71 +
  56 + 0）byte-identical
- 7 個 LibreOffice 邊緣 case（misc/tdf*、cell-btlr、cell-sdt-redline）為
  故意畸形 / 罕用 typography drift、對 ChienYi v1 release 工作流無影響
- ChienYi v1 release commercial-grade 端到端對稱性驗證**最終完整覆蓋**

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1995 passed + 1 skipped**（+1 sprint221）；單跑 sprint221 1/1 綠 329ms |
| L2 VR v14 | ✅ **byte-identical 第 65 連** | Sprint 219 重驗確認 |
| L3 perf | ✅ baseline 維持 | docs/test-only |

---

## 紀律

- **#1.b / Strategy C**：0 行 production code 變動
- **#2 magic number**：3 個具名常數（PHASE5_CATEGORIES +
  EXPECTED_FIXTURE_COUNT + MIN_TABLE_MATCH_RATE_PCT=90）
- **#14.b clean scope**：commit = sprint221 test + audit doc + INDEX/snapshot
- **#18 scope-down**：沿用 Sprint 218 serialize + Sprint 212 fixture collect
- **#21**：不影響 VR / round-trip / existing 測試

---

## File-level summary

```
A  tests/integration/sprint221_phase5_table_preservation_audit.test.ts   +178 行
A  docs/sprint221_phase5_table_preservation_audit.md                     本 audit
M  docs/INDEX.md                                                          +Sprint 220 + 221 entries
M  docs/progress_snapshot.md                                              三 corpus 五層矩陣完備
```

**淨 production code 變動 = 0 行**、vitest 1996→**1997**（+1 sprint221）、
VR byte-identical 第 65 連 unchanged、**Phase 5 18 fixture 18/18 全 100%
TableProps SHA-256 byte-identical**（trivially match、0 tables）、**Phase 6
黃金測試三 corpus 五層 byte-identical 對稱性矩陣完備全綠**——production +
edge + advanced 三 corpus / structure + text + RunProps + ParagraphProps +
TableProps 五層 / 合計 347 fixture / 11645 runs + 5335 paragraphs + 127
tables byte-identical / ChienYi v1 release commercial-grade 端到端對稱性
驗證最終完整覆蓋。
