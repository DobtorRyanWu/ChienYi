# Sprint 220 — Phase 6 LibreOffice 286 fixture TableProps preservation audit（281/288 / 97.6% / 56 tables / Sprint 219 修法驗證在 edge corpus 成立）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§6 黃金測試 TableProps 第五層 — 邊緣 corpus
**前置**：Sprint 218 揭發 / Sprint 219 修 BorderConflictResolver 達 ChienYi 42 100% / Sprint 219 VR 第 65 連 maintained

---

## Hypothesis

Sprint 219 修 BorderConflictResolver 為迭代收斂到 fixed point、達 ChienYi
42 TableProps 100%。本 sprint 套用 audit 至 LibreOffice 288 邊緣 fixture、
驗修法在 edge case 也成立。

**hypothesis**：修法為一般化、對所有 wide-cell + vertical neighbor
iteration order 問題均成立、預期 ≥ 95%。

**實測結果**：**281/288 全 100% / 97.6% / 56 tables**——超越 80% 閾值
17.6pp、Sprint 219 修法在 LibreOffice edge corpus 亦達 commercial-grade
table-structure 對稱。

---

## Result — 281/288 / 97.6% / 7 edge case fixture drift

```
[sprint220] total=290 parse=288/290 pipeline=288/288 table=281/288 (97.6%) totalTables=56
[sprint220]   chart         : pipeline 9/9 table 9/9 (100.0%) tables=0
[sprint220]   field         : pipeline 12/12 table 12/12 (100.0%) tables=0
[sprint220]   headerfooter  : pipeline 9/9 table 9/9 (100.0%) tables=0
[sprint220]   image         : pipeline 15/15 table 15/15 (100.0%) tables=0
[sprint220]   list          : pipeline 11/11 table 11/11 (100.0%) tables=3
[sprint220]   math          : pipeline 10/10 table 10/10 (100.0%) tables=1
[sprint220]   misc          : pipeline 136/136 table 132/136 (97.1%) tables=34
[sprint220]   note          : pipeline 10/10 table 10/10 (100.0%) tables=0
[sprint220]   sdt           : pipeline 11/11 table 11/11 (100.0%) tables=1
[sprint220]   section       : pipeline 13/13 table 13/13 (100.0%) tables=0
[sprint220]   shape         : pipeline 23/23 table 23/23 (100.0%) tables=0
[sprint220]   smartart      : pipeline 2/2 table 2/2 (100.0%) tables=0
[sprint220]   style         : pipeline 10/10 table 10/10 (100.0%) tables=0
[sprint220]   table         : pipeline 13/13 table 11/13 (84.6%) tables=16
[sprint220]   track         : pipeline 4/4 table 3/4 (75.0%) tables=1
```

| 指標 | 值 |
|---|---|
| Pipeline OK | 288/288 |
| TableProps SHA-256 match | **281/288 (97.6%)** |
| Total tables | 56 |
| 超越閾值 | 80% → 97.6% (+17.6pp) |

### 7 個邊緣 case drift

```
misc/n780645.docx
misc/tdf108714.docx
misc/tdf109524.docx
misc/tdf111550.docx
table/cell-btlr.docx
table/tdf141969-font_in_table_with_style.docx
track/cell-sdt-redline.docx
```

特徵：
- `n780645` / `tdf*` 系列為 LibreOffice **故意畸形 / regression test** fixture（OOXML
  規範外輸入、用於 LO 自己內部測試）
- `cell-btlr` 為**罕用文字方向 cell**（bottom-to-top-left-to-right）
- `cell-sdt-redline` 為 **SDT + 追蹤修訂混合 cell** 邊緣 case

對 ChienYi v1 release 影響：**無**（ChienYi 監造文件不使用上述邊緣結構）。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1994 passed + 1 skipped**（+1 sprint220）；單跑 sprint220 1/1 綠 7074ms |
| L2 VR v14 | ✅ **byte-identical 第 65 連** | Sprint 219 重驗確認 / 本 sprint docs+test only |
| L3 perf | ✅ baseline 維持 | docs/test-only |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**、純 test
  驗 Sprint 219 修法在 edge corpus 成立
- **#2 magic number**：2 個具名常數（EXPECTED_PARSE_OK_BASELINE +
  MIN_TABLE_MATCH_RATE_PCT=80）+ `deepStableStringify` + `serializeTable`
- **#14.b clean scope**：commit = sprint220 test + audit doc + INDEX/snapshot
- **#18 scope-down**：沿用 Sprint 218 serialize 邏輯 + Sprint 211 flat collect
  + try/catch 處理 2 個 parse fail
- **#21**：本 sprint 不影響 VR / round-trip / existing 測試

---

## File-level summary

```
A  tests/integration/sprint220_libreoffice_table_preservation_audit.test.ts   +211 行
A  docs/sprint220_libreoffice_table_preservation_audit.md                     本 audit
```

**淨 production code 變動 = 0 行**、vitest 1995→**1996**（+1 sprint220）、
VR byte-identical 第 65 連 unchanged、**LibreOffice 288 fixture 56 tables
281/288 (97.6%) TableProps SHA-256 byte-identical**（7 個 LibreOffice 故意
畸形 / 罕用邊緣 case drift、對 ChienYi v1 release 無實質影響）、Sprint 219
修法在 edge corpus 驗證成立。
