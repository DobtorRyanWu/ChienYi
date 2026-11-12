# -*- coding: utf-8 -*-
"""S3 全域公司規則的寫入面（S3 fix1，2026-11-11）。

為什麼要有
----------
18 條全域公司規則（rule_company_global_<模型>，在 construction_payment／construction_contract_change／
construction_progress／construction_general／construction_supervision_base 的 security/company_rules.xml）
讀、刪、建都擋得住，**寫入只擋一半**：核心 write 只在寫入**前**用舊值檢查 ir.rule（odoo/models.py write 開頭的
``self.check_access('write')``），寫完不再檢查（只有 create 有寫後檢查）。於是讀得到、寫得了自己公司紀錄的人，
可以把它的工程或父單改成別家公司的——請款、計量驗收（＋明細）、非契約工項、進度報告明細、工項版本實測寫得進去
（S3 審查 skeptic F1；估驗、變更單的 project_id 另有 relational_input_guard 擋）。

這裡補兩件事，只對**非 sudo** 的 write、而且只在 vals 改到下表的欄位時（效能）：

1. **寫後再檢查**：寫完以寫入者身分 ``check_access('write')``；不符合規則就 AccessError（例外讓整個請求的交易回滾，
   與核心 create 的寫後檢查同一種語意）。
2. **有工程的單不能變成沒有工程**（UserError）：估驗、變更單、變更明細的規則對「工程空白」放行建立者
   （先存空單再「匯入工程案件」），所以把有工程的單清空工程、或把明細改掛到自己的空工程變更單上，
   第 1 點照樣會過，但同事從此看不到它（S3 審查 red-team F1）。建立者自己清也一樣擋。
3. **表上的 related 欄位不能直接寫**（UserError，S3 fix2）：company_id（工程的公司）、非契約工項明細的 project_id
   （估驗的工程）跟著來源走。同屬兩家公司的帳號直接改它，第 1 點會過（新公司也在他的公司裡），但值就和工程對不上：
   原公司的同事看不到、另一家公司的人看得到（S3 第二輪審查 skeptic F2）。要換請改來源（工程、父單）。
4. **已經有單據的工程，只有系統管理者與代操作員能改公司**（UserError，2026-11-12 使用者決定「1b」；同日追加「代操跟管理者都要可以做」）：第 3 點擋住直接改單據的
   公司，但改上游——工程的 company_id——底下整串單據的公司跟著重算、一起搬到別家公司，只屬原公司的同事從此看不到
   （S3 第三輪審查 red-team R1；要同屬兩家公司又有工程寫權的人才做得到）。「單據」＝下表的模型（不另寫清單），
   連到工程的欄位路徑由 _project_paths() 從表推；封存的也算。只在非 sudo、值真的有變時查；批次 write 逐個工程查。
   正當流程（grep 全 repo，報告 project_company_guard_report.md）沒有以非 sudo 改工程公司的：前台「修改工程資訊」
   （/construction/<id>/update）是 sudo 寫入、只限未開始的工程，不經這道檢查。

sudo（系統內部流程）不檢查。正當的非 sudo 改寫（grep 全 repo，S3_fix1_report.md W-3）只有「匯入工程案件」
（estimate.import.wizard 替工程空白的估驗設工程）與契約變更精靈（contract.change.wizard 替變更單設工程），
都是「空白 → 自己公司的工程」，兩道檢查都會過。
測試：construction_company_dashboard/tests/test_company_isolation.py（TestCompanyIsolation 的 test_reparent_*、
test_related_*、test_blank_project_*、test_line_*、test_legit_*；下表由 test_write_guard_table_matches_rules
從資料庫的規則推出來兩個方向比，表上每一格另有一格行為測試）。
"""
from odoo import _, models
from odoo.exceptions import UserError

# 模型 → 全域公司規則用得到、而且寫得進去的欄位。規則用 stored related 欄位（company_id 等）的，同時列來源欄位與
# related 欄位本身（related 欄位的 readonly 只是畫面屬性，ORM write 照樣把值寫進欄位；非 sudo 直接寫由第 3 點擋）。
# 這張表是規則 domain 的第二份：改規則就要改這裡，test_write_guard_table_matches_rules 會紅。
# report.project.task.user 是核心 SQL 檢視（寫不了），不在表上。
COMPANY_RULE_FIELDS = {
    'payment.claim': frozenset({'project_id'}),
    'payment.estimate': frozenset({'project_id'}),
    'payment.estimate.line': frozenset({'estimate_id'}),
    'payment.estimate.extra.item': frozenset({'project_id'}),
    'payment.estimate.extra.line': frozenset({'estimate_id', 'project_id'}),
    'work.acceptance': frozenset({'project_id'}),
    'work.acceptance.line': frozenset({'acceptance_id'}),
    'contract.change.order': frozenset({'project_id', 'company_id'}),
    'contract.change.order.line': frozenset({'change_order_id', 'company_id'}),
    'progress.schedule': frozenset({'project_id', 'company_id'}),
    'progress.schedule.line': frozenset({'schedule_id', 'company_id'}),
    'general.progress.report': frozenset({'project_id', 'company_id'}),
    'general.progress.report.line': frozenset({'report_id'}),
    'general.realtime.profit': frozenset({'project_id', 'company_id'}),
    'general.realtime.profit.cost': frozenset({'profit_id'}),
    'profit.loss.entry': frozenset({'project_id', 'company_id'}),
    'project.task.version': frozenset({'task_id'}),
}
# 模型 → 「這筆有沒有工程」的路徑：規則對工程空白放行建立者的那三個模型（#2 估驗、#8 變更單、#9 變更明細）
PROJECT_PATHS = {
    'payment.estimate': 'project_id',
    'contract.change.order': 'project_id',
    'contract.change.order.line': 'change_order_id.project_id',
}
# 第 4 點：已經有單據的工程，只有這些群組（系統管理者、代操作員）能改公司
COMPANY_MOVE_GROUPS = ('base.group_system', 'construction_supervision_base.group_operator')
PROJECT_MODEL = 'project.project'
# 表外的父單模型（工項版本 → 工項）沿這個欄位連到工程
PROJECT_FIELD = 'project_id'


