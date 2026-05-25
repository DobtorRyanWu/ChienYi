# Sprint 215 — Phase 6 ChienYi fixture ParagraphProps preservation audit（42/42 全 100%、3384 paragraphs 全綠）

**日期**：2026-05-25（週一）
**類型**：test-only audit（無 production code 變動）
**規畫書對應**：§6 黃金測試「import(export(doc)) ≅ doc」**ParagraphProps 格式級對稱**
**前置**：Sprint 210-212 RunProps 三 corpus 矩陣完備（11645 runs 全 100%）

---

## Hypothesis

Sprint 210-212 完成 RunProps SHA-256 三 corpus 三層矩陣（合計 11645 runs
全 byte-identical）；但 **paragraph-level 格式（ParagraphProps）未獨立
驗證**。

對 ChienYi v1 release 商用層次而言：
- run-level 格式保留 100%（Sprint 210） → 字型 / 顏色 / 粗體 不丟
- **段落層級格式保留 ?** → 若段落對齊 / 縮排 / 間距在 round-trip 後丟失、
  export 排版視覺仍會跑掉（如標題置中變左對齊、條列縮排消失）

本 sprint 對 ChienYi 42 production fixture 各段落的 **ParagraphProps
deep-stable JSON SHA-256 fingerprint** 對照、量化段落格式保留率。

**hypothesis**：Phase 6 Sprint 187 writePPr 設計即為對等 path（schema
順序 + OOXML §17.3 對等屬性）、預期 100% match。

**實測結果**：**42/42 全 100% / 3384 paragraphs 全綠**——超越 95% 閾值
5pp、Phase 6 writer 對 ChienYi production workflow 達 **paragraph-level
byte-identical 格式級對稱**。

---

## 修法

新檔 `tests/integration/sprint215_chienyi_pprops_preservation_audit.test.ts`
（+220 行）：

### Deep stable stringify（紀律 #2 / #18 必要、與 Sprint 210 不同）

ParagraphProps 含 5 個 nested object（indent / spacing / borders / shading /
framePr）+ 1 個 nested array（tabs[]）、無法用 Sprint 210 RUN_PROPS_KEYS
top-level 顯式 list 處理；改用遞迴 deep-stable 排序：

```ts
function deepStableStringify(value: unknown): string {
  if (value === null || value === undefined) return JSON.stringify(value);
  if (typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(deepStableStringify).join(',') + ']';
  const keys = Object.keys(value).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + deepStableStringify(value[k])).join(',') + '}';
}
```

保證跨進程 / 跨平台 deterministic、不受 Object.keys 插入順序影響。

### Pipeline 流程

每 fixture：
1. parse(原 bytes) → originalDoc
2. write(originalDoc) → exported bytes
3. parse(exported bytes) → reparseDoc
4. collectPParagraphPropsSignatures：遞迴 sections → blocks → table cells、
   按出現順序收集 `serializeParagraphProps(p.props)`
5. SHA-256(originalSigs.join('|')) === SHA-256(reparseSigs.join('|'))

ParagraphProps 14 個頂層欄位涵蓋：
- alignment（left / center / right / both / distribute）
- indent（left / right / firstLine / hanging）
- spacing（before / after / line.{rule,value}）
- borders（top / bottom / left / right）
- shading（fill / color / pattern）
- keepNext / keepLines / pageBreakBefore / snapToGrid
- numId / ilvl（清單編號）
- tabs[]（tab stop 陣列）
- textAlignment（垂直對齊）
- framePr（段落框 ~12 子欄位）

---

## Result — 42/42 全 100% ParagraphProps SHA-256 對齊

```
[sprint215] total=42 pProps match=42/42 (100.0%) totalParagraphs=3384
[sprint215]   01_simple         : 7/7 (100.0%) paragraphs=1219
[sprint215]   02_std_table      : 8/8 (100.0%) paragraphs=356
[sprint215]   03_complex_table  : 8/8 (100.0%) paragraphs=275
[sprint215]   04_with_image     : 6/6 (100.0%) paragraphs=221
[sprint215]   05_header_footer  : 10/10 (100.0%) paragraphs=1125
[sprint215]   06_template       : 3/3 (100.0%) paragraphs=188
```

| 指標 | 值 |
|---|---|
| Fixture count | 42 |
| ParagraphProps SHA-256 match | **42/42 (100%)** ⭐ |
| Total paragraphs verified | **3384** |
| 超越閾值 | 95% → 100% (+5pp) |

---

## 為何全 100%

Phase 6 Sprint 187 `writePPr` 設計即為對等 path：

