# -*- coding: utf-8 -*-
"""docx 樣板套印。

舊 EAGLE 樣板的 docx 用 `+++...+++` 語法：

    +++INS name+++            取值
    +++INS $item.field+++     迴圈變數取值
    +++FOR v IN col+++        段落層級迴圈
    +++FOR v IN $col+++       表格列層級迴圈
    +++END-FOR v+++           迴圈結束
    +++IF x+++ … +++END-IF+++ 條件（只有檢試驗管制用到）

`dobtor_doc_editor` 已經實作了 INS / FOR / END-FOR → docxtpl Jinja2 的轉換
（`_convert_ins_to_jinja`，段落層級操作，正確處理 Word 把標記切碎成多個
`<w:r>` run 的問題），直接沿用不重寫。

**但它不處理 `+++IF+++` / `+++END-IF+++`**（實測 2026-08-05：`_ANY` 只認
INS|FOR|END-FOR），未處理的標記會原樣印在報表上。本模組補上這一段——
採「移除標記、保留內容」：對照表保證條件欄位一定存在（取不到就給空字串），
所以條件本身沒有意義，留著反而會印出垃圾字。
"""

import io
import logging
import re
from types import SimpleNamespace

from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment as _JinjaSandbox

from odoo.models import BaseModel

_logger = logging.getLogger(__name__)


class SandboxedEnvironment(_JinjaSandbox):
    """樣板用的沙箱：再擋掉 Odoo 記錄的一切屬性。

    Jinja2 的沙箱只擋底線開頭的屬性與標了不安全的呼叫，`record.unlink()` 這種公開
    方法照樣能呼叫。對照表的 context 目前都是純值（dict、SimpleNamespace、字串），
    這一道是萬一有人把 recordset 放進 context 時的保險——樣板是使用者上傳的。
    """

    def is_safe_attribute(self, obj, attr, value):
        if isinstance(obj, BaseModel):
            # 回 False 的話 Jinja 只會給一個印成空白的 Undefined；樣板是使用者上傳的，
            # 碰到這種寫法要明確失敗，不要產出一份「看起來正常但缺字」的檔
            raise SecurityError('樣板不能存取系統記錄（%s.%s）' % (obj._name, attr))
        return super().is_safe_attribute(obj, attr, value)

    def getitem(self, obj, argument):
        # record['name'] 走這條，不經 is_safe_attribute（Odoo 記錄支援以字串鍵取欄位值）
        if isinstance(obj, BaseModel):
            raise SecurityError('樣板不能存取系統記錄（%s[%r]）' % (obj._name, argument))
        return super().getitem(obj, argument)

# +++IF <任意運算式>+++ / +++END-IF+++
# 條件式是舊系統的 JS 運算式（例：$record.images[0].isEmpty !== true），
# 含 [] ! = 等字元，不能只認識別字元。
# 🔴 條件式裡**可能含有 `+`**：自主檢查樣板的照片頁寫的是
# `+++IF inspection.images[$evenIndex + 1] +++`。原本用 `[^+]` 界定範圍，
# 遇到這種就整個匹配不到，標記原樣印在紙上（2026-09-11 實測）。
# 改用非貪婪 `.*?` ——它會停在最近的 `+++`，而單獨一個 `+` 不會被
# `\+{3,4}` 吃掉；相鄰標記黏成一長串加號的情況，上面的 `\+{6,}` 預處理
# 已經先用零寬空格切開了。
IF_RE = re.compile(r'\+{3}IF\s+.{1,160}?\+{3,4}')
ENDIF_RE = re.compile(r'\+{3}END-IF\s*\+{3,4}')

