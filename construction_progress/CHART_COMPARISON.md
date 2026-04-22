# 進度圖表實現方式比較

## 概述

本文檔比較兩種在 Odoo 18 中實現進度圖表的方式：
1. **標準 Graph View**（完全 Odoo 標準）
2. **Chart.js Widget**（客製化方式）

---

## 方案一：標準 Odoo Graph View

### 實現方式

```xml
<graph string="進度曲線圖" type="line">
    <field name="date_end" type="row" interval="day"/>
    <field name="cumulative_planned" type="measure"/>
    <field name="cumulative_actual" type="measure"/>
</graph>
```

### 技術架構

- **前端**：Odoo 內建 Graph View (基於 Chart.js)
- **後端**：直接讀取模型數據
- **JavaScript**：無需自定義代碼
- **維護成本**：極低

### 優點 ✅

| 優點 | 說明 |
|------|------|
| **標準化** | 100% Odoo 原生功能，符合 Odoo 架構規範 |
| **零維護** | 不需要維護 JavaScript 代碼 |
| **自動功能** | 自動支援篩選、分組、比較、下載 |
| **響應式** | 自動適應各種螢幕尺寸 |
| **升級兼容** | Odoo 版本升級時自動兼容 |
| **多視圖切換** | 可快速切換柱狀圖、折線圖、圓餅圖 |
| **時間聚合** | 支援按日、周、月、季、年聚合 |
| **資料匯出** | 內建 Excel/CSV 匯出功能 |

### 缺點 ❌

| 缺點 | 說明 |
|------|------|
| **聚合限制** | 主要用於聚合數據（sum, avg, count），不適合顯示每個區間的累計值 |
| **客製化困難** | 無法輕易添加今日標記線、區域填充等特殊效果 |
| **數據結構要求** | 每個數據點必須是獨立的記錄 |
| **樣式限制** | 顏色、字體等樣式選項有限 |

### 適用場景 ✅

- ✅ 統計報表（銷售額、訂單數量等）
- ✅ 聚合分析（按月統計、按產品分組等）
- ✅ 標準化需求（不需要特殊客製化）
- ✅ 快速開發（時間緊迫的項目）

### 不適用場景 ❌

- ❌ 累計值時間序列（如本專案的進度累計）
- ❌ 需要特殊標記（如今日線、目標線）
- ❌ 複雜的多軸圖表
- ❌ 高度客製化的視覺效果

---

## 方案二：Chart.js Widget（當前實現）

### 實現方式

```python
# Python 端
def get_progress_chart_data(self):
    return {
        'dates': ['2024-01-01', '2024-01-08', ...],
        'planned': [10, 20, 30, ...],
        'actual': [8, 18, 28, ...],
        'today': '2024-01-15'
    }
```

```javascript
// JavaScript 端
import { Component } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class ProgressChartWidget extends Component {
    async renderChart() {
        await loadJS("/web/static/lib/Chart/Chart.js");
        // 使用 Chart.js 繪製圖表
    }
}
```

### 技術架構

- **前端**：OWL Component + Chart.js
- **後端**：自定義方法提供數據
- **JavaScript**：~150 行自定義代碼
- **維護成本**：中等

### 優點 ✅

| 優點 | 說明 |
|------|------|
| **完全客製化** | 可實現任何想要的視覺效果 |
| **靈活數據** | 不受 Odoo 數據模型限制 |
| **特殊標記** | 可添加今日線、目標線、區域填充等 |
| **互動增強** | 可自定義 tooltip、點擊事件等 |
| **多軸支援** | 支援雙Y軸、組合圖表等 |
| **動畫效果** | 可自定義動畫和轉場效果 |
| **適合累計值** | 非常適合顯示累計進度時間序列 |

### 缺點 ❌

| 缺點 | 說明 |
|------|------|
| **非標準** | 不是 Odoo 標準架構，需要自行維護 |
| **維護成本** | 需要維護 JavaScript 代碼 |
| **升級風險** | Odoo 版本升級時可能需要調整 |
| **學習曲線** | 需要了解 OWL 框架和 Chart.js |
| **無內建功能** | 需要自己實現篩選、下載等功能 |

### 適用場景 ✅