1. **Schema 順序**：依 OOXML CT_PPr schema 順序序列化（pStyle → numPr →
   pBdr → shd → tabs → spacing → ind → jc → textAlignment → framePr →
   keep* → pageBreakBefore → snapToGrid）、reparser 對等
2. **Twips 轉換**：indent / spacing.line value Pt × 20 ⇄ twips 對等讀回
3. **Toggle property**：keepNext / keepLines / pageBreakBefore / snapToGrid
   `true` 用空 element、`false` 用顯 `w:val="0"` 覆蓋 style
4. **Nested objects**：indent / spacing / borders / shading / framePr 各走
   對等 path、parser & writer 屬性順序一致
5. **Numbering**：numId + ilvl 嵌於 `<w:numPr>` 子元素、parser 對等讀回
6. **Tabs[]**：array 按出現順序保留、tab 屬性（pos / align / leader）對等

---

## 完整格式對等性驗證層次（Sprint 198-215）

| 驗證層次 | Sprint | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|---|
| Parse OK | 198 | n/a | 99.3% | n/a |
| Round-trip 4-stage structure | 206 + 199 + 209 | 100% | 100% | 100% |
| Text SHA-256 | 207 + 208 + 209 | 100% | 100% | 100% |
| **RunProps SHA-256** | **210 + 211 + 212** | **100% / 9508 runs** | **100% / 2114 runs** | **100% / 23 runs** |
| **ParagraphProps SHA-256** | **215** | **100% / 3384 paragraphs** ⭐ | future sprint | future sprint |
| Perf parse + layout | 203 + 205 + 214 | < 閾值 | n/a | n/a |

**Phase 6 黃金測試「import(export(doc)) ≅ doc」對 ChienYi production
workflow 達四層對稱**：
- Structure ✅
- Text content ✅
- RunProps formatting ✅
- **ParagraphProps formatting ✅** ⭐

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1990 passed + 1 skipped**（+1 sprint215）；單跑 sprint215 1/1 綠 8378ms |
| L2 VR v14 | ✅ **byte-identical 第 62 連** | docs/test-only、不改動 writer / parser / layout / render → 42 VR fixture 結構性 unchanged |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**、純 test
  補 ParagraphProps 格式級對稱驗證
- **#2 magic number**：3 個具名常數（CHIENYI_CATEGORIES +
  EXPECTED_FIXTURE_COUNT + MIN_PPROPS_MATCH_RATE_PCT=95）+
  `deepStableStringify` 遞迴序列化函式
- **#14.b clean scope**：commit = sprint215 test + audit doc + INDEX/snapshot
- **#18 scope-down**：
  - 只 ChienYi 42 production corpus（LibreOffice 286 + Phase 5 18 留
    Sprint 216-217 補完三 corpus）
  - 改用 deepStableStringify 處理 nested objects、不引入 ParagraphProps
    顯式 key list（14 欄位 + 5 nested objects 過於複雜、deep stable 更
    robust）
  - 95% 閾值寬鬆設定、實測達 100%
- **#21**：本 sprint 不影響 VR / round-trip 既有測試

---

## Phase 6 完成度更新

- Sprint 196 後 100% MVP
- Sprint 206-214 三 corpus 三層 byte-identical 矩陣完備（structure + text + RunProps）
- **Sprint 215 補 ChienYi paragraph-level 格式對稱、3384 paragraphs 全綠**
- Phase 6 完成度維持 100% MVP、**新增「ChienYi production ParagraphProps
  byte-identical」段落層級格式對稱驗證**

---

## File-level summary

```
A  tests/integration/sprint215_chienyi_pprops_preservation_audit.test.ts   +220 行
A  docs/sprint215_chienyi_pprops_preservation_audit.md                     本 audit
M  docs/INDEX.md                                                           +Sprint 215 entry
M  docs/progress_snapshot.md                                               Sprint 215 區塊 + ParagraphProps 對稱性
```

**淨 production code 變動 = 0 行**、vitest 1989→**1990**（+1 sprint215）、
VR byte-identical 第 62 連 unchanged、**ChienYi 42 fixture 3384
paragraphs 全 ParagraphProps SHA-256 100% byte-identical**（涵蓋
alignment / indent / spacing / borders / shading / numId+ilvl / tabs /
textAlignment / framePr 14 個欄位）、Phase 6 黃金測試「import(export(doc))
≅ doc」**ChienYi production 達 structure + text + RunProps +
ParagraphProps 四層對稱**、ChienYi v1 release commercial-grade 端到端
「匯入→匯出→再匯入文字 + run 格式 + 段落格式皆不失真」最嚴格量化保證。
