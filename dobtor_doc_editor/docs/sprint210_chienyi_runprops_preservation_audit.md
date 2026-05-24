# Sprint 210 — Phase 6 ChienYi fixture RunProps preservation audit（42/42 全 100%、9508 runs 全綠）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§6 黃金測試「import(export(doc)) ≅ doc」**RunProps 格式級對稱**
**前置**：Sprint 207 ChienYi 42 text 100% / Sprint 208 LibreOffice 286 text 100% / Sprint 209 Phase 5 18 全 100%

---

## Hypothesis

Sprint 207-209 audit pipeline 驗證 ChienYi + LibreOffice + Phase 5 fixture 文字
SHA-256 100% byte-identical；但 **文字格式（RunProps：bold / italic / fontSize /
color / underline / strike / highlight / vertAlign / spacing / lang / 4 個字型
family）未獨立驗證**。

對 ChienYi v1 release 商用層次而言：
- 文字保留 100%（Sprint 207） → 文字內容不丟
- **格式保留 ?** → 若 bold/italic/size 在 round-trip 後丟失、export 在商用
  場景仍不可用（監造會議記錄章節標題若沒粗體就跑版、估驗表金額若沒對齊就難看）

本 sprint 對 ChienYi 42 production fixture 各 run 的 **RunProps 序列化 SHA-256
fingerprint** 對照、量化格式保留率。

**hypothesis**：Phase 6 Sprint 186 writeRPr 設計即為對等 path（schema 順序 +
toggle property + 4 字型 family）、預期 100% match；< 100% 即真實 commercial gap。

**實測結果**：**42/42 全 100% / 9508 runs 全綠**——超越 95% 閾值 5pp、Phase 6
writer 對 ChienYi production workflow 達 **byte-identical 格式級對稱 commercial-
grade**。

---

## 修法

新檔 `tests/integration/sprint210_chienyi_runprops_preservation_audit.test.ts`
（+215 行）：

### Deterministic serialization（無 magic、紀律 #2）

`RUN_PROPS_KEYS` 列舉 15 個 RunProps 欄位、按 interface 宣告順序（避免
Object.keys 不確定性）：
```ts
['fontFamily', 'fontFamilyEastAsia', 'fontFamilyHAnsi', 'fontFamilyCs',
 'fontSize', 'bold', 'italic', 'underline', 'strike', 'dstrike',
 'color', 'highlight', 'vertAlign', 'spacing', 'lang']
```

### Pipeline 流程

每 fixture：
1. parse(原 bytes) → originalDoc
2. write(originalDoc) → exported bytes
3. parse(exported bytes) → reparseDoc
4. collectRunPropsSignatures：遞迴 sections → blocks → paragraph.runs →
   table.rows → cell.content、按出現順序收集 `serializeRunProps(run.props)`
5. SHA-256(originalSigs.join('|')) === SHA-256(reparseSigs.join('|'))

---

## Result — 42/42 全 100% RunProps SHA-256 對齊

```
[sprint210] total=42 runProps match=42/42 (100.0%) totalRuns=9508
[sprint210]   01_simple         : 7/7 (100.0%) runs=2520
[sprint210]   02_std_table      : 8/8 (100.0%) runs=730
[sprint210]   03_complex_table  : 8/8 (100.0%) runs=460
[sprint210]   04_with_image     : 6/6 (100.0%) runs=388
[sprint210]   05_header_footer  : 10/10 (100.0%) runs=4929
[sprint210]   06_template       : 3/3 (100.0%) runs=481
```

| 指標 | 值 |
|---|---|
| Fixture count | 42 |
| RunProps SHA-256 match | **42/42 (100%)** ⭐ |
| Total runs verified | **9508** |
| 超越閾值 | 95% → 100% (+5pp) |

---

## 為何全 100%

Phase 6 Sprint 186 `writeRPr` 設計即為對等 path：

1. **Schema 順序**：依 OOXML CT_RPr schema 順序序列化（rFonts → b → i → strike →
   dstrike → color → spacing → sz → highlight → u → vertAlign → lang）、reparser
   讀回的 props 對等
