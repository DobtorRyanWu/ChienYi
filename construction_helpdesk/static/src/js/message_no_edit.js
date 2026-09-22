/** @odoo-module **/
/**
 * 服務單上的留言：連「編輯」「刪除」按鈕都不顯示（後台與前台 chatter 都適用）。
 *
 * Odoo 18 的留言動作（編輯／刪除）以 message.editable 決定要不要出現
 * （mail/static/src/core/common/message_actions.js）；editable 預設是「作者本人或管理員」。
 * 這裡只對服務單回傳 false，其他單據維持原行為。
 *
 * 這只是畫面層；真正的阻擋在後端（服務單 _message_update_content ＋ mail.message write/unlink），
 * 即使有人繞過畫面直接呼叫 API 也改不了。
 *
 * 需同時放在 web.assets_backend 與 portal.assets_chatter（前台 chatter 是另一個 bundle）。
 */
import { Message } from "@mail/core/common/message_model";
import { patch } from "@web/core/utils/patch";

const LOCKED_MODELS = ["construction.service.ticket"];

patch(Message.prototype, {
    get editable() {
        if (this.thread && LOCKED_MODELS.includes(this.thread.model)) {
            return false;
        }
        return super.editable;
    },
});
