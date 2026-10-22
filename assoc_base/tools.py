"""公會系統共用工具：QR、寫入守衛哨兵。

守衛哨兵（GUARD）是本系統所有寫入守衛的基礎，設計理由見計畫 §16 通則 1–2：
call_kw 直接把前端送來的 context 套進 env（odoo/api.py:531-532），所以
「context 旗標為真」這種守衛，任何有寫入 ACL 的角色都能用 RPC 偽造。
JSON 造不出 Python 物件，改用 `is GUARD` 比對就擋得住。
"""

import base64
import hashlib
import hmac as hmac_lib
import re
import secrets
import time

from odoo import _, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import hmac as odoo_hmac


class _Guard:
    """寫入守衛的哨兵物件。只有模組內部拿得到，不可序列化。"""

    __slots__ = ()

    def __repr__(self):
        return '<assoc.GUARD>'


GUARD = _Guard()

# 公會所在地的時區。**凡是「公會當地發生的事實」一律用它呈現**：
# 收據取號的日期、前台顯示的領取／繳費時間都屬於這一類——它們不該隨
# 觀看者的時區改變（會員出國看自己的收據，時間不可以跟著跑）。
# 第十輪抗辯實查：前台帳號建立時沒設 tz，示範資料裡 m1-T002／m1-T003
# 的 partner tz 是 `Europe/Brussels`、還有帳號是空的，於是領取時間會印成
# 形狀完全合理但**錯 6 小時**的值——比原本外露微秒的 UTC 更難被發現。
ASSOC_TZ = 'Asia/Taipei'


def assoc_today(record):
    """公會所在地的「今天」。**不看登入者的時區。**

    `fields.Date.context_today()` 走的是 `context['tz']`，拿不到就用
    `env.user.tz`——而前台路由的 `sudo()` **不換 uid**，所以那個 tz 是
    會員自己的設定。第十一輪紅隊實跑把自己的 tz 改成 `Pacific/Kiritimati`
    （UTC+14）：核心在**首次登入**會用瀏覽器 cookie 覆寫 tz
    （`res_users.py:946-949`，條件含 `not user.login_date`），所以連 RPC 都不必，
    `action_grant_portal` 寫的 `ASSOC_TZ` 撐不過第一次登入。
    於是「會籍有效」「已逾期」在到期當天可以被自己推移一天。

    會籍、繳費期限、投票資格都是**公會當地發生的事實**，不是呈現偏好，
    所以釘死公會時區（L2⑳：屬於某地事實的時間不隨觀看者變）。
    """
    return fields.Date.context_today(record.with_context(tz=ASSOC_TZ))


def term_label(term_no):
    """「第 N 屆」。選罷辦法 §6 要求選票載明的法定字串。

    **只留一份**：後台表單、電子選票頁、紙本選票 PDF（M12）印的必須逐字相同，
    在兩個檔案各寫一次就是還沒修好、只是這次記得（L9）。
    刻意**不經 `_()`**：它是法條用語不是 UI 文案，而且 `_()` 的結果若被存進
    stored compute 會凍在建立者的語言。
    （封存包裡的離線驗算腳本不能 import 本模組，那一份重複是必要的。）
    """
    return '第 %s 屆' % term_no


def guarded(env, flag):
    """這次寫入是不是由本系統的方法發動的（而不是 RPC 直接呼叫）。"""
    return env.context.get(flag) is GUARD


def with_guard(records, flag):
    """回傳帶哨兵、而且**洗掉 `default_*` 的 context** 的 recordset。

    內部建立紀錄一律經這支。理由：`with_context()` 是**疊加**，
    呼叫端（`call_kw` 直接套用前端送來的 context）的 `default_state='claimed'`
    會原封流進內部的 `create()`，而 `check_created` 看到哨兵就直接放行——
    等於哨兵把守衛關掉了，而守衛存在的唯一理由就是擋 `default_*`。
    2026-09-20 red-team 以非 system 的公會管理員實跑複現：
    對 `action_ready` 帶 `default_state='claimed'`，32 列全部建成「已領取」。
    """
    clean = {key: value for key, value in records.env.context.items()
             if not key.startswith('default_')}
    # 位置參數＝**取代**整個 context（`models.py:6368-6382`），不是疊加
    return records.with_context(clean, **{flag: GUARD})


