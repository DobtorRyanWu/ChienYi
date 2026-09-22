# -*- coding: utf-8 -*-
"""HTTP 端到端測試 —— 以臨時前台帳號實際登入前台走一遍（在容器內以 python3 執行）。"""
import json
import re

import requests

cfg = json.load(open('/tmp/e2e_helpdesk.json'))
BASE = 'http://localhost:8069'
s = requests.Session()
results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def csrf_of(html):
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html) or \
        re.search(r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)', html)
    return m.group(1) if m else None


r = s.get(BASE + '/web/login')
r = s.post(BASE + '/web/login', data={'login': cfg['login'], 'password': cfg['pw'],
                                      'csrf_token': csrf_of(r.text), 'redirect': ''})
check('前台帳號登入成功', r.status_code == 200 and '/web/login' not in r.url, r.url)

pid = cfg['project_id']
r = s.get(BASE + '/construction/%s' % pid)
check('工程首頁的抽屜有「意見回饋」真入口', r.status_code == 200
      and '/construction/feedback?from_project=%s' % pid in r.text
      and '意見回饋即將推出' not in r.text, r.status_code)

r = s.get(BASE + '/construction/feedback?from_project=%s' % pid)
check('意見回饋列表 200', r.status_code == 200 and '我要反映問題或提出需求' in r.text, r.status_code)
check('列表看不到別人的單', 'ZZ E2E 客服代登記' not in r.text)

r = s.get(BASE + '/construction/feedback/new?from_project=%s' % pid)
check('新增表單 200', r.status_code == 200 and 'name="category_id"' in r.text, r.status_code)
form = r.text
check('表單有 8 個類別選項', len(re.findall(r'data-ask-module="[01]"', form)) == 8)
check('只有 2 個類別會詢問發生功能', len(re.findall(r'data-ask-module="1"', form)) == 2)
module_block = form.split('id="cy_fb_module"')[1].split('</select>')[0]
check('發生功能選單不含後台專用項目（契約工項、估驗計價）',
      '契約管理' not in module_block and '估驗計價' not in module_block and '施工日誌' in module_block)
check('發生功能選單用前台名稱（工程進度／照片中心，不是後台的進度管理／照片管理）',
      '工程進度' in module_block and '進度管理' not in module_block
      and '照片中心' in module_block and '照片管理' not in module_block)
check('頁面載入前台 JS（portal_feedback）', 'web.assets_frontend' in form or '/web/assets/' in form)
token = csrf_of(form)

# 缺欄位 → 擋回
r = s.post(BASE + '/construction/feedback/create',
           data={'csrf_token': token, 'category_id': '', 'subject': '', 'description': '',
                 'from_project': pid}, allow_redirects=False)
check('缺類別／主旨／說明 → 擋回表單', r.status_code in (302, 303) and 'error=missing' in r.headers.get('Location', ''),
      r.headers.get('Location'))

# 正常送出：系統問題＋故意塞後台專用的「估驗計價」＋附件
cats = dict(re.findall(r'<option value="(\d+)"\s+data-ask-module="[01]">\s*([^<\s]+)', form))
cat_ids = {v: k for k, v in cats.items()}
mods = dict(re.findall(r'<option value="(\d+)">([^<]+)</option>', module_block))
payload = {
    'csrf_token': token, 'from_project': pid,
    'category_id': cat_ids.get('系統問題'),
    'functional_module_id': '__BACKEND__',
    'subject': 'ZZ E2E 施工日誌存檔錯誤', 'description': '按存檔後出現錯誤\n第二行<script>x</script>',
}
# 「估驗計價」是後台專用項目，前台頁面刻意不列 → id 由準備腳本從 DB 取來，模擬有人改 HTML 硬送
payload['functional_module_id'] = cfg['payment_module_id']
files = {'attachments': ('screen.png', b'\x89PNG fake', 'image/png')}
r = s.post(BASE + '/construction/feedback/create', data=payload, files=files, allow_redirects=False)
loc = r.headers.get('Location', '')
m = re.search(r'/construction/feedback/(\d+)\?message=created', loc)
check('送出成功並導到詳情頁', r.status_code in (302, 303) and m, (r.status_code, loc))
tid = int(m.group(1)) if m else 0

r = s.get(BASE + '/construction/feedback/%s' % tid)
check('詳情頁 200、顯示主旨與「待受理」', r.status_code == 200 and 'ZZ E2E 施工日誌存檔錯誤' in r.text
      and '已送出，待受理' in r.text, r.status_code)
check('詳情頁帶出工程名稱', cfg['project_name'] in r.text)
check('詳情頁說明中的 <script> 被跳脫', '<script>x</script>' not in r.text)
check('詳情頁有前台對話區', 'o_portal_chatter' in r.text)
check('詳情頁沒有洩漏內部欄位字樣', '關聯問題單' not in r.text and '負責客服' not in r.text)

# 第二張：操作疑問＋合法的前台功能
payload2 = dict(payload, category_id=cat_ids.get('操作疑問'), functional_module_id=mods and
                [k for k, v in mods.items() if v == '施工日誌'][0], subject='ZZ E2E 操作疑問')
r = s.post(BASE + '/construction/feedback/create', data=payload2, allow_redirects=False)
m2 = re.search(r'/construction/feedback/(\d+)', r.headers.get('Location', ''))
tid2 = int(m2.group(1)) if m2 else 0
check('第二張（操作疑問＋施工日誌）送出成功', tid2)

# 別人的單 → 導回列表
r = s.get(BASE + '/construction/feedback/%s' % cfg['other_ticket'], allow_redirects=False)
check('開別人的單 → 導回列表', r.status_code in (302, 303) and r.headers.get('Location', '').endswith('/construction/feedback'),
      (r.status_code, r.headers.get('Location')))

json.dump({'tid': tid, 'tid2': tid2}, open('/tmp/e2e_helpdesk_out.json', 'w'))
ok = sum(1 for x in results if x[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== HTTP %d/%d 通過 ====' % (ok, len(results)))
