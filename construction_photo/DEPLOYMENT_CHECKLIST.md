# 快速檢查清單 - 照片自動同步功能

## 📋 檔案修改確認

### ✅ construction_photo 模組

- [x] `models/photo_sync_mixin.py` - 已建立
- [x] `models/__init__.py` - 已更新（加入 photo_sync_mixin import）
- [x] `models/supervision_photo.py` - 已修改：
  - [x] name 改為計算欄位
  - [x] 新增 description 欄位
  - [x] 新增 project_location/latitude/longitude 欄位
  - [x] 新增 _compute_name 方法
  - [x] 新增 _name_search 方法
- [x] `views/supervision_photo_views.xml` - 已修改：
  - [x] Form view 佈局調整
  - [x] 工程位置欄位顯示
  - [x] GPS 頁籤調整
  - [x] 照片預覽尺寸調整（1200x900）
  - [x] Search view 加入 description 欄位

---

### ✅ construction_general 模組

- [x] `models/general_defect_improvement.py`:
  - [x] _inherit 加入 'photo.sync.mixin'
  - [x] 實作 _get_photo_sync_config() 方法
  - [x] 配置 defect_photo_ids 同步
  - [x] 配置 improvement_photo_ids 同步

- [x] `__manifest__.py`:
  - [x] depends 加入 'construction_photo'

---

### ✅ construction_quality 模組

- [x] `models/general_self_inspection.py`:
  - [x] _inherit 加入 'photo.sync.mixin'
  - [x] 實作 _get_photo_sync_config() 方法
  - [x] 配置 photo_ids 同步

- [x] `models/reservation_self_inspection.py`:
  - [x] _inherit 加入 'photo.sync.mixin'
  - [x] 實作 _get_photo_sync_config() 方法
  - [x] 配置 photo_ids 同步

- [x] `models/reservation_defect_improvement.py`:
  - [x] _inherit 加入 'photo.sync.mixin'
  - [x] 實作 _get_photo_sync_config() 方法
  - [x] 配置 defect_photo_ids 同步
  - [x] 配置 improvement_photo_ids 同步

- [x] `__manifest__.py`:
  - [x] depends 加入 'construction_photo'

---

## 🔧 部署前檢查

### 步驟1：檔案完整性確認

```bash
# 檢查所有修改的檔案是否存在
ls -l E:\work\system\addons\construction_photo\models\photo_sync_mixin.py
ls -l E:\work\system\addons\construction_photo\models\supervision_photo.py
ls -l E:\work\system\addons\construction_general\models\general_defect_improvement.py
ls -l E:\work\system\addons\construction_quality\models\general_self_inspection.py
```

### 步驟2：Python 語法檢查

```bash
# 檢查 Python 語法錯誤
python3 -m py_compile E:\work\system\addons\construction_photo\models\photo_sync_mixin.py
python3 -m py_compile E:\work\system\addons\construction_general\models\general_defect_improvement.py
```

### 步驟3：XML 語法檢查

```bash
# 檢查 XML 語法錯誤
xmllint --noout E:\work\system\addons\construction_photo\views\supervision_photo_views.xml
```

---

## 🚀 部署步驟

### 1. 備份資料庫（重要！）

```bash
# PostgreSQL 備份
pg_dump -U odoo18 -d your_database > backup_before_upgrade.sql
```

### 2. 停止 Odoo

```bash
sudo systemctl stop odoo18
```

### 3. 清除 Python Cache

```bash
cd E:\work\system\addons
find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
```

### 4. 啟動 Odoo（開發模式）

```bash
# 使用開發模式啟動，方便查看錯誤
odoo -c /etc/odoo18.conf --dev=all
```

### 5. 升級模組（依序執行）

在 Odoo 介面中：

1. **啟用開發者模式**
   - 設定 > 啟用開發者模式

2. **更新模組列表**
   - 設定 > 技術 > 模組 > 更新模組列表

3. **依序升級模組**：
   ```
   ① construction_photo        （必須先升級）
   ② construction_quality       （第二個）
   ③ construction_general       （最後）
   ```

### 6. 重啟 Odoo（正常模式）

```bash
sudo systemctl start odoo18
sudo systemctl status odoo18
```

---

## ✅ 功能測試清單

### 測試1：缺失改善照片同步

- [ ] 建立一般式缺失改善記錄
- [ ] 填寫缺失說明、缺失位置
- [ ] 上傳缺失照片
- [ ] 儲存記錄
- [ ] 檢查照片管理模組是否有新照片
- [ ] 驗證照片資訊：
  - [ ] 照片說明格式正確
  - [ ] 備註包含缺失說明
  - [ ] 位置資訊正確
  - [ ] 來源分類為「缺失改善」

