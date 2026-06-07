# Sprint 10 — ConcreteStyleResolver（對接層前置）

**日期**：2026-06-07
**Phase**：4.5（產品化）對接層前置
**對齊**：規劃書 §結論「parser → ast → style compiler → XlsxModelBridge → o-spreadsheet model commands」

---

## Root cause（開工前假設）

§2.1 StyleResolver 攤平出 ResolvedStyle，但 font.color / fill / border 仍是抽象 `Color`；
§2.2 ThemeResolver 能把單一 Color → RGB。但兩者尚未組合——要餵 o-spreadsheet 或做 VR 像素比對，
需要「一個 cell → 一個所有色都具體的樣式物件」。本 sprint 補這個對接層。

## 修法（實際做的事）

### `concrete_style.ts`
- `ConcreteStyleResolver(styles, theme).resolve(styleIndex)` → `ConcreteStyle`（含快取）：
  內部組合 StyleResolver + ThemeResolver，把 ResolvedStyle 的每個 Color → 6-hex（或 undefined = 系統/auto）
- 型別：`ConcreteFont` / `ConcreteFill` / `ConcreteBorder`（color 欄位皆 `string`，非 `Color`）
- `fillBackgroundColor(fill)`：取可見底色（solid → fgColor 才是顯示色、none → undefined、其他 pattern → bgColor）
- undefined 色不寫入物件（保持乾淨，渲染層自行補黑/白）

## 三層 SOP 結果

- **L1 vitest**：**491 passed**（unit 160 + integration 331）
  - `concrete_style.test.ts`（7）：合成 cellXf 走完整鏈
    - 日期 numFmt176 / 紅字粗體（ARGB FFFF0000 → FF0000）/
      **fill theme7(accent4) + tint0.8 = FFF2CC（端到端具體色）** /
      border thin（auto → undefined、FF000000 → 000000）/ fillBackgroundColor solid→fgColor / 快取
    - 真實契約詳細表：每 cellXf 解出色彩皆合法 6-hex 或 undefined
  - `concrete_style_corpus.test.ts`（48）：**全 48 fixture** 取首 sheet 實際 cell.styleIndex 走
    cell → ConcreteStyle，所有 font/fill/border 色為合法 6-hex 或 undefined、numFmtId 整數、不丟錯
- **L2 visual regression**：N/A（VR pipeline 待 Phase 4 接入；本層產出即為 VR 的輸入）
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（13s）

## 完整樣式鏈（本 sprint 收口）

```
cell.s（styleIndex）
  → StyleResolver.resolve（§2.1 xf cascade：cellXf + cellStyleXf + applyX 旗標）
    → ResolvedStyle（font/fill/border 為抽象 Color + numFmt + isDate）
      → ThemeResolver.resolveColor（§2.2 theme/indexed/tint → RGB）
        → ConcreteStyle（font/fill/border 全具體 6-hex）   ← 本 sprint
```

端到端驗證：`theme7 + tint0.8 → FFF2CC` 穿過整條鏈正確，與 Excel「Gold, Lighter 80%」一致。

## 對齊進度

| 層 | 狀態 |
|---|---|
| cell value 提取（§1.6 + §2.3） | 🟢 99.998% |
| 樣式 cascade（§2.1） | 🟢 |
| 色彩具體化（§2.2） | 🟢 |
| **ConcreteStyle 對接層** | 🟢 本 sprint |
| o-spreadsheet command 發射（Phase 4.5 本體） | ⚪ 待續 |
| VR 像素比對（Phase 4） | ⚪ 待續 |

→ cell value + ConcreteStyle 皆就緒，具備餵 o-spreadsheet model commands（setCellContent + updateCellFormat）
或 VR pipeline 的完整輸入。

## 負面結果 / 待解（紀律 #4）

1. **無像素級驗證**：ConcreteStyle 正確性以 FFF2CC 對標 Excel 間接驗證；真正像素比對需 Phase 4 VR
   pipeline（o-spreadsheet 渲染 → pixelmatch vs golden PNG）。
2. **gradient fill / 複雜 pattern 未涵蓋**：fillBackgroundColor 對 solid/none 正確、其他 pattern 回 bgColor
   為近似（圖樣繪製待 Phase 4）。
3. **alignment 原樣傳遞**：未轉成 o-spreadsheet 的 align 枚舉（Phase 4.5 command 發射時再 map）。

## 下一步（Sprint 11）

可選：
- **Phase 4.5 本體**：ConcreteStyle + cell value → o-spreadsheet model commands（XlsxModelBridge）
- **§1.8 DataValidations** / **§1.11 Tables**（補完 Phase 1 廣度）
- **Phase 4 VR pipeline**：接 o-spreadsheet headless 渲染 → pixelmatch vs golden PNG（真正像素驗證）
