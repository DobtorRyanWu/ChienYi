# -*- coding: utf-8 -*-
"""缺失改善個別 docx 通用解析器

輸入：一個 zip 含多份 docx 檔，或單一 docx bytes
輸出：list[dict]，每筆含比對鍵 + 抽取到的 缺失事項 / 改善中 / 改善後

檔名慣例（實測 E:\\work\\工程資料 底下 329 個缺失 docx 的分布）
--------------------------------------------------------------
    41  括號無編號     `1100517缺失矯正改善追蹤回報表(QR)(磺港溪-雜草清除).docx`
    31  連字號帶編號   `1100824-缺失矯正改善追蹤表-QR-001(109.8.24)-達客利.docx`
    26  括號帶編號     `1-0803-缺失矯正改善追蹤回報表(...)(QA-001).docx`
    14  開頭帶編號     `QA-11309191-缺失矯正改善追蹤回報表-xxx.docx`
   656  開頭民國日期   `1121025-磺港溪缺失矯正改善(勞安).docx`      ← A 標慣例
   其餘 無 QA/QR 也無類別括號

舊版只認「開頭 7 位民國日期」與「開頭 QA-/QR-」兩種，且把 register_no **捏造**成
`Q01-` + 日期（`Q01-` 是 A 標登錄編號的開頭，套到別的案場就是錯的）。
本版改為 **literal 抽取**：檔名裡有什麼編號就用什麼，抽不到才退回日期鍵。

比對機制
--------
不再用單一 register_no 做等值比對，改成雙方各產生一組「比對鍵」，依優先序逐一嘗試：

    docx  →  docx_match_keys(filename)
             ['QA-001']                    有 literal 編號
             ['DATE:1121025']              只有日期

    缺失  →  defect_index_keys(source_description, found_date)
             ['Q01-1121007', 'DATE:1121007']

    A 標   docx 給 DATE:1121007，缺失的 source_description `Q01-1121007` 也能推出
           DATE:1121007 → 對上（舊版靠捏造 Q01- 前綴才對得上，換案場就失效）
    P11001 docx 給 QA-001，缺失 source_description 就是 QA-001 → 直接對上
"""

import re
import zipfile
from io import BytesIO


# ── 檔名編號抽取（優先序：越明確越前面） ───────────────────────────
_REGISTER_PATTERNS = (
    # (QA-001) / （QR-006）
    re.compile(r'[（(]\s*(QA|QR)\s*[-－]\s*(\d{1,4})\s*[）)]', re.I),
    # -QA-001 / -QR-006（前面必須是連字號，避免誤抓內文）
    re.compile(r'[-－]\s*(QA|QR)\s*[-－]\s*(\d{1,4})(?![\d-])', re.I),
    # 檔名開頭 QA-11309191（QA/QR + 民國日期 + 序號）
    re.compile(r'^(QA|QR)\s*[-－]\s*(\d{7,8})', re.I),
)
# 只有 QA/QR 沒有編號：(QA) / （QR）／ -QA- 這種
_QAQR_ONLY_PATTERNS = (
    re.compile(r'[（(]\s*(QA|QR)\s*[）)]', re.I),
    re.compile(r'[-－]\s*(QA|QR)\s*[-－]', re.I),
    re.compile(r'^(QA|QR)\s*[-－]', re.I),
)
# 獨立的 7 位民國日期，後面可帶 1~2 位當日序號。
# 前後都不能再接數字，避免把 8 位以上的流水號切一半（QA-11309191 不會被誤切）。
# 不綁「必須在開頭」—— 實際檔名可能帶資料夾前綴、序號前綴或案場名稱前綴。
#
# 當日序號很關鍵：A 標 88 筆裡有 31 筆是 `Q01-1130506-1` / `-2` / `-3` 這種
# 同一天多筆的形式（最多的一天 8 筆），只比日期會全部撞在一起。
_ANY_ROC_RE = re.compile(r'(?<!\d)(\d{7})(?:[-－](\d{1,2}))?(?!\d)')

