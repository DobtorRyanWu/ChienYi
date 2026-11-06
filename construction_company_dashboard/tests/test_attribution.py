# -*- coding: utf-8 -*-
"""營造廠歸屬欄位 contractor_company_id（合約 §3.5）與安裝回填驗算。"""
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.construction_company_dashboard.hooks import post_init_hook

from .test_scope_rules import EXPECT_CONTRACTOR_LEVEL, DashScopeCase


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestAttribution(DashScopeCase):

    def _vals(self, model, project):
        return self._doc_vals(model, project)

    # ── 預設值三種情況 ───────────────────────────────────────────────────
    def test_default_single_contractor_project(self):
        """工程只有一家營造廠 → 那一家（監造方建立、沒給值）。"""
        for model in EXPECT_CONTRACTOR_LEVEL:
            if model.startswith('reservation.'):
                continue    # 預約式只造了共用工程 R；單一營造廠的情況由一般式 6 種涵蓋
            rec_a = self.env[model].create(self._vals(model, self.p_a))
            rec_b = self.env[model].create(self._vals(model, self.p_b))
            self.assertEqual(rec_a.contractor_company_id, self.co_a, model)
            self.assertEqual(rec_b.contractor_company_id, self.co_b, model)

    def test_default_multi_contractor_left_blank(self):
        """工程有多家營造廠、建立者是監造方 → 留空（由監造方補）。"""
        for model in EXPECT_CONTRACTOR_LEVEL:
            project = self.r_shared if model.startswith('reservation.') else self.p_shared
            rec = self.env(user=self.sup)[model].sudo().create(self._vals(model, project))
            self.assertFalse(rec.contractor_company_id, model)

    def test_contractor_creator_gets_own_scope(self):
        """建立者是營造方 → 範圍公司（多家營造廠的工程也一樣）。"""
        for model in EXPECT_CONTRACTOR_LEVEL:
            project = self.r_shared if model.startswith('reservation.') else self.p_shared
            rec = self.env(user=self.portal_a)[model].sudo().create(self._vals(model, project))
            self.assertEqual(rec.contractor_company_id, self.co_a, model)

    # ── 營造方強制自家 ───────────────────────────────────────────────────
    def test_contractor_forced_own_scope_even_with_sudo(self):
        """營造方傳 B 也變 A（前台 sudo 建立、後台營造廠主管 sudo 建立都一樣）。"""
        for user in (self.portal_a, self.mgr_a):
            for model in EXPECT_CONTRACTOR_LEVEL:
                project = self.r_shared if model.startswith('reservation.') else self.p_shared
                vals = dict(self._vals(model, project), contractor_company_id=self.co_b.id)
                rec = self.env(user=user)[model].sudo().create(vals)
                self.assertEqual(rec.contractor_company_id, self.co_a, f'{user.login} {model}')

    def test_contractor_cannot_create_on_project_not_contracted(self):
        """營造方在自己沒承攬的工程建單 → 強制成自家後不在工程營造廠內 → 約束擋下。"""
        with self.assertRaises(ValidationError) as ctx:
            self.env(user=self.portal_a)['general.defect.improvement'].sudo().create(
                self._vals('general.defect.improvement', self.p_b))
        self.assertIn('不在所屬工程', str(ctx.exception))

    def test_contractor_cannot_write_attribution(self):
        for model in EXPECT_CONTRACTOR_LEVEL:
            rec = self.docs[(model, self.co_a)][:1]
            env = self.env(user=self.portal_a)
            with self.assertRaises(AccessError, msg=model) as ctx:
                env[model].sudo().browse(rec.id).write({'contractor_company_id': self.co_b.id})
            self.assertIn('不能修改', str(ctx.exception))
            with self.assertRaises(AccessError, msg=model):
                env[model].sudo().browse(rec.id).write({'contractor_company_id': False})
            # 寫回同一個值不算修改
            env[model].sudo().browse(rec.id).write({'contractor_company_id': self.co_a.id})
            self.assertEqual(rec.contractor_company_id, self.co_a)

    def test_contractor_recompute_never_attributes_to_others(self):
        """營造方（前台 sudo）改了未歸屬單據的工程：只能算成自家，不能算給別家。"""
        rec = self.env['general.defect.improvement'].create(
            self._vals('general.defect.improvement', self.p_shared))
        self.assertFalse(rec.contractor_company_id)
        env = self.env(user=self.portal_a)
        env['general.defect.improvement'].sudo().browse(rec.id).write({'project_id': self.p_a.id})
        self.assertEqual(rec.contractor_company_id, self.co_a)
        rec2 = self.env['general.defect.improvement'].create(
            self._vals('general.defect.improvement', self.p_shared))
        env['general.defect.improvement'].sudo().browse(rec2.id).write({'project_id': self.p_b.id})
        self.assertFalse(rec2.contractor_company_id, '不可以因為 PB 只有 B 就算給 B')

    def test_supervision_can_change_attribution(self):
        rec = self.docs[('supervision.photo', self.co_a)].filtered(lambda r: r.project_id == self.p_shared)
        self.env(user=self.sup)['supervision.photo'].sudo().browse(rec.id).write(
            {'contractor_company_id': self.co_b.id})
        self.assertEqual(rec.contractor_company_id, self.co_b)

    # ── 約束 ────────────────────────────────────────────────────────────
    def test_constraint_rejects_non_contractor_company(self):
        rec = self.docs[('payment.estimate', self.co_a)][:1]
        with self.assertRaises(ValidationError) as ctx:
            rec.write({'contractor_company_id': self.co_s.id})
        self.assertIn('不是營造廠', str(ctx.exception))

    def test_constraint_rejects_company_not_in_project(self):
        for model in EXPECT_CONTRACTOR_LEVEL:
            rec = self.docs[(model, self.co_a)][:1]
            with self.assertRaises(ValidationError, msg=model) as ctx:
                rec.write({'contractor_company_id': self.co_c.id})
            self.assertIn('不在所屬工程', str(ctx.exception))

    # ── 安裝回填驗算 ─────────────────────────────────────────────────────
    def test_post_init_hook_passes_on_consistent_data(self):
        post_init_hook(self.env)
        for model in EXPECT_CONTRACTOR_LEVEL:
            rec = self.docs[(model, self.co_a)]
            self.assertTrue(all(r.contractor_company_id == self.co_a for r in rec), model)

    def test_post_init_hook_fills_blank_single_contractor(self):
        """安全網：單一營造廠工程的單據被清成空白，回填會補回去。"""
        rec = self.docs[('supervision.test.record', self.co_a)].filtered(lambda r: r.project_id == self.p_a)
        self.env.flush_all()
        self.env.cr.execute('UPDATE supervision_test_record SET contractor_company_id = NULL WHERE id = %s',
                            [rec.id])
        post_init_hook(self.env)
        self.assertEqual(self.env['supervision.test.record'].browse(rec.id).contractor_company_id, self.co_a)

    def test_post_init_hook_fails_on_wrong_attribution(self):
        """錯填（歸給不在工程內的營造廠）→ 驗算不一致 → 安裝失敗。"""
        rec = self.docs[('daily.log.sheet', self.co_a)].filtered(lambda r: r.supervision_project_id == self.p_a)
        self.env.flush_all()
        self.env.cr.execute('UPDATE daily_log_sheet SET contractor_company_id = %s WHERE id = %s',
                            [self.co_c.id, rec.id])
        with self.assertRaises(UserError) as ctx:
            post_init_hook(self.env)
        self.assertIn('daily.log.sheet', str(ctx.exception))

    # ── 照片跟著所屬單據（合約 §0b-11）───────────────────────────────────
    def _photo_parent_fields(self):
        """照片上指向營造廠層級單據的來源欄位：{單據模型: 照片欄位}（7 種單據，照片本身除外）。"""
        source_map = self.env['supervision.photo']._photo_source_field_map()
        fields_ = {model: field for model, field in source_map.items() if model in EXPECT_CONTRACTOR_LEVEL}
        self.assertEqual(set(fields_), set(EXPECT_CONTRACTOR_LEVEL) - {'supervision.photo'}, '前提：7 種單據都掛得上照片')
        return fields_

    def _shared_parent(self, model):
        project = self.r_shared if model.startswith('reservation.') else self.p_shared
        parent = self.docs[(model, self.co_a)].filtered(lambda r: r[EXPECT_CONTRACTOR_LEVEL[model]] == project)
        self.assertEqual(len(parent), 1, model)
        return project, parent

    def test_photo_follows_parent_document(self):
        """共用工程（兩家營造廠）上監造方掛到 A 單據的照片 → A（依工程判斷會留空）；單據改歸屬，照片跟著改。"""
        for model, field in self._photo_parent_fields().items():
            project, parent = self._shared_parent(model)
            vals = dict(self._vals('supervision.photo', project), **{field: parent.id})
            photo = self.env(user=self.sup)['supervision.photo'].sudo().create(vals)
            self.assertEqual(photo.contractor_company_id, self.co_a, f'{model}：照片跟著單據歸 A')
            parent.write({'contractor_company_id': self.co_b.id})
            self.assertEqual(photo.contractor_company_id, self.co_b, f'{model}：單據改歸屬，照片跟著改')

    def test_photo_without_parent_keeps_original_rule(self):
        """沒掛在有歸屬的單據上（單獨上傳）：照原規則——共用工程、監造方上傳 → 留空。"""
        photo = self.env(user=self.sup)['supervision.photo'].sudo().create(
            self._vals('supervision.photo', self.p_shared))
        self.assertFalse(photo.contractor_company_id)

    def test_post_init_hook_photo_follows_parent(self):
        """回填驗算：照片空白而單據有值 → 補成單據的；照片與單據不一致 → 安裝失敗。"""
        _project, parent = self._shared_parent('general.defect.improvement')
        photo = self.env['supervision.photo'].create(dict(
            self._vals('supervision.photo', self.p_shared), general_defect_id=parent.id))
        self.env.flush_all()
        self.env.cr.execute('UPDATE supervision_photo SET contractor_company_id = NULL WHERE id = %s', [photo.id])
        post_init_hook(self.env)
        self.assertEqual(self.env['supervision.photo'].browse(photo.id).contractor_company_id, self.co_a)
        self.env.flush_all()
        self.env.cr.execute('UPDATE supervision_photo SET contractor_company_id = %s WHERE id = %s',
                            [self.co_b.id, photo.id])
        with self.assertRaises(UserError) as ctx:
            post_init_hook(self.env)
        self.assertIn('歸屬與所屬單據不同', str(ctx.exception))
