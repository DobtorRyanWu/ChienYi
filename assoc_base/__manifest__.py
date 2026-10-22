{
    'name': '公會會員基礎',
    'version': '18.0.1.2.0',
    'category': 'Association',
    'summary': '公會會員名冊、會籍與會費狀態、會員卡',
    'description': """
公會會員系統的共用地基：會員名冊（同庫多公會，以 res.company 隔離）、
會費繳納狀態與選舉權判定、會員卡（靜態 QR，供大會報到掃描）、
理監事屆次（選罷辦法 §6 要求選票載明選舉屆次）。
""",
    'author': 'ChienYi',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'base_import'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'views/assoc_member_views.xml',
        'views/assoc_term_views.xml',
        'views/assoc_document_views.xml',
        'views/assoc_audit_views.xml',
        'views/menus.xml',
        'report/member_card_report.xml',
        'data/assoc_data.xml',
    ],
    'installable': True,
    'application': True,
}
