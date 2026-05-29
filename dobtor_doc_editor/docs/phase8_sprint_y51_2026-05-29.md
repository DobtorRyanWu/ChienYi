# Phase 8 Sprint Y51 — 格式按鈕完整 active toggle 雙向同步 source fix（2026-05-29）

**性質**：source fix sprint — 修掉 Y50 揭露、卡住「格式按鈕完整 active toggle」的根因。Y50 診斷：格式按鈕（B/I/U/S + 對齊）是普通 OWL `<button>`、點按時 canvas 失焦 → canvas-editor 內部選取被 `clearSideEffect`（document mousedown listener）清掉 → `executeBold` 對空 range 無效（boldCount:0 / rangeCtx:null）→ 完整「選取→套用→active 回寫」E2E 不穩、Y50 只能鎖 aria-pressed 動態性、完整 toggle 留 Y51。Y51 用 canvas-editor 內建的 `editor-component` 屬性機制保住選取、補 mousedown.prevent 保持焦點視覺、鎖完整 forward 雙向同步。

**範圍**：`doc_editor.xml`（`.doc-format-toolbar` 加 `editor-component="format-toolbar"` ×1 + 8 個格式按鈕加 `t-on-mousedown.prevent` ×8）、新 spec `admin-dobtor-doc-editor-sprint-y51-format-btn-toggle.spec.ts`（top-level、+~190 行）、新 sprint doc。

---

## 1. 為什麼開這個

Y50 sprint doc Y51 候選第一條：「格式按鈕完整 active toggle 雙向同步（需先修 source：按鈕 mousedown preventDefault 保住 canvas 選取 + rangeStyleChange listener 加 this.render() 觸發即時更新；再 spec）」。Y51 兌現——但探查推翻了 Y50 候選描述裡的兩個假設（見 3.2、3.3），改用更正確的機制。

格式按鈕（Sprint Y5、`.doc-format-btn`）的「選取文字 → 點 B → 套用 + 按鈕亮起」是 Google Docs 風最基本互動。Y50 揭露它在 E2E（甚至實際使用）下會 silent 半壞：點按鈕清掉選取、套用落空。Y51 修 source 讓它真的能用、並鎖死。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `doc_editor.xml` source fix（A）| `.doc-format-toolbar` 加 `editor-component="format-toolbar"` → canvas-editor `clearSideEffect` 偵測到工具列互動、**不清** canvas 選取 |
| `doc_editor.xml` source fix（B）| 8 個格式按鈕（B/I/U/S + 對齊 4）加 `t-on-mousedown.prevent` → mousedown 不搬焦點、canvas agent 保持 focus（選取視覺持續、多格式連點不掉選取）|
| Y51.1 test | 新增（top-level、~190 行）：seed content_json 真文字 → 全選 → 點粗體 → 內容層 oracle（getValue 有 bold element）+ 按鈕層 oracle（aria-pressed 翻 true）+ toggle off + 斜體平行 wiring |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼用 canvas-editor 的 `editor-component` 屬性、不用 stopPropagation

根因在 canvas-editor 內部（`canvas-editor.es.js`）：

```js
addEvent() {
  window.addEventListener("blur", this.clearSideEffect);
  document.addEventListener("mousedown", this.clearSideEffect);   // ← 元兇
  ...
}
clearSideEffect = (evt) => {
  const target = evt.composedPath()[0] || evt.target;
  // 1) 點在頁面內 → 不清
  if (innerEditorDom) return;
  // 2) 點在帶 EDITOR_COMPONENT 屬性的元素內 → watchCursorActive() + 不清！
  const outerEditorDom = findParent(target, n => n.getAttribute(EDITOR_COMPONENT), true);
  if (outerEditorDom) { this.watchCursorActive(); return; }
  // 3) 其它 → recoveryCursor / recoveryRangeStyle（清選取）
  this.range.recoveryRangeStyle();
  ...
};
```

`EDITOR_COMPONENT = "editor-component"`。canvas-editor **本來就設計了逃生口**：mousedown target 落在帶 `editor-component` 屬性的 DOM 內就跳過清除。這正是官方 demo 工具列不掉選取的方式。

- **stopPropagation 是錯解**：`document` 上的 listener 靠 `editor-component` 判斷、不是靠事件到不到得了 document。雖然 `.stop` 也能擋掉冒泡到 document、但會**順帶擋掉本專案自己的 `_onGlobalClick`（mousedown 關 menu/dropdown）**、引入「點格式按鈕時開著的下拉不關」副作用。
- **preventDefault 不夠**：`preventDefault` 只擋瀏覽器預設動作（搬焦點），**擋不掉 document 上的 JS listener**。所以單加 `mousedown.prevent` 不解決清選取（實測仍 fail）。

