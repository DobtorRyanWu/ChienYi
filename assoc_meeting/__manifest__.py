{
    'name': '公會會員大會',
    'version': '18.0.1.0.0',
    'category': 'Association',
    'summary': '會員大會與研討會、報到台（掃碼分流）、委託出席（§38）、簽退與積分',
    'author': 'ChienYi',
    'license': 'LGPL-3',
    'depends': ['assoc_base'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'views/assoc_meeting_views.xml',
        'views/assoc_meeting_proxy_views.xml',
        'views/desk_templates.xml',
        'views/menus.xml',
        'report/credit_certificate.xml',
        'report/proxy_form.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'assoc_meeting/static/src/css/assoc.css',
            'assoc_meeting/static/src/js/desk.js',
        ],
    },
    'installable': True,
}
