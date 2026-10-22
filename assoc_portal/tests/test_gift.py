"""禮品名單、領取與造冊（計畫 §2.4、§9）。

名單是**快照**：產生之後不隨會員狀態浮動，否則同一個人早上領得到、
下午領不到，現場無法處理。唯一在領取當下才判斷的是「出席」——
名單要在報到開始前就印得出來。

領取走單一條件 UPDATE，重領、未出席、非現場品項、沒有委託關係都在 WHERE 裡擋，
兩台報到台同時按只有一台拿得到那一列。
"""

import json

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_base.tests.common import guild_today

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_portal.models.assoc_gift import GUARD_GIFT
from odoo.addons.assoc_portal.models.assoc_gift_export import GUARD_GIFT_EXPORT

from .common import PASSWORD, PortalCase


class GiftCase(PortalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.desk_user = cls.env['res.users'].create({
            'name': '報到台（M9）', 'login': 'm9_desk',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_meeting.group_meeting_desk').id])],
        })
        cls.staff_user = cls.env['res.users'].create({
            'name': '職員（M9）', 'login': 'm9_staff',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_base.group_assoc_staff').id])],
        })
        cls.meeting = cls.env['assoc.meeting'].create({
            'name': 'M9 會員大會', 'kind': 'assembly', 'company_id': cls.company.id,
            'date_begin': fields.Datetime.now()})
        cls.other = cls.new_member('M9002')
        cls.third = cls.new_member('M9003')
        cls.meeting.action_open_checkin()

    def campaign(self, eligibility='attendees', items=(('紀念品', 'pickup', 0),)):
        record = self.env['assoc.gift.campaign'].with_user(self.admin_user).create({
            'name': '禮品 %s' % eligibility, 'company_id': self.company.id,
            'meeting_id': self.meeting.id, 'eligibility': eligibility,
        })
        for name, delivery, value in items:
            self.env['assoc.gift.item'].with_user(self.admin_user).create({
                'campaign_id': record.id, 'name': name,
                'delivery': delivery, 'unit_value': value})
        return record

    def open_campaign(self, **kw):
        record = self.campaign(**kw)
        record.action_ready()
        record.action_open()
        return record

    def rows_of(self, campaign, member):
        return self.env['assoc.gift.entitlement'].sudo().search([
            ('campaign_id', '=', campaign.id), ('member_id', '=', member.id)])

    def check_in(self, member):
        attendance = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', self.meeting.id), ('member_id', '=', member.id)], limit=1)
        attendance._checkin_by_code(self.meeting, member.barcode)
        return attendance

    def gift_proxy(self, principal, holder):
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, principal, holder, purpose='gift', channel='backend')
        proxy._try_activate()
        return proxy