def _path_to_project(env, model_name, seen=frozenset()):
    """model_name 經哪條欄位路徑連到工程（例 'estimate_id.project_id'）；推不出來回 None。

    表上的模型只看表上的欄位（規則用得到的那幾個）：有直接指向工程的 many2one 就用它，否則沿父單欄位往上推；
    表外的模型（工項）用它的 project_id。
    """
    Model = env[model_name]
    names = sorted(COMPANY_RULE_FIELDS.get(model_name, {PROJECT_FIELD}))
    links = [Model._fields[name] for name in names
             if name in Model._fields and Model._fields[name].type == 'many2one']
    for field in links:
        if field.comodel_name == PROJECT_MODEL:
            return field.name
    for field in links:
        if field.comodel_name in seen or field.comodel_name not in env:
            continue
        sub = _path_to_project(env, field.comodel_name, seen | {model_name})
        if sub:
            return f'{field.name}.{sub}'
    return None


def _project_paths(env):
    """{模型: 連到工程的欄位路徑}，表上每個已安裝的模型一列（本模組不依賴那幾個模組，沒裝就不會有那種單據）。

    已安裝卻推不出路徑就 raise——不可以靜默略過那種單據（略過＝那種單據不算，工程照樣搬得走）。
    """
    paths = {}
    for model_name in COMPANY_RULE_FIELDS:
        if model_name not in env:
            continue
        path = _path_to_project(env, model_name)
        if not path:
            raise UserError(_('%s：推不出連到工程的欄位（company_rule_write_guard.COMPANY_RULE_FIELDS）', model_name))
        paths[model_name] = path
    return paths


class Base(models.AbstractModel):
    _inherit = 'base'

    def write(self, vals):
        watched = COMPANY_RULE_FIELDS.get(self._name)
        if not self or not watched or self.env.su or watched.isdisjoint(vals):
            return super().write(vals)
        # 第 3 點：related 欄位（例 company_id＝工程的公司）跟著來源走，寫入前就拒（不會先寫進去再回滾）
        related = [name for name in sorted(watched.intersection(vals)) if self._fields[name].related]
        if related:
            raise UserError(_(
                '%(model)s：「%(fields)s」跟著「%(sources)s」帶出來，不能直接改——改了會和上層對不上，'
                '同事可能從此看不到。要換請改「%(sources)s」。',
                model=self._description,
                fields='、'.join(self._fields[name].string for name in related),
                sources='、'.join(dict.fromkeys(
                    self._fields[self._fields[name].related.split('.', 1)[0]].string for name in related))))
        path = PROJECT_PATHS.get(self._name)
        # 以寫入者身分讀（讀不到的紀錄在這裡就 AccessError，與 write 本身的寫前檢查同結果）
        had_project = self.filtered(path) if path else self.browse()
        result = super().write(vals)
        # 寫完以 sudo 讀：清空工程之後，非建立者已經讀不到這筆（讀它會先丟 AccessError，蓋掉下面要給的說明）
        lost = had_project.sudo().filtered(lambda record: not record.mapped(path))
        if lost:
            raise UserError(_(
                '%(model)s：已經有工程的紀錄不能改成沒有工程（清空工程、或改掛到沒有工程的單）——'
                '工程空白的單只有建立者看得到，改了同事就看不到。要換工程請直接選另一個工程。（%(names)s）',
                model=self._description, names='、'.join(lost.mapped('display_name'))))
        self.check_access('write')
        return result


class ProjectProject(models.Model):
    _inherit = 'project.project'

    def write(self, vals):
        # 第 4 點：已經有單據的工程改公司，只有系統管理者與代操作員能改（寫入前就拒，不會先寫進去再回滾）
        if ('company_id' in vals and not self.env.su
                and not any(self.env.user.has_group(group) for group in COMPANY_MOVE_GROUPS)):
            self._check_company_move_allowed(vals['company_id'])
        return super().write(vals)

    def _check_company_move_allowed(self, new_company):
        """self 裡公司真的會變、而且底下已經有單據（含封存）的工程 → UserError，列出工程名稱。"""
        new_company_id = new_company.id if isinstance(new_company, models.BaseModel) else (new_company or False)
        moving = self.filtered(lambda project: project.company_id.id != new_company_id)
        if not moving:
            return
        env = self.env(su=True, context=dict(self.env.context, active_test=False))
        paths = _project_paths(env)
        blocked = moving.browse([
            project.id for project in moving
            if any(env[model_name].search_count([(path, '=', project.id)], limit=1)
                   for model_name, path in paths.items())])
        if blocked:
            raise UserError(_(
                '工程「%(names)s」已經有估驗等單據，改公司會讓底下的單據跟著搬到別家公司，只有系統管理者或代操作員能改。',
                names='、'.join(blocked.sudo().mapped('display_name'))))
