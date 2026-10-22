"""測試共用工具。"""

from datetime import datetime

import pytz

from odoo.addons.assoc_base.tools import ASSOC_TZ


def guild_today():
    """公會所在地的今天。**刻意不呼叫產品的 `tools.assoc_today()`。**

    產品的日期判定（會籍有效、已逾期、收據取號）一律釘死公會時區，
    而測試若用 `fields.Date.today()`（UTC）當「今天」，兩邊在
    **UTC 16:00–24:00** 這 8 小時會差一天——台北已經跨日、UTC 還沒。
    2026-09-24 21:37 UTC 實際踩到：三支會籍測試同時紅，而且連帶讓
    M8／M9／M10 的 mutation 全部以「基準就是紅的」中止。
    先前每一次全套測試都剛好跑在兩邊同日的時段（L2⑫：測試只跑過
    bug 不會出現的那種幾何）。

    這裡用 `pytz` 直接算，**不重用產品那支函式**：量尺與被量的東西同源時，
    把 `assoc_today` 改壞會讓兩邊一起移動、測試照樣綠（L1④）。
    釘住 `assoc_today` 本身的是 `test_member.py` 那支用凍結時間與日期字面值的測試。
    """
    return datetime.now(pytz.timezone(ASSOC_TZ)).date()


def force_internal_user_on(env, partner, login):
    """硬把一個**內部**帳號安在這筆聯絡人上，繞過 ORM 約束。

    `res.users._check_no_internal_account_on_a_roster_contact` 擋住了
    「設定→使用者→聯絡人挑會員那一筆」這條正常入口，但它擋不住
    `odoo shell` 與直接寫 DB（與本系統其他守衛同級）。
    所以「這個狀態萬一還是成立了」那一層防線（`_partner_sudo()` 拒絕寫入
    內部使用者的聯絡人）仍然要有測試——而要測它就得先造出那個狀態。

    做法：先在別的聯絡人上建帳號（約束不觸發），再用 SQL 換 partner。
    **不要**改成 `with_context(tracking_disable=True)` 之類的把戲：
    那只是關掉別的東西，約束照樣會跑。
    """
    user = env['res.users'].sudo().create({
        'name': login, 'login': login,
        'groups_id': [(6, 0, [env.ref('base.group_user').id])]})
    env.cr.execute("UPDATE res_users SET partner_id = %s WHERE id = %s", [partner.id, user.id])
    env.invalidate_all()
    return user
