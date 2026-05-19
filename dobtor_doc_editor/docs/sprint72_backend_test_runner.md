# Sprint 72：tests/scripts/run_backend_tests.sh 統一 backend test runner

**性質**：infra / mechanical（catch-up）
**日期**：2026-05-16

---

## 0. 一句話定位

Sprint 64b/66/68/69/71 加了 21 個 Odoo backend tests（font_serve 12 + zip_guard 9）、但**沒有統一的觸發方式**。每次跑都要記憶 `--test-tags=...` + `--http-port=8169` + `-u dobtor_doc_editor` 一長串 docker exec 命令。Sprint 72 把它封裝成 `tests/scripts/run_backend_tests.sh`。

---

## 1. Method

### 1.1 範圍評估

候選方案：
- (A) 加 GitHub Actions CI job 跑 Odoo HttpCase
- (B) 加 shell 腳本給 user 手動觸發
- (C) Makefile target

評估：
- (A) **CI** 需要在 GitHub runner 內跑 Odoo + Postgres、scope 大（Docker compose CI matrix）、且 ChienYi 的 CI 一向不跑 Odoo runtime（只 lint + manifest validation）— 太大 scope，留作 Sprint 73+
- (B) **shell 腳本**最務實、立即可用、tests/scripts/ 已有同類腳本（generate_golden.sh / run_visual_regression.sh）
- (C) Makefile target 是 (B) 的封裝、可選

Sprint 72 走 (B)、為 Sprint 73+ (C) 鋪路。

### 1.2 設計

`tests/scripts/run_backend_tests.sh`：
- 預設 tag = `font_serve,zip_guard`、可用 `--tag=<name>` 縮 scope
- 環境變數覆寫：`ODOO_DB`、`ODOO_CONF`、`HTTP_PORT`
- 用 `--http-port=8169` 避開既有 server 8069 衝突
- 用 `--max-cron-threads=0` 避開 cron worker spawn 干擾
- 從 log 抓 `odoo.tests.result: N failed, M error(s) of K tests` 一行做最終判定
- 三種 exit code：0 pass / 1 fail / 2 zero-tests-matched（tag 對不到）

### 1.3 整合既有 tag 系統

| 來源 | tag | tests |
|---|---|---|
| Sprint 64b / 66 / 68 / 69 | `font_serve` | 12 |
| Sprint 20 W9-10 + Sprint 71 | `zip_guard` | 9 |
| **Sprint 72 合計** | `font_serve,zip_guard` | **21** |

---

## 2. Result（三層 SOP）

### 2.1 bash syntax

```bash
$ bash -n tests/scripts/run_backend_tests.sh
(0 issues)
```

### 2.2 實跑驗證

```bash
$ docker exec odoo18 bash /mnt/extra-addons/dobtor_doc_editor/tests/scripts/run_backend_tests.sh
─── dobtor_doc_editor backend tests ───
  Tag(s):       font_serve,zip_guard
  DB:           odoo18_dev
  HTTP port:    8169（避開 production 8069）
─────────────────────────────────────────
... [test execution] ...
2026-05-16 04:27:47 odoo.tests.result: 0 failed, 0 error(s) of 21 tests
✓ All 21 tests passed
```

→ **21 tests passed / 0 failed**（font_serve 12 + zip_guard 9）。

### 2.3 三層 SOP 對齊

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑（純 infra script）|
| L2 VR | 0.073191 不變 |
| L3 Python flake8 + AST | 不適用（無 .py 變動）|
| L4 Odoo HttpCase / TransactionCase | **21 passed via Sprint 72 script** ✓ |
| L5 bash -n | ✓ |

---

## 3. 紀律與啟示

### 3.1 紀律 #12 應用（test class 必須 explicit tag）

Sprint 71 揭示紀律 #12：「test class 必須 explicit tag 對應到 `--test-tags` query」。Sprint 72 的 script 把這個紀律**固化為使用 contract** — 預設 tag list `font_serve,zip_guard` 是 explicit 公開的、新 test class 要加新 tag 進 script 才會被跑。

→ 對「dead test」風險的雙重防護：
1. 紀律 #12：test class 加 tag
2. Sprint 72 script：把 tag list 顯式化、加 test 必須改 script

### 3.2 「無 CI = 半 dead test」紀律候選（第 13 條）

Sprint 72 script 仍需 user 手動觸發 / 排程觸發。**沒人定期跑 = 半 dead test**（regress 不被即時抓到）。

→ 新紀律候選（第 13 條）：**Odoo backend test 必須有「定期被跑」機制**（CI 或排程 docker exec）才算真實 coverage。Sprint 72 script 是 enabler、不是 closure。

Sprint 73+ 候選：CI 工程 Odoo container + 排程跑此 script。

### 3.3 Sprint 50-72 累積紀律分布（23 sprints）

| 類型 | 個數 | 比例 |
|---|---|---|
| Code change（改善） | 8（+Sprint 70 PDF fallback、+71 zip_guard tests、+72 script）| 35% |
| Code change（neutral） | 3 | 13% |
| 純診斷 | 7 | 30% |
| Mechanical commit | 1 | 4% |
| Catch-up sprint | 4（66 + 67 + 68 + 71）| 17% |

---

## 4. 後續 sprint 候選

- Sprint 73：docs/glossary.md
- Sprint 74：docs/sprint50_66_retro.md
- Sprint 75：docs/architecture_decision.md 補完
- 紀律 #13 follow-up：CI job 跑 Odoo container（scope 大、留更多 sprint）

---

## 5. 一句話結論

**Sprint 72 把 21 個 backend tests 統一為一行 `bash run_backend_tests.sh` 觸發**：紀律 #12（test tag）+ 紀律 #13 候選（定期跑）雙層固化、Sprint 50-72 累積 23 sprints。
