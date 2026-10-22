"""監票封存包（計畫 §10、§2.5、法規 §26「電磁資料妥適保存並採異地備份」）。

公告之後產生**一個** zip，只有這場的監票員下載得到。裡面是監票員在自己的電腦上
（只有 Python、沒有 Odoo）重算得出結論所需要的一切：

- `verify_core.py`：**夾帶原檔**。公式在線上與離線是同一份程式碼——
  寫兩遍的話，兩邊算出不同答案時沒有人知道哪一邊錯。
- `verify_digest.py`：呼叫腳本，跑完逐項印出 OK／FAIL 並以退出碼表示。
  它自己**不含任何公式**，全部轉呼叫 `verify_core`。
- `ballots_plain.csv` 與 `roster.csv` **沒有共用鍵**（D1）：兩份都在，
  但無法把某一張票對回某一個人——這是無記名投票的底線。

**zip 本體不掛在 `assoc.election` 上**，而是存進沒有任何 ACL 的 `assoc.election.archive`
（比照 `assoc.election.ballot`）。原本是 `assoc.election.archive_sealed` 這個
`groups=observer` 的 Binary 欄位，那樣有兩個洞，red-team 兩條都實跑複現過：

1. **群組不等於本場**。monitor rule 與 officer 的 `[(1,'=',1)]` 是 OR 的，
   身兼監票員與選務（或管理員）的人看得到**每一場**選舉；而欄位的 `groups=` 只問
   「你在不在監票員群組」，不問「你是不是這一場的監票員」。兩者相乘，
   A 場的監票員只要同時是選務，`read(['archive_sealed'])` 就拿得到 B 場的明文選票。
2. **`/web/content` 是第二條路**。`?model=assoc.election&field=archive_sealed` 直接把
   欄位串流出去，完全不經過這個模組的下載路由，也就不會留下稽核軌跡。

把欄位拿掉之後這兩條路都不存在了：模型沒有 ACL，任何非 superuser 的 ORM 讀取與
`/web/content` 都會被擋在 `check_access` 那一關，唯一的出口是
`/assoc/election/<id>/archive`——它先跑 `_check_observer()` 再 sudo，而且必寫軌跡。
"""

import base64
import csv
import hashlib
import io
import pathlib
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.assoc_base.tools import GUARD

from .. import verify_core
from ..tools import canonical_json, utc_iso
from .assoc_election import GUARD_STATE, OFFICES