@tagged('post_install', '-at_install')
class TestGiftEntitlement(GiftCase):

    def test_ready_builds_one_row_per_item_and_member(self):
        campaign = self.campaign(items=(('紀念品', 'pickup', 0), ('毛巾', 'pickup', 0)))
        created = campaign.action_ready()
        members = self.meeting.attendance_ids.member_id
        self.assertEqual(created, len(members) * 2)
        self.assertEqual(campaign.state, 'ready')
        self.assertTrue(campaign.snapshot_at)
        self.assertEqual(len(self.rows_of(campaign, self.member)), 2)

    def test_ready_is_idempotent_and_only_fills_gaps(self):
        """現場常常臨時加一個品項：重按一次只補缺的，已領走的不會被動到。"""
        campaign = self.campaign()
        campaign.action_ready()
        before = len(campaign.entitlement_ids)
        self.assertEqual(campaign.action_ready(), 0, '沒有新品項就不該再建列')
        self.env['assoc.gift.item'].with_user(self.admin_user).create({
            'campaign_id': campaign.id, 'name': '加碼品', 'delivery': 'pickup'})
        added = campaign.action_ready()
        self.assertEqual(added, len(self.meeting.attendance_ids.member_id))
        self.assertEqual(len(campaign.entitlement_ids), before + added)

    def test_fee_current_eligibility_filters(self):
        """「會費有效」的口徑用的是產生名單**當下**的狀態。"""
        self.member.sudo().fee_paid_opening = guild_today()   # 公會時區，不是 UTC
        campaign = self.campaign(eligibility='fee_current')
        campaign.action_ready()
        listed = campaign.entitlement_ids.member_id
        self.assertIn(self.member, listed)
        self.assertNotIn(self.other, listed, '沒有繳費紀錄的不該在名單上')

    def test_entitlement_needs_the_sentinel(self):
        """報到台對權利名單有寫入 ACL：truthy context 是可偽造的（P23）。"""
        campaign = self.open_campaign()
        row = self.rows_of(campaign, self.member).with_user(self.desk_user)
        for context in ({}, {'assoc_gift': True}, {'assoc_gift': 1}):
            with self.assertRaises(AccessError, msg=str(context)):
                row.with_context(**context).write({'state': 'claimed'})
        row.with_context(**{GUARD_GIFT: GUARD}).write({'state': 'claimed'})
        self.assertEqual(self.rows_of(campaign, self.member).state, 'claimed')

    def test_entitlement_cannot_be_created_claimed(self):
        """只看 vals 的守衛擋不住 `default_state`（§16 通則 1）。"""
        campaign = self.campaign()
        item = campaign.item_ids[0]
        with self.assertRaises(UserError):
            self.env['assoc.gift.entitlement'].with_user(self.admin_user).with_context(
                default_state='claimed').create({
                    'campaign_id': campaign.id, 'item_id': item.id,
                    'member_id': self.member.id})

    def test_campaign_definition_locks_once_the_list_exists(self):
        """名單是快照：改了發放對象，已經發出去的權利列就對不上它宣稱的口徑。"""
        campaign = self.campaign()
        campaign.write({'eligibility': 'active_members'})     # 還沒產生名單，隨便改
        campaign.action_ready()
        with self.assertRaises(AccessError):
            campaign.write({'eligibility': 'fee_current'})
        with self.assertRaises(AccessError):
            campaign.write({'meeting_id': False})
        campaign.write({'name': '改名字沒問題'})

    def test_item_amount_stays_editable_but_delivery_locks(self):
        """金額要改得動，發放方式不行。

        `unit_value`／`qty` **不在快照裡**——造冊時才讀當下的值，所以打錯要改得回來。
        鎖住它們的話唯一的補救是重建名單，而重建又被「已有人領取」擋住，等於永遠改不了。
        `delivery` 則是權利列的 stored related，改了會讓已產生的列對不上快照。
        """
        campaign = self.campaign(items=(('禮金', 'cash_list', 2000),))
        campaign.action_ready()
        item = campaign.item_ids[0].with_user(self.admin_user)
        item.write({'unit_value': 500, 'qty': 2, 'name': '車馬費', 'sequence': 5})
        self.assertEqual(item.unit_value, 500)
        with self.assertRaises(AccessError):
            item.write({'delivery': 'pickup'})

    def test_reset_list_only_before_anyone_claims(self):
        campaign = self.open_campaign()
        campaign.action_reset_list()
        self.assertEqual(campaign.state, 'draft')
        self.assertFalse(campaign.entitlement_ids)
        campaign.action_ready()
        campaign.action_open()
        self.check_in(self.member)
        self.rows_of(campaign, self.member)._claim(campaign, self.member, True)
        # 要斷言**訊息**：拿掉這道守衛之後 `unlink()` 自己那道照樣會擋，
        # 只斷言例外型別的話分不出是哪一道在擋，而外層這道的價值正是
        # 「說得出有幾筆」與「不做到一半」
        with self.assertRaises(UserError) as caught:
            campaign.action_reset_list()
        self.assertIn('名單不能重建', str(caught.exception))

    def test_campaign_actions_are_admin_only(self):
        """活動動作限公會管理員。

        ACL 已經擋得住（權利名單的 create 只給管理員），這道是第二層——
        但它決定了**訊息**，而且擋在做任何事之前。
        """
        campaign = self.campaign()
        for user in (self.desk_user, self.staff_user):
            with self.assertRaises(AccessError, msg=user.login) as caught:
                campaign.with_user(user).action_ready()
            self.assertIn('只有公會管理員', str(caught.exception))
        campaign.action_ready()
        for user in (self.desk_user, self.staff_user):
            with self.assertRaises(AccessError, msg=user.login):
                campaign.with_user(user).action_open()
            with self.assertRaises(AccessError, msg=user.login):
                campaign.with_user(user).action_reset_list()

    def test_staff_cannot_touch_the_list(self):
        campaign = self.open_campaign()
        row = self.rows_of(campaign, self.member)
        with self.assertRaises(AccessError):
            row.with_user(self.staff_user).with_context(
                **{GUARD_GIFT: GUARD}).write({'state': 'claimed'})


