/** @odoo-module **/
// 版本對比（client action）：某個版本 vs 試算表目前內容。
// 伺服器給兩邊各一份「底稿＋未合併操作」，這裡各建一個不顯示的 o-spreadsheet Model
// 把操作重播上去，匯出實際內容後交給 diffWorkbooks 逐格比。

import * as spreadsheet from "@odoo/o-spreadsheet";
import {CHANGE_ADDED, CHANGE_REMOVED, diffWorkbooks} from "./version_diff";
import {Component, onWillStart, useState} from "@odoo/owl";
import {OdooDataProvider} from "@spreadsheet/data_sources/odoo_data_provider";
import {registry} from "@web/core/registry";
import {standardActionServiceProps} from "@web/webclient/actions/action_service";
import {useService} from "@web/core/utils/hooks";

const {Model, load} = spreadsheet;

// 每張工作表最多畫出幾列差異；超過只顯示筆數，避免大檔把瀏覽器卡住
const MAX_DISPLAYED_ROWS_PER_SHEET = 500;
const ACTION_TAG = "spreadsheet_workspace.version_compare";

const CHANGE_LABELS = {
    [CHANGE_ADDED]: "新增",
    [CHANGE_REMOVED]: "清除",
};
const DEFAULT_CHANGE_LABEL = "修改";
const CHANGE_BADGE_CLASSES = {
    [CHANGE_ADDED]: "text-bg-success",
    [CHANGE_REMOVED]: "text-bg-danger",
};
const DEFAULT_CHANGE_BADGE_CLASS = "text-bg-warning";

export class VersionCompareAction extends Component {
    static template = "spreadsheet_workspace.VersionCompare";
    static props = {...standardActionServiceProps};

    setup() {
        this.orm = useService("orm");
        this.state = useState({error: false});
        this.maxRows = MAX_DISPLAYED_ROWS_PER_SHEET;
        this.payload = null;
        this.diff = {sheets: [], total: 0};
        onWillStart(() => this.loadComparison());
    }

    async loadComparison() {
        const params = this.props.action.params || {};
        if (!params.version_id) {
            // 重新整理頁面後動作參數會不見
            this.state.error = "找不到要對比的版本，請回到版本歷史重新點「對比最新版」。";
            return;
        }
        this.payload = await this.orm.call(
            "spreadsheet.workspace.version",
            "get_compare_payload",
            [[params.version_id]]
        );
        this.diff = diffWorkbooks(
            this.materialize(this.payload.from),
            this.materialize(this.payload.to)
        );
    }

    /**
     * 「底稿＋未合併操作」→ 實際內容。Model 的建法比照 OCA 編輯器
     * （spreadsheet_renderer.esm.js），只是不接協作傳輸、不掛到畫面上。
     * @param {{data: Object, revisions: Object[]}} side
     * @returns {Object} exportData() 的結果
     */
    materialize(side) {
        const odooDataProvider = new OdooDataProvider(this.env);
        const model = new Model(
            load(side.data),
            {custom: {env: this.env, orm: this.orm, odooDataProvider}},
            side.revisions || []
        );
        return model.exportData();
    }

    changeLabel(change) {
        return CHANGE_LABELS[change] || DEFAULT_CHANGE_LABEL;
    }

    changeBadgeClass(change) {
        return CHANGE_BADGE_CLASSES[change] || DEFAULT_CHANGE_BADGE_CLASS;
    }

    onClose() {
        this.env.config.historyBack();
    }
}

registry.category("actions").add(ACTION_TAG, VersionCompareAction, {force: true});
