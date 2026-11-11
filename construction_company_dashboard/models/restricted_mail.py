# -*- coding: utf-8 -*-
"""受限帳號與訊息、通知（合約 §0b-24、§0b-25；S1 fix1／fix2，2026-11-10；fix3，2026-11-11）。

帳號定義（都在 construction_supervision_base 的 res.users，全系統各只有一份）：
* 受限帳號 `_dash_is_restricted()`：營造方（後台營造廠主管、前台營造帳號、營造方角色帳號）、控台讀取帳號、後台角色帳號。
* 受限的內部帳號 `_dash_is_restricted_internal()`：上面那些裡面的內部帳號（營造廠主管、控台讀取、後台角色帳號）；
  前台帳號（share）照核心原本的規則。下面「留言／附件／通知／訊息寫入」的守衛都看這一個。

一、公開頻道（合約 §0b-25；使用者 11-06 決定：討論是千溢／監造方內部在用，營造方不用）
讀取與寫入的收窄在 rule_scope.py（公開頻道 channel_type='channel' 與其成員紀錄讀不到、改不了）；這裡管「成員資格」：
* 不自動加入：核心在建帳號、改群組、頻道改「自動加入群組」時，把群組裡的人全部加進頻道
  （mail/models/discuss/res_users.py:13-27、res_groups.py:12、discuss_channel.py:344-365 _subscribe_users_automatically）。
  覆寫 _subscribe_users_automatically_get_members 把受限帳號剔掉（一個程式點涵蓋上面三條路）。
* 既有成員資格移除：升級本模組時（data/restricted_channels.xml 的 function）與帳號的群組／營造標記改變時
  （res_users_guard.py write）移除受限帳號在公開頻道的成員紀錄。私訊（chat）、群組對話（group）不動。
* 訊息搜尋不因「讀不到的來源單據」而整個出錯（11-06 抗辯 red-team F10）：對受限帳號先把來源單據濾成讀得到的再交給核心。

二、受限的內部帳號不能在業務紀錄上發訊息、傳附件（fix1-A）。只有對話（discuss.channel）照常。
1. /mail/message/post、/mail/attachment/upload（mail/controllers/thread.py、attachment.py）：先問
   `_get_mail_message_access(…, 'create')` 要什麼權限，再 `_get_thread_with_access(mode=…)` 取單據，之後以 sudo 發訊息／建附件。
   → MailThread._get_mail_message_access：建立訊息一律要 'write'（交給拒寫規則）；
   → MailThread._get_thread_with_access：讀取以外的模式直接回空（portal 在模式不合格時還接受存取權杖／hash）。
2. ORM／call_kw 的 message_post（含 attachments=、partner_ids=）、message_notify、message_post_with_source、直接建 mail.message：
   都經過 mail.message.create（非 sudo）。→ MailMessage.create：受限內部帳號（非 sudo）只能建對話的訊息。
   直接建 mail.notification 不必另擋：核心規則「mail.notifications: group_user: write its own entries」只准建自己的，
   替自己建「範圍外訊息」的通知又會被 relational_input_guard 擋（訊息讀不到；fix2-N 實測，原本那道守衛已刪）。

三、受限的內部帳號發的訊息都不寄 email、不通知也不加入對話成員以外的人（fix2-J，審查 skeptic r2 F1）——**例外見七**（手機動作）。
   對話照常，所以受限帳號仍在對話裡發訊息；核心的對話收件人＝訊息的 partner_ids（@ 到的人，不限成員），沒有帳號的
   聯絡人一律寄 email；路由對內部帳號不過濾 partner_ids。
   「要不要收窄」＝`_dash_narrow_recipients`（全檔只有這一份）：作者是受限內部帳號（系統以 sudo 或排程代發時
   env.user 不是作者，所以看作者），**或**非 sudo 而且呼叫者本人是受限內部帳號（fix3-S 保證 2：作者是呼叫端指定的，
   保證 1 若漏掉某條路，這裡仍然成立）；扣掉七的手機動作。
   保證 1（fix3-S，審查 skeptic r3 F1：帶 author_id＝監造方人員就繞過了上面的作者判斷）：非 sudo 的受限內部帳號建的訊息，
   作者一定是本人的聯絡人——`MailMessage.create`（message_post、message_notify 都經過它，非 sudo 時以呼叫者身分建；
   含 context 的 default_author_id、message_post 的 email_from 依 email 找出別人當作者）與 `write` 改 author_id
   一律 AccessError。選「拒絕」而不是「改回本人」：介面上沒有任何一條路會替內部帳號帶 author_id
   （/mail/message/post 只收 _get_allowed_message_post_params 列的參數，mail/models/mail_thread.py:2150；
   portal 只替未登入的 token 訪客帶，portal/controllers/thread.py:10-17），帶了就是直接打 RPC——默默改掉會讓呼叫端以為成功。
   系統以 sudo 代發（例：離開對話的「已離開」以離開者為作者，mail/models/discuss/discuss_channel.py:387-389）不受影響。
   擋在三處：
   → `_notify_get_recipients`（mail.thread 與 discuss.channel 兩份核心實作都接）：收件人只留「對話成員、而且是站內類通知」
     （MEMBER_NOTIFICATION_TYPES 白名單：inbox、web_push；fix3-V 起推播照常）；不是對話的單據一個都不留。
     email（_notify_thread_by_email 只寄給收件人裡 notif='email' 的）、簡訊都跟著收件人走。
   → MailMessage.create：訊息的 partner_ids 只留對話成員（partner_ids 也是讀取權：被列在上面的人讀得到這則訊息）；
     例外見九（可 @ 的同事）。write 改 partner_ids 也照同一條（S2 fix3-3，見九）。
   → message_post／message_notify：拿掉 sms 模組的 sms_numbers／sms_pid_to_number（傳簡訊到任意號碼，不經收件人）。
   涵蓋：/mail/message/post（含 /mail/attachment/upload 上傳到對話的附件）、ORM message_post、message_notify、
   私訊對象本身就是外部聯絡人、message_post_with_source（走 message_post）、排程通知（到時重算收件人）。

四、受限的內部帳號不能改、刪業務紀錄上的既有訊息，不能加表情回應（fix2-K，審查 skeptic r2 F2、F3）。
   核心准「訊息的 partner_ids 裡的人」寫入訊息、准「單據的追蹤者」對訊息做建立類操作——被 @ 到內部備註的受限帳號可以把它
   改成一般訊息後讀到內容與附件（同單據的前台帳號也跟著看得到）。
   → MailMessage.write／unlink：非 sudo 時，不是對話的訊息一律拒（/mail/update_is_internal 也是這個 write）；
   → MailMessage._get_with_access：讀取以外的操作，不是對話的訊息一律不給（/mail/message/update_content、/mail/message/reaction）。
   加星號（寫的是 res.partner 的 starred_message_ids）、標為已讀（mail.notification sudo）、讀 chatter 不受影響。

五、內部備註不通知受限帳號（S1；fix2-L 改成與讀取規則同一個判準）：收件人計算時，訊息不符合 rule_scope 的
   NOT_INTERNAL_NOTE（受限帳號讀不到的內部備註，含 is_internal=True 而子類型不是內部的）就拿掉受限帳號。
   原本在 mail.followers._get_recipient_data 自己判斷子類型，少了 is_internal（審查 simplifier r2 F1、red-team r2 G1-1）；
   改到 `_notify_get_recipients`，那裡拿得到訊息，直接 `filtered_domain(NOT_INTERNAL_NOTE)`。
   沒有訊息（只有 msg_vals）一律當內部備註（拒絕方向；fix3-U 拿掉以 new() 手寫欄位求值的備援，那是 NOT_INTERNAL_NOTE
   欄位集合的第二份）。核心 _notify_thread 的三個呼叫端都帶已建立的訊息：mail_thread.py:2320 message_post、
   :2786 message_notify、mail_message_schedule.py:84。

六、內部受限帳號不准把通知方式改成 email（核心讓使用者自己改：mail/models/res_users.py SELF_WRITEABLE_FIELDS
   的 notification_type）——寄出去的信收不回來。前台帳號（share）本來就只能是 email，不受影響。
系統以 sudo 幫受限帳號做的事不受影響（例：改密碼、啟用 TOTP 的安全通知信是 sudo 直接建 mail.mail，不經收件人計算）。

七、手機（前台）動作（S2，2026-11-11；審查 review4-redteam F1、fix2-J 的劃線）
   後台角色帳號在手機做的動作（送審、退件、結案、通知改善、留言…）由前台路由以 sudo 代為執行，作者是角色帳號本人。
   照三的規則它們全部會被收窄成「只剩對話成員」＝業務單據上一個人都不通知（舊的前台帳號做同一個動作會通知負責人、追蹤者）。
   劃線（`_dash_narrow_recipients` 扣掉 `_dash_phone_action`）：
   * **照核心收件人**：業務單據（不是對話）上、系統以 sudo 代發（env.su）、作者就是呼叫者本人、而且本人是有手機能力的
     後台角色帳號（res.users._portal_role_level() 有值：老闆／主管，範圍合格）。這時 partner_ids 是程式碼算的
     （例：缺失的負責人、發現人、通報單的工地主任），不是使用者送進來的；舊的前台帳號做同一個動作也照核心算。
   * **使用者送進來的 partner_ids** 只有前台留言一條路（/mail/message/post 以 sudo 發，核心對內部帳號不過濾 partner_ids）：
     controllers/role_thread.py 對受限內部帳號比照核心對前台帳號的寫法，只留那張單據的追蹤者（核心 _filter_message_post_partners）。
   * **照舊收窄**：對話（仍只留成員的站內通知）；非 sudo（RPC 直接打，本來就建不了業務單據上的訊息，見二-2）；作者不是呼叫者本人；
     沒有手機能力的受限內部帳號（營造廠主管、控台讀取、範圍不合格的角色帳號）。
   * 結果：同一個動作，舊的前台帳號與角色帳號的收件人（聯絡人與通知方式）相同；舊的前台帳號本來就會寄 email 給
     沒有帳號、或通知方式是 email 的追蹤者／負責人，角色帳號照舊（tests/test_role_phone.py 並排比對）。

八、範圍不合格的受限內部帳號（res.users._dash_is_blocked_internal：營造廠主管、角色帳號；控台讀取除外），
   不收業務單據上的任何通知（S2-D，審查 review5-skeptic F1）。範圍不合格＝組合不合法（範圍公司、方別、層級設定錯誤）；
   S2 fix2-Z（使用者 11-11 暫定）起**沒開 TOTP 不再算**（res_users_guard.DASH_REQUIRE_TOTP＝False），通知自然照發——
   常數改回 True 時沒開 TOTP 的又會落在這裡。
   讀取規則另外讓它們讀不到業務單據上的訊息（rule_scope：範圍不合格時 mail.message 只剩對話）；收件人也要先拿掉，
   否則核心組站內通知的 bus 酬載（message.with_user(收件人)）會因為讀不到而讓**發訊息的人**的交易整個失敗。對話照常。

九、唯讀帳號在私訊／群組對話裡 @ 對話外的內部同事（S2 fix2-U；**使用者 11-11 暫定，之後會再改**）：
   * 「內部同事」＝啟用中的內部使用者（share=False）的聯絡人，而且**發訊息的唯讀帳號以自己的權限讀得到**
     （非 sudo；rule_scope 決定範圍：監造方看得到監造公司的人，營造方看不到監造方的人）——`_dash_colleagues`，**只有這一份**
     （S2 fix3-2，審查 s2review2 simplifier U-1、skeptic F5）：送出時的收窄（建立、編輯）與後端 @ 建議名單都呼叫它，
     前端只顯示後端回的聯絡人。
   * 被 @ 到的同事加進訊息的 partner_ids（讀得到那一則）、收**站內**通知：對方偏好 email 也改成站內，絕不產生 mail.mail、
     不寄簡訊；不加入對話成員。前台帳號、沒有帳號的聯絡人、讀不到的內部使用者照三拿掉。
   * 同事的那一列通知自己組（`_dash_colleague_recipients`，S2 fix3-1）：核心的對話收件人 SQL 只取 email 不是空的聯絡人
     （mail/models/discuss/discuss_channel.py:566 `partner.email != %s`，NULL 比較為假），沒有 email 的同事整個收不到
     （dev 啟用中的內部帳號 11 個有 10 個沒 email）。核心那一列（有 email 的同事才有）不沿用，一律在這裡組 notif='inbox'；
     只對使用者發的訊息（與核心同一個判斷，:545-546）。
   * 編輯訊息（/mail/message/update_content 以 sudo 寫 partner_ids，mail/models/mail_thread.py:4698-4705）照建立時同一條收窄
     （S2 fix3-3，審查 skeptic F4）：MailMessage.write 寫完 partner_ids 之後，不在「成員＋可 @ 的同事」裡的拿掉。
   * 只限私訊（chat）、群組對話（group）；業務紀錄照二全拒；手機動作（七）的收件人不變。
   * @ 建議名單：核心在私訊／群組對話只列成員（所有人都一樣；mail/static/src/core/common/suggestion_service.js
     getPartnerSuggestions 的 isNonPublicChannel、res.partner.get_mention_suggestions_from_channel）。唯讀帳號另外列同一份
     「內部同事」（ResPartner.get_mention_suggestions_from_channel；前端 static/src/backend/mention_colleagues_patch.js 只加
     後端對這個對話回過的聯絡人，session 旗標 dash_mention_colleagues）。後台人員與其他帳號照核心。
   * 作者自己重新載入那則訊息：見十。
   * 查證（核心對非成員 partner_ids 沒有第二道收窄）：mail/controllers/thread.py:101-102 只對非內部帳號以
     _filter_message_post_partners（discuss 版 mail/controllers/discuss/thread.py:8-13 只留成員）過濾；
     discuss.channel.message_post（mail/models/discuss/discuss_channel.py:714-731）不動 partner_ids；
     對話的收件人（:529-631）＝partner_ids 依偏好通知＋成員推播。

十、受限的內部帳號看自己發的訊息時，讀不到的通知不給網頁（S2 fix3，驗收真瀏覽器時發現）。
   核心組訊息給網頁時，對內部帳號會帶上訊息的通知（mail/models/mail_message.py:1093-1094、:1182
   `message.notification_ids._filtered_for_web_client()`），逐筆讀通知的欄位。而 dev 的「mail.notifications: group_user」規則
   是 noupdate 的舊資料、perm_read＝True（核心 XML 是 False）：內部帳號只讀得到通知到自己的那幾筆，讀到別人的就 AccessError——
   作者 @ 了同事（九）、在意見回饋單上留言通知了客服之後，**自己打不開那個私訊／那張單**（一般內部帳號在這個規則狀態下也一樣，
   這是資料的狀態，不是本模組造成的；本模組只處理受限內部帳號這一側）。
   → MailNotification._filtered_for_web_client：受限內部帳號（非 sudo）先濾成讀得到的再交給核心。只是「不顯示讀不到的」，
     沒有放寬任何讀取權（規則是核心值時本來就全讀得到，濾了等於沒濾）。
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.osv import expression

from odoo.addons.mail.tools.discuss import Store

from .rule_scope import CHANNEL_TYPE_PUBLIC, NOT_INTERNAL_NOTE

# 受限內部帳號唯一能發訊息的地方：對話
DISCUSS_MODEL = 'discuss.channel'
# _get_thread_with_access 不擋的模式（讀 chatter）
THREAD_READ_MODE = 'read'
DENY_POST_NOTE = '公司儀表板範圍規則：唯讀帳號不能在業務紀錄上留言、上傳附件或通知別人（對話照常）。'
DENY_AUTHOR_NOTE = '公司儀表板範圍規則：唯讀帳號不能以別人的名義發訊息（訊息的作者只能是自己）。'
DENY_MESSAGE_CHANGE_NOTE = '公司儀表板範圍規則：唯讀帳號不能修改、刪除業務紀錄上的訊息，也不能加表情回應（對話照常）。'
# 受限內部帳號發的訊息：收件人只留對話成員的「站內類」通知（fix3-V，白名單）。核心收件人資料的 notif 可能值：
#   'inbox'／'email'：帳號的 notification_type（mail/models/res_users.py:20-23），沒有帳號的聯絡人一律 'email'
#     （mail/models/mail_followers.py:325 'notif': notif，SQL 是 COALESCE(sub_user.notification_type, 'email')；
#     對話：mail/models/discuss/discuss_channel.py:561 同一個 COALESCE）；
#   'web_push'：對話成員的推播（discuss_channel.py:618-628），只有 _notify_thread_by_web_push 用（discuss_channel.py:687）；
#   'sms'：sms 模組把 message_type='sms' 的收件人改成它（sms/models/mail_followers.py:28）。
# 只放 inbox、web_push；email、sms 與將來任何新的值一律剔除。
MEMBER_NOTIFICATION_TYPES = frozenset({'inbox', 'web_push'})
# sms 模組在 message_post／message_notify 接的「另外傳簡訊到這些號碼」參數（sms/models/mail_thread.py _notify_thread_by_sms）
SMS_EXTRA_RECIPIENT_KWARGS = ('sms_numbers', 'sms_pid_to_number')

# res.users.notification_type 的 email 值（mail/models/res_users.py）
NOTIFICATION_TYPE_EMAIL = 'email'
# 檔頭九（使用者 11-11 暫定）：@ 得到對話外內部同事的對話類型，與同事收到的通知方式（一律站內）
MENTION_CHANNEL_TYPES = frozenset({'chat', 'group'})
COLLEAGUE_NOTIFICATION_TYPE = 'inbox'
# 核心對話只通知使用者發的訊息（mail/models/discuss/discuss_channel.py:545-546）；同事那一列照同一個判斷（S2 fix3-1）
CHANNEL_NOTIFIED_MESSAGE_TYPES = frozenset({'comment', 'email', 'email_outgoing', 'whatsapp_message'})

_logger = logging.getLogger(__name__)


def _partner_is_restricted_internal(env, partner_id):
    """這個聯絡人掛著受限的內部帳號（訊息作者用；系統以 sudo 或排程代發時 env.user 不是作者，所以看作者）。"""
    if not partner_id:
        return False
    users = env['res.users'].sudo().with_context(active_test=False).search([('partner_id', '=', partner_id)])
    return any(user._dash_is_restricted_internal() for user in users)


def _dash_phone_action(env, author_id, model):
    """檔頭七：業務單據上、系統以 sudo 代「有手機能力的後台角色帳號本人」發的訊息（手機動作）。"""
    if not env.su or not model or model == DISCUSS_MODEL:
        return False
    user = env.user
    return bool(user and author_id and author_id == user.partner_id.id
                and user._is_role_account() and user._portal_role_level())


def _dash_narrow_recipients(env, author_id, model):
    """這則訊息的收件人要不要收窄成「只剩對話成員」（檔頭三；收件人與 partner_ids 兩道收窄都看它，全檔只有這一份）。

    要收窄＝作者是受限內部帳號（系統以 sudo 或排程代發時 env.user 不是作者），或非 sudo 且呼叫者本人是受限內部帳號
    （fix3-S 保證 2：作者由呼叫端指定）；扣掉檔頭七的手機動作（照核心收件人）。model＝訊息所在單據的模型（沒有單據給 False）。
    S2 fix1-T：原名 _dash_sender_is_restricted，名稱說「作者是不是受限帳號」、實際回的是「要不要收窄」（手機動作回 False），已改名。
    """
    restricted = _partner_is_restricted_internal(env, author_id) or (not env.su and env.user._dash_is_restricted_internal())
    return restricted and not _dash_phone_action(env, author_id, model)


def _restricted_partner_ids(env, partner_ids):
    """partner_ids 之中掛著受限帳號的（同一個聯絡人掛著任何一個受限帳號就算：站內通知是發給聯絡人的）。"""
    if not partner_ids:
        return set()
    users = env['res.users'].sudo().with_context(active_test=False).search([('partner_id', 'in', list(partner_ids))])
    return set(users.filtered(lambda user: user._dash_is_restricted()).partner_id.ids)


def _blocked_partner_ids(env, partner_ids):
    """檔頭八：partner_ids 之中掛著「範圍不合格的受限內部帳號」的（組合不合法：什麼業務資料都不該收到）。"""
    if not partner_ids:
        return set()
    users = env['res.users'].sudo().with_context(active_test=False).search([('partner_id', 'in', list(partner_ids))])
    # 與讀取規則同一個判斷（res.users._dash_is_blocked_internal：rule_scope 讓它們讀不到業務單據上的訊息）
    return set(users.filtered(lambda user: user._dash_is_blocked_internal()).partner_id.ids)


def _dash_internal_user(partner):
    """partner 的啟用中內部帳號（sudo；沒有回空的 recordset）。檔頭九「內部同事」的帳號判斷與同事通知的 uid 都用它。"""
    users = partner.sudo().with_context(active_test=False).user_ids
    return users.filtered(lambda user: user.active and not user.share)[:1]


def _dash_colleagues(env, author, domain, limit=None):
    """檔頭九（使用者 11-11 暫定）：author（res.users）以自己的權限讀得到的、啟用中內部使用者的聯絡人。**只有這一份**
    （S2 fix3-2）：訊息建立與編輯的 partner_ids 收窄、同事的通知、後端 @ 建議名單都呼叫它。

    domain＝額外條件（指定的聯絡人 id，或建議名單的名稱搜尋）；limit＝最多幾筆（建議名單用）。
    讀得到＝非 sudo 搜尋（rule_scope 決定範圍）。是不是啟用中的內部使用者：搜尋時先以儲存欄位 partner_share 縮小
    （與 limit 一起才拿得到「前 N 位同事」），再以 sudo 逐一確認帳號（作者不一定讀得到對方的 res.users，營造方就讀不到
    監造方人員的帳號；OdooBot 的聯絡人 partner_share 也是 False，但它的帳號是停用的，這一步把它拿掉）。
    """
    readable = env['res.partner'].with_user(author).search(
        expression.AND([list(domain), [('partner_share', '=', False)]]), limit=limit)
    return readable.filtered(lambda partner: bool(_dash_internal_user(partner)))


def _dash_colleague_ids(env, author_id, partner_ids):
    """partner_ids 之中作者（聯絡人 id）的內部同事（_dash_colleagues）；作者沒有帳號回空集合。"""
    if not partner_ids or not author_id:
        return set()
    author = env['res.users'].sudo().search([('partner_id', '=', author_id)], limit=1)
    if not author:
        return set()
    return set(_dash_colleagues(env, author, [('id', 'in', list(partner_ids))]).ids)


def _dash_mention_channel(thread):
    """檔頭九：這個 thread 是 @ 得到對話外內部同事的對話（私訊、群組對話）。"""
    return bool(thread) and thread._name == DISCUSS_MODEL and thread.sudo().channel_type in MENTION_CHANNEL_TYPES


def _dash_colleague_recipients(thread, message, msg_vals, author_id, members):
    """檔頭九（使用者 11-11 暫定；S2 fix3-1）：私訊／群組對話裡，訊息 partner_ids 中作者讀得到的內部同事（不是成員、不是作者），
    各一列站內通知（核心收件人資料的格式，mail/models/discuss/discuss_channel.py:571-582）。不靠核心那一列：核心只取有 email 的聯絡人。"""
    if not _dash_mention_channel(thread):
        return []
    # 只通知使用者發的訊息（核心同一個判斷：msg_vals 沒給類型時當 comment）
    message_type = msg_vals.get('message_type', 'comment') if msg_vals else message.message_type
    if message_type not in CHANNEL_NOTIFIED_MESSAGE_TYPES:
        return []
    # 訊息上存的 partner_ids（建立時已收窄成成員＋同事，見 MailMessage.create）；msg_vals 裡的是呼叫端原本送來的
    mentioned = set(message.sudo().partner_ids.ids) if message else {
        pid for pid in msg_vals.get('partner_ids') or [] if isinstance(pid, int)}
    colleague_ids = _dash_colleague_ids(thread.env, author_id, mentioned - members - {author_id})
    rows = []
    for partner in thread.env['res.partner'].sudo().browse(sorted(colleague_ids)):
        user = _dash_internal_user(partner)
        rows.append({
            'active': True, 'id': partner.id, 'is_follower': False, 'groups': [], 'lang': partner.lang,
            'notif': COLLEAGUE_NOTIFICATION_TYPE, 'share': partner.partner_share, 'type': 'user',
            'uid': user.id, 'ushare': user.share,
        })
    return rows


def _dash_filter_recipients(thread, message, msg_vals, recipients):
    """收件人計算的收窄（檔頭三、五、七、八、九）。thread＝發訊息的單據或對話（可能是空的 recordset：沒有單據的通知）。"""
    # 私訊／群組對話：核心沒有算出任何收件人（例：被 @ 的同事都沒有 email、成員都靜音）時，同事那一列仍要組（檔頭九）
    if not recipients and not _dash_mention_channel(thread):
        return recipients
    env = thread.env
    msg_vals = msg_vals or {}
    author_id = msg_vals.get('author_id') or message.author_id.id
    is_discuss = thread._name == DISCUSS_MODEL
    # 沒有單據（空的 recordset）不算業務單據：手機動作的例外（檔頭七）不適用
    if _dash_narrow_recipients(env, author_id, thread._name if thread else False):
        members = set()
        if is_discuss and thread:
            members = set(thread.sudo().channel_member_ids.partner_id.ids)
        recipients = [r for r in recipients if r['notif'] in MEMBER_NOTIFICATION_TYPES and r['id'] in members]
        # 見檔頭九（使用者 11-11 暫定）：讀得到的內部同事一律一列站內通知（S2 fix3-1：自己組，沒有 email 也收得到）
        recipients += _dash_colleague_recipients(thread, message, msg_vals, author_id, members)
    # 見檔頭八：業務單據上的訊息不通知範圍不合格的受限內部帳號（對話照常）
    if recipients and not is_discuss:
        blocked = _blocked_partner_ids(env, {r['id'] for r in recipients})
        recipients = [r for r in recipients if r['id'] not in blocked]
    # 見檔頭五：沒有訊息一律當內部備註（拒絕方向）
    if recipients and not (message and message.sudo().filtered_domain(list(NOT_INTERNAL_NOTE))):
        blocked = _restricted_partner_ids(env, {r['id'] for r in recipients})
        recipients = [r for r in recipients if r['id'] not in blocked]
    return recipients


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _get_mail_message_access(self, res_ids, operation, model_name=None):
        # 見檔頭 1：受限內部帳號在業務紀錄上「建立訊息」一律要寫入權（拒寫規則擋下）；對話照核心。
        # 例外：前台留言者（_is_portal_commenter）照前台帳號「讀得到就能留言」——收件人怎麼算見檔頭七
        mode = super()._get_mail_message_access(res_ids, operation, model_name=model_name)
        if (operation == 'create' and (model_name or self._name) != DISCUSS_MODEL
                and self.env.user._dash_is_restricted_internal()
                and not self._is_portal_commenter(model_name)):
            return 'write'
        return mode

    def _get_thread_with_access(self, thread_id, mode=THREAD_READ_MODE, **kwargs):
        # 見檔頭二-1：讀取以外的模式不給（連存取權杖／hash 的後門一起關掉）；對話照核心。
        # 前台留言者（上面的例外）拿到的模式就是 'read'，不受這裡影響
        if mode != THREAD_READ_MODE and self._name != DISCUSS_MODEL and self.env.user._dash_is_restricted_internal():
            return self.browse()
        return super()._get_thread_with_access(thread_id, mode, **kwargs)

    def _dash_drop_sms_extra_recipients(self, kwargs):
        # 見檔頭三：受限內部帳號不能傳簡訊到任意號碼（不論 sudo：路由以 sudo 呼叫 message_post）
        if self.env.user._dash_is_restricted_internal():
            for key in SMS_EXTRA_RECIPIENT_KWARGS:
                kwargs.pop(key, None)
        return kwargs

    # 這兩支只收窄：方法閘門不把它們算成自訂實作（method_gate.NARROWING_ONLY_OVERRIDES），經 RPC 在對話發訊息照常
    def message_post(self, **kwargs):
        return super().message_post(**self._dash_drop_sms_extra_recipients(kwargs))

    def message_notify(self, **kwargs):
        return super().message_notify(**self._dash_drop_sms_extra_recipients(kwargs))

    def _notify_get_recipients(self, message, msg_vals, **kwargs):
        # 見檔頭三、五
        recipients = super()._notify_get_recipients(message, msg_vals, **kwargs)
        return _dash_filter_recipients(self, message, msg_vals, recipients)


class MailNotification(models.Model):
    _inherit = 'mail.notification'

    def _filtered_for_web_client(self):
        # 見檔頭十：受限內部帳號讀不到的通知（別人的）先拿掉，核心才不會逐筆讀它們的欄位而 AccessError
        records = self
        if not self.env.su and self.env.user._dash_is_restricted_internal():
            records = self._filtered_access('read')
        return super(MailNotification, records)._filtered_for_web_client()


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    # 附件 → 引用它的訊息（mail.message.attachment_ids 的反向，同一張 message_attachment_rel）。
    # 欄位名＝rule_scope.ATTACHMENT_MESSAGES_FIELD；只給 NOT_ONLY_ON_INTERNAL_NOTES 用（規則以 sudo 求值），一般帳號讀不到。
    dash_message_ids = fields.Many2many(
        'mail.message', 'message_attachment_rel', 'attachment_id', 'message_id',
        string='引用此附件的訊息', groups='base.group_system')


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _notify_get_recipients(self, message, msg_vals, **kwargs):
        # 見檔頭三、五：核心的對話版本不呼叫 mail.thread 那份（不看追蹤者），兩份都要接
        recipients = super()._notify_get_recipients(message, msg_vals, **kwargs)
        return _dash_filter_recipients(self, message, msg_vals, recipients)

    def _subscribe_users_automatically_get_members(self):
        new_members = super()._subscribe_users_automatically_get_members()
        partner_ids = {pid for pids in new_members.values() for pid in pids}
        if not partner_ids:
            return new_members
        restricted = self.env['res.partner'].sudo().browse(partner_ids).with_context(
            active_test=False).user_ids.filtered(lambda user: user._dash_is_restricted()).partner_id
        if not restricted:
            return new_members
        blocked = set(restricted.ids)
        return {channel_id: [pid for pid in pids if pid not in blocked] for channel_id, pids in new_members.items()}


class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        if vals.get('notification_type') == NOTIFICATION_TYPE_EMAIL:
            blocked = self.sudo().filtered(lambda user: user._dash_is_restricted_internal())
            if blocked:
                raise ValidationError(_(
                    '帳號「%s」是唯讀的受限帳號（營造廠主管／後台角色帳號／控台讀取），通知只能在系統內收（站內通知），'
                    '不能改成 email。', '、'.join(blocked.mapped('display_name'))))
        return super().write(vals)

    def _dash_leave_public_channels(self):
        """self 之中的受限帳號：移除它們在公開頻道的成員紀錄（sudo；回傳移除筆數）。"""
        restricted = self.sudo().with_context(active_test=False).filtered(lambda user: user._dash_is_restricted())
        if not restricted:
            return 0
        members = self.env['discuss.channel.member'].sudo().search([
            ('partner_id', 'in', restricted.partner_id.ids),
            ('channel_id.channel_type', '=', CHANNEL_TYPE_PUBLIC),
        ])
        if members:
            _logger.info('受限帳號移出公開頻道：%s',
                         ', '.join(f'{m.partner_id.display_name}@{m.channel_id.name}' for m in members))
            members.unlink()
        return len(members)

    @api.model
    def _dash_remove_restricted_channel_memberships(self):
        """升級時呼叫（data/restricted_channels.xml）：全部受限帳號移出公開頻道。可重跑。"""
        partners = self.env['discuss.channel.member'].sudo().search([
            ('channel_id.channel_type', '=', CHANNEL_TYPE_PUBLIC), ('partner_id', '!=', False),
        ]).partner_id
        users = partners.with_context(active_test=False).user_ids
        return users._dash_leave_public_channels()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def get_mention_suggestions_from_channel(self, channel_id, search, limit=8):
        """檔頭九（使用者 11-11 暫定）：唯讀帳號在私訊／群組對話的 @ 建議名單＝核心（成員）＋讀得到的內部同事。其他帳號照核心。"""
        result = super().get_mention_suggestions_from_channel(channel_id, search, limit=limit)
        user = self.env.user
        if not user._dash_is_restricted_internal():
            return result
        channel = self.env[DISCUSS_MODEL].search([('id', '=', channel_id)])
        if not _dash_mention_channel(channel):
            return result
        # 與送出時保留的是同一份（S2 fix3-2）：送出時 partner_ids 收窄也只呼叫 _dash_colleagues
        colleagues = _dash_colleagues(self.env, user, self._get_mention_suggestions_domain(search), limit=limit)
        # sudo 組資料：同事是本人讀得到的，但它們的 res.users 紀錄本人不一定讀得到（_to_store 要讀主帳號判斷是不是內部使用者）
        extra = Store(colleagues.sudo()).get_result()
        for key, rows in extra.items():
            existing = result.setdefault(key, [])
            if isinstance(existing, list) and isinstance(rows, list):
                ids = {row.get('id') for row in existing if isinstance(row, dict)}
                existing.extend(row for row in rows if not (isinstance(row, dict) and row.get('id') in ids))
        return result


class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model_create_multi
    def create(self, vals_list):
        # 見檔頭二-2：受限內部帳號（非 sudo）只能建對話的訊息；model 沒給（含靠 context 預設值帶的）一律當成不是對話
        if not self.env.su and self.env.user._dash_is_restricted_internal() and any(
                vals.get('model') != DISCUSS_MODEL for vals in vals_list):
            raise AccessError(DENY_POST_NOTE)
        # 見檔頭三（fix3-S 保證 1）：作者一定是本人
        self._dash_check_own_author([self._dash_effective_author(vals) for vals in vals_list])
        for vals in vals_list:
            if 'partner_ids' in vals and _dash_narrow_recipients(
                    self.env, self._dash_effective_author(vals), vals.get('model')):
                vals['partner_ids'] = self._dash_member_partner_commands(vals)
        return super().create(vals_list)

    @api.model
    def _dash_effective_author(self, vals):
        """建立後的作者：vals 有給就是它，沒給就是 context 的 default_author_id，再沒有才是欄位預設值（呼叫者本人）。"""
        if 'author_id' in vals:
            return vals['author_id']
        return self.env.context.get('default_author_id', self.env.user.partner_id.id)

    @api.model
    def _dash_check_own_author(self, author_ids):
        """見檔頭三（fix3-S 保證 1）：非 sudo 的受限內部帳號，訊息作者只能是本人的聯絡人（False＝沒有作者也不行）。"""
        if self.env.su or not self.env.user._dash_is_restricted_internal():
            return
        own = self.env.user.partner_id.id
        if any(author_id != own for author_id in author_ids):
            raise AccessError(DENY_AUTHOR_NOTE)

    @api.model
    def _dash_member_partner_commands(self, vals):
        """見檔頭三：受限內部帳號作者的訊息，partner_ids 只留對話成員（不是對話：全拿掉）＋私訊／群組對話裡讀得到的
        內部同事（檔頭九，使用者 11-11 暫定）。只認 (4, id)、(6, 0, ids)。"""
        members = set()
        channel = self.env[DISCUSS_MODEL]
        if vals.get('model') == DISCUSS_MODEL and vals.get('res_id'):
            channel = channel.sudo().browse(vals['res_id'])
            members = set(channel.channel_member_ids.partner_id.ids)
        wanted = []
        for command in vals.get('partner_ids') or []:
            if isinstance(command, (list, tuple)) and len(command) >= 2 and command[0] == 4:
                wanted.append(command[1])
            elif isinstance(command, (list, tuple)) and len(command) == 3 and command[0] == 6:
                wanted.extend(command[2] or [])
        keep = set(members)
        if _dash_mention_channel(channel):
            keep |= _dash_colleague_ids(self.env, self._dash_effective_author(vals), set(wanted) - members)
        return [(6, 0, [pid for pid in wanted if pid in keep])]

    def _dash_deny_business_message_change(self):
        # 見檔頭四：非 sudo 的受限內部帳號，不是對話的訊息一律不准改、刪
        if (not self.env.su and self.env.user._dash_is_restricted_internal()
                and any(message.model != DISCUSS_MODEL for message in self.sudo())):
            raise AccessError(DENY_MESSAGE_CHANGE_NOTE)

    def write(self, vals):
        self._dash_deny_business_message_change()
        if 'author_id' in vals:
            self._dash_check_own_author([vals['author_id']])   # 見檔頭三（fix3-S 保證 1）
        result = super().write(vals)
        if 'partner_ids' in vals:
            self._dash_narrow_written_partners()
        return result

    def _dash_narrow_written_partners(self):
        """見檔頭三、九（S2 fix3-3，審查 skeptic F4）：寫了 partner_ids（編輯訊息 /mail/message/update_content 以 sudo 寫）之後，
        照建立時同一條收窄（_dash_narrow_recipients ＋ _dash_member_partner_commands：成員＋可 @ 的同事）。
        寫完才收窄：寫入值可以是 id 清單或任何 x2many 指令，看結果才不必逐種解讀。"""
        for message in self.sudo():
            if not _dash_narrow_recipients(self.env, message.author_id.id, message.model):
                continue
            current = message.partner_ids.ids
            [(_cmd, _zero, kept)] = self._dash_member_partner_commands({
                'model': message.model, 'res_id': message.res_id, 'author_id': message.author_id.id,
                'partner_ids': [(6, 0, current)]})
            if set(kept) != set(current):
                super(MailMessage, message).write({'partner_ids': [(6, 0, kept)]})

    def unlink(self):
        self._dash_deny_business_message_change()
        return super().unlink()

    @api.model
    def _get_with_access(self, message_id, operation, **kwargs):
        # 見檔頭四：讀取以外（建立類：update_content、表情回應；寫入）不給業務紀錄上的訊息——
        # 核心另有「單據追蹤者」「訊息 partner_ids 裡的人」兩條放行
        message = super()._get_with_access(message_id, operation, **kwargs)
        if (message and operation != THREAD_READ_MODE and message.sudo().model != DISCUSS_MODEL
                and self.env.user._dash_is_restricted_internal()):
            return self.browse()
        return message

    def _filter_records_for_message_operation(self, doc_model, doc_res_ids, operation):
        if self.env.su or not (self.env.user and self.env.user._dash_is_restricted()):
            return super()._filter_records_for_message_operation(doc_model, doc_res_ids, operation)
        # 受限帳號：讀不到（或已刪除）的來源單據先拿掉——核心對它們的判定本來就是「不可見」（見檔頭）
        documents = self.env[doc_model].with_context(active_test=False).browse(doc_res_ids).exists()
        readable = set(documents._filtered_access('read').ids)
        return super()._filter_records_for_message_operation(
            doc_model, [doc_id for doc_id in doc_res_ids if doc_id in readable], operation)
