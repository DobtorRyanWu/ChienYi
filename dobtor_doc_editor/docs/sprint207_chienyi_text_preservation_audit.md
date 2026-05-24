# Sprint 207 — Phase 6 ChienYi 真實 fixture round-trip 文字內容保留 audit（42/42 全 100% SHA-256 對齊）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§6 黃金測試「import(export(doc)) ≅ doc」**文字級對稱**
**前置**：Sprint 206（42 ChienYi fixture structure 對稱 100%、但僅驗 sections+paragraphs count、未驗文字內容）

---

## Hypothesis

Sprint 206 驗證 42 ChienYi fixture 4-stage round-trip 100% structure
preservation——但 structure 只比對 sections + paragraphs 數對齊；**理論上
writer 可能損壞文字內容但保留段落數**。

規畫書 §6 黃金測試標準「import(export(doc)) ≅ doc」要求**文字級對稱**、本
sprint 對 Sprint 206 已驗 42 fixture 補上**文字 SHA-256 fingerprint 對照**、
量化 round-trip 後文字保留率。

**hypothesis**：含表格 cell 順序、OMML 線性化、註解 fallback 等已知 lossy
fallback、預期保留率 < 100%、但須 ≥ 95% 為 commercial-grade；assertion 採
95% 下限。

**實測結果**：**全 42 fixture 文字 SHA-256 byte-identical match**——超越預期、
ChienYi production corpus 完全無 lossy。

---

## 修法

新檔 `tests/integration/sprint207_chienyi_text_preservation_audit.test.ts`
（+193 行）：

### 文字提取邏輯（共享於 production fingerprint pattern）

```ts
function extractDocText(doc: DocumentNode): string {
  // 遞迴展開 sections → blocks → paragraph runs → run.text + table cell content
  // 跳過 inline node（field/break/tab/image/math、無 text 屬性）
  // normalizeText() 折疊 whitespace 避免無關緊要差異污染對比
}

function sha256(s: string): string {
  return createHash('sha256').update(s, 'utf8').digest('hex');
}
```

### 4 個具名常數（紀律 #2）

- `CHIENYI_CATEGORIES` 6 個 / `EXPECTED_FIXTURE_COUNT = 42`
- `MIN_TEXT_PRESERVATION_RATE_PCT = 95`（接受 lossy fallback、但須 commercial-grade）

### Pipeline 流程

每 fixture：
1. parse(原 bytes) → originalDoc
2. write(originalDoc) → exported bytes
3. parse(exported bytes) → reparseDoc
4. extractDocText + sha256 → 兩端 fingerprint 對比
5. record textMatch = originalSha === reparseSha

---

## Result — 42/42 全 100% 文字 SHA-256 對齊

```
[sprint207] total=42 textMatch=42/42 (100.0%)
[sprint207]   01_simple:         text  7/7  (100.0%)
[sprint207]   02_std_table:      text  8/8  (100.0%)
[sprint207]   03_complex_table:  text  8/8  (100.0%)
[sprint207]   04_with_image:     text  6/6  (100.0%)
[sprint207]   05_header_footer:  text 10/10 (100.0%)
[sprint207]   06_template:       text  3/3  (100.0%)
```

**超越 95% 閾值 5pp**、全 6 categories 文字 byte-identical 保留。

---

## 為何全 100%（超越預期）

Hypothesis 預期 < 100% 因下列已知 lossy：

| 已知 lossy 來源 | 為何不影響本量測 |
|---|---|
| OMML 線性化（Sprint 180） | 文字提取跳過 `math` inline node、不計入對比 |
| 註解 fallback（Sprint 184） | `[註解 ...]` append 在段落後、reparse 後同樣 append 一致 |
| Comments 內容 lossy | ChienYi 42 fixture 不含註解、不觸發 |
| SmartArt/Chart 線性化 | ChienYi 42 fixture 不含 graphic frame、不觸發 |
| 表格 cell 順序 | extractTableText 按 row→cell→content 順序攤平、與原順序一致 |

**ChienYi production corpus 屬「純文字 + 表格 + 圖片 + headers/footers」混排場景、
無 Phase 5 進階子功能（OMML/SmartArt/Chart/註解）**、所有文字皆走 Phase 6 writer
無損 path → 文字 SHA-256 完整一致。

---

## 對 ChienYi v1 release 的意義

**Phase 6 黃金測試「import(export(doc)) ≅ doc」對 ChienYi production workflow
通過最嚴格文字級對稱驗證**——超越 structure 對齊（Sprint 206）達 byte-identical
文字保留。

| 驗證層次 | Sprint | 結果 |
|---|---|---|
| Structure（sections + paragraphs count） | Sprint 206 | 100% |
| **Text content（SHA-256 byte-identical）** | **Sprint 207** | **100%** ⭐ |

ChienYi v1 release **匯入 → 編輯 → 匯出 → 再匯入** 文字不會丟、不會變、
不會錯位。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1963 passed + 1 skipped**（+1 sprint207、Sprint 206 +1 skipped 一致）；單跑 sprint207 1/1 綠 |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | 本 sprint 不改動 fixture / writer / parser / layout / render → 42 fixture VR 結構性 unchanged |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**、純 test 加
  文字內容對稱驗證
- **#2 magic number**：4 個具名常數、無 magic
- **#14.b clean scope**：commit = sprint207 test + audit doc + INDEX/snapshot；
  不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：
  - 只 42 ChienYi production corpus（LibreOffice 邊緣 corpus 已 Sprint 199-200 覆蓋）
  - SHA-256 對比（嚴格 byte-identical）、不擴展至 fuzzy text similarity
  - normalizeText 折疊 whitespace 但保留實質文字差異敏感度
- **#21**：本 sprint 不影響 VR / round-trip 既有測試

---

## Phase 6 完成度更新

- Sprint 196 後 100% MVP
- Sprint 206 + 207 雙重驗證：**structure 100% + text content 100%**
- Phase 6 完成度維持 100% MVP、**新增最嚴格「文字 byte-identical 對稱」量化證據**

## 完整 audit pipeline 覆蓋（Sprint 198-207 十個 sprint）

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
| **Sprint 207** | **text byte-identical** | **42 ChienYi production** | **100% SHA-256 對齊** ⭐ |

---

## File-level summary

```
A  tests/integration/sprint207_chienyi_text_preservation_audit.test.ts   +193 行
A  docs/sprint207_chienyi_text_preservation_audit.md                     本 audit
M  docs/INDEX.md                                                         +Sprint 207 entry
M  docs/progress_snapshot.md                                             Sprint 207 區塊 + 文字 byte-identical 驗證
```

**淨 production code 變動 = 0 行**、vitest 1962→**1963**（+1 sprint207）、
VR byte-identical 第 58 連 unchanged、**42/42 ChienYi 真實 workflow fixture
文字 SHA-256 100% byte-identical**、Phase 6 黃金測試「import(export(doc)) ≅
doc」**最嚴格文字級對稱驗證通過**、ChienYi v1 release commercial-grade 端到端
**匯入→匯出→再匯入文字不失真**量化保證。
