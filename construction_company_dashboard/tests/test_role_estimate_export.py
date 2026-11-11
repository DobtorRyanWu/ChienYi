# -*- coding: utf-8 -*-
"""後台角色帳號匯出估驗四份文件（S1 fix2-X，2026-11-10），全走真的 HTTP（/web/dataset/call_button → /web/content）。

估驗表單上四顆按鈕都是 payment.estimate.action_export_estimate_template，差在 context 的 template_type
（construction_template/views/payment_estimate_export_views.xml）。規格：
1. 只能匯出讀得到的估驗：範圍外的 id（RPC 直接帶）在任何套印、寫入之前就拒（payment_estimate.py）；
2. 角色帳號只准那四種樣板類型；
3. 以本人身分套印：多營造廠共用的工程上，營造方的估驗照片只有自家的、累計實際進度只算自家的日誌；
4. 不改業務資料：匯出檔不掛在估驗上、只刪自己先前匯出的同名檔——別人上傳到估驗上、剛好同名的附件不會被刪；
   樣板使用次數＋1 是唯一的寫入（允許的副作用，這裡明確斷言）；
5. xlsx 不走試算表預覽，直接下載；四份都真的下載下來、打開檔案比對夾具的值。
營造廠主管、控台讀取帳號、前台營造帳號照樣被方法閘門擋（閘門只放角色帳號，method_gate.ROLE_ONLY_METHODS）。

夾具：監造公司 S、營造廠 A、B；共用工程 P（S，A＋B）、他案 PO（另一家監造公司 S2，B）。
估驗：P 上 A 的（est_a，今天）、P 上 B 的（est_b，明天）、PO 上 B 的（est_o）。照片、日誌 A、B 各一。
期望值由測試依夾具獨立寫出。construction_template 沒裝的庫整個類別略過（本模組不依賴它）。
"""
import base64
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.construction_company_dashboard.models.method_gate import GATE_NOTE

from .test_role_accounts import ROLE_BOSS, ROLE_MANAGER, ROLE_SUPERVISION
from .test_scope_rules import CONSOLE_GROUP, MANAGER_GROUP, PORTAL_LEADER, SUPERVISOR_ADMIN, TOTP_FIXTURE_SECRET

MODULE = 'construction_company_dashboard'
EXPORT_METHOD = 'action_export_estimate_template'
# 表單上四顆按鈕的 template_type（計價單那顆不帶 context，用方法的預設值；以 None 表示「不帶」）
BUTTON_TYPES = (None, 'invoice_detail', 'invoice_photo', 'estimate_progress_report')
XLSX_TYPES = (None, 'invoice_detail')
# 同一個方法也套得出的其他類型：表單上藏起來的「匯出進度報告」（invisible="1"）
HIDDEN_TYPE = 'progress_report'
SCOPE_DENY = '唯讀帳號只能匯出自己讀得到的估驗'
TYPE_DENY = '唯讀帳號只能匯出估驗表單上的四份文件'
EXPORT_MARKER = 'document.template.export'

PROJECT_NAME = 'ROLE-EX 匯出測試工程'
TASK_NAME = 'ROLE-EX 工項甲'
PHOTO_A = 'ROLE-EX 照片甲'
PHOTO_B = 'ROLE-EX 照片乙'
# 本日實際進度（%）：A、B 各一張日誌；營造方只讀得到 A 的，累計＝A；監造方讀得到兩張，累計＝A＋B
PROGRESS_A = 3.17
PROGRESS_B = 5.29
ESTIMATE_QTY = 2.0
UNIT_PRICE = 100.0
IMAGE_SIZE = (200, 150)
# 照片拍攝時間＝現在往前推的天數：換成台灣日期仍在今天（估驗日）之前
PHOTO_DAYS_AGO = 2
OK_STATUS = 200


def _png():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', IMAGE_SIZE, (120, 160, 200)).save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue())


def _xlsx_text(content):
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    return '\n'.join(str(cell.value) for sheet in book.worksheets for row in sheet.iter_rows()
                     for cell in row if cell.value is not None)


