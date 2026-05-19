# Sprint 70：doc_controller.py filesystem audit + PDF export graceful fallback

**性質**：code change（improvement、紀律 #11 應用）
**日期**：2026-05-16
**前置**：Sprint 69 揭示紀律 #11、Sprint 70 走「controller filesystem 互動 audit」應用域

---

## 0. 一句話定位

紀律 #11 揭示後第一個應用 sprint。Audit `doc_controller.py` 所有 `os.path` / `open()` / `subprocess` / `shutil.which` 互動、cross-check odoo18 container 內實際路徑/工具是否存在。發現 **`fill_template` PDF export 在當前 container broken**（註解誤宣稱「`/usr/bin/soffice` 已確認存在」、實際無 libreoffice），修為 graceful fallback。

---

## 1. Method

### 1.1 Grep 所有 filesystem 互動

```bash
grep -nE "os\.path|open\(|tempfile|shutil|subprocess|Path\(" controllers/doc_controller.py
```

→ 14 處需 audit。

### 1.2 Cross-check container

```bash
$ docker exec odoo18 which node soffice
/usr/bin/node
# (soffice 無輸出 = 不存在)
$ docker exec odoo18 ls /mnt/extra-addons/dobtor_doc_editor/tools/dist/
parse_docx_cli.cjs  visual_regression_pipeline.iife.js
```

| 依賴 | container 狀態 | 用途 |
|---|---|---|
| `node` | ✓ /usr/bin/node | `_ts_parse_docx_to_elements` CLI |
| `soffice` | **❌ 不存在** | `_lo_convert_to_html` + `fill_template` PDF |
| `tools/dist/parse_docx_cli.cjs` | ✓ exists | TS parser CLI |

---

## 2. Findings

### 2.1 `_ts_parse_docx_to_elements`（line 473）✓ SAFE

- `if not os.path.isfile(cli_path): return None` — graceful
- `if not shutil.which('node'): return None` — graceful
- subprocess 失敗 → 回 None
- tempfile.TemporaryDirectory() context manager — 自動清理

### 2.2 `_lo_convert_to_html`（line 537）⚠️ DEAD CODE BUT GRACEFUL

- `if not shutil.which('soffice'): return None` — graceful fallback
- container 內無 soffice → **永遠回 None**、caller fallback 到 Python 解析器
- **不是 blocker**（與 Sprint 69 font_serve dead code 不同 — 那個沒 fallback、回 404）

### 2.3 `fill_template` PDF path（line 1085）❌ **BROKEN，已修**

```python
# 原版（Sprint 70 前）
# PDF：LibreOffice headless（/usr/bin/soffice 已確認存在）  ← 註解錯誤宣告
subprocess.run(['soffice', ...], check=True, timeout=60, ...)
```

- 註解誤宣稱 soffice 存在、實際 container 無
- `subprocess.run(check=True)` 會 raise `FileNotFoundError`
- 沒 catch → user 直接看 500
- **這是 user-facing 功能、不是 dev-only infrastructure**（差別於 Sprint 69 font_serve）

**Sprint 70 修法**：
```python
if not shutil.which('soffice'):
    return {
        'success': False,
        'error': 'PDF export 需要 LibreOffice — 當前 container 未安裝...',
        'fallback': 'docx',
    }
try:
    with tempfile.TemporaryDirectory() as tmpdir:
        ...
        subprocess.run(['soffice', ...], check=True, ...)
except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
    return {
        'success': False,
        'error': f'LibreOffice PDF 轉換失敗：{type(e).__name__} — {str(e)[:200]}',
        'fallback': 'docx',
    }
```

→ user 收到結構化 error + 建議 fallback、不是 500。

### 2.4 `test_render` / `test_data`（line 1434, 1459）✓ SAFE

```python
abs_path = os.path.normpath(os.path.join(fixtures_root, fixture))
if not abs_path.startswith(fixtures_root + os.sep):
    return 400
```

Path traversal 防護 explicit、Sprint 70 audit 確認 OK。`tests/fixtures/` 在 production 可能不存在 → `os.path.isfile` 回 False → 404 graceful。`auth='user'` 開放給 internal user — 是 dev/test infra、評估是否該限制更嚴（紀律 #11.b 候選）。

---

## 3. Result（三層 SOP）

| 層 | 結果 |
|---|---|
| L1 Vitest | **不跑**（純 Python 變動、無 frontend 影響）|
| L2 VR | 0.073191 不變 |
| L3 Python flake8 + AST | ✓（edit area 1085-1115 無新 issues、AST OK；pre-existing issues 在 line 151/586-590 與本 sprint 無關）|
| L4 HttpCase | 留 Sprint 71+ 加 PDF fallback test |

---

## 4. 紀律與啟示

### 4.1 紀律 #11 第一個應用實例

紀律 #11（Sprint 69 揭示）：「Controller 觸碰 filesystem 必須 cross-check production 環境」。

Sprint 70 走第一個應用實例：
- Grep `os.path|open\(|subprocess|shutil` 找所有 filesystem 互動
- `docker exec which/ls` cross-check container 實際情況
- 比對 controller 假設 vs container 現況

**揭示**：14 處 filesystem 互動中、1 處明確 broken（PDF export）+ 1 處 dead code but graceful（_lo_convert_to_html）+ 12 處 OK。

### 4.2 「graceful fallback」是 best practice 不是降級

Sprint 64b font_serve `if not os.path.exists: return 404` 是 graceful；Sprint 70 audit `_lo_convert_to_html` `if not which('soffice'): return None` 也是 graceful。**這些是好設計**。

→ 對比 `fill_template` PDF path `subprocess.run(check=True)` 沒 graceful — **這是壞設計**。一行 `if not shutil.which('soffice')` 能省下 user-facing 500。

### 4.3 註解 vs 實際行為的 drift

`# /usr/bin/soffice 已確認存在` 註解寫在 controller、但實際 container 沒有。**註解陳述「我們相信 X」、與 production 現況不符 → drift**。

→ 紀律 #11 延伸：「**assumes-X-exists 註解必須伴隨 runtime check**，否則註解就是 lying」。

---

## 5. 後續 sprint 候選

- Sprint 71：`doc_zip_guard.py` 邊界 audit（zip bomb / depth check / path traversal）
- Sprint 72：CI 加 `--test-tags font_serve` job
- Sprint 73-75：autonomous docs sprint（glossary / retro / ADR 補完）

PDF fallback 的 unit test 留 Sprint 71+（需要 mock subprocess、scope 略大）。

---

## 6. 一句話結論

**Sprint 70 救回 `fill_template` PDF export 的 user-facing 500**：紀律 #11 第一應用、grep + `docker exec` cross-check 揭示 14 處 filesystem 互動中 1 個 broken / 1 個 dead-but-graceful、修為 graceful fallback + 結構化 error。
