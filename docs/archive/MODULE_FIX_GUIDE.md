# 🔧 Odoo 18 模組修復完整指南

## 🎯 根本問題診斷

經過全面檢查，發現以下核心問題：

### 1. project_key 識別碼生成問題

**問題**：子模組定義的 `_get_task_key_prefix()` 方法**不會被 project_key 調用**！

project_key 的 `project.task.create()` 直接調用：
```python
vals["key"] = project.get_next_task_key()  # 生成格式：PROJECT_KEY-001
```

而子模組期望的格式是：
- contract.pay.item: `{PROJECT_KEY}-PAY-001`
- daily.record: `{PROJECT_KEY}-DAILY-001`
- inspection: `{PROJECT_KEY}-INS-001`

### 2. 解決方案

每個繼承 project.task 的模組**必須在 create() 方法中自己生成 key**，在調用 `super().create()` **之前**設置 key。

---

## 📋 需要修正的模組清單

| 模組 | 模型 | 識別碼格式 | 狀態 |
|------|------|-----------|------|
| contract_pay_item | contract.pay.item | {PROJECT}-PAY-001 | ⚠️ 需檢查 |
| daily_record | daily.record | {PROJECT}-DAILY-001 | ⚠️ 需檢查 |
| inspection | inspection | {PROJECT}-INS-001 | ⚠️ 需檢查 |
| test_record | test.record | {PROJECT}-record-001 | ⚠️ 需檢查 |
| test_standard | test.standard | {PROJECT}-standard-001 | ⚠️ 需檢查 |
| template_setting | template.setting | {PROJECT}-PLATE-001 | ⚠️ 需檢查 |
| ReviewApplication | review.application | {PROJECT}-RA-001 | ⚠️ 需檢查 |
| ErrorRecord | deficiency.improvement | {PROJECT}-ERROR-001 | ⚠️ 需檢查 |
| file | file.file | {PROJECT}-FILE-001 | ⚠️ 需檢查 |
| image | image.record | {PROJECT}-IMG-001 | ⚠️ 需檢查 |
| inspection_type | inspection.type | {PROJECT}-INSTYPE-001 | ⚠️ 需檢查 |

---

## 🔨 標準修復模式

每個繼承 project.task 的模組都必須：

### 1. 正確處理 Many2many 欄位

```python
# 必須重新定義這些欄位，使用唯一的 relation 名稱
user_ids = fields.Many2many(
    'res.users',
    'your_module_user_rel',  # 唯一表名
    'record_id',
    'user_id',
    string='負責人'
)

depend_on_ids = fields.Many2many(
    'project.task',
    'your_module_dependency_rel',  # 唯一表名
    'record_id',
    'depend_id',
    string='前置任務'
)

dependent_ids = fields.Many2many(
    'project.task',
    'your_module_dependency_rel',  # 與 depend_on_ids 相同
    'depend_id',
    'record_id',
    string='後續任務',
)

# 禁用不需要的欄位
personal_stage_type_ids = fields.Many2many(relation=False)

tag_ids = fields.Many2many(
    'project.tags',
    'your_module_tag_rel',  # 唯一表名
    'record_id',
    'tag_id',
    string='標籤',
)
```

### 2. 正確的 create() 方法

```python
@api.model
def create(self, vals):
    """創建記錄時自己生成 key"""
    # 1. 處理 project_id
    if 'project_id' not in vals:
        project_id = self.env.context.get('default_project_id')
        if not project_id and self.env.context.get('active_model') == 'project.project':
            project_id = self.env.context.get('active_id')
        if project_id:
            vals['project_id'] = project_id
        else:
            raise ValidationError("必須指定所屬專案")
    
    # 2. 在 super().create() 之前生成 key
    if 'key' not in vals or not vals.get('key'):
        project = self.env['project.project'].browse(vals['project_id'])
        vals['key'] = self._generate_custom_key(project)
    
    # 3. 調用父類
    return super().create(vals)

def _generate_custom_key(self, project):
    """生成自定義識別碼"""
    if not project or not project.key:
        raise ValidationError("專案沒有有效的識別碼")
    
    prefix = f"{project.key}-YOUR_SUFFIX"  # 如 PAY, DAILY, INS 等
    
    # 查找該專案下同類型的最後一筆記錄
    last_record = self.search([
        ('key', '=like', f'{prefix}-%')
    ], order='key desc', limit=1)
    
    next_seq = 1
    if last_record and last_record.key:
        try:
            last_seq = int(last_record.key.split('-')[-1])
            next_seq = last_seq + 1
        except (ValueError, IndexError):
            pass
    
    return f"{prefix}-{next_seq:03d}"
```

---

## 🚀 一勞永逸的安裝順序

### 正確的安裝順序（從基礎到高階）：

```bash
# 第 1 層：無自定義依賴
project_key
web_leaflet_lib
dms
progress_schedule

# 第 2 層：依賴第 1 層
base_geoengine  # 依賴 base, web
dms_field       # 依賴 dms

# 第 3 層：依賴第 2 層
project_id      # 依賴 project_key, base_geoengine

# 第 4 層：依賴 project_id
file            # 依賴 dms, project_id, project_key
image           # 依賴 dms_field, project_id, project_key
template_setting
contract_pay_item
inspection_type
project_report
project_construction
ReviewApplication

# 第 5 層：依賴第 4 層
project_main
project_workspace
ErrorRecord     # 依賴 image, template_setting
inspection      # 依賴 inspection_type, image, template_setting
test_standard   # 依賴 contract_pay_item

# 第 6 層
test_record     # 依賴 test_standard, contract_pay_item
daily_record    # 依賴 progress_schedule, inspection_type

# 第 7 層
daily_record_integration  # 依賴 daily_record

# 最後
base_system     # 所有模組的彙整包
```

---

## 📝 Docker-compose.yml 正確配置

```yaml
# 開發模式（不要用 --stop-after-init）
command: odoo -d odoo18_dev --update=all

# 安裝特定模組
command: odoo -d odoo18_dev -i project_key,web_leaflet_lib,base_geoengine,dms,dms_field,project_id
```

---

## 🔍 快速診斷命令

在容器內執行：
```bash
# 進入容器
docker exec -it odoo18 bash

# 測試 Python 語法
python3 -c "import sys; sys.path.insert(0, '/mnt/extra-addons'); import contract_pay_item"

# 查看 Odoo 日誌
tail -f /var/log/odoo/odoo.log
```

---

## ⚠️ 常見錯誤和解決方案

### 1. Many2many 關係表衝突
```
Error: duplicate key value violates unique constraint
```
**解決**：確保每個模組的 Many2many 欄位都有唯一的 relation 名稱

### 2. Key 生成失敗
```
Error: project.get_next_task_key() returned None
```
**解決**：在 create() 方法中自己生成 key

### 3. 視圖載入失敗
```
Error: Element '<tree' cannot be located in parent view
```
**解決**：Odoo 18 使用 `<list>` 而不是 `<tree>`

### 4. 欄位繼承衝突
```
Error: Field `personal_stage_type_ids` already defined
```
**解決**：添加 `personal_stage_type_ids = fields.Many2many(relation=False)`

---

## 📌 最終建議

1. **分層安裝**：按照上述順序逐層安裝模組
2. **每層測試**：每安裝一層後測試功能
3. **日誌監控**：始終查看 Odoo 日誌找出具體錯誤
4. **備份資料庫**：每次大規模安裝前備份

如果遵循這個指南，您的模組安裝問題將一勞永逸地解決！
