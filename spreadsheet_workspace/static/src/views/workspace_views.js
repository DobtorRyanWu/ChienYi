/** @odoo-module **/
// 試算表清單／看板：「新增」不開表單，直接建立空白試算表並進編輯器。
// 清單沿用 OCA 的 SpreadsheetListView（保留上傳 xlsx 的按鈕），只換掉新增行為與按鈕文字。

import {
    SpreadsheetListController,
    SpreadsheetListView,
} from "@spreadsheet_oca/spreadsheet_tree/spreadsheet_tree_view.esm";
import {KanbanController} from "@web/views/kanban/kanban_controller";
import {kanbanView} from "@web/views/kanban/kanban_view";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

const FOLDER_FIELD = "folder_id";

/**
 * 建立時要帶的 context：左側面板目前選了哪個資料夾，新試算表就放進那個資料夾。
 * @param {Object} env 檢視的 env（要有 searchModel）
 * @param {Object} baseContext 動作本身的 context
 * @returns {Object}
 */
function buildCreateContext(env, baseContext) {
    const context = {...(baseContext || {})};
    const searchModel = env.searchModel;
    if (searchModel) {
        const sections = searchModel.getSections(
            (section) => section.type === "category" && section.fieldName === FOLDER_FIELD
        );
        const folderId = sections.length ? sections[0].activeValueId : false;
        if (folderId) {
            context.default_folder_id = folderId;
        }
    }
    return context;
}

async function createBlankAndOpen(controller) {
    const action = await controller.workspaceOrm.call(
        "spreadsheet.spreadsheet",
        "action_create_blank",
        [],
        {context: buildCreateContext(controller.env, controller.props.context)}
    );
    return controller.workspaceAction.doAction(action);
}

export class WorkspaceListController extends SpreadsheetListController {
    setup() {
        super.setup();
        this.workspaceOrm = useService("orm");
        this.workspaceAction = useService("action");
    }

    async createRecord() {
        return createBlankAndOpen(this);
    }
}

export const WorkspaceListView = {
    ...SpreadsheetListView,
    Controller: WorkspaceListController,
    buttonTemplate: "spreadsheet_workspace.ListView.Buttons",
};

export class WorkspaceKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.workspaceOrm = useService("orm");
        this.workspaceAction = useService("action");
    }

    async createRecord() {
        return createBlankAndOpen(this);
    }
}

export const WorkspaceKanbanView = {
    ...kanbanView,
    Controller: WorkspaceKanbanController,
};

registry.category("views").add("spreadsheet_workspace_list", WorkspaceListView);
registry.category("views").add("spreadsheet_workspace_kanban", WorkspaceKanbanView);
