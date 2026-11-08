# -*- coding: utf-8 -*-
"""估驗計價 dobtor 文件：建立時把表頭變數與「本期完成工項」寫成這張估驗的實際值。

為什麼不用欄位對映（field_aliases）：
- 範本 dobtor_doc_editor.template_payment_estimate 出廠沒有對映；「顯示實際值」
  （/dobtor_doc/preview_content_json）沒有對映就回錯誤，文件永遠只看得到 {{ var }}
  （2026-11-07 使用者在 jt 實看：「完全是沒內容」）。
- 對映一格只能換一個值，展不開工項表（範本只有一列空白）。
所以照自主檢查（self_inspection_doc_helper.inject_checklist）的做法：
建立文件與「重新套用範本」時，在 server 端把值直接寫進 content_html。
值是建立當下的快照；估驗之後改了，要按「重新套用範本」重抓（會先存版本快照）。

範本內容各站不一定相同（範本是 noupdate：dev 是舊版型、jt 是新版型），
所以只依賴兩件事：{{ 變數名 }} 文字、以及「工項表是範本裡唯一有 <thead> 的表」。
找不到或不只一張就原樣留著（安全降級），不猜。
⚠️ 不能用「第一個 <tbody>」認工項表：範本在後台 HTML 編輯器存過一次，瀏覽器會替
沒寫 tbody 的表頭表補上 <tbody>，表頭就會整張被換成工項列（2026-11-08 抗辯實跑重現）。

⚠️ 填進去的值會變成 Jinja 原始碼：匯出 PDF／DOCX 與快速預覽會把 content_html 整份交給
Jinja 渲染（doc.render.mixin._render_template）。escape() 只處理 & < > ' "，所以工項名稱裡的
{{ 7*7 }} 會被求值、{# … #} 會讓中間的工項在 PDF 裡消失。值一律經 _text()：
跳脫 HTML 之外，把 {{ {% {# 開頭的「{」換成全形「｛」。不用 &#123;：編輯器存檔會把實體還原成 {；
不用零寬字元：canvas-editor 自己拿 \u200B 當內部記號。
"""
import re

from markupsafe import escape

from odoo.tools.float_utils import float_round

# 與 construction_template/utils/formatters.py 的 ROC_YEAR_OFFSET 相同
# （本模組不依賴 construction_template，不能 import）
ROC_YEAR_OFFSET = 1911
# 數量、單價顯示到小數第幾位（多的 0 會去掉：3.5000 → 3.5）
QTY_DIGITS = 4
PRICE_DIGITS = 4

_CELL = 'border:1px solid #000;padding:6px'
_NUM_CELL = _CELL + ';text-align:right'
# 範本沒有巢狀表格；表格與 tbody 都可能帶屬性（瀏覽器／編輯器存過）
_TABLE_RE = re.compile(r'<table\b[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)
_THEAD_RE = re.compile(r'<thead\b', re.IGNORECASE)
_TBODY_RE = re.compile(r'<tbody\b[^>]*>.*?</tbody>', re.DOTALL | re.IGNORECASE)
_VAR_RE = re.compile(r'\{\{\s*(\w+)\s*\}\}')
# Jinja 的三種開頭：{{ 運算式、{% 敘述、{# 註解
_JINJA_OPEN_RE = re.compile(r'\{(?=[{%#])')


def roc_date(value):
    """西元日期 → 民國點格式 113.09.23（與「工程估驗計價單」匯出同格式）。"""
    if not value:
        return ''
    return '%s.%02d.%02d' % (value.year - ROC_YEAR_OFFSET, value.month, value.day)


def round_half_up(value):
    """四捨五入到元。先到分再到元：加總的浮點誤差（1234.4999999998）不能把 .5 吃掉。

    與 construction_template/mappings/estimate_report.py::_round 同一個算法。
    不用 '{:,.0f}'：那是銀行家捨入（10.5 → 10）。
    """
    return int(float_round(float_round(value or 0.0, precision_digits=2), precision_digits=0))


def balanced(values, total):
    """各列四捨五入成整數，且加起來等於 round_half_up(total)（最大餘數法調尾差）。

    與 construction_template/mappings/estimate_report.py::_balanced 同一個算法：
    差額只補給「捨入時往反方向吃虧」的列；候選列不夠＝不是捨入造成的差異，照實印、不抹平。
    """
    target = round_half_up(total)
    rounded = [round_half_up(v) for v in values]
    diff = target - sum(rounded)
    if diff:
        step = 1 if diff > 0 else -1
        candidates = sorted((i for i in range(len(values)) if (values[i] - rounded[i]) * step > 0),
                            key=lambda i: (values[i] - rounded[i]) * step, reverse=True)
        if len(candidates) >= abs(diff):
            for i in candidates[:abs(diff)]:
                rounded[i] += step
    return rounded


def money(value):
    """整數元 → 千分位。"""
    return '{:,}'.format(value)


def number(value, digits):
    """數量／單價：千分位，最多 digits 位小數，去掉尾巴的 0（3.5000 → 3.5、2.0 → 2）。"""
    text = '{:,.{d}f}'.format(float_round(value or 0.0, precision_digits=digits), d=digits)
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _text(value):
    """要寫進 content_html 的資料值：跳脫 HTML，並拆掉 Jinja 開頭（見檔頭）。"""
    return _JINJA_OPEN_RE.sub('｛', str(escape(value)))


def fill_vars(content_html, values):
    """把 {{ 變數名 }} 換成處理過的值；values 沒列的變數原樣留著。

    用函式當替換值：值裡的反斜線不會被 re 當成跳脫序列。
    """
    return _VAR_RE.sub(
        lambda m: _text(values[m.group(1)]) if m.group(1) in values else m.group(0),
        str(content_html))


def inject_rows(content_html, rows):
    """把範本工項表（唯一有 <thead> 的表）的 <tbody> 換成 rows。

    每列 6 格：項次、工項名稱、單位、數量、單價、小計。
    rows 為空、找不到工項表、或有不只一張帶 thead 的表時原樣回傳（保留範本那一列空白）。
    """
    if not content_html or not rows:
        return content_html
    content_html = str(content_html)
    item_tables = [m for m in _TABLE_RE.finditer(content_html) if _THEAD_RE.search(m.group(0))]
    if len(item_tables) != 1:
        return content_html
    body = ''.join(
        '<tr>'
        '<td style="%s">%s</td>' % (_CELL, _text(item_no))
        + '<td style="%s">%s</td>' % (_CELL, _text(name))
        + '<td style="%s">%s</td>' % (_CELL, _text(unit))
        + ''.join('<td style="%s">%s</td>' % (_NUM_CELL, _text(v)) for v in (qty, price, amount))
        + '</tr>'
        for item_no, name, unit, qty, price, amount in rows
    )
    table = item_tables[0]
    new_table, n = _TBODY_RE.subn(lambda _m: '<tbody>' + body + '</tbody>', table.group(0), count=1)
    if not n:
        return content_html
    return content_html[:table.start()] + new_table + content_html[table.end():]
