# -*- coding: utf-8 -*-
"""估驗計價表空白樣板的 calcChain，以及 3.9.0 換預設樣板的 migration（2026-11-05）。

估驗計價表：xl/calcChain.xml 還記著 E24、I23 兩個公式，工作表裡卻沒有公式
（e9ae543 刪掉公式時沒清 calcChain）→ Excel 正常模式打不開。

（監造日報表（一）第 13–16 列 1.5pt 看不到施工項目：改成 15.75pt 會從 1 頁變 2 頁，
客戶原始表單也是壓扁的、一頁；使用者 2026-11-05 裁示維持原始版面，不修。）
"""

import base64
import hashlib
import importlib.util
import os
import re
import zipfile

from odoo.tests.common import TransactionCase, tagged

from .common import blank_template

BLANK_DIR = os.path.dirname(blank_template('estimate_report.xlsx'))
MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', '18.0.3.9.0', 'post-migrate.py')


def _calc_chain_orphans(path):
    """calcChain 裡記著、但工作表那格其實沒有公式的儲存格：[(sheet, ref)]"""
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if 'xl/calcChain.xml' not in names:
            return []
        workbook = zf.read('xl/workbook.xml').decode('utf-8')
        rels = zf.read('xl/_rels/workbook.xml.rels').decode('utf-8')
        targets = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
        targets.update({rid: tgt for tgt, rid in
                        re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
        sheet_by_id = {}
        for sheet_id, rid in re.findall(r'<sheet\b[^>]*sheetId="(\d+)"[^>]*r:id="([^"]+)"',
                                        workbook):
            sheet_by_id[sheet_id] = 'xl/' + targets[rid].lstrip('/').replace('xl/', '', 1)
        orphans = []
        current = None
        for attrs in re.findall(r'<c\b([^>]*)/?>', zf.read('xl/calcChain.xml').decode('utf-8')):
            ref = re.search(r'\br="([A-Z]+\d+)"', attrs).group(1)
            sheet = re.search(r'\bi="(\d+)"', attrs)
            current = sheet.group(1) if sheet else current
            sheet_path = sheet_by_id.get(current)
            sheet_xml = zf.read(sheet_path).decode('utf-8') if sheet_path in names else ''
            cell = re.search(r'<c r="%s"[^>]*?(?:/>|>(.*?)</c>)' % ref, sheet_xml, re.DOTALL)
            if not (cell and cell.group(1) and '<f' in cell.group(1)):
                orphans.append((sheet_path, ref))
        return orphans


@tagged('post_install', '-at_install', 'construction_template')
class TestBlankXlsxCalcChain(TransactionCase):

    def test_calc_chain_only_lists_real_formulas(self):
        bad = {}
        for name in sorted(os.listdir(BLANK_DIR)):
            if name.endswith('.xlsx'):
                orphans = _calc_chain_orphans(os.path.join(BLANK_DIR, name))
                if orphans:
                    bad[name] = orphans
        self.assertFalse(bad, 'calcChain 記著不存在的公式（Excel 正常模式打不開）：%s' % bad)


def _load_migration():
    spec = importlib.util.spec_from_file_location('mig_3_9_0', MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha1_of_blank(name):
    with open(blank_template(name), 'rb') as fp:
        return hashlib.sha1(fp.read()).hexdigest()


@tagged('post_install', '-at_install', 'construction_template')
class TestSeed390Migration(TransactionCase):

    def _default(self, ttype):
        return self.env['document.template'].search([
            ('template_type', '=', ttype), ('is_default', '=', True)], limit=1)

    def test_replaceable_lists_old_versions_only(self):
        mod = _load_migration()
        self.assertEqual(set(mod.REPLACEABLE), {'estimate_report'},
                         '日報表（一）維持原始版面（使用者 11-05 裁示），不換')
        for ttype, checksums in mod.REPLACEABLE.items():
            self.assertTrue(checksums, ttype)
            self.assertNotIn(_sha1_of_blank('%s.xlsx' % ttype), checksums,
                             '%s：新版不該列在可被覆蓋的舊版裡' % ttype)

    def test_shipped_old_version_is_replaced(self):
        mod = _load_migration()
        tmpl = self._default('estimate_report')
        self.assertTrue(tmpl, '測資前提：有系統預設的估驗計價表')
        fake_old = b'fake shipped estimate_report'
        tmpl.attachment_id.write({'datas': base64.b64encode(fake_old)})
        mod.REPLACEABLE['estimate_report'].add(hashlib.sha1(fake_old).hexdigest())
        self.env.flush_all()
        mod.migrate(self.env.cr, '18.0.3.8.3')
        self.env.invalidate_all()
        self.assertEqual(tmpl.attachment_id.checksum, _sha1_of_blank('estimate_report.xlsx'))
        self.assertFalse(tmpl.attachment_id.public)
        self.assertEqual(tmpl.attachment_id.res_id, tmpl.id)

    def test_customized_default_is_kept(self):
        mod = _load_migration()
        tmpl = self._default('estimate_report')
        tmpl.attachment_id.write({'datas': base64.b64encode(b'customized by someone')})
        att, checksum = tmpl.attachment_id, tmpl.attachment_id.checksum
        self.env.flush_all()
        mod.migrate(self.env.cr, '18.0.3.8.3')
        self.env.invalidate_all()
        self.assertEqual(tmpl.attachment_id, att)
        self.assertEqual(tmpl.attachment_id.checksum, checksum)


@tagged('post_install', '-at_install', 'construction_template')
class TestSeedKeepsSharedAttachment(TransactionCase):
    """換系統預設樣板時，舊附件還被別的樣板指著就不能刪（2026-11-05 red-team 實證）。

    「複製樣板」（document.template.action_duplicate）用 copy()，attachment_id 預設 copy=True
    → 副本與系統預設共用同一個附件。seed 換檔時 unlink 舊附件，外鍵是 ON DELETE SET NULL，
    副本的檔案就靜靜變成空的；get_template_for_report 又優先挑公司／專案層的副本，
    整家公司的匯出都會失敗。
    """

    def test_duplicated_default_keeps_its_file(self):
        from odoo.addons.construction_template.hooks import seed_default_templates
        ttype = 'estimate_report'
        default = self.env['document.template'].search([
            ('template_type', '=', ttype), ('is_default', '=', True)], limit=1)
        self.assertTrue(default, '測資前提：有系統預設的估驗計價表')
        default.action_duplicate()
        copy = self.env['document.template'].search([
            ('template_type', '=', ttype), ('is_default', '=', False),
            ('attachment_id', '=', default.attachment_id.id)])
        self.assertEqual(len(copy), 1, '測資前提：副本與預設共用同一個附件')
        shared = copy.attachment_id
        seed_default_templates(self.env, types=(ttype,),
                               replaceable={ttype: {shared.checksum}})
        self.env.invalidate_all()
        self.assertNotEqual(default.attachment_id, shared, '預設應換成新檔')
        self.assertTrue(shared.exists(), '副本還在用的舊附件被刪了')
        self.assertEqual(copy.attachment_id, shared)
        self.assertTrue(copy.attachment_id.datas, '副本的樣板檔變成空的')
        self.assertEqual(shared.res_id, copy.id, '舊附件應改掛在還在用它的副本上（權限跟著副本走）')
