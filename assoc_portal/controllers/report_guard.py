"""擋住通知單的 HTML 輸出路徑（計畫 P5）。

wkhtmltopdf 狀態不正常時，前端會退回 `GET /report/html/<報表>?options={...}`，
token 就跟著進了 access log。這裡只擋 HTML 那條路由——
**不要去覆寫 `_render_qweb_html`**：核心產 PDF 時自己就會呼叫它。
"""

from odoo import _, http
from odoo.addons.web.controllers.report import ReportController
from odoo.exceptions import UserError

from ..report.activation_notice import REPORT_NAME

# 核心接受的兩種參照形式（report_name 與 action 的 xmlid）
NOTICE_REFS = frozenset({REPORT_NAME, 'assoc_portal.action_report_activation_notice'})
# 收據一律給過帳當下存下來的那一份，不即時重算：
# `/report/pdf/...` 會用**現值**重新渲染，於是同一個收據號碼可以印出兩份
# 內容不同的文件。核心的 report_routes 不檢查報表的 `groups_id`
# （web/controllers/report.py），所以擋不能靠那個。
# 這張報表沒有 binding_model_id，不在列印選單裡，擋掉不影響任何既有入口。
RECEIPT_REFS = frozenset({'assoc_portal.report_receipt',
                          'assoc_portal.action_report_receipt'})
# 委託書（帶單號）同理：`/report/html/<報表>?options={"code": …}` 會把 24 位單號
# 塞進 query string，單號就進了 access log，與通知單一模一樣的漏法。
# 空白委託書沒有任何秘密，不必擋。
PROXY_FORM_REFS = frozenset({'assoc_meeting.report_proxy_form',
                             'assoc_meeting.action_report_proxy_form'})


# 秘密走報表 `data` 的兩張報表：**只准 POST。**
# **它買到的不是「秘密不會進 log」**——第十四輪 skeptic 與 red-team 各自實跑證明
# werkzeug 的 access log 在**進 controller 之前**就寫下 request line，
# 所以被這道擋成 400 的那個 GET，單號其實早就進 log 了；POST 帶 query string
# 也一樣會進。**這條殘餘風險要寫進提案的限制段，不可以宣稱已修。**
# 這道真正買到的是：讓**正當流程**不可能把秘密放進網址
# （wkhtmltopdf 不可用時核心會退回 GET；前端若哪天改成 GET 也會當場紅），
# 而正當入口都是 POST（`/report/download` 送 POST；前台列印路由自己 render、
# 根本不經這個 controller），所以限 POST 不擋掉任何既有路徑。
POST_ONLY_REFS = NOTICE_REFS | PROXY_FORM_REFS


class AssocReportController(ReportController):

    @http.route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        # 兩種寫法都要擋：核心的 `_get_report()`（ir_actions_report.py:649-672）
        # 先用 report_name 找，找不到再 `env.ref()`，所以
        # `/report/html/assoc_portal.action_report_activation_notice` 也到得了同一張報表。
        # 這裡刻意不查 registry：守衛要在沒有 env 的情況下也成立，
        # 而且「查不到就放行」是 fail-open。
        if converter != 'pdf' and reportname in NOTICE_REFS:
            raise UserError(_('開通通知單只能列印 PDF。'))
        if converter != 'pdf' and reportname in PROXY_FORM_REFS:
            raise UserError(_('委託書只能列印 PDF。'))
        if reportname in POST_ONLY_REFS and http.request.httprequest.method != 'POST':
            # GET 會把 data 裡的秘密（單號／開通 token）寫進 access log
            raise UserError(_('這張報表請從表單上的列印按鈕產生。'))
        if reportname in RECEIPT_REFS:
            raise UserError(_('收據請用收款單上的「列印收據」，那會給過帳當下存下來的正本。'))
        return super().report_routes(reportname, docids=docids, converter=converter, **data)
