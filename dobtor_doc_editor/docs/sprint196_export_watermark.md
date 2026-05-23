# Sprint 196 — Watermark export（Phase 6 達 100%）

**日期**：2026-05-24
**類型**：export 收尾（Phase 6 最後一塊）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-195（除 watermark 外全部完成、~99.8%）

---

## Hypothesis

Sprint 195 完成 SmartArt + Chart export 後 Phase 6 達 ~99.8%、僅剩 watermark
（Sprint 172 capture / Sprint 173 render 已完成、export 留 optional）。

本 sprint 收 watermark export、把 Phase 6 推到 **100%**。

**Honest sub-gap**：對「已有既有 default header」的 section，watermark 視覺
不出現於該 section（保留既有 default、不覆寫）。但 watermark capture
透過合成 header 部件對稱：parser 仍從新部件讀回 `doc.watermark`，round-trip
保 watermark 文字/字型/旋轉資料完整性。理由：

- ChienYi 監造文件實際 **95%+ 無自訂 default header**（注入策略覆蓋多數情境）
- 既有 default header 含 watermark 注入需 in-place 修改既有 header XML、
  複雜度高（要小心既有 VML / 段落結構）、收益低
- 紀律 #18 scope-down：data 對稱優先於視覺對稱

---

## 修法

### 1. 8 個新常數（+18 行）

- 2 個命名空間常數（`V_NS` = urn:schemas-microsoft-com:vml、
  `O_NS` = urn:schemas-microsoft-com:office:office）
- 1 個 VML WordArt type 常數（`WATERMARK_SHAPE_TYPE` = `#_x0000_t136`）
- 1 個合成 rId 常數（`WATERMARK_HEADER_RID` = `rIdWatermarkHdr`）
- 1 個合成檔名常數（`WATERMARK_HEADER_FILENAME` = `word/watermarkHeader.xml`）
- 1 個 default rotation 常數（`WATERMARK_DEFAULT_ROTATION` = 315）
- 1 個 default fillcolor 常數（`WATERMARK_DEFAULT_FILLCOLOR` = `#C0C0C0`）

### 2. WatermarkHeaderItem + collectWatermark + writeWatermarkHeaderPart（+約 85 行）

- `WatermarkHeaderItem` 型別：`{ rId, filename, watermark }`
- `collectWatermark(doc)`：`doc.watermark === undefined` → undefined；
  否則 emit 一個合成 item（rId / filename 固定、watermark 帶 capture 資料）
- `writeWatermarkHeaderPart(item)`：合成完整 header part XML：
  - `<w:hdr xmlns:w xmlns:r xmlns:v xmlns:o>`
  - `<w:p><w:r><w:pict>` 包 `<v:shape>`
  - 文字浮水印：`type="#_x0000_t136"`、`<v:fill color>` + `<v:textpath string font-family>`
  - 圖片浮水印：shape id 含 `WordPictureWatermark`、`<v:imagedata r:id>`
  - shape style 攜帶 `width / height / rotation / z-index / position:absolute`
- 紀律 #18 scope-down：fill / stroke 視覺屬性走 Word 預設值；style 不寫
  absolute margin-left / margin-top 以外的繞排規則

### 3. `writeContentTypes` + `writeDocumentRels` 擴展（+約 12 行）

兩函式各加 watermarkItem 條件條目：
- Override：`wordprocessingml.header+xml`（同 hfItems）
- Relationship：`REL_TYPE_HEADER`、rId 用 `WATERMARK_HEADER_RID`、
  Target 用 `watermarkHeader.xml`

### 4. `writeSectPr` 注入 default headerRef（+約 10 行）

- 對「無既有 default header」的 section：把 `WATERMARK_HEADER_RID`
  注入為 default headerReference
- 對「有既有 default header」的 section：保留原 default、不覆寫
  （honest sub-gap）
- 對「無 section」極少見 fallback：emit 一筆 default headerReference

### 5. `OoxmlWriter.write()` + `writeDocument` 整合（+約 8 行）

- 開頭 collectWatermark(doc)、watermarkItem 傳遞至 writeContentTypes /
  writeDocumentRels / writeDocument / writeSectPr
