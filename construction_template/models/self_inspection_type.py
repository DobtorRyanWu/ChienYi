# -*- coding: utf-8 -*-
"""自主檢查類型 ▸ 樣板的兩個工具：測試樣板、從樣板匯入設定。

## 測試樣板

使用者自己上傳樣板，錯了必須**當場**知道，不能等到現場填完檢查單、下載時才
發現少了幾項或整欄錯位。這個按鈕用假資料套印一次，把兩種錯誤攔在設定階段：

    項目比樣板多 → 多的會靜靜消失
    項目比樣板少 → 套印當場崩潰
    順序不一樣   → 每格都有字但全部錯位（最危險，看不出來）

## 從樣板匯入設定（反推）

硬編索引樣板的**段落名稱與項目名稱是印刷在檔案裡的**，可以反推回來，省掉
逐項手打。實測 79 份共 763 格，抽得到 758 格（99.3%）。

🔴 **抽不到「檢查標準」**——那一格在 Word 樣板裡是佔位符（`+++INS …standard+++`），
樣板本身就沒有這個內容。所以反推後標準欄一律留白，要使用者自己補一次。
省下來的是項目名稱與分段（最費工的部分），不是全部。
"""

import base64
import logging

from odoo import _, models
from odoo.exceptions import UserError

from ..utils import docx_render, template_probe, template_tokens
from ..mappings import self_inspection_form as mapping
from ..mappings.self_inspection_form import RESULT_MARKS, TIMING_MARK, TIMING_SLOTS

_logger = logging.getLogger(__name__)

TEMPLATE_TYPE = 'self_inspection_form'
TEST_WORD = '測試'          # 與舊系統一致：每個細項填「測試」字樣


def _ns(**kwargs):
    from types import SimpleNamespace
    return SimpleNamespace(**kwargs)


