# 社區蓄水池水位（community_water_level）部署說明

> 給學長。2026-10-22 版，對應 `community_water_level` **18.0.4.0.0**。
> 有不清楚、或跟 CorPaaS 的做法對不上的地方，直接問我。

## 1. 這是什麼

社區大樓／學校的蓄水池水位監測：管委會用手機看儲水率、事件、報表，旗艦方案的異常會推 LINE 給管委會。
跟工程監造（jt）是**分開的產品**：獨立一個 Odoo 實例、獨立資料庫，**不裝任何 `construction_*` 模組、也不裝 project**。

| 方案 | 前台功能 |
|---|---|
| 基本 | 水情（儲水率、水位歷程、地圖）、事件清單＋簽收、讀值 CSV、週／月／季／半年／年報 PDF |
| 進階 | ＋事件影像、單一事件 PDF |
| 旗艦 | ＋LINE 異常通知（管委會自己綁定） |

方案設在**社區**（監測場域）上，旗下監測站自動跟著；前台、下載、影像都在伺服器端依方案擋。

## 2. 需要的東西

| 項目 | 內容 |
|---|---|
| 執行環境 | Odoo 18 CE。用現在跑 jt 的同一個映像就可以（依 2026-10-13 紀錄＝`jerry42041s/chienyi-odoo-dobtorsi:18.0.2`，與地端 `chienyi-odoo:18.0` 同一份）。**沒有額外 Python 套件**；PDF 要映像裡的 wkhtmltopdf（已有，0.12.6.1 patched qt） |
| 社區模組 | `community_water_level` 18.0.4.0.0，在 ChienYi 裡（見第 3 節） |
| ChienYi 的三個模組 | `water_level_core` **18.0.3.2.0 以上**、`web_leaflet_lib`、`web_view_leaflet_map`。來源 `DobtorRyanWu/ChienYi` 分支 18.0，**至少要到 commit `9964017`**（2026-10-22 已推上 GitHub） |
| 對外網址 | 一個 HTTPS 網域（管委會的前台、設備上報、LINE webhook 都走它）。憑證用一般 CA（Let's Encrypt 等）。**不要用 Tailscale Funnel**：實測 LINE 打 Funnel 會 TLS 協商失敗 |

相依關係：`community_water_level` → `water_level_core`、`portal`；`water_level_core` → `base`、`mail`、兩個 leaflet 模組。
裝社區模組時 Odoo 會自動把其他的一起裝上。

## 3. 程式碼從哪裡來（跟 jt 同一個做法）

**執行環境不用換、也不用重包映像**：直接用同事的 `jerry42041s/chienyi-odoo-dobtorsi:18.0.2`。
那個映像只有 Odoo 與套件，`/mnt/extra-addons` 是空的掛載點（2026-10-22 查過 `docker history`：沒有任何一層放模組）——
jt 也是這樣，程式碼是 CorPaaS 從 GitHub 抓下來再掛進去。社區模組沒有額外套件，那個映像裡要用的都有。

**程式碼只要掛 ChienYi 一個 repo**（`DobtorRyanWu/ChienYi` 分支 18.0；2026-10-22 起社區模組也放在這裡）。
每個網址是一個資料庫，**每個庫只裝自己要的模組**——沒裝的模組放在磁碟上不會被載入（jt 和 template 現在就共用同一份程式碼、各裝各的）：

| 網址（資料庫） | 要裝 | 不要裝 |
|---|---|---|
| 社區的網址（新庫） | 只裝 `community_water_level`（`water_level_core`、兩個 leaflet 模組會自動一起裝） | 任何 `construction_*`、`project`、`assoc_*` |
| jt.qytech.com.tw（`jt`） | 照舊（工程 `construction_*`，含 `construction_water_level`） | `community_water_level`、`assoc_*` |
| 選舉／公會會員系統的網址（新庫） | 裝 `assoc_portal_election`（`assoc_base`、`assoc_meeting`、`assoc_election`、`assoc_portal` 會自動一起裝） | 任何 `construction_*`、`community_water_level`、`water_level_*` |

- 跟 jt 共用同一個容器的話：更新程式碼要重啟容器，所有網址會一起斷線約 20 秒；水位核心更新時每個站都要各自「更新」。
- 一個庫裝錯模組很難退（卸載會連資料刪掉），照上表裝。
- 選舉站另外**必須**在 odoo.conf 設 `assoc_pii_key_file`（身分證字號加密金鑰的檔案路徑，檔案放容器外、唯讀掛進去、只給 odoo 帳號讀）；沒設的話任何牽涉身分證的動作都會被擋下。金鑰遺失＝所有身分證無法解密，要另外備份。選舉站的其他上線步驟（寄信開關 `assoc.mail.hold` 等）上線前另外對。
- 建一個**新的資料庫**給社區，不要裝進 jt 的庫。

## 4. Odoo 設定（odoo.conf 與系統參數）

| 設定 | 值 | 為什麼 |
|---|---|---|
| `dbfilter` | **只對到這一個庫**（例如 `^water$`） | 設備上報 `/water-level/ingest` 與 LINE webhook 是 `auth='none'`，沒有登入狀態；同時對到兩個以上的庫時 Odoo 選不到庫，請求會變 404 |
| `list_db` | `False` | 不對外列庫名 |
| `proxy_mode` | `True`（有 nginx 在前面時） | 拿到正確的對外網址與來源 IP |
| `workers` | **2 以上** | 後台「檢查 LINE 連線」會請 LINE 回打本機 webhook，自己還在等回應；只有 1 個 worker 時回打會排隊到逾時（推論，未實測；jt 目前是 3） |
| 系統參數 `report.url` | 容器**內部**看得到 Odoo 的位址，例如 `http://127.0.0.1:8069` | PDF 由容器裡的 wkhtmltopdf 去抓樣式；沒設就照 `web.base.url`（對外網址）去抓，容器裡常常連不到 → PDF 沒有任何樣式（地端實測：拿掉就壞、設了就好） |
| 系統參數 `web.base.url` | 對外網址，並設 `web.base.url.freeze = True` | 管理員登入會覆寫 `web.base.url` |

