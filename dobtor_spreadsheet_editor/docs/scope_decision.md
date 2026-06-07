# 文件產製通路決策

ChienYi 系統目前有**三條文件產製通路**並存：

1. **QWeb PDF**（既有）— 通報單、估驗單、施工日誌、自主檢查表
2. **dobtor_doc_editor**（開發中）— 監造會議記錄、施工計畫書、現場編輯類 docx
3. **dobtor_spreadsheet_editor**（本模組、Sprint 0）— 試算表類 xlsx 高保真匯入

新增任何「產出文件 / 試算表」需求時，**必須先依下表決定走哪條通路**，避免三邊都做半套。

## 決策樹

| 文件特性 | QWeb PDF | dobtor_doc_editor | dobtor_spreadsheet_editor |
|---|---|---|---|
| 系統自動產出、無人工編輯（月報、列印單據） | ✅ | ❌ | ❌ |
| 範本欄位固定、需簽核（通報單、估驗單、施工日誌、自主檢查表） | ✅（保留現狀） | ⚠️ 不取代 | ❌ |
| 需多人協作、版面複雜、現場需編輯（會議記錄、施工計畫書） | ❌ | ✅ | ❌ |
| 需法定固定格式（政府公文、報部資料） | ✅ | ❌ | ❌ |
| 需即時填表 + 可追蹤版本歷史 | ❌ | ✅ | ✅（試算表類） |
| **試算表**：含公式、合併儲存格、條件格式 | ❌ | ❌ | ✅ |
| **試算表**：估驗計價試算、契約工項分析 | ⚠️（簡單者用）| ❌ | ✅ |
| **試算表**：含 chart、pivot、樞紐分析 | ❌ | ❌ | ✅ |
| 跨表格 VLOOKUP / INDIRECT 試算 | ❌ | ❌ | ✅ |
| 雙向 round-trip（xlsx 進、編輯、xlsx 出） | ❌ | ❌ | ✅ |

## 三條通路目前狀態

| 通路 | 已落地交付 | 模組路徑 | 規劃文件 |
|---|---|---|---|
| **QWeb PDF** | 通報單、估驗單、施工日誌（單張+批量）、自主檢查表 | 各 `construction_*/report/` | — |
| **dobtor_doc_editor** | docx 匯入 Sprint 200+、Phase 1-6 完成 | `addons/dobtor_doc_editor/` | `dobtor_doc_editor_高保真匯入開發規劃.md` |
| **dobtor_spreadsheet_editor** | Sprint 0 基建中 | `addons/dobtor_spreadsheet_editor/`（本模組） | `dobtor_spreadsheet_editor_高保真匯入開發規劃.md` |

## 引用規則

- **不要把既有 QWeb 報表搬到 dobtor**：QWeb 已穩定且支援批量列印，搬遷成本高、收益低
- **新文件需求預設用 QWeb**，除非明確需要多人協作、現場編輯、或試算
- **試算需求預設用 dobtor_spreadsheet_editor**（即使試算結果只用一次）—— 因為試算表的公式邏輯不適合用 QWeb 表達
- **dobtor mixin 整合**：未來 ChienYi 模型若要關聯 dobtor 文件，inherit `doc.linked.mixin`（dobtor_doc_editor）或 `xlsx.linked.mixin`（dobtor_spreadsheet_editor、Phase 4.5）；不要在模型直接寫 `doc_id`/`xlsx_id` Many2one
- **三方互通**：不規劃 docx ↔ xlsx 互轉；若需要 PDF 輸出，xlsx 走 openpyxl → LibreOffice headless → PDF，與 dobtor_doc_editor 的 PDF 路徑分開

## 邊界情況

| 場景 | 走哪條 | 理由 |
|---|---|---|
| 估驗計價表（含公式 + PDF 列印） | **xlsx Editor + 自動 PDF 輸出** | 編輯靠 xlsx、列印走 LibreOffice headless |
| 監造日報（含表格 + 多人簽核） | **doc Editor**（不是 xlsx） | 簽核位置固定、表格簡單 |
| 月報（含損益試算 + 文字說明） | **xlsx Editor 為主、doc Editor 為輔** | 試算是主、文字附議；兩個檔案分開 |
| 政府電子採購標單 XML | **xlsx Editor 入庫 + QWeb 列印** | XML 結構化匯入用 xlsx parser、列印用既有 QWeb |
| 工地照片週報（圖片密集） | **doc Editor** | 圖片排版需求 |
| 一次性試算（如成本評估） | **xlsx Editor** | 公式需求 |

## 詳細規範

本檔為 ChienYi 整體分流規範。各模組 README 應引用本檔。

未來若新增第四通路（如 PowerPoint / Slide editor），須更新本檔。
