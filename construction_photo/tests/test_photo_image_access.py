# -*- coding: utf-8 -*-
"""回歸測試 —— 非 base.group_system 使用者取得照片影像。

原始 bug（代操人員 2026-08-27 回報）：後台地圖模式（photo_map）的縮圖全部是
灰色佔位圖。根因不在地圖，而在**縮圖 URL 打錯了模型**：

    /web/image/ir.attachment/<att_id>/datas/200x200   ← 壞的
    /web/image/supervision.photo/<photo_id>/image/…   ← 對的

Odoo core `ir.attachment.check()` 有一條：

    if not self.env.is_system():
        if not res_id and create_uid != self.env.uid:
            raise AccessError(...)

也就是「res_id 為空的附件」只有建立者本人與 base.group_system 讀得到。
而 `/web/image` 的 controller 會把 AccessError（UserError 子類）吞掉、
改回傳 web.image_placeholder —— 於是畫面上是一片灰圖、HTTP 仍然 200，
完全看不出是權限問題。生產站 4,484 張照片有 4,373 張的附件 res_id=0
（舊系統遷移留下的），對代操帳號全滅。

用 HttpCase 而不是 TransactionCase：`ir.binary` 產生影像串流時會用到
`request`（`http.py` 的 `Stream.from_binary_field` 讀 `request.env`），
沒有 HTTP context 會直接 RuntimeError，測不到真正的行為。

佔位圖的比對基準不寫死 bytes，改用「查一個不存在的 id」即時取得 ——
MissingError 同樣是 UserError 子類，走的是同一條 fallback，
所以 Odoo 換掉佔位圖檔案時本測試不會假性失敗。
"""

import base64

from odoo.tests.common import HttpCase, tagged

# 32x32 紅色 PNG（要夠大，縮圖後才不會與佔位圖巧合等長）
RED_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAPElEQVRYhe3OMQEA'
    'IAzAsIF/z0MGjiYKenXPzsxHTb2BuwECBAgQIECAAAECBAgQIECAAAECBAgQIPAB'
    'C6MBAcCuKgcAAAAASUVORK5CYII='
)


@tagged('post_install', '-at_install', 'construction_photo')
class TestPhotoImageAccess(HttpCase):

    def setUp(self):
        super().setUp()
        self.project = self.env['project.project'].create({
            'name': '照片取圖權限測試工程',
            'code': 'IMG-ACL',
            'company_id': self.env.company.id,
        })
        # 刻意複製生產站的病灶：res_model / res_id 都空的附件，
        # 建立者是 superuser（等一下用另一個使用者去讀）
        self.orphan_att = self.env['ir.attachment'].create({
            'name': 'orphan.png',
            'datas': base64.b64encode(RED_PNG),
            'mimetype': 'image/png',
            'public': False,
        })
        self.photo = self.env['supervision.photo'].create({
            'project_id': self.project.id,
            'attachment_id': self.orphan_att.id,
        })
        # 內部使用者，但**沒有** base.group_system —— 代操帳號（jt100/jtsy）
        # 就是這種身分。用 admin 測永遠測不出這個 bug。
        self.operator = self.env['res.users'].create({
            'name': 'photo_acl_operator',
            'login': 'photo_acl_operator',
            'password': 'photo_acl_operator',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref(
                    'construction_supervision_base.group_supervisor_admin').id,
            ])],
        })

    def _placeholder_bytes(self):
        """即時取得佔位圖：查一個不存在的 id 會走同一條 fallback。"""
        res = self.url_open(
            '/web/image/supervision.photo/999999999/image/200x200?crop=true')
        self.assertEqual(res.status_code, 200)
        return res.content

    def test_setup_user_is_not_system(self):
        """前提檢查：測試帳號真的不是系統管理者，否則整個測試沒有意義。"""
        self.assertFalse(
            self.operator.has_group('base.group_system'),
            '測試帳號不能有 base.group_system，否則測不出這個 bug')

    def test_orphan_attachment_reproduces_production_state(self):
        """前提檢查：病灶條件成立（res_id 為空、非 public）。"""
        self.assertFalse(self.orphan_att.res_id)
        self.assertFalse(self.orphan_att.res_model)
        self.assertFalse(self.orphan_att.public)

    def test_photo_route_returns_real_image(self):
        """對的路徑：/web/image/supervision.photo/<id>/image 拿得到真圖。

        這正是 photo_map 縮圖現在走的路徑，這條紅了就是破圖復發。
        """
        self.authenticate('photo_acl_operator', 'photo_acl_operator')
        placeholder = self._placeholder_bytes()
        res = self.url_open(
            '/web/image/supervision.photo/%s/image/200x200?crop=true'
            % self.photo.id)
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(
            res.content, placeholder,
            '非系統管理者拿到佔位圖 = 地圖縮圖又破了')

    def test_attachment_route_returns_placeholder(self):
        """壞的路徑：直接打 ir.attachment 會被 core 擋成佔位圖。

        這是「為什麼縮圖 URL 不能寫 ir.attachment」的證據。
        哪天 core 改了 check() 的行為這條會紅 —— 那時要回來重新評估，
        不是直接把它刪掉。
        """
        self.authenticate('photo_acl_operator', 'photo_acl_operator')
        placeholder = self._placeholder_bytes()
        res = self.url_open(
            '/web/image/ir.attachment/%s/datas/200x200?crop=true'
            % self.orphan_att.id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.content, placeholder,
            'res_id 為空的附件對非系統管理者應該只拿得到佔位圖')
