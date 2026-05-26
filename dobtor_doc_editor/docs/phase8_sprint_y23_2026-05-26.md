# Phase 8 Sprint Y23 — Row 3 工具列 user toggle（2026-05-26）

**性質**：Y11 hide 留的尾巴 — Row 3（紙張 / 縮放 / 版本 / 匯入匯出）整列原本 `t-if="false"` 永遠隱藏，今改成 `state.showLegacyToolbar` 由查看 menu 開關、localStorage 持久化。Default 仍 hidden（同 Y11 預期、零視覺回歸）、user 可 opt-in。
**範圍**：`doc_editor.js`（+~16 行）、`doc_editor.xml`（修 1 個 attribute + 註解）、新建 sprint doc。零 CSS（既有 `.doc-toolbar` rules 全部沿用）。

---

## 1. 為什麼開這個

Y11 把 Row 3 收進 menubar 後寫死 `t-if="false"`、留下 DOM block 給「日後 revert 或改 user toggle」（Y11 sprint doc 明寫）。

- 部分 power user 抱怨 menubar 多兩層點擊（檔案 → 匯出為 PDF vs Row 3 直接按 PDF）
- 也有 user 想要更 minimal、只看 menubar 一條

兩種偏好併存、應給 user 選擇。Y23 兌現。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `state.showLegacyToolbar` | 新 boolean、default false、IIFE 從 localStorage `dobtor_doc_editor_show_legacy_toolbar` hydrate |
| 查看 menu | 加 1 行 `{ label: '✓ 顯示舊版工具列' / '   顯示舊版工具列', action: 'view:toggle-legacy-toolbar' }`、放在「顯示縮圖」與「外觀」之間 |
| `onMenuItemClick` 分派 | 加 `case 'view:toggle-legacy-toolbar'`：翻轉 state + 寫 localStorage |
| `doc_editor.xml` | Row 3 `t-if="false"` → `t-if="state.showLegacyToolbar"`、註解標 Sprint Y23 |
| sprint doc | 新檔 |

零 method 新增、零 CSS / XML 結構動。`.doc-toolbar` 的所有既有 rules 重新生效（Y11 後完全沒用過、Y23 恢復可用）。

---

## 3. 設計取捨

### 3.1 為什麼 default 仍 false

- Y11 collapsed 之後沒有 user 抱怨「畫面變少功能」、表示大多數 user 接受 menubar-only
- Default true 等於 visual regression、不該擅自加
- Opt-in 對 power user 是 menu 點兩下、零阻力

### 3.2 為什麼用 `view:toggle-` 一致命名

跟 `view:toggle-ruler` `view:toggle-thumbnails` 對齊、dispatcher case 一眼看出是「翻 boolean」。localStorage 寫回是 `view:toggle-` action 的次要副作用、用 try/catch 包不 crash。

### 3.3 為什麼不用 separator 分組

「顯示舊版工具列」跟「顯示尺規」「顯示縮圖」三個都是 visibility toggle、放同一段沒理由切。「外觀：跟系統 / 淺色 / 深色」是 cycle action 不同類、但仍同屬「View 偏好」、不切也 OK。要嚴格分組可下 sprint 加 separator。

### 3.4 為什麼 localStorage key prefix `dobtor_doc_editor_`

跟 Y9 `dark_mode`、Y13 `recent_colors`、Y19 `theme_mode` 一致。命名前綴避免跟其他模組撞鍵。

---

## 4. 預期 + 實測

**預期**：
- Default 隱藏（同 Y11）
- 查看 menu「顯示舊版工具列」menu item 出現、Click 翻轉 visibility
- Reload 後狀態保留
- 既有 6 條 E2E 不受影響（Y14.1 + Y20.1 + Y22.1 + G.1/HN.1/J.1）

**實測**（gstack /browse runtime probe）：

| 階段 | localStorage | `.doc-toolbar` count |
|---|---|---|
| 初始（無 LS） | null | 0 ✓ |
| Toggle ON | `'1'` | 1 ✓ |
| Toggle OFF | `'0'` | 0 ✓ |
| Toggle ON + reload | `'1'` | 1 ✓（persistence）|

E2E 6/6 pass (2.0m)、無回歸。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~16 行：state 加 1 key（含 IIFE）、menu items 加 1 行、dispatcher 加 1 case |
| `doc_editor.xml` | t-if 從 `"false"` 改 `"state.showLegacyToolbar"` + 註解改寫指向 Y23 sprint doc |
| `phase8_sprint_y23_2026-05-26.md` | 新檔 |

零 CSS、零既有 method 邏輯動。

---

## 6. 教訓

1. **deprecate ≠ delete**：Y11 hide 而非 delete Row 3 DOM、留下 12 sprint 後仍可 revive。回退是 1 attribute 改動，不用考古挖回整個 toolbar markup。
2. **user 偏好分歧的 feature 一律 opt-in**：default false 對既有 user 零驚喜、對想要的 user 一個 click。比強制改 default 安全。
3. **toggle pattern 是 Y23 第 4 次重用**：Y9 dark mode / Y19 themeMode cycle / Y13 recent colors / Y23 legacy toolbar 全套同樣 model（state + IIFE hydrate + onMenuItemClick case + localStorage write）。下次任何 user-pref boolean、複貼即用。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y22 | ✅ |
| **Y23 — Row 3 工具列 user toggle** | ✅（6/6 全綠） |

### Sprint Y24 候選

- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- 段落間距 / 縮排（沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state（selection 跨多 element 樣式不一）
- submenu 基礎建設（為「字型 / 字號 / 段落樣式集」鋪路）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數 etc.）
- localStorage 統一 wrapper / migration helper（Y23 是第 4 個直接寫 localStorage 的 sprint、值得抽 utility）
- Row 3 user toggle 對應 E2E spec（Y23 manual probe 驗過、未補回歸 spec）
