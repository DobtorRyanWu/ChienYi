{
    'name': '公會理監事選舉',
    'version': '18.0.1.2.0',
    'category': 'Association',
    'summary': '會員大會現場電子投票：報到領票、手機投票、關票洗牌、開票與稽核鏈',
    'description': """
依《人民團體選舉罷免辦法》§6 的電子選舉票辦理理監事現場選舉。

- 無記名：選票不帶選舉人、不留 create_uid；開票時整批洗牌重寫，事後無法自資料庫關聯
- 領票：報到台產生 90 秒短效 QR → 手機領取綁定 → 選務輸入手機上的配對碼才可投
- 連記法／限制連記法上限、§11 重複圈選以一票計、名單外會員可填寫（write-in）
- 選務事件寫入 hash 串接的稽核鏈
""",
    'author': 'ChienYi',
    'license': 'LGPL-3',
    'depends': ['assoc_meeting'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'views/assoc_election_views.xml',
        'views/assoc_term_views.xml',
        'views/vote_templates.xml',
        'views/desk_templates.xml',
        'views/screen_templates.xml',
        'views/menus.xml',
        'report/result_report.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'assoc_election/static/src/js/desk_election.js',
            'assoc_election/static/src/js/vote.js',
            'assoc_election/static/src/js/screen.js',
            'assoc_election/static/src/css/assoc_screen.css',
        ],
    },
    'installable': True,
}
