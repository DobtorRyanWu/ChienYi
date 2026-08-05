# -*- coding: utf-8 -*-
"""安裝／升級時把 data/templates_blank/ 的 13 個空白範本灌成系統預設樣板。

原本這 13 筆是靠 tools/gen_doc_templates/import_templates.py 手動以 odoo shell
灌進 odoo18_dev 的——模組本身既沒有 post_init_hook 也沒有 data XML，
所以全新安裝（部署到線上平台、開新租戶）樣板模組會是空的。

本檔是那支腳本的移植：TYPES 對照表與冪等邏輯原樣沿用。
"""

import base64
import logging
import os

_logger = logging.getLogger(__name__)

BLANK_DIR = os.path.join(os.path.dirname(__file__), 'data', 'templates_blank')

MIME = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

# (template_type, 中文標籤, 副檔名, 來源說明)
# 與 tools/gen_doc_templates/import_templates.py 的 TYPES 一致，改動時兩邊要同步。
TYPES = [
    ('daily_log_1',        '施工日誌-第一聯', 'xlsx', '111年 P11102 西區/監工日報表第一聯'),
    ('daily_log_2',        '施工日誌-第二聯', 'xlsx', '111年 P11102 西區/監工日報表第二聯'),
    ('self_inspection',    '自主檢查表',     'xlsx', '111年 P11102 通河東街/施工抽查紀錄表(自主檢查表)'),
    ('defect_improvement', '缺失改善',       'xlsx', '111年 P11102 西區/品質缺失矯正紀錄表'),
    ('defect_control',     '缺失改善管制表', 'xlsx', '110年 P11001/工程缺失改善追蹤一覽表'),
    ('review_control',     '送審管制表',     'xlsx', '111年 P11102/材料送審管制表'),
    ('test_control',       '檢(試)驗管制表', 'xlsx', '110年 P11001/材料檢驗統計表.送審管制表'),
    ('progress_report',    '進度報告',       'docx', '111年 P11102 西區/檢陳週報表'),
    ('progress_schedule',  '工程預定進度表', 'xlsx', '110年 P11006/施工預定進度表'),
    ('estimate_report',    '估驗計價表',     'xlsx', '111年 P11102 西區/估驗計價單'),
    ('acceptance_report',  '驗收報告',       'docx', '110年 P11001/勞務驗收紀錄'),
    ('notification_slip',  '通報單',         'xlsx', '111年 P11102 西區/預約式工程施工通知回報單'),
    ('material_test',      '材料試驗報告',   'docx', '111年 P11102 西區/試驗報告'),
    # 營造版（施工廠商填的「公共工程施工日誌」）。2026-08-05 由使用者提供，
    # 檔內已內建 ${...} 佔位符，套印走 mappings/daily_log_c1.py 的 placeholder 模式。
    ('daily_log_c1', '施工日誌-第一聯（營造版）', 'xlsx', '任泰第二期 EAGLE 樣板匯出'),
    ('daily_log_c2', '施工日誌-第二聯（營造版）', 'xlsx', '任泰第二期 EAGLE 樣板匯出'),
]


def seed_default_templates(env):
    """冪等建立／更新 13 筆系統預設樣板。

    重跑只會 update 既有記錄，不會產生重複——unique_default_per_type 約束
    （template_type + company_id + is_default）本身也擋著。
    """
    company = env.ref('base.main_company', raise_if_not_found=False)
    if not company:
        company = env['res.company'].search([], limit=1)
    if not company:
        _logger.warning('找不到公司，略過預設樣板建立')
        return

    Attachment = env['ir.attachment'].sudo()
    Template = env['document.template'].sudo()

    created, updated, skipped = 0, 0, 0
    for ttype, label, ext, note in TYPES:
        path = os.path.join(BLANK_DIR, f'{ttype}.{ext}')
        if not os.path.isfile(path):
            _logger.warning('預設樣板 %s：找不到檔案 %s，略過', ttype, path)
            skipped += 1
            continue
        with open(path, 'rb') as fp:
            data_b64 = base64.b64encode(fp.read())
        fname = f'{label}（空白範本）.{ext}'

        existing = Template.search([
            ('template_type', '=', ttype),
            ('is_default', '=', True),
            ('company_id', '=', company.id),
        ], limit=1)

        att = Attachment.create({
            'name': fname,
            'datas': data_b64,
            'mimetype': MIME[ext],
            'public': True,
            'res_model': 'document.template',
        })

        vals = {
            'name': f'{label}（空白範本）',
            'template_type': ttype,
            'is_default': True,
            'company_id': company.id,
            'version': '1.0',
            'attachment_id': att.id,
            'description': f'系統預設空白範本，來源：{note}（自動去識別化，僅保留版型骨架）',
            'active': True,
        }
        if existing:
            old_att = existing.attachment_id
            existing.write(vals)
            att.write({'res_id': existing.id})
            if old_att:
                old_att.unlink()
            updated += 1
        else:
            tmpl = Template.create(vals)
            att.write({'res_id': tmpl.id})
            created += 1

    total = Template.search_count([('is_default', '=', True)])
    _logger.info(
        '預設樣板處理完成：新建 %s、更新 %s、略過 %s；目前系統預設記錄總數 = %s',
        created, updated, skipped, total)


def post_init_hook(env):
    """模組安裝後灌入系統預設樣板"""
    seed_default_templates(env)
