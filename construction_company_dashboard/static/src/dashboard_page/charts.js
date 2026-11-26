/** @odoo-module **/
// 公司儀表板「統計圖表」頁（淞源 2026-11-10 會議 C9）：選資料集、工程、期間、圖型（柱狀／圓餅／雷達），
// 圖可下載成圖片放簡報，下方同時列數字總表。
// 資料全部來自後端 project.project.get_dash_chart_data（以看的人的權限算）；這裡只做顯示，不算任何數字。
// 顏色規則（dataviz）：
//   * 一條數列的柱狀圖，每根柱子同一個顏色；類別本身有好／壞意義（合格、不合格）才用狀態色，旁邊一定有文字。
//   * 多條數列、圓餅的各塊：用固定順序的序列色，顏色跟著項目走（換篩選條件不重新配色）。
//   * 文字一律用墨色，不用資料色。
import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { LOAD_FAILED_MESSAGE, PROJECT_MODEL, STATUS_OK, formatDateLabel, formatQty } from "./dash_common";

export const CHARTS_PAGE_TAG = "company_dashboard_charts";
const CHART_LIB_URL = "/web/static/lib/Chart/Chart.js";
const CHART_BAR = "bar";
const CHART_PIE = "pie";
const CHART_RADAR = "radar";
const CHART_TYPE_LABELS = { [CHART_BAR]: "柱狀圖", [CHART_PIE]: "圓餅圖", [CHART_RADAR]: "雷達圖" };
const CHART_TYPE_ICONS = { [CHART_BAR]: "fa-bar-chart", [CHART_PIE]: "fa-pie-chart", [CHART_RADAR]: "fa-bullseye" };
const ALL_PROJECTS = "all";
const PROJECT_ORDER = "name";

// 期間預設選項
const PERIOD_MONTH = "month";
const PERIOD_QUARTER = "quarter";
const PERIOD_YEAR = "year";
const PERIOD_ALL = "all";
const PERIOD_CUSTOM = "custom";
const PERIOD_OPTIONS = [
    { key: PERIOD_MONTH, label: "本月" },
    { key: PERIOD_QUARTER, label: "近 3 個月" },
    { key: PERIOD_YEAR, label: "今年" },
    { key: PERIOD_ALL, label: "全部期間" },
    { key: PERIOD_CUSTOM, label: "自訂" },
];
const QUARTER_MONTHS_BACK = 2;      // 近 3 個月＝本月＋往前 2 個月

// 序列色（固定順序，已用 dataviz 的 validate_palette.js 對白底驗過：相鄰 6 色、前 3 色全配對皆通過）
const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"];
// 狀態色：只用在類別本身有好／壞意義時，一定搭配文字標籤
const ROLE_COLORS = { good: "#0ca30c", warning: "#fab219", critical: "#d03b3b", neutral: "#9aa3ad" };
const ROLE_SERIES = "series";
const NEUTRAL_COLOR = ROLE_COLORS.neutral;
const SURFACE_COLOR = "#ffffff";
const INK_COLOR = "#2b2f36";
const MUTE_COLOR = "#6c757d";
const GRID_COLOR = "#e6e8eb";
const AREA_ALPHA_HEX = "1a";        // 雷達圖的面積填色：序列色加約 10% 不透明度
const BAR_MAX_THICKNESS = 24;
const BAR_RADIUS = 4;
const LINE_WIDTH = 2;
const POINT_RADIUS = 4;
const PIE_GAP = 2;
const PIE_MAX_SLICES = 6;           // 圓餅最多幾塊（含「其他」），再多就看不清
const RADAR_MIN_CATEGORIES = 3;
const HORIZONTAL_LABEL_LENGTH = 6;  // 類別名稱超過這個字數，柱狀圖改成橫條（名稱才排得下）
const HORIZONTAL_CATEGORY_COUNT = 8;
// 字級（2026-11-25 會議：圖上的字太小，貼進簡報看不到）。畫面上用這組；下載的圖另外照簡報尺寸重畫（見 onDownload）
const TITLE_FONT_SIZE = 20;
const SUBTITLE_FONT_SIZE = 14;
const TICK_FONT_SIZE = 15;
const LEGEND_BOX_SIZE = 14;
const VALUE_LABEL_OFFSET = 6;
const LAYOUT_PADDING_RIGHT = 44;    // 橫條圖柱子尾端的數字要有位置
const LABEL_WRAP_CHARS = 10;        // 類別名稱超過這個字數就折行（柱狀、雷達；圓餅的名稱寫在圖例，不折）
// 下載的圖：固定 16:9，直接貼進簡報整頁寬；字級是畫面的 EXPORT_SCALE 倍（1600 寬的圖縮到投影片寬度後，字仍大於內文字級）
const EXPORT_WIDTH = 1600;
const EXPORT_HEIGHT = 900;
const EXPORT_SCALE = 1.6;
const SCREEN_SCALE = 1;
const OTHER_KEY = "other";
const OTHER_LABEL = "其他";
const EXPORT_PREFIX = "統計圖表";
const PERCENT_UNIT = "%";

