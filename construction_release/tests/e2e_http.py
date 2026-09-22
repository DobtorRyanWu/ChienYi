# -*- coding: utf-8 -*-
"""HTTP 端到端：登入頁橫幅、前台公告跳窗、按「知道了」之後不再跳、回查頁（容器內 python3 執行）。

用法：先跑 e2e_setup.py（未發布，驗橫幅）→ 本檔 --stage before
     再跑 e2e_publish.py（發布）→ 本檔 --stage after
"""
import json
import re
import sys

import requests

cfg = json.load(open('/tmp/e2e_release.json'))
BASE = 'http://localhost:8069'
stage = sys.argv[sys.argv.index('--stage') + 1] if '--stage' in sys.argv else 'before'
results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def csrf_of(html):
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html) or \
        re.search(r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)', html)
    return m.group(1) if m else None


s = requests.Session()
r = s.get(BASE + '/web/login')
login_html = r.text

if stage == 'before':
    # 未登入的登入頁就要看得到維護橫幅
    check('登入頁 200', r.status_code == 200)
    check('登入頁有維護橫幅', 'cy-maint-banner' in login_html and '系統維護預告' in login_html)
    check('登入頁帶出預告內容', '屬正常現象' in login_html)
    check('還沒發布 → 登入頁沒有公告跳窗', 'cyReleaseAnnouncement' not in login_html)
else:
    check('發布後：登入頁沒有維護橫幅', 'cy-maint-banner' not in login_html)

r = s.post(BASE + '/web/login', data={'login': cfg['login'], 'password': cfg['pw'],
                                      'csrf_token': csrf_of(login_html), 'redirect': ''})
check('前台帳號登入成功', r.status_code == 200 and '/web/login' not in r.url, r.url)

home = s.get(BASE + '/construction')
check('前台首頁 200', home.status_code == 200, home.status_code)

if stage == 'before':
    check('前台頁面有維護橫幅', 'cy-maint-banner' in home.text)
    check('還沒發布 → 前台沒有公告跳窗', 'cyReleaseAnnouncement' not in home.text)
    # ⚠️ 這個測試帳號沒有任何可見工程，/construction 走的是「沒有工程」的版面（沒有抽屜）
    #    → 抽屜要在有頁首的頁面看（公告回查頁本身就有）
    drawer_page = s.get(BASE + '/construction/announcements')
    check('公告回查頁 200（未發布時也進得去）', drawer_page.status_code == 200, drawer_page.status_code)
    check('抽屜入口是更新公告、不是 v11.0 佔位',
          '/construction/announcements' in drawer_page.text
          and 'ChienYi Portal v11.0' not in drawer_page.text)
    check('還沒發布 → 回查頁沒有任何公告', '還沒有發布過更新公告' in drawer_page.text)
else:
    check('發布後：前台頁面沒有維護橫幅', 'cy-maint-banner' not in home.text)
    check('發布後：前台跳出公告', 'cyReleaseAnnouncement' in home.text)
    check('跳窗帶公告標題與版號',
          'ZZ 端到端測試用的公告內容' in home.text and cfg['version'] in home.text)
    check('跳窗不含模組版號', '18.0.1.8.1' not in home.text)

    page = s.get(BASE + '/construction/announcements')
    check('回查頁 200', page.status_code == 200, page.status_code)
    check('回查頁列出公告', 'ZZ 端到端測試用的公告內容' in page.text and cfg['version'] in page.text)
    check('回查頁不含模組版號與更新紀錄內容',
          '18.0.1.8.1' not in page.text and 'E2E 做法' not in page.text)

    # 按「知道了」
    ack = s.post(BASE + '/construction/announcements/read',
                 json={'jsonrpc': '2.0', 'method': 'call',
                       'params': {'release_ids': [cfg['release_id']]}})
    check('已讀 API 回 200', ack.status_code == 200, ack.status_code)
    check('已讀 API 回 true', ack.json().get('result') is True, ack.text[:120])

    home2 = s.get(BASE + '/construction')
    check('按過知道了 → 不再跳', 'cyReleaseAnnouncement' not in home2.text)
    page2 = s.get(BASE + '/construction/announcements')
    check('回查頁仍看得到（回查不受已讀影響）', 'ZZ 端到端測試用的公告內容' in page2.text)

ok = sum(1 for x in results if x[0])
for passed, name, detail in results:
    print('%s %s %s' % ('OK  ' if passed else 'FAIL', name, detail if not passed else ''))
print('==== %s: %d/%d ====' % (stage, ok, len(results)))
