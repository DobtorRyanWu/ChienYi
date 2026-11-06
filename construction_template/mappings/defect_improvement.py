# -*- coding: utf-8 -*-
"""矯正與預防處理紀錄（缺失改善）—— docx 對照表（專案層級，一筆一頁）。

樣板語法：`+++FOR record IN errorRecords+++ … +++END-FOR record+++`
——整份文件對每筆缺失重複一次。

EAGLE token → Odoo general.defect.improvement：
    no              defect_no          isConstruction/isHealthAndSafety  check_type
    notifiedAt      notification_date  deadLine                          deadline
    description     defect_description reason                            defect_cause
    improvements    improvement_action finishedAt                        improvement_date
    isQualified／isTimeout／isUncorrected／isOther   只勾一格，見 _outcome()（outcome_result 優先；
                    沒填才看 state、recheck_result、is_overdue）
"""

import base64

from ..utils import photo_stamp, record_filter
from ..utils.formatters import contractor_name, roc_date
from .self_inspection_form import ordered_photos

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
BOX_ON, BOX_OFF = '■', '□'   # 新北版樣板的勾選框（舊樣板用上面的 MARK 慣例）

# 「缺失改善成果確認」的結果（_outcome），樣板上 □符合要求 □逾時未矯正 □未矯正 □其他 只勾一格
QUALIFIED, TIMEOUT, UNCORRECTED, OTHER = 'qualified', 'timeout', 'uncorrected', 'other'

# 照片尺寸上限（公分）：樣板標記寫的是 imageGenerator(…, {height:6}, …)，EAGLE 原系統
# 是 `maxHeight = opts.height || 10`、`maxWidth = opts.width || 14` → 高 6 cm。
# 寬度不用 EAGLE 的 14：照片格只有 7223 dxa（12.74 cm），扣掉左右內距後 12 cm 才放得下
# （2026-11-05 Word 實印：用 14×10 時照片 13.3 cm，右邊被切掉）。
PHOTO_MAX_HEIGHT_CM = 6
PHOTO_MAX_WIDTH_CM = 12


def _outcome(defect):
    """缺失改善成果確認：qualified / timeout / uncorrected / other，或 None／corrected（都不勾）。

    0. 缺失上有存「成果確認」（construction_quality outcome_result）就照它：值就是上面這幾個常數；
       「已矯正」（corrected）表單上沒有格子，EAGLE 列印時四格都不勾（methods/errorRecord.js）。
       2026-11-06 使用者裁示：回填舊資料要照 EAGLE（EAGLE 是監造選的結果、印的時候照勾，例：存「未矯正」
       但期限已過，EAGLE 印未矯正，自動判斷會印逾時未矯正）。狀態一變存值就被清掉（mixin.write）。
       沒填才走下面的自動判斷。

    EAGLE 原系統是單一 result 欄、四格互斥（main.js `isQualified=result===qualified` …）。
    🔴 原本三格各自判斷（2026-11-05 實查）：
      ・未矯正＝「狀態不是已驗證／結案」→ 已改善（廠商做完、監造還沒驗證）被勾成未矯正
      ・符合要求只看 recheck_result，但沒有任何按鈕會寫它（驗證通過寫的是 verify_result
        與 state）→ dev 176 筆結案的三格全空
      ・逾期時「逾時未矯正」「未矯正」兩格一起勾
    判斷順序（使用者 2026-11-05 裁示 EAGLE 式只勾一格；已改善待驗證不勾）：
      1. 已驗證／結案 → 符合要求
      2. 一般式表單可手填的複查結果：通過 → 符合要求；不通過 → 未矯正（逾期則逾時未矯正）；
         待複查 → 不勾（附表12 測試 10-24 定的語意，保留）
      3. 已改善 → 不勾（等監造驗證）
      4. 其餘（草稿、已通知、改善中——含驗證不通過退回的）→ 未矯正（逾期則逾時未矯正）
    """
    if defect.outcome_result:
        return defect.outcome_result
    if defect.state in CLOSED_STATES:
        return QUALIFIED
    if defect.recheck_result == 'pass':
        return QUALIFIED
    if defect.recheck_result == 'pending':
        return None
    if defect.state == 'improved' and defect.recheck_result != 'fail':
        return None
    return TIMEOUT if defect.is_overdue else UNCORRECTED


