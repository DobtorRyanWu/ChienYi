# -*- coding: utf-8 -*-
"""營造廠層級單據的「營造廠」歸屬欄位（合約 §3.5）。

全部放在本模組（不改各模組、不升各模組版號）。讀取規則見 rule_scope.py：
營造方只看得到 contractor_company_id＝自己範圍公司、且工程營造廠仍含該公司的單據。

* 預設（compute＋store＋precompute，readonly=False）：照片掛在有歸屬的單據上 → 跟著那張單據（§0b-11）；
  其他：已有值、且仍是所屬工程的營造廠 → 不覆寫；工程只有一家營造廠 → 那家；
  建立者是營造方且範圍公司在工程營造廠內 → 範圍公司；其他留空（工程有多家營造廠時由監造方補）。
* 改工程（合約 §0b-26，write）：監造方把單據／照片改到另一個工程、沒有同時指定歸屬，而原歸屬不是新工程的營造廠時，
  依新工程重算（新工程只有一家營造廠 → 那家；建立者是營造方且範圍公司在新工程內 → 範圍公司；否則留空）；
  原歸屬仍在新工程內、或工程其實沒變（寫回同一個工程）就保留——營造廠被移出工程後，舊單據的歸屬不會因為
  有人重存一次就被改給剩下的那一家。跟著單據的照片不在此列（照舊跟單據）。
  營造方改工程照舊：已有值不覆寫（改到沒承攬的工程 → 約束擋下，營造方不能藉改工程把資料移給別家）。
* 營造方建立時一律強制成自己的範圍公司（忽略傳入值；sudo 也一樣，判定用 env.user）。
* 營造方不能改這個欄位，只有監造方能改。
* 約束：有值時必須是營造廠，且在所屬工程的營造廠內。例外：照片跟著所屬單據、值就是單據的歸屬時不查工程
  （合約 §0b-26：營造廠被移出工程後，監造方替它的舊缺失補照片；單據才是依據，照片只是跟著它）。
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

COMPANY_TYPE_CONTRACTOR = 'contractor'
MIXIN_NAME = 'construction.contractor.attribution.mixin'


class ContractorAttributionMixin(models.AbstractModel):
    _name = MIXIN_NAME
    _description = '營造廠歸屬（公司儀表板）'

    # 所屬工程欄位名；日誌的 project_id 是 related（precompute 會被 Odoo 關掉），改用 supervision_project_id
    _dash_project_field = 'project_id'

    contractor_company_id = fields.Many2one(
        'res.company',
        string='營造廠',
        domain="[('company_type', '=', 'contractor')]",
        compute='_compute_contractor_company_id',
        store=True,
        readonly=False,
        precompute=True,
        index=True,
        help='這筆資料屬於哪一家營造廠（公司儀表板：營造方只看得到自家的）。\n'
             '工程只有一家營造廠時自動帶入；營造方建立的一律是自己的公司；多家營造廠的工程由監造方補填。',
    )

    def _dash_project(self):
        self.ensure_one()
        return self[self._dash_project_field]

    def _dash_project_contractors(self):
        """所屬工程的營造廠：承包廠商中公司類型是營造廠的（真實資料有把監造公司填進承包廠商的工程）。"""
        self.ensure_one()
        return self.sudo()._dash_project().contractor_company_ids.filtered(
            lambda c: c.company_type == COMPANY_TYPE_CONTRACTOR)

    @api.model
    def _dash_attribution_depends(self):
        """歸屬欄位 compute 的依賴：所屬工程欄位；各模型可再加（照片：所屬單據與單據的歸屬）。"""
        return [self._dash_project_field] if self._dash_project_field in self._fields else []

    def _dash_attribution_parent(self):
        """這筆資料要「跟著它歸屬」的所屬單據（合約 §0b-11，只有照片有）；不跟任何單據回 None。"""
        return None

    @api.depends(lambda self: self._dash_attribution_depends())
    def _compute_contractor_company_id(self):
        user = self.env.user
        # 營造方觸發的重算（例：前台 sudo 改了工程）只能歸到自己的範圍公司，不能把資料算給別家
        acting_scope = None
        if user._dash_is_contractor_side():
            acting_scope = user.sudo().dash_scope_company_id if user._dash_scope_ok() else self.env['res.company']
        for rec in self:
            # 掛在有歸屬的單據上（照片）：跟著那張單據，含單據還沒歸屬（合約 §0b-11）。
            # 營造方觸發的重算不走這條：照舊只能歸到自己的範圍公司，不能經由改掛單據把資料算給別家
            parent = rec._dash_attribution_parent() if acting_scope is None else None
            if parent is not None:
                rec.contractor_company_id = parent.sudo().contractor_company_id
                continue
            if rec.contractor_company_id:
                # 已有值不覆寫（要寫回去，否則 stored compute 視為沒指派）。監造方改工程的情況在 write 處理（§0b-26）
                rec.contractor_company_id = rec.contractor_company_id
                continue
            contractors = rec._dash_project_contractors()
            if acting_scope is not None:
                rec.contractor_company_id = acting_scope if acting_scope and acting_scope in contractors else False
                continue
            rec.contractor_company_id = rec._dash_default_attribution(contractors)

    def _dash_default_attribution(self, contractors):
        """沒有既有值、不跟單據、不是營造方觸發時的預設：工程只有一家營造廠 → 那家；
        建立者是營造方且範圍公司在工程營造廠內 → 範圍公司；其他留空。contractors＝所屬工程的營造廠。"""
        self.ensure_one()
        if len(contractors) == 1:
            return contractors
        creator = self.create_uid
        scope = creator.sudo().dash_scope_company_id if creator else self.env['res.company']
        if creator and creator._dash_is_contractor_side() and creator._dash_scope_ok() and scope in contractors:
            return scope
        return self.env['res.company']

    def _dash_rederive_on_project_change(self, vals):
        """監造方改工程（合約 §0b-26）：self（工程真的變了的紀錄）之中「原歸屬不是新工程的營造廠、不跟單據」的，
        依新工程重算的歸屬 → {營造廠（可為空）: 紀錄}。呼叫端有指定歸屬、或是營造方時回空（照舊）。"""
        field = self._dash_project_field
        if field not in vals or 'contractor_company_id' in vals or self.env.user._dash_is_contractor_side():
            return {}
        Project = self.env[self._fields[field].comodel_name].sudo()
        new_project = Project.browse(vals[field]) if vals[field] else Project
        contractors = new_project.contractor_company_ids.filtered(
            lambda c: c.company_type == COMPANY_TYPE_CONTRACTOR)
        groups = {}
        for rec in self.sudo():
            current = rec.contractor_company_id
            if not current or current in contractors or rec._dash_attribution_parent() is not None:
                continue
            derived = rec._dash_default_attribution(contractors)
            groups[derived] = groups.get(derived, self.browse()) | self.browse(rec.id)
        return groups

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        if user._dash_is_contractor_side():
            # 營造方：一律強制自己的範圍公司（範圍不合格 → 空白；讀取規則本來就預設拒絕）
            scope = user.sudo().dash_scope_company_id if user._dash_scope_ok() else self.env['res.company']
            vals_list = [dict(vals, contractor_company_id=scope.id) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if 'contractor_company_id' in vals and self.env.user._dash_is_contractor_side():
            new_id = vals['contractor_company_id'] or False
            if any(rec.contractor_company_id.id != new_id for rec in self):
                raise AccessError('營造方帳號不能修改單據的「營造廠」歸屬，請洽監造單位。')
        field = self._dash_project_field
        if field not in vals or 'contractor_company_id' in vals:
            return super().write(vals)
        # 寫回同一個工程＝工程沒變：不把工程欄位往下送（否則觸發歸屬重算與約束——營造廠被移出工程後，
        # 舊單據重存一次就 ValidationError；合約 §0b-26）。上層的覆寫已經看過完整的 vals。
        new_id = vals[field] or False
        same = self.filtered(lambda rec: rec.sudo()[field].id == new_id)
        if same:
            rest_vals = {key: value for key, value in vals.items() if key != field}
            if rest_vals:
                super(ContractorAttributionMixin, same).write(rest_vals)
        changed = self - same
        if not changed:
            return True
        regroup = changed._dash_rederive_on_project_change(vals)
        moved = self.browse()
        for company, recs in regroup.items():
            # 依新工程重算的歸屬一起寫（不寫就會沿用原值、被約束擋下：skeptic F2 觸發 1）
            super(ContractorAttributionMixin, recs).write(dict(vals, contractor_company_id=company.id or False))
            moved |= recs
        rest = changed - moved
        return super(ContractorAttributionMixin, rest).write(vals) if rest else True

    @api.constrains(lambda self: ['contractor_company_id', self._dash_project_field]
                     if self._dash_project_field in self._fields else ['contractor_company_id'])
    def _check_contractor_company_id(self):
        for rec in self:
            company = rec.sudo().contractor_company_id
            if not company:
                continue
            if company.company_type != COMPANY_TYPE_CONTRACTOR:
                raise ValidationError(
                    '「%s」的營造廠「%s」不是營造廠（公司類型必須是施工廠商）。'
                    % (rec.sudo().display_name, company.display_name))
            parent = rec._dash_attribution_parent()
            if parent is not None and company == parent.sudo().contractor_company_id:
                continue    # 照片跟著所屬單據（見檔頭：營造廠移出工程後補舊單據的照片）
            project = rec.sudo()._dash_project()
            if company not in project.contractor_company_ids:
                raise ValidationError(
                    '「%s」的營造廠「%s」不在所屬工程「%s」的承包廠商內。'
                    % (rec.sudo().display_name, company.display_name, project.display_name or '（無工程）'))


# ── 套用 8 個營造廠層級模型（合約 §3.5）────────────────────────────────
class DailyLogSheet(models.Model):
    _name = 'daily.log.sheet'
    _inherit = ['daily.log.sheet', 'construction.contractor.attribution.mixin']
    _dash_project_field = 'supervision_project_id'


class SupervisionPhoto(models.Model):
    """照片的歸屬跟著所屬單據（合約 §0b-11）：掛在日誌、缺失、檢查、檢試驗、估驗上時取那張單據的歸屬
    ——共用工程上監造方傳到 A 單據的照片要歸 A，依工程判斷會因為工程有兩家營造廠而留空、A 看不到。
    沒掛在有歸屬的單據上（告示牌、通報單、單獨上傳）才照原規則。"""
    _name = 'supervision.photo'
    _inherit = ['supervision.photo', 'construction.contractor.attribution.mixin']

    @api.model
    def _dash_parent_fields(self):
        """照片上指向「有營造廠歸屬的單據」的來源欄位（各模組在 _photo_source_field_map 掛上來的）。

        「有歸屬」＝掛了本 mixin 的模型；不看欄位名（驗收單等模型也有同名的 contractor_company_id，意思不同）。"""
        attributed = self.env.registry[MIXIN_NAME]._inherit_children
        return [field for model_name, field in self._photo_source_field_map().items()
                if field in self._fields and model_name in attributed]

    @api.model
    def _dash_attribution_depends(self):
        parents = self._dash_parent_fields()
        return super()._dash_attribution_depends() + parents + [f'{f}.contractor_company_id' for f in parents]

    def _dash_attribution_parent(self):
        self.ensure_one()
        photo = self.sudo()
        for field in self._dash_parent_fields():
            if photo[field]:
                return photo[field]
        return None


class GeneralDefectImprovement(models.Model):
    _name = 'general.defect.improvement'
    _inherit = ['general.defect.improvement', 'construction.contractor.attribution.mixin']


class ReservationDefectImprovement(models.Model):
    _name = 'reservation.defect.improvement'
    _inherit = ['reservation.defect.improvement', 'construction.contractor.attribution.mixin']


class SupervisionTestRecord(models.Model):
    _name = 'supervision.test.record'
    _inherit = ['supervision.test.record', 'construction.contractor.attribution.mixin']


class GeneralSelfInspection(models.Model):
    _name = 'general.self.inspection'
    _inherit = ['general.self.inspection', 'construction.contractor.attribution.mixin']


class ReservationSelfInspection(models.Model):
    _name = 'reservation.self.inspection'
    _inherit = ['reservation.self.inspection', 'construction.contractor.attribution.mixin']


class PaymentEstimate(models.Model):
    _name = 'payment.estimate'
    _inherit = ['payment.estimate', 'construction.contractor.attribution.mixin']
