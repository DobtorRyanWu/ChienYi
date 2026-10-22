"""`fee_paid_until` 從可編輯欄位變成 stored compute（M8）。

和 `assoc_base` 的同名腳本做同一件事，**兩邊都要有**：

升級順序決定資料存不存在。只跑 `-u assoc_portal` 的話，`assoc_base` 的 migration
不會執行，但 `assoc.member` 的 compute 會在這次升級重算——於是既有的「會費繳至」
先被洗掉，之後再也救不回來（實測：只升 assoc_portal，值就沒了）。

`WHERE fee_paid_opening IS NULL` 讓它是冪等的：兩個模組一起升級時，
先跑的那個搬完，後跑的那個什麼都不做。
"""


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE assoc_member ADD COLUMN IF NOT EXISTS fee_paid_opening date;
        ALTER TABLE assoc_member ADD COLUMN IF NOT EXISTS coverage_from date;
        UPDATE assoc_member SET fee_paid_opening = fee_paid_until
         WHERE fee_paid_opening IS NULL AND fee_paid_until IS NOT NULL;
    """)
