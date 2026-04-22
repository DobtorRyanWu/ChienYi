# 圖表實現指南

## 快速決策流程圖

```
開始
  │
  ├─ 需要顯示累計值？
  │   ├─ 是 → 使用 Chart.js Widget ✅
  │   └─ 否 → 需要聚合統計（sum/avg）？
  │        ├─ 是 → 使用 Graph View ✅
  │        └─ 否 → 使用 Chart.js Widget
  │
  ├─ 需要今日標記線或特殊標記？
  │   ├─ 是 → 使用 Chart.js Widget ✅
  │   └─ 否 → 繼續
  │
  ├─ 追求標準化和零維護？
  │   ├─ 是 → 使用 Graph View ✅
  │   └─ 否 → 使用 Chart.js Widget
  │
  └─ 團隊有前端開發經驗？
      ├─ 是 → 可選擇任一方式
      └─ 否 → 建議使用 Graph View
```

---

## 實際代碼對比

### 情境：顯示進度曲線

#### 方案一：Graph View（標準）

**步驟 1：創建視圖（僅需 XML）**

```xml
<!-- views/progress_schedule_graph_views.xml -->
<record id="view_progress_line_graph" model="ir.ui.view">
    <field name="name">progress.schedule.line.graph</field>
    <field name="model">progress.schedule.line</field>
    <field name="arch" type="xml">
        <graph string="進度圖" type="line">
            <field name="date_end" type="row"/>
            <field name="cumulative_planned" type="measure"/>
            <field name="cumulative_actual" type="measure"/>
        </graph>
    </field>
</record>
```

**步驟 2：加入選單**

```xml
<menuitem id="menu_progress_graph"
          name="進度圖表"
          action="action_progress_graph"/>
```

**完成！** 總共約 20 行 XML，無需 Python 或 JavaScript。

**效果：**
- ✅ 自動生成圖表
- ✅ 內建篩選、分組、下載
- ✅ 響應式設計
- ❌ 但會對數值進行聚合（不適合累計值）
- ❌ 無法加今日標記線

---

#### 方案二：Chart.js Widget（客製化）

**步驟 1：Python 方法（models/supervision_project.py）**

```python
def get_progress_chart_data(self):
    """獲取圖表數據"""
    self.ensure_one()

    if not self.active_schedule_id:
        return {'dates': [], 'planned': [], 'actual': [], 'today': ''}

    lines = self.active_schedule_id.line_ids.sorted('date_end')

    return {
        'dates': [line.date_end.isoformat() for line in lines],
        'planned': [line.cumulative_planned for line in lines],
        'actual': [line.cumulative_actual for line in lines],
        'today': fields.Date.today().isoformat(),
    }
```

**步驟 2：JavaScript Widget（static/src/components/progress_chart/progress_chart.js）**

```javascript
/** @odoo-module **/
import { Component, onWillStart, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class ProgressChartWidget extends Component {
    static template = "construction_progress.ProgressChartWidget";

    setup() {
        this.orm = useService("orm");
        this.chartRef = useRef("chart");

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
        });

        onMounted(() => this.renderChart());
    }

    async renderChart() {
        const data = await this.orm.call(
            "supervision.project",
            "get_progress_chart_data",
            [this.props.record.resId]
        );

        new Chart(this.chartRef.el, {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [
                    {
                        label: '預定進度',
                        data: data.planned,
                        borderColor: '#00A7E1',
                    },
                    {
                        label: '實際進度',
                        data: data.actual,
                        borderColor: '#E74C3C',
                    }
                ]
            },
            options: {
                // 自定義選項（可加今日標記線等）
            }
        });
    }
}

registry.category("fields").add("progress_chart", {
    component: ProgressChartWidget,
});
```

**步驟 3：XML 模板（static/src/components/progress_chart/progress_chart.xml）**

```xml
<templates xml:space="preserve">
    <t t-name="construction_progress.ProgressChartWidget">
        <canvas t-ref="chart"/>
    </t>
</templates>
```

**步驟 4：視圖中使用（views/supervision_project_views.xml）**

```xml
<field name="progress_chart" widget="progress_chart" nolabel="1"/>
```

**步驟 5：註冊資源（__manifest__.py）**

```python
"assets": {
    "web.assets_backend": [
        "construction_progress/static/src/components/progress_chart/progress_chart.js",
        "construction_progress/static/src/components/progress_chart/progress_chart.xml",
    ],
},
```

