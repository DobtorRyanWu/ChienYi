"""前台帳號的限制與登入軌跡（計畫 P6、P14、§11）。"""

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.assoc_base import tools_pii

# 會員不能自己改的欄位：
# - name／image_1920：名冊姓名與報到台核對用的照片，改了等於繞過審核
# - company_id：會連帶改掉 partner 的公司（res_users.py:778-781），破壞公會隔離
# - email：日後開寄信時，改 email 就等於可以要重設密碼
# 判準是「**系統會不會拿這個欄位去做判定**，或它代不代表名冊身分」。
# name／image_1920 是名冊姓名與報到核對照片；company_id／email 是身分與聯絡管道。
#
# **`tz` 曾經加進來過，是錯的，而且是線上故障。** 核心在 `_login()` 裡做
# `user = user.with_user(user)` 然後 `user.tz = tz`（`res_users.py:946-949`，
# 條件 `not user.tz or not user.login_date`）——那是 **self-write**，
# 走的正是 `SELF_WRITEABLE_FIELDS` 這條路。`tz` 一旦不在清單裡，核心的
# `for/else` 就不 sudo，改走 ACL，而 portal 帳號對 `res.users` 沒有寫權
# → `AccessError`。它不是 `AccessDenied`，`_login` 的 `except AccessDenied`
# 攔不到，整個 cursor 回滾，於是 `user._update_last_login()` 永遠跑不到、
# `login_date` 永遠是空、下次條件還成立——**那個帳號永久登不進來**。
# 實測（帶 tz cookie 打 `/web/login`）：403
# 「You are not allowed to modify 'User' (res.users) records.」
# 而 `HttpCase.authenticate()` 不經過 HTTP、沒有 request、`cookies.get('tz')`
# 恆為 None，所以整套測試沒有一支抓得到（L2⑫：測試釘死了唯一能成立的幾何）。
#
# 時區那件事的治本在 `tools.assoc_today()`：公會的事實釘死公會時區、
# 不看任何人的設定。鎖欄位本來就攔不到核心自己的寫入，是多餘的第二條皮帶。
MEMBER_LOCKED_FIELDS = ('name', 'image_1920', 'company_id', 'email')
MIN_PASSWORD_LEN = 8      # 與 /assoc/activate 同一個下限


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.constrains('login')
    def _check_login_not_id_shaped(self):
        """帳號不可長得像身分證字號。

        登入頁對這個形狀的輸入一律走身分證路徑、不交給核心（否則輸入會進 INFO log），
        所以這種帳號**永遠登不進來**，而且錯誤訊息是「帳號或密碼錯誤」，完全查不出原因。
        與其讓它在登入時無聲失敗，不如在建立帳號時就講清楚。
        """
        for user in self:
            if tools_pii.looks_like_id_attempt(user.login or ''):
                raise ValidationError(_(
                    '帳號不可使用身分證字號的形狀（會與身分證登入衝突），請改用 Email。'))

    @api.constrains('partner_id', 'groups_id')
    def _check_no_internal_account_on_a_roster_contact(self):
        """名冊那筆聯絡人底下**不可以有內部帳號**。

        只擋住「寫得到」是不夠的，還要擋住「改不回來」。第十二輪紅隊實跑：
        在會員的名冊 partner 上多開一個內部帳號之後，公會管理員從此
        **改不動那位會員的姓名、照片、Email、手機**——四個 inverse 全走
        `_partner_sudo()`，而它見到 partner 是內部使用者就 raise
        「此聯絡人是內部使用者，請由系統管理員維護」；`action_grant_portal`
        也死在同一行。如果姓名或照片在那之前已經被換掉，就等於被**凍結**在名冊上。
        而 `action_revoke_portal` 的復原分支條件是「`member.user_id` 指向內部帳號」，
        在這個攻擊形狀下 `user_id` 仍是合法的 share 帳號——**永遠不會觸發**，
        復原路徑與它宣稱修的攻擊形狀對不上。

        所以在源頭擋：這條路（設定→使用者→聯絡人挑會員那一筆）是那個攻擊唯一的
        正常入口。擋不住 `odoo shell` 與直接寫 DB（與本系統其他守衛同級），
        但那些路徑本來就在「偵測得到、擋不住」的那一類。

        會員自己的前台帳號是 share，不受這條管；純內部職員的 partner 不在名冊上，
        也不受影響（實查：目前庫裡違反這條的帳號 0 筆）。
        """
        for user in self:
            if user.share or not user.partner_id:
                continue
            member = self.env['assoc.member'].sudo().with_context(active_test=False).search(
                [('partner_id', '=', user.partner_id.id)], limit=1)
            if member:
                raise ValidationError(_(
                    '這個聯絡人是公會會員「%(name)s」的名冊資料，不能拿來開內部帳號'
                    '（開了之後公會管理員就改不動那位會員的姓名與照片）。'
                    '請改用另一個聯絡人。', name=member.sudo().member_no))

    @property
    def SELF_WRITEABLE_FIELDS(self):
        """核心允許使用者改自己的這些欄位，而且是以 sudo 寫入（res_users.py:749-758）。

        對前台會員要拿掉——否則 call_kw 一行就能改名冊姓名或換掉報到照片。
        """
        fields_list = super().SELF_WRITEABLE_FIELDS
        # fields_get 是 @api.model（self 為空集合，res_users.py:2153），
        # 這時要看「目前登入者」，否則前台會員拿到的 metadata 會說這些欄位可寫
        users = self if self else self.env.user
        # **判準不是「是不是 share」，是「這個帳號綁著會員嗎」。**
        # 只看 share 的話，被手動連結的**內部**帳號（`user_id` 指到非 share 使用者）
        # 不適用這道移除，於是 P6 那個洞復活：他用 call_kw 改自己 partner 的姓名，
        # 而那就是名冊姓名。`_assoc_member_accounts()` 刻意不濾 share——
        # 擋核心行為要 fail-closed，與「要不要給前台服務」那一側（要求 share）相反。
        # `or` 短路：一般前台會員走 `all(share)` 那條，不會多打一次查詢。
        if users and (all(user.share for user in users) or users._assoc_member_accounts()):
            return [name for name in fields_list if name not in MEMBER_LOCKED_FIELDS]
        return fields_list

    def _assoc_member_accounts(self):
        """這批帳號裡，哪些會**寫到某位會員的名冊 partner 上**（含已停權的會員）。

        **判準是 partner，不是 `user_id`。** 原本只查 `user_id`，而要保護的資產
        （名冊姓名、報到照片）住在 `res.partner` 上——`res_users` 沒有 partner
        唯一約束，所以系統管理員在 Settings 新增一個內部帳號、聯絡人挑會員那一筆，
        就完全繞過：這支回空 → `name` 留在 `SELF_WRITEABLE_FIELDS` → 那個職員
        用核心的「改自己的資料」把名冊姓名與報到照片換掉，
        而公會管理員**改不回來**（`_partner_sudo()` 認定那是內部使用者而拒絕）。
        第十一輪 skeptic 提出、主迴圈獨立複現（rollback，未留資料）：
        名冊姓名 '王志明' → '偽造 名冊姓名'、照片被換、兩道守衛全程沉默。
        這是 L4① 的形狀：擋了鏡像欄位（member 端寫 partner），
        來源端（user 端寫 partner）敞開。

        用 `partner_id` 查同時涵蓋原本的 `user_id` 情形（正常開通的帳號共用同一筆
        partner，`_linked_user()` 就是這樣驗的），所以是純粹的放寬、不會漏掉舊行為。

        active_test=False：會員被停權時預設的 search 會回空 → 攔截失效（守衛反轉）。
        """
        Member = self.env['assoc.member']
        return Member.sudo().with_context(active_test=False).search(
            Member._account_domain(self))

    def action_reset_password(self):
        """會員帳號不走核心的重設密碼信（信不會寄出，核心卻顯示「已寄出」）。"""
        if self._assoc_member_accounts():
            raise UserError(_('會員帳號請改用「列印重設密碼通知單」。'))
        return super().action_reset_password()

    @api.model
    def reset_password(self, login):
        """匿名的 `/web/reset_password` 走這裡（auth_signup/models/res_users.py:157）。

        不能讓它看到 `action_reset_password` 那句「會員帳號請改用…」：
        那句話只對會員帳號出現，等於一個匿名可用的會員枚舉預言
        （核心對查無帳號回 "No account found"，兩種訊息一比就知道這個 Email 是不是會員）。
        對外一律回核心查無帳號的同一句話。
        """
        users = self.sudo().search(self._get_login_domain(login))
        if not users:
            users = self.sudo().search(self._get_email_domain(login))
        if users and users._assoc_member_accounts():
            raise Exception(_('No account found for this login'))
        return super().reset_password(login)

    def _change_password(self, new_passwd):
        """核心只擋空字串（res_users.py `_change_password`），而 `auth_password_policy`
        沒有安裝——`/my/security` 讓會員可以把密碼設成一個字元。

        只對前台帳號設下限：內部帳號沿用核心行為（沙盒的 admin 密碼就很短）。
        """
        if self.share and len((new_passwd or '').strip()) < MIN_PASSWORD_LEN:
            raise UserError(_('密碼至少要 %s 個字元。', MIN_PASSWORD_LEN))
        return super()._change_password(new_passwd)

    def _assoc_password_hash(self):
        """取密碼雜湊（等時登入用）。

        用 `id = ANY(%s)` 讓「查到」與「查無」跑同一條查詢：
        查詢次數不同也是一種時間差。
        """
        self.env.cr.execute("SELECT COALESCE(password, '') FROM res_users WHERE id = ANY(%s)",
                            [self.ids])
        rows = self.env.cr.fetchall()
        return rows[0][0] if len(rows) == 1 else ''

    def _update_last_login(self):
        """登入成功寫一筆軌跡。

        法規要的是「誰在什麼時候碰過個資」，而看得到身分證明文的是後台職員，
        所以**所有使用者**都記——核心的 res.users.log 會被 GC 清掉，撐不到 5 年。
        """
        res = super()._update_last_login()
        for user in self:
            self.env['assoc.audit.log']._log(
                'login_ok', company=user.company_id,
                detail={'share': user.share}, count=1)
        return res
