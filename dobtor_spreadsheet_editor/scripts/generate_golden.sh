#!/usr/bin/env bash
# generate_golden.sh — 為 tests/fixtures/{01-08}/*.xlsx 產生 golden artifacts
#
# 對每份 fixture 產生兩種 golden：
#   1. PNG（LibreOffice Calc headless 渲染）— 用於 pixelmatch visual regression
#   2. JSON（python-calamine 讀 cell values）— 用於 cell value correctness diff
#
# 依賴：
#   - libreoffice （WSL host 已裝 24.2.7.2；container 沒裝、不要用 docker exec）
#   - docker container odoo18 內的 python-calamine
#
# 用法：
#   bash scripts/generate_golden.sh                  # 產生所有分類
#   bash scripts/generate_golden.sh 08_chienyii_business   # 僅一個分類

set -euo pipefail

MODULE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURES_DIR="$MODULE_ROOT/tests/fixtures"

if [ ! -d "$FIXTURES_DIR" ]; then
    echo "Error: fixtures dir not found: $FIXTURES_DIR" >&2
    exit 1
fi

if ! command -v libreoffice >/dev/null 2>&1; then
    echo "Error: libreoffice not in PATH. WSL host 需有 LibreOffice 24+。" >&2
    exit 1
fi

# Categories to process
if [ $# -gt 0 ]; then
    CATEGORIES=("$@")
else
    CATEGORIES=(
        01_simple_formula
        02_merged_cells
        03_number_format
        04_conditional_format
        05_multi_sheet
        06_chart
        07_pivot
        08_chienyii_business
    )
fi

for cat in "${CATEGORIES[@]}"; do
    cat_dir="$FIXTURES_DIR/$cat"
    [ -d "$cat_dir" ] || { echo "Skip: $cat_dir not found"; continue; }
    golden_dir="$cat_dir/golden"
    mkdir -p "$golden_dir"

    shopt -s nullglob
    xlsx_files=("$cat_dir"/*.xlsx)
    shopt -u nullglob

    if [ ${#xlsx_files[@]} -eq 0 ]; then
        echo "[$cat] no .xlsx fixture（待 user 提供）"
        continue
    fi

    echo "=== [$cat] processing ${#xlsx_files[@]} files ==="
    for xlsx in "${xlsx_files[@]}"; do
        base="$(basename "$xlsx" .xlsx)"
        echo "  $base"

        # 1. PNG golden（每張 sheet 一張 PNG；LibreOffice 預設只渲染第一張）
        libreoffice --headless --convert-to png:writer_png_Export \
            --outdir "$golden_dir" "$xlsx" >/dev/null 2>&1

        # 2. JSON golden（cell values；用 container 內的 python-calamine）
        docker exec odoo18 python3 -c "
import json, sys
import python_calamine
src = '/mnt/extra-addons/dobtor_spreadsheet_editor/tests/fixtures/$cat/$base.xlsx'
wb = python_calamine.CalamineWorkbook.from_path(src)
out = {}
for name in wb.sheet_names:
    sheet = wb.get_sheet_by_name(name)
    out[name] = sheet.to_python(skip_empty_area=False)
print(json.dumps(out, default=str, ensure_ascii=False, indent=2))
" > "$golden_dir/$base.cells.json" 2>&1 || echo "    [warn] calamine read failed"
    done
done

echo ""
echo "=== Golden generation complete ==="
echo "Output: $FIXTURES_DIR/<category>/golden/"
