/** @odoo-module **/
// 公司儀表板的單一工程頁（合約 §0b-33）：照雛型版面——抬頭（工作天、起迄、預定／實際長條）、今天做什麼、進度曲線、
// 交辦進度：缺失改善、待補檢驗紀錄、本期估驗摘要、現場照片。
// 繼承既有「工程進度儀表板」元件（construction_progress 的 ProgressDashboard，本模組 progress_dashboard_patch.js 已 patch 區塊錯誤處理）：
// Chart.js 的 S 曲線、get_project_dashboard_data／get_progress_chart_data 的呼叫都直接沿用；只換模板、多帶 context 旗標拿三個新區塊。
import { useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { ProgressDashboard } from "@construction_progress/components/progress_dashboard/progress_dashboard";
import {
    ESTIMATE_PILL, LOAD_FAILED_MESSAGE, NO_ACCESS_MESSAGE, OVERVIEW_PAGE_TAG, PROJECT_MODEL, PROJECT_PAGE_TAG,
    formatAmount, formatDateLabel, formatMoney, formatPercent, formatQty, isAccessError, photoThumbUrl, splitKeys,
    groupStatus,
} from "./dash_common";

// models/progress_dashboard_ext.py 的 PAGE_BLOCKS_CONTEXT_KEY：帶了才多拿 today_work／open_defects／pending_tests
const PAGE_BLOCKS_CONTEXT = { dash_page_blocks: true };
const PAGE_BLOCK_TITLES = {
    today_work: "今天做什麼",
    open_defects: "交辦進度：缺失改善",
    pending_tests: "待補檢驗紀錄",
};
// 抬頭要的欄位：工程名、起迄、工作天與進度三值（dash_* 以看的人的權限算；read 是 ORM 讀取 API，閘門放行）
const HEAD_FIELDS = [
    "name", "code", "contract_start_date", "contract_end_date", "actual_start_date",
    "dash_workday_elapsed", "dash_workday_total", "dash_workday_note", "dash_workday_state",
    "dash_progress_planned", "dash_progress_actual", "dash_progress_variance", "dash_has_schedule",
    "dash_denied_keys", "dash_error_keys",
];
const WORKDAY_BAD_STATES = ["no_calendar", "no_dates", "error"];
// 缺失狀態 → pill 顏色（雛型：待改善紅、改善中琥珀、待複查藍）；逾期一律紅
const DEFECT_PILL = { draft: "muted", notified: "no", improving: "wait", improved: "blue", verified: "ok", closed: "ok" };
const PHOTO_THUMBS_LIMIT = 8;

export class CompanyDashboardProject extends ProgressDashboard {
    static template = "construction_company_dashboard.ProjectPage";
    static components = { Layout };

    setup() {
        super.setup();
        this.actionService = useService("action");
        this.display = { controlPanel: {} };
        this.blockTitles = { ...this.blockTitles, ...PAGE_BLOCK_TITLES };
        this.head = useState({ loading: false, data: null, error: false });
        this.todayLabel = formatDateLabel();
    }

    /** 不需要父類的工程下拉選單（它會把所有進度表掃一遍）；openRequestedProject 讀不到名稱時會自己補 */
    async loadProjects() {
        this.state.projects = [];
    }

    /** progress_dashboard_patch.js 的鉤子：多帶 context 旗標拿三個新區塊 */
    dashboardCallKwargs() {
        return { context: PAGE_BLOCKS_CONTEXT };
    }

    async onProjectChange(ev) {
        const projectId = parseInt(ev.target.value);
        await Promise.all([super.onProjectChange(ev), projectId ? this.loadHead(projectId) : Promise.resolve()]);
    }

    async loadHead(projectId) {
        this.head.loading = true;
        this.head.error = false;
        try {
            const [record] = await this.orm.read(PROJECT_MODEL, [projectId], HEAD_FIELDS);
            const denied = splitKeys(record.dash_denied_keys);
            const failed = splitKeys(record.dash_error_keys);
            const variance = Number(record.dash_progress_variance) || 0;
            if (this.env.config && typeof this.env.config.setDisplayName === "function") {
                this.env.config.setDisplayName(record.name || "單一工程");
            }
            this.head.data = {
                id: record.id,
                name: record.name || "",
                code: record.code || "",
                start: record.actual_start_date || record.contract_start_date || "",
                end: record.contract_end_date || "",
                startIsActual: Boolean(record.actual_start_date),
                workday: {
                    ...groupStatus(denied, failed, "workday"),
                    bad: WORKDAY_BAD_STATES.includes(record.dash_workday_state),
                    elapsed: record.dash_workday_elapsed || 0,
                    total: record.dash_workday_total || 0,
                    note: record.dash_workday_note || "",
                },
                progress: {
                    ...groupStatus(denied, failed, "progress"),
                    has: Boolean(record.dash_has_schedule),
                    planned: Number(record.dash_progress_planned) || 0,
                    actual: Number(record.dash_progress_actual) || 0,
                    variance,
                    behind: variance < 0,
                },
            };
        } catch (error) {
            console.error("單一工程抬頭讀取失敗", error);
            this.head.data = null;
            this.head.error = isAccessError(error) ? NO_ACCESS_MESSAGE : LOAD_FAILED_MESSAGE;
        } finally {
            this.head.loading = false;
        }
    }

    // ── 區塊取用（失敗的區塊在 dashExt.blockErrors，有原因就顯示原因） ──
    get data() {
        return this.state.dashboardData || {};
    }

    block(key) {
        return this.data[key] || null;
    }

    blockError(key) {
        return (this.dashExt.blockErrors && this.dashExt.blockErrors[key]) || false;
    }

    get estimateSummary() {
        const est = this.block("estimate");
        if (!est) {
            return null;
        }
        const basic = this.block("basic_info");
        const contract = basic ? Number(basic.contract_amount) || 0 : 0;
        return {
            latest: est.latest || null,
            cumulative: est.cumulative_amount || 0,
            month: est.month_amount || 0,
            contract,
            ratio: contract ? ((est.cumulative_amount || 0) / contract) * 100 : null,
            symbol: est.currency || "NT$",
        };
    }

    get photoIds() {
        const photos = this.block("today_photos");
        return photos ? (photos.photos || []).slice(0, PHOTO_THUMBS_LIMIT) : [];
    }

    defectPill(row) {
        return row.is_overdue ? "no" : DEFECT_PILL[row.state] || "wait";
    }

    estimatePill(latest) {
        return (latest && ESTIMATE_PILL[latest.state]) || "muted";
    }

    /** 今天做什麼：沒有明細時的一句話（沒填／非工作天／缺日曆各自講清楚，不以空白冒充） */
    todayWorkEmptyText(work) {
        const log = this.block("today_log") || {};
        if (!work) {
            return "";
        }
        if (work.log_state === "filled") {
            return "今日日誌尚未填工項明細";
        }
        if (work.log_state === "missing") {
            return "今日未填";
        }
        if (work.log_state === "no_calendar") {
            return log.message || "缺政府辦公日曆";
        }
        return "今日非工作天，無施工日誌";
    }

    /** 父類畫完後把 Chart.js 自己的標題與圖例關掉：卡片標題與下方圖例已經有了 */
    drawChart(data) {
        super.drawChart(data);
        const plugins = this.chart && this.chart.options && this.chart.options.plugins;
        if (plugins) {
            if (plugins.title) {
                plugins.title.display = false;
            }
            if (plugins.legend) {
                plugins.legend.display = false;
            }
            this.chart.update();
        }
    }

    headWorkdayText() {
        const w = this.head.data && this.head.data.workday;
        if (!w) {
            return "";
        }
        if (!w.ok) {
            return w.message;
        }
        if (w.bad) {
            return w.note || "工作天無法計算";
        }
        return `第 ${w.elapsed}／${w.total} 工作天${w.note ? `（${w.note}）` : ""}`;
    }

    formatAmount(value) {
        return formatAmount(value);
    }

    formatMoney(value, symbol) {
        return formatMoney(value, symbol);
    }

    formatPercent1(value) {
        return formatPercent(value);
    }

    formatQty(value) {
        return formatQty(value);
    }

    thumbUrl(photoId) {
        return photoThumbUrl(photoId);
    }

    /** 「← 返回總覽」：有歷史就回上一頁（breadcrumb），否則直接開總覽 */
    async backToOverview() {
        if (this.env.config && typeof this.env.config.historyBack === "function") {
            this.env.config.historyBack();
            return;
        }
        await this.actionService.doAction({ type: "ir.actions.client", tag: OVERVIEW_PAGE_TAG, name: "公司儀表板" });
    }
}

registry.category("actions").add(PROJECT_PAGE_TAG, CompanyDashboardProject);
