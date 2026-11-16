# -*- coding: utf-8 -*-
"""前台公告橫幅的 CSS 變數守則：portal CSS／JS 只用 --wb-*，不可出現 --cy-*（E2E 會掃全部 stylesheet）。"""
from pathlib import Path

from odoo.tests import TransactionCase, tagged

STATIC_DIR = Path(__file__).resolve().parent.parent / 'static' / 'src'
FORBIDDEN_PREFIX = '--cy-'
CHECKED_FILES = ('css/portal_announcement.css', 'js/portal_announcement.js')


@tagged('post_install', '-at_install')
class TestAnnouncementCssVars(TransactionCase):

    def test_no_legacy_cy_variables(self):
        """修前：橫幅高度變數叫 --cy-maint-h，E2E「禁用 --cy-*」會失敗。"""
        for rel in CHECKED_FILES:
            text = (STATIC_DIR / rel).read_text(encoding='utf-8')
            self.assertNotIn(FORBIDDEN_PREFIX, text, rel)

    def test_css_and_js_use_same_variable(self):
        """CSS 讀的變數必須就是 JS 寫的變數，否則橫幅高度推不下去。"""
        css = (STATIC_DIR / 'css/portal_announcement.css').read_text(encoding='utf-8')
        js = (STATIC_DIR / 'js/portal_announcement.js').read_text(encoding='utf-8')
        self.assertIn('--wb-maint-h', css)
        self.assertIn('"--wb-maint-h"', js)
