/** @odoo-module **/
// 標案地圖（合約 §0b-33）：照雛型——OSM 底圖、有座標的工程畫標記（紅＝落後、綠＝超前、灰＝未建進度表）＋標籤，
// 右側每工程一張小卡；沒座標的工程只列在右側並標「未設座標」。點標記或小卡進單一工程頁。
// 資料：核心 search_read 拿座標（快），只對有座標的工程再用 web_search_read 讀 dash_* 指標；沒有新的 RPC。
// 安全：標記標籤與小卡全部用 DOM 節點／OWL 模板組（不拼字串進 innerHTML）。
// 瓦片請求只帶站台 origin 當 Referer（OSM 規定要有；不帶路徑，看不到工程 id），見 TILE_REFERRER_POLICY。
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { Layout } from "@web/search/layout";
import {
    DEFAULT_DOMAIN, LOAD_FAILED_MESSAGE, MAP_PAGE_TAG, PROJECT_MODEL, ROW_ORDER, ROW_SPECIFICATION,
    formatDateLabel, formatPercent, loadSelectionLabels, openProjectPage, shapeRow,
} from "./dash_common";

const COORD_FIELDS = ["code", "name", "latitude", "longitude"];
const TAIWAN_CENTER = [23.7, 121.0];
const TAIWAN_ZOOM = 8;
const MAX_ZOOM = 19;
const FIT_PADDING = [48, 48];
const SINGLE_MARKER_ZOOM = 14;
const OSM_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION = "&copy; OpenStreetMap contributors";
// ⚠️ 不可改成 "no-referrer"：OSM 對「桌面瀏覽器 UA 卻沒帶 Referer」的請求回 HTTP 200 的
// 「403 Access blocked」PNG——Leaflet 當成 tileload 成功，tileerror／下面的 CARTO 備援都不會觸發，
// 整張地圖變成封鎖圖（2026-11-11 實測；headless Chromium 的 UA 不會被擋，所以自動化驗收要用桌面 UA 才看得到）。
// 用瀏覽器標準預設：跨站只送 origin（https://站台/），不送路徑與 #action。
const TILE_REFERRER_POLICY = "strict-origin-when-cross-origin";
// 真的連不到 OSM（斷網、防火牆擋 openstreetmap.org）時的備援底圖：CARTO 淺色，免金鑰、要標註
const FALLBACK_TILE_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png";
const FALLBACK_SUBDOMAINS = "abcd";
const FALLBACK_ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';
const TILE_PROBE_TIMEOUT_MS = 6000;
const MARKER_SIZE = 22;
const MARKER_COLOR = { behind: "o_dash_mk_behind", ahead: "o_dash_mk_ahead", none: "o_dash_mk_none" };