const pad = (number) => String(number).padStart(2, "0");
const isoDate = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/** 匯出的圖片要白底（預設是透明，貼進簡報的深色版面會看不到字） */
const whiteBackgroundPlugin = {
    id: "dashWhiteBackground",
    beforeDraw(chart) {
        const { ctx, width, height } = chart;
        ctx.save();
        ctx.globalCompositeOperation = "destination-over";
        ctx.fillStyle = SURFACE_COLOR;
        ctx.fillRect(0, 0, width, height);
        ctx.restore();
    },
};

/** 單一數列的柱狀圖：數值寫在柱子尾端（多數列不寫，交給圖例、提示框與下方總表） */
const barValueLabelPlugin = {
    id: "dashBarValueLabel",
    afterDatasetsDraw(chart, _args, options) {
        if (!options || !options.enabled) {
            return;
        }
        const { ctx } = chart;
        const meta = chart.getDatasetMeta(0);
        const horizontal = chart.options.indexAxis === "y";
        ctx.save();
        ctx.fillStyle = INK_COLOR;
        ctx.font = `${options.fontSize}px sans-serif`;
        ctx.textBaseline = horizontal ? "middle" : "bottom";
        ctx.textAlign = horizontal ? "left" : "center";
        meta.data.forEach((bar, index) => {
            const text = options.format(chart.data.datasets[0].data[index]);
            if (horizontal) {
                ctx.fillText(text, bar.x + options.offset, bar.y);
            } else {
                ctx.fillText(text, bar.x, bar.y - options.offset / 2);
            }
        });
        ctx.restore();
    },
};

