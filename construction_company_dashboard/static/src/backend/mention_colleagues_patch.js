/** @odoo-module **/
// S2 fix2-U（使用者 11-11 暫定，之後會再改）：唯讀帳號（營造廠主管、控台讀取、後台角色帳號；session 旗標
// dash_mention_colleagues）在私訊／群組對話裡打 @，建議名單除了對話成員，另列「讀得到的內部同事」。
// 核心在私訊／群組對話只列成員（suggestion_service.js getPartnerSuggestions 的 isNonPublicChannel）。
// S2 fix3-2（審查 s2review2-skeptic F5）：只加**後端對這個對話回過的聯絡人**（res.partner.get_mention_suggestions_from_channel，
// restricted_mail.py 檔頭九 _dash_colleagues——送出時保留的也是同一份），不再列 store 裡所有內部使用者（那會列出讀過 chatter
// 而進了 store、送出時卻被後端拿掉的人，發訊息的人看不出來）。其他帳號照核心。
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { SuggestionService } from "@mail/core/common/suggestion_service";

const MENTION_CHANNEL_TYPES = ["chat", "group"];
const SUGGESTION_METHOD = "get_mention_suggestions_from_channel";

function isColleagueThread(thread) {
    return Boolean(session.dash_mention_colleagues) && MENTION_CHANNEL_TYPES.includes(thread?.channel_type);
}

patch(SuggestionService.prototype, {
    makeOrmCall(model, method, args, kwargs, options) {
        const request = super.makeOrmCall(...arguments);
        if (model !== "res.partner" || method !== SUGGESTION_METHOD || !session.dash_mention_colleagues) {
            return request;
        }
        // 記下後端對這個對話回過的聯絡人（同一個對話累積：每一筆都是後端認可的成員或同事）
        return request.then((data) => {
            this.dashMentionable ??= new Map();
            const known = this.dashMentionable.get(kwargs.channel_id) || new Set();
            for (const row of data?.["res.partner"] || []) {
                known.add(row.id);
            }
            this.dashMentionable.set(kwargs.channel_id, known);
            return data;
        });
    },

    getPartnerSuggestions(thread) {
        const partners = super.getPartnerSuggestions(thread);
        const known = isColleagueThread(thread) && this.dashMentionable?.get(thread.id);
        if (!known?.size) {
            return partners;
        }
        const colleagues = [...known]
            .map((id) => this.store.Persona.get({ type: "partner", id }))
            .filter((persona) => persona && !persona.eq(this.store.odoobot));
        return [...new Set([...partners, ...colleagues])];
    },
});
