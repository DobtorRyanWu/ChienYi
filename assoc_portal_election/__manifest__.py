{
    'name': '公會會員前台：選舉',
    'version': '18.0.1.1.0',
    'category': 'Association',
    'summary': '會員在前台自助登記參選與退選',
    'description': """把「候選人登記」從只能由承辦後台建檔，擴充成會員可以在前台自助登記。

為什麼是獨立的橋接模組：assoc_portal 與 assoc_election 刻意互不依賴（計畫 D8：
選舉的金路徑不依賴會員登入，portal 不裝時選舉照跑）。自助登記同時要用到兩邊，
所以放在這裡宣告雙向依賴，而不是在 portal 裡隱性引用 assoc.election——這個環境
已經有過隱性依賴的前例。不裝這個模組，兩邊都照舊。

資格與時限的閘門一律在模型層（_register_self / _withdraw_self），
controller 只負責解出「登入者是哪一位會員」。
""",
    'author': 'ChienYi',
    'license': 'LGPL-3',
    'depends': ['assoc_portal', 'assoc_election'],
    'data': [
        'views/assoc_election_views.xml',
        'views/portal_templates.xml',
        'views/portal_meeting_election.xml',
    ],
    'installable': True,
    'application': False,
}
