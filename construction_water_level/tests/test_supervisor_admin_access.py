# -*- coding: utf-8 -*-
"""監造系統管理員的水位管理權限，要跟著「監造系統管理員」這個群組走。

**這個測試在防什麼**

拆模組前，水位各模型的管理列 ACL 直接綁 ``group_supervisor_admin``：
把人移出監造系統管理員，水位的刪除／建立權限就一起沒了。

拆模組時曾改成「監造系統管理員 implied 核心的水位監測管理員」。Odoo 的 implied
只會加不會減——移出監造系統管理員時，被帶進去的水位監測管理員不會跟著移除，
於是權限殘留，而且使用者表單上要另外去找那個群組才拔得掉。
這裡釘住：移出群組之後，管理權限要真的消失（退回一般內部使用者的權限）。
"""

from odoo.tests import common, new_test_user, tagged

# (模型, 動作)：管理列有、一般內部使用者沒有的權限，拿來分辨兩種身分
ADMIN_ONLY_RIGHTS = [
    ('water.level.site', 'unlink'),
    ('water.level.device', 'unlink'),
    ('water.level.reading', 'create'),
    ('water.level.source', 'unlink'),
    ('water.level.alert.channel', 'write'),
]


@tagged('post_install', '-at_install')
class TestSupervisorAdminWaterLevelAccess(common.TransactionCase):

    def test_rights_follow_supervisor_admin_group(self):
        admin_group = self.env.ref('construction_supervision_base.group_supervisor_admin')
        user = new_test_user(
            self.env, login='wl_supervisor_admin_test',
            groups='base.group_user,construction_supervision_base.group_supervisor_admin')

        for model, operation in ADMIN_ONLY_RIGHTS:
            self.assertTrue(
                self.env[model].with_user(user).has_access(operation),
                '監造系統管理員應該能對 %s 做 %s' % (model, operation))

        user.write({'groups_id': [(3, admin_group.id)]})

        self.assertNotIn(admin_group, user.groups_id)
        for model, operation in ADMIN_ONLY_RIGHTS:
            self.assertFalse(
                self.env[model].with_user(user).has_access(operation),
                '移出監造系統管理員後，不該還能對 %s 做 %s' % (model, operation))
