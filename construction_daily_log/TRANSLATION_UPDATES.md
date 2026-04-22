# 施工日誌模組 - 繁體中文翻譯更新

## 修改日期
2026-01-08

## 修改內容

### 1. 模型欄位翻譯 (Python 檔案)

#### models/daily_log_sheet.py
- 所有欄位的 `string` 參數已改為繁體中文
- 所有錯誤訊息和使用者提示已改為繁體中文
- 狀態選項已翻譯:
  - new → 新建
  - draft → 草稿
  - confirm → 待審核
  - done → 已核准

#### models/daily_log_line.py
- 所有欄位的 `string` 參數已改為繁體中文
- 星期選項已翻譯 (星期一 ~ 星期日)
- 錯誤訊息已改為繁體中文

#### models/daily_log_weather.py
- 所有欄位的 `string` 參數已改為繁體中文
- 天氣選項已翻譯:
  - sunny → 晴
  - cloudy → 多雲
  - overcast → 陰
  - rainy → 雨
  - heavy_rain → 大雨
  - typhoon → 颱風
  - foggy → 霧
- 停工原因選項已翻譯
- 錯誤訊息已改為繁體中文

### 2. 視圖翻譯 (XML 檔案)

#### views/daily_log_views.xml
- 列表視圖 (List View) 的所有欄位標籤已翻譯
- **新增按鈕已啟用**: 在列表視圖中添加了 `create="true"` 和 `edit="true"` 屬性
- 表單視圖 (Form View) 的所有標籤和按鈕已翻譯
- 看板視圖 (Kanban View) 的所有內容已翻譯
- 行事曆視圖 (Calendar View) 的標題已翻譯
- 搜尋視圖 (Search View) 的所有篩選器和分組已翻譯
- 動作 (Actions) 的名稱和說明文字已翻譯

### 3. 按鈕標籤翻譯

所有動作按鈕已翻譯:
- Submit for Review → 提交審核
- Approve → 核准
- Set to Draft → 重設為草稿
- Refuse → 退回
- Add Weather Records → 新增天氣記錄
- Edit → 編輯
- Delete → 刪除

### 4. 幫助文字翻譯

所有 help 文字已翻譯,包括:
- 空白狀態的提示訊息
- 欄位的說明文字
- 操作說明

## 重要變更

### 新增按鈕問題已解決

在列表視圖中明確添加了以下屬性:
```xml
<list
    create="true"
    edit="true"
    ...
>
```

這確保了使用者可以在列表視圖中看到「新增」按鈕。

## 安裝說明

### 1. 重啟 Odoo 服務

修改 Python 檔案後,必須重啟 Odoo 服務:

```bash
# 停止服務
sudo systemctl stop odoo

# 啟動服務
sudo systemctl start odoo
```

或使用:
```bash
sudo systemctl restart odoo
```

### 2. 升級模組

在 Odoo 後台執行以下步驟:
1. 進入「應用程式」選單
2. 移除「應用程式」篩選器
3. 搜尋「construction_daily_log」
4. 點擊「升級」按鈕

### 3. 清除瀏覽器快取

升級完成後,建議清除瀏覽器快取並重新載入頁面,確保看到最新的介面。

## 驗證檢查清單

升級完成後,請檢查以下項目:

- [ ] 施工日誌列表頁面可以看到「新增」按鈕
- [ ] 所有欄位標籤顯示為繁體中文
- [ ] 狀態標籤顯示為繁體中文 (新建/草稿/待審核/已核准)
- [ ] 星期顯示為繁體中文
- [ ] 天氣選項顯示為繁體中文
- [ ] 所有按鈕標籤顯示為繁體中文
- [ ] 錯誤訊息顯示為繁體中文
- [ ] 搜尋篩選器顯示為繁體中文

## 注意事項

1. **權限檢查**: 確認當前使用者有建立施工日誌的權限
2. **員工設定**: 確認當前使用者關聯到一個員工記錄
3. **公司設定**: 確認當前使用者的公司設定正確

## 已修改的檔案

```
construction_daily_log/
├── models/
│   ├── daily_log_sheet.py     ✓ 已修改
│   ├── daily_log_line.py      ✓ 已修改
│   └── daily_log_weather.py   ✓ 已修改
└── views/
    └── daily_log_views.xml    ✓ 已修改
```

## 技術細節

### Python 字串編碼
所有繁體中文字串使用 Unicode 編碼,確保與 Python 3 相容。

### XML 特殊字符
在 XML 中,某些特殊字符需要轉義或使用 Unicode:
- & → &amp;
- < → &lt;
- 中文字符直接使用或使用 Unicode 編碼

## 後續建議

如果需要支援多語言切換,建議:
1. 使用 Odoo 的 i18n 翻譯系統
2. 建立 `i18n/zh_TW.po` 翻譯檔案
3. 保持程式碼中的 string 為英文,透過 .po 檔案提供翻譯

目前的實作方式是直接在程式碼中使用繁體中文,適合單一語言環境使用。