**完成！** 總共約 200 行代碼（Python + JS + XML）。

**效果：**
- ✅ 完全客製化
- ✅ 可加今日標記線
- ✅ 適合累計值
- ✅ 嵌入式顯示
- ❌ 需要維護代碼
- ❌ 不是 Odoo 標準

---

## 代碼量對比

| 方案 | Python | JavaScript | XML | 總行數 | 複雜度 |
|------|--------|-----------|-----|--------|--------|
| Graph View | 0 | 0 | ~20 | ~20 | ⭐ 簡單 |
| Chart.js Widget | ~30 | ~150 | ~30 | ~210 | ⭐⭐⭐ 中等 |

---

## 實際案例：Odoo 官方模組

### 1. 會計模組（Accounting）

**使用 Graph View**
- 銷售分析報表
- 發票統計
- 收支趨勢

**原因**：標準的聚合統計，適合 Graph View

### 2. 銷售模組（Sales）

**使用 Graph View**
- 銷售額統計
- 訂單數量分析
- 客戶排名

**原因**：聚合數據，需要分組和篩選

### 3. 製造模組（Manufacturing）

**使用 Gantt View + 客製化 Widget**
- 生產排程甘特圖
- 工作中心負載圖

**原因**：需要特殊視覺化，標準 View 不足

### 4. 儀表板模組（Dashboard）

**使用客製化 Widget**
- 即時監控圖表
- KPI 指標卡
- 進度環

**原因**：高度客製化需求

---

## Odoo 圖表生態系統

### 內建視圖類型

```
odoo
├── list        # 列表視圖
├── form        # 表單視圖
├── kanban      # 看板視圖
├── calendar    # 日曆視圖
├── gantt       # 甘特圖視圖
├── graph       # 圖表視圖 ← 我們討論的
│   ├── bar    # 柱狀圖
│   ├── line   # 折線圖
│   └── pie    # 圓餅圖
├── pivot       # 透視表視圖
└── cohort      # 同期群分析
```

### 第三方擴展

```
Odoo Apps Store
├── web_widget_bokeh_chart      # Bokeh 圖表
├── web_widget_plotly_chart     # Plotly 圖表
├── report_maker                # 進階報表製作
├── web_graph_chart             # 增強 Graph View
└── dashboard_ninja             # Dashboard 套件
```

### 自定義 Widget（本專案採用）

```
Custom Implementation
├── 使用 Chart.js
├── 使用 D3.js
├── 使用 ECharts
└── 使用其他圖表庫
```

---

## 建議的實現策略

### 階段一：快速上線（使用 Graph View）

適合：
- 時間緊迫
- 標準化需求
- MVP 階段

```xml
<!-- 5 分鐘搞定 -->
<graph type="line">
    <field name="date" type="row"/>
    <field name="value" type="measure"/>
</graph>
```

### 階段二：功能增強（使用 Widget）

適合：
- 需要特殊效果
- 客戶有客製化需求
- 有開發資源

```javascript
// 花 1-2 天開發
class CustomChartWidget extends Component {
    // 完全客製化實現
}
```

### 階段三：混合優化

適合：
- 成熟產品
- 多種使用場景
- 平衡標準化與客製化

```
├── 主選單：使用 Graph View（標準）
├── Dashboard：使用 Widget（客製化）
└── 報表：使用 Pivot + Graph（標準）
```

---

## 總結

### 對於您的進度表專案

**當前實現（Chart.js Widget）✅ 正確**

原因：
1. 數據是累計值（不適合 Graph View 的聚合邏輯）
2. 需要今日標記線（Graph View 無法實現）
3. 嵌入工程案件表單（需要 Widget）
4. 進度曲線是核心功能（值得投資）

**可選改進：**

```xml
<!-- 給進階使用者的標準報表 -->
<menuitem name="進度統計報表"
          action="action_progress_graph_view"/>

<!-- 給專案經理的客製化儀表板 -->
<field name="progress_chart" widget="progress_chart"/>
```

兩種方式並存，各取所長！

---

## 參考文件

1. [CHART_COMPARISON.md](./CHART_COMPARISON.md) - 詳細比較文檔
2. [官方文檔](https://www.odoo.com/documentation/18.0/applications/essentials/reporting.html)
3. [Chart.js 文檔](https://www.chartjs.org/)
