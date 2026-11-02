# -*- coding: utf-8 -*-
"""3.8.2：預設空白樣板去識別化＋預設樣板附件改非公開。

(一) 樣板換版（T5）：下列 13 種預設樣板的出貨檔清掉了內網路徑、外部連結路徑、建立者帳號；
    material_test 另把寫死任泰的「負責人」與 email 改成 token。系統裡的檔是「以前出貨過的版本」
    才換成新版；被人在系統裡換過的（checksum 不在 REPLACEABLE）一律不動，seed 會記 WARNING。
    REPLACEABLE 的 checksum 取自 git 歷史（bd271db 及更早）裡這些檔的每一個版本的 sha1，
    與 ir.attachment.checksum 同一種算法。
(二) 附件不公開（T7）：舊版 seed 建附件時 public=True，未登入的人用 /web/content/<連號 id>
    就能下載。先回填 res_id（沒有 res_id 的非公開附件會變孤兒，只有建立者與 base.group_system
    讀得到），再把 document.template 的公開附件全設成非公開。順序不能反。
    使用者上傳的樣板本來就不公開（public 為 NULL），這裡只動 public 為真的。
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates

# 這幾種是 .docx，其餘 .xlsx（測試用來決定副檔名）
DOCX_TYPES = ('defect_control', 'defect_improvement', 'invoice_photo', 'material_test', 'review_control', 'self_inspection_form', 'test_control',)

REPLACEABLE = {
    # daily_log_c1.xlsx：3 個出貨版本
    'daily_log_c1': {
        '8e57f1409b08325ef19ced5d7ccf6556f750dc26',  # 089f1af
        '163f1de6fa4db303130a99a38995ec9d4db91cab',  # 7efbe50
        '8a7b1e00650a939b9aa0e3c496ed890ffa260456',  # ef62ea6
    },
    # daily_log_c2.xlsx：1 個出貨版本
    'daily_log_c2': {
        'a0ca3376eebeb81f5ac5143abafde707d62399ab',  # ef62ea6
    },
    # progress_report.xlsx：1 個出貨版本
    'progress_report': {
        '10ffdaa736cb5b5e1935dabc24f11d51143adf55',  # 555f8dd
    },
    # self_inspection.xlsx：10 個出貨版本
    'self_inspection': {
        '7e14a603d3ad3a63a2591c54191a6cf1da101151',  # a7a616f
        '5a7c29a68a9a8eca841ec4a4ed49374a6a921cc5',  # b641e36
        'c27c3bdc5babce1a1dc11dd0ff9351e29888ddc5',  # dc77c2b
        '9b5b0419c1044cda3e89f60a6f91e5565ad70dcf',  # 8ef9ab8
        'f3dad24231c5c69f58b7f2d6ef9db5fa7c1278da',  # c20c5aa
        'e9a21651601bdbd952a1f4aa8a36b98d966a90c1',  # 8091622
        'a0c0152d58993a3e0b752b754dc44b0252d5b426',  # 52dd7ab
        '72969af830fe1ec7d36f265ddd119e81b23865f9',  # 7c26cbf
        '43cab7cabd8187d577f025920a47d40afd488520',  # 8c069e0
        'acf741c3419501cfc54048ffd76f7e08b66760e1',  # 84ab5bf
    },
    # invoice_detail.xlsx：2 個出貨版本
    'invoice_detail': {
        'a17f97f3ecdf34e3761ba9e82b99bbaad7fa63ff',  # 2762429
        'c6d75d2c4f7b037c62b8e2c2340c635715e0a298',  # 555f8dd
    },
    # plan_control.xlsx：1 個出貨版本
    'plan_control': {
        '13747bc8262ddec404d9af538dd0d3580e9345bd',  # 0f95cd6
    },
    # material_test.docx：9 個出貨版本
    'material_test': {
        'b66972d080ee1ee8cfbba393c09eb7acd0b1f441',  # 083e7ec
        'f612df1a4962c7db844d93c35f45eb164ee496d3',  # b641e36
        'eeea1b85262856f7e9ba572b2f0e339fd5570330',  # 8ef9ab8
        'bb470ded351087afd83b38f8ba14f64fccae3492',  # c20c5aa
        '60097ebd58647c8228f49909ec26a399d6a58fda',  # 8091622
        '406edd8011d3357b73b617611661fe4b8e74aa47',  # 52dd7ab
        '6892bea8059882f2180c29afabee9e31af8fef72',  # 7c26cbf
        '74aaa7f77832acffc5d492cd1536afacba925d34',  # 0362f81
        '106b2cef0c3717fd67fd5cd81eb8ee1754814370',  # 84ab5bf
    },
    # defect_control.docx：1 個出貨版本
    'defect_control': {
        '120d810f650116f27fb41bebcc35a99c6dc5af09',  # a7a616f
    },
    # defect_improvement.docx：1 個出貨版本
    'defect_improvement': {
        'dca3001eefd74ab8f9cb30f8b8857c44a8a7066d',  # a7a616f
    },
    # invoice_photo.docx：2 個出貨版本
    'invoice_photo': {
        '1614da26ef1f0bae1c8297852010ebbc781a6e17',  # 2762429
        '3b201a46628c2950371ca6abd1a8693245732de6',  # 555f8dd
    },
    # review_control.docx：1 個出貨版本
    'review_control': {
        'c9a24a92f0e7647f52f4eca0fa34f23dae568707',  # a7a616f
    },
    # self_inspection_form.docx：1 個出貨版本
    'self_inspection_form': {
        '8fe32f540cb2bb7b20ff147cc4eb196741df9740',  # 2236c1a
    },
    # test_control.docx：3 個出貨版本
    'test_control': {
        'c976a3fe474d815e3efade927bc90dd5967850c5',  # 7700aa0
        '75f0cf0cab83a9109cbe0eb12118de4921083118',  # 872ae43
        'ea4d1e92afc6eaa13f61d35a7e98d969ddd55afb',  # a7a616f
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env, types=tuple(REPLACEABLE), replaceable=REPLACEABLE)
    # 先回填 res_id：附件指向還在引用它的樣板（seed 換檔後 res_id 也是新樣板的 id）
    cr.execute("""
        UPDATE ir_attachment a
           SET res_id = t.id
          FROM document_template t
         WHERE t.attachment_id = a.id
           AND a.res_model = 'document.template'
           AND (a.res_id IS NULL OR a.res_id = 0)
    """)
    cr.execute("""
        UPDATE ir_attachment SET public = false
         WHERE res_model = 'document.template' AND public
    """)
