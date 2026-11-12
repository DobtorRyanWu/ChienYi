# -*- coding: utf-8 -*-
"""竣工打包精靈（wizard/completion_package_wizard.py；淞源 2026-11-10 會議 C12）。

老闆答應的是「工程做完，把這個案子的東西一次包出來」。這裡用真的樣板套印、打開產出的 zip 來斷言：
① zip 裡的檔案數＝清冊的列數＝畫面上的檔案數，每個檔都在清冊上；
② 少一天日誌，缺漏清單就列出那一天（有日誌的工作天、週末不列）；
③ 空工程不產生空的 zip，而是明講沒有資料；
另外：草稿日誌與未核定的估驗不納入但列在缺漏、應交文件未上傳與沒照片的檢查要列、
一份表單產生失敗不拖垮整包、份數與大小超過上限會停下來說明。
"""
import base64
import io
import zipfile
from datetime import date
from unittest.mock import patch

from freezegun import freeze_time
from openpyxl import load_workbook

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..wizard import completion_package_wizard as package_module
from ..wizard.completion_package_wizard import (
    FOLDER_DAILY, FOLDER_DOCUMENT, FOLDER_ESTIMATE, FOLDER_PHOTO, MANIFEST_NAME,
)

FROZEN_NOW = '2026-10-16 04:00:00'       # UTC；台灣 2026-10-16（五）12:00
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY = (date(2026, 10, day) for day in (12, 13, 14, 15, 16))
MANIFEST_HEADER_ROWS = 6                 # 清冊工作表：4 列摘要＋1 列空白＋1 列欄名
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