@tagged('post_install', '-at_install')
class TestGiftClaim(GiftCase):

    def claim(self, campaign, holder, rows=None, scanned=True, reason=None):
        rows = rows if rows is not None else self.rows_of(campaign, holder)
        return rows.with_user(self.desk_user)._claim(campaign, holder, scanned, reason)

    def test_claim_marks_the_row(self):
        campaign = self.open_campaign()
        self.check_in(self.member)
        result = self.claim(campaign, self.member)
        row = self.rows_of(campaign, self.member)
        self.assertEqual(result[row.id], 'claimed')
        self.assertEqual(row.state, 'claimed')
        self.assertEqual(row.claim_channel, 'scan_self')
        self.assertEqual(row.holder_member_id, self.member)
        self.assertTrue(row.claimed_at)

    def test_second_claim_reports_already_not_an_error(self):
        """現場不能讓人以為系統壞了：重領要回「已經領過」而不是例外。"""
        campaign = self.open_campaign()
        self.check_in(self.member)
        self.claim(campaign, self.member)
        row = self.rows_of(campaign, self.member)
        self.assertEqual(self.claim(campaign, self.member)[row.id], 'already')
        self.assertEqual(row.state, 'claimed')

    def test_not_attended_cannot_claim(self):
        """發放對象是「大會出席者」時，出席在**領取當下**才檢查。"""
        campaign = self.open_campaign()
        row = self.rows_of(campaign, self.member)
        self.assertEqual(self.claim(campaign, self.member)[row.id], 'not_attended')
        self.assertEqual(row.state, 'pending')
        self.check_in(self.member)
        self.assertEqual(self.claim(campaign, self.member)[row.id], 'claimed')

    def test_active_members_eligibility_does_not_require_attendance(self):
        campaign = self.open_campaign(eligibility='active_members')
        row = self.rows_of(campaign, self.member)
        self.assertEqual(self.claim(campaign, self.member)[row.id], 'claimed')

    def test_non_pickup_items_are_not_claimable_at_the_desk(self):
        """造冊發放的品項不能在現場領走：那份是要匯出交給對方發的。"""
        campaign = self.open_campaign(items=(('禮券', 'edenred', 1000),))
        self.check_in(self.member)
        row = self.rows_of(campaign, self.member)
        self.assertEqual(self.claim(campaign, self.member)[row.id], 'not_pickup')
        self.assertEqual(row.state, 'pending')

    def test_cannot_claim_before_the_campaign_opens(self):
        campaign = self.campaign()
        campaign.action_ready()
        self.check_in(self.member)
        with self.assertRaises(UserError):
            self.claim(campaign, self.member)

    def test_cannot_claim_someone_elses_row_without_a_proxy(self):
        campaign = self.open_campaign(eligibility='active_members')
        stranger_row = self.rows_of(campaign, self.other)
        result = self.claim(campaign, self.member, rows=stranger_row)
        self.assertEqual(result[stranger_row.id], 'no_permission')
        self.assertEqual(stranger_row.state, 'pending')

    def test_manual_claim_records_the_reason_and_writes_audit(self):
        campaign = self.open_campaign(eligibility='active_members')
        Audit = self.env['assoc.audit.log'].sudo()
        before = Audit.search_count([('action', '=', 'gift_manual_claim')])
        self.claim(campaign, self.member, scanned=False, reason='忘記帶卡，已核對身分證')
        row = self.rows_of(campaign, self.member)
        self.assertEqual(row.claim_channel, 'manual')
        self.assertEqual(row.manual_reason, '忘記帶卡，已核對身分證')
        self.assertEqual(Audit.search_count([('action', '=', 'gift_manual_claim')]), before + 1)

    def test_claimable_list_shows_blocked_rows_with_a_reason(self):
        """未出席的要**列出來**並寫明原因。

        畫面上沒有的話，承辦會以為系統壞了而改用手動——
        而手動就繞過出席檢查了。
        """
        campaign = self.open_campaign()
        rows = self.env['assoc.gift.entitlement']._claimable_for(campaign, self.member)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['blocked'])
        self.assertTrue(rows[0]['blocked_reason'])
        self.check_in(self.member)
        rows = self.env['assoc.gift.entitlement']._claimable_for(campaign, self.member)
        self.assertFalse(rows[0]['blocked'])


