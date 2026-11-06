/** @odoo-module **/
// 公司儀表板看板（合約 §6）：上方公司合計（每個數字可點下鑽）、營造廠主管未啟用兩步驟驗證的提示、點卡片開單一工程頁。
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { onWillStart, useState } from "@odoo/owl";

const PROJECT_MODEL = "project.project";
const KPI_STATUS_OK = "ok";
const KPI_STATUS_NOT_APPLICABLE = "not_applicable";   // 不是錯誤，是這類帳號用不到的項目：不顯示
const PROGRESS_CHART_TAG = "progress_chart_dashboard";
const KPI_LOAD_ERROR = "讀取失敗";

export class CompanyDashboardKanbanController extends KanbanController {
    static template = "construction_company_dashboard.KanbanView";

    setup() {
        super.setup();
        this.dashOrm = useService("orm");
        this.dashAction = useService("action");
        this.totpMissing = Boolean(session.dash_totp_missing);
        this.dash = useState({ kpis: null, blockedMessage: false, loadError: false, openKey: null });
        onWillStart(() => this.loadKpis());
    }

    async loadKpis() {
        try {
            const data = await this.dashOrm.call(PROJECT_MODEL, "get_dash_company_kpis", []);
            this.dash.kpis = Object.entries(data.kpis)
                .filter(([, kpi]) => kpi.status !== KPI_STATUS_NOT_APPLICABLE)
                .map(([key, kpi]) => ({ key, ...kpi }));
            this.dash.blockedMessage = data.blocked_message || false;
            this.dash.loadError = false;
        } catch (error) {
            // 大聲失敗：合計讀不到就明講，不留空白
            console.error("公司合計讀取失敗", error);
            this.dash.kpis = null;
            this.dash.loadError = KPI_LOAD_ERROR;
        }
    }

    formatAmount(value) {
        return Math.round(value || 0).toLocaleString("zh-TW");
    }

    async onKpiClick(kpi) {
        if (kpi.status !== KPI_STATUS_OK) {
            return;
        }
        if (kpi.parts.length > 1) {
            // 多個資料來源（缺失分一般式／預約式、未歸屬 8 種）：先選要看哪一種
            this.dash.openKey = this.dash.openKey === kpi.key ? null : kpi.key;
            return;
        }
        await this.drilldown(kpi.key, kpi.parts.length ? kpi.parts[0].model : null);
    }

    async drilldown(key, modelName) {
        this.dash.openKey = null;
        const action = await this.dashOrm.call(PROJECT_MODEL, "action_dash_drilldown", [[], key, modelName]);
        await this.dashAction.doAction(action);
    }

    /** 點卡片：開「進度表圖表」頁並帶入工程 */
    async openRecord(record) {
        await this.dashAction.doAction({
            type: "ir.actions.client",
            tag: PROGRESS_CHART_TAG,
            name: "進度表圖表",
            params: { project_id: record.resId },
        });
    }
}

registry.category("views").add("company_dashboard_kanban", {
    ...kanbanView,
    Controller: CompanyDashboardKanbanController,
});
