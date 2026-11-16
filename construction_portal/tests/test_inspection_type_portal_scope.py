# -*- coding: utf-8 -*-
"""自主檢查樣板 self.inspection.type（含明細）的前台讀取範圍（2026-11-16）。

背景：前台規則原本是 (1=1)——任何前台帳號經 RPC（/web/dataset/call_kw）都讀得到別的工程
專屬的樣板（名稱、說明、上傳的 docx 樣板檔）；明細表（項目、段落、檢查時機、量測區塊）連規則都沒有。
改成跟其他工程資料同一套：
- 全域樣板（不綁工程）：所有前台帳號可讀；
- 綁工程的樣板：該工程的參與成員可讀（工程未開始／終止時不可，同工程規則）；老闆（公司範圍）看全部；
- 明細跟著樣板（同一個條件，路徑前面多一段 type_id）。
檢查的 inspection_type_id 沒限制工程、樣板也可能事後改綁別的工程，而前台清單、首頁、日誌頁、通報單頁
以本人身分列檢查——那幾處讀樣板名稱改成只取名稱的 sudo，所以樣板改綁之後頁面照樣打得開、明細照樣讀不到。
前台樣板頁（/construction/inspection-types）本來就用 sudo＋可見工程過濾，行為不變；寫入照舊只給內部帳號。
營造方與監造方前台帳號都驗（營造方另外疊公司儀表板的範圍規則，監造方只走核心規則）。
"""

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    SUPERVISION_USER_VALS, contractor_project_vals, contractor_user_vals, make_contractor)

BOSS = 'construction_supervision_base.group_portal_subscriber'     # 老闆
FIELD = 'construction_supervision_base.group_portal_user'          # 現場人員
CHILD_MODELS = ('self.inspection.type.item', 'self.inspection.type.stage',
                'self.inspection.type.timing', 'self.inspection.type.measure')


