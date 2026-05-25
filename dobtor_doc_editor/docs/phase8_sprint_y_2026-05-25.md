# Phase 8 Sprint Y — Google Docs 風 UI skin pass + canvas 上方公分尺規（2026-05-25）

**性質**：純 CSS 視覺改造 + 1 個 ruler element 加 XML，不動 class names / selectors，零功能變動、E2E 全綠。
**範圍**：[doc_editor.css](../static/src/css/doc_editor.css)（末尾 append override section）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（canvas-workspace 內加 `<div class="doc-ruler">`）。

---

## 1. 目標

user 指 Google Docs 截圖：「視覺化 (H/J) 受 canvas-editor 架構限制最大畫作到這些功能，可以文書編輯尺噹等等」。意即：在 canvas-editor 架構容許範圍內，UI 朝 Google Docs 簡潔風 + 公分尺規靠攏。

**核心約束（保留 E2E + 既有功能）**：
- 所有 class names 不變（`.doc-field-btn-scan`、`.doc-field-btn-rollback`、`.doc-inspector-fields-list-header` 等都被 E2E 用）
- XML 結構盡量不動（只新加 ruler element、不重排既有 row）
- canvas-editor 內部 paper rendering 不破壞

---

## 2. CSS skin pass（append override section 於 `doc_editor.css` 末尾）

### 配色系統（Google Docs / Material 3 風）

```css
.o_dobtor_doc_editor {
    --gd-bg: #f8f9fa;
    --gd-paper-bg: #ffffff;
    --gd-toolbar-bg: #ffffff;
    --gd-toolbar-border: #e5e7eb;
    --gd-text: #202124;
    --gd-text-muted: #5f6368;
    --gd-accent: #1a73e8;            /* Google blue */
    --gd-accent-soft: #e8f0fe;
    --gd-hover-bg: rgba(60, 64, 67, 0.08);
    --gd-shadow-toolbar: 0 1px 3px 0 rgba(60, 64, 67, 0.08);
    --gd-shadow-paper: 0 2px 8px rgba(60, 64, 67, 0.16);
    --gd-radius: 8px;
    --gd-radius-sm: 4px;
    --gd-font: "Google Sans", "Noto Sans TC", -apple-system, BlinkMacSystemFont,
               "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
```

### 各 row 重新皮膚

| Row | 改動 |
|---|---|
| Header bar（檔名 + 預覽/儲存/關閉） | 白底 + subtle shadow；文件名稱透明 border + hover 才浮；儲存按鈕 Google blue primary |
| Sub-nav（儀表板/請求/範本/設定） | chips 風（pill rounded）；active 用 `--gd-accent-soft` 底 + `--gd-accent` 文字 |
| Toolbar（紙張/版本/匯出/縮放） | 白底簡潔；select 用淡灰 border、focus 才變藍；btn-group 沿用 segmented 外觀但 border 淡化 |
| Field toolbar（欄位類型 + 掃描按鈕） | 各按鈕配色：掃描變數=blue / 掃描並替換=orange / 預覽=gray / 復原=green / Odoo=accent |
| Signer bar（簽約人 + 頁碼 + zoom） | chip 風；active signer 用 `--gd-accent-soft`；頁碼按鈕透明 + hover 浮 |
| Inspector（右側欄位列表） | header 用 `--gd-bg`；row hover 浮 `--gd-hover-bg`；is-selected 用 `--gd-accent-soft`；is-orphan 用 `#fef7e0`（Material amber）|

---

## 3. 公分尺規（Sprint Y 突破）

### 嘗試 1（失敗）：把 doc-workspace 改 column flex

想讓 ruler 在上、canvas 在下，自然 stack。CSS：

```css
.doc-main > .doc-workspace {
    flex-direction: column;
    align-items: center;
}
```

結果：**canvas-editor 內部 paper rendering 整個消失**（screenshot v2 — canvas 區全空白、只剩縮圖看得到內容）。canvas-editor 對 parent flex 方向有隱性依賴，不能改 row→column。

### 嘗試 2（成功）：ruler 改 `position: absolute` 浮在 workspace 頂部

```css
.o_dobtor_doc_editor .doc-ruler {
    position: absolute;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 5;
}
```

不動 doc-workspace 原本 row flex 結構、canvas-editor 正常運作。Ruler 自然漂浮在 canvas 紙張上方、橫向置中。

