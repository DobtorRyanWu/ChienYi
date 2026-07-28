# -*- coding: utf-8 -*-
"""construction_portal 前台共用工具（M4-a：從 portal.py god-file 抽出）。

模組層級的照片/缺失照片/GPS 輔助函式與前台角色群組常數。無任何對 controller 類別
的依賴，故可被 portal.py 與各路由 mixin 檔共同 import，不造成循環相依。
"""

import base64
import math

from odoo import fields

# 前台角色群組 XML id
# 註：v18.0.4.3.0 已將 boss/manager/field/observer 往下合併進
#     subscriber/leader/user/viewer（改名為 老闆/主管/現場人員/定期閱覽者），
#     故以下常數指向合併後的舊 xml_id。因四群組為單一繼承鏈
#     （viewer⊂user⊂leader⊂subscriber），guard 的 has_group 判斷語意等價：
#     _can_manage=subscriber or leader（老闆/主管）、_is_field_only=user 且非 leader。
GROUP_BOSS = 'construction_supervision_base.group_portal_subscriber'
GROUP_MANAGER = 'construction_supervision_base.group_portal_leader'
GROUP_FIELD = 'construction_supervision_base.group_portal_user'
GROUP_OBSERVER = 'construction_supervision_base.group_portal_viewer'
# 監造代操作員（內部）→ 前台管理權比照老闆/主管：可建案/審核/樣板 CRUD（_can_manage）。
# 註：可見範圍由內部使用者的核心多公司 rule 決定（見 supervision_project._get_portal_projects_domain）。
GROUP_OPERATOR = 'construction_supervision_base.group_operator'


# ─────────────────────────────────────────────────────────────────────
# 缺失匯入：record_type（監造／營造）四層優先序判定
# ─────────────────────────────────────────────────────────────────────
# QA=監造、QR=營造。權威依據是使用者自己的匯入管道 —— 匯入來源檔
# `E:\work\匯入\磺港溪B標\B標匯入_合併_20260726.xlsx`「缺失改善」工作表 R1 註記：
#   「⑦ record_type 由『原始編號(source_no)』前綴自動推導：
#     QA→監造(supervision)、QR→營造(contractor)。空白或前綴非 QA/QR 將報 ERR 不匯入。」
# 實測 B 標 43 筆 100% 符合；全庫 6 筆缺失編號前綴設定也一律是 XXXQA／XXXQR。
_QAQR_TO_RECORD_TYPE = {'QA': 'supervision', 'QR': 'contractor'}

# 第 3 層（代理推論）：缺失類別 → 監造／營造。
# A 標 88 筆的登錄編號全部是 `Q01-`（不帶 QA/QR），「改正單位」是唯一可用訊號。
# 標為推論而非權威：改正單位嚴格對應的是 check_type（施工檢查／安衛及環境清潔檢查），
# 與「誰開的單」是兩個維度，在這些案場高度重合但非邏輯必然。
_CATEGORY_TO_RECORD_TYPE = {
    'material': 'supervision',
    'workmanship': 'supervision',
    'dimension': 'supervision',
    'document': 'supervision',
    'safety': 'contractor',
    'environment': 'contractor',
}


def resolve_record_type(row, sheet_name=None, fallback='supervision'):
    """判定缺失單屬監造還是營造，四層優先序（權威 → 推論 → 人工）。

    1. 登錄編號前綴 QA/QR    —— 權威（B標 `QA-11309191`、P11001 `QA-001`）
    2. 工作表名 QA/QR        —— 權威（P11001 `QA.QR-工程缺失改善追蹤一覽表.xlsx`）
    3. 解析器自檔名推導      —— docx `derive_record_type()`
    4. 缺失類別代理推論      —— A 標唯一可用訊號
    5. 匯入頁下拉 fallback   —— 人工兜底

    `sheet_name` 現階段一律為 None（xlsx parser 尚未回傳工作表名）；
    介面先留著，parser 通用化後開始回傳即可生效，controller 不需再改。

    :param row: parser 輸出的單筆 dict
    :param sheet_name: 該筆所屬的工作表名（若 parser 有提供）
    :param fallback: 全部判不出時採用的值（來自匯入頁下拉）
    :return: 'supervision' 或 'contractor'
    """
    reg = (row.get('register_no') or '').strip().upper()
    for token, rt in _QAQR_TO_RECORD_TYPE.items():
        if reg.startswith(token):
            return rt

    if sheet_name:
        key = str(sheet_name).strip().upper()
        if key in _QAQR_TO_RECORD_TYPE:
            return _QAQR_TO_RECORD_TYPE[key]

    if row.get('record_type') in ('supervision', 'contractor'):
        return row['record_type']

    cat = row.get('defect_category')
    if cat in _CATEGORY_TO_RECORD_TYPE:
        return _CATEGORY_TO_RECORD_TYPE[cat]

    return fallback if fallback in ('supervision', 'contractor') else 'supervision'


def _photo_category_options(env):
    """照片分類下拉／篩選選項。

    改用後台可自由維護的 supervision.photo.category 主檔（取代舊的固定
    11 項 Selection `category`），讓前台選項與後台維護的分類一致。
    回傳 [(str(id), name), ...]，沿用既有模板/JS 的 (value, label) 結構，
    其中 value = 分類記錄 id 的字串。
    """
    cats = env['supervision.photo.category'].sudo().search(
        [('active', '=', True)], order='sequence, name')
    return [(str(c.id), c.name) for c in cats]


