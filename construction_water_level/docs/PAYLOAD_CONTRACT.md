# 水位監測上報契約 v2

這份契約是「機器端」與「Odoo 端」之間唯一的約定。機器怎麼取得水位（Modbus、SDI-12、
自家韌體）Odoo 一律不管，只要最後有人照這份契約打 HTTP 進來即可。

因此：**機器如果不能自己發 HTTP，就在現場或伺服器補一支中介程式代打，Odoo 這側不用改。**

---

## 端點

```
POST /water-level/ingest
Content-Type: application/json
X-Device-Uid: <監測站的設備碼>
X-Api-Key:    <該站的上報金鑰明文>
```

設備碼與金鑰在 Odoo 後台「品質安全 → 水位監測 → 監測站」建立站點後，
按表單上的 **產生上報金鑰** 取得。金鑰明文只會在按下按鈕的當下顯示一次，
資料庫只存 sha256 雜湊，遺失就重新產生（舊金鑰立刻失效）。

## 版本

body 帶 `"v": 2`。**沒帶就當成 v1**，v1 的設備一行都不用改，照樣能打。

## Request body

```json
{
  "v": 2,
  "readings": [
    {"ts": "2026-08-19T06:00:00Z", "value": 3.421, "seq_no": 1201, "hash": "a1b2..."},
    {"ts": "2026-08-19T06:01:00Z", "value": 3.438, "seq_no": 1202, "hash": "c3d4..."}
  ],
  "device": {
    "power_source": "mains", "on_backup_power": false, "battery_percent": 97.5,
    "comm_type": "4G", "comm_path": "primary", "signal_dbm": -71,
    "firmware_version": "1.4.0", "model_version": "yolo-2026a",
    "local_buffer_count": 0, "clock_drift_sec": 0.4
  }
}
```

### readings（必填）

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `ts` | string / number | ✔ | 量測時間。三種寫法：帶時區 ISO 8601（`...Z` 或 `+08:00`）、不帶時區 ISO 8601（**視為 UTC**）、Unix timestamp 秒數 |
| `value` | number | ✔ | 感測器量到的值，單位公尺。**不要自己加基準高程**，Odoo 會用站點設定的 `datum_elevation` 換算成水位高程；原始值也會原樣存一份 |
| `seq_no` | int | v2 建議 | 設備端連續流水號，**永不重用、永不倒退**。缺號稽核與補送全靠它 |
| `hash` | hex64 | 進階等級 | 雜湊鏈值，定義見下方「雜湊鏈」 |

### device（選填，旗艦等級的現場韌性狀態）

`power_source`（`mains`/`ups`/`battery`）、`on_backup_power`、`battery_percent`、
`comm_type`、`comm_path`（`primary`/`backup`）、`signal_dbm`、`firmware_version`、
`model_version`、`local_buffer_count`（本地還沒送出的筆數）、`clock_drift_sec`。

只送有變化的欄位即可，沒帶的欄位 Odoo 不會覆蓋。

一次最多 2000 筆、body 最大 1 MB。

### 補傳與重送

`(監測站, 時間)` 與 `(監測站, 序號)` 都是唯一鍵。同一筆重複送不會產生第二筆，也不會報錯，
所以機器斷訊後把整段補傳回來是安全的。

**補送不會觸發告警。** 判斷「這批是不是補送」由 Odoo 用自己的時間決定
（整批最新時間不晚於既有最後上報時間 → 視為補送）。設備可以在 payload 裡自稱補送，
但那只是提示——告警的開關不會交給現場設備。

### 缺號與補送（基本等級承諾的功能）

Odoo 收到序號後會核對連續性。**向前跳號**（本批最小序號 > 已收到的最大序號 + 1）
就開一個缺口，並在**之後每一次上報的回應**裡把缺口區間放進 `resend`。

設備看到 `resend` 就把那些序號的資料重送回來即可。不另開查詢端點的理由：
設備在 4G/NAT 後面沒有公網入口，Odoo 反向連不進去；而設備本來每分鐘就會打這支，
掛在回應上零額外攻擊面、零額外連線。

同一個缺口最多主動要求 5 次，之後標成「無法補回」並停止索取，不會沒完沒了。

## 雜湊鏈（進階等級：竄改可偵測）

**由設備計算，Odoo 只負責驗。** 如果由 Odoo 算，鏈只證明「Odoo 內部一致」——
有資料庫權限的人改完重算就好，「竄改可偵測」就是假的。設備沒能力算時 Odoo 會代算，
並把該站標記成「伺服器代算」，報表上必須誠實顯示這個差別。

定義（UTF-8 編碼後取 sha256，十六進位小寫）：

```
sha256( device_uid + "|" + seq_no + "|" + ts + "|" + raw_value + "|" + prev_hash )
```

| 欄位 | 格式 | 說明 |
|---|---|---|
| `device_uid` | 原字串 | 設備碼 |
| `seq_no` | 十進位整數字串 | 不補零 |
| `ts` | `%Y-%m-%dT%H:%M:%SZ` | UTC、秒精度、**不帶毫秒、不帶時區偏移** |
| `raw_value` | **固定三位小數** | `3.4` 要寫成 `3.400` |
| `prev_hash` | 前一筆的 hash | **第一筆用空字串** |

