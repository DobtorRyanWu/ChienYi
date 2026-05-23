# Sprint 192 — 圖片 / media export（Phase 6 docx export 擴充）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 InlineImageNode / FloatImageNode + media 部件序列化、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-191（MVS + 樣式 + 表格 + 多 section + numbering）

---

## Hypothesis

Sprint 191 完成多 section + numbering。本 sprint 補圖片 export（InlineImageNode
+ FloatImageNode、含 media 部件、Content_Types + rels 自動擴充），把 Phase 6
推到 ~95%（剩頁首頁尾 + Phase 5 子功能 export 兩塊）。

---

## 修法

### 1. 4 個新命名空間常數（+5 行）

`WP_NS` / `A_NS` / `PIC_NS` / `R_NS` / `A_GRAPHIC_PICTURE_URI`、含
DrawingML 完整命名空間集（紀律 #2）。

### 2. EMU 單位常數 + 工具（+5 行）

`EMU_PER_PT = 12700`（1 inch = 914400 EMU = 72 pt → 1 pt = 12700 EMU）。
`ptToEmu(pt) = Math.round(pt × 12700)`。

### 3. `MediaItem` 型別 + `collectMedia()`（+約 35 行）

把 `DocumentNode.media`（Map<rId, base64 data URL>）轉為 MediaItem[]：
- `parseDataUrl(dataUrl)`：解析 `data:<mime>;base64,<bytes>`、回 mime + bytes
- 非 image/* mime（如 text/plain）→ 跳過
- 檔名用序號流水：`word/media/imageN.<ext>` 避免 rId 字串衝突
- `extensionForMime`：'image/png' → 'png'、'image/x-emf' → 'emf'、'image/svg+xml' → 'svg'
- `base64ToBytes(b64)`：Node Buffer / 瀏覽器 atob 雙路徑

### 4. `writeContentTypes(imageExtensions)` 擴展（+8 行）

依 doc 內出現的圖片副檔名集合新增 `<Default>` entries：
- `<Default Extension="png" ContentType="image/png"/>`
- `<Default Extension="jpeg" ContentType="image/jpeg"/>` 等
- `mimeForExtension(ext)` mapping：含常見 9 種 + fallback `image/${ext}`

### 5. `writeDocumentRels(mediaItems)` 擴展（+10 行）

- styles/numbering rels 改用**具名 Id**（rIdStyles / rIdNumbering）以避免與
  image rIds 的數字命名空間衝突（image rIds 從 doc.media 原樣帶入、可能是
  "rId1" 等與 numeric rels 衝突）
- 每個 MediaItem 加 image rel：`<Relationship Id="${rId}" Type="...image" Target="media/imageN.ext"/>`

### 6. `writeInlineImageRun(img)`（+約 25 行）

把 InlineImageNode / FloatImageNode 序列化為 `<w:r><w:drawing><wp:inline>`
完整結構：
- `<wp:extent cx cy>` — width × 12700 / height × 12700 EMU
- `<wp:docPr id name descr?>` — docPr id 序號（由 `nextDocPrId` 計數）+ altText
- `<wp:cNvGraphicFramePr/>`
- `<a:graphic>` → `<a:graphicData uri="...picture">`
- `<pic:pic>` → `<pic:nvPicPr>` + `<pic:blipFill><a:blip r:embed="rId">` + `<a:stretch>` + `<pic:spPr>`（xfrm + prstGeom rect）

FloatImageNode 降級為 inline（與 ToCanvasEditor 一致：production pipeline 已
把浮動圖片視為 inline）。posH / posV / wrap / srcRect lossy、留後續 optional sprint。

### 7. `writeParagraph` 整合（+4 行）

`para.runs` 迴圈加 `inlineImage` / `floatImage` 分支、呼叫 `writeInlineImageRun`。

### 8. `nextDocPrId()` 模組級計數器（+5 行）

`_docPrCounter` 模組變數 + `resetDocPrCounter()` + `nextDocPrId()`。
`OoxmlWriter.write()` 開頭重置、確保多次 write 不會累加計數器。

### 9. `OoxmlWriter.write()` 重構（+10 行）

- 開頭 `resetDocPrCounter()`
- 收集 `mediaItems = collectMedia(doc.media)`
- 算出 `imageExtensions = new Set(mediaItems.map((m) => m.ext))`
- 傳入 `writeContentTypes(imageExtensions)` / `writeDocumentRels(mediaItems)`
- `parts` 字典加每個 MediaItem 的 bytes：`parts[m.target] = m.bytes`

### 10. 既有測試升級（Sprint 185 MVS）

「非 run 的 InlineNode（image / break / field）→ MVS 跳過」改為
「Sprint 192：image 升級為輸出 `<w:drawing>`，break/field 仍跳過」。

### 11. 測試（+17）

- `tests/unit/OoxmlWriter.test.ts` Sprint 192 區塊（+12）：
  - 無 media → 仍 6 part（無 media 檔加入）
  - 單張 PNG → `word/media/image1.png` 寫入 zip + PNG 簽名驗證（89 50 4E 47）
  - Content_Types 含 image 副檔名 Default（png）
  - 多種 mime → 各自 Default + 各自檔名（image1.png / image2.jpeg）
  - document.xml.rels 含 image rel + styles/numbering 改用具名 Id
  - 非 image/* 的 data URL（text/plain）→ 跳過
  - InlineImageNode → `<w:drawing>` + r:embed
  - extent cx/cy 換 EMU（100pt × 12700 = 1270000）
  - altText → wp:docPr descr 屬性
  - 多張圖片 → docPr id 遞增
  - FloatImageNode → 降級為 inline
  - 多次 write → docPr 計數器重置
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 192 區塊（+5）：
  - 單張內嵌圖片 round-trip（width/height/rId 還原）
  - 圖片 bytes 在 round-trip 後保留（PNG 簽名 + base64 字串相等）
  - altText round-trip
  - 多張圖片各自 rId 還原（媒體 Map size + 內容）
  - **FloatImageNode 降級為 inline 後 round-trip → 還原為 inlineImage**（lossy 降級驗證）

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1800 → **1817 passed + 1 skipped**（+17） |
| L2 VR v14 | ✅ **byte-identical 第 52 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 5 個圖片案例（含 bytes-level、altText、FloatImage 降級） | 端到端對稱 |

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
| 表格 | ✅ | 190 |
| 多 section + numbering.xml | ✅ | 191 |
| **圖片 / media + Content_Types/rels 自動擴充** | ✅ | **192** |
| 頁首頁尾 / 註腳 / 註解 | ⏳ | Sprint 193-194 |
| Phase 5 子功能（OMML / SmartArt / Chart / 浮水印 / 追蹤修訂） | ⏳ | Sprint 195+ |

**Phase 6 完成度估算：~85% → ~95%**

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 52 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：`base64ToBytes` 對稱於 OoxmlParser 的 `toBase64`（Node Buffer
  / 瀏覽器 atob 雙路徑模式相同）；`escapeXml` / `ptToEmu` 與既有 `ptToTwips` /
  `ptToHalfPoints` 風格統一。
- **#18 scope-down**：FloatImageNode 降級為 inline（與 ToCanvasEditor 一致）；
  posH / posV / wrap / srcRect 留後續 optional；headerRefs/footerRefs 的圖片
  也透過 doc.media 共用同 collectMedia 路徑。
- **#21**：無 media → 不輸出 media/* 部件、不加 image Defaults、不加 image rels。
- **#2 magic number**：5 個新常數（EMU_PER_PT / WP_NS / A_NS / PIC_NS / R_NS /
  A_GRAPHIC_PICTURE_URI / REL_TYPE_IMAGE）。
- **正確性**：
  - styles/numbering rels 改用具名 Id（rIdStyles / rIdNumbering）避免與 image
    rIds 數字命名空間衝突
  - 多次 write 重置 docPr 計數器
  - PNG signature 驗證 zip 內 bytes 確實是有效 PNG

---

## 後續

- **Sprint 193**：頁首頁尾 export。需要：
  - header*.xml / footer*.xml 部件寫入
  - sectPr 內 `<w:headerReference r:id>` / `<w:footerReference r:id>` 引用
  - rels 條目加 header/footer 關係
  - 內容 reuse writeParagraph / writeTable / writeBlock dispatcher
- 依 Phase 6 進度表逐步推進至 100%。

---

## Sprint 192 結尾累積指標

- vitest **1817 passed + 1 skipped**（`npm test` 全套；+17）
- VR mean **0.073191**（byte-identical 第 52 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 191 → **192**
- Phase 6 完成度 ~85% → ~95%（圖片 + media 完整覆蓋）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       collectMedia + writeInlineImageRun + Content_Types/rels 擴充（+約 130）
M  tests/unit/OoxmlWriter.test.ts                    +12 test + 1 既有測試升級（image 不再跳過）
M  tests/integration/sprint185_export_roundtrip.test.ts  +5 test（含 bytes-level + FloatImage 降級）
```

**淨 production code 變動 = +約 130 行**、圖片 round-trip 對稱（含 bytes 保留）、
VR byte-identical 第 52 連、Phase 6 完成度 ~95%。