### 測試2：改善照片同步

- [ ] 在同一筆缺失改善記錄中
- [ ] 上傳改善照片
- [ ] 儲存記錄
- [ ] 檢查照片管理模組
- [ ] 驗證改善照片資訊

### 測試3：自主檢查照片同步

- [ ] 建立一般式自主檢查記錄
- [ ] 選擇檢查類型
- [ ] 填寫檢查地點
- [ ] 上傳檢查照片
- [ ] 儲存記錄
- [ ] 檢查照片管理模組
- [ ] 驗證來源分類為「自主檢查」

### 測試4：預約式模組測試

- [ ] 建立預約式自主檢查
- [ ] 上傳照片並同步
- [ ] 建立預約式缺失改善
- [ ] 上傳照片並同步

### 測試5：照片搜尋功能

- [ ] 在照片管理模組中搜尋 description 內容
- [ ] 搜尋檔案名稱
- [ ] 按來源分類篩選
- [ ] 按工程案件篩選

### 測試6：照片預覽功能

- [ ] 開啟照片記錄
- [ ] 檢查大圖預覽（1200x900）
- [ ] 測試點擊放大功能
- [ ] 檢查工程位置資訊顯示

---

## 🐛 常見錯誤及解決

### 錯誤1: ImportError: cannot import name 'photo_sync_mixin'

**原因**：__init__.py 沒有正確更新

**解決**：
```python
# 確認 construction_photo/models/__init__.py 包含：
from . import photo_sync_mixin
from . import supervision_photo_tag
from . import supervision_photo
```

### 錯誤2: AttributeError: 'photo.sync.mixin' not found

**原因**：construction_photo 模組沒有先升級

**解決**：
1. 先升級 construction_photo
2. 重啟 Odoo
3. 再升級其他模組

### 錯誤3: KeyError: 'description'

**原因**：supervision_photo 欄位結構未更新

**解決**：
1. 確認 supervision_photo.py 已修改
2. 重新升級 construction_photo 模組
3. 檢查資料庫欄位是否建立：
   ```sql
   SELECT column_name 
   FROM information_schema.columns 
   WHERE table_name = 'supervision_photo' 
   AND column_name = 'description';
   ```

### 錯誤4: 照片沒有同步

**檢查項目**：
1. 查看 Odoo 日誌：`grep -i "photo" /var/log/odoo/odoo.log`
2. 確認記錄有 project_id
3. 確認 _get_photo_sync_config() 回傳內容正確
4. 檢查照片欄位名稱是否與配置一致

---

## 📊 驗證資料庫變更

### 檢查 supervision_photo 新欄位

```sql
-- 檢查新欄位是否存在
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'supervision_photo' 
AND column_name IN ('description', 'project_location', 'project_latitude', 'project_longitude')
ORDER BY column_name;

-- 應該回傳：
-- description       | text
-- project_location  | character varying
-- project_latitude  | numeric
-- project_longitude | numeric
```

### 檢查同步的照片記錄

```sql
-- 查看最近同步的照片
SELECT 
    sp.id,
    sp.description,
    sp.source_model,
    sp.source_id,
    sp.create_date,
    sp.create_uid
FROM supervision_photo sp
ORDER BY sp.create_date DESC
LIMIT 10;
```

---

## 📝 升級日誌範本

```
升級日期：_________________
執行人：___________________
資料庫備份：_______________

□ 步驟1：資料庫備份完成
□ 步驟2：Odoo 服務停止
□ 步驟3：Python Cache 清除
□ 步驟4：Odoo 開發模式啟動成功
□ 步驟5：construction_photo 升級成功
□ 步驟6：construction_quality 升級成功
□ 步驟7：construction_general 升級成功
□ 步驟8：Odoo 正常模式啟動成功

測試結果：
□ 缺失改善照片同步 - 正常/異常
□ 改善照片同步 - 正常/異常
□ 自主檢查照片同步 - 正常/異常
□ 照片搜尋功能 - 正常/異常
□ 照片預覽功能 - 正常/異常

問題記錄：
________________________________
________________________________
________________________________

備註：
________________________________
________________________________
```

---

## 🎯 成功標準

全部功能正常運作才算成功：

✅ **必須通過的測試**：
1. 缺失改善上傳照片後，照片管理模組自動建檔
2. 照片資訊完整（說明、位置、來源分類）
3. 照片搜尋功能正常
4. 照片大圖預覽正常
5. 工程位置資訊正確顯示
6. 沒有Python錯誤或警告
7. 資料庫查詢效能正常（< 100ms）

---

**準備好了嗎？開始部署吧！** 🚀