export class CompanyDashboardCharts extends Component {
    static template = "construction_company_dashboard.ChartsPage";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.display = { controlPanel: {} };
        this.canvasRef = useRef("canvas");
        this.chart = null;
        this.todayLabel = formatDateLabel();
        this.periodOptions = PERIOD_OPTIONS;
        this.chartTypeLabels = CHART_TYPE_LABELS;
        this.chartTypeIcons = CHART_TYPE_ICONS;
        this.allProjects = ALL_PROJECTS;
        // 顏色跟著項目走：資料集 → (類別或數列 key → 序列色位置)。換篩選條件時，留下來的項目顏色不變
        this.colorSlots = new Map();
        const today = new Date();
        this.state = useState({
            loading: true,
            error: false,
            catalog: [],
            projects: [],
            dataset: null,
            project: ALL_PROJECTS,
            period: PERIOD_YEAR,
            customFrom: isoDate(new Date(today.getFullYear(), 0, 1)),
            customTo: isoDate(today),
            chartType: CHART_BAR,
            data: null,
        });
        if (this.env.config && typeof this.env.config.setDisplayName === "function") {
            this.env.config.setDisplayName("統計圖表");   // 直接開網址時麵包屑不要顯示「未命名的」
        }
        onWillStart(async () => {
            await loadJS(CHART_LIB_URL);
            await this.loadOptions();
            await this.loadData();
        });
        // 畫布在模板裡（有資料才出現），所以等畫面更新完再畫：資料、圖型、載入狀態任何一個變了就重畫
        useEffect(
            () => {
                this.renderChart();
            },
            () => [this.state.data, this.state.chartType, this.state.loading]
        );
        onWillUnmount(() => this.destroyChart());
    }

    // ── 資料 ────────────────────────────────────────────────────────────
    async loadOptions() {
        try {
            this.state.catalog = await this.orm.call(PROJECT_MODEL, "get_dash_chart_catalog", []);
            this.state.projects = await this.orm.searchRead(PROJECT_MODEL, [], ["name", "code"], { order: PROJECT_ORDER });
            this.state.dataset = this.state.catalog.length ? this.state.catalog[0].key : null;
        } catch (error) {
            console.error("統計圖表選項讀取失敗", error);
            this.state.error = LOAD_FAILED_MESSAGE;
        }
    }

    get period() {
        const today = new Date();
        switch (this.state.period) {
            case PERIOD_MONTH:
                return [isoDate(new Date(today.getFullYear(), today.getMonth(), 1)), isoDate(today)];
            case PERIOD_QUARTER:
                return [isoDate(new Date(today.getFullYear(), today.getMonth() - QUARTER_MONTHS_BACK, 1)), isoDate(today)];
            case PERIOD_YEAR:
                return [isoDate(new Date(today.getFullYear(), 0, 1)), isoDate(today)];
            case PERIOD_CUSTOM:
                return [this.state.customFrom || false, this.state.customTo || false];
            default:
                return [false, false];
        }
    }

    async loadData() {
        if (!this.state.dataset) {
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        this.state.error = false;
        const [dateFrom, dateTo] = this.period;
        const projectIds = this.state.project === ALL_PROJECTS ? [] : [Number(this.state.project)];
        try {
            const data = await this.orm.call(PROJECT_MODEL, "get_dash_chart_data",
                                             [this.state.dataset, projectIds, dateFrom, dateTo]);
            this.state.data = data;
        } catch (error) {
            // 大聲失敗：讀不到就明講（後端的說明文字優先，例：日期格式不對）
            console.error("統計圖表資料讀取失敗", error);
            this.state.data = null;
            this.state.error = (error && error.data && error.data.message) || LOAD_FAILED_MESSAGE;
        } finally {
            this.state.loading = false;
        }
    }

    async reload() {
        await this.loadData();
    }

    // ── 篩選列 ──────────────────────────────────────────────────────────
    async onDatasetChange(ev) {
        this.state.dataset = ev.target.value;
        await this.reload();
    }

    async onProjectChange(ev) {
        this.state.project = ev.target.value;
        await this.reload();
    }

    async onPeriodClick(key) {
        this.state.period = key;
        await this.reload();
    }

    async onCustomDateChange(field, ev) {
        this.state[field] = ev.target.value;
        if (this.state.period === PERIOD_CUSTOM) {
            await this.reload();
        }
    }

    onChartTypeClick(type) {
        if (!this.isChartTypeAvailable(type)) {
            return;
        }
        this.state.chartType = type;
    }

    // ── 畫面用的衍生值 ──────────────────────────────────────────────────
    get data() {
        return this.state.data;
    }

    get ok() {
        return Boolean(this.data && this.data.status === STATUS_OK);
    }

    get hasValues() {
        if (!this.ok || !this.data.categories.length) {
            return false;
        }
        // 百分比（進度）的 0 是有意義的值，有類別就畫；件數類全部是 0 才算沒有資料
        return this.data.unit === PERCENT_UNIT || this.data.series.some((series) => series.values.some((value) => value));
    }

    get chartTypes() {
        return [CHART_BAR, CHART_PIE, CHART_RADAR];
    }

    /** 實際畫的圖型：選的那種不適用於目前資料（例：雷達圖類別不足）時退回柱狀圖 */
    get effectiveChartType() {
        return this.isChartTypeAvailable(this.state.chartType) ? this.state.chartType : CHART_BAR;
    }

    isChartTypeAvailable(type) {
        if (!this.data || !this.data.chart_types.includes(type)) {
            return false;
        }
        return type !== CHART_RADAR || this.data.categories.length >= RADAR_MIN_CATEGORIES;
    }

    chartTypeHint(type) {
        if (!this.data || this.isChartTypeAvailable(type)) {
            return "";
        }
        if (type === CHART_RADAR && this.data.chart_types.includes(type)) {
            return `雷達圖至少要 ${RADAR_MIN_CATEGORIES} 個類別`;
        }
        return type === CHART_PIE ? "這個資料集不是整體的組成，不適合圓餅圖" : "這個資料集不適合這種圖";
    }

    /** 模板的運算式拿不到 String 這類全域函式，型別轉換放在這裡（選單的值是字串、工程 id 是數字） */
    isSelectedProject(project) {
        return String(project.id) === String(this.state.project);
    }

    get projectLabel() {
        if (this.state.project === ALL_PROJECTS) {
            return "全部工程";
        }
        const project = this.state.projects.find((item) => String(item.id) === String(this.state.project));
        return project ? project.name : "";
    }

    get periodLabel() {
        if (!this.data || !this.data.date_label) {
            return "今日";
        }
        const from = this.data.date_from;
        const to = this.data.date_to;
        const range = from || to ? `${from || "最早"} ～ ${to || "最新"}` : "全部期間";
        return `${this.data.date_label} ${range}`;
    }

    get totalLabel() {
        if (!this.ok || this.data.total === null || this.data.total === undefined) {
            return "";
        }
        return `合計 ${formatQty(this.data.total)} ${this.data.unit}`;
    }

    get subtitle() {
        return [this.projectLabel, this.periodLabel, this.totalLabel].filter(Boolean).join("　·　");
    }

    formatValue(value) {
        return formatQty(value);
    }

    /** 總表每一列的合計（件數類才有；百分比不能加） */
    rowTotal(index) {
        return this.data.series.reduce((sum, series) => sum + (Number(series.values[index]) || 0), 0);
    }

    seriesTotal(series) {
        return series.values.reduce((sum, value) => sum + (Number(value) || 0), 0);
    }

    get showTotals() {
        return this.ok && this.data.unit !== PERCENT_UNIT;
    }

    get showRowTotal() {
        return this.showTotals && this.data.series.length > 1;
    }

    // ── 顏色 ────────────────────────────────────────────────────────────
    /** 這個資料集裡 key 的序列色；留在畫面上的項目顏色不變，新出現的拿目前沒人用的最前面一個 */
    slotColor(key, visibleKeys) {
        const dataset = this.state.dataset;
        if (!this.colorSlots.has(dataset)) {
            this.colorSlots.set(dataset, new Map());
        }
        const slots = this.colorSlots.get(dataset);
        if (!slots.has(key)) {
            const taken = new Set(visibleKeys.filter((other) => other !== key && slots.has(other)).map((other) => slots.get(other)));
            let free = SERIES_COLORS.findIndex((_color, index) => !taken.has(index));
            if (free < 0) {
                free = SERIES_COLORS.length - 1;
            }
            slots.set(key, free);
        }
        return SERIES_COLORS[slots.get(key)];
    }

    categoryColors(categories) {
        const keys = categories.map((category) => category.key);
        return categories.map((category) => {
            if (category.role && category.role !== ROLE_SERIES) {
                return ROLE_COLORS[category.role] || NEUTRAL_COLOR;
            }
            return this.slotColor(category.key, keys);
        });
    }

    /** 一條數列的柱狀圖：每根柱子同一個顏色（序列色第一色）；只有類別本身有好／壞意義時那一根用狀態色，
     *  「其他」「未判定」這類用中性灰。不逐根換色——柱子的長度已經在比大小，顏色再變只是雜訊。 */
    barColors(categories) {
        return categories.map((category) =>
            category.role && category.role !== ROLE_SERIES ? (ROLE_COLORS[category.role] || NEUTRAL_COLOR) : SERIES_COLORS[0]
        );
    }

    seriesColors(seriesList) {
        const keys = seriesList.map((series) => series.key);
        return seriesList.map((series) => this.slotColor(series.key, keys));
    }

    // ── 畫圖 ────────────────────────────────────────────────────────────
    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    /** 目前這張圖的倍率：畫面上 1 倍，下載時 EXPORT_SCALE 倍（字級、柱寬、間距一起放大） */
    get scale() {
        return this.exportScale || SCREEN_SCALE;
    }

    px(size) {
        return Math.round(size * this.scale);
    }

    /** 類別名稱太長就折行（Chart.js 的標籤給陣列＝多行） */
    wrapLabel(label) {
        const text = String(label);
        if (text.length <= LABEL_WRAP_CHARS) {
            return text;
        }
        // 各行字數平均分（11 個字折成 6＋5，不要 10＋1 剩一個字）
        const lineCount = Math.ceil(text.length / LABEL_WRAP_CHARS);
        const perLine = Math.ceil(text.length / lineCount);
        const lines = [];
        for (let start = 0; start < text.length; start += perLine) {
            lines.push(text.slice(start, start + perLine));
        }
        return lines;
    }

    get baseOptions() {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            color: INK_COLOR,
            layout: { padding: { top: this.px(4), right: this.px(LAYOUT_PADDING_RIGHT), bottom: this.px(4), left: this.px(4) } },
            plugins: {
                title: { display: true, text: this.data.label, color: INK_COLOR, align: "start",
                         font: { size: this.px(TITLE_FONT_SIZE), weight: "bold" }, padding: { bottom: this.px(2) } },
                subtitle: { display: true, text: this.subtitle, color: MUTE_COLOR, align: "start",
                            font: { size: this.px(SUBTITLE_FONT_SIZE) }, padding: { bottom: this.px(14) } },
                legend: { display: false, position: "bottom",
                          labels: { color: INK_COLOR, boxWidth: this.px(LEGEND_BOX_SIZE), boxHeight: this.px(LEGEND_BOX_SIZE),
                                    padding: this.px(12), font: { size: this.px(TICK_FONT_SIZE) } } },
                tooltip: { callbacks: {} },
            },
        };
    }

    buildBarConfig() {
        const { categories, series, unit } = this.data;
        const single = series.length === 1;
        const longest = Math.max(...categories.map((category) => category.label.length));
        const horizontal = longest > HORIZONTAL_LABEL_LENGTH || categories.length > HORIZONTAL_CATEGORY_COUNT;
        const seriesColors = this.seriesColors(series);
        const datasets = series.map((item, index) => ({
            label: item.label,
            data: item.values,
            backgroundColor: single ? this.barColors(categories) : seriesColors[index],
            maxBarThickness: this.px(BAR_MAX_THICKNESS),
            borderRadius: this.px(BAR_RADIUS),
            borderSkipped: "start",
            borderWidth: 0,
        }));
        const options = this.baseOptions;
        const valueAxis = {
            beginAtZero: true,
            grid: { color: GRID_COLOR, drawTicks: false },
            border: { display: false },
            ticks: { color: MUTE_COLOR, font: { size: this.px(TICK_FONT_SIZE) }, precision: 0,
                     callback: (value) => (unit === PERCENT_UNIT ? `${value}%` : formatQty(value)) },
        };
        const categoryAxis = {
            grid: { display: false },
            border: { color: GRID_COLOR },
            ticks: { color: INK_COLOR, font: { size: this.px(TICK_FONT_SIZE) }, autoSkip: false },
        };
        options.indexAxis = horizontal ? "y" : "x";
        options.scales = horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis };
        options.plugins.legend.display = !single;
        options.plugins.dashBarValueLabel = {
            enabled: single,
            fontSize: this.px(TICK_FONT_SIZE),
            offset: this.px(VALUE_LABEL_OFFSET),
            format: (value) => (unit === PERCENT_UNIT ? `${formatQty(value)}%` : formatQty(value)),
        };
        options.plugins.tooltip.callbacks.label = (context) =>
            `${context.dataset.label}：${formatQty(context.parsed[horizontal ? "x" : "y"])} ${unit}`;
        return { type: "bar", data: { labels: categories.map((category) => this.wrapLabel(category.label)), datasets }, options,
                 plugins: [whiteBackgroundPlugin, barValueLabelPlugin] };
    }

    /** 圓餅：超過 PIE_MAX_SLICES 塊時，最小的併成「其他」；值是 0 的不畫 */
    pieSlices() {
        const { categories, series } = this.data;
        const slices = categories
            .map((category, index) => ({ ...category, value: Number(series[0].values[index]) || 0 }))
            .filter((slice) => slice.value > 0);
        if (slices.length <= PIE_MAX_SLICES) {
            return slices;
        }
        const named = slices.filter((slice) => slice.key !== OTHER_KEY).sort((a, b) => b.value - a.value);
        const kept = named.slice(0, PIE_MAX_SLICES - 1);
        const restValue = slices.reduce((sum, slice) => sum + slice.value, 0) - kept.reduce((sum, slice) => sum + slice.value, 0);
        return [...kept, { key: OTHER_KEY, label: OTHER_LABEL, role: "neutral", value: restValue }];
    }

    buildPieConfig() {
        const { unit } = this.data;
        const slices = this.pieSlices();
        const total = slices.reduce((sum, slice) => sum + slice.value, 0);
        const share = (value) => (total ? `${((value / total) * 100).toFixed(1)}%` : "0%");
        const options = this.baseOptions;
        options.plugins.legend.display = true;
        options.plugins.legend.position = "right";
        // 圖例直接寫名稱、數值與占比：不必靠顏色對照，也不必滑到圖上才看得到數字
        options.plugins.legend.labels.generateLabels = (chart) =>
            chart.data.labels.map((label, index) => ({
                text: `${label}　${formatQty(chart.data.datasets[0].data[index])} ${unit}（${share(chart.data.datasets[0].data[index])}）`,
                fillStyle: chart.data.datasets[0].backgroundColor[index],
                strokeStyle: SURFACE_COLOR,
                fontColor: INK_COLOR,
                lineWidth: 0,
                index,
            }));
        options.plugins.legend.onClick = () => {};      // 圓餅不做點圖例隱藏（占比會跟著變、容易誤讀）
        options.plugins.tooltip.callbacks.label = (context) =>
            `${context.label}：${formatQty(context.parsed)} ${unit}（${share(context.parsed)}）`;
        return {
            type: "pie",
            data: {
                labels: slices.map((slice) => slice.label),
                datasets: [{
                    data: slices.map((slice) => slice.value),
                    backgroundColor: this.categoryColors(slices),
                    borderColor: SURFACE_COLOR,
                    borderWidth: PIE_GAP,
                }],
            },
            options,
            plugins: [whiteBackgroundPlugin],
        };
    }

    buildRadarConfig() {
        const { categories, series, unit } = this.data;
        const colors = this.seriesColors(series);
        const options = this.baseOptions;
        options.plugins.legend.display = series.length > 1;
        options.scales = {
            r: {
                beginAtZero: true,
                grid: { color: GRID_COLOR },
                angleLines: { color: GRID_COLOR },
                pointLabels: { color: INK_COLOR, font: { size: this.px(TICK_FONT_SIZE) } },
                ticks: { color: MUTE_COLOR, backdropColor: SURFACE_COLOR, precision: 0, font: { size: this.px(SUBTITLE_FONT_SIZE) } },
            },
        };
        options.plugins.tooltip.callbacks.label = (context) =>
            `${context.dataset.label}：${formatQty(context.parsed.r)} ${unit}`;
        return {
            type: "radar",
            data: {
                labels: categories.map((category) => this.wrapLabel(category.label)),
                datasets: series.map((item, index) => ({
                    label: item.label,
                    data: item.values,
                    borderColor: colors[index],
                    backgroundColor: colors[index] + AREA_ALPHA_HEX,
                    borderWidth: this.px(LINE_WIDTH),
                    pointRadius: this.px(POINT_RADIUS),
                    pointBackgroundColor: colors[index],
                    pointBorderColor: SURFACE_COLOR,
                    pointBorderWidth: LINE_WIDTH,
                })),
            },
            options,
            plugins: [whiteBackgroundPlugin],
        };
    }

    renderChart() {
        this.destroyChart();
        const canvas = this.canvasRef.el;
        if (!canvas || !this.hasValues || !window.Chart) {
            return;
        }
        this.chart = new window.Chart(canvas.getContext("2d"), this.buildConfig());
    }

    buildConfig() {
        const builders = { [CHART_BAR]: () => this.buildBarConfig(), [CHART_PIE]: () => this.buildPieConfig(),
                           [CHART_RADAR]: () => this.buildRadarConfig() };
        return builders[this.effectiveChartType]();
    }

    /** 下載用的圖：不拿畫面上那張（尺寸跟著視窗、字是螢幕字級），另外在固定 16:9 的畫布上用放大的字重畫一張 */
    exportImage() {
        const canvas = document.createElement("canvas");
        canvas.width = EXPORT_WIDTH;
        canvas.height = EXPORT_HEIGHT;
        this.exportScale = EXPORT_SCALE;
        let exportChart = null;
        try {
            const config = this.buildConfig();
            config.options.responsive = false;
            config.options.devicePixelRatio = 1;
            exportChart = new window.Chart(canvas.getContext("2d"), config);
            return exportChart.toBase64Image("image/png", 1);
        } finally {
            this.exportScale = null;
            if (exportChart) {
                exportChart.destroy();
            }
        }
    }

    // ── 下載圖片 ────────────────────────────────────────────────────────
    onDownload() {
        if (!this.chart) {
            return;
        }
        const link = document.createElement("a");
        link.href = this.exportImage();
        link.download = `${EXPORT_PREFIX}_${this.data.label}_${isoDate(new Date())}.png`;
        document.body.appendChild(link);
        link.click();
        link.remove();
    }
}

registry.category("actions").add(CHARTS_PAGE_TAG, CompanyDashboardCharts);
