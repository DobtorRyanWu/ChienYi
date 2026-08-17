# -*- coding: utf-8 -*-
"""對照表用的值格式器。13 張樣板共用，加新格式器請寫在這裡不要散在各對照表。

對照表寫 `('log_date', 'roc_date')` 時，'roc_date' 就是這裡的鍵。
"""

ROC_YEAR_OFFSET = 1911  # 民國 = 西元 - 1911


def roc_date(value, record=None, field=None):
    """西元日期 → 民國格式，例：2024-09-23 → 113.09.23"""
    if not value:
        return ''
    return '%s.%02d.%02d' % (value.year - ROC_YEAR_OFFSET, value.month, value.day)


def roc_date_slash(value, record=None, field=None):
    """民國格式（斜線），例：113/09/23"""
    if not value:
        return ''
    return '%s/%02d/%02d' % (value.year - ROC_YEAR_OFFSET, value.month, value.day)


def roc_date_cn(value, record=None, field=None):
    """民國「年月日」格式，例：2024-09-23 → 113年9月23日（不補零）。

    EAGLE 原系統的 docx 管制表用這個格式
    （models/errorRecord.js：`${y-1911}年${m+1}月${d}日`），
    與 xlsx 用的點格式 113.09.23 不同，不要混用。
    """
    if not value:
        return ''
    return '%s年%s月%s日' % (value.year - ROC_YEAR_OFFSET, value.month, value.day)


def ad_date(value, record=None, field=None):
    """西元日期字串 2024-09-23"""
    return value.strftime('%Y-%m-%d') if value else ''


def selection_label(value, record=None, field=None):
    """Selection 的 value → 顯示標籤（天氣、狀態這類欄位用）"""
    if not value or record is None or not field:
        return value or ''
    selection = record._fields[field].selection
    if callable(selection):
        selection = selection(record)
    return dict(selection).get(value, value)


def percent(value, record=None, field=None):
    """數值 → 兩位小數字串（不加 %，因為樣板格子通常已經印了）"""
    return '' if value is None else '%.2f' % value


def money(value, record=None, field=None):
    """金額 → 千分位整數"""
    return '' if value is None else '{:,.0f}'.format(value)


def yes_no(value, record=None, field=None):
    """Boolean 或 yes/no Selection → 「有 / 無」"""
    if isinstance(value, bool):
        return '有' if value else '無'
    return {'yes': '有', 'no': '無'}.get(value, value or '')


def count(value, record=None, field=None):
    """One2many / Many2many → 筆數（契約變更次數這類欄位用）"""
    return len(value) if value else 0


def contractor_name(project):
    """工程案件的「施工廠商 / 承攬廠商」名稱，給各張管制表的表頭用。

    取值序：contractor_company_name（純文字）→ contractor_company_ids 的聯絡人名。

    ⚠️ 不可以只讀 contractor_partner_ids：那是 contractor_company_ids（承包廠商
    **公司記錄**）的 partner，而本系統是一庫一公司架構，多數專案根本沒設那個 M2M，
    只讀它會讓所有管制表的廠商欄整格空白（2026-08-17 實測：自主檢查總表就是這樣，
    工程案件明明填了「測試用02」，印出來卻是空的）。

    這不是格式器（不吃 value/record/field），所以不進 FORMATTERS 字典，
    由各對照表的 build_context() 直接呼叫。
    """
    if project.contractor_company_name:
        return project.contractor_company_name
    return '、'.join(project.contractor_partner_ids.mapped('name'))


FORMATTERS = {
    'count': count,
    'roc_date': roc_date,
    'roc_date_slash': roc_date_slash,
    'roc_date_cn': roc_date_cn,
    'ad_date': ad_date,
    'selection_label': selection_label,
    'percent': percent,
    'money': money,
    'yes_no': yes_no,
}
