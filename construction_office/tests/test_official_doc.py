# -*- coding: utf-8 -*-
"""公文（models/official_doc.py、security/office_rules.xml；淞源 2026-11-10 會議 C10）。

淞源技師要的是「用日期、機關、文號、主旨關鍵字找得到公文」；另外鎖住誰看得到：
公文屬於所屬公司，同一個工程上的另一方（監造↔營造、營造 A↔營造 B）看不到。
"""
from datetime import timedelta

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import BOSS, DOC_MODEL, FIELD, OfficeCase


@tagged('post_install', '-at_install', 'construction_office')
class TestOfficialDoc(OfficeCase):

    # ── 預設值 ──────────────────────────────────────────────────────────
    def test_state_default_follows_deadline(self):
        filed = self._doc('存查的', self.co_s, self.p1)
        pending = self._doc('要辦的', self.co_s, self.p1, reply_deadline=self.tomorrow)
        explicit = self._doc('指定存查', self.co_s, self.p1, reply_deadline=self.tomorrow, state='filed')
        self.assertEqual((filed.state, pending.state, explicit.state), ('filed', 'pending', 'filed'))
        self.assertEqual(filed.direction, 'incoming')
        self.assertEqual(filed.doc_date, self.today)

    def test_receive_date_not_before_doc_date(self):
        with self.assertRaises(ValidationError):
            self._doc('日期顛倒', self.co_s, self.p1, doc_date=self.today, receive_date=self.yesterday)

    # ── 搜尋條件（後台總表與手機頁共用）──────────────────────────────────
    def test_search_by_keyword_date_direction_state(self):
        water = self._doc('磺港溪護岸工程施工計畫審查意見', self.co_s, self.p1, organization='新北市政府水利局',
                          doc_number='新北水工字第1150012345號', doc_date=self.today - timedelta(days=40))
        traffic = self._doc('交通維持計畫核定', self.co_s, self.p1, organization='臺北市政府交通局',
                            doc_number='北市交工字第1150054321號', doc_date=self.today - timedelta(days=5),
                            direction='outgoing', reply_deadline=self.tomorrow)
        other = self._doc('驗收會勘通知', self.co_s, self.p2, organization='新北市政府水利局',
                          doc_number='新北水工字第1150099999號', doc_date=self.today)
        docs = water | traffic | other

        def find(**kwargs):
            return self.Doc.search([('id', 'in', docs.ids)] + self.Doc._search_domain(**kwargs))

        # 關鍵字：主旨、文號、機關任一含有
        self.assertEqual(find(keyword='審查意見'), water)
        self.assertEqual(find(keyword='1150054321'), traffic)
        self.assertEqual(find(keyword='水利局'), water | other)
        # 多個詞：全部都要符合（可以落在不同欄位）
        self.assertEqual(find(keyword='水利局 會勘'), other)
        self.assertEqual(find(keyword='水利局 交通'), self.Doc)
        # 日期起迄（含頭含尾）
        self.assertEqual(find(date_from=self.today - timedelta(days=5)), traffic | other)
        self.assertEqual(find(date_to=self.today - timedelta(days=6)), water)
        self.assertEqual(find(date_from=self.today, date_to=self.today), other)
        # 收發文、辦理狀態
        self.assertEqual(find(direction='outgoing'), traffic)
        self.assertEqual(find(state='pending'), traffic)
        # 組合
        self.assertEqual(find(keyword='水利局', date_from=self.today - timedelta(days=1)), other)
        # 不認得的收發文／狀態值不當條件（網址被亂改時不能變成查不到或報錯）
        self.assertEqual(find(direction='x', state='y'), docs)

    # ── 逾期 ────────────────────────────────────────────────────────────
    def test_overdue_only_pending_past_deadline(self):
        late = self._doc('逾期', self.co_s, self.p1, reply_deadline=self.today - timedelta(days=3))
        due_today = self._doc('今天到期', self.co_s, self.p1, reply_deadline=self.today)
        done = self._doc('已辦', self.co_s, self.p1, reply_deadline=self.yesterday, state='done')
        no_deadline = self._doc('沒期限', self.co_s, self.p1)
        docs = late | due_today | done | no_deadline
        self.assertEqual([d.is_overdue for d in docs], [True, False, False, False])
        self.assertEqual((late.days_left, due_today.days_left), (-3, 0))
        self.assertEqual(self.Doc.search([('id', 'in', docs.ids), ('is_overdue', '=', True)]), late)
        self.assertEqual(self.Doc.search([('id', 'in', docs.ids), ('is_overdue', '=', False)]),
                         due_today | done | no_deadline)
        late.action_mark_done()
        self.assertFalse(late.is_overdue)

    # ── 所屬公司 ────────────────────────────────────────────────────────
    def test_contractor_created_doc_always_belongs_to_own_company(self):
        """營造方建立的公文一律是自己的範圍公司——傳別家公司、用 sudo 都一樣；之後也不能改。"""
        doc = self.Doc.with_user(self.a_field).sudo().create(
            {'subject': '營造 A 建的', 'project_id': self.p1.id, 'company_id': self.co_b.id})
        self.assertEqual(doc.company_id, self.co_a)
        with self.assertRaises(AccessError):
            doc.with_user(self.a_field).sudo().write({'company_id': self.co_b.id})
        self.assertEqual(doc.company_id, self.co_a)
        # 後台人員可以改（代操時把公文歸給營造廠）
        doc.with_user(self.staff).write({'company_id': self.co_s.id})
        self.assertEqual(doc.company_id, self.co_s)

    # ── 讀取範圍 ────────────────────────────────────────────────────────
    def test_supervision_portal_member_boss_outsider(self):
        on_p1 = self._doc('S 的工程一公文', self.co_s, self.p1)
        on_p2 = self._doc('S 的工程二公文', self.co_s, self.p2)
        no_project = self._doc('S 的公司共通公文', self.co_s)
        docs = on_p1 | on_p2 | no_project
        self.assertEqual(self._visible(self.sup_field, docs), on_p1, '成員只看自己參與的工程')
        self.assertEqual(self._visible(self.sup_boss, docs), docs, '老闆看得到全部（含沒掛工程的）')
        self.assertEqual(self._visible(self.sup_outsider, docs), self.Doc, '不是成員就看不到')
        self.assertEqual(self._visible(self.staff, docs), docs)

    def test_other_party_on_same_project_cannot_see(self):
        """同一個工程：監造 S 的公文營造 A 看不到，營造 A 的公文監造方前台帳號也看不到。"""
        s_doc = self._doc('監造的公文', self.co_s, self.p1)
        a_doc = self._doc('營造 A 的公文', self.co_a, self.p1)
        b_doc = self._doc('營造 B 的公文（掛在工程一）', self.co_b, self.p1)
        docs = s_doc | a_doc | b_doc
        self.assertEqual(self._visible(self.sup_field, docs), s_doc)
        self.assertEqual(self._visible(self.sup_boss, docs), s_doc)
        # 後台人員開了 S 與 A 兩家公司：看得到這兩家的，B 的看不到
        self.assertEqual(self._visible(self.staff, docs), s_doc | a_doc)

    def test_supervision_portal_with_contractor_in_allowed_companies(self):
        """監造方前台帳號的允許公司裡有營造廠（例：要看營造廠名下的工程）時，仍看不到那家營造廠的公文——
        同一個工程上的監造與營造廠彼此看不到對方的公文（淞源權限審查 low #5；後台的監造方角色帳號
        由 construction_company_dashboard 的 rule_scope 同樣只看監造公司的）。後台人員不受影響。"""
        boss = self._user('office_sup_boss_sa', [BOSS], self.co_s, self.co_s | self.co_a, supervision=True)
        member = self._user('office_sup_field_sa', [FIELD], self.co_s, self.co_s | self.co_a,
                            supervision=True, member_of=self.p1)
        s_doc = self._doc('監造的公文', self.co_s, self.p1)
        a_doc = self._doc('營造 A 在工程一的公文', self.co_a, self.p1)
        a_common = self._doc('營造 A 的公司共通公文', self.co_a)
        docs = s_doc | a_doc | a_common
        # 成員名單是儲存的計算欄位（工程的 member_user_ids）：規則條件走它，先寫進資料庫再以帳號身分查
        self.env.flush_all()
        self.assertEqual(self._visible(boss, docs), s_doc, '老闆：營造 A 的公文一份都看不到')
        self.assertEqual(self._visible(member, docs), s_doc, '工程一的成員：同工程上營造 A 的公文看不到')
        self.assertEqual(self._visible(self.staff, docs), docs, '後台人員：允許公司內照舊都看得到')

    def test_contractor_portal_sees_only_own_company(self):
        """營造 A 的前台帳號只看得到所屬公司＝A 的公文（要有 construction_company_dashboard 的範圍規則）。"""
        if not self.dashboard_installed:
            self.skipTest('沒裝 construction_company_dashboard：營造方的範圍收窄由它負責')
        s_doc = self._doc('監造的公文', self.co_s, self.p1)
        a_doc = self._doc('營造 A 的公文', self.co_a, self.p1)
        a_other_project = self._doc('營造 A 在工程二的公文', self.co_a, self.p2)
        docs = s_doc | a_doc | a_other_project
        self.assertEqual(self._visible(self.a_field, docs), a_doc, 'A 的現場人員：自家的、而且是自己參與的工程')
        self.assertEqual(self._visible(self.a_viewer, docs), a_doc)

    def test_portal_accounts_cannot_write_through_orm(self):
        doc = self._doc('唯讀', self.co_s, self.p1)
        for user in (self.sup_field, self.sup_boss, self.a_field):
            with self.assertRaises(AccessError, msg=user.login):
                doc.with_user(user).write({'subject': '被改了'})
            with self.assertRaises(AccessError, msg=user.login):
                self.Doc.with_user(user).create({'subject': '前台直接建', 'project_id': self.p1.id})

    # ── 附件 ────────────────────────────────────────────────────────────
    def test_attachments_are_the_ones_linked_to_the_doc(self):
        doc = self._doc('有附件', self.co_s, self.p1)
        other = self._doc('別份', self.co_s, self.p1)
        Attachment = self.env['ir.attachment']
        mine = Attachment.create({'name': '掃描.pdf', 'raw': b'%PDF-1', 'res_model': DOC_MODEL, 'res_id': doc.id})
        theirs = Attachment.create({'name': '別份.pdf', 'raw': b'%PDF-2', 'res_model': DOC_MODEL, 'res_id': other.id})
        unrelated = Attachment.create({'name': '無關.pdf', 'raw': b'%PDF-3'})
        doc.invalidate_recordset()
        self.assertEqual((doc.attachment_ids, doc.attachment_count), (mine, 1))
        # 把別人的附件 id 寫進 attachment_ids 沒有作用（欄位是唯讀的計算結果）
        doc.write({'attachment_ids': [(6, 0, (theirs | unrelated).ids)]})
        doc.invalidate_recordset()
        self.assertEqual(doc.attachment_ids, mine)
        self.assertEqual(theirs.res_id, other.id)
        self.assertFalse(unrelated.res_id)
