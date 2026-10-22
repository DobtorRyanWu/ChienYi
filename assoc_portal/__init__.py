from . import models
from . import controllers
from . import report


def post_init_hook(env):
    """釘住兩個決定攻擊面的 auth_signup 參數。

    這兩個值不是偏好設定，是本模組的前提：
    - `reset_password`：開著的話 `/web/reset_password` 會復活，而信件一律 hold
      在佇列（核心卻顯示「已寄出」），會員只會一直等；重設密碼走紙本通知單。
    - `invitation_scope`：b2c 等於開放匿名註冊。
    不用 XML data 是因為 `ir.config_parameter` 以 key 為唯一鍵，
    既有列沒有 external id，載入資料會撞唯一約束。
    """
    params = env['ir.config_parameter'].sudo()
    params.set_param('auth_signup.reset_password', 'False')
    params.set_param('auth_signup.invitation_scope', 'b2b')

