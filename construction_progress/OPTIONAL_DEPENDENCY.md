# 進度表模組：可選依賴說明

## 概述

`construction_progress` 模組採用**可選依賴（Optional Dependency）**設計，對 `construction_contract_change` 模組的依賴是可選的。

---

## 設計理念

### 為什麼使用可選依賴？

**進度表變更的原因不只是契約變更！**

實際工程中，進度表需要重新規劃的原因包括：

| 變更原因 | 說明 | 是否需要契約變更單 |
|----------|------|-------------------|
| 契約變更 | 工期展延、範圍變更、金額變更 | ✅ 是 |
| 設計變更 | 設計圖調整、規格變更 | ❌ 否 |
| 施工方法調整 | 施工順序、工法改變 | ❌ 否 |
| 業主要求 | 業主臨時需求調整 | ❌ 否 |
| 天候因素 | 颱風、豪雨等不可抗力 | ❌ 否 |
| 資源調配 | 人力、機具調整 | ❌ 否 |
| 其他原因 | 各種非契約性調整 | ❌ 否 |

因此，將契約變更作為**可選功能**更符合實際需求。

---

## 功能說明

### 核心功能（無需契約變更模組）

以下功能**永遠可用**，不需要安裝 `construction_contract_change` 模組：

1. ✅ **版本管理**
   - 創建多版本進度表
   - 記錄版本號、變更日期
   - 填寫變更原因

2. ✅ **圖表顯示**
   - 顯示跨版本進度曲線
   - 標記版本變更點（紫色虛線）
   - Tooltip 顯示變更原因

3. ✅ **進度追蹤**
   - 預定進度與實際進度對比
   - 今日標記
   - 差異分析

### 增強功能（需要契約變更模組）

安裝 `construction_contract_change` 模組後，額外獲得：

1. ✅ **契約變更關聯**
   - 關聯契約變更單到進度表版本
   - 在圖表 Tooltip 中顯示變更單編號

2. ✅ **過時檢查**
   - 自動檢測未處理的契約變更單
   - 提示更新進度表

---

## 技術實現

### 1. 欄位定義（可選）

```python
# models/progress_schedule.py

# === 基本欄位（永遠可用）===
version = fields.Integer(...)
change_date = fields.Date(...)
change_reason = fields.Text(...)  # 任何原因都可以填寫

# === 可選欄位（需要契約變更模組）===
related_change_order_ids = fields.Many2many(
    'contract.change.order',  # ← 如果模組未安裝，此欄位會被忽略
    string='對應的契約變更單',
    help='【可選功能】...',
)
```

### 2. 安全檢查

```python
@api.depends('project_id', 'state', 'related_change_order_ids')
def _compute_is_outdated(self):
    """檢查是否過時（安全檢查）"""

    # ✅ 安全檢查：模組是否已安裝
    if 'contract.change.order' not in self.env:
        # 模組未安裝，跳過檢查
        for schedule in self:
            schedule.is_outdated = False
        return

    # 模組已安裝，執行正常檢查
    ContractChange = self.env['contract.change.order']
    # ... 後續邏輯
```

### 3. 圖表數據（安全處理）

```python
def get_progress_chart_data(self):
    """獲取圖表數據"""

    for schedule in all_schedules:
        if schedule.version > 1:
            change_info = {
                'date': schedule.change_date,
                'version': schedule.version,
                'reason': schedule.change_reason,  # ← 永遠可用
                # ✅ 安全處理：如果欄位不存在，返回空列表
                'change_orders': [
                    co.name for co in schedule.related_change_order_ids
                ] if schedule.related_change_order_ids else [],
            }
```

---

## 使用場景

### 場景一：未安裝契約變更模組

**情況：**
- 只安裝 `construction_progress`
- 未安裝 `construction_contract_change`

**功能：**
```python
# 創建進度表
schedule_v2 = env['progress.schedule'].create({
    'project_id': project.id,
    'version': 2,
    'change_date': '2024-01-15',
    'change_reason': '設計變更：結構調整',  # ✅ 手動填寫原因
    # related_change_order_ids 欄位不存在或被忽略
})
```

**圖表效果：**
- ✅ 顯示版本變更點（紫色虛線）
- ✅ Tooltip 顯示變更原因
- ❌ 不顯示契約變更單（因為沒有）

### 場景二：已安裝契約變更模組

**情況：**
- 安裝 `construction_progress`
- 安裝 `construction_contract_change`

