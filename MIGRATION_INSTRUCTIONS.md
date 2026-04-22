# Claude Code 遷移作業指令

## 前置準備

1. 把 `CLAUDE.md` 放到 `D:\work\odoo18-docker\addons\CLAUDE.md`
2. 把 v10 prototype 存成 `D:\work\odoo18-docker\addons\v10_prototype.jsx`（給 Claude Code 當設計參考）
3. 把乾淨版 portal 複製過去：
   ```
   把 D:\work\odoo18-docker\ChienYi-18.0\construction_portal\
   複製到 D:\work\odoo18-docker\addons\construction_portal\
   （覆蓋掉原本那個肥的版本）
   ```

## 啟動 Claude Code

```bash
cd D:\work\odoo18-docker\addons
claude
```

Claude Code 會自動讀取 CLAUDE.md 了解專案脈絡。

---

## 遷移步驟 — 一步一步給指令

### 第 1 步：改 CSS 成 dark theme

```
讀取 construction_portal/static/src/css/portal_mobile.css，
改成 dark theme。配色參考 CLAUDE.md 裡的配色系統。

需求：
- 背景色 #0a0c10
- 卡片背景 #1a1e28
- 主文字 #f0f2f8
- 強調色 #f5b740
- 所有 class 加 cy- prefix
- 用 .o_portal scope 避免影響後台
- 保留現有的觸控優化跟 min-height 44px 設定
```

### 第 2 步：加 bottom nav

```
在 portal_templates.xml 裡用 xpath 繼承 portal.portal_layout，
在 body 底部加一個固定的 bottom navigation bar。

5 個 tab：
- 工程資訊 → /my/construction/{project_id}
- 施工日誌 → /之後再加 route
- 照片中心 → /my/construction/{project_id}/photos
- 自主檢查 → /my/construction/{project_id}/inspections
- 缺失改善 → /my/construction/{project_id}/defects

用 dark theme 配色，active tab 用 amber 色，badge 用紅色圓點。
bottom nav 高度 72px，fixed position。
頁面 content 底部要加 padding-bottom 避免被 nav 擋住。

注意：bottom nav 只在有 project context 的頁面顯示，
專案列表頁 /my/construction 不顯示。
用 t-if="project" 控制。
```

### 第 3 步：改首頁 layout

```
改 portal_construction_project_detail template，
參考 v10_prototype.jsx 裡的 renderHome() 函數。

保留 controller 傳進來的變數名（project, inspections, defects, photos），
不要改 controller。

頁面結構：
1. 頂部：工程名稱 + 狀態 badge + 進度百分比
2. Event cards：逾期缺失（紅色）、待檢查指派（amber）
   - 用 t-foreach 跑 defects 裡 state==open 且 is_overdue 的
   - 每張卡有「立即處理」按鈕連到缺失詳情頁
3. 統計卡片：工程進度 / 待改缺失數 / 照片數
4. 功能區塊：自主檢查（最近 5 筆）、缺失（最近 5 筆）

全部用 dark theme，配色參考 CLAUDE.md。
```

### 第 4 步：改缺失列表頁

```
改 portal_defect_templates.xml 裡的缺失列表 template，
參考 v10_prototype.jsx 裡的 DefectListPage。

每張缺失卡片：
- 左邊框 4px 色條表示狀態（open=紅, investigating=amber, action_taken=藍, verified=綠）
- 顯示：缺失編號、描述、位置、狀態 badge
- 逾期的顯示「⚠ 逾期 X 天」紅色文字
- 點擊整張卡片連到詳情頁

頂部加：
- 「+ 提報缺失」按鈕（紅色漸層）
- 共 X 筆 計數
- 預約式工程顯示通報單篩選按鈕（用 t-if）
```

### 第 5 步：改自主檢查列表頁

```
同上邏輯，改 portal_inspection_templates.xml，
參考 v10_prototype.jsx 的 InspectionListPage。
```

### 第 6 步：改照片頁面

```
改 portal_photo_templates.xml，
參考 v10_prototype.jsx 的 PhotoListPage。

照片用 2 欄 grid 顯示，每張有縮圖、名稱、位置。
```

---

## 追加功能（之後再做）

### 施工日誌 route + template
```
現在 controller 裡還沒有施工日誌的 route。
在 portal.py 加：
- GET /my/construction/<id>/logs → 日誌列表
- GET /my/construction/<id>/logs/<log_id> → 日誌表單
- POST /my/construction/log/save → 儲存日誌

然後建 portal_daily_log_templates.xml，
參考 v10 的 LogListPage 和 LogFormPage。
```

### OWL 互動元件
```
建 static/src/js/components/ 目錄，
用 public_components registry 註冊以下 OWL 元件：

1. CollapseSection — 展開/收合區塊
2. InspectionChecklist — 檢查項目的合格/缺失/無此項 toggle
3. PhotoPicker — 照片選取+預覽（用 URL.createObjectURL）
4. YesNoToggle — 是/否切換按鈕

每個元件放 web.assets_frontend bundle。
```

---

## 驗證指令

改完後跑：
```bash
docker compose restart odoo
docker compose exec odoo odoo -u construction_portal --stop-after-init
```

然後開瀏覽器看 /my/construction 確認畫面。
