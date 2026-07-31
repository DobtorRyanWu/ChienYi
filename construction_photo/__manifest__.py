# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 照片管理模組',
    # 1.4.0: 修復照片刪不掉（unlink 註解說會檢查「有無其他關聯」卻沒檢查，
    #        撞缺失照片行的 RESTRICT FK）+ 新增 _photo_source_line_refs() 反向級聯掛鉤
    # 1.3.0: 修復 photo.sync.mixin 對 project.project 失效（工程告示牌照片不同步）
    #        + 新增 _get_sync_project() 可覆寫掛鉤 + 既有告示牌照片一次性回填
    # 2.0.0: 伺服器端 EXIF GPS 解析（一處涵蓋所有照片入口，Pillow 為官方 image 內建）
    #        + 新增 gps_source 欄位區分「實拍座標」與「推定座標」
    #        + 座標繼承掛鉤 _get_photo_fallback_geo()：僅工程告示牌 opt-in
    # 3.0.0: 照片資料表收斂 —— 照片從 12 張表（本表 + 2 張缺失照片行 + 9 張 M2M）
    #        收斂成 supervision_photo 一張。新增 photo_stage / signboard_project_id
    #        與 _photo_source_field_map() 掛載規則；photo.sync.mixin 整個退場；
    #        unlink() 的 S→L→A 順序與遞迴防護大幅簡化（只剩一個 RESTRICT FK）。
    # 3.1.0: 新增後台批次上傳精靈 supervision.photo.upload.wizard —— 一次補回
    #        「檢試驗／通報單後台沒有上傳入口」與 3.0.0 改 One2many 後失去的
    #        「一次拖多檔」能力；三個描述欄位採整批共用預設值、事後可逐張改
    # 3.2.0: 座標兜底全面化 —— 原本只有工程告示牌與通報單會繼承座標，改為
    #        **每張照片最後都退到所屬工程案件的經緯度**（精確度：通報單 >
    #        告示牌工程 > 所屬工程）。繼承來的一律標 gps_source='inherit'，
    #        所以「實拍位置 vs 推定位置」在畫面上仍分得出來
    # 3.3.0: 後台照片頁籤統一改用共用嵌入式看板（照片在上、下方五個欄位），取代原本每個頁籤各自內嵌一份 <list>
    # 3.4.0: 手動改座標時 gps_source 跟著變成「前台輸入」（原本只在 create 判定，事後改座標仍顯示舊來源）；照片頁籤關掉無效的「加入」按鈕
    'version': '18.0.3.4.0',
    'category': 'Construction/Supervision',
    'summary': '工程照片管理與 GPS 追蹤',
    'description': """
工程監造系統 - 照片管理模組
============================

此模組提供工程照片管理功能：

主要功能
--------
* 工程照片上傳與管理 (supervision.photo)
* 照片標籤分類系統 (supervision.photo.tag)
* GPS 位置記錄與追蹤
* 來源追蹤 (施工日誌、自主檢查、缺失改善等)
* 拍攝資訊記錄

技術特點
--------
* 使用 ir.attachment 存儲照片檔案
* 支援多標籤分類
* GPS 位置資訊記錄
* 完整來源追蹤機制
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'mail',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Wizard 必須排在所有 views 之前：supervision_project_views.xml 等多個
        # 視圖用 %(action_photo_upload_wizard)d 引用這裡的 action，
        # 排在後面會噴 "External ID not found in the system"。
        'wizard/supervision_photo_upload_wizard_views.xml',
        # Views (photo_views first for action reference)
        'views/supervision_photo_views.xml',
        'views/supervision_photo_tag_views.xml',
        'views/supervision_photo_category_views.xml',
        'views/supervision_project_views.xml',
        'views/menu.xml',
        # Master data (loaded after views so menus can reference actions)
        'data/supervision_photo_category_data.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 25,
}
