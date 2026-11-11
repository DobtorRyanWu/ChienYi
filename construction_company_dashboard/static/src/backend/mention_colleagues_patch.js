/** @odoo-module **/
// S2 fix2-U（使用者 11-11 暫定，之後會再改）：唯讀帳號（營造廠主管、控台讀取、後台角色帳號；session 旗標
// dash_mention_colleagues）在私訊／群組對話裡打 @，建議名單除了對話成員，另列「讀得到的內部同事」。
// 核心在私訊／群組對話只列成員（suggestion_service.js getPartnerSuggestions 的 isNonPublicChannel）；同事資料由後端
// res.partner.get_mention_suggestions_from_channel（restricted_mail.py 檔頭九，同一個判斷）放進 store，這裡只把 store 裡的
// 內部使用者聯絡人加進候選。送出時後端照樣再判斷一次（讀不到的、不是內部使用者的一律拿掉）。其他帳號照核心。
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { SuggestionService } from "@mail/core/common/suggestion_service";

const MENTION_CHANNEL_TYPES = ["chat", "group"];

patch(SuggestionService.prototype, {
    getPartnerSuggestions(thread) {
        const partners = super.getPartnerSuggestions(thread);
        if (!session.dash_mention_colleagues || !MENTION_CHANNEL_TYPES.includes(thread?.channel_type)) {
            return partners;
        }
        const colleagues = Object.values(this.store.Persona.records).filter(
            (persona) => persona.type === "partner" && persona.isInternalUser && !persona.eq(this.store.odoobot)
        );
        return [...new Set([...partners, ...colleagues])];
    },
});
