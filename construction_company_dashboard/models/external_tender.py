# -*- coding: utf-8 -*-
"""外部標案（淞源 2026-11-10 會議 C6）：別人的標案，給標案地圖的「外部標案」圖層用。

老闆想要的是「地圖上看得到附近有哪些標案」。政府電子採購網與公共工程委員會的開放資料沒有任何一份帶座標
（2026-11-13 查過），所以做成：清單用匯入的（Excel，清單畫面的「匯入紀錄」，有範本），位置在標案地圖上點，
或用「履約地點」文字自動定位（見 project_geo.py）。

* 這是公司自己整理的參考資料，不是工程案件：不進工程的任何統計。
* 誰看得到：後台人員（唯讀）；監造管理員與代操作員可以建、改、匯入。受限帳號（營造方、角色帳號、控台讀取）
  不在讀取白名單（rule_scope 預設拒絕），地圖上不會有這個圖層。
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

STAGE_OPEN = 'open'
STAGE_SELECTION = [
    (STAGE_OPEN, '招標中'),
    ('awarded', '已決標'),
    ('watching', '觀察中'),
    ('closed', '不追蹤'),
]
MAP_STAGES = (STAGE_OPEN, 'awarded', 'watching')        # 會畫在地圖上的階段（「不追蹤」不畫）
GEO_SOURCE_MANUAL = 'manual'
GEO_SOURCE_GEOCODED = 'geocoded'
GEO_SOURCE_SELECTION = [
    (GEO_SOURCE_MANUAL, '地圖上標定'),
    (GEO_SOURCE_GEOCODED, '地點文字自動定位（請確認）'),
]
MAX_LATITUDE = 90
MAX_LONGITUDE = 180
IMPORT_TEMPLATE = '/construction_company_dashboard/static/xls/external_tender_template.xlsx'


class ConstructionExternalTender(models.Model):
    _name = 'construction.external.tender'
    _description = '外部標案'
    _order = 'deadline_date desc, id desc'

    active = fields.Boolean(string='啟用', default=True)
    name = fields.Char(string='標案名稱', required=True, index='trigram')
    agency = fields.Char(string='機關')
    tender_no = fields.Char(string='標案案號')
    stage = fields.Selection(STAGE_SELECTION, string='階段', required=True, default=STAGE_OPEN, index=True)
    currency_id = fields.Many2one(
        'res.currency', string='幣別', required=True, default=lambda self: self.env.company.currency_id)
    budget_amount = fields.Monetary(string='預算金額', currency_field='currency_id')
    announce_date = fields.Date(string='公告日')
    deadline_date = fields.Date(string='截止投標')
    location = fields.Char(string='履約地點', help='地址或地點描述；可以拿來自動定位，也可以直接在標案地圖上點位置')
    latitude = fields.Float(string='緯度', digits=(10, 7))
    longitude = fields.Float(string='經度', digits=(10, 7))
    geo_source = fields.Selection(GEO_SOURCE_SELECTION, string='座標來源', readonly=True)
    url = fields.Char(string='公告網址')
    note = fields.Text(string='備註')
    company_id = fields.Many2one(
        'res.company', string='所屬公司', required=True, index=True, default=lambda self: self.env.company)

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        """座標範圍（0 視為沒填）：和工程案件同一個規則，避免經緯度填反。"""
        for tender in self:
            if tender.latitude and not -MAX_LATITUDE <= tender.latitude <= MAX_LATITUDE:
                raise ValidationError('緯度要在 -90 到 90 之間（是不是和經度填反了？）')
            if tender.longitude and not -MAX_LONGITUDE <= tender.longitude <= MAX_LONGITUDE:
                raise ValidationError('經度要在 -180 到 180 之間')

    @api.model
    def get_import_templates(self):
        """清單畫面「匯入紀錄」上的範本下載。"""
        return [{'label': '外部標案匯入範本（Excel）', 'template': IMPORT_TEMPLATE}]