def check_created(records, initial, flag):
    """create 驗結果不驗輸入（§16 通則 1）。

    只檢查傳進來的 vals 是不夠的：context 的 `default_*` 與使用者自己建的
    ir.default 都會在 super().create() 內部補進初值（odoo/models.py:1662-1672），
    出納因此可以用 `default_state='paid'` 建出「已繳」的應繳列。
    所以一律在 super().create() 之後比對「產出的紀錄」。

    :param records: super().create() 的回傳值
    :param initial: {欄位名: 允許的初值}
    :param flag: 帶哨兵時可略過檢查的 context 旗標名
    """
    if guarded(records.env, flag):
        return
    for record in records:
        for fname, expected in initial.items():
            value = record[fname]
            if hasattr(value, 'id'):  # Many2one 比 id
                value = value.id or False
            if value != expected:
                raise ValidationError(_(
                    '%(model)s 的「%(field)s」不能在建立時指定，請改用系統提供的動作。',
                    model=records._description,
                    field=records._fields[fname].string,
                ))


FINANCE_GROUPS = ('assoc_portal.group_assoc_finance', 'assoc_base.group_assoc_admin')


def require_finance(env):
    """只有出納或公會管理員可以動錢。

    原本在 dues／period／payment 各寫一份，而且兩邊丟的例外型別還不一樣。
    `AccessError` 繼承 `UserError`，所以統一成前者不會弄壞既有斷言。
    """
    if not any(env.user.has_group(group) for group in FINANCE_GROUPS):
        raise AccessError(_('只有出納或公會管理員可以維護會費。'))


ADMIN_GROUP = 'assoc_base.group_assoc_admin'


def assert_own_company(records, message=None):
    """每一筆記錄都必須落在使用者目前的 allowed companies 內。

    **這支與「你在哪個群組」無關，所以刻意獨立成一支。**
    群組是全域的，公會是逐筆的——L4① 早就寫過「群組回答不了『這一筆』的問題」，
    而這裡是同一條的第二次現身：管理員動作的標準寫法是
    `self._check_admin()` → `ensure_one()` → `.sudo()`，
    而 `ensure_one()` **不讀任何欄位**，所以 `record_rules.xml` 的公會 rule
    從頭到尾沒有機會被觸發，之後又整條走 sudo。
    第十三輪 red-team 實跑：台北的公會管理員對新北的委託書按「已收書面」，
    成功把別家公會的出席列翻成 `proxy`——直接動到人民團體法的法定人數。

    用 `sudo()` 讀 `company_id` 是故意的：這支要**比對**那個值，
    不是要被 rule 擋在讀取之前（被擋就變成「看不到所以放行」的 fail-open）。
    錯誤訊息與群組不足時**完全相同**：分辨得出「不存在」與「不是你的」，
    這支就成了跨公會的存在性探測器。
    """
    env = records.env
    if 'company_id' not in records._fields:
        # 沒有公會欄位的模型不該呼叫這支——寧可當場爆掉，不要靜默放行
        raise AccessError(_('%s 沒有公會欄位，無法判斷歸屬。', records._name))
    if not records:
        # **空 recordset 一律拒絕。** 對「沒有東西」做公會比對，迴圈跑零圈
        # 就靜默通過——那是 L1「一道不可能 FAIL 的閘」。
        # 第十四輪 skeptic 與 simplifier 各自獨立指到同一處：
        # `assoc.gift.export._check_admin` 掛 `@api.model`，於是造冊那條路的
        # 公會檢查從頭到尾沒有執行過，而我把它算進了「七處都補上」。
        # 呼叫端要傳真正要檢查的那筆（造冊傳 `item`），不是空的 `self`。
        raise AccessError(message or _('只有公會管理員可以執行這個動作。'))
    if env.su:
        return          # 內部流程；群組那一半由 `check_guild_admin` 另外把關
    allowed = env.companies
    for record in records:
        company = record.sudo().company_id
        if not company or company not in allowed:
            # **falsy 也要擋（fail-closed）。** `company_id` 的外鍵是
            # ON DELETE SET NULL（DB 實查），公會被刪就會留下一筆
            # 對「每一家公會的管理員」都可寫的紀錄。
            raise AccessError(message or _('只有公會管理員可以執行這個動作。'))


