# -*- coding: utf-8 -*-
"""18.0.1.4.0：既有人員機具設定一律改成共用（company_id 空白）

這一版起，日誌人機下拉只列「共用＋工程所屬公司」的項目。升級前下拉不分公司、大家都看得到全部；
既有項目掛的公司常常不是使用它的工程的公司（dev 實查 23,545 筆明細有 18,021 筆如此；
jt 有 56 筆掛在 My Company、給任泰的工程用）。全部改成共用＝升級前後每個人看到的清單不變。
唯一約束 UNIQUE(name, record_type, company_id) 把 NULL 視為互不相等，改完不會撞約束。
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE personnel_type SET company_id = NULL WHERE company_id IS NOT NULL")
    _logger.info('construction_equipment 18.0.1.4.0：%d 筆人員機具設定改成共用', cr.rowcount)
