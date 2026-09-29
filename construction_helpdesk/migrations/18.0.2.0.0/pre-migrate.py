# -*- coding: utf-8 -*-
"""18.0.2.0.0（分級標準 v0.3）：服務單「待客戶確認」拆成「待客戶補件」「待客戶驗證」。

舊狀態 waiting_customer 同時用在「修好之前請客戶補資料」與「修好之後請客戶確認」，
依關聯問題單判斷是哪一種：
  - 沒有掛問題單            → processing（兩個等待狀態只給已掛問題單的單用）
  - 問題單已部署（待驗證／已結案）→ waiting_verify
  - 其他                    → waiting_info
要在 ORM 載入新的 selection 之前做（pre），否則舊值會殘留在資料庫裡。
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE construction_service_ticket
           SET state = 'processing'
         WHERE state = 'waiting_customer' AND problem_id IS NULL
    """)
    no_problem = cr.rowcount
    cr.execute("""
        UPDATE construction_service_ticket t
           SET state = 'waiting_verify'
          FROM construction_problem p
         WHERE t.problem_id = p.id
           AND t.state = 'waiting_customer'
           AND p.state IN ('pending_verify', 'done')
    """)
    verify = cr.rowcount
    cr.execute("""
        UPDATE construction_service_ticket
           SET state = 'waiting_info'
         WHERE state = 'waiting_customer'
    """)
    info = cr.rowcount
    _logger.info('construction_helpdesk 2.0.0：待客戶確認 → 處理中 %s、待客戶驗證 %s、待客戶補件 %s',
                 no_problem, verify, info)
