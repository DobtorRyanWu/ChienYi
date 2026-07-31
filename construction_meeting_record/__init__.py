# -*- coding: utf-8 -*-
from . import models
# 不要在這裡 import tests：Odoo 的測試探索是直接 import 本模組的 tests 子套件
# （odoo/tests/loader.py 的 _get_tests_modules），與這裡有沒有 import 無關。
# 在模組載入期匯入 odoo.tests 會讓 Odoo 噴
# 「Importing test framework, avoid importing from business modules」ERROR。
