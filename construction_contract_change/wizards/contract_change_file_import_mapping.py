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

    # 與精靈／變更明細同一組三選項，否則表尾總計列在這個頁籤上只能選「既有彙總項」，
    # 問題只解一半。
    parent_kind = fields.Selection([
        ('existing', '原契約已有的彙總項'),
        ('new_group', '本次變更新增的彙總項'),
        ('top_level', '無父項（頂層項次）'),
    ], string='父項類型',
        help='無父項（頂層項次）＝ 與「壹 發包工程費」同層，會直接計入契約金額；'
             '表尾的「總計／總價／合計」列請一併勾「不計入契約金額」。')

    parent_task_id = fields.Many2one(
        'project.task',
        string='所屬分類',
        domain="[('supervision_project_id', '=', project_id), ('is_summary_item', '=', True), ('active', '=', True)]",
        help='新增工項所屬的分類（類型為「新增」時填寫）')

    # 「在契約樹裡找不到父工項的章節列」專用 —— 政府變更明細表的表尾總計列
    # （「貳 總計」「總價(總計)」…）就是這一型。它沒有父工項，套用後會成為
    # 第二個頂層工項，而契約金額 ＝ Σ 頂層工項 → 金額非 0 就會直接墊高契約金額。
    # 所以一律送進本頁籤裁決，並預先勾好建議值。
    is_new_group = fields.Boolean(
        string='章節列',
        readonly=True,
        help='此列在來源檔是「章節（彙總）列」，不是一般工項')
    exclude_from_contract_amount = fields.Boolean(
        string='不計入契約金額',
        help='勾選後此工項雖然會建立，但不計入工程的契約金額。\n'
             '表尾的「總計／總價／合計」列請勾選 —— 它的金額是其他章節的重複，'
             '不勾會讓契約金額變成兩倍。\n'
             '若這其實是一個該計入的新章節，請取消勾選。')

    project_id = fields.Integer(
        string='工程 ID',
        related='wizard_import_id.wizard_id.project_id.id',
        store=False)