@tagged('post_install', '-at_install')
class TestGiftProxy(GiftCase):

    def test_holder_can_claim_for_the_principal(self):
        campaign = self.open_campaign(eligibility='active_members')
        self.gift_proxy(self.other, self.member)
        rows = self.rows_of(campaign, self.member) | self.rows_of(campaign, self.other)
        result = rows.with_user(self.desk_user)._claim(campaign, self.member, True)
        self.assertEqual(set(result.values()), {'claimed'})
        self.assertEqual(self.rows_of(campaign, self.other).claim_channel, 'scan_proxy')
        self.assertEqual(self.rows_of(campaign, self.member).claim_channel, 'scan_self')

    def test_cancelled_proxy_cannot_claim(self):
        campaign = self.open_campaign(eligibility='active_members')
        proxy = self.gift_proxy(self.other, self.member)
        proxy.sudo().action_cancel('委託人自己來了')
        row = self.rows_of(campaign, self.other)
        result = row.with_user(self.desk_user)._claim(campaign, self.member, True)
        self.assertEqual(result[row.id], 'no_permission')
        self.assertEqual(row.state, 'pending')

    def test_holder_limit_is_one(self):
        """每人最多代領 1 人（唯一索引，M7 建的）。"""
        self.gift_proxy(self.other, self.member)
        second = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.third, self.member, purpose='gift', channel='backend')
        self.assertEqual(second._try_activate(), 'rejected')
        self.assertEqual(second.state, 'rejected')

    def test_lookup_includes_the_principals_rows(self):
        campaign = self.open_campaign(eligibility='active_members')
        self.gift_proxy(self.other, self.member)
        rows = self.env['assoc.gift.entitlement']._claimable_for(campaign, self.member)
        owners = {row['member_id'] for row in rows}
        self.assertEqual(owners, {self.member.id, self.other.id})
        self.assertFalse(all(row['is_self'] for row in rows))