### Ruler 本體（CSS-only 公分刻度）

```css
.doc-ruler {
    display: flex;
    height: 22px;
    --ruler-cm-px: 37.8px;          /* 1cm ≈ 37.8px @ 96dpi */
    --ruler-tick-color: #9aa0a6;
    /* 主刻線：每公分一條淡灰線（background gradient） */
    background-image: repeating-linear-gradient(
        to right,
        transparent 0,
        transparent calc(var(--ruler-cm-px) - 1px),
        var(--ruler-tick-color) calc(var(--ruler-cm-px) - 1px),
        var(--ruler-tick-color) var(--ruler-cm-px)
    );
    background-size: 100% 8px;
    background-position: 0 14px;
}
.doc-ruler-labels { display: flex; align-items: center; ... }
.doc-ruler-tick { flex: 0 0 var(--ruler-cm-px); }
```

XML：

```xml
<div class="doc-ruler" aria-hidden="true">
    <div class="doc-ruler-labels">
        <t t-foreach="[1,2,...,21]" t-as="cm" t-key="cm">
            <span class="doc-ruler-tick"><t t-esc="cm"/></span>
        </t>
    </div>
</div>
```

寬度由 labels content 決定（21 ticks × 37.8px = ~794px ≈ A4 寬度），與 canvas-editor 預設 paper width 對齊。

### 已知限制（留 Sprint Y2+）

- ruler 寬度寫死 21cm（A4 寬）—— 切 A3/Letter/Legal 不會自動跟
- zoom 不會更新 `--ruler-cm-px`（要 JS 改 inline style）
- ruler 不顯示左/右 margin indicator（Google Docs 有藍色三角形）

---

## 4. 視覺驗證

3 階段截圖（mcp playwright）：

- **v1** — skin pass 後沒 ruler，工具列 + 按鈕配色全更新 ✓
- **v2** — 試 column flex → canvas 不見（教訓）
- **v3** — ruler absolute 浮頂部 → canvas 正常 + 公分刻度 1-21 全顯示 ✓

最終效果 vs 原 design：對照 Google Docs 截圖（user 提供），UI 在簡潔配色、留白、ruler 三點上靠攏。差距：頂部仍有 Odoo navbar（purple bar）和 sub-nav 切分；Google Docs 的 menu bar（檔案/編輯/查看 dropdown）尚未做。

---

## 5. 驗證

### E2E 回歸（3/3 全綠，無 selector 破壞）

```
Phase 8 Sprint R — Sprint G/H/M/N E2E smoke
  ✓ G.1 (19.8s)
  ✓ HN.1 (21.7s)
  ✓ J.1 (16.9s)
3 passed (1.1m)
```

### 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.css` | append ~220 行 override（末尾「Sprint Y」段） |
| `doc_editor.xml` | +1 `<div class="doc-ruler">` element 在 canvas-workspace 內 |

零 JS 改動、零 class rename、零 XML 結構重排。

---

## 6. 進度

| Sprint | 狀態 |
|---|---|
| G-X | ✅ |
| **Y — Google Docs 風 skin + ruler** | ✅（功能性 polish；ruler 自動 zoom / 多 paper size 留 Y2） |

### Sprint Y2 候選

- ruler 寬度動態跟 paper size（A3/Letter/Legal）+ zoom（CSS variable + JS onZoomChange）
- 加 Google Docs 風 menu bar（檔案/編輯/查看 dropdown）取代 row 2 sub-nav
- ruler 加 margin indicator（左/右藍三角）
- 全黑暗模式 token（`prefers-color-scheme: dark`）

---

## 7. 教訓

1. **canvas-editor 對 parent flex 方向有隱性依賴**：不能把 doc-workspace 從 row 改 column。新 element 要加在 workspace 內必須用 absolute / fixed 浮層方式，不能改 row flow。
2. **CSS-only ruler 可行**：用 `repeating-linear-gradient` 畫刻度 + flex `flex: 0 0 <cm-px>` 撐 label tick 寬度，零 JS 就能做出 Google Docs 風尺規。
3. **CSS override section（不改既有規則）是最低風險的 skin pass**：CSS variable 駕馭主色票、所有 override 集中在檔尾，回退簡單（git revert 末段即可）、E2E 零干擾。