@tagged('post_install', '-at_install', 'construction_portal')
class TestInspectionTypePortalScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.contractor = make_contractor(env, '樣板範圍測試營造')
        # 兩個工程同一家營造廠：營造方帳號在公司儀表板的範圍內兩個都看得到，差別只在是不是成員
        cls.project = cls._mk_project('樣板範圍本案', 'ITS-OWN', 'general')
        cls.other_project = cls._mk_project('樣板範圍他案', 'ITS-OTHER', 'general')
        # 本案成員：營造方與監造方各一個（都不是他案成員）
        cls.field = cls._mk_user('its_field', FIELD, contractor_user_vals(cls.contractor))
        cls.sup_field = cls._mk_user('its_sup_field', FIELD, SUPERVISION_USER_VALS)
        cls.other_member = cls._mk_user('its_other_member', FIELD, contractor_user_vals(cls.contractor))
        cls.boss = cls._mk_user('its_boss', BOSS, contractor_user_vals(cls.contractor))
        for user in (cls.field, cls.sup_field):
            cls._join(cls.project, user)
        cls._join(cls.other_project, cls.other_member)

        Type = env['self.inspection.type']
        cls.global_type = Type.create({'name': '樣板範圍全域樣板'})
        cls.own_type = Type.create({'name': '樣板範圍本案樣板', 'project_id': cls.project.id})
        cls.other_type = Type.create({'name': '樣板範圍他案樣板', 'project_id': cls.other_project.id})
        cls.outsiders = (cls.field, cls.sup_field)

    @classmethod
    def _mk_project(cls, name, code, project_type):
        return cls.env['project.project'].create({
            'name': name, 'code': code, 'project_type': project_type,
            'state': 'construction', 'company_id': cls.env.company.id,
            **contractor_project_vals(cls.contractor)})

    @classmethod
    def _mk_user(cls, login, group, side_vals):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group).id])], **side_vals})

    @classmethod
    def _join(cls, project, user):
        cls.env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})

    def _visible(self, user, records):
        return self.env[records._name].with_user(user).search([('id', 'in', records.ids)])

    # ═══ 樣板本身 ════════════════════════════════════════════════════
    def test_other_project_type_hidden_from_non_member(self):
        """洞本身：不是他案成員的前台帳號經 RPC 讀不到他案專屬樣板（原本 (1=1) 讀得到）。"""
        self.env.invalidate_all()
        for user in self.outsiders:
            with self.subTest(user=user.login):
                self.assertFalse(self.other_type.with_user(user).has_access('read'),
                                 '不是成員的前台帳號不可讀別案專屬樣板')
                self.assertNotIn(self.other_type, self._visible(user, self.other_type))

    def test_global_and_own_types_still_visible(self):
        """正當入口：全域樣板所有前台帳號可讀；本案樣板本案成員可讀；他案樣板他案成員與老闆可讀。"""
        everything = self.global_type | self.own_type | self.other_type
        self.env.invalidate_all()
        for user in self.outsiders:
            with self.subTest(user=user.login):
                self.assertEqual(self._visible(user, everything), self.global_type | self.own_type)
        self.assertEqual(self._visible(self.other_member, everything), self.global_type | self.other_type)
        self.assertEqual(self._visible(self.boss, everything), everything, '老闆是公司範圍，三種都看得到')

    # ═══ 明細跟著樣板 ════════════════════════════════════════════════
    def _children(self, itype):
        """樣板的四種明細各至少一筆（段落、檢查時機建立樣板時就有預設值）。"""
        env = self.env
        env['self.inspection.type.item'].create({
            'type_id': itype.id, 'name': '%s 項目' % itype.name, 'stage_id': itype.stage_ids[:1].id})
        env['self.inspection.type.measure'].create({
            'type_id': itype.id, 'name': '%s 量測' % itype.name, 'template': '丈量___位置'})
        out = {}
        for model in CHILD_MODELS:
            out[model] = env[model].search([('type_id', '=', itype.id)])
            self.assertTrue(out[model], '前提：%s 有資料（防恆真）' % model)
        return out

    def test_template_children_follow_parent(self):
        """別案樣板的項目、段落、檢查時機、量測區塊：非成員讀不到；他案成員、老闆讀得到；全域樣板的人人可讀。"""
        other = self._children(self.other_type)
        glob = self._children(self.global_type)
        self.env.invalidate_all()
        for model in CHILD_MODELS:
            with self.subTest(model=model):
                for user in self.outsiders:
                    self.assertFalse(self._visible(user, other[model]), '%s 不可讀別案樣板的 %s' % (user.login, model))
                    self.assertEqual(self._visible(user, glob[model]), glob[model])
                self.assertEqual(self._visible(self.other_member, other[model]), other[model])
                self.assertEqual(self._visible(self.boss, other[model]), other[model])

    # ═══ 樣板改綁別的工程之後，前台頁面照樣打得開 ═════════════════════
    def _drive(self, user, method, *args):
        """以 user 身分跑真實路由並把模板真的渲染。回傳 (values, html)；被導走時 values 為 None。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    def test_rebound_type_pages_do_not_403(self):
        """本案的檢查用到本案樣板，之後樣板被改綁到他案（非成員）：清單、首頁、日誌列表與詳情、
        預約式清單、通報單詳情都要照常渲染並顯示樣板名稱；樣板本身經 RPC 照樣讀不到。"""
        env = self.env
        rebound = env['self.inspection.type'].create({'name': '樣板範圍改綁樣板', 'project_id': self.project.id})
        today = fields.Date.today()
        # 一般式：草稿（首頁、日誌列表的待完成）＋已檢查（檢查清單、日誌詳情的本日自主檢查）
        env['progress.schedule'].create({'project_id': self.project.id, 'change_date': today}).write(
            {'state': 'active'})
        for state in ('draft', 'inspected'):
            # 分項名稱留空：清單頁是「分項名稱 or 樣板名稱」，留空才會真的去讀樣板名稱
            insp = env['general.self.inspection'].create({
                'project_id': self.project.id, 'inspection_type_id': rebound.id,
                'inspection_date': today, 'inspection_location': 'A 區', 'sub_project_name': ''})
            if state != 'draft':
                insp.sudo().write({'state': state})
        emp = env['hr.employee'].create({'name': 'its_log_emp', 'company_id': env.company.id})
        log = env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': env.company.id,
            'employee_id': emp.id, 'log_date': today})
        # 預約式：本案預約式工程＋通報單＋檢查
        res_project = self._mk_project('樣板範圍本案預約式', 'ITS-RSV', 'reservation')
        for user in self.outsiders:
            self._join(res_project, user)
        slip = env['reservation.notification.slip'].create({
            'project_id': res_project.id, 'location': '樣板範圍地點', 'slip_no': 1})
        slip.sudo().write({'state': 'in_progress'})
        env['reservation.self.inspection'].create({
            'slip_id': slip.id, 'inspection_type_id': rebound.id,
            'sub_project_name': '', 'inspection_date': today})
        # 改綁到他案（本案成員都不是他案成員）
        rebound.write({'project_id': self.other_project.id})

        pages = (
            ('首頁', self.ctrl.portal_construction_project_detail, (self.project.id,)),
            ('自主檢查清單', self.ctrl.portal_construction_inspections, (self.project.id,)),
            ('日誌列表', self.ctrl.portal_construction_daily_logs, (self.project.id,)),
            ('日誌詳情', self.ctrl.portal_construction_daily_log_detail, (self.project.id, log.id)),
            ('預約式檢查清單', self.ctrl.portal_construction_reservation_inspections, (res_project.id,)),
            ('通報單詳情', self.ctrl.portal_construction_slip_detail, (res_project.id, slip.id)),
        )
        for user in self.outsiders:
            self.assertFalse(rebound.with_user(user).has_access('read'), '前提：改綁後本案成員讀不到這個樣板')
            for label, method, args in pages:
                with self.subTest(user=user.login, page=label):
                    vals, html = self._drive(user, method, *args)
                    self.assertIsNotNone(vals, '%s 應渲染而不是被導走：%s' % (label, html))
                    self.assertIn('樣板範圍改綁樣板', html, '%s 要顯示樣板名稱' % label)
