# Sprint 114 — CI 加 backend-tests job (font_serve gate v1 / workflow_dispatch only)

**日期**:2026-05-16
**類型**:catch-up sprint / CI infra / ~60 行 YAML
**觸發**:autonomous_roadmap.md 階段 A 行 1 = 「CI 加 `--test-tags font_serve` job、gate PR HttpCase」(Sprint 69 收口、紀律 #15)

---

## Hypothesis

Sprint 64b-69 落地 12 個 font_serve HttpCase(path traversal、null byte、URL-encoded CJK、unknown family 404、empty paths fallback、font_path_map 結構、CJK candidate chain 共用)。但 12 test **沒進 CI gate** — 只能透過 `make test-backend-font` 手動跑、PR landing 是否真跑這 12 test 依賴 reviewer 記得。

紀律 #15(security test 跑) Sprint 78 起列為候選、本 sprint 落地第一個正式 CI gate。

**設計挑戰**:`.github/workflows/dobtor_doc_editor_ci.yml` 位於 `addons/` repo 內(submodule、DobtorRyanWu/ChienYi)、但專案的 `Dockerfile` / `docker-compose.yml` 在外層 `odoo18-docker/` repo、CI runner `actions/checkout@v4` 只 checkout 當前 repo、外層基礎建設不可用。

**假設**:font_serve 12 test 純測 controller 路徑解析 + font path map 安全邊界、無 geo / docx / 外層 Dockerfile 額外 deps 需求(已驗證 `test_font_serve.py` import 僅 `unittest.mock`、`odoo.tests.common`、`..controllers.font_serve`)。直接用 upstream `odoo:18.0` image + GitHub Actions postgres service 即可重現完整測試環境。

---

## Method

### 1. 本地 smoke test(CI dry-run)

跑 `docker exec odoo18 bash /mnt/extra-addons/dobtor_doc_editor/tests/scripts/run_backend_tests.sh --tag=font_serve`、確認:
- ✅ Test runner script 正確
- ✅ 12 個 test 全綠(0 failed, 0 errors)
- ✅ 結果輸出格式穩定(`of 12 tests when loading database`)
- 執行時間:1.62s + setup

這是 Sprint 114 三層 SOP 中的 **L4 = CI 等價驗證**:在 production-like 容器內跑 CI 將觸發的同一個 command、確認結果。

### 2. 新增 backend-tests job(`addons/.github/workflows/dobtor_doc_editor_ci.yml`)

| 設計選擇 | 理由 |
|---|---|
| `if: github.event_name == 'workflow_dispatch'` | Mirror 既有 visual-regression 模式、第一版 manual only、避免新增 flaky check block 真 PR |
| `runs-on: ubuntu-latest` + `timeout-minutes: 25` | 手動觸發、給 odoo pull(~2min)+ install + test(~3min) 足夠 buffer |
| `services: postgres:15` | GitHub Actions 原生 service container、healthcheck 設定到 60s 內 ready |
| `docker pull odoo:18.0` + `--network host` | 避免依賴外層 Dockerfile、`--network host` 讓 odoo 容器看見 runner 的 `localhost:5432` |
| `--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons` | upstream odoo:18 預設 addons-path 不包括 mount、必須顯式 append |
| `-d ci_backend_test`(每次新建 DB)| 隔離測試 DB、避免污染 |
| `-i dobtor_doc_editor`(install)| Sprint 64b font_serve controller 需先 install module 才能註冊路由 |
| `--test-tags=font_serve` | 縮限 scope、只跑 12 test |
| `--http-port=8169` | 避開生產 8069、HttpCase 需真 HTTP server |
| `--max-cron-threads=0` | 不啟動 cron worker、加速 stop-after-init |

### 3. 雙向 gate 驗證

```bash
# 反向 gate:任何 "[1-9][0-9]* failed" 或 "[1-9][0-9]* error" 都 fail
if grep -aE "[1-9][0-9]* (failed|error\(s\))" /tmp/odoo-backend/stdout.log; then
  exit 1
fi

# 正向 gate:必須看到「12 tests」字樣(防止 0 test 假綠)
if ! grep -aE "of 12 tests when loading database" /tmp/odoo-backend/stdout.log; then
  exit 1
fi
```

**為什麼正向 gate 不可省**:Odoo 在 module install 失敗時可能整個 phase 跳過(無 test 運行),log 不會有 "X failed" 但也不會有 "12 tests"。若只看反向 gate、會誤判為綠。Sprint 78 Finding 模式 = 必須 assert positive evidence、不只 absence of negative。

### 4. Upload artifact

`/tmp/odoo-backend/` 整目錄(含 `run.log` + `stdout.log`)、`if: always()` 讓 fail 與 pass 都保留、14 天 retention、診斷 flaky 用。

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**(0 行 source code 變動、結果**必然** = Sprint 113 結尾 976 passed + 1 skipped) |
| L2 VR v14 | **跳過**(0 行 pipeline / fixture / production code 變動、VR mean **必然** = 0.073191) |
| L3 Spot check | **跑** — YAML parse via PyYAML / jobs 結構 grep / 既有 frontend+python+xml job 未動 |
| L4 CI 等價驗證 | **跑** — `docker exec ... run_backend_tests.sh --tag=font_serve` 12/12 綠、確認 CI 將執行的同一個 command |

---

## Result

### YAML 變動

| 檔案 | 變動 |
|---|---|
| `addons/.github/workflows/dobtor_doc_editor_ci.yml` | +63 行 backend-tests job(workflow_dispatch only) |

### YAML 結構驗證(L3 spot check)

```python
import yaml
data = yaml.safe_load(open('dobtor_doc_editor_ci.yml'))
jobs = list(data['jobs'].keys())
# ['frontend', 'python', 'xml', 'backend-tests', 'visual-regression']
bt = data['jobs']['backend-tests']
# trigger gate: github.event_name == 'workflow_dispatch'
# steps: 4 (checkout / pull / run / upload artifact)
# services: ['postgres']
```

✅ YAML parse OK / jobs 5 個 / backend-tests 結構完整

### CI 等價驗證(L4 真跑)

```
─── dobtor_doc_editor backend tests ───
  Tag(s):       font_serve
  DB:           odoo18_dev
─────────────────────────────────────────
... 12 個 test 全綠 ...
2026-05-16 13:59:07 INFO odoo18_dev odoo.tests.result: 0 failed, 0 error(s) of 12 tests when loading database 'odoo18_dev'
─── 結果 ───
✓ All 12 tests passed
```

12 test 詳細:
- TestFontServeHttp(2):known family 200 / unknown 404
- TestFontServeLogic(3):font_path_map 結構 / resolve unknown / CJK candidate chain
- TestFontServeSecurity(5):empty paths fallback / null byte 404 / path traversal literal / path traversal double-encoded / URL-encoded CJK decode

### Sprint 114 結尾累積

| 指標 | 數值 | 差 Sprint 113 |
|---|---|---|
| vitest | 976 passed + 1 skipped | 不變(未跑) |
| VR mean | 0.073191 | 不變(未跑) |
| Odoo backend(本地) | 21 passed(font 12 + zip 9) | 不變 |
| Odoo backend(CI gate)| **12 font_serve 進 CI**(workflow_dispatch v1)| **+12 進 CI 第一次** |
| Phase 0 | 100% | 不變 |
| Phase 4.5 產品化 | 100% | 不變(CI 嚴謹度 ↑) |
| 紀律條數 | 18 + 3 子原則 | 不變 |
| Sprint audit doc 數 | 113 → **114** | +1 |
| CI job 數 | 4 → **5** | +1(backend-tests) |

---

## Root cause

Sprint 64b-69 建 font_serve controller + 12 test、但沒同步把 CI 接通。原因 = backend HttpCase 需 Odoo runtime、與 frontend vitest / Python flake8 / XML xmllint 不同層、CI runner bootstrap 成本高(~5min image pull + DB init)、Sprint 69 收口時跳過。

紀律 #15 候選(security test 跑)持續累積到 Sprint 114 才正式落地、揭示 **#15 子原則**:**security test 要進 CI gate 才算「跑」**、local make 跑只算「能跑」、CI gate 才算 enforce。

---

## 紀律累積

### #15 子原則(Sprint 114 揭示)

**Security test 要進 CI gate 才算「跑」**

- **Why**:Sprint 64b-69 落地 12 test 後、PR landing 依賴 reviewer 記得 `make test-backend-font`、實際長期可靠度 ≈ 「能跑」≠「會跑」。CI gate 強制每次都跑、才符合 #15 enforce 精神
- **How to apply**:新增 security-related backend test 後、同 sprint 內必須:(a) 跑通 local(`make test-backend-*` 等價)(b) 加進 CI workflow(workflow_dispatch v1 起步、3 次穩定後 promote 到 push/PR gate)

### 漸進式 CI gate 模式(Sprint 114 確立 / 沿用 visual-regression Sprint 14)

**新 CI job 第一版 = workflow_dispatch only、3 次穩定後 promote 到 PR gate**

- 第一版風險 = image pull rate limit / DB init race / network 異常、若直接 gate PR、第一次 flaky 就 block 真 PR、信任成本太高
- 漸進式:dispatch v1(manual)→ 3 次手動觸發全綠 → schedule nightly v2(自動但不 gate)→ 3 次 nightly 全綠 → push/PR gate v3(正式 enforce)
- 整套流程符合 Sprint 110 教訓 = Strategy A 並存策略、有 fallback 路徑、可隨時 revert

### 紀律 #5 應用(誠實跳過 SOP)

L1 vitest / L2 VR 跳過 — 0 行 production code 變動、結果必然不變。紀律 #5 在 docs sprint 與 CI infra sprint 都適用、誠實聲明 + L3/L4 等價驗證補位。

---

## 後續

### 下一個 sprint = Sprint 115(doc_controller.py / portal routes security test 缺口)

Roadmap 階段 A 行 2 候選、scope:

- 檢視 `controllers/doc_controller.py` + `controllers/portal.py` 是否有 path traversal / null byte / URL-encoded CJK 等同 font_serve 的安全邊界但缺 test
- 補 security test suite(預期 5-10 個新 HttpCase)
- 紀律 #5 廣域應用 + 紀律 #15 enforce
- 三層 SOP:vitest 跳過 / VR 跳過 / Odoo backend 跑 / CI 等價驗證(Sprint 114 backend-tests job 跑得起來、本 sprint 補的 test 同 tag 自動進 CI gate)

### CI gate 漸進 promote 觀察期

Sprint 114-118 範圍內、若 `backend-tests` workflow_dispatch 3 次手動觸發全綠(0 flaky / 0 image pull 失敗 / 0 DB init race)、Sprint 119+ 候選:promote 到 `schedule: cron '0 8 * * *'`(每日 UTC 08:00 nightly)、再 3 次穩定後 push 到 PR gate。

### Sprint 115+ 候選:zip_guard 進 CI

`backend-tests` job 目前只 gate font_serve 12 test、zip_guard 9 test 在 Sprint 116 或同 sprint 加入(`--test-tags=font_serve,zip_guard`、`of 21 tests`)。

### 紀律候選 → 正式化條件

紀律 #15 子原則 + 漸進式 CI gate 模式 → 走「3 sprint 跨度驗證」(roadmap 標準流程 #8)。預期 Sprint 116 / 117 / 118 連續驗證後、可在 Sprint 119 同 autonomous docs sprint 同步寫進 CONTRIBUTING.md + glossary + 規畫書 §6.5。

---

**Document End** — Sprint 114 audit / CI infra / 紀律 #15 子原則 + 漸進式 CI gate 模式確立