# +++IMAGE imageGenerator($record.images[0].src, $record.images[0].extension,
#                         {height:6}, $record.images[0].date)+++
# 抓出「哪個集合的哪一張圖」，轉成我們自己的 context 鍵。
#
# 🔴 索引不一定是數字。缺失改善的樣板用固定索引 images[0]/[1]/[2]，但自主檢查
# 的 79 份樣板全部是 `images[$evenIndex]` 與 `images[$evenIndex + 1]`
# （照片頁一頁兩張，$evenIndex 來自 +++FOR evenIndex IN inspection.evenImagesIndex+++）。
# 原本只認 (\d+) 的話，這類標記**完全匹配不到 → 原樣印在紙上、照片全部不見**
# （2026-09-11 實測：分頁是對的、圖片一張都沒有）。
# 所以索引改成「到 ] 為止的任意運算式」，替換時把 $ 去掉即可交給 Jinja2。
IMAGE_RE = re.compile(
    r'\+{3}IMAGE\s+imageGenerator\(\s*\$?(\w+)\.images\[([^\]]+)\]\.src.*?\+{3,4}')
IMAGE_KEY = '__image__'          # context 裡的圖片佔位標記

# 原生 Jinja 寫法的照片格：`{{ page.first.image }}`（系統預設的自主檢查表單張）
IMAGE_JINJA_RE = re.compile(r'\{\{[^{}]*\.image\s*\}\}')

# 帶索引的取值：+++INS $record.images[0].description+++
# 既有轉換器的 _INS 只認 `[A-Za-z_][\w]*` 加點號，不支援 [0]，
# 這類標記會原樣留在報表上，所以自己先轉掉。
INDEXED_INS_RE = re.compile(
    r'\+{3}INS\s+\$?\s*'
    r'([A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*|\s*\[\s*\d+\s*\])*'
    r'\s*\[\s*\d+\s*\]'
    r'(?:\s*\.\s*[A-Za-z_]\w*|\s*\[\s*\d+\s*\])*)\s*\+{3,4}')


def _unclip_image_paragraph(para):
    """照片格的段落不能是固定行高。

    🔴 樣板的照片格段落常直接設 `w:spacing w:lineRule="exact"`（矯正與預防處理紀錄
    16pt、使用者上傳的 117 份自主檢查樣板 25pt；2026-11-05 實查，都寫在段落本身、
    不是 style 繼承）。InlineImage 放進同一段後段落仍是那個高度 → LibreOffice 把照片
    裁成一條（Word 實印不裁，但兩邊都要能用）。所以照片格把固定行高拿掉、改回自動，
    段前段後距離照留。

    只動照片格：一般文字段落的固定行高是版面設計；附表12 標題段雖然含 drawing
    （anchor 文字方塊）也是 exact，所以判斷依據是「段落裡有照片標記」，不是「含 drawing」。
    只改 pPr、不重寫 run——原生 Jinja 的照片段落裡還有 `w:br` 與說明文字。
    """
    from docx.oxml.ns import qn

    p_pr = para._p.pPr
    spacing = p_pr.find(qn('w:spacing')) if p_pr is not None else None
    if spacing is not None and spacing.get(qn('w:lineRule')) == 'exact':
        spacing.attrib.pop(qn('w:line'), None)
        spacing.attrib.pop(qn('w:lineRule'), None)