@tagged('post_install', '-at_install', 'construction_batch')
class TestCompletionPackage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.Wizard = env['completion.package.wizard']
        with freeze_time(FROZEN_NOW):
            cls.project = cls._project('竣工打包測試工程', 'PKG-P1')
            cls.empty_project = cls._project('竣工打包空工程', 'PKG-EMPTY')
            env['progress.schedule'].create({
                'project_id': cls.project.id, 'change_date': MONDAY}).write({'state': 'active'})
            cls.employee = env['hr.employee'].create({'name': 'PKG 填表人', 'company_id': env.company.id})
            # 日誌：週一、二、四已完成；週五是草稿；週三故意沒有
            cls.logs = {day: cls._log(day) for day in (MONDAY, TUESDAY, THURSDAY)}
            cls.draft_log = cls._log(FRIDAY, state=None)
            # 估驗：第 1 期已核定、第 2 期草稿
            task = env['project.task'].create({
                'name': 'PKG 工項', 'project_id': cls.project.id, 'item_no': '1', 'unit': '式',
                'planned_qty': 10.0, 'unit_price': 100.0})
            cls.estimate_done = cls._estimate(task, TUESDAY, 'approved')
            cls.estimate_draft = cls._estimate(task, THURSDAY, None)
            # 文件：一份已上傳（有附檔）、一份應交未上傳
            category = env['supervision.document.category'].create({'name': 'PKG/契約 文件'})
            attachment = env['ir.attachment'].create({
                'name': 'PKG 契約.pdf', 'raw': b'%PDF-pkg-contract', 'res_model': 'supervision.document'})
            cls.document = env['supervision.document'].create({
                'name': 'PKG 契約書', 'project_id': cls.project.id, 'document_category_id': category.id,
                'upload_attachment_ids': [(4, attachment.id)]})
            cls.document_due = env['supervision.document'].create({
                'name': 'PKG 竣工圖', 'project_id': cls.project.id, 'document_category_id': category.id,
                'due_date': FRIDAY})
            # 照片一張
            photo_file = env['ir.attachment'].create({
                'name': 'pkg.png', 'raw': PNG, 'mimetype': 'image/png', 'res_model': 'supervision.photo'})
            cls.photo = env['supervision.photo'].create({
                'project_id': cls.project.id, 'attachment_id': photo_file.id, 'shot_at': '2026-10-13 02:00:00'})
            # 自主檢查：一張已完成、沒有照片
            itype = env['self.inspection.type'].create({'name': 'PKG 模板組立'})
            cls.inspection = env['general.self.inspection'].create({
                'project_id': cls.project.id, 'inspection_type_id': itype.id, 'inspection_date': TUESDAY,
                'sub_project_name': 'PKG 擋土牆'})
            cls.inspection.write({'state': 'inspected'})

    @classmethod
    def _project(cls, name, code):
        return cls.env['project.project'].create({
            'name': name, 'code': code, 'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id, 'contract_start_date': MONDAY, 'contract_end_date': date(2026, 12, 31)})

    @classmethod
    def _log(cls, day, state='filled'):
        log = cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id, 'company_id': cls.env.company.id,
            'employee_id': cls.employee.id, 'log_date': day})
        if state:
            log.sudo().write({'state': state})
        return log

    @classmethod
    def _estimate(cls, task, day, state):
        estimate = cls.env['payment.estimate'].create({'project_id': cls.project.id, 'estimate_date': day})
        cls.env['payment.estimate.line'].create({
            'estimate_id': estimate.id, 'task_id': task.id, 'estimate_qty': 1.0, 'unit_price': 100.0})
        if state:
            estimate.sudo().write({'state': state})
        return estimate

    def _build(self, project=None, **vals):
        wizard = self.Wizard.create({'project_id': (project or self.project).id, **vals})
        wizard.action_build()
        return wizard

    @staticmethod
    def _open(wizard):
        """(zip 裡的檔名清單, 清冊的資料列, 缺漏清單的資料列)"""
        archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(wizard.result_file)))
        names = archive.namelist()
        workbook = load_workbook(io.BytesIO(archive.read(MANIFEST_NAME)))
        listed = [row for row in workbook['清冊'].iter_rows(min_row=MANIFEST_HEADER_ROWS + 1, values_only=True)]
        missing = [row for row in workbook['缺漏清單'].iter_rows(min_row=2, values_only=True)]
        return names, listed, missing

    # ── ① 清冊＝zip 的內容 ──────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_manifest_lists_every_file_in_the_zip(self):
        wizard = self._build()
        names, listed, _missing = self._open(wizard)
        self.assertEqual(wizard.state, 'done')
        self.assertTrue(wizard.result_filename.startswith('竣工資料_PKG-P1_'))
        self.assertTrue(wizard.result_filename.endswith('.zip'))
        self.assertEqual(len(names), len(listed), 'zip 內檔案數＝清冊列數')
        self.assertEqual(wizard.file_count, len(names))
        self.assertEqual(len(set(names)), len(names), '沒有互相覆蓋的同名檔')
        listed_paths = {('%s/%s' % (folder, filename)) if folder else filename for _no, folder, filename, _src, _kb in listed}
        self.assertEqual(listed_paths, set(names), '每個檔都在清冊上，清冊上的每一列在 zip 裡都有')
        self.assertEqual([row[0] for row in listed], list(range(1, len(listed) + 1)), '序號連續')
        # 各分類真的有東西：三張已完成的日誌、一期已核定的估驗、一份文件（分類名的 / 換成 _）、一張照片
        by_folder = {}
        for name in names:
            by_folder.setdefault(name.split('/')[0], []).append(name)
        self.assertEqual(len(by_folder[FOLDER_DAILY]), 3)
        self.assertEqual(len(by_folder[FOLDER_ESTIMATE]), 1)
        self.assertEqual(by_folder[FOLDER_DOCUMENT], ['%s/PKG_契約 文件/PKG 契約.pdf' % FOLDER_DOCUMENT])
        self.assertEqual(by_folder[FOLDER_PHOTO], ['%s/2026-10/2026-10-13_%s.png' % (FOLDER_PHOTO, self.photo.id)])
        archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(wizard.result_file)))
        self.assertEqual(archive.read(by_folder[FOLDER_DOCUMENT][0]), b'%PDF-pkg-contract')
        self.assertEqual(archive.read(by_folder[FOLDER_PHOTO][0]), PNG)
        self.assertIn('缺漏清單', wizard.result_note)

    # ── ② 缺漏清單 ──────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_missing_list_names_the_day_without_log_and_other_gaps(self):
        wizard = self._build()
        _names, _listed, missing = self._open(wizard)
        self.assertEqual(wizard.missing_count, len(missing))
        no_log = [item for kind, item, note in missing if kind == '施工日誌' and note.startswith('工作天沒有日誌')]
        self.assertEqual(no_log, ['2026-10-14'], '只有週三沒有日誌；有日誌的日子（含草稿那天）不列')
        notes = {(kind, item): note for kind, item, note in missing}
        self.assertIn('草稿', notes[('施工日誌', '2026-10-16')])
        self.assertIn('還沒核定', notes[('估驗計價', '第 %s 期' % self.estimate_draft.estimate_no)])
        self.assertIn('應交文件還沒上傳', notes[('工程文件', 'PKG 竣工圖')])
        self.assertIn('2026-10-16', notes[('工程文件', 'PKG 竣工圖')])
        inspection_notes = [note for (kind, _item), note in notes.items() if kind == '自主檢查']
        self.assertIn('這張檢查沒有照片', inspection_notes)
        # 補上週三的日誌後，那一天就不在缺漏清單
        self.logs[WEDNESDAY] = self._log(WEDNESDAY)
        _names, _listed, missing = self._open(self._build())
        self.assertFalse([item for kind, item, note in missing
                          if kind == '施工日誌' and note.startswith('工作天沒有日誌')])

    @freeze_time(FROZEN_NOW)
    def test_date_range_limits_records_and_missing_days(self):
        wizard = self._build(date_from=MONDAY, date_to=TUESDAY, include_photos=False, include_documents=False,
                             include_inspection_forms=False, include_control_tables=False)
        names, _listed, missing = self._open(wizard)
        self.assertEqual(len([name for name in names if name.startswith(FOLDER_DAILY)]), 2, '只有週一、週二')
        self.assertFalse([row for row in missing if row[0] == '施工日誌'], '週三不在範圍內，不算缺')
        self.assertFalse([name for name in names if name.startswith((FOLDER_PHOTO, FOLDER_DOCUMENT))])

    # ── ③ 空工程 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_empty_project_gives_message_not_empty_zip(self):
        wizard = self.Wizard.create({'project_id': self.empty_project.id})
        with self.assertRaises(UserError) as caught:
            wizard.action_build()
        self.assertIn('沒有任何可以打包的資料', str(caught.exception))
        self.assertEqual((wizard.state, wizard.result_file), ('draft', False))
        with self.assertRaises(UserError):
            self.Wizard.create({
                'project_id': self.project.id, 'include_daily_logs': False, 'include_estimates': False,
                'include_control_tables': False, 'include_inspection_forms': False, 'include_documents': False,
                'include_photos': False}).action_build()

    # ── 上限與部分失敗 ──────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_limits_stop_with_instructions(self):
        with patch.object(package_module, 'MAX_FORMS', 2):
            with self.assertRaises(UserError) as caught:
                self._build()
        self.assertIn('分批', str(caught.exception))
        self.assertIn('施工日誌 3 份', str(caught.exception))
        with patch.object(package_module, 'MAX_PACKAGE_BYTES', 10):
            with self.assertRaises(UserError) as caught:
                self._build()
        self.assertIn('上限', str(caught.exception))

    @freeze_time(FROZEN_NOW)
    def test_one_failing_form_does_not_fail_the_package(self):
        real_render = package_module.template_render.render
        broken = self.logs[TUESDAY]

        def render(template, record):
            if record == broken:
                raise UserError('PKG 模擬的套印失敗')
            return real_render(template, record)

        with patch.object(package_module.template_render, 'render', side_effect=render):
            wizard = self._build(include_photos=False)
        names, _listed, missing = self._open(wizard)
        self.assertEqual(len([name for name in names if name.startswith(FOLDER_DAILY)]), 2)
        self.assertIn(('施工日誌', '2026-10-13', '產生失敗：PKG 模擬的套印失敗'), missing)

    @freeze_time(FROZEN_NOW)
    def test_reset_clears_result(self):
        wizard = self._build(include_photos=False)
        wizard.action_reset()
        self.assertEqual((wizard.state, wizard.result_file, wizard.file_count, wizard.missing_count),
                         ('draft', False, 0, 0))
