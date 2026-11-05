# -*- coding: utf-8 -*-
"""3.10.0：換七份系統預設樣板（2026-11-05 跑版檢查，Word 16／Excel 16 實印）。

(一) daily_log_2（監造日報表第二聯）：工程名稱的 ${project.name} 放在合併儲存格 A4:F4 裡的 B4，
    Excel 只顯示左上角 → 每一頁的工程名稱都印不出來。A4 改成「工程名稱：${project.name}」、B4 清空。
(二) review_control、defect_control、test_control（三份管制表）：表頭列設「跨頁重複標題列」，
    資料列撐高溢到下一頁時，那一頁仍看得到欄位標題。
(三) qc_staff_register、site_staff_register（新北附表8-1／8-2 系統預設版）：開工日期、預定完工日期
    兩格 2.75～3.1cm，「115年11月1日」最後一個「日」折到下一行 → 這兩格改 10pt。
(四) material_review_record（附表7 系統預設版）：「送審日期」那一格的 run 抄到粗體，比同欄其他值粗。
(三)(四) 由 tools/ntpc_forms/build_forms.py 重產（*_neutral.docx），新北兩案版由同一支工具的 *_ntpc.docx 經 seed_ntpc 換檔。
(一) 另外補一個隱藏的第 6 列：表頭第 5 列與資料第 7 列之間原本沒有定義第 6 列，第 1 頁多印一條空白列。
daily_log_c1（營造版施工日誌第一聯）不換：EAGLE 原檔就是「整張縮成一頁」，使用者 2026-11-05 裁示照 EAGLE。

系統裡的檔是「以前出貨過的版本」才換；被人換過的（checksum 不在 REPLACEABLE）一律不動，
seed 會記 WARNING。checksum 取自 git 歷史裡這幾個檔的每一個版本（sha1，與
ir.attachment.checksum 同一種算法）。做法同 18.0.3.8.2、18.0.3.9.0。
"""
import hashlib
import os

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import BLANK_DIR, TYPES, seed_default_templates

REPLACEABLE = {
    # daily_log_2.xlsx：8 個出貨版本
    'daily_log_2': {
        '05bc16272cf54445d9543e0ea683c2e2e262afd3',  # 2c00270
        '5bae66156d785ce7f882ecc5edca7dd166c5e710',  # 8ef9ab8
        '9b4e70c73be458ab5fa5750c024f3f96837f9f89',  # c20c5aa
        '8a463887f46040ff3017a3ba3219a8c191954636',  # 8091622
        '3fc537495b0568b1108b2e2715508ab6c2f684c5',  # 52dd7ab
        '8142be191494938f7e20270ecf164466f19d61dd',  # 7c26cbf
        'fb460abadbd74f8948e9a68a37447c32a139286c',  # 17932ad
        '38fb829a6567d3ff1ef88ce5eb3e63dcf215ecbf',  # 84ab5bf
    },
    # review_control.docx：2 個出貨版本
    'review_control': {
        'a27f3f295583ee3cf1f30db79d067c20666b2aa6',  # 341f994
        'c9a24a92f0e7647f52f4eca0fa34f23dae568707',  # a7a616f
    },
    # defect_control.docx：2 個出貨版本
    'defect_control': {
        'cfac9f008185bcecbc3cca0f32fb5c9b9fa693ae',  # 341f994
        '120d810f650116f27fb41bebcc35a99c6dc5af09',  # a7a616f
    },
    # test_control.docx：4 個出貨版本
    'test_control': {
        '2da050c67c9a9c5717a2c57859d2a32e09a2f408',  # 341f994
        'c976a3fe474d815e3efade927bc90dd5967850c5',  # 7700aa0／2e9b952
        '75f0cf0cab83a9109cbe0eb12118de4921083118',  # 872ae43（git log 要加 --full-history 才看得到）
        'ea4d1e92afc6eaa13f61d35a7e98d969ddd55afb',  # a7a616f
    },
    # qc_staff_register.docx、site_staff_register.docx、material_review_record.docx：各 1 個出貨版本（3.7.0）
    'qc_staff_register': {
        '6fa88b1fae01b97c116c8adb80e1ea02d8853b16',  # 089f1af
    },
    'site_staff_register': {
        'f2783985f63f9c91ed6d0af45a8550ec08b53668',  # 089f1af
    },
    'material_review_record': {
        'a203f5f38d1778e9076c361f42d562912a67c5bd',  # 089f1af
    },
}


def _already_new(env):
    """系統預設已經是磁碟上的新檔（例：從 3.8.2 以前一次升上來，3.8.2 的 migration 先灌了新檔）
    → 不用換，也不要記「可能有人換過」的假警告（2026-11-05 抗辯審查）。"""
    done = set()
    for ttype, _label, ext, _note in TYPES:
        if ttype not in REPLACEABLE:
            continue
        path = os.path.join(BLANK_DIR, '%s.%s' % (ttype, ext))
        with open(path, 'rb') as fh:
            new = hashlib.sha1(fh.read()).hexdigest()
        current = env['document.template'].search(
            [('template_type', '=', ttype), ('is_default', '=', True)], limit=1)
        if current and current.attachment_id.checksum == new:
            done.add(ttype)
    return done


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    types = tuple(t for t in REPLACEABLE if t not in _already_new(env))
    if types:
        seed_default_templates(env, types=types, replaceable=REPLACEABLE)
