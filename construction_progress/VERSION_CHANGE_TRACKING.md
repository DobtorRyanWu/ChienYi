# 進度圖表：契約變更追蹤功能

## 功能概述

本模組的進度圖表現在支援**跨版本顯示**和**契約變更點標記**，可以完整呈現工程進度因契約變更而產生的轉折點。

---

## 業務邏輯

### 1. 版本管理機制

```
專案
├── 進度表 v1 (原始版本)
│   ├── 區間 1: 2024-01-01 ~ 2024-01-07, 預定 10%
│   ├── 區間 2: 2024-01-08 ~ 2024-01-14, 預定 10%
│   └── ...
│
├── 契約變更單-001 (2024-01-15 核准)
│   └── 工期展延 30 天
│
└── 進度表 v2 (變更後版本) ← 轉折點
    ├── 變更日期: 2024-01-15
    ├── 變更原因: "工期展延"
    ├── 對應變更單: [契約變更單-001]
    ├── 區間 1: 2024-01-01 ~ 2024-01-07, 預定 8%  ← 調整後
    ├── 區間 2: 2024-01-08 ~ 2024-01-14, 預定 8%  ← 調整後
    └── ...
```

### 2. 圖表呈現

```
進度 (%)
100 ┤
    │
 80 ┤                    ╱────────      藍線：累計預定進度
    │                  ╱│                紅線：累計實際進度
 60 ┤                ╱  │ v2             黃線：今日標記
    │              ╱    │                紫線：契約變更點
 40 ┤            ╱      │
    │          ╱        │
 20 ┤        ╱          │
    │      ╱            │
  0 ┼────────────────────┼───────────→ 時間
         v1              變更點
```

---

## 技術實現

### 1. 後端數據處理

#### [supervision_project.py](./models/supervision_project.py)

```python
def get_progress_chart_data(self):
    """獲取跨版本進度數據"""

    # 1. 獲取所有版本的進度表
    all_schedules = self.schedule_ids.sorted('version')

    # 2. 遍歷每個版本
    for schedule in all_schedules:
        # 記錄版本變更點
        if schedule.version > 1:
            version_changes.append({
                'date': schedule.change_date,
                'version': schedule.version,
                'reason': schedule.change_reason,
                'change_orders': [契約變更單清單],
            })

        # 收集進度數據
        for line in schedule.line_ids:
            data_points.append({
                'date': line.date_end,
                'planned': line.cumulative_planned,
                'actual': line.cumulative_actual,
            })

    # 3. 返回完整數據
    return {
        'dates': [...],
        'planned': [...],
        'actual': [...],
        'version_changes': [...],  # ← 新增
    }
```

### 2. 前端圖表渲染

#### [progress_chart.js](./static/src/components/progress_chart/progress_chart.js)

```javascript
drawChart(data) {
    // 1. 準備標註
    const annotations = {};

    // 2. 今日標記線（橘色虛線）
    annotations.todayLine = {
        type: "line",
        xMin: todayIndex,
        xMax: todayIndex,
        borderColor: "#F39C12",
        borderDash: [5, 5],
        label: { content: "今日" }
    };

    // 3. 契約變更標記線（紫色虛線）
    data.version_changes.forEach((change, index) => {
        annotations[`versionChange${index}`] = {
            type: "line",
            xMin: changeIndex,
            xMax: changeIndex,
            borderColor: "#9B59B6",
            borderDash: [10, 5],
            label: {
                content: `v${change.version}`,
                backgroundColor: "#9B59B6"
            }
        };
    });

    // 4. 繪製圖表
    new Chart(ctx, {
        options: {
            plugins: {
                annotation: { annotations }
            }
        }
    });
}
```

---

## 視覺設計

### 顏色規範

| 元素 | 顏色 | 樣式 | 說明 |
|------|------|------|------|
| 累計預定進度 | 藍色 #00A7E1 | 實線，粗 3px | 原始或調整後的預定進度 |
| 累計實際進度 | 紅色 #E74C3C | 實線，粗 3px | 實際施工進度 |
| 今日標記 | 橘色 #F39C12 | 虛線 [5, 5] | 當前日期位置 |
| 契約變更點 | 紫色 #9B59B6 | 虛線 [10, 5] | 進度表版本變更 |

### 標籤設計

```
┌─────────────────────────────────────┐
│  工程進度曲線圖                      │
├─────────────────────────────────────┤
│                                     │
│  [圖表區域]                          │
│    │                                │
│    │  ┊ 今日  ┊ v2                  │
│    │          ↑                     │
│    └──────────變更點                │
│                                     │
├─────────────────────────────────────┤
│ ─── 累計預定  ─── 累計實際          │
│ ┄┄┄ 今日      ┈┈┈ 契約變更點       │
├─────────────────────────────────────┤
│ 💡 提示：滑鼠移到變更點可查看詳情   │
└─────────────────────────────────────┘
```

---

## 互動功能

### 1. Tooltip 顯示

當滑鼠移到圖表上時，顯示：

```
2024-01-15
累計預定進度: 20.00%
累計實際進度: 18.50%

📋 進度表版本 v2
工期展延
契約變更：契約變更單-001, 契約變更單-002
```

### 2. 標記點顏色

- **綠色區域**：實際進度超前預定進度
- **紅色區域**：實際進度落後預定進度

---

