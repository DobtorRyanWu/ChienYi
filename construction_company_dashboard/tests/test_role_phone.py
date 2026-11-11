# -*- coding: utf-8 -*-
"""S2（2026-11-11）：後台角色帳號的手機能力＝同方別、同層級的舊前台角色帳號（規格 S2_spec.md）。

* 能力矩陣（A、驗收 1）：四種角色帳號 × 每一個前台能力（入口顯示、路由放行、寫入結果），與舊前台帳號並排；
  差異只能是 ALLOWED_DIFFERENCES（必守的差異之外的，逐條寫理由）。矩陣由這支測試算出來、逐格比對，
  另外把每一格印進 log（S2_MATRIX|…），報告的矩陣表從 log 取，不是人工填。
* 畫面與路由同一個判斷：入口顯示（真的渲染頁面）＝路由放行。
* F5（B）、轉換與改回（C）、第一次登入與 TOTP（D）、登入導向與切換入口（E）、手機動作的通知（H）、水位（A 的「其他」類）。
群組定義在本模組；夾具與 construction_portal 的前台測試同一套寫法（dash_fixtures）。
"""
import logging
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from .test_scope_rules import require_totp
from odoo.addons.construction_portal.tests.dash_fixtures import (
    MANAGER_TOTP_SECRET, SUPERVISION_USER_VALS, contractor_user_vals, make_contractor)

_logger = logging.getLogger(__name__)
MODULE = 'construction_company_dashboard'
D = MODULE
CONTRACTOR_MARKER = f'{D}.group_contractor_manager'
ROLE_BOSS = f'{D}.group_role_boss'
ROLE_MANAGER = f'{D}.group_role_manager'
ROLE_SUPERVISION = f'{D}.group_role_supervision'
P_BOSS = 'construction_supervision_base.group_portal_subscriber'
P_LEADER = 'construction_supervision_base.group_portal_leader'
P_FIELD = 'construction_supervision_base.group_portal_user'
P_VIEWER = 'construction_supervision_base.group_portal_viewer'
ORG_SUPERVISION = 'construction_supervision_base.group_supervision_org'
ORG_CONTRACTOR = 'construction_supervision_base.group_contractor_org'
ENGINEERING_MANAGER = 'construction_supervision_base.group_engineering_manager'
INBOX_GROUP = 'mail.group_mail_notification_type_inbox'
COMPANY_TYPE_SUPERVISION = 'supervision'
SIDE_CONTRACTOR, SIDE_SUPERVISION = 'contractor', 'supervision'
LEVEL_BOSS, LEVEL_MANAGER = 'boss', 'manager'
PAIRS = ((SIDE_CONTRACTOR, LEVEL_BOSS), (SIDE_CONTRACTOR, LEVEL_MANAGER),
         (SIDE_SUPERVISION, LEVEL_BOSS), (SIDE_SUPERVISION, LEVEL_MANAGER))
MATRIX_MARK = 'S2_MATRIX'
# 日誌超過幾天自動鎖定（construction_daily_log LOCK_DAYS＝14）；夾具用更舊的日期
LOCKED_LOG_DAYS_AGO = 20
PNG_BYTES = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
             b'\x00\x00\x00\rIDATx\xdac\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82')
# 必守的差異以外、角色帳號比舊前台帳號少的能力：(方別, 能力) → 理由（不可以有「角色帳號比較多」的差異）
# S2 原本有一條：監造方的意見回饋入口（角色帳號沒開）。S2 fix2-W（使用者 11-11 決定開）起拿掉，矩陣與舊帳號全部相同
ALLOWED_DIFFERENCES = {}


def _mail_sender_config(env):
    """測試交易內設好寄件人（dev 沒設 catchall／default.from）：舊前台帳號本來就會寄 email 給外部追蹤者，
    不設的話測試模式送信時 build_email 丟錯誤、log 一堆 ERROR（不是這裡要驗的東西）。"""
    params = env['ir.config_parameter'].sudo()
    params.set_param('mail.catchall.domain', 'example.invalid')
    params.set_param('mail.default.from', 'notifications')


class _Upload:
    def __init__(self, name='s2.png', data=PNG_BYTES, mimetype='image/png'):
        self.filename, self._data, self.mimetype, self.content_type = name, data, mimetype, mimetype

    def read(self):
        return self._data


