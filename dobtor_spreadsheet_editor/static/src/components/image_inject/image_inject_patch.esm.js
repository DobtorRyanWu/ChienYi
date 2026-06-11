/** @odoo-module **/
// §5.3 可編輯圖片 — post-load 注入
//
// xlsx 內嵌圖片不放進初始 spreadsheet_raw（避免 o-spreadsheet v1→v22 遷移對 image figure
// 的 dataSets 假設崩潰）。改由本 patch 在 SpreadsheetRenderer 載入完成後，讀取記錄的
// dobtor_pending_images（JSON），逐一 dispatch CREATE_IMAGE 注入圖片，再清空欄位。

import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";
import { SpreadsheetRenderer } from "@spreadsheet_oca/spreadsheet/bundle/spreadsheet_renderer.esm";

patch(SpreadsheetRenderer.prototype, {
    setup() {
        super.setup();
        onMounted(() => this._dobtorInjectImages());
    },

    /** 讀 dobtor_pending_images → dispatch CREATE_IMAGE → 清空。失敗不阻斷編輯。*/
    async _dobtorInjectImages() {
        try {
            const resModel = this.props.model;
            const resId = this.props.res_id;
            if (resModel !== "spreadsheet.spreadsheet" || !resId) {
                return;
            }
            const recs = await this.orm.read(resModel, [resId], ["dobtor_pending_images"]);
            const raw = recs && recs[0] && recs[0].dobtor_pending_images;
            if (!raw) {
                return;
            }
            const images = JSON.parse(raw);
            if (!Array.isArray(images) || images.length === 0) {
                return;
            }
            const sheetIds = new Set(this.spreadsheet_model.getters.getSheetIds());
            for (const img of images) {
                if (!sheetIds.has(img.sheetId)) {
                    continue; // sheet 不存在（保險）
                }
                this.spreadsheet_model.dispatch("CREATE_IMAGE", {
                    sheetId: img.sheetId,
                    figureId: img.figureId,
                    position: img.position,
                    size: img.size,
                    definition: img.definition,
                });
            }
            // 清空：避免重開時重複注入
            await this.orm.write(resModel, [resId], { dobtor_pending_images: false });
        } catch (e) {
            console.warn("[dobtor] 可編輯圖片注入失敗（不阻斷編輯）:", e);
        }
    },
});
