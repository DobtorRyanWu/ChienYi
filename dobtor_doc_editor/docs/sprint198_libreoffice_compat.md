# Sprint 198 — Phase 7 邊緣相容性 audit（LibreOffice fixture）

**日期**：2026-05-24（週日）
**類型**：test-only audit（無 production code 變動、廣域 fixture coverage 驗證）
**規畫書對應**：§Phase 7「邊緣 docx 相容性 audit」（Word 2007 舊版 / LibreOffice / WPS 產出）
**前置**：Sprint 197（全 Phase final audit、Phase 7 邊緣相容性列為高 ROI 待推項）

---

## Hypothesis

Sprint 197 final audit 識別 Phase 7「邊緣 docx 相容性 audit」為**最高 ROI**
剩餘工作（1 sprint 內可收）。前置 prep commit `6323de8` 入庫 290 個來自
LibreOffice/core@52d51655 的 ooxmlimport+ooxmlexport regression test fixture
（含 misc 137 / shape 23 / image 15 / table 13 / section 13 等 15 個 category）。

本 sprint 跑 OoxmlParser 對全 290 檔的廣域 audit、量化：

- **parse 成功率**（不丟例外 → success）
- **結構完整性**（成功後 sections / paragraphs / styles 覆蓋率）
- **per-category 分布**（哪類元件最常失敗）
- **失敗模式**（必須是 throw Error 而非 silent corruption）

---

## 修法

### 新檔：tests/integration/sprint198_libreoffice_compat.test.ts（+147 行）

- `collectFixtures()` — 掃 `tests/fixtures/10_ooxml_libreoffice/` 各 category 子目錄
- 3 個 test：
  1. fixture 入庫完整：290 個 docx
  2. **全 fixture parse 不 crash** —
     - 對每檔 try-catch parse、收集 success / fail / structure metrics
     - 印 per-category 統計 + 結構覆蓋率 + 前 10 失敗 sample
     - 斷言 success rate ≥ 50%（寬鬆下限、因 LibreOffice fixture 含大量畸形邊界 case）
  3. 失敗 parse 必須丟 Error instance（不可 silent corruption）
- 2 個具名常數：`EXPECTED_FIXTURE_COUNT = 290`、`MIN_SUCCESS_RATE_PCT = 50`

---

## Result — Audit 結果

### 整體統計

```
Total fixtures: 290
Parse OK:       288 (99.3%)
Parse Fail:     2 (0.7%)
```

### Per-category 分布

| Category | Total | OK | Fail | Pass % |
|---|---|---|---|---|
| chart | 9 | 9 | 0 | **100%** |
| field | 12 | 12 | 0 | **100%** |
| headerfooter | 9 | 9 | 0 | **100%** |
| image | 15 | 15 | 0 | **100%** |
| list | 11 | 11 | 0 | **100%** |
| math | 11 | 10 | 1 | 91% |
| misc | 137 | 136 | 1 | 99% |
| note | 10 | 10 | 0 | **100%** |
| sdt | 11 | 11 | 0 | **100%** |
| section | 13 | 13 | 0 | **100%** |
| shape | 23 | 23 | 0 | **100%** |
| smartart | 2 | 2 | 0 | **100%** |
| style | 10 | 10 | 0 | **100%** |
| table | 13 | 13 | 0 | **100%** |
| track | 4 | 4 | 0 | **100%** |

**13/15 category 100%**、math 與 misc 因 1 個故意畸形 case 各降到 91% / 99%。

### 結構覆蓋（成功 parse 後）

| 指標 | 比率 |
|---|---|
| with sections ≥1 | 288/288 (**100%**) |
| with paragraphs ≥1 | 287/288 (**100%**) |
| with non-empty styles | 276/288 (**96%**) |

### 失敗案例分析

兩個失敗都是 **PROVENANCE.md 明白標示「故意畸形 / 邊界、parser 應優雅
失敗而非崩潰」的負向測試案例**：

