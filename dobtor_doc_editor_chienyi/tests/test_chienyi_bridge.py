# -*- coding: utf-8 -*-
"""Sprint 21 — ChienYi × dobtor_doc_editor 整合測試

驗證 general.self.inspection 透過 doc.linked.mixin 能：
1. 取得 mixin 提供的欄位 / methods
2. 第一次點 action_open_linked_doc 自動建立 doc.document
3. 套用正確樣板（template_self_inspection）
4. 自動加入正確 collaborators
5. 反向 lookup 從 doc_id → record 能找回原 inspection
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor', 'dobtor_doc_editor_chienyi')
class TestChienyiBridge(TransactionCase):
    """Sprint 21 整合測試。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.User = cls.env['res.users']
        cls.Inspection = cls.env['general.self.inspection']
        cls.Doc = cls.env['doc.document']

        # 建立必要的支援資料
        cls.project = cls.env['project.project'].create({
            'name': 'Sprint 21 測試工程',
            'code': 'S21-TEST',
            'project_type': 'general',
        })
        cls.inspection_type = cls.env['self.inspection.type'].create({
            'name': '混凝土澆置檢查',
            'project_id': cls.project.id,
        })
        cls.inspector = cls.User.create({
            'name': 'Sprint 21 檢查人',
            'login': 's21_inspector@example.com',
        })

    def _make_inspection(self, **vals):
        defaults = {
            'project_id': self.project.id,
            'inspection_type_id': self.inspection_type.id,
            'sub_project_name': '基礎開挖',
            'inspector_id': self.inspector.id,
        }
        defaults.update(vals)
        return self.Inspection.create(defaults)

    # ─── 1. mixin fields/methods 都正確繼承 ─────────────────────────

    def test_mixin_fields_present(self):
        """繼承後應該有 linked_doc_id 與 linked_doc_count 欄位。"""
        self.assertIn('linked_doc_id', self.Inspection._fields)
        self.assertIn('linked_doc_count', self.Inspection._fields)

    def test_mixin_methods_present(self):
        """繼承後應該有 action_open_linked_doc 與 hook methods。"""
        self.assertTrue(hasattr(self.Inspection, 'action_open_linked_doc'))
        self.assertTrue(hasattr(self.Inspection, '_doc_default_template_xml_id'))
        self.assertTrue(hasattr(self.Inspection, '_doc_collaborators'))
        self.assertTrue(hasattr(self.Inspection, '_doc_render_context'))

    def test_initial_linked_doc_count_is_zero(self):
        """新建 inspection 還沒開啟線上文件，count = 0。"""
        rec = self._make_inspection()
        self.assertFalse(rec.linked_doc_id)
        self.assertEqual(rec.linked_doc_count, 0)

    # ─── 2. action_open_linked_doc 第一次觸發建立 ───────────────────

    def test_action_open_linked_doc_creates_doc(self):
        """第一次點 action 應自動建立 doc.document。"""
        rec = self._make_inspection()
        action = rec.action_open_linked_doc()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'doc.document')
        self.assertTrue(rec.linked_doc_id)
        self.assertEqual(rec.linked_doc_count, 1)
        self.assertEqual(action['res_id'], rec.linked_doc_id.id)

    def test_action_open_linked_doc_idempotent(self):
        """第二次點不應再建立新文件。"""
        rec = self._make_inspection()
        rec.action_open_linked_doc()
        first_doc_id = rec.linked_doc_id.id
        rec.action_open_linked_doc()
        self.assertEqual(rec.linked_doc_id.id, first_doc_id)

    # ─── 3. 套用樣板 ────────────────────────────────────────────────

    def test_doc_uses_self_inspection_template(self):
        """覆寫的 _doc_default_template_xml_id 回傳 template_self_inspection。"""
        rec = self._make_inspection()
        xml_id = rec._doc_default_template_xml_id()
        self.assertEqual(xml_id, 'dobtor_doc_editor.template_self_inspection')
        # 該樣板須真的存在（已在 dobtor_doc_editor data 內定義）
        template = self.env.ref(xml_id, raise_if_not_found=False)
        self.assertTrue(template, '樣板 %s 應該已存在於 dobtor_doc_editor 資料中' % xml_id)

    def test_created_doc_has_template_content(self):
        """從樣板複製的文件 content_html 不應為空。"""
        rec = self._make_inspection()
        rec.action_open_linked_doc()
        doc = rec.linked_doc_id
        self.assertTrue(doc.content_html, 'content_html 不應為空（應從樣板複製）')

    # ─── 4. Collaborators ──────────────────────────────────────────

    def test_collaborators_include_inspector_and_current_user(self):
        """檢查人應自動成為 collaborator（current user 也應在內）。"""
        rec = self._make_inspection()
        collaborators = rec._doc_collaborators()
        self.assertIn(self.inspector, collaborators)
        self.assertIn(self.env.user, collaborators)

    def test_created_doc_has_collaborators(self):
        """建立後 doc.collaborator_ids 應包含 inspector。"""
        rec = self._make_inspection()
        rec.action_open_linked_doc()
        doc = rec.linked_doc_id
        self.assertIn(self.inspector, doc.collaborator_ids)

    # ─── 5. Render context（Jinja 填充用） ─────────────────────────

    def test_render_context_contains_key_fields(self):
        """_doc_render_context 應提供樣板需要的所有 key。"""
        rec = self._make_inspection(sub_project_name='Sprint 21 整合測試')
        ctx = rec._doc_render_context()
        for key in [
            'record_id', 'record_model', 'project_name', 'inspection_no',
            'inspection_date', 'inspection_type', 'sub_project_name',
            'timing', 'inspector',
        ]:
            self.assertIn(key, ctx, '_doc_render_context 應包含 %s' % key)
        self.assertEqual(ctx['record_model'], 'general.self.inspection')
        self.assertEqual(ctx['sub_project_name'], 'Sprint 21 整合測試')
        self.assertEqual(ctx['inspector'], self.inspector.name)

    def test_render_context_handles_missing_optional_fields(self):
        """部分欄位空白時不應 crash（如承攬廠商、監造員）。"""
        # contractor 取自 contractor_name，該欄會自工程的營造廠商自動帶入；
        # 這裡明確確保工程沒填，才是真正在測「空值 fallback」而非碰巧為空。
        self.assertFalse(self.project.contractor_company_name)
        rec = self._make_inspection()
        ctx = rec._doc_render_context()
        self.assertEqual(ctx['contractor'], '')
        self.assertEqual(ctx['supervisor'], '')

    def test_render_context_contractor_follows_project(self):
        """承攬廠商未填時，自工程案件的營造廠商自動帶入。"""
        project = self.env['project.project'].create({
            'name': '承攬廠商帶入測試', 'code': 'S21-CONTRACTOR',
            'project_type': 'general',
            'contractor_company_name': '大禹營造股份有限公司',
        })
        insp_type = self.env['self.inspection.type'].create({
            'name': '帶入測試檢查', 'project_id': project.id,
        })
        rec = self._make_inspection(
            project_id=project.id, inspection_type_id=insp_type.id)
        self.assertEqual(rec.contractor_name, '大禹營造股份有限公司')
        self.assertEqual(
            rec._doc_render_context()['contractor'], '大禹營造股份有限公司')

    def test_contractor_name_override_survives_project_rename(self):
        """逐筆覆寫後，工程案件改名不得回頭蓋掉已填的值。"""
        project = self.env['project.project'].create({
            'name': '覆寫測試', 'code': 'S21-OVERRIDE',
            'project_type': 'general',
            'contractor_company_name': '原本的營造廠',
        })
        insp_type = self.env['self.inspection.type'].create({
            'name': '覆寫測試檢查', 'project_id': project.id,
        })
        rec = self._make_inspection(
            project_id=project.id, inspection_type_id=insp_type.id,
            contractor_name='本次特例承攬廠商')
        # 明給的值不得被 compute 蓋掉（Odoo 於 create 期間 protect 明給的 computed 欄）
        self.assertEqual(rec.contractor_name, '本次特例承攬廠商')
        project.contractor_company_name = '改名後的營造廠'
        self.env.flush_all()
        self.assertEqual(rec.contractor_name, '本次特例承攬廠商')

    # ─── 6. 文件命名 ──────────────────────────────────────────────

    def test_initial_name_combines_no_and_subproject(self):
        """文件名應為「檢查編號 - 分項工程名稱」。"""
        rec = self._make_inspection(sub_project_name='Test Item')
        name = rec._doc_initial_name()
        self.assertIn('Test Item', name)
        # 文件名必含檢查編號（自動 sequence 或預設）
        self.assertTrue(name)

    # ─── 7. 反向 lookup（doc → record） ───────────────────────────

    def test_reverse_lookup_doc_to_record(self):
        """從建立的 doc_id 應能反查回原 inspection。"""
        rec = self._make_inspection()
        rec.action_open_linked_doc()
        doc = rec.linked_doc_id

        # mixin 的 _create_linked_doc 應有寫入 model_id + res_id
        if 'model_id' in doc._fields and 'res_id' in doc._fields:
            self.assertEqual(doc.model_id.model, 'general.self.inspection')
            self.assertEqual(doc.res_id, rec.id)

            # 走 mixin 提供的反向 lookup
            recovered = self.Inspection._get_record_from_linked_doc(doc.id)
            self.assertEqual(recovered, rec)

    # ─── 8. ondelete='set null' 守則 ─────────────────────────────

    def test_doc_deletion_clears_linked_doc_id(self):
        """刪除 doc.document 後 linked_doc_id 應變 false（mixin ondelete=set null）。"""
        rec = self._make_inspection()
        rec.action_open_linked_doc()
        doc = rec.linked_doc_id
        doc.unlink()
        rec.invalidate_recordset(['linked_doc_id', 'linked_doc_count'])
        self.assertFalse(rec.linked_doc_id)
        self.assertEqual(rec.linked_doc_count, 0)