用 `editor-component` 是順著 lib 設計、零副作用、最小侵入。

### 3.2 為什麼還加 `mousedown.prevent`（推翻 Y50 候選的「不需要」）

`editor-component` 已足以讓 `executeBold` 套用到選取（range 資料保住、bold 真的套上、實測 R3 selText 仍在）。但 `mousedown.prevent` 補的是**焦點視覺**：不加時點按鈕 → 焦點搬到 button → canvas agent 失焦 → 游標停閃、選取藍底淡掉（資料還在、視覺糊）。加了 `mousedown.prevent` → 焦點不離 canvas → 選取藍底持續 → user 可連點 B→I→U 維持同一段選取（Google Docs 體驗）。兩者職責不同、都留。

### 3.3 為什麼**不需要** `this.render()`（推翻 Y50 候選的猜測）

Y50 候選寫「rangeStyleChange listener 加 this.render() 觸發即時更新」、依據是 Y50 doc 猜「listener mutate state 在 OWL reactivity 外、不觸發 render」。**實測推翻**：點粗體後 `aria-pressed` 確實翻 `true`（probe `ARIA_after: true`）。`this.state` 是 `useState` reactive proxy、寫入靠 Proxy set trap 攔截、**與是否在 OWL 事件處理器內無關**；canvas-editor listener 內 `this.state.activeBold = true` 照樣 schedule re-render。Sprint B 的 `intersectionPageNoChange` listener mutate `state.pageNo` 也是同理。**先驗證再加 code**：省下一段沒必要的 `this.render()`（會造成多餘 double-render）。

### 3.4 為什麼 spec 的 click 位置從 (80,60) 改 (140,112)

探查最大發現：Y49 沿用的 `selectAllInCanvas` click `(80,60)` **落在 A4 頁面 PAGING 模式的左上 margin（~100-120px）、不是文字上** → canvas-editor 不放游標（`getRange()` 回 `{startIndex:-1,endIndex:-1}`）→ Ctrl+A 無作用 → 根本沒選取。實測 `(140,112)` 落在第一個字、可靠放游標（range `{s:1,e:1}` → Ctrl+A → `{s:0,e:9}`、selText 有值）。

這也確認了 **Y50 doc 教訓 #3 的根因**：Y49 字型/字號 select「通過」是 native select 值保留的假陽性、不是真反向同步——因為它的選取根本沒成立（click 在 margin）。Y51 找到真正落在文字的 click 點、第一次做出**真選取**的 canvas 互動 spec。（Y49 retrofit 留 Y52 候選。）

### 3.5 為什麼 fixture 直接灌 content_json、不靠 template content_html

實測 fresh doc（只給 `template_id`）開啟後 `getValue().data.main` 只有 1 個空 element——template 的 `content_html` fallback（`executeSetHTML`）在新建文件不一定觸發。**spec 要可靠的可選取文字、直接 seed `content_json`**（沿用 Y47 驗證過的 `[{value:'...'}]` 扁平陣列、canvas-editor `Editor` 建構子接 `IElement[]`）。canvas-editor 會把多字 `{value}` 合併成單一 run、getValue 回 `[{value:"...全文...\n", bold?}]`、`bold:true` 計數 oracle 仍成立。

### 3.6 spec scope：forward 雙向 + toggle off + 平行 wiring

- **forward（button↔canvas 雙向）**：全選 → 點粗體 → getValue 出現 `bold:true` element（內容層 oracle、證套用生效）+ 按鈕 aria-pressed 翻 true（按鈕層 oracle、證 caret 狀態回寫 + re-render）。一個 round-trip 同時鎖：選取保住 + 套用 + 反向同步 + render。
- **toggle off**：再全選 → 再點粗體 → 全選皆 bold → executeBold 反轉成取消 → aria-pressed 回 false。
- **斜體平行 wiring**：B/I/U/S 走同一 `_executeCmd` + 同一 rangeStyleChange 同步 block（讀 el.bold/italic/...）、機制共用；斜體各鎖一次 forward 證平行 wiring 通（同 Y49 字型/字號各測一次）。

---

## 4. 預期 + 實測

**預期**：修後格式按鈕點按保住 canvas 選取、executeBold 真套用、按鈕 active 狀態反向同步亮起。

