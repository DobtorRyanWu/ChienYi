# Sprint 191 — 多 section + numbering.xml export（Phase 6 擴充）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 多 section + numbering part 序列化、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-190（MVS / RunProps / ParagraphProps / Styles.xml / 表格）

---

## Hypothesis

Sprint 190 完成表格 export。本 sprint 補兩個 Phase 6 仍缺的關鍵：

1. **多 section export** — 原 MVS 把所有 section 的 blocks concat 成單列、
   只在 body 末端輸出最後一個 sectPr（多 section 退化為單）。本 sprint
   正確支援多 section：中間 section 用 anchor paragraph 嵌入 sectPr。

2. **numbering.xml export** — 原 MVS 完全不輸出 numbering.xml；本 sprint
   補完整輸出 DocumentNode.numbering（含 abstractNum + num + lvls）。

完成後 Phase 6 進度從 ~75% 推到 ~85%。

---

## 修法

### 1. 多 section export（writeDocument 重構、+約 15 行）

OOXML §17.6 多 section 結構：
- 中間 section：在 section 最後段落的 `pPr` 內嵌入 `<w:sectPr>`、結束該 section
- 最後 section：body 末端的 `<w:sectPr>`

實作策略：**對每個非最後 section、緊接其 blocks 後追加 anchor paragraph**：

```
<w:p><w:pPr><w:sectPr>...</w:sectPr></w:pPr></w:p>
```

優點：
- 不依賴 section 最後一個 block 是 paragraph 還是 table（table 結尾的 section
  靠 anchor 段落正確收尾）
- parser walkBodyAsSections 支援兩種 sectPr 位置（段內 pPr / body 末端）、
  re-parse 正確切分為 N section

### 2. numbering.xml 新增（+約 60 行）

#### 對稱性設計

Parser 把 `<w:num numId> → <w:abstractNumId> → <w:abstractNum>` 三層關係
resolve 後、每個 numId 在 NumberingMap 內存一份完整 levels 副本。

**Export 策略**：**用 numId 直接當 abstractNumId**（保證唯一、避免「多個
numId 共用 abstractNumId 但 levels 不同」場景在 re-parse 時被 Map 覆蓋）。
`entry.abstractNumId` 欄位於 round-trip 後變為 numId（acceptable lossy；
parser 不靠此值來解析 levels、levels 才是 functional payload）。

#### 結構

```xml
<w:numbering>
  <w:abstractNum w:abstractNumId="{numId}">
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1."/>
      <w:lvlRestart w:val="0"/>?         <!-- 如有 -->
      <w:isLgl/>?                         <!-- 如有 -->
      <w:pPr>...</w:pPr>?                 <!-- 含 indent 合併 -->
      <w:rPr>...</w:rPr>?                 <!-- 如有 runProps -->
    </w:lvl>
    ...
  </w:abstractNum>
  <w:num w:numId="{numId}">
    <w:abstractNumId w:val="{numId}"/>
  </w:num>
  ...
</w:numbering>
```

關鍵實作細節：
- **indent 合併到 pPr**：parser `parseLvl` 把 `<w:pPr><w:ind>` 的 left / hanging
  抽出為獨立 `level.indent` 欄位（firstLine / right 留在 `level.pProps.indent`）；
  export 時需把兩者 merge 回 pProps 再呼叫 `writePPr`。
- **複用 writePPr / writeRPr**：紀律 #14 DRY。
- 空 NumberingMap → 空 `<w:numbering/>` 骨架（向下相容 Sprint 185 行為）。

### 3. 5 → 6 必要 part

加 `word/numbering.xml`：
- `[Content_Types].xml` 加 numbering override
- `word/_rels/document.xml.rels` 加 numbering 關係（rId2）
- 永遠 emit（即使空 map）—— 比條件式 emit 更簡單可預測

### 4. 新常數（+1）

`REL_TYPE_NUMBERING`（紀律 #2）。

### 5. 測試（+20）