class RolePhoneCase(TransactionCase):
    """夾具：監造公司 S、營造廠 A；工程 P（一般式）、R（預約式）、P_DRAFT（未開始）都在 S、承攬 A。
    帳號（四對）：舊前台帳號（營造老闆、營造主管、監造老闆、監造主管）與同方別同層級的後台角色帳號（都開 TOTP）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        _mail_sender_config(env)
        cls.co_s = env['res.company'].create({'name': 'S2 監造 S', 'company_type': COMPANY_TYPE_SUPERVISION})
        cls.co_a = make_contractor(env, 'S2 營造 A')
        cls.today = fields.Date.today()
        cls.p = cls._project('S2-P', 'general', 'construction')
        cls.r = cls._project('S2-R', 'reservation', 'construction')
        cls.p_draft = cls._project('S2-PD', 'general', 'draft')
        cls.projects = cls.p | cls.r | cls.p_draft
        Users = env['res.users'].with_context(no_reset_password=True)

        def portal(login, group, side):
            vals = {'name': login, 'login': login, 'groups_id': [(6, 0, [env.ref(group).id])],
                    'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]}
            vals.update(contractor_user_vals(cls.co_a) if side == SIDE_CONTRACTOR else SUPERVISION_USER_VALS)
            return Users.create(vals)

        cls.old = {
            (SIDE_CONTRACTOR, LEVEL_BOSS): portal('s2_old_cb', P_BOSS, SIDE_CONTRACTOR),
            (SIDE_CONTRACTOR, LEVEL_MANAGER): portal('s2_old_cm', P_LEADER, SIDE_CONTRACTOR),
            (SIDE_SUPERVISION, LEVEL_BOSS): portal('s2_old_sb', P_BOSS, SIDE_SUPERVISION),
            (SIDE_SUPERVISION, LEVEL_MANAGER): portal('s2_old_sm', P_LEADER, SIDE_SUPERVISION),
        }
        cls.new = {
            (SIDE_CONTRACTOR, LEVEL_BOSS): cls._role('s2_new_cb', SIDE_CONTRACTOR, ROLE_BOSS),
            (SIDE_CONTRACTOR, LEVEL_MANAGER): cls._role('s2_new_cm', SIDE_CONTRACTOR, ROLE_MANAGER),
            (SIDE_SUPERVISION, LEVEL_BOSS): cls._role('s2_new_sb', SIDE_SUPERVISION, ROLE_BOSS),
            (SIDE_SUPERVISION, LEVEL_MANAGER): cls._role('s2_new_sm', SIDE_SUPERVISION, ROLE_MANAGER),
        }
        # 前台現場人員（S2 fix1-R：「現場人員只能改自己建的」那一格要有人量）：營造方、監造方各一
        cls.field_users = portal('s2_old_cf', P_FIELD, SIDE_CONTRACTOR) | portal('s2_old_sf', P_FIELD, SIDE_SUPERVISION)
        for user in list(cls.old.values()) + list(cls.new.values()) + list(cls.field_users):
            for project in cls.projects:
                env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})
        cls.staff = Users.create({
            'name': 's2_staff', 'login': 's2_staff',
            'groups_id': [(6, 0, [env.ref('base.group_user').id,
                                  env.ref('construction_supervision_base.group_supervisor_admin').id])],
            'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        cls.emp = env['hr.employee'].create({'name': 'S2 填表人', 'company_id': cls.co_s.id})
        cls.itype = env['self.inspection.type'].create({'name': 'S2 檢查類型'})
        cls._slip_no = 0

    @classmethod
    def _project(cls, code, ptype, state):
        env = cls.env
        project = env['project.project'].create({
            'name': f'{code} 角色帳號手機測試', 'code': code, 'project_type': ptype, 'state': state,
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)],
            'contract_start_date': fields.Date.to_date('2026-01-05'),
            'contract_end_date': fields.Date.to_date('2026-12-30')})
        env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': code.replace('-', '') + 'S',
            'contractor_prefix': code.replace('-', '') + 'C'})
        # 填日誌要有啟用中的進度表（construction_progress）
        env['progress.schedule'].create({'project_id': project.id, 'change_date': fields.Date.today()}).write(
            {'state': 'active'})
        return project

    @classmethod
    def _role(cls, login, side, level_group, totp=True):
        env = cls.env
        marker = CONTRACTOR_MARKER if side == SIDE_CONTRACTOR else ROLE_SUPERVISION
        companies = cls.co_s | cls.co_a if side == SIDE_CONTRACTOR else cls.co_s
        vals = {'name': login, 'login': login, 'groups_id': [(6, 0, [env.ref(marker).id, env.ref(level_group).id])],
                'company_id': cls.co_s.id, 'company_ids': [(6, 0, companies.ids)]}
        if side == SIDE_CONTRACTOR:
            vals['dash_scope_company_id'] = cls.co_a.id
        user = env['res.users'].with_context(no_reset_password=True).create(vals)
        if totp:
            user.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
        return user

    # ── 資料工廠（都歸營造廠 A，營造方帳號才讀得到） ──────────────────────
    def _log(self, days_ago=1, state='draft'):
        # 每一格都在 savepoint 裡退回，日期不必錯開；超過 14 天會自動鎖定（LOCKED_LOG_DAYS_AGO 那一格才要）
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.p.id, 'company_id': self.co_s.id, 'employee_id': self.emp.id,
            'log_date': self.today - timedelta(days=days_ago), 'contractor_company_id': self.co_a.id,
            'state': state})

    def _inspection(self, state='draft', creator=None):
        Insp = self.env['general.self.inspection']
        if creator:
            Insp = Insp.with_user(creator).sudo()   # create_uid＝creator（前台以 sudo 建，sudo 不換人）
        insp = Insp.create({
            'project_id': self.p.id, 'name': 'S2-INSP', 'inspection_type_id': self.itype.id,
            'sub_project_name': 'S2', 'inspection_date': self.today, 'inspection_location': 'S2 L1',
            'contractor_company_id': self.co_a.id})
        self.env['general.self.inspection.item'].create({'inspection_id': insp.id, 'check_item': 'S2 項目'})
        if state != 'draft':
            insp.sudo().write({'state': state})
        return insp

    def _defect(self, state='draft', **extra):
        vals = {'project_id': self.p.id, 'record_type': 'supervision', 'check_type': 'construction',
                'defect_category': 'workmanship', 'defect_description': 'S2 缺失', 'defect_location': 'B1',
                'source_type': 'daily_check', 'found_date': self.today - timedelta(days=3),
                'deadline': self.today + timedelta(days=7), 'contractor_company_id': self.co_a.id, **extra}
        defect = self.env['general.defect.improvement'].create(vals)
        if state != 'draft':
            defect.sudo().write({'state': state})
        return defect

    def _slip(self, state='draft'):
        type(self)._slip_no += 1
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.r.id, 'location': 'S2 地點', 'slip_no': self._slip_no})
        task = self.env['project.task'].create({'name': 'S2 契約工項', 'project_id': self.r.id})
        self.env['reservation.notification.slip.line'].create({
            'slip_id': slip.id, 'task_id': task.id, 'item_no': '1', 'unit': '式'})
        if state != 'draft':
            slip.sudo().write({'state': state})
            slip.detail_line_ids.sudo().write({'actual_qty': 1.0})
        return slip

    # ── 驅動真實路由（同 construction_portal TestContractorScopePortal._call） ─────────────
    def _call(self, user, method, *args, files=None, render=False, **kw):
        """以 user 身分跑真實路由。回傳 (status, value)：
        status＝'render'（value＝HTML，render=True 時）／'redirect'（value＝Location）／'json'（value＝回傳值）／'denied'。"""
        self.env.flush_all()
        self.env.invalidate_all()
        seen = {}
        env = self.env(user=user)
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = files or []
            req.httprequest.args = {}
            req.params = {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            try:
                res = method(*args, **kw)
            except AccessError as exc:
                return 'denied', str(exc)
            if 'tpl' in seen:
                if not render:
                    return 'render', ''
                html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
                return 'render', html.decode() if isinstance(html, bytes) else str(html)
        if hasattr(res, 'headers'):
            return 'redirect', res.headers.get('Location', '')
        return 'json', res

    def _html(self, user, method, *args, **kw):
        status, value = self._call(user, method, *args, render=True, **kw)
        return value if status == 'render' else ''

    def _attempt(self, fn):
        """在 savepoint 裡跑 fn，跑完一律退回（每一格互不影響）。"""
        self.env.flush_all()
        savepoint = self.env.cr.savepoint()
        try:
            return fn()
        finally:
            try:
                self.env.flush_all()
            except Exception:  # noqa: BLE001 — 失敗的寫入就是要退回的那些
                pass
            savepoint.close(rollback=True)
            self.env.invalidate_all()


@tagged('post_install', '-at_install', MODULE)
class TestRolePhoneMatrix(RolePhoneCase):
    """驗收 1：能力矩陣。每一格 = (入口顯示, 路由放行, 寫入結果)；None＝這個能力沒有那一欄。"""

    # 每個能力：名稱 → 方法（回傳 dict(entry=, route=, write=)）
    def _cap_project_new(self, user):
        html = self._html(user, self.ctrl.portal_construction_project_detail, self.p.id)
        route = self._call(user, self.ctrl.portal_construction_project_new)[0] == 'render'
        name = f'S2M 新工程 {user.login}'
        self._call(user, self.ctrl.portal_construction_project_create, name=name)
        return {'entry': '/construction/project/new' in html, 'route': route,
                'write': bool(self.env['project.project'].sudo().search_count([('name', '=', name)]))}

    def _cap_project_edit(self, user):
        html = self._html(user, self.ctrl.portal_construction_project_info, self.p_draft.id)
        route = self._call(user, self.ctrl.portal_construction_project_edit, self.p_draft.id)[0] == 'render'
        self._call(user, self.ctrl.portal_construction_project_update, self.p_draft.id, notes='S2M 改')
        self.env.invalidate_all()
        return {'entry': f'/construction/{self.p_draft.id}/edit' in html, 'route': route,
                'write': 'S2M 改' in (self.p_draft.notes or '')}   # Html 欄位存成 <p>…</p>

    def _cap_project_code(self, user):
        html = self._html(user, self.ctrl.portal_construction_project_info, self.p.id)
        status, res = self._call(user, self.ctrl.portal_construction_project_code_update, self.p.id, code='S2M-CODE')
        self.env.invalidate_all()
        return {'entry': 'cy-code-edit-btn' in html, 'route': status == 'json' and bool(res.get('success')),
                'write': self.p.code == 'S2M-CODE'}

    def _cap_schedule_extend(self, user):
        html = self._html(user, self.ctrl.portal_construction_project_detail, self.p.id)
        route = self._call(user, self.ctrl.portal_schedule_extend_page, self.p.id)[0] == 'render'
        return {'entry': '/schedule/extend' in html, 'route': route, 'write': None}

    def _cap_log_create(self, user):
        Log = self.env['daily.log.sheet'].sudo()
        before = Log.search_count([('supervision_project_id', '=', self.p.id)])
        status, _value = self._call(user, self.ctrl.portal_construction_daily_log_create,
                                    project_id=str(self.p.id), log_date=self.today.isoformat(),
                                    work_summary='S2M 新日誌')
        return {'entry': None, 'route': status != 'denied',
                'write': Log.search_count([('supervision_project_id', '=', self.p.id)]) == before + 1}

    def _cap_log_update(self, user):
        log = self._log()
        status, _value = self._call(user, self.ctrl.portal_construction_daily_log_update, self.p.id, log.id,
                                    work_summary='S2M 改日誌')
        self.env.invalidate_all()
        return {'entry': None, 'route': status != 'denied', 'write': log.work_summary == 'S2M 改日誌'}

    def _cap_log_mark_filled(self, user):
        log = self._log()
        html = self._html(user, self.ctrl.portal_construction_daily_log_detail, self.p.id, log.id)
        status, _value = self._call(user, self.ctrl.portal_daily_log_mark_filled, self.p.id, log.id)
        self.env.invalidate_all()
        return {'entry': '/mark-filled' in html, 'route': status != 'denied', 'write': log.state == 'filled'}

    def _cap_log_unlock(self, user):
        log = self._log(days_ago=LOCKED_LOG_DAYS_AGO)
        self.assertTrue(log.sudo().is_locked, '前提：夾具日誌已鎖定')
        html = self._html(user, self.ctrl.portal_construction_daily_log_detail, self.p.id, log.id)
        status, location = self._call(user, self.ctrl.portal_construction_daily_log_unlock, self.p.id, log.id)
        self.env.invalidate_all()
        return {'entry': '/unlock' in html, 'route': 'no_unlock_permission' not in location,
                'write': bool(log.is_unlocked)}

    def _cap_insp_create(self, user):
        Insp = self.env['general.self.inspection'].sudo()
        before = Insp.search_count([('project_id', '=', self.p.id)])
        status, _value = self._call(user, self.ctrl.portal_construction_inspection_create,
                                    project_id=str(self.p.id), inspection_type_id=str(self.itype.id),
                                    inspection_date=self.today.isoformat(), sub_project_name='S2M')
        return {'entry': None, 'route': status != 'denied',
                'write': Insp.search_count([('project_id', '=', self.p.id)]) == before + 1}

    def _inspect_attempt(self, user, insp):
        html = self._html(user, self.ctrl.portal_construction_inspection_detail, insp.id)
        status, value = self._call(user, self.ctrl.portal_inspection_inspect, insp.id)
        self.env.invalidate_all()
        # 路由在 _require_owner_or_manager 擋下時把 AccessError 轉成帶錯誤訊息的導回：只有成功的導回（msg=inspected）才算放行
        return {'entry': f'/construction/inspection/{insp.id}/inspect' in html,
                'route': status == 'redirect' and 'msg=inspected' in value,
                'write': insp.state == 'inspected'}

    def _cap_insp_inspect(self, user):
        return self._inspect_attempt(user, self._inspection())   # 別人（系統）建的

    def _cap_insp_inspect_own(self, user):
        return self._inspect_attempt(user, self._inspection(creator=user))   # 本人建的

    def _cap_insp_confirm(self, user):
        insp = self._inspection('inspected')
        html = self._html(user, self.ctrl.portal_construction_inspection_detail, insp.id)
        status, _value = self._call(user, self.ctrl.portal_inspection_confirm, insp.id)
        self.env.invalidate_all()
        return {'entry': f'/construction/inspection/{insp.id}/confirm' in html, 'route': status != 'denied',
                'write': insp.state == 'confirmed'}

    def _cap_insp_close(self, user):
        insp = self._inspection('confirmed')
        html = self._html(user, self.ctrl.portal_construction_inspection_detail, insp.id)
        status, _value = self._call(user, self.ctrl.portal_inspection_close, insp.id)
        self.env.invalidate_all()
        return {'entry': f'/construction/inspection/{insp.id}/close' in html, 'route': status != 'denied',
                'write': insp.state == 'closed'}

    def _cap_defect_create(self, user):
        Defect = self.env['general.defect.improvement'].sudo()
        before = Defect.search_count([('project_id', '=', self.p.id)])
        status, _value = self._call(user, self.ctrl.portal_construction_defect_create,
                                    project_id=str(self.p.id), description='S2M 缺失', location='B1',
                                    found_date=self.today.isoformat())
        return {'entry': None, 'route': status != 'denied',
                'write': Defect.search_count([('project_id', '=', self.p.id)]) == before + 1}

    def _defect_review(self, user, state, method, url_part, target):
        defect = self._defect(state)
        html = self._html(user, self.ctrl.portal_construction_defect_detail, defect.id)
        status, _value = self._call(user, method, defect.id)
        self.env.invalidate_all()
        return {'entry': f'/construction/defect/{defect.id}/{url_part}' in html, 'route': status != 'denied',
                'write': defect.state == target}

    def _cap_defect_notify(self, user):
        return self._defect_review(user, 'draft', self.ctrl.portal_defect_notify, 'notify', 'notified')

    def _cap_defect_notify_deadline(self, user):
        """缺失沒有改善期限：詳情頁的通知改善表單帶期限送出（路由先寫期限再通知的那個分支；S2 fix1-S）。"""
        defect = self._defect('draft', deadline=False)
        html = self._html(user, self.ctrl.portal_construction_defect_detail, defect.id)
        status, _value = self._call(user, self.ctrl.portal_defect_notify, defect.id,
                                    deadline=(self.today + timedelta(days=5)).isoformat())
        self.env.invalidate_all()
        return {'entry': f'/construction/defect/{defect.id}/notify' in html, 'route': status != 'denied',
                'write': defect.state == 'notified' and bool(defect.deadline)}

    def _cap_defect_verify(self, user):
        return self._defect_review(user, 'improved', self.ctrl.portal_defect_verify, 'verify', 'verified')

    def _cap_defect_close(self, user):
        return self._defect_review(user, 'verified', self.ctrl.portal_defect_close, 'close', 'closed')

    def _slip_review(self, user, state, method, url_part, target):
        slip = self._slip(state)
        html = self._html(user, self.ctrl.portal_construction_slip_detail, self.r.id, slip.id)
        status, _value = self._call(user, method, self.r.id, slip.id)
        self.env.invalidate_all()
        return {'entry': f'/slip/{slip.id}/{url_part}' in html, 'route': status != 'denied',
                'write': slip.state == target}

    def _cap_slip_confirm(self, user):
        return self._slip_review(user, 'draft', self.ctrl.portal_slip_confirm, 'confirm', 'not_started')

    def _cap_slip_close(self, user):
        return self._slip_review(user, 'in_progress', self.ctrl.portal_slip_close, 'close', 'closed')

    def _cap_photo_upload(self, user):
        Photo = self.env['supervision.photo'].sudo()
        before = Photo.search_count([('project_id', '=', self.p.id)])
        status, _value = self._call(user, self.ctrl.portal_construction_photo_upload,
                                    project_id=str(self.p.id), photo=_Upload())
        return {'entry': None, 'route': status != 'denied',
                'write': Photo.search_count([('project_id', '=', self.p.id)]) > before}

    def _cap_photo_delete_others(self, user):
        photo = self.env['supervision.photo'].create({
            'project_id': self.p.id, 'contractor_company_id': self.co_a.id,
            'attachment_id': self.env['ir.attachment'].create({
                'name': 's2.png', 'raw': PNG_BYTES, 'res_model': 'supervision.photo'}).id})
        with MockRequest(self.env(user=user)):
            try:
                self.ctrl._require_photo_deleter(photo)
                allowed = True
            except AccessError:
                allowed = False
        return {'entry': None, 'route': allowed, 'write': None}

    def _cap_document_upload(self, user):
        Att = self.env['ir.attachment'].sudo()
        before = Att.search_count([('name', '=', 's2m.pdf')])
        status, _value = self._call(user, self.ctrl.portal_construction_document_upload, self.p.id,
                                    file=_Upload('s2m.pdf', b'%PDF-1.4 s2', 'application/pdf'))
        return {'entry': None, 'route': status != 'denied',
                'write': Att.search_count([('name', '=', 's2m.pdf')]) > before}

    def _cap_comment(self, user):
        log = self._log()
        Log = self.env(user=user)['daily.log.sheet']
        mode = Log._get_mail_message_access(log.ids, 'create')
        thread = Log._get_thread_with_access(log.id, mode=mode)
        return {'entry': None, 'route': bool(thread) and mode == 'read', 'write': None}

    def _cap_water_level(self, user):
        html = self._html(user, self.ctrl.portal_construction_project_detail, self.p.id)
        route = self._call(user, self.ctrl.portal_construction_water_level, self.p.id)[0] == 'render'
        status, res = self._call(user, self.ctrl.portal_water_level_data, self.p.id)
        return {'entry': f'/construction/{self.p.id}/water-level' in html,
                'route': route and status == 'json' and 'devices' in res, 'write': None}

    def _cap_feedback_entry(self, user):
        html = self._html(user, self.ctrl.portal_construction_project_detail, self.p.id)
        return {'entry': '意見回饋' in html, 'route': None, 'write': None}

    def _cap_inspection_types_manage(self, user):
        with MockRequest(self.env(user=user)):
            allowed = self.ctrl._can_manage_inspection_types()
        return {'entry': None, 'route': allowed, 'write': None}

    CAPABILITIES = (
        'project_new', 'project_edit', 'project_code', 'schedule_extend',
        'log_create', 'log_update', 'log_mark_filled', 'log_unlock',
        'insp_create', 'insp_inspect', 'insp_inspect_own', 'insp_confirm', 'insp_close',
        'defect_create', 'defect_notify', 'defect_notify_deadline', 'defect_verify', 'defect_close',
        'slip_confirm', 'slip_close',
        'photo_upload', 'photo_delete_others', 'document_upload', 'comment',
        'water_level', 'feedback_entry', 'inspection_types_manage',
    )

    def _matrix(self):
        rows = {}
        for pair in PAIRS:
            for cap in self.CAPABILITIES:
                method = getattr(self, f'_cap_{cap}')
                old = self._attempt(lambda m=method, p=pair: m(self.old[p]))
                new = self._attempt(lambda m=method, p=pair: m(self.new[p]))
                rows[(pair, cap)] = (old, new)
                _logger.info('%s|%s|%s|%s|old=%s|new=%s', MATRIX_MARK, pair[0], pair[1], cap,
                             _fmt(old), _fmt(new))
        return rows

    def test_capability_matrix_equals_old_portal_accounts(self):
        rows = self._matrix()
        mismatches = []
        for (pair, cap), (old, new) in rows.items():
            for column in ('entry', 'route', 'write'):
                if old[column] == new[column]:
                    continue
                allowed = ALLOWED_DIFFERENCES.get((pair[0], cap))
                # 必守的差異只准「角色帳號比較少」：舊的有、新的沒有
                if allowed and old[column] and not new[column]:
                    continue
                mismatches.append(f'{pair[0]}/{pair[1]} × {cap}.{column}：舊前台帳號={old[column]} 角色帳號={new[column]}')
        self.assertEqual(mismatches, [], '角色帳號與舊前台帳號的手機能力不同（必守的差異以外）')
        # 每一條允許的差異都真的存在（否則是過時的例外；L1⑨ 的反面：沒有東西要驗不等於通過）
        for (side, cap) in ALLOWED_DIFFERENCES:
            for level in (LEVEL_BOSS, LEVEL_MANAGER):
                old, new = rows[((side, level), cap)]
                self.assertNotEqual(old, new, f'{side}/{level} × {cap}：允許的差異已不存在，拿掉 ALLOWED_DIFFERENCES 那一條')
        # 矩陣本身有鑑別力：營造方的審核類照擋、監造方照放（否則全 False＝全 False 也會「相等」）
        self.assertFalse(rows[((SIDE_CONTRACTOR, LEVEL_BOSS), 'defect_verify')][1]['route'], '營造方審核類照擋')
        self.assertTrue(rows[((SIDE_SUPERVISION, LEVEL_BOSS), 'defect_verify')][1]['write'], '監造老闆審核得了')
        self.assertFalse(rows[((SIDE_CONTRACTOR, LEVEL_BOSS), 'defect_notify_deadline')][1]['route'],
                         '營造方帶期限的通知改善照擋（S2 fix1-S：與按鈕同一個判斷）')
        self.assertTrue(rows[((SIDE_SUPERVISION, LEVEL_MANAGER), 'defect_notify_deadline')][1]['write'], '監造主管補期限並通知')
        self.assertTrue(rows[((SIDE_CONTRACTOR, LEVEL_MANAGER), 'log_create')][1]['write'], '營造主管填得了日誌')
        self.assertTrue(rows[((SIDE_SUPERVISION, LEVEL_MANAGER), 'insp_close')][1]['write'], '監造主管結案得了自主檢查')
        self.assertFalse(rows[((SIDE_SUPERVISION, LEVEL_BOSS), 'inspection_types_manage')][1]['route'], '危險閘門照擋')

    def test_entry_shown_iff_route_allowed(self):
        """畫面與路由同一個判斷（S2 規格 A）：所有帳號（含監造方後台人員）入口顯示＝路由放行。"""
        users = list(self.old.values()) + list(self.new.values()) + [self.staff] + list(self.field_users)
        both = [cap for cap in self.CAPABILITIES if cap not in ('feedback_entry',)]
        checked = 0
        for user in users:
            for cap in both:
                row = self._attempt(lambda c=cap, u=user: getattr(self, f'_cap_{c}')(u))
                if row['entry'] is None or row['route'] is None:
                    continue
                checked += 1
                self.assertEqual(row['entry'], row['route'], f'{user.login} × {cap}：入口顯示與路由放行不一致 {row}')
        self.assertGreaterEqual(checked, len(users) * 10, '前提：真的比到了入口與路由兩欄都有的能力')

    def test_field_user_only_own_record(self):
        """S2 fix1-R：現場人員只能改自己建的（畫面與路由同一個判斷）：別人建的看不到「完成檢查」、送了也不放行、狀態不變；
        本人建的看得到、做得到。老闆／主管兩種都做得到（反證：這支測試量得到「放行」）。"""
        for user in self.field_users:
            other = self._attempt(lambda u=user: self._cap_insp_inspect(u))
            own = self._attempt(lambda u=user: self._cap_insp_inspect_own(u))
            self.assertEqual(other, {'entry': False, 'route': False, 'write': False}, f'{user.login}：別人建的')
            self.assertEqual(own, {'entry': True, 'route': True, 'write': True}, f'{user.login}：本人建的')
        boss = self.new[(SIDE_SUPERVISION, LEVEL_BOSS)]
        self.assertEqual(self._attempt(lambda: self._cap_insp_inspect(boss)), {'entry': True, 'route': True, 'write': True})

    def test_defect_notify_with_deadline_uses_review_predicate(self):
        """S2 fix1-S：帶期限的「通知改善」與按鈕、其他審核路由同一個判斷（res.users._portal_review_visible）——
        判斷說不行就不寫期限、不通知（原本這個分支自己組兩道守衛）。"""
        user = self.new[(SIDE_SUPERVISION, LEVEL_BOSS)]
        defect = self._defect('draft', deadline=False)
        deadline = self.today + timedelta(days=5)
        with patch.object(type(self.env['res.users']), '_portal_review_visible', lambda self: False):
            status, _value = self._call(user, self.ctrl.portal_defect_notify, defect.id, deadline=deadline.isoformat())
        self.env.invalidate_all()
        self.assertEqual(status, 'denied', '判斷說不行：路由擋')
        self.assertFalse(defect.deadline, '沒有先寫期限')
        self.assertEqual(defect.state, 'draft')
        status, _value = self._call(user, self.ctrl.portal_defect_notify, defect.id, deadline=deadline.isoformat())
        self.env.invalidate_all()
        self.assertEqual((defect.state, defect.deadline), ('notified', deadline), '反證：判斷照常時同一個呼叫成功')
        # 判斷的兩個條件各自打到這條路（mutation A3 拿掉「不是營造方」、A4 拿掉管理權時要在這裡紅，不只是別的審核格紅）：
        # 營造方老闆（有管理權、是營造方）、監造方現場人員（不是營造方、沒有管理權）帶期限送出都擋、期限不寫
        denied = {'entry': False, 'route': False, 'write': False}
        for who in (self.old[(SIDE_CONTRACTOR, LEVEL_BOSS)], self.field_users.filtered(lambda u: u.login == 's2_old_sf')):
            self.assertEqual(self._attempt(lambda: self._cap_defect_notify_deadline(who)), denied,
                             f'{who.login}：帶期限的通知改善照擋')

    @require_totp
    def test_no_totp_role_account_has_no_phone_capability(self):
        """（強制兩步驟驗證時；S2 fix2-Z 起常數預設 False，見 test_role_fix2.TestNoTotpRequired）沒開 TOTP 的角色帳號：層級 None、所有寫入守衛拒（不必先讀紀錄的「新增工程」也拒）。"""
        for side, level_group in ((SIDE_SUPERVISION, ROLE_BOSS), (SIDE_CONTRACTOR, ROLE_MANAGER)):
            user = self._role(f's2_nototp_{side}', side, level_group, totp=False)
            self.assertIsNone(user._portal_role_level(), user.login)
            self.assertFalse(user._portal_can_manage() or user._portal_can_write(), user.login)
            name = f'S2 沒開 TOTP 建的 {side}'
            self.assertEqual(self._call(user, self.ctrl.portal_construction_project_create, name=name)[0], 'denied')
            self.assertFalse(self.env['project.project'].search_count([('name', '=', name)]))
            self.assertEqual(self._call(user, self.ctrl.portal_construction_daily_log_create,
                                        project_id=str(self.p.id))[1], '/my', f'{user.login}：讀不到工程，導回')

    def test_capability_source_single_definition(self):
        """能力判斷只在 construction_supervision_base 定義一次（S2 規格 A：全系統各只有一份）。"""
        for name in ('_portal_role_level', '_portal_can_manage', '_portal_review_visible', '_portal_can_write',
                     '_portal_is_field_only', '_dash_is_contractor_or_console',
                     '_portal_other_data_visible', '_portal_uses_phone_home', '_dash_is_blocked_internal'):
            owners = [cls.__module__ for cls in type(self.env['res.users']).mro() if name in vars(cls)]
            self.assertEqual(owners, ['odoo.addons.construction_supervision_base.models.res_users'], name)


def _fmt(row):
    return ','.join(f'{k}={"-" if v is None else int(bool(v))}' for k, v in sorted(row.items()))


@tagged('post_install', '-at_install', MODULE)
class TestRoleOrgGroupSync(RolePhoneCase):
    """B（F5）：組織旗標只對前台帳號同步組織群組。"""

    def test_internal_flag_does_not_join_org_group(self):
        contractor_org = self.env.ref(ORG_CONTRACTOR)
        supervision_org = self.env.ref(ORG_SUPERVISION)
        sb = self.new[(SIDE_SUPERVISION, LEVEL_BOSS)]
        staff = self.staff
        # 監造方角色帳號勾營造旗標：不會加進組織群組（否則 portal 與 internal 並存）；約束照樣擋（不可是營造方）
        with self.assertRaises(ValidationError):
            sb.write({'is_contractor_org': True})
        staff.write({'is_supervision_org': True})
        self.assertNotIn(supervision_org, staff.groups_id, '內部帳號勾監造組織：不加群組')
        self.assertFalse(staff.share)
        cb = self.new[(SIDE_CONTRACTOR, LEVEL_BOSS)]
        cb.write({'is_contractor_org': True})
        self.assertNotIn(contractor_org, cb.groups_id, '營造方角色帳號勾營造組織：不加群組')
        self.assertFalse(cb.share, '仍是內部帳號')
        created = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 's2_internal_flag', 'login': 's2_internal_flag', 'is_contractor_org': True,
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.assertNotIn(contractor_org, created.groups_id, '建立時就勾：同樣不加')
        # 反證：前台帳號照舊同步
        portal = self.old[(SIDE_SUPERVISION, LEVEL_MANAGER)]
        self.assertIn(supervision_org, portal.groups_id)
        portal.write({'is_contractor_org': True})
        self.assertIn(contractor_org, portal.groups_id, '前台帳號照舊加組織群組')
        portal.write({'is_contractor_org': False})
        self.assertNotIn(contractor_org, portal.groups_id, '前台帳號照舊移出組織群組')


@tagged('post_install', '-at_install', MODULE)
class TestRoleConversion(RolePhoneCase):
    """C：前台角色帳號 ↔ 後台角色帳號（同一個 user id）。"""

    COMPARE_FIELDS = ('login', 'partner_id', 'active', 'share', 'groups_id', 'is_supervision_org', 'is_contractor_org',
                      'dash_scope_company_id', 'company_id', 'company_ids', 'notification_type', 'portal_role',
                      'totp_enabled')

    def _snapshot(self, user):
        user = user.sudo()
        self.env.invalidate_all()
        out = {}
        for name in self.COMPARE_FIELDS:
            value = user[name]
            out[name] = tuple(sorted(value.ids)) if hasattr(value, 'ids') else value
        out['member_projects'] = tuple(sorted(self.env['supervision.project.member'].sudo().search(
            [('user_id', '=', user.id)]).project_id.ids))
        return out

    def _capabilities(self, user):
        with MockRequest(self.env(user=user)):
            return {
                'level': user._portal_role_level(), 'manage': self.ctrl._can_manage(),
                'review': user._portal_review_visible(), 'write': user._portal_can_write(),
                'field_only': self.ctrl._is_field_only(), 'unlock': self.env['daily.log.sheet'].with_user(user).new({}).can_unlock,
                'other_data': user._portal_other_data_visible(),
                'projects': set(self.env['project.project'].sudo().search(
                    self.env['project.project'].with_user(user)._get_portal_projects_domain(user.partner_id)
                    + [('id', 'in', self.projects.ids)]).ids),
            }

    def _engineering_manager(self):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 's2_eng_mgr', 'login': 's2_eng_mgr', 'company_id': self.co_s.id,
            'company_ids': [(6, 0, self.co_s.ids)],
            'groups_id': [(6, 0, [self.env.ref(ENGINEERING_MANAGER).id])]})

    def test_convert_and_revert_both_sides(self):
        admin = self._engineering_manager()
        for pair in PAIRS:
            portal = self.old[pair]
            portal.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})   # 範圍合格（角色帳號要 TOTP）；轉換保留它
            before = self._snapshot(portal)
            caps_before = self._capabilities(portal)
            portal.with_user(admin).action_convert_to_role_account()
            role = self.env['res.users'].browse(portal.id)
            self.assertEqual(role.id, portal.id, 'id 不變')
            self.assertTrue(role._is_role_account(), pair)
            self.assertEqual(role._role_side(), pair[0])
            self.assertEqual(role._role_level_raw(), pair[1])
            self.assertFalse(role.share)
            self.assertEqual(role.notification_type, 'inbox')
            self.assertFalse(role.groups_id & (self.env.ref(ORG_CONTRACTOR) | self.env.ref(ORG_SUPERVISION)
                                               | self.env.ref('base.group_portal') | self.env.ref(P_VIEWER)))
            self.assertIn(self.env.ref(INBOX_GROUP), role.groups_id)
            if pair[0] == SIDE_SUPERVISION:
                self.assertFalse(role.is_contractor_org, '監造方清掉營造旗標')
            else:
                self.assertEqual(role.sudo().dash_scope_company_id, self.co_a)
                self.assertIn(self.co_s, role.company_ids, '允許公司＝營造廠＋承攬工程的監造公司')
            self.assertEqual(self._snapshot(role)['member_projects'], before['member_projects'], '工程成員資格不變')
            caps_after = self._capabilities(role)
            self.assertEqual(caps_after, caps_before, f'{pair}：手機能力轉換前後相同')
            self.assertTrue(self.env['ir.ui.menu'].with_user(role)._visible_menu_ids(), '後台多了唯讀（看得到選單）')
            role.with_user(admin).action_revert_to_portal_role()
            after = self._snapshot(portal)
            self.assertEqual(after, before, f'{pair}：改回後逐欄相同（{self.COMPARE_FIELDS}＋工程成員）')

    def test_convert_supervision_clears_auto_contractor_flag(self):
        """監造方前台帳號建立時沒勾監造組織 → 被自動勾營造組織（_apply_default_contractor_org），之後才補勾監造組織：
        兩個旗標都在。轉成監造方角色帳號要清掉營造旗標，否則它是營造方標記、轉出來的帳號不合法（mutation C1 第一輪存活後補的測試）。"""
        admin = self._engineering_manager()
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 's2_both_flags', 'login': 's2_both_flags', 'company_id': self.co_s.id,
            'company_ids': [(6, 0, self.co_s.ids)], 'groups_id': [(6, 0, [self.env.ref(P_BOSS).id])]})
        self.assertTrue(user.is_contractor_org, '前提：建帳號時被自動勾營造組織')
        user.write({'is_supervision_org': True})
        user.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
        user.with_user(admin).action_convert_to_role_account()
        self.assertEqual(user._role_side(), SIDE_SUPERVISION)
        self.assertFalse(user.is_contractor_org, '營造旗標清掉')
        self.assertFalse(user._dash_is_contractor_side())
        self.assertTrue(user._dash_scope_ok(), '轉出來的監造老闆角色帳號範圍合格')
        self.assertEqual(user._portal_role_level(), LEVEL_BOSS)

    def _p_fixtures(self):
        """S2 fix1-P（審查 s2review1-skeptic F1、F2）：轉換會改到組織旗標或範圍公司的兩種前台帳號。"""
        Users = self.env['res.users'].with_context(no_reset_password=True)
        both = Users.create({'name': 's2p_both_flags', 'login': 's2p_both_flags', 'company_id': self.co_s.id,
                             'company_ids': [(6, 0, self.co_s.ids)], 'groups_id': [(6, 0, [self.env.ref(P_BOSS).id])]})
        both.write({'is_supervision_org': True})   # 建帳號時已被自動勾營造組織 → 兩個旗標都勾、公司都不是營造廠
        blank = Users.create({'name': 's2p_blank_scope', 'login': 's2p_blank_scope', 'company_id': self.co_a.id,
                              'company_ids': [(6, 0, self.co_a.ids)], 'groups_id': [(6, 0, [self.env.ref(P_LEADER).id])]})
        blank.sudo().write({'dash_scope_company_id': False})   # 建帳號時預帶成主要公司；清掉＝範圍公司空白、主要公司是營造廠
        # S2 fix2（P 補充，使用者 11-11）：帶非標準群組的前台帳號（監造方），改回後完整群組集合要原樣回來
        extra_group = self.env['res.groups'].create({'name': 'S2P 非標準群組（測試）'})
        extra = Users.create({'name': 's2p_extra_group', 'login': 's2p_extra_group', **SUPERVISION_USER_VALS,
                              'company_id': self.co_s.id, 'company_ids': [(6, 0, self.co_s.ids)],
                              'groups_id': [(6, 0, [self.env.ref(P_BOSS).id, extra_group.id])]})
        self.assertIn(extra_group, extra.groups_id, '前提：帶著非標準群組')
        for user in (both, blank, extra):
            user.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
            for project in self.projects:
                self.env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})
        return both, blank, extra

    def test_convert_and_revert_restore_every_field(self):
        """S2 fix1-P：改回後與轉換前逐欄相同（含組織旗標、組織群組、範圍公司、公司），手機能力也回到轉換前。
        轉換前後的能力印進 log（S2FIX1_P|…，報告 P-2 用）：這兩種帳號起點都是「營造方、範圍不合格」＝手機什麼都看不到。"""
        admin = self._engineering_manager()
        for user in self._p_fixtures():
            with self.subTest(login=user.login):   # 兩種夾具各自回報（一種紅了另一種照跑）
                self._p_round_trip(admin, user)

    def _p_round_trip(self, admin, user):
        # 前兩種起點是營造方前台帳號（skeptic F1、F2）；第三種是帶非標準群組的監造方前台帳號（P 補充）
        contractor_start = user.login != 's2p_extra_group'
        self.assertTrue(user.share and user._dash_is_contractor_side() == contractor_start,
                        f'前提：{user.login} 起點是{"營造方" if contractor_start else "監造方"}前台帳號')
        before = self._snapshot(user)
        caps_before = self._capabilities(user)
        user.with_user(admin).action_convert_to_role_account()
        self.assertTrue(user._is_role_account(), user.login)
        _logger.info('S2FIX1_P|%s|before=%s|role=%s|side=%s', user.login, caps_before, self._capabilities(user),
                     user._role_side())
        user.with_user(admin).action_revert_to_portal_role()
        self.assertEqual(self._snapshot(user), before, f'{user.login}：改回後逐欄相同（{self.COMPARE_FIELDS}＋工程成員）')
        self.assertEqual(self._capabilities(user), caps_before, f'{user.login}：改回後手機能力與轉換前相同')
        self.assertFalse(user.sudo().dash_role_origin, f'{user.login}：改回後清掉轉換紀錄')

    def test_revert_without_full_origin_and_bad_origin(self):
        """S2 fix1-P 的另外兩條路：沒有轉換紀錄（直接建成的角色帳號）照層級／方別推，範圍公司與公司不動；
        紀錄的群組不像前台帳號、或主要公司不在允許公司裡 → 拒絕，帳號照舊是角色帳號（沒有改到一半）。
        S2 fix3-7：拿掉「只記了公司」的舊格式相容路徑，改測「沒有紀錄」那格。"""
        admin = self._engineering_manager()
        direct = self.new[(SIDE_CONTRACTOR, LEVEL_MANAGER)]
        self.assertFalse(direct.sudo().dash_role_origin, '前提：直接建成的角色帳號沒有轉換紀錄')
        companies_before = (direct.company_id, direct.company_ids, direct.sudo().dash_scope_company_id)
        direct.with_user(admin).action_revert_to_portal_role()
        self.assertTrue(direct.share)
        self.assertEqual(direct.portal_role, LEVEL_MANAGER)
        self.assertEqual((direct.is_contractor_org, direct.is_supervision_org), (True, False), '組織旗標照方別')
        self.assertEqual((direct.company_id, direct.company_ids, direct.sudo().dash_scope_company_id), companies_before,
                         '沒有紀錄：範圍公司、主要公司、允許公司都不動')
        self.assertFalse(direct.sudo().dash_role_origin)

        user = self.old[(SIDE_SUPERVISION, LEVEL_BOSS)]
        user.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
        user.with_user(admin).action_convert_to_role_account()
        origin = dict(user.sudo().dash_role_origin)
        bad = (({'groups_id': origin['groups_id'] + [self.env.ref('base.group_user').id]}, '不是前台帳號的群組'),
               ({'company_id': self.co_a.id}, '主要公司已不存在'))
        for patch_vals, message in bad:
            with self.subTest(message=message):
                user.sudo().write({'dash_role_origin': {**origin, **patch_vals}})
                with self.assertRaises(UserError) as ctx:
                    user.with_user(admin).action_revert_to_portal_role()
                self.assertIn(message, str(ctx.exception))
                self.assertTrue(user._is_role_account(), '拒絕時沒有改到一半')
        user.sudo().write({'dash_role_origin': origin})
        user.with_user(admin).action_revert_to_portal_role()
        self.assertTrue(user.share and user.portal_role == LEVEL_BOSS, '紀錄正確就改得回去')

    def test_conversion_refusals(self):
        admin = self._engineering_manager()
        Users = self.env['res.users'].with_context(no_reset_password=True)
        field = Users.create({'name': 's2_field', 'login': 's2_field', **SUPERVISION_USER_VALS,
                              'groups_id': [(6, 0, [self.env.ref(P_FIELD).id])]})
        viewer = Users.create({'name': 's2_viewer', 'login': 's2_viewer', **SUPERVISION_USER_VALS,
                               'groups_id': [(6, 0, [self.env.ref(P_VIEWER).id])]})
        no_side = Users.create({'name': 's2_noside', 'login': 's2_noside', 'company_id': self.co_s.id,
                                'company_ids': [(6, 0, self.co_s.ids)],
                                'groups_id': [(6, 0, [self.env.ref(P_BOSS).id])]})
        no_side.write({'is_contractor_org': False})
        both = Users.create({'name': 's2_both', 'login': 's2_both', **SUPERVISION_USER_VALS,
                             'dash_scope_company_id': self.co_a.id,
                             'groups_id': [(6, 0, [self.env.ref(P_BOSS).id])]})
        cases = ((field, '老闆或主管'), (viewer, '老闆或主管'), (no_side, '無法判定方別'), (both, '無法判定'),
                 (self.staff, '已經是內部帳號'), (self.new[(SIDE_SUPERVISION, LEVEL_BOSS)], '已經是內部帳號'))
        for user, message in cases:
            groups_before = user.groups_id
            with self.assertRaises(UserError, msg=user.login) as ctx:
                user.with_user(admin).action_convert_to_role_account()
            self.assertIn(message, str(ctx.exception), user.login)
            self.assertEqual(user.groups_id, groups_before, f'{user.login}：沒有改到一半')
        with self.assertRaises(AccessError):
            self.old[(SIDE_SUPERVISION, LEVEL_BOSS)].with_user(self.staff).action_convert_to_role_account()
        with self.assertRaises(UserError):
            self.staff.with_user(admin).action_revert_to_portal_role()

    def test_server_actions_bound_to_user_form(self):
        for xmlid in (f'{D}.action_convert_to_role_account', f'{D}.action_revert_to_portal_role'):
            action = self.env.ref(xmlid)
            self.assertEqual(action.binding_model_id.model, 'res.users')
            self.assertEqual(action.groups_id, self.env.ref(ENGINEERING_MANAGER))


@tagged('post_install', '-at_install', MODULE)
@require_totp
class TestRoleBlockedNoTotp(RolePhoneCase):
    """D：沒開 TOTP 的角色帳號——後台第一次開啟（OdooBot 初始化）不崩潰；業務訊息讀不到、也不被通知；別人發訊息不失敗。
    S2 fix2-Z 起預設不強制 TOTP（DASH_REQUIRE_TOTP＝False）：這裡驗的是「強制時」的行為（常數 patch 成 True）。"""

    def test_odoobot_init_works_while_blocked(self):
        user = self._role('s2_fresh_sb', SIDE_SUPERVISION, ROLE_BOSS, totp=False)
        self.assertFalse(user._dash_scope_ok(), '前提：範圍不合格（沒開 TOTP）')
        self.assertIn(user.odoobot_state, (False, 'not_initialized'), '前提：從沒初始化過')
        channel = self.env(user=user)['res.users'].browse(user.id)._init_odoobot()
        self.assertTrue(channel, 'OdooBot 初始化成功（原本讀 OdooBot 聯絡人 AccessError）')
        self.assertEqual(user.odoobot_state, 'onboarding_emoji')
        # 只多 OdooBot 一個系統聯絡人，其他人照樣讀不到
        partners = self.env(user=user)['res.partner'].with_context(active_test=False).search([])
        self.assertEqual(set(partners.ids), {user.partner_id.id, self.env.ref('base.partner_root').id})

    def test_blocked_reads_no_business_message_and_staff_post_does_not_fail(self):
        user = self._role('s2_blocked_sm', SIDE_SUPERVISION, ROLE_MANAGER, totp=False)
        log = self._log()
        log.message_subscribe(partner_ids=user.partner_id.ids)
        message = log.with_user(self.staff).message_post(
            body='S2 業務訊息', message_type='comment', subtype_xmlid='mail.mt_comment',
            partner_ids=user.partner_id.ids)
        self.assertTrue(message, '監造方人員發訊息成功（收件人有範圍不合格的帳號也不失敗）')
        self.assertFalse(message.sudo().notification_ids.filtered(lambda n: n.res_partner_id == user.partner_id),
                         '範圍不合格的帳號不被通知')
        self.assertFalse(self.env(user=user)['mail.message'].search([('id', '=', message.id)]),
                         '也讀不到業務單據上的訊息本文')
        self.assertNotEqual(self.env(user=user)['ir.rule']._dash_scope_kind(), None, 'kind 不是 None')
        # 對話照常
        chat = self.env(user=user)['discuss.channel'].channel_get([self.staff.partner_id.id])
        chat_msg = chat.with_user(self.staff).message_post(body='S2 對話', message_type='comment',
                                                           subtype_xmlid='mail.mt_comment')
        self.assertTrue(self.env(user=user)['mail.message'].search([('id', '=', chat_msg.id)]), '對話訊息照常讀得到')
        # 開了 TOTP 之後恢復：照常被通知、讀得到
        user.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
        self.env.registry.clear_cache()
        message2 = log.with_user(self.staff).message_post(
            body='S2 業務訊息 2', message_type='comment', subtype_xmlid='mail.mt_comment')
        self.assertTrue(message2.sudo().notification_ids.filtered(lambda n: n.res_partner_id == user.partner_id),
                        '開了 TOTP 的追蹤者照常收到')
        self.assertTrue(self.env(user=user)['mail.message'].search([('id', '=', message2.id)]))


@tagged('post_install', '-at_install', MODULE)
class TestRolePhoneNotify(RolePhoneCase):
    """H：同一個手機動作由舊前台帳號與角色帳號做，收件人（聯絡人與通知方式）相同。"""

    def _recipients(self, message):
        return {(n.res_partner_id.id, n.notification_type) for n in message.sudo().notification_ids}

    def _latest_message(self, record, before_ids):
        return self.env['mail.message'].sudo().search(
            [('model', '=', record._name), ('res_id', '=', record.id), ('id', 'not in', before_ids)], order='id')

    def test_defect_notify_same_recipients(self):
        outsider = self.env['res.partner'].create({'name': 'S2 外部負責人', 'email': 's2-out@example.invalid'})
        responsible = self.staff
        results = {}
        for kind, accounts in (('old', self.old), ('new', self.new)):
            user = accounts[(SIDE_SUPERVISION, LEVEL_BOSS)]
            defect = self._defect('draft', responsible_user_id=responsible.id)
            defect.message_subscribe(partner_ids=outsider.ids)
            before = self.env['mail.message'].sudo().search(
                [('model', '=', defect._name), ('res_id', '=', defect.id)]).ids
            status, _value = self._call(user, self.ctrl.portal_defect_notify, defect.id)
            self.assertNotEqual(status, 'denied')
            messages = self._latest_message(defect, before)
            results[kind] = {frozenset(self._recipients(m)) for m in messages}
            self.assertTrue(any(responsible.partner_id.id in {p for p, _t in r} for r in results[kind]),
                            f'{kind}：負責人收到「已派發給您」')
        self.assertEqual(results['old'], results['new'], '收件人（聯絡人, 通知方式）相同')

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_phone_action_line_is_not_a_bypass(self):
        """劃線的反面（J 原本要防的）：不是 sudo、不是本人當作者、對話、沒有手機能力 → 照舊收窄。"""
        from odoo.addons.construction_company_dashboard.models import restricted_mail
        sb = self.new[(SIDE_SUPERVISION, LEVEL_BOSS)]
        log = self._log()
        env_su = self.env(user=sb, su=True)
        own = sb.partner_id.id
        self.assertFalse(restricted_mail._dash_narrow_recipients(env_su, own, 'daily.log.sheet'), '手機動作照核心')
        self.assertTrue(restricted_mail._dash_narrow_recipients(self.env(user=sb), own, 'daily.log.sheet'), '非 sudo')
        self.assertTrue(restricted_mail._dash_narrow_recipients(env_su, own, 'discuss.channel'), '對話')
        self.assertTrue(restricted_mail._dash_narrow_recipients(env_su, own, False), '沒有單據')
        self.assertFalse(restricted_mail._dash_narrow_recipients(env_su, self.staff.partner_id.id, 'daily.log.sheet'),
                         '作者是監造方人員：本來就不收窄（r4 F1 的既有行為，沒有路由會這樣帶）')
        other_role = self.new[(SIDE_CONTRACTOR, LEVEL_BOSS)]
        self.assertTrue(restricted_mail._dash_narrow_recipients(env_su, other_role.partner_id.id, 'daily.log.sheet'),
                        '作者是別的受限帳號（不是呼叫者本人）：照舊收窄')
        blocked = self._role('s2_blocked_cb', SIDE_CONTRACTOR, ROLE_BOSS, totp=False)
        self.assertTrue(restricted_mail._dash_narrow_recipients(
            self.env(user=blocked, su=True), blocked.partner_id.id, 'daily.log.sheet'), '沒有手機能力（沒開 TOTP）')
        self.assertTrue(log)


@tagged('post_install', '-at_install', MODULE)
class TestRolePhoneCommentHttp(HttpCase):
    """H＋留言權：真 HTTP /mail/message/post。舊前台主管與角色主管在日誌留言 @ 追蹤者與外部聯絡人：
    收件人相同（追蹤者收到、不是追蹤者的外部聯絡人被拿掉，不寄 email）。"""

    PASSWORD = 'S2-comment-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_s = env['res.company'].create({'name': 'S2C 監造', 'company_type': COMPANY_TYPE_SUPERVISION})
        cls.co_a = make_contractor(env, 'S2C 營造 A')
        cls.project = env['project.project'].create({
            'name': 'S2C 留言測試', 'code': 'S2C', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        Users = env['res.users'].with_context(no_reset_password=True)
        cls.old = Users.create({'name': 's2c_old', 'login': 's2c_old', 'password': cls.PASSWORD,
                                'groups_id': [(6, 0, [env.ref(P_LEADER).id])], **SUPERVISION_USER_VALS,
                                'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        cls.new = Users.create({'name': 's2c_new', 'login': 's2c_new', 'password': cls.PASSWORD,
                                'groups_id': [(6, 0, [env.ref(ROLE_SUPERVISION).id, env.ref(ROLE_MANAGER).id])],
                                'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        cls.new.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
        cls.staff = Users.create({'name': 's2c_staff', 'login': 's2c_staff', 'company_id': cls.co_s.id,
                                  'company_ids': [(6, 0, cls.co_s.ids)],
                                  'groups_id': [(6, 0, [env.ref('base.group_user').id])]})
        for user in (cls.old, cls.new):
            env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': user.id})
        env['progress.schedule'].create({'project_id': cls.project.id, 'change_date': fields.Date.today()}).write(
            {'state': 'active'})
        _mail_sender_config(env)
        cls.emp = env['hr.employee'].create({'name': 'S2C 填表人', 'company_id': cls.co_s.id})
        cls.follower_ext = env['res.partner'].create({'name': 'S2C 追蹤的外部聯絡人', 'email': 's2c-f@example.invalid'})
        cls.outsider = env['res.partner'].create({'name': 'S2C 不相干的外部聯絡人', 'email': 's2c-o@example.invalid'})

    def _log(self, day):
        log = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.co_s.id, 'employee_id': self.emp.id,
            'log_date': fields.Date.today() - timedelta(days=day), 'contractor_company_id': self.co_a.id})
        log.message_subscribe(partner_ids=(self.staff.partner_id | self.follower_ext).ids)
        return log

    def _login(self, user):
        with patch.object(type(self.env['res.users']), '_rpc_api_keys_only', lambda self: False):
            self.authenticate(user.login, self.PASSWORD)

    def test_comment_same_recipients_and_no_outsider(self):
        results = {}
        for day, user in ((1, self.old), (2, self.new)):
            log = self._log(day)
            self._login(user)
            body = f'S2C 留言 {user.login}'
            result = self.make_jsonrpc_request('/mail/message/post', {
                'thread_model': 'daily.log.sheet', 'thread_id': log.id,
                'post_data': {'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment',
                              'partner_ids': [self.follower_ext.id, self.outsider.id]}})
            self.assertTrue(result, user.login)
            message = self.env['mail.message'].sudo().search([('body', 'ilike', body)])
            self.assertEqual(len(message), 1, f'{user.login}：留言成功')
            self.assertEqual(message.author_id, user.partner_id)
            recipients = {(n.res_partner_id.id, n.notification_type) for n in message.notification_ids}
            self.assertNotIn(self.outsider.id, {p for p, _t in recipients} | set(message.partner_ids.ids),
                             f'{user.login}：不是追蹤者的外部聯絡人被拿掉')
            self.assertIn(self.staff.partner_id.id, {p for p, _t in recipients}, f'{user.login}：追蹤者收到')
            results[user.login] = {(p if p not in (self.old.partner_id.id, self.new.partner_id.id) else 'author', t)
                                   for p, t in recipients}
            self.assertTrue(log.sudo().message_partner_ids & user.partner_id, f'{user.login}：留言者自動關注')
        self.assertEqual(results['s2c_old'], results['s2c_new'], '舊前台主管與角色主管：收件人相同')


@tagged('post_install', '-at_install', MODULE)
class TestRoleLoginAndSwitchHttp(HttpCase):
    """E：角色帳號登入後先到手機首頁；手機有「電腦版後台」、後台有「手機版」（只有角色帳號）。D：沒開 TOTP 的提示。"""

    PASSWORD = 'S2-login-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_s = env['res.company'].create({'name': 'S2L 監造', 'company_type': COMPANY_TYPE_SUPERVISION})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups):
            return Users.create({'name': login, 'login': login, 'password': cls.PASSWORD,
                                 'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                                 'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        cls.role = user('s2l_role', [ROLE_SUPERVISION, ROLE_BOSS])
        cls.staff = user('s2l_staff', ['base.group_user'])

    @require_totp
    def test_login_redirect_and_totp_hint(self):
        # （強制兩步驟驗證時；S2 fix2-Z）沒開 TOTP：密碼登入 → /construction，看得到「請先啟用兩步驟驗證」與連結；工程是空的
        response = self.url_open('/web/login', data={
            'login': self.role.login, 'password': self.PASSWORD, 'csrf_token': self._csrf()}, allow_redirects=False)
        self.assertIn('/construction', response.headers.get('Location', ''), '角色帳號登入後先到手機首頁')
        page = self.url_open('/construction?view=list')
        self.assertEqual(page.status_code, 200)
        self.assertIn('請先啟用兩步驟驗證', page.text)
        self.assertIn('href="/my/security"', page.text)
        self.assertIn('id="dash_backend_link"', page.text, '手機有電腦版後台入口')
        self.assertEqual(self.url_open('/my/security').status_code, 200, '啟用頁打得開')
        self.assertIn('我的工程案件', self.url_open('/my').text, '角色帳號的 /my 首頁＝手機工程清單（同前台帳號）')
        # 監造方後台人員：登入導向照舊（不去手機）、沒有電腦版後台入口
        self.url_open('/web/session/logout')
        response = self.url_open('/web/login', data={
            'login': self.staff.login, 'password': self.PASSWORD, 'csrf_token': self._csrf()}, allow_redirects=False)
        self.assertNotIn('/construction', response.headers.get('Location', ''), '監造方後台人員導向照舊')

    def _csrf(self):
        page = self.url_open('/web/login')
        import re
        match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        return match.group(1) if match else ''

    def test_backend_phone_menu_only_for_role_accounts(self):
        menu = self.env.ref(f'{D}.menu_role_phone_home')
        self.assertIn(menu.id, self.env['ir.ui.menu'].with_user(self.role)._visible_menu_ids())
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(self.staff)._visible_menu_ids())
        self.assertEqual(menu.action.url, '/construction')


@tagged('post_install', '-at_install', MODULE)
class TestRoleWaterLevelScope(RolePhoneCase):
    """「其他」類的水位：監造方角色帳號後台讀得到範圍內工程的（唯讀），營造方角色帳號 0 筆；手機看得到的 ⊆ 後台。"""

    def test_water_level_scope(self):
        Device = self.env['water.level.device']

        def device(project, uid):
            site = self.env['water.level.site'].create({
                'name': f'S2 場域 {uid}', 'site_type': 'project', 'project_id': project.id})
            return Device.create({'name': f'S2 站 {uid}', 'site_id': site.id, 'device_uid': f'S2-WL-{uid}'})
        device_in = device(self.p, 'IN')
        other_co = self.env['res.company'].create({'name': 'S2 別家監造', 'company_type': COMPANY_TYPE_SUPERVISION})
        other_project = self.env['project.project'].create({
            'name': 'S2 別家工程', 'code': 'S2-OTHER', 'company_id': other_co.id, 'state': 'construction'})
        device_out = device(other_project, 'OUT')
        sb, sm = self.new[(SIDE_SUPERVISION, LEVEL_BOSS)], self.new[(SIDE_SUPERVISION, LEVEL_MANAGER)]
        for user in (sb, sm):
            seen = set(Device.with_user(user).search([('id', 'in', (device_in | device_out).ids)]).ids)
            self.assertEqual(seen, {device_in.id}, user.login)
            with self.assertRaises(AccessError):
                device_in.with_user(user).write({'name': 'S2 改'})
            status, res = self._call(user, self.ctrl.portal_water_level_data, self.p.id)
            self.assertEqual({d['id'] for d in res['devices']}, seen, f'{user.login}：手機看得到的＝後台讀得到的')
        for pair in ((SIDE_CONTRACTOR, LEVEL_BOSS), (SIDE_CONTRACTOR, LEVEL_MANAGER)):
            user = self.new[pair]
            self.assertFalse(Device.with_user(user).search_count([]), f'{user.login}：營造方照拒')
            self.assertEqual(self._call(user, self.ctrl.portal_water_level_data, self.p.id)[1],
                             {'error': 'Access denied'})
