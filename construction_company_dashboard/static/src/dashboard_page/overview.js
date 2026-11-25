/** @odoo-module **/
// 公司儀表板總覽（合約 §0b-33）：照雛型版面——公司合計卡、「各工程現況」一列一工程、今日現場照片、右上「標案地圖」。
// 資料：公司合計用既有 get_dash_company_kpis／action_dash_drilldown；表用核心 web_search_read 讀 dash_* 欄位
// （一頁 DASH_PAGE_SIZE 列、以看的人的權限算，合約 §1-5）。頁面本身不算指標。
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { Layout } from "@web/search/layout";
import {
    DASH_PAGE_SIZE, DEFAULT_DOMAIN, LOAD_FAILED_MESSAGE, MAP_PAGE_TAG, OVERVIEW_PAGE_TAG, PROJECT_MODEL,
    ROW_ORDER, ROW_SPECIFICATION, STATUS_OK, formatAmount, formatDateLabel, formatMoney, formatPercent,
    loadSelectionLabels, openProjectPage, photoThumbUrl, shapeRow, workdayText,
} from "./dash_common";
import { CHARTS_PAGE_TAG } from "./charts";

const DEADLINE_FILTER_ALL = "all";

const KPI_NOT_APPLICABLE = "not_applicable";
// 五張主卡以外的合計排成一排小卡（雛型沒有，但看板原本就有、使用者看慣了）
const MINOR_KPI_KEYS = ["today_photo", "estimate_cum", "log_today", "unattributed"];
const MINOR_KPI_UNITS = { today_photo: "張", estimate_cum: "", log_today: "張", unattributed: "件" };
const AMOUNT_KPI_KEYS = ["month_estimate", "estimate_cum"];
const PHOTO_THUMBS_PER_PROJECT = 6;