- `tests/unit/OoxmlWriter.test.ts` Sprint 191 區塊（+10）：
  - 多 section anchor paragraph 結構（3 section → 3 個 sectPr + 2 個 anchor）
  - 單 section 仍只有 body 尾 sectPr（無 anchor）
  - 空 numbering map → self-closing
  - Content_Types + rels 含 numbering
  - 單一 entry：abstractNum + num + lvl 結構
  - 多 levels（ilvl 0/1/2、不同 numFmt）
  - lvlRestart / isLegal toggle
  - indent 合併進 pPr（驗證 twips 換算）
  - level runProps
  - 多 entry 各自 abstractNum + num

- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 191 區塊（+10）：
  - 3 個 section round-trip → sections.length=3、各自段落保留
  - 多 section 各自 page 屬性 round-trip（直/橫式）
  - 空 numbering map round-trip
  - 單一 numbering entry round-trip（start/numFmt/lvlText/abstractNumId=numId）
  - 多 levels round-trip
  - lvlRestart / isLegal round-trip
  - indent round-trip
  - runProps round-trip
  - 多 numId entry round-trip
  - **paragraph 引用 numId+ilvl + 對應 numbering 端到端 round-trip**

### 6. Sprint 185 / 190 既有測試升級

- `'空文件 → zip 含 ... 5 part'` → 6 part（含 numbering.xml）
- `'多 section → MVS 退化為單'` → 「中間 anchor + 末 body 尾」
- 整合測試 `'round-trip 後仍只有 1 section'` → 「2 個 section、anchor 拆分還原」

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1780 → **1800 passed + 1 skipped**（+20） |
| L2 VR v14 | ✅ **byte-identical 第 51 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 10 個案例（含端到端 paragraph 引用 numId+ilvl） | 多 section + numbering 完整對稱 |

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
| Styles.xml 完整輸出 | ✅ | 189 |
| 表格（tblPr / tblGrid / trPr / tcPr / gridSpan / vMerge / 巢狀） | ✅ | 190 |
| **多 section + numbering.xml** | ✅ | **191** |
| 圖片 / media | ⏳ | Sprint 192 |
| 頁首頁尾 / 註腳 / 註解 | ⏳ | Sprint 193-194 |
| Phase 5 子功能（OMML / SmartArt / Chart / 浮水印 / 追蹤修訂） | ⏳ | Sprint 195+ |

**Phase 6 完成度估算：~75% → ~85%**

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 51 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：numbering writer 複用 `writePPr` / `writeRPr` / `escapeXml`；
  numbering 對稱性策略與 Sprint 189 styles.xml 同（parser flatten + flat-equivalent
  輸出）。
- **#18 scope-down**：多 section anchor paragraph 採「永遠補 anchor」策略
  （unambiguous）而非「last paragraph reuse」；複雜的「reuse 最後段 pPr」最佳化
  留後續、目前 anchor 寫法已 round-trip 正確。
- **#21**：空 NumberingMap → self-closing；level 各欄位 optional 不掛則跳過；
  lvlRestart / isLegal / runProps / indent 缺漏不輸出對應子元素。
- **#2 magic number**：`REL_TYPE_NUMBERING` 新常數。

---

## 後續

- **Sprint 192**：圖片 / media export。需要：
  - 媒體 part 寫入 zip（`word/media/imageN.png` 等）
  - document.xml 內 `<w:drawing><wp:inline><a:blip r:embed="rId">` 序列化
  - rels + Content_Types 對應
- 依 Phase 6 進度表逐步推進至 100%。

---

## Sprint 191 結尾累積指標

- vitest **1800 passed + 1 skipped**（`npm test` 全套；+20）
- VR mean **0.073191**（byte-identical 第 51 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 190 → **191**
- Phase 6 完成度 ~75% → ~85%（多 section + numbering 補完）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       writeDocument 多 section 重構 + writeNumbering + writeAbstractNum + writeLvl（+約 90）
M  tests/unit/OoxmlWriter.test.ts                    +10 test + 2 既有測試升級（6-part / 多 section anchor）
M  tests/integration/sprint185_export_roundtrip.test.ts  +10 test + 1 既有測試升級（多 section 還原）
```

**淨 production code 變動 = +約 90 行**、多 section + numbering round-trip 對稱、
VR byte-identical 第 51 連、Phase 6 完成度 ~85%。