@tagged('post_install', '-at_install')
class TestGiftExport(GiftCase):

    def cash_campaign(self):
        campaign = self.open_campaign(eligibility='active_members',
                                      items=(('禮金', 'cash_list', 2000),))
        return campaign, campaign.item_ids[0]

    def test_export_writes_a_file_and_marks_the_rows(self):
        campaign, item = self.cash_campaign()
        export = self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        self.assertEqual(export.kind, 'cash')
        self.assertTrue(export.file)
        self.assertEqual(len(export.sha256), 64)
        self.assertEqual(export.row_count, len(campaign.entitlement_ids))
        self.assertEqual(set(campaign.entitlement_ids.mapped('state')), {'exported'})
        self.assertEqual(campaign.entitlement_ids.export_id, export)

    def test_export_skips_rows_already_exported(self):
        campaign, item = self.cash_campaign()
        self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        with self.assertRaises(UserError):
            self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)

    def test_pickup_items_cannot_be_exported(self):
        """要斷言訊息：不然「沒有待造冊的名單」那道檢查會先擋住，
        測試就以錯誤的理由通過（拿掉發放方式的判斷也照樣綠）。"""
        campaign = self.open_campaign(eligibility='active_members')
        with self.assertRaises(UserError) as caught:
            self.env['assoc.gift.export'].with_user(self.admin_user).action_export(
                campaign.item_ids[0])
        self.assertIn('不需要造冊', str(caught.exception))

    def test_edenred_lists_members_without_contact_as_exceptions(self):
        """宜睿是寄給本人的：沒有手機也沒有 Email 就寄不出去。

        這些人**不匯出**、列進例外清單交回辦公室補資料，
        而不是丟一列空白進去讓對方去猜。
        """
        self.member.sudo().mobile = '0912345678'
        campaign = self.open_campaign(eligibility='active_members',
                                      items=(('禮券', 'edenred', 1000),))
        item = campaign.item_ids[0]
        export = self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        self.assertEqual(export.row_count, 1, '只有有聯絡方式的那位進名單')
        self.assertTrue(export.exception_count >= 1)
        self.assertIn(self.other.member_no, export.exception_note)
        self.assertEqual(self.rows_of(campaign, self.member).state, 'exported')
        self.assertEqual(self.rows_of(campaign, self.other).state, 'pending',
                         '沒進名單的人不能被標成已造冊——那等於漏發')

    def test_revert_puts_the_rows_back_and_keeps_the_file(self):
        campaign, item = self.cash_campaign()
        Audit = self.env['assoc.audit.log'].sudo()
        export = self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        before = Audit.search_count([('action', '=', 'gift_revert')])
        with self.assertRaises(UserError):
            export.with_user(self.admin_user).action_revert('')
        export.with_user(self.admin_user).action_revert('名單給錯窗口')
        self.assertEqual(export.state, 'reverted')
        self.assertTrue(export.file, '原檔要留著：已經交出去的那一份是事實')
        self.assertEqual(set(campaign.entitlement_ids.mapped('state')), {'pending'})
        self.assertFalse(campaign.entitlement_ids.export_id)
        self.assertEqual(Audit.search_count([('action', '=', 'gift_revert')]), before + 1)
        # 還原後可以重新造冊，而且是**新的**批次
        again = self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        self.assertNotEqual(again, export)

    def test_export_record_needs_the_sentinel(self):
        campaign, item = self.cash_campaign()
        export = self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        # ACL 只給 admin「可讀可建」，所以寫入本來就進不來；這道哨兵守的是
        # **sudo 的路徑**（還原是唯一該動它的動作，其他 sudo 程式碼一律擋下）
        for context in ({}, {'assoc_gift_export': True}):
            with self.assertRaises(AccessError, msg=str(context)):
                export.sudo().with_context(**context).write({'row_count': 0})
            with self.assertRaises(AccessError, msg=str(context)):
                self.env['assoc.gift.export'].sudo().with_context(**context).create({
                    'campaign_id': campaign.id, 'item_id': item.id, 'kind': 'cash'})
        export.sudo().with_context(**{GUARD_GIFT_EXPORT: GUARD}).write({'row_count': 0})

    def test_export_cannot_be_deleted(self):
        _campaign, item = self.cash_campaign()
        export = self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        with self.assertRaises(UserError):
            export.sudo().unlink()

    def test_staff_cannot_export(self):
        _campaign, item = self.cash_campaign()
        with self.assertRaises(AccessError) as caught:
            self.env['assoc.gift.export'].with_user(self.staff_user).action_export(item)
        self.assertIn('只有公會管理員', str(caught.exception))