VERIFY_SCRIPT = '''#!/usr/bin/env python3
"""離線驗算監票封存包。

用法：**先**在這個資料夾以外的地方、用完整路徑核對 verify_digest.py 與
verify_core.py 的指紋（與系統商公布的值比），**再**執行
python3 <這個資料夾的完整路徑>/verify_digest.py。理由印在輸出最後；
這支程式自己印不出可信的指紋，被換掉的版本也會把這段刪掉。

只用 Python 標準函式庫，不需要 Odoo。公式全部來自同一層的 verify_core.py，
那是線上系統跑的**同一份**檔案。
"""
import os
import sys

# **輸出編碼不得讓合法的封存包崩潰。** zh-TW Windows 的 locale 編碼是 cp950，
# 它編不出 ✔／✘／↳，也編不出不少人名用字。原本一碰到就 UnicodeEncodeError：
# 31 項全 OK 印完之後在鏈表那一行炸掉、退出碼 1——**合法的包被判成驗不過**
# （比漏報更糟），而且監票員永遠拿不到要跟紙本比對的那張表
# （第七輪 red-team 實測：`PYTHONIOENCODING=cp950 … > 結果.txt`，grep seq = 0）。
# `backslashreplace`：編不出來的字降級成跳脫寫法（例如 U+2714），其餘照常，絕不中斷。
try:
    sys.stdout.reconfigure(errors='backslashreplace')
    sys.stderr.reconfigure(errors='backslashreplace')
except (AttributeError, OSError, ValueError):
    pass        # stdout 被換成非 TextIOWrapper 的東西時就算了，不值得為此放棄驗算

# **這裡只 import 兩個模組**。每多 import 一個，就多一支模組在
# `sys.path` 還沒清乾淨的時候被解析——`types` 原本在這裡，只因為要拿
# `types.ModuleType`，而那個東西 `type(sys)` 就給得出來，不必冒這個險。
# （`os`／`sys` 在直譯器啟動時已在 `sys.modules`，遮蔽不了；但那是版本相依的
#   事實，不是設計保證，所以能少一個是一個。）

# ============================================================================
# **這一段必須在任何其他 import 之前**，而且順序不能動。
#
# 這支腳本在「被驗的那個資料夾」裡執行，而那個資料夾就是 `sys.path[0]`，
# 並且完全由封存包的提供者控制。所以在動任何東西之前要先把它拔掉：
#   ① 封存包裡多塞一支 `csv.py`，就會遮蔽掉下面 `import csv` 的標準庫，
#      攻擊者可以在裡面改寫 `builtins.print`（把 FAIL 換成 OK）與 `sys.exit`。
#   ② 保持 `verify_core.py` 位元組不變、另附一份標頭對齊的
#      `__pycache__/verify_core.cpython-3xx.pyc`，CPython 會直接用那份 bytecode
#      而不回讀 .py——**指紋對得上，跑的卻不是那份程式碼**。
# 兩種都實跑複現過：`log.csv`／`verify_core.py`／`verify_digest.py` 位元組全未動，
# 紙本鏈頭與兩個公布指紋全部吻合，30 項全 OK、退出碼 0，而當選人被對調。
#
# 前幾輪都在替「資料」上錨點；這一條繞過的是「讀資料的程式碼」。
# ============================================================================
# **兩邊都要 realpath**：CPython 放進 `sys.path[0]` 的是**解過符號連結**的路徑，
# 而 `abspath` 不解。只要呼叫路徑上有任何一段是符號連結，兩邊算出來的字串就不相等，
# 這個過濾式一個也濾不掉，封存包目錄原封不動留在 `sys.path` 上。
# 而 **macOS 的 `/tmp` 與 `$TMPDIR` 預設就是符號連結**（→ `/private/...`），
# 監票員把 zip 解到暫存或下載資料夾再執行就會中——這不是刁鑽案例，是常見路徑。
# 第七輪抗辯實跑：誠實包＋一支 `csv.py`，經符號連結路徑呼叫 → 31 OK／0 FAIL／
# 退出碼 0，而印出去的當選名單已被改寫（改 realpath 後同一個攻擊得到 FAIL）。
# **入口自己不可以是符號連結**（第七輪 red-team 實跑，critical）：`realpath` 會跟著
# 入口連結走，於是頂層放原版 verify_core.py、verify_digest.py 做成連結指向隱藏資料夾
# 裡的原版 verify_digest.py，`HERE` 就被搬到那個資料夾，讀的、exec 的是那裡的
# 公式檔——監票員事先對 `sha256sum` 兩個檔都吻合（連結會被跟著算），驗算照樣
# 33 OK、退出碼 0。這一道擋得住，因為那個攻擊必須讓**原版**腳本跑起來，而原版
# 會先執行這一行。訊息是程式常數（這裡還沒有消毒層）。
if os.path.islink(os.path.abspath(__file__)):
    print('FAIL no_symlinks  ——verify_digest.py 本身是符號連結（或捷徑），拒絕執行：'
          '它讀的會是連結指向的那個資料夾，而不是你核對過指紋的這一份。')
    print('【總判定】**沒有通過**。請向公會索取原始封存包，解壓到空資料夾再跑一次。')
    sys.exit(1)
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path[:] = [entry for entry in sys.path
               if os.path.realpath(entry or '.') != HERE]
sys.dont_write_bytecode = True      # 不產生 __pycache__，也就沒有那個藏身處

import csv          # noqa: E402  — 這幾行一定要在拔掉 sys.path[0] 之後
import hashlib      # noqa: E402
import json         # noqa: E402
import pathlib      # noqa: E402
import random       # noqa: E402

# ---- 讀**任何一個檔之前**：符號連結與檔案大小 ----
# `is_file()`、`read()`、`read_text()` 都跟著連結走，所以包裡一個
# `verify_core.py -> /dev/zero`（`unzip` 會建出來，Python 的 `zipfile` 不會）
# 會讓下面第一次讀檔變成無限位元：實跑 `MemoryError`、**stdout 零行**
# ——連一個 FAIL 都沒有，比「全 OK ＋工具壞了」更極端。
# 大小上限是同一件事的另一半：**不必用連結**也做得到，`verify_core.py` 換成
# 300 MB 的零位元組檔同樣炸，而 deflate 把 100 MB 的零壓成 102 KB，所以
# zip 的體積不構成防線（第三輪 skeptic 與 red-team 各自實跑）。
#
# **這一段原本排在 69 行之後**（在 `verify_core.py` 讀完並 exec 之後），
# 而它自己的註解寫著「在讀任何一個檔之前」——第二輪把它加進來時只看了
# 「`missing` 那道早退」，沒看更上面的公式檔載入（L3：寫成判準要掃一遍
# 全部同類）。這裡**不能用 `core.display`**，因為 `core` 還沒載入。
# 真封存包最大的檔是 result.pdf，數百 KB；五千人的名冊約 1 MB。原本是 64 MB，而 CSV
# 每一列都變成 dict，極短的列會把記憶體放大約四十倍：64 MB 的 roster.csv 峰值 2.7 GB、
# 跑 66 秒、期間零行輸出（第七輪 red-team 實跑）。8 MB 仍有八倍餘裕。
_MAX_FILE_BYTES = 8 * 1024 * 1024
REQUIRED = ('result.json', 'digests.txt', 'ballots_plain.csv', 'roster.csv', 'log.csv',
            'candidates.csv', 'receipts.csv', 'verify_core.py', 'verify_digest.py')
# **白名單，不是黑名單**：原本只要求「資料夾內容與指紋表一致」，而指紋表是
# 封存包提供者寫的——多塞一支 `csv.py` 並登記進去，`files_present` 就通過，
# 而且還會印出 `OK file:csv.py` 替那支惡意模組背書（實跑複現）。
# 封存包的檔案清單是固定的，多一個就是多一個。
ALLOWED = REQUIRED + ('result.pdf',)
# **只掃 `ALLOWED`——這支腳本只讀這幾個檔**。原本用 `rglob('*')` 掃整棵樹，
# 兩個獨立的問題同時出在那上面：
#   ① **假警報**：監票員把包解在自己的下載資料夾（資料夾裡有一支 100 MB 影片、
#      或一個捷徑），整份驗算就印兩行、零項檢查、退出碼 1，而訊息還把成因**斷言**成
#      「這是被改過的包」。`files_present` 的註腳自己寫著「多出來的若是你放的檔
#      （含驗算輸出），解壓到空資料夾再跑一次」——作者知道監票員會在髒資料夾裡跑
#      （L1⑨：假警報比漏報更糟；第四輪 skeptic 實跑三種情境都被判死）。
#   ② **終端機注入**：印出去的是**攻擊者控制的檔名**，而消毒用的 `print` 包裝層
#      還要 50 行之後才安裝。檔名裡放清屏與隱藏屬性的控制字元，就能在螢幕上只留下
#      一個偽造的「【總判定】通過」。第四輪 skeptic 與 red-team 各自端到端實跑過
#      （155 KB 的 zip 就夠——deflate 把 65 MB 的零壓成那麼小，正是下面那句
#      「體積不構成防線」）。第三輪把這一段提前時連 `core.display()` 一起拿掉了，
#      而 `verify_core.printable` 的 docstring 正記著「同一個坑被三個代理獨立
#      找到三次，所以才把 print 整個換掉」——這是第四次。
# 掃固定清單同時解掉兩個：印出去的名字**只可能來自這個常數**（注入在結構上不可能），
# 而監票員自己的檔不在清單裡，由 `files_present` 用那段帶指引的文字處理。
# **「清單外的檔不讀」要由讀檔的那一端保證，不是由這裡宣稱。** 第四輪收窄成固定
# 清單時這一句就寫在這裡，而逐檔指紋那個迴圈照樣對指紋表（提供者寫的）裡**每一個
# 鍵** `read_bytes()`：登記一個 `x.pdf -> /dev/stdin` 的連結就卡死、stdout 零行，
# 指 `/dev/zero` 就吃光記憶體（第五輪 skeptic 與 red-team 各自實跑）。那個迴圈
# 現在只讀 `ALLOWED` 裡的名字，所以這兩道早退蓋得住它會讀的每一個檔。
# 原本這裡另有一份 `_OWN_FILES`，與 `ALLOWED` 逐字相同、靠註解維持相等
# （第五輪 simplifier）——日後新增封存檔，加進 `REQUIRED` 就自動受這兩道保護。
# **不只連結：任何「不是一般檔案」的都拒讀**。具名管線（FIFO）`islink` 與 `isfile`
# 都是假，於是兩道都跳過它，而讀它會永遠卡住、stdout 零行（第六輪 skeptic 與
# red-team 各自實跑 `result.pdf`／`verify_core.py` 換成 FIFO）。
_links = [_name for _name in ALLOWED
          if os.path.islink(os.path.join(HERE, _name))
          or (os.path.exists(os.path.join(HERE, _name))
              and not os.path.isfile(os.path.join(HERE, _name)))]
if _links:
    print('FAIL no_symlinks  ——封存包自己的這幾個檔不是一般檔案（符號連結、管線、'
          '裝置或資料夾），拒絕讀取：' + '、'.join(_links))
    print('  系統產生的封存包只有一般檔案（跟著連結讀會讀到連結指向的東西，管線會卡住）。')
    print('  可能是解壓工具建出來的，也可能有人動過：請向公會索取原始檔，'
          '解壓到一個空資料夾再跑一次。')
    sys.exit(1)
_oversized = []
for _name in ALLOWED:
    _path = os.path.join(HERE, _name)
    if os.path.isfile(_path) and os.path.getsize(_path) > _MAX_FILE_BYTES:
        _oversized.append('%s（%.1f MB）' % (_name, os.path.getsize(_path) / 1048576.0))
if _oversized:
    print('FAIL file_size  ——封存包自己的這幾個檔異常巨大，拒絕讀取：'
          + '、'.join(_oversized))
    print('  真的封存包每個檔都在數百 KB 以內。壓縮檔的體積不構成防線'
          '（一大片零位元組壓完只有幾十 KB），所以這一道在讀檔之前先攔。')
    sys.exit(1)

# **公式檔用原始碼直接執行，不走 import**：`import` 會查 `__pycache__`，
# 而那份 .pyc 是攻擊者可以替換的。用 compile(原始位元組) 才保證「監票員事先用
# 作業系統工具對過指紋的那份 .py」就是「實際跑的程式碼」。
# （原本寫成「保證下面**印出去**給人比對的指紋」——那是錯的：指紋若由這個行程
# 自己印，被換掉的公式檔 exec 之後想印什麼都可以，第六輪 red-team 實跑。）
_core_path = os.path.join(HERE, 'verify_core.py')
try:
    with open(_core_path, 'rb') as _handle:
        _core_source = _handle.read()
except OSError as _error:
    print('FAIL data_shape  ——讀不到 verify_core.py：%s' % _error)
    sys.exit(1)
core = type(sys)('verify_core')         # type(sys) 就是 types.ModuleType
core.__file__ = _core_path
exec(compile(_core_source, 'verify_core.py', 'exec'), core.__dict__)

# ============================================================================
# **把 print 換成會消毒的包裝層。** 這一行是防「終端機注入」的主防線，
# 個別呼叫點的 `core.display()` 自此只剩截斷職責。
#
# 為什麼是結構性的而不是逐處補：同一個 bug 被三個不同的抗辯代理獨立找到三次
# （姓名／檔名／鏈表狀態欄——來龍去脈見 `verify_core.printable` 的 docstring）。
# 前兩次都是「補上漏掉的那一處」，於是第三次照樣發生；而用 grep 掃
# 「print 裡有沒有未消毒的資料」也抓不到第三處——因為取值寫在前一行。
# 唯一能讓第四次不發生的做法，是讓「忘記消毒」在結構上不可能。
_raw_print = print
# **包裝層與結尾段自己不可以是單點故障。** 主 try 外面會呼叫的公式只有這三支
# （每一次 print 經過 `printable`、結尾段的 `display` 與 `unique_transition`）；
# 包裡的 `verify_core.py` 換成缺其中一支的**合法舊版**，不是整份輸出零行，就是
# 結論處一段裸 traceback、鏈表與【總判定】都不印（第十輪 skeptic、第五輪 red-team、
# 第六輪 skeptic 各自實測過其中一支）。
# **缺了就直接早退**，與上面幾道早退同一個寫法，印出去的字串全是程式常數。
# 第五輪曾經改成「退回本地實作、主 try 一開始就判 data_shape」，結果結尾段拿著
# 還沒讀進來的預設值印出「這包沒有封箱紀錄」「沒有任何監票員」這類與事實相反的話，
# 而唯一值得留的鏈表在那個狀態下必然是空的（第六輪三個鏡頭都指到）。
# **這擋的是「版本錯配」，不是攻擊者**：公式檔一旦被 exec，它就能改 builtins、
# `sys.exit` 與這支腳本之後印的每一行（第六輪 red-team 實跑），所以公式檔與這支
# 腳本的指紋一定要在**執行之前**用作業系統的工具對過——見結尾段那一句。
_core_missing = [_name for _name in ('printable', 'display', 'unique_transition')
                 if not callable(getattr(core, _name, None))]
if _core_missing:
    _raw_print('FAIL data_shape  ——這包的 verify_core.py 少了 ' + '、'.join(_core_missing)
               + '：不是舊版就是被換過，公式檔不可採信，本腳本不往下驗。')
    _raw_print('【總判定】**沒有通過**。請向公會索取原始封存包，解壓到空資料夾再跑一次。')
    sys.exit(1)
_printable = core.printable


def print(*values, **kwargs):           # noqa: A001 — 故意遮蔽內建 print
    _raw_print(*(_printable(one) for one in values), **kwargs)


HERE = pathlib.Path(HERE)
# **作業系統雜訊檔忽略但點名**。`.DS_Store` 是 Finder **開過資料夾就會生**的，
# 在 Finder 裡看不見也刪不掉，而監票員不是工程師，唯一的操作方式就是點進去看。
# 把它判成 FAIL 的後果不是這一次驗不過，是**教會監票員「FAIL files_present 是正常的」**
# ——而真正的程式碼注入露出來的正好是同一行檢查（第七輪抗辯實測）。
# `.py`／`.pyc`／`__pycache__` **不在此列，維持硬 FAIL**：那是攻擊面，不是雜訊。
NOISE_NAMES = ('.DS_Store', 'Thumbs.db', 'desktop.ini')
NOISE_DIRS = ('__MACOSX',)


def is_os_noise(name):
    parts = pathlib.PurePath(name).parts
    return bool(parts) and (parts[-1] in NOISE_NAMES or parts[0] in NOISE_DIRS)
# 符號連結與檔案大小的早退**排在這個檔案的最上面**（`verify_core.py` 載入之前），
# 因為那裡才是「讀第一個檔」的地方。這一道（少一個檔就乾淨地 FAIL，不要變成
# 看不懂的 traceback）要在下面讀 `result.json`／`digests.txt` 之前。
missing = [name for name in REQUIRED if not (HERE / name).is_file()]
if missing:
    print('FAIL files_present  ——少了：' + '、'.join(missing))
    sys.exit(1)

try:
    # **`utf-8-sig`（與 CSV 一致）**：`digests.txt` 的副檔名是 .txt（記事本的
    # 預設關聯），又是唯一不在逐檔指紋表裡的檔——監票員自己開起來看、存檔
    # 就可能加上 BOM，而 `utf-8` 會讓整份驗算在印出任何一項之前就退出
    # （訊息還是英文的 `Unexpected UTF-8 BOM`）。乾淨的包被判死是假警報，
    # 而假警報比漏報更糟（L1⑨；第三輪 red-team 實跑）。
    result = json.loads((HERE / 'result.json').read_text(encoding='utf-8-sig'))
    digests = json.loads((HERE / 'digests.txt').read_text(encoding='utf-8-sig'))
except Exception as error:
    # **這裡要攔的是「所有讀不進來」，不是只有壞 JSON**（第四輪 red-team 實跑兩條）：
    #   ① `[` 疊 40000 層（80 KB）→ `json.loads` 丟 **RecursionError**，那是
    #      `RuntimeError` 的子類、不是 `ValueError` → **stdout 零行**、純 traceback。
    #   ② `result.json` 的權限位設成 000（zip 帶得動權限、`unzip` 照建）→
    #      `PermissionError`（OSError）→ 同樣零行。
    # 零行輸出是攻擊者最想要的結果：鏈表（唯一的包外錨點）、對帳數字、
    # 【總判定】一行都不印，而且不必動鏈（比第二輪 `observers` 那個 high 更徹底）。
    # 對照組就在上面 20 行：讀 `verify_core.py` 那一讀有 `except OSError`，
    # 同一個檔裡兩種寫法（M-A：工具自己壞掉的樣子不可以長得像「沒事」）。
    # **攔 `Exception` 而不是列舉型別**：這一讀之後的每一項都靠 `result`／`digests`，
    # 所以「讀不進來」一律是乾淨的 FAIL，列舉型別只會漏掉下一個沒想到的。
    # 標成 data_shape 而不是 files_present：檔案明明在，壞的是形狀。
    print('FAIL data_shape  ——result.json 或 digests.txt 讀不進來（不是合法的 JSON、'
          '或是讀取時出錯）：%s: %s' % (type(error).__name__, error))
    sys.exit(1)
if not isinstance(digests, dict) or not isinstance(result, dict):
    # 合法 JSON 但型別不對（例如整份是個陣列）→ 下面每一個 `.get()` 都會
    # AttributeError，而那是在大 try 之外，會變成純 traceback、一行檢查都不印
    print('FAIL data_shape  ——result.json 與 digests.txt 必須是 JSON 物件')
    sys.exit(1)
# 一律 `.get()`：鍵被刪掉時要印出 FAIL，不要變成看不懂的 traceback。
# （退出碼兩種情況都非 0，差別在監票員看不看得懂發生什麼事。）
uuid = digests.get('election_uuid') or ''
checks = []
notes = {}      # 檢查項 → 補充說明（FAIL 時要講清楚是哪個檔／哪一筆）
# ---- 第三種結果 N/A：「這條鏈沒有這個欄位」不等於「這個欄位被改壞了」----
# 每次有人往鏈的 payload 加一個新鍵，**所有在那之前凍結的選舉**重建封存包就會
# 開始 FAIL：基準取不到（`.get()` 回 None），比對永遠不成立。
# 2026-10-15 在 48 場已公告選舉的副本上實測：20 場因此退出碼 1，FAIL 的全是
# `draw`／`ballot_numbers`／`receipts_digest`／`roster_count_matches_freeze`
# ——那幾場的鏈一個位元都沒被動過，只是比 `draw_method`（當時 31/48 場有）與
# `receipts_digest`（29/48）這兩個欄位更早凍結名冊／開票。
#
# 這是 L1⑨ 的同一個形狀（「沒有東西要驗」不等於「證據被刪了」），只是這次缺的
# 不是候選人而是**欄位**。假警報比漏報更糟：它會教會監票員「FAIL 是正常的」。
#
# 判準：基準所在的那個鍵不存在時，這一項判**不適用**——
#   ①不計入失敗、不影響退出碼
#   ②印成 `N/A` 而**不是** `OK`（M-A：驗收工具必須分得出「通過」與「沒跑」）
#   ③逐項列進【程式驗不到的部分】，不讓「全部通過」替它背書
#
# **這條路買不買得到放行，取決於那個鍵在哪一筆。** payload 整個進雜湊公式，
# 拿掉一個鍵會改掉那一筆的 entry_hash 與其後每一筆；但這只有在**那一筆早於
# 監票員抄鏈頭的時點**才擋得住人。
#   - `counted` 的鍵（receipts_digest）在抄鏈頭**之後** → 重鑄鏈尾本來就做得到
#     （這支腳本在【程式驗不到的部分】自己講了），所以刪掉那個鍵就能把一個
#     FAIL 換成 N/A ＋退出碼 0。**能力沒有變大**（會重鑄的人本來就算得出
#     正確的 digest），但偵測訊號確實變弱了——所以下面對這一類鍵另外示警。
#   - `ballot_ready` 的鍵（roster_digest、ballot_numbers、draw_method、term_no）
#     在抄鏈頭之前。**但「之前」不等於「動不了」**——紙上那串是**封箱／開票／
#     公告**那一筆的雜湊，而凍結名冊那一筆在它之前就寫出來了：攻擊者在「凍結
#     名冊 → 封箱」這整段（含投票進行中）改 seq1 的 payload 並重鑄當下已存在的
#     每一筆，之後封箱那一筆是**線上系統自己**疊在被改過的鏈上算出來的，監票員
#     抄到的就是重鑄後的值，逐字吻合（第二輪 red-team 實跑三種基準：原封不動
#     → FAIL；刪掉基準鍵 → N/A；**把基準偽造成自洽的值 → 零 FAIL 零 N/A、
#     退出碼 0、「每一項都 OK」**）。
#     所以 N/A 這條路**沒有擴大能力**，理由不是「鏈頭擋得住」，而是**同樣的
#     能力下偽造一個自洽的值比刪鍵更乾淨**（偽造連一行 N/A 都不留）。
#     （第一版的註解把「鏈頭擋得住」寫成對全部的鍵都成立，那是錯的；第二版
#     只修了 counted 那一側，ballot_ready 這一側照樣寫成「動它一定對不上」。）
#
# **下一個往鏈上加鍵的人要過的判別式**：這個鍵的正確值，攻擊者在不碰紙上那串
# 的前提下**算得出來嗎**？算得出來（像上面每一個摘要）→ 缺鍵只買得到向後相容，
# 走 N/A 沒問題。算不出來（例如綁到包外錨點的值）→ 缺席就是竄改訊號，
# 要進 `POST_ANCHOR_KEYS` 級別的示警，不可以靜靜判 N/A。
class NotApplicable:
    """第三種結果。**刻意不能被當成真假值用。**

    寫成 `NA = 'n/a'` 時這個類別不存在，而非空字串天生 truthy——於是
    `all(ok for …)` 與 `if not ok` 都「剛好」把不適用算成通過，判斷是對的
    但理由是巧合：哪天有人把哨兵換成 `''`、`0` 或 `None`，同一行就會反過來
    把舊世代的包全部判成失敗，而且不會有任何東西變紅
    （2026-10-15 的 mutation 第 17 條實測：拿掉明確比對，19 條裡唯一存活的
    就是它——等價 mutant 正是在說「這段程式碼撐不住它宣稱的那件事」）。

    讓 `__bool__` 直接拋例外，「忘記處理不適用」就變成當場炸掉的程式錯誤，
    而不是一個靜靜說謊的 OK（M-A：驗收工具必須分得出「通過」與「沒跑」）。
    """

    def __init__(self, missing):
        # 鏈上缺的那個鍵名（或「A／B」＝幾代寫法都缺）。**跟著結果本身走**：
        # 原本另外維護一個 `missing_basis` dict，於是「判了不適用」與「登記缺了
        # 什麼」是兩句分開的語句，少寫一句就會在列印時 KeyError。
        self.missing = missing

    def __bool__(self):
        raise TypeError('「不適用」不可以當真假值用，'
                        '請寫 `isinstance(ok, NotApplicable)` 明確比對')


# 線上 `assoc.election.term_no` 是 Odoo 的 Integer＝PostgreSQL int4
TERM_NO_MAX = 2147483647
POST_ANCHOR_KEYS = {
    # 鍵名 → 為什麼它缺席的證據力比較弱
    'receipts_digest':
        '這個欄位記在**開票**那一筆，在你抄鏈頭之後——重鑄鏈尾的人可以把它'
        '拿掉而紙上那串完全不變。缺席不等於舊世代。',
}
# 某些檢查一旦不適用，會連帶讓**另一道已經被刪掉的防線**失去唯一的靠山。
# 這些話要印出來，否則「通過」會替一個它撐不起來的結論背書。
# **這張表只在「判了 N/A」時才印得出來。** 第三輪 skeptic 實查：正式庫副本的
# 62 筆 `ballot_ready` payload **100% 都有 `roster_count`**（`git log -S` 顯示
# 它自模組第一個 commit 就在），所以下面這一句掛的「兩代基準都缺」分支，
# 在**那個庫**裡到不了（L5①：這個否定性斷言的範圍只有那一個副本，更古老的
# 世代仍可能存在，所以句子留著當縱深）。
# **真正會發生的是「退回只比筆數」那一支，而它印的是 OK** ——那個降級的揭露
# 放在【程式驗不到的部分】（無條件印），不在這裡。
# **姓名那一項不在這裡**（第五輪 simplifier F1、skeptic R1）：它不適用時姓名有沒有
# 錨點，取決於鏈上有沒有 `roster_digest`——有的話姓名早就被逐列摘要釘住，
# 印「包裡沒有任何東西證明得了」是假警報；沒有的話，那段話在【程式驗不到的部分】
# 已經由 `names_pinned` 那一把尺決定要不要印。兩處各用一把尺量同一件事，
# 同一份輸出就會互相矛盾。
NA_SIDE_EFFECTS = {
    'roster_count_matches_freeze':
        '這一項不適用時（鏈上連 roster_count 都沒有），roster.csv 就只剩開票'
        '那一筆綁著——「名冊凍結後有沒有偷加選舉人」本包證明不了。',
}


# 下面兩支**只算出結果，不自己登記**。原本是一支 `check_against_chain(name, …)`
# 自己呼叫 `checks.append`，那讓 `tools/check_verify_script.py` 的第三項檢查
# （「每一項具名檢查都是主 try 的直線碼」）掃不到——它只掃主 try 的直接子節點，
# 而 append 跑到 module 層的函式體裡去了。當時的修法是再寫一道靜態檢查去守那個
# 洞（約 50 行）；第二輪 simplifier 指出正解是**把 append 搬回主 try**，讓那個
# 不變量由構造成立，不必再寫一道檢查去保護它。
#
# **`payload` 整個是空的時候不可以判不適用**：`ready`／`anchor` 會因為鏈上那一筆
# 重複或根本不存在而變成 {}（`unique_transition` 回 None），那是竄改訊號——
# 第五輪抗辯就是往鏈尾追加一筆 ballot_ready 把基準打空，讓兩項「證明承辦沒挑
# 號次」的檢查一起恆真的。只有「那一筆真的在、只是沒有這個欄位」才算舊世代。
# （第二輪 skeptic 另外查證：那個攻擊今天會先被 `chain_complete` 擋下來，所以
# 這道前置條件是**縱深**，不是唯一的靠山——原本的 docstring 把它寫成唯一靠山。）
def needs_all(payload, keys, ok):
    """這一項要鏈上**每一個**鍵才算得出來；少一個就不適用。

    少一個而照算下去，式子常常退化成恆真——`draw` 少了候選人名單這個**分母**，
    `numbered == expected_numbered` 就變成 `0 == 0`（第二輪 red-team 實跑：
    刪掉 `ballot_numbers` 與 `candidates`、留下 `draw_method` 與監票員紙上那組
    骰子值 → `OK draw` 而什麼都沒驗）。恆真的 OK 比 FAIL 糟，因為它印的是通過
    （L1①）。

    **空的 payload 一律 False，在這裡判、不在呼叫端判**：原本只做「缺鍵 → N/A」，
    「空 payload → FAIL」靠三個呼叫端各寫一次 `bool(ready) and`——同一個陷阱在
    三處各寫一次正確用法＝還沒修好，只是這次記得（L9；第五輪 simplifier）。
    """
    if not payload:
        return False
    missing = [key for key in keys if key not in payload]
    if missing:
        return NotApplicable('／'.join(missing))
    return ok
def dicts_in(value):
    """主 try **外面**要逐筆 `.get()` 的清單：濾掉不是 dict 的元素。

    結尾那一整段（含鏈表——整份驗算**唯一的包外錨點**）在主 try 外面，
    在那裡炸掉，畫面上留下的是「三十幾行 OK ＋ 一份名單 ＋ 一段 traceback」，
    而鏈表與【總判定】一行都不印。攻擊者拿它換的不是「全綠」（退出碼仍是 1），
    是把「FAIL ＋ 看得懂的報告」換成「全 OK ＋ 工具壞了」——監票員手上那串紙
    從此無處可對（第二輪 red-team 實跑：把 open 那一筆的 `observers` 改成
    字串／`["alice"]`／`[[1,2]]`，三種都是 AttributeError）。
    `offices` 在第五輪補過同樣的防線，`observers` 與 `ranking` 沒拿到
    ——L9：同一個陷阱在兩個地方各寫一次正確用法，就是還沒修好。
    **主 try 裡沒有任何一項檢查碰過的值**（`observers` 正是）尤其要走這一支：
    那種值的型別錯誤不會先被 `data_shape` 收走。
    """
    return [one for one in value if isinstance(one, dict)] if isinstance(value, list) else []


# 下面的 try 若在半路炸掉，結尾那幾段人工指引還是要印得出來（不能再吐一次 traceback），
# 所以先給定預設值
# （`result` 與 `digests` 在上面已經讀進來了，**不要**放進這一行——
#   那會把真正的內容覆寫成空的，而且每一項檢查都還是會照常印出 OK／FAIL，
#   看起來像「資料有問題」而不是「工具寫錯了」）
# **結尾的人工指引用到的每一個名字都要在這裡**：漏一個就會在 try 外面
# 再炸一次，而那正是整份驗算唯一的包外錨點印不出來的原因
# （加同票亂數那一段時漏了 `anchor`，測試當場抓到）
entries, offices, ready, seq_of, anchor = [], {}, {}, {}, {}
# 結尾段會用它判斷要不要印「這個世代只比了筆數」那一段（② 會抓漏）
roster_basis = ''
# 當選人的姓名有沒有包內錨點——【程式驗不到的部分】與鏈表**共用這一把尺**。
# `identity_unanchored`＝「凍結那一筆讀到了、而且上面沒有逐列摘要」，結尾段據此斷言
# 鏈上缺什麼。兩個都預設 False：主 try 沒算到時，既不替沒驗到的姓名背書，也不斷言
# 鏈上缺什麼（原本用 None 第三態記這件事，第七輪 simplifier 指出兩態就等價）。
names_pinned = identity_unanchored = False
transitions, boundary_ties, noise, facts = [], [], [], {}
sealed, seal_seq, seal_voids, seal_problem = None, None, [], None
# 註：這份清單已經漏過三次（加同票亂數時漏 anchor、加監票員名單時漏 transitions）。
# 每次在結尾那幾段引用新名字，就要回來這裡加一個——
# 守著這件事的是 `test_verify_script_reports_broken_shapes_as_a_clean_fail`，
# 它每次都抓到了。

# **形狀壞掉也要印得出人看得懂的 FAIL**。原本只擋 JSON 解不開，
# 但「files 是字串」「result.json 是陣列」「log.csv 少一欄」這些都會直接
# 吐 traceback、一行 FAIL 都沒有（抗辯實跑五種）。監票員多半不是工程師，
# traceback 與「驗不過」在他眼裡是同一件事，卻分不出是資料被動過還是工具壞了。
try:


    def rows(name):
        """讀一個 CSV。每一格都先還原 `csv_cell` 的防公式前綴——摘要是用原值算的。"""
        with (HERE / name).open(encoding='utf-8-sig', newline='') as handle:
            return [{key: core.csv_uncell(value) for key, value in row.items()}
                    for row in csv.DictReader(handle)]


    # ---- 稽核鏈：整包裡**唯一**自帶錨點的東西 ----
    # 它從 sha256(uuid) 起算、每一筆串上一筆，而鏈頭在投票當天就被監票員抄在紙上。
    # 所以下面每一項摘要都跟**鏈裡的那一份**比，不跟 digests.txt 比：
    # digests.txt 與 CSV 是同一個人放進同一個壓縮檔的，拿它們互相比對
    # 只證明得了「這包自己前後一致」，證明不了內容沒被換過。
    parsed = [{'seq': int(row['seq']), 'ts': row['ts'], 'actor_uid': int(row['actor_uid']),
               'action': row['action'], 'payload': json.loads(row['payload']),
               'prev_hash': row['prev_hash'], 'hash': row['entry_hash']} for row in rows('log.csv')]
    # **payload 必須是 JSON 物件**。把某一格改成合法的 `[]`，上面的檢查都照常印，
    # 但結尾那張鏈表的 `entry['payload'].get('to')` 在大 try **外面** AttributeError，
    # 鏈表印到一半吐 traceback——整份驗算唯一的包外錨點又一次被截斷
    # （第七輪 red-team 實測）。先驗形狀再綁定，壞的話 `entries` 維持空清單，
    # 結尾那幾段照樣印得出來。
    if not all(isinstance(entry['payload'], dict) for entry in parsed):
        raise ValueError('log.csv 有一筆 payload 不是 JSON 物件')
    entries = parsed
    bad_seq = core.verify_chain(entries, uuid)
    checks.append(('chain', bad_seq is None))
    checks.append(('chain_head', bool(entries)
                   and entries[-1]['hash'] == digests.get('chain_head')))

    # **每個狀態只能出現一次，而且 published 必須是最後一筆。**
    # 原本這裡用 `setdefault` 取第一筆畫 ✔、卻用「最後一筆覆寫」當基準，
    # 兩邊不對稱——於是在 published 之後**追加**一筆 counted，基準就整個易主，
    # 而監票員抄的舊鏈頭照樣成立、照樣標 ✔（第四輪兩個抗辯代理各自實跑複現，
    # 而且不必手改 zip：線上流程自己就能產出這樣一包）。
    transitions = core.chain_transitions(entries)
    anchor = core.unique_transition(transitions, 'counted') or {}
    ready = core.unique_transition(transitions, 'ballot_ready') or {}
    # `published` 這個變數原本只用來做 `bool(published)`，而那一句被
    # 「所有狀態唯一」＋「最後一筆必須是 published」蘊含（published 被砍→最後一筆
    # 那兩句紅；出現兩次→唯一性紅；之後追加→最後一筆紅）。唯一新放行的情況是
    # 「published 的 payload 被清成 {}」，而那個 payload 線上離線都沒有人讀。
    for seq, state, _payload in transitions:
        seq_of.setdefault(state, seq)

    # 鏈驗得過**不代表鏈是完整的**：把最後幾筆整個砍掉，剩下的仍然首尾相接、
    # 每一筆的雜湊也都算得出來（`verify_chain` 是從頭往後串的）。唯一會露餡的是
    # 鏈頭，而鏈頭寫在 digests.txt 裡——那是竄改者自己放的。
    # 所以這裡另外要求「該有的狀態都還在，而且順序正確」：一包已公告的封存檔，
    # 鏈上一定要先有 counted 再有 published。
    # 鏈要「完整」有五個條件，缺一個就等於錨點保護不了結果：
    #   ①四個必要狀態都在（含 `closed`——票匭的承諾記在那一筆）
    #   ②**每一個狀態都只出現一次**，不只是那四個。原本只驗四個，於是鏈上可以有
    #     兩筆 `open`；而結尾那段監票員名單取的是 `unique_transition(…, 'open')`，
    #     重複就回 None → 整段退化成「（沒有任何監票員）」而所有檢查照樣全綠
    #     （第八輪 skeptic）。線上的 `_verify_chain` 驗的是**全部**狀態，
    #     離線比線上鬆本身就是一個洞：系統擋得住的東西，包驗不出來。
    #   ③順序是 ballot_ready → closed → counted → published
    #   ④**published 是整條鏈的最後一筆**——它之後還有東西，就代表有人往後接過
    states = [state for _seq, state, _payload in transitions]
    checks.append(('chain_complete', bool(anchor) and bool(ready)
                   # 問「關票那一筆在不在」，不是問「它的 payload 非不非空」：
                   # 這支腳本**不讀** closed 的 payload（第九輪撤回票匭摘要之後），
                   # 用 `bool(payload)` 當代理的話，payload 被清空會變成假警報，
                   # 而它保護的 `seq_of['closed']` KeyError 一樣擋得住（第十輪 simplifier）。
                   and 'closed' in seq_of and len(set(states)) == len(states)
                   and seq_of['ballot_ready'] < seq_of['closed']
                   # `< seq_of['published']` 原本也在這裡，但它被
                   # 「published 唯一」＋「最後一筆是 published」＋seq 連續蘊含
                   # （published 必然是最大的 seq）。留著會讓人以為多了一道。
                   and seq_of['closed'] < seq_of['counted']
                   # **最後一筆必須是真的 state_change**：只看 payload 的標籤的話，
                   # 追加一筆 `action='reissue'` 但 payload 寫 `{'to':'published'}`
                   # 就滿足了（第五輪兩個代理各自實跑：26 項全綠，✔ 表格還會把它
                   # 印成第二筆 published）。
                   # `bool(entries)` 原本也在這裡，但 `bool(anchor)` 已經蘊含它
                   # （anchor 非空 ⟹ transitions 非空 ⟹ entries 非空），
                   # 而 `and` 短路也保證了 entries[-1] 不會 IndexError
                   and entries[-1]['action'] == 'state_change'
                   and entries[-1]['payload'].get('to') == 'published'))

    ballot_rows = [(row['office'], [int(x) for x in row['choices'].split() if x],
                    row['status'], row['invalid_reason'])
                   for row in rows('ballots_plain.csv')]
    ballots = [(office, choices, status) for office, choices, status, _reason in ballot_rows]
    # 第八輪曾經在**關票那一筆**比對票匭摘要，第九輪撤回（那個摘要看不到在途選票，
    # 於是「票被刪掉」會被它認證成「票匭沒被動過」）。第十輪改成比對**封箱**那一筆——
    # 封箱是關票之後的另一個請求，快照看得到每一張票，所以它承諾的是相等而不是子集。
    # 詳見 `assoc_election.py::action_seal_ballots` 的長註解。
    recomputed_ballots = core.ballots_digest(uuid, ballots)
    checks.append(('ballots_digest', recomputed_ballots == anchor.get('ballots_digest')))
    # **封箱那一筆是關票到開票之間唯一的錨點。**
    # `sealed` 為 None 代表這包是加封箱之前產的（或有人塞了兩筆）——
    # 前者是合法的舊資料，不可以判 FAIL（26 場既有的誠實選舉就是這樣被第八輪判死的），
    # 所以這一項**只在有封箱紀錄時才驗**，沒有就在下面的指引裡明講「這包沒有封箱」。
    # **這一項一定要無條件出現。** 寫成 `if sealed is not None:` 的話，沒有封箱的包
    # 會讓它整項消失——而 `all()` 對少掉的項目無話可說（工具當場擋下來了）。
    # 所以：沒有封箱時這一項通過（沒有東西與它矛盾），而「這包沒有封箱」
    # 改在【程式驗不到的部分】明講——那才是「限制」該待的地方。
    # 「現行是哪一筆封箱」用**同一支**公式算（`verify_core.live_seal`），
    # 線上的 `action_count` 與這裡共用——兩邊各寫一遍的話，對同一條鏈算出不同的
    # 基準時沒有人知道哪邊錯（第四輪的教訓）。作廢紀錄的合法性也在那支裡驗。
    seal_seq, sealed, seal_voids, seal_problem = core.live_seal(entries)
    seal_ok = seal_problem is None
    if seal_ok and sealed is None and seal_voids and seq_of.get('counted') is not None:
        # 作廢過、卻沒有現行封箱，而票已經開了——線上走不出這個組合
        # （`action_count` 要求有現行封箱）。所以它只能是有人繞過系統寫出來的。
        seal_ok = False
        seal_problem = '有 %d 筆作廢紀錄卻沒有現行封箱，而票已經開了' % len(seal_voids)
    if seal_ok and sealed is not None:
        seal_ok = (recomputed_ballots == sealed.get('ballots_digest')
                   and seq_of.get('closed') is not None and seq_of.get('counted') is not None
                   and seq_of['closed'] < seal_seq < seq_of['counted'])
    checks.append(('ballots_sealed_matches', seal_ok))
    notes['ballots_sealed_matches'] = seal_problem or (
        '這包沒有封箱紀錄' if sealed is None else
        '現行封箱在 seq %s，關票 seq %s、開票 seq %s；作廢紀錄 %d 筆' % (
            seal_seq, seq_of.get('closed'), seq_of.get('counted'), len(seal_voids)))

    roster_rows = rows('roster.csv')
    roster_lines = [core.roster_line(row['member_id'], row['member_no'], row['name'],
                                     row['state'], row['voted_at']) for row in roster_rows]
    checks.append(('roster_digest',
                   core.roster_digest(roster_lines) == anchor.get('roster_final_digest')))

    # ---- 筆數對帳：**摘要只證明「這份資料沒被改」，不證明「沒有被加進來」** ----
    # 雜湊是對最終狀態算的，所以名冊凍結後偷加選舉人、或把沒來的人改成「已投票」
    # 再補幾張票，每一個摘要都會重新算得漂漂亮亮——26 項全綠、退出碼 0、當選人被換掉
    # （第五輪抗辯實跑兩個變體都成功）。拆穿它需要的數字就躺在鏈上，原本一個都沒讀。
    #
    # 名冊在 `action_ready` 建立之後就不再增減（voter 的 unlink 有守衛），
    # 所以凍結那一筆的 `roster_count` 與 `roster_digest` 是可以直接拿來對的：
    # 把每一列的狀態正規化回 `eligible`、投票時間清空，就該重算出凍結當下的那個摘要。
    frozen_roster = core.roster_digest([
        core.roster_line(row['member_id'], row['member_no'], row['name'], 'eligible', '')
        for row in roster_rows])
    # 有 `roster_digest` 時只比摘要就夠了：它是對 **list** 排序後 join 的，
    # 多一列、少一列、重複一列都會改變它，所以筆數是被蘊含的。
    # 檢查項的名字保留 `count`，因為 FAIL 時最可能的原因就是有人被加進來。
    #
    # **基準有兩代，新的缺席要退回舊的。** 上面那段註解自己說「`roster_count`
    # 與 `roster_digest` 是可以直接拿來對的」，而這一項原本只綁 `roster_digest`
    # ——於是「有 count、沒有 digest」那個世代（正式庫今天有 3 份已公告的封存包
    # 是這樣）整項判不適用，而基準就躺在同一筆 payload 裡沒人讀
    # （第二輪 skeptic 實跑：那種包上凍結後偷加一位選舉人，32 OK ＋ 2 N/A ＋
    # 退出碼 0）。退回舊鍵之後這一項**變弱了**——只比得出筆數，比不出有沒有
    # 改名——所以要在對帳數字那一區說出用的是哪一代基準，降級而不說的話，
    # 下一個人會以為它仍然蓋得住改名。
    roster_basis = next((key for key in ('roster_digest', 'roster_count') if key in ready), '')
    if roster_basis == 'roster_digest':
        roster_ok = frozen_roster == ready['roster_digest']
    elif roster_basis == 'roster_count':
        roster_ok = len(roster_rows) == ready['roster_count']
    elif ready:
        # 兩代基準都沒有（而凍結那一筆在鏈上）＝舊世代，判不適用。
        # **這裡不需要另一支 helper**：`roster_basis == ''` 與
        # 「ready 非空且兩代鍵都不在」是同一件事，呼叫端已經算過了
        # （第三輪 simplifier：那支 `needs_any` 只有這一個呼叫端，
        # 而它的 docstring 與上面這段註解是同一份證據寫兩次）。
        roster_ok = NotApplicable('roster_digest／roster_count')
    else:
        # `ready` 被整個打空：那是竄改訊號，不是舊世代——留 False（FAIL）
        roster_ok = False
    checks.append(('roster_count_matches_freeze', roster_ok))

    # 「投了幾票」有三個獨立的來源，三個必須一致：
    #   ①鏈上 counted 那一筆記的 `voted` ②名冊裡標 voted 的列 ③收據碼的張數
    # 收據碼與 `state='voted'` 是同一句 UPDATE 寫的，是硬不變量；
    # 變體二（把沒來的人改成已投票再補票）躲得過列數檢查，就是這一項擋下來的。
    voted_rows = [row for row in roster_rows if row['state'] == 'voted']
    receipt_rows = rows('receipts.csv')
    checks.append(('voted_count_agrees',
                   anchor.get('voted') == len(voted_rows) == len(receipt_rows)))
    checks.append(('result_digest', core.result_digest(result) == anchor.get('result_digest')))

    # digests.txt 只是方便閱讀的摘要本，它說的話必須與鏈一致（不一致＝有人動過）。
    # `chain_length` 是這裡唯一能獨立顯示「鏈被砍尾」的欄位，比對成本一行；
    # 其餘欄位（選舉名稱、公會、各階段時間）原本全部無錨點也無檢查——
    # 實跑六欄全改仍 30 項全綠（第六輪抗辯）。時間欄位在鏈上每一筆的 `ts` 裡，
    # 這裡至少要求 digests.txt 說的鏈長與實際筆數一致。
    checks.append(('digests_match_chain', bool(anchor)
                   and digests.get('chain_length') == len(entries)
                   and all(digests.get(key) == anchor.get(key)
                           for key in ('ballots_digest', 'roster_final_digest',
                                       'result_digest'))))

    # ---- 重點票：依同一組規則重算每個職位的得票 ----
    electable = {int(row['member_id']) for row in roster_rows}
    offices = result.get('offices') or {}
    # 每個投票的人在每個職位各投一張，所以**每個職位**的張數都等於投票人數。
    # 只驗總和是不夠的：刪掉 N 張監事票、補進 N 張理事票，總數不變就過了，
    # 而當選人已經被換掉（第六輪抗辯實跑）。拆穿它的數字就在 result.json 裡
    # （`valid_ballots`／`invalid_ballots`，經 result_digest 綁在鏈上），
    # 而這支腳本原本從頭到尾沒出現過 `valid_ballots` 這個字串。
    voted_total = anchor.get('voted') or 0
    per_office, tallied = {}, {}
    for office, _choices, status, reason in ballot_rows:
        per_office[office] = per_office.get(office, 0) + 1
        bucket = tallied.setdefault(office, {'valid': 0, 'invalid': 0, 'reasons': {}})
        if status == 'valid':
            bucket['valid'] += 1
        else:
            bucket['invalid'] += 1
            bucket['reasons'][reason] = bucket['reasons'].get(reason, 0) + 1
    ballots_ok = bool(offices) and set(per_office) <= set(offices)
    for office, data in sorted(offices.items()):
        counted = tallied.get(office) or {'valid': 0, 'invalid': 0, 'reasons': {}}
        # **分項也要對，不能只對總和**：把理事的「有效 4／無效 0」改成「2／2」，
        # 總和不變、`ballots_plain.csv` 一張票都沒動，原本 30/30 全綠（第七輪實跑）。
        # 而這兩個數字經 `_report_offices` 印進**結果公告 PDF**，腳本印給監票員的
        # 名單又不含票數統計——人工比對那一關也照不到。
        # 每一列的 `status`／`invalid_reason` 由下面的 `ballot_status` 綁回規則重算，
        # 所以這裡拿 CSV 當基準是安全的：兩段接起來就是「PDF 上的統計 ← CSV ← 規則」。
        # 原本這裡還有一句 `有效＋無效 == 投票人數`。加了下面的分項比對之後，
        # 那一句與第一句成了**同一個命題**（分項相等 ⟹ 兩邊的總和相等），
        # 於是拆開的 mutation 兩條都 STILL GREEN——不是兩道防線各自沒人守，
        # 是多寫了一道。留著會讓下一個人以為這裡有兩層保護。
        if (per_office.get(office, 0) != voted_total
                or (data.get('valid_ballots') or 0) != counted['valid']
                or (data.get('invalid_ballots') or 0) != counted['invalid']
                or dict(data.get('invalid_reasons') or {}) != counted['reasons']):
            ballots_ok = False
    checks.append(('ballot_count_agrees', ballots_ok))
    # **只印 facts 沒有的那一項。** 投票人數／各職位張數／從選票重數的有效無效
    # 這三個，下面的【拿這幾個數字去跟你在現場看到的對】已經**無條件**印出來了，
    # FAIL 時同一組數字印兩遍（第十輪 simplifier）。
    notes['ballot_count_agrees'] = 'result.json 自己記的有效／無效：%s' % (
        {office: (data.get('valid_ballots') or 0, data.get('invalid_ballots') or 0)
         for office, data in sorted(offices.items())})
    recount = {}
    status_ok = True
    for office, choices, status, reason in ballot_rows:
        data = offices.get(office) or {}
        computed = core.recheck_ballot(choices, data.get('max_marks', 0), electable) or ''
        # `invalid_reason` 進不了 `ballot_hash`（改公式會讓已公告的摘要全部作廢），
        # 改用重算把它綁住：同一組規則算出來的結論必須與檔案裡寫的一模一樣。
        # 少了這一項，光改這一欄就能讓「廢票」看起來是別的原因而全部驗得過。
        if computed != reason or status != ('invalid' if computed else 'valid'):
            status_ok = False
        if computed or status != 'valid':
            continue
        for member_id in choices:
            recount[(office, member_id)] = recount.get((office, member_id), 0) + 1
    checks.append(('ballot_status', status_ok))

    # **兩個方向都要比**：只驗「表上的人票數對」的話，把某個當選人整列刪掉照樣驗得過。
    # 反向那一句（有票的人都要出現在名次表上）同時也蓋掉了「名次表被整個清空」——
    # 原本這裡還有一個 `bool(ranked)` 前置條件，隔離後的 mutation 證明它抓不到任何
    # 反向那句抓不到的東西（而「名次表是空的」另外也會讓下面的 `ranking` 紅），
    # 留著只是讓人以為多了一道防線。
    ranked = [(office, row) for office, data in sorted(offices.items())
              for row in (data.get('ranking') or [])]
    ranked_keys = {(office, row['member_id']) for office, row in ranked}
    checks.append(('recount',
                   all(recount.get((office, row['member_id']), 0) == row['votes']
                       for office, row in ranked)
                   and all(key in ranked_keys for key, votes in recount.items() if votes)))

    # ---- §6 的「選舉屆次」：綁回凍結名冊那一筆 ----
    # 選罷辦法 §6 I 要求選舉票（**紙本與電子票都一樣**）載明團體名稱、選舉屆次、
    # 職稱及年月日。這四樣裡只有屆次推不出來——團體名稱在 result.json、職稱就是
    # office、年月日是大會日——所以它必須自己進鏈，而且要進**凍結名冊**那一筆：
    # 在第一張票發出去之前（L1⑫：承諾的時點比承諾的內容更要緊）。
    #
    # **這一項能證明的只有「鏈上登記的屆次是這個數字」**，證明不了「印在票上的
    # 就是它」——那要監票員拿一張實體票（或投票頁截圖）對下面印出來的數字。
    # 所以權威輸出那一段一定要把它印出來，不可以只在這裡判個真假就算了。
    term_no = ready.get('term_no')
    # `isinstance(True, int)` 是真，所以 bool 要單獨排除：payload 被改成
    # `"term_no": true` 時不可以當成「第 1 屆」放行。
    # **上界也要驗**：線上那個欄位是 int4（最大 2147483647），而 JSON 寫得出
    # 10**100——超出範圍的值不可能來自系統，只可能來自竄改，驗算不可以
    # 照單全收還把它印出來。
    # **算一次就好**：這個判準原本在這裡與對帳區那一列各寫一份逐字相同的
    # 運算式，而 mutant 只打在這一份——對帳區那一份改壞（例如拿掉 bool
    # 排除）不會有任何東西變紅（L9；第三輪 simplifier）。
    term_no_ok = (isinstance(term_no, int) and not isinstance(term_no, bool)
                  and 0 < term_no <= TERM_NO_MAX)
    checks.append(('term_no', needs_all(ready, ('term_no',), term_no_ok)))

    # ---- 號次抽籤：用同一條公式重算，證明承辦沒有挑號次 ----
    # 凍結名冊當下入鏈的號次，必須與 candidates.csv 上的一致（把檔案綁回鏈）。
    # payload 被改壞時要記成 FAIL，不要在印出任何一項之前就崩潰
    numbers = {}
    numbers_parsed = True
    try:
        for item in ready.get('ballot_numbers') or []:
            office, number, member_no = item.split(':', 2)
            numbers.setdefault(office, []).append((int(number), member_no))
    except (ValueError, AttributeError, TypeError):
        # **不要塞一筆假資料當旗標**：下面兩項都是 `all()`，
        # 空的那一筆會讓它們雙雙變成恆真——那正是這支腳本一開始的毛病
        numbers, numbers_parsed = {}, False
    # 這個檔下面 `candidates_match_result` 還要再用一次，解析一次就好
    candidate_rows = rows('candidates.csv')
    by_key = {(row['office'], row['member_no']): row['ballot_number']
              for row in candidate_rows}
    # `ready` 若因為重複的 ballot_ready 而變成 {}，這一項不可以靜靜地恆真
    # （空集合的 all() 為真——第五輪抗辯實測 `OK ballot_numbers` 與 `OK draw:none`
    #  在該情境下同時出現，兩項「證明承辦沒挑號次」的檢查一起消失）
    checks.append(('ballot_numbers', needs_all(
        ready, ('ballot_numbers',),
        numbers_parsed and all(
            by_key.get((office, member_no)) == str(number)
            for office, pairs in numbers.items()
            for number, member_no in pairs))))

    method = ready.get('draw_method', 'none')
    # **「沒有東西要驗」不等於「證據被刪了」。** 零登記候選人、全靠名單外得票的場次
    # 是合法的（§6 明文），而 `action_ready` 只要填了亂數就回報 `draw_method='system'`、
    # `ballot_numbers=[]`——於是系統自己產出的**真**封存包會被自己的驗算判 FAIL、
    # 退出碼 1（第五輪抗辯實跑）。這與第四輪為姓名那項修掉的是同一個洞，
    # 當時沒有把判準掃到這一項來（L3 的教訓，又犯一次）。
    # 判準改成「鏈上說有幾位候選人，就要有幾個號次」，而不是「號次不能是空的」。
    expected_numbered = len(ready.get('candidates') or [])
    numbered = sum(len(pairs) for pairs in numbers.values())
    draw_ok = numbers_parsed and numbered == expected_numbered
    for office, pairs in numbers.items():
        if method == 'system':
            # 種子只由公開資訊組成：uuid、職位、監票員擲出的亂數、候選人編號
            member_nos = sorted(no for _number, no in pairs)
            order = list(member_nos)
            random.Random(core.draw_seed(
                uuid, office, ready.get('draw_entropy', ''), member_nos)).shuffle(order)
            if {no: i for i, no in enumerate(order, start=1)} != {no: n for n, no in pairs}:
                draw_ok = False
        elif method == 'manual':
            # 實體抽籤：只能驗每個職位 1..n 不重複
            if sorted(n for n, _no in pairs) != list(range(1, len(pairs) + 1)):
                draw_ok = False
    # 檢查項的名字裡帶 method：`ready` 被打空時 method 會從 system 退回 none，
    # 連**檢查項的名稱都變了**，以名稱斷言的測試看不到它消失——所以名字固定、
    # method 放進 notes
    # **兩個基準鍵**：`draw_method` 說號次是誰決定的，`candidates` 是號次的
    # **分母**。少了分母，下面那個等式退化成 `0 == 0` 恆真，而 `draw` 照印 OK
    # （第二輪 red-team 實跑）——所以缺任一個都判不適用，不是只看 method。
    checks.append(('draw', needs_all(ready, ('draw_method', 'candidates'), draw_ok)))
    notes['draw'] = '抽籤方式：%s（鏈上登記 %d 位候選人、包裡有 %d 個號次）' % (
        method, expected_numbered, numbered)

    # ---- 名額與候選人名單：綁回 `ballot_ready`（**紙本錨點之前**的那一筆）----
    # 凍結名冊發生在投票開始之前，監票員抄鏈頭的時機一定在它之後。
    # **但「之前」不等於「動不了」**：紙上那串是封箱／開票／公告那一筆，攻擊者
    # 在「凍結名冊 → 封箱」整段改掉 seq1 再重鑄當下已存在的每一筆，之後封箱
    # 那一筆是線上系統自己疊上去算的，監票員抄到的就是重鑄後的值（第二輪
    # red-team 實跑）。這一段原本寫「這是整包裡少數『連重造鏈的人也動不了』
    # 的東西」——那是假的，而且同一句話還印在 `MEANING` 裡給監票員看
    # （第三輪 simplifier 查到同一份輸出一段說動不了、一段說動得了）。
    # 它買到的是「**攻擊者要在投票開始之前就決定好結果**」，不是「動不了」。
    # 原本 `ranking` 用 `result.json` 自己的 seats 重算——又是拿被驗物件當基準：
    # 抗辯實跑只把 `director.seats` 由 3 改成 4 再重鑄 counted/published 兩筆，
    # 1 票的人就從候補變當選，而所有檢查全綠（同一包裡 seq1 白紙黑字寫著 seats: 3）。
    frozen = ready.get('offices') or {}
    seats_ok = bool(frozen) and set(frozen) == set(offices)
    for office, data in sorted(offices.items()):
        spec = frozen.get(office) or {}
        if (data.get('seats') != spec.get('seats')
                or data.get('alternates') != spec.get('alternates')
                or data.get('max_marks') != spec.get('max_marks')):
            seats_ok = False
    checks.append(('seats_match_frozen_roster', seats_ok))

    # 當選人的**姓名與編號**要對得上名冊。`roster.csv` 已被 `roster_final_digest`
    # 綁在鏈上，而且涵蓋**每一位選舉人**——包含名單外得票（write-in）的當選人，
    # 那種人不在 `ballot_ready` 的候選人清單裡，只綁凍結名冊管不到他改名。
    roster_names = {int(row['member_id']): (row['member_no'], row['name'])
                    for row in roster_rows}
    names_ok = True
    for office, data in sorted(offices.items()):
        for row in (data.get('ranking') or []):
            if roster_names.get(row['member_id']) != (str(row['member_no']), row['name']):
                names_ok = False
    checks.append(('names_match_roster', names_ok))

    # ---- 當選名單的姓名要綁回**凍結名冊那一筆的候選人清單** ----
    # 這道比對第八輪被刪掉，理由是「`roster_count_matches_freeze` 已經把
    # roster.csv 的摘要對回 `ballot_ready` 的 `roster_digest`，而姓名是
    # `roster_line` 的一個欄位，所以任何改名都必然讓那一項紅」。
    #
    # **那個理由在第二輪被我自己弄假了**：我給 `roster_count_matches_freeze`
    # 加了世代退路（鏈上沒有 `roster_digest` 時退回只比 `roster_count` 的筆數），
    # 於是在那個世代「改名」不再讓它紅——而第三輪 skeptic 與 red-team **各自
    # 獨立實跑**同一個攻擊：在 count 世代的真封存包上對調兩位候選人的姓名、
    # 只重鑄 counted 與 published 兩筆（封箱那一筆雜湊逐位元不變，而腳本自己
    # 就是叫監票員抄那一個）→ **33 OK／0 FAIL／0 N/A、退出碼 0**，印出去的
    # 當選名單換人。
    # 這是 L1⑲ 的教科書形狀：「刪掉 A，因為 B 撐得住」，而 B 後來被改動了，
    # 沒有人回頭複查那個理由。
    #
    # 基準用 `candidates`（`office:member_no:member_name`）而不是 roster：
    # 它在**凍結名冊那一筆**、與 `roster_digest` 是兩個獨立的鍵，所以 count
    # 世代也有基準可比。它只蓋得住候選人（當選人必然是候選人），蓋不住
    # 非候選人選舉人的姓名——那個殘餘在【程式驗不到的部分】講。
    # **`candidates` 有兩個格式世代**（實測正式庫副本的 48 份包）：
    #   新：`office:member_no:member_name`（三段，有姓名基準）
    #   舊：`office:member_no`（兩段，**沒有姓名**）
    # 把兩段當成「格式壞掉」就是假警報——第一版這樣寫，實跑讓一份原本全綠的
    # 正式封存包（id 2）變成 FAIL。舊格式不是錯誤，它是「這一項沒有基準」，
    # 那正是 N/A 該用的地方（L1⑨：假警報比漏報更糟）。
    # **比對不要解析，用整串比對**（第四輪 red-team／skeptic 各自實跑同一條）：
    # 原本寫 `item.split(':', 2)`，而 `member_no` 是 `fields.Char`、**沒有任何
    # 格式驗證**，一個含半形冒號的編號（凍結之前就寫得進去）會讓
    # `director:N:001:張建宏` 切成 `('director','N','001:張建宏')`，查表的鍵是
    # `('director','N:001')` → 對不上 → 靜靜落到「名單外得票」而姓名完全不比，
    # 而 `len(parts) == 3` 所以「格式壞掉要大聲失敗」一次都不會觸發。
    # 整串比對沒有這個歧義：鏈上那一串長什麼樣，就拿一模一樣的字串去比。
    raw_candidates = ready.get('candidates') or []
    frozen_list = set(one for one in raw_candidates if isinstance(one, str))
    # 非字串的列：線上那個 f-string 永遠寫不出來 ⇒ 確定是有人動過 seq1。
    broken_rows = len(raw_candidates) - len(
        [one for one in raw_candidates if isinstance(one, str)])
    # **世代與歸屬都不靠數冒號判**（第五輪 skeptic 實跑兩條）：`member_no`
    # 可以含冒號，於是舊格式的 `director:B:002` 被數成三段 → 合法舊包判混世代
    # FAIL；`startswith('director:A:')` 又會把 `A:1` 那一位的列算到 `A` 頭上
    # → 誠實的包判「姓名不符」。改成**以名次表上的人為準**：每一列歸給以它開頭
    # 的**最長**那個 `職位:會員編號`，等於它＝舊格式，後面接冒號＝有姓名。
    # 名次表上的人是從票匭重算的（`recount`／`ranking`），不是這一項自己說了算。
    stems = {'%s:%s' % (office, row['member_no'])
             for office, data in offices.items() for row in (data.get('ranking') or [])}
    owner = {}
    for one in frozen_list:
        heads = [stem for stem in stems if one == stem or one.startswith(stem + ':')]
        if heads:
            owner[one] = max(heads, key=len)
    legacy_rows = sum(1 for one, stem in owner.items() if one == stem)
    with_names = len(owner) - legacy_rows
    # 連一個冒號都沒有的列湊不出「職位:編號」，那個 f-string 寫不出它
    other_rows = sum(1 for one in frozen_list if ':' not in one)
    frozen_name_hits = 0
    legacy_hits = 0
    renamed = []
    write_ins = []
    for office, data in sorted(offices.items()):
        for row in (data.get('ranking') or []):
            stem = '%s:%s' % (office, row['member_no'])
            mine = {one for one, head in owner.items() if head == stem}
            if ('%s:%s' % (stem, row['name'])) in mine:
                frozen_name_hits += 1
            elif stem in mine:
                # **舊格式不是「名單外得票」**：那個人有登記，只是鏈上沒有他的
                # 姓名。混在一起算會讓對帳區說謊（第一版這樣寫，實測把 5 位
                # 舊格式候選人印成「名單外得票」）。
                legacy_hits += 1
            elif mine:
                # 編號對得上、姓名對不上 ⇒ 這就是要抓的那件事。
                renamed.append('%s/%s' % (office, row['member_no']))
            else:
                # 真的名單外得票（write-in）：沒有凍結基準，不能判 FAIL
                # ——第八輪 skeptic F7 踩過（整列刪掉原本零 FAIL）。
                write_ins.append('%s/%s' % (office, row['member_no']))
    # **當選的是哪一位會員（編號與姓名）有沒有包內錨點**，【程式驗不到的部分】與
    # 鏈表都看這一個值。**只有一條路**：`roster_digest` 釘住 roster.csv 的每一列
    # （`roster_line` 同時含 member_id、編號與姓名），`names_match_roster` 再把名次表
    # 綁回 roster.csv——兩項都要**真的通過**，不是只看鍵在不在。
    # 票匭與名次是用 member_id 算的，而 member_id ↔（編號, 姓名）這層對應只有
    # `roster_digest` 釘得住。凍結那一筆的 `candidates` 只記編號與姓名、沒有
    # member_id，所以「名次表上每一位都逐字比到」只證明「顯示出來的配對當時有登記」，
    # 不證明那些票是那個人的：第五輪把它當成第二條路，第六輪 skeptic 與 red-team
    # 各自實跑——只有 `roster_count` 的包，封箱後把兩位候選人的編號與姓名**整組**
    # 對調，33 OK、退出碼 0，鏈表還印「都釘住」。而刪掉 `roster_digest` 一個鍵只會
    # 退回比筆數（印 OK，不是 N/A），也不必事先知道結果（再更早的一版是從
    # 「姓名那一項是 True」推論，True 可以是零比對的空真，第五輪 skeptic）。
    # 日後要讓第二條路成立，`candidates` 要帶 member_id（residual #11 的新鍵）。
    names_pinned = (roster_basis == 'roster_digest' and roster_ok is True
                    and names_ok is True)
    # `bool(ready)`：凍結那一筆重複或缺少時 `roster_basis` 是空的，而那**不是**「鏈上沒有
    # 逐列摘要」——那一筆有兩份（第七輪 skeptic）。那種包由對帳區說「基準是空的」。
    identity_unanchored = bool(ready) and roster_basis != 'roster_digest'
    # **判定的優先序被第四輪抓到是錯的**：原本「整場舊格式 → N/A」排在
    # 「格式壞掉 → FAIL」前面，於是把 `candidates` 整段換成 9 筆垃圾
    # （筆數不變，`draw` 的分母還保住）得到 0 FAIL ／ N/A ／退出碼 0 ／總判定通過,
    # 而 N/A 的理由印「鏈上缺的欄位」——鍵在、壞的是內容，那句話與事實不符。
    # 確定的竄改訊號一律優先於「沒有基準」。
    # 「清單格式異常」只算一次：對帳區那一列也用它（原本抄了一份，第五輪只改了
    # 其中一份——L9，第六輪 simplifier）。
    format_broken = bool(broken_rows or other_rows or (with_names and legacy_rows))
    if format_broken or renamed:
        # 混世代（有些列有姓名、有些沒有）**線上系統產不出來**：那個 f-string
        # 一定給三段。所以混世代＝有人逐列動過 seq1，不是世代差異
        # （第三輪把它寫成「照比有姓名的那幾列」，而逐列降級正好是攻擊者要的
        # 靜音開關——第四輪 red-team 實跑：只把目標那一列改成兩段式就印 OK）。
        names_result = False
    elif frozen_name_hits or names_pinned:
        # **零比對但姓名已被 `roster_digest` 釘住時判 OK，不判 N/A**（使用者 2026-10-20
        # 裁決）：那時名冊摘要與名次表兩項都通過，結論有撐住它的東西，不是空真。
        # 印 N/A 的話，新世代「零登記候選人、全靠名單外得票」的合法場次會得到「通過，
        # 但有 1 項不適用」與「可能是舊世代或被拿掉」的說明，而鏈表同時說「都釘住」——
        # 同一份輸出互相矛盾（第六、七輪 simplifier）。代價是這一項在新世代的意思從
        # 「姓名對凍結清單」變成「姓名有錨點」；舊世代（沒有 roster_digest）照樣 N/A。
        names_result = True
    else:
        # **一位都沒逐字比到＝這一項什麼都沒驗到**，印 OK 會讓「通過」替一個它
        # 撐不起來的結論背書（M-A）。原本只在「候選人清單非空、而且整份都是
        # 兩段式」時判 N/A，於是零登記候選人（§6 合法）、全是名單外得票、
        # 編號含冒號的舊格式三種形狀都印 **OK**——第五輪 skeptic 在三種形狀上
        # 各自實跑換名：33 OK、退出碼 0，鏈表還印「當選名單都釘住」。
        # `needs_all` 照樣把「基準被打空」判 FAIL、把「沒有這個鍵」判 N/A。
        names_result = needs_all(ready, ('candidates',), NotApplicable(
            'candidates 裡的姓名欄位' if legacy_hits
            else 'candidates 裡可逐字比對的候選人（上榜者都不在清單裡）'))
    checks.append(('names_match_frozen_candidates', names_result))
    # 覆蓋範圍的**數字**無條件印在對帳區（見下面 `facts`）；**是誰**放這裡
    notes['names_match_frozen_candidates'] = (
        '編號對得上但姓名不符：%s／名單外得票（無凍結基準）：%s'
        % ('、'.join(core.display(one, 24) for one in sorted(renamed)) or '無',
           '、'.join(core.display(one, 24) for one in sorted(write_ins)) or '無'))

    # ---- 誰當選：**從票數重推**，不是照抄 result.json ----
    # 只重算票數是不夠的：票數對、名次算錯（程式 bug 或有人動手腳）照樣全綠。
    # 抗辯代理實跑過——把線上的排名反轉，1 票的人當選、4 票的人落選，20 項全 OK。
    # 排名需要的東西全都在**鏈上**：得票由 CSV 重算、名額取自凍結名冊那一筆、
    # 兩個抽籤種子取自開票那一筆。`result.json` 在這一段只提供「有誰參選」。
    ranking_ok = bool(offices)
    recomputed_ties = []        # 重算出來的跨界同票群組，下面拿去跟鏈上那份對帳
    for office, data in sorted(offices.items()):
        ranking_rows = data.get('ranking') or []
        # **`dict` 在本該唯一的序列上會無聲吃掉重複列**（天生取最後一筆）。
        # 複製一列、票數不變但把 `rank`／`result` 改成當選，下面的 `ranking`
        # 驗不到那一列，而結尾印出去的當選名單會多一個人。
        # 目前另外被 `result_digest` 擋著，但這與第四輪修掉的
        # 「在本該唯一的序列上用 dict 取值」是同一個形狀，該輪的判準沒掃到這裡。
        if len({row['member_id'] for row in ranking_rows}) != len(ranking_rows):
            ranking_ok = False
        rows_by_id = {row['member_id']: row for row in ranking_rows}
        if not rows_by_id:
            # **席位從缺是合法結果**（§6：零登記候選人＋全體投空白）。
            # 線上完全放行、照樣產包，而原本這裡一律判 FAIL——系統自己產的
            # 合法封存包被自己的驗算說「被動過」（第六輪抗辯造了三場實跑）。
            # 這與已修的「零登記但有 write-in 得票」是同一個 L3 教訓的姊妹案例。
            # 要驗的是「沒有人有票」，不是「名次表不能空」。
            if any(votes for (this_office, _mid), votes in recount.items()
                   if this_office == office):
                ranking_ok = False
            continue
        # entrants 依會員編號排序：sorted 是穩定的，這個初始順序決定同票而不需抽籤時誰在前
        entrants = sorted(rows_by_id, key=lambda mid: str(rows_by_id[mid]['member_no']))
        tally = {mid: recount.get((office, mid), 0) for mid in rows_by_id}
        # 名額取自**凍結名冊那一筆**（上面驗過它與 result.json 一致），
        # 不是取自 result.json 自己——後者是被驗的物件
        spec = frozen.get(office) or {}
        seats, alternates = spec.get('seats', 0), spec.get('alternates', 0)
        # **抽籤的兩個種子也要取自鏈上那一筆**，不能取自 `result.json`。
        # 名額已經改綁凍結名冊了，但種子還留在被驗的物件裡——而種子決定的正是
        # 「跨越當選／候補界線的同票，誰當選」。第七輪抗辯造了一場 4/4/2/2 票的
        # 真選舉，實跑兩個各自獨立的變體：
        #   ① 改 `result['tie_entropy']` ② **只**改 `result['ballots_digest']`
        # 兩者都 30/30 OK、退出碼 0、紙本錨點吻合，而理事第 3 名（當選）與
        # 第 4 名（候補）被對調。②證明了「只比 tie_entropy」的單行修法不夠：
        # `ballots_digest` 是第二個種子輸入，在這支腳本裡除了當種子沒有別的用途。
        ranked, office_ties = core.rank_office(
            entrants, tally, seats, alternates,
            anchor.get('ballots_digest', ''), office, anchor.get('tie_entropy', ''))
        recomputed_ties.extend(office_ties)
        for rank, member_id in enumerate(ranked, start=1):
            row = rows_by_id[member_id]
            expected = core.outcome_for(rank, tally[member_id], seats, alternates)
            if row['rank'] != rank or row['result'] != expected:
                ranking_ok = False
    checks.append(('ranking', ranking_ok))

    # `result.json` 自己也帶著一份種子。上面排名已經改用鏈上那一份，所以這裡
    # 不是為了排名，而是要讓「包裡寫的」與「鏈上釘的」不一致本身成為一項 FAIL——
    # 否則兩者可以靜靜地各說各話，而監票員看到的是包裡那一份。
    # （重算的 CSV 摘要對鏈上那一份，由上面的 `ballots_digest` 守著，三方因此閉合。）
    checks.append(('seeds_match_chain',
                   result.get('ballots_digest') == anchor.get('ballots_digest')
                   and (result.get('tie_entropy') or '') == (anchor.get('tie_entropy') or '')))

    # ---- 「這場到底有沒有抽過籤」要由重算決定，不能由 payload 單方面宣告 ----
    # `rank_office` 每次都算得出誰跟誰同票、跨不跨界線，但回傳值原本被丟掉，
    # 底下印給監票員的那一段完全信任鏈上 payload。把 counted payload 的
    # `boundary_ties` 清成 `[]`，腳本就印「本場沒有跨越界線的同票，沒有抽籤」，
    # 而且同票亂數整段包在 `if ties:` 裡 → **連那組要跟骰子對的值都不會印出來**。
    # 第五輪好不容易把兩組亂數都搬上大螢幕與驗算，一個欄位就把它整段關掉。
    def tie_shape(tie):
        """同票群組的可比較形狀（組間與組內順序都無關）。"""
        tie = tie if isinstance(tie, dict) else {}
        return (str(tie.get('office')), str(tie.get('votes')),
                tuple(sorted(str(one) for one in (tie.get('member_ids') or []))))

    claimed_ties = anchor.get('boundary_ties')
    checks.append(('boundary_ties_match_recount',
                   isinstance(claimed_ties, list)
                   and sorted(map(tie_shape, claimed_ties))
                   == sorted(map(tie_shape, recomputed_ties))))
    notes['boundary_ties_match_recount'] = '鏈上記 %s 組跨界同票，從票數重算得 %s 組' % (
        len(claimed_ties) if isinstance(claimed_ties, list) else '（型別不對）',
        len(recomputed_ties))
    boundary_ties = recomputed_ties      # 結尾那段印的是重算值，不是 payload

    # **全綠的時候才最需要看到這幾個數字。** 它們原本只放在 `notes` 裡，
    # 而 `notes` 只在 FAIL 時印——於是監票員在「一切正常」的情況下，
    # 看不到任何一個他能拿去跟現場記憶對帳的數字（第八輪 skeptic）。
    # 這很要命：票匭與名冊的竄改**在包內是自洽的**（投票人數、收據碼張數、
    # 名冊已投列數在開票那一刻全是同一張表的下游，改一張表三者一起變一致），
    # 所以包外的人腦記憶是唯一的獨立來源——而封存包裡沒有報到資料。
    facts.update({
        '名冊人數': len(roster_rows),
        # `anchor` 被打空（開票那一筆重複或缺少）時 `.get()` 是 None，而
        # `core.display(None, 60)` 回空字串 → 這一列印成**標籤加空白**，與
        # 「版面壞了」分不出來。今天一定伴隨 `voted_count_agrees` FAIL，所以是
        # 說不出話而不是說謊，但它與年月日那一列是同一個形狀（第四輪 skeptic）。
        '投票人數（鏈上記的）': ('（開票那一筆在鏈上重複或缺少，取不到這個數字）'
                                 if anchor.get('voted') is None else anchor['voted']),
        '名冊標為已投票的列數': len(voted_rows),
        '收據碼張數': len(receipt_rows),
        '各職位選票張數': dict(sorted(per_office.items())),
        '各職位有效／無效': {office: (one['valid'], one['invalid'])
                             for office, one in sorted(tallied.items())},
        # 名冊比對用的是**哪一代基準**要說出來：退回 `roster_count` 時這一項
        # 只比得出筆數、比不出有沒有改名（見上面那一段）。不說的話，一個
        # 「OK roster_count_matches_freeze」在兩種強度下長得一模一樣。
        # **不要替缺席編成因**：「舊世代」是這支腳本驗證不了的事——攻擊者刪掉
        # `roster_digest` 同樣做得到，而那正好是他希望監票員讀到的解釋
        # （與 N/A 註腳、封箱缺席兩處被判死過的安撫語同一形狀，第三輪
        # skeptic 與 red-team 各自指到這裡是第三次重犯）。
        # 「比不出改名」也講得不夠：**增一刪一**（筆數不變的替換）同樣比不出。
        '名冊基準（鏈上記的）': (
            '（凍結名冊那一筆在鏈上重複或缺少，整個基準是空的）' if not ready
            else {
                'roster_digest': '每一列的摘要（改名、增減、替換都抓得到）',
                # **這一列只講名冊這一項自己比得出什麼**，當選人的姓名有沒有錨點
                # 交給【程式驗不到的部分】那一段（它看 `names_pinned`）。第四輪
                # 這裡寫「任何人的姓名都比不出來（含當選人）」——那是用 roster 側
                # 的鍵**推論** candidates 側的事實，兩代完全相關時碰巧對，
                # 有 roster_count ＋三段式候選人清單時就與鏈表互相矛盾（第五輪
                # simplifier F1、skeptic 實跑）。而且那句 57 字＋位數，會員過千就被
                # `display(…, 60)` 靜靜截掉尾巴的指路語（第五輪 simplifier F4）。
                'roster_count': '只有筆數 %s——比不出改名，也比不出「增一刪一」'
                                '（見下面【程式驗不到的部分】）'
                                % ready.get('roster_count'),
            }.get(roster_basis, '**鏈上兩代基準都沒有**：這一項什麼都沒驗到')),
        # §6 要求選票載明屆次與年月日。印出來讓監票員拿票面比對——這是唯一
        # 能把「鏈上的值」與「紙上的值」連起來的一步，程式做不到。
        # **三種狀態要分開講**：「鏈上沒有這個欄位」（舊世代或被拿掉）、
        # 「基準那一筆被打空了」（竄改訊號）、「值壞掉」（上面那一項 FAIL 的
        # 原因）——三者長得一樣而意義完全不同。
        '選舉屆次（鏈上記的）': (
            '（凍結名冊那一筆在鏈上重複或缺少，整個基準是空的）' if not ready
            else '（鏈上沒有這個欄位）' if 'term_no' not in ready
            else ('第 %s 屆' % term_no) if term_no_ok
            else '**不是合法的屆次**：%s' % core.display(repr(term_no), 40)),
        # 年月日**只印不判**：包裡沒有別的東西可以跟它互比，判了就是一道
        # 永遠不會 FAIL 的閘（L1①）。它的用途是讓你拿票面對。
        # **所以這一行是它唯一的出口**，三種狀態尤其不可以印成同一句話：
        # 原本寫 `str(ready.get('meeting_date') or '（鏈上沒有這個欄位）')`，
        # 於是把值改成 `""`／`0`／`false`（不必刪鍵）就會印出與「舊世代」
        # 逐字相同的那句安心話，退出碼 0、總判定「每一項都 OK」
        # （第二輪 red-team 與 skeptic 各自實跑；上面那一項才剛把這個判準
        # 寫下來，下一個鍵就沒套上去——L3「寫成判準再掃一遍全部同類」）。
        '選舉年月日（鏈上記的）': (
            '（凍結名冊那一筆在鏈上重複或缺少，整個基準是空的）' if not ready
            else '（鏈上沒有這個欄位）' if 'meeting_date' not in ready
            # `.strip()` 判空：`"   "`（三個半形空白）`isprintable()` 為真、
            # 非空所以原本的 `or` 不觸發，那一行就印成**視覺空白**，與「版面
            # 壞了」分不出來——三態修法被一個字元繞過（第三輪 red-team 實跑）。
            # `''` 與 `'   '` 的意義相同（都沒有日期），所以印同一句。
            else core.display(str(ready['meeting_date']), 40)
            if str(ready['meeting_date']).strip() else '**是空的**'),
        # 抽籤方式要帶著**分母**一起印：「鏈上登記 0 位候選人」是唯一戳得破
        # 「0 == 0 恆真」的數字，而它原本只放在 `notes` 裡，只在 FAIL／N/A 時
        # 才印（第二輪 red-team）——與這一區「對帳數字無條件印」的判準相反。
        # 基準被打空時 `method` 會從 system 退回 none、分母變 0，於是這一行
        # 與「真的零候選人」**逐字相同**——屆次與年月日補了這一態，這裡沒有
        # 跟著套（第三輪 skeptic；L3 的同一條教訓第三次）。
        '號次抽籤方式': ('（凍結名冊那一筆在鏈上重複或缺少，整個基準是空的）'
                         if not ready else notes.get('draw', '（未記錄）')),
        '跨界同票組數（重算）': len(recomputed_ties),
        # **覆蓋範圍要無條件印**（`notes` 只在 FAIL／N/A 時印）：「這一項比了
        # 幾位、哪幾位沒有基準」決定了它能證明什麼，而那是監票員判斷的前提。
        # **這一列只給數字**：`core.display(…, 60)` 會截斷，而把名單塞進來
        # 就會把後面的數字擠掉（實測：5 位 write-in 的編號就蓋掉了「舊格式」
        # 那一段）。名單放 `notes`。
        # **這一列也要有「基準被打空」那一態**：少了它，`ready` 被打空時這一列
        # 印「逐字比對 0 位／名單外得票 N 位」，與「這場真的沒有登記候選人」
        # 逐字相同——同一份輸出的其他三列都說「基準是空的」（第四輪 skeptic）。
        '當選名單對凍結基準': (
            '（凍結名冊那一筆在鏈上重複或缺少，整個基準是空的）' if not ready
            # **標籤要短**：這一列走 `core.display(…, 60)`，而我第一版把四個欄位
            # 寫成長標籤，於是「；**凍結清單有格式壞掉或混世代的列**」被**靜靜
            # 截掉**——兩支新測試因此紅（而紅的原因不是防線失效，是這一列說不完
            # 話；上面那句「這一列只給數字」的註解就是為了這個，我自己又踩了一次）。
            # 「共 N 位」是**對帳用的分母**：四個數字相加要等於名次表的列數，
            # 少了它，一個漏算的人看不出來（第四輪 skeptic 指出四個成因混在一起）。
            else '逐字比對 %d／舊格式 %d／姓名不符 %d／名單外 %d（共 %d 位）%s'
            % (frozen_name_hits, legacy_hits, len(renamed), len(write_ins),
               frozen_name_hits + legacy_hits + len(renamed) + len(write_ins),
               '；**清單格式異常**'
               if format_broken else '')),
    })

    # ---- 候選人得票表：綁回**鏈上的** result.json，不是綁回 digests.txt ----
    # `candidates.csv` 的票數／名次／當選結果與 result.json 是同一份資料的兩種寫法。
    by_candidate = {}
    for office, data in sorted(offices.items()):
        for row in (data.get('ranking') or []):
            by_candidate[(office, str(row['member_no']))] = (
                str(row['votes']), str(row['rank']), row['result'], row['name'])
    candidates_ok = True
    seen_candidates = set()
    for row in candidate_rows:
        key = (row['office'], row['member_no'])
        seen_candidates.add(key)
        if key not in by_candidate:
            # `result.json` 只收「有登記或有得票」的人，退選又零票的候選人不在裡面。
            # **但不能就這樣跳過**——那等於可以在這個檔追加一列「幽靈當選人」，
            # 而 `candidates_match_result` 連看都不看（抗辯實跑：加一列 rank1 elected，
            # 24 項全綠）。多出來的列只允許是「退選且零票」。
            if row['state'] != 'withdrawn' or row['result'] or row['votes'] not in ('0', ''):
                candidates_ok = False
            continue
        if by_candidate[key] != (row['votes'], row['rank'], row['result'], row['name']):
            candidates_ok = False
    # **兩個方向都要比。** 原本只從 CSV 往 result.json 走，於是 result.json 裡
    # 有、CSV 裡沒有的列可以整列刪掉而零 FAIL——名單外得票（write-in）的當選人
    # 正好就是這種列（`ballot_numbers` 只蓋得住凍結時就登記過的候選人）。
    # `recount` 那一項刻意做了雙向，這一項第八輪之前是單向的（skeptic F7）。
    if set(by_candidate) - seen_candidates:
        candidates_ok = False
    # `bool(by_candidate)` 原本是防恆真，但席位全部從缺時它是合法的空集合。
    # 改成「有候選人或有票時才要求非空」——仍然擋得住「名次表被清空」，
    # 因為那種情況下 recount 會有票。
    has_votes = any(votes for votes in recount.values())
    checks.append(('candidates_match_result',
                   candidates_ok and (bool(by_candidate) or not has_votes)))
    notes['candidates_match_result'] = 'result.json 有但 candidates.csv 缺的：%s' % (
        '、'.join(core.display('%s/%s' % pair, 24)
                  for pair in sorted(set(by_candidate) - seen_candidates)) or '無')

    # ---- 收據碼清單：綁回鏈上的 receipts_digest ----
    # 會員唯一能親自核對的就是「我的碼在不在這份清單裡」。
    receipt_codes = [row['receipt_code'] for row in receipt_rows]
    checks.append(('receipts_digest', needs_all(
        anchor, ('receipts_digest',),
        core.receipts_digest(receipt_codes) == anchor.get('receipts_digest'))))

    # 逐檔指紋：包裡每一個檔都要對得上（`digests.txt` 自己除外，它裝的就是這份清單）。
    # **先要求這張表本身存在且蓋得住每一個該有的檔**——把整個 `files` 鍵刪掉的話，
    # 下面的迴圈跑零次，九項 `file:` 檢查會無聲消失、一行 FAIL 都沒有（抗辯實測）。
    # 資料夾裡多出來的檔也要列進去，否則可以塞一份看起來像官方文件的東西進來。
    file_map = digests.get('files') if isinstance(digests.get('files'), dict) else None
    # **要遞迴走**：只列頂層的話，`mkdir 公會官方文件 && cp … 正式公告.pdf` 完全隱形，
    # 而這道檢查的設計目的正是「不讓人塞一份看起來像官方文件的東西進來」（抗辯實測）。
    # **比相對路徑，不是比檔名**：原本 `path.name != 'digests.txt'` 會把
    # `公會官方文件/digests.txt` 一起排除掉，於是每個子目錄都能藏一個檔
    # （第五輪兩個抗辯代理各自實跑：26 項全綠）。這道檢查的設計目的白紙黑字
    # 寫著「不讓人塞一份看起來像官方文件的東西進來」。
    # `not path.is_symlink()`：`ALLOWED` 裡的連結上面已經早退；**清單外的連結在這裡
    # 是忽略（不讀、不報），不是縱深**——第四輪把早退收窄成固定清單之後，
    # 原本那句「這裡是縱深」就不成立了（第五輪 simplifier F3）。忽略是安全的，
    # 因為這支腳本不讀清單外的任何檔（下面的逐檔指紋只讀 `ALLOWED`）。
    found = sorted(str(path.relative_to(HERE)) for path in HERE.rglob('*')
                   if path.is_file() and not path.is_symlink())
    noise = [name for name in found if is_os_noise(name)]
    present = [name for name in found if name != 'digests.txt' and name not in noise]
    extra = sorted(set(present) - set(file_map or {}))
    absent = sorted(set(file_map or {}) - set(present))
    # 不在白名單上的檔，**就算登記在指紋表裡也不行**
    unexpected = sorted(set(present) - set(ALLOWED))
    # 兩個子句已經移除，理由同一個——被 `not extra` 蘊含：
    #   ①REQUIRED ⊆ file_map（早退保證九個檔都在）
    #   ②`file_map is not None`（為 None 時 extra＝全部檔名，必然非空）
    # 留著會讓人以為多了兩道（第十輪 simplifier 的可證明死子句）。
    checks.append(('files_present', not extra and not absent and not unexpected))
    if extra or absent or unexpected:
        # **檔名是竄改者寫的**，一律經 `core.display` 再印：原樣 join 的話，
        # 一個帶 ANSI 跳脫序列的檔名就能在終端機上改寫這一行想說什麼
        # （游標上移、清行、重印成綠色的 OK）。這是整支腳本最後一條
        # 「使用者資料直接進 print」的路徑。
        notes['files_present'] = (
            '不該出現的檔：%s／未登記的檔：%s／指紋表有但資料夾裡沒有的：%s'
            '（①多出來的若是你自己放進去的檔（含驗算輸出），請解壓到空資料夾再跑一次'
            '　②`__pycache__/*.pyc` 可能是**舊版**封存包裡的驗算器留下的，'
            '　同一個資料夾跑過兩包就會這樣，也請換空資料夾）' % (
                '、'.join(core.display(one, 60) for one in unexpected) or '無',
                '、'.join(core.display(one, 60) for one in extra) or '無',
                '、'.join(core.display(one, 60) for one in absent) or '無'))
    for name, expected in sorted((file_map or {}).items()):
        # **鍵是竄改者控制的**：`HERE / '/etc/hostname'` 會直接跳出封存包資料夾
        # （pathlib 對絕對路徑的行為），指到 `/dev/zero` 還會讓 `read_bytes()`
        # 一路吃記憶體。原本只擋絕對路徑與 `..`，而**符號連結**照樣跟著讀：
        # 登記一個 `x.pdf -> /dev/stdin` 就卡死、stdout 零行，指 100 MB 的包外
        # 檔也照讀（大小上限只蓋 `ALLOWED`）——第五輪 skeptic 與 red-team 各自實跑。
        # 所以**只讀 `ALLOWED` 裡的名字**：那幾個檔的連結與大小在最上面就早退了，
        # 而清單外的鍵本來就由 `files_present` 判 FAIL，讀它不會多證明任何事。
        # 檢查項的名字會被逐字 print，所以也要消毒（同 `files_present` 的理由）。
        label = 'file:' + core.display(name, 60)
        if name not in ALLOWED:
            checks.append((label, False))
            notes[label] = '指紋表登記了封存包檔案清單以外的檔（不讀它）'
            continue
        path = HERE / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ''
        checks.append((label, actual == expected))

except Exception as error:          # noqa: BLE001 — 這裡就是要攔下所有形狀問題
    checks.append(('data_shape', False))
    notes['data_shape'] = '封存包的資料形狀不對（%s: %s）' % (
        type(error).__name__, str(error)[:120])

# 「跑了幾項」原本是一項獨立檢查（`all_checks_ran`）。但主 try 內每一個
# `checks.append` 都是**無條件的直線程式碼**，所以「有一項沒跑」⟺「發生例外」
# ⟺「`data_shape` 在場」——那一項與 `data_shape` 是充要等價，對退出碼的貢獻
# 一模一樣，等於印一行沒有資訊量的 OK 給監票員看。更糟的是唯一證明得了它的
# 測試只斷言**那一行存在**，是循環自證（第七輪 simplifier）。
# 真正要守的是「沒有人把某個 `checks.append` 包進 `if` 裡」這個程式形狀，
# 而那不是執行期驗得到的東西：它由 `tools/check_verify_script.py` 的 AST
# 斷言守著（第七輪 skeptic F6——今天等價，但沒有任何東西守著這個等價）。

# **每一項 FAIL 都要有中文說明。** 第九輪之前 24 項裡只有 6 項有——其餘 FAIL 時
# 只印一個英文代號。整份結論宣稱「非工程師能判斷這包能證明什麼」，而判斷力最需要
# 被支撐的正是失敗路徑，那裡卻是空的（第九輪 skeptic F5）。
# 這份對照表是**靜態**的，`notes` 則帶實際數值；兩者都有時一起印。
MEANING = {
    'chain': '稽核鏈自己串不起來：有一筆的雜湊與前一筆對不上。這包的紀錄被改過。',
    'chain_head': 'digests.txt 寫的鏈頭與實際最後一筆不符。',
    'chain_complete': '鏈缺了必要的狀態、有重複的狀態、順序不對，或公告不是最後一筆。',
    'ballots_digest': '選票檔與稽核鏈記的選票摘要對不上：選票被改過或被加減過。',
    'ballots_sealed_matches': '封箱那一筆記的票匭與這包的選票對不上，'
                              '或鏈上有兩筆封箱（＝封了又改再封），'
                              '或封箱不在關票與開票之間。',
    'roster_digest': '名冊檔與稽核鏈記的名冊摘要對不上。',
    'roster_count_matches_freeze': '名冊與**凍結當下**那一筆對不上：有人在審定之後被加進名冊或改掉。',
    'voted_count_agrees': '「投了幾票」的三個來源（鏈上、名冊已投欄、收據碼張數）互相矛盾。',
    'result_digest': 'result.json 與稽核鏈記的結果摘要對不上：開票結果被改過。',
    'digests_match_chain': 'digests.txt 這份摘要本說的話與稽核鏈不一致。',
    'ballot_status': '有效／廢票的判定與規則重算的結果不同：狀態或廢票原因被改過。',
    'recount': '從選票重數的結果與名次表對不上：票數被改過，'
               '或有人的票被灌進來、或某位當選人整列被刪掉（這一項是雙向比對）。',
    'ranking': '依票數與凍結名額重推的名次，與名次表不同：誰當選被改過。',
    'ballot_numbers': '候選人號次與稽核鏈記的不符。',
    'term_no': '稽核鏈上的選舉屆次不是一個正整數；選罷辦法 §6 要求選票載明選舉屆次。',
    'draw': '號次抽籤用公開公式重算的結果，與檔案裡的號次不同。',
    'seats_match_frozen_roster': '應選／候補名額或每人可圈選數，與凍結名冊那一筆不符。'
                                 '（凍結那一筆在投票開始之前，所以改它的人必須在'
                                 '投票開始之前就決定好結果——這不等於動不了它。）',
    'names_match_roster': '名次表上的姓名或會員編號與名冊對不上。',
    'names_match_frozen_candidates':
        '當選名單上的姓名與**凍結名冊那一筆**登記的候選人姓名對不上：'
        '有人在名冊凍結之後改掉了名字。',
    'seeds_match_chain': 'result.json 裡的抽籤種子與稽核鏈記的不同。',
    'boundary_ties_match_recount': '從票數重算出來的跨界同票組，與稽核鏈記的不同。',
    'candidates_match_result': '候選人得票表與 result.json 對不上（或有一邊多／少了列）。',
    'receipts_digest': '收據碼清單與稽核鏈記的不符：會員拿碼來對會對不到。',
    # 這一句與下面的 `notes['files_present']` 今天確實重複（第十輪 simplifier 建議刪），
    # 但那個蘊含依賴「`files_present` 的子句與 note 的印出條件永遠一致」——
    # 而那正是 `check_verify_script.py` 第④項要防的漂移。留著，但寫成不重複的一行。
    'files_present': '資料夾裡的檔案與指紋表對不起來（詳見下一行）。',
    'ballot_count_agrees': '每個職位的選票張數、有效／無效統計或廢票原因分布對不上。',
    'data_shape': '檔案格式就不對，後面的檢查沒有跑完。',
}
# N/A 既不是通過也不是失敗。**一律先比 `is NA`、不要比真假值**——
# `NA.__bool__` 會拋 TypeError，所以漏掉這個比對的地方會當場炸，
# 不會變成一個靜靜把「沒跑」算成「通過」的 OK。
failed = [name for name, ok in checks
          if not isinstance(ok, NotApplicable) and not ok]
skipped = [(name, ok.missing) for name, ok in checks if isinstance(ok, NotApplicable)]
all_ok = not failed
for name, ok in checks:
    if isinstance(ok, NotApplicable):
        # **這一行只說事實 ＋ 指路。** 中性措辭、`POST_ANCHOR_KEYS` 的警語、
        # `NA_SIDE_EFFECTS` 的側效、`notes` 的數字全部收斂到下面
        # 【程式驗不到的部分】的「這包驗不到」那一段，**只留一份**。
        # 原本逐項與總結段各印一份（第二輪為了「監票員記得的是最後那一段」
        # 而加了第二份），於是同一句話有三個來源（第三處是「凍結名冊那一筆」
        # 那段說明），測試得切兩個區段才打得準，而四條 mutant 在守同一件事
        # 的兩個複本——第三輪 simplifier 算出代價是 1 支 helper ＋1 支測試
        # ＋4 條 mutant，買到的只有「同一段話多看一次」。
        print('N/A  ' + name)
        # 「沒有可以當基準的東西」而不是「沒有這個欄位」：姓名那一項判 N/A 時
        # `candidates` 鍵明明在（舊格式沒有姓名、或上榜的都不在清單裡），寫成
        # 「沒有這個欄位」就是第四輪判死過的「鍵在、那句話與事實不符」（第六輪 simplifier）。
        print('     ↳ 稽核鏈上沒有可以當基準的東西（%s），所以這一項**沒有驗到任何'
              '東西**；為什麼、以及它連帶拖掉了什麼，見下面「這包驗不到」那一段。'
              % ok.missing)
        continue
    print(('OK   ' if ok else 'FAIL ') + name)
    if ok:
        continue
    if MEANING.get(name):
        print('     ↳ ' + MEANING[name])
    elif name.startswith('file:'):
        print('     ↳ 這個檔的內容與指紋表登記的不符：被改過。')
    if notes.get(name):
        print('     ↳ ' + notes[name])

# **最後一道不是程式能做的**：鏈頭要與監票員在投票當下從大螢幕抄下來的那一串比對。
# 有 DB 權限的人可以把整包連同摘要一起重造（公式是公開的、沒有秘密金鑰），
# 唯一擋得住的是「會場當下寫在紙上的那個值」。
print('')
# **主檢查半路停了的話，先講清楚下面各段可能是用預設值印的。** 結尾段在主 try
# 外面，用到的名字都有預設值（印得完是一道獨立防線，residual #7）——但預設值會被
# 印成事實：log.csv 某一筆的 payload 改成 `[]` 就在讀到封箱之前停下，於是一份有封箱、
# 有監票員、有同票抽籤的包印出「這包沒有封箱紀錄……或者有人把它刪掉了」「沒有任何
# 監票員」「本場沒有同票」，鏈表零列再接「一個都找不到＝這包不是那場選舉的紀錄」
# （第六輪 skeptic 與 red-team 各自實跑）。總判定照樣是「沒有通過」，但交給公會的
# 輸出帶著假線索。`data_shape` 只在主 try 的 except 裡登記，所以它在場＝主 try 沒跑完。
# 警語不逐字引用下面那幾句：改了那幾句的措辭，這裡會靜靜失真（L9；第七輪 simplifier）。
if 'data_shape' in failed:
    print('【注意】上面的 data_shape 表示主檢查在半路停了。下面各段有些要用到還沒讀進來的')
    print('  資料，印出來的是預設值：凡是說「沒有……」「找不到……」的句子，在這種情況下')
    print('  **不代表包裡真的沒有**，不要拿來判斷原因。')
    print('')
# **這幾個數字是給人腦對帳用的，所以一律印，不是只在 FAIL 時印。**
# 包內的竄改可以做到完全自洽（改一張 voter 表，投票人數／收據碼張數／
# 名冊已投列數會一起變一致），而封存包裡**沒有報到資料**——所以「當天現場
# 大概幾個人投票」只存在於監票員**在關票當下親眼記下的**那個數字裡，
# 那是唯一獨立於這包的來源（這套系統不產生紙本簽到簿，見下面那段的說明）。
# 這些數字原本只塞在 `notes` 裡，而 `notes` 只在 FAIL 時印（第八輪 skeptic）。
print('【拿這幾個數字去跟你在現場看到的對】')
if facts:
    # **直接走 facts 本身，不要另外抄一份標籤清單。** 抄第二份的後果是：
    # 在 facts 加或改一個鍵卻忘了改清單，就會印出「標籤＋空值」而全套測試照樣綠
    # （`core.display(None)` 是空字串）——第九輪 simplifier 抓到的第三個循環自證。
    # dict 自 3.7 保序，所以顯示順序就是上面 facts.update 的撰寫順序。
    for label, value in facts.items():
        print('  %-24s %s' % (label, core.display(value, 60)))
    # **這一段改過兩次，兩次都錯，第三版把話說準。**
    # 第八輪叫人去對大螢幕——螢幕的已投人數來自 `election.voted_count`，
    # 那是 `assoc_election_voter` 的 count，與可能被竄改的是同一張表（同源）。
    # 第九輪改成叫人去對「紙本簽到簿」——而那個東西**這套系統根本不產生**
    # （全 repo grep 只命中那三行、計畫裡標成 [M3] 且比的是大會出席數），
    # 量綱也不對：簽到簿記的是**到場人數**，這裡的數字是**投票人數**，
    # 到場而沒投票是常態，於是「多了或少了都要追」會在每一場誠實選舉觸發
    # 人工追查——把假錨點換成一把不存在而且刻度不同的尺（第十輪 skeptic）。
    #
    # 說得準的版本：唯一獨立於「這包」的東西，是監票員**在關票當下親眼記下的**
    # 那個數字。它擋得住的是關票之後才被加進／拿掉的投票人，
    # 擋不住投票進行中的竄改（那時螢幕會跟著一起變），
    # 也擋不住「人數不變、只換圈了誰」——那一類要靠開票當場完成與鏈頭比對。
    print('  ——「投票人數」與你在**關票當下**從大螢幕記下的數字一樣嗎？')
    print('    （那是唯一不在這包裡的數字。多了或少了都要追。）')
    print('    注意：人數對得上**不代表沒被動過**——把「誰圈了誰」整批換掉')
    print('    並不會改變任何一個數字，而上面每一項檢查仍然會全綠。')
else:
    print('  （資料形狀有問題，算不出來——上面應該已經有一項 FAIL）')
print('')
# **「全部 OK」不等於「整包都驗過了」**，所以把驗不到的東西逐項講出來。
# `digests['files']` 這份逐檔指紋沒有鏈上的錨點——`log.csv` 是包裡的檔案，
# 所以描述這包 zip 的 `archive_built` 那一筆鏈紀錄不可能在這包 zip 裡面（雞生蛋）。
# 上面每一項綁得回鏈的檢查才是真的；沒綁到的只能靠人工。
print('【程式驗不到的部分】')
# **這一條必須排在最前面，因為它最容易被「全部 OK」蓋過去。**
# 票匭的摘要**最早在開票（counted）那一筆才進鏈**。從第一張票投進來，
# 一路到承辦按下開票為止，選票列沒有被任何雜湊綁住。
#
# 這段文字曾經寫成「最早在關票那一筆」——那是第八輪短暫存在過的機制，
# 第九輪因為它看不到在途選票（會讓乾淨的選舉永久卡死、還把刪票認證成沒動過）
# 而撤回，但**這段印給人看的文字忘了跟著改**，於是它一邊說「關票當下抄鏈頭
# 擋得住」，一邊在四行之後的鏈表把 closed 標成「證明不了誰當選」——
# 同一份輸出裡兩段互斥的指示（第十輪 skeptic 與 red-team 各自指到這裡）。
# 這與第九輪剛修掉的「註解寫對、印給人看的那行寫錯」是同一個形狀。
#
# 第十輪 red-team 實跑了這個窗口：關票之後、開票之前下一句 SQL 改掉
# 「圈了誰」（每職位張數與 status 全不動，所以線上的張數斷言擋不到），
# 再照正常按鈕開票公告產包——稽核鏈一個位元都沒偽造、`_verify_chain()` 回 True、
# 這支腳本 31 項全 OK 退出碼 0，而當選名單整組換掉。
# 逐票入鏈擋得住嗎？擋不住而且不能做：每一筆的 payload 會帶著那張票的雜湊，
# 配上時間戳就能把「誰在幾點投的」與「那張票圈了誰」對起來，直接破壞無記名（D1）。
if sealed is None:
    # **不要替它編理由。** 這裡原本寫「（是加上封箱功能之前產生的）」——
    # 而這支腳本沒有任何辦法知道那是不是真的。第十一輪紅隊實跑：把封箱那一筆
    # 整個刪掉再重鑄鏈尾，32 項全 OK 退出碼 0，而且**附贈這句安撫語**。
    # 於是攻擊者有一條比「偽造一筆對得上的封箱」更便宜的路：刪掉就好。
    # 正確的寫法是中性陳述 ＋ 把判斷交給看得到外部事實的人（L1⑨）。
    print('  開票之前的竄改  ——**這包沒有封箱紀錄。**')
    print('              封箱功能上線之後辦的選舉一定會有這一筆；')
    print('              沒有，就是這場選舉早於該功能，**或者有人把它刪掉了**。')
    print('              本腳本分辨不出是哪一種——請向公會查證這場選舉的日期。')
    print('              沒有封箱那一筆時，票匭摘要最早在「開票」才進鏈，')
    print('              在那之前改票整條鏈一筆都不必偽造，這裡照樣全部 OK。')
    print('              上面那一項 `ballots_sealed_matches` 是「沒有東西與它矛盾」，')
    print('              **不是「驗過了」**。')
else:
    # **把時間差印出來。** 封箱把窗口從「關票→開票（承辦一個人的時間）」縮到
    # 「關票→封箱」，而那一段縮不掉——能做的是讓它**看得見**：
    # 當場封的話是幾秒，隔了幾十分鐘就該問為什麼。
    closed_ts = next((entry['ts'] for entry in entries
                      if entry['payload'].get('to') == 'closed'), '')
    seal_ts = next((entry['ts'] for entry in entries if entry['seq'] == seal_seq), '')
    print('  關票→封箱那段  ——票匭在「封箱」那一筆才被釘住，關票到封箱之間')
    print('              仍然是承辦一個人的時間，本腳本驗不到那段。')
    print('              關票：%s' % core.display(closed_ts, 32))
    print('              封箱：%s' % core.display(seal_ts, 32))
    print('              **這兩個時間應該只差幾秒**（規定是當著監票員的面按）。')
    print('              差了幾十分鐘以上，請向公會要說明。')
if seal_voids:
    # 作廢封箱是設計上留的出口（否則票匭一對不上，這場選舉就只能下 SQL 救，
    # 而那完全無痕）。它擋不住舞弊，但它**看得見**——所以一定要印出來，
    # 而且要講清楚「你抄的鏈頭可能已經失效」。
    print('  票匭被作廢重封  ——這場選舉的封箱被作廢過 %d 次。'
          '這是設計上留的出口，' % len(seal_voids))
    print('              但它也正是「封箱→改票→作廢→再封箱」會留下的痕跡。')
    print('              **如果你抄鏈頭的時間早於下面任何一筆，那個值已經不算數**，')
    print('              請改用公告當下抄的值，並要求公會說明每一筆的原因：')
    for void_seq, voided_seq, reason in seal_voids:
        print('                seq %s 作廢了 seq %s 的封箱：%s'
              % (void_seq, voided_seq, core.display(reason or '（沒寫原因）', 60)))
print('              不論哪一種，投票**進行中**的竄改都驗不到——那要逐票入鏈，')
print('              而逐票入鏈會讓「誰在幾點投的」與「那張票圈了誰」對得起來，')
print('              直接破壞無記名（D1）。擋它的是監票員在場。')
# **有 PDF 才叫人去對 PDF**。它不在 REQUIRED 裡（沒有 wkhtmltopdf 的環境本來就產不出來），
# 所以「刪掉 result.pdf 連同它的指紋」是零 FAIL 的——而腳本若照樣叫監票員
# 「與 PDF 上的名單逐字比對」，等於把唯一的人工防線靜靜地拿掉（抗辯實測）。
if (HERE / 'result.pdf').is_file():
    print('  result.pdf  ——PDF 每次產生的位元組都不同，沒辦法重算。')
    print('              **權威版本是 result.json**（已綁回稽核鏈）。下面印出的名單')
    print('              就是從它算出來的，請與 PDF 上的名單逐字比對。')
else:
    print('  result.pdf  ——**這包裡沒有結果公告 PDF**。若你手上有一份，')
    print('              請與下面印出的名單逐字比對；若沒有，請向公會索取。')
# **這支程式不再印自己的指紋。** 原本在這裡印 verify_core.py／verify_digest.py 的
# sha256、再叫監票員拿去比公布值——而指紋是在**已經執行過包裡公式檔**的這個行程裡
# 算、印的：公式檔原樣保留再附加二十行，換掉 builtins.print 與 sys.exit，就能
# 印出原版的指紋、把 FAIL 改成 OK、退出碼 0（第六輪 red-team 實跑，33 OK）。
# 程式在自己的行程裡證明不了自己沒被換，所以指紋只能在**執行之前**由作業系統算。
print('  verify_core.py／verify_digest.py  ——這兩個檔就是驗算本身，被換掉的話上面')
print('              每一個 OK 都不算數，而且**被換掉的程式想印什麼都可以**。')
# **要在資料夾以外的地方、用完整路徑**（第七輪 red-team）：Windows 的命令提示字元會先
# 執行目前資料夾裡同名的檔，包裡夾一個 certutil.bat／python.bat，「核對指紋」與「執行
# 驗算」就一起被替換，而兩個 .py 一個位元都沒動。PowerShell 不會這樣。
print('              所以要在**執行這支程式之前**算它們的指紋、與系統商公布的值比對，')
print('              而且要在封存包資料夾**以外**的地方、用完整路徑下指令——Windows 的')
print('              命令提示字元會先執行資料夾裡同名的檔，包裡夾一個 certutil.bat 就能')
print('              印出假指紋。Linux `sha256sum 完整路徑`、macOS `shasum -a 256 完整路徑`、')
print('              Windows 用 PowerShell 的 `Get-FileHash 完整路徑`。執行驗算也一樣：')
print('              在資料夾外面跑 `python3 完整路徑/verify_digest.py`。')
print('              本程式刻意不印自己的指紋——那證明不了任何事。')
print('              （公布的指紋請向公會索取；若公會提不出來，這兩個檔就只能')
print('              當成「與封存包同批交付」，不構成獨立佐證。）')
if noise:
    # **點名但不判 FAIL**（見 NOISE_NAMES 的說明）。不說出來也不行：
    # 「忽略」與「沒看到」在監票員眼裡必須是兩件事。
    print('  另外有 %d 個作業系統自動產生的檔，已忽略、不影響驗算：' % len(noise))
    for one in noise:
        print('      ' + core.display(one, 60))
    print('              （Finder／檔案總管開過資料夾就會生，看不見也刪不掉是正常的）')
# **§6 的四個要件：鏈上有的只是「系統當時登記的值」。**
# 屆次與年月日在上面的對帳數字區印出來了，而「印在票上的就是這個數字」程式
# 證明不了——那要有人拿**票面**來對。這句話原本只寫在程式註解裡，輸出從頭到尾
# 沒有，於是 `OK term_no` 被【總判定】吞成「每一項都 OK」（第二輪 skeptic）。
# **而且今天沒有可以拿來對的紙**：這套系統還不產生紙本選票（M12 未實作），
# 電子投票頁上的屆次來自同一個快照欄位、不是獨立來源，投票頁也不進封存包。
# 所以這裡不可以叫人「拿一張實體票對」——那與第十輪被判死的「拿紙本簽到簿對」
# 是同一個形狀：把指示指向一把這套系統不產生的尺。
print('  選票上的 §6 要件  ——鏈上登記的屆次與年月日（見下面的對帳數字）')
print('              只證明**系統當時登記的是這個值**。「選票上印的就是它」')
print('              本腳本證明不了：這套系統目前不產生紙本選票，電子投票頁')
print('              的屆次來自同一個快照欄位（不是獨立來源），投票頁也不在')
print('              這個封存包裡。要證明這一件事，只能靠投票當下在現場')
print('              看過畫面的人。')
# **這一段講的是「通過」而不是「失敗」，所以不能放在 FAIL 才印的 MEANING 裡。**
# 第二輪 red-team 實跑了三種基準：原封不動 → FAIL；刪掉基準鍵 → N/A；
# 把基準偽造成自洽的值 → 零 FAIL 零 N/A、退出碼 0、「每一項都 OK」。
# **count 世代的降級要無條件講出來。** 第二輪為了接上舊世代退路，讓
# `roster_count_matches_freeze` 在鏈上沒有 `roster_digest` 時改比筆數——
# 那抓得到偷加，但抓不到改名與「增一刪一」，**而它印的是 OK**。
# 第三輪 skeptic 與 red-team 各自實跑：在 count 世代的真封存包上對調兩位
# 候選人的姓名、只重鑄 counted 與 published 兩筆（封箱那一筆雜湊逐位元不變），
# 得到 33 OK／0 FAIL／0 N/A、退出碼 0、當選名單換人。
# **第三輪的修法沒有補到這個洞，第四輪兩個鏡頭各自實跑證明它原封不動。**
# 第三輪加回 `names_match_frozen_candidates`（基準是凍結那一筆的 `candidates`）
# 並在這裡寫「當選人的姓名另有一項比對」——而實查兩個正式庫共 69 筆
# `ballot_ready`：沒有 `roster_digest` 的 6 筆，`candidates` **全部**是兩段式
# （沒有姓名欄位）；有 `roster_digest` 的 63 筆，`candidates` 全部三段式。
# 兩個鍵是同一次改動加進 payload 的，所以**完全相關**：
#   需要姓名比對的世代 → 那一項一定是 N/A（基準自己沒有姓名）
#   那一項比得動的世代 → 姓名早就被 `roster_digest` 釘住了（它是縱深，不是靠山）
# 於是上一輪那句話是**安心話術替一個它撐不起來的結論背書**——指向的檢查項
# 在同一份輸出的 20 行後印著「證明不了任何事」（L1⑲：刪掉／弱化 A 的時候
# 宣稱 B 撐得住，就要當場證明 B 撐得住；這次是「加了 B 並宣稱它撐得住」）。
# **第五輪把這一段拆成兩件事、各用自己的尺**：名冊只比筆數看 `roster_basis`，
# 當選人的姓名有沒有錨點看 `names_pinned`（與鏈表同一把）。原本整段掛在
# `roster_basis == 'roster_count'` 上，用名冊側的鍵推論候選人清單有沒有姓名——
# 兩代完全相關時碰巧對；零登記候選人、編號含冒號、名單外當選這三種形狀下，
# 這裡說「沒有錨點」而鏈表說「都釘住」，而且鏈表那句才是錯的（第五輪 skeptic 實跑）。
if roster_basis == 'roster_count':
    print('  名冊（這個世代）  ——鏈上只有 `roster_count`（筆數），沒有逐列摘要：')
    print('              「名冊凍結後有沒有偷加選舉人」比得出筆數，但比不出改名，')
    print('              也比不出「增一刪一」（筆數不變的替換）。')
# **第六輪：連「會員編號」也沒有釘住。** 票匭記的是系統內部的 member_id，
# member_id ↔（編號, 姓名）這層對應只有 `roster_digest` 釘得住；這一段原本寫
# 「票數、名次與會員編號釘得住，拿編號去對名單上的姓名」——封箱後把兩位候選人的
# 編號與姓名**整組**對調，每一組配對都還是真的，照那句指示對會放行（第六輪 skeptic
# 與 red-team 各自實跑，正式庫那 6 份 count 世代的包就是這個狀態）。
if identity_unanchored:
    print('  當選人是誰  ——鏈上沒有逐列摘要（roster_digest），所以名冊裡「這些票投的')
    print('              那個人是哪一個編號、叫什麼名字」這層對應沒有錨點。票數與名次')
    print('              從票匭重算、釘得住，但票匭記的是系統內部的序號，不是編號或姓名：')
    print('              **包裡沒有任何東西可以證明當選的是哪一位會員**')
    print('              ——編號與姓名整組對調也驗不出來。')
    print('              實跑過的攻擊：封箱之後把兩位候選人的編號與姓名整組對調、')
    print('              只重鑄開票與公告兩筆，封箱那一筆（你抄的那個）雜湊逐位元')
    print('              不變，權威名單上的當選人換了人，零 FAIL、退出碼 0。')
    print('              **要查這一項只能用包外的東西**：開票當場公布、監票員記下的')
    print('              當選名單，或理監事會議紀錄、當選證書——**編號與姓名要一起對**，')
    print('              只對其中一個不夠。')
print('  凍結名冊那一筆  ——「名冊凍結後有沒有偷加選舉人」這一項**通過**')
print('              也只是「對得上鏈上登記的那個值」。凍結名冊那一筆早於')
print('              你抄的鏈頭，但那不代表動不了：改得了鏈的人可以把偷加')
print('              之後的摘要寫回那一筆、重鑄當下已經存在的每一筆，之後')
print('              封箱那一筆是系統自己疊上去算的，你抄到的鏈頭會逐字')
print('              吻合。擋得住這件事的只有「投票當下就在現場、而且會去')
print('              核對名冊人數」的人。')
# 上面印成 N/A 的那幾項在這裡再講一次。**不可以只印在檢查清單裡**：
# 清單有三十幾行，監票員捲過去之後留在印象裡的是最後的【總判定】。
if skipped:
    # **這一段的措辭與上面逐項的註腳必須一致。** 上面那句原本也寫著「因為這場
    # 選舉在該欄位加進系統之前就…」，第一輪抗辯把它改成中性（兩種可能都講），
    # 卻漏了這一段——而這一段的開頭兩行自己寫著「監票員捲過三十幾行之後留在
    # 印象裡的是最後的【總判定】」：避險版留在它說會被捲過去的地方，斷言版
    # 留在它說會被記住的地方（第二輪 skeptic）。
    print('  下列 %d 項**這包驗不到**：稽核鏈上沒有可以當基準的東西' % len(skipped))
    print('  （不是檢查失敗，也不是通過）。可能是這場選舉早於該欄位加進系統、這場本來')
    print('  就沒有可比的對象，**也可能是有人把它拿掉了**——本腳本分不出來：')
    for name, key in skipped:
        print('      %-28s 缺的基準：%s' % (name, key))
        # **這裡是唯一一份**（逐項那邊只留「沒驗到 ＋ 看這裡」）。
        for one in key.split('／'):
            if one in POST_ANCHOR_KEYS:
                print('      ↳ ' + POST_ANCHOR_KEYS[one])
        if name in NA_SIDE_EFFECTS:
            print('      ↳ ' + NA_SIDE_EFFECTS[name])
        # `notes` 是人工判斷「這個不適用合不合理」所需要的數字（例如 draw
        # 那條的「鏈上登記 N 位候選人、包裡有 M 個號次」）。原本印在逐項。
        if notes.get(name):
            print('      ↳ ' + notes[name])
    print('              這幾項證明不了任何事，請改用書面紀錄核對。')
print('')
# **標題不可以無條件說「驗證過」。** 第十輪 skeptic 實跑：把 result.json 的名次
# 結果欄對調並同步指紋，FAIL `result_digest`／`ranking`／`candidates_match_result`、
# 退出碼 1，而這一段照樣把**被竄改的名單**掛在「本包驗證過的」底下；
# FAIL 全在前 22 行，終端機捲完之後留在畫面上的就是這張名單。
# 更糟的是下一段還叫人「與 PDF 上的名單逐字比對」——竄改者的 PDF 當然一致，
# 人工那一關反而替偽造背書。
# **編號與姓名沒有錨點時也不可以說「驗證過」**（第七輪 skeptic、simplifier）：同一份
# 輸出上面才說「包裡沒有任何東西可以證明當選的是哪一位會員」，這裡把編號與姓名
# 掛在「本包驗證過的」底下，等於收回那句話。正式庫那 6 份 count 世代的誠實包都是這樣。
if all_ok and not identity_unanchored:
    print('【本包驗證過的當選與候補名單（來源：綁回稽核鏈的 result.json）】')
elif all_ok:
    print('【當選與候補名單：票數與名次驗證過，**編號與姓名沒有包內錨點**'
          '（見上面「當選人是誰」那一段）】')
else:
    print('【下列名單**未通過驗證，不可採信**】（上面有 FAIL，這裡照印只為了讓你看出差在哪）')
print('  （director＝理事、supervisor＝監事）')
# `offices` 的型別由檔案內容決定：被指派成陣列時 `.items()` 會在大 try **外面**
# 再炸一次，於是下面那張 ✔／✘ 鏈表——整份驗算唯一的包外錨點——根本印不出來
# （第五輪抗辯實跑）。預設值只保護了「沒被指派」，沒保護「被指派成錯的型別」。
if not isinstance(offices, dict):
    print('  （result.json 的 offices 型別不對，名單無法印出）')
    offices = {}
for office, data in sorted(offices.items()):
    # **同一個洞往下一層**：`offices` 是 dict 了，它的 value 與 value 裡的
    # `ranking` 還是檔案說什麼就是什麼（`ranking` 寫成字串時 `row.get` 會
    # AttributeError，而字串是 iterable 所以迴圈照跑）。走 `dicts_in()`。
    data = data if isinstance(data, dict) else {}
    elected = [row for row in dicts_in(data.get('ranking'))
               if row.get('result') in ('elected', 'alternate')]
    print('  %s（應選 %s、候補 %s）' % (core.display(office, 16),
                                      core.display(data.get('seats'), 4),
                                      core.display(data.get('alternates'), 4)))
    # **「席位從缺」要用說的，不能用「印不出東西」來表達。** 上一段才剛叫監票員
    # 「與 PDF 上的名單逐字比對」，而空白的那一格在他眼裡與「這支程式印壞了」
    # 長得一模一樣（第八輪 skeptic；同 L1⑨「沒有東西要驗 ≠ 證據被刪了」的顯示端版本）。
    if not elected:
        print('    （本職位無人當選——席位從缺。零登記候選人或全部投空白票時'
              '這是合法結果，請與公告核對。）')
    for row in elected:
        # **姓名與編號是使用者資料**，印出去之前一律消毒（見 core.display 的說明）
        print('    %-4s %-12s %-14s %s 票  %s' % (
            core.display(row.get('rank'), 4), core.display(row.get('member_no'), 12),
            core.display(row.get('name'), 14),
            core.display(row.get('votes'), 8), core.display(row.get('result'), 10)))
# 註：這裡原本有三個 `print('')`，中間只隔著註解與指派——實際印出三行空白，
# 而真正需要分隔的兩個標題前面反而沒有空行（第八輪 simplifier）。
# **監票員名單也要印出來**：整套設計唯一的包外錨點是「監票員當場抄的鏈頭」，
# 那份名單是誰就決定了誰有資格持有錨點。原本腳本連提都沒提，
# 零監票員的包照樣全綠（第六輪抗辯實跑）。
observers_claimed = (core.unique_transition(transitions, 'open') or {}).get('observers')
observers = dicts_in(observers_claimed)
# **D6 宣稱「officer 一人從頭做到尾的舞弊偵測得到」**——那就要讓人看得到。
# 原本 `actor_uid` 只進雜湊，腳本從不印，包裡也沒有 uid→人的對照表：
# 監票員得自己去開 log.csv、自己注意到欄位全同值、再自己去問公會那是誰。
actors = {}
# **警語只看狀態轉換的 actor。** 原本用「全部紀錄的 actor 數」判斷，而
# `chain_complete` 只對 `state_change` 要求唯一與順序——於是在 counted 與
# published 之間插一筆 `action='reissue'`、`actor_uid=999` 的紀錄並重鑄鏈，
# 這個警語就消失，而且零 FAIL、退出碼 0（第三輪 red-team 實跑）。
# 那是 D6「officer 一人從頭做到尾偵測得到」的唯一偵測訊號。
# 插一筆假的 `state_change` 做不到同一件事：狀態重複會讓 `chain_complete` 紅。
state_actors = set()
for entry in entries:
    actors[entry['actor_uid']] = actors.get(entry['actor_uid'], 0) + 1
    if entry['action'] == 'state_change':
        state_actors.add(entry['actor_uid'])
print('')
print('【這條鏈上的每一步是誰做的】')
for uid, count in sorted(actors.items()):
    print('    uid %-6s 共 %d 筆' % (core.display(uid, 6), count))
if len(state_actors) == 1:
    print('  **整條鏈的狀態轉換只有一個人操作**（凍結名冊→開始投票→關票→'
          '開票→公告）。選務分工（領票與配對確認不同人）是這套系統防內部')
    print('  舞弊的前提，請向公會確認這是不是預期的。')
    if len(actors) > 1:
        # 其餘紀錄有別人的 uid，但那不構成分工——說清楚，不要讓上面那張表
        # 看起來像是「有兩個人在操作」
        print('  （上面那張表裡的其他 uid 不是狀態轉換，不構成分工。）')

print('')
print('【開始投票當下凍結在稽核鏈上的監票員名單】')
# **三種情況要分開講**：有名單、名單的型別不對、真的沒有監票員。
# 把第二種印成第三種，就是把竄改訊號吞成「這場沒有人被指派監票」。
# （第一版把長度示警寫成一個獨立的 `if`，於是後面的 `else` 掛到它身上——
# 字串型別會同時印出「型別不對」與「沒有任何監票員」兩句互斥的話，
# 而測試正是這樣抓到的。）
if observers:
    for entry in observers:
        print('    uid %-6s %s' % (core.display(entry.get('uid'), 6),
                                   core.display(entry.get('login'), 40)))
    print('  **你的帳號要在上面**。不在的話，這包不是交給你驗的。')
    if isinstance(observers_claimed, list) and len(observers) != len(observers_claimed):
        # 部分壞掉：濾掉之後筆數變少而不說，就是把竄改訊號吞成「名單比較短」
        print('    （鏈上那一筆共 %d 筆監票員紀錄，其中 %d 筆型別不對、'
              '印不出來——竄改訊號）'
              % (len(observers_claimed), len(observers_claimed) - len(observers)))
    # **`dicts_in()` 只濾「不是 dict」，濾不掉「是 dict 而欄位是 null」**：
    # `[{}]` 或 `[{"uid":null,"login":null}]` 兩筆都是 dict、長度相等，於是
    # 上面那道示警不觸發，畫面上印出一列空白——監票員看到的是「印壞了」
    # 而不是竄改訊號（第三輪 red-team；同一節為「席位從缺」立下的
    # 「要用說的，不能用印不出東西來表達」沒掃到這裡）。
    blank_rows = sum(1 for entry in observers
                     if not str(entry.get('uid') or '').strip()
                     and not str(entry.get('login') or '').strip())
    if blank_rows:
        print('    （其中 %d 筆的 uid 與 login 都是空的——那不是「沒有監票員」，'
              '是這一筆紀錄被清掉了，竄改訊號）' % blank_rows)
elif observers_claimed:
    print('    （鏈上那一筆的監票員名單型別不對，印不出來——這是竄改訊號，')
    print('    不是「沒有監票員」。請把這份輸出整份交給公會並要求說明。）')
else:
    print('    （沒有任何監票員）——這場選舉沒有人被指派監票，')
    print('    下面的紙本比對也就沒有人做得了。')

print('')
print('【最後一步：拿你手上的紙本對下面這張表】')
# **這是整份驗算唯一的包外錨點，而它只保護「那一筆以前」。**
# 稽核鏈是從 `sha256(uuid)` 往後串的，公式完全公開、沒有金鑰——
# 有資料庫權限的人可以整條重造。他唯一動不了的，是已經被寫在紙上的那個值
# **以及它之前的每一筆**；那個值之後的鏈，他要怎麼接都可以。
#
# 而「誰當選」是在 counted 那一筆才產生的。所以：
#   抄的是投票進行中的值 → 只證明開票**之前**的流程沒被動過，證明不了當選名單
#   抄的是公告（published）那一筆 → 當選名單才真的被釘住
# 兩輪抗辯都實跑複現過：保留投票中的前幾筆、只重造 counted 與 published 兩筆，
# 就能把當選人換掉而這支腳本 24 項全綠——而監票員抄的那一串照樣出現在表裡。
# 所以下表要逐筆標明「這一筆保不保護開票結果」，不能只說「找到就好」。
# **不要再用 ✔／✘ 兩分法。** 那個圖例原本寫「✔＝當選名單被它釘住」，
# 而第八輪實跑證明那句話是假的：關票到開票之間換票，整條鏈一筆都不必偽造，
# 連 published 那個最強的錨點都完全吻合。真相有三層，逐筆講清楚。
# （順帶：改用文字而不是符號，cp950 的終端機也印得出來。）
# **第八輪的中間層（「票匭釘住，同票抽籤的亂數未必」）第九輪拿掉了，因為它說謊。**
# 實跑：保留 seq1–5 一個位元不動、只重鑄 counted 與 published 兩筆，就能改寫
# 「誰投了票」與**全部六張收據碼**，而關票鏈頭逐字元相同、32 項全 OK、退出碼 0，
# 整份 96 行輸出只差兩行（那兩筆的雜湊）。原因：`receipts_digest` 只錨在 counted，
# 而名冊的 `state`／`voted_at` 在比對前被正規化掉，所以「誰投票」也只錨在 counted。
# 更糟的是承辦可以在關票**之後**刪票（見 assoc_election.py::action_close 的註解），
# 那時關票鏈頭仍然吻合。所以關票那一筆保證得了的東西，不比投票中那幾筆多。
seq_counted = seq_of.get('counted')
# **釘得住結果的最早一筆是「封箱」，不是「開票」。**
# 封箱那一筆承諾了票匭內容，而這支腳本是**從票匭重算名次**的
# （recount／ranking／candidates_match_result），所以票匭被釘住＝當選名單被釘住。
# 這一段原本用 `seq >= seq_counted` 分類，於是把封箱那一筆印成
# 「證明不了誰當選」——而它正是唯一抓得到「關票後改票」的那個值。
# 第十一輪紅隊實跑：保留封箱那一筆、只重鑄 counted 與 published →
# `FAIL ballots_sealed_matches`（機制有效）；連封箱一起重鑄 → 32 項全 OK
# （指引失效）。照著舊指引做的監票員，抄到的正好是攻擊不必動的那一筆。
pin_from = seal_seq if seal_seq is not None else seq_counted
# **票匭釘住的是「票數與名次」，不是「當選的是哪一位會員」。** 票匭記的是 member_id；
# 編號與姓名來自 `roster.csv`，而 member_id ↔（編號, 姓名）只有 `roster_digest`
# 釘得住。這一行原本無條件寫「當選名單都釘住」（第四輪各自實跑：對調姓名、
# 封箱那一筆雜湊不變、權威名單換人、退出碼 0）；第四輪改成「會員編號釘住、姓名沒有」，
# 第六輪又實跑出編號與姓名整組對調同樣驗不出來，所以那半句也收回。
# `names_pinned` 在主 try 裡算，與【程式驗不到的部分】用的是同一個值。
print('  你抄的那一串（或它的前 16 個字）要出現在下表：')
for entry in entries:
    state = entry['payload'].get('to') or entry['action']
    # **跨界同票的名次要到開票那一筆才定**（第七輪 red-team 與 skeptic 各自實跑）：同票
    # 抽籤亂數在開票那一筆才入鏈，封箱那一筆只釘得住票數——保留封箱、只重鑄開票與
    # 公告、亂數換一組，當選人就換人而封箱雜湊不變。擋它的是下面【兩組抽籤亂數】那段
    # 要人拿亂數去對骰子。指路語只在「當選人是誰」那段真的印出來時才加。
    tie_open = bool(boundary_ties) and seq_counted is not None and entry['seq'] < seq_counted
    if names_pinned and not tie_open:
        pins = '票匭與當選名單都釘住'
    else:
        pins = '；'.join(
            (['票數釘住', '**跨界同票的名次要到開票那一筆才定**（見【兩組抽籤亂數】）']
             if tie_open else ['票數與名次釘住'])
            + ([] if names_pinned else
               ['**當選的是哪一位會員（編號與姓名）沒有**'
                + ('（見上面「當選人是誰」那一段）' if identity_unanchored else '')]))
    if pin_from is None or entry['seq'] < pin_from:
        pins = '只證明開票之前的流程，**證明不了誰當選**'
    print('    seq %-3s %-14s %s  ← %s' % (entry['seq'], state, entry['hash'], pins))
# 雜湊鏈綁的永遠是「這一筆**以前**」（原本註解寫反成「之後」，而那個錯誤的
# 心智模型正是「往後追加就能換掉基準」那個洞的來源）；
# 之後的事要靠「published 必須是最後一筆」來擋。
print('    ——每一筆保護的是「它自己與它之前的每一筆」，之後的不算。')
if seal_seq is not None:
    print('  **最早釘得住票匭的是「封箱」那一筆（seq %s）**：關票之後、開票之前，' % seal_seq)
    print('  承辦當著你的面按下「封存票匭」，螢幕上的鏈頭就是那一筆——請抄那一個。')
    print('  大螢幕在開票完成與公告時也還顯示鏈頭，抄那兩個同樣有效。')
    if boundary_ties:
        print('  **這場有跨界同票**：誰當選要等開票那一筆才定（同票抽籤亂數在那時才入鏈）。')
        print('  只抄了封箱的話，請用下面【兩組抽籤亂數】核對亂數是不是當場擲出的那一組。')
else:
    print('  **大螢幕在開票完成與公告時都還顯示鏈頭**：那兩個時點抄下來的才釘得住票匭。')
print('  只抄了投票進行中或關票那一次的話，這包連票數都證明不了——')
print('  請向公會要結果公告，並記得公告 PDF 上的鏈頭是承辦產生的，不是獨立來源。')
print('  一個都找不到＝這包不是那場選舉的紀錄，或中間被換過。')
print('')
print('【兩組抽籤亂數】')
print('  號次抽籤亂數：' + core.display(ready.get('draw_entropy') or '（未使用系統抽籤）', 60))
# **同票抽籤的亂數比號次抽籤重要得多**——它直接決定跨越當選／候補界線的同票誰當選，
# 而它是在**看得到票匭之後**才填的。原本這個值連印都不印，監票員甚至看不出
# 這場有沒有抽過籤（第五輪抗辯換 7 組值試算，得到 2 種理事名單、2 種監事名單，
# 而封存包 26 項全綠、紙本錨點完全吻合）。防線本來裝在比較不重要的那一邊。
#
# 群組取自**重算**（`boundary_ties_match_recount`），不是取自鏈上 payload：
# 照抄 payload 的話，把那個欄位清成 `[]` 就讓這整段消失，連同下面那個
# 要跟骰子比對的值一起（第七輪抗辯實跑：30/30 OK、當選人被換、輸出裡
# 完全看不出這場有同票）。亂數則一律印，有記就要能比對。
if boundary_ties:
    print('  **本場有 %d 組同票跨越當選／候補界線，當選人由抽籤決定**：' % len(boundary_ties))
    for tie in boundary_ties:
        print('      %s　%s 票　%d 人' % (
            core.display(tie.get('office'), 16), core.display(tie.get('votes'), 8),
            len(tie.get('member_ids') or [])))
    print('  ——下面這一組**直接決定上面那幾組同票誰當選**，而且是在開票前、')
    print('    看得到票匭之後才填的。')
else:
    print('  同票抽籤：從票數重算，本場沒有跨越當選／候補界線的同票。')
print('  同票抽籤亂數：' + core.display(anchor.get('tie_entropy') or '（未填）', 60))
print('')
print('  **這兩組都要等於監票員當場擲出的那一組**。')
print('  抽籤公式是公開的、沒有秘密金鑰——承辦如果可以自己挑亂數，')
print('  就可以事先試出想要的結果。擋得住這件事的只有「當場擲、當場抄」。')
# **整份輸出原本沒有任何總判定，只有退出碼**——而這支腳本自述的服務對象
# 「多半不是工程師」，不會去打 `echo $?`（第十輪 skeptic）。
# 一百多行指引捲完之後，畫面上要留下一句他看得懂的結論。
print('')
print('=' * 60)
if all_ok:
    if skipped:
        print('【總判定】通過，**但有 %d 項不適用**（上面標 N/A，它們什麼都沒驗到）。'
              % len(skipped))
    else:
        print('【總判定】通過：上面每一項都 OK。')
    print('  但請記得——通過的意思是「這包內容與稽核鏈一致」，')
    print('  不是「這場選舉沒有問題」。開票之前的竄改本腳本驗不到（見上面那一段），')
    print('  而鏈頭要不要相信，取決於你手上那張紙。')
else:
    print('【總判定】**沒有通過**。以下 %d 項 FAIL：' % len(failed))
    for name in failed:
        print('    ' + name)
    print('  這包的內容與稽核鏈對不起來。請把這份輸出完整交給公會並要求說明，')
    print('  不要只看上面印出來的名單——那份名單正是對不起來的那一份。')
print('=' * 60)
sys.exit(0 if all_ok else 1)
'''