# 檔名括號分類詞 → defect_category（general/reservation 詞彙）
_KEYWORD_TO_CATEGORY = {
    '品質': 'workmanship',
    '施工': 'workmanship',
    '職安': 'safety',
    '勞安': 'safety',
    '安衛': 'safety',
    '勞檢': 'safety',
    '環境': 'environment',
}

# QA=監造、QR=營造。依據使用者匯入來源檔（B標匯入_合併）「缺失改善」R1 註記。
_QAQR_TO_RECORD_TYPE = {'QA': 'supervision', 'QR': 'contractor'}


def _basename(filename):
    return filename.replace('\\', '/').rsplit('/', 1)[-1]


def _roc_key(digits, seq=None):
    """民國日期鍵。帶當日序號時形如 DATE:1130506#2。"""
    if seq:
        return 'DATE:%s#%d' % (digits, int(seq))
    return 'DATE:%s' % digits


def _roc_key_from_date(d):
    if not d:
        return None
    return 'DATE:%03d%02d%02d' % (d.year - 1911, d.month, d.day)


def derive_register_no(filename):
    """從檔名抽出登錄編號（literal，不捏造）；抽不到回 None。"""
    bn = _basename(filename)
    for pattern in _REGISTER_PATTERNS:
        m = pattern.search(bn)
        if m:
            return '%s-%s' % (m.group(1).upper(), m.group(2))
    return None


def derive_record_type(filename):
    """從檔名的 QA/QR 推 record_type；推不出回 None（交由上層落下一層優先序）。"""
    bn = _basename(filename)
    for pattern in _REGISTER_PATTERNS + _QAQR_ONLY_PATTERNS:
        m = pattern.search(bn)
        if m:
            return _QAQR_TO_RECORD_TYPE.get(m.group(1).upper())
    return None


def derive_category(filename):
    """從檔名括號分類詞或 QA/QR 推 defect_category。"""
    bn = _basename(filename)
    for kw, val in _KEYWORD_TO_CATEGORY.items():
        if f'({kw})' in bn or f'（{kw}）' in bn or f'{kw}缺失' in bn:
            return val
    rt = derive_record_type(filename)
    if rt == 'supervision':
        return 'workmanship'
    if rt == 'contractor':
        return 'safety'
    return 'other'


def _roc_digits_to_date(digits):
    from datetime import date
    try:
        return date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7]))
    except (ValueError, TypeError):
        return None


def derive_found_date(filename):
    """從檔名裡的 7 位民國日期推 found_date。

    掃「所有」獨立的 7 位數字並逐一驗證，取第一個能構成合法日期的
    —— 不假設日期一定在檔名開頭（實際檔名常帶序號或資料夾前綴）。

    注意：`1-0803-…(QA-001).docx` 這種只有月日、沒有年份的慣例推不出日期，
    回 None。這類檔案只能走 enrich（補既有缺失），不能走 import-docx（直接建）。
    """
    bn = _basename(filename)

    # 編號本身帶民國日期時（QA-11309191）優先取編號裡的
    for pattern in _REGISTER_PATTERNS:
        mm = pattern.search(bn)
        if mm and len(mm.group(2)) >= 7:
            d = _roc_digits_to_date(mm.group(2)[:7])
            if d:
                return d

    for m in _ANY_ROC_RE.finditer(bn):
        d = _roc_digits_to_date(m.group(1))
        if d:
            return d
    return None


def docx_match_keys(filename):
    """一份 docx 可用來比對既有缺失的鍵，由精確到寬鬆。

    例：
        1130925-1 護欄鋼筋未綁紮牢固.docx  → ['DATE:1130925#1', 'DATE:1130925']
        1121025-磺港溪缺失矯正改善(勞安).docx → ['DATE:1121025']
        1-0803-…(QA-001).docx              → ['QA-001']
    """
    keys = []
    reg = derive_register_no(filename)
    if reg:
        keys.append(reg.upper())

    bn = _basename(filename)
    for m in _ANY_ROC_RE.finditer(bn):
        if not _roc_digits_to_date(m.group(1)):
            continue                      # 7 位數字但構不成合法日期
        if m.group(2):
            keys.append(_roc_key(m.group(1), m.group(2)))
        keys.append(_roc_key(m.group(1)))
        break                             # 只取第一個合法日期

    # 編號本身帶日期時（QR-11210251）上面的 regex 抓不到（8 位以上連續數字），
    # 補上由 derive_found_date 推出的日期鍵
    fallback = _roc_key_from_date(derive_found_date(filename))
    if fallback and fallback not in keys:
        keys.append(fallback)
    return keys


