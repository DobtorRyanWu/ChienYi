"""選舉模組共用的純函式與例外（不依賴 ORM，供模型、控制器、離線驗算共用）。

摘要與雜湊的公式**不在這裡**：它們在 `verify_core.py`（只用 stdlib），
因為監票封存包要夾帶那一份原檔給離線驗算用。這裡只是轉出去，
讓既有的 import 路徑不變——公式寫兩遍的話，兩邊算出不同答案時沒人知道哪邊錯。
"""
import re
import secrets

from odoo.exceptions import UserError

from .verify_core import canonical_json, chain_hash, sha256_hex  # noqa: F401  （轉出）

# 選舉識別碼一律是 uuid4 的正規形式（`assoc.election.create()` 無條件重發），
# 所以公開路由可以先擋形狀。不擋的話 `%00` 會一路走到 psycopg2 才爆
# （`A string literal cannot contain NUL characters`）→ **公開路由回 500**，
# 而 type='json' 的路由還會把整份 traceback 吐給匿名呼叫者。
# 這支放共用：同一個坑第一次只修在 screen.py，vote.py 的五條路由沒跟上。
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def is_election_uuid(value):
    return isinstance(value, str) and bool(UUID_RE.match(value))


# 領取碼 128 bit、票券 nonce 192 bit（URL-safe base64）
CLAIM_TOKEN_BYTES = 16
NONCE_BYTES = 24
PAIR_CODE_DIGITS = 4
# 收據碼：Crockford Base32（去掉易混淆的 I L O U），10 碼分兩段
RECEIPT_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
RECEIPT_LENGTH = 10


class AssocVoteError(UserError):
    """投票／領票流程中可預期的拒絕，只會在寫入之前 raise。code 對應前端訊息。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def clean_token(value, max_length):
    """瀏覽器送來的 token／cookie：只接受 ASCII 且長度合理的字串，其他一律視為沒有。

    非 ASCII 字串丟進 hmac.compare_digest 會拋 TypeError（500），等於給攻擊者一個不留痕跡的試探管道。
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > max_length or not value.isascii():
        return None
    return value


def escape_like(text):
    """ilike 萬用字元跳脫：否則 '%%' 或 '__' 就能列舉名冊。"""
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def new_claim_token():
    return secrets.token_urlsafe(CLAIM_TOKEN_BYTES)


def new_nonce():
    return secrets.token_urlsafe(NONCE_BYTES)


def new_pair_code():
    return f'{secrets.randbelow(10 ** PAIR_CODE_DIGITS):0{PAIR_CODE_DIGITS}d}'


def new_receipt_code():
    raw = ''.join(secrets.choice(RECEIPT_ALPHABET) for _ in range(RECEIPT_LENGTH))
    half = RECEIPT_LENGTH // 2
    return f'{raw[:half]}-{raw[half:]}'


def utc_iso(dt, fmt='%Y-%m-%dT%H:%M:%SZ'):
    """Odoo Datetime 是 naive UTC；稽核鏈與 digest 一律用字串，避免 json.dumps 碰到 datetime。"""
    return dt.strftime(fmt) if dt else ''
