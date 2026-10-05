# -*- coding: utf-8 -*-
"""停工／退單 HTTP 端到端驗證（容器內 python3 執行；要先跑 e2e_setup.py）。

docker exec pg18-odoo python3 /mnt/extra-addons/construction_notification_slip/tests/e2e_http.py

前台用臨時老闆帳號實際登入：首頁／清單／詳情的顯示，以及退單後被擋的四條路由。
後台用臨時工程帳號走 JSON-RPC：重複通報單次的錯誤訊息（IntegrityError → 可讀訊息）、
退單後唯讀、匯入工具會用的帶參數 action_suspend／action_resume。
⚠ 這裡不跑 JavaScript；畫面與按鈕要另外用瀏覽器點。
"""
import json
import re

import requests

BASE = 'http://localhost:8069'
cfg = json.load(open('/tmp/e2e_slip.json'))
P = cfg['project_id']
S = cfg['slips']
results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def csrf_of(html):
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html) or \
        re.search(r'csrf_token:\s*"([^"]+)"', html)
    return m.group(1) if m else ''


def login(sess, who):
    r = sess.get(BASE + '/web/login')
    r = sess.post(BASE + '/web/login', data={
        'login': cfg[who]['login'], 'password': cfg[who]['pw'],
        'csrf_token': csrf_of(r.text), 'redirect': ''})
    return r.status_code == 200 and '/web/login' not in r.url


# ================= 前台 =================
s = requests.Session()
check('前台老闆登入', login(s, 'portal'))

home = s.get(f'{BASE}/construction/{P}').text
check('首頁：停工中的通報單有出現（橙色卡）', 'data-state="suspended"' in home and '[E2E] 停工中' in home)
check('首頁：退單的通報單不出現', '[E2E] 合併退單' not in home and '[E2E] 退單' not in home)
check('首頁：同次重開的那張有出現', '[E2E] 同次重開' in home)

lst = s.get(f'{BASE}/construction/{P}/slips').text
check('清單：預設不列退單', '[E2E] 合併退單' not in lst and '[E2E] 退單<' not in lst)
check('清單：頁頂有「顯示已退單（N 張）」', re.search(r'顯示已退單（\s*\d+\s*張）', lst) is not None)
lst2 = s.get(f'{BASE}/construction/{P}/slips?show_cancelled=1').text
check('清單（顯示已退單）：退單出現、卡片標 cancelled',
      '[E2E] 合併退單' in lst2 and 'data-state="cancelled"' in lst2 and '隱藏已退單' in lst2)
check('清單（顯示已退單）：狀態文字「退單」', 'cy-slip-state cancelled' in lst2)

# 18.0.3.0.1 修正：前台帳號開「有明細」的詳情頁以前一律 403（明細的 is_manual_amount 要讀
# 契約工項，前台帳號沒有權限）。這裡用前台帳號直接驗，包含一張這次完全沒動過的舊單。
old = s.get(f'{BASE}/construction/{P}/slip/1')
check('前台帳號開沒動過的舊單（第 1 次，有明細）＝200', old.status_code == 200, old.status_code)
d953 = s.get(f'{BASE}/construction/{P}/slip/{S["953"]}').text
check('退單詳情：橫幅寫出原因', '本通報單已退單（合併）' in d953)
check('退單詳情：連到併入的那一通', f'/construction/{P}/slip/{S["952"]}' in d953)
check('退單詳情：沒有「新增檢查」', f'reservation-inspection/new?slip_id={S["953"]}' not in d953)
check('退單詳情：沒有上傳照片表單', f'/slip/{S["953"]}/photo/upload' not in d953)
check('退單詳情：沒有設定座標', 'sec_slip_geo' not in d953)
check('退單詳情：沒有核定／結案按鈕', f'/slip/{S["953"]}/confirm' not in d953
      and f'/slip/{S["953"]}/close' not in d953)

d952 = s.get(f'{BASE}/construction/{P}/slip/{S["952"]}').text
check('目標單詳情：「併入本單：第 953 次」', '併入本單' in d952 and '第 953 次' in d952)