class AssocElectionArchiveFile(models.Model):
    """封存包本體。**故意沒有 `ir.model.access` 列**（比照 `assoc.election.ballot`）。

    檔案裡有選票明文，所以這裡不是「給對的人看」的問題，是「只有一條出得去的路」
    的問題：沒有 ACL 就沒有 ORM 讀、沒有 `/web/content`、沒有匯出，
    只剩 `_check_observer()` 通過後的那一次 sudo。
    """

    _name = 'assoc.election.archive'
    _description = '監票封存包'

    election_id = fields.Many2one(
        'assoc.election', string='選舉', required=True, ondelete='cascade', index=True)
    content = fields.Binary(string='封存包', attachment=True)
    # 指紋只留在 `assoc.election.archive_sha256`（表單與下載路由讀的是那一個）。
    # 同一個值存兩份，遲早會有一份沒跟著更新。

    _sql_constraints = [
        ('election_uniq', 'unique(election_id)', '每場選舉只留一包封存檔'),
    ]


class AssocElectionArchive(models.Model):
    _inherit = 'assoc.election'

    def _archive_blob(self):
        """取出封存包的 bytes（沒有就回 None）。呼叫端負責先驗身分。"""
        self.ensure_one()
        record = self.env['assoc.election.archive'].sudo().search(
            [('election_id', '=', self.id)], limit=1)
        return base64.b64decode(record.content) if record.content else None

    def _frozen_observers(self):
        """開始投票那一刻**寫進稽核鏈**的監票員名單（uid 集合）。

        欄位上的 m2m 是活的：`observer_user_ids` 在公告之後仍然改得動
        （`write()` 的守衛只擋 `ballot_ready` 之後的**業務**欄位，而這是 m2m，
        帶哨兵的內部流程也碰得到）。名單一換，紙本錨點的持有人就被換掉了——
        真監票員拿不到封存包，換上去的人拿得到明文選票，而且**沒有人看得出來**
        （第六輪抗辯實跑複現）。鏈上那一份是凍結的，要以它為準。
        """
        self.ensure_one()
        frozen = self.log_ids.filtered(
            lambda log: log.action == 'state_change' and log.payload.get('to') == 'open')
        if len(frozen) != 1:
            return None                      # 還沒開始投票，或鏈被動過
        return {entry.get('uid') for entry in (frozen.payload.get('observers') or [])}

    def _check_observer(self):
        """只有**這一場、而且名字在鏈上**的監票員拿得到封存包。

        群組不夠：監票員是逐場指派的，一個公會可能同時有好幾場選舉，
        A 場的監票員沒有理由看得到 B 場的明文選票。
        欄位上的 m2m 也不夠：它在公告後還改得動（見 `_frozen_observers`）。
        """
        self.ensure_one()
        frozen = self._frozen_observers()
        allowed = self.observer_user_ids.ids if frozen is None else frozen
        if self.env.user.id not in allowed:
            raise AccessError(_('封存包只有本場的監票員可以下載。'))

    # ------------------------------------------------------------------
    def _archive_files(self):
        """組出封存包裡的每一個檔（名稱 → bytes）。"""
        self.ensure_one()
        result = self.result_json or {}
        digests = {
            'election_uuid': self.uuid,
            'election_name': self.name,
            'company': self.company_id.name,
            'ballots_digest': self.ballots_digest or '',
            'roster_final_digest': self.roster_final_digest or '',
            'result_digest': self.result_digest or '',
            'chain_head': (self.log_ids.filtered('is_head')[:1].entry_hash or ''),
            'chain_length': len(self.log_ids),
            'closed_at': utc_iso(self.closed_at),
            'counted_at': utc_iso(self.counted_at),
            'published_at': utc_iso(self.published_at),
        }
        files = {
            'result.json': canonical_json(result).encode('utf-8'),
            'ballots_plain.csv': self._csv_ballots(),
            'roster.csv': self._csv_roster(),
            'log.csv': self._csv_log(),
            'candidates.csv': self._csv_candidates(),
            'receipts.csv': self._csv_receipts(),
            'verify_core.py': (pathlib.Path(__file__).resolve().parent.parent
                               / 'verify_core.py').read_bytes(),
            'verify_digest.py': VERIFY_SCRIPT.encode('utf-8'),
        }
        pdf = self._archive_result_pdf()
        if pdf:
            files['result.pdf'] = pdf
        # **包裡的每一個檔都要有指紋**。原本 `candidates.csv` 與 `receipts.csv`
        # 沒有進任何摘要，改了、刪了都驗得過——在一個標榜防竄改的包裡放
        # 「改了不會被抓到」的檔案是負資產。
        digests['files'] = {name: hashlib.sha256(content).hexdigest()
                            for name, content in sorted(files.items())}
        files['digests.txt'] = canonical_json(digests).encode('utf-8')
        return files

    @staticmethod
    def _csv_bytes(header, rows):
        """一律 UTF-8-SIG：cp950 編不了「喆、堃、峯」這類常見人名用字。

        每一格都過 `verify_core.csv_cell`：封存包是給監票員用 Excel 打開的，
        叫「=cmd…」的會員名會變成一條會執行的公式。離線驗算腳本用同一個檔裡的
        `csv_uncell` 還原，所以摘要仍然是用原值算的。
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator='\n')
        writer.writerow(header)
        writer.writerows([verify_core.csv_cell(cell) for cell in row] for row in rows)
        return buffer.getvalue().encode('utf-8-sig')

    def _csv_ballots(self):
        """明文選票。**依 (office, ballot_hash) 排序**：資料列順序本身會洩漏投票順序，
        而投票順序與報到順序高度相關——照 id 排就等於把票排回人。
        """
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT office, choices, status, invalid_reason "
            "FROM assoc_election_ballot WHERE election_id = %s", [self.id])
        rows = []
        for office, choices, status, reason in self.env.cr.fetchall():
            picks = sorted(choices or [])
            rows.append((verify_core.ballot_hash(self.uuid, office, picks, status),
                         office, ' '.join(str(x) for x in picks), status, reason or ''))
        rows.sort(key=lambda row: (row[1], row[0]))
        return self._csv_bytes(['office', 'choices', 'status', 'invalid_reason'],
                               [(office, picks, status, reason)
                                for _hash, office, picks, status, reason in rows])

    def _csv_roster(self):
        """名冊。與 `ballots_plain.csv` **沒有共用鍵**（D1）：
        兩份都在，但無法把某一張票對回某一個人。
        """
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT member_id, member_no, member_name, state, voted_at "
            "FROM assoc_election_voter WHERE election_id = %s ORDER BY member_no", [self.id])
        return self._csv_bytes(
            ['member_id', 'member_no', 'name', 'state', 'voted_at'],
            [(member_id, no, name, state, utc_iso(voted_at, verify_core.ROSTER_TIME_FORMAT))
             for member_id, no, name, state, voted_at in self.env.cr.fetchall()])

    def _csv_log(self):
        return self._csv_bytes(
            ['seq', 'ts', 'actor_uid', 'action', 'payload', 'prev_hash', 'entry_hash'],
            [(log.seq, log.ts, log.actor_uid, log.action, canonical_json(log.payload or {}),
              log.prev_hash, log.entry_hash)
             for log in self.log_ids.sorted('seq')])

    def _csv_candidates(self):
        # 寫**代碼**不寫「理事／監事」：這一欄要能跟 result.json 與 ballots_plain.csv
        # 的 office 對得起來，中文標籤一翻譯就對不上了
        return self._csv_bytes(
            ['office', 'ballot_number', 'member_id', 'member_no', 'name', 'state', 'votes',
             'rank', 'result'],
            [(c.office, c.ballot_number, c.member_id.id, c.member_no,
              c.member_name, c.state, c.votes, c.rank, c.result or '')
             for c in self.candidate_ids.sorted(lambda c: (c.office, c.rank or 999, c.member_no or ''))])

    def _csv_receipts(self):
        """已投票者的收據碼，**排序後**輸出且不含姓名。

        會員拿自己手上的收據碼在這份清單裡找得到，就知道自己的票進了票匭；
        排序是為了不洩漏投票順序，不含姓名是為了不讓這份清單變成投票名冊。
        """
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT receipt_code FROM assoc_election_voter "
            "WHERE election_id = %s AND receipt_code IS NOT NULL ORDER BY receipt_code", [self.id])
        return self._csv_bytes(['receipt_code'], [(row[0],) for row in self.env.cr.fetchall()])

    # ------------------------------------------------------------------
    # 結果公告 PDF 的取值（樣板只呼叫這兩支，不自己解 JSON）
    # ------------------------------------------------------------------
    def _report_chain_head(self):
        self.ensure_one()
        return self.log_ids.filtered('is_head')[:1].entry_hash or ''

    def _report_offices(self):
        """把 `result_json` 攤成樣板好用的形狀，並補上號次。

        號次在 `result_json` 裡沒有（開票只管票數），但公告要印——
        從候選人列取，用 member_id 對應。
        """
        self.ensure_one()
        labels = dict(OFFICES)
        outcome_labels = dict(self.env['assoc.election.candidate']._fields['result'].selection)
        numbers = {(c.office, c.member_id.id): c.ballot_number for c in self.candidate_ids}
        offices = []
        for code, data in sorted((self.result_json or {}).get('offices', {}).items()):
            offices.append({
                'label': labels.get(code, code),
                'seats': data.get('seats'),
                'alternates': data.get('alternates'),
                'valid_ballots': data.get('valid_ballots'),
                'invalid_ballots': data.get('invalid_ballots'),
                'rows': [dict(row,
                              ballot_number=numbers.get((code, row.get('member_id'))),
                              result_label=outcome_labels.get(row.get('result'), ''))
                         for row in data.get('ranking') or []],
            })
        return offices

    def _archive_result_pdf(self):
        """結果公告 PDF。產不出來就**不放**，不要放一份 HTML 假裝是 PDF。"""
        report = self.env['ir.actions.report'].sudo()
        if report.get_wkhtmltopdf_state() not in ('ok', 'upgrade'):
            return None
        pdf, _content_type = report._render_qweb_pdf(
            'assoc_election.action_report_result', res_ids=self.ids)
        return pdf

    # ------------------------------------------------------------------
    def action_build_archive(self):
        """產生封存包。只能在公告之後，而且要先驗過鏈。"""
        self.ensure_one()
        self._check_officer()
        if self.state != 'published':
            raise UserError(_('只有已公告的選舉可以產生封存包。'))
        if not self._verify_chain():
            raise UserError(_('稽核鏈驗證失敗，拒絕產生封存包，請通報監票員。'))
        files = self._archive_files()          # 只組一次：組兩次可能得到不同內容
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        blob = buffer.getvalue()
        digest = hashlib.sha256(blob).hexdigest()
        # sudo：封存包模型沒有 ACL，產生封存包卻是**選務**的動作。
        # 身分在上面的 `_check_officer()` 已經驗過，這裡只是搬 bytes。
        Archive = self.env['assoc.election.archive'].sudo()
        existing = Archive.search([('election_id', '=', self.id)], limit=1)
        values = {'content': base64.b64encode(blob)}
        if existing:
            existing.write(values)                      # 重建就換掉舊的那一包
        else:
            Archive.create({'election_id': self.id, **values})
        self.sudo().with_context(**{GUARD_STATE: GUARD}).write({
            'archive_sha256': digest,
            'archive_built_at': self.env.cr.now(),
        })
        # **產生封存包故意不入稽核鏈**。它曾經是鏈上的一筆，而那讓鏈頭在建包之後
        # 又前進一格：監票員在系統裡看到的鏈頭（含 archive_built）與封存包裡印的
        # （只到 published）永遠不一樣，唯一的包外錨點因此形同虛設，
        # 而且每重建一次封存包就再差一筆（三輪抗辯都實測到這個現象）。
        # 鏈到 `published` 為止就固定下來，軌跡改記在稽核表——那本來就是它的用途。
        self.env['assoc.audit.log']._log(
            'archive_build', company=self.company_id, count=1,
            detail={'election_id': self.id, 'election': self.name,
                    'sha256': digest, 'size': len(blob), 'files': sorted(files)})
        return True

    def action_download_archive(self):
        self.ensure_one()
        self._check_observer()
        return {
            'type': 'ir.actions.act_url',
            'url': '/assoc/election/%s/archive' % self.id,
            'target': 'self',
        }
