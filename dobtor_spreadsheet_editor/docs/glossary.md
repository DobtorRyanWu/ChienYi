# 術語表

與規劃書附錄 B 同步維護。本檔提供延伸補充。

## OOXML SpreadsheetML 縮寫

| 縮寫 | 全寫 | 說明 |
|---|---|---|
| SML | SpreadsheetML | OOXML 的 spreadsheet 規格（ECMA-376 §18） |
| OOXML | Office Open XML | Microsoft 主導的辦公文件 XML 規格 |
| DrawingML | Drawing Markup Language | OOXML 的繪圖規格（§20），含 chart / shape / image |
| EMU | English Metric Unit | 1 EMU = 1/914400 inch；1 pt = 12700 EMU |
| dxa | twentieths of a point | Word 用單位；spreadsheet 較少 |
| xf | (cell)Format | styles.xml 中的 cell format index |
| dxf | Differential Format | CF rule 套用的部分樣式 |
| CF | Conditional Format | 條件格式 |
| sqRef | Sequence Reference | 空格分隔的多範圍引用（如 `A1:B2 C3:D4`） |
| rId | Relationship Id | .rels 文件內的關係 ID（如 `rId1`） |
| si | (SharedString) Index / (Shared formula) Index | 雙義：sharedStrings 的 index、或 shared formula 的 anchor id |

## o-spreadsheet 內部用語

| 術語 | 含義 |
|---|---|
| Model | spreadsheet 的資料 + dispatch 中心 |
| Plugin | 擴展 Model 的模組（CorePlugin 寫資料、UIPlugin 處理顯示） |
| Command | Model.dispatch 接收的指令物件（如 `{ type: 'ADD_MERGE', ... }`） |
| Revision | 一次 dispatch 的記錄、用於協作 + undo/redo |
| Figure | sheet 上可拖曳的物件（chart、image） |
| Zone | 範圍物件 `{ top, bottom, left, right }` |
| sheetId | sheet 的 UUID（與 Excel sheetId 不同） |
| getters | Plugin 提供的查詢 API |

## ChienYi 業務術語（用於 Phase 8）

| 術語 | 含義 | xlsx 對應 |
|---|---|---|
| 估驗計價表 | 工程款項估驗試算 | 多 sheet xlsx、含合併儲存格、SUM/SUMIF 公式 |
| 契約工項 | 工程合約細項 | 樹狀縮排表格、粗體分層 |
| 月報損益 | 每月損益試算 | 條件格式（紅負/綠正）、百分比 |
| 政府採購標單 | XML 標單轉 xlsx | 結構化欄位（itemNo、Description、Unit、Quantity、Price） |
| 進度 S 曲線 | 工期累進百分比曲線 | line chart + 月度 bar |