def _strip_conditionals(raw_bytes):
    """移除 +++IF+++ / +++END-IF+++ 標記，保留中間內容。

    與既有轉換器同樣在段落層級操作（para.text 已拼接所有 run），
    才不會被 Word 的 run 切割弄壞。照片格的固定行高也在這裡拿掉（_unclip_image_paragraph）。
    """
    import docx as python_docx

    doc = python_docx.Document(io.BytesIO(raw_bytes))

    def clean(paragraphs):
        for para in paragraphs:
            text = para.text
            if IMAGE_RE.search(text) or IMAGE_JINJA_RE.search(text):
                _unclip_image_paragraph(para)
            if '+++' not in text:
                continue
            # 相鄰標記會黏成一長串加號：`+++END-IF++++++INS x+++` 中間是 6 個
            # （前一個收尾 3~4 個 ＋ 下一個開頭 3 個）。既有轉換器的正則結尾吃
            # `\+{3,4}`，會啃掉下一個標記的開頭，導致 +++INS 原樣留在報表上。
            # 用零寬空格切開，輸出看不見但正則能正確斷詞。
            text = re.sub(r'\+{6,}', '+++​+++', text)
            # 圖片：轉成自己的 context 鍵，由 render() 換成 docxtpl 的 InlineImage
            text = IMAGE_RE.sub(
                lambda m: '{{ %s.images[%s].image }}' % (
                    m.group(1), m.group(2).replace('$', '').strip()), text)
            # 帶索引的取值：既有轉換器處理不了，自己轉成 Jinja
            text = INDEXED_INS_RE.sub(
                lambda m: '{{ %s }}' % re.sub(r'\s', '', m.group(1)), text)
            text = ENDIF_RE.sub('', IF_RE.sub('', text))
            # 整段重寫成單一 run：標記本來就跨 run，逐 run 改會漏
            for run in list(para.runs)[1:]:
                run._element.getparent().remove(run._element)
            if para.runs:
                para.runs[0].text = text
            elif text:
                para.add_run(text)

    def walk(container):
        clean(container.paragraphs)
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    walk(cell)          # 儲存格裡還可能有巢狀表格

    walk(doc)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _swap_images(value, tpl):
    """把 context 裡的圖片佔位標記換成 docxtpl 的 InlineImage。

    對照表無法自己建 InlineImage（那需要 tpl 物件），所以改成放
    `{'__image__': <bytes>, 'max_width_cm': 14, 'max_height_cm': 10}` 這種標記。

    尺寸照 EAGLE 原系統 imageGenerator 的算法**等比縮放**（上限 14×10 cm），
    先前寫死高度 60mm 會把直式照片壓扁。
    """
    from docx.shared import Cm
    from docxtpl import InlineImage

    from . import photo_stamp

    # SimpleNamespace：對照表的 context 用它而不是 dict，因為 Jinja2 的 `.` 存取
    # 先找 attribute，dict 的 items/keys/values 會把同名的資料鍵蓋掉
    # （`stage.items` 會拿到 dict.items 這個 method）。這裡要一起遞迴進去，
    # 否則巢狀在 namespace 裡的照片標記換不到 InlineImage，照片會靜靜不見。
    if isinstance(value, SimpleNamespace):
        for key, inner in list(vars(value).items()):
            setattr(value, key, _swap_images(inner, tpl))
        return value
    if isinstance(value, dict):
        if IMAGE_KEY in value:
            raw = value.get(IMAGE_KEY)
            if not raw:
                return ''
            width_px, height_px = photo_stamp.image_size_px(raw)
            width_cm, height_cm = photo_stamp.fit_size_cm(
                width_px, height_px,
                value.get('max_width_cm', photo_stamp.DEFAULT_MAX_WIDTH_CM),
                value.get('max_height_cm', photo_stamp.DEFAULT_MAX_HEIGHT_CM))
            return InlineImage(tpl, io.BytesIO(raw),
                               width=Cm(width_cm), height=Cm(height_cm))
        return {k: _swap_images(v, tpl) for k, v in value.items()}
    if isinstance(value, list):
        return [_swap_images(v, tpl) for v in value]
    return value


