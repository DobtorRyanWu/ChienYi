# Sprint 7 — StyleResolver（xf cascade 攤平，§2.1）

**日期**：2026-06-07
**Phase**：2（Cell Rendering & Text Metrics）§2.1
**對齊**：規劃書 §2.1 StyleResolver

---

## Root cause（開工前假設）

§1.5 已把 styles.xml 解析成各池（fonts/fills/borders/cellXfs/cellStyleXfs）與 cellXfs 索引，
但 cell 要拿到「最終生效樣式」還需做 cascade：cellXf（直接格式）疊在 cellStyleXf（named style）之上，
各屬性依 applyX 旗標決定取自身或繼承。沒有這層，Phase 2 渲染／Phase 4.5 餵 o-spreadsheet 都無法取得
單一可用的樣式物件。

紀律 #18 對齊：§2.1 只做「xf cascade 攤平成 ResolvedStyle」。theme/indexed color → RGB 是 §2.2
ThemeResolver、number format 完整渲染是 §2.3，皆不在本 sprint。

## 修法（實際做的事）

### `style_resolver.ts`
- `StyleResolver(styles).resolve(styleIndex)` → `ResolvedStyle`（含快取）：
  - cascade 規則：`parent = cellStyleXfs[cellXf.xfId]`；各屬性
    `applyX=1 → 用 cellXf 自身 id；否則繼承 parent；無 parent 時恆用 cellXf`
  - 攤平 numFmtId/font/fill/border/alignment → 具體 `Font`/`Fill`/`Border` 物件
  - 附帶 `numFmtCode`（numberFormatCode 解析）+ `isDate`（isDateNumberFormat）
  - styleIndex undefined / 越界 → 預設樣式，不丟錯
- `resolveXf(xf)`：對單一 cellXf 攤平（供 dxf/其他來源 xf 重用）

## 三層 SOP 結果

- **L1 vitest**：**307 passed**（unit 120 + integration 187）
  - `style_resolver.test.ts`（7）：合成 4 個 cellXf 驗證
    - index0 全繼承 named style（alignment vertical=center）
    - index1 applyFont 只覆寫 font、其餘繼承
    - index2 全自訂（日期 numFmt176 + 紅粗體 + 黃底 + thin 框 + 置中）
    - **index3：fontId1 但無 applyFont → 繼承 named style font0**（驗證 apply 旗標 gating）
    - 預設/越界/快取（同 index 回同一物件）
  - `style_resolver_corpus.test.ts`（48）：**全 48 fixture** 每個 cellXf 攤平後 font/fill/border 為物件、
    numFmtId 非負整數、isDate↔numFmtCode 一致、預設樣式不丟錯
- **L2 visual regression**：N/A（像素比對待 Phase 4 VR pipeline 接入）
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（13.4s）

## 設計取捨（紀律 #4）

1. **apply 旗標模型 vs 值差異啟發式**：採 ECMA-376 的 applyX 旗標 cascade（Excel 寫直接格式時必設旗標），
   而非「cellXf 值 ≠ parent 值就套用」的啟發式（後者易過度套用）。對 ChienYi 實檔（旗標齊全）正確；
   標為 hypothesis：若遇旗標缺失但值有異的非 Excel 產出檔，可能需補值差異 fallback。
2. **本層不解色**：font.color / fill.fgColor 仍是 theme/indexed/rgb 原始 `Color`，→ 具體 RGB 待 §2.2。
   故本 sprint 無法做像素級樣式驗證，僅做結構健全性（cascade 不崩、索引有效）。
3. **alignment 不做欄位級合併**：採整段取 cellXf 或 parent（applyAlignment gating），不做
   horizontal/vertical 個別欄位 merge。實檔 alignment 多為整段定義，影響小。

## 對齊 Phase 進度

| 項目 | 狀態 |
|---|---|
| §1.5 StylesParser | 🟢（Sprint 5） |
| §2.1 StyleResolver（cascade 攤平） | 🟢 本 sprint |
| §2.2 ThemeResolver（theme/tint/indexed → RGB） | ⚪ 下一步 |
| §2.3 NumberFormat（日期最小版） | 🟢（Sprint 6）；完整渲染待續 |

## 下一步（Sprint 8）

§2.2 ThemeResolver（解析 `xl/theme/theme1.xml` clrScheme 12 色 + tint/shade 演算法 + indexed 56 色 palette
→ 把 ResolvedStyle 內的 theme/indexed color 轉具體 RGB）。完成後 ResolvedStyle 即為完全具體的樣式，
可接 Phase 4.5 餵 o-spreadsheet 或 Phase 4 VR 像素比對。
