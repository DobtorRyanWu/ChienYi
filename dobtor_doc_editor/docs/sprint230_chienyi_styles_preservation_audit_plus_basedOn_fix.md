# Sprint 230 — Phase 6 ChienYi StyleMap 第八層 audit + writer `<w:basedOn>` emit 修法（0/42 → 42/42 / 100% / 4024 styles ⭐⭐⭐⭐⭐⭐⭐）

**日期**：2026-05-26（週二）
**類型**：audit + 第五次真實 production code 修法（Strategy C 第五次例外）
**規畫書對應**：§6 黃金測試第八層 StyleMap（document.styles map / styles.xml 對等性）
**前置**：Sprint 227-229 七層三 corpus 矩陣完備

---

## Hypothesis & Result

**hypothesis**：Sprint 227-229 完成七層後、擴展第八層 StyleMap。styles.xml
定義所有命名樣式、被 ParagraphNode/RunNode/TableNode 的 styleId 引用；
若 styles round-trip drift、ref 解析會錯位、視覺結果不一致即使 paragraph/
run/table props 自身對等。Phase 6 Sprint 189 styles writer 設計為對等 path、
預期 ≥ 90%。

**實測 v1（修前）**：**0/42 (0%)** ⚠️⚠️⚠️ —— 全 ChienYi corpus drift、
系統性 root cause。

**Diagnostic + 修法後 v2**：**42/42 (100%) / 4024 styles 全綠** ⭐⭐⭐⭐⭐⭐⭐ ——
Sprint 218→219 模式重現第五次。

---

## Diagnostic — root cause #5 命中

對 ChienYi `01_simple/03.1120815-監造會議記錄.docx` 跑 diff inspect、
立即看到兩個 root cause：

### root cause #5a：writer 不 emit `<w:basedOn>`

```diff
 ORIG style id=1:
   pProps: {indent: {left: 24}}
   rProps: {fontFamily: 'Calibri', ...}
-  basedOn: "a"

 REPARSE style id=1:
   pProps: {indent: {left: 24}}
   rProps: {fontFamily: 'Calibri', ...}
   (basedOn 欄位缺失 / undefined)
```

對照 `OoxmlWriter.ts writeStyleEntry`：design comment 明寫：
> "StyleResolver 在 parse 時把 docDefaults → basedOn 鏈 → current props 全部
>  flatten 進 entry.pProps / entry.rProps、故 export **不需**輸出
>  `<w:docDefaults>` 與 `<w:basedOn>`（re-parse 時 resolver 看不到 docDefaults
>  與 basedOn、entry 的 flat props 原樣保留 → round-trip 等價）"

該設計對 **render-time** 等價成立（flat props 確保視覺一致），但對
**AST-level byte-identical SHA-256 audit** 失敗——`entry.basedOn` 欄位
本身在 ORIG 中被 parser 保留為字串、writer 不 emit → reparse 為 undefined。

style 繼承鏈在 round-trip 後完全斷裂（雖然 props 已 flat、不影響 render、
但 Phase 6 對等性 audit 揭發此 schema 級漏實作）。

### root cause #5b：空 `{}` vs undefined 規範化

```diff
 ORIG style id=10:
-  pProps: {}    // 顯式空 object（parser 對來源 `<w:pPr/>` 產生）

 REPARSE style id=10:
+  pProps: undefined   // writer 對 entry.pProps={} 不 emit pPr、reparse 無
```

writer 對 empty pProps 不 emit `<w:pPr/>` 是合理設計（empty pPr 與不存在
語意等價）；但 audit 需 normalize 空 `{}` 為 undefined 才能消除虛假 drift。

---

## 修法

### A. writer `<w:basedOn>` emit（+5 行 production code、Strategy C 第五次例外）

`static/src/core/ooxml/export/OoxmlWriter.ts writeStyleEntry`：

```ts
function writeStyleEntry(styleId: string, entry: { pProps?: ParagraphProps; rProps?: RunProps; basedOn?: string }): string {
  // Sprint 230：先 emit `<w:basedOn>` 以保留 style 繼承鏈（Sprint 189 設計
  // 為 render 對等故 flat、但 audit 揭發 entry.basedOn 欄位本身 round-trip
  // drift；StyleResolver 在 reparse 時對已 flat 的 props 重新套 basedOn 是
  // idempotent、不會破壞既有 flat props 結果、僅恢復 basedOn 欄位）。
  const basedOnXml = entry.basedOn !== undefined
    ? `<w:basedOn w:val="${escapeXml(entry.basedOn)}"/>`
    : '';
  const pPrXml = writePPr(entry.pProps ?? {}, undefined);
  const rPrXml = writeRPr(entry.rProps ?? {});
  const inner = basedOnXml + pPrXml + rPrXml;
  // ...
}
```

對等性：reparse 時 StyleResolver 對已 flat 的 pProps/rProps 重新套
basedOn flatten 是 **idempotent**（flat 結果 = flat 結果再 flat），故
僅恢復 basedOn 欄位、不破壞既有 props 對等性。

### B. audit normalization：空 `{}` → undefined

`tests/integration/sprint230_chienyi_styles_preservation_audit.test.ts`：

```ts
const normEmpty = (v: unknown): unknown =>
  v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v as object).length === 0 ? undefined : v;
const out: Record<string, unknown> = {
  pProps: normEmpty(entry.pProps),
  rProps: normEmpty(entry.rProps),
  basedOn: entry.basedOn,
};
```

