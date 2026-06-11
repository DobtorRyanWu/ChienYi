/** @odoo-module **/
// §4.5.3 Portal 試算表編輯器
//
// 在 portal 前台 mount o-spreadsheet 的純 UI 元件 Spreadsheet（非 OCA SpreadsheetRenderer，
// 後者耦合後端 action hook useSetupAction）。流程：
//   loadBundle("spreadsheet.o_spreadsheet") → 取 @odoo/o-spreadsheet 的 Model/Spreadsheet/load
//   → rpc 取 spreadsheet_raw → new Model → 動態 mount Spreadsheet → 編輯時 debounce 存檔 rpc。

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { loadBundle } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";

const SAVE_DEBOUNCE_MS = 2000;

// spreadsheet.o_spreadsheet bundle 的 spreadsheetLinkMenuCell 服務依賴後端 `menu` 服務
// （webclient 選單，用於 cell 內 odoo menu 連結）。portal 前台無此服務 → 註冊安全 stub
// 滿足依賴（portal 試算表不用 odoo menu 連結）。
const ROOT_MENU = { id: "root", name: "root", children: [], appID: "root", actionID: false };
if (!registry.category("services").contains("menu")) {
    registry.category("services").add("menu", {
        start() {
            return {
                getAll: () => [],
                getApps: () => [],
                getMenu: () => ROOT_MENU,
                getCurrentApp: () => undefined,
                getMenuAsTree: () => ROOT_MENU,
                selectMenu: () => {},
                setCurrentMenu: () => {},
                reload: async () => {},
            };
        },
    });
}

export class PortalSpreadsheet extends Component {
    static template = "dobtor_spreadsheet_editor.PortalSpreadsheet";
    static props = {
        spreadsheetId: { type: Number },
        editable: { type: Boolean, optional: true },
    };

    setup() {
        this.state = useState({ loading: true, error: "", SpreadsheetComp: null, readonlyHint: false });
        this.model = null;
        this._saveTimer = null;
        onWillStart(() => this._boot());
    }

    async _boot() {
        try {
            // o-spreadsheet 主 bundle + 圖表依賴（charts 用）
            await loadBundle("spreadsheet.o_spreadsheet");
            await loadBundle("web.chartjs_lib");
            const oSpreadsheet = odoo.loader.modules.get("@odoo/o-spreadsheet");
            if (!oSpreadsheet) {
                throw new Error("@odoo/o-spreadsheet 未載入");
            }
            const { Model, Spreadsheet, load } = oSpreadsheet;
            const data = await rpc(`/my/spreadsheet/${this.props.spreadsheetId}/data`);
            // 行動版降級唯讀（手機編輯 xlsx 體驗差；§4.5.3）
            const isMobile = window.matchMedia("(max-width: 767px)").matches;
            const editable = this.props.editable && !isMobile;
            this.state.readonlyHint = this.props.editable && isMobile;
            this.model = new Model(load(data.spreadsheet_raw), {
                mode: editable ? "normal" : "readonly",
            });
            if (editable) {
                this.model.on("update", this, () => this._scheduleSave());
            }
            this.state.SpreadsheetComp = Spreadsheet;
            this.state.loading = false;
        } catch (e) {
            this.state.error = String(e && e.message ? e.message : e);
            this.state.loading = false;
        }
    }

    _scheduleSave() {
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => this._save(), SAVE_DEBOUNCE_MS);
    }

    async _save() {
        try {
            const data = this.model.exportData();
            await rpc(`/my/spreadsheet/${this.props.spreadsheetId}/save`, { data });
        } catch (e) {
            // 存檔失敗不阻斷編輯（portal 容錯）
            console.warn("[dobtor] portal 試算表存檔失敗:", e);
        }
    }
}

registry.category("public_components").add("dobtor_spreadsheet_editor.PortalSpreadsheet", PortalSpreadsheet);
