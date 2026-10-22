"""收據需要的公司層級設定（計畫 §2.3）。"""

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    assoc_receipt_seal = fields.Image(string='收據印章', max_width=512, max_height=512)
    assoc_receipt_footer = fields.Text(
        string='收據頁尾', help='例如統一編號、地址、電話，或「本收據請妥善保存」。')
    assoc_receipt_sequence_id = fields.Many2one(
        'ir.sequence', string='收據號碼序號', readonly=True, copy=False,
        help='每個公會一條 no_gap 序號，首次過帳時自動建立。')