## 使用場景

### 場景 1：單一版本（無契約變更）

```python
# 專案只有一個進度表版本
schedule_ids = [v1]

# 圖表顯示
- 藍線：v1 的預定進度
- 紅線：實際進度
- 橘色虛線：今日標記
- 無紫色虛線（無契約變更）
```

### 場景 2：多版本（有契約變更）

```python
# 專案有多個進度表版本
schedule_ids = [v1, v2, v3]

# 圖表顯示
- 藍線：v1 → v2 → v3 的預定進度（連續曲線）
- 紅線：實際進度
- 橘色虛線：今日標記
- 紫色虛線：v2 和 v3 的變更點
```

### 場景 3：契約變更導致進度調整

```
時間軸：
  v1: 原定 100 天完成，每天 1%
  ↓
  [契約變更: 工期展延 50 天]
  ↓
  v2: 調整為 150 天完成，每天 0.67%

圖表效果：
  - 在變更點會看到藍線斜率改變（轉折點）
  - 紫色虛線標記變更點
  - Tooltip 顯示變更原因
```

---

## 數據範例

### 輸入數據

```python
{
    'dates': [
        '2024-01-07',  # v1 區間 1
        '2024-01-14',  # v1 區間 2
        '2024-01-15',  # v2 變更點
        '2024-01-21',  # v2 區間 1
        '2024-01-28',  # v2 區間 2
    ],
    'planned': [10, 20, 20, 28, 36],  # 在變更點後斜率改變
    'actual': [8, 18, 18, 25, 34],
    'today': '2024-01-20',
    'version_changes': [
        {
            'date': '2024-01-15',
            'version': 2,
            'reason': '工期展延 30 天',
            'change_orders': ['契約變更單-001']
        }
    ]
}
```

### 圖表輸出

```
進度 (%)
 40 ┤           ╱────╱ (v2, 較平緩)
    │         ╱    ╱
 30 ┤       ╱    ╱
    │     ╱    ╱
 20 ┤   ╱    ╱│ v2 (紫色虛線)
    │ ╱    ╱  │
 10 ┤╱    ╱   │
    │   ╱     │
  0 ┼─────────┼────────→ 時間
      v1      變更點
   (較陡峭)
```

---

## 優點與限制

### ✅ 優點

1. **完整歷程**：顯示所有版本的進度數據
2. **清楚標記**：契約變更點一目了然
3. **互動查詢**：Tooltip 顯示變更詳情
4. **視覺化轉折**：可清楚看到預定進度因變更而調整

### ⚠️ 限制

1. **數據連續性**：假設版本之間數據連續
2. **重疊處理**：如果同一天有多個版本，取最新版本的數據
3. **實際進度**：只顯示已核准的施工日誌數據

---

## 測試場景

### 測試 1：創建第一個版本

```python
# 1. 創建進度表 v1
schedule_v1 = env['progress.schedule'].create({
    'project_id': project.id,
    'version': 1,
})

# 2. 加入進度明細
schedule_v1.line_ids = [
    (0, 0, {'date_end': '2024-01-07', 'planned_progress': 10}),
    (0, 0, {'date_end': '2024-01-14', 'planned_progress': 10}),
]

# 3. 啟用
schedule_v1.action_activate()

# 預期結果：
# - 圖表顯示藍線（v1 預定進度）
# - 無紫色虛線（無契約變更）
```

### 測試 2：契約變更，創建第二個版本

```python
# 1. 創建契約變更單
change_order = env['contract.change.order'].create({
    'project_id': project.id,
    'name': '契約變更單-001',
})

# 2. 創建進度表 v2
schedule_v2 = env['progress.schedule'].create({
    'project_id': project.id,
    'version': 2,
    'change_date': '2024-01-15',
    'change_reason': '工期展延 30 天',
    'related_change_order_ids': [(6, 0, [change_order.id])],
})

# 3. 加入調整後的進度明細
schedule_v2.line_ids = [
    (0, 0, {'date_end': '2024-01-21', 'planned_progress': 8}),
    (0, 0, {'date_end': '2024-01-28', 'planned_progress': 8}),
]

# 4. 啟用
schedule_v2.action_activate()

# 預期結果：
# - 圖表顯示 v1 + v2 的完整預定進度
# - 在 2024-01-15 顯示紫色虛線標記
# - 標籤顯示 "v2"
# - Tooltip 顯示變更原因和變更單
```

---

## 進階功能建議

### 未來可能的增強

1. **區域填充**：預定與實際進度之間填色（超前用綠色，落後用紅色）
2. **目標線**：顯示合約要求的目標進度
3. **預測線**：根據當前進度預測完工日期
4. **版本比較**：並排顯示不同版本的預定進度
5. **匯出功能**：將圖表匯出為 PNG 或 PDF

---

## 相關文件

- [README.md](./README.md) - 模組主要說明
- [CHART_COMPARISON.md](./CHART_COMPARISON.md) - 圖表方案比較
- [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) - 實現指南

---

## 總結

此功能完美解決了**契約變更導致進度調整**的視覺化需求，讓使用者可以：

1. ✅ 清楚看到進度曲線的轉折點
2. ✅ 了解每個轉折點的變更原因
3. ✅ 追蹤完整的進度歷程
4. ✅ 快速識別超前或落後狀態

這正是您示意圖中想要表達的效果！