def render(raw_bytes, context):
    """把 context 套進 docx 樣板，回傳新的 docx bytes。"""
    from docxtpl import DocxTemplate
    # 匯入既有轉換器（dobtor_doc_editor 已在 depends 裡）
    from odoo.addons.dobtor_doc_editor.controllers.doc_controller import (
        _convert_ins_to_jinja)

    stripped = _strip_conditionals(raw_bytes)
    converted = _convert_ins_to_jinja(stripped)

    tpl = DocxTemplate(io.BytesIO(converted))
    # ⚠️ autoescape 必須開：docxtpl 預設 autoescape=False，資料裡的 & < >
    # 會直接寫進 XML 變成非法標記；而 docxtpl 的 fix_tables() 是用
    # etree.XMLParser(recover=True) 解析的——lxml 會**無聲**丟掉壞掉的那段，
    # 整筆記錄就從報表上消失，不拋例外、log 也乾淨。
    # 實例（2026-08-06 實測 odoo18_dev）：送審管制表 project 43 有 80 筆，
    # 名稱「工地密度(第6層&第7層)」那筆整列不見，只印出 79 筆；
    # 另有「盤式支承 固定型，標稱載重 < 50tf」同樣會中。
    # InlineImage 有定義 __html__()，autoescape 下 markupsafe 會呼叫它取原始
    # XML 而不是跳脫，所以照片不受影響。
    # 🔴 沙箱：樣板是使用者上傳的（任何後台帳號都能換），docxtpl 預設的 Environment
    # 沒有沙箱，`{{ x.__class__.__mro__ }}` 這類運算式就能走到 Python 內部在主機上執行
    # （2026-10-25 紅隊審查）。SandboxedEnvironment 擋底線屬性與不安全呼叫，
    # 一般的取值、for、if 照常；dev 117 份自主檢查樣板與系統預設樣板回歸比對產出相同。
    tpl.render(_swap_images(context, tpl),
               jinja_env=SandboxedEnvironment(autoescape=True), autoescape=True)
    strip_trailing_blank(tpl.docx.element.body)
    breaks_to_page_break_before(tpl.docx.element.body)
    out = io.BytesIO()
    tpl.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- 結尾空白頁
# 2026-11-05 跑版檢查（Word 16 實印）：套印後文件結尾常多一頁白紙，三種樣子——
#   A. 每頁結尾放「分頁符號」的迴圈（管制表、矯正與預防處理紀錄）：最後一頁後面還有分頁＋空段落
#   B. 照片頁迴圈每頁結尾是「分節（下一頁）」（使用者上傳的自主檢查樣板 89／93 種、自主檢查表單張）：
#      最後一個分節後面只剩空段落，Word 為它們開一整頁
#   C. 第一頁剛好排滿，結尾的空段落被推到第二頁（估驗照片該期沒有照片時）
# 樣板本身多半沒有空白頁，是迴圈展開後才出現的，所以在套印完成後統一處理，不逐份改樣板。
_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
# 有這些元素的段落算「有內容」，不能刪（功能變數的 fldChar 也算：刪掉會留下有頭沒尾的欄位）
_CONTENT_TAGS = tuple(_W + t for t in (
    'drawing', 'pict', 'object', 'fldSimple', 'fldChar', 'instrText', 'sym',
    'footnoteReference', 'endnoteReference', 'commentReference')) + (_M + 'oMath', _M + 'oMathPara')
# 段落本身看得見的格式：框線（分隔線）、網底、框架
_VISIBLE_PPR_TAGS = (_W + 'pBdr', _W + 'framePr')
# body 層不佔版面的標記，往回找最後一塊內容時跳過（不刪）
_INVISIBLE_TAGS = (_W + 'bookmarkStart', _W + 'bookmarkEnd', _W + 'proofErr',
                   _W + 'permStart', _W + 'permEnd')
# 會讓 Word 規定「後面要接一段」的區塊（表格、包著表格的內容控制項）
_TABLE_LIKE_TAGS = (_W + 'tbl', _W + 'sdt')
# Word 規定文件最後一塊要是段落：表格後面留的那一段縮成 1pt，避免它自己又被擠到下一頁
_TAIL_FONT_HALF_PT = '2'
_TAIL_LINE_TWIP = '20'
# 結尾可能連著好幾個空節，一輪只併一個；上限只是保險，實務上 1～2 輪就穩定
_MAX_TRAILING_PASSES = 5
_FALSE_VALUES = ('0', 'false', 'off')


def _is_on(el):
    """w:val 省略＝開；0／false／off＝關（例：<w:pageBreakBefore w:val="0"/>）"""
    return el is not None and (el.get(_W + 'val') or '1').lower() not in _FALSE_VALUES


