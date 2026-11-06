# -*- coding: utf-8 -*-
"""照片的 onchange／create／write／copy 不能拿讀不到的附件帶出內容（11-06 抗辯 F1；合約 §0b-23，線 H）。

``supervision.photo.image`` 是 related ``attachment_id.datas``（sudo 計算）。修之前：
``supervision.photo.onchange([], {'attachment_id': X}, …)`` 回傳任意附件全文——前台營造帳號、監造方、
未啟用兩步驟驗證的營造廠主管都打得到（18.0 既有）。守衛在 construction_supervision_base
（models/relational_input_guard.py）；這裡用照片模型逐一驗。

判準打在使用者看得到的結果上、兩個方向都比（L1④、M-B）：
**對每個（帳號 × 附件），onchange 帶得出內容 ⇔ 本人直接讀得到那個附件，且帶出來的內容等於直接讀到的。**
jt 情境：兩家監造公司共用一庫，各自的帳號只有自己的公司。
"""
import base64

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

SUPERVISOR_ADMIN = 'construction_supervision_base.group_supervisor_admin'
PORTAL_LEADER = 'construction_supervision_base.group_portal_leader'
GUARD_MSG = '沒有讀取權限的紀錄'
SPEC = {'attachment_id': {}, 'image': {}, 'mimetype': {}, 'image_filename': {}}


def _b64(raw):
    return base64.b64encode(raw).decode()


