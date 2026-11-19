/** @odoo-module **/
// 版本對比要用到 o-spreadsheet 引擎，引擎在延遲載入的 spreadsheet.o_spreadsheet bundle 裡。
// 這裡只註冊「先載入 bundle、再執行真正動作」的殼；真正的動作在 static/src/bundle/ 內以 force 覆蓋。

import {addSpreadsheetActionLazyLoader} from "@spreadsheet/assets_backend/spreadsheet_action_loader";

addSpreadsheetActionLazyLoader("spreadsheet_workspace.version_compare");
