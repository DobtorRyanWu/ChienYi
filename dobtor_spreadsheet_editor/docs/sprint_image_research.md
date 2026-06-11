# §5.3 可編輯圖片 — 研究與部分交付

## 已交付
- **HTML 預覽圖片**（commit 5c5b447）：preview_images data URL `<img>`，已驗證（IMG_COUNT=1）
- **image_extractor.ts**：xlsx 內嵌圖片 → base64 + 位置 + sheetIndex（§5.3-B，已測試），供未來可編輯圖片用

## o-spreadsheet 圖片機制（研究結論）
- image figure 存於 `sheet.figures`（tag="image"），import 讀 `figure.data.path` + `figure.data.size`
- path 格式：`/web/image/{attId}?access_token={token}`（ir.attachment，Model external.fileStore=ImageFileStore）
- ImageFigure 元件用 `getters.getImagePath(figureId)` 渲染

## 可編輯圖片的阻礙（已實測）
1. 建 ir.attachment + 注入 image figure（data.path）→ **圖片確實在 o-spreadsheet 渲染**（實測 EDITABLE_IMG_COUNT=1）
2. **但**：我方 WorkbookData `version: 1`，o-spreadsheet `CURRENT_VERSION=22`
   - v1→v22 遷移中某步驟假設所有 figure 都是 chart（`[...figure.data.dataSets]`），
     image figure 無 dataSets → **TypeError: dataSets is not iterable**（載入崩潰）
   - 改 `version: 22` 可跳過該遷移、圖片正常顯示，**但跳過了公式必需的遷移 → 儲存格 #ERROR**
   - → 無單一 version 能同時「跳過 image-不相容遷移」且「保留公式遷移」

## 正解（未實作，獨立任務）
不把 image figure 放進初始 WorkbookData（避免遷移），改為**編輯器載入後 dispatch CREATE_IMAGE 指令**
注入圖片。需在 OWL 端取得 o-spreadsheet model 實例（OCA action 載入後），較大重構。

## 現況
預覽圖片已交付；可編輯圖片 building block（image_extractor）就緒；完整可編輯圖片待 post-load 方案。

## ✅ 完整交付（post-load 方案，已驗證）
1. models/spreadsheet_spreadsheet.py：spreadsheet.spreadsheet 加 `dobtor_pending_images`（Text/JSON）
2. xlsx_import.js：建 ir.attachment + generate_access_token，圖片定義存 dobtor_pending_images
   （含 sheetId=`sheet{i+1}`、figureId、position、size、definition.path=/web/image/...）
3. image_inject_patch.esm.js（spreadsheet.o_spreadsheet bundle）：patch SpreadsheetRenderer
   onMounted → 讀 dobtor_pending_images → dispatch CREATE_IMAGE → 清空欄位
4. **關鍵**：圖片不進初始 spreadsheet_raw（version 1 維持，公式遷移正常），
   載入後（遷移完成）才注入 → 避開 image figure 的 dataSets 遷移崩潰

驗證：GRID errDialog=0、EDITABLE_IMG_COUNT=1（圖片以 /web/image img 渲染）、
chart/cf/standalone 無回歸。
