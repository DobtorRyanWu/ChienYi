/** @odoo-module **/
// 公司儀表板三頁共用（合約 §0b-33）：常數、把 web_search_read 回來的一筆工程整理成畫面用的列、格式化。
// 指標數字全部來自後端 project.project 的 dash_* 欄位（以看的人的權限算，合約 §1-5）；這裡只做顯示整理，不算任何指標。
// 三頁都沒有新的 RPC：總覽與地圖用核心 web_search_read，單一工程頁走既有 get_project_dashboard_data（方法閘門不用加）。
import { markup } from "@odoo/owl";

export const PROJECT_MODEL = "project.project";
export const ESTIMATE_MODEL = "payment.estimate";
export const OVERVIEW_PAGE_TAG = "company_dashboard_page";
export const PROJECT_PAGE_TAG = "company_dashboard_project";
export const MAP_PAGE_TAG = "company_dashboard_map";
// 總覽每頁工程數；必須等於 models/progress_dashboard_ext.py 的 DASH_PAGE_SIZE（tests 比對）
export const DASH_PAGE_SIZE = 24;
export const ROW_ORDER = "name";
// 預設只列有效且施工中的工程（與原看板的預設篩選相同）
export const DEFAULT_DOMAIN = [["state", "=", "construction"], ["active", "=", true]];
export const KEY_SEPARATOR = ",";
export const NO_ACCESS_MESSAGE = "無權限查看";
export const LOAD_FAILED_MESSAGE = "讀取失敗";
export const STATUS_OK = "ok";
export const STATUS_NO_ACCESS = "no_access";
export const STATUS_ERROR = "error";
export const WEEKDAY_LABELS = ["日", "一", "二", "三", "四", "五", "六"];
export const DEFAULT_CURRENCY_SYMBOL = "NT$";
// Odoo 的 TWD 符號是「$」；畫面照雛型與本地習慣一律寫 NT$（其他幣別照原符號）
const BARE_DOLLAR_SYMBOLS = ["$", "", undefined, null, false];
// 總覽列的日誌 pill 用短標籤（清單只列施工中工程，「非施工中」那半句用不到）
export const LOG_SHORT_LABEL = { not_required: "非工作天" };

// web_search_read 的欄位規格：一列要顯示的全部欄位（總覽與地圖共用）
export const ROW_SPECIFICATION = {
    code: {},
    name: {},
    state: {},
    currency_id: { fields: { symbol: {} } },
    dash_log_today: {},
    dash_workday_elapsed: {},
    dash_workday_total: {},
    dash_workday_note: {},
    dash_workday_state: {},
    dash_today_photo_ids: { fields: {} },
    dash_today_photo_count: {},
    dash_open_defect_count: {},
    dash_overdue_defect_count: {},
    dash_pending_test_count: {},
    dash_latest_estimate_id: { fields: { display_name: {}, estimate_no: {}, state: {}, subtotal: {} } },
    dash_estimate_cum_amount: {},
    dash_estimate_month_amount: {},
    dash_progress_planned: {},
    dash_progress_actual: {},
    dash_progress_variance: {},
    dash_has_schedule: {},
    dash_progress_svg: {},
    dash_denied_keys: {},
    dash_error_keys: {},
};
// 要中文標籤的 Selection 欄位：fields_get 一次拿，不在前端寫死（模型改了會跟著變）
export const SELECTION_FIELDS = {
    [PROJECT_MODEL]: ["dash_log_today", "dash_workday_state"],
    [ESTIMATE_MODEL]: ["state"],
};
// pill 顏色：雛型的 ok（綠）／no（紅）／wait（琥珀）／blue／muted
export const LOG_PILL = { filled: "ok", missing: "no", not_required: "muted", no_calendar: "wait", no_access: "bad", error: "bad" };
export const ESTIMATE_PILL = { draft: "muted", pending_approval: "wait", approved: "ok", archived: "blue" };
const WORKDAY_BAD_STATES = ["no_calendar", "no_dates", "error"];

export function splitKeys(value) {
    return value ? String(value).split(KEY_SEPARATOR).filter(Boolean) : [];
}

/** 指標群組的狀態：無權限／讀取失敗／正常（與原看板卡片相同的三種文字路徑，不以 0 冒充） */
export function groupStatus(denied, failed, group) {
    if (denied.includes(group)) {
        return { status: STATUS_NO_ACCESS, message: NO_ACCESS_MESSAGE, ok: false };
    }
    if (failed.includes(group)) {
        return { status: STATUS_ERROR, message: LOAD_FAILED_MESSAGE, ok: false };
    }
    return { status: STATUS_OK, message: false, ok: true };
}

export function formatAmount(value) {
    return Math.round(Number(value) || 0).toLocaleString("zh-TW");
}

export function formatMoney(value, symbol) {
    const shown = BARE_DOLLAR_SYMBOLS.includes(symbol) ? DEFAULT_CURRENCY_SYMBOL : symbol;
    return `${shown} ${formatAmount(value)}`;
}

