# Sprint 194 — Phase 5 子功能 export（Phase 6 收尾、~98% → ~99.5%）

**日期**：2026-05-23
**類型**：export 擴充（Phase 5 子功能 OOXML 序列化、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-193（文件流 + 樣式 + 表格 + 多 section + numbering + 圖片 + 頁首頁尾）

---

## Hypothesis

Sprint 193 完成頁首頁尾。剩 Phase 6 最後 ~2-3pp 為 Phase 5 子功能 export
（OMML / 追蹤修訂 / 註解 / background / watermark / SmartArt / Chart）。

**Sprint 194 scope**：拿下 5 個（OMML / 追蹤修訂 / 註解 / background / comments.xml）；
watermark + SmartArt/Chart 留 Sprint 195（複雜部件、需獨立子目錄 part）。

完成後 Phase 6 ~98% → ~99.5%。

---

## 修法

### 1. 2 個新常數（+2 行）

- `REL_TYPE_COMMENTS`（comments rel type、紀律 #2）
- `M_NS`（OMML 命名空間）

### 2. OMML export（+約 35 行）

複用 capture-only Sprint 179 的 `OmmlNode { tag, text?, attrs?, children? }`
資料結構：tag/attrs 統一去 `m:` 前綴存於 AST、export 端統一加回。

- `writeParagraphMath(math)` — `<m:oMath>` / `<m:oMathPara>`（display=true 包裹）
- `writeOmmlChildren(nodes)` / `writeOmmlNode(node)` — 遞迴序列化、紀律 #21
  無 children 無 text → self-closing
- `xmlns:m="..."` 在每個 `<m:oMath>` / `<m:oMathPara>` 自帶（簡化、不在 root 統一）

整合：`writeParagraph` 在 runs 之後輸出 math（無公式 → 紀律 #21 不輸出）。

### 3. 追蹤修訂 export（+約 18 行）

- `writeRun(run, useDelText = false)` — `<w:t>` / `<w:delText>` 切換（OOXML
  §17.13.5：del 包裹的 text 必為 `<w:delText>`）
- `writeRevisedRun(run)` — 把 run 包進 `<w:ins>` 或 `<w:del>`：
  - 屬性：`w:id`（缺漏 → 0）/`w:author`?/`w:date`?
  - del 變體：inner run 用 `useDelText=true`
- `writeParagraph` 對每個 run 檢查 `run.revision`、有則調 `writeRevisedRun`

### 4. 註解錨點 + comments.xml export（+約 35 行）

註解錨點（OOXML §17.13.5.4-5）：`para.commentRefs` 每個 id 在段落層級
emit 三個元素：
- `<w:commentRangeStart w:id>` — runs 之前
- `<w:commentRangeEnd w:id>` — runs 之後
- `<w:r><w:commentReference w:id></w:r>` — 段尾

comments.xml 部件（OOXML §17.13.4）：
- `writeComments(doc)` — 空 Map → 空 `<w:comments/>`；非空逐 entry 序列化
- `writeCommentEntry(c)` — `<w:comment w:id w:author? w:date? w:initials?>`
  含 BlockNode[] body（透過 writeBlock dispatcher reuse 段落 / 表格 / 巢狀）

Content_Types Override + rels（Id="rIdComments"）：
- 永遠 emit comments.xml（即使空 Map、簡單可預測、與 styles/numbering 同模式）
- 7 → 8 必要 part... 實作上 comments.xml 直接擠進固定 parts 字典

### 5. background export（+約 10 行）

`writeBackground(bg)` — `<w:background w:color="HEX"/>` 作為 `<w:document>`
直接子元素（`<w:body>` 之 sibling、schema 規定）。

`writeDocument` 在 `<w:document>` 開標籤後、`<w:body>` 之前插入。

紀律 #21：無 background 或無 color → 空字串。

### 6. Sprint 191 既有測試升級

「6 必要 part」測試斷言更新為「7 必要 part（含 comments.xml）」。

### 7. 測試（+21）

