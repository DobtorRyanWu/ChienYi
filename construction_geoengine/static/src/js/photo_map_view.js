/** @odoo-module */

import { Component, useRef, onMounted, onPatched, onWillUnmount, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { RelationalModel } from "@web/model/relational_model/relational_model";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";

// 來源分類色彩
const SOURCE_COLORS = {
    daily_log: "#3b82f6",
    inspection: "#22c55e",
    defect: "#ef4444",
    test: "#f59e0b",
    acceptance: "#8b5cf6",
    notification: "#06b6d4",
    other: "#6b7280",
};

const SOURCE_LABELS = {
    daily_log: "施工日誌",
    inspection: "自主檢查",
    defect: "缺失改善",
    test: "檢試驗",
    acceptance: "驗收",
    notification: "通報單",
    other: "其他",
};

const MARKERS_LIMIT = 5000;
const AREA_LIST_LIMIT = 500;
const NEARBY_LIST_LIMIT = 50;

// Haversine 公式計算兩點距離(km)
function haversineKm(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
              Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

// =============================================
// Controller
// =============================================
class PhotoMapController extends Component {
    static template = "construction_geoengine.PhotoMapView";
    static components = { Layout, SearchBar };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.searchBarToggler = useSearchBarToggler();
        this.mapContainerRef = useRef("mapContainer");

        // Odoo 原生 control panel 透過 CSS 隱藏(不用 display.controlPanel=false,
        // 因為那會連 search view 初始化也跳過,導致 switchView 壞掉)

        this.state = useState({
            totalPhotos: 0,
            gpsPhotos: 0,
            filteredCount: 0,
            projects: [],
            tags: [],
            filterOptions: {},
            filters: {
                project_id: false,
                source_model: "",
                tag_id: false,
                category: "",
                construction_phase: "",
                date_from: "",
                date_to: "",
            },
            // 面板
            panelOpen: true,
            activeTab: "area",
            // Chip popover
            openChip: "",
            // 附近
            radius: 1,
            nearbyStatus: "",
            nearbyPhotos: [],
            userLat: null,
            userLng: null,
            // 區域
            areaPhotos: [],
            // 此地點(點 cluster 後)
            locationPhotos: [],
        });

        this.map = null;
        this.markerCluster = null;
        this.markersById = {};
        this.allPhotos = [];
        this.userMarker = null;
        this._domainChanged = false;

        onMounted(async () => {
            // 隱藏 Odoo 原生 control panel(同 view 的兄弟節點)
            const contentEl = this.mapContainerRef.el?.closest(".o_content");
            const cp = contentEl?.previousElementSibling;
            if (cp && cp.classList.contains("o_control_panel")) {
                cp.style.display = "none";
                this._hiddenControlPanel = cp;
            }

            // 改 SearchBar placeholder 為「搜尋工程照片」
            const setPlaceholder = () => {
                const input = contentEl?.querySelector(
                    ".pm-searchbar-wrap .o_searchview_input"
                );
                if (input) input.placeholder = "搜尋工程照片";
            };
            setPlaceholder();
            setTimeout(setPlaceholder, 100);
            setTimeout(setPlaceholder, 500);

            await this._loadInitialData();
            this._initMap();
            window._photoMapView = this;
            await this._loadMarkers();
        });

        onWillUpdateProps((nextProps) => {
            if (JSON.stringify(nextProps.domain) !== JSON.stringify(this.props.domain)) {
                this._domainChanged = true;
            }
        });

        onPatched(() => {
            if (this._domainChanged) {
                this._domainChanged = false;
                this._loadMarkers();
            }
        });

        onWillUnmount(() => {
            if (window._photoMapView === this) delete window._photoMapView;
            // 復原被隱藏的 control panel
            if (this._hiddenControlPanel) {
                this._hiddenControlPanel.style.display = "";
                this._hiddenControlPanel = null;
            }
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    // =============================================
    // 初始資料
    // =============================================
    async _loadInitialData() {
        const Photo = "supervision.photo";
        this.state.totalPhotos = await this.orm.searchCount(Photo, [["active", "=", true]]);
        this.state.gpsPhotos = await this.orm.searchCount(Photo, [
            ["active", "=", true], ["latitude", "!=", 0], ["longitude", "!=", 0],
        ]);

        const projects = await this.orm.searchRead(
            "supervision.project", [], ["id", "name", "latitude", "longitude"],
            { limit: 500, order: "name" }
        );
        this.state.projects = projects;

        // 載入標籤(supervision.photo.tag,Many2many 欄位 tag_ids)
        const tags = await this.orm.searchRead(
            "supervision.photo.tag", [["active", "=", true]],
            ["id", "name", "color"],
            { limit: 500, order: "sequence, name" }
        );
        this.state.tags = tags;

        const fieldsInfo = await this.orm.call(Photo, "fields_get", [
            ["source_model", "category", "construction_phase"],
        ]);
        this.state.filterOptions = {
            source_model: fieldsInfo.source_model?.selection || [],
            category: fieldsInfo.category?.selection || [],
            construction_phase: fieldsInfo.construction_phase?.selection || [],
        };
    }

    // =============================================
    // 地圖初始化
    // =============================================
    _initMap() {
        const el = this.mapContainerRef.el;
        if (!el || !window.L) return;

        this.map = L.map(el, { center: [23.5, 120.5], zoom: 8, zoomControl: false });
        L.control.zoom({ position: "bottomleft" }).addTo(this.map);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap", maxZoom: 19,
        }).addTo(this.map);

        this.markerCluster = L.markerClusterGroup({
            maxClusterRadius: (zoom) => (zoom >= 17 ? 1 : 50),
            showCoverageOnHover: false,
            chunkedLoading: true,
            spiderfyOnMaxZoom: false,     // Google Photos 風:不螺旋展開
            zoomToBoundsOnClick: false,   // 自己 handle
            iconCreateFunction: (cluster) => {
                const count = cluster.getChildCount();
                const size = count < 10 ? "small" : count < 50 ? "medium" : "large";
                return L.divIcon({
                    html: `<div class="pm-cluster pm-cluster-${size}">${count}</div>`,
                    className: "pm-cluster-wrapper", iconSize: L.point(44, 44),
                });
            },
        });
        this.map.addLayer(this.markerCluster);

        // 點 cluster:同座標 → flyTo + popup 預覽;不同座標 → fitBounds zoom
        this.markerCluster.on("clusterclick", (ev) => {
            const cluster = ev.layer;
            const markers = cluster.getAllChildMarkers();
            if (markers.length === 0) return;
            const first = markers[0].getLatLng();
            const eps = 1e-5;
            const allSame = markers.every((m) => {
                const ll = m.getLatLng();
                return Math.abs(ll.lat - first.lat) < eps
                    && Math.abs(ll.lng - first.lng) < eps;
            });
            if (allSame) {
                const photos = markers.map((m) => m._photoData);
                this.state.locationPhotos = photos;
                // 飛到該點 + zoom in
                const targetZoom = Math.max(this.map.getZoom(), 18);
                this.map.flyTo([first.lat, first.lng], targetZoom, { duration: 0.5 });
                // 飛完後顯示 popup 預覽
                setTimeout(() => {
                    L.popup({
                        maxWidth: 280,
                        className: "pm-popup-container",
                        offset: [0, -10],
                        autoPan: true,
                    })
                        .setLatLng([first.lat, first.lng])
                        .setContent(this._buildLocationPopupHtml(photos))
                        .openOn(this.map);
                }, 520);
            } else {
                this.map.fitBounds(cluster.getBounds(), { padding: [50, 50] });
            }
        });

        // 區域 tab:地圖移動後 refresh
        this.map.on("moveend", () => {
            if (this.state.activeTab === "area") {
                this._refreshAreaPhotos();
            }
        });

        // 點地圖空白處關閉 chip popover
        this.map.on("click", () => {
            if (this.state.openChip) this.state.openChip = "";
        });
    }

    // =============================================
    // Markers
    // =============================================
    async _loadMarkers() {
        const domain = this._buildDomain(true);
        const photos = await this.orm.searchRead(
            "supervision.photo", domain,
            ["id", "name", "latitude", "longitude", "project_id", "source_model",
             "shot_date", "attachment_id", "location_description"],
            { limit: MARKERS_LIMIT, order: "shot_date desc" }
        );
        this.state.filteredCount = photos.length;
        this.allPhotos = photos;
        // markers 重載 → 此地點資料可能失效,清空並切離 location tab
        this.state.locationPhotos = [];
        if (this.state.activeTab === "location") {
            this.state.activeTab = "area";
        }
        this._renderMarkers(photos);
        if (photos.length > 0) {
            this._fitAllMarkers();
        }
        // 依當前 tab 刷新列表
        if (this.state.activeTab === "area") {
            this._refreshAreaPhotos();
        }
        if (this.state.activeTab === "nearby" && this.state.userLat !== null) {
            this._computeNearby();
        }
    }

    _renderMarkers(photos) {
        if (!this.markerCluster) return;
        this.markerCluster.clearLayers();
        this.markersById = {};

        const markers = [];
        for (const p of photos) {
            if (!p.latitude || !p.longitude) continue;

            const color = SOURCE_COLORS[p.source_model] || SOURCE_COLORS.other;
            const icon = L.divIcon({
                className: "pm-marker-wrapper",
                html: `<div class="pm-marker-dot" style="background:${color}"><i class="fa fa-camera"></i></div>`,
                iconSize: [30, 38], iconAnchor: [15, 38], popupAnchor: [0, -36],
            });

            const marker = L.marker([p.latitude, p.longitude], { icon });
            marker._photoData = p;
            marker.bindPopup(() => this._buildPopupHtml(p), {
                maxWidth: 240, className: "pm-popup-container",
            });
            markers.push(marker);
            this.markersById[p.id] = marker;
        }
        this.markerCluster.addLayers(markers);
    }

    _buildLocationPopupHtml(photos) {
        const n = photos.length;
        const previewCount = Math.min(4, n);
        let thumbsHtml = "";
        for (let i = 0; i < previewCount; i++) {
            const p = photos[i];
            const url = this.getThumbnailUrl(p);
            thumbsHtml += url
                ? `<img src="${url}" class="pm-loc-thumb" loading="lazy" alt="" onclick="window._photoMapView.openPhoto(${p.id}); return false;"/>`
                : `<div class="pm-loc-thumb pm-loc-thumb-ph"><i class="fa fa-image"></i></div>`;
        }
        return `<div class="pm-loc-popup">` +
            `<div class="pm-loc-popup-title"><i class="fa fa-map-marker"></i> 此地點 <strong>${n}</strong> 張照片</div>` +
            `<div class="pm-loc-popup-grid">${thumbsHtml}</div>` +
            `<a href="#" class="pm-popup-btn primary" onclick="window._photoMapView.openLocationPanel(); return false;">` +
                `<i class="fa fa-th"></i> 看全部 ${n} 張</a>` +
        `</div>`;
    }

    openLocationPanel() {
        this.state.activeTab = "location";
        this.state.panelOpen = true;
        if (this.map) this.map.closePopup();
    }

    _buildPopupHtml(p) {
        const thumbUrl = this.getThumbnailLargeUrl(p);
        const projectName = p.project_id ? p.project_id[1] : "";
        const sourceLabel = SOURCE_LABELS[p.source_model] || "";
        const navUrl = `https://www.openstreetmap.org/directions?to=${p.latitude},${p.longitude}`;

        let meta = "";
        if (projectName) meta += `<div><i class="fa fa-building-o"></i> ${this._esc(projectName)}</div>`;
        if (p.shot_date) meta += `<div><i class="fa fa-calendar"></i> ${this._esc(p.shot_date)}</div>`;
        if (sourceLabel) meta += `<div><i class="fa fa-tag"></i> ${this._esc(sourceLabel)}</div>`;
        if (p.location_description) meta += `<div><i class="fa fa-map-marker"></i> ${this._esc(p.location_description)}</div>`;

        const thumbHtml = thumbUrl
            ? `<img src="${thumbUrl}" class="pm-popup-img" loading="lazy" alt=""/>`
            : `<div class="pm-popup-img pm-popup-placeholder"><i class="fa fa-image"></i></div>`;

        return `<div class="pm-popup">` +
            thumbHtml +
            `<div class="pm-popup-info">` +
                `<div class="pm-popup-name">${this._esc(p.name || "未命名")}</div>` +
                `<div class="pm-popup-meta">${meta}</div>` +
                `<div class="pm-popup-actions">` +
                    `<a href="#" class="pm-popup-btn primary" onclick="window._photoMapView.openPhoto(${p.id}); return false;">` +
                        `<i class="fa fa-eye"></i> 檢視</a>` +
                    `<a href="${navUrl}" target="_blank" rel="noopener" class="pm-popup-btn">` +
                        `<i class="fa fa-location-arrow"></i> 導航</a>` +
                `</div>` +
            `</div></div>`;
    }

    _fitAllMarkers() {
        if (this.markerCluster && this.markerCluster.getLayers().length > 0) {
            this.map.fitBounds(this.markerCluster.getBounds(), { padding: [50, 50] });
        }
    }

    // =============================================
    // 面板 / Tab
    // =============================================
    togglePanel() {
        this.state.panelOpen = !this.state.panelOpen;
        // map 永遠全寬,面板 absolute overlay,不需要 invalidateSize
    }

    switchTab(tab) {
        this.state.activeTab = tab;
        if (tab === "area") {
            this._refreshAreaPhotos();
        } else if (tab === "nearby" && this.state.userLat !== null) {
            this._computeNearby();
        }
    }

    // =============================================
    // Chip 篩選(懸浮列)
    // =============================================
    toggleChip(name) {
        this.state.openChip = this.state.openChip === name ? "" : name;
    }

    selectChipValue(name, value) {
        if (name === "project_id" || name === "tag_id") {
            this.state.filters[name] = value ? parseInt(value, 10) : false;
        } else {
            this.state.filters[name] = value;
        }
        this.state.openChip = "";
        this._loadMarkers();
    }

    clearChip(name, ev) {
        if (ev) ev.stopPropagation();
        if (name === "project_id" || name === "tag_id") {
            this.state.filters[name] = false;
        } else {
            this.state.filters[name] = "";
        }
        this._loadMarkers();
    }

    clearAllFilters() {
        this.state.filters = {
            project_id: false,
            source_model: "",
            tag_id: false,
            category: "",
            construction_phase: "",
            date_from: "",
            date_to: "",
        };
        this.state.openChip = "";
        this._loadMarkers();
    }

    onDateFilterChange(field, ev) {
        this.state.filters[field] = ev.target.value;
        this._loadMarkers();
    }

    // Chip 顯示 label
    getChipLabel(name) {
        const f = this.state.filters;
        if (name === "project_id") {
            if (!f.project_id) return "全部工程";
            const p = this.state.projects.find((x) => x.id === f.project_id);
            return p ? p.name : "工程";
        }
        if (name === "source_model") {
            if (!f.source_model) return "全部來源";
            const opt = (this.state.filterOptions.source_model || []).find((o) => o[0] === f.source_model);
            return opt ? opt[1] : "來源";
        }
        if (name === "tag_id") {
            if (!f.tag_id) return "全部標籤";
            const t = this.state.tags.find((x) => x.id === f.tag_id);
            return t ? t.name : "標籤";
        }
        if (name === "category") {
            if (!f.category) return "全部分類";
            const opt = (this.state.filterOptions.category || []).find((o) => o[0] === f.category);
            return opt ? opt[1] : "分類";
        }
        if (name === "construction_phase") {
            if (!f.construction_phase) return "全部階段";
            const opt = (this.state.filterOptions.construction_phase || []).find((o) => o[0] === f.construction_phase);
            return opt ? opt[1] : "階段";
        }
        if (name === "date") {
            if (!f.date_from && !f.date_to) return "拍攝日期";
            return `${f.date_from || "…"} ~ ${f.date_to || "…"}`;
        }
        return "";
    }

    isChipActive(name) {
        const f = this.state.filters;
        if (name === "project_id" || name === "tag_id") return !!f[name];
        if (name === "date") return !!(f.date_from || f.date_to);
        return !!f[name];
    }

    hasAnyFilter() {
        const f = this.state.filters;
        return !!(f.project_id || f.source_model || f.tag_id || f.category
            || f.construction_phase || f.date_from || f.date_to);
    }

    // =============================================
    // 附近 Tab
    // =============================================
    setRadius(r) {
        this.state.radius = r;
        if (this.state.userLat !== null) {
            this._computeNearby();
        }
    }

    locateMe() {
        if (!navigator.geolocation) {
            this.state.nearbyStatus = "瀏覽器不支援定位";
            return;
        }
        this.state.nearbyStatus = "正在取得位置...";
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                this.state.userLat = pos.coords.latitude;
                this.state.userLng = pos.coords.longitude;
                this.state.nearbyStatus = "";
                this._drawUserMarker(pos.coords.latitude, pos.coords.longitude);
                this.map.flyTo([pos.coords.latitude, pos.coords.longitude], 15, { duration: 0.6 });
                this._computeNearby();
            },
            () => { this.state.nearbyStatus = "無法取得位置"; },
            { enableHighAccuracy: true, timeout: 10000 }
        );
    }

    _computeNearby() {
        const lat = this.state.userLat;
        const lng = this.state.userLng;
        if (lat === null) return;
        const radius = this.state.radius;

        const results = [];
        for (const p of this.allPhotos) {
            if (!p.latitude || !p.longitude) continue;
            const d = haversineKm(lat, lng, p.latitude, p.longitude);
            if (d <= radius) {
                results.push({ ...p, distance_km: d });
            }
        }
        results.sort((a, b) => a.distance_km - b.distance_km);
        this.state.nearbyPhotos = results.slice(0, NEARBY_LIST_LIMIT);
        if (results.length === 0) {
            this.state.nearbyStatus = `${radius}km 範圍內沒有照片`;
        } else {
            this.state.nearbyStatus = `找到 ${results.length} 張,顯示前 ${this.state.nearbyPhotos.length} 張`;
        }
    }

    _drawUserMarker(lat, lng) {
        if (this.userMarker) this.map.removeLayer(this.userMarker);
        this.userMarker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: "pm-user-wrapper",
                html: '<div class="pm-user-dot"></div>',
                iconSize: [16, 16], iconAnchor: [8, 8],
            }),
            zIndexOffset: 1000,
        }).addTo(this.map).bindPopup("<b>我的位置</b>");
    }

    // =============================================
    // 區域 Tab (Google Photos 風 gallery)
    // =============================================
    _refreshAreaPhotos() {
        if (!this.map) return;
        const bounds = this.map.getBounds();
        const results = [];
        for (const p of this.allPhotos) {
            if (!p.latitude || !p.longitude) continue;
            if (bounds.contains([p.latitude, p.longitude])) {
                results.push(p);
            }
        }
        this.state.areaPhotos = results.slice(0, AREA_LIST_LIMIT);
    }

    // 依日期分群(給 gallery 用)
    groupByDate(photos) {
        const map = new Map();
        for (const p of photos) {
            const key = p.shot_date || "unknown";
            if (!map.has(key)) map.set(key, []);
            map.get(key).push(p);
        }
        return Array.from(map.entries()).map(([key, items]) => ({ key, items }));
    }

    formatDateHeader(key) {
        if (!key || key === "unknown") return "未知日期";
        const parts = key.split("-");
        if (parts.length === 3) {
            return `${parts[0]} 年 ${parseInt(parts[1], 10)} 月 ${parseInt(parts[2], 10)} 日`;
        }
        return key;
    }

    // =============================================
    // 通用:聚焦照片
    // =============================================
    focusPhoto(photo) {
        if (photo.latitude && photo.longitude) {
            this.map.flyTo([photo.latitude, photo.longitude], 17, { duration: 0.6 });
            const marker = this.markersById[photo.id];
            if (marker) setTimeout(() => marker.openPopup(), 700);
        } else {
            this.openPhoto(photo.id);
        }
    }

    // =============================================
    // 右下浮動按鈕
    // =============================================
    locateMeOnMap() {
        if (!navigator.geolocation) {
            alert("瀏覽器不支援定位");
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                this.state.userLat = pos.coords.latitude;
                this.state.userLng = pos.coords.longitude;
                this._drawUserMarker(pos.coords.latitude, pos.coords.longitude);
                this.map.flyTo([pos.coords.latitude, pos.coords.longitude], 16, { duration: 0.6 });
            },
            () => alert("無法取得位置"),
            { enableHighAccuracy: true, timeout: 10000 }
        );
    }

    fitAll() { this._fitAllMarkers(); }

    // =============================================
    // 動作
    // =============================================
    openPhoto(photoId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "supervision.photo",
            res_id: photoId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    createPhoto() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "supervision.photo",
            views: [[false, "form"]],
            target: "current",
        });
    }

    // =============================================
    // View Switcher(懸浮,硬編碼 3 種)
    // =============================================
    get viewSwitcherEntries() {
        return [
            { type: "kanban",   icon: "fa-th-large", label: "看板" },
            { type: "list",     icon: "fa-list-ul",  label: "列表" },
            { type: "calendar", icon: "fa-calendar", label: "行事曆" },
        ];
    }

    switchViewType(type) {
        this.actionService.switchView(type);
    }

    get viewTitle() {
        return (this.env.config && this.env.config.displayName) || "工程照片";
    }

    // =============================================
    // Domain 建構
    // =============================================
    _buildDomain(requireGps) {
        const domain = [...(this.props.domain || []), ["active", "=", true]];
        if (requireGps) {
            domain.push(["latitude", "!=", 0], ["longitude", "!=", 0]);
        }
        const f = this.state.filters;
        if (f.project_id) domain.push(["project_id", "=", f.project_id]);
        if (f.source_model) domain.push(["source_model", "=", f.source_model]);
        if (f.tag_id) domain.push(["tag_ids", "in", [f.tag_id]]);
        if (f.category) domain.push(["category", "=", f.category]);
        if (f.construction_phase) domain.push(["construction_phase", "=", f.construction_phase]);
        if (f.date_from) domain.push(["shot_date", ">=", f.date_from]);
        if (f.date_to) domain.push(["shot_date", "<=", f.date_to]);
        return domain;
    }

    // =============================================
    // 輔助
    // =============================================
    _esc(str) {
        const d = document.createElement("div");
        d.textContent = str || "";
        return d.innerHTML;
    }

    formatDistance(km) {
        if (km === undefined || km === null) return "";
        return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(2)} km`;
    }

    getSourceLabel(src) { return SOURCE_LABELS[src] || src || ""; }
    getSourceColor(src) { return SOURCE_COLORS[src] || "#6b7280"; }

    getThumbnailUrl(photo) {
        return photo.attachment_id
            ? `/web/image/ir.attachment/${photo.attachment_id[0]}/datas/200x200?crop=true`
            : "";
    }

    getThumbnailLargeUrl(photo) {
        return photo.attachment_id
            ? `/web/image/ir.attachment/${photo.attachment_id[0]}/datas/320x200?crop=true`
            : "";
    }
}

// =============================================
// ArchParser
// =============================================
class PhotoMapArchParser {
    parse(xmlDoc, models, modelName) {
        return {};
    }
}

// =============================================
// 註冊 View Type
// =============================================
registry.category("views").add("photo_map", {
    type: "photo_map",
    display_name: _t("地圖"),
    icon: "fa fa-map-marker",
    multiRecord: true,
    Controller: PhotoMapController,
    Model: RelationalModel,
    ArchParser: PhotoMapArchParser,

    props(genericProps, view) {
        const { ArchParser } = view;
        const { arch, relatedModels, resModel } = genericProps;
        const archInfo = new ArchParser().parse(arch, relatedModels, resModel);

        return {
            ...genericProps,
            Model: view.Model,
            archInfo,
        };
    },
});