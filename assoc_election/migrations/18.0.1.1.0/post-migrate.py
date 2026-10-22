"""18.0.1.1.0：選舉人與候選人的姓名／會員編號改成凍結名冊時的快照。

原本是讀即時會員資料的 related 欄位（投票中改會員資料就能讓選票顯示的姓名對應到別人），
升級後補上既有紀錄的快照值。
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE assoc_election_voter v
           SET member_name = p.name, member_no = COALESCE(v.member_no, m.member_no)
          FROM assoc_member m JOIN res_partner p ON p.id = m.partner_id
         WHERE m.id = v.member_id AND v.member_name IS NULL
    """)
    cr.execute("""
        UPDATE assoc_election_candidate c
           SET member_name = p.name, member_no = COALESCE(c.member_no, m.member_no)
          FROM assoc_election e, assoc_member m JOIN res_partner p ON p.id = m.partner_id
         WHERE e.id = c.election_id AND m.id = c.member_id AND c.member_name IS NULL AND e.state != 'draft'
    """)