# 比對層級，由精確到寬鬆。**必須分層**：若把所有鍵混在同一個索引裡，
# 精確度不同的鍵會互撞，製造出本來不存在的歧義（低層級的日期鍵會蓋掉
# 高層級的編號鍵）。A 標實測差異：
#   不分層           → 33 個歧義鍵、回配 17 份
#   分層但無當日序號 → 33 個歧義鍵、回配 17 份（同一天最多 8 筆，全撞在一起）
#   分層＋當日序號   → 見驗證結果
DEFECT_KEY_TIERS = ('register', 'register_date_seq', 'register_date', 'found_date')


def defect_index_keys(source_description, found_date=None):
    """一筆既有缺失在各層級的比對鍵，回傳 {層級: 鍵}（沒有的層級不出現）。

    register           登錄編號本身                QA-001 / Q01-1130506-2
    register_date_seq  編號裡的民國日期＋當日序號   Q01-1130506-2 → DATE:1130506#2
    register_date      編號裡的民國日期            Q01-1121007   → DATE:1121007
    found_date         發現日期換算的民國日期       2023-10-07    → DATE:1121007

    :param source_description: 缺失的「來源登錄編號」
    :param found_date: 缺失的發現日期
    """
    keys = {}
    s = (source_description or '').strip().upper()
    if s:
        keys['register'] = s
        m = _ANY_ROC_RE.search(s)
        if m:
            if m.group(2):
                keys['register_date_seq'] = _roc_key(m.group(1), m.group(2))
            keys['register_date'] = _roc_key(m.group(1))
    key = _roc_key_from_date(found_date)
    if key:
        keys['found_date'] = key
    return keys


def build_defect_index(defects):
    """為一組缺失建立分層索引。

    :return: (index, ambiguous)
             index     {層級: {鍵: 缺失}}
             ambiguous {層級: {鍵: [對到的多筆缺失]}}
    """
    index = {tier: {} for tier in DEFECT_KEY_TIERS}
    ambiguous = {tier: {} for tier in DEFECT_KEY_TIERS}
    for defect in defects:
        pairs = defect_index_keys(
            getattr(defect, 'source_description', None),
            getattr(defect, 'found_date', None))
        for tier, key in pairs.items():
            if key in ambiguous[tier]:
                ambiguous[tier][key].append(defect)
                continue
            hit = index[tier].get(key)
            if hit is not None and hit.id != defect.id:
                ambiguous[tier][key] = [hit, defect]
                del index[tier][key]
            else:
                index[tier].setdefault(key, defect)
    return index, ambiguous


# 用描述文字拆解同日多筆的歧義。
# A 標的實況：同一天最多 8 筆缺失，編號是 Q01-1130506-1/-2/-3，但 docx 檔名
# 不一定帶序號（`1130925型鋼護欄未排列整齊.docx`）—— 檔名裡卻有缺失內容，
# 拿去跟候選缺失的說明比對就能判出是哪一筆。
_DISAMBIGUATE_MIN_RATIO = 0.45   # 低於此視為沒把握
_DISAMBIGUATE_MIN_GAP = 0.10     # 與次高分差距太小也視為沒把握
_NON_WORD_RE = re.compile(r'[\s\W_]+', re.UNICODE)


def _text_key(s):
    return _NON_WORD_RE.sub('', s or '')


