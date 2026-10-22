"""`fee_paid_until` 從可編輯欄位變成 stored compute（M8）。

升級時 compute 會整欄重算，把既有的手填值洗掉——所以要**先**把現值搬到
新的可編輯欄位 `fee_paid_opening`，compute 再從它往後接。
用 SQL 而不是 ORM：這時候新欄位還沒在 registry 裡。

`assoc_portal` 有一份一樣的腳本：升級順序決定資料存不存在——只跑
`-u assoc_portal` 的話這支不會執行，而 compute 會在那次升級把值洗掉。
`WHERE fee_paid_opening IS NULL` 讓兩份互為冪等。
"""


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE assoc_member ADD COLUMN IF NOT EXISTS fee_paid_opening date;
        ALTER TABLE assoc_member ADD COLUMN IF NOT EXISTS coverage_from date;
        UPDATE assoc_member SET fee_paid_opening = fee_paid_until
         WHERE fee_paid_opening IS NULL AND fee_paid_until IS NOT NULL;
    """)