def check_guild_admin(records, message=None):
    """公會管理員動作的唯一入口：**同時**驗群組與公會，缺一不可。

    七個模型各自寫了一份只驗群組的 `_check_admin`（L9：同一個坑寫七次就是還沒修好），
    全部改成呼叫這支。理由與反例見 `assert_own_company`。
    """
    if not records.env.user.has_group(ADMIN_GROUP):
        # **su 也要驗群組。** `sudo()` 只翻 `su`、**不改 uid**，所以
        # `env.user.has_group(...)` 在 sudo 下問的仍然是「這個真人」。
        # 第十三輪我寫成 `if env.su: return`，第十四輪 skeptic 實跑指出
        # 那對七處裡的六處是**淨損失**（它們原本在 sudo 下仍會驗群組），
        # 而 `assoc.meeting.proxy.write()` 的證物欄位只靠這一道把關——
        # 未來任何 `record.sudo().write({'paper_file': …})` 都會讓它靜默消失。
        raise AccessError(message or _('只有公會管理員可以執行這個動作。'))
    assert_own_company(records, message)


def qr_data_uri(env, value, size_px):
    """把值畫成正方形 QR 的 data URI。

    - 一定要明給正方形尺寸：ir.actions.report.barcode() 預設 600×100，會把 QR 拉扁到手機掃不到。
    - 不走 /report/barcode/<值> 網址：那條路由會把值寫進 access log，回應還帶一年期公開快取。
    """
    png = env['ir.actions.report'].barcode('QR', value, width=size_px, height=size_px, barLevel='M')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


