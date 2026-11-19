# -*- coding: utf-8 -*-
import json

from odoo.tests.common import TransactionCase

SHEET_ID = 'sheet1'
USER_GROUP = 'spreadsheet_oca.group_user'
COMPANY_TYPE_FIELD = 'company_type'
COMPANY_TYPE_SUPERVISION = 'supervision'
COMPANY_TYPE_CONTRACTOR = 'contractor'
MANAGER_GROUP = 'spreadsheet_oca.group_manager'


class WorkspaceCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Sheet = cls.env['spreadsheet.spreadsheet']
        cls.Folder = cls.env['spreadsheet.workspace.folder']
        cls.Template = cls.env['spreadsheet.workspace.template']
        cls.Version = cls.env['spreadsheet.workspace.version']
        cls.Revision = cls.env['spreadsheet.oca.revision']
        cls.company_a = cls.env.company
        company_b_vals = {'name': 'WS 測試乙公司'}
        if COMPANY_TYPE_FIELD in cls.env['res.company']._fields:
            # ChienYi：公司類型預設是施工廠商，主要公司是施工廠商的帳號會被公司儀表板判成「營造方」、
            # 白名單以外的模型全拒。這裡要測的是一般的公司隔離，所以用監造類型的公司。
            company_b_vals[COMPANY_TYPE_FIELD] = COMPANY_TYPE_SUPERVISION
        cls.company_b = cls.env['res.company'].create(company_b_vals)
        cls.owner = cls._make_user('ws_owner', USER_GROUP)
        cls.contributor = cls._make_user('ws_contributor', USER_GROUP)
        cls.reader = cls._make_user('ws_reader', USER_GROUP)
        cls.outsider = cls._make_user('ws_outsider', USER_GROUP)
        cls.manager = cls._make_user('ws_manager', MANAGER_GROUP)

    @classmethod
    def _make_user(cls, login, *group_xmlids, company=None):
        company = company or cls.env.company
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'company_id': company.id,
            'company_ids': [(6, 0, company.ids)],
            'groups_id': [(6, 0, [cls.env.ref(x).id for x in ('base.group_user',) + group_xmlids])],
        })

    def _raw(self, a1_content):
        """一份 A1 有指定內容的底稿（以 OCA 的空白底稿為基礎）。"""
        data = self.Sheet._empty_spreadsheet_data()
        data['sheets'][0]['id'] = SHEET_ID
        data['sheets'][0]['cells'] = {'A1': {'content': a1_content}}
        return data

    def _a1(self, raw):
        return raw['sheets'][0]['cells']['A1']['content']

    def _add_pending_revision(self, record, content='pending'):
        """模擬「編輯中、還沒併回底稿」的一筆協作操作。"""
        # OCA 存檔時用 spreadsheet_revision_ids 找要清的操作列，它的快取不會自己更新（見 spreadsheet_abstract.py）
        record.invalidate_recordset(['spreadsheet_revision_ids'])
        return self.Revision.create({
            'model': record._name,
            'res_id': record.id,
            'type': 'REMOTE_REVISION',
            'client_id': 'ws-test-client',
            'server_revision_id': 'START_REVISION',
            'next_revision_id': 'ws-test-next',
            'commands': json.dumps({
                'type': 'REMOTE_REVISION',
                'version': 1,
                'commands': [{'type': 'UPDATE_CELL', 'sheetId': SHEET_ID, 'col': 1, 'row': 0, 'content': content}],
            }),
        })

    def _shared_sheet(self):
        """擁有者建立、分享給可編輯者與唯讀者的試算表。"""
        sheet = self.Sheet.with_user(self.owner).create({'name': 'WS 共用表'})
        sheet.sudo().write({
            'contributor_ids': [(6, 0, self.contributor.ids)],
            'reader_ids': [(6, 0, self.reader.ids)],
        })
        return sheet
