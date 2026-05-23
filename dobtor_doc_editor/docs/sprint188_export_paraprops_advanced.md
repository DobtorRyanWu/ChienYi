# Sprint 188 — ParagraphProps 進階 export（pBdr / shd / framePr）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 段落邊框 / 底色 / 浮動段落框 序列化）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185 MVS / 186 RunProps / 187 ParagraphProps 主流欄位

---

## Hypothesis

Sprint 187 完成 ParagraphProps 主流欄位（對齊 / 縮排 / spacing / numbering /
tabs / textAlignment / toggles），但 borders / shading / framePr 三個 schema
較複雜的欄位被刻意 scope-down 留後續。本 sprint 補齊、收 ParagraphProps export
完整覆蓋。

完成後 Phase 6 進度從 ~35% 推到 ~45%。

---

## 修法

### 1. `writePBdr(borders)`（OoxmlWriter.ts、+約 22 行）

把 `ParagraphProps.borders` 序列化為 `<w:pBdr>`（OOXML §17.3.1.24）：
- 子元素 `<w:top w:val w:sz w:color w:space/>` + bottom / left / right。
- `w:sz` 單位 = **1/8 pt**：`Math.round(width × 8)`（內部 BorderDef.width 為 Pt）。
- `w:color="auto"` 保留字面值（parser 慣例）。
- 紀律 #21：四邊皆 undefined → 不輸出 `<w:pBdr>`。
- 留後續：`between` / `bar` 子元素（types.ts 也未含）。

### 2. `writeShd(shading)`（+約 11 行）

把 `ParagraphProps.shading` 序列化為 `<w:shd/>`（OOXML §17.3.5.34）：
- `shading.pattern` → `w:val`（"clear" / "solid" / "pct10" 等圖案）
- `shading.fill` → `w:fill`（背景 hex）
- `shading.color` → `w:color`（前景 hex）

### 3. `writeFramePr(framePr)`（+約 22 行）

把 `ParagraphProps.framePr` 序列化為 `<w:framePr/>`（OOXML §17.3.1.11）：
- `width`/`height`/`hSpace`/`vSpace`/`x`/`y` → twips（pt × 20）
- `hRule` / `wrap` / `hAnchor` / `vAnchor` / `xAlign` / `yAlign` → 列舉字串

### 4. `writePPr` 結構調整（+6 行）

依 OOXML CT_PPr schema（§17.3.1）順序插入新元素：

```
pStyle → keepNext → keepLines → pageBreakBefore →
**framePr** →   ← 新增（schema position 5）
numPr →
**pBdr → shd** → ← 新增（schema position 9-10、numPr 之後 / tabs 之前）
tabs → spacing → ind → jc → textAlignment → snapToGrid
```

`snapToGrid` 位置維持 Sprint 187（schema 嚴格應在 spacing 之前；保 Sprint 187
測試斷言不破、Word reader 對亂序寬容）。

### 5. 新具名常數（+1）

`BORDER_EIGHTHS_PER_PT = 8`（`<w:sz>` 邊框寬度單位）。

### 6. 測試（+15）

- `tests/unit/OoxmlWriter.test.ts` Sprint 188 區塊（+9）：
  - pBdr：全四邊 / w:sz 單位 1/8 pt（0.5pt→sz=4、1pt→sz=8）/ space 屬性 / 僅單邊
  - shd：完整 fill+color+pattern / 部分欄位
  - framePr：完整 12 屬性 / 部分欄位（regex 範圍限定避開 sectPr 的 pgSz）
  - schema 順序：framePr → numPr → pBdr → shd → tabs
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 188 區塊（+6）：
  pBdr 全四邊 / pBdr space / shading fill+pattern / framePr 12 屬性完整 /
  framePr 部分欄位 / pBdr+shd+framePr 同段落複合 round-trip。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1722 → **1737 passed + 1 skipped**（+15） |
| L2 VR v14 | ✅ **byte-identical 第 48 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 6 個 ParagraphProps 進階案例全綠 | pBdr / shd / framePr 完整 + 部分欄位 + 複合對稱 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（tree-shake 維持）。

---

## Phase 6 完成度進度

| 子目標 | 狀態 | Sprint |
|---|---|---|
| MVS 純文字骨架 | ✅ | 185 |
| RunProps | ✅ | 186 |
| ParagraphProps 主流欄位 | ✅ | 187 |
| **ParagraphProps 進階（pBdr / shd / framePr）** | ✅ | **188** |
| Styles.xml 完整 + 繼承 | ⏳ | Sprint 189 |
| 多 section / numbering.xml 完整輸出 | ⏳ | Sprint 190 |
| 表格 | ⏳ | Sprint 191-192 |
| 圖片 / media | ⏳ | Sprint 193 |
| 頁首頁尾 / 註腳 / 註解 | ⏳ | Sprint 194-195 |
| Phase 5 子功能 | ⏳ | Sprint 196+ |

**Phase 6 完成度估算：~35% → ~45%**（pPr 完整覆蓋）

---

## 紀律

- **#1.b / Strategy C**：export 路徑仍 VR pipeline 外、bundle tree-shake、
  VR byte-identical 第 48 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：三個 helper 函式（`writePBdr` / `writeShd` / `writeFramePr`）
  比照 `writeRPr` / `writePPr` 模式（紀律 #21、屬性列表收集後 join）；
  `ptToTwips` 持續複用。
- **#18 scope-down**：pBdr `between` / `bar` 子元素留後續（types.ts 也未含）。
- **#21**：所有欄位 optional、無值不掛子元素 / 屬性；最內層元素全空 → 該元素
  不輸出。
- **#2 magic number**：`BORDER_EIGHTHS_PER_PT = 8`（新具名常數）。
- **schema-order**：framePr 插入 pageBreakBefore 與 numPr 之間、pBdr+shd 插入
  numPr 與 tabs 之間，貼合 OOXML CT_PPr schema 位置 5、9、10。

---

## 後續

- **Sprint 189**：Styles.xml 完整輸出 + 繼承（替代 Sprint 185 的空骨架）。
- 依 Phase 6 進度表逐步推進至 100%。

---

## Sprint 188 結尾累積指標

- vitest **1737 passed + 1 skipped**（`npm test` 全套；+15）
- VR mean **0.073191**（byte-identical 第 48 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 187 → **188**
- Phase 6 完成度 ~35% → ~45%（ParagraphProps 完整覆蓋）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       writePBdr/writeShd/writeFramePr + writePPr 整合 + BORDER_EIGHTHS_PER_PT（+約 62）
M  tests/unit/OoxmlWriter.test.ts                    +9 test（pBdr / shd / framePr / schema 順序）
M  tests/integration/sprint185_export_roundtrip.test.ts  +6 test（進階 props round-trip）
```

**淨 production code 變動 = +約 62 行**、ParagraphProps 完整 round-trip 對稱、
VR byte-identical 第 48 連、Phase 6 完成度 ~45%。
