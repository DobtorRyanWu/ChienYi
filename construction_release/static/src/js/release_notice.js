/** @odoo-module **/
/**
 * 後台的更新公告跳窗與維護橫幅。
 *
 * - 公告：web client 啟動時查一次「自己還沒看過的已發布版本」，有就開對話框。
 *   ⚠️ 按「知道了」才寫入已讀；只是開起來看到、關掉分頁，下次登入還會再跳（刻意）。
 * - 橫幅：掛在 NavBar 底下，每一頁都看得到；發布或取消維護預告就收起來。
 */
import { Component, reactive, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { NavBar } from "@web/webclient/navbar/navbar";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

export class ReleaseAnnouncementDialog extends Component {
    static template = "construction_release.AnnouncementDialog";
    static components = { Dialog };
    static props = {
        announcements: { type: Array },
        onAck: { type: Function },
        close: { type: Function },
    };

    async onAck() {
        await this.props.onAck();
        this.props.close();
    }
}

export class ReleaseMaintenanceBanner extends Component {
    static template = "construction_release.MaintenanceBanner";
    static props = {};

    setup() {
        // ⚠️ 一定要 useState：資料是啟動後才非同步填進來的，
        //    直接用 useService 拿到的物件不會讓這個元件重新渲染（實測：橫幅永遠不出現）
        this.notice = useState(useService("construction_release_notice"));
    }
}

export const releaseNoticeService = {
    dependencies: ["orm", "dialog"],
    start(env, { orm, dialog }) {
        const state = reactive({ maintenance: null });
        // ⚠️ 一定要等 web client 掛好再開對話框：服務啟動時畫面還沒掛上，
        //    這時候 dialog.add() 叫得起來卻不會顯示（實測過）。
        // 不 await：查詢失敗或慢，都不應該卡住 web client 啟動
        const load = async () => {
            let notices;
            try {
                notices = await orm.call("construction.release", "get_startup_notices", []);
            } catch (error) {
                // 沒裝好或沒權限就當作沒有公告，不要跳錯誤給使用者；但要留線索
                console.warn("construction_release: 取不到更新公告", error);
                return;
            }
            state.maintenance = notices.maintenance || null;
            const announcements = notices.announcements || [];
            if (announcements.length) {
                dialog.add(ReleaseAnnouncementDialog, {
                    announcements,
                    onAck: () =>
                        orm.call("construction.release", "mark_announcements_read", [
                            announcements.map((a) => a.id),
                        ]),
                });
            }
        };
        // 🔴 還要再等「首頁那個 action 載完」：Odoo 每次換畫面都會 dialog.closeAll()
        //    （action_service.js），登入後載入預設首頁時會把剛開的對話框直接關掉
        //    ——實測是「閃一下就不見」。保險起見另外設一個 4 秒的後備，
        //    萬一某些情況沒有任何 action 也還是要跳。
        const openOnce = () => {
            let done = false;
            const run = () => {
                if (!done) {
                    done = true;
                    load();
                }
            };
            env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () => setTimeout(run, 0), {
                once: true,
            });
            setTimeout(run, 4000);
        };
        env.bus.addEventListener("WEB_CLIENT_READY", openOnce, { once: true });
        return state;
    },
};

registry.category("services").add("construction_release_notice", releaseNoticeService);

// NavBar 底下掛橫幅（在版面流裡，不會蓋到內容）
patch(NavBar, {
    components: { ...NavBar.components, ReleaseMaintenanceBanner },
});