@tagged('post_install', '-at_install')
class TestGiftAdversarial(GiftCase):
    """三鏡頭審查（skeptic／red-team）發現後補上的守衛。"""

    def test_sentinel_create_still_refuses_forged_defaults(self):
        """**帶哨兵的內部建立不能把守衛一起關掉**。

        `with_context()` 是疊加：`call_kw` 送來的 `default_state='claimed'`
        會原封流進 `action_ready` 內部的 create，而 `check_created`
        看到哨兵就直接放行——等於哨兵反而把守衛關掉了。
        red-team 以非 system 的公會管理員實跑：32 列全部建成「已領取」。
        """
        campaign = self.campaign(eligibility='active_members')
        campaign.with_context(
            default_state='claimed', default_claim_channel='scan_self',
            default_claimed_by_uid=self.env.uid).action_ready()
        rows = campaign.entitlement_ids
        self.assertTrue(rows)
        self.assertEqual(set(rows.mapped('state')), {'pending'}, '不能被 default_* 污染')
        self.assertFalse(any(rows.mapped('claim_channel')))

    def test_sentinel_create_of_proxy_refuses_forged_defaults(self):
        """同一個洞在 M7 的委託建立也在：`default_state='active'` 會建出已生效的委託。"""
        proxy = self.env['assoc.meeting.proxy'].sudo().with_context(
            default_state='active', default_paper_received=True)._new_proxy(
                self.meeting, self.other, self.member, purpose='gift', channel='portal')
        self.assertEqual(proxy.state, 'requested')
        self.assertFalse(proxy.paper_received)

    def test_export_only_includes_people_who_attended(self):
        """造冊也要看出席。

        名單是以大會**名冊**建的（全體會員），出席在領取當下才判斷——
        現場領取那條路有檢查，造冊這條路沒有的話，發放對象是「大會出席者」的
        現金清冊會把沒到場的人整批列進去，錢真的會發出去。
        """
        campaign = self.open_campaign(eligibility='attendees',
                                      items=(('車馬費', 'cash_list', 500),))
        item = campaign.item_ids[0]
        self.check_in(self.member)                       # 只有一個人到場
        export = self.env['assoc.gift.export'].with_user(self.admin_user).action_export(item)
        self.assertEqual(export.row_count, 1, '只有到場的人進清冊')
        self.assertEqual(self.rows_of(campaign, self.member).state, 'exported')
        self.assertEqual(self.rows_of(campaign, self.other).state, 'pending',
                         '沒到場的不能被標成已造冊——那等於當作已發放')

    def test_export_refuses_when_nobody_attended(self):
        campaign = self.open_campaign(eligibility='attendees',
                                      items=(('車馬費', 'cash_list', 500),))
        with self.assertRaises(UserError):
            self.env['assoc.gift.export'].with_user(self.admin_user).action_export(
                campaign.item_ids[0])

    def test_cash_list_amount_includes_quantity(self):
        """印領清冊上的金額要是**實付**：只印單價的話 qty>1 會少發而且看不出來。"""
        from odoo.addons.assoc_portal.models import assoc_gift_export as mod
        campaign = self.open_campaign(eligibility='active_members',
                                      items=(('餐費', 'cash_list', 300),))
        item = campaign.item_ids[0]
        item.with_user(self.admin_user).qty = 2
        rows, _exceptions, _ids = self.env['assoc.gift.export']._rows_for(
            item, campaign.entitlement_ids[:1], 'cash')
        self.assertEqual(rows[0]['total'], 600)
        headers = [col[0] for col in mod.CASH_COLUMNS]
        self.assertIn('數量', headers, '清冊要看得到數量')
        self.assertLess(headers.index('數量'), headers.index('金額'))
        # 「金額」那一欄取的必須是實付，不是單價
        total_getter = dict((col[0], col[1]) for col in mod.CASH_COLUMNS)['金額']
        self.assertEqual(total_getter(rows[0]), 600)

    def test_campaign_cannot_be_deleted_once_claimed(self):
        """`campaign_id` 是 cascade，而 Odoo 的 unlink 是 raw DELETE——
        子模型的 unlink 守衛在這條路上等於不存在。
        不擋的話：刪活動 → 重建 → 同一份再領一次，第一次的軌跡一起消失。
        """
        campaign = self.open_campaign(eligibility='active_members')
        self.rows_of(campaign, self.member)._claim(campaign, self.member, True)
        with self.assertRaises(UserError):
            campaign.with_user(self.admin_user).unlink()
        self.assertTrue(campaign.exists())
        self.assertTrue(campaign.entitlement_ids)

    def test_meeting_with_a_campaign_cannot_be_deleted(self):
        """刪大會預設會把 `meeting_id` 清成 NULL——活動的領取會永遠 not_attended，
        而 `meeting_id` 已被鎖住改不回去（`set null` 讓破壞看起來像成功）。
        """
        campaign = self.campaign()
        with self.assertRaises(Exception):
            self.meeting.sudo().unlink()
        self.assertTrue(campaign.meeting_id)

    def test_ready_refuses_an_empty_roster(self):
        empty = self.env['res.company'].create({'name': '空公會（M9）'})
        campaign = self.env['assoc.gift.campaign'].sudo().create({
            'name': '空名單', 'company_id': empty.id, 'eligibility': 'active_members'})
        # 用造冊品項：現場領取的品項會先撞「必須指定大會」那道檢查，
        # 測試就會以錯誤的理由通過（拿掉空名冊的守衛也照樣綠）
        self.env['assoc.gift.item'].sudo().create({
            'campaign_id': campaign.id, 'name': '禮金', 'delivery': 'cash_list'})
        with self.assertRaises(UserError) as caught:
            campaign.sudo().action_ready()
        self.assertIn('名單是空的', str(caught.exception))
        self.assertEqual(campaign.state, 'draft', '沒建出東西就不能標成 ready')

    def test_export_refuses_unknown_file_type(self):
        campaign = self.open_campaign(eligibility='active_members',
                                      items=(('禮金', 'cash_list', 100),))
        with self.assertRaises(UserError):
            self.env['assoc.gift.export'].with_user(self.admin_user).action_export(
                campaign.item_ids[0], file_type='CSV')

    def test_blocked_reason_distinguishes_proxy_from_self(self):
        """「尚未報到」對代領的情境會誤導：實際是**委託人**沒到。"""
        campaign = self.open_campaign(eligibility='attendees')
        self.gift_proxy(self.other, self.member)
        rows = self.env['assoc.gift.entitlement']._claimable_for(campaign, self.member)
        by_owner = {row['member_id']: row for row in rows}
        self.assertIn('委託人', by_owner[self.other.id]['blocked_reason'])
        self.assertNotIn('委託人', by_owner[self.member.id]['blocked_reason'])


