# construction_menu_profile — 後台選單設定檔

把「後台要看到哪些選單」集中成一份清單。實際開關表在
[`models/ir_ui_menu.py`](models/ir_ui_menu.py) 的 `MENUS_OFF`。

## 怎麼改

**要把某個選單開回來** → 從 `MENUS_OFF` 刪掉那一行，然後：

```bash
docker exec pg18-odoo bash -lc 'odoo -u construction_menu_profile -d system_development --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" --stop-after-init' && docker restart pg18-odoo
```

⚠️ 只在後台「設定 → 技術 → 使用者介面 → 選單項目」把 active 勾回來是**撐不住的**——
下次升級本模組時 `<function>` 會重新套用整份設定檔，又會被關掉。這是刻意的：
讓「預設關閉」在每個站台都是一致狀態。臨時要看一下可以勾回來，長期開啟請改這裡。

**要多關一個選單** → 在 `MENUS_OFF` 加一行 `(xml_id, 說明, 子項數)`。
若那個選單屬於還沒列進 `depends` 的模組，記得一併補 `__manifest__.py` 的 `depends`
（確保載入順序），或依賴清單裡的 `raise_if_not_found=False` 容錯（會在 log 留 warning）。

---

## 保留的選單（2026-08-10 使用者確認）

```
工程管理
├── 工程總覽 ─ 工程案件 / 契約工項 / 從價格庫匯入工項
├── 契約管理 ─ 契約變更單 / 待處理變更單 / 已套用變更單
├── 送審管制表
├── 進度管理 ─ 進度表 / 進度明細 / 進度表圖表 / 進度報告
└── 人機管理 ─ 人員機具設定 / 所有人機紀錄 / 人員出工統計 / 機具使用統計

檔案管理
├── 文件管理 ─ 文件分類 / 工程文件 / 全部工程附件
└── 照片管理 ─ 工程照片 / 照片標籤 / 照片分類

施工執行
└── 施工日誌 ─ 我的日誌 / 施工排程 / 所有日誌 / 批次下載

通報單管理 ─ 通報單 / 執行中通報單

品質安全
├── 自主檢查 ─ 自主檢查類型設定 / 一般式自主檢查 / 預約式自主檢查
├── 缺失管理 ─ 編號前綴設定 / 一般式監造缺失改善 / 一般式營造缺失改善
│              / 預約式監造缺失改善 / 預約式營造缺失改善
│              / 一般式逾期缺失 / 預約式逾期缺失
└── 檢試驗管理 ─ 檢試驗項目設定 / 檢(試)驗管制記錄 / 工項檢試驗統計
                 / 檢驗預警通知 / 設定 ─ 公式範本庫

計價請款 ─ 估驗計價 / 成本分析 / 即時損益 / 報表下載 ─ 批次下載

報表 / 下載 ─ 批次下載

系統設定
├── 樣板設定 ─ 所有樣板 / 自主檢查項目樣板庫
│              / 依類型 ─ 施工日誌樣板 / 自主檢查樣板 / 缺失改善樣板
│                         / 估驗計價樣板 / 進度報告樣板
└── 價格庫 ─ 價格庫分類 / 價格庫項目 / 價格變更歷史

文件編輯器 ─ 我的文件 / 文件範本 / 批次匯入 / 監控 ─ 錯誤紀錄 / 效能指標 / 匯出紀錄
```

另外保留的 Odoo 原生 App（使用者決定不關）：
**討論**、**待辦事項**、**Dashboards**、**員工**、**測試**、**應用程式**、**設定**。

> 應用程式（`base.menu_management`）與 設定（`base.menu_administration`）**絕對不能關**，
> 關了就無法安裝模組、管理使用者與權限。

### 名稱對照（使用者清單 vs 系統實際名稱）

清單裡的每一項都對得上現有選單，只有 4 處字面略有出入，**不改名**：

| 使用者寫的 | 系統實際名稱 |
|---|---|
| 工程總**攬** | 工程總**覽** |
| 全部工程**文件** | 全部工程**附件**（`menu_supervision_attachment_all`） |
| 缺失**改善**（父層） | 缺失**管理**（`menu_defect_management`） |
| 檢試驗管制**紀錄** | 檢(試)驗管制**記錄** |

---

## 關閉的選單

### 由本模組關閉（`MENUS_OFF`，19 個父層 → 約 45 個入口）

