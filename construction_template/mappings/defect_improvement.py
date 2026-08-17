# -*- coding: utf-8 -*-
"""矯正與預防處理紀錄（缺失改善）—— docx 對照表（專案層級，一筆一頁）。

樣板語法：`+++FOR record IN errorRecords+++ … +++END-FOR record+++`
——整份文件對每筆缺失重複一次。

EAGLE token → Odoo general.defect.improvement：
    no              defect_no          isConstruction/isHealthAndSafety  check_type
    notifiedAt      notification_date  deadLine                          deadline
    description     defect_description reason                            defect_cause
    improvements    improvement_action finishedAt                        improvement_date
    isQualified     recheck_result     isTimeout                         is_overdue
"""

import base64

from ..utils import photo_stamp, record_filter
from ..utils.formatters import contractor_name, roc_date

MODEL = 'project.project'
MODE = 'docx'

# 批次下載中心可用 context 限定期間；本表以「發現日期」為準（與既有 order 一致）
DATE_FIELD = 'found_date'
DATE_LABEL = '發現日期'


def WARNINGS(project):
    """日期空白的缺失一律列入，但要讓人知道有哪幾筆"""
    return record_filter.project_warning(
        project, source_model(project), DATE_FIELD, DATE_LABEL)

MARK = 'ˇ'          # 樣板既有的勾選符號慣例（見送審管制「是ˇ、否X」）
# 以下值由 fields_get 實查（2026-08-05），不是照字面猜：
#   check_type      construction 施工檢查 / safety_env 安衛及環境清潔檢查
#                   ——與樣板上印的兩個選項文字完全一致
#   recheck_result  pass 通過 / fail 不通過 / pending 待複查
#   state           draft 草稿 / notified 已通知 / improving 改善中 /
#                   improved 已改善 / verified 已驗證 / closed 結案
CLOSED_STATES = ('verified', 'closed')


def _photo(photos):
    """取第一張照片給樣板的 IMAGE 佔位；沒有就留白。

    照 EAGLE 原系統 imageGenerator 的行為（source map 還原）：
      · 尺寸等比縮放，上限 14×10 cm（由 docx_render 依實際圖片比例算）
      · 拍攝日期印在右下角紅字浮水印

    supervision.photo.image 是 Odoo Binary 欄位，讀出來是 base64 的 bytes，
    要解碼成原始位元組才能交給 docxtpl 的 InlineImage。
    """
    photo = photos[:1]
    raw = None
    if photo and photo.image:
        raw = base64.b64decode(photo.image)
        taken = photo.shot_date or (photo.shot_at.date() if photo.shot_at else None)
        raw = photo_stamp.stamp_date(raw, taken)
    return {
        'image': {'__image__': raw},
        'description': (photo.description or photo.name or '') if photo else '',
        'isEmpty': not raw,
    }


def _record(defect):
    return {
        'no': defect.defect_no or defect.name or '',
        # 樣板第二頁（照片紀錄表）用的是大寫 No，與第一頁的 no 並存
        'No': defect.defect_no or defect.name or '',
        'isOther': '',
        # 前 / 中 / 後三張照片，對應樣板的 images[0] / [1] / [2]
        'images': [_photo(defect.before_photo_ids),
                   _photo(defect.during_photo_ids),
                   _photo(defect.after_photo_ids)],
        'isConstruction': MARK if defect.check_type == 'construction' else '',
        'isHealthAndSafety': MARK if defect.check_type == 'safety_env' else '',
        'notifiedAt': roc_date(defect.notification_date),
        'deadLine': roc_date(defect.deadline),
        'description': defect.defect_description or '',
        'reason': defect.defect_cause or '',
        'improvements': defect.improvement_action or '',
        'finishedAt': roc_date(defect.improvement_date),
        'isQualified': MARK if defect.recheck_result == 'pass' else '',
        'isTimeout': MARK if defect.is_overdue else '',
        'isUncorrected': MARK if defect.state not in CLOSED_STATES else '',
        'result': defect.improvement_result or '',
    }


def source_model(project):
    """預約式專案的缺失掛在通報單底下，是另一個模型。

    兩者都繼承 construction.daily.defect.mixin，本檔用到的欄位名完全一致；
    預約式的 project_id 是 store=True 的 related，domain 直接可用。
    寫法比照 self_inspection.py 的 _inspection_model()。
    """
    return ('reservation.defect.improvement' if project.project_type == 'reservation'
            else 'general.defect.improvement')


def build_context(project):
    Defect = project.env[source_model(project)]
    defects = Defect.search(
        [('project_id', '=', project.id)]
        + record_filter.date_domain(project.env, DATE_FIELD),
        order='found_date, id')
    contractor = contractor_name(project)
    return {
        # 原系統的 title 是填報單位（依 unitType 給營造或監造），不是表名
        'title': contractor or (project.management_company_name or ''),
        'projectContractor': contractor,
        'projectName': project.name or '',
        'errorRecords': [_record(d) for d in defects],
    }


def FILENAME(project):
    return '矯正與預防處理紀錄_%s.docx' % (project.name or project.id)