@tagged('post_install', '-at_install', 'construction_photo')
class TestPhotoRelationalGuard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_sa = Company.create({'name': 'H 照片監造 A', 'company_type': 'supervision'})
        cls.co_sb = Company.create({'name': 'H 照片監造 B', 'company_type': 'supervision'})
        cls.co_c = Company.create({'name': 'H 照片營造 C', 'company_type': 'contractor'})
        cls.sup_a = cls._user('hp_sup_a', [SUPERVISOR_ADMIN], cls.co_sa, cls.co_sa)
        cls.sup_b = cls._user('hp_sup_b', [SUPERVISOR_ADMIN], cls.co_sb, cls.co_sb)
        cls.portal_c = cls._user('hp_portal_c', [PORTAL_LEADER], cls.co_c, cls.co_c | cls.co_sa,
                                 extra={'is_contractor_org': True, 'dash_scope_company_id': cls.co_c.id})
        Project = env['project.project']
        cls.p_a = Project.create({'name': 'H 照片工程 A', 'code': 'HP-A', 'company_id': cls.co_sa.id,
                                  'state': 'construction', 'contractor_company_ids': [(6, 0, cls.co_c.ids)]})
        cls.p_b = Project.create({'name': 'H 照片工程 B', 'code': 'HP-B', 'company_id': cls.co_sb.id,
                                  'state': 'construction'})
        env['supervision.project.member'].create({'project_id': cls.p_a.id, 'user_id': cls.portal_c.id})
        Att = env['ir.attachment']
        cls.att_photo_a = Att.create({'name': 'hp_a.png', 'raw': b'PHOTO-A', 'res_model': 'supervision.photo'})
        cls.photo_a = env['supervision.photo'].create({'project_id': cls.p_a.id,
                                                       'attachment_id': cls.att_photo_a.id})
        cls.att_photo_a.write({'res_id': cls.photo_a.id})
        cls.att_photo_b = Att.create({'name': 'hp_b.png', 'raw': b'PHOTO-B', 'res_model': 'supervision.photo'})
        cls.photo_b = env['supervision.photo'].create({'project_id': cls.p_b.id,
                                                       'attachment_id': cls.att_photo_b.id})
        cls.att_photo_b.write({'res_id': cls.photo_b.id})
        # 掛在 B 工程上的附件（例：契約、估驗附件）
        cls.att_pb = Att.create({'name': 'hp_contract_b.pdf', 'raw': b'CONTRACT-B', 'res_model': 'project.project',
                                 'res_id': cls.p_b.id})
        # 沒掛單據、建立者是系統（生產站舊照片 4,373 張的附件就是這種）
        cls.att_orphan = Att.create({'name': 'hp_orphan.png', 'raw': b'ORPHAN'})
        cls.att_own = Att.with_user(cls.sup_a).create({'name': 'hp_own.png', 'raw': b'OWN-A'})
        cls.victims = (cls.att_photo_a, cls.att_photo_b, cls.att_pb, cls.att_orphan, cls.att_own)

    @classmethod
    def _user(cls, login, groups, company, companies, extra=None):
        vals = {'name': login, 'login': login, 'company_id': company.id,
                'company_ids': [(6, 0, companies.ids)],
                'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])]}
        vals.update(extra or {})
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)

    def _photo(self, user):
        return self.env['supervision.photo'].with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def _direct(self, user, attachment):
        """本人直接讀附件內容（read 走的就是核心的附件存取判定）；讀不到回 None。"""
        self.env.invalidate_all()
        try:
            att = attachment.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)
            datas = att.read(['datas'])[0]['datas'] or ''
            return datas.decode() if isinstance(datas, bytes) else datas
        except AccessError:
            return None

    def _onchange(self, user, attachment, **ctx):
        self.env.invalidate_all()
        try:
            result = self._photo(user).with_context(**ctx).onchange(
                {'attachment_id': attachment.id}, ['attachment_id'], SPEC)
            image = result.get('value', {}).get('image')
            return ('OK', image.decode() if isinstance(image, bytes) else image)
        except AccessError as exc:
            return ('DENY', str(exc))

    def test_onchange_matches_direct_read(self):
        """每個（帳號 × 附件）：onchange 帶得出 ⇔ 直接讀得到，且內容相同；讀不到的訊息指名 attachment_id。"""
        outcomes = {}
        for user in (self.sup_a, self.sup_b, self.portal_c):
            for att in self.victims:
                direct = self._direct(user, att)
                status, payload = self._onchange(user, att)
                label = f'{user.login} × {att.name}'
                if direct is None:
                    self.assertEqual(status, 'DENY', f'{label}：直接讀不到，onchange 也不可帶出內容')
                    self.assertIn(GUARD_MSG, payload, label)
                    self.assertIn('（attachment_id）', payload, label)
                else:
                    self.assertEqual(status, 'OK', f'{label}：直接讀得到，onchange 照常（正當用法）：{payload}')
                    self.assertEqual(payload, direct, f'{label}：onchange 帶出的內容要等於直接讀到的')
                outcomes.setdefault(user.login, set()).add(status)
        # 夾具要兩種結果都有（否則上面的斷言可能恆真，M-C）；前台帳號沒有 ir.attachment 的讀取 ACL
        # （前台看照片走帶權限的 /construction/img），所以 ORM 上一律讀不到、onchange 一律擋
        self.assertEqual(outcomes['hp_sup_a'], {'OK', 'DENY'})
        self.assertEqual(outcomes['hp_sup_b'], {'OK', 'DENY'})
        self.assertEqual(outcomes['hp_portal_c'], {'DENY'})
        # 具體的 jt 情境：A 的人拿不到 B 工程的契約附件；B 的人拿得到（他讀得到）
        self.assertEqual(self._onchange(self.sup_a, self.att_pb)[0], 'DENY')
        self.assertEqual(self._onchange(self.sup_b, self.att_pb), ('OK', _b64(b'CONTRACT-B')))

    def test_attachment_check_access_alone_is_not_enough(self):
        """附件的讀取權在 ir.attachment._search 判定：check_access('read') 對內部帳號一律通過，守衛不能只靠它。"""
        att = self.att_orphan.with_user(self.sup_a)
        att.check_access('read')    # 不丟例外——這就是只用 check_access 會漏的地方
        self.assertIsNone(self._direct(self.sup_a, self.att_orphan))
        self.assertEqual(self._onchange(self.sup_a, self.att_orphan)[0], 'DENY')

    def test_context_default_does_not_bypass(self):
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            self._photo(self.sup_a).with_context(default_attachment_id=self.att_pb.id).onchange({}, [], SPEC)
        with self.assertRaises(AccessError):
            self._photo(self.portal_c).with_context(default_attachment_id=self.att_orphan.id).onchange({}, [], SPEC)

    def test_context_default_into_x2many_child_does_not_bypass(self):
        """呼叫端的 context 預設值會一路帶進 x2many 新增的子紀錄（核心行為），而外層只查得到巢狀 vals、
        查不到子模型的預設值——子紀錄那一層不能因為「在另一個模型的 write 裡」就放行（第二輪抗辯 simplifier A）。"""
        project = self.env['project.project'].with_user(self.sup_a).with_context(
            allowed_company_ids=self.sup_a.company_ids.ids).browse(self.p_a.id)
        self.assertIsNone(self._direct(self.sup_a, self.att_pb), '前提：本人讀不到乙工程的附件')
        with self.assertRaisesRegex(AccessError, GUARD_MSG):
            project.with_context(default_attachment_id=self.att_pb.id).write(
                {'photo_ids': [(0, 0, {'notes': 'H 巢狀預設值'})]})
        # 正當用法：預設值是自己讀得到的附件，照常建得出照片
        project.with_context(default_attachment_id=self.att_own.id).write(
            {'photo_ids': [(0, 0, {'notes': 'H 巢狀預設值（自己的）'})]})
        made = self.env['supervision.photo'].search([('notes', '=', 'H 巢狀預設值（自己的）')])
        self.assertEqual(made.attachment_id, self.att_own)

    def test_create_and_write(self):
        Photo = self._photo(self.sup_a)
        with self.assertRaisesRegex(AccessError, GUARD_MSG):
            Photo.create({'project_id': self.p_a.id, 'attachment_id': self.att_pb.id})
        own = Photo.create({'project_id': self.p_a.id, 'attachment_id': self.att_own.id})
        self.assertEqual(own.image, _b64(b'OWN-A').encode(), '正當用法：自己的附件照常建照片')
        # 生產站舊照片：附件 res_id 空白、建立者是系統（本人讀不到附件，但照片讀得到）
        legacy = self.env['supervision.photo'].create({'project_id': self.p_a.id,
                                                       'attachment_id': self.att_orphan.id})
        mine = Photo.browse(legacy.id)
        mine.write({'notes': 'H 備註', 'attachment_id': self.att_orphan.id})   # 現值寫回：不查
        self.assertEqual(mine.notes, 'H 備註')
        with self.assertRaisesRegex(AccessError, GUARD_MSG):
            mine.write({'attachment_id': self.att_pb.id})
        mine.write({'attachment_id': self.att_own.id})
        self.assertEqual(mine.attachment_id, self.att_own)

    def test_existing_record_onchange_unchanged_value(self):
        """既有照片的 onchange：表單上原本就掛著的附件（本人讀不到）不查，改成讀不到的才擋。"""
        legacy = self.env['supervision.photo'].create({'project_id': self.p_a.id,
                                                       'attachment_id': self.att_orphan.id})
        mine = self._photo(self.sup_a).browse(legacy.id)
        self.env.invalidate_all()
        mine.onchange({'attachment_id': self.att_orphan.id, 'name': 'x'}, ['name'], SPEC)
        self.env.invalidate_all()
        with self.assertRaisesRegex(AccessError, GUARD_MSG):
            mine.onchange({'attachment_id': self.att_pb.id}, ['attachment_id'], SPEC)

    def test_copy(self):
        """複製：值來自原紀錄（本人讀得到原照片），不因附件讀不到而擋；呼叫端給的 default 照查。"""
        legacy = self.env['supervision.photo'].create({'project_id': self.p_a.id,
                                                       'attachment_id': self.att_orphan.id})
        mine = self._photo(self.sup_a).browse(legacy.id)
        duplicate = mine.copy()
        self.assertEqual(duplicate.sudo().attachment_id, self.att_orphan)
        with self.assertRaisesRegex(AccessError, GUARD_MSG):
            mine.copy({'attachment_id': self.att_pb.id})
        # 回傳的紀錄不帶複製憑證：之後的 write 照常受守衛
        with self.assertRaisesRegex(AccessError, GUARD_MSG):
            duplicate.write({'attachment_id': self.att_pb.id})
