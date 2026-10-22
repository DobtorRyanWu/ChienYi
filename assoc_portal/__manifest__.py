{
    'name': '公會會員前台',
    'version': '18.0.1.2.0',
    'category': 'Association',
    'summary': '會員帳號開通、身分證登入、會員自助頁（資料、證書、會員證）',
    'description': """
會員前台：
- 以 Email 或身分證字號登入（身分證路徑等時處理，不把輸入交給核心避免寫進 log）
- 帳號開通與重設密碼走紙本一次性通知單（不寄信）
- 一個帳號只對應一位會員；同一身分證在他公會已開通時拒絕並留軌跡
- 會員自助：個人資料（身分證隱碼）、證書與照片上傳、繳費與會員證（M8 接手）
""",
    'author': 'ChienYi',
    'license': 'LGPL-3',
    'depends': ['assoc_meeting', 'portal', 'auth_signup'],
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'views/assoc_member_views.xml',
        'views/assoc_dues_views.xml',
        'views/assoc_gift_views.xml',
        # 統計選單引用上面三個檔裡的 action，所以一定排在它們之後
        'views/assoc_stats_menus.xml',
        'views/portal_templates.xml',
        'views/portal_meeting_templates.xml',
        'report/activation_notice.xml',
        'report/receipt.xml',
        'data/mail_template.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'assoc_portal/static/src/js/desk_gift.js',
        ],
    },
    'installable': True,
}