export class CompanyDashboardOverview extends Component {
    static template = "construction_company_dashboard.Overview";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        // 總覽是根頁：自己有抬頭，不再顯示控制列（單一工程頁與地圖才靠麵包屑返回）
        this.display = { controlPanel: false };
        this.totpMissing = Boolean(session.dash_totp_missing);
        this.labels = {};
        this.kpi = useState({ loading: true, data: null, error: false, openKey: null });
        this.table = useState({ loading: true, error: false, rows: [], count: 0, offset: 0, search: "" });
        this.deadline = useState({ loading: true, data: null, error: false, filter: DEADLINE_FILTER_ALL });
        this.monthly = useState({ loading: true, data: null, error: false });
        this.calendar = useState({ loading: true, data: null, error: false });
        this.pageSize = DASH_PAGE_SIZE;
        // 不是從選單進來時（別頁按「返回總覽」、直接開網址、重新整理），這一頁沒有名稱：
        // 從這裡點數字開清單，麵包屑的上一層會顯示「未命名的」。其他三頁同樣自己設名稱
        if (this.env.config && typeof this.env.config.setDisplayName === "function") {
            this.env.config.setDisplayName("公司儀表板");
        }
        onWillStart(async () => {
            this.labels = await loadSelectionLabels(this.orm);
            await Promise.all([this.loadKpis(), this.loadRows(), this.loadDeadlines(), this.loadMonthly(),
                this.loadCalendar()]);
        });
    }

    // ── 公司合計 ────────────────────────────────────────────────────────
    async loadKpis() {
        this.kpi.loading = true;
        try {
            this.kpi.data = await this.orm.call(PROJECT_MODEL, "get_dash_company_kpis", []);
            this.kpi.error = false;
        } catch (error) {
            // 大聲失敗：合計讀不到就明講，不留空白
            console.error("公司合計讀取失敗", error);
            this.kpi.data = null;
            this.kpi.error = LOAD_FAILED_MESSAGE;
        } finally {
            this.kpi.loading = false;
        }
    }

    get kpis() {
        return (this.kpi.data && this.kpi.data.kpis) || null;
    }

    get blockedMessage() {
        return (this.kpi.data && this.kpi.data.blocked_message) || false;
    }

    get todayLabel() {
        return formatDateLabel(this.kpi.data && this.kpi.data.today);
    }

    /** 一張卡：value／unit／sub 是顯示文字；entry 是可點下鑽的 KPI；extra 是卡上第二個可點數字（逾期、未填） */
    _card(key, label, unit, entry, overrides = {}) {
        const ok = entry && entry.status === STATUS_OK;
        return {
            key,
            label,
            ok,
            message: ok ? false : (entry && entry.message) || LOAD_FAILED_MESSAGE,
            value: ok ? String(entry.count) : "",
            unit,
            sub: false,
            entry,
            extra: null,
            ...overrides,
        };
    }

    get mainCards() {
        const k = this.kpis;
        if (!k) {
            return [];
        }
        const cards = [this._card("construction_project", "施工中工程", "件", k.construction_project)];
        // 今日施工日誌 已填／應填：已填＝今日已填日誌的工程數、應填＝已填＋未填（同一份工作天狀態表）
        const filled = k.log_filled;
        const missing = k.log_missing;
        const logCard = this._card("log_filled", "今日施工日誌 已填／應填", "", filled);
        if (logCard.ok && missing && missing.status === STATUS_OK) {
            const required = filled.count + missing.count;
            logCard.value = `${filled.count} / ${required}`;
            if (missing.count) {
                logCard.extra = { label: "尚有", value: String(missing.count), unit: "件未填", entry: missing, bad: true };
            } else if (required) {
                logCard.extra = { label: "", value: "全部已填", unit: "", entry: null, bad: false };
            } else {
                // 例假日、國定假日：沒有工程該填（不是「全部已填」）
                logCard.extra = { label: "", value: "今日非工作天", unit: "", entry: null, bad: false };
            }
        } else if (logCard.ok) {
            // 已填算得出來、未填算不出來（例：缺政府辦公日曆）：已填照顯示，原因附在旁邊
            logCard.unit = "件已填";
            logCard.extra = { label: "", value: (missing && missing.message) || LOAD_FAILED_MESSAGE, unit: "", entry: null, bad: true };
        }
        cards.push(logCard);
        const defectCard = this._card("open_defect", "待改缺失", "件", k.open_defect);
        if (defectCard.ok && k.overdue_defect && k.overdue_defect.status === STATUS_OK) {
            defectCard.extra = { label: "其中逾期", value: String(k.overdue_defect.count), unit: "件", entry: k.overdue_defect, bad: k.overdue_defect.count > 0 };
        }
        cards.push(defectCard);
        cards.push(this._card("pending_test", "檢驗待補", "件", k.pending_test));
        const month = k.month_estimate;
        cards.push(this._card("month_estimate", "本月估驗金額", "", month, month && month.status === STATUS_OK
            ? { value: formatMoney(month.amount), sub: `${month.count} 期` }
            : {}));
        return cards;
    }

    get minorCards() {
        const k = this.kpis;
        if (!k) {
            return [];
        }
        const cards = [];
        for (const key of MINOR_KPI_KEYS) {
            const entry = k[key];
            if (!entry || entry.status === KPI_NOT_APPLICABLE) {
                continue;
            }
            const card = this._card(key, entry.label, MINOR_KPI_UNITS[key], entry);
            if (card.ok && AMOUNT_KPI_KEYS.includes(key)) {
                card.value = formatMoney(entry.amount);
                card.sub = `${entry.count} 期`;
            }
            cards.push(card);
        }
        return cards;
    }

    async onKpiClick(entry) {
        if (!entry || entry.status !== STATUS_OK) {
            return;
        }
        if (entry.parts.length > 1) {
            // 多個資料來源（缺失分一般式／預約式、未歸屬 8 種）：先選要看哪一種
            this.kpi.openKey = this.kpi.openKey === entry.key ? null : entry.key;
            return;
        }
        await this.drilldown(entry.key, entry.parts.length ? entry.parts[0].model : null);
    }

    async drilldown(key, modelName) {
        this.kpi.openKey = null;
        const action = await this.orm.call(PROJECT_MODEL, "action_dash_drilldown", [[], key, modelName]);
        await this.actionService.doAction(action);
    }

    // ── 期限待辦、每月估驗（淞源 C5）────────────────────────────────────
    /** 讀一個區塊的資料：讀不到就明講（不留空白、不當成 0）。
     *  fetch 由呼叫端給（方法名稱要寫成字串常值，tests/test_dashboard_page.py 的掃描器才看得到、才比得到閘門清單）。 */
    async _loadBlock(block, fetch, what) {
        block.loading = true;
        try {
            block.data = await fetch();
            block.error = false;
        } catch (error) {
            console.error(`${what}讀取失敗`, error);
            block.data = null;
            block.error = LOAD_FAILED_MESSAGE;
        } finally {
            block.loading = false;
        }
    }

    async loadDeadlines() {
        await this._loadBlock(
            this.deadline, () => this.orm.call(PROJECT_MODEL, "get_dash_deadline_items", []), "期限待辦");
    }

    async loadMonthly() {
        await this._loadBlock(
            this.monthly, () => this.orm.call(PROJECT_MODEL, "get_dash_monthly_estimates", []), "每月估驗");
    }

    get deadlineOk() {
        return Boolean(this.deadline.data && this.deadline.data.status === STATUS_OK);
    }

    get deadlineCounts() {
        return this.deadlineOk ? this.deadline.data.counts : null;
    }

    /** 「7 天內」那一格其實是「超過緊急門檻、到提醒門檻為止」：寫成 4–7 天，不和「3 天內」重疊 */
    get deadlineSoonLabel() {
        const data = this.deadline.data;
        return `${data.manager_days + 1}–${data.site_days} 天`;
    }

    get deadlineMoreCount() {
        return this.deadlineOk ? this.deadlineCounts.total - this.deadline.data.items.length : 0;
    }

    /** 清單上方的篩選鈕：全部／逾期／N 天內／N–M 天（數字是全部的件數，不是清單上列出的筆數） */
    get deadlineFilters() {
        const data = this.deadline.data;
        const counts = this.deadlineCounts;
        return [
            { key: DEADLINE_FILTER_ALL, label: "全部", count: counts.total, lamp: null },
            { key: "overdue", label: "逾期", count: counts.overdue, lamp: "overdue" },
            { key: "urgent", label: `${data.manager_days} 天內`, count: counts.urgent, lamp: "urgent" },
            { key: "soon", label: this.deadlineSoonLabel, count: counts.soon, lamp: "soon" },
        ];
    }

    setDeadlineFilter(key) {
        this.deadline.filter = key;
    }

    /** 照篩選鈕過濾後要畫的列（後端給的順序：逾期在最上、期限由近到遠） */
    get deadlineVisibleItems() {
        if (!this.deadlineOk) {
            return [];
        }
        const items = this.deadline.data.items;
        return this.deadline.filter === DEADLINE_FILTER_ALL ? items : items.filter((item) => item.level === this.deadline.filter);
    }

    get deadlineDeniedText() {
        return this.deadlineOk ? this.deadline.data.denied.join("、") : "";
    }

    /** 期限的白話：逾期 3 天／今天到期／還剩 5 天（燈號旁邊一定有這行字，不只靠顏色） */
    deadlineText(item) {
        if (item.days_left < 0) {
            return `逾期 ${-item.days_left} 天`;
        }
        return item.days_left === 0 ? "今天到期" : `還剩 ${item.days_left} 天`;
    }

    async openDeadlineItem(item) {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: item.model,
            res_id: item.res_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ── 近期行事曆（淞源 C7；construction_office 沒裝就整塊不顯示）─────────
    async loadCalendar() {
        await this._loadBlock(
            this.calendar, () => this.orm.call(PROJECT_MODEL, "get_dash_week_calendar", []), "近期行事曆");
    }

    /** 沒裝行事曆模組＝整塊不顯示；讀取失敗要顯示（不然壞了沒人知道） */
    get calendarShown() {
        return Boolean(this.calendar.error || (this.calendar.data && this.calendar.data.installed));
    }

    get calendarOk() {
        return Boolean(this.calendar.data && this.calendar.data.status === STATUS_OK);
    }

    get calendarMoreCount() {
        return this.calendarOk ? this.calendar.data.count - this.calendar.data.items.length : 0;
    }

    /** 第二行小字：權責人・工程・地點（有的才列） */
    calendarSubText(item) {
        return [item.responsible, item.project_name, item.location].filter(Boolean).join("・");
    }

    async openCalendarItem(item) {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "construction.calendar.event",
            res_id: item.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openCalendar() {
        await this.actionService.doAction("construction_office.action_calendar_event");
    }

    get monthlyOk() {
        return Boolean(this.monthly.data && this.monthly.data.status === STATUS_OK);
    }

    /** 橫條長度：相對於這 12 個月裡金額最高的那個月 */
    monthBarStyle(row) {
        const max = this.monthly.data.max_amount || 0;
        return `width: ${max ? Math.round((row.amount / max) * 100) : 0}%`;
    }

    /** 滑鼠停在一列上的說明（橫條本身沒有數字） */
    monthTitle(row) {
        return row.count ? `${row.month}：${row.count} 期，${formatMoney(row.amount)}` : `${row.month}：沒有估驗`;
    }

    formatMoney(value) {
        return formatMoney(value);
    }

    // ── 各工程現況 ──────────────────────────────────────────────────────
    async loadRows() {
        this.table.loading = true;
        this.table.error = false;
        try {
            const domain = [...DEFAULT_DOMAIN];
            const query = this.table.search.trim();
            if (query) {
                domain.push("|", ["name", "ilike", query], ["code", "ilike", query]);
            }
            const result = await this.orm.webSearchRead(PROJECT_MODEL, domain, {
                specification: ROW_SPECIFICATION,
                offset: this.table.offset,
                limit: DASH_PAGE_SIZE,
                order: ROW_ORDER,
            });
            this.table.rows = result.records.map((record) => shapeRow(record, this.labels));
            this.table.count = result.length;
        } catch (error) {
            console.error("各工程現況讀取失敗", error);
            this.table.rows = [];
            this.table.count = 0;
            this.table.error = LOAD_FAILED_MESSAGE;
        } finally {
            this.table.loading = false;
        }
    }

    get pageLabel() {
        if (!this.table.count) {
            return "0 / 0";
        }
        const start = this.table.offset + 1;
        const end = Math.min(this.table.offset + this.table.rows.length, this.table.count);
        return `${start}–${end} / ${this.table.count}`;
    }

    get hasPrev() {
        return this.table.offset > 0;
    }

    get hasNext() {
        return this.table.offset + this.table.rows.length < this.table.count;
    }

    async prevPage() {
        if (this.hasPrev) {
            this.table.offset = Math.max(0, this.table.offset - DASH_PAGE_SIZE);
            await this.loadRows();
        }
    }

    async nextPage() {
        if (this.hasNext) {
            this.table.offset += DASH_PAGE_SIZE;
            await this.loadRows();
        }
    }

    async onSearchInput(ev) {
        this.table.search = ev.target.value || "";
    }

    async onSearchSubmit(ev) {
        if (ev && ev.key && ev.key !== "Enter") {
            return;
        }
        this.table.offset = 0;
        await this.loadRows();
    }

    /** 今日現場照片：當頁有今日照片的工程，每工程一列縮圖 */
    get photoGroups() {
        return this.table.rows
            .filter((row) => row.photos.ok && row.photos.ids.length)
            .map((row) => ({
                id: row.id,
                name: row.name,
                count: row.photos.count,
                ids: row.photos.ids.slice(0, PHOTO_THUMBS_PER_PROJECT),
            }));
    }

    workdayText(row) {
        return workdayText(row.workday);
    }

    formatPercent(value) {
        return formatPercent(value);
    }

    formatAmount(value) {
        return formatAmount(value);
    }

    thumbUrl(photoId) {
        return photoThumbUrl(photoId);
    }

    async openProject(row) {
        await openProjectPage(this.actionService, row.id, row.name);
    }

    async openCharts() {
        await this.actionService.doAction({ type: "ir.actions.client", tag: CHARTS_PAGE_TAG, name: "統計圖表" });
    }

    async openMap() {
        await this.actionService.doAction({ type: "ir.actions.client", tag: MAP_PAGE_TAG, name: "標案地圖" });
    }
}

registry.category("actions").add(OVERVIEW_PAGE_TAG, CompanyDashboardOverview);
