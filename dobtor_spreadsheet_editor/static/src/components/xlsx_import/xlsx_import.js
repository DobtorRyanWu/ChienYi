/** @odoo-module **/
// Phase 4.5 — Xlsx 高保真匯入預覽（client action）
// 上傳 xlsx → 呼叫 bundle 的 importXlsxToHtmlPreview（OOXML parser + 樣式 + number format）
// → iframe srcdoc 預覽，支援多工作表分頁切換。

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class XlsxImportAction extends Component {
    static template = "dobtor_spreadsheet_editor.XlsxImport";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            sheets: [],
            activeSheet: 0,
            html: "",
            fileName: "",
            error: "",
            opening: false,
        });
        this.buffer = null;
    }

    /** UMD bundle 暴露的全域（web.assets_backend 載入）。*/
    get lib() {
        return window.DobtorSpreadsheetEditor;
    }

    async onFile(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        this.state.error = "";
        this.state.fileName = file.name;
        // 前端大小把關（§4.5.4）：超過 30MB 直接拒絕，不浪費讀取/解析
        const MAX_UPLOAD_BYTES = 30 * 1024 * 1024;
        if (file.size > MAX_UPLOAD_BYTES) {
            this.state.error = `檔案過大：${(file.size / 1048576).toFixed(1)}MB 超過 ${MAX_UPLOAD_BYTES / 1048576}MB 上限`;
            return;
        }
        if (!this.lib || typeof this.lib.importXlsxToHtmlPreview !== "function") {
            this.state.error = "解析器尚未載入（DobtorSpreadsheetEditor bundle 未就緒）";
            return;
        }
        try {
            this.buffer = await file.arrayBuffer();
            this._renderSheet(0);
        } catch (e) {
            this.state.error = `讀取失敗：${e}`;
        }
    }

    selectSheet(idx) {
        if (this.buffer) {
            this._renderSheet(idx);
        }
    }

    _renderSheet(idx) {
        try {
            const preview = this.lib.importXlsxToHtmlPreview(this.buffer, idx);
            this.state.sheets = preview.sheets;
            this.state.activeSheet = preview.activeSheet;
            this.state.html = preview.html;
        } catch (e) {
            this.state.error = `解析失敗：${e}`;
        }
    }

    /** 用我方 xlsx writer 把解析結果重新寫出並下載（Phase 6 round-trip）。*/
    downloadXlsx() {
        if (!this.buffer || !this.lib || typeof this.lib.exportXlsxFromBuffer !== "function") {
            this.state.error = "解析器尚未載入";
            return;
        }
        try {
            const bytes = this.lib.exportXlsxFromBuffer(this.buffer);
            const blob = new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = (this.state.fileName.replace(/\.xlsx$/i, "") || "export") + "_roundtrip.xlsx";
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            this.state.error = `匯出 xlsx 失敗：${e}`;
        }
    }

    /**
     * 把解析結果建成 OCA spreadsheet.spreadsheet 記錄、開 OCA 編輯器（可編輯、繼承 OCA 渲染）。
     */
    async openInOSpreadsheet() {
        if (!this.buffer || !this.lib || typeof this.lib.importXlsxToOSpreadsheetData !== "function") {
            this.state.error = "解析器尚未載入";
            return;
        }
        this.state.opening = true;
        this.state.error = "";
        let action = null;
        try {
            const data = this.lib.importXlsxToOSpreadsheetData(this.buffer);
            const name = this.state.fileName.replace(/\.xlsx$/i, "") || "Imported Xlsx";
            // 命名空間 context：呼叫方（如估驗 bridge）可指定額外 create 欄位（回掛來源記錄）。
            const ctx = (this.props.action && this.props.action.context) || {};
            const extraVals = ctx.sse_create_vals && typeof ctx.sse_create_vals === "object" ? ctx.sse_create_vals : {};
            const ids = await this.orm.create("spreadsheet.spreadsheet", [
                { name, spreadsheet_raw: data, ...extraVals },
            ]);
            const id = Array.isArray(ids) ? ids[0] : ids;
            action = {
                type: "ir.actions.client",
                tag: "action_spreadsheet_oca",
                params: { spreadsheet_id: id, model: "spreadsheet.spreadsheet" },
            };
        } catch (e) {
            this.state.error = `開啟可編輯試算表失敗：${e}`;
            this.state.opening = false;
            return;
        }
        // 重置 state 後再 doAction：導航會銷毀本元件，doAction 之後不可再碰 state（OWL: Component is destroyed）。
        this.state.opening = false;
        // clearBreadcrumbs：以 top-level 開啟 o-spreadsheet（避免深層巢狀 action 下 asset/元件載入問題）。
        await this.action.doAction(action, { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("dobtor_spreadsheet_editor.import", XlsxImportAction);
