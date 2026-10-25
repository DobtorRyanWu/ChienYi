# -*- coding: utf-8 -*-
"""材料設備品質抽(查)驗紀錄表 —— docx 對照表（一筆檢(試)驗紀錄一張）。

樣板來自新北市政府工程契約附表11（承攬廠商品質管制規定，2026-10-25 由
tools/ntpc_forms/build_forms.py 從契約 Word 原表切出）。系統預設版拿掉「附表11」標籤，
八里／中正橋的案件專用版保留。欄位是 construction_test 2.7.0 為這張表新增的。

勾選框印 ■／□；「其他」抽驗方式沒有獨立勾選，有填說明就勾。
「抽(查)驗結果」只自動勾合格／不合格（由「抽試驗結果」決定），數量不足、
堆置場所不良、其他三格由現場手勾——系統沒有記這三種情況。
試驗數據紙本預印 3 組：不足補空白，超過的接在 valuesMore（不能靜靜消失）。
"""

from ..utils.formatters import roc_date_cn

MODEL = 'supervision.test.record'
MODE = 'docx'

BOX_ON, BOX_OFF = '■', '□'
PRINTED_VALUE_ROWS = 3


def _box(flag):
    return BOX_ON if flag else BOX_OFF


def _qty(value, unit):
    if not value:
        return ''
    text = ('%g' % value) if isinstance(value, float) else str(value)
    return '%s %s' % (text, unit) if unit else text


def _members(record):
    names = (record.supervision_member_ids | record.contractor_member_ids).mapped('name')
    if record.owner_member:
        names.append(record.owner_member)
    return '、'.join(n for n in names if n)


def _values(record):
    rows = [{'item': v.item_name or '', 'standard': v.standard_value or '',
             'test': v.test_value or ''} for v in record.value_ids]
    printed = rows[:PRINTED_VALUE_ROWS]
    while len(printed) < PRINTED_VALUE_ROWS:
        printed.append({'item': '', 'standard': '', 'test': ''})
    more = '；'.join('%s：合格值 %s、試驗值 %s' % (r['item'], r['standard'] or '－', r['test'] or '－')
                    for r in rows[PRINTED_VALUE_ROWS:])
    return printed, more


def build_context(record):
    project = record.project_id
    values, more = _values(record)
    return {
        'projectName': project.name or '',
        'no': record.name or '',
        'materialName': record.task_id.name or (record.standard_id.material or ''),
        'supplier': record.supplier_name or '',
        'inSiteDate': roc_date_cn(record.in_site_date),
        'inSiteQty': _qty(record.in_site_quantity, record.standard_unit),
        'factoryCertDocs': record.factory_cert_docs or '',
        'storageLocation': record.storage_location or '',
        'contractNorm': record.standard_norm or '',
        'methodFactory': _box(record.method_factory),
        'methodCatalog': _box(record.method_catalog),
        'methodSite': _box(record.method_site),
        'methodLab': _box(record.method_lab),
        'methodDocument': _box(record.method_document),
        'methodOther': _box(record.method_other_note),
        'methodOtherNote': record.method_other_note or '',
        'sampleQty': _qty(record.sample_quantity, record.standard_unit),
        'sampleKeepLocation': record.sample_keep_location or '',
        'sampleDate': roc_date_cn(record.sample_date),
        'sampleSendDate': roc_date_cn(record.sample_send_date),
        'testDate': roc_date_cn(record.test_date),
        'members': _members(record),
        'concretePourLocation': record.concrete_pour_location or '',
        'labName': record.lab_name or '',
        'reportNo': record.test_report_no or '',
        # 「如試驗報告」：有附報告、但數據沒有逐項打進系統時勾
        'asReportBox': _box(record.attachment_ids and not record.value_ids),
        'values': values,
        'valuesMore': more,
        'passBox': _box(record.result == 'pass'),
        'failBox': _box(record.result == 'fail'),
        'remark': record.note or '',
    }


def FILENAME(record):
    return '材料設備品質抽查驗紀錄表_%s_%s.docx' % (
        record.project_id.name or '', record.name or record.id)
