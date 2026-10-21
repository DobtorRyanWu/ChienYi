# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 水位監測',
    # 1.x–2.8：整套水位監測都在本模組（版本歷程見 water_level_core 的 manifest）。
    # 3.0.0: 拆模組。共用的部分搬到 water_level_core、社區蓄水池搬到 community_water_level，
    #        本模組只留工程案件這一側：場域／監測站／水位紀錄的 project_id、
    #        一案一場域的部分唯一索引、工程前台（portal 角色）的 ACL 與 record rule、
    #        「水位監測」選單掛到品質安全底下。資料表與欄位一律不動。
    #        升級指令：有社區資料的庫要 -u construction_water_level -i community_water_level
    #        同一次跑（migrations/18.0.3.0.0 與核心的 pre_init_hook 都會擋）。
    #        2026-10-21 起社區模組移到獨立專案 water-odoo、不在本 repo：ChienYi 的庫（8069、jt）只裝核心＋本模組。
    'version': '18.0.3.0.0',
    'category': 'Construction/Supervision',
    'summary': '水位監測接上工程案件：場域綁工程、前台依工程成員看水位',
    'description': """
工程監造系統 - 水位監測
========================

在水位監測核心（water_level_core）上補工程案件這一側：

* 監測場域綁工程案件（project.project），一案一場域
* 監測站、水位紀錄帶工程案件，後台可依工程分群
* 工程前台：參與成員看自己的工程、老闆（訂閱者）看全部工程場域
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'water_level_core',
        'project',
        'construction_supervision_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/water_level_security.xml',
        'views/water_level_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}
