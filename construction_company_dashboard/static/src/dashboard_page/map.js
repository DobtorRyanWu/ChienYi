/** @odoo-module **/
// 標案地圖（合約 §0b-33）：照雛型——OSM 底圖、有座標的工程畫標記（紅＝落後、綠＝超前、灰＝未建進度表）＋標籤，
// 右側每工程一張小卡；沒座標的工程只列在右側並標「未設座標」。點標記或小卡進單一工程頁。
// 資料：核心 search_read 拿座標（快），只對有座標的工程再用 web_search_read 讀 dash_* 指標；沒有新的 RPC。
// 安全：標記標籤與小卡全部用 DOM 節點／OWL 模板組（不拼字串進 innerHTML）。
// 瓦片請求只帶站台 origin 當 Referer（OSM 規定要有；不帶路徑，看不到工程 id），見 TILE_REFERRER_POLICY。
// 淞源 C6（2026-11-13）：可以定位——對沒座標的工程按「定位」後在地圖上點一下（ORM write，有寫入權才存得進去）、
// 「用地點文字自動定位」（後端 action_dash_geocode）、「外部標案」圖層與「看附近」（後端 get_dash_map_extras）。
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { Layout } from "@web/search/layout";
import {
    DEFAULT_DOMAIN, LOAD_FAILED_MESSAGE, MAP_PAGE_TAG, PROJECT_MODEL, ROW_ORDER, ROW_SPECIFICATION,
    formatDateLabel, formatPercent, loadSelectionLabels, openProjectPage, shapeRow,
} from "./dash_common";

