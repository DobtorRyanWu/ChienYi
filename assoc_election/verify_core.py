"""離線驗算的公式（**只用 stdlib**，不 import Odoo）。

這個檔案是**單一來源**：模型、`tools.py`、以及監票封存包裡的驗算腳本
都從這裡拿公式。封存包直接夾帶本檔原件，所以監票員手上那份與線上跑的
是同一份程式碼——公式寫兩遍的話，兩邊算出不同答案時沒有人知道哪邊錯。

不 import Odoo 是硬性要求：監票員在自己的電腦上只會有 Python，
不會有 Odoo。這裡出現任何 `from odoo ...` 都會讓封存包變成廢紙。
"""

import hashlib
import json
import random
from itertools import groupby

# 名冊行的時間精度：到分鐘。秒會讓同一份名冊在不同時區／不同機器算出不同摘要
ROSTER_TIME_FORMAT = '%Y-%m-%dT%H:%MZ'

# Excel 會把這些字元開頭的儲存格當公式執行（監票員收到封存包就是要用 Excel 打開）
CSV_FORMULA_PREFIX = ('=', '+', '-', '@', '\t', '\r')
# **單引號自己也要跳脫**，否則這一對就不是單射：叫「'=1+1」的會員原樣寫出去，
# 讀回來會被當成「跳脫過的 =1+1」而剝掉一層，摘要就對不上（假警報）。
CSV_ESCAPE_TRIGGERS = CSV_FORMULA_PREFIX + ("'",)


def printable(value):
    """把任何值變成「可以安全印到終端機上」的字串。**不截斷。**

    會員姓名是使用者資料而且沒有任何過濾（`fields.Char`）。姓名裡塞一個換行，
    印出來的「當選名單」就會多一列幽靈當選人——而那個姓名一路誠實地進了
    名冊摘要、結果摘要與稽核鏈，所以**每一項檢查都是綠的**（實跑複現：
    30/30 OK、退出碼 0、紙本錨點吻合，名單上多一個 0 票的人變成當選）。
    控制字元更糟：`\x1b[1A\x1b[2K` 可以把已經印出去的 FAIL 那一行從終端抹掉，
    `\x1b[3J\x1b[2J\x1b[H` 可以清掉整個畫面連 scrollback 一起，重繪一張假的。

    **這個坑被獨立找到過三次**：第六輪是會員姓名、第七輪是封存包裡的檔名、
    第八輪是稽核鏈表的狀態欄（`payload['to'] or action`——`reissue` 那類紀錄的
    action 字串完全由承辦控制）。三次都是「某一處忘了呼叫消毒函式」。
    所以離線腳本自第八輪起**把 `print` 整個換成會呼叫這支函式的包裝層**，
    讓「忘記消毒」在結構上不可能發生；個別呼叫點的 `display()` 只剩截斷職責。
    """
    text = '' if value is None or value is False else str(value)
    return ''.join(char if char.isprintable() else '\\x%02x' % ord(char)
                   for char in text)


def display(value, limit=40):
    """消毒**並截斷**到 limit 個字，給有欄寬的表格用。

    `limit` 不可以統一成單一預設值：抽籤亂數那兩處用 60，降成 40 會把
    監票員要逐字比對紙本的值靜靜截成「…」，而那正是整份驗算唯一包外錨點的一半。
    """
    safe = printable(value)
    return safe if len(safe) <= limit else safe[:limit - 1] + '…'


def csv_cell(value):
    """寫進 CSV 的儲存格：需要跳脫的加一個單引號前綴，讓 Excel 當文字。"""
    text = '' if value is None or value is False else str(value)
    return "'" + text if text.startswith(CSV_ESCAPE_TRIGGERS) else text


def csv_uncell(text):
    """`csv_cell` 的反向，而且是**嚴格的**反向（兩者互為單射）。

    **摘要一律用原值算**，所以讀回來一定要先還原，否則叫「=王小明」的會員
    會讓整份名冊的摘要對不上。兩個方向寫在一起，就不會只改到其中一邊。
    """
    text = text or ''
    if text[:1] == "'" and text[1:].startswith(CSV_ESCAPE_TRIGGERS):
        return text[1:]
    return text