**功能：**
```python
# 創建契約變更單
change_order = env['contract.change.order'].create({
    'project_id': project.id,
    'name': '契約變更單-001',
})

# 創建進度表（可關聯變更單）
schedule_v2 = env['progress.schedule'].create({
    'project_id': project.id,
    'version': 2,
    'change_date': '2024-01-15',
    'change_reason': '工期展延 30 天',
    'related_change_order_ids': [(6, 0, [change_order.id])],  # ✅ 可關聯
})
```

**圖表效果：**
- ✅ 顯示版本變更點（紫色虛線）
- ✅ Tooltip 顯示變更原因
- ✅ Tooltip 顯示契約變更單編號

### 場景三：混合使用

**情況：**
- 有些變更有契約變更單
- 有些變更沒有契約變更單

**功能：**
```python
# v2: 契約變更（有變更單）
schedule_v2 = env['progress.schedule'].create({
    'version': 2,
    'change_reason': '工期展延',
    'related_change_order_ids': [(6, 0, [co1.id])],  # 有關聯
})

# v3: 設計變更（無變更單）
schedule_v3 = env['progress.schedule'].create({
    'version': 3,
    'change_reason': '設計變更：結構調整',
    'related_change_order_ids': [],  # 無關聯
})

# v4: 施工調整（無變更單）
schedule_v4 = env['progress.schedule'].create({
    'version': 4,
    'change_reason': '施工方法調整：改用新工法',
    'related_change_order_ids': [],  # 無關聯
})
```

**圖表效果：**
- ✅ v2 顯示契約變更單
- ✅ v3, v4 不顯示契約變更單
- ✅ 所有版本都顯示變更原因

---

## 視圖設計

### 進度表表單

```xml
<!-- 基本資訊（永遠顯示）-->
<group string="基本資訊">
    <field name="version"/>
    <field name="change_date"/>
    <field name="change_reason"
           placeholder="請說明變更原因（如：契約變更、設計變更、施工調整等）"/>
</group>

<!-- 契約變更資訊（可選，只有填寫時才顯示）-->
<group string="契約變更資訊（可選）"
       invisible="not related_change_order_ids and state == 'draft'">
    <field name="related_change_order_ids"
           help="【可選功能】選擇對應的契約變更單..."/>
</group>
```

---

## 部署建議

### 最小部署（基本功能）

```bash
# 只安裝進度表模組
odoo-bin -i construction_progress -d your_database
```

**可用功能：**
- ✅ 版本管理
- ✅ 進度圖表
- ✅ 版本變更點標記
- ❌ 契約變更關聯

### 完整部署（所有功能）

```bash
# 同時安裝進度表和契約變更模組
odoo-bin -i construction_progress,construction_contract_change -d your_database
```

**可用功能：**
- ✅ 版本管理
- ✅ 進度圖表
- ✅ 版本變更點標記
- ✅ 契約變更關聯
- ✅ 過時檢查

---

## 優點與限制

### ✅ 優點

1. **靈活性**：根據實際需求選擇是否使用契約變更功能
2. **獨立性**：進度表模組可以獨立運作
3. **相容性**：安裝契約變更模組後自動啟用增強功能
4. **真實性**：符合實際業務（變更不一定源於契約）

### ⚠️ 限制

1. **手動關聯**：需要手動關聯契約變更單（不會自動）
2. **無自動化**：契約變更時不會自動創建新進度表
3. **需要文檔**：使用者需要了解可選功能的存在

---

## 未來增強方向

### 如果需要自動化

可以考慮在 `construction_contract_change` 模組中添加：

```python
# models/contract_change_order.py

def action_approve(self):
    """核准契約變更單時，提示創建新進度表"""
    res = super().action_approve()

    # 檢查是否需要更新進度表
    if self.affects_schedule:
        return {
            'type': 'ir.actions.act_window',
            'name': '建議更新進度表',
            'res_model': 'progress.schedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.project_id.id,
                'default_change_order_id': self.id,
            }
        }

    return res
```

這樣就能在契約變更核准時，**建議**（而非強制）創建新進度表。

---

## 總結

`construction_progress` 模組採用**可選依賴**設計：

| 特性 | 說明 |
|------|------|
| **核心功能** | 無需依賴，獨立運作 ✅ |
| **增強功能** | 安裝契約變更模組後自動啟用 ✅ |
| **靈活性** | 根據需求選擇功能 ✅ |
| **安全性** | 模組未安裝時不會報錯 ✅ |
| **擴展性** | 未來可添加更多可選功能 ✅ |

這種設計讓模組既能獨立使用，又能與其他模組無縫整合，是 Odoo 模組化架構的最佳實踐。
