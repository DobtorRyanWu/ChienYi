"""積分名冊匯出的欄位常數表（計畫 P17、§8）。

不做成後台可設定的模型：工程會的正式格式目前拿不到（§14 #5），
拿到時本來就要開發者核對一次，可設定化只是把錯誤面放大。
拿到格式之後改的是這張表，不是使用者介面。
"""

from odoo.addons.assoc_base import tools_export

# (標題, getter, fmt)。身分證是否遮蔽由呼叫端決定（匯出明文要寫 audit）。
CREDIT_EXPORT_COLUMNS = (
    ('身分證字號', lambda att: att['national_id'], 'text'),
    ('姓名', lambda att: att['name'], 'text'),
    ('技師科別', lambda att: att['engineer_field'], 'text'),
    ('課程名稱', lambda att: att['course'], 'text'),
    ('日期', lambda att: att['date'], 'date_roc'),
    ('時數', lambda att: att['hours'], 'text'),
    ('積分', lambda att: att['points'], 'int'),
    ('類別', lambda att: att['category'], 'text'),
    ('認可文號', lambda att: att['approval_ref'], 'text'),
)


def credit_rows(attendances, reveal_national_id=False):
    """把出席紀錄轉成匯出用的 dict（明文身分證要另外寫 audit）。"""
    rows = []
    for att in attendances:
        member = att.member_id.sudo()
        rows.append({
            'national_id': (att.member_id._national_id_plain()
                            if reveal_national_id else member.national_id_masked or ''),
            'name': member.name,
            'engineer_field': member.engineer_field or '',
            'course': att.meeting_id.name,
            'date': att.meeting_id.date_begin.date() if att.meeting_id.date_begin else False,
            'hours': att.meeting_id.credit_hours or '',
            'points': att.credit_points,
            'category': dict(att.meeting_id._fields['credit_category'].selection).get(
                att.meeting_id.credit_category, ''),
            'approval_ref': att.meeting_id.approval_ref or '',
        })
    return rows


def write_credit_file(attendances, file_type='xlsx', reveal_national_id=False):
    return tools_export.write_rows(
        CREDIT_EXPORT_COLUMNS, credit_rows(attendances, reveal_national_id), file_type)