export function formatPercent(value, digits = 1) {
    return (Number(value) || 0).toFixed(digits);
}

export function formatQty(value) {
    if (value === null || value === undefined || value === false) {
        return "";
    }
    const number = Number(value);
    return Number.isInteger(number) ? number.toLocaleString("zh-TW") : number.toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

/** "2026-11-10" → "2026-11-10（二）"；沒有就用瀏覽器的今天 */
export function formatDateLabel(iso) {
    let date;
    if (iso) {
        const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
        date = new Date(y, m - 1, d);
    } else {
        date = new Date();
    }
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}（${WEEKDAY_LABELS[date.getDay()]}）`;
}

export function isAccessError(error) {
    const name = error && error.data && error.data.name;
    return Boolean(name && String(name).includes("AccessError"));
}

/** 回 { 模型: { 欄位: { 值: 標籤 } } } */
export async function loadSelectionLabels(orm) {
    const labels = {};
    for (const [model, fieldNames] of Object.entries(SELECTION_FIELDS)) {
        const info = await orm.call(model, "fields_get", [fieldNames, ["selection"]]);
        labels[model] = {};
        for (const [fieldName, field] of Object.entries(info)) {
            labels[model][fieldName] = Object.fromEntries(field.selection || []);
        }
    }
    return labels;
}

/** x2many 在 web_read 不同規格下回 id 清單或 {id} 清單，兩種都收 */
export function recordIds(value) {
    return (value || []).map((item) => (typeof item === "number" ? item : item.id));
}

export function photoThumbUrl(photoId) {
    return `/web/image/supervision.photo/${photoId}/image/128x128`;
}

/** web_search_read 的一筆工程 → 畫面用的列（總覽表、地圖右側小卡、地圖標籤共用） */
export function shapeRow(record, labels) {
    const denied = splitKeys(record.dash_denied_keys);
    const failed = splitKeys(record.dash_error_keys);
    const status = (group) => groupStatus(denied, failed, group);
    const projectLabels = (labels && labels[PROJECT_MODEL]) || {};
    const estimateLabels = ((labels && labels[ESTIMATE_MODEL]) || {}).state || {};
    const variance = Number(record.dash_progress_variance) || 0;
    const latest = record.dash_latest_estimate_id || null;
    const logState = record.dash_log_today || "error";
    return {
        id: record.id,
        code: record.code || "",
        name: record.name || "",
        symbol: (record.currency_id && record.currency_id.symbol) || DEFAULT_CURRENCY_SYMBOL,
        workday: {
            ...status("workday"),
            state: record.dash_workday_state,
            bad: WORKDAY_BAD_STATES.includes(record.dash_workday_state),
            elapsed: record.dash_workday_elapsed || 0,
            total: record.dash_workday_total || 0,
            note: record.dash_workday_note || "",
        },
        progress: {
            ...status("progress"),
            has: Boolean(record.dash_has_schedule),
            planned: Number(record.dash_progress_planned) || 0,
            actual: Number(record.dash_progress_actual) || 0,
            variance,
            behind: variance < 0,
            even: variance === 0,
            svg: record.dash_progress_svg ? markup(record.dash_progress_svg) : null,
        },
        log: {
            ...status("log"),
            state: logState,
            label: (projectLabels.dash_log_today || {})[logState] || logState,
            shortLabel: LOG_SHORT_LABEL[logState] || (projectLabels.dash_log_today || {})[logState] || logState,
            pill: LOG_PILL[logState] || "muted",
        },
        photos: {
            ...status("photo"),
            count: record.dash_today_photo_count || 0,
            ids: recordIds(record.dash_today_photo_ids),
        },
        defects: {
            ...status("defect"),
            open: record.dash_open_defect_count || 0,
            overdue: record.dash_overdue_defect_count || 0,
        },
        tests: {
            ...status("test"),
            count: record.dash_pending_test_count || 0,
        },
        estimate: {
            ...status("estimate"),
            latest: latest
                ? {
                      id: latest.id,
                      name: latest.display_name || "",
                      no: latest.estimate_no,
                      state: latest.state,
                      stateLabel: estimateLabels[latest.state] || latest.state || "",
                      pill: ESTIMATE_PILL[latest.state] || "muted",
                      amount: latest.subtotal || 0,
                  }
                : null,
            cum: record.dash_estimate_cum_amount || 0,
            month: record.dash_estimate_month_amount || 0,
        },
    };
}

/** 工作天欄位的一句話（與原看板相同的四種情況） */
export function workdayText(workday) {
    if (!workday.ok) {
        return workday.message;
    }
    if (workday.bad) {
        return workday.note || "工作天無法計算";
    }
    return `第 ${workday.elapsed}／${workday.total} 工作天${workday.note ? `（${workday.note}）` : ""}`;
}

export function openProjectPage(actionService, projectId, name) {
    return actionService.doAction({
        type: "ir.actions.client",
        tag: PROJECT_PAGE_TAG,
        name: name || "單一工程",
        params: { project_id: projectId },
    });
}