class SelfInspectionType(models.Model):
    _inherit = 'self.inspection.type'

    # ------------------------------------------------------------ 找樣板
    def _form_template(self):
        """回傳 (樣板 bytes, 檔名, 來源說明)。與檢查紀錄那邊同一套兩層 fallback。"""
        self.ensure_one()
        if self.template_file:
            return (base64.b64decode(self.template_file),
                    self.template_filename or '%s.docx' % (self.name or ''),
                    _('本檢查類型上傳的樣板'))
        template = self.env['document.template'].get_template_for_report(
            TEMPLATE_TYPE, project_id=self.project_id.id or None)
        if not template or not template.attachment_id:
            raise UserError(_(
                '找不到可用的自主檢查表樣板。\n'
                '請先在本頁上傳 Word 樣板，或到「系統設定 ▸ 樣板設定」'
                '確認「自主檢查表（單張）」有可用的預設樣板。'))
        return (template.attachment_id.raw,
                template.attachment_id.name or '',
                _('系統預設樣板「%s」') % template.display_name)


    # ------------------------------------------------------------ 測試樣板
    def _test_context(self, probe_result=None):
        """假資料：每個細項填「測試」，讓使用者一眼看出哪一格對到哪一項。"""
        self.ensure_one()
        stages, index = [], {}
        for item in self.default_item_ids:
            key = item.stage_id.id or 0
            if key not in index:
                index[key] = _ns(name=item.stage_id.name or '', items=[])
                stages.append(index[key])
            # 🔴 每一格都填同樣的「測試」兩個字，錯位就完全看不出來——而錯位
            # 正是測試樣板要抓的東西（實測回報：下載的檔案看起來完全正常）。
            # 所以：標準欄填**項目名稱**（可與樣板自己印的名稱肉眼對照），
            # 情形欄填**段-項編號**（一眼看出這一格對到第幾段第幾項）。
            index[key].items.append(_ns(
                name=item.name or '',
                standard=item.check_standard or ('【%s】' % (item.name or '')),
                situation='%s %d-%d' % (TEST_WORD, len(stages),
                                        len(index[key].items) + 1),
                result=RESULT_MARKS['pass'],
                remark=TEST_WORD,
            ))

        measures = []
        for block in self.measure_ids:
            measures.append(_ns(title=block.name or '', lines=[
                _ns(no=n + 1, text=(block.template or '').replace('_', TEST_WORD),
                    result='pass', passMark=TIMING_MARK, failMark='')
                for n in range(max(block.row_count or 1, 1))
            ]))

        # 硬編樣板的量測列印在檢查項目表格裡，要併進 stages（與實際套印一致）
        if probe_result is not None and probe_result.is_indexed:
            from ..mappings.self_inspection_form import _merge_measures_into_stages
            stages = _merge_measures_into_stages(stages, measures, probe_result)

        codes = set(self.timing_ids.mapped('legacy_code')) - {False, ''}
        return {
            'contractor': TEST_WORD,
            'projectName': self.project_id.name or TEST_WORD,
            'inspection': _ns(
                no=TEST_WORD,
                name=self.name or TEST_WORD,
                subContractor=TEST_WORD,
                position=TEST_WORD,
                inspectedAt=TEST_WORD,
                inspectionTiming=_ns(**{
                    slot: (TIMING_MARK if code in codes else '')
                    for slot, code in TIMING_SLOTS.items()}),
                stages=stages,
                measures=measures,
                images=[],
                imagePages=[],
                evenImagesIndex=[],
            ),
        }

    def action_test_inspection_template(self):
        """用假資料套印一次，驗證樣板與預設檢查項目對不對得上。"""
        self.ensure_one()
        if not self.default_item_ids:
            raise UserError(_(
                '這個檢查類型還沒有預設檢查項目，測不出樣板對不對。\n'
                '請先到「預設檢查項目」分頁建立項目，或用「從樣板匯入設定」'
                '直接從上傳的樣板反推。'))

        raw, filename, source_label = self._form_template()
        if not (filename or '').lower().endswith('.docx'):
            raise UserError(_('%s 不是 Word (.docx) 檔（目前是「%s」）。')
                            % (source_label, filename or '未命名'))

        result = template_probe.probe(raw)
        if result.error:
            raise UserError(_('%s 讀不出來：%s') % (source_label, result.error))

        template_tokens.check_or_raise(
            result.xml, mapping.TOKEN_SCHEMA, source_label)
        problems = template_probe.check_fit(
            result, template_probe.groups_from_type(self, result))
        if problems:
            raise UserError(_(
                '樣板與預設檢查項目對不上：\n\n%s\n\n使用的樣板：%s\n\n'
                '可以這樣處理：\n'
                '• 改用不限項目數的「動態表格」樣板（系統預設樣板就是）；或\n'
                '• 調整預設檢查項目，讓它與樣板的列數、順序、名稱一致。'
            ) % ('\n'.join('• %s' % p for p in problems), source_label))

        content = docx_render.render(raw, self._test_context(result))
        attachment = self.env['ir.attachment'].sudo().create({
            'name': '樣板測試_%s.docx' % (self.name or self.id),
            'raw': content,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument'
                        '.wordprocessingml.document',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    # ------------------------------------------------------ 從樣板匯入設定
    def action_import_from_template(self):
        """從上傳的 Word 樣板反推查驗段落、預設檢查項目、量測區塊。"""
        self.ensure_one()
        if not self.template_file:
            raise UserError(_(
                '請先在本頁上傳 Word 樣板，才能從它反推設定。'))
        # 🔴 既有資料的檢查要**連量測區塊一起看**。只看 default_item_ids 的話：
        # 反推一次建了量測區塊 →（照訊息）清掉預設檢查項目 → 再反推一次 →
        # 這一關放行 → 重建同名區塊 → 撞 UNIQUE 約束，使用者看到的是
        # 「同一檢查類型內的量測區塊標題不可重複！」這種完全不知道要幹嘛的訊息
        # （2026-09-14 使用者實測打出來的）。
        # 只擋「預設檢查項目」。量測區塊刻意不擋——它一旦被檢查紀錄用過就
        # **刪不掉**（ondelete='restrict'），要求先清空等於要求使用者先去刪掉
        # 歷史量測資料，那是死結（2026-09-14 使用者實測撞上：
        # 「此量測區塊已被 3 筆『一般式自主檢查量測列』使用」）。
        # 改為在 _apply_probe 裡「同名沿用、不同名才新增」。
        if self.default_item_ids:
            raise UserError(_(
                '「預設檢查項目」已經有 %d 筆資料了。\n'
                '為了不覆蓋你既有的設定，請先清空這一頁再匯入。\n\n'
                '（「量測區塊」不必清——同名的會自動沿用，'
                '既有的句型與設定不會被蓋掉。）'
            ) % len(self.default_item_ids))

        filename = (self.template_filename or '').lower()
        if filename and not filename.endswith('.docx'):
            raise UserError(_(
                '樣板必須是 Word (.docx) 檔，目前上傳的是「%s」。\n\n'
                'Excel 格式的檢查表目前不支援反推，也不能用來套印。'
            ) % self.template_filename)

        raw = base64.b64decode(self.template_file)
        result = template_probe.probe(raw)
        if result.error:
            raise UserError(_('樣板讀不出來：%s') % result.error)
        if not result.is_indexed:
            # 兩種都反推不出來，但原因完全不同，訊息不能共用一句
            # （「沒有佔位符的空白紙本」被說成「動態表格格式」會讓人更困惑）。
            if result.kind == template_probe.KIND_DYNAMIC:
                raise UserError(_(
                    '這份樣板是「動態表格」格式，它本身不含檢查項目的名稱'
                    '（項目是套印時才填進去的），所以沒有東西可以反推。\n\n'
                    '動態表格樣板不限項目數，直接在「預設檢查項目」分頁'
                    '建立項目即可——不需要先反推。'))
            raise UserError(_(
                '這份樣板裡沒有任何欄位標記，看起來是一份「空白紙本」，'
                '沒有東西可以反推。\n\n'
                '反推只對「固定列數」的樣板有用——那種樣板會把'
                '檢查項目的名稱印在表格裡，同時用 +++INS …+++ 標出要填資料的格子。\n\n'
                '如果這是你要用的版面，請先在 Word 裡替每一格加上欄位標記；'
                '或到「系統設定 ▸ 樣板設定」下載「自主檢查表（單張）」的空白範本當起點。'))

        checklist = result.checklist_rows()
        if not checklist:
            raise UserError(_(
                '在這份樣板裡找不到檢查項目的欄位，無法反推。'))

        created = self._apply_probe(result, checklist)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('已從樣板匯入設定'),
                'message': _(
                    '建立了 %(stages)d 個查驗段落、%(items)d 個檢查項目'
                    '%(measures)s。\n\n'
                    '⚠️ 「檢查標準」欄一律是空的——那一格在 Word 樣板裡是'
                    '待填的空格，樣板本身沒有這個內容，請逐項補上。'
                ) % created,
                'type': 'success',
                'sticky': True,
                # 不 reload 的話新建的段落／項目不會出現在畫面上，使用者得自己
                # 按 F5（實測回報）。display_notification 的 next 不經過
                # clean_action，所以只放最單純的 reload，不要塞 act_window
                # （那種要自帶 views，否則前端 views.map 會 TypeError）。
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def _apply_probe(self, result, checklist):
        """把反推結果寫進段落／項目／量測區塊。"""
        self.ensure_one()
        Stage = self.env['self.inspection.type.stage']
        Item = self.env['self.inspection.type.item']
        Measure = self.env['self.inspection.type.measure']

        # 段落：樣板沒印名稱時給一個看得出是第幾段的預設值，不要留空
        stage_names = result.stage_names()
        stage_by_index = {}
        existing = {s.name: s for s in self.stage_ids}
        for order, index in enumerate(sorted({r.stage_index for r in result.rows})):
            name = stage_names.get(index) or _('第 %d 段') % (index + 1)
            stage = existing.get(name)
            if not stage:
                stage = Stage.create({
                    'type_id': self.id, 'name': name,
                    'sequence': (order + 1) * 10,
                })
                existing[name] = stage
            stage_by_index[index] = stage

        # 量測區塊：連續、單一欄位、共用標題的列（見 template_probe 說明）
        measure_stage_indexes = set()
        n_measures = 0
        n_reused = 0
        by_name = {b.name: b for b in self.measure_ids}
        for title, row_count, stage_index in result.measure_blocks():
            if not title:
                continue           # 連標題都抽不到就不要猜，留給使用者自己建
            if title in by_name:
                # 🔴 沿用既有區塊，**一個欄位都不動**。句型尤其不能覆蓋——
                # 反推只給得出佔位句型（Word 樣板裡那一格是空的），而既有區塊
                # 的句型很可能已經被使用者填成正確的了，蓋掉就毀了。
                measure_stage_indexes.add(stage_index)
                n_reused += 1
                continue
            Measure.create({
                'type_id': self.id,
                'name': title,
                # 句型在 Word 樣板裡是**空格子**（只有 xlsx 監造版才印了完整句型
                # 「1.丈量______位置，長____cm…」），所以反推抽不到，只能給一個
                # 一眼看得出「還沒填」的預設值。空格必須是**半形**底線連續兩個
                # 以上，否則撞 _check_template_has_blank。
                'template': _('___（請改成紙本印的句型）'),
                'row_count': row_count,
                'sequence': (n_measures + 1) * 10,
            })
            measure_stage_indexes.add(stage_index)
            n_measures += 1

        # 檢查項目：跳過已經被認成量測區塊的那些列
        measure_rows = set()
        for row in result.rows:
            if row.is_measure_like and row.stage_index in measure_stage_indexes:
                measure_rows.add((row.stage_index, row.item_index))

        # 🔴 sequence 要**跨段落全域遞增**，不能每段從 10 重新開始。
        # 「預設檢查項目」那個清單有 <field name="sequence" widget="handle"/>，
        # handle widget 會讓前端**只依 sequence 排序**、忽略 model _order 裡的
        # stage_sequence。每段各自從 10 起算的話，畫面上會變成
        # 施工前(10)→施工中(10)→施工前(20)→施工中(20)… 整個交錯（實測回報）。
        # 既有的匯入資料本來就是全域遞增（10,20,…,120），這裡照同一套。
        n_items = 0
        for row in sorted(checklist, key=lambda r: (r.stage_index, r.item_index)):
            if (row.stage_index, row.item_index) in measure_rows:
                continue
            n_items += 1
            Item.create({
                'type_id': self.id,
                'stage_id': stage_by_index[row.stage_index].id,
                'name': row.item_name or _('第 %d 項') % (row.item_index + 1),
                # 🔴 刻意留空：Word 樣板的標準欄是佔位符，沒有內容可抽。
                'check_standard': False,
                'sequence': n_items * 10,
            })

        parts = []
        if n_measures:
            parts.append(_('%d 個量測區塊') % n_measures)
        if n_reused:
            parts.append(_('沿用既有的 %d 個量測區塊') % n_reused)
        return {
            'stages': len(stage_by_index),
            'items': n_items,
            'measures': ('、' + '、'.join(parts)) if parts else '',
        }