def disambiguate_by_text(candidates, hint):
    """在多個候選缺失中用描述文字挑出最相符的一筆；沒把握回 None。"""
    from difflib import SequenceMatcher

    hint_norm = _text_key(hint)
    if not hint_norm or not candidates:
        return None
    scored = sorted(
        ((SequenceMatcher(None, hint_norm,
                          _text_key(getattr(c, 'defect_description', ''))).ratio(), c)
         for c in candidates),
        key=lambda pair: -pair[0])
    best_ratio, best = scored[0]
    if best_ratio < _DISAMBIGUATE_MIN_RATIO:
        return None
    if len(scored) > 1 and best_ratio - scored[1][0] < _DISAMBIGUATE_MIN_GAP:
        return None
    return best


def match_defect(docx_keys, index, ambiguous, hint=None):
    """把一份 docx 的比對鍵配到既有缺失。

    由精確到寬鬆逐層嘗試。某層的鍵對到多筆時，若有 hint（docx 的缺失說明／
    檔名）就用文字相似度拆解；拆不開才記為歧義並往下一層。

    :param hint: 用來拆解歧義的文字，通常是 docx 內文抽到的缺失說明 + 檔名
    :return: (缺失 or None, 歧義鍵 or None)
    """
    hit_ambiguous = None
    for tier in DEFECT_KEY_TIERS:
        for key in docx_keys:
            candidates = ambiguous[tier].get(key)
            if candidates:
                picked = disambiguate_by_text(candidates, hint) if hint else None
                if picked is not None:
                    return picked, None
                hit_ambiguous = key
                continue
            defect = index[tier].get(key)
            if defect is not None:
                return defect, None
    return None, hit_ambiguous


def docx_hint_text(row):
    """組出用來拆解歧義的文字：內文抽到的缺失說明 + 檔名（去掉副檔名）。"""
    parts = [row.get('description') or '']
    bn = _basename(row.get('filename') or '')
    parts.append(re.sub(r'\.docx?$', '', bn, flags=re.I))
    return ' '.join(p for p in parts if p)


# ── docx 內文抽取 ───────────────────────────────────────────────────
_FIELD_KEYS = {
    '缺失事項': 'description',
    '不符情形': 'description',
    '改善中': 'improvement',
    '改善後': 'close_comment',
    '改善追蹤': 'improvement',
    '改善位置': 'location',
}

# QA/QR layout 的照片 table：C1 column 放 改善前/改善中/改善後 label，
# 同列 (或前一列) C0 放 `照片內容：XXX`
_PHOTO_LABELS = {
    '改善中': 'improvement',
    '改善後': 'close_comment',
}

# 內文的檢查類型勾選：☑施工抽查 / □安衛、環境清潔（\uf052 是勾選符號）
_CHECKED_MARKS = ('\uf052', '☑', '■', '▓', 'V')


def _clean(text: str) -> str:
    return (text or '').strip().replace('\r\n', '\n').strip()


def _extract_from_prefix(text: str, prefix: str):
    """檢查 text 是否以 prefix: / prefix： 開頭，回傳冒號後的值或 None。

    也接受 `1.改善位置：` / `2.不符情形：` 這種帶序號的寫法。
    """
    stripped = re.sub(r'^\s*\d+\s*[.、]\s*', '', text)
    for candidate in (text, stripped):
        for delim in ('：', ':'):
            key = prefix + delim
            if candidate.startswith(key):
                return _clean(candidate[len(key):])
    return None


def _split_after_colon(text: str) -> str:
    """抽 `prefix：value` / `prefix:value` 後面的 value；無冒號 → 原文。"""
    for delim in ('：', ':'):
        idx = text.find(delim)
        if idx >= 0:
            return _clean(text[idx + 1:])
    return _clean(text)


def _scan_photo_table(table) -> dict:
    """掃 QA/QR layout 的照片 table。

    照片 table 的 pattern：某列 C1 是 `改善中`/`改善後` label，
    其它 cell 的 `照片內容：XXX` 文字就是對應內容。
    同 label 下可能跨多列，取第一個非空值。
    """
    found = {}
    rows = list(table.rows)
    for i, row in enumerate(rows):
        label_field = None
        for cell in row.cells:
            txt = _clean(cell.text)
            if txt in _PHOTO_LABELS:
                label_field = _PHOTO_LABELS[txt]
                break
        if not label_field or label_field in found:
            continue

        search_range = [i]
        if i > 0:
            search_range.insert(0, i - 1)
        if i + 1 < len(rows):
            search_range.append(i + 1)

        for j in search_range:
            seen = set()
            for cell in rows[j].cells:
                txt = _clean(cell.text)
                if not txt or txt in seen:
                    continue
                seen.add(txt)
                if txt.startswith('照片內容'):
                    val = _split_after_colon(txt)
                    if val and not val.startswith('照片內容'):
                        found[label_field] = val
                        break
            if label_field in found:
                break
    return found


