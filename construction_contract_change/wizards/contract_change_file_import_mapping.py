# -*- coding: utf-8 -*-
from odoo import models, fields


class ContractChangeFileImportMapping(models.TransientModel):
    """
    手動配對暫存記錄

    當 XLSX 匯入精靈無法自動比對某個工項時，建立一筆記錄，
    讓使用者手動選擇對應的 project.task，再繼續套用。
    """
    _name = 'contract.change.file.import.mapping'
    _description = '契約變更匯入手動配對'

    wizard_import_id = fields.Many2one(
        'contract.change.file.import.wizard',
        string='所屬匯入精靈',
        required=True,
        ondelete='cascade')

    # 類別：區分「配不到」與「對帳異常」兩種待處理工項，分流到不同頁籤
    kind = fields.Selection([
        ('unmatch', '配不到'),
        ('recon', '對帳異常'),
    ], string='類別', default='unmatch', readonly=True)

    # XLSX 來源資訊（唯讀，顯示用）
    item_no = fields.Char(string='XLSX 項次', readonly=True)
    item_name = fields.Char(string='XLSX 工項名稱', readonly=True)
    change_type = fields.Selection([
        ('add', '新增'),
        ('modify', '修改'),
        ('zero_out', '歸零'),
        ('delete', '刪除'),
        ('none', '不變更/略過'),
    ], string='處置')
    # 對帳異常時：系統偵測出的原始變更類型（唯讀，供參考）
    detected_type = fields.Selection([
        ('add', '新增'),
        ('modify', '修改'),
        ('zero_out', '歸零'),
        ('unchanged', '未變更'),
    ], string='偵測類型', readonly=True)
    orig_qty = fields.Float(string='文件原數量', readonly=True)
    new_qty = fields.Float(string='變更後數量', readonly=True)
    orig_price = fields.Float(string='文件原單價', readonly=True)
    new_price = fields.Float(string='變更後單價')
    # 對帳異常時：系統工項的現值（唯讀，與文件原數量/原單價對照）
    system_qty = fields.Float(string='系統現值數量', readonly=True)
    system_price = fields.Float(string='系統現值單價', readonly=True)
    new_amount = fields.Float(string='新金額', readonly=True)
    notes = fields.Char(string='備註', readonly=True)

    # 使用者手動選擇的對應工項
    task_id = fields.Many2one(
        'project.task',
        string='對應系統工項',
        domain="[('supervision_project_id', '=', project_id), ('active', '=', True)]",
        help='請選擇此 XLSX 工項對應的系統工項')

    parent_task_id = fields.Many2one(
        'project.task',
        string='所屬分類',
        domain="[('supervision_project_id', '=', project_id), ('is_summary_item', '=', True), ('active', '=', True)]",
        help='新增工項所屬的分類（類型為「新增」時填寫）')

    project_id = fields.Integer(
        string='工程 ID',
        related='wizard_import_id.wizard_id.project_id.id',
        store=False)
