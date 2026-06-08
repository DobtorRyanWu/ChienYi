# -*- coding: utf-8 -*-
{
    'name': 'Dobtor Spreadsheet Editor — ChienYi Bridge',
    'version': '18.0.1.0.0',
    'summary': '把 xlsx 高保真匯入／可編輯試算表接到 ChienYi 估驗計價',
    'description': 'dobtor_spreadsheet_editor 與 ChienYi 業務模組橋接：'
    'payment.estimate（估驗計價）表單加「匯入估驗試算表」按鈕，開 Xlsx 高保真匯入'
    '（解析→可編輯 o-spreadsheet→下載 xlsx）。通用編輯器保持與業務無關，整合集中於本 bridge。',
    'category': 'Productivity',
    'author': 'Dobtor / ChienYi',
    'license': 'LGPL-3',
    'depends': [
        'dobtor_spreadsheet_editor',
        'construction_payment',
    ],
    'data': [
        'views/payment_estimate_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