**實測**（probe 逐步追蹤）：
- click `(80,60)`：range `{-1,-1}`、ctxNull（**落在 margin、無選取**）→ 確認 Y49 click 位置問題
- click `(140,112)` → Ctrl+A：range `{0,9}`、selText `"探查文字段落內容"`（**真全選**）
- 點粗體後：range 仍 `{0,9}`、selText 仍在（**選取保住**）、getValue `bold:1`（**套用生效**）、`aria-pressed=true`（**反向同步 + re-render**）
- API `executeBold()` 再切：`bold:0`（**toggle off 生效**）
- Y51.1 單跑：1/1 pass (29.8s)
- 38-test full suite 連跑：35 pass + 3 fail（`abce` Sprint E 開 DocFieldPickerDialog、`ghn` J.1 table-cell 替換、`y20` find-keyboard）12.3m
- 3 個 fail 全部單跑：9/9 pass (2.9m) ← **確認與本 sprint format-toolbar source 改動無關**（我的改動是 deterministic、只動格式工具列、若破壞它們單跑也會 fail）＝高負載 timing flaky、非 save_field/drag 家族（與 Y43/Y49 修的那組不同源）、留 Y52 flaky 批次

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `static/src/components/doc_editor/doc_editor.xml` | `.doc-format-toolbar` +`editor-component` ×1 + 8 格式按鈕 +`t-on-mousedown.prevent` ×8（selective staging）|
| `admin-dobtor-doc-editor-sprint-y51-format-btn-toggle.spec.ts` | 新檔 +~190 行（top-level repo）|
| `phase8_sprint_y51_2026-05-29.md` | 新檔 |

---

## 6. 教訓

1. **canvas-editor 有 `editor-component` 屬性逃生口、外部工具列互動不掉選取**：根因是 canvas-editor `document.addEventListener("mousedown", clearSideEffect)`、會在點 canvas 外時清選取。**正解是給工具列容器加 `editor-component="..."` 屬性**（lib 內建 `clearSideEffect` 會偵測並跳過）、不是 stopPropagation（會誤擋自家 global mousedown）也不是 preventDefault（擋不掉 document listener）。整合第三方 canvas 編輯器先翻它的 side-effect listener 找官方 hook、別硬擋事件流。
2. **canvas E2E 的 click 位置要落在文字上、不是頁面 margin**：A4 PAGING 模式有 ~100-120px margin、click `(80,60)` 落在 margin → canvas-editor 不放游標（range `-1`）→ Ctrl+A 假全選。**先用 probe 印 `getRange()` 確認 click 真的放了游標**（range≠-1）再往下做。這直接坐實 Y50 教訓 #3：Y49 select「通過」是假陽性（選取根本沒成立、靠 native select 值保留）。怕脆而避開 canvas 互動是一回事、寫了卻沒驗證選取真成立是更隱蔽的假測。
3. **fresh doc 靠 template content_html fallback 不可靠、spec 要真文字直接 seed content_json**：只給 template_id 的新 doc 開啟後 main 可能只有 1 空 element。需要可選取文字的 canvas spec **直接灌 `content_json`**（Y47 的 `[{value}]` 扁平陣列）、別賭 fallback。
4. **useState 從非 OWL 事件 mutate 也會 re-render、先驗證再加 code**：Y50 猜「rangeStyleChange listener mutate state 不觸發 render、需 this.render()」——實測 `aria-pressed` 自動翻 true 推翻。`useState` reactive proxy 靠 Proxy trap、與呼叫端是否在 OWL handler 內無關。**候選描述裡的「需要某修法」是假設、不是事實**；動手前用 probe 驗證、省下沒必要的 double-render。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y50 | ✅ |
| **Y51 — 格式按鈕完整 active toggle source fix** | ✅（待 full suite 最終確認、首個真 canvas 選取 + 真套格式的 E2E）|

### Sprint Y52 候選

- Y49 retrofit：把 `selectAllInCanvas` click 改 `(140,112)` 真選取、補 getValue 字號/字型 oracle（把 Y49 假陽性轉真測）
- 對齊 align 完整 active toggle（同 Y51 機制已修、補 spec 鎖：點置中 → rowFlex='center' → aria-pressed 對齊組翻）
- indeterminate state（部分選中、跨樣式選取 → format toolbar 顯示未定態）
- 清除格式 / 複製格式（painter）按鈕也納入 editor-component 保護範圍的 spec
- 模板模式匯出 PDF/DOCX spec（rpc fill_template → LibreOffice → download、需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（file input + TS Parser、需 .docx 上傳 fixture）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次
