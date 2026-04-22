/** @odoo-module **/

import { Component, onWillStart, useRef, onWillUnmount, useState, onPatched } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class ProgressDashboard extends Component {
    static template = "construction_progress.ProgressDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.chartRef = useRef("chart");
        this.chart = null;
        this._pendingChartData = null;

        this.state = useState({
            projects: [],
            selectedProjectId: null,
            loading: false,
            chartLoading: false,
            noData: false,
            error: null,
            // 儀表板資料
            dashboardData: null,
            dashboardLoading: false,
        });

        onWillStart(async () => {
            // 載入 Chart.js 及相關外掛
            await loadJS("/web/static/lib/Chart/Chart.js");
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js");
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js");
            await loadJS("https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js");
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js");

            // 載入有進度表的工程列表
            await this.loadProjects();
        });

        // DOM 更新後繪製圖表
        onPatched(() => {
            if (this._pendingChartData) {
                const data = this._pendingChartData;
                this._pendingChartData = null;
                this.drawChart(data);
            }
        });

        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }

    async loadProjects() {
        this.state.loading = true;
        try {
            // 查找所有有進度表的工程案件
            const schedules = await this.orm.searchRead(
                "progress.schedule",
                [],
                ["project_id"],
                { order: "project_id" }
            );

            // 取得不重複的工程 ID
            const projectIdSet = new Set();
            const projectList = [];
            for (const s of schedules) {
                if (s.project_id && !projectIdSet.has(s.project_id[0])) {
                    projectIdSet.add(s.project_id[0]);
                    projectList.push({
                        id: s.project_id[0],
                        name: s.project_id[1],
                    });
                }
            }

            this.state.projects = projectList;
        } catch (error) {
            console.error("Failed to load projects:", error);
            this.state.error = "載入工程列表失敗";
        } finally {
            this.state.loading = false;
        }
    }

    async onProjectChange(ev) {
        const projectId = parseInt(ev.target.value);
        if (!projectId) {
            this.state.selectedProjectId = null;
            this.state.noData = false;
            this.state.dashboardData = null;
            if (this.chart) {
                this.chart.destroy();
                this.chart = null;
            }
            return;
        }

        this.state.selectedProjectId = projectId;
        // 並行載入圖表與儀表板資料
        await Promise.all([
            this.loadChart(projectId),
            this.loadDashboardData(projectId),
        ]);
    }

    async loadDashboardData(projectId) {
        this.state.dashboardLoading = true;
        try {
            const data = await this.orm.call(
                "supervision.project",
                "get_project_dashboard_data",
                [projectId]
            );
            this.state.dashboardData = data;
        } catch (error) {
            console.error("Failed to load dashboard data:", error);
            this.state.dashboardData = null;
        } finally {
            this.state.dashboardLoading = false;
        }
    }

    // === 格式化輔助方法 ===

    formatCurrency(value) {
        if (value === null || value === undefined) return '-';
        if (value >= 100000000) {
            return (value / 100000000).toFixed(2) + ' 億';
        }
        if (value >= 10000) {
            return (value / 10000).toFixed(1) + ' 萬';
        }
        return value.toLocaleString();
    }

    formatPercent(value) {
        if (value === null || value === undefined) return '-';
        return value.toFixed(2) + '%';
    }

    getVarianceClass() {
        const ds = this.state.dashboardData;
        if (!ds || !ds.progress_summary) return '';
        const status = ds.progress_summary.variance_status;
        if (status === 'ahead') return 'text-success';
        if (status === 'delayed') return 'text-danger';
        return 'text-warning';
    }

    getVarianceBorderClass() {
        const ds = this.state.dashboardData;
        if (!ds || !ds.progress_summary) return '';
        const status = ds.progress_summary.variance_status;
        if (status === 'ahead') return 'border-success';
        if (status === 'delayed') return 'border-danger';
        return 'border-warning';
    }

    async loadChart(projectId) {
        this.state.chartLoading = true;
        this.state.noData = false;
        this.state.error = null;

        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }

        try {
            const data = await this.orm.call(
                "supervision.project",
                "get_progress_chart_data",
                [projectId]
            );

            if (!data.dates || data.dates.length === 0) {
                this.state.noData = true;
                this.state.chartLoading = false;
                return;
            }

            // 先更新狀態讓 canvas 顯示出來，再透過 onPatched 繪圖
            this._pendingChartData = data;
            this.state.chartLoading = false;
        } catch (error) {
            console.error("Failed to load chart data:", error);
            this.state.error = "載入圖表資料失敗";
            this.state.chartLoading = false;
        }
    }

    resetZoom() {
        if (this.chart) {
            this.chart.resetZoom();
        }
    }

    drawChart(data) {
        const canvasEl = this.chartRef.el;
        if (!canvasEl) {
            console.error("Canvas element not found");
            return;
        }

        const ctx = canvasEl.getContext("2d");

        // === 準備標註 ===
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
                aspectRatio: 2.0,
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
                                const rawX = context[0].raw?.x || context[0].label;
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
                        type: 'time',
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

registry.category("actions").add("progress_chart_dashboard", ProgressDashboard);
