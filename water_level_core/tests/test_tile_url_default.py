# -*- coding: utf-8 -*-
"""後台水位地圖底圖：leaflet.tile_url 是空的或字串 False 才補 OSM，已設定的不動。"""
import importlib.util
import os

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.water_level_core.hooks import DEFAULT_TILE_URL, TILE_URL_PARAM

MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', '18.0.3.2.1', 'post-migrate.py')


@tagged('post_install', '-at_install', 'water_level_core')
class TestTileUrlDefault(TransactionCase):

    def _migrate(self):
        spec = importlib.util.spec_from_file_location('mig_3_2_1', MIGRATION)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(self.env.cr, '18.0.3.2.0')

    def _value(self):
        return self.env['ir.config_parameter'].sudo().get_param(TILE_URL_PARAM)

    def test_string_false_is_filled(self):
        self.env['ir.config_parameter'].sudo().set_param(TILE_URL_PARAM, 'False')
        self._migrate()
        self.assertEqual(self._value(), DEFAULT_TILE_URL)

    def test_missing_param_is_filled(self):
        self.env['ir.config_parameter'].sudo().search(
            [('key', '=', TILE_URL_PARAM)]).unlink()
        self._migrate()
        self.assertEqual(self._value(), DEFAULT_TILE_URL)

    def test_custom_url_is_untouched(self):
        custom = 'https://tiles.example.test/{z}/{x}/{y}.png'
        self.env['ir.config_parameter'].sudo().set_param(TILE_URL_PARAM, custom)
        self._migrate()
        self.assertEqual(self._value(), custom)
