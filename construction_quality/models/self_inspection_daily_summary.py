# -*- coding: utf-8 -*-
"""某工程某一天「已完成的自主檢查」清單（一般式＋預約式）。

淞源 2026-11-10 需求（會議記錄 C1）：工地手機填完的檢查紀錄要帶進當天的施工日誌。
手機日誌頁、後台日誌表單、營造版施工日誌第一聯匯出都讀這裡，三個地方同一份清單。

* 本模組不依賴 construction_daily_log，所以只收「工程＋日期」，不收日誌紀錄；
  日誌那邊（construction_portal、construction_template）各自把日誌的工程與日期傳進來。
* 不寫進日誌的任何欄位：每次讀都是現查，已鎖定的日誌也帶得出來，也不會蓋掉手填的文字。
* 以呼叫者自己的權限讀（不 sudo）：讀不到的模型略過，營造方帳號只會帶到自家的檢查。
* 方法都以底線開頭：只給伺服器端程式呼叫，不開成 RPC 入口。
"""
from odoo import api, models

# 兩種自主檢查：模型 → 檢查編號欄位（一般式是 name，預約式是 inspection_no）
INSPECTION_NUMBER_FIELDS = {
    'general.self.inspection': 'name',
    'reservation.self.inspection': 'inspection_no',
}
STATE_DRAFT = 'draft'           # 草稿＝還沒檢查完，不算「當天做過的檢查」
ROW_ORDER = 'id'                # 依建立先後列
BLOCK_HEADING = '本日自主檢查：'
LINE_FORMAT = '%(no)s. %(title)s：%(result)s'
OVERFLOW_FORMAT = '…共 %s 筆（詳自主檢查表）'
TITLE_WITH_PLACE = '%s（%s）'
PLACE_SEPARATOR = ' '


class SelfInspectionDailySummary(models.AbstractModel):
    _name = 'self.inspection.daily.summary'
    _description = '自主檢查當日摘要'

    @api.model
    def _rows(self, project, day):
        """project 這個工程在 day 這一天已完成（非草稿）的自主檢查，一筆一個 dict：

        model、id、number（檢查編號）、type_name（檢查類型）、title（類型＋分項／位置）、
        result（overall_result 的值，沒有檢查項目時是 False）、result_label（顯示文字；
        沒有整體結果時用狀態名稱）、state。
        """
        if not project or not day:
            return []
        project.ensure_one()
        rows = []
        for model_name, number_field in INSPECTION_NUMBER_FIELDS.items():
            Model = self.env[model_name]
            if not Model.has_access('read'):
                continue
            result_labels = dict(Model._fields['overall_result']._description_selection(self.env))
            state_labels = dict(Model._fields['state']._description_selection(self.env))
            inspections = Model.search([
                ('project_id', '=', project.id),
                ('inspection_date', '=', day),
                ('state', '!=', STATE_DRAFT),
            ], order=ROW_ORDER)
            for inspection in inspections:
                # 樣板名稱只取名稱用 sudo：樣板可能已改綁別的工程（本人讀不到），日誌頁不能因此 403（2026-11-16）
                type_name = inspection.inspection_type_id.sudo().name or ''
                rows.append({
                    'model': model_name,
                    'id': inspection.id,
                    'number': inspection[number_field] or '',
                    'type_name': type_name,
                    'title': self._row_title(
                        type_name, inspection.sub_project_name, inspection.inspection_location),
                    'result': inspection.overall_result or False,
                    'result_label': (result_labels.get(inspection.overall_result)
                                     or state_labels.get(inspection.state, '')),
                    'state': inspection.state,
                })
        return rows

    @api.model
    def _row_title(self, type_name, sub_project_name, location):
        """檢查類型（分項工程 位置）；分項名稱與類型同名時不重複印，都沒有就只印類型。"""
        base = (type_name or '').strip() or (sub_project_name or '').strip()
        places = []
        for text in ((sub_project_name or '').strip(), (location or '').strip()):
            if text and text != base and text not in places:
                places.append(text)
        return TITLE_WITH_PLACE % (base, PLACE_SEPARATOR.join(places)) if places else base

    @api.model
    def _lines(self, rows, limit=None):
        """清單 → 「1. 類型（位置）：結果」；超過 limit 筆時只列前 limit 筆，最後一行寫總筆數。"""
        shown = rows[:limit] if limit and len(rows) > limit else rows
        lines = [LINE_FORMAT % {'no': index, 'title': row['title'], 'result': row['result_label']}
                 for index, row in enumerate(shown, start=1)]
        if len(shown) < len(rows):
            lines.append(OVERFLOW_FORMAT % len(rows))
        return lines

    @api.model
    def _block_text(self, project, day, limit=None):
        """整段文字（標題一行＋每筆一行）；當天沒有已完成的檢查回空字串。"""
        rows = self._rows(project, day)
        if not rows:
            return ''
        return '\n'.join([BLOCK_HEADING] + self._lines(rows, limit))
