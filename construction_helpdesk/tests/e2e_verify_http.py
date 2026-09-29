# -*- coding: utf-8 -*-
"""HTTP 端到端（2.0.0 客戶驗證）—— 客戶在前台按「仍有問題」「問題已解決」（在容器內以 python3 執行）。"""
import json
import re

import requests

cfg = json.load(open('/tmp/e2e_helpdesk.json'))
out = json.load(open('/tmp/e2e_helpdesk_out.json'))
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
s.post(BASE + '/web/login', data={'login': cfg['login'], 'password': cfg['pw'],
                                  'csrf_token': csrf_of(r.text), 'redirect': ''})
tid, tid2 = out['tid'], out['tid2']

r = s.get(BASE + '/construction/feedback/%s' % tid)
check('待客戶驗證：詳情頁顯示「請確認是否已解決」與兩個按鈕',
      r.status_code == 200 and '請確認是否已解決' in r.text and '問題已解決' in r.text and '仍有問題' in r.text,
      r.status_code)
check('按鈕表單送到 /verify 且有 CSRF', ('/construction/feedback/%s/verify' % tid) in r.text and csrf_of(r.text))
token = csrf_of(r.text)

r = s.post(BASE + '/construction/feedback/%s/verify' % tid, data={'csrf_token': token, 'result': 'not_resolved'},
           allow_redirects=False)
check('按「仍有問題」→ 導回詳情頁並提示', r.status_code in (302, 303)
      and 'message=not_resolved' in r.headers.get('Location', ''), r.headers.get('Location'))
r = s.get(BASE + '/construction/feedback/%s' % tid)
check('按「仍有問題」後：狀態變處理中、按鈕消失', '處理中' in r.text and '請確認是否已解決' not in r.text)

r = s.post(BASE + '/construction/feedback/%s/verify' % tid, data={'csrf_token': token, 'result': 'resolved'},
           allow_redirects=False)
r2 = s.get(BASE + '/construction/feedback/%s' % tid)
check('不在待客戶驗證時再送「問題已解決」→ 沒有作用（仍處理中）', '已結案' not in r2.text.split('對話紀錄')[0])

r = s.get(BASE + '/construction/feedback/%s' % tid2)
token2 = csrf_of(r.text)
r = s.post(BASE + '/construction/feedback/%s/verify' % tid2, data={'csrf_token': token2, 'result': 'resolved'},
           allow_redirects=False)
check('按「問題已解決」→ 導回詳情頁並提示', 'message=resolved' in r.headers.get('Location', ''),
      r.headers.get('Location'))
r = s.get(BASE + '/construction/feedback/%s?message=resolved' % tid2)
check('按「問題已解決」後：已結案、顯示感謝', '已結案' in r.text and '謝謝您的確認' in r.text)

r = s.post(BASE + '/construction/feedback/%s/verify' % cfg['other_ticket'],
           data={'csrf_token': token2, 'result': 'resolved'}, allow_redirects=False)
check('對別人的單送驗證 → 導回列表', r.headers.get('Location', '').endswith('/construction/feedback'),
      r.headers.get('Location'))
r = s.post(BASE + '/construction/feedback/%s/verify' % tid2, data={'result': 'resolved'}, allow_redirects=False)
check('沒有 CSRF → 被拒', r.status_code == 400, r.status_code)

ok = sum(1 for x in results if x[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== 客戶驗證 HTTP %d/%d 通過 ====' % (ok, len(results)))