def sha256_hex(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical_json(obj):
    """稽核鏈與結果摘要共用的序列化：鍵排序、無空白、不轉義非 ASCII。

    三個參數都不能少：少了 `sort_keys` 同一份資料會因字典順序算出不同雜湊；
    少了 `separators` 會多出空白；`ensure_ascii=False` 讓中文姓名維持原樣
    （否則同一個名字在不同 Python 版本的轉義可能不同）。
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def chain_hash(election_uuid, seq, ts, actor_uid, action, payload, prev_hash):
    return sha256_hex('%s|%s|%s|%s|%s|%s|%s' % (
        election_uuid, seq, ts, actor_uid, action, canonical_json(payload), prev_hash))


def ballot_hash(election_uuid, office, choices, status):
    return sha256_hex('%s|%s|%s|%s' % (
        election_uuid, office, ','.join(map(str, sorted(choices))), status))


def ballots_digest(election_uuid, ballots):
    """與資料列順序無關、但**保留重複票**的選票摘要。

    :param ballots: 可迭代的 (office, choices, status)
    """
    hashes = sorted(ballot_hash(election_uuid, office, choices or [], status)
                    for office, choices, status in ballots)
    return sha256_hex('\n'.join(hashes))


def _roster_field(value):
    return str(value).replace('\\', '\\\\').replace('|', '\\|')


def roster_line(member_id, member_no, member_name, state, voted_at_minute):
    """名冊的一行。**每個欄位都先跳脫分隔符號**。

    不跳脫的話摘要就不是單射的：叫「王|小明」的會員與另一組欄位切法會算出
    同一行，等於可以換掉名冊而摘要不變。`ballot_hash` 與 `chain_hash` 不必跳脫，
    它們每一段都是 uuid、Selection 代碼、整數或十六進位雜湊，出不了分隔符號。

    注意：改這條公式會讓**舊版算出來的 `roster_final_digest` 全部對不上**
    （摘要已經寫進稽核鏈）。只能在還沒有正式資料時換。
    """
    return '|'.join(_roster_field(value) for value in
                    (member_id, member_no, member_name, state, voted_at_minute or ''))


def roster_digest(lines):
    return sha256_hex('\n'.join(sorted(lines)))


def receipts_digest(codes):
    """收據碼清單的摘要（與順序無關）。

    會員拿手上的收據碼在 `receipts.csv` 裡找得到，才知道自己的票進了票匭。
    這份清單原本沒有任何錨點，改掉它就等於能讓某些會員以為自己的票不見了，
    而離線驗算全綠。所以把它一起寫進開票那一筆稽核鏈。
    """
    return sha256_hex('\n'.join(sorted(codes)))


def result_digest(result):
    return sha256_hex(canonical_json(result))


def rank_office(entrants, votes, seats, alternates, ballots_digest, office, tie_entropy):
    """得票降冪排名，回傳 (依名次排好的 member_id, 需要抽籤的同票群組)。

    **只有跨越當選／候補界線的同票群組才抽籤**（選罷辦法「同票以抽籤定之」），
    種子由選票摘要與監票員現場填的亂數決定——兩者都是公開的，所以任何人都能重算。

    `entrants` 必須**已依會員編號排序**：Python 的 sorted 是穩定的，
    這個初始順序決定了同票而不需抽籤時誰排前面。

    這支放在 verify_core 而不是模型裡，是因為「誰當選」正是整包封存檔最要緊的一句話。
    只重算票數不重算名次的話，線上把名次算錯（或有人動手腳）照樣驗得過——
    抗辯代理實跑過：把排名反轉，1 票的人當選、4 票的人落選，離線驗算 20 項全綠。
    """
    boundaries = {seats, seats + alternates}
    ordered = sorted(entrants, key=lambda member_id: -votes.get(member_id, 0))
    rng = random.Random(sha256_hex('%s|%s|%s' % (ballots_digest, office, tie_entropy or '')))
    ranked, boundary_ties = [], []
    for vote_count, group in groupby(ordered, key=lambda member_id: votes.get(member_id, 0)):
        group = list(group)
        start, end = len(ranked), len(ranked) + len(group)
        if vote_count > 0 and len(group) > 1 and any(start < b < end for b in boundaries):
            boundary_ties.append({'office': office, 'votes': vote_count, 'member_ids': list(group)})
            rng.shuffle(group)
        ranked.extend(group)
    return ranked, boundary_ties


def outcome_for(rank, vote_count, seats, alternates):
    """名次 → 當選／候補／未當選。零票一律未當選（沒有人投他就不該佔名額）。"""
    if vote_count > 0 and rank <= seats:
        return 'elected'
    if vote_count > 0 and rank <= seats + alternates:
        return 'alternate'
    return 'none'


def recheck_ballot(choices, max_marks, electable):
    """開票時重驗一張票（投票時已擋過，這是防禦層）。回傳無效原因或 None。

    `electable` 是合格被選舉人的 member_id 集合。
    """
    if not isinstance(choices, list) or any(type(x) is not int for x in choices):
        return 'malformed'
    unique = set(choices)
    if len(unique) != len(choices):
        return 'malformed'      # 投票時已去重，出現重複代表資料被動過
    if not unique:
        return 'blank'
    if len(unique) > max_marks:
        return 'over_mark'
    if not unique <= set(electable):
        return 'unknown_member'
    return None


def draw_seed(election_uuid, office, entropy, member_numbers):
    """號次抽籤的種子：只由公開資訊組成，任何人都能重算。"""
    return sha256_hex('%s|draw|%s|%s|%s' % (
        election_uuid, office, entropy, ','.join(member_numbers)))


def chain_transitions(entries):
    """把鏈上的狀態轉換攤成 [(seq, 目標狀態, payload)]，只含 `state_change`。"""
    return [(entry['seq'], entry['payload'].get('to'), entry['payload'])
            for entry in entries if entry['action'] == 'state_change']


def unique_transition(transitions, state):
    """取某個狀態**唯一**那一筆的 payload；不存在或超過一筆都回 None。

    **「唯一」是重點，不是方便**。`{狀態: payload}` 這種寫法天生取最後一筆，
    於是在鏈尾**追加**一筆重複的狀態就能讓基準整個易主——攻擊者不必改動任何
    既有紀錄，監票員抄下的舊鏈頭照樣成立、照樣被標成「這一筆保護得了結果」。
    第四輪兩個抗辯代理各自獨立實跑複現：保留真鏈不動、只追加一筆 `counted`，
    當選名單就換人而 24 項檢查全綠、退出碼 0。
    一場選舉的每個狀態本來就只會發生一次，所以「超過一筆」等於「有人動過」。
    """
    hits = [payload for _seq, to_state, payload in transitions if to_state == state]
    return hits[0] if len(hits) == 1 else None


def verify_chain(entries, election_uuid):
    """逐筆重算稽核鏈。回傳第一個對不上的 seq，全部吻合則回 None。

    序號從 1 開始連續這一條是**縱深防禦**：seq 本身就是 `chain_hash` 的輸入之一，
    而且每一筆都要接上一筆的雜湊，所以重排、砍前段、改號碼其實都會先被
    prev_hash 或雜湊那兩道攔下來。留著是因為它便宜，而且失效模式好讀
    （「第 3 筆序號不對」比「第 3 筆雜湊不對」好查）。
    **這一支擋不住的是「砍掉尾巴」**：剩下的部分照樣首尾相接。
    那要靠呼叫端檢查「該有的狀態都還在」（見 verify_digest.py 的 chain_complete）
    與監票員手上抄的鏈頭。

    :param entries: 依 seq 排序的 dict，鍵：seq, ts, actor_uid, action, payload, prev_hash, hash
    """
    expected_prev = sha256_hex(election_uuid)
    for expected_seq, entry in enumerate(entries, start=1):
        if entry['seq'] != expected_seq:
            return entry['seq']
        if entry['prev_hash'] != expected_prev:
            return entry['seq']
        digest = chain_hash(election_uuid, entry['seq'], entry['ts'], entry['actor_uid'],
                            entry['action'], entry['payload'], entry['prev_hash'])
        if digest != entry['hash']:
            return entry['seq']
        expected_prev = digest
    return None


def live_seal(entries):
    """票匭封存的**現行**那一筆，外加作廢紀錄。線上線下共用同一支。

    回傳 `(seq, payload, voids, problem)`：
      * `seq`／`payload`：現行那一筆封箱（完全沒封過時是 `(None, None)`）
      * `voids`：作廢紀錄 `[(作廢那一筆的 seq, 被作廢的封箱 seq, 原因)]`
      * `problem`：結構有問題時的一句中文說明；沒問題是 `None`

    **為什麼需要「作廢」這件事。** 封箱之後票匭一旦與封存當下不符，原本這場選舉
    就沒有任何出口了：不能開票（摘要不符）、不能重封（只能封一次）、
    `action_cancel` 不吃 `closed`、也刪不掉。對一場**誠實**但資料被動到的選舉，
    唯一的復原手段是下 SQL——也就是把公會推去繞過整個系統，而那是完全無痕的
    （第十一輪紅隊）。所以留一條出口，但它必須**入鏈**：作廢是看得見的。

    **為什麼不能寫成「取最後一筆封箱」。** 那是第四輪那個洞的形狀：
    攻擊者不必改動任何既有紀錄，只要往鏈尾追加一筆，基準就易主，
    而監票員抄的舊鏈頭照樣成立。所以現行那一筆是**用排除法**決定的
    ——被某一筆作廢紀錄指名的封箱就不算現行，剩下的必須恰好一筆。
    作廢紀錄本身也要驗：它指的封箱要存在、要在它之前、而且不可以重複指同一筆。
    """
    seals = {}
    for entry in entries:
        if entry['action'] != 'ballots_sealed':
            continue
        if entry['seq'] in seals:
            # `{seq: payload}` 這種寫法天生後者勝——而本支的整個立論就是
            # 「不可以取最後一筆」。seq 重複另有 `verify_chain` 的連號檢查會抓，
            # 但那是**別人**在守，這支自己的契約不能有這個洞（第十二輪 skeptic）。
            return None, None, [], '鏈上有兩筆封箱共用 seq %s' % entry['seq']
        seals[entry['seq']] = entry['payload'] or {}
    voids = []
    voided = set()
    for entry in entries:
        if entry['action'] != 'ballots_seal_voided':
            continue
        payload = entry['payload'] or {}
        target = payload.get('voided_seq')
        voids.append((entry['seq'], target, payload.get('reason') or ''))
        if not isinstance(target, int) or isinstance(target, bool):
            # payload 完全由寫鏈的人控制。`target` 是 list 之類的不可雜湊值時，
            # 下一行的 `in` 會丟 TypeError——離線被 except 收成乾淨 FAIL，
            # 線上卻是在 `_compute_ballots_sealed` 裡炸掉、表單整個開不起來，
            # 而錯誤訊息與作廢無關（第十二輪 skeptic）。純函式不可以丟例外。
            return None, None, voids, '第 %s 筆作廢紀錄的 voided_seq 不是整數' % entry['seq']
        if target not in seals:
            return None, None, voids, '第 %s 筆作廢紀錄指的封箱（seq %s）不存在' % (entry['seq'], target)
        if not (target < entry['seq']):
            return None, None, voids, '第 %s 筆作廢紀錄指的封箱（seq %s）在它之後' % (entry['seq'], target)
        if target in voided:
            return None, None, voids, '封箱 seq %s 被作廢了兩次' % target
        voided.add(target)
    live = sorted(set(seals) - voided)
    if not live:
        # **「每一筆都被作廢」不是鏈壞掉，是合法的可復原狀態**：作廢完還沒重封。
        # 第一版把它判成 problem，於是「作廢 → 重封」這條唯一的出口自己把門關上了
        # （實跑：作廢之後按封箱被自己的守衛擋下來）。
        # 「有作廢紀錄卻已經開票」才是可疑的——那個判準需要知道 counted 在哪，
        # 所以留給呼叫端（離線腳本）判，不在這裡。
        return None, None, voids, None
    if len(live) > 1:
        return None, None, voids, '有 %d 筆封箱同時有效（封了、改了、再封一次）' % len(live)
    return live[0], seals[live[0]], voids, None