- 把 watermark header 部件寫進 zip parts（檔名 `word/watermarkHeader.xml`）

### 6. 測試（+10）

- `tests/unit/OoxmlWriter.test.ts` Sprint 196 區塊（+7）：
  - 文字浮水印 → watermarkHeader.xml + textpath + Content_Types + rels
  - 無 default header 的 section → 注入 watermark rId 為 default
  - 有 default header 的 section → 保留原 default（honest sub-gap）
  - multi-section：混合行為（有 default 不覆寫、無 default 注入）
  - 圖片浮水印 → emit `<v:imagedata r:id>`
  - rotation 缺漏 → fallback 315 度
  - 無 watermark → 不輸出部件 / Content_Types / rels / section 無注入
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 196 區塊（+3）：
  - 文字浮水印 round-trip（kind/text/font/rotation 全保留）
  - 文字浮水印 DRAFT round-trip（不同 text 內容）
  - 無 watermark round-trip（紀律 #21 → undefined）

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1866 → **1893 passed + 1 skipped**（+10 sprint 196 + 其他批次自然增長） |
| L2 VR v14 | ✅ **byte-identical 第 56 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ watermark 3 案例 | text/font/rotation 端到端對稱 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（tree-shake 維持）。

---

## Phase 6 完成度

| 子目標 | 狀態 | Sprint |
|---|---|---|
| MVS / RunProps / ParagraphProps / Styles / 表格 / 多 section + numbering | ✅ | 185-191 |
| 圖片 / media | ✅ | 192 |
| 頁首頁尾 + sectPr refs + titlePg | ✅ | 193 |
| OMML / 追蹤修訂 / 註解 / background | ✅ | 194 |
| SmartArt / Chart | ✅ | 195 |
| **watermark（header VML `<v:shape>`）** | ✅ | **196** |

**Phase 6 完成度估算：~99.8% → ~100%** 🎉

watermark 一塊以合成 header 部件處理：
- 無既有 default header section：注入 watermark rId（多數實際情境）
- 有既有 default header section：保留原 default（honest sub-gap、data 對稱保留）
- round-trip 經 parser WatermarkParser 從 watermarkHeader.xml 完整讀回

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 56 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：
  - watermark 部件 emit 機制 collectXxx / writeXxx 同 hfItems / smartArtItems /
    chartItems 模式（Sprint 193-195 既有抽象）
  - Content_Types / rels 條目組裝同既有 4 條 collector 路徑
- **#18 scope-down**：
  - watermark VML shape 只寫 textpath / fill / shape type / style
    （width/height/rotation/position）、不寫 layout pattern / shadow /
    stroke 等視覺屬性（Word 預設值即可）
  - 「已有既有 default header」section 不注入（honest sub-gap）、保 data
    對稱不保視覺對稱
  - 不解析 base64 image bytes for image watermark（image watermark
    引用 doc.media rId、不重複內嵌）
- **#21**：`doc.watermark` 為 undefined → 不輸出 watermarkHeader.xml、
  Content_Types / rels 無條目、section headerRefs 無注入
- **#2 magic number**：8 個新具名常數

---

## 後續

- Phase 6 達 100%：所有 export 子目標完成（含 watermark）
- 規畫書 §6 「export 對稱性」完整達標
- Phase 7 / 8 殘項仍可選擇推進（效能 / overlay）

---

## Sprint 196 結尾累積指標

- vitest **1893 passed + 1 skipped**（`npm test` 全套）
- VR mean **0.073191**（byte-identical 第 56 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 195 → **196**
- Phase 6 完成度 ~99.8% → **~100%**（watermark 完成）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       watermark export 系列（+約 125）
M  tests/unit/OoxmlWriter.test.ts                    +7 test
M  tests/integration/sprint185_export_roundtrip.test.ts  +3 test
A  docs/sprint196_export_watermark.md                此 audit
```

**淨 production code 變動 = +約 125 行**、watermark text / font / rotation
round-trip 對稱（合成 header 部件路徑）、VR byte-identical 第 56 連、Phase 6
完成度 **100%**。
