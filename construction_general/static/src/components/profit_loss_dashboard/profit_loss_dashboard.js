/** @odoo-module **/

import { Component, onWillStart, useRef, onWillUnmount, useState, onPatched } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class ProfitLossDashboard extends Component {
    static template = "construction_general.ProfitLossDashboard";
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
            data: null,
            error: null,
            saving: false,
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js");
            await loadJS("https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js");
            await this.loadProjects();
        });

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
            // 只查詢一般式工程案件
            const projects = await this.orm.searchRead(
                "project.project",
                [["project_type", "=", "general"]],
                ["id", "name", "code"],
                { order: "code desc" }
            );

            this.state.projects = projects.map((p) => ({
                id: p.id,
                name: p.code ? `[${p.code}] ${p.name}` : p.name,
            }));
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
            this.state.data = null;
            if (this.chart) {
                this.chart.destroy();
                this.chart = null;
            }
            return;
        }

        this.state.selectedProjectId = projectId;
        await this.loadData(projectId);
    }

    async loadData(projectId) {
        this.state.loading = true;
        this.state.error = null;

        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }

        try {
            const data = await this.orm.call(
                "project.project",
                "get_profit_loss_data",
                [projectId]
            );

            this.state.data = data;

            if (data.estimates && data.estimates.length > 0) {
                this._pendingChartData = data;
            }
        } catch (error) {
            console.error("Failed to load data:", error);
            this.state.error = "載入資料失敗";
        } finally {
            this.state.loading = false;
        }
    }

    async onExpenseChange(estimateId, ev) {
        const value = parseFloat(ev.target.value) || 0;
        const projectId = this.state.selectedProjectId;
        if (!projectId) return;

        this.state.saving = true;
        try {
            const data = await this.orm.call(
                "project.project",
                "save_profit_loss_expense",
                [projectId, estimateId, value]
            );

            this.state.data = data;

            if (data.estimates && data.estimates.length > 0) {
                this._pendingChartData = data;
            }
        } catch (error) {
            console.error("Failed to save expense:", error);
            this.state.error = "儲存支出失敗";
        } finally {
            this.state.saving = false;
        }
    }

    formatCurrency(value) {
        if (value === null || value === undefined) return "-";
        return value.toLocaleString("zh-TW", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }

    drawChart(data) {
        const canvasEl = this.chartRef.el;
        if (!canvasEl) {
            console.error("Canvas element not found");
            return;
        }

        const ctx = canvasEl.getContext("2d");

        if (this.chart) {
            this.chart.destroy();
        }

        const estimates = data.estimates || [];
        if (estimates.length === 0) return;

        // 準備圖表資料
        const incomeData = estimates.map((est) => ({
            x: est.estimate_date,
            y: est.income,
        }));
        const expenseData = estimates.map((est) => ({
            x: est.estimate_date,
            y: est.expense,
        }));

        // 估驗日期垂直虛線標註
        const annotations = {};
        estimates.forEach((est, index) => {
            if (est.estimate_date) {
                annotations["est" + index] = {
                    type: "line",
                    xMin: est.estimate_date,
                    xMax: est.estimate_date,
                    borderColor: "#9ca3af",
                    borderWidth: 1,
                    borderDash: [5, 5],
                    label: {
                        display: true,
                        content: "\u7b2c" + est.estimate_no + "\u6b21",
                        position: "start",
                        backgroundColor: "rgba(156, 163, 175, 0.8)",
                        color: "#fff",
                        font: { size: 10 },
                        padding: 3,
                    },
                };
            }
        });

        this.chart = new Chart(ctx, {
            type: "line",
            data: {
                datasets: [
                    {
                        label: "\u6536\u5165",
                        data: incomeData,
                        borderColor: "#3b82f6",
                        backgroundColor: "rgba(59, 130, 246, 0.1)",
                        borderWidth: 3,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: "#3b82f6",
                        tension: 0.1,
                        fill: false,
                    },
                    {
                        label: "\u652f\u51fa",
                        data: expenseData,
                        borderColor: "#ef4444",
                        backgroundColor: "rgba(239, 68, 68, 0.1)",
                        borderWidth: 3,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: "#ef4444",
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
                        text: "\u5373\u6642\u640d\u76ca\u5206\u6790\u5716",
                        font: { size: 18, weight: "bold" },
                        padding: { top: 10, bottom: 20 },
                    },
                    legend: {
                        display: true,
                        position: "top",
                        labels: {
                            usePointStyle: true,
                            padding: 15,
                            font: { size: 13 },
                        },
                    },
                    tooltip: {
                        mode: "index",
                        intersect: false,
                        callbacks: {
                            label: function (context) {
                                let label = context.dataset.label || "";
                                if (label) label += ": ";
                                label += context.parsed.y.toLocaleString("zh-TW");
                                return label;
                            },
                        },
                    },
                    annotation: Object.keys(annotations).length > 0 ? {
                        annotations: annotations,
                    } : undefined,
                },
                scales: {
                    x: {
                        type: "time",
                        display: true,
                        title: {
                            display: true,
                            text: "\u65e5\u671f",
                            font: { size: 14, weight: "bold" },
                        },
                        time: {
                            unit: "day",
                            displayFormats: { day: "yyyy-MM-dd" },
                            tooltipFormat: "yyyy-MM-dd",
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            font: { size: 11 },
                            autoSkip: true,
                            maxTicksLimit: 15,
                        },
                        grid: { color: "rgba(0, 0, 0, 0.05)" },
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: "\u91d1\u984d",
                            font: { size: 14, weight: "bold" },
                        },
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return value.toLocaleString("zh-TW");
                            },
                            font: { size: 11 },
                        },
                        grid: { color: "rgba(0, 0, 0, 0.1)" },
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

registry.category("actions").add("profit_loss_dashboard", ProfitLossDashboard);
