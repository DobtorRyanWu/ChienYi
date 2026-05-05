# dobtor_doc_editor — Sprint 0 Makefile
#
# 用法：在 dobtor_doc_editor/ 目錄下執行 make <target>
# 目標分組：
#   build / dev          — 前端打包與 Odoo 重啟
#   fixtures / scan      — fixture 回歸 + OOXML 元素統計
#   docker / odoo        — Odoo container 操作
#   clean / verify       — 清理與健檢

ODOO_CONTAINER ?= odoo18
ODOO_DB        ?= odoo18_dev
MODULE         ?= dobtor_doc_editor
FIXTURE_DIR    ?= tests/fixtures

# 預設執行 help
.DEFAULT_GOAL := help

.PHONY: help install build watch dev upgrade restart logs \
        scan-ooxml fixtures-golden fixtures-compare \
        clean clean-build clean-deps verify

help: ## 列出所有 target
	@echo "dobtor_doc_editor — Sprint 0 開發指令"
	@echo ""
	@echo "前端打包："
	@grep -E '^(install|build|watch|dev|upgrade|restart|logs):.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Fixture 回歸："
	@grep -E '^(scan-ooxml|fixtures-.*):.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "清理與驗證："
	@grep -E '^(clean.*|verify):.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── 前端打包 ─────────────────────────────────────────────────────────────────

install: ## 安裝 npm 依賴（含 patch-package 套用）
	npm install --no-audit --no-fund

build: ## rollup 打包 OOXML Parser → canvas-editor-custom.umd.js
	npm run build:frontend

watch: ## rollup --watch（修改 .ts 即時重打包）
	npm run build:watch

# ── Odoo container 操作 ──────────────────────────────────────────────────────

upgrade: ## odoo -u dobtor_doc_editor（更新 DB schema、views、ACL）
	docker exec $(ODOO_CONTAINER) odoo -c /etc/odoo/odoo.conf -d $(ODOO_DB) -u $(MODULE) --stop-after-init

restart: ## 重啟 Odoo container（載入 Python controller 變更）
	docker restart $(ODOO_CONTAINER)

logs: ## 跟看 Odoo container 日誌
	docker logs -f --tail 50 $(ODOO_CONTAINER)

dev: build upgrade restart ## 完整開發循環：build TS → upgrade module → restart container
	@echo "✓ dev cycle complete: bundle rebuilt, module upgraded, container restarted"

# ── Fixture 回歸與 OOXML 掃描 ────────────────────────────────────────────────

scan-ooxml: ## 掃 tests/fixtures/ 全部 DOCX 統計使用到的 OOXML 元素
	python3 tools/scan_ooxml_elements.py $(FIXTURE_DIR)

fixtures-golden: ## 用 LibreOffice + pdftoppm 為每份 DOCX 產 golden PNG（在 container 內跑）
	docker exec $(ODOO_CONTAINER) bash -c "cd /mnt/extra-addons/$(MODULE) && bash tests/scripts/generate_golden.sh"

fixtures-compare: ## 用 puppeteer + pixelmatch 比對 canvas-editor 渲染與 golden PNG
	@if [ -z "$(FIXTURE)" ]; then \
		node tests/scripts/compare_fixtures.js; \
	else \
		node tests/scripts/compare_fixtures.js --fixture $(FIXTURE); \
	fi

# ── 清理 ──────────────────────────────────────────────────────────────────────

clean-build: ## 刪除 rollup 輸出與 .tsbuildinfo
	rm -f static/src/lib/canvas_editor/canvas-editor-custom.umd.js
	rm -f static/src/lib/canvas_editor/canvas-editor-custom.umd.js.map
	rm -rf dist *.tsbuildinfo

clean-deps: ## 刪除 node_modules 與 package-lock.json
	rm -rf node_modules package-lock.json

clean: clean-build clean-deps ## 全清（build artifact + node_modules）

# ── 健檢 ──────────────────────────────────────────────────────────────────────

verify: ## 確認 build 鏈通電（type check + rollup build）
	@echo "→ TypeScript type check"
	npx tsc --noEmit
	@echo "→ rollup build"
	npm run build:frontend
	@echo "→ bundle 產出檢查"
	@test -f static/src/lib/canvas_editor/canvas-editor-custom.umd.js && \
		echo "✓ bundle exists ($$(stat -c%s static/src/lib/canvas_editor/canvas-editor-custom.umd.js) bytes)" || \
		(echo "✗ bundle missing" && exit 1)
