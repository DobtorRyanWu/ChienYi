/** @odoo-module */

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// 來源分類色彩
// ⚠️ 這兩張表的 key 必須與 supervision.photo 的 source_model Selection 同步
// （construction_photo/models/supervision_photo.py）。漏掉一個值，地圖上那些
// 照片就會變成灰色、沒有名字的點（見下方 `|| SOURCE_COLORS.other` 的退路）。
// 2026-08-20：+ estimate / signboard（原本都塞在 other），- acceptance（全庫 0 筆）。
const SOURCE_COLORS = {
    daily_log: "#3b82f6",
    inspection: "#22c55e",
    defect: "#ef4444",
    test: "#f59e0b",
    estimate: "#8b5cf6",
    notification: "#06b6d4",
    signboard: "#ec4899",
    other: "#6b7280",
};

const SOURCE_LABELS = {
    daily_log: "施工日誌",
    inspection: "自主檢查",
    defect: "缺失改善",
    test: "檢試驗",
    estimate: "估驗計價",
    notification: "通報單",
    signboard: "工程告示牌",
    other: "其他",
};

/**
 * 照片地圖互動式 Client Action
 * 使用 Leaflet.js + MarkerCluster
 */
export class PhotoMapAction extends Component {
    static template = "construction_geoengine.PhotoMapAction";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            totalPhotos: 0,
            gpsPhotos: 0,
            filteredCount: 0,
            activeTab: "filter",
            panelOpen: true,
            locating: false,
            nearbyStatus: "",
            nearbyPhotos: [],
            areaPhotos: [],
            areaTotal: 0,
            // 篩選
            projects: [],
            filterOptions: {},
            filters: {
                project_id: false,
                source_model: "",
                category: "",
                construction_phase: "",
                date_from: "",
                date_to: "",
            },
            nearbyRadius: 1,
        });

        this.map = null;
        this.markerCluster = null;
        this.userMarker = null;
        this.userCircle = null;
        this.userLat = null;
        this.userLng = null;
        this._moveEndTimer = null;

        onMounted(() => this._onMounted());
        onWillUnmount(() => this._onWillUnmount());
    }

    async _onMounted() {
        await this._loadInitialData();
        this._initMap();
        await this._loadMarkers();
    }

    _onWillUnmount() {
        if (this._moveEndTimer) clearTimeout(this._moveEndTimer);
        if (this.map) {
            this.map.remove();
            this.map = null;
        }
    }

    // =============================================
    // 資料載入
    // =============================================

    async _loadInitialData() {
        // 統計
        const Photo = "supervision.photo";
        this.state.totalPhotos = await this.orm.searchCount(Photo, [["active", "=", true]]);
        this.state.gpsPhotos = await this.orm.searchCount(Photo, [
            ["active", "=", true],
            ["latitude", "!=", 0],
            ["longitude", "!=", 0],
        ]);

        // 工程案件
        const projects = await this.orm.searchRead(
            "project.project",
            [],
            ["id", "name", "latitude", "longitude"],
            { limit: 500 }
        );
        this.state.projects = projects;

        // 篩選選項
        const fieldsInfo = await this.orm.call(Photo, "fields_get", [
            ["source_model", "category", "construction_phase"],
        ]);
        this.state.filterOptions = {
            source_model: fieldsInfo.source_model?.selection || [],
            category: fieldsInfo.category?.selection || [],
            construction_phase: fieldsInfo.construction_phase?.selection || [],
        };
    }

    async _loadMarkers() {
        const domain = this._buildDomain(true);
        const photos = await this.orm.searchRead(
            "supervision.photo",
            domain,
            ["id", "name", "latitude", "longitude", "project_id", "source_model", "category", "shot_date", "attachment_id"],
            { limit: 5000, order: "shot_date desc" }
        );

        this.state.filteredCount = photos.length;
        this._renderMarkers(photos);

        if (photos.length > 0) {
            this._fitAllMarkers();
        }
    }

    async _loadAreaPhotos(reset) {
        if (reset) {
            this.state.areaPhotos = [];
            this.state.areaTotal = 0;
        }
        if (!this.map) return;

        const bounds = this.map.getBounds();
        const domain = this._buildDomain(true);
        domain.push(
            ["latitude", ">=", bounds.getSouth()],
            ["latitude", "<=", bounds.getNorth()],
            ["longitude", ">=", bounds.getWest()],
            ["longitude", "<=", bounds.getEast()]
        );

        const offset = reset ? 0 : this.state.areaPhotos.length;
        const limit = 30;

        this.state.areaTotal = await this.orm.searchCount("supervision.photo", domain);
        const photos = await this.orm.searchRead(
            "supervision.photo",
            domain,
            ["id", "name", "latitude", "longitude", "project_id", "source_model", "shot_date", "attachment_id", "location_description"],
            { limit, offset, order: "shot_date desc" }
        );

        if (reset) {
            this.state.areaPhotos = photos;
        } else {
            this.state.areaPhotos = [...this.state.areaPhotos, ...photos];
        }
    }

    async _loadNearbyPhotos(lat, lng, radius) {
        this.state.nearbyPhotos = [];
        this.state.nearbyStatus = "searching";

        const latDelta = radius / 111.0;
        const lngDelta = radius / (111.0 * Math.cos((lat * Math.PI) / 180));

        const domain = [
            ["active", "=", true],
            ["latitude", ">=", lat - latDelta],
            ["latitude", "<=", lat + latDelta],
            ["longitude", ">=", lng - lngDelta],
            ["longitude", "<=", lng + lngDelta],
            ["latitude", "!=", 0],
            ["longitude", "!=", 0],
        ];

        const photos = await this.orm.searchRead(
            "supervision.photo",
            domain,
            ["id", "name", "latitude", "longitude", "project_id", "source_model", "shot_date", "attachment_id", "location_description"],
            { limit: 200 }
        );

        // Haversine 距離計算 + 排序
        const results = [];
        for (const p of photos) {
            const d = this._haversine(lat, lng, p.latitude, p.longitude);
            if (d <= radius) {
                p._distance = d;
                p._distanceLabel = d < 1 ? `${Math.round(d * 1000)} 公尺` : `${d.toFixed(1)} 公里`;
                results.push(p);
            }
        }
        results.sort((a, b) => a._distance - b._distance);

        this.state.nearbyPhotos = results.slice(0, 30);
        this.state.nearbyStatus = results.length > 0 ? "found" : "empty";
    }

    // =============================================
    // 地圖初始化
    // =============================================

    _initMap() {
        const el = document.querySelector(".photo-map-container");
        if (!el || !window.L) return;

        this.map = L.map(el, {
            center: [23.5, 120.5],
            zoom: 8,
            zoomControl: false,
        });

        L.control.zoom({ position: "topright" }).addTo(this.map);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap",
            maxZoom: 19,
        }).addTo(this.map);

        // MarkerCluster
        this.markerCluster = L.markerClusterGroup({
            maxClusterRadius: 50,
            showCoverageOnHover: false,
            chunkedLoading: true,
            iconCreateFunction: (cluster) => {
                const count = cluster.getChildCount();
                const size = count < 10 ? "small" : count < 50 ? "medium" : "large";
                return L.divIcon({
                    html: `<div class="pm-cluster pm-cluster-${size}">${count}</div>`,
                    className: "pm-cluster-wrapper",
                    iconSize: L.point(44, 44),
                });
            },
        });
        this.map.addLayer(this.markerCluster);

        // moveend → 更新區域照片
        this.map.on("moveend", () => {
            if (this._moveEndTimer) clearTimeout(this._moveEndTimer);
            this._moveEndTimer = setTimeout(() => {
                if (this.state.activeTab === "area") {
                    this._loadAreaPhotos(true);
                }
            }, 600);
        });
    }

    // =============================================
    // Marker 管理
    // =============================================

    _renderMarkers(photos) {
        if (!this.markerCluster) return;
        this.markerCluster.clearLayers();

        const markers = [];
        for (const p of photos) {
            if (!p.latitude || !p.longitude) continue;

            const color = SOURCE_COLORS[p.source_model] || SOURCE_COLORS.other;
            const icon = L.divIcon({
                className: "pm-marker-wrapper",
                html: `<div class="pm-marker-dot" style="background:${color}"><i class="fa fa-camera"></i></div>`,
                iconSize: [30, 38],
                iconAnchor: [15, 38],
                popupAnchor: [0, -40],
            });

            const marker = L.marker([p.latitude, p.longitude], { icon });

            const thumbUrl = p.attachment_id
                ? `/web/image/ir.attachment/${p.attachment_id[0]}/datas/100x100?crop=true`
                : "";
            const sourceLabel = SOURCE_LABELS[p.source_model] || "";
            const sourceColor = SOURCE_COLORS[p.source_model] || "#6b7280";
            const projectName = p.project_id ? p.project_id[1] : "";

            marker.bindPopup(
                () =>
                    `<div class="pm-popup">` +
                    (thumbUrl
                        ? `<img src="${thumbUrl}" class="pm-popup-img" loading="lazy"/>`
                        : `<div class="pm-popup-img pm-popup-placeholder"><i class="fa fa-image"></i></div>`) +
                    `<div class="pm-popup-info">` +
                    `<div class="pm-popup-name">${this._esc(p.name || "未命名")}</div>` +
                    `<div class="pm-popup-project"><i class="fa fa-building-o"></i> ${this._esc(projectName)}</div>` +
                    (sourceLabel
                        ? `<div><span class="pm-source-badge" style="background:${sourceColor}">${sourceLabel}</span></div>`
                        : "") +
                    (p.shot_date ? `<div class="pm-popup-date"><i class="fa fa-calendar"></i> ${p.shot_date}</div>` : "") +
                    `<a href="/odoo/supervision-photo/${p.id}" class="pm-popup-link" target="_blank"><i class="fa fa-external-link"></i> 開啟</a>` +
                    `</div></div>`,
                { maxWidth: 360, className: "pm-popup-container" }
            );

            marker._photoId = p.id;
            markers.push(marker);
        }

        this.markerCluster.addLayers(markers);
    }

    _fitAllMarkers() {
        if (this.markerCluster && this.markerCluster.getLayers().length > 0) {
            this.map.fitBounds(this.markerCluster.getBounds(), { padding: [50, 50] });
        }
    }

    // =============================================
    // 使用者定位
    // =============================================

    locateMe() {
        if (!navigator.geolocation) {
            this.state.nearbyStatus = "unsupported";
            return;
        }

        this.state.locating = true;
        this.state.nearbyStatus = "locating";

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                this.state.locating = false;
                this.userLat = pos.coords.latitude;
                this.userLng = pos.coords.longitude;

                this._showUserLocation(this.userLat, this.userLng);
                this.map.flyTo([this.userLat, this.userLng], 15);

                this.switchTab("nearby");
                this._loadNearbyPhotos(this.userLat, this.userLng, this.state.nearbyRadius);
            },
            (err) => {
                this.state.locating = false;
                if (err.code === err.PERMISSION_DENIED) {
                    this.state.nearbyStatus = "denied";
                } else if (err.code === err.POSITION_UNAVAILABLE) {
                    this.state.nearbyStatus = "unavailable";
                } else {
                    this.state.nearbyStatus = "timeout";
                }
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    _showUserLocation(lat, lng) {
        if (this.userMarker) this.map.removeLayer(this.userMarker);
        if (this.userCircle) this.map.removeLayer(this.userCircle);

        this.userMarker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: "pm-user-wrapper",
                html: '<div class="pm-user-dot"></div><div class="pm-user-pulse"></div>',
                iconSize: [20, 20],
                iconAnchor: [10, 10],
            }),
            zIndexOffset: 1000,
        }).addTo(this.map);
        this.userMarker.bindPopup("<b>我的位置</b>");

        this.userCircle = L.circle([lat, lng], {
            radius: this.state.nearbyRadius * 1000,
            color: "#3b82f6",
            fillColor: "#3b82f6",
            fillOpacity: 0.08,
            weight: 2,
            dashArray: "6, 6",
        }).addTo(this.map);
    }

    // =============================================
    // UI 事件
    // =============================================

    switchTab(tab) {
        this.state.activeTab = tab;
        if (tab === "area") {
            this._loadAreaPhotos(true);
        }
    }

    togglePanel() {
        this.state.panelOpen = !this.state.panelOpen;
    }

    applyFilters() {
        this._loadMarkers();
    }

    resetFilters() {
        this.state.filters = {
            project_id: false,
            source_model: "",
            category: "",
            construction_phase: "",
            date_from: "",
            date_to: "",
        };
        this._loadMarkers();
    }

    fitAll() {
        this._fitAllMarkers();
    }

    loadMoreArea() {
        this._loadAreaPhotos(false);
    }

    setRadius(radius) {
        this.state.nearbyRadius = radius;
        if (this.userCircle) {
            this.userCircle.setRadius(radius * 1000);
        }
        if (this.userLat) {
            this._loadNearbyPhotos(this.userLat, this.userLng, radius);
        }
    }

    flyToPhoto(photo) {
        if (photo.latitude && photo.longitude) {
            this.map.flyTo([photo.latitude, photo.longitude], 17);
            // 嘗試打開對應 popup
            this.markerCluster.eachLayer((layer) => {
                if (layer._photoId === photo.id) {
                    setTimeout(() => layer.openPopup(), 500);
                }
            });
        }
    }

    openPhoto(photoId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "supervision.photo",
            res_id: photoId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    /**
     * 切換到標準 Odoo 視圖（列表/看板/日曆）
     * 使用原始的 supervision_photo_action
     */
    switchView(viewType) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "工程照片",
            res_model: "supervision.photo",
            views: [
                [false, "kanban"],
                [false, "list"],
                [false, "form"],
                [false, "calendar"],
            ],
            view_mode: `${viewType},kanban,list,form,calendar`,
            target: "current",
        });
    }

    onFilterChange(field, ev) {
        const val = ev.target.value;
        if (field === "project_id") {
            this.state.filters.project_id = val ? parseInt(val) : false;
        } else {
            this.state.filters[field] = val;
        }
    }

    // =============================================
    // 工具
    // =============================================

    _buildDomain(requireGps) {
        const domain = [["active", "=", true]];
        if (requireGps) {
            domain.push(["latitude", "!=", 0], ["longitude", "!=", 0]);
        }
        const f = this.state.filters;
        if (f.project_id) domain.push(["project_id", "=", f.project_id]);
        if (f.source_model) domain.push(["source_model", "=", f.source_model]);
        if (f.category) domain.push(["category", "=", f.category]);
        if (f.construction_phase) domain.push(["construction_phase", "=", f.construction_phase]);
        if (f.date_from) domain.push(["shot_date", ">=", f.date_from]);
        if (f.date_to) domain.push(["shot_date", "<=", f.date_to]);
        return domain;
    }

    _haversine(lat1, lng1, lat2, lng2) {
        const R = 6371;
        const dLat = ((lat2 - lat1) * Math.PI) / 180;
        const dLng = ((lng2 - lng1) * Math.PI) / 180;
        const a =
            Math.sin(dLat / 2) ** 2 +
            Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
        return R * 2 * Math.asin(Math.sqrt(a));
    }

    _esc(str) {
        const d = document.createElement("div");
        d.textContent = str || "";
        return d.innerHTML;
    }

    getSourceLabel(src) {
        return SOURCE_LABELS[src] || src || "";
    }

    getSourceColor(src) {
        return SOURCE_COLORS[src] || "#6b7280";
    }

    getThumbnailUrl(photo) {
        return photo.attachment_id
            ? `/web/image/ir.attachment/${photo.attachment_id[0]}/datas/80x80?crop=true`
            : "";
    }

    getProjectName(photo) {
        return photo.project_id ? photo.project_id[1] : "";
    }
}

PhotoMapAction.template = "construction_geoengine.PhotoMapAction";

registry.category("actions").add("photo_map_action", PhotoMapAction);
