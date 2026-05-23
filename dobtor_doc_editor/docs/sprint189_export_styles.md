# Sprint 189 — Styles.xml 完整輸出 + 繼承（Phase 6 docx export 擴充）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 樣式 part 序列化、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-188（MVS / RunProps / ParagraphProps 完整）

---

## Hypothesis

Sprint 185 MVS 階段 `word/styles.xml` 是空骨架（`<w:styles/>`、parser 接受但
無內容）。本 sprint 補完整輸出：把 `DocumentNode.styles`（StyleMap）序列化
為一系列 `<w:style>` 元素、達成 styles part round-trip 對稱。

完成後 Phase 6 進度從 ~45% 推到 ~55%。

---

## 修法

### 對稱性設計（與 parser StyleResolver 對齊）

關鍵觀察：StyleResolver 在 parse 時把
**docDefaults → basedOn 鏈 → current props** 全部 **flatten** 進
`entry.pProps` / `entry.rProps`。意即：
- StyleMap 內的 entry 已是「展開後」的最終 props。
- export 端**不需要**輸出 `<w:docDefaults>` 或 `<w:basedOn>`。
- re-parse 時，resolver 看不到 docDefaults、看不到 basedOn → 直接把 entry 的
  props 當 flat result → round-trip 等價。

### 1. `writeStyles(doc)`（OoxmlWriter.ts、+約 30 行）

簽名改為接收 DocumentNode（原 MVS 為無參空骨架）：
- 空 StyleMap → 維持 `<w:styles/>` 自閉合骨架（向下相容 Sprint 185）。
- 非空 StyleMap → 對每個 entry 呼叫 `writeStyleEntry`，包進
  `<w:styles xmlns:w=...><w:style ...>...</w:style>...</w:styles>`。

### 2. `writeStyleEntry(styleId, entry)`（+約 12 行）

序列化單一 StyleEntry：
- 屬性：`w:type="paragraph" w:styleId="X"`（type 統一 paragraph、StyleEntry
  本身不保留 type；re-parse 時 type 不影響 pProps/rProps 解析結果）。
- 內容：**複用 Sprint 187/188 的 `writePPr` / `writeRPr`**（同一輸出邏輯、
  紀律 #14 DRY）。
- 空 body（pProps + rProps 皆無內容）→ `<w:style ... />` self-closing；
  保持 styleId 鍵的存在性以便 round-trip Map 大小一致。
- styleId 透過 `escapeXml` 跳脫（紀律：所有 attribute 值必跳脫）。

### 3. 留後續 sprint 的部分

紀律 #18 scope-down：
- `<w:docDefaults>` 顯式輸出（目前 flat 等價、未來若 export 端要 minimize
  styles.xml 體積時再做）。
- `<w:basedOn>` 顯式輸出（同上、目前不影響 round-trip 等價性）。
- `<w:name>`（顯示名稱）/ `<w:uiPriority>` / `<w:hidden>` 等 metadata
  （StyleEntry 不保留、無從輸出）。
- 表格條件樣式 `conditional`（`<w:tblStylePr>` 子元素、留 Sprint 190+ 表格相關）。

### 4. 測試（+15）

- `tests/unit/OoxmlWriter.test.ts` Sprint 189 區塊（+8）：
  - 空 styles map → `<w:styles/>` 骨架
  - 單一空 entry → `<w:style w:type="paragraph" w:styleId="X"/>` self-closing
  - entry pProps → `<w:pPr>` 內容（複用 writePPr）
  - entry rProps → `<w:rPr>` 內容（複用 writeRPr）
  - entry pProps + rProps 同時輸出（pPr 在 rPr 之前）
  - 多 entry 依 Map 順序輸出
  - styleId XML 特殊字元跳脫
  - 不輸出 docDefaults / basedOn（紀律 #14 對稱性驗證）
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 189 區塊（+7）：
  - 空 styles map round-trip
  - 單一空 entry round-trip（Map size = 1、key 存在）
  - entry pProps round-trip
  - entry rProps round-trip
  - entry pProps + rProps 同時 round-trip
  - 多 entry round-trip（Map size + 各鍵內容）
  - **paragraph 引用 styleId + 對應 style entry 連同 round-trip**（端到端 styling 場景）

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1737 → **1752 passed + 1 skipped**（+15） |
| L2 VR v14 | ✅ **byte-identical 第 49 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 7 個 styles 案例全綠 | 含端到端 paragraph 引用 styleId 場景 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（tree-shake 維持）。

---

## Phase 6 完成度進度

| 子目標 | 狀態 | Sprint |
|---|---|---|
| MVS 純文字骨架 | ✅ | 185 |
| RunProps | ✅ | 186 |
| ParagraphProps 主流欄位 | ✅ | 187 |
| ParagraphProps 進階（pBdr / shd / framePr） | ✅ | 188 |
| **Styles.xml 完整輸出 + 繼承（flat-equivalent）** | ✅ | **189** |
| 多 section / numbering.xml 完整輸出 | ⏳ | Sprint 190 |
| 表格 | ⏳ | Sprint 191-192 |
| 圖片 / media | ⏳ | Sprint 193 |
| 頁首頁尾 / 註腳 / 註解 | ⏳ | Sprint 194-195 |
| Phase 5 子功能 | ⏳ | Sprint 196+ |

**Phase 6 完成度估算：~45% → ~55%**（styles part 補完）

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 49 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：`writeStyleEntry` 直接複用 `writePPr` / `writeRPr`（兩者
  在 Sprint 187/188 已具備、無需重寫）；styles `xmlDecl` / `escapeXml` 工具
  持續複用。
- **#18 scope-down**：明確 defer `<w:docDefaults>` / `<w:basedOn>` / `<w:name>` /
  conditional table styles；對稱性透過「StyleResolver flatten + 等價輸出」達成、
  非「逐欄位 1:1 對稱輸出」。
- **#21**：空 StyleMap → 空 `<w:styles/>` self-closing；空 entry → 空 `<w:style/>`
  self-closing；保 styleId 鍵的存在性以 round-trip Map 大小一致。
- **對稱性策略**：明確記錄「flat-equivalent」設計理由（parser 已 flatten、
  export 不需重建 docDefaults+basedOn 鏈、re-parse 仍得等價 StyleMap）。

---

## 後續

- **Sprint 190**：多 section / numbering.xml 完整輸出（目前 numbering 也是
  空骨架；StyleMap 對稱性策略可移植到 NumberingMap）。
- 依 Phase 6 進度表逐步推進至 100%。

---

## Sprint 189 結尾累積指標

- vitest **1752 passed + 1 skipped**（`npm test` 全套；+15）
- VR mean **0.073191**（byte-identical 第 49 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 188 → **189**
- Phase 6 完成度 ~45% → ~55%（styles part 補完）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       writeStyles + writeStyleEntry（+約 42）
M  tests/unit/OoxmlWriter.test.ts                    +8 test
M  tests/integration/sprint185_export_roundtrip.test.ts  +7 test
```

**淨 production code 變動 = +約 42 行**、styles round-trip 對稱（flat-equivalent）、
VR byte-identical 第 49 連、Phase 6 完成度 ~55%。