# ----------------------------------------------------------------------
# 動態報到碼（計畫 §6）
# ----------------------------------------------------------------------
# 掃碼槍是「鍵盤輸入」：字母會受 Caps Lock、鍵盤配置與中文輸入法影響，
# 所以 token 一律是數字。長度固定 30：'1' + 會員 id(10) + 時窗(8) + MAC(11)。
PASS_SCOPE = 'assoc-pass-v1'
PASS_WINDOW_SECONDS = 30       # 一個時窗 30 秒，驗證時接受「這個」與「上一個」→ 最長 60 秒
PASS_MAC_DIGITS = 11
PASS_TOKEN_RE = re.compile(r'^1[0-9]{29}$')   # 只收 ASCII 數字；isdigit() 會收全形
def sha256_hex(text):
    """十六進位 sha256。存 nonce／單號的雜湊一律走這支。

    **`assoc_election/verify_core.py` 另有一份同名函式，那是刻意的**：
    那個檔案是監票封存包夾帶給監票員的離線驗算公式，硬性要求「只用 stdlib、
    不 import Odoo」，所以它不能從這裡拿。這裡這一份給線上的 Odoo 程式用。
    `assoc_portal/models/assoc_member.py` 原本內嵌 `hashlib.sha256(...)`，
    新的呼叫點一律改用這支，不要再各寫一次（L9）。
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# 委託書單號（計畫 v14 M11）
# ----------------------------------------------------------------------
# **長度必須與另外兩種碼都不重疊**，因為報到台的掃碼分流唯一的判準就是形狀
# （`assoc_meeting_attendance._checkin_by_code`）：
#   * 動態報到碼＝固定 30 位、`1` 開頭
#   * 靜態會員卡＝`str(secrets.randbits(64))`，最多 20 位純數字
# 所以委託書取 **24 位、`2` 開頭**：24 > 20 進不了靜態卡那一支，
# 長度與首碼又都與動態碼不同。`2` 開頭只是多一層人眼可辨，不是安全機制。
#
# 碼的內容＝`2` + proxy_id(10) + 隨機 13 位。**隨機那段存 sha256、不存明碼**，
# 與開通通知單的 `activation_nonce_hash` 同一個形狀——這樣「重印即作廢」
# 是白送的（覆寫 hash 就讓外面那張紙失效），而 HMAC 做不到撤銷（還要另存 nonce）。
PROXY_CODE_DIGITS = 24
PROXY_CODE_RE = re.compile(r'^2[0-9]{23}$')   # 只收 ASCII 數字；isdigit() 會收全形
PROXY_ID_DIGITS = 10
PROXY_RANDOM_DIGITS = 13
PROXY_FORM_SCOPE = 'assoc-proxy-form-v1'


def proxy_form_code(proxy_id):
    """鑄一個委託書單號。明碼只在列印那一次回傳，資料庫只存雜湊。

    `proxy_id` 超出 10 位就 **raise**，不要靜默產出 25 位的碼：
    `'%010d'` 對超長的值是加寬而不是截斷，於是 24 位變 25 位、
    `PROXY_CODE_RE` 再也不收，而呼叫端已經先覆寫了 hash——
    結果是「舊那張紙死了、新那張紙掃不出來」，而且一個錯誤訊息都沒有。
    10^10 筆委託在現實裡到不了，但這裡值兩行。
    """
    if not isinstance(proxy_id, int) or not 0 < proxy_id < 10 ** PROXY_ID_DIGITS:
        raise ValidationError(_('委託書單號無法產生（紀錄編號超出範圍），請洽系統管理員。'))
    return '2%0*d%0*d' % (PROXY_ID_DIGITS, proxy_id,
                          PROXY_RANDOM_DIGITS, secrets.randbelow(10 ** PROXY_RANDOM_DIGITS))


def proxy_form_hash(env, code):
    """單號的儲存形式：**帶伺服器秘密的 HMAC，不是裸 sha256。**

    亂數只有 13 位十進位（約 2^43）而 `proxy_id` 是明碼，所以無鹽 sha256
    的離線搜尋空間就是 10^13——讀得到那個欄位的人（任一公會管理員、任何
    DB dump／BI 匯出）回推得出可掃的碼。走 `odoo_hmac` 之後要先有
    `database.secret` 才算得動，與 `desk_ref`／`pass_token` 同一個形狀。
    """
    return odoo_hmac(env(su=True), PROXY_FORM_SCOPE, code)


def proxy_id_from_code(code):
    """從單號取出 proxy id；形狀不對回 None（**不要讓呼叫端自己切字串**）。

    形狀不對一律回 None 而不是 raise：這個值來自掃碼槍，
    而掃碼槍會送進任何鍵盤打得出來的東西（動態碼那邊是靠 `PASS_TOKEN_RE` 擋同一件事）。
    """
    if not isinstance(code, str) or not PROXY_CODE_RE.match(code):
        return None
    return int(code[1:1 + PROXY_ID_DIGITS])


DESK_REF_SCOPE = 'assoc-desk-ref'
DESK_REF_WINDOW_SECONDS = 300   # 驗證時接受目前與上一個時窗 → 實際有效 5–10 分鐘


def _pass_window(at=None):
    return int(at or time.time()) // PASS_WINDOW_SECONDS


def _pass_mac(env, member, window):
    """MAC 綁會員與會員卡條碼：換發會員卡時，靜態卡與動態碼一起失效。"""
    digest = odoo_hmac(env(su=True), PASS_SCOPE,
                       '%s|%s|%s' % (member.id, member.sudo().barcode, window))
    return int(digest[:16], 16) % (10 ** PASS_MAC_DIGITS)


def pass_token(env, member, at=None):
    """產生這一刻的動態報到碼。"""
    window = _pass_window(at)
    return '1%010d%08d%0*d' % (member.id, window, PASS_MAC_DIGITS, _pass_mac(env, member, window))


def verify_pass_token(env, code):
    """回傳 (member, 'ok'|'expired'|'invalid')。

    先驗 MAC 再看時窗：MAC 不符一律回 invalid（不透露「這個會員存在但碼過期了」）。
    """
    if not code or not PASS_TOKEN_RE.match(code):
        return env['assoc.member'].browse(), 'invalid'
    member_id, window = int(code[1:11]), int(code[11:19])
    mac = code[19:]
    member = env['assoc.member'].sudo().browse(member_id).exists()
    if not member or not member.active:
        return env['assoc.member'].browse(), 'invalid'
    if not hmac_lib.compare_digest(mac, '%0*d' % (PASS_MAC_DIGITS, _pass_mac(env, member, window))):
        return env['assoc.member'].browse(), 'invalid'
    if window not in (_pass_window(), _pass_window() - 1):
        return member, 'expired'
    return member, 'ok'


# 參照碼的來源：掃到實體卡／手機動態碼，還是承辦手動點名
DESK_SOURCE_SCAN = 'scan'
DESK_SOURCE_MANUAL = 'manual'


def desk_ref(env, uid, meeting_id, member_id, at=None, source=DESK_SOURCE_SCAN):
    """報到台的參照碼：證明「這台在這 5 分鐘內**以某種方式**碰過這位會員」。

    代簽與禮品領取是第二段請求，沒有這個就無法分辨「掃碼」與「手動」，
    對帳用的手動筆數會失去意義。

    **`source` 一定要進訊息本身**：手動簽到也會回一把參照碼（不然沒帶卡的人
    沒辦法代簽），若兩種來源鑄出同一把碼，報到台只要「手動簽到某人」就能拿到
    一把碼，再拿它去領那個人的禮品——紀錄會寫成 `scan_self`、
    `manual_reason` 為空、手動領取的稽核整段跳過（2026-09-20 red-team）。
    """
    window = int(at or time.time()) // DESK_REF_WINDOW_SECONDS
    return odoo_hmac(env(su=True), DESK_REF_SCOPE,
                     '%s|%s|%s|%s|%s' % (uid, meeting_id, member_id, window, source))[:32]


DESK_REF_RE = re.compile(r'^[0-9a-f]{32}$')


def verify_desk_ref(env, value, uid, meeting_id, member_id, source=DESK_SOURCE_SCAN):
    """比對前先收斂型別與字元集。

    `hmac.compare_digest` 對非 ASCII 字串丟 TypeError、對非字串丟別的型別錯誤，
    一路傳上去就是 500（動態報到碼那邊是靠 `PASS_TOKEN_RE` 擋掉同一件事）。

    `source` 預設只認「掃碼」鑄出來的碼：呼叫端要的是「卡真的被掃過」，
    手動簽到鑄的那把過不了這裡。
    """
    return desk_ref_source(env, value, uid, meeting_id, member_id) == source


def desk_ref_source(env, value, uid, meeting_id, member_id):
    """這把參照碼是哪一種來源鑄的？認不得就回 None。

    兩種來源要分得開又都要認得：
    - 代簽（M7）接受兩者——承辦手動點名時也確認過身分了，
      不然沒帶卡的受託人就代簽不了。
    - 禮品領取只把 `scan` 當「掃過卡」，`manual` 走手動路徑（要填原因、寫稽核）。
    """
    if not isinstance(value, str) or not DESK_REF_RE.match(value):
        return None
    now = int(time.time())
    for source in (DESK_SOURCE_SCAN, DESK_SOURCE_MANUAL):
        for offset in (0, DESK_REF_WINDOW_SECONDS):
            expected = desk_ref(env, uid, meeting_id, member_id,
                                at=now - offset, source=source)
            if hmac_lib.compare_digest(value, expected):
                return source
    return None


PASS_QR_SIZE_PX = 260


def pass_data_uri(env, member, at=None):
    """把動態報到碼畫成 QR 的 data URI（伺服器產圖，碼不進網址也不進 log）。"""
    return qr_data_uri(env, pass_token(env, member, at=at), PASS_QR_SIZE_PX)
