# -*- coding: utf-8 -*-
"""construction_portal 前台共用工具（M4-a：從 portal.py god-file 抽出）。

模組層級的照片/缺失照片/GPS 輔助函式與前台角色群組常數。無任何對 controller 類別
的依賴，故可被 portal.py 與各路由 mixin 檔共同 import，不造成循環相依。
"""

import base64
import logging
import math

from odoo import fields

_logger = logging.getLogger(__name__)

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


def _post_photo_meta(post):
    """從表單取照片的三個描述欄位（說明／材料分類／拍攝地點說明）。

    回傳可直接併進 _portal_save_photos 的 meta 的 dict。

    **欄位名在本 codebase 有兩套並存**：
      - 不帶前綴 `description` / `category` / `location_description`
        ── 共用片段 cy_photo_meta_fields（portal_templates.xml）、
           共用照片區塊 portal_construction_photos_block、照片中心批次上傳
      - 帶前綴 `photo_description` / `photo_category` / `photo_location_description`
        ── 施工日誌主上傳表單、自主檢查新增表單

    兩套都收。這與座標欄位的 _post_geo()（portal_photo.py）同一個問題與同一種
    解法：只認一套的話，另一邊改了會**靜默失效** —— 不噴例外，只是欄位恆為空，
    使用者以為填了、資料庫裡卻沒有。

    **優先序：帶前綴的先取。** 不帶前綴的 `description` 這種通用名字會跟宿主
    表單自己的欄位撞名 —— 新增缺失表單的「缺失說明」就是 name="description"，
    共用片段再放一個同名的，瀏覽器兩個都送、post.get() 只拿得到排在前面的那個，
    結果照片說明被塞進缺失的敘述文字、使用者填的照片說明整個消失。
    帶前綴的名字不可能是別的東西，拿它當第一順位才不會被宿主表單汙染。
    """
    return {
        'description': post.get('photo_description') or post.get('description') or '',
        'category': post.get('photo_category') or post.get('category') or False,
        'location_description': (post.get('photo_location_description')
                                 or post.get('location_description') or ''),
    }


def _photo_source_field(env, record):
    """找出 supervision.photo 上對應這個來源模型的 Many2one 欄位名。

    對照表由各模組在 supervision.photo._photo_source_field_map() 自行註冊
    （見 construction_daily_log / construction_quality / ... 的
    models/supervision_photo.py），上游不必知道下游有哪些模型。
    找不到就回 None —— 照片仍會建出來、仍看得到，只是不掛在來源上。
    """
    return env['supervision.photo'].sudo()._photo_source_field_map().get(record._name)