def _docx_text(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return archive.read('word/document.xml').decode('utf-8')


@tagged('post_install', '-at_install', MODULE)
class TestRoleEstimateExportHttp(HttpCase):

    PASSWORD = 'Role-export-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        if 'document.template' not in env or not hasattr(env['payment.estimate'], EXPORT_METHOD):
            raise unittest.SkipTest('construction_template 沒裝')
        today = fields.Date.today()
        cls.co_a = env['res.company'].create({'name': 'ROLE-EX 營造 A', 'company_type': 'contractor'})
        cls.co_b = env['res.company'].create({'name': 'ROLE-EX 營造 B', 'company_type': 'contractor'})
        cls.co_s = env['res.company'].create({'name': 'ROLE-EX 監造 S', 'company_type': 'supervision'})
        cls.co_s2 = env['res.company'].create({'name': 'ROLE-EX 監造 S2', 'company_type': 'supervision'})

        def project(name, code, company, contractors):
            return env['project.project'].create({
                'name': name, 'code': code, 'project_type': 'general', 'state': 'construction',
                'company_id': company.id, 'contractor_company_ids': [(6, 0, contractors.ids)]})
        cls.p_shared = project(PROJECT_NAME, 'ROLE-EX', cls.co_s, cls.co_a | cls.co_b)
        cls.p_other = project('ROLE-EX 他案', 'ROLE-EXO', cls.co_s2, cls.co_b)
        # 日誌要求工程有進度表（construction_progress daily_log_sheet._check_progress_schedule_exists）
        env['progress.schedule'].create({'project_id': cls.p_shared.id, 'change_date': today}).write({'state': 'active'})
        cls.task = env['project.task'].create({
            'name': TASK_NAME, 'project_id': cls.p_shared.id, 'item_no': '1', 'unit': '式',
            'planned_qty': 10.0, 'unit_price': UNIT_PRICE})

        def estimate(project, contractor, day):
            return env['payment.estimate'].create({
                'project_id': project.id, 'estimate_date': day, 'contractor_company_id': contractor.id})
        cls.est_a = estimate(cls.p_shared, cls.co_a, today)
        env['payment.estimate.line'].create({
            'estimate_id': cls.est_a.id, 'task_id': cls.task.id, 'estimate_qty': ESTIMATE_QTY, 'unit_price': UNIT_PRICE})
        cls.est_b = estimate(cls.p_shared, cls.co_b, fields.Date.add(today, days=1))
        cls.est_o = estimate(cls.p_other, cls.co_b, today)

        # 本期照片（拍攝日落在本期區間內）與日誌：A、B 各一
        image = _png()
        for contractor, description in ((cls.co_a, PHOTO_A), (cls.co_b, PHOTO_B)):
            attachment = env['ir.attachment'].create({
                'name': 'role-ex.png', 'datas': image, 'mimetype': 'image/png', 'res_model': 'supervision.photo'})
            # shot_date 是由 shot_at 以台灣日期算的（construction_photo _compute_shot_date，寫 shot_date 會被蓋掉）：
            # 不給 shot_at 就是「現在」，UTC 16:00 以後台灣已是明天、落在本期之外——測試會隨時段紅綠（fix3 發現）
            env['supervision.photo'].create({
                'project_id': cls.p_shared.id, 'attachment_id': attachment.id, 'description': description,
                'shot_at': fields.Datetime.subtract(fields.Datetime.now(), days=PHOTO_DAYS_AGO),
                'contractor_company_id': contractor.id})
        employee = env['hr.employee'].create({'name': 'ROLE-EX 填表人', 'company_id': cls.co_s.id})
        for days, contractor, progress in ((2, cls.co_a, PROGRESS_A), (3, cls.co_b, PROGRESS_B)):
            env['daily.log.sheet'].create({
                'supervision_project_id': cls.p_shared.id, 'employee_id': employee.id,
                'log_date': fields.Date.subtract(today, days=days), 'contractor_company_id': contractor.id,
                'daily_actual_progress': progress})

        # 帳號（角色帳號都啟用兩步驟驗證；沒啟用的角色帳號範圍不合格、讀不到資料）
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, company, companies, scope=None, **extra):
            vals = dict({'name': login, 'login': login, 'password': cls.PASSWORD,
                         'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                         'company_id': company.id, 'company_ids': [(6, 0, companies.ids)]}, **extra)
            if scope:
                vals['dash_scope_company_id'] = scope.id
            record = Users.create(vals)
            record.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
            return record
        contractor_companies = cls.co_s | cls.co_a
        cls.cb = user('role_ex_cb', [MANAGER_GROUP, ROLE_BOSS], cls.co_s, contractor_companies, cls.co_a)
        cls.cm = user('role_ex_cm', [MANAGER_GROUP, ROLE_MANAGER], cls.co_s, contractor_companies, cls.co_a)
        cls.sb = user('role_ex_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s, cls.co_s)
        cls.sm = user('role_ex_sm', [ROLE_SUPERVISION, ROLE_MANAGER], cls.co_s, cls.co_s)
        for manager in (cls.cm, cls.sm):
            env['supervision.project.member'].create({'project_id': cls.p_shared.id, 'user_id': manager.id})
        cls.roles = (cls.cb, cls.cm, cls.sb, cls.sm)
        cls.contractor_roles = (cls.cb, cls.cm)
        # 閘門照擋的既有帳號
        cls.mgr_a = user('role_ex_mgr_a', [MANAGER_GROUP], cls.co_s, contractor_companies, cls.co_a)
        cls.console = user('role_ex_console', [CONSOLE_GROUP], cls.co_s, cls.co_s)
        cls.portal_a = user('role_ex_portal_a', [PORTAL_LEADER], cls.co_a, contractor_companies, cls.co_a,
                            is_contractor_org=True)
        env['supervision.project.member'].create({'project_id': cls.p_shared.id, 'user_id': cls.portal_a.id})
        # 監造方後台人員（對照：照舊把匯出檔掛在估驗上、xlsx 照舊開預覽）
        cls.sup = Users.create({'name': 'role_ex_sup', 'login': 'role_ex_sup', 'password': cls.PASSWORD,
                                'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref(SUPERVISOR_ADMIN).id])],
                                'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        env.registry.clear_cache()

    # ── 工具 ─────────────────────────────────────────────────────────
    def _login(self, user):
        """已啟用 TOTP 的帳號：核心對非互動式登入只收 API 金鑰；測試裡當互動式登入（同 test_role_accounts）。"""
        with patch.object(type(self.env['res.users']), '_rpc_api_keys_only', lambda self: False):
            self.authenticate(user.login, self.PASSWORD)

    def _export(self, user, estimate, template_type):
        """以 user 按估驗表單上的匯出按鈕：('ok', 動作) 或 ('error', 例外名, 訊息)。"""
        self._login(user)
        context = {'allowed_company_ids': user.company_ids.ids}
        if template_type:
            context['template_type'] = template_type
        response = self.url_open('/web/dataset/call_button', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
                'model': 'payment.estimate', 'method': EXPORT_METHOD, 'args': [[estimate.id]],
                'kwargs': {'context': context}}}), headers={'Content-Type': 'application/json'})
        body = response.json()
        if 'error' in body:
            data = body['error'].get('data', {})
            return 'error', data.get('name', ''), data.get('message', '')
        return 'ok', body['result']

    @staticmethod
    def _download_action(action):
        """資料有需要注意的地方時，下載包在提示的 next 裡（template_export_mixin._wrap_with_warnings）。"""
        if action.get('type') == 'ir.actions.client' and action.get('tag') == 'display_notification':
            return action['params']['next']
        return action

    def _download(self, user, estimate, template_type):
        outcome = self._export(user, estimate, template_type)
        label = f'{user.login} × {template_type or "estimate_report"}'
        self.assertEqual(outcome[0], 'ok', f'{label}：{outcome}')
        action = self._download_action(outcome[1])
        self.assertEqual(action.get('type'), 'ir.actions.act_url', f'{label}：直接下載（不走試算表預覽）：{action}')
        response = self.url_open(action['url'])
        self.assertEqual(response.status_code, OK_STATUS, f'{label}：下載得到')
        return response.content, action

    def _template(self, template_type):
        return self.env['document.template'].sudo().get_template_for_report(
            template_type or 'estimate_report', project_id=self.p_shared.id)

    def _usage(self):
        self.env.invalidate_all()
        return {t: self._template(t).usage_count for t in BUTTON_TYPES + (HIDDEN_TYPE,)}

    def _business_state(self):
        """估驗本身、估驗上的附件與訊息：匯出不能改到任何一樣。"""
        self.env.invalidate_all()
        Attachment = self.env['ir.attachment'].sudo()
        return {
            estimate.id: (estimate.write_date, estimate.message_ids.ids,
                          Attachment.search([('res_model', '=', 'payment.estimate'), ('res_id', '=', estimate.id)]).ids)
            for estimate in (self.est_a | self.est_b | self.est_o)}

    # ── 1＋3＋5：四個角色 × 四份文件，打開檔案比對 ──────────────────────
    def test_four_roles_export_four_documents(self):
        for template_type in BUTTON_TYPES + (HIDDEN_TYPE,):
            self.assertTrue(self._template(template_type), f'前提：{template_type} 有可用的樣板')
        before = self._business_state()
        usage = self._usage()
        exports = 0
        for user in self.roles:
            contractor_side = user in self.contractor_roles
            for template_type in BUTTON_TYPES:
                label = f'{user.login} × {template_type or "estimate_report"}'
                content, action = self._download(user, self.est_a, template_type)
                exports += 1
                text = _xlsx_text(content) if template_type in XLSX_TYPES else _docx_text(content)
                if template_type in (None, 'invoice_photo', 'estimate_progress_report'):
                    self.assertIn(PROJECT_NAME, text, f'{label}：檔案裡有工程名稱')
                if template_type == 'invoice_detail':
                    self.assertIn(TASK_NAME, text, f'{label}：估驗詳細表有工項')
                if template_type == 'invoice_photo':
                    self.assertIn(PHOTO_A, text, f'{label}：有自家（A）的照片')
                    self.assertEqual(PHOTO_B in text, not contractor_side,
                                     f'{label}：別家營造廠（B）的照片只有監造方看得到')
                if template_type == 'estimate_progress_report':
                    expected = PROGRESS_A if contractor_side else PROGRESS_A + PROGRESS_B
                    other = PROGRESS_A + PROGRESS_B if contractor_side else PROGRESS_A
                    self.assertIn('%.2f' % expected, text, f'{label}：累計實際進度＝讀得到的日誌')
                    self.assertNotIn('%.2f' % other, text, f'{label}：累計實際進度不含讀不到的日誌')
                # 匯出檔：本人擁有、不掛在單據上、帶匯出標記；別的角色帳號下載不到
                attachment_id = int(action['url'].split('/web/content/')[1].split('?')[0])
                attachment = self.env['ir.attachment'].sudo().browse(attachment_id)
                self.assertEqual((attachment.res_model, attachment.res_id, attachment.create_uid, attachment.description),
                                 (False, 0, user, EXPORT_MARKER), f'{label}：匯出檔不掛在估驗上')
        # 別人的匯出檔下載不到（核心：沒有掛單據的附件只有建立者與系統管理者讀得到）
        mine = self.env['ir.attachment'].sudo().search([('create_uid', '=', self.sb.id),
                                                        ('description', '=', EXPORT_MARKER)], limit=1)
        self._login(self.cm)
        self.assertIn(self.url_open(f'/web/content/{mine.id}?download=true').status_code, (403, 404),
                      '營造主管下載不到監造老闆的匯出檔')
        # 4：業務資料一樣都沒變；唯一的寫入是樣板使用次數（每匯出一次＋1）
        self.assertEqual(self._business_state(), before, '估驗本身、估驗上的附件與訊息都沒變')
        after = self._usage()
        self.assertEqual(sum(after[t] - usage[t] for t in BUTTON_TYPES), exports, '樣板使用次數每匯出一次＋1')
        self.assertEqual(after[HIDDEN_TYPE], usage[HIDDEN_TYPE])

    # ── 1：範圍外的估驗；2：其他樣板類型 ──────────────────────────────
    def test_out_of_scope_and_other_types_rejected(self):
        before = self._business_state()
        usage = self._usage()
        outside = {self.cb: (self.est_b, self.est_o), self.cm: (self.est_b, self.est_o),
                   self.sb: (self.est_o,), self.sm: (self.est_o,)}
        for user in self.roles:
            for estimate in outside[user]:
                outcome = self._export(user, estimate, None)
                self.assertEqual(outcome[0], 'error', f'{user.login} × 估驗 {estimate.id}：範圍外要被拒')
                self.assertIn('AccessError', outcome[1])
                self.assertIn(SCOPE_DENY, outcome[2], f'{user.login}：是範圍檢查擋的（在任何套印之前）')
            outcome = self._export(user, self.est_a, HIDDEN_TYPE)
            self.assertEqual(outcome[0], 'error', f'{user.login}：{HIDDEN_TYPE} 不在表單的四顆按鈕裡')
            self.assertIn(TYPE_DENY, outcome[2])
        self.assertEqual(self._usage(), usage, '被拒的匯出沒有動到樣板使用次數')
        self.assertEqual(self._business_state(), before)
        self.assertFalse(self.env['ir.attachment'].sudo().search_count([('description', '=', EXPORT_MARKER),
                                                                        ('create_uid', 'in', [u.id for u in self.roles])]),
                         '被拒的匯出沒有產生任何檔案')
        # 反證：監造方老闆讀得到 est_b（範圍內），匯得出來
        self._download(self.sb, self.est_b, None)

    # ── 4：別人上傳到估驗上、剛好同名的附件不會被刪；重匯只清自己的 ────────────
    def test_same_named_upload_survives_and_reexport_replaces_own(self):
        content, action = self._download(self.cb, self.est_a, None)
        first = self.env['ir.attachment'].sudo().browse(int(action['url'].split('/web/content/')[1].split('?')[0]))
        filename = first.name
        upload = self.env['ir.attachment'].with_user(self.sup).create({
            'name': filename, 'raw': b'ROLE-EX uploaded by staff', 'res_model': 'payment.estimate',
            'res_id': self.est_a.id})
        for user in (self.cb, self.sb):
            self._download(user, self.est_a, None)
        self.env.invalidate_all()
        self.assertTrue(upload.exists(), '監造方人員上傳到估驗上的同名附件還在')
        self.assertEqual(upload.raw, b'ROLE-EX uploaded by staff')
        Attachment = self.env['ir.attachment'].sudo()
        own = Attachment.search([('name', '=', filename), ('create_uid', '=', self.cb.id),
                                 ('description', '=', EXPORT_MARKER)])
        self.assertEqual(len(own), 1, '重匯只留最新一份自己的')
        self.assertNotEqual(own, first, '舊的那份被換掉')
        self.assertEqual(Attachment.search_count([('name', '=', filename), ('create_uid', '=', self.sb.id),
                                                  ('description', '=', EXPORT_MARKER)]), 1,
                         '別的角色帳號匯出同一份不會刪掉營造老闆的')

    # ── 閘門：既有受限帳號照擋；監造方後台人員照舊 ─────────────────────────
    def test_existing_restricted_accounts_still_blocked(self):
        for user in (self.mgr_a, self.console, self.portal_a):
            for template_type in BUTTON_TYPES:
                outcome = self._export(user, self.est_a, template_type)
                self.assertEqual(outcome[0], 'error', f'{user.login} × {template_type}：要被擋')
                self.assertIn(GATE_NOTE, outcome[2], f'{user.login}：是方法閘門擋的')
        self.assertFalse(self.env['ir.attachment'].sudo().search_count([
            ('create_uid', 'in', (self.mgr_a | self.console | self.portal_a).ids)]), '沒有產生任何檔案')

    def test_backend_staff_unchanged(self):
        """監造方後台人員：匯出檔照舊掛在估驗上；xlsx 有裝試算表預覽就照舊開預覽。"""
        outcome = self._export(self.sup, self.est_a, 'invoice_photo')
        self.assertEqual(outcome[0], 'ok', outcome)
        self.env.invalidate_all()
        attached = self.env['ir.attachment'].sudo().search([('res_model', '=', 'payment.estimate'),
                                                            ('res_id', '=', self.est_a.id)])
        self.assertTrue(attached.filtered(lambda a: a.name.endswith('.docx')), '照舊掛在估驗上')
        outcome = self._export(self.sup, self.est_a, 'invoice_detail')
        self.assertEqual(outcome[0], 'ok', outcome)
        action = self._download_action(outcome[1])
        if hasattr(self.env['ir.attachment'], 'action_open_spreadsheet_preview'):
            self.assertNotEqual(action.get('type'), 'ir.actions.act_url', 'xlsx 照舊開試算表預覽')
