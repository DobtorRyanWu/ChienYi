# -*- coding: utf-8 -*-
import re
import io
import json
import base64
import logging
from collections import defaultdict, Counter
from decimal import Decimal, ROUND_HALF_UP

from odoo import models, fields, api, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def round_twd(value):
    """政府採購四捨五入（小數點後 2 位），避免 Python 銀行家捨入產生 0.01 誤差"""
    return float(Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class ContractChangeFileImportWizard(models.TransientModel):
    """
    契約變更檔案匯入精靈

    必須在 contract.change.wizard（已選擇工程案件、工項已載入）內開啟。
    解析 ETenderSheet XML（代表「變更後」的完整契約）後，
    與現有工項做全量比對，填入 wizard_line_ids。

    匹配方式：層級比對 → item_no+名稱 → 全域唯一名稱，三層策略。
    """
    _name = 'contract.change.file.import.wizard'
    _description = '契約變更檔案匯入精靈'

    wizard_id = fields.Many2one(
        'contract.change.wizard',
        string='變更精靈',
        required=True,
        readonly=True)

    import_file = fields.Binary(
        string='上傳工程變更明細表 XLSX',
        required=True,
        attachment=False)

    import_filename = fields.Char(string='檔案名稱')

    file_type = fields.Selection([
        ('xlsx', 'XLSX'),
    ], string='檔案類型', compute='_compute_file_type', store=True)

    state = fields.Selection([
        ('upload', '上傳檔案'),
        ('parsed', '已解析，待確認'),
    ], string='狀態', default='upload', readonly=True)

    # 解析預覽（唯讀）
    preview_add_count = fields.Integer(string='新增工項', readonly=True)
    preview_modify_count = fields.Integer(string='修改工項', readonly=True)
    preview_zero_out_count = fields.Integer(string='歸零工項', readonly=True)
    preview_tax_misc_count = fields.Integer(string='稅什費更新', readonly=True)
    preview_tax_misc_rate_before = fields.Float(
        string='解析前稅什費比例 (%)', digits=(12, 4), readonly=True,
        help='套用前，工程案件中稅什費工項的現行比例')
    preview_rate_detail = fields.Text(
        string='比例項明細', readonly=True,
        help='本次解析到的所有比例項（以「比例 × 基數」計算金額者），逐項列出')

    preview_tax_misc_rate_after = fields.Float(
        string='解析後稅什費比例 (%)', digits=(12, 4), readonly=True,
        help='依 XLSX 解析後的預計稅什費比例')
    preview_unmatch_count = fields.Integer(string='無法比對', readonly=True)
    preview_unmatch_details = fields.Text(string='無法比對明細', readonly=True)
    # 全表對帳：原數量/原單價與系統現值不符的工項數
    preview_recon_count = fields.Integer(string='對帳異常', readonly=True)

    # 手動配對（無法自動比對的工項）— kind='unmatch'
    unmatch_line_ids = fields.One2many(
        'contract.change.file.import.mapping',
        'wizard_import_id',
        string='待手動配對工項',
        domain=[('kind', '=', 'unmatch')])
    # 對帳異常（配到但原數量/原單價與系統現值不符）— kind='recon'
    recon_line_ids = fields.One2many(
        'contract.change.file.import.mapping',
        'wizard_import_id',
        string='對帳異常工項',
        domain=[('kind', '=', 'recon')])

    @api.depends('import_filename')
    def _compute_file_type(self):
        for rec in self:
            fname = (rec.import_filename or '').lower()
            rec.file_type = 'xlsx' if fname.endswith('.xlsx') else False

    def _get_project(self):
        """取得關聯工程案件"""
        project = self.wizard_id.project_id
        if not project:
            raise UserError('變更精靈尚未選擇工程案件，請先完成工程案件選擇再匯入檔案')
        return project

    # ── 第一步：解析預覽 ─────────────────────────────────────────────────────

    def action_parse(self):
        """解析檔案並顯示統計，不修改任何資料"""
        self.ensure_one()
        if not self.import_file:
            raise UserError('請先上傳檔案')
        if not self.file_type:
            raise UserError('請上傳工程變更明細表 XLSX（.xlsx）格式的檔案')

        parsed, _xlsx_sec = self._parse_file()
        counts = self._count_changes(parsed)

        unmatch_items = [i for i in parsed if i.get('change_type') == 'unmatch']
        recon_items = [i for i in parsed if i.get('change_type') == 'recon']
        unmatch_details = [
            f"  • 項次 [{i.get('item_no', '?')}] {i.get('item_name', '')}"
            for i in unmatch_items
        ]

        # 清除舊的待處理記錄（配不到 + 對帳異常），建立新的
        (self.unmatch_line_ids | self.recon_line_ids).unlink()
        mapping_vals = []
        for i in unmatch_items:
            mapping_vals.append((0, 0, {
                'kind': 'unmatch',
                'item_no': i.get('item_no', ''),
                'item_name': i.get('item_name', ''),
                'change_type': {'delete': 'zero_out', 'tax_misc': 'modify'}.get(
                    i.get('change_type_hint') or 'modify',
                    i.get('change_type_hint') or 'modify'),
                'orig_qty': i.get('orig_qty') or 0.0,
                'new_qty': i.get('new_qty') or 0.0,
                'orig_price': i.get('orig_price') or 0.0,
                'new_price': i.get('new_price') or 0.0,
                'new_amount': i.get('new_amount') or 0.0,
                'notes': i.get('notes', '') or '',
            }))
        # 對帳異常：配到但原數量/原單價≠系統現值。預填處置：
        #   偵測為未變更 → 預設「不變更」（系統值為真）；偵測為 modify/zero → 預設照常套用
        recon_vals = []
        for i in recon_items:
            dtype = i.get('detected_type') or 'modify'
            default_ct = 'none' if dtype == 'unchanged' else dtype
            task = i.get('task')
            recon_vals.append((0, 0, {
                'kind': 'recon',
                'item_no': i.get('item_no', ''),
                'item_name': i.get('item_name', ''),
                'detected_type': dtype,
                'change_type': default_ct,
                'task_id': task.id if task else False,
                'orig_qty': i.get('orig_qty') or 0.0,
                'new_qty': i.get('new_qty') or 0.0,
                'orig_price': i.get('orig_price') or 0.0,
                'new_price': i.get('new_price') or 0.0,
                'system_qty': i.get('system_qty') or 0.0,
                'system_price': i.get('system_price') or 0.0,
                'new_amount': i.get('new_amount') or 0.0,
                'notes': i.get('notes', '') or '',
            }))

        # 比例項預覽：逐項列出（不是只取第一個稅什費 —— 一個案子可以有
        # 自主檢查費、工安費、稅什費等多個比例項，各有各的比例與基數）
        tax_misc_rate_before = 0.0
        tax_misc_rate_after = 0.0
        rate_lines = []
        for item in parsed:
            if item.get('change_type') != 'tax_misc':
                continue
            task = item.get('task')
            before = (task.tax_misc_rate or 0.0) if task else 0.0
            m = re.search(r'([\d.]+)\s*%', item.get('notes', '') or '')
            after = float(m.group(1)) if m else before
            if not rate_lines:          # 第一筆同時填舊的單一欄位（相容既有引用）
                tax_misc_rate_before, tax_misc_rate_after = before, after
            base_desc = '同層全部前置工項'
            if task and task.rate_base_task_ids:
                base_desc = '、'.join(
                    b.display_item_no or b.item_no or b.name
                    for b in task.rate_base_task_ids)
            rate_lines.append(
                '%-6s %-20s 比例 %s%% → %s%%   金額 %s → %s   基數：%s'
                % (item.get('item_no') or '',
                   (item.get('item_name') or '')[:20],
                   ('%.4f' % before), ('%.4f' % after),
                   '{:,.0f}'.format(task.planned_amount or 0.0) if task else '?',
                   '{:,.0f}'.format(float(item.get('new_amount') or 0.0)),
                   base_desc))

        self.write({
            'state': 'parsed',
            'preview_add_count': counts['add'],
            'preview_modify_count': counts['modify'],
            'preview_zero_out_count': counts['zero_out'],
            'preview_tax_misc_count': counts['tax_misc'],
            'preview_tax_misc_rate_before': tax_misc_rate_before,
            'preview_tax_misc_rate_after': tax_misc_rate_after,
            'preview_rate_detail': '\n'.join(rate_lines) if rate_lines else False,
            'preview_unmatch_count': counts['unmatch'],
            'preview_unmatch_details': '\n'.join(unmatch_details) if unmatch_details else False,
            'preview_recon_count': len(recon_items),
            'unmatch_line_ids': mapping_vals,
            'recon_line_ids': recon_vals,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── 第二步：填入現有 wizard ───────────────────────────────────────────────

    def action_apply_to_wizard(self):
        """解析檔案，直接將變更類型填入已載入工項的 contract.change.wizard"""
        self.ensure_one()
        if not self.import_file:
            raise UserError('請先上傳檔案')
        if self.state != 'parsed':
            raise UserError('請先點擊「解析」按鈕確認統計')

        # 檢查手動配對是否都已處理（change_type='add' 不需要選 task）
        unmapped = self.unmatch_line_ids.filtered(
            lambda l: not l.task_id and l.change_type != 'add')
        if unmapped:
            names = '、'.join(
                f'項次[{l.item_no}] {l.item_name}' for l in unmapped)
            raise UserError(f'以下工項尚未選擇對應的系統工項，請完成手動配對後再套用：\n{names}')

        # 對帳異常擋閘：處置為修改/歸零者必須有對應工項；新增者必須有所屬分類
        recon_no_task = self.recon_line_ids.filtered(
            lambda l: l.change_type in ('modify', 'zero_out') and not l.task_id)
        if recon_no_task:
            names = '、'.join(l.item_name for l in recon_no_task)
            raise UserError(f'以下對帳異常工項處置為修改/歸零，請選擇對應系統工項：\n{names}')
        recon_no_parent = self.recon_line_ids.filtered(
            lambda l: l.change_type == 'add' and not l.parent_task_id)
        if recon_no_parent:
            names = '、'.join(l.item_name for l in recon_no_parent)
            raise UserError(f'以下對帳異常工項處置為新增，請選擇所屬分類：\n{names}')

        parsed, xlsx_sec = self._parse_file()

        # 將手動配對結果注入 parsed 清單
        for mapping_line in self.unmatch_line_ids:
            if mapping_line.change_type == 'add' and not mapping_line.task_id:
                # 使用者確認為新增工項（不需要對應現有 task）
                parsed.append({
                    'change_type': 'add',
                    'item_no': mapping_line.item_no,
                    'item_name': mapping_line.item_name,
                    'unit': '',
                    'task': None,
                    'parent_task': mapping_line.parent_task_id or None,
                    'orig_qty': None,
                    'new_qty': mapping_line.new_qty,
                    'new_price': mapping_line.new_price,
                    'new_amount': mapping_line.new_amount,
                    'notes': mapping_line.notes or '',
                })
            elif mapping_line.task_id:
                ct = 'zero_out' if mapping_line.change_type == 'delete' else mapping_line.change_type
                parsed.append({
                    'change_type': ct,
                    'item_no': mapping_line.item_no,
                    'item_name': mapping_line.item_name,
                    'unit': mapping_line.task_id.unit or '',
                    'task': mapping_line.task_id,
                    'parent_task': None,
                    'orig_qty': mapping_line.orig_qty,
                    'new_qty': mapping_line.new_qty,
                    'orig_price': mapping_line.orig_price,
                    'new_price': mapping_line.new_price,
                    'new_amount': mapping_line.new_amount,
                    'notes': mapping_line.notes or '',
                })

        # 將「對帳異常」的使用者處置注入 parsed。
        # 原則：系統現值為真，只套「變更後數量/單價」，絕不以文件原數量/原單價覆寫系統。
        for rl in self.recon_line_ids:
            if rl.change_type == 'none':
                continue  # 確認系統值正確、本次不動此項
            if rl.change_type == 'add':
                parsed.append({
                    'change_type': 'add',
                    'item_no': rl.item_no,
                    'item_name': rl.item_name,
                    'unit': '',
                    'task': None,
                    'parent_task': rl.parent_task_id or None,
                    'orig_qty': None,
                    'new_qty': rl.new_qty,
                    'new_price': rl.new_price,
                    'new_amount': rl.new_amount,
                    'notes': rl.notes or '',
                })
            elif rl.task_id:
                ct = 'zero_out' if rl.change_type in ('delete', 'zero_out') else 'modify'
                parsed.append({
                    'change_type': ct,
                    'item_no': rl.item_no,
                    'item_name': rl.item_name,
                    'unit': rl.task_id.unit or '',
                    'task': rl.task_id,
                    'parent_task': None,
                    'orig_qty': rl.orig_qty,
                    'new_qty': rl.new_qty,
                    'orig_price': rl.orig_price,
                    'new_price': rl.new_price,
                    'new_amount': rl.new_amount,
                    'notes': rl.notes or '',
                })

        self._apply_to_existing_wizard(parsed)

        # ── F1：稅什費自動計算 + 金額核對報告 ────────────────────────────────
        wizard = self.wizard_id
        line_by_task_id = {l.task_id.id: l for l in wizard.wizard_line_ids if l.task_id}

        # 新增工項依父分類分組，讓分類金額模擬時能加入直屬新增工項
        add_lines_by_parent_id = {}
        for _wl in wizard.wizard_line_ids:
            if _wl.change_type == 'add' and _wl.parent_task_id:
                add_lines_by_parent_id.setdefault(_wl.parent_task_id.id, []).append(_wl)

        # 新增彙總群組：其子項以 parent_line_id 指向群組列（群組列本身無量價）
        add_children_by_parent_line = {}
        for _wl in wizard.wizard_line_ids:
            if _wl.change_type == 'add' and _wl.parent_line_id:
                add_children_by_parent_line.setdefault(
                    _wl.parent_line_id.id, []).append(_wl)

        def wizard_line_amount(wl):
            """單一新增 wizard 行的金額。
            新增彙總群組（is_new_group）本身無量價，金額＝其底下子項加總（支援巢狀群組）；
            一般新增工項＝new_qty × new_unit_price。"""
            if wl.is_new_group:
                return round_twd(sum(
                    wizard_line_amount(c)
                    for c in add_children_by_parent_line.get(wl.id, [])))
            return round_twd((wl.new_qty or 0) * (wl.new_unit_price or 0))

        def simulate_task_amount(task):
            """計算 task 在本次變更後的預估金額（直接子節點加總，避免越層彙總）"""
            if task.is_summary_item and task.child_ids:
                # 分類項：加總直接子節點
                total = sum(simulate_task_amount(c) for c in task.child_ids)
                # 加上直接屬於此分類的新增工項（含新增彙總群組，其金額由子項加總）
                for add_wl in add_lines_by_parent_id.get(task.id, []):
                    total += wizard_line_amount(add_wl)
                return round_twd(total)
            wl = line_by_task_id.get(task.id)
            if wl:
                if wl.change_type in ('modify', 'add'):
                    return round_twd((wl.new_qty or 0) * (wl.new_unit_price or 0))
                elif wl.change_type in ('zero_out', 'delete'):
                    return 0.0
                # change_type=False（未變更）：沿用原始金額
                return task.planned_amount or 0.0
            return task.planned_amount or 0.0

        # F1-C：稅什費金額自動計算（以變更後章節模擬金額為基礎）
        for item in parsed:
            if item.get('change_type') != 'tax_misc':
                continue
            task = item.get('task')
            if not task or not task.parent_id:
                continue

            rate = None
            m = re.search(r'([\d.]+)\s*%', item.get('notes', '') or '')
            if m:
                rate = float(m.group(1)) / 100.0
            elif hasattr(task, 'tax_misc_rate') and task.tax_misc_rate:
                rate = task.tax_misc_rate / 100.0

            if not rate:
                continue

            siblings = task.parent_id.child_ids.sorted('sequence')
            preceding_sum = sum(
                simulate_task_amount(sib)
                for sib in siblings
                if sib.sequence < task.sequence
            )
            new_tax_amount = round_twd(preceding_sum * rate)

            wl = line_by_task_id.get(task.id)
            if wl:
                # 比例項的金額走「新金額」，不塞進「新單價」。
                # 舊寫法 new_tax_amount / qty 會產生一個兩千多萬的假單價，
                # 套用時被寫回 task.unit_price（估驗明細會抄走），
                # 且讓變更設計詳細表印成「原單價 0、追加 = 全額」。
                # 本段是稅什費的最後一手，會覆蓋 _apply_to_existing_wizard
                # 的設定，所以這裡也必須把 new_unit_price 壓成 0。
                wl.write({
                    'change_type': 'modify',
                    'new_qty': task.planned_qty or 1.0,
                    'new_unit_price': 0.0,
                    'new_amount': new_tax_amount,
                })

        # 重建 line_by_task_id，捕捉 F1-C 對稅什費 wizard_line 的更新
        line_by_task_id = {l.task_id.id: l for l in wizard.wizard_line_ids if l.task_id}

        # flush 確保所有 write() 都落地 DB；invalidate_all 清全部 ORM cache
        self.env.flush_all()
        self.env.invalidate_all()
        # 強制重算所有精靈行金額，確保分類行的 new_amount 在 UI 正確顯示
        wizard.wizard_line_ids._compute_amounts()
        # 診斷：確認 compute 後的值
        for line in wizard.wizard_line_ids:
            if line.task_id and line.task_id.child_ids and not line.task_id.parent_id:
                _logger.info('[after_compute] %s new_amount=%s', line.task_id.name, line.new_amount)
        self.env.flush_all()

        # F1-B：金額核對報告（僅在有 XLSX 章節合計資料時執行）
        _logger.info('[F1-B] xlsx_sec keys: %s', list(xlsx_sec.keys()) if xlsx_sec else 'EMPTY')
        if xlsx_sec:
            warn_rows = []
            ok_count = 0
            for task_id_key, sec_info in xlsx_sec.items():
                sec_task = self.env['project.task'].browse(int(task_id_key))
                if not sec_task.exists():
                    continue
                xlsx_total = sec_info.get('new_amount') or 0.0
                simulated = simulate_task_amount(sec_task)
                diff = round_twd(simulated - xlsx_total)
                _logger.info('[F1-B] %s: simulated=%.2f xlsx=%.2f diff=%.2f',
                             sec_info.get('name', '?'), simulated, xlsx_total, diff)
                if abs(diff) > 0.01:
                    warn_rows.append(
                        f"⚠ {sec_info['name']}：系統 {simulated:,.2f} / XLSX {xlsx_total:,.2f} / 差異 {diff:+,.2f}")
                else:
                    ok_count += 1

            _logger.info('[F1-B] warn_rows=%d ok_count=%d wizard.id=%s', len(warn_rows), ok_count, wizard.id)
            if warn_rows:
                summary_line = f"（其餘 {ok_count} 個章節金額吻合）" if ok_count else ''
                report_text = '\n'.join(warn_rows)
                if summary_line:
                    report_text += '\n' + summary_line
                wizard.write({
                    'reconciliation_report': report_text,
                    'show_reconciliation_report': True,
                })
                _logger.info('[F1-B] wrote reconciliation_report to wizard.id=%s, show=%s, report_len=%d',
                             wizard.id, wizard.show_reconciliation_report, len(wizard.reconciliation_report or ''))

        # 關閉 dialog，讓父頁面的 contract.change.wizard form 自動 reload（含新寫入的 reconciliation_report）
        _logger.info('[apply] closing dialog, wizard_id=%s, reconciliation_report=%s',
                     self.wizard_id.id, bool(wizard.reconciliation_report))
        return {'type': 'ir.actions.act_window_close'}

    # ── 解析分派 ────────────────────────────────────────────────────────────

    def _parse_file(self):
        """解析工程變更明細表 XLSX，回傳 (parsed_list, xlsx_section_amounts)"""
        data = base64.b64decode(self.import_file)
        if self.file_type != 'xlsx':
            raise UserError('請上傳工程變更明細表 XLSX（.xlsx）格式的檔案')
        project = self._get_project()
        if not project.tender_xml_data:
            raise UserError(
                '此工程尚未儲存原始標單 XML，無法匯入 XLSX。\n'
                '請先以 ETenderSheet XML 重新匯入原始標單（系統將自動儲存 XML，下次即可直接上傳 XLSX）。'
            )
        original_xml = base64.b64decode(project.tender_xml_data)
        return self._parse_xlsx_via_xml(data, original_xml)

    def _count_changes(self, parsed):
        counts = {'add': 0, 'modify': 0, 'zero_out': 0, 'tax_misc': 0, 'unmatch': 0}
        for item in parsed:
            ct = item.get('change_type')
            if ct in counts:
                counts[ct] += 1
        return counts

    # ── 文字正規化 ───────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_name(name):
        """
        正規化名稱以提升比對成功率：
        - 全形標點 → 半形
        - 去除首尾空白
        """
        if not name:
            return ''
        name = name.strip()
        # 全形逗號/頓號 → 半形逗號
        name = name.replace('，', ',').replace('、', ',')
        # 全形括號 → 半形
        name = name.replace('（', '(').replace('）', ')')
        # 全形空格 → 半形
        name = name.replace('　', ' ')
        # 壓縮連續空白
        import re as _re
        name = _re.sub(r'\s+', ' ', name)
        return name

    @staticmethod
    def _names_compatible(name_a, name_b):
        """名稱相似度驗證：防止位置號碼誤配到不同工項。
        兩端先正規化（半/全形統一，同 _normalize_name 邏輯），
        再判斷：完全匹配 OR 包含關係 OR 字元集重疊率 > 35%。
        任一端為空時不做限制（回傳 True）。
        """
        def _norm(s):
            s = (s or '').strip()
            for f, h in [('，', ','), ('、', ','), ('（', '('), ('）', ')'), ('　', ' ')]:
                s = s.replace(f, h)
            return re.sub(r'\s+', ' ', s)
        a = _norm(name_a)
        b = _norm(name_b)
        if not a or not b:
            return True
        if a == b or a in b or b in a:
            return True
        set_a, set_b = set(a), set(b)
        union = len(set_a | set_b)
        return union > 0 and len(set_a & set_b) / union > 0.35

    def _rate_item_keys(self, tasks):
        """已設「計算比例」的工項索引：{項次, 顯示項次, 正規化名稱}。

        用來讓 _detect_xlsx_change_type 認出比例項，而不必寫死「稅什費」這個名字
        —— 自主檢查費、工安費等只要在系統裡設了比例，就走同一條路徑
        （F1-C 依變更後的基數重算金額、預覽也會逐項列出）。
        """
        keys = set()
        for t in tasks:
            if not t.tax_misc_rate:
                continue
            if t.item_no:
                keys.add(t.item_no)
            if t.display_item_no:
                keys.add(t.display_item_no)
            nm = self._normalize_name(t.name or '')
            if nm:
                keys.add(nm)
        return keys

    def _task_is_in_section(self, task, section_task):
        """沿 parent_id 鏈向上回溯，判斷 task 是否在 section_task 的子樹下。
        用於替代 xml_parent_chain，以系統資料庫關係消歧，與 XML 格式完全無關。
        """
        cur = task.parent_id
        while cur:
            if cur.id == section_task.id:
                return True
            cur = cur.parent_id if cur.parent_id else None
        return False

    # ── XLSX + XML 查找表解析（主要路徑）────────────────────────────────────────

    @staticmethod
    def _get_worksheet(wb):
        """依序嘗試多個 sheet 名稱取得工作表，含模糊匹配"""
        for name in ('詳細表(議價前)', '詳細表', '工程變更明細'):
            if name in wb.sheetnames:
                return wb[name]
        # 模糊匹配（如 "1變"、"第一次變更" 等）
        for name in wb.sheetnames:
            if '詳細' in name or '變更' in name:
                return wb[name]
        return wb.active

    def _update_section_context(self, item_no_raw, current_section_task,
                                  sections_by_parent, task_by_item_no):
        """
        章節追蹤 walk-up 演算法：從 current_section_task 向上回溯，
        找哪一層包含 item_no_raw 這個子節點。

        解決重複章節名稱問題（如「一」「(一)」在 壹/貳 下各出現一次），
        以及相鄰同層切換（(一)→(二)：(二) 是兄弟節點，需回溯至父層查找）。
        """
        search_from = current_section_task
        while search_from:
            candidate = sections_by_parent.get(search_from.id, {}).get(item_no_raw)
            if candidate:
                return candidate
            search_from = search_from.parent_id if search_from.parent_id else None
        # Fallback：根節點（壹/貳/參 等無 parent 的項目）
        return task_by_item_no.get(item_no_raw)

    def _find_task_by_context(self, item_no_raw, item_name, current_section_task,
                               children_by_parent, task_by_item_no,
                               task_by_name_unique=None):
        """
        三層策略找對應 project.task（XLSX 與 XML 共用）。

        策略 1（精確）：Task Hierarchy — current_section_task 直接子節點中查 display_item_no
        策略 2（全域）：全域 item_no + 名稱相容性驗證 + 章節所屬驗證
        策略 3（名稱）：全域唯一名稱（僅在無章節上下文時啟用，避免跨章節誤配）
        """
        # 策略 1：精確 Task Hierarchy（加名稱相容性驗證，避免同短碼不同名工項誤配）
        if current_section_task:
            task = children_by_parent.get(current_section_task.id, {}).get(item_no_raw)
            if task and self._names_compatible(item_name, task.name):
                return task

        # 策略 2：全域 item_no + 名稱相容 + 章節所屬
        task = task_by_item_no.get(item_no_raw)
        if task and not task.is_summary_item and self._names_compatible(item_name, task.name):
            if (not current_section_task
                    or self._task_is_in_section(task, current_section_task)
                    # 「往上跳一層」：像「二 自主品管費」這種掛在頂層彙總項底下的
                    # 葉節點，緊接在「一 工程費」的阿拉伯編號子項之後。讀到它時
                    # 章節上下文還停在「一 工程費」，而它的父項是「壹」——
                    # 只比對「是否在目前章節內」會判成配不到（實測整包費用項
                    # 因此變成 unmatch，整包金額的變更就靜靜遺失）。
                    # 目前章節若落在候選工項的父項底下，代表我們正要回到上一層，
                    # 這是合法的移動，予以接受。
                    or (task.parent_id
                        and self._task_is_in_section(current_section_task,
                                                     task.parent_id))):
                return task

        # 策略 3（名稱）：全域唯一名稱（僅在無章節上下文時，避免跨章節誤配）
        if task_by_name_unique is not None and not current_section_task:
            norm = self._normalize_name(item_name)
            if norm:
                task = task_by_name_unique.get(norm)
                if task and not task.is_summary_item:
                    return task

        return None

    @staticmethod
    def _detect_header_row(ws):
        """掃描前 20 列，找含「項次」且含「項目名稱」的標題列，回傳 1-indexed 列號"""
        for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=20, values_only=True), start=1):
            cells = [str(c).strip() if c is not None else '' for c in row]
            if '項次' in cells and any('項目名稱' in c for c in cells):
                return idx
        return 7  # 預設第 7 列

    # 語意欄位 → 標題關鍵字規則（正規化後比對）。不可寫死 col：不同檔案欄序可能不同。
    _COLUMN_RULES = [
        ('item_no',    lambda h: h == '項次' or '項次' in h),
        ('name',       lambda h: '項目名稱' in h or '名稱' in h),
        ('unit',       lambda h: h == '單位'),
        ('orig_qty',   lambda h: '原定' in h and '數量' in h),
        ('new_qty',    lambda h: '變更後' in h and '數量' in h),
        ('qty_change', lambda h: '增減' in h),
        ('orig_price', lambda h: '單價' in h and ('契約' in h or '原' in h)),
        ('new_price',  lambda h: '單價' in h and '議定' in h),
        ('orig_amount', lambda h: '合價' in h and ('原訂' in h or '原定' in h or '契約' in h)),
        ('new_amount', lambda h: '變更後' in h and '合價' in h),
        ('notes',      lambda h: '備註' in h),
    ]
    # fallback 固定索引（本參考檔位置）；對應不到時退回此處並 warning。
    _COLUMN_FALLBACK = {
        'item_no': 0, 'name': 1, 'unit': 2, 'orig_qty': 3, 'new_qty': 4,
        'qty_change': 5, 'orig_price': 6, 'new_price': 8, 'orig_amount': 9,
        'new_amount': 10, 'notes': 13,
    }

    @staticmethod
    def _norm_header(cell):
        """標題正規化：去除所有空白/換行（如 '原 定\\n數 量' → '原定數量'）"""
        if cell is None:
            return ''
        return re.sub(r'\s+', '', str(cell))

    def _build_column_map(self, header_cells):
        """以標題名稱動態對應欄位索引；任何欄位對應不到 → fallback 回固定索引並 warning，
        確保不同欄序的檔案不會整排錯位，且現有可解析檔案不退步。"""
        norms = [self._norm_header(c) for c in header_cells]
        cols = {}
        for key, rule in self._COLUMN_RULES:
            idx = next((i for i, h in enumerate(norms) if h and rule(h)), None)
            if idx is None:
                idx = self._COLUMN_FALLBACK[key]
                _logger.warning(
                    '工程變更明細表欄位「%s」找不到對應標題，fallback 回固定第 %d 欄', key, idx)
            cols[key] = idx
        return cols

    _CN_UPPER = '壹貳參肆伍陸柒捌玖拾'
    _CN_LOWER = '一二三四五六七八九十'

    @classmethod
    def _item_no_level_key(cls, item_no):
        """以項次的「格式骨架」當層級指紋：(前綴, 風格, 後綴)，風格∈upper/lower/arabic。
        用於資料驅動推斷新彙總項的層級（不寫死格式對層級）。
        刻意不把數字轉值（project_task._parse_item_no_skeleton 對「一０」這種混寫會失敗），
        改以字元集判斷風格，故 (一)/(一０)/(九) 同指紋＝同層級。失敗回 None。"""
        s = (item_no or '').strip()
        if not s:
            return None
        num_chars = '0-9０-９' + cls._CN_UPPER + cls._CN_LOWER
        m = re.search(
            r'^(?P<pre>[^%s]*)(?P<num>[%s]+)(?P<suf>[^%s]*)$'
            % (num_chars, num_chars, num_chars), s)
        if not m:
            return None
        pre, num, suf = m.group('pre'), m.group('num'), m.group('suf')
        if any(c in cls._CN_UPPER for c in num):
            style = 'upper'
        elif any(c in cls._CN_LOWER for c in num):
            style = 'lower'
        else:
            style = 'arabic'
        return (pre, style, suf)

    def _resolve_new_summary_parent(self, item_no, current_section_task, level_by_key):
        """決定新彙總項的正確父項。
        依項次格式指紋推斷其層級 s_level；父項應在 level=(s_level-1)。
        從 current_section_task 沿 parent_id 往上回溯，回傳該層祖先；
        s_level=0（頂層）回 False。推不出層級時 fallback 為「掛在 current_section_task 之下」。"""
        s_level = level_by_key.get(self._item_no_level_key(item_no))
        if s_level is None:
            # 推不出層級：保守地視為 current_section_task 的直屬子層
            return current_section_task
        target = s_level - 1
        if target < 0:
            return False
        node = current_section_task
        while node and node.item_level > target:
            node = node.parent_id if node.parent_id else None
        # 找到 level 剛好 == target 的祖先才採用；否則回退 current_section_task 避免掛到頂層亂飄
        if node and node.item_level == target:
            return node
        return current_section_task

    def _build_xml_lookup(self, original_xml_data):
        """
        解析原始 ETenderSheet XML，建立查找所需的資料結構

        回傳：
            xml_items_by_ino  : {itemNo: [{'ref_item_code': ..., 'name': ..., ...}, ...]}
                                  同一 itemNo 可能有多筆（格式如單一數字時跨章節重複）
            xml_parent_chain  : {child_itemNo: parent_itemNo}（字串對字串，供 xml_ps 追蹤用）
        """
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(original_xml_data)
        except ET.ParseError as e:
            raise UserError(f'原始標單 XML 解析失敗：{e}')

        ns_uri = ''
        if '}' in root.tag:
            ns_uri = root.tag.split('}')[0].lstrip('{')

        def qtag(tag):
            return f'{{{ns_uri}}}{tag}' if ns_uri else tag

        def find_text(element, *tags):
            for tag in tags:
                el = element.find(qtag(tag))
                if el is not None:
                    return (el.text or '').strip()
            return ''

        xml_items_by_ino = defaultdict(list)
        xml_parent_chain = {}

        def collect(element, parent_ino=None):
            for child in element:
                local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if local != 'PayItem':
                    collect(child, parent_ino)
                    continue
                ino = child.get('itemNo', '')
                ref = child.get('refItemCode', '').strip()
                xml_items_by_ino[ino].append({
                    'item_no': ino,
                    'name': find_text(child, 'Description', 'ItemName'),
                    'unit': find_text(child, 'Unit'),
                    'qty': float(find_text(child, 'Quantity') or 0),
                    'price': float(find_text(child, 'UnitPrice', 'Price') or 0),
                    'amount': float(find_text(child, 'TotalAmount') or 0),
                })
                if parent_ino is not None:
                    xml_parent_chain[ino] = parent_ino
                collect(child, ino)

        # 從 DetailList 開始收集（支援任意深度）
        detail_list = None
        for el in root.iter():
            local = el.tag.split('}')[-1] if '}' in el.tag else el.tag
            if local == 'DetailList':
                detail_list = el
                break
        collect(detail_list if detail_list is not None else root)

        return xml_items_by_ino, xml_parent_chain

    def _find_xml_item_by_xlsx_no(self, item_no_raw, xml_ps,
                                   xml_items_by_ino, xml_parent_chain):
        """
        從 XLSX 項次（如 "22"）找對應的 XML PayItem（如 "1.1.22"）

        策略：
        1. 直接比對（適用中文 itemNo 如 壹/一/(一)）
        2. 找末段吻合的候選，在 xml_ps 最深 parent 下消歧
        3. 依序回溯 xml_ps 各層級
        """
        if item_no_raw in xml_items_by_ino:
            return xml_items_by_ino[item_no_raw]

        if not xml_ps:
            return None

        candidates = [
            ino for ino in xml_items_by_ino
            if (ino.rsplit('.', 1)[-1] if '.' in ino else ino) == item_no_raw
        ]

        if not candidates:
            return None
        if len(candidates) == 1:
            return xml_items_by_ino[candidates[0]]

        for depth in sorted(xml_ps.keys(), reverse=True):
            parent_no = xml_ps[depth]
            for ino in candidates:
                if self._xml_ino_is_descendant(ino, parent_no, xml_parent_chain):
                    return xml_items_by_ino[ino]

        return None

    @staticmethod
    def _xml_ino_is_descendant(child_ino, ancestor_ino, xml_parent_chain):
        """判斷 child_ino 是否為 ancestor_ino 的後代（遍歷 parent 鏈）"""
        cur = xml_parent_chain.get(child_ino)
        while cur:
            if cur == ancestor_ino:
                return True
            cur = xml_parent_chain.get(cur)
        return False

    def _parse_xlsx_via_xml(self, xlsx_data, original_xml_data):
        """
        解析 XLSX 工程變更明細表，使用原始 XML 作為查找表取得 refItemCode

        原理：
        - XLSX 章節標題（壹/一/(一)）與 XML 的 itemNo 格式完全相同
        - 利用 XLSX 章節追蹤在 XML 中定位對應 PayItem，取得 refItemCode
        - 再以 refItemCode 精確比對系統工項，達到 100% 準確率
        """
        try:
            import openpyxl
        except ImportError:
            raise UserError('需要安裝 openpyxl 套件才能解析 XLSX 檔案')

        xml_items_by_ino, xml_parent_chain = self._build_xml_lookup(original_xml_data)

        project = self._get_project()
        existing_tasks = self.env['project.task'].search([
            ('supervision_project_id', '=', project.id),
            ('active', '=', True),
        ])
        task_by_item_no = {t.item_no: t for t in existing_tasks if t.item_no}
        rate_item_keys = self._rate_item_keys(existing_tasks)

        # 策略 4 查找表：正規化名稱 → task（唯一名稱）
        _name_map = defaultdict(list)
        for t in existing_tasks:
            _name_map[self._normalize_name(t.name or '')].append(t)
        task_by_name_unique = {k: v[0] for k, v in _name_map.items() if len(v) == 1}

        # 策略 1 查找表：parent_task_id → {display_item_no → 葉節點 task}
        children_by_parent = defaultdict(dict)
        for t in existing_tasks:
            if not t.is_summary_item and t.display_item_no and t.parent_id:
                children_by_parent[t.parent_id.id][t.display_item_no] = t

        # 章節追蹤查找表：parent_task_id → {item_no → task}
        sections_by_parent = defaultdict(dict)
        for t in existing_tasks:
            if t.parent_id:
                sections_by_parent[t.parent_id.id][t.item_no] = t

        # 層級指紋 → item_level（資料驅動推斷新彙總項層級，供決定正確父項用）
        _lvl_counter = defaultdict(Counter)
        for t in existing_tasks:
            key = self._item_no_level_key(t.item_no)
            if key:
                _lvl_counter[key][t.item_level] += 1
        level_by_key = {k: c.most_common(1)[0][0] for k, c in _lvl_counter.items()}

        try:
            wb = openpyxl.load_workbook(io.BytesIO(xlsx_data), data_only=True)
        except Exception as e:
            raise UserError(f'無法開啟 XLSX 檔案：{e}')

        ws = self._get_worksheet(wb)
        header_row = self._detect_header_row(ws)
        # 以標題名稱動態對應欄位索引（不可寫死 col；不同檔案欄序可能不同）
        header_cells = next(
            ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True), ())
        cols = self._build_column_map(header_cells)

        current_section_task = None
        current_new_group = None    # {'key','item_no','item_name','parent_task'}；非 None 表示在新彙總群組底下
        group_counter = [0]
        results = []
        xlsx_section_amounts = {}   # key = task.id，value = {name, new_amount}

        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            if not any(c is not None for c in (row[:14] if len(row) >= 14 else row)):
                continue

            def cell(idx, _row=row):
                return _row[idx] if len(_row) > idx else None

            _raw = cell(cols['item_no'])
            if _raw is None:
                item_no_raw = ''
            elif isinstance(_raw, float) and _raw.is_integer():
                item_no_raw = str(int(_raw))
            else:
                item_no_raw = str(_raw).strip()
            _nm = cell(cols['name'])
            item_name = str(_nm).strip() if _nm is not None else ''
            _u = cell(cols['unit'])
            unit = str(_u).strip() if _u is not None else ''
            orig_qty = cell(cols['orig_qty'])
            new_qty = cell(cols['new_qty'])
            qty_change = cell(cols['qty_change'])
            orig_price = cell(cols['orig_price'])
            new_price = cell(cols['new_price'])
            orig_amount = cell(cols['orig_amount'])
            new_amount = cell(cols['new_amount'])
            _nt = cell(cols['notes'])
            notes = str(_nt).strip() if _nt is not None else ''

            change_type = self._detect_xlsx_change_type(
                orig_qty, new_qty, qty_change, orig_price, new_price, notes, item_name,
                orig_amount, new_amount, item_no_raw, rate_item_keys)

            if change_type == 'summary':
                new_section = self._update_section_context(
                    item_no_raw, current_section_task, sections_by_parent, task_by_item_no)
                # 名稱輔助：項次找不到時，再以正規化名稱找既有彙總項（短碼項次易對不上）
                if not new_section:
                    _norm = self._normalize_name(item_name)
                    cand = task_by_name_unique.get(_norm) if _norm else None
                    if cand and cand.is_summary_item:
                        new_section = cand
                if new_section:
                    # 既有彙總項
                    current_section_task = new_section
                    current_new_group = None
                    if new_amount is not None:
                        xlsx_section_amounts[new_section.id] = {
                            'name': item_name,
                            'new_amount': new_amount,
                        }
                else:
                    # 新彙總項（項次＋名稱皆查無）→ 建立「新增彙總群組」，後續子項掛它。
                    # 與資料佐證一致：新彙總列原定數量=0、契約單價=0。
                    # 父項以「層級」決定：依項次格式指紋推斷本彙總項層級，再從目前章節
                    # 往上回溯到 level=(本層-1) 的祖先（避免被掛到前一個同層 section 之下）。
                    new_parent = self._resolve_new_summary_parent(
                        item_no_raw, current_section_task, level_by_key)
                    group_counter[0] += 1
                    gkey = group_counter[0]
                    current_new_group = {
                        'key': gkey,
                        'item_no': item_no_raw,
                        'item_name': item_name,
                        'parent_task': new_parent,
                    }
                    results.append({
                        'change_type': 'add',
                        'is_new_group': True,
                        'group_key': gkey,
                        'item_no': item_no_raw,
                        'item_name': item_name,
                        'unit': unit,
                        'task': None,
                        'parent_task': new_parent,
                        'orig_qty': None,
                        'new_qty': 0.0,
                        'new_price': 0.0,
                        'new_amount': new_amount or 0.0,
                        'notes': notes,
                    })
                continue

            # 在「新彙總群組」底下：所有葉列一律視為新增子項，掛到該新群組，
            # 不進既有比對 → 徹底避免拿別章節同短碼工項亂匹配。
            if current_new_group is not None:
                results.append({
                    'change_type': 'add',
                    'parent_group_key': current_new_group['key'],
                    'item_no': item_no_raw,
                    'item_name': item_name,
                    'unit': unit,
                    'task': None,
                    'parent_task': None,
                    'orig_qty': None,
                    'new_qty': new_qty or 0.0,
                    'new_price': new_price if new_price is not None else (orig_price or 0.0),
                    'new_amount': new_amount or 0.0,
                    'notes': notes,
                })
                continue

            if change_type == 'unchanged':
                # 全表對帳：未變更列也比對「原數量/原單價」是否＝系統現值，
                # 抓「文件未變更、卻與系統不符（漂移）」（情況1，財務驗算抓不到）
                task = self._find_task_by_context(
                    item_no_raw, item_name, current_section_task,
                    children_by_parent, task_by_item_no, task_by_name_unique)
                if task and self._recon_mismatch(orig_qty, orig_price, task):
                    results.append({
                        'change_type': 'recon',
                        'detected_type': 'unchanged',
                        'item_no': item_no_raw,
                        'item_name': item_name,
                        'unit': unit,
                        'task': task,
                        'parent_task': None,
                        'orig_qty': orig_qty,
                        'new_qty': new_qty,
                        'orig_price': orig_price,
                        'new_price': new_price,
                        'system_qty': task.planned_qty,
                        'system_price': task.unit_price,
                        'new_amount': new_amount,
                        'notes': notes,
                    })
                continue

            if change_type == 'add':
                parent_task = current_section_task
                results.append({
                    'change_type': 'add',
                    'item_no': item_no_raw,
                    'item_name': item_name,
                    'unit': unit,
                    'task': None,
                    'parent_task': parent_task,
                    'orig_qty': None,
                    'new_qty': new_qty or 0.0,
                    'new_price': new_price if new_price is not None else (orig_price or 0.0),
                    'new_amount': new_amount or 0.0,
                    'notes': notes,
                })
                continue

            # modify / delete / tax_misc → 四層策略找對應工項
            # tax_misc 是父章節層級（is_summary_item=True），直接以名稱查找，
            # 不走 _find_task_by_context()（策略 2 過濾 summary item）
            task = None
            if change_type == 'tax_misc':
                norm = self._normalize_name(item_name)
                task = task_by_name_unique.get(norm) if norm else None
            if not task:
                task = self._find_task_by_context(
                    item_no_raw,
                    item_name,
                    current_section_task,
                    children_by_parent,
                    task_by_item_no,
                    task_by_name_unique,
                )

            if not task:
                # §4.3「原定0/空、同章節查無 → 新增」：新增葉項的原定數量常是字面 0（非 None），
                # 會被判成 modify；同章節又找不到對應工項 → 視為新增（父=現章節），
                # 不退成 unmatch（避免使用者在手動配對時誤選別項造成亂匹配）。
                eff_new = new_qty or 0.0
                if change_type != 'tax_misc' and (orig_qty in (None, 0)) and eff_new > 0:
                    results.append({
                        'change_type': 'add',
                        'item_no': item_no_raw,
                        'item_name': item_name,
                        'unit': unit,
                        'task': None,
                        'parent_task': current_section_task,
                        'orig_qty': None,
                        'new_qty': eff_new,
                        'new_price': new_price if new_price is not None else (orig_price or 0.0),
                        'new_amount': new_amount or 0.0,
                        'notes': notes,
                    })
                    continue
                results.append({
                    'change_type': 'unmatch',
                    'change_type_hint': change_type,
                    'item_no': item_no_raw,
                    'item_name': item_name,
                    'unit': unit,
                    'orig_qty': orig_qty,
                    'new_qty': new_qty,
                    'orig_price': orig_price,
                    'new_price': new_price,
                    'new_amount': new_amount,
                    'notes': notes,
                })
                continue

            # XLSX 'delete'（new_qty=0）→ 'zero_out'
            actual_ct = 'zero_out' if change_type == 'delete' else change_type

            # 全表對帳：配到了，但文件原數量/原單價與系統現值不符 → 列入「對帳異常」
            # 不自動套用，交由使用者確認/改判（絕不以文件原值覆寫系統）
            if actual_ct in ('modify', 'zero_out') and self._recon_mismatch(orig_qty, orig_price, task):
                results.append({
                    'change_type': 'recon',
                    'detected_type': actual_ct,
                    'item_no': item_no_raw,
                    'item_name': item_name,
                    'unit': unit or task.unit or '',
                    'task': task,
                    'parent_task': None,
                    'orig_qty': orig_qty,
                    'new_qty': new_qty,
                    'orig_price': orig_price,
                    'new_price': new_price,
                    'system_qty': task.planned_qty,
                    'system_price': task.unit_price,
                    'new_amount': new_amount,
                    'notes': notes,
                })
                continue

            results.append({
                'change_type': actual_ct,
                'item_no': item_no_raw,
                'item_name': item_name,
                'unit': unit or task.unit or '',
                'task': task,
                'parent_task': None,
                'orig_qty': orig_qty if orig_qty is not None else task.planned_qty,
                'new_qty': new_qty,
                'orig_price': orig_price if orig_price is not None else task.unit_price,
                'new_price': new_price,
                'new_amount': new_amount,
                'notes': notes,
            })

        return results, xlsx_section_amounts

    # ── XLSX 直接解析（備用，需原始 XML 時不可用）────────────────────────────

    def _parse_xlsx(self, file_data):
        """
        解析工程變更明細表 XLSX

        格式規格：
        - Sheet：「詳細表(議價前)」
        - 標題列：第 7 列（row 7 in Excel）
        - 資料起始：第 8 列（row 8 in Excel）

        欄位對應：
        A(0)=項次, B(1)=項目名稱, C(2)=單位,
        D(3)=原定數量, E(4)=變更後數量, F(5)=增減數量,
        G(6)=契約單價, I(8)=議定單價,
        K(10)=變更後複價, N(13)=備註
        """
        try:
            import openpyxl
        except ImportError:
            raise UserError('需要安裝 openpyxl 套件才能解析 XLSX 檔案')

        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(file_data), read_only=True, data_only=True)
        except Exception as e:
            raise UserError(f'無法開啟 XLSX 檔案：{e}')

        sheet_name = '詳細表(議價前)'
        ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active

        project = self._get_project()
        existing_tasks = self.env['project.task'].search([
            ('supervision_project_id', '=', project.id),
            ('active', '=', True),
        ])

        # 建立多層查找表
        task_by_item_no = {t.item_no: t for t in existing_tasks if t.item_no}
        rate_item_keys = self._rate_item_keys(existing_tasks)

        # display_item_no 查找（葉節點只有最後一段數字，與 XLSX 格式相符）
        from collections import defaultdict
        _disp_map = defaultdict(list)
        for t in existing_tasks:
            disp = t.display_item_no or t.item_no or ''
            _disp_map[disp].append(t)
        task_by_display_no_unique = {k: v[0] for k, v in _disp_map.items() if len(v) == 1}
        task_by_display_no_multi = {k: v for k, v in _disp_map.items() if len(v) > 1}

        # 名稱查找（正規化後比對，名稱唯一時直接使用，重複時需用 parent 消歧）
        _name_map = defaultdict(list)
        for t in existing_tasks:
            _name_map[self._normalize_name(t.name or '')].append(t)
        task_by_name_unique = {k: v[0] for k, v in _name_map.items() if len(v) == 1}
        task_by_name_multi = {k: v for k, v in _name_map.items() if len(v) > 1}

        results = []
        parent_stack = {}  # {item_level: task}，追蹤層級

        for row in ws.iter_rows(min_row=8, values_only=True):
            if not any(cell is not None for cell in (row[:14] if len(row) >= 14 else row)):
                continue

            def cell(idx):
                return row[idx] if len(row) > idx else None

            _raw0 = cell(0)
            if _raw0 is None:
                item_no = ''
            elif isinstance(_raw0, float) and _raw0.is_integer():
                item_no = str(int(_raw0))
            else:
                item_no = str(_raw0).strip()
            item_name = str(cell(1)).strip() if cell(1) is not None else ''
            unit = str(cell(2)).strip() if cell(2) is not None else ''
            orig_qty = cell(3)
            new_qty = cell(4)
            qty_change = cell(5)
            orig_price = cell(6)
            new_price = cell(8)   # None = 單價不變；0 = 真的變為 0
            orig_amount = cell(9)  # 原訂合價（整包費用項靠它偵測金額變化）
            new_amount = cell(10)  # 變更後複價（稅什費用）
            notes = str(cell(13)).strip() if cell(13) is not None else ''

            change_type = self._detect_xlsx_change_type(
                orig_qty, new_qty, qty_change, orig_price, new_price, notes, item_name,
                orig_amount, new_amount, item_no, rate_item_keys)

            if change_type == 'summary':
                # 彙總列：以 item_no（中文）找對應的 task 更新 parent_stack
                task = task_by_item_no.get(item_no)
                if task:
                    level = task.item_level
                    parent_stack[level] = task
                    for lv in list(parent_stack.keys()):
                        if lv > level:
                            del parent_stack[lv]
                continue

            if change_type == 'unchanged':
                continue

            task = None
            if change_type != 'add':
                task = self._find_task_for_xlsx(
                    item_no, item_name, parent_stack,
                    task_by_item_no,
                    task_by_display_no_unique, task_by_display_no_multi,
                    task_by_name_unique, task_by_name_multi)
                if not task:
                    results.append({
                        'change_type': 'unmatch',
                        'change_type_hint': change_type,
                        'item_no': item_no,
                        'item_name': item_name,
                        'unit': unit,
                        'orig_qty': orig_qty,
                        'new_qty': new_qty,
                        'orig_price': orig_price,
                        'new_price': new_price,
                        'new_amount': new_amount,
                        'notes': notes,
                    })
                    continue

            parent_task = None
            if change_type == 'add':
                parent_no = self._get_parent_item_no(item_no)
                if parent_no:
                    parent_task = task_by_item_no.get(parent_no)
                if not parent_task and parent_stack:
                    parent_task = parent_stack[max(parent_stack.keys())]

            results.append({
                'change_type': change_type,
                'item_no': item_no,
                'item_name': item_name,
                'unit': unit,
                'task': task,
                'parent_task': parent_task,
                'orig_qty': orig_qty,
                'new_qty': new_qty,
                'orig_price': orig_price,
                'new_price': new_price,
                'new_amount': new_amount,
                'notes': notes,
            })

        return results

    @staticmethod
    def _recon_mismatch(orig_qty, orig_price, task):
        """全表對帳：文件「原數量/原單價」是否與系統工項現值不符（容差內視為相符）。
        任一非空且超出容差 → True。原值為空（None）者不比對該欄。
        數量容差 0.0001、單價容差 0.01。"""
        qty_bad = (orig_qty is not None
                   and abs((task.planned_qty or 0.0) - float(orig_qty)) > 0.0001)
        price_bad = (orig_price is not None
                     and abs((task.unit_price or 0.0) - float(orig_price)) > 0.01)
        return qty_bad or price_bad

    def _detect_xlsx_change_type(self, orig_qty, new_qty, qty_change,
                                  orig_price, new_price, notes, item_name='',
                                  orig_amount=None, new_amount=None,
                                  item_no='', rate_item_keys=None):
        """
        判斷 XLSX 列的變更類型

        判斷順序：
        1. 稅什費（依名稱，最優先）
        2. 彙總標題行
        3. 新增工項
        4. 刪除工項
        5. 修改工項
        6. 不變
        """
        # 比例項：金額 = 比例 × 基數，不是「數量 × 單價」，走專屬路徑
        # （F1-C 會依變更後的基數重算金額，預覽也會逐項列出）。
        # 判斷來源有二：
        #   1. 系統裡該工項已設有計算比例（rate_item_keys，涵蓋自主檢查費等
        #      任何比例項）—— 這是主要依據；
        #   2. 名稱含「稅什費／稅雜費」—— 舊有的後備，涵蓋「系統還沒設比例、
        #      但文件就是稅什費」的第一次匯入。
        if rate_item_keys:
            if (item_no or '') in rate_item_keys or self._normalize_name(
                    item_name or '') in rate_item_keys:
                return 'tax_misc'
        if '稅什費' in (item_name or '') or '稅雜費' in (item_name or ''):
            return 'tax_misc'

        # 彙總標題行：變更後數量和增減數量均為空
        # 章節列 orig_qty 可能是小計值（不為 None），但 new_qty/qty_change 一定是 None
        if new_qty is None and qty_change is None:
            return 'summary'

        # 新增工項：原定數量為空（彙總行已在上面攔截，此處 orig_qty is None 必為真正新增）
        if orig_qty is None:
            return 'add'

        # 刪除工項：變更後數量為 0、原數量有值
        if new_qty == 0 and orig_qty and orig_qty > 0:
            return 'delete'

        # 修改工項：數量有增減，或有議定單價（I欄不為空）
        if (qty_change and qty_change != 0) or new_price is not None:
            return 'modify'

        # 整包費用項（自主品管費、工安費…）：單價欄本來就空白、金額只寫在複價欄。
        # 數量恆為 1、也沒有議定單價，上面每一條規則都攔不到 —— 舊版判成「不變」
        # 直接跳過，整包金額的變更就這樣靜靜遺失。改靠複價差異偵測。
        if (not orig_price and orig_amount is not None and new_amount is not None
                and abs(float(new_amount) - float(orig_amount)) > 0.01):
            return 'modify'

        return 'unchanged'

    def _find_task_for_xlsx(self, item_no, item_name, parent_stack,
                             task_by_item_no,
                             task_by_display_no_unique, task_by_display_no_multi,
                             task_by_name_unique, task_by_name_multi):
        """
        多策略查找 XLSX 列對應的 project.task

        策略（依序）：
        1. 直接 item_no 精確比對（處理中文彙總項，如「壹」「(一)」）
        2. display_item_no 比對（葉節點末段數字，唯一時直接使用）
        3. display_item_no + parent 上下文消歧（有重複 display_no 時）
        4. 名稱精確比對（唯一名稱）
        5. 名稱 + parent 上下文消歧（有重複名稱時）
        """
        # 策略 1：直接比對（適用中文項次 壹/一/(一) 等）
        task = task_by_item_no.get(item_no)
        if task:
            return task

        # 策略 2：display_item_no 唯一比對
        task = task_by_display_no_unique.get(item_no)
        if task:
            return task

        # 策略 3：display_item_no 重複 → 用 parent 上下文消歧
        if item_no in task_by_display_no_multi and parent_stack:
            candidates = task_by_display_no_multi[item_no]
            task = self._disambiguate_by_parent(candidates, parent_stack)
            if task:
                return task

        # 策略 4：名稱唯一比對（正規化後）
        norm_name = self._normalize_name(item_name)
        task = task_by_name_unique.get(norm_name)
        if task:
            return task

        # 策略 5：名稱重複 → 用 parent 上下文消歧（正規化後）
        if norm_name in task_by_name_multi and parent_stack:
            candidates = task_by_name_multi[norm_name]
            task = self._disambiguate_by_parent(candidates, parent_stack)
            if task:
                return task

        return None

    def _disambiguate_by_parent(self, candidates, parent_stack):
        """從候選 tasks 中，找出是 parent_stack 任一 task 之後代的那個"""
        if not parent_stack:
            return None
        # 取 parent_stack 中層級最深（最近的）父節點
        current_parent = parent_stack[max(parent_stack.keys())]
        for t in candidates:
            if self._is_descendant_of(t, current_parent):
                return t
        return None

    def _is_descendant_of(self, task, ancestor):
        """判斷 task 是否為 ancestor 的後代"""
        cur = task.parent_id
        while cur:
            if cur.id == ancestor.id:
                return True
            cur = cur.parent_id
        return False

    @staticmethod
    def _get_parent_item_no(item_no):
        """從項次取得父項次（移除最後一個點號分段）"""
        if not item_no:
            return None
        s = str(item_no).strip()
        idx = s.rfind('.')
        return s[:idx] if idx > 0 else None

    # ── XML 解析 ────────────────────────────────────────────────────────────

    def _parse_xml(self, file_data):
        """
        解析 ETenderSheet XML（代表更新後的完整契約）。

        比對策略：三層（層級 → item_no+名稱 → 全域唯一名稱）。
        找不到對應工項 → unmatch（讓使用者手動選擇），不自動 add。
        未比對到的葉節點工項 → zero_out。
        """
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(file_data)
        except ET.ParseError as e:
            raise UserError(f'XML 解析失敗：{e}')

        if 'ETenderSheet' not in root.tag:
            raise UserError('檔案格式錯誤：必須是 ETenderSheet 格式的 XML 檔案')

        project = self._get_project()

        dummy_wizard = self.env['tender.import.wizard'].new({'project_id': project.id})
        xml_items = dummy_wizard._parse_pay_items(root)

        existing_tasks = self.env['project.task'].search([
            ('supervision_project_id', '=', project.id),
            ('active', '=', True),
        ])
        task_by_item_no = {t.item_no: t for t in existing_tasks if t.item_no}

        # 名稱唯一查找表（策略 3 fallback 用）
        _name_map = defaultdict(list)
        for t in existing_tasks:
            _name_map[self._normalize_name(t.name or '')].append(t)
        task_by_name_unique = {k: v[0] for k, v in _name_map.items() if len(v) == 1}

        # children_by_parent 供 _find_task_by_context() 策略 1 使用
        children_by_parent = defaultdict(dict)
        for t in existing_tasks:
            if not t.is_summary_item and t.display_item_no and t.parent_id:
                children_by_parent[t.parent_id.id][t.display_item_no] = t

        results = []
        matched_task_ids = set()

        for xml_item in xml_items:
            item_no = xml_item.get('item_no', '')
            name = xml_item.get('name', '')
            unit = xml_item.get('unit', '')
            quantity = xml_item.get('quantity', 0) or 0
            unit_price = xml_item.get('unit_price', 0) or 0

            task = self._find_task_by_context(
                item_no, name, None,
                children_by_parent, task_by_item_no,
                task_by_name_unique,
            )

            if not task:
                # bug 5：unmatch 而非自動 add，讓使用者手動確認
                results.append({
                    'change_type': 'unmatch',
                    'change_type_hint': 'add',
                    'item_no': item_no,
                    'item_name': name,
                    'unit': unit,
                    'orig_qty': None,
                    'new_qty': quantity,
                    'orig_price': None,
                    'new_price': unit_price,
                    'new_amount': xml_item.get('amount', 0),
                    'notes': xml_item.get('remark', ''),
                })
                continue

            if task.is_summary_item:
                continue

            matched_task_ids.add(task.id)

            qty_changed = abs((task.planned_qty or 0) - quantity) > 0.0001
            price_changed = abs((task.unit_price or 0) - unit_price) > 0.01
            # 式工項（Price=0）靠 xml_amount 偵測金額變化（如稅什費）
            xml_amount = xml_item.get('amount', 0) or 0
            amount_changed = (
                unit_price == 0
                and abs((task.xml_amount or 0) - xml_amount) > 0.01
            )

            if qty_changed or price_changed or amount_changed:
                results.append({
                    'change_type': 'modify',
                    'item_no': item_no,
                    'item_name': name,
                    'unit': unit,
                    'task': task,
                    'parent_task': None,
                    'orig_qty': task.planned_qty,
                    'new_qty': quantity,
                    'orig_price': task.unit_price,
                    'new_price': unit_price,
                    'new_amount': xml_item.get('amount', 0),
                    'notes': xml_item.get('remark', ''),
                })

        # zero_out：本次 XML 未比對到的葉節點工項
        for task in existing_tasks:
            if task.is_summary_item or task.child_ids:
                continue
            if task.id not in matched_task_ids:
                results.append({
                    'change_type': 'zero_out',
                    'item_no': task.item_no or '',
                    'item_name': task.name or '',
                    'unit': task.unit or '',
                    'task': task,
                    'parent_task': None,
                    'orig_qty': task.planned_qty,
                    'new_qty': 0,
                    'orig_price': task.unit_price,
                    'new_price': 0,
                    'new_amount': 0,
                    'notes': '',
                })

        return results

    # ── 套用至現有 wizard ────────────────────────────────────────────────────

    def _apply_to_existing_wizard(self, parsed):
        """
        將解析結果套用至現有的 contract.change.wizard

        先清除所有 wizard_line 的 change_type，再依解析結果重新設定。
        稅什費行直接更新 task 的 xml_amount / tax_misc_rate。
        """
        wizard = self.wizard_id

        # 清除所有既有 change_type（檔案匯入為唯一真相來源）
        wizard.wizard_line_ids.write({'change_type': False})

        # 建立 task_id → wizard_line 快速查詢
        line_by_task_id = {
            line.task_id.id: line
            for line in wizard.wizard_line_ids
            if line.task_id
        }

        max_seq = max(
            (l.sequence for l in wizard.wizard_line_ids), default=0)

        # 新增彙總群組：group_key → 已建立的 wizard_line.id（供子項以 parent_line_id 指向）。
        # parsed 中群組列必在其子項之前（xlsx 由上而下解析），故單趟即可建立對應。
        ChangeLine = self.env['contract.change.wizard.line']
        group_line_by_key = {}

        for item in parsed:
            ct = item.get('change_type')
            # unmatch / recon 不自動套用：交由使用者在精靈中確認/改判後，
            # 由 action_apply_to_wizard 以「處置結果」另行注入 parsed 套用。
            if ct in ('unmatch', 'recon'):
                continue

            if ct == 'add':
                max_seq += 10
                vals = {
                    'wizard_id': wizard.id,
                    'sequence': max_seq,
                    'change_type': 'add',
                    'item_no': item.get('item_no', ''),
                    'item_name': item.get('item_name', ''),
                    'unit': item.get('unit', ''),
                    'new_qty': item.get('new_qty') or 0.0,
                    'new_unit_price': item.get('new_price') or 0.0,
                }
                # 新增的整包費用項（來源單價欄空白、金額只在複價欄）：
                # 不標記的話 _create_added_task 會建出一個 xml_amount=0、
                # unit_price=0 的工項 —— 四個分支全落空，永遠 0 元。
                _add_price = item.get('new_price') or 0.0
                _add_amount = item.get('new_amount') or 0.0
                if (not item.get('is_new_group')
                        and not _add_price and _add_amount > 0):
                    vals['is_new_lump_sum'] = True
                    vals['new_amount'] = round(_add_amount, 2)
                if item.get('is_new_group'):
                    # 新彙總群組列：本身無量價，父=外層既有彙總項（可為空＝頂層）
                    parent_task = item.get('parent_task')
                    vals['is_new_group'] = True
                    vals['parent_task_id'] = parent_task.id if parent_task else False
                    line = ChangeLine.create(vals)
                    gkey = item.get('group_key')
                    if gkey is not None:
                        group_line_by_key[gkey] = line.id
                else:
                    gkey = item.get('parent_group_key')
                    if gkey is not None and gkey in group_line_by_key:
                        # 子項父為本次新增群組 → 以 parent_line_id 指向群組列
                        vals['parent_line_id'] = group_line_by_key[gkey]
                    else:
                        parent_task = item.get('parent_task')
                        vals['parent_task_id'] = parent_task.id if parent_task else False
                    ChangeLine.create(vals)
                continue

            task = item.get('task')
            if not task:
                continue

            if ct == 'tax_misc':
                task_vals = {}
                new_amount = item.get('new_amount')
                if new_amount is not None:
                    task_vals['xml_amount'] = new_amount
                match = re.search(r'([\d.]+)\s*%', item.get('notes', '') or '')
                if match:
                    rate = float(match.group(1))
                    task_vals['tax_misc_rate'] = rate
                    wizard.tax_misc_rate = rate
                if task_vals:
                    task.write(task_vals)
                wizard_line = line_by_task_id.get(task.id)
                if wizard_line and new_amount is not None:
                    # 比例項的金額走「新金額」，不塞進「新單價」——
                    # new_amount / qty 那種假單價會被 _apply_changes 寫回
                    # task.unit_price，也讓變更設計詳細表印成「原單價 0、追加=全額」。
                    wizard_line.write({
                        'change_type': 'modify',
                        'new_qty': task.planned_qty or 1.0,
                        'new_unit_price': 0.0,
                        'new_amount': round(new_amount, 2),
                    })
                continue

            wizard_line = line_by_task_id.get(task.id)
            if not wizard_line:
                continue

            if ct == 'modify':
                new_qty = item.get('new_qty')
                new_price = item.get('new_price')
                new_amount = item.get('new_amount')

                if task.is_lump_sum or task.tax_misc_rate:
                    # 整包費用項與比例項：金額載體是「新金額」，不是「新單價」。
                    # 舊寫法把 new_amount ÷ qty 塞進 new_unit_price，套用時就會被
                    # 寫回 task.unit_price —— 那正是 18.0.2.0.0 要消除的污染。
                    # 也刻意「不」在這裡直接改 task.xml_amount：那會讓明細列的
                    # 「原金額」變成新值、金額增減顯示成 0。改由變更單套用時
                    # （_apply_changes_to_tasks）寫回，變更前／後才對得起來。
                    wizard_line.write({
                        'change_type': 'modify',
                        'new_qty': (new_qty if new_qty is not None
                                    else task.planned_qty or 1.0),
                        'new_unit_price': 0.0,
                        'new_amount': round(new_amount or 0.0, 2),
                    })
                # 式工項（Price=0）：xml_amount 發生變化（如稅什費）
                # → 更新 task.xml_amount，wizard_line 以新 xml_amount 呈現
                elif (not new_price or new_price == 0) and new_amount and new_amount > 0:
                    task.write({'xml_amount': new_amount})
                    qty = new_qty or task.planned_qty or 1.0
                    wizard_line.write({
                        'change_type': 'modify',
                        'new_qty': qty,
                        'new_unit_price': new_amount / qty if qty else 0.0,
                    })
                else:
                    wizard_line.write({
                        'change_type': 'modify',
                        'new_qty': (
                            new_qty if new_qty is not None else task.planned_qty or 0.0),
                        'new_unit_price': (
                            new_price if new_price is not None else task.unit_price or 0.0),
                    })

            elif ct in ('zero_out', 'delete'):
                wizard_line.write({'change_type': 'zero_out'})
