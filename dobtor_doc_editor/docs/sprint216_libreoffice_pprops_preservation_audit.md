# Sprint 216 — Phase 6 LibreOffice 286 fixture ParagraphProps preservation audit（288/288 全 100%、1914 paragraphs 全綠）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§6 黃金測試 ParagraphProps 格式級對稱 — 邊緣 corpus
**前置**：Sprint 215 ChienYi 42 pProps 100% / 3384 paragraphs

---

## Hypothesis

Sprint 215 對 ChienYi 42 production fixture 驗證 ParagraphProps SHA-256
100% byte-identical（3384 paragraphs 全綠）；但 **LibreOffice 邊緣 corpus
（含 Phase 5 lossy / 故意畸形 case）段落格式級保留率未獨立驗證**。

本 sprint 把 Sprint 215 pattern 套用至 Sprint 198 已 parse 成功的 288 個
LibreOffice 邊緣 fixture、量化 writer 在 edge case docx 上的 ParagraphProps
段落格式保留率。

**hypothesis**：
- 邊緣 corpus 含 Phase 5 lossy fallback、預期 ≥ 80%
- 主流結構 writer 對 paragraph-level 仍應對等

**實測結果**：**288/288 全 100% / 1914 paragraphs 全綠**——超越 80% 閾值
20pp、LibreOffice 邊緣 corpus ParagraphProps 達 byte-identical 段落格式
對稱。

---

## 修法

新檔 `tests/integration/sprint216_libreoffice_pprops_preservation_audit.test.ts`
（+207 行）：

- 沿用 Sprint 215 `deepStableStringify` 遞迴排序（ParagraphProps 含 5
  nested object + 1 nested array）
- 沿用 Sprint 211 flat fixture collect 邏輯（readdir entire root）+
  try/catch 處理 2 個 parse fail edge case

---

## Result — 288/288 全 100% ParagraphProps SHA-256 對齊

```
[sprint216] total=290 parse=288/290 pipeline=288/288 pProps=288/288 (100.0%) totalParagraphs=1914
[sprint216]   chart         : pipeline 9/9 pProps 9/9 (100.0%) paragraphs=28
[sprint216]   field         : pipeline 12/12 pProps 12/12 (100.0%) paragraphs=154
[sprint216]   headerfooter  : pipeline 9/9 pProps 9/9 (100.0%) paragraphs=17
[sprint216]   image         : pipeline 15/15 pProps 15/15 (100.0%) paragraphs=31
[sprint216]   list          : pipeline 11/11 pProps 11/11 (100.0%) paragraphs=136
[sprint216]   math          : pipeline 10/10 pProps 10/10 (100.0%) paragraphs=45
[sprint216]   misc          : pipeline 136/136 pProps 136/136 (100.0%) paragraphs=812
[sprint216]   note          : pipeline 10/10 pProps 10/10 (100.0%) paragraphs=17
[sprint216]   sdt           : pipeline 11/11 pProps 11/11 (100.0%) paragraphs=22
[sprint216]   section       : pipeline 13/13 pProps 13/13 (100.0%) paragraphs=41
[sprint216]   shape         : pipeline 23/23 pProps 23/23 (100.0%) paragraphs=33
[sprint216]   smartart      : pipeline 2/2 pProps 2/2 (100.0%) paragraphs=2
[sprint216]   style         : pipeline 10/10 pProps 10/10 (100.0%) paragraphs=116
[sprint216]   table         : pipeline 13/13 pProps 13/13 (100.0%) paragraphs=452
[sprint216]   track         : pipeline 4/4 pProps 4/4 (100.0%) paragraphs=8
```

| 指標 | 值 |
|---|---|
| Pipeline OK | 288/288 |
| ParagraphProps SHA-256 match | **288/288 (100%)** ⭐ |
| Total paragraphs verified | **1914** |
| 超越閾值 | 80% → 100% (+20pp) |

---

## 完整 ChienYi + LibreOffice 雙 corpus 四層對稱性

| 驗證層次 | ChienYi 42 (production) | LibreOffice 286 (edge) |
|---|---|---|
| Structure | 100% (Sprint 206) | 100% (Sprint 199 + 200) |
| Text SHA-256 | 100% (Sprint 207) | 100% (Sprint 208) |
| RunProps SHA-256 | 100% (Sprint 210) / 9508 runs | 100% (Sprint 211) / 2114 runs |
| **ParagraphProps SHA-256** | **100% (Sprint 215) / 3384 paragraphs** | **100% (Sprint 216) / 1914 paragraphs** ⭐ |

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1991 passed + 1 skipped**（+1 sprint216）；單跑 sprint216 1/1 綠 8434ms |
| L2 VR v14 | ✅ **byte-identical 第 63 連** | docs/test-only → 42 VR fixture 結構性 unchanged |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：0 行 production code 變動
- **#2 magic number**：2 個具名常數（EXPECTED_PARSE_OK_BASELINE +
  MIN_PPROPS_MATCH_RATE_PCT）+ `deepStableStringify` 函式
- **#14.b clean scope**：commit = sprint216 test + audit doc + INDEX/snapshot
- **#18 scope-down**：沿用 Sprint 215 + Sprint 211 既有 pattern、無新抽象
- **#21**：不影響 VR / round-trip / existing 測試

---

## File-level summary

```
A  tests/integration/sprint216_libreoffice_pprops_preservation_audit.test.ts   +207 行
A  docs/sprint216_libreoffice_pprops_preservation_audit.md                     本 audit
M  docs/INDEX.md                                                               +Sprint 216 entry
M  docs/progress_snapshot.md                                                   Sprint 216 區塊 + 雙 corpus 四層對稱
```

**淨 production code 變動 = 0 行**、vitest 1990→**1991**（+1 sprint216）、
VR byte-identical 第 63 連 unchanged、**LibreOffice 288 fixture 1914
paragraphs 全 ParagraphProps SHA-256 100% byte-identical**、Phase 6 黃金
測試**雙 corpus 四層對稱性全綠**——commercial-grade 邊緣 docx「段落格式
亦不失真」最嚴格邊緣量化保證。