const COORD_FIELDS = ["code", "name", "latitude", "longitude", "location", "dash_geo_source"];
const EXTERNAL_MODEL = "construction.external.tender";
const KIND_PROJECT = "project";
const KIND_TENDER = "tender";
const GEO_SOURCE_MANUAL = "manual";
const GEO_SOURCE_GEOCODED = "geocoded";
const NEARBY_RADII_KM = [5, 10, 20];
const DEFAULT_NEARBY_KM = 10;
const EARTH_RADIUS_KM = 6371;
const METERS_PER_KM = 1000;
const COORD_DECIMALS = 7;
const LOCATE_ZOOM = 16;
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
        this.notification = useService("notification");
        this.nearbyRadii = NEARBY_RADII_KM;
        this.layers = null;
        this.fitted = false;
        this.display = { controlPanel: {} };
        this.mapRef = useRef("map");
        this.map = null;
        this.hasLeaflet = Boolean(window.L);
        this.todayLabel = formatDateLabel();
        this.state = useState({ loading: true, error: false, located: [], unlocated: [], tileError: false, tilesLoaded: 0,
                                fallback: false, tileStatus: null,
                                // C6：定位、外部標案、看附近
                                extras: null, showExternal: true, locate: null, busy: false, notice: null, nearby: null });
        this.tiles = null;
        this.fallbackTried = false;
        if (this.env.config && typeof this.env.config.setDisplayName === "function") {
            this.env.config.setDisplayName("標案地圖");   // 直接開網址時麵包屑不要顯示「未命名的」
        }
        onWillStart(() => Promise.all([this.loadProjects(), this.loadExtras()]));
        onMounted(async () => {
            this.initMap();
            await this.startLocateFromAction();
        });
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
            // 自動定位的座標不一定準：在清單上標出來，方便在地圖上再點一次修正
            const geocoded = new Set(located.filter((p) => p.dash_geo_source === GEO_SOURCE_GEOCODED).map((p) => p.id));
            for (const row of this.state.located) {
                row.geocoded = geocoded.has(row.id);
            }
            this.state.unlocated = unlocated.map((p) => ({ id: p.id, code: p.code || "", name: p.name || "", location: p.location || "" }));
        } catch (error) {
            console.error("標案地圖讀取失敗", error);
            this.state.error = LOAD_FAILED_MESSAGE;
            this.state.located = [];
            this.state.unlocated = [];
        } finally {
            this.state.loading = false;
        }
    }

    // ── C6：額外資料（能不能定位、外部標案）────────────────────────────────
    async loadExtras() {
        try {
            this.state.extras = await this.orm.call(PROJECT_MODEL, "get_dash_map_extras", []);
        } catch (error) {
            console.error("標案地圖的定位／外部標案資料讀取失敗", error);
            this.state.extras = null;       // 讀不到就只是沒有定位按鈕與外部標案圖層，地圖照常
        }
    }

    get canLocate() {
        return Boolean(this.state.extras && this.state.extras.can_locate && this.hasLeaflet);
    }

    get geocodeEnabled() {
        return Boolean(this.state.extras && this.state.extras.geocode_enabled);
    }

    get external() {
        const external = this.state.extras && this.state.extras.external;
        return external && external.status === "ok" ? external : null;
    }

    get externalLocated() {
        return this.external ? this.external.items.filter((t) => t.lat && t.lng) : [];
    }

    get externalUnlocated() {
        return this.external ? this.external.items.filter((t) => !(t.lat && t.lng)) : [];
    }

    get canLocateTender() {
        return Boolean(this.external && this.external.can_edit && this.hasLeaflet);
    }

    /** 還沒座標、但有地點文字（可以拿去自動定位）的工程數 */
    get geocodableProjects() {
        return this.state.unlocated.filter((p) => p.location).length;
    }

    get geocodableTenders() {
        return this.externalUnlocated.filter((t) => t.location).length;
    }

    async reloadAll() {
        await Promise.all([this.loadProjects(), this.loadExtras()]);
        this.renderMarkers();
    }

    // ── C6：在地圖上點位置 ───────────────────────────────────────────────
    /** 從工程表單的「在地圖上定位」進來：action.params.locate_project_id */
    async startLocateFromAction() {
        const params = (this.props.action && this.props.action.params) || {};
        const projectId = Number(params.locate_project_id);
        if (!projectId || !this.canLocate) {
            return;
        }
        try {
            const [project] = await this.orm.read(PROJECT_MODEL, [projectId], ["name", "latitude", "longitude"]);
            if (project) {
                this.startLocate(KIND_PROJECT, { id: project.id, name: project.name });
                if (Number(project.latitude) && Number(project.longitude) && this.map) {
                    this.map.setView([Number(project.latitude), Number(project.longitude)], LOCATE_ZOOM);
                }
            }
        } catch (error) {
            console.error("讀不到要定位的工程", error);
        }
    }

    startLocate(kind, item) {
        this.state.notice = null;
        this.state.locate = { kind, id: item.id, name: item.name };
        // 窄畫面時清單在地圖下面：按了「定位」要把地圖帶回畫面，不然不知道要點哪裡
        if (this.mapRef.el && typeof this.mapRef.el.scrollIntoView === "function") {
            this.mapRef.el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }

    cancelLocate() {
        this.state.locate = null;
    }

    async onMapClick(ev) {
        const target = this.state.locate;
        if (!target || this.state.busy) {
            return;
        }
        const lat = Number(ev.latlng.lat.toFixed(COORD_DECIMALS));
        const lng = Number(ev.latlng.lng.toFixed(COORD_DECIMALS));
        const [model, sourceField] = target.kind === KIND_PROJECT
            ? [PROJECT_MODEL, "dash_geo_source"] : [EXTERNAL_MODEL, "geo_source"];
        this.state.busy = true;
        try {
            await this.orm.write(model, [target.id], { latitude: lat, longitude: lng, [sourceField]: GEO_SOURCE_MANUAL });
            this.state.locate = null;
            this.notification.add(`已定位：${target.name}`, { type: "success" });
            await this.reloadAll();
        } catch (error) {
            console.error("定位存檔失敗", error);
            this.state.notice = { tone: "bad", text: `「${target.name}」的位置沒有存進去（可能沒有修改權限）。` };
        } finally {
            this.state.busy = false;
        }
    }

    // ── C6：用地點文字自動定位 ───────────────────────────────────────────
    async geocode(kind) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.notice = { tone: "info", text: "正在查座標（外部定位服務一秒只能查一個，請稍候）…" };
        try {
            const result = await this.orm.call(PROJECT_MODEL, "action_dash_geocode", [kind]);
            const parts = [`查到 ${result.located.length} 個`];
            const approx = result.located.filter((item) => item.approx).length;
            if (approx) {
                parts.push(`其中 ${approx} 個只定位到路段或行政區（門牌查不到）`);
            }
            if (result.failed.length) {
                parts.push(`查不到 ${result.failed.length} 個（${result.failed.slice(0, 3).map((f) => `${f.name}：${f.reason}`).join("；")}${result.failed.length > 3 ? "…" : ""}）`);
            }
            if (result.remaining) {
                parts.push(`還有 ${result.remaining} 個沒輪到，可以再按一次`);
            }
            if (result.no_location) {
                parts.push(`${result.no_location} 個沒有填地點文字，請直接在地圖上點`);
            }
            this.state.notice = { tone: result.located.length ? "ok" : "info",
                                  text: `自動定位：${parts.join("；")}。自動查到的位置不一定準，請在地圖上確認，不對就按「重新定位」。` };
            await this.reloadAll();
        } catch (error) {
            console.error("自動定位失敗", error);
            const message = error && error.data && error.data.message;
            this.state.notice = { tone: "bad", text: message || "自動定位失敗，請稍後再試或直接在地圖上點位置。" };
        } finally {
            this.state.busy = false;
        }
    }

    // ── C6：外部標案 ─────────────────────────────────────────────────────
    toggleExternal() {
        this.state.showExternal = !this.state.showExternal;
        this.renderMarkers();
    }

    async openTender(tender) {
        await this.actionService.doAction({
            type: "ir.actions.act_window", res_model: EXTERNAL_MODEL, res_id: tender.id,
            views: [[false, "form"]], target: "current",
        });
    }

    async openTenderList() {
        await this.actionService.doAction("construction_company_dashboard.action_external_tender");
    }

    formatAmount(tender) {
        return tender.amount ? `${tender.currency || ""} ${Math.round(tender.amount).toLocaleString()}` : "";
    }

    /** 外部標案的第二行小字：機關・截止日・金額（有的才列） */
    tenderSubText(tender) {
        return [tender.agency, tender.deadline ? `截止 ${tender.deadline}` : "", this.formatAmount(tender)].filter(Boolean).join("・");
    }

    // ── C6：看某個工程附近的外部標案 ─────────────────────────────────────
    showNearby(row) {
        this.state.nearby = { id: row.id, name: row.name, lat: row.lat, lng: row.lng, radius: DEFAULT_NEARBY_KM };
        this.state.showExternal = true;
        this.renderMarkers();
    }

    setNearbyRadius(km) {
        if (this.state.nearby) {
            this.state.nearby.radius = km;
            this.renderMarkers();
        }
    }

    closeNearby() {
        this.state.nearby = null;
        this.renderMarkers();
    }

    /** 兩點的直線距離（公里） */
    distanceKm(lat1, lng1, lat2, lng2) {
        const rad = (deg) => (deg * Math.PI) / 180;
        const a = Math.sin(rad(lat2 - lat1) / 2) ** 2
            + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lng2 - lng1) / 2) ** 2;
        return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
    }

    /** 「附近」範圍內的外部標案，近的在前；每筆帶 distance（公里） */
    get nearbyTenders() {
        const center = this.state.nearby;
        if (!center) {
            return [];
        }
        return this.externalLocated
            .map((t) => ({ ...t, distance: this.distanceKm(center.lat, center.lng, t.lat, t.lng) }))
            .filter((t) => t.distance <= center.radius)
            .sort((a, b) => a.distance - b.distance);
    }

    formatKm(value) {
        return value < 1 ? `${Math.round(value * METERS_PER_KM)} 公尺` : `${value.toFixed(1)} 公里`;
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
        // 標記分三層（工程、外部標案、附近範圍），重畫時整層清掉再畫
        this.layers = { projects: L.layerGroup().addTo(this.map), external: L.layerGroup().addTo(this.map),
                        nearby: L.layerGroup().addTo(this.map) };
        this.map.on("click", (ev) => this.onMapClick(ev));
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

    /** 外部標案的標籤（textContent，不拼 HTML 字串） */
    _tenderLabelElement(tender) {
        const box = document.createElement("div");
        box.className = "o_dash_ml";
        const title = document.createElement("b");
        title.textContent = tender.name;
        box.appendChild(title);
        const line = document.createElement("span");
        line.className = "o_dash_mute";
        line.textContent = [`外部標案・${tender.stage_label}`, this.tenderSubText(tender)].filter(Boolean).join("・");
        box.appendChild(line);
        return box;
    }

    renderMarkers() {
        if (!this.map || !window.L || !this.layers) {
            return;
        }
        const L = window.L;
        const bounds = [];
        this.layers.projects.clearLayers();
        this.layers.external.clearLayers();
        this.layers.nearby.clearLayers();
        if (this.state.showExternal) {
            for (const tender of this.externalLocated) {
                const dot = document.createElement("i");
                dot.className = "o_dash_mk_dot o_dash_mk_external";
                const icon = L.divIcon({ className: "o_dash_mk_icon", html: dot, iconSize: [MARKER_SIZE, MARKER_SIZE],
                                         iconAnchor: [MARKER_SIZE / 2, MARKER_SIZE / 2] });
                const marker = L.marker([tender.lat, tender.lng], { icon, title: tender.name }).addTo(this.layers.external);
                marker.bindTooltip(this._tenderLabelElement(tender), { direction: "right", offset: [MARKER_SIZE / 2 + 4, 0],
                                                                       className: "o_dash_ml_tip" });
                marker.on("click", () => { if (!this.state.locate) { this.openTender(tender); } });
                bounds.push([tender.lat, tender.lng]);
            }
        }
        if (this.state.nearby) {
            L.circle([this.state.nearby.lat, this.state.nearby.lng], {
                radius: this.state.nearby.radius * METERS_PER_KM, className: "o_dash_nearby_circle", interactive: false,
            }).addTo(this.layers.nearby);
        }
        for (const row of this.state.located) {
            const dot = document.createElement("i");
            dot.className = `o_dash_mk_dot ${this.markerClass(row)}`;
            const icon = L.divIcon({
                className: "o_dash_mk_icon",
                html: dot,
                iconSize: [MARKER_SIZE, MARKER_SIZE],
                iconAnchor: [MARKER_SIZE / 2, MARKER_SIZE / 2],
            });
            const marker = L.marker([row.lat, row.lng], { icon, title: row.name }).addTo(this.layers.projects);
            marker.bindTooltip(this._labelElement(row), {
                permanent: true,
                direction: "right",
                offset: [MARKER_SIZE / 2 + 4, 0],
                className: "o_dash_ml_tip",
                interactive: true,
            });
            marker.on("click", () => { if (!this.state.locate) { this.openProject(row); } });
            bounds.push([row.lat, row.lng]);
        }
        // 視野只在第一次畫的時候自動調（之後定位、開關圖層不要把使用者正在看的地方移走）
        if (!this.fitted && bounds.length) {
            this.fitted = true;
            if (bounds.length === 1) {
                this.map.setView(bounds[0], SINGLE_MARKER_ZOOM);
            } else {
                this.map.fitBounds(bounds, { padding: FIT_PADDING });
            }
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
