"""身分證字號的加密、查詢索引與隱碼。

設計（計畫 §11）：
- 明文只在「寫入當下」存在，落地一律是 AES-GCM 密文；AAD 綁 `assoc.member:<id>`，
  把 A 會員的密文搬到 B 會員名下會解不開。
- 查詢（身分證登入、跨公會唯一性）用帶金鑰的 HMAC 索引：身分證的組合空間只有
  約 2.4 億，單純 SHA 可以暴力還原，HMAC 沒有金鑰就算不出來。
- 主金鑰放容器外的檔案（compose 唯讀掛載），DB dump 外洩拿不到明文。
- 顯示一律隱碼：首 2 碼＋末 2 碼，中間 6 碼遮掉。遮末 4 碼是常見做法，但末碼是
  檢查碼，候選只剩約 10^3 組；本法約 10^5 組。

錯誤訊息一律不回顯輸入值（§16 通則 9）。
"""

import base64
import binascii
import hashlib
import hmac
import os
import re
import unicodedata

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from odoo import _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config

ENC_PREFIX = 'v1:'
IDX_PREFIX = 'v1:'
NONCE_BYTES = 12
MASK_CHAR = '*'

# 首字母對應的兩位數字（內政部規則）
LETTER_CODE = {
    'A': 10, 'B': 11, 'C': 12, 'D': 13, 'E': 14, 'F': 15, 'G': 16, 'H': 17,
    'I': 34, 'J': 18, 'K': 19, 'L': 20, 'M': 21, 'N': 22, 'O': 35, 'P': 23,
    'Q': 24, 'R': 25, 'S': 26, 'T': 27, 'U': 28, 'V': 29, 'W': 32, 'X': 30,
    'Y': 31, 'Z': 33,
}
WEIGHTS = (1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1)

PATTERNS = (
    ('tw_id', re.compile(r'^[A-Z][12][0-9]{8}$')),       # 國民身分證
    ('arc_new', re.compile(r'^[A-Z][89][0-9]{8}$')),     # 新式外來人口統一證號
    ('arc_old', re.compile(r'^[A-Z][A-D][0-9]{8}$')),    # 舊式居留證號（2030-12-31 前仍有效）
)
# 登入輸入的寬鬆樣式：檢查碼錯也要走身分證路徑，不能落到核心 _login 被寫進 log
LOOSE_RE = re.compile(r'^[A-Z][A-Z0-9][0-9]{8}$')
# 「看起來是在打身分證，但打錯了」：長度差一碼、0 打成 O、夾了破折號……
# 這些不符 LOOSE_RE，落到核心就會被原樣寫進 INFO log（res_users.py:952）並回填登入頁。
# 判準取「沒有 @、長度 9–11、至少 6 個數字」——這個形狀的合法帳號會被
# `res.users` 的約束擋在建立時（見 assoc_portal/models/res_users.py），
# 所以攔下來不會擋到任何人登入。
ID_ATTEMPT_MIN_DIGITS = 6
ID_ATTEMPT_LENGTH = (9, 11)


def _master_key():
    """讀主金鑰。

    不做快取：金鑰檔只有 45 bytes，每次讀的成本可忽略；
    以 (mtime, size) 當快取鍵反而會在「還原備份／cp -p」後繼續用舊金鑰
    （base64 的 32-byte 金鑰長度固定，等於只剩 mtime 一個判準）。
    """
    inline = config.get('assoc_pii_key')
    if inline:
        # 只給測試注入用：正式環境把金鑰寫進 odoo.conf 等於放進 git 備份範圍
        if not config.get('test_enable'):
            raise UserError(_('金鑰不可寫在設定檔，請改用 assoc_pii_key_file。'))
        key = base64.b64decode(inline)
    else:
        path = config.get('assoc_pii_key_file')
        if not path:
            raise UserError(_('未設定個資加密金鑰（assoc_pii_key_file），無法處理身分證字號。'))
        try:
            with open(path, 'rb') as fh:
                key = base64.b64decode(fh.read().strip())
        except (OSError, ValueError, binascii.Error) as exc:
            raise UserError(_('個資加密金鑰無法讀取，請洽系統管理員。')) from exc
    if len(key) != 32:
        raise UserError(_('個資加密金鑰長度不正確（需 32 bytes 的 base64）。'))
    return key


