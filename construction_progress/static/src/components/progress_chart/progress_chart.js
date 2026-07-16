/** @odoo-module **/

import { Component, onWillStart, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class ProgressChartWidget extends Component {
    static template = "construction_progress.ProgressChartWidget";
    static props = {
        record: Object,
    };

    setup() {
        this.orm = useService("orm");
        this.chartRef = useRef("chart");
        this.chart = null;

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            // 載入 Chart.js 日期適配器（用於時間軸）
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js");
            // 載入 Chart.js annotation plugin（從 CDN）
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js");
            // 載入 Chart.js zoom plugin（從 CDN）
            await loadJS("https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js");
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js");
        });

        onMounted(() => {
            this.renderChart();
        });

        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }

    resetZoom() {
        if (this.chart) {
            this.chart.resetZoom();
        }
    }

    async renderChart() {
        const projectId = this.props.record.resId;

        if (!projectId) {
            return;
        }

        try {
            const data = await this.orm.call(
                "project.project",
                "get_progress_chart_data",
                [projectId]
            );

            if (!data.dates || data.dates.length === 0) {
                this.chartRef.el.innerHTML = '<div class="alert alert-info text-center" style="margin: 20px;">尚無進度表資料</div>';
                return;
            }

            this.drawChart(data);
        } catch (error) {
            console.error("Failed to load chart data:", error);
            this.chartRef.el.innerHTML = '<div class="alert alert-danger text-center" style="margin: 20px;">載入圖表失敗</div>';
        }
    }

    drawChart(data) {
        const ctx = this.chartRef.el.getContext("2d");

        // 準備標註（annotations）- 使用日期值（供時間軸使用）
        const annotations = {};

        // 1. 今日標記線
        if (data.today) {
            annotations.todayLine = {
                type: "line",
                xMin: data.today,
                xMax: data.today,
                borderColor: "#F39C12",
                borderWidth: 2,
                borderDash: [5, 5],
                label: {
                    display: true,
                    content: "今日",
                    position: "start",
                    backgroundColor: "#F39C12",
                    color: "#fff",
                    font: {
                        size: 11,
                    },
                },
            };
        }

        // 2. 契約變更標記線（版本變更點）
        if (data.version_changes && data.version_changes.length > 0) {
            data.version_changes.forEach((change, index) => {
                if (!change.date) return;

                // 準備標籤內容
                let labelContent = `v${change.version}`;

                annotations[`versionChange${index}`] = {
                    type: "line",
                    xMin: change.date,
                    xMax: change.date,
                    borderColor: "#9B59B6",
                    borderWidth: 2,
                    borderDash: [10, 5],
                    label: {
                        display: true,
                        content: labelContent,
                        position: "end",
                        backgroundColor: "#9B59B6",
                        color: "#fff",
                        font: {
                            size: 10,
                            weight: "bold",
                        },
                        padding: 4,
                    },
                };
            });
        }

        if (this.chart) {
            this.chart.destroy();
        }

        // 將數據轉換為 {x, y} 格式（供時間軸使用）
        const plannedData = data.dates.map((date, i) => ({
            x: date,
            y: data.planned[i],
        }));
        const actualData = data.dates.map((date, i) => ({
            x: date,
            y: data.actual[i],
        }));

        this.chart = new Chart(ctx, {
            type: "line",
            data: {
                datasets: [
                    {
                        label: "累計預定進度 (%)",
                        data: plannedData,
                        borderColor: "#00A7E1",
                        backgroundColor: "rgba(0, 167, 225, 0.1)",
                        borderWidth: 3,
                        pointRadius: function(context) {
                            // 只在關鍵點顯示圓點
                            const index = context.dataIndex;
                            const type = data.point_types ? data.point_types[index] : 'normal';
                            return type === 'key' ? 4 : 0;
                        },
                        pointHoverRadius: 6,
                        tension: 0.1,
                        fill: false,
                    },
                    {
                        label: "累計實際進度 (%)",
                        data: actualData,
                        borderColor: "#E74C3C",
                        backgroundColor: "rgba(231, 76, 60, 0.1)",
                        borderWidth: 3,
                        pointRadius: function(context) {
                            // 只在關鍵點顯示圓點
                            const index = context.dataIndex;
                            const type = data.point_types ? data.point_types[index] : 'normal';
                            return type === 'key' ? 4 : 0;
                        },
                        pointHoverRadius: 6,
                        tension: 0.1,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: 2.0,  // 從 2.5 調整為 2.0（讓圖表更高）
                plugins: {
                    title: {
                        display: true,
                        text: "工程進度曲線圖",
                        font: {
                            size: 18,
                            weight: "bold",
                        },
                        padding: {
                            top: 10,
                            bottom: 20,
                        },
                    },
                    legend: {
                        display: true,
                        position: "top",
                        labels: {
                            usePointStyle: true,
                            padding: 15,
                            font: {
                                size: 13,
                            },
                        },
                    },
                    tooltip: {
                        mode: "index",
                        intersect: false,
                        callbacks: {
                            label: function (context) {
                                let label = context.dataset.label || "";
                                if (label) {
                                    label += ": ";
                                }
                                label += context.parsed.y.toFixed(2) + "%";
                                return label;
                            },
                            afterBody: function (context) {
                                // 顯示版本變更資訊
                                // 時間軸模式下，使用 parsed.x（時間戳）來比對日期
                                const rawX = context[0].raw?.x || context[0].label;
                                // 如果是時間戳，轉換為 ISO 日期格式
                                let dateStr = rawX;
                                if (typeof rawX === 'number') {
                                    dateStr = new Date(rawX).toISOString().split('T')[0];
                                }

                                const versionChange = data.version_changes?.find(
                                    change => change.date === dateStr
                                );

                                if (versionChange) {
                                    const info = [
                                        '',
                                        `📋 進度表版本 v${versionChange.version}`,
                                        versionChange.reason || '',
                                    ];

                                    if (versionChange.change_orders?.length > 0) {
                                        info.push(`契約變更：${versionChange.change_orders.join(', ')}`);
                                    }

                                    return info;
                                }
                                return [];
                            },
                        },
                    },
                    annotation: Object.keys(annotations).length > 0 ? {
                        annotations: annotations,
                    } : undefined,
                    zoom: {
                        zoom: {
                            wheel: {
                                enabled: true,
                                speed: 0.1,
                            },
                            pinch: {
                                enabled: true,
                            },
                            mode: 'x',
                        },
                        pan: {
                            enabled: true,
                            mode: 'x',
                            modifierKey: null,
                        },
                        limits: {
                            x: {
                                min: 'original',
                                max: 'original',
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        type: 'time',  // 使用時間軸（相同日期的點會重疊，形成垂直線）
                        display: true,
                        title: {
                            display: true,
                            text: "時間 (日期)",
                            font: {
                                size: 14,
                                weight: "bold",
                            },
                        },
                        time: {
                            unit: 'day',
                            displayFormats: {
                                day: 'yyyy-MM-dd',
                            },
                            tooltipFormat: 'yyyy-MM-dd',
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            font: {
                                size: 11,
                            },
                            autoSkip: true,
                            maxTicksLimit: 20,
                        },
                        grid: {
                            color: "rgba(0, 0, 0, 0.05)",
                        },
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: "進度 (%)",
                            font: {
                                size: 14,
                                weight: "bold",
                            },
                        },
                        min: 0,
                        max: 100,
                        ticks: {
                            callback: function (value) {
                                return value + "%";
                            },
                            font: {
                                size: 11,
                            },
                        },
                        grid: {
                            color: "rgba(0, 0, 0, 0.1)",
                        },
                    },
                },
                interaction: {
                    mode: "nearest",
                    axis: "x",
                    intersect: false,
                },
            },
        });
    }
}

registry.category("fields").add("progress_chart", {
    component: ProgressChartWidget,
});
