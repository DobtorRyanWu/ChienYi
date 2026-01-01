# 工程監造系統 - Portal 入口

> Construction Supervision System - Portal Extension

## 模組資訊

| 項目 | 內容 |
|------|------|
| **技術名稱** | `construction_portal` |
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Portal |
| **授權** | LGPL-3 |
| **依賴** | `portal`, `construction_supervision_base`, `construction_quality`, `construction_photo` |

## 功能說明

此模組提供 Portal 用戶（承包廠商聯絡人）的前台操作功能，讓承包廠商可以透過網頁介面參與工程管理。

### 主要功能

1. **工程案件瀏覽**
   - 查看關聯的工程案件列表
   - 工程案件詳情與統計資訊
   - 自動篩選承包廠商關聯的工程

2. **自主檢查管理**
   - 新增自主檢查表
   - 查看歷史檢查記錄
   - 選擇檢查類型自動帶入項目

3. **缺失改善提交**
   - 查看待處理缺失清單
   - 填寫改善說明
   - 追蹤改善進度

4. **照片上傳**
   - 上傳工程照片
   - 照片分類與說明
   - 照片瀏覽與下載

## 操作說明

### 1. 設定承包廠商 Portal 用戶

1. 進入「聯絡人」應用程式
2. 找到承包廠商的聯絡人
3. 點擊「動作」→「授予 Portal 存取權」
4. 確認該聯絡人的公司已設定為承包廠商

### 2. 關聯工程案件

1. 進入工程案件
2. 在「承包廠商」欄位加入廠商公司
3. Portal 用戶即可看到該工程

### 3. Portal 用戶操作

Portal 用戶登入後，在「我的帳號」頁面可以：

#### 查看工程案件
- 路徑：`/my/construction`
- 顯示所有關聯的工程案件
- 點擊查看詳情

#### 新增自主檢查
- 路徑：`/my/construction/{id}/inspection/new`
- 選擇檢查類型
- 填寫檢查日期與地點
- 提交後自動通知監造人員

#### 提交缺失改善
- 路徑：`/my/construction/defect/{id}`
- 查看缺失詳情與照片
- 填寫改善說明
- 提交後自動發送通知

#### 上傳照片
- 路徑：`/my/construction/{id}/photo/upload`
- 選擇照片檔案
- 填寫拍攝日期與說明
- 支援 JPG、PNG、GIF 格式

## Portal 路由

| 路徑 | 說明 |
|------|------|
| `/my/construction` | 工程案件列表 |
| `/my/construction/{id}` | 工程案件詳情 |
| `/my/construction/{id}/inspections` | 自主檢查列表 |
| `/my/construction/{id}/inspection/new` | 新增自主檢查 |
| `/my/construction/inspection/{id}` | 自主檢查詳情 |
| `/my/construction/{id}/defects` | 缺失列表 |
| `/my/construction/defect/{id}` | 缺失詳情/改善 |
| `/my/construction/{id}/photos` | 照片列表 |
| `/my/construction/{id}/photo/upload` | 上傳照片 |
| `/my/construction/photo/{id}` | 照片詳情 |

## 技術說明

### 模型擴展

| 模型 | 擴展內容 |
|------|----------|
| `supervision.project` | 繼承 `portal.mixin`，新增 Portal 統計欄位 |
| `general.self.inspection` | 繼承 `portal.mixin`，新增 Portal 建立者欄位 |
| `supervision.defect` | 繼承 `portal.mixin`，新增 Portal 改善欄位 |
| `supervision.photo` | 繼承 `portal.mixin`，新增 Portal 上傳者欄位 |

### 新增欄位

**supervision.project**
- `inspection_count` - 自主檢查數（計算欄位）
- `defect_count` - 缺失數（計算欄位）
- `open_defect_count` - 待處理缺失數（計算欄位）
- `photo_count` - 照片數（計算欄位）

**general.self.inspection**
- `portal_creator_id` - Portal 填表人
- `is_portal_created` - 是否 Portal 建立

**supervision.defect**
- `portal_improver_id` - Portal 改善人
- `portal_improvement_note` - Portal 改善說明
- `portal_updated_date` - Portal 更新時間

**supervision.photo**
- `portal_uploader_id` - Portal 上傳者
- `is_portal_uploaded` - 是否 Portal 上傳

### 存取規則

Portal 用戶的存取權限：

- **讀取**：可查看其公司為承包廠商的工程案件及相關資料
- **寫入**：透過專用方法（`create_from_portal`、`portal_submit_improvement`）進行操作
- **建立/刪除**：不允許直接建立或刪除記錄

## 安全性

- 所有 Portal 操作都經過權限驗證
- 使用 `sudo()` 執行需要較高權限的操作
- 記錄 Portal 用戶的操作軌跡
- CSRF 保護已啟用

## 注意事項

1. **Portal 用戶設定**
   - 確保聯絡人已正確關聯到公司
   - 公司必須在工程案件的承包廠商欄位中

2. **工程案件狀態**
   - 草稿、已終止狀態的工程不會顯示
   - Portal 用戶只能查看進行中的工程

3. **照片上傳**
   - 建議圖片大小不超過 10MB
   - 系統自動記錄上傳來源為「其他」

## 版本歷程

### 18.0.1.0.0
- 初始版本
- 工程案件 Portal 存取
- 自主檢查填寫功能
- 缺失改善提交功能
- 照片上傳功能