def _derive(label):
    return hmac.new(_master_key(), label, hashlib.sha256).digest()


def normalize(value):
    """全形轉半形、去空白、轉大寫。只用於比對與判斷，不改寫使用者的登入輸入。"""
    if not value:
        return ''
    return unicodedata.normalize('NFKC', value).strip().replace(' ', '').upper()


def looks_like_id(value):
    """寬鬆判斷：是不是身分證／居留證格式（檢查碼錯也算）。"""
    return bool(value) and '@' not in value and bool(LOOSE_RE.match(normalize(value)))


def looks_like_id_attempt(value):
    """使用者是不是在打身分證字號（含打錯的形狀）。見 ID_ATTEMPT_* 的說明。"""
    text = normalize(value)
    if not text or '@' in text:
        return False
    low, high = ID_ATTEMPT_LENGTH
    if not low <= len(text) <= high:
        return False
    return sum(char.isdigit() for char in text) >= ID_ATTEMPT_MIN_DIGITS


def detect_kind(value):
    for kind, pattern in PATTERNS:
        if pattern.match(value):
            return kind
    return False


def checksum_ok(value, kind):
    """內政部檢查碼：首碼轉兩位數，依 1987654321 加權，總和個位數為 0。

    舊式居留證（arc_old）第 2 碼是字母、取其對應碼的個位數——這條規則只見於
    非官方來源（計畫 §14 標 hypothesis），所以呼叫端對 arc_old 只警告不擋。
    """
    code = LETTER_CODE.get(value[0])
    if code is None:
        return False
    digits = [code // 10, code % 10]
    if kind == 'arc_old':
        second = LETTER_CODE.get(value[1])
        if second is None:
            return False
        digits.append(second % 10)
        digits.extend(int(c) for c in value[2:])
    else:
        digits.extend(int(c) for c in value[1:])
    if len(digits) != len(WEIGHTS):
        return False
    return sum(w * d for w, d in zip(WEIGHTS, digits)) % 10 == 0


def validate(value):
    """回傳 (正規化後的值, kind, checksum_ok)；格式不合直接 raise。"""
    norm = normalize(value)
    kind = detect_kind(norm)
    if not kind:
        raise ValidationError(_('身分證字號格式不正確（需 1 碼英文字母＋9 碼數字）。'))
    return norm, kind, checksum_ok(norm, kind)


def mask(value):
    """A1******78：保留首 2 碼與末 2 碼（空字串回空字串）。"""
    norm = normalize(value)
    return norm[:2] + MASK_CHAR * max(len(norm) - 4, 0) + norm[-2:] if norm else ''


def index_hmac(value):
    """跨公會唯一性與身分證登入用的查詢索引。"""
    norm = normalize(value)
    if not norm:
        return False
    digest = hmac.new(_derive(b'assoc-pii-idx-v1'), norm.encode(), hashlib.sha256).hexdigest()
    return IDX_PREFIX + digest


def encrypt(value, aad):
    """AES-GCM 加密；aad 綁定擁有者（例：'assoc.member:42'）。"""
    norm = normalize(value)
    if not norm:
        return False
    nonce = os.urandom(NONCE_BYTES)
    blob = AESGCM(_derive(b'assoc-pii-enc-v1')).encrypt(nonce, norm.encode(), aad.encode())
    return ENC_PREFIX + base64.urlsafe_b64encode(nonce + blob).decode()


def decrypt(stored, aad):
    if not stored or not stored.startswith(ENC_PREFIX):
        return ''
    try:
        raw = base64.urlsafe_b64decode(stored[len(ENC_PREFIX):])
        plain = AESGCM(_derive(b'assoc-pii-enc-v1')).decrypt(
            raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad.encode())
    except (InvalidTag, binascii.Error, ValueError, TypeError) as exc:
        # InvalidTag（不是 ValueError 子類，要明列）＝金鑰不符或密文被搬到別的擁有者名下；
        # binascii.Error＝密文被改成非法 base64。兩者都不該變成 500。
        raise UserError(_('身分證字號無法解密（金鑰不符或資料已被更動）。')) from exc
    return plain.decode()