@tagged('post_install', '-at_install')
class TestGiftDeskHttp(HttpCase, GiftCase):
    """報到台的兩段式請求要走真的 HTTP 才驗得到（參照碼是第二段的憑證）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.desk_user.write({'password': PASSWORD, 'login': 'm9_desk_http'})
        cls.campaign_open = cls.env['assoc.gift.campaign'].with_user(cls.admin_user).create({
            'name': 'HTTP 禮品', 'company_id': cls.company.id,
            'meeting_id': cls.meeting.id, 'eligibility': 'active_members'})
        cls.env['assoc.gift.item'].with_user(cls.admin_user).create({
            'campaign_id': cls.campaign_open.id, 'name': '毛巾', 'delivery': 'pickup'})
        cls.campaign_open.action_ready()
        cls.campaign_open.action_open()

    def desk_rpc(self, path, params):
        response = self.url_open(
            '/assoc/desk/%s%s' % (self.meeting.id, path),
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
            headers={'Content-Type': 'application/json'})
        return response.json()['result']

    def test_manual_checkin_ref_cannot_pass_as_a_scan(self):
        """手動簽到也會鑄一把參照碼（讓沒帶卡的受託人代簽得了），
        但拿它去領禮品要被當成**手動**：填原因、寫稽核、計入手動筆數。

        不分來源的話，報到台只要「手動簽到某人」就等於取得他的掃碼憑證，
        偷領會被記成 `scan_self`、`manual_reason` 為空、稽核整段跳過。
        """
        self.authenticate('m9_desk_http', PASSWORD)
        attendance = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', self.meeting.id), ('member_id', '=', self.member.id)], limit=1)
        manual = self.desk_rpc('/manual', {'attendance_id': attendance.id,
                                           'reason': '未帶會員卡，已核對身分證'})
        self.assertTrue(manual.get('desk_ref'), '手動簽到仍要給參照碼（代簽要用）')
        rows = self.env['assoc.gift.entitlement'].sudo().search([
            ('campaign_id', '=', self.campaign_open.id), ('member_id', '=', self.member.id)])
        result = self.desk_rpc('/gift/claim', {
            'member_id': self.member.id, 'ids': rows.ids, 'desk_ref': manual['desk_ref']})
        self.assertEqual(result['status'], 'need_reason',
                         '手動來源的參照碼不能當成「卡被掃過」')
        self.assertEqual(rows.state, 'pending')
        # 補上原因就領得到，而且記成手動
        result = self.desk_rpc('/gift/claim', {
            'member_id': self.member.id, 'ids': rows.ids,
            'desk_ref': manual['desk_ref'], 'reason': '未帶卡'})
        self.assertEqual(result['claimed'], 1)
        self.assertEqual(rows.claim_channel, 'manual')
        self.assertEqual(rows.manual_reason, '未帶卡')

    def test_scan_ref_counts_as_scanned(self):
        self.authenticate('m9_desk_http', PASSWORD)
        scan = self.desk_rpc('/scan', {'barcode': self.other.barcode})
        rows = self.env['assoc.gift.entitlement'].sudo().search([
            ('campaign_id', '=', self.campaign_open.id), ('member_id', '=', self.other.id)])
        result = self.desk_rpc('/gift/claim', {
            'member_id': self.other.id, 'ids': rows.ids, 'desk_ref': scan['desk_ref']})
        self.assertEqual(result['claimed'], 1)
        self.assertEqual(rows.claim_channel, 'scan_self')
        self.assertFalse(rows.manual_reason)