| xml_id | 位置 | 帶走子項 |
|---|---|---|
| `contacts.menu_contacts` | 頂層 App「聯絡人」 | 0 |
| `maintenance.menu_maintenance_title` | 頂層 App「保養」 | 0 |
| `base_geoengine.geoengine_base_menu` | 頂層 App「GeoEngine Backend」 | 4 |
| `spreadsheet_oca.spreadsheet_spreadsheet_menu` | 頂層 App「Spreadsheets」（`dobtor_spreadsheet_editor.menu_xlsx_import` 掛在其下） | 1 |
| `construction_supervision_base.menu_acceptance_root` | 頂層 App「驗收結案」 | 12 |
| `construction_supervision_base.menu_standard_work_item_root` | 頂層 App「標準工項管理」 | 0 |
| `construction_supervision_base.menu_resource_management` | 工程管理 > 資源管理 | 7 |
| `construction_supervision_base.menu_reports` | 工程管理 > 報表（原為 `group_no_one`） | 3 |
| `construction_timeline.menu_schedule_analysis` | 工程管理 > 進度管理 > 時程分析 | 4 |
| `construction_progress.menu_progress_chart_graph` | 工程管理 > 進度管理 > 進度曲線圖(標準)（原為 `group_no_one`） | 0 |
| `construction_equipment.menu_equipment_list` | 工程管理 > 人機管理 > 機具設備 | 2 |
| `construction_equipment.menu_equipment_maintenance` | 工程管理 > 人機管理 > 維護請求 | 3 |
| `construction_meeting_record.menu_construction_meeting_record` | 檔案管理 > 文件管理 > 會議記錄 | 0 |
| `construction_daily_log.menu_daily_log_config` | 施工執行 > 施工日誌 > 設定 | 2 |
| `construction_supervision_base.menu_timesheet_management` | 施工執行 > 工時管理 | 2 |
| `construction_supervision_base.menu_cost_analysis` | 計價請款 > 成本分析（空殼，撞名） | 0 |
| `construction_supervision_base.menu_equipment_config` | 系統設定 > 設備設定 | 2 |
| `construction_supervision_base.menu_basic_config` | 系統設定 > 基礎設定 | 1 |
| `construction_supervision_base.menu_audit_config` | 系統設定 > 稽核管理 | 4 |

### 各自模組裡早就 `active=False`（本模組不重複處理）

| xml_id | 位置 |
|---|---|
| `construction_timeline.menu_task_timeline` | 工程管理 > 進度管理 > 工項時程 |
| `construction_partner.menu_technical_contacts` | 工程管理 > 資源管理 > 技術聯絡人 |
| `construction_supervision_base.menu_claim` | 計價請款 > 請款管理 |
| `construction_daily_log.menu_daily_log_lines` | 施工日誌 > 設定 > 日誌明細 |
| `construction_daily_log.menu_daily_log_weather` | 施工日誌 > 設定 > 天氣記錄 |
| `project.menu_main_pm` | 頂層 App「專案」 |
| `hr_timesheet.timesheet_menu_root` | 頂層 App「工時表」 |

---

## 連帶影響

**關閉「機具設備」後，施工日誌人機明細的「機具設備」欄會挑不到資料。**
因此 `construction_equipment` 18.0.1.3.0 把日誌人機頁籤的欄位從關聯的
`equipment_id` 換回自由文字的 `specific_equipment_name`。

模型欄位 `daily.log.man.machine.detail.equipment_id` **保留不刪**（刪掉要連帶改
`equipment.py:_compute_usage_stats` 並寫 migration，日後要恢復關聯又得重來）。
留著只是不顯示，唯一副作用是 `supervision.equipment.total_usage_hours` 恆為 0——
而機具設備畫面本來就關了。

要恢復關聯式選擇：從 `MENUS_OFF` 移除 `construction_equipment.menu_equipment_list`，
並把 `construction_equipment/views/daily_log_sheet_views.xml` 的欄位換回 `equipment_id`。

---

## 驗證

列出目前所有還開著的選單（樹狀）：

```bash
docker exec pg18-db psql -U jerry -d system_development -c "
WITH RECURSIVE t AS (
  SELECT m.id, m.parent_id, m.sequence, 0 AS lvl,
         LPAD('', 0) || COALESCE(m.name->>'zh_TW', m.name->>'en_US') AS path
    FROM ir_ui_menu m WHERE m.parent_id IS NULL AND m.active
  UNION ALL
  SELECT m.id, m.parent_id, m.sequence, t.lvl+1,
         t.path || ' > ' || COALESCE(m.name->>'zh_TW', m.name->>'en_US')
    FROM ir_ui_menu m JOIN t ON m.parent_id = t.id WHERE m.active)
SELECT lvl, path FROM t ORDER BY path;"
```
