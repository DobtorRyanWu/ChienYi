# -*- coding: utf-8 -*-
{
    'name': '千溢科技官方網站',
    'version': '18.0.1.0.0',
    'category': 'Website',
    'summary': '千溢科技行銷首頁與可拖拉區塊（源於工程，歸於智慧）',
    'description': """
千溢科技 (QYTech) 官方網站
==========================
將千溢科技單頁式行銷網站移植為 Odoo 18 原生網站區塊（snippet）：

- 6 個可在網站建構器拖拉、雙擊編輯的區塊：Hero、公司簡介、核心產品輪播、
  說明中心（即時搜尋）、聯絡/報修表單、Footer
- 內建 FontAwesome 6 與 Noto Sans TC 字型，避免破圖
- 聯絡表單對接 Odoo CRM（crm.lead）
- 登入按鈕導向 /web/login
""",
    'author': 'QYTech',
    'website': 'https://www.qytech.com.tw',
    'license': 'LGPL-3',
    'depends': [
        'website',
        'website_crm',
    ],
    'data': [
        'views/snippets.xml',
        'views/homepage.xml',
        'data/website_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            # FontAwesome 6（自帶，避免使用 Odoo 內建 4.7 造成破圖）
            'website_qytech/static/lib/fontawesome6/css/all.css',
            # 自訂樣式（漸層 / glass / clip-path / 動畫 / 配色）
            'website_qytech/static/src/scss/qytech.scss',
            # 互動邏輯（說明中心搜尋等）
            'website_qytech/static/src/js/qytech.js',
        ],
    },
    'installable': True,
    'application': True,
}
