# -*- coding: utf-8 -*-
"""自主檢查表（單張）→ 套印下載。

與 daily_log_sheet.py 那種「一種單據對一個 template_type」不同，這裡的樣板
有兩層來源：

    1. 檢查類型上傳的樣板（self.inspection.type.template_file）
    2. 沒上傳 → 系統預設樣板（document.template 的 self_inspection_form）

**為什麼上傳的樣板不放 document.template**：它有 SQL 約束
`UNIQUE(template_type, project_id)`，一個型別在一個專案只准一份。而檢查類型
是幾十種（鋼筋、模板、瀝青…各一份樣板），塞不進去。掛在 self.inspection.type
上天生一對一，而且檢查類型本身就有 project_id，「不同工程不同樣板」不必另外做。

所以這裡不能用 mixin 的 _export_document_template()（它綁死 document.template），
改為自己組：找樣板 → 守門 → docx_render → 附件 → 下載動作。

## 兩道守門，順序不能顛倒

    1. 欄位名稱（utils/template_tokens）——樣板寫的欄位系統填不填得出來
    2. 版面容量（utils/template_probe）——硬編樣板裝不裝得下這些資料

先驗欄位名稱：整份樣板的欄位都對不上時，再去比對列數沒有意義，而且訊息會
指錯方向（使用者會以為是項目數的問題）。
"""

import base64
import logging

from odoo import _, models
from odoo.exceptions import UserError

from ..mappings import self_inspection_form as mapping
from ..utils import docx_render, template_probe, template_tokens

_logger = logging.getLogger(__name__)

TEMPLATE_TYPE = 'self_inspection_form'


class SelfInspectionExportMixin(models.AbstractModel):
    """兩式自主檢查共用的匯出邏輯（欄位差異在 mappings 裡處理）"""

    _name = 'self.inspection.export.mixin'
    _description = '自主檢查表樣板匯出'
    _inherit = ['document.template.export.mixin']

    # ------------------------------------------------------------ 找樣板
    def _inspection_form_template(self):
        """回傳 (樣板 bytes, 檔名, 來源說明)。找不到就擋下並說清楚去哪設定。"""
        self.ensure_one()
        itype = self.inspection_type_id
        if itype and itype.template_file:
            return (base64.b64decode(itype.template_file),
                    itype.template_filename or '%s.docx' % (itype.name or ''),
                    _('檢查類型「%s」上傳的樣板') % (itype.name or ''))

        template = self.env['document.template'].get_template_for_report(
            TEMPLATE_TYPE, project_id=self.project_id.id or None)
        if not template or not template.attachment_id:
            raise UserError(_(
                '找不到可用的自主檢查表樣板。\n\n'
                '請擇一處理：\n'
                '• 到「自主檢查類型」開啟「%s」，上傳這種檢查表的 Word 樣板；或\n'
                '• 到「系統設定 ▸ 樣板設定」確認「自主檢查表（單張）」有可用的預設樣板。'
            ) % (itype.name if itype else '（未選檢查類型）'))
        return (template.attachment_id.raw,
                template.attachment_id.name or '',
                _('系統預設樣板「%s」') % template.display_name)

    # ------------------------------------------------------------ 守門
    def _check_inspection_form_fit(self, raw, source_label):
        """套印前確認這份樣板用得了。用不了就擋，並說清楚差在哪。

        版面容量那一關只有硬編索引的樣板需要：它的列數是固定的，資料多了會
        靜靜漏印、少了會直接崩潰（見 utils/template_probe 的說明）。動態表格
        樣板不限項目數，check_fit() 會直接回空清單。
        """
        self.ensure_one()
        result = template_probe.probe(raw)
        if result.error:
            raise UserError(_('%s 讀不出來：%s') % (source_label, result.error))

        template_tokens.check_or_raise(
            result.xml, mapping.TOKEN_SCHEMA, source_label)

        # 🔴 量測記錄會不會靜靜消失：檢查類型設了量測區塊、使用者也填了，
        # 但樣板裡沒有可以印的地方——套印照樣成功，那幾筆就是不見了
        # （2026-09-13 實測：少了量測那一段的樣板，3 筆量測記錄無聲蒸發）。
        if self.measure_line_ids and not result.has_measure_slot():
            raise UserError(_(
                '這張檢查紀錄有 %d 筆量測記錄，但 %s 裡沒有可以印量測區塊的地方，@'
                '套印出來會整段不見。@@'
                '請擇一處理：@'
                '• 在樣板的檢查項目表格下方加入量測區塊的欄位；或@'
                '• 如果這種檢查表本來就不需要量測記錄，'
                '請到檢查類型的「量測區塊」分頁移除設定，並清掉已填的量測列。'
            ).replace('@', chr(10))
                % (len(self.measure_line_ids), source_label))

        # 🔴 守門比對的結構必須與實際套印用的**完全同一份**（build_stages），
        # 否則會出現「守門過了但套印錯位」，而錯位在產出的檔案上看不出來。
        problems = template_probe.check_fit(
            result, mapping.stage_groups(mapping.build_stages(self, result)))
        if not problems:
            return result
        raise UserError(_(
            '這張檢查紀錄的項目與樣板對不上，先修正才能匯出。\n\n'
            '使用的樣板：%s\n\n%s\n\n'
            '可以這樣處理：\n'
            '• 把樣板換成不限項目數的「動態表格」樣板（系統預設樣板就是）；或\n'
            '• 調整樣板的列數與項目名稱，讓它與檢查項目一致。'
        ) % (source_label,
             '\n'.join('• %s' % p for p in problems)))

    # ------------------------------------------------------------ 匯出
    def render_inspection_form(self):
        """套印本張檢查紀錄，回傳 (docx bytes, 檔名)。

        抽出來是給批次下載中心用的——它一次要產幾十份再打包 zip，不需要每一份
        都建一個附件。單筆下載的 action 才建附件（要有 URL 可以給瀏覽器抓）。
        """
        self.ensure_one()
        raw, filename, source_label = self._inspection_form_template()
        if not (filename or '').lower().endswith('.docx'):
            raise UserError(_(
                '%s 不是 Word (.docx) 檔（目前是「%s」）。\n'
                '自主檢查表的樣板必須是 .docx。'
            ) % (source_label, filename or '未命名'))

        probe_result = self._check_inspection_form_fit(raw, source_label)
        content = docx_render.render(
            raw, mapping.build_context(self, probe_result))
        return content, mapping.FILENAME(self)

    def action_export_inspection_form(self):
        """把本張檢查紀錄的資料填進樣板並下載。"""
        self.ensure_one()
        content, out_name = self.render_inspection_form()
        attachment = self._create_export_attachment(out_name, content)
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }


class GeneralSelfInspection(models.Model):
    _name = 'general.self.inspection'
    _inherit = ['general.self.inspection', 'self.inspection.export.mixin']


class ReservationSelfInspection(models.Model):
    _name = 'reservation.self.inspection'
    _inherit = ['reservation.self.inspection', 'self.inspection.export.mixin']
