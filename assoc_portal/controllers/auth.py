"""以身分證字號登入（計畫 P1、§11「登入等時」）。

為什麼不覆寫 `_get_login_domain`：核心 `_login` 會把**使用者輸入的字串**寫進 INFO log
（`res_users.py:952,955`），session 也存它（`http.py:1097`），失敗頁還會回填到輸入框。
身分證字號一旦走進核心，就等於散進 log、session 檔與畫面。

所以身分證格式的輸入**完全在這裡處理**，核心只會看到換算後的真實 login 或一個固定佔位字串：

1. 先正規化（全形、小寫、空白），寬鬆樣式就走身分證路徑——**檢查碼錯也要走**，
   否則打錯字的身分證會落回核心被寫進 log。
2. 冷卻中直接失敗，不做雜湊（否則每個請求都能逼出 0.44 秒 CPU）。
3. 不論查不查得到，都跑**恰好一次** `verify`：查到就用該帳號的雜湊，其餘情況用 DUMMY_HASH。
   核心對「查無帳號」「空密碼」「空雜湊」都是 0 秒回絕，只補一半會變成反向計時預言。
4. 失敗時另外以身分證索引計數：核心的冷卻計數是以 IP 為 key，**任何人登入成功就整個清空**
   （`res_users.py:1409-1410`），攻擊者用自己的帳號登入一次就能重置。
"""

import logging
import secrets
import time

from odoo import http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.http import request

from odoo.addons.assoc_base import tools_pii

_logger = logging.getLogger(__name__)

# 交給核心的固定 login（一定不存在 → 核心快速失敗、訊息與帳密錯誤相同）。
# 核心的 INFO log 與失敗頁只會看到這個字串或換算後的真實 login，不會看到身分證。
PLACEHOLDER_LOGIN = 'assoc-id-login-unmatched'
MAX_LOGIN_LENGTH = 64          # 身分證只有 10 碼；更長的一律不走這條路徑（NFKC 對超長字串很貴）
ID_FAILURE_LIMIT = 10          # 同一組（身分證, 來源 IP）連續失敗幾次就鎖
ID_FAILURE_WINDOW = 600        # 秒
ID_FAILURE_MAX_ENTRIES = 5000  # 計數表上限：key 由攻擊者決定，不能無限成長

_dummy_hashes = {}      # 輪數 → 假雜湊（每個 worker 各算一次）
_site_rounds = {}       # 這個站實際在用的 pbkdf2 輪數


def _dummy_hash(crypt, rounds=None):
    """與真雜湊**同輪數**的假雜湊；每個 worker 每種輪數產生一次。

    輪數一定要帶進 `crypt.hash()`：只拿它當快取鍵的話，假雜湊永遠是設定檔的預設輪數，
    遇到舊輪數的存量雜湊（例如從別站匯入、或改過 password.hashing.rounds）
    就會出現「查得到會員比較快」的時間差——實測 100000 輪 0.082 秒 vs 600000 輪 0.473 秒。
    """
    key = rounds or 'default'
    if key not in _dummy_hashes:
        secret = secrets.token_urlsafe(16)
        _dummy_hashes[key] = crypt.hash(secret, rounds=int(rounds)) if rounds else crypt.hash(secret)
    return _dummy_hashes[key]


def _hash_rounds(hashed):
    """從 $pbkdf2-sha512$600000$... 取出輪數，讓假雜湊跟著設定走。"""
    parts = (hashed or '').split('$')
    return parts[2] if len(parts) > 3 and parts[2].isdigit() else None


def _remember_rounds(hashed):
    """記住這個站實際在用的輪數，讓之後查無帳號時的假雜湊跟著它走。"""
    rounds = _hash_rounds(hashed)
    if rounds:
        _site_rounds['value'] = rounds


def _last_rounds():
    return _site_rounds.get('value')


def _id_failures():
    """以（身分證索引, 來源 IP）計數的失敗紀錄（行程內，與核心的 IP 計數互不影響）。

    只用身分證當 key 的話，任何人知道某會員的身分證就能從別的 IP 一直打錯、
    把那個人鎖住（身分證在台灣是半公開資訊）。加上 IP 之後，鎖的是「這個人從這個來源」。
    key 由請求方決定，所以要有 TTL 與筆數上限。
    """
    registry = request.env.registry
    failures = getattr(registry, '_assoc_id_failures', None)
    if failures is None:
        failures = registry._assoc_id_failures = {}
    if len(failures) > ID_FAILURE_MAX_ENTRIES:
        deadline = time.time() - ID_FAILURE_WINDOW
        for key in [k for k, (_count, last) in failures.items() if last < deadline]:
            failures.pop(key, None)
        if len(failures) > ID_FAILURE_MAX_ENTRIES:   # 仍然滿：整批丟掉，寧可放行也不要吃光記憶體
            failures.clear()
    return failures