用的是**設備原始上報值**，不是加了基準高程之後的水位高程：設備算雜湊時不知道
我們的基準高程，而且基準高程日後可能修正——鏈不能因為我們改設定就整段變紅。

### Golden vectors（設備端第一件事就是對這三組）

三個位元組級的細節（三位小數、時間格式、空字串 prev）任一不同，鏈就全紅，
而且會等到上線後真的要舉證時才發現。實作完先跑這三組：

| # | device_uid | seq_no | ts | raw_value | prev_hash | 期望 hash |
|---|---|---|---|---|---|---|
| 1 | `WL-DEMO-01` | 1 | `2026-06-01T00:00:00Z` | 2.000 | （空字串） | `f59af1ef2b2276632c1c0b0ec75ec0e274f99c7023a142f98067498cf99275fb` |
| 2 | `WL-DEMO-01` | 2 | `2026-06-01T00:01:00Z` | 2.100 | 第 1 組的 hash | `d6bc65844dc2a201d08562339ea73baf9d309e330a91366ee884a6ec6f273f7b` |
| 3 | `社區A-01` | 12345 | `2026-12-31T23:59:59Z` | 0.500 | 第 2 組的 hash | `318865e9abee5790a6dd4dbe3188abc5b52cdc9f41ebf55a7cc99c1039a1199b` |

第 3 組故意用中文設備碼與跨年時間，確認兩端的 UTF-8 編碼一致。

## Response

```json
{
  "ok": true, "v": 2,
  "accepted": 2, "duplicated": 0,
  "ack_seq": 1202,
  "resend": [{"from": 1150, "to": 1160}],
  "desired": {"firmware": "1.4.2", "model": "yolo-2026a"},
  "server_time": "2026-08-19T06:01:03Z"
}
```

| 欄位 | 說明 |
|---|---|
| `accepted` / `duplicated` | 真的寫進去的筆數／被唯一鍵擋掉的重複筆數 |
| `ack_seq` | Odoo 目前已收到的最大序號。設備可以據此清掉本地緩衝 |
| `resend` | 請補送的序號區間清單，空陣列代表沒有缺口 |
| `desired` | 指定的韌體／模型版本（宣告式更新，設備自己去取，Odoo 不推二進位） |
| `server_time` | 伺服器 UTC 時間，設備可用來校時與算時鐘偏移 |

| HTTP | Body | 意思 |
|---|---|---|
| 200 | 見上 | 收下了 |
| 400 | `{"error": "bad payload"}` / `{"error": "bad reading format"}` / `{"error": "too many readings"}` | 格式不對。**整批退回**，不會只吃一半 |
| 401 | `{"error": "unauthorized"}` | 設備碼不存在、站已停用、或金鑰錯。三種情況回同一句話，避免這支端點變成設備碼探測器 |
| 403 | `{"error": "forbidden"}` | 來源 IP 不在白名單（僅在有設定系統參數 `water_level.allowed_ips` 時才會檢查） |
| 413 | `{"error": "payload too large"}` | body 超過 1 MB |

## curl 範例

```bash
curl -sS -X POST http://127.0.0.1:8069/water-level/ingest \
  -H 'Content-Type: application/json' \
  -H 'X-Device-Uid: WL-DEMO-01' \
  -H 'X-Api-Key: <金鑰明文>' \
  -d '{"readings":[{"ts":"2026-08-19T06:00:00Z","value":3.421}]}'
```

## 時區

Odoo 的 Datetime 欄位存 naive UTC。換算只在 `controllers/ingest.py::_parse_ts()`
做一次，之後從資料庫到畫面都不再動它——顯示時 Odoo 自己會依使用者時區呈現。

機器端如果送本地時間又不帶時區，資料會整批位移 8 小時，而且**寫入不會報錯**，
只有事後對帳才看得出來。所以契約要求：要嘛帶時區，要嘛就送 UTC。

## ⚠️ 多資料庫部署的前提

Odoo 要先知道這筆請求該寫進哪個資料庫，才輪得到這支端點。而**沒有 session 的匿名請求
（機器就是這種）只有在 dbfilter 對該主機名只匹配到一個 DB 時才選得出來**
（odoo/http.py:1670-1682：`len(all_dbs) == 1` 才有 monodb）。

本機開發環境的 `dbfilter = ^odoo18_(dev|c2|web)$` 匹配三個庫，所以：

* **單庫部署**：直接可用。
* **多租戶部署**：機器要打的網址必須是「該主機名只解析到一個 DB」的網址
  （例如 dbfilter 改成 `^%h$` 搭配各租戶自己的網域）。否則這支路由對機器來說等於不存在。
* 本機要測，可以先用 `/web/session/authenticate` 取得 cookie 再帶著打（測試腳本就是這樣做的），
  但那只是測試手段，不是機器的正式流程。

## 選用的防護

系統參數（設定 → 技術 → 系統參數）：

| 參數 | 值 | 效果 |
|---|---|---|
| `water_level.allowed_ips` | `1.2.3.4,5.6.7.8` | 只接受這些來源 IP。沒設就不檢查 |

機器數量變多、或這支端點要暴露到公網時，建議再加上反向代理層的 rate limit。

**設定要走後台 UI 或 JSON-RPC**：`get_param` 有 ormcache，用 `odoo shell` 改參數不會通知
正在跑的伺服器行程，改了不生效（實測過），要嘛從後台系統參數頁改，要嘛改完重啟容器。
