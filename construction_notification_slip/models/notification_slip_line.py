# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ReservationNotificationSlipLine(models.Model):
    """
    通報單詳細表項目

    設計說明:
    - planned_qty/planned_amount = 預算 (planned)
    - actual_qty/actual_amount = 實際執行
    - task_id 關聯契約工項（由 wizard 批次帶入）

    階層與金額（2026-08-25 起）:
    詳細表是契約工項樹的一個**完整子樹**——選了葉節點就會自動補齊祖先彙總項，
    刪除某列會連同本單內的子孫一起刪。因為樹永遠完整，parent_line_id 可以直接
    取「本單內對應到 task_id.parent_id 的那一列」，不必找最近祖先。

    金額三分支（與契約工項 project.task._compute_planned_amount 同一套規則）:
      1. 本單內有子列        → Σ 子列金額（唯讀）
      2. 無子列的彙總項/無單價項 → 手填（compute 不覆寫）
      3. 一般葉節點          → 數量 × 單價

    來源實例（第1次通報單_預約式工程施工通知回報單.xlsx）:
      壹 發包工程費 274,673      ← 分支 1
      一 工程費     222,644.24   ← 分支 1
      1/5/62…279 共 15 列        ← 分支 3
      二~七（契約中有子工項，通報單只寫一個總數） ← 分支 2
      八 稅什費(含保險費) 27,130.76（契約中是無單價葉節點） ← 分支 2
    """
    _name = 'reservation.notification.slip.line'
    _description = '通報單詳細表項目'
    _order = 'sequence, item_no, id'

    # === 關聯 ===
    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單',
        required=True, ondelete='cascade', index=True)

    project_id = fields.Many2one(
        'project.project', string='所屬工程',
        related='slip_id.project_id', store=True)

    company_id = fields.Many2one(
        'res.company', string='公司',
        related='slip_id.company_id', store=True)

    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        related='slip_id.currency_id', store=True)

    sequence = fields.Integer(
        string='排序', default=10)

    # === 工項關聯 ===
    task_id = fields.Many2one(
        'project.task', string='契約工項',
        required=True,
        domain="[('supervision_project_id', '=', project_id)]",
        help='關聯的契約工項')

    parent_item_name = fields.Char(
        string='父工項路徑',
        compute='_compute_parent_item_name', store=True)

    # === 本單內的階層（詳細表 = 契約工項樹的完整子樹）===
    parent_line_id = fields.Many2one(
        'reservation.notification.slip.line',
        string='父明細列',
        compute='_compute_parent_line_id', store=True, index=True,
        help='本單內對應到「契約工項的父工項」的那一列。'
             '結算金額只加總沒有父列的根列，避免小計被重複計入。')

    child_line_ids = fields.One2many(
        'reservation.notification.slip.line', 'parent_line_id',
        string='子明細列')

    is_summary_line = fields.Boolean(
        string='彙總項',
        related='task_id.is_summary_item', store=True,
        help='對應的契約工項底下還有子工項')

    is_manual_amount = fields.Boolean(
        string='金額手填',
        compute='_compute_is_manual_amount',
        help='本單內沒有子列，且是彙總項或無單價項（如稅什費）→ 金額直接手填')

    # === 項目基本資訊 ===
    item_no = fields.Char(
        string='項目編號', required=True,
        help='工項編號')

    display_item_no = fields.Char(
        related='task_id.display_item_no', string='項次', store=True)

    description = fields.Char(
        string='項目及說明', related='task_id.name', store=True, readonly=True)

    unit = fields.Char(
        string='單位', required=True,
        help='計量單位，如：M, M2, M3, 式')

    # 彙總項與稅什費類沒有單價（金額直接手填），故不可 required
    unit_price = fields.Monetary(
        string='單價', default=0.0,
        currency_field='currency_id')

    # === 預算欄位 (預估需求) ===
    planned_qty = fields.Float(
        string='預估數量 (預算)',
        digits=(16, 4),
        help='預估施作數量')

    planned_amount = fields.Monetary(
        string='預估金額 (預算)',
        currency_field='currency_id',
        compute='_compute_planned_amount', store=True, readonly=False,
        recursive=True,
        help='有子列 → 子列加總；無子列的彙總項/無單價項 → 手填；'
             '一般葉節點 → 預估數量 × 單價')

    # === 實際執行欄位 ===
    actual_qty = fields.Float(
        string='實際完成數量',
        digits=(16, 4),
        help='實際施作完成數量')

    actual_amount = fields.Monetary(
        string='實際金額',
        currency_field='currency_id',
        compute='_compute_actual_amount', store=True, readonly=False,
        recursive=True,
        help='有子列 → 子列加總；無子列的彙總項/無單價項 → 手填；'
             '一般葉節點 → 實際完成數量 × 單價')

    # === Portal 需要的欄位 ===
    specification = fields.Text(
        string='規格說明')

    completion_rate = fields.Float(
        string='完成率 (%)',
        compute='_compute_completion_rate', store=True,
        digits=(5, 2),
        help='(actual_amount / planned_amount) x 100')

    # === 備註 ===
    note = fields.Text(string='備註')

    # === 計算方法 ===
    @api.depends('task_id', 'task_id.parent_id',
                 'slip_id', 'slip_id.detail_line_ids.task_id')
    def _compute_parent_line_id(self):
        """父列 = 本單內 task_id 等於自己 task_id.parent_id 的那一列。

        能這樣直接取而不必找「最近祖先」，是因為詳細表的樹永遠完整：
        加入時自動補齊祖先（_create_lines_for_tasks），刪除時級聯刪子孫（unlink）。
        """
        for line in self:
            parent_task = line.task_id.parent_id
            if not parent_task or not line.slip_id:
                line.parent_line_id = False
                continue
            match = line.slip_id.detail_line_ids.filtered(
                lambda l: l.task_id.id == parent_task.id and l.id != line.id)
            line.parent_line_id = match[:1]

    @api.depends('slip_id.detail_line_ids.task_id', 'task_id',
                 'is_summary_line', 'unit_price', 'task_id.tax_misc_rate',
                 'task_id.is_lump_sum')
    def _compute_is_manual_amount(self):
        """金額是否由人工填寫。

        本單內有子列 → 一律加總，不可手填。
        沒有子列時，彙總項（如「三 雜項工程費」只寫一個總數）與無單價項
        （如「八 稅什費」在契約中是 tax_misc_rate 驅動的無單價葉節點）都只能手填。

        ⚠️ 「有沒有子列」刻意從**同單的工項階層**推，而不是讀 child_line_ids。
        使用者在表單上刪掉子列、還沒存檔時，被刪那一列的 parent_line_id 仍留在
        資料庫裡，child_line_ids 因此還看得到它 —— 父列的金額欄會一直卡在唯讀，
        要存檔後才變成可填。改看 detail_line_ids 就能在 onchange 當下正確翻轉。
        """
        for line in self:
            siblings = line.slip_id.detail_line_ids
            has_child = any(
                sib != line and sib.task_id.parent_id == line.task_id
                for sib in siblings)
            if has_child:
                line.is_manual_amount = False
            else:
                line.is_manual_amount = bool(
                    line.is_summary_line
                    or line.task_id.tax_misc_rate
                    or line.task_id.is_lump_sum
                    or not line.unit_price)

    @api.depends('planned_qty', 'unit_price', 'is_manual_amount',
                 'child_line_ids', 'child_line_ids.planned_amount')
    def _compute_planned_amount(self):
        for line in self:
            if line.child_line_ids:
                line.planned_amount = sum(
                    line.child_line_ids.mapped('planned_amount'))
            elif line.is_manual_amount:
                # 手填：不覆寫既有值。compute 期間欄位受 env.protecting 保護，
                # 讀回來的是資料庫現值，不會觸發遞迴重算，也不需要影子欄位。
                line.planned_amount = line.planned_amount or 0.0
            else:
                line.planned_amount = line.planned_qty * line.unit_price

    @api.depends('actual_qty', 'unit_price', 'is_manual_amount',
                 'child_line_ids', 'child_line_ids.actual_amount')
    def _compute_actual_amount(self):
        for line in self:
            if line.child_line_ids:
                line.actual_amount = sum(
                    line.child_line_ids.mapped('actual_amount'))
            elif line.is_manual_amount:
                line.actual_amount = line.actual_amount or 0.0
            else:
                line.actual_amount = line.actual_qty * line.unit_price

    @api.depends('planned_amount', 'actual_amount')
    def _compute_completion_rate(self):
        for line in self:
            if line.planned_amount:
                line.completion_rate = (line.actual_amount / line.planned_amount) * 100
            else:
                line.completion_rate = 0.0

    @api.depends('task_id', 'task_id.parent_id', 'task_id.parent_id.full_item_path')
    def _compute_parent_item_name(self):
        for line in self:
            if line.task_id and line.task_id.parent_id:
                line.parent_item_name = line.task_id.parent_id.full_item_path or ''
            else:
                line.parent_item_name = ''

    # === 建立詳細表列（後台精靈與匯入共用，避免兩份實作漂移）===
    # ⚠️ 這裡**不能**下 UNIQUE(slip_id, task_id)。
    # 2026-08-25 實測：既有資料有 12 組同單同工項的重複列，全部是葉節點——
    # 來源標單有兩個項次（1.100 / 1.101）名稱完全相同，匯入以名稱解析後對到同一
    # 個 task。葉節點重複不會算錯：兩列都掛在同一個父列下，父列把兩筆都加進去。
    # 真正會算錯的只有「彙總項重複」：子列只會認第一列當父，第二列變成沒有子列的
    # 彙總列（走手填分支），它的金額會在祖父列那邊被重複加一次。
    # 因此改用 Python constrains，只擋彙總項。
    @api.constrains('slip_id', 'task_id')
    def _check_summary_task_unique(self):
        for rec in self:
            if not rec.task_id or not rec.task_id.child_ids:
                continue
            dup = self.search_count([
                ('slip_id', '=', rec.slip_id.id),
                ('task_id', '=', rec.task_id.id),
                ('id', '!=', rec.id),
            ])
            if dup:
                raise ValidationError(
                    f'彙總項「{rec.task_id.name}」在本通報單中已存在，不可重複加入！\n'
                    '彙總項重複會讓子列只認第一列當父，第二列的金額被重複計入結算金額。')

    @api.model
    def _expand_with_ancestors(self, tasks):
        """把選取的契約工項擴充成「含所有祖先」的集合。

        使用者只勾葉節點時，「壹 發包工程費」「一 工程費」這些彙總項也必須一起
        建進詳細表——列印格式需要它們，結算金額也靠它們當根列。
        """
        result = tasks.browse()
        for task in tasks:
            node = task
            while node:
                result |= node
                node = node.parent_id
        return result

    @api.model
    def _prepare_line_vals(self, slip, task):
        """由契約工項組出一列詳細表的預設值。

        item_no 取 display_item_no（葉節點只留末段，如 1.62 → 62），
        與來源回報單的「項次」欄一致；彙總項則原樣是壹/一/二。
        彙總項沒有單價，unit_price 落 0，金額改由手填或子列加總。
        """
        return {
            'slip_id': slip.id,
            'task_id': task.id,
            'sequence': task.sequence,
            'item_no': task.display_item_no or task.item_no or '',
            # description 是 related='task_id.name' 的 store 欄位，不可在此指定，
            # 否則寫入會反向蓋回契約工項的名稱。
            'unit': task.unit or '式',
            'unit_price': task.unit_price or 0.0,
        }

    @api.model
    def _create_lines_for_tasks(self, slip, tasks):
        """建立詳細表列：自動補齊祖先、跳過已存在者、依契約順序排列。"""
        tasks = self._expand_with_ancestors(tasks)
        existing = slip.detail_line_ids.mapped('task_id')
        new_tasks = (tasks - existing).sorted(lambda t: (t.sequence, t.id))
        used_nos = set(slip.detail_line_ids.mapped('item_no'))
        created = self.browse()
        for task in new_tasks:
            vals = self._prepare_line_vals(slip, task)
            # 同單 item_no 不可重複（_check_unique_item_no）。自動補進來的祖先
            # 彙總項若剛好與既有明細撞號，加尾碼讓它進得來，而不是整批建立失敗。
            base_no = vals['item_no'] or task.name or 'X'
            no, n = base_no, 1
            while no in used_nos:
                n += 1
                no = '%s-%d' % (base_no, n)
            vals['item_no'] = no
            used_nos.add(no)
            created |= self.create(vals)
        created._apply_tax_misc_default()
        return created

    def _apply_tax_misc_default(self):
        """稅什費類（無單價、有 tax_misc_rate）建立時以契約比例試算一次當預設。

        ⚠️ 只在建立時算，**不放進 compute 依賴鏈**：它依賴同單前置列、前置列又
        依賴父列，放進依賴鏈會繞成循環。試算值必定要能改——實測契約比例
        10.94681908% 算出 27,096，回報單實際填 27,130.76。
        同層前置列金額尚未填寫時試算為 0，由使用者自行輸入。
        """
        for line in self:
            task = line.task_id
            if not task.tax_misc_rate or task.child_ids or line.planned_amount:
                continue
            preceding = line.slip_id.detail_line_ids.filtered(
                lambda l: l.id != line.id
                and l.parent_line_id.id == line.parent_line_id.id
                and l.sequence < line.sequence)
            base = sum(preceding.mapped('planned_amount'))
            if base:
                line.planned_amount = round(
                    base * task.tax_misc_rate / 100.0, 2)

    # 金額欄位是 compute + store + readonly=False，Odoo 對這種欄位的規則是
    # 「一旦被明確寫入，就不再重算」。後台表單靠 readonly="not is_manual_amount"
    # 擋住手改，但 ORM／匯入沒有這道保護 —— 在一般葉節點寫進一個與「數量×單價」
    # 不符的金額會被原樣存起來，不報錯也不會被修正（實測 V10）。
    # 以下兩個覆寫把非手填列的金額一律交還給 compute。
    _AMOUNT_FIELDS = ('planned_amount', 'actual_amount')

    def _restore_computed_amounts(self):
        """把非手填列的金額排入重算佇列（丟棄外部寫入的值）。"""
        auto = self.filtered(lambda l: not l.is_manual_amount)
        for fname in self._AMOUNT_FIELDS:
            if auto:
                self.env.add_to_compute(self._fields[fname], auto)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._restore_computed_amounts()
        return records

    def write(self, vals):
        amount_keys = [k for k in self._AMOUNT_FIELDS if k in vals]
        if not amount_keys:
            return super().write(vals)

        # 先寫其他欄位（unit_price 可能同批寫入），is_manual_amount 才是最新狀態
        rest = {k: v for k, v in vals.items() if k not in amount_keys}
        if rest:
            super().write(rest)

        manual = self.filtered('is_manual_amount')
        if manual:
            super(ReservationNotificationSlipLine, manual).write(
                {k: vals[k] for k in amount_keys})
        (self - manual)._restore_computed_amounts()
        return True

    def unlink(self):
        """刪除某列時一併刪除本單內的子孫列，維持樹的完整性。

        沒有這一段的話，刪掉「一 工程費」會讓 15 個葉節點失去父列而變成根列，
        同時祖父列「壹」還把它們算在加總裡 → 結算金額重複計算。
        子列全數移除後，父列金額歸零，回到可手填狀態。
        """
        all_lines = self
        frontier = self
        while frontier:
            children = frontier.child_line_ids - all_lines
            all_lines |= children
            frontier = children
        parents = all_lines.mapped('parent_line_id') - all_lines
        res = super(ReservationNotificationSlipLine, all_lines).unlink()
        orphaned = parents.exists().filtered(lambda l: not l.child_line_ids)
        if orphaned:
            orphaned.write({'planned_amount': 0.0, 'actual_amount': 0.0})
        return res

    # === 約束驗證 ===
    @api.constrains('planned_qty', 'actual_qty', 'unit_price')
    def _check_positive_values(self):
        """驗證約束：數量與單價必須為正數"""
        for rec in self:
            if rec.planned_qty < 0:
                raise ValidationError(
                    f'項目 {rec.item_no}: 預估數量不得為負數'
                )
            if rec.actual_qty < 0:
                raise ValidationError(
                    f'項目 {rec.item_no}: 實際數量不得為負數'
                )
            if rec.unit_price < 0:
                raise ValidationError(
                    f'項目 {rec.item_no}: 單價不得為負數'
                )

    @api.constrains('slip_id', 'item_no')
    def _check_unique_item_no(self):
        """驗證約束：同一通報單內項次不可重複"""
        for rec in self:
            if rec.slip_id and rec.item_no:
                duplicate = self.search([
                    ('slip_id', '=', rec.slip_id.id),
                    ('item_no', '=', rec.item_no),
                    ('id', '!=', rec.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        f'項目編號 {rec.item_no} 在此通報單中已存在'
                    )

    def name_get(self):
        result = []
        for rec in self:
            name = f'{rec.item_no} - {rec.description}'
            result.append((rec.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|',
                      ('item_no', operator, name),
                      ('description', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