export class CompanyDashboardMap extends Component {
    static template = "construction_company_dashboard.MapPage";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.display = { controlPanel: {} };
        this.mapRef = useRef("map");
        this.map = null;
        this.hasLeaflet = Boolean(window.L);
        this.todayLabel = formatDateLabel();
        this.state = useState({ loading: true, error: false, located: [], unlocated: [], tileError: false, tilesLoaded: 0,
                                fallback: false, tileStatus: null });
        this.tiles = null;
        this.fallbackTried = false;
        if (this.env.config && typeof this.env.config.setDisplayName === "function") {
            this.env.config.setDisplayName("標案地圖");   // 直接開網址時麵包屑不要顯示「未命名的」
        }
        onWillStart(() => this.loadProjects());
        onMounted(() => this.initMap());
        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    async loadProjects() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const labels = await loadSelectionLabels(this.orm);
            const projects = await this.orm.searchRead(PROJECT_MODEL, DEFAULT_DOMAIN, COORD_FIELDS, { order: ROW_ORDER });
            const located = projects.filter((p) => Number(p.latitude) && Number(p.longitude));
            const unlocated = projects.filter((p) => !(Number(p.latitude) && Number(p.longitude)));
            let rows = {};
            if (located.length) {
                // 只對有座標的工程算指標（165 個全算要 8 秒；dev 目前 1 個有座標）
                const result = await this.orm.webSearchRead(PROJECT_MODEL, [["id", "in", located.map((p) => p.id)]], {
                    specification: ROW_SPECIFICATION,
                    limit: located.length,
                    order: ROW_ORDER,
                });
                rows = Object.fromEntries(result.records.map((record) => [record.id, shapeRow(record, labels)]));
            }
            this.state.located = located
                .filter((p) => rows[p.id])
                .map((p) => ({ ...rows[p.id], lat: Number(p.latitude), lng: Number(p.longitude) }));
            this.state.unlocated = unlocated.map((p) => ({ id: p.id, code: p.code || "", name: p.name || "" }));
        } catch (error) {
            console.error("標案地圖讀取失敗", error);
            this.state.error = LOAD_FAILED_MESSAGE;
            this.state.located = [];
            this.state.unlocated = [];
        } finally {
            this.state.loading = false;
        }
    }

    // ── Leaflet ─────────────────────────────────────────────────────────
    initMap() {
        const el = this.mapRef.el;
        if (!el || !window.L) {
            return;
        }
        const L = window.L;
        this.map = L.map(el, { center: TAIWAN_CENTER, zoom: TAIWAN_ZOOM, zoomControl: false });
        L.control.zoom({ position: "bottomright" }).addTo(this.map);
        // 部署方可在系統參數 leaflet.tile_url 換自架瓦片（web_leaflet_lib 放進 session）；沒有就用 OSM
        const tileUrl = session["leaflet.tile_url"] || OSM_TILE_URL;
        const attribution = session["leaflet.copyright"] || OSM_ATTRIBUTION;
        this.tiles = L.tileLayer(tileUrl, { attribution, maxZoom: MAX_ZOOM, referrerPolicy: TILE_REFERRER_POLICY }).addTo(this.map);
        this.tiles.on("tileload", () => { this.state.tilesLoaded += 1; this.state.tileError = false; });
        this.tiles.on("tileerror", (ev) => this.onTileError(ev));
        this.renderMarkers();
        // 容器尺寸是 CSS 給的，掛上去後要重算一次
        setTimeout(() => this.map && this.map.invalidateSize(), 0);
    }

    /** 第一張瓦片就失敗、而且一張都還沒成功：探 HTTP 狀態，換 CARTO 底圖；備援也失敗才顯示「底圖載入失敗」 */
    async onTileError(ev) {
        if (this.state.tilesLoaded || this.fallbackTried || !this.map || !window.L) {
            return;
        }
        this.fallbackTried = true;
        this.state.tileStatus = await this.probeTile(ev && ev.tile && ev.tile.src);
        if (!this.map) {
            return;
        }
        this.map.removeLayer(this.tiles);
        this.tiles = window.L.tileLayer(FALLBACK_TILE_URL, {
            attribution: FALLBACK_ATTRIBUTION, subdomains: FALLBACK_SUBDOMAINS, maxZoom: MAX_ZOOM, referrerPolicy: TILE_REFERRER_POLICY,
        }).addTo(this.map);
        this.tiles.on("tileload", () => { this.state.tilesLoaded += 1; this.state.tileError = false; this.state.fallback = true; });
        this.tiles.on("tileerror", () => { if (!this.state.tilesLoaded) { this.state.tileError = true; } });
    }

    /** 用 fetch 讀同一張瓦片的 HTTP 狀態（img 讀不到狀態碼）；連不上回 "network" */
    async probeTile(url) {
        if (!url) {
            return "unknown";
        }
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), TILE_PROBE_TIMEOUT_MS);
        try {
            const response = await fetch(url, { mode: "cors", cache: "no-store", referrerPolicy: TILE_REFERRER_POLICY, signal: controller.signal });
            return response.status;
        } catch (error) {
            return "network";
        } finally {
            clearTimeout(timer);
        }
    }

    markerClass(row) {
        if (!row.progress.ok || !row.progress.has) {
            return MARKER_COLOR.none;
        }
        return row.progress.behind ? MARKER_COLOR.behind : MARKER_COLOR.ahead;
    }

    /** 標籤的 DOM（textContent，不拼 HTML 字串） */
    _labelElement(row) {
        const box = document.createElement("div");
        box.className = "o_dash_ml";
        const title = document.createElement("b");
        title.textContent = row.name;
        box.appendChild(title);
        const line = document.createElement("span");
        if (row.progress.ok && row.progress.has) {
            const diff = document.createElement("span");
            const tone = row.progress.behind ? "neg" : row.progress.even ? "even" : "pos";
            diff.className = `o_dash_diff o_dash_diff_${tone}`;
            diff.textContent = `${row.progress.behind ? "落後" : row.progress.even ? "持平" : "超前"} ${formatPercent(Math.abs(row.progress.variance))}%`;
            line.appendChild(diff);
        } else {
            const none = document.createElement("span");
            none.className = "o_dash_mute";
            none.textContent = row.progress.ok ? "未建進度表" : row.progress.message;
            line.appendChild(none);
        }
        const stats = document.createElement("span");
        stats.className = "o_dash_mute o_dash_ml_stats";
        const logText = row.log.ok ? `日誌 ${row.log.label}` : `日誌 ${row.log.message}`;
        const defectText = row.defects.ok ? `缺失 ${row.defects.open}` : `缺失 ${row.defects.message}`;
        stats.textContent = `　${logText}・${defectText}`;
        line.appendChild(stats);
        box.appendChild(line);
        return box;
    }

    renderMarkers() {
        if (!this.map || !window.L) {
            return;
        }
        const L = window.L;
        const bounds = [];
        for (const row of this.state.located) {
            const dot = document.createElement("i");
            dot.className = `o_dash_mk_dot ${this.markerClass(row)}`;
            const icon = L.divIcon({
                className: "o_dash_mk_icon",
                html: dot,
                iconSize: [MARKER_SIZE, MARKER_SIZE],
                iconAnchor: [MARKER_SIZE / 2, MARKER_SIZE / 2],
            });
            const marker = L.marker([row.lat, row.lng], { icon, title: row.name }).addTo(this.map);
            marker.bindTooltip(this._labelElement(row), {
                permanent: true,
                direction: "right",
                offset: [MARKER_SIZE / 2 + 4, 0],
                className: "o_dash_ml_tip",
                interactive: true,
            });
            marker.on("click", () => this.openProject(row));
            bounds.push([row.lat, row.lng]);
        }
        if (bounds.length === 1) {
            this.map.setView(bounds[0], SINGLE_MARKER_ZOOM);
        } else if (bounds.length > 1) {
            this.map.fitBounds(bounds, { padding: FIT_PADDING });
        }
    }

    formatPercent(value) {
        return formatPercent(value);
    }

    async openProject(row) {
        await openProjectPage(this.actionService, row.id, row.name);
    }
}

registry.category("actions").add(MAP_PAGE_TAG, CompanyDashboardMap);