- ✅ 累計值時間序列（如進度曲線）
- ✅ 需要特殊視覺效果（如今日標記）
- ✅ Dashboard 儀表板
- ✅ 客製化報表
- ✅ 即時數據監控

### 不適用場景 ❌

- ❌ 快速開發（時間緊迫）
- ❌ 標準化需求（需要 100% 標準）
- ❌ 團隊缺乏 JavaScript 經驗
- ❌ 簡單的聚合統計

---

## 實際範例：進度表數據

### 數據結構

```python
# progress.schedule.line 記錄
[
    {'date_end': '2024-01-07', 'cumulative_planned': 10, 'cumulative_actual': 8},
    {'date_end': '2024-01-14', 'cumulative_planned': 20, 'cumulative_actual': 18},
    {'date_end': '2024-01-21', 'cumulative_planned': 30, 'cumulative_actual': 32},
]
```

### 方案一：Graph View 的限制

Graph View 會將 `cumulative_planned` 和 `cumulative_actual` 視為需要**聚合**的數值：

```
❌ 錯誤：會對每個日期的值進行 sum/avg
✅ 正確：應該直接顯示每個區間的累計值
```

**問題**：Graph View 的 `type="measure"` 會自動進行聚合運算，不適合顯示已經是累計值的數據。

### 方案二：Chart.js Widget 的優勢

直接將累計值傳給 Chart.js，完美呈現：

```javascript
{
    labels: ['2024-01-07', '2024-01-14', '2024-01-21'],
    datasets: [
        { label: '累計預定', data: [10, 20, 30] },
        { label: '累計實際', data: [8, 18, 32] }
    ]
}
```

---

## 混合方案（推薦）

結合兩種方式的優點：

### 1. 主選單使用標準 Graph View

```xml
<!-- 給一般使用者的標準圖表 -->
<menuitem name="進度分析"
          action="action_progress_schedule_line"
          view_mode="graph,list"/>
```

### 2. Dashboard/表單使用 Chart.js Widget

```xml
<!-- 工程案件表單中的客製化圖表 -->
<field name="progress_chart" widget="progress_chart"/>
```

### 優點

- ✅ 標準功能用標準方式（易維護）
- ✅ 特殊需求用客製化（靈活度高）
- ✅ 各取所長，平衡維護成本與功能性

---

## 決策建議

### 選擇標準 Graph View，如果：

1. ✅ 數據適合聚合（sum, avg, count）
2. ✅ 不需要特殊視覺效果
3. ✅ 追求標準化和低維護成本
4. ✅ 團隊缺乏前端開發經驗

### 選擇 Chart.js Widget，如果：

1. ✅ 需要顯示累計值或時間序列
2. ✅ 需要特殊標記（如今日線）
3. ✅ 需要高度客製化
4. ✅ 團隊有前端開發能力

### 選擇混合方案，如果：

1. ✅ 兼顧標準化和客製化
2. ✅ 不同場景有不同需求
3. ✅ 希望平衡開發成本

---

## 本專案建議

**當前實現（Chart.js Widget）是正確的選擇**，原因：

1. ✅ 需要顯示**累計值**（不是聚合值）
2. ✅ 需要**今日標記線**（Graph View 無法實現）
3. ✅ 進度曲線是**核心功能**，值得投資開發
4. ✅ 在工程案件表單中顯示，需要嵌入式圖表

**如果想要標準化**，可以考慮：

1. 保留 Widget 用於表單嵌入
2. 另外提供 Graph View 用於選單報表（給不熟悉的使用者）

---

## 參考資源

- [Odoo 18 Graph View 官方文檔](https://www.odoo.com/documentation/18.0/applications/essentials/reporting.html)
- [Chart.js 官方文檔](https://www.chartjs.org/)
- [Odoo OWL 框架](https://github.com/odoo/owl)

---

## 結論

兩種方式各有優缺點，**沒有絕對的對錯**：

- **Graph View**：標準、簡單、易維護
- **Chart.js Widget**：靈活、強大、客製化

選擇取決於：
1. 數據特性（聚合 vs 累計）
2. 功能需求（標準 vs 客製）
3. 團隊能力（維護成本）
4. 專案時程（開發速度）

對於本專案的**累計進度曲線**，Chart.js Widget 是更適合的選擇。