- `tests/unit/OoxmlWriter.test.ts` Sprint 194 區塊（+14）：
  - OMML inline / display / 分數結構 / attrs 寫回 / self-closing
  - 追蹤修訂 ins / del（含 delText） / id-author-date 缺漏處理
  - 註解：commentRangeStart-Reference-End 順序 / comments.xml 空骨架 / entries
  - Content_Types comments override + rels comments 關係
  - background 顏色 + 位置（在 body 之前）/ 無 background 不輸出
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 194 區塊（+7）：
  - OMML 行內 / display / 分數結構 round-trip
  - 追蹤修訂 ins / del round-trip
  - comments + commentRefs 端到端 round-trip
  - background 顏色 round-trip

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1834 → **1855 passed + 1 skipped**（+21） |
| L2 VR v14 | ✅ **byte-identical 第 54 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 7 個 Phase 5 案例 | OMML/ins/del/comments/commentRefs/background 端到端對稱 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（tree-shake 維持）。

---

## Phase 6 完成度進度

| 子目標 | 狀態 | Sprint |
|---|---|---|
| MVS / RunProps / ParagraphProps / Styles / 表格 / 多 section + numbering / 圖片+media / 頁首頁尾 | ✅ | 185-193 |
| **OMML 數學公式 (`<m:oMath>`)** | ✅ | **194** |
| **追蹤修訂 (`<w:ins>` / `<w:del>` / `<w:delText>`)** | ✅ | **194** |
| **註解錨點 + comments.xml** | ✅ | **194** |
| **background (`<w:background>`)** | ✅ | **194** |
| watermark（header VML `<v:shape>`） | ⏳ | Sprint 195 |
| SmartArt（`diagrams/dataN.xml`）/ Chart（`charts/chartN.xml`） | ⏳ | Sprint 195 |

**Phase 6 完成度估算：~98% → ~99.5%**（5/7 個 Phase 5 子功能完成）

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 54 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：
  - OmmlNode 樹結構讓 export 變成單純 prefix-add 遞迴
  - `writeRun(useDelText)` 一個 flag 共用 `<w:t>` / `<w:delText>` 邏輯
  - `writeCommentEntry` 透過 `writeBlock` dispatcher reuse 段落/表格/巢狀
  - comments.xml 對稱性策略同 styles.xml flat-equivalent（parser
    parseBodyContent reuse、export `writeBlock` reuse）
- **#18 scope-down**：
  - OMML xmlns:m 在每個 `<m:oMath>` 自帶（簡化、不在 root 統一）
  - 註解錨點 emit 在段落 boundary（精確字元位置 + range overlap 留後續）
  - background 只支援 `w:color`（themeColor / themeTint / themeShade 留後續、
    capture 已 resolved 為 hex、export 用 hex 即可）
- **#21**：math/revision/commentRefs/background 皆 optional、空時不輸出對應元素。
- **#2 magic number**：2 個新常數（REL_TYPE_COMMENTS / M_NS）。

---

## 後續

- **Sprint 195**（Phase 6 收尾）：
  - watermark export（header VML `<v:shape>` 文字浮水印序列化）
  - SmartArt export（`diagrams/dataN.xml` + drawing1.xml + rels 子目錄）
  - Chart export（`charts/chartN.xml` + rels 子目錄）
  - 達 Phase 6 100%

---

## Sprint 194 結尾累積指標

- vitest **1855 passed + 1 skipped**（`npm test` 全套；+21）
- VR mean **0.073191**（byte-identical 第 54 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 193 → **194**
- Phase 6 完成度 ~98% → ~99.5%（OMML + 追蹤修訂 + 註解 + background）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       OMML + revision + comments + background + comments.xml 部件（+約 100）
M  tests/unit/OoxmlWriter.test.ts                    +14 test + 1 既有測試升級（7-part）
M  tests/integration/sprint185_export_roundtrip.test.ts  +7 test（含端到端 comments+commentRefs）
```

**淨 production code 變動 = +約 100 行**、5 個 Phase 5 子功能 round-trip 對稱、
VR byte-identical 第 54 連、Phase 6 完成度 ~99.5%。