def _photo_category_to_id(value):
    """把前台送來的分類值（分類 id 字串）轉為可寫入 category_id 的整數。

    空值或非數字（例如舊 Selection key 'civil'）一律回傳 False（視為未選）。
    """
    try:
        return int(value) if value else False
    except (TypeError, ValueError):
        return False


def _portal_save_photos(env, record, supervision_project, files, meta):
    """把 multipart 上傳檔案存成 ir.attachment + supervision.photo,並 link 到 record.photo_ids

    繞過 photo.sync.mixin(對 daily.log.sheet 因 project_id 型別錯誤而失效),
    直接寫入正確的 supervision.project.id。

    files: list of werkzeug FileStorage(來自 request.httprequest.files.getlist('photos'))
    meta: dict 含 description / category / source_model / latitude / longitude / location_description
    回傳: 新增的 attachment id list
    """
    Attachment = env['ir.attachment'].sudo()
    Photo = env['supervision.photo'].sudo()
    new_atts = []
    try:
        lat = float(meta.get('latitude') or 0)
    except (TypeError, ValueError):
        lat = 0.0
    try:
        lng = float(meta.get('longitude') or 0)
    except (TypeError, ValueError):
        lng = 0.0
    description = meta.get('description') or ''
    category = meta.get('category') or False
    source_model = meta.get('source_model') or 'other'
    location_description = meta.get('location_description') or ''

    for f in files:
        if not f or not f.filename:
            continue
        data = f.read()
        if not data:
            continue
        att = Attachment.create({
            'name': f.filename,
            'datas': base64.b64encode(data),
            'res_model': record._name,
            'res_id': record.id,
            'mimetype': f.mimetype or 'image/jpeg',
            # M0.6：不再 public（避免 /web/content 枚舉洩漏）；
            # 前台顯圖改走帶權限檢查的 /construction/img/<att_id>。
            'public': False,
        })
        # 直接建 supervision.photo,不依賴 mixin
        if not Photo.search([('attachment_id', '=', att.id)], limit=1):
            Photo.create({
                'project_id': supervision_project.id,
                'attachment_id': att.id,
                'description': description or f.filename,
                'category_id': _photo_category_to_id(category),
                'source_model': source_model,
                'source_id': record.id,
                'shot_at': fields.Datetime.now(),
                'latitude': lat,
                'longitude': lng,
                'location_description': location_description,
            })
        new_atts.append(att.id)

    # C（2026-07-14）：僅在 record 真有 photo_ids 欄位時才寫入。
    # 通報單(reservation.notification.slip)沒有 photo_ids，靠 computed
    # related_photo_ids 反查 supervision.photo(source_model='notification')，
    # 上面已建好 supervision.photo，故此處跳過即可正確顯示。
    if new_atts and 'photo_ids' in record._fields:
        record.sudo().write({'photo_ids': [(4, aid) for aid in new_atts]})
    return new_atts


def _defect_save_photos(env, defect, files, stage):
    """建立缺失改善照片行(general/reservation.defect.improvement.photo)。

    缺失的 before_photo_ids / during_photo_ids / after_photo_ids 是 One2many
    到專用照片行模型(<defect_model>.photo),而非 ir.attachment 的 M2M。
    因此照片要用 create 照片行(image 為 binary,模型 create() 會自動建 attachment),
    不能用 (4, attachment_id) 去 link——那會被當成照片行 id 造成 MissingError。

    files: list of werkzeug FileStorage
    stage: 'before' / 'during' / 'after'
    回傳: 新增照片行數
    """
    Photo = env[defect._name + '.photo'].sudo()
    count = 0
    for f in files:
        if not f or not f.filename:
            continue
        raw = f.read()
        if not raw:
            continue
        line = Photo.create({
            'defect_improvement_id': defect.id,
            'image': base64.b64encode(raw),
            'image_filename': f.filename,
            'photo_stage': stage,
        })
        # M0.6：不再把附件設 public。缺失照片行的 image 欄位附件預設非 public，
        # 前台改走帶權限檢查的 /construction/img/<att_id>（依 defect→專案成員判定）。
        count += 1
    return count


def _portal_delete_photo(env, record, attachment_id):
    """從 record.photo_ids 移除一張 + 同步刪 supervision.photo + ir.attachment"""
    record.sudo().write({'photo_ids': [(3, attachment_id)]})
    env['supervision.photo'].sudo().search([
        ('attachment_id', '=', attachment_id),
    ]).unlink()
    env['ir.attachment'].sudo().browse(attachment_id).unlink()


def _portal_photo_to_supervision(env, attachments):
    """給 detail 頁用:回傳 {attachment_id: supervision_photo_id} dict"""
    if not attachments:
        return {}
    photos = env['supervision.photo'].sudo().search([
        ('attachment_id', 'in', attachments.ids),
    ])
    return {p.attachment_id.id: p.id for p in photos}


def _haversine_km(lat1, lng1, lat2, lng2):
    # 兩點球面距離(公里),用於比較大小,精度足夠
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