def _underlined(run):
    rpr = run.find(_W + 'rPr')
    u = rpr.find(_W + 'u') if rpr is not None else None
    return u is not None and (u.get(_W + 'val') or 'single') != 'none'


def _paragraph_has_content(para):
    """這一段印出來看不看得到東西。

    2026-11-05 抗辯審查：只看 w:t 會把結尾的「底線全形空白」（簽名線）、框線段（分隔線）、
    方程式、功能變數的結束標記當成空段落刪掉。
    """
    if any(t.text and t.text.strip() for t in para.iter(_W + 't')):
        return True
    if any(para.find('.//' + tag) is not None for tag in _CONTENT_TAGS):
        return True
    ppr = para.find(_W + 'pPr')
    if ppr is not None:
        if any(ppr.find(tag) is not None for tag in _VISIBLE_PPR_TAGS):
            return True
        shd = ppr.find(_W + 'shd')
        if shd is not None and (shd.get(_W + 'fill') or 'auto').lower() not in ('auto', 'ffffff'):
            return True
    # 加底線的空白或定位字元＝簽名線
    for run in para.iter(_W + 'r'):
        if _underlined(run) and (run.find(_W + 'tab') is not None
                                 or any(t.text for t in run.iter(_W + 't'))):
            return True
    return False


def _section_props(para):
    ppr = para.find(_W + 'pPr')
    return ppr.find(_W + 'sectPr') if ppr is not None else None


def _drop_trailing_page_breaks(para):
    """只拿掉段落「最後一個看得見的東西之後」的分頁符號（結尾分頁＝多一頁白紙）。

    段落中間的分頁（例：「附件：照片」另起一頁）與段落本身的「段落前分頁」都不能動
    ——2026-11-05 抗辯審查實測：整段全拿掉會把附件內容拉回前一頁（Word 2 頁變 1 頁）。
    """
    last_content = -1
    nodes = list(para.iter())
    for idx, el in enumerate(nodes):
        if ((el.tag == _W + 't' and el.text and el.text.strip())
                or el.tag in _CONTENT_TAGS or el.tag == _W + 'tab'):
            last_content = idx
    for idx, el in enumerate(nodes):
        if idx > last_content and el.tag == _W + 'br' and el.get(_W + 'type') == 'page':
            el.getparent().remove(el)


def _tiny_paragraph():
    """表格後面必留的那一段：行距固定 1pt、字 1pt、前後距 0。

    新建的 pPr 只有 spacing、rPr 兩個子元素（順序合乎 schema）——在既有 pPr 裡追加 spacing
    可能排到 rPr 後面，Word 會判定內容有問題、跳修復提示。
    """
    from lxml import etree
    para = etree.Element(_W + 'p')
    ppr = etree.SubElement(para, _W + 'pPr')
    etree.SubElement(ppr, _W + 'spacing', {
        _W + 'before': '0', _W + 'after': '0',
        _W + 'line': _TAIL_LINE_TWIP, _W + 'lineRule': 'exact'})
    rpr = etree.SubElement(ppr, _W + 'rPr')
    for tag in ('sz', 'szCs'):
        etree.SubElement(rpr, _W + tag, {_W + 'val': _TAIL_FONT_HALF_PT})
    return para


def _visible_blocks(body):
    return [el for el in body if el.tag not in _INVISIBLE_TAGS and el.tag != _W + 'sectPr']


def _strip_once(body):
    """一輪：拿掉結尾空段落；最後一塊若是「帶分節的段落」（＝最後一節是空的）就併回前一節。
    回傳這一輪有沒有改東西。"""
    changed = False
    # 1) 從後往前拿掉空段落（只有分頁符號的段落也算空）；帶分節的段落另外處理
    for el in reversed(_visible_blocks(body)):
        if el.tag == _W + 'p' and _section_props(el) is None and not _paragraph_has_content(el):
            body.remove(el)
            changed = True
            continue
        break
    blocks = _visible_blocks(body)
    if not blocks:
        return changed
    last = blocks[-1]
    sect = _section_props(last) if last.tag == _W + 'p' else None
    if sect is not None:
        # 2) B：把該段落的分節設定搬到 body 層（取代空節的設定）＝最後一節併回前一節
        last.find(_W + 'pPr').remove(sect)
        body_sect = body.find(_W + 'sectPr')
        if body_sect is not None:
            body.replace(body_sect, sect)
        else:
            body.append(sect)
        if not _paragraph_has_content(last):
            body.remove(last)            # 表格後面需要的那一段，最後統一補
        changed = True
    return changed


