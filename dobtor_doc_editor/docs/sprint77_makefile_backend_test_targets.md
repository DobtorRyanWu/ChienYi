# Sprint 77：Makefile 加 test-backend / test-backend-font / test-backend-zip targets

**性質**：infra / mechanical
**日期**：2026-05-16

## 0. 一句話

Sprint 72 加了 `tests/scripts/run_backend_tests.sh`、但要記得 `docker exec odoo18 bash /mnt/extra-addons/.../run_backend_tests.sh` 很長。Sprint 77 把它包成 `make test-backend` 一個字。

## 1. Method

加 3 個 Makefile target：

```makefile
test-backend: ## 跑 Odoo backend tests (font_serve + zip_guard)
	docker exec $(ODOO_CONTAINER) bash /mnt/extra-addons/$(MODULE)/tests/scripts/run_backend_tests.sh

test-backend-font: ## 只跑 font_serve test
	docker exec $(ODOO_CONTAINER) bash /mnt/extra-addons/$(MODULE)/tests/scripts/run_backend_tests.sh --tag=font_serve

test-backend-zip: ## 只跑 zip_guard test
	docker exec $(ODOO_CONTAINER) bash /mnt/extra-addons/$(MODULE)/tests/scripts/run_backend_tests.sh --tag=zip_guard
```

加進 `.PHONY:` 列表 + 更新 `help` 分組。

## 2. 揭示（紀律 #11 廣域應用對「dev tools 自身」也適用）

WSL 主機 `which make` 沒結果 — **dobtor_doc_editor Makefile 在 WSL 環境無法直接 run**！

但 Makefile 本身只是 string template、`docker exec odoo18 make` 也不通（odoo18 container 也未必裝 make）、所以 Sprint 77 的 Makefile target **設計上是「user 自己裝 make 後用」**。

→ 紀律 #11 第二應用（dev tools 自身的環境假設）：
- Sprint 70 揭示 controller 假設 production container 有 soffice
- Sprint 77 揭示 Makefile 假設 dev host 有 make

兩種 assumption 都是「環境 X 有工具 Y」、都需要 explicit 文檔或 fallback。

## 3. Result（三層 SOP）

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑（無 frontend 變動）|
| L2 VR | 0.073191 不變 |
| L3 Python lint | 不適用 |
| L4 Makefile syntax | text-level OK（Sprint 72 script 已驗 21 tests 跑得起來）|
| L5 actual `make test-backend` 跑 | **本機無 make 工具、用 docker exec 路徑驗證**（Sprint 72 已跑、結果 21 passed）|

## 4. 紀律啟示

### 4.1 Makefile target = sprint 紀律的 docs

Makefile 不只是 build script、也是「**這個專案有什麼可跑的東西**」的單一 source of truth。每加一個 Sprint 紀律操作就應該對應一個 target（或加到既有 target）。

→ 紀律 #14 候選（Sprint 75 揭示「文件 sprint 必須即時同步」）的具體應用：**Makefile 是紀律的最低反射層**。

### 4.2 dev-tool env assumption 也算紀律 #11 範圍

紀律 #11 原始 scope = controller filesystem。Sprint 77 揭示應該擴到「**任何 environment-X-must-have-Y 假設**」。

→ 紀律 #11 廣域版：**任何外部依賴（filesystem path / shell tool / env var / network）都必須有 explicit fallback 或文檔說明**。

## 5. 後續 sprint 候選

- Sprint 78：security/ir.model.access.csv ACL audit
- Sprint 79：i18n strings / 翻譯完整性 audit
- Sprint 80+：紀律 #11 廣域版應用到其他外部依賴

## 6. 一句話結論

**Sprint 77 把 21 個 backend tests 從「記憶 docker exec ... script ...」縮到 `make test-backend`**：揭示紀律 #11 第二應用面（dev tools 自身 env assumption）+ 紀律 #14 候選（Makefile 是紀律最低反射層）。