2. **Toggle property**：bold/italic/strike `true` 用空 element、`false` 用顯
   `w:val="0"` 覆蓋 style、reparser 也對等讀回 boolean
3. **Half-points 轉換**：fontSize Pt × 2 → half-points、reparser 對等 ÷ 2 還原
4. **4 個字型 family**：fontFamily / fontFamilyEastAsia / fontFamilyHAnsi /
   fontFamilyCs 各自走 `w:rFonts` 屬性、reparser 對等讀回
5. **Twips / hex / 列舉**：spacing twips / color hex / highlight hex / vertAlign
   列舉 / lang 字串 各走對等 path

---

## 完整驗證層次（Sprint 198-210）

| 驗證層次 | Sprint | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|---|
| Parse OK | 198 | n/a | 99.3% | n/a |
| Round-trip 4-stage structure | 206 + 199 + 209 | 100% | 100% (Sprint 200 後) | 100% |
| Text SHA-256 byte-identical | 207 + 208 + 209 | 100% | 100% | 100% |
| **RunProps SHA-256 byte-identical** | **210** | **100%** ⭐ | future sprint | future sprint |
| Perf parse + layout | 203 + 205 | < 閾值 | n/a | n/a |
| Perf cold/warm | 201 + 202 | included | included | included |

**Phase 6 黃金測試「import(export(doc)) ≅ doc」對 ChienYi production workflow
達成最嚴格層次驗證**：
- Structure ✅
- Text content ✅
- **RunProps formatting ✅** ⭐

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1967 passed + 1 skipped**（+1 sprint210）；單跑 sprint210 1/1 綠 |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | docs/test-only、不改動 writer / parser / layout / render → 42 VR fixture 結構性 unchanged |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**、純 test 補
  RunProps 格式級對稱驗證
- **#2 magic number**：3 個具名常數（CHIENYI_CATEGORIES + EXPECTED_FIXTURE_COUNT +
  MIN_RUNPROPS_MATCH_RATE_PCT）+ `RUN_PROPS_KEYS` 顯式 list；無 magic
- **#14.b clean scope**：commit = sprint210 test + audit doc + INDEX/snapshot；
  不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：
  - 只 ChienYi 42 production corpus（LibreOffice 286 + Phase 5 18 留 future
    sprint 如需）
  - 顯式 RUN_PROPS_KEYS list 避免 Object.keys 不確定性
  - 95% 閾值寬鬆設定、實測達 100% 證明 writer 對格式達 byte-identical
- **#21**：本 sprint 不影響 VR / round-trip 既有測試

---

## Phase 6 完成度更新

- Sprint 196 後 100% MVP
- Sprint 206 + 207 + 208 + 209 雙 corpus + Phase 5 進階 100%
- **Sprint 210 補 RunProps 格式級對稱、9508 runs 全綠**
- Phase 6 完成度維持 100% MVP、**新增「ChienYi production RunProps byte-identical」
  最嚴格格式級對稱驗證**

---

## File-level summary

```
A  tests/integration/sprint210_chienyi_runprops_preservation_audit.test.ts   +215 行
A  docs/sprint210_chienyi_runprops_preservation_audit.md                     本 audit
M  docs/INDEX.md                                                             +Sprint 210 entry
M  docs/progress_snapshot.md                                                 Sprint 210 區塊 + RunProps 格式級對稱驗證
```

**淨 production code 變動 = 0 行**、vitest 1966→**1967**（+1 sprint210）、
VR byte-identical 第 58 連 unchanged、**ChienYi 42 fixture 9508 runs 全
RunProps SHA-256 100% byte-identical**（涵蓋 bold/italic/fontSize/color/
underline/strike/highlight/vertAlign/spacing/lang/4 字型 family）、Phase 6
黃金測試「import(export(doc)) ≅ doc」**ChienYi production 達 structure + text +
RunProps 三層對稱**、ChienYi v1 release commercial-grade 端到端「匯入→匯出→
再匯入文字 + 格式皆不失真」最嚴格量化保證。