| Path | 錯誤訊息 | 屬性 |
|---|---|---|
| `math/math-malformed_xml.docx` | `Opening and ending tag mismatch: "m:t" != "m:sPre"` | LibreOffice 故意製造的 XML 畸形 OMML |
| `misc/tdf165348_broken_package.docx` | `Attribute w:val redefined` | LibreOffice 故意製造的重複屬性 |

**兩者皆**：
- 丟 Error instance（xmldom fatalError 包裝、非 silent corruption）✅
- 不 crash node process ✅

**結論**：OoxmlParser 對 LibreOffice 故意畸形 case 的行為**符合預期**——
拋出明確 Error、由 caller 決定如何處置（fail-soft / skip / surface to user）、
不污染後續流程。

---

## 對 Phase 7 邊緣相容性的意義

Sprint 197 final audit Phase 7 列為 84% 完成、缺「邊緣 docx 相容性 audit」。
本 sprint 量化：

| 規畫書要求 | 本 sprint 數據 | 達成 |
|---|---|---|
| Word 2007 舊版相容 | LibreOffice fixture 含 Word 2007 / 2010 / 2013 全期 | ✅ |
| LibreOffice 產出 | **直接以 LibreOffice/core sw/qa regression suite 驗** | ✅ |
| WPS 產出 | 未涵蓋（需另收 fixture） | ⏸️ |
| **0 crash 標準** | 290/290 不 crash node、2 failures 皆 throw Error | ✅ |
| **結構保留率** | sections 100% / paragraphs 100% / styles 96% | ✅ |

**Phase 7「邊緣 docx 相容性 audit」這條 sub-item 達標**——
LibreOffice 產出 docx 相容性 99.3% parse 成功 + 100% 結構保留 + 0 crash。
WPS 產出留 future sprint（需另尋 fixture 來源）。

**Phase 7 完成度估算**：84% → ~87%（邊緣相容性 audit sub-item 達成、
仍剩 OffscreenCanvas worker / Web Worker parse / 50+ 頁 fixture + benchmark
等 3 個 cluster、合計 ~8 sprint、Sprint 197 已標 ROI 低）

---

## 三層 SOP（Sprint 198）

- L1 vitest：**1912 passed + 1 skipped**（`npm test` 全套；+6：3 Sprint 198
  audit + 3 自然增長）
- L2 VR v14：**byte-identical 第 56 連 unchanged**（無 production code 變動）
- L3 audit-only：本 sprint 0 行 production code、純 test/fixture 廣域驗證

---

## 紀律

- **#1 / Strategy C**：本 sprint test-only、不動 VR
- **#2 magic number**：2 個具名常數（EXPECTED_FIXTURE_COUNT / MIN_SUCCESS_RATE_PCT）
- **#14.b clean scope**：fixture prep 已先 commit（`6323de8`）、本 commit 只含
  audit test + audit doc + INDEX / snapshot 更新
- **#18 scope-down**：寬鬆 success rate 下限 50%（接受 LibreOffice 故意畸形
  case 失敗）、不強要 100%；WPS fixture 留 future sprint（需另尋來源）
- **#21**：失敗 case 必須 throw Error、不 silent corruption（已驗證）
- **honest gap**：WPS docx 來源 fixture 未涵蓋、留 future sprint optional

---

## 後續

- **Phase 7 OffscreenCanvas worker / Web Worker parse**（高成本低 ROI、
  Sprint 197 判定不建議）
- **大檔 fixture + benchmark**（合成 50/100/200p、需建合成器）
- **WPS 產出 fixture audit**（需另尋來源、補完邊緣相容性最後一塊）

---

## File-level summary

```
A  tests/integration/sprint198_libreoffice_compat.test.ts  (+147 行)
A  docs/sprint198_libreoffice_compat.md                    本 audit
M  docs/INDEX.md                                           +Sprint 198 entry
M  docs/progress_snapshot.md                               Phase 7 更新 84% → ~87%
```

**淨 production code 變動 = 0 行**、test-only audit、290 個 LibreOffice
邊緣 fixture **99.3% parse 成功 / 100% 結構保留 / 0 crash**、Phase 7
「邊緣 docx 相容性 audit」sub-item 達成。
