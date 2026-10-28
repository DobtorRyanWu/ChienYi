# -*- coding: utf-8 -*-
"""檢查類型的「結果欄位」：除了合格／缺失／無此項目，有些檢查表要照表上的欄名勾（2026-10-28，新北契約檢查表）。

- standard：合格／缺失／無此項目（原本的做法，check_result 直接選）
- yes_no：是／否／不適用，只紀錄、不判定——勾什麼、沒勾都算通過（工地環境清潔及交通維持安全措施檢查表；
  表上有反著問的題目，例如「是否有塵土外溢道路」，照實勾就好）
- yes_partial_no：是／不足／否，「不足」「否」算缺失（生態保育措施自主檢查表的「執行結果」欄）；
  反向題（self.inspection.type.item.reverse_question，例：「是否有民眾陳情」）反過來：「是」「不足」算缺失、「否」正常。
  勾選照實印在是／否欄，反向只影響換算（樣板不再對調欄位）

非 standard 時，每一題實際勾的是 mark；check_result 由 mark 換算（MARK_RESULT），所以缺失精靈、
自主檢查報表、通報單合格率這些讀 check_result 的地方都不用改：紀錄型不會出現缺失，是不足否的「不足」「否」是缺失。
列印依 mark 決定印在哪一欄（construction_template/mappings/self_inspection_form.py）。
"""

from odoo import api, fields, models

STANDARD = 'standard'
RESULT_LAYOUTS = [
    (STANDARD, '合格／缺失／無此項目'),
    ('yes_no', '是／否／不適用（只紀錄、不判定）'),
    ('yes_partial_no', '是／不足／否（不足、否算缺失）'),
]
# 各樣式的勾選選項，順序＝前台按鈕順序
LAYOUT_MARKS = {
    'yes_no': [('yes', '是'), ('no', '否'), ('na', '不適用')],
    'yes_partial_no': [('yes', '是'), ('partial', '不足'), ('no', '否')],
}
MARKS = [('yes', '是'), ('partial', '不足'), ('no', '否'), ('na', '不適用')]
# 勾選 → check_result。鍵 False＝沒勾：紀錄型照樣算通過；是不足否沒勾就沒有結果（不算合格也不算缺失）
MARK_RESULT = {
    'yes_no': {'yes': 'pass', 'no': 'pass', 'na': 'na', False: 'pass'},
    'yes_partial_no': {'yes': 'pass', 'partial': 'defect', 'no': 'defect', False: False},
}
# 反向題：答「是」代表有狀況（紀錄型不判定，所以不受影響）
MARK_RESULT_REVERSED = dict(MARK_RESULT, yes_partial_no={'yes': 'defect', 'partial': 'defect', 'no': 'pass', False: False})


def result_for_mark(layout, mark, reverse=False):
    """非 standard 樣式下，勾選對應的 check_result；standard 回 None（不換算）"""
    table = MARK_RESULT_REVERSED if reverse else MARK_RESULT
    if layout not in table:
        return None
    return table[layout].get(mark or False, False)


class SelfInspectionItemMarkMixin(models.AbstractModel):
    """一般式與預約式檢查項目共用：mark 欄位，以及存檔時依類型的結果欄位換算 check_result"""
    _name = 'self.inspection.item.mark.mixin'
    _description = '自主檢查項目：照表上欄名勾選'

    mark = fields.Selection(
        MARKS, string='勾選',
        help='檢查類型的「結果欄位」不是「合格／缺失／無此項目」時，實際勾的是這一欄；'
             '檢查結果由它換算（是不足否：不足、否＝缺失；只紀錄：一律通過）')

    def _layout_for(self, inspection_id):
        inspection = self.env[self._fields['inspection_id'].comodel_name].browse(inspection_id)
        return inspection.inspection_type_id.result_layout or STANDARD

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('inspection_id'):
                reverse = bool(vals.get('type_item_id')) and \
                    self.env['self.inspection.type.item'].browse(vals['type_item_id']).reverse_question
                result = result_for_mark(self._layout_for(vals['inspection_id']), vals.get('mark'), reverse)
                if result is not None:
                    vals['check_result'] = result
        return super().create(vals_list)

    def write(self, vals):
        if 'mark' not in vals:
            return super().write(vals)
        # 不同張檢查可能是不同類型：逐筆換算
        for item in self:
            item_vals = dict(vals)
            result = result_for_mark(item.inspection_id.inspection_type_id.result_layout, vals['mark'],
                                     item.type_item_id.reverse_question)
            if result is not None:
                item_vals['check_result'] = result
            super(SelfInspectionItemMarkMixin, item).write(item_vals)
        return True
