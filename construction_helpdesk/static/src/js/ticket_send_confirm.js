/** @odoo-module **/
/**
 * 後台服務單的防呆：按「傳送訊息」（客戶看得到）時先跳確認視窗。
 * 「記錄備註」是內部備註、客戶看不到，不跳。
 *
 * ⚠️ 只能放在 web.assets_backend：前台 chatter 用的是同一個 Composer 元件，
 *    放進前台 bundle 會讓客戶自己留言時也跳「客戶會看到」的提醒。
 */
import { Composer } from "@mail/core/common/composer";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

const TICKET_MODEL = "construction.service.ticket";

function isCustomerVisibleMessage(composer) {
    return (
        composer.props.type !== "note" &&
        composer.thread?.model === TICKET_MODEL &&
        !composer.props.composer?.message // 編輯既有留言另有後端擋，這裡不處理
    );
}

function askConfirm(composer, body) {
    return new Promise((resolve) => {
        composer.env.services.dialog.add(
            ConfirmationDialog,
            {
                title: _t("這是傳給客戶的訊息嗎？"),
                body,
                confirmLabel: _t("是，傳給客戶"),
                cancelLabel: _t("取消"),
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            },
            { onClose: () => resolve(false) }
        );
    });
}

patch(Composer.prototype, {
    async sendMessage() {
        if (isCustomerVisibleMessage(this)) {
            const ok = await askConfirm(
                this,
                _t("「傳送訊息」客戶在前台會看到。內部討論請改用「記錄備註」。確定要傳送嗎？")
            );
            if (!ok) {
                return;
            }
        }
        return super.sendMessage(...arguments);
    },

    async onClickFullComposer(ev) {
        if (isCustomerVisibleMessage(this)) {
            const ok = await askConfirm(
                this,
                _t("即將開啟完整編輯器撰寫「傳送訊息」，客戶在前台會看到。內部討論請改用「記錄備註」。確定要繼續嗎？")
            );
            if (!ok) {
                return;
            }
        }
        return super.onClickFullComposer(...arguments);
    },
});