def _failure_key(index):
    source = request.httprequest.remote_addr if request else '?'
    return (index, source)


class AssocAuthHome(AuthSignupHome):

    @http.route()
    def web_login(self, *args, **kw):
        raw_login = request.params.get('login') or ''
        short_enough = (request.httprequest.method == 'POST'
                        and len(raw_login) <= MAX_LOGIN_LENGTH)
        is_id_login = short_enough and tools_pii.looks_like_id(raw_login)
        # 打錯的身分證（長度差一碼、0 打成 O、夾破折號）不符寬鬆樣式，
        # 落到核心就會被原樣寫進 INFO log 並回填登入頁 → 一樣要攔下來，
        # 只是不必查詢（那個形狀不可能對到任何帳號，見 res.users 的 login 約束）
        looks_attempted = (short_enough and not is_id_login
                           and tools_pii.looks_like_id_attempt(raw_login))
        if is_id_login:
            # 核心從此看不到身分證：不是換成真實 login，就是換成固定佔位字串
            request.params['login'] = self._assoc_login_for_id(
                raw_login, request.params.get('password') or '')
        elif looks_attempted:
            request.params['login'] = PLACEHOLDER_LOGIN

        response = super().web_login(*args, **kw)

        if (is_id_login or looks_attempted) and getattr(response, 'qcontext', None) is not None:
            # 失敗頁不要回填任何東西：回填換算後的 Email 等於把登入頁變成「身分證查 Email」
            response.qcontext['login'] = ''
        return response

    def _assoc_login_for_id(self, raw_login, password):
        """身分證 → 真實 login；任何一關不過都回固定佔位字串。"""
        users = request.env['res.users'].sudo()
        crypt = users._crypt_context()
        index = tools_pii.index_hmac(raw_login)
        # 冷卻只「讀」不「加」：失敗的計數交給核心做一次就好
        # （我們自己 raise 一次、佔位 login 再讓核心 raise 一次 → 同一次嘗試被算兩次，
        #   `base.login_cooldown_after` 預設 5 的話，打錯 2.5 次就進冷卻）
        if self._assoc_in_cooldown(users) or self._assoc_id_locked(index):
            return PLACEHOLDER_LOGIN
        user = request.env['assoc.member'].sudo()._user_by_national_id(raw_login)
        hashed = user._assoc_password_hash()   # 空集合也跑同一條查詢
        # 先取輪數再決定用哪個雜湊：寫成 `hashed or _dummy_hash(...)` 會短路，
        # _hash_rounds 永遠拿到空字串，等於沒有跟著輪數走
        if hashed:
            _remember_rounds(hashed)
        reference = hashed or _dummy_hash(crypt, _last_rounds())
        valid, _replacement = crypt.verify_and_update(password, reference)
        if not (user and valid):
            self._assoc_id_failure(index)
            return PLACEHOLDER_LOGIN      # 交給核心失敗一次（冷卻計數由核心累加）
        self._assoc_id_success(index)
        return user.login

    def _assoc_in_cooldown(self, users):
        """讀核心的 IP 冷卻狀態，但不動它的計數。"""
        failures_map = getattr(request.env.registry, '_login_failures', None)
        if not failures_map or not request:
            return False
        failures, previous = failures_map.get(request.httprequest.remote_addr, (0, None))
        if not previous:
            return False
        return users._on_login_cooldown(failures, previous)

    def _assoc_id_locked(self, index):
        entry = _id_failures().get(_failure_key(index))
        if not entry:
            return False
        count, last = entry
        if time.time() - last > ID_FAILURE_WINDOW:
            return False
        return count >= ID_FAILURE_LIMIT

    def _assoc_id_failure(self, index):
        failures = _id_failures()
        key = _failure_key(index)
        count, last = failures.get(key, (0, 0))
        if time.time() - last > ID_FAILURE_WINDOW:
            count = 0
        failures[key] = (count + 1, time.time())

    def _assoc_id_success(self, index):
        # 只清掉自己這一筆：核心成功時會清掉整個 IP 的計數
        _id_failures().pop(_failure_key(index), None)