def _photo(photos):
    """取第一張照片給樣板的 IMAGE 佔位；沒有就留白。

    照 EAGLE 原系統 imageGenerator 的行為（source map 還原）：
      · 尺寸等比縮放，上限照樣板標記（高 6 cm，寬見 PHOTO_MAX_WIDTH_CM）
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
        'image': {'__image__': raw, 'max_width_cm': PHOTO_MAX_WIDTH_CM,
                  'max_height_cm': PHOTO_MAX_HEIGHT_CM},
        'description': (photo.description or photo.name or '') if photo else '',
        'isEmpty': not raw,
    }


def _photo_pages(defect):
    """照片紀錄表的每一頁：[{no, total, images:[前, 中, 後]}]。

    樣板每個階段只有一格；同一階段不只一張時，第 2 張起印在續頁（使用者 2026-11-06 裁示），
    續頁上沒有照片的階段留白。每階段依拍攝先後（原本取 _order＝最新的那張）。
    """
    stages = [ordered_photos(photos) for photos in (
        defect.before_photo_ids, defect.during_photo_ids, defect.after_photo_ids)]
    total = max([len(photos) for photos in stages] + [1])
    return [{'no': n + 1, 'total': total,
             'images': [_photo(photos[n:n + 1]) for photos in stages]}
            for n in range(total)]


def _record(defect):
    outcome = _outcome(defect)
    photo_pages = _photo_pages(defect)
    return {
        'no': defect.defect_no or defect.name or '',
        # 樣板第二頁（照片紀錄表）用的是大寫 No，與第一頁的 no 並存
        'No': defect.defect_no or defect.name or '',
        # 前 / 中 / 後三張照片，對應樣板的 images[0] / [1] / [2]——第一頁那三張；
        # 舊樣板（$record.images、新北附表12）照舊只印這三張
        'images': photo_pages[0]['images'],
        # 系統預設樣板的照片紀錄表依這個迴圈印續頁（$page.images、page.no／page.total）
        'photoPages': photo_pages,
        'isConstruction': MARK if defect.check_type == 'construction' else '',
        'isHealthAndSafety': MARK if defect.check_type == 'safety_env' else '',
        'notifiedAt': roc_date(defect.notification_date),
        'deadLine': roc_date(defect.deadline),
        'description': defect.defect_description or '',
        'reason': defect.defect_cause or '',
        'improvements': defect.improvement_action or '',
        'finishedAt': roc_date(defect.improvement_date),
        # 只勾一格（_outcome）
        'isQualified': MARK if outcome == QUALIFIED else '',
        'isTimeout': MARK if outcome == TIMEOUT else '',
        'isUncorrected': MARK if outcome == UNCORRECTED else '',
        'isOther': MARK if outcome == OTHER else '',
        'result': defect.improvement_result or '',
        # 新北契約附表12「不合格品改正紀錄表」用（2026-10-24 加；舊 key 不動）
        'foundAt': roc_date(defect.found_date),
        'location': defect.defect_location or '',
        'recheckAt': roc_date(defect.recheck_date),
        # 「□改善完成 □未完成改善」：與上面三格同一套判斷（使用者 2026-11-05 裁示）；
        # 已改善待驗證、待複查兩格都不勾
        'doneBox': BOX_ON if outcome == QUALIFIED else BOX_OFF,
        'undoneBox': BOX_ON if outcome in (TIMEOUT, UNCORRECTED) else BOX_OFF,
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
        # 新北附表12 的「監造廠商」；與 review_control／test_control 的 supervision 同一欄
        'supervisorCompany': project.management_company_name or '',
        'errorRecords': [_record(d) for d in defects],
    }


def FILENAME(project):
    return '矯正與預防處理紀錄_%s.docx' % (project.name or project.id)
