"""會員匯入：範本、非 Contact Creation 也能建聯絡人、暫存檔的保護與清除。"""

import base64
import io

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from .common import force_internal_user_on
from odoo.tools import config

from .. import tools_pii
from .test_pii import TEST_KEY

COLUMNS = ['會員編號', '姓名', '身分證字號', 'Email', '手機']
FIELDS = ['member_no', 'name', 'national_id', 'email', 'mobile']


def make_csv(rows):
    buf = io.StringIO()
    buf.write(','.join(COLUMNS) + '\n')
    for row in rows:
        buf.write(','.join(row) + '\n')
    return buf.getvalue().encode()


@tagged('post_install', '-at_install')
class TestMemberImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._old_key = config.options.get('assoc_pii_key')
        config.options['assoc_pii_key'] = TEST_KEY
        cls.company = cls.env.company
        # 非 system 的公會管理員：沒有 Contact Creation 也要能建會員
        cls.admin_user = cls.env['res.users'].create({
            'name': '公會管理員（測試）',
            'login': 'assoc_admin_test',
            'company_id': cls.company.id,
            'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_base.group_assoc_admin').id])],
        })

    @classmethod
    def tearDownClass(cls):
        if cls._old_key is None:
            config.options.pop('assoc_pii_key', None)
        else:
            config.options['assoc_pii_key'] = cls._old_key
        super().tearDownClass()

    def test_admin_without_contact_creation_can_create_member(self):
        user = self.admin_user
        self.assertFalse(user.has_group('base.group_partner_manager'),
                         '前提：公會管理員不該有 Contact Creation')
        member = self.env['assoc.member'].with_user(user).create({
            'name': '受控 sudo 測試', 'member_no': 'I001'})
        self.assertTrue(member.partner_id)
        self.assertEqual(member.partner_id.company_id, self.company)
        self.assertEqual(member.name, '受控 sudo 測試')

    def test_internal_user_partner_cannot_become_member(self):
        """內部使用者的聯絡人不能被指定成會員：否則改 email → 重設密碼即可劫持帳號。"""
        with self.assertRaises(ValidationError):
            self.env['assoc.member'].create({
                'partner_id': self.env.user.partner_id.id, 'member_no': 'I002'})

    def test_partner_from_other_company_rejected(self):
        """聯絡人沒有公司或屬於別的公會都不行（res.partner.company_id 多數是 NULL）。"""
        no_company = self.env['res.partner'].create({'name': '無公司聯絡人'})
        with self.assertRaises(ValidationError):
            self.env['assoc.member'].create({
                'partner_id': no_company.id, 'member_no': 'I003'})
        other_company = self.env['res.company'].create({'name': '他公會（匯入測試）'})
        other_partner = self.env['res.partner'].create({
            'name': '他公會聯絡人', 'company_id': other_company.id})
        with self.assertRaises(ValidationError):
            self.env['assoc.member'].create({
                'partner_id': other_partner.id, 'member_no': 'I004'})

    def test_import_error_points_at_the_right_row(self):
        """一列壞資料不能毒死整批，錯誤也要歸在那一列（帶會員編號、不回顯身分證）。"""
        rows = [['I210', '正常列', 'C123456781', '', ''],
                ['I211', '壞檢查碼', 'A123456788', '', '']]
        _wizard, result = self._run_import(self.admin_user, rows)
        messages = ' '.join(m['message'] for m in result.get('messages', []))
        self.assertIn('I211', messages, '要指出是哪一列')
        self.assertNotIn('A123456788', messages, '不得回顯身分證')
        self.assertNotIn('I210', messages, '沒問題的那列不該被報錯')

    def test_import_template_exists(self):
        import odoo.modules
        templates = self.env['assoc.member'].get_import_templates()
        self.assertTrue(templates)
        path = templates[0]['template'].lstrip('/')
        module, relative = path.split('/', 1)
        full = odoo.modules.module.get_module_resource(module, *relative.split('/'))
        self.assertTrue(full, '範本檔要真的存在，否則使用者按下載會 404：%s' % path)

    def _run_import(self, user, rows, dryrun=False, limit=None, wizard=None, skip=0):
        if wizard is None:
            wizard = self.env['base_import.import'].with_user(user).create({
                'res_model': 'assoc.member',
                'file': make_csv(rows),
                'file_type': 'text/csv',
                'file_name': 'members.csv',
            })
        options = {'headers': True, 'separator': ',', 'quoting': '"', 'has_headers': True}
        if limit:
            options['limit'] = limit
        if skip:
            options['skip'] = skip  # 前端續傳時會帶上次回傳的 nextrow
        result = wizard.execute_import(FIELDS, COLUMNS, options, dryrun=dryrun)
        return wizard, result

    def test_import_creates_members_and_clears_stash(self):
        rows = [['I100', '匯入甲', 'A123456789', 'a@example.com', '0912000111'],
                ['I101', '匯入乙', 'B234567894', 'b@example.com', '0912000222']]
        wizard, result = self._run_import(self.admin_user, rows)
        self.assertFalse(result.get('messages'), result.get('messages'))
        self.assertEqual(len(result['ids']), 2)
        members = self.env['assoc.member'].browse(result['ids'])
        self.assertEqual(members.mapped('national_id_masked'), ['A1******89', 'B2******94'])
        self.assertFalse(wizard.exists(), '匯入成功後暫存檔要立刻刪掉（含身分證明文）')

    def test_dryrun_keeps_stash(self):
        rows = [['I110', '試算甲', 'A123456789', '', '']]
        wizard, result = self._run_import(self.admin_user, rows, dryrun=True)
        self.assertTrue(wizard.exists(), '試算階段還要留著給使用者修正')

    def test_bad_row_keeps_stash_for_retry(self):
        rows = [['I120', '格式錯', '12345', '', '']]
        wizard, result = self._run_import(self.admin_user, rows)
        self.assertTrue(result.get('messages'))
        self.assertTrue(wizard.exists(), '有錯誤時要留著讓使用者改')

    def test_other_user_cannot_read_stash(self):
        """核心 ACL 對所有內部使用者開放且沒有 rule：他公會職員能讀到含身分證的上傳檔。"""
        rows = [['I130', '暫存保護', 'A123456789', '', '']]
        wizard, _result = self._run_import(self.admin_user, rows, dryrun=True)
        other = self.env['res.users'].create({
            'name': '他人', 'login': 'assoc_other_test',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        found = self.env['base_import.import'].with_user(other).search([('id', '=', wizard.id)])
        self.assertFalse(found, '別人的匯入暫存不可見')

    def test_gc_removes_stale_stash(self):
        rows = [['I140', '逾時暫存', 'A123456789', '', '']]
        wizard, _result = self._run_import(self.admin_user, rows, dryrun=True)
        self.env.cr.execute(
            "UPDATE base_import_import SET write_date = now() - interval '2 hours' WHERE id = %s",
            [wizard.id])
        wizard.invalidate_recordset()
        self.env['base_import.import']._gc_assoc_member_imports()
        self.assertFalse(wizard.exists())

    def test_batched_import_keeps_stash_until_last_batch(self):
        """前端依 nextrow 用同一筆暫存續傳；第一批就刪會讓後面整批 MissingError。"""
        rows = [[f'I2{i:02d}', f'分批{i}', '', '', ''] for i in range(1, 6)]
        wizard, first = self._run_import(self.admin_user, rows, limit=2)
        self.assertTrue(first.get('nextrow'), '前提：這批之後還有資料')
        self.assertTrue(wizard.exists(), '還沒匯完就不能刪暫存')

        second = self._run_import(self.admin_user, rows, limit=2, wizard=wizard,
                                  skip=first['nextrow'])[1]
        self.assertFalse(second.get('messages'), second.get('messages'))
        self.assertTrue(wizard.exists())

        third = self._run_import(self.admin_user, rows, wizard=wizard, skip=second['nextrow'])[1]
        self.assertFalse(third.get('nextrow'))
        self.assertFalse(wizard.exists(), '最後一批完成才刪暫存')
        created = self.env['assoc.member'].search_count([('member_no', 'like', 'I2')])
        self.assertEqual(created, 5, '五筆都要匯進去')

    def test_partner_company_cleared_afterwards_is_rejected(self):
        """聯絡人的公司事後被清空（例如系統管理員改過）→ 受控 sudo 仍要擋。

        res.partner.company_id 多數是 NULL，寫成 `company_id and company_id != …`
        的話這道檢查對大多數聯絡人根本沒生效。
        """
        member = self.env['assoc.member'].create({'name': '事後被清公司', 'member_no': 'I300'})
        member.partner_id.sudo().company_id = False
        with self.assertRaises(AccessError):
            member.write({'email': 'x@example.com'})

    def test_archived_internal_user_partner_is_rejected(self):
        """已封存的內部使用者，partner_share 會變成 True——不能用它當判準。

        聯絡人的公司先設成本公會，才不會被 `_check_partner_company` 搶先擋下，
        這樣這條測試打的就只有「內部使用者」那一關。
        """
        internal = self.env['res.users'].create({
            'name': '離職職員', 'login': 'assoc_left_staff',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        internal.partner_id.sudo().company_id = self.company.id
        internal.action_archive()
        self.assertTrue(internal.partner_id.partner_share, '前提：封存後 partner_share 變 True')
        with self.assertRaises(ValidationError):
            self.env['assoc.member'].create({
                'partner_id': internal.partner_id.id, 'member_no': 'I301'})

    def test_roster_contact_cannot_be_turned_into_an_internal_user(self):
        """名冊那筆聯絡人不可以被拿去開內部帳號——**在源頭擋**。

        原本這裡只驗「事後變成內部使用者 → 寫入被擋」，而那個狀態一旦成立，
        公會管理員就永遠改不動那位會員的姓名／照片／Email
        （第十二輪紅隊）。現在那條路在 ORM 層就走不通。
        """
        member = self.env['assoc.member'].create({'name': '之後變員工', 'member_no': 'I302'})
        with self.assertRaises(ValidationError):
            self.env['res.users'].create({
                'name': '之後變員工', 'login': 'assoc_later_staff',
                'partner_id': member.partner_id.id,
                'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})

    def test_writes_are_still_blocked_if_that_state_is_forced(self):
        """萬一那個狀態還是成立了（shell／直接寫 DB），底下那道防線仍要在。

        新約束擋的是正常入口，不是所有路徑——所以縱深不能因為加了約束就拆掉
        （L2⑯：加了一條更廣的檢查之後，舊的那條就沒人守了）。
        """
        member = self.env['assoc.member'].create({'name': '硬安上去', 'member_no': 'I303'})
        force_internal_user_on(self.env, member.partner_id, 'assoc_forced_staff')
        with self.assertRaises(AccessError):
            member.write({'email': 'later@example.com'})