def _scan_check_type(doc):
    """從內文的「☑施工抽查 □安衛、環境清潔」勾選推 check_type。"""
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                txt = _clean(cell.text)
                if not txt:
                    continue
                checked = any(mark in txt for mark in _CHECKED_MARKS)
                if not checked:
                    continue
                if '施工抽查' in txt or '施工檢查' in txt:
                    return 'construction'
                if '安衛' in txt or '環境清潔' in txt:
                    return 'safety_env'
    return None


def parse_defect_docx(docx_bytes: bytes) -> dict:
    """解析單一 docx，回傳 {description, improvement, close_comment, location, check_type}。"""
    from docx import Document

    result = {'description': '', 'improvement': '', 'close_comment': '',
              'location': '', 'check_type': None}
    try:
        doc = Document(BytesIO(docx_bytes))
    except Exception:
        return result

    # Pass 1: keyword prefix scan
    for table in doc.tables:
        for row in table.rows:
            seen = set()
            for cell in row.cells:
                text = _clean(cell.text)
                if not text or text in seen:
                    continue
                seen.add(text)
                for prefix, field in _FIELD_KEYS.items():
                    if result.get(field):
                        continue
                    val = _extract_from_prefix(text, prefix)
                    if val:
                        result[field] = val

    # Pass 2: photo-label pattern（QA/QR Table1）
    if not (result['improvement'] and result['close_comment']):
        for table in doc.tables:
            if not table.rows:
                continue
            header = _clean(table.rows[0].cells[0].text) if table.rows[0].cells else ''
            if '照片' not in header and '缺失改善' not in header:
                continue
            for field, val in _scan_photo_table(table).items():
                if not result[field]:
                    result[field] = val

    result['check_type'] = _scan_check_type(doc)
    return result


def parse_defect_zip(zip_bytes: bytes) -> list:
    """解析 zip 內所有 docx，回傳 list[dict]。

    每筆：
        {
            'filename': '1-0803-缺失矯正改善追蹤回報表(...)(QA-001).docx',
            'register_no': 'QA-001',        # literal 抽取，可能為 None
            'match_keys': ['QA-001'],       # 供 enrich 依序比對
            'record_type': 'supervision',   # 可能為 None
            'defect_category': 'workmanship',
            'check_type': 'construction',   # 從內文勾選推得，可能為 None
            'found_date': date(2021, 8, 3), # 可能為 None（檔名只有月日時）
            'description': '...',
            'improvement': '...',
            'close_comment': '...',
            'location': '...',
            'error': str or None,
        }
    """
    results = []
    try:
        zf = zipfile.ZipFile(BytesIO(zip_bytes), 'r')
    except zipfile.BadZipFile:
        return results

    with zf:
        for name in zf.namelist():
            if not name.lower().endswith('.docx'):
                continue
            if name.startswith('__MACOSX') or '/__MACOSX' in name:
                continue
            if _basename(name).startswith('~$'):      # Word 暫存檔
                continue

            entry = {
                'filename': name,
                'register_no': derive_register_no(name),
                'match_keys': docx_match_keys(name),
                'record_type': derive_record_type(name),
                'defect_category': derive_category(name),
                'check_type': None,
                'found_date': derive_found_date(name),
                'description': '',
                'improvement': '',
                'close_comment': '',
                'location': '',
                'error': None,
            }
            try:
                parsed = parse_defect_docx(zf.read(name))
                entry.update({k: v for k, v in parsed.items() if v})
            except Exception as e:
                entry['error'] = str(e)[:150]
            results.append(entry)

    return results
