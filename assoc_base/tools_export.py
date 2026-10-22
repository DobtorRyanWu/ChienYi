"""共用匯出 writer（積分名冊、現金與宜睿禮券名單等）。

設計（計畫 P17）：欄位對應寫成各自的 Python 常數表，不做成後台可設定的模型——
宜睿與工程會的官方範本目前都拿不到，拿到時本來就要開發者核對，
可設定化只是把錯誤面放大。

兩個硬規則：
- **公式注入**：姓名或備註以 `= + - @` 開頭時，Excel 會把儲存格當公式執行。
  xlsx 一律 write_string；csv 一律加 `'` 前綴。
- **編碼**：csv 一律 UTF-8-SIG。cp950（Big5）編不出「喆、堃、峯」這類常見人名用字，
  strict 會整批失敗、replace 會把名字寫壞。
"""

import csv
import io

FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')
CSV_ENCODING = 'utf-8-sig'


def escape_formula(value):
    text = '' if value is None or value is False else str(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def roc_date(value):
    """民國年：115/09/18。value 為 date 或 False。"""
    if not value:
        return ''
    return '%d/%02d/%02d' % (value.year - 1911, value.month, value.day)


def iso_date(value):
    return value.strftime('%Y-%m-%d') if value else ''


def _cell(value, fmt, escape=True):
    """escape=True 只給 csv 用：xlsx 靠 write_string 防公式，加 ' 反而會在儲存格裡看得到。"""
    if fmt == 'int':
        return int(value or 0)
    if fmt == 'date_roc':
        return roc_date(value)
    if fmt == 'date_iso':
        return iso_date(value)
    text = '' if value is None or value is False else str(value)
    return escape_formula(text) if escape else text


def write_rows(columns, records, file_type='xlsx'):
    """把紀錄輸出成 xlsx 或 csv 的 bytes。

    :param columns: ((標題, getter, fmt), ...)；getter 收一筆紀錄回傳值，
                    fmt ∈ text/int/date_iso/date_roc
    :param records: 可迭代的紀錄（Odoo recordset 或 dict 皆可，由 getter 決定）
    """
    headers = [col[0] for col in columns]
    rows = list(records)

    if file_type == 'csv':
        table = [[_cell(getter(rec), fmt) for _header, getter, fmt in columns] for rec in rows]
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator='\n')
        writer.writerow(headers)
        writer.writerows(table)
        return buf.getvalue().encode(CSV_ENCODING)

    table = [[_cell(getter(rec), fmt, escape=False) for _header, getter, fmt in columns]
             for rec in rows]

    import xlsxwriter  # 只有 xlsx 才需要，csv 路徑不依賴它

    stream = io.BytesIO()
    book = xlsxwriter.Workbook(stream, {'in_memory': True})
    sheet = book.add_worksheet()
    bold = book.add_format({'bold': True})
    for col, header in enumerate(headers):
        sheet.write_string(0, col, header, bold)
    for row_idx, row in enumerate(table, start=1):
        for col, value in enumerate(row):
            if isinstance(value, int) and not isinstance(value, bool):
                sheet.write_number(row_idx, col, value)
            else:
                # write_string：不用 write()，它會把 "=..." 當公式寫進去
                sheet.write_string(row_idx, col, value)
    book.close()
    return stream.getvalue()