def strip_trailing_blank(body):
    """拿掉文件結尾的空白頁來源（就地修改 body）。

    只動「最後一塊有內容的區塊」之後的東西；文件中間的空行一律不碰。
    """
    for _ in range(_MAX_TRAILING_PASSES):
        if not _strip_once(body):
            break
    blocks = _visible_blocks(body)
    if not blocks:
        return
    last = blocks[-1]
    if last.tag == _W + 'p':
        _drop_trailing_page_breaks(last)          # A：最後一段結尾的分頁符號
    elif last.tag in _TABLE_LIKE_TAGS:
        last.addnext(_tiny_paragraph())           # Word 規定最後一塊要是段落


# pPr 子元素裡排在 pageBreakBefore 前面的（schema 規定順序）
_PPR_BEFORE_PBB = (_W + 'pStyle', _W + 'keepNext', _W + 'keepLines')


def _only_page_break(para):
    return (para.tag == _W + 'p' and _section_props(para) is None
            and not _paragraph_has_content(para)
            and any(br.get(_W + 'type') == 'page' for br in para.iter(_W + 'br')))


def breaks_to_page_break_before(body):
    """「只有分頁符號的段落」→ 拿掉，改在下一段設「段落前分頁」（就地修改 body）。

    2026-11-05 跑版檢查：管制表每一頁結尾是一個只有分頁符號的段落。前一頁剛好排滿到底時，
    這個段落被擠到新的一頁、再分一次頁 → 中間多一張白紙（缺失管制表 15 頁裡的第 12 頁）。
    「段落前分頁」在段落本來就位於頁首時不會再多分一頁。
    只處理 body 這一層（表格裡的不動）。下一塊是表格、或下一段也只有分頁符號
    （連續兩個分頁＝刻意留的空白頁）時，保留原本的分頁符號。下一段是空白間隔段照樣轉
    （缺失管制表就是「分頁 → 空白段 → 標題」）。
    """
    from lxml import etree
    blocks = _visible_blocks(body)
    for el, nxt in zip(blocks, blocks[1:]):
        if not _only_page_break(el) or nxt.tag != _W + 'p' or _only_page_break(nxt):
            continue
        ppr = nxt.find(_W + 'pPr')
        if ppr is None:
            ppr = etree.Element(_W + 'pPr')
            nxt.insert(0, ppr)
        pbb = ppr.find(_W + 'pageBreakBefore')
        if pbb is None:
            pos = sum(1 for child in ppr if child.tag in _PPR_BEFORE_PBB)
            ppr.insert(pos, etree.Element(_W + 'pageBreakBefore'))
        elif not _is_on(pbb):
            pbb.attrib.pop(_W + 'val', None)       # <w:pageBreakBefore w:val="0"/> → 打開
        body.remove(el)


def _chunks(records, page_size):
    if not records:
        return [[]]
    return [records[i:i + page_size] for i in range(0, len(records), page_size)]


def paginate_plain(records, page_size):
    """`+++FOR item IN $page+++` 用——page 本身就是清單。

    送審管制、檢試驗管制的樣板是這種寫法。
    """
    return _chunks(records, page_size)


def paginate_pages(records, page_size, key='errorRecords'):
    """`+++FOR record IN $page.errorRecords+++` 用——page 是物件。

    缺失改善管制表的樣板是這種寫法，且要 $page.currentPage 印頁碼。
    """
    return [{'currentPage': i + 1, key: chunk}
            for i, chunk in enumerate(_chunks(records, page_size))]
