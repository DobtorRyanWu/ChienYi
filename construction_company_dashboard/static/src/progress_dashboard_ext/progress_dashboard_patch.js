/** @odoo-module **/
// 進度表圖表頁（合約 §6）：讀 params.project_id 或 context active_id 開啟指定工程；
// 單一工程頁每個區塊的錯誤分開顯示（「無權限查看」「讀取失敗」），不拿空白冒充。
import { patch } from "@web/core/utils/patch";
import { onMounted, useState } from "@odoo/owl";
import { ProgressDashboard } from "@construction_progress/components/progress_dashboard/progress_dashboard";

const BLOCK_STATUS_NO_ACCESS = "no_access";
const BLOCK_STATUS_ERROR = "error";
const BLOCK_FAILED = [BLOCK_STATUS_NO_ACCESS, BLOCK_STATUS_ERROR];
const LOAD_FAILED_MESSAGE = "讀取失敗";
const NO_ACCESS_MESSAGE = "無權限查看";
const BLOCK_TITLES = {
    basic_info: "基本資訊",
    duration_info: "工期資訊",
    progress_summary: "進度狀態",
    change_order_summary: "契約變更",
    defect_summary: "缺失改善",
    test_summary: "檢試驗",
    review_summary: "送審管制",
    today_photos: "今日照片",
    today_log: "今日日誌",
    estimate: "估驗",
};

patch(ProgressDashboard.prototype, {
    setup() {
        super.setup(...arguments);
        this.dashExt = useState({ blockErrors: {}, failedBlocks: [], fatal: false });
        this.blockTitles = BLOCK_TITLES;
        onMounted(() => this.openRequestedProject());
    },

    get requestedProjectId() {
        const action = this.props.action || {};
        const id = (action.params && action.params.project_id) || (action.context && action.context.active_id);
        return id ? Number(id) : null;
    },

    async openRequestedProject() {
        const projectId = this.requestedProjectId;
        if (!projectId) {
            return;
        }
        if (!this.state.projects.some((p) => p.id === projectId)) {
            // 還沒建進度表的工程不在下拉選單裡：補一個選項，下面的區塊與「無進度表」提示照常顯示
            try {
                const [project] = await this.orm.read("project.project", [projectId], ["display_name"]);
                this.state.projects = [...this.state.projects, { id: projectId, name: project.display_name }];
            } catch (error) {
                console.error("讀取工程失敗", error);
                this.dashExt.fatal = this.isAccessError(error) ? NO_ACCESS_MESSAGE : LOAD_FAILED_MESSAGE;
                return;
            }
        }
        await this.onProjectChange({ target: { value: String(projectId) } });
    },

    isAccessError(error) {
        const name = error && error.data && error.data.name;
        return Boolean(name && name.includes("AccessError"));
    },

    async loadDashboardData(projectId) {
        this.state.dashboardLoading = true;
        this.dashExt.fatal = false;
        try {
            const raw = await this.orm.call("project.project", "get_project_dashboard_data", [projectId]);
            const data = {};
            const blockErrors = {};
            for (const [key, block] of Object.entries(raw)) {
                if (block && BLOCK_FAILED.includes(block.status)) {
                    // 舊版卡片只認「有資料／沒資料」：失敗的區塊當沒有資料交給舊模板，原因另列
                    blockErrors[key] = block.message;
                    data[key] = null;
                } else {
                    data[key] = block;
                }
            }
            this.dashExt.blockErrors = blockErrors;
            this.dashExt.failedBlocks = Object.keys(blockErrors);
            this.state.dashboardData = data;
        } catch (error) {
            console.error("Failed to load dashboard data:", error);
            this.dashExt.fatal = this.isAccessError(error) ? NO_ACCESS_MESSAGE : LOAD_FAILED_MESSAGE;
            this.state.dashboardData = null;
        } finally {
            this.state.dashboardLoading = false;
        }
    },
});