## 5. 安裝

新庫：

```bash
odoo -c /etc/odoo/odoo.conf -d <庫名> -i community_water_level --without-demo=all --stop-after-init
```

裝完重啟 Odoo 主程序（Odoo 18 沒有熱載，Python 改了一定要重啟）。

之後更新：`-u community_water_level`（ChienYi 的水位核心更新時加 `-u water_level_core`）＋重啟。

## 6. 上線後的設定（後台，管理員）

選單都在「**水位監測**」底下。

1. **公司資料**：名稱、Logo——會印在週期報表與事件 PDF 的頁首（沒填就是「Your logo／My Company」）。
2. **告警外送通道**（千溢自己收）：新增 → 類型 **Discord**、對象**千溢內部**、貼 Discord 頻道的 Webhook 網址 → 「送出測試訊息」。
   千溢內部通道**所有方案的告警都送**（斷線也要知道）。
3. **LINE 通道**（旗艦方案給管委會用）：新增 → 類型 **LINE**、對象**客戶**、填 Channel secret、Channel access token（LINE Developers 的
   Basic settings／Messaging API 分頁）、加好友網址（`https://lin.ee/…`）、每社區每月上限（預設 50 則）。
   - LINE Developers → Messaging API → Webhook URL 填 `https://<網域>/water-level/line/webhook/<通道 id>`（通道 id＝存檔後網址列最後的數字）
     → Verify → 打開 Use webhook；官方帳號管理後台 → 回應設定：Webhook 開、自動回應訊息關、加入好友的歡迎訊息建議關。
   - 回 Odoo 按「**檢查 LINE 連線**」：檢查 token、Webhook URL、並請 LINE 實際打一次 webhook 驗 Channel secret；不推訊息、不扣額度。
   - 額度是官方帳號共用的（輕用量每月 200 則，推給一個人算一則）。保護機制：同一台同一類斷線一小時只推一次、每社區每月上限、
     月額度用完當月停推並站內通知水位管理員。
4. **每個社區**：
   1. 監測場域：類型「社區」、管委會（場域擁有者，必填）、**方案等級**、前台成員（管委會的帳號，見下）。
   2. 蓄水池：池底與滿水位高程、有效容量（異形池用容量曲線）。
   3. 監測站：「設備碼」（設備端上報用的 uid）、所屬場域與蓄水池、「期望取樣間隔(分鐘)」、
      **「斷線判定(分鐘)」要大於設備實際上傳間隔**（例如 12 小時才傳一次的設備，用預設 30 分鐘會一直判斷線、一直告警）、
      「一／二／三級警戒水位(m)」（沒填就沒有越線告警）。
      按「**產生上報金鑰**」——只顯示一次，交給設備端。
   4. 管委會帳號：Portal 使用者，加進該場域的「前台成員」。登入後在 My account 會看到「社區水情」。
5. **LINE 綁定**（旗艦社區）：管委會自己在前台「通知」頁新增收件人 → 拿到 10 碼綁定碼（24 小時有效、只能用一次）
   → 手機加官方帳號好友、傳綁定碼 → 回「綁定成功」。千溢可在「水位監測 → LINE 收件人」看綁定狀況、按「傳測試訊息」（會扣 1 則）。

## 7. 設備上報

設備（或轉接程式）POST 到 `https://<網域>/water-level/ingest`，帶 `X-Device-Uid`、`X-Api-Key`；一次最多 2,000 筆、1 MB；
同一台同一時間點重送會被略過，可以放心重試。格式見 ChienYi `water_level_core/docs/PAYLOAD_CONTRACT.md`（上報契約 v2）。

## 8. 驗收

1. **自動測試**（建一個丟棄式空庫跑，跑完刪掉；`--db-filter` 要對到那個庫，不然 HttpCase 會被 dbfilter 擋）：
   ```bash
   odoo -c /etc/odoo/odoo.conf -d water_test -i community_water_level \
     --test-tags /water_level_core,/community_water_level --without-demo=all --stop-after-init \
     --db-filter='^water_test$' --http-port=8199
   ```
   預期最後一行：`0 failed, 0 error(s) of 132 tests`（地端 2026-10-22 結果）。測試會呼叫 LINE 的地方全部是模擬的，不會連外。
2. **冒煙**（用一個管委會帳號）：前台 社區水情 → 事件 → 報表（下載一份週報 PDF，打開確認有樣式）→ 讀值 CSV（Excel 開中文正常）；
   旗艦社區的「通知」頁打得開，基本方案的社區打通知頁是「方案不含」說明頁。
3. Odoo log 沒有新的 ERROR。

## 9. 已知限制

- 時間一律以**台灣時間**顯示與切日（不看帳號時區）；報表的資料完整率以「目前設定的回報間隔」計算，改了回報間隔，舊報表數字會跟著變。
- 監測站依「目前所在的蓄水池」列在報表上，換池的歷史不追溯（換池會留在監測站的紀錄裡）。
- LINE 額度所有社區共用；某社區當月達上限後，該社區只剩站內通知。
- 報表的資料完整率用「期望取樣間隔」當一格：設成 1 分鐘、設備實際 10 分鐘一筆，完整率就只有 10%。要照設備實際間隔設。
- 地端 8071（`127.0.0.1:8071`）是測試站，裡面是示範社區的測試資料，**正式站從空庫開始，不搬資料**。
