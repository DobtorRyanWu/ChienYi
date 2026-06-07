# Sprint 13 — Number Format 完整渲染（§2.3）

**日期**：2026-06-07
**Phase**：2/3（§2.3 number format 渲染，§2.3 最小版日期後續）
**對齊**：規劃書 §2.3 NumberFormatCompiler；Sprint 12 指出 number format 為 VR 收斂候選

---

## Root cause（開工前假設）

Sprint 6 只做日期序號 → 日期字串；數字（千分位/貨幣/百分比）在 render 仍顯示原始值
（1234.5 而非 "1,234.50"）。要對齊 golden 顯示，需把 formatCode 套到數值。

**關鍵約束（紀律 #2）**：cell value 提取率（99.998%）比對 calamine 的**原始數字**。若把 number format
套進 `buildValueMapStyled`，提取率會破裂（calamine=1234.5、ours="1,234.50"）。
→ number format **只能用於視覺渲染**，獨立模組、只接 html_render，不動提取路徑。

## 修法（實際做的事）

### `number_formatter.ts`
- `formatNumber(value, code)` → 顯示字串。tokenizer 處理：
  - `# 0 ?`（數字佔位）、`,`（千分位）、`.`（小數）— 整數補零（min 由 `0` 數）、小數固定位、四捨五入
  - `%`（×100）、`"字面"` / `\跳脫` / `[$NT$-404]`（取貨幣符號）/ `_寬度`（→空白）/ `*填充`（跳過）
  - **多段** `正;負;零;文字`（依符號選段、負數段自帶括號為字面、單段負數補 `-`）
  - `General` / 空 → 原樣
- 接入 `vr/html_render.ts`：cell 為數字 + numFmtCode 非 General → formatNumber；其餘原樣（日期已是字串）

## 三層 SOP 結果

- **L1 vitest**：**518 passed**（unit 187 + integration 331）
  - `number_formatter.test.ts`（13）：千分位/小數/補零/百分比/單段負號/**會計括號負數**/零段/General
    + **ChienYi 實碼**：`#,##0.00_ `（尾隨寬度空白）、`[$NT$-404]#,##0.00`（NT$）、
      `"第"\ #\ "次估驗附表"\ `（numFmt178 → "第 5 次估驗附表 "）
- **L2 VR baseline**（套 number format 後）：
  | fixture | Sprint 12 content | Sprint 13 content |
  |---|---|---|
  | 估驗差異表 11309 | 11.7% | 11.8% |
  | 變更金額分析 | 13.8% | 14.4% |
  | C-A土單 | 20.4% | 20.4% |
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（14.4s）

## 誠實結論（紀律 #4）

**number format 渲染正確（13 測試證明），但 VR content diff 幾乎不動**——原因：
- 這 3 個樣本是**文字密集**營造文書（估驗差異說明、狀態碼土單），數字格化的 cell 少、
  且 VR 差異由**字型/欄寬 metrics 主導**，非數字顯示
- content 微幅波動（11.7→11.8、13.8→14.4）為 render 文字變動 + 最近鄰縮放取樣噪音，非退步

→ 本 sprint 是**正確性投資**（o-spreadsheet 餵入 / 數字密集表如估驗計價表、契約詳細表會顯著受益），
非 VR 指標投資。**VR 收斂的真正下一槓桿是字型保真**（瀏覽器 fallback → LibreOffice 同款 CJK 字型 + 欄寬精算）。

## 對齊進度

| 項目 | 狀態 |
|---|---|
| 日期序號 → 字串（§2.3 最小） | 🟢（Sprint 6） |
| number format 渲染（千分位/貨幣/%） | 🟢 本 sprint |
| 日期 format code 渲染（民國年/mm-dd-yy 等顯示） | ⚪ 待續（目前統一 ISO） |
| 字型保真（VR 下一槓桿） | ⚪ Sprint 14 候選 |

## 負面結果 / 待解

1. **VR 未降**：見上；非 bug，是樣本特性 + 字型主導。
2. **分數 `?/?` / 科學記號 `E+` 未實作**：ChienYi 未見，最小版略過。
3. **日期 format code 未渲染**：日期統一 ISO，未依 `gge"年"`（民國年）等顯示 → 與 golden 日期 cell 仍有差異，
   待日期 format 渲染補。

## 下一步（Sprint 14）

VR 收斂最高槓桿 = **字型保真**：
- html_render 換 `font-family` 為 LibreOffice 實際渲染字型（新細明體/標楷體 → 容器內同款 CJK 字型）
- 欄寬/列高用 LibreOffice 量測校準（目前用 Excel col width px 公式，與 LibreOffice 有偏差）
- 或轉 **o-spreadsheet headless render**（用目標引擎本身渲染、根本對齊）
