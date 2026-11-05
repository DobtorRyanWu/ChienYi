# -*- coding: utf-8 -*-
"""安裝／升級時把 data/templates_blank/ 的空白範本灌成系統預設樣板。

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
    # 2026-08-05 換成使用者提供的 EAGLE 版「自主檢查總表」（內建 ${} 佔位符，專案層級彙總）
    ('self_inspection',    '自主檢查總表',   'xlsx', '任泰第二期 EAGLE 樣板匯出'),
    # 2026-09-11 新增：自主檢查表「單張」的預設樣板（動態表格，不限項目數）。
    # 由 tools/gen_doc_templates/build_self_inspection_form.py 從使用者提供的
    # inspection_template.docx 草稿加工而來（修 {%tr %}、重做照片頁、補量測區塊）。
    ('self_inspection_form', '自主檢查表（單張）', 'docx', '使用者提供之動態表格草稿'),
    ('defect_improvement', '矯正與預防處理紀錄', 'docx', '任泰第二期 EAGLE 樣板匯出'),
    ('defect_control', '矯正與預防紀錄管制表', 'docx', '任泰第二期 EAGLE 樣板匯出'),
    ('review_control', '材料設備送審管制總表', 'docx', '任泰第二期 EAGLE 樣板匯出'),
    # 2026-08-11 新增：由既有案件的管制表 1.計畫 工作表去識別化而來，明細只留
    # 一列 ${table:items.*} 樣板列，套印時依筆數展開。表名是 ${project.reportTitle}，
    # 計畫書／分項計畫／施工圖三張表共用這一份。
    ('plan_control', '計畫書送審管制總表', 'xlsx', '既有案件管制表 1.計畫 工作表'),
    # 2026-08-12 換成工程會新版格式（「材料設備檢（試）驗管制總表（修正版）」），
    # 由 tools/gen_doc_templates/build_test_control.py 加工佔位符後產生。
    ('test_control', '材料設備檢（試）驗管制總表', 'docx', '工程會新版空白表（修正版）'),
    # 2026-08-06 換成 EAGLE 的 progressReportTemplate（xlsx，內建 ${} 佔位符）。
    # 舊的 .docx（來源「111年 P11102 西區/檢陳週報表」）沒有對照表也不是同一份表，已移除。
    ('progress_report',    '進度報告',       'xlsx', '任泰第二期 EAGLE 樣板匯出'),
    ('progress_schedule',  '工程預定進度表', 'xlsx', '110年 P11006/施工預定進度表'),
    ('estimate_report',    '估驗計價表',     'xlsx', '111年 P11102 西區/估驗計價單'),
    ('acceptance_report',  '驗收報告',       'docx', '110年 P11001/勞務驗收紀錄'),
    ('notification_slip',  '通報單',         'xlsx', '111年 P11102 西區/預約式工程施工通知回報單'),
    ('material_test',      '材料試驗報告',   'docx', '111年 P11102 西區/試驗報告'),
    # 營造版（施工廠商填的「公共工程施工日誌」）。2026-08-05 由使用者提供，
    # 檔內已內建 ${...} 佔位符，套印走 mappings/daily_log_c1.py 的 placeholder 模式。
    ('daily_log_c1', '施工日誌-第一聯（營造版）', 'xlsx', '任泰第二期 EAGLE 樣板匯出'),
    ('daily_log_c2', '施工日誌-第二聯（營造版）', 'xlsx', '任泰第二期 EAGLE 樣板匯出'),
    # EAGLE 的全域估驗樣板（原系統打包成 zip；這裡拆成兩份各自下載）
    ('invoice_detail', '估驗詳細表', 'xlsx', '任泰第二期 EAGLE 樣板匯出'),
    ('invoice_photo', '估驗照片', 'docx', '任泰第二期 EAGLE 樣板匯出'),
    # 2026-10-25 從新北市政府工程契約原表切出（tools/ntpc_forms/build_forms.py 的 neutral 版：
    # 拿掉新北的附表編號，機關名稱用案件的主辦機關）
    ('material_inspection_record', '材料設備品質抽(查)驗紀錄表', 'docx',
     '新北市政府工程契約 附表11（承攬廠商品質管制規定）'),
    ('estimate_progress_report', '工程施工進度報告表（估驗附件）', 'docx',
     '新北市政府工程契約 第五條附件一、附件二'),
    # 3.7.0 契約附表（只帶表頭；附表6-2、附表7 有送審資料可帶）
    ('plan_review_opinion_construction', '施工計畫審查意見表', 'docx', '新北市政府工程契約 附表4'),
    ('plan_review_opinion_quality', '品質計畫審查意見表', 'docx', '新北市政府工程契約 附表5'),
    ('plan_review_stamp', '計畫送審核章表', 'docx', '新北市政府工程契約 附表6-2'),
    ('material_review_record', '材料設備申請及審查紀錄表', 'docx', '新北市政府工程契約 附表7'),
    ('qc_staff_register', '廠商品管人員登錄表', 'docx', '新北市政府工程契約 附表8-1'),
    ('site_staff_register', '工地相關人員登錄表', 'docx', '新北市政府工程契約 附表8-2'),
    ('quality_evaluation', '施工品質評量表', 'docx', '新北市政府工程契約 契約附表八'),
    ('engineer_supervision_record', '專任工程人員督察紀錄表', 'docx', '新北市政府工程契約 附表10-1'),
    ('technician_sign_sheet', '施工日誌之技術士簽章表', 'docx', '新北市政府工程契約 附表9-1 附件'),
    ('soil_transport_attachments', '土石方運送附件（照片黏貼頁）', 'docx', '新北市政府工程契約 第九條附件一、二、四'),
]


def seed_default_templates(env, types=None, replaceable=None):
    """冪等建立／更新 TYPES 列的系統預設樣板。

    重跑只會 update 既有記錄，不會產生重複——unique_default_per_type 約束
    （template_type + company_id + is_default）本身也擋著。

    :param types: 只處理這些 template_type（None＝全部；安裝時用）
    :param replaceable: {template_type: {sha1, ...}}——既有系統預設的附件 checksum 在清單裡
        （＝之前出貨的版本）才覆蓋；不在清單裡代表有人在系統裡換過，**略過並記 WARNING**，
        升級不能默默蓋掉別人換過的檔（2026-10-25 紅隊審查）。None＝不檢查（安裝時沒有既有記錄）。
        找不到既有記錄時一律新建；同一類型的系統預設不只一筆（含已封存）時略過並記 WARNING。
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
        if types is not None and ttype not in types:
            continue
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

        if replaceable is not None:
            # 已封存的也要算：不然封存的那筆會讓 create 撞 UNIQUE、整個 -u 中止
            all_defaults = Template.with_context(active_test=False).search([
                ('template_type', '=', ttype), ('is_default', '=', True)])
            if len(all_defaults) > 1 or (all_defaults and not existing):
                _logger.warning(
                    '預設樣板 %s：系統預設有 %s 筆（含封存或掛在別家公司），不自動處理，請人工確認',
                    ttype, len(all_defaults))
                skipped += 1
                continue
            if existing and existing.attachment_id.checksum not in replaceable.get(ttype, set()):
                _logger.warning(
                    '預設樣板 %s：系統裡的檔（checksum %s）不是已知的出貨版本，可能有人換過，'
                    '不覆蓋；要更新請手動上傳 data/templates_blank/%s.%s',
                    ttype, existing.attachment_id.checksum, ttype, ext)
                skipped += 1
                continue

        att = Attachment.create({
            'name': fname,
            'datas': data_b64,
            'mimetype': MIME[ext],
            # 不公開：public=True 讓未登入的人用 /web/content/<連號 id> 就能下載每一份預設樣板。
            # 非公開附件的存取看 res_model/res_id 指到的 document.template，所以下面建好
            # 樣板後一定要回填 res_id，否則變孤兒附件（只有建立者與 base.group_system 讀得到）
            'public': False,
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
                # 🔴 「複製樣板」（action_duplicate 用 copy()）的副本與系統預設共用同一個附件。
                # 還有樣板指著它就不能刪——外鍵是 SET NULL，副本會靜靜變空，而匯出優先挑
                # 公司／專案層的副本，整家公司都會失敗（2026-11-05 red-team 實證）。
                # 不刪，改掛到還在用它的樣板上（非公開附件的存取看 res_id 指的那筆）。
                users = Template.with_context(active_test=False).search(
                    [('attachment_id', '=', old_att.id)])
                if users:
                    old_att.write({'res_id': users[0].id})
                else:
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
