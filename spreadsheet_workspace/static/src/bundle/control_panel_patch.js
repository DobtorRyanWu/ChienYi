/** @odoo-module **/
// OCA 編輯器上方列加「存成版本」：開小視窗填說明，不離開編輯器。
// 按鈕要不要出現由 control_panel_patch.xml 依 props.record.workspace_version 判斷
// （只有 spreadsheet.spreadsheet 的 get_spreadsheet_data() 會回這個鍵，模板、儀表板、附件預覽都不會）。

import {SpreadsheetControlPanel} from "@spreadsheet_oca/spreadsheet/bundle/spreadsheet_controlpanel.esm";
import {patch} from "@web/core/utils/patch";

const SAVE_VERSION_ACTION = "spreadsheet_workspace.action_spreadsheet_version_save";

patch(SpreadsheetControlPanel.prototype, {
    onWorkspaceSaveVersion(spreadsheetId) {
        return this.actionService.doAction(SAVE_VERSION_ACTION, {
            additionalContext: {default_spreadsheet_id: spreadsheetId},
        });
    },
});