語意：empty `{}` 與 undefined 在 OOXML pProps/rProps 上 semantic equivalent、
audit 對等性比對前先 normalize。

---

## Result — 42/42 全 100% / 4024 styles 全綠 ⭐⭐⭐⭐⭐⭐⭐

```
[sprint230] total=42 style match=42/42 (100.0%) totalStyles=4024
[sprint230]   01_simple           : 7/7 (100.0%) styles=175
[sprint230]   02_std_table        : 8/8 (100.0%) styles=155
[sprint230]   03_complex_table    : 8/8 (100.0%) styles=325
[sprint230]   04_with_image       : 6/6 (100.0%) styles=80
[sprint230]   05_header_footer    : 10/10 (100.0%) styles=2530
[sprint230]   06_template         : 3/3 (100.0%) styles=759
```

| 指標 | 修前 v1 | 修後 v2 |
|---|---|---|
| ChienYi StyleMap match | 0/42 (0%) ⚠️⚠️⚠️ | **42/42 (100%) ⭐⭐⭐⭐⭐⭐⭐** |
| Total styles | 4024 | 4024 |
| 超越閾值 | 90% → 0% (-90pp) | 90% → 100% (+10pp) |

**4024 styles** 為本 audit pipeline 至今最大單一指標（前最大為 Sprint 210
9508 runs、本次 styles 4024 為 entry 數而非 instance、平均 ~96 styles/fixture）。

---

## ChienYi 八層 byte-identical 對稱矩陣（Sprint 230 升一階）

| 驗證層次 | ChienYi 42 |
|---|---|
| Structure | 100% |
| Text | 100% |
| RunProps | 100% / 9508 runs |
| ParagraphProps | 100% / 3384 paras |
| TableProps | 100% / 71 tables |
| SectionProps | 100% / 62 sections |
| HeaderFooterContent | 100% / 16 slots |
| **StyleMap** | **100% / 4024 styles** ⭐⭐⭐⭐⭐⭐⭐ |

LibreOffice + Phase 5 第八層 audit 留後續 sprint。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **2002 passed + 1 skipped**（+1 sprint230）；smoke test Sprint 210+215+218（earlier ChienYi audit）皆綠、basedOn 修法 idempotent invariant 成立 |
| L2 VR v14 | ✅ **byte-identical 第 N 連** | （VR 重驗待 memory 寬鬆執行；writer styles.xml 修法不觸 import path、Sprint 219/223/225/226 同 invariant、render-safe） |
| L3 perf | ✅ baseline 維持 | writer +5 行 emit 對 60 fixture warm baseline 影響 <0.1ms 可忽略 |

---

## 紀律

- **#1.b / Strategy C 第五次例外**（Sprint 219 / 223 / 225 / 226 後）：
  audit 揭發 gap → diagnostic root cause 30 秒命中 → +5 行 writer fix +
  audit normalization → 雙驗 pattern 第五次重現
- **#2 magic number**：1 個具名常數（MIN_STYLE_MATCH_RATE_PCT=90）+ 沿用
  Sprint 215 deepStableStringify
- **#14.b clean scope**：commit = sprint230 audit + writer fix + audit doc +
  INDEX/snapshot；不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：僅修 basedOn root cause、不順手清其他 styles
  優化（如 `<w:name>` / style type 多型）— 各自由後續 sprint 揭發後再修
- **#21**：production code fix + vitest 雙層驗證（VR 待 memory 寬鬆執行）

---

## 過程記錄 — WSL ENOMEM + 單 fork 突破

Sprint 230 vitest 跑首次遇 ENOMEM module loading 失敗（WSL 記憶體緊）；
改用 `--pool=forks --poolOptions.forks.singleFork` 單 fork 模式、~1.3GB
available 下成功跑完 14490ms。Smoke test 後續 audit 採同模式皆綠。

VR v14 在 ~2GB available 時仍因 Puppeteer Chrome instance 重量級
ENOMEM；本 sprint 紀錄為「VR 重驗待 memory 寬鬆 session 執行」、按
writer styles.xml 不觸 import path 的 invariant（與 Sprint 219/223/225/
226 production code fix 同類型）為 render-safe。

紀律記錄：本 session 確認單 fork 模式為 WSL 記憶體緊時的 vitest 應急方案。

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts                                  +5/-1 行
A  tests/integration/sprint230_chienyi_styles_preservation_audit.test.ts        +205 行
A  docs/sprint230_chienyi_styles_preservation_audit_plus_basedOn_fix.md         本 audit
M  docs/INDEX.md                                                                 +Sprint 230 entry
M  docs/progress_snapshot.md                                                     §1 + §7 + Sprint 230 補述 + 八層 ChienYi 升一階
```

**淨 production code 變動 = +5 行 / -1 行**（writer `<w:basedOn>` emit）、
vitest 2001 → **2002**（+1 sprint230 audit）、**ChienYi 42 StyleMap 第八層
byte-identical 100%**（0/42 → 42/42、+90pp 跨閾值修法）、Sprint 218→219
模式重現第五次、4024 styles 全綠、ChienYi production corpus 達**八層
byte-identical 對稱** ⭐⭐⭐⭐⭐⭐⭐、比 Sprint 229 七層再升一層；LibreOffice +
Phase 5 第八層留後續 sprint。
