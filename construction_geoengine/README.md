# construction_geoengine - 工程監造系統地理資訊整合

## 模組說明

將工程照片整合至 Odoo 後台 GeoEngine 地圖視圖，取代前端 Portal 的 Leaflet CDN 方案。

## 技術架構

### 依賴模組
- `construction_photo` — 提供 `supervision.photo` 模型
- `base_geoengine` (OCA) — 提供 GeoEngine 地圖視圖引擎

### 環境需求
- Odoo 18 Community Edition
- PostgreSQL + PostGIS 擴展
- Python: shapely, geojson

### 資料流

```
gps_location (Char "lat,lng")
  → latitude, longitude (Float, compute+store, EPSG:4326)
    → geo_point (GeoPoint, compute+store, EPSG:3857)
```

反向（地圖拖曳 marker）：
```
geo_point → latitude, longitude → gps_location
```

座標轉換使用 PostGIS `ST_Transform`（EPSG:4326 ↔ EPSG:3857）。

### 地圖組件
- **底圖**：OpenStreetMap（raster_type=osm，免 API key）
- **向量圖層**：按 `source_model` 分類著色（colored + unique classification）
- **地圖引擎**：OpenLayers 10.5.0（打包在 base_geoengine 內，無外部 CDN）

### 照片來源分類（7 種）
| 代碼 | 名稱 |
|------|------|
| daily_log | 施工日誌 |
| inspection | 自主檢查 |
| defect | 缺失改善 |
| test | 檢試驗 |
| acceptance | 驗收 |
| notification | 通報單 |
| other | 其他 |

## 安裝步驟

### 1. 搬移 base_geoengine 到正式路徑

```bash
cp -r /mnt/d/work/odoo18-docker/1214暫時/addons/base_geoengine /mnt/d/work/odoo18-docker/3rd-party/
```

### 2. 修改 odoo.conf

`/mnt/d/work/odoo18-docker/config/odoo.conf` 的 `addons_path` 加入 `/mnt/3rd-party-addons`：

```ini
addons_path = /mnt/extra-addons,/mnt/3rd-party-addons,/usr/lib/python3/dist-packages/odoo/addons
```

### 3. 重啟並安裝

```bash
# 重啟載入新路徑
docker-compose down && docker-compose up -d

# 安裝 base_geoengine（自動初始化 PostGIS）
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev -i base_geoengine --stop-after-init

# 安裝 construction_geoengine
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev -i construction_geoengine --stop-after-init

# 重啟主進程
docker restart odoo18
```

## 驗證方法

```bash
# PostGIS 是否啟用
docker exec -e PGPASSWORD=odoo odoo_postgres psql -U odoo -d odoo18_dev -c "SELECT PostGIS_Version();"

# geo_point 欄位是否建立
docker exec -e PGPASSWORD=odoo odoo_postgres psql -U odoo -d odoo18_dev -c "SELECT column_name, udt_name FROM information_schema.columns WHERE table_name='supervision_photo' AND column_name='geo_point';"

# 資料是否轉換
docker exec -e PGPASSWORD=odoo odoo_postgres psql -U odoo -d odoo18_dev -c "SELECT id, latitude, longitude, ST_AsText(geo_point) FROM supervision_photo WHERE latitude != 0 LIMIT 5;"
```

UI 驗證：後台 → 工程照片 → 切換地圖視圖（globe icon）

## 注意事項

- `GeoPoint.to_latlon()` 回傳順序是 `(longitude, latitude)`
- `base_geoengine` 安裝時的 `pre_init_hook` 需要 PostgreSQL 有 CREATE EXTENSION 權限
- `base.group_user` 自動繼承 `group_geoengine_user`，內部使用者預設可用地圖
- 地圖預設範圍已設為台灣區域