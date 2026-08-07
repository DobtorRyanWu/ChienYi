# -*- coding: utf-8 -*-
"""估驗詳細表與估驗照片的抬頭改成佔位符，需要重灌這兩份空白樣板。

原樣板把「臺北市政府工務局水利工程處」寫死在儲存格／段落裡，換業主就得換檔案。
改成 ${authorityName} / +++INS authorityName+++，接工程案件既有的
`project.project.authority_name`（業主/主辦機關）欄位；欄位空白時對照表回退到
原本那個字串，所以既有輸出不變。

`seed_default_templates` 冪等：既有記錄只 update 附件內容。
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env)