def _portal_save_photos(env, record, supervision_project, files, meta):
    """把 multipart 上傳檔案存成 ir.attachment + supervision.photo，並掛回來源。

    照片資料表收斂（2026-07-31）後，這是**唯一**的前台照片存檔路徑：
    缺失改善原本走的照片行子模型已經不存在，_defect_save_photos 現在只是
    帶 photo_stage 的薄包裝。

    掛回來源不再是寫 M2M（record.photo_ids = [(4, att_id)]），而是直接把
    supervision.photo 的來源 Many2one 設好 —— 那個欄位就是來源的 One2many
    反向端，所以存完照片自然出現在來源表單上，不需要任何「同步」。

    files: list of werkzeug FileStorage（來自 request.httprequest.files.getlist）
    meta 可帶：
        description / category / location_description   ← 使用者填的三個欄位
        latitude / longitude                            ← 定位鈕或手填
        fallback_latitude / fallback_longitude          ← 座標繼承（僅告示牌與通報單）
        source_model                                    ← 相容用，留空會自動推導
        photo_stage                                     ← 缺失專用（before/during/after）
    回傳: 新增的 attachment id list
    """
    Attachment = env['ir.attachment'].sudo()
    Photo = env['supervision.photo'].sudo()
    new_atts = []

    def _f(key):
        try:
            return float(meta.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    lat, lng = _f('latitude'), _f('longitude')
    description = meta.get('description') or ''
    category = meta.get('category') or False
    location_description = meta.get('location_description') or ''
    photo_stage = meta.get('photo_stage') or False

    # 座標繼承（opt-in）：只有工程告示牌與通報單會帶。supervision.photo.create()
    # 會在「使用者沒填、照片也沒有 EXIF」時才採用。
    PhotoTarget = Photo
    fb_lat, fb_lng = meta.get('fallback_latitude'), meta.get('fallback_longitude')
    if fb_lat is not None and fb_lng is not None:
        PhotoTarget = Photo.with_context(
            photo_fallback_latitude=fb_lat,
            photo_fallback_longitude=fb_lng)

    source_field = _photo_source_field(env, record)
    if not source_field:
        _logger.warning(
            '照片上傳：supervision.photo 沒有對應 %s 的來源欄位，'
            '照片會建立但不會掛在來源記錄上', record._name)

    for f in files:
        if not f or not f.filename:
            continue
        data = f.read()
        if not data:
            continue
        att = Attachment.create({
            'name': f.filename,
            'datas': base64.b64encode(data),
            'res_model': 'supervision.photo',
            'mimetype': f.mimetype or 'image/jpeg',
            # M0.6：不再 public（避免 /web/content 枚舉洩漏）；
            # 前台顯圖改走帶權限檢查的 /construction/img/<att_id>。
            'public': False,
        })
        if not Photo.with_context(active_test=False).search(
                [('attachment_id', '=', att.id)], limit=1):
            vals = {
                'project_id': supervision_project.id,
                'attachment_id': att.id,
                # 使用者有填就用使用者的，沒填才退回檔名。
                # （收斂前走同步那條路的會被系統套版字串蓋掉，格式因此不一致）
                'description': description or f.filename,
                'category_id': _photo_category_to_id(category),
                'location_description': location_description,
                'shot_at': fields.Datetime.now(),
                'latitude': lat,
                'longitude': lng,
            }
            if photo_stage:
                vals['photo_stage'] = photo_stage
            if source_field:
                vals[source_field] = record.id
            # source_model 留空時由 _normalize_source_fields() 依來源欄位自動推導
            if meta.get('source_model'):
                vals['source_model'] = meta['source_model']
            PhotoTarget.create(vals)
        new_atts.append(att.id)

    return new_atts


def _defect_save_photos(env, defect, files, stage, meta=None):
    """建立缺失改善照片（before / during / after）。

    照片收斂後這只是 _portal_save_photos 的薄包裝：缺失照片與其他照片走
    完全同一條路，差別只在多帶一個 photo_stage。

    收斂前這裡要自己建照片行子模型、再手動呼叫 _auto_sync_photos() 補同步、
    最後還要另外把座標補寫回 supervision.photo（因為座標欄位只在那邊）——
    整整三段，現在一段都不需要了。
    """
    meta = dict(meta or {})
    meta['photo_stage'] = stage
    project = defect.project_id
    return len(_portal_save_photos(env, defect, project, files, meta))



def _portal_delete_photo(env, record, attachment_id):
    """刪除一張前台照片（以 attachment id 指定）。

    照片資料表收斂後大幅簡化：photo_ids 是 One2many 到 supervision.photo，
    刪掉照片本身就等於從來源移除，不需要再先解 M2M 關聯。
    supervision.photo.unlink() 會順手回收沒人再引用的 ir.attachment。

    `record` 參數保留是為了呼叫端相容（三條路由都還在傳），本身已不需要用到。
    """
    photos = env['supervision.photo'].sudo().with_context(
        active_test=False).search([('attachment_id', '=', attachment_id)])
    if photos:
        photos.unlink()
        return
    # 沒有對應 supervision.photo 的孤兒附件（理論上不該出現），直接清掉。
    # exists() 不可省：對已刪除的 record 再 unlink 會拋 MissingError，
    # Odoo 會把整個 request transaction rollback → 症狀是「跳錯誤而且沒刪掉」。
    attachment = env['ir.attachment'].sudo().browse(attachment_id).exists()
    if attachment:
        attachment.unlink()


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