d951 = s.get(f'{BASE}/construction/{P}/slip/{S["951"]}').text
check('停工詳情：停工橫幅與原因', '停工中（' in d951 and '機關通知暫停施工（E2E）' in d951)
check('停工詳情：老闆看得到「結案」（停工可直接結案）', f'/slip/{S["951"]}/close' in d951)
check('停工詳情：狀態徽章 suspended', 'cy-slip-state suspended' in d951)

# 退單後被擋的路由（介面已隱藏，這裡直接打）
tok = csrf_of(d951)
r = s.post(f'{BASE}/construction/{P}/slip/{S["953"]}/photo/upload',
           data={'csrf_token': tok}, files={'photos': ('x.png', b'\x89PNG\r\n', 'image/png')},
           allow_redirects=False)
check('退單：上傳照片被擋並導回', r.status_code in (302, 303)
      and 'error=slip_cancelled' in r.headers.get('Location', ''), r.headers.get('Location'))
r = s.post(f'{BASE}/construction/{P}/slip/{S["953"]}/set-geo',
           data={'csrf_token': tok, 'latitude': '25.1', 'longitude': '121.5'}, allow_redirects=False)
check('退單：設定座標被擋並導回', r.status_code in (302, 303)
      and 'error=slip_cancelled' in r.headers.get('Location', ''), r.headers.get('Location'))
r = s.get(f'{BASE}/construction/{P}/reservation-inspection/new?slip_id={S["953"]}', allow_redirects=False)
check('退單：新增自主檢查頁被擋並導回', r.status_code in (302, 303)
      and 'error=slip_cancelled' in r.headers.get('Location', ''), r.headers.get('Location'))
r = s.post(f'{BASE}/construction/reservation-inspection/create',
           data={'csrf_token': tok, 'slip_id': S['953'], 'sub_project_name': 'x'}, allow_redirects=False)
check('退單：建立自主檢查被擋並導回', r.status_code in (302, 303)
      and 'error=slip_cancelled' in r.headers.get('Location', ''), r.headers.get('Location'))
back = s.get(f'{BASE}/construction/{P}/slip/{S["953"]}?error=slip_cancelled').text
check('導回後顯示「已退單，無法執行」', '本通報單已退單，無法執行這個動作' in back)

ins = s.get(f'{BASE}/construction/{P}/reservation-inspections').text
check('自主檢查篩選 chips：沒有檢查的退單通報單不列', f'slip_id={S["953"]}' not in ins)
check('自主檢查篩選 chips：停工中的有列', f'slip_id={S["951"]}' in ins)

# ================= 後台 JSON-RPC =================
b = requests.Session()
check('後台帳號登入', login(b, 'back'))


def call(model, method, args, kwargs=None):
    r = b.post(f'{BASE}/web/dataset/call_kw/{model}/{method}', json={
        'jsonrpc': '2.0', 'method': 'call', 'id': 1,
        'params': {'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}}})
    data = r.json()
    if 'error' in data:
        return None, data['error']['data'].get('message', '')
    return data['result'], None


_, err = call('reservation.notification.slip', 'create', [{
    'project_id': P, 'slip_no': 952, 'location': '[E2E] 重複'}])
check('RPC：同次兩張未退單 → 可讀訊息（非原始 SQL 錯誤）',
      err and '同一工程的通報單次不可重複（已退單的通報單不算）' in err, err)
_, err = call('reservation.notification.slip', 'write', [[S['954']], {'location': '改'}])
check('RPC：退單後改地點被擋', err and '已退單的通報單不可修改' in err, err)
_, err = call('reservation.notification.slip', 'action_suspend', [[S['955']], '2020-01-01', '太早'])
check('RPC：停工日早於實際開工被擋', err and '實際開工日' in err, err)
res, err = call('reservation.notification.slip', 'action_open_suspend_wizard', [[S['955']]])
check('RPC：停工按鈕回傳精靈 action', res and res.get('res_model') == 'reservation.notification.slip.state.wizard', err)
print(json.dumps({'ok': True}))

ok = sum(1 for x in results if x[0])
for passed, name, detail in results:
    print(('PASS ' if passed else 'FAIL ') + name + (('  — ' + str(detail)[:150]) if detail and not passed else ''))
print(f'\n{ok}/{len(results)} passed')
