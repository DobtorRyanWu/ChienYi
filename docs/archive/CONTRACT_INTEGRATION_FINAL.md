# Contract Pay Item 整合最終報告

## 📊 項次顯示格式說明

### 正確的需求理解

從 contract_pay_item 的 XML 解析器可以確認：

**契約工項的層級結構：**
1. **第一層級**（已跳過）：壹、貳、參...（大寫中文數字）
2. **第二層級**（母項次）：一、二、三...（小寫中文數字）
3. **第三層級**（子項次）：1、2、3...（阿拉伯數字）

**顯示需求：**
- **格式**：`母項次,子項次`
- **範例**：一,1、二,3、三,2
- **母項次**：如果沒有子項次，只顯示母項次（例：一）

---

## ✅ 最終修改方案

### 一、test_record 模組

#### 1. contract_item_no 欄位（計算欄位）

```python
contract_item_no = fields.Char(
    string='契約項次',
    compute='_compute_contract_item_no',
    store=False,
    help='顯示格式：母項次,子項次（例：一,1）'
)

@api.depends('material_id', 'material_id.item_no', 'material_id.parent_id', 'material_id.parent_id.item_no')
def _compute_contract_item_no(self):
    """
    計算契約項次顯示
    
    顯示規則：
    - 如果有父項目（子項次）：母項次,子項次（例：一,1）
    - 如果沒有父項目（母項次）：只顯示母項次（例：一）
    """
    for record in self:
        if not record.material_id:
            record.contract_item_no = ''
            continue
        
        pay_item = record.material_id
        
        # 如果是子項次（有父項目）
        if pay_item.parent_id and pay_item.parent_id.item_no:
            # 顯示格式：母項次,子項次
            parent_no = pay_item.parent_id.item_no
            child_no = pay_item.item_no
            record.contract_item_no = f"{parent_no},{child_no}"
        else:
            # 母項次，只顯示自己的編號
            record.contract_item_no = pay_item.item_no or ''
```

**顯示效果：**
- 子項次：`一,1`、`二,3`、`三,2`
- 母項次：`一`、`二`、`三`

#### 2. 報表方法優化

```python
# 準備契約工項資訊（payItem）
pay_item = record.material_id

# 計算項次編號（母項次,子項次格式）
if pay_item.parent_id and pay_item.parent_id.item_no:
    # 子項次：母項次,子項次
    full_item_no = f"{pay_item.parent_id.item_no},{pay_item.item_no}"
else:
    # 母項次：只顯示自己
    full_item_no = pay_item.item_no or ''

pay_item_data = {
    'fullItemNo': full_item_no,
    'quantity': pay_item.quantity or 0.0,
    'description': pay_item.name or pay_item.description or '',
    'unit': pay_item.unit or '',
}
```

**報表顯示效果：**
- 子項次：`一,1`、`二,3`
- 母項次：`一`、`二`

---

## 🎯 顯示範例

### Tree View 顯示

| 契約項次 | 材料名稱 | 契約數量 | 契約單位 |
|---------|---------|---------|---------|
| 一,1 | 混凝土預拌 | 100 | m³ |
| 一,2 | 混凝土澆置 | 100 | m³ |
| 二,1 | 鋼筋加工 | 5000 | kg |
| 二,2 | 鋼筋組立 | 5000 | kg |
| 三 | 工地管理費 | 1 | 式 |

### Form View 下拉選單顯示

選擇檢試驗項目後，材料下拉選單顯示：
```
一,1 - 混凝土預拌
一,2 - 混凝土澆置
二,1 - 鋼筋加工
二,2 - 鋼筋組立
三 - 工地管理費
```

---

## 📋 完整修改檔案清單

### test_record 模組
1. ✅ `models/test_record_data.py`
   - 修改 `contract_item_no` 為計算欄位
   - 新增 `_compute_contract_item_no` 方法
   - 優化 `prepare_template_data` 報表方法

---

## ✅ 功能確認

### 1. 顯示格式正確
- ✅ 子項次顯示：`母項次,子項次`（例：一,1）
- ✅ 母項次顯示：只顯示母項次（例：一）
- ✅ 使用小寫中文數字（一、二、三...）
- ✅ 使用阿拉伯數字（1、2、3...）

### 2. UI 功能保持不變
- ✅ test_standard 連接工項功能正常
- ✅ test_record 選擇契約工項正常
- ✅ Tree View 顯示正確
- ✅ Form View 下拉選單正常
- ✅ 合規性檢查功能正常
- ✅ 報表生成功能正常

### 3. 資料完整性
- ✅ 項次編號：正確格式
- ✅ 工項名稱：完整顯示
- ✅ 數量資訊：準確
- ✅ 單位資訊：完整

---

## 🎉 總結

✅ **項次顯示格式完全符合需求**
- 母項次,子項次格式（一,1、二,3）
- 母項次為小寫中文數字
- 子項次為阿拉伯數字

✅ **所有功能正常運作**
- UI 畫面無任何改變
- 功能邏輯完全保留
- 顯示格式完全正確

✅ **程式碼簡潔可靠**
- 使用計算欄位自動生成
- 無需手動維護
- 易於理解和維護

**整合完成，可以安全部署！** 🎉
