"""委託書（計畫 v14 M11）。

兩張：
- `report_proxy_form`（帶單號）：資料已經在系統裡，右下角印一個可掃的 24 位單號 QR。
  **單號只從 `data` 進來，報表自己不鑄、也不寫入**——理由與開通通知單一字不差：
  核心的 `/report/pdf/<報表>/<id>` 是 auth=user 且不驗 docids，
  單號若在報表裡鑄，任何內部使用者打那條網址就能拿到別人的委託單號，
  而且 GET 還會順手把已發出的那張紙作廢。
- `report_proxy_blank`（空白）：掛在 `assoc.meeting` 上，大會名稱與日期先印好，
  委託人／受託人欄位留空白線。**沒有 QR**——它要給誰用還不知道。
  委託人那一格是「會員編號」的填寫欄（可以自己貼會員編號條碼），
  **不是會員卡條碼**：後者是「掃了就被標成親自出席」的持有者憑證。
"""

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.assoc_base.tools import ASSOC_TZ, qr_data_uri

QR_SIZE_PX = 240
# 人眼可讀的單號分組寬度：24 位切成 6 組 4 碼，承辦要對紙上那串時看得動
CODE_GROUP = 4


def _grouped(code):
    return ' '.join(code[i:i + CODE_GROUP] for i in range(0, len(code), CODE_GROUP))


class ProxyFormReport(models.AbstractModel):
    _name = 'report.assoc_meeting.report_proxy_form'
    _description = '委託書（帶單號）'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        code = data.get('code') or ''
        # **不可以要求一定要帶 docids。** 第十三輪我加過那道，第十四輪 skeptic 實跑打掉：
        # 核心 `web/static/src/webclient/actions/reports/utils.js:15-23` 在
        # `action.data` 非空時把 URL 組成 `?options=…&context=…`，
        # `active_ids` **只進 context、不進路徑**——所以後台那顆列印按鈕送出的
        # 請求 `docids=None`。而 `action_print_proxy_form` 已經先 `_issue_form_code()`
        # 並 commit，於是每按一次就是「會員手上那張紙作廢 ＋ 新的印不出來」。
        # 跨公會真正靠的是下面那道 `check_access('read')`（red-team 第十四輪實跑
        # 驗過它把 officer_nt 擋成 400），不是 docids。
        proxy = self.env['assoc.meeting.proxy'].sudo()._by_form_code(code)
        if not proxy:
            # 沒有有效單號就印不出來（直接打 /report/pdf/<報表>/<id> 會走到這裡）
            raise UserError(_('請從會員專區或委託書表單按「列印委託書」。'))
        if docids and proxy.id not in docids:
            # 單號與網址上的 id 不一致：拒絕，不要讓其中一個蓋過另一個
            raise UserError(_('委託書單號與這筆紀錄不符。'))
        # **公會閘門。** `_by_form_code` 必須 sudo（要用 hash 找人），
        # 所以到這裡為止沒有任何一次讀取經過 `record_rules.xml` 的公會 rule。
        # 用報表自己的 env 重新要一次讀取權：前台那條路的 env 是 sudo（刻意，
        # 路由已經硬綁 `principal_member_id`），`/report/pdf` 那條路的 env 是
        # 請求使用者本人，跨公會就在這裡被擋下來。
        proxy.with_env(self.env).check_access('read')
        return {
            'doc_ids': proxy.ids,
            'doc_model': 'assoc.meeting.proxy',
            'docs': proxy,
            'proxy': proxy,
            'code_grouped': _grouped(code),
            'qr': qr_data_uri(self.env, code, QR_SIZE_PX),
            # 開會時間是「公會當地發生的事實」，釘死公會時區、不隨列印的人跑
            'assoc_tz': ASSOC_TZ,
        }


class ProxyBlankReport(models.AbstractModel):
    _name = 'report.assoc_meeting.report_proxy_blank'
    _description = '委託書（空白）'

    @api.model
    def _get_report_values(self, docids, data=None):
        meetings = self.env['assoc.meeting'].browse(docids)
        return {
            'doc_ids': meetings.ids,
            'doc_model': 'assoc.meeting',
            'docs': meetings,
            'assoc_tz': ASSOC_TZ,
        }
