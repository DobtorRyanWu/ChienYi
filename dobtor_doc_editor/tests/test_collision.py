# -*- coding: utf-8 -*-
"""M1.4 回歸測試 — dobtor portal controller 不得撞名 CustomerPortal 標準方法。

背景：DobtorDocPortal 繼承 portal.CustomerPortal。若它定義與標準同名的
`_document_check_access`，會污染整個 portal 組合類別（construction_portal 63 處在用），
重現 2026-06-19 撞名連鎖 500 的同類風險。修法：改用模組專屬名 `_doc_editor_check_access`。

本測試以結構性斷言鎖定：dobtor 不再定義標準名、改用專屬名。純檢查類別 __dict__，
不需 HttpCase，穩定可靠。
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestDocumentCheckAccessCollision(TransactionCase):

    def test_no_standard_name_collision(self):
        from odoo.addons.dobtor_doc_editor.controllers.portal import DobtorDocPortal
        self.assertNotIn(
            '_document_check_access', DobtorDocPortal.__dict__,
            "M1.4 撞名復發：DobtorDocPortal 又定義了標準名 _document_check_access，"
            "會污染整個 portal 組合類別",
        )
        self.assertIn(
            '_doc_editor_check_access', DobtorDocPortal.__dict__,
            "應以模組專屬名 _doc_editor_check_access 取代",
        )
