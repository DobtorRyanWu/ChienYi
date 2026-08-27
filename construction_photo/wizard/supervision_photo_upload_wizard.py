# -*- coding: utf-8 -*-
"""後台批次上傳照片精靈。

解決三件事：
1. 檢試驗記錄與通報單的後台照片頁籤**只有唯讀反查**，完全沒有上傳入口
   （見 construction_test/views/test_record_views.xml 與
     construction_notification_slip/views/notification_slip_views.xml
     的 related_photo_ids readonly="1" + no_create）
2. 照片資料表收斂後，各業務模型的照片欄位從 M2M（widget=many2many_binary，
   可一次拖多檔）改成 One2many 內嵌 list（只能一列一列加）→ 用精靈把
   「一次拖多檔」補回來
3. 使用者要求每張照片都要有 說明／材料分類／拍攝地點說明，且是
   **整批共用預設值、事後可逐張改**（照片管理清單已設 editable="bottom"）

放在 construction_photo 而不是各業務模組：construction_daily_log /
construction_quality / construction_general / construction_test /
construction_notification_slip 五個模組的 manifest 都 depends 本模組，
而本精靈靠 supervision.photo._photo_source_field_map() 在執行期查來源欄位，
不需要 import 任何下游模型。
"""

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SupervisionPhotoUploadWizard(models.TransientModel):
    _name = 'supervision.photo.upload.wizard'
    _description = '批次上傳照片'

    # widget="many2many_binary"（在 form view 指定）＝ 可一次拖進多個檔案
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'supervision_photo_upload_wizard_att_rel',
        'wizard_id', 'attachment_id',
        string='照片檔案',
        required=True,
        help='可一次選取／拖曳多個檔案')

    # ── 整批共用的預設值（寫進每一張照片後可逐張修改）──────────────
    description = fields.Char(
        string='照片說明',
        help='留空則自動使用檔案名稱。此值會套用到本次上傳的每一張照片，'
             '之後可在照片管理清單逐張修改。')
    category_id = fields.Many2one(
        'supervision.photo.category', string='材料分類')
    location_description = fields.Char(string='拍攝地點說明')

    latitude = fields.Float(string='緯度', digits=(10, 7))
    longitude = fields.Float(string='經度', digits=(10, 7))

    photo_stage = fields.Selection([
        ('before', '矯正及預防前'),
        ('during', '矯正及預防中'),
        ('after', '矯正及預防後'),
    ], string='照片階段',
       help='缺失改善專用：區分矯正前／中／後三階段。其他來源留空。')

    # ── 來源（由 action 的 context 帶入，唯讀顯示讓使用者確認掛對地方）──
    source_model = fields.Char(string='來源模型', readonly=True)
    source_name = fields.Char(string='上傳到', readonly=True)

    # 從「照片管理」清單／看板／選單直接開精靈時沒有來源記錄（沒有 active_model），
    # 這時候照片要掛哪個工程案件無從推導，改由使用者自己選。
    # 有來源記錄時這個欄位隱藏，工程案件仍由 _resolve_project() 從來源推出來。
    project_id = fields.Many2one(
        'project.project', string='所屬工程',
        help='從照片管理直接開啟時才需要指定；從各業務記錄的照片頁籤開啟時，'
             '系統會自動沿用該記錄所屬的工程案件。')

    @api.model
    def default_get(self, fields_list):
        """從 action_* context 取來源記錄，順便把 photo_stage 帶進來。

        active_model / active_id 是 Odoo 從表單按鈕自動塞進 context 的；
        default_photo_stage 由缺失視圖的按鈕明確指定（缺失前/中/後三個頁籤
        各一顆按鈕），與既有的 One2many context 用同一個鍵。
        """
        res = super().default_get(fields_list)
        record = self._source_record()
        if record:
            res['source_model'] = record._name
            res['source_name'] = record.display_name
        return res

    def _source_record(self):
        """回傳 context 指定的來源記錄，取不到回 None。"""
        model = self.env.context.get('active_model')
        res_id = self.env.context.get('active_id')
        if not model or not res_id or model not in self.env:
            return None
        record = self.env[model].browse(res_id).exists()
        return record or None

    def action_upload(self):
        """把選到的檔案建成 supervision.photo，並掛回來源記錄。

        兩種開啟情境：
        1. 從業務記錄的照片頁籤開啟 → 有 active_model/active_id，照片掛回該記錄
        2. 從「照片管理」清單／看板／選單開啟 → 沒有來源記錄，改用使用者選的
           project_id，照片只掛工程案件（source_model 由模型端推導成「其他」）
        """
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError(_('請先選擇要上傳的照片檔案。'))

        record = self._source_record()
        if record:
            project = self._resolve_project(record)
            if not project:
                raise UserError(_('無法判斷這批照片所屬的工程案件。'))
        else:
            # 情境 2：沒有來源記錄，工程案件由使用者指定
            project = self.project_id
            if not project:
                raise UserError(_('請選擇這批照片所屬的工程案件。'))

        Photo = self.env['supervision.photo']
        source_field = None
        if record:
            source_field = Photo.sudo()._photo_source_field_map().get(record._name)
            if not source_field:
                # 與前台 _portal_save_photos 一致：照片仍然建出來、仍看得到，
                # 只是不會掛在來源記錄上。不要因此讓整批上傳失敗。
                _logger.warning(
                    '批次上傳：supervision.photo 沒有對應 %s 的來源欄位，'
                    '照片會建立但不會掛在來源記錄上', record._name)

        photos = Photo
        for att in self.attachment_ids:
            att_copy = self._detach_attachment(att)
            vals = {
                'project_id': project.id,
                'attachment_id': att_copy.id,
                # 使用者有填就用使用者的，沒填才退回檔名
                # ——與前台 _portal_save_photos 同一條規則
                'description': self.description or att_copy.name,
                'category_id': self.category_id.id or False,
                'location_description': self.location_description or '',
                'shot_at': fields.Datetime.now(),
                'latitude': self.latitude,
                'longitude': self.longitude,
            }
            if self.photo_stage:
                vals['photo_stage'] = self.photo_stage
            if source_field:
                vals[source_field] = record.id
            elif not record:
                # 沒有來源記錄時 _normalize_source_fields() 推不出 source_model
                # （_photo_source_model_code() 會回 False），留空會落在篩選的
                # 「未指定」桶裡。明給 other，語意與前台直接上傳的照片一致。
                vals['source_model'] = 'other'
            # source_model 留空，交給 _normalize_source_fields() 依來源欄位推導
            photos |= Photo.create(vals)

        target_name = record.display_name if record else project.display_name
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('上傳完成'),
                'message': _('已新增 %s 張照片到「%s」') % (len(photos), target_name),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _detach_attachment(self, attachment):
        """把附件從 wizard 脫鉤，改掛到 supervision.photo。

        ⚠️ 這一步不可省。Many2many 到 ir.attachment 的檔案，其 res_model /
        res_id 指向本 TransientModel；TransientTable 會被 Odoo 的 vacuum 定期
        清掉，屆時附件的 res_id 就指向不存在的記錄。更麻煩的是 core 對
        res_field 非空的「欄位附件」會跟著宿主記錄一起刪 —— 照片資料表收斂
        （階段 2B）的 migration 正是踩在同一個坑上，那次是靠先脫鉤才保住
        全部 65 張附件。

        這裡直接改寫同一筆附件而不是複製一份：複製會讓 filestore 多存一份
        相同內容，且 ir_attachment 總數對不上（那是我們的驗證判準之一）。
        """
        attachment.sudo().write({
            'res_model': 'supervision.photo',
            'res_field': False,
            'res_id': 0,
        })
        return attachment

    def _resolve_project(self, record):
        """推出這批照片該歸屬哪個工程案件。

        依序試：
          1. 來源記錄本身就是工程案件（工程告示牌）
          2. supervision_project_id（施工日誌用的欄位名）
          3. project_id（其餘模型）
        """
        if record._name == 'project.project':
            return record
        for fname in ('supervision_project_id', 'project_id'):
            if fname in record._fields:
                project = record[fname]
                if project:
                    return project
        return None
