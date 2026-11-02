# -*- coding: utf-8 -*-
"""說明書發現問題的回歸（第 2 批，2026-11-02）。

- B18 `_resolve_uom_id` 的 Uom.search 不能因呼叫者權限而 AccessError。
- T12 只有「代操作員」群組的新帳號要能跑標單匯入（建 project.task、product.product、uom）。
"""
import base64

from odoo.tests.common import TransactionCase, tagged

OPERATOR = 'construction_supervision_base.group_operator'
LEADER = 'construction_supervision_base.group_portal_leader'

# 全新單位：標單匯入與契約變更都會走到「自動建立 uom」
NEW_UNIT = 'T12測試單位'

TENDER_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<ETenderSheet xmlns="http://pcstd.pcc.gov.tw/2003/eTender">
  <DetailList>
    <PayItem itemKey="1" itemNo="壹">
      <Description language="zh-TW">發包工程費</Description>
      <Unit language="zh-TW">式</Unit>
      <Quantity>1</Quantity><Price>0</Price><Amount>1000</Amount>
      <PayItem itemKey="2" itemNo="一" refItemCode="T12-REF-001">
        <Description language="zh-TW">測試工項</Description>
        <Unit language="zh-TW">%s</Unit>
        <Quantity>10</Quantity><Price>100</Price><Amount>1000</Amount>
      </PayItem>
    </PayItem>
  </DetailList>
</ETenderSheet>''' % NEW_UNIT


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestManualFixes20261102(TransactionCase):

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])],
        })

    # B18 ---------------------------------------------------------------
    def test_b18_resolve_uom_lookup_without_admin(self):
        """非管理員（前台主管）解析單位：既有單位的三種查法與自動建立都不可 AccessError。"""
        leader = self._mk_user('b18_leader', LEADER)
        Task = self.env['project.task'].with_user(leader)
        existing = self.env['uom.uom'].search([], limit=1)
        self.assertEqual(Task._resolve_uom_id(existing.name), existing.id, '精確比對')
        self.assertEqual(
            Task._resolve_uom_id(' %s ' % existing.name.upper()), existing.id, '正規化模糊比對')
        self.assertTrue(Task._resolve_uom_id('B18全新單位'), '自動建立')

    # T12 ---------------------------------------------------------------
    def test_t12_operator_can_create_task(self):
        """代操作員（只有 group_operator）要能建 project.task —— 標單匯入第一個卡點。"""
        operator = self._mk_user('t12_operator_task', OPERATOR)
        project = self.env['project.project'].create({
            'name': 'T12 建工項', 'code': 'T12-TASK', 'project_type': 'general',
            'company_id': self.env.company.id})
        task = self.env['project.task'].with_user(operator).create({
            'name': 'T12 工項', 'project_id': project.id, 'item_no': '1'})
        self.assertTrue(task.exists())

    def test_t12_operator_can_import_tender(self):
        operator = self._mk_user('t12_operator', OPERATOR)
        project = self.env['project.project'].create({
            'name': 'T12 標單匯入', 'code': 'T12-IMP', 'project_type': 'general',
            'company_id': self.env.company.id})
        wizard = self.env['tender.import.wizard'].with_user(operator).create({
            'project_id': project.id,
            'xml_file': base64.b64encode(TENDER_XML.encode()),
            'xml_filename': 't12.xml',
        })
        wizard.action_preview()
        wizard.action_confirm_import()
        tasks = self.env['project.task'].search([('project_id', '=', project.id)])
        self.assertEqual(len(tasks), 2, '應匯入 2 個工項')
        leaf = tasks.filtered(lambda t: t.ref_item_code == 'T12-REF-001')
        self.assertEqual(leaf.unit_id.name, NEW_UNIT)
        self.assertTrue(leaf.product_id, '應建立 product')
