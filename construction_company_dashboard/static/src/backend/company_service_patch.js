/** @odoo-module **/
// 營造廠主管：後台預設開啟全部允許公司（合約 §2；核心 company_service.js:21-32 只開主公司）。
// 作法：公司服務啟動前，若網址與 cookie 都沒有 cids，就先把 cids cookie 設成全部允許公司
// （目前公司在最前面）；使用者之後在公司切換器自己選的，仍照核心寫 cookie。
// 另外沒啟用兩步驟驗證時提示去「我的個人資料」（或「個人設定」）→「帳戶安全性」啟用。前端行為待真瀏覽器驗證（線 C／F）。
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { cookie } from "@web/core/browser/cookie";
import { router } from "@web/core/browser/router";
import { companyService } from "@web/webclient/company_service";

const CIDS_SEPARATOR = "-";

patch(companyService, {
    dependencies: [...companyService.dependencies, "notification"],
    start(env, services) {
        if (session.dash_show_all_allowed_companies && !("cids" in router.current) && !cookie.get("cids")) {
            const { allowed_companies, current_company } = session.user_companies;
            const others = Object.keys(allowed_companies).map(Number).filter((id) => id !== current_company);
            cookie.set("cids", [current_company, ...others].join(CIDS_SEPARATOR));
        }
        if (session.dash_totp_missing) {
            services.notification.add(
                "您的帳號尚未啟用兩步驟驗證，啟用前看不到任何資料。請到右上角頭像 →「我的個人資料」（或「個人設定」）→「帳戶安全性」啟用。",
                { type: "warning", sticky: true }
            );
        }
        return super.start(env, services);
    },
});
