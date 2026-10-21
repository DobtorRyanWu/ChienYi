/** @odoo-module **/
/**
 * latlng_map_picker —— 在地圖上點一下就把座標寫進兩個 Float 欄位。
 *
 * 用法（掛在緯度欄位上，經度欄位用 option 指過去）：
 *   <field name="latitude" widget="latlng_map_picker"
 *          options="{'longitude_field': 'longitude'}"/>
 *
 * 幾個前提：
 * - Leaflet 由 web_leaflet_lib 掛進 web.assets_backend，後台每頁 window.L 都在，
 *   所以這裡不需要 loadJS，只做存在性檢查（與 construction_geoengine 同慣例）。
 * - 圖磚沿用 portal 照片地圖的做法：主源用不帶子網域的 OSM（子網域輪替會被部分
 *   內容封鎖器擋掉），連續失敗才切 CARTO。若系統參數 leaflet.tile_url 有設就優先用它。
 */

import { Component, onMounted, onWillUnmount, onPatched, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { session } from "@web/session";

// 沒有座標時的預設視野：台灣全島
const DEFAULT_CENTER = [23.7, 121.0];
const DEFAULT_ZOOM = 7;
// 已有座標時的視野
const PIN_ZOOM = 16;
// 連續幾張圖磚失敗才切備援來源（避免單張瞬斷誤觸發）
const TILE_FAIL_THRESHOLD = 3;

const TILE_PRIMARY = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_FALLBACK =
    "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";
const TILE_MAX_ZOOM = 19;

export class LatLngMapPicker extends Component {
    static template = "construction_water_level.LatLngMapPicker";
    static props = {
        ...standardFieldProps,
        longitudeField: { type: String, optional: true },
    };

    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.marker = null;

        onMounted(() => this._initMap());
        onPatched(() => this._syncMarkerFromRecord());
        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    get lonField() {
        return this.props.longitudeField || "longitude";
    }

    get latitude() {
        return this.props.record.data[this.props.name] || 0;
    }

    get longitude() {
        return this.props.record.data[this.lonField] || 0;
    }

    get hasCoords() {
        return Boolean(this.latitude || this.longitude);
    }

    get coordText() {
        if (!this.hasCoords) {
            return "尚未標記";
        }
        return `${this.latitude.toFixed(7)}, ${this.longitude.toFixed(7)}`;
    }

    _initMap() {
        const el = this.mapRef.el;
        if (!el || !window.L) {
            return;
        }
        const L = window.L;
        const center = this.hasCoords ? [this.latitude, this.longitude] : DEFAULT_CENTER;
        const zoom = this.hasCoords ? PIN_ZOOM : DEFAULT_ZOOM;

        this.map = L.map(el, { center, zoom, zoomControl: true });
        this._addTileLayer(L);

        if (this.hasCoords) {
            this.marker = L.marker(center).addTo(this.map);
        }
        if (!this.props.readonly) {
            this.map.on("click", (ev) => this._onMapClick(ev));
        }
        // 表單頁籤／視窗尺寸尚未 settle 時 Leaflet 會算錯容器大小
        setTimeout(() => this.map && this.map.invalidateSize(), 0);
    }

    _addTileLayer(L) {
        const configured = session["leaflet.tile_url"];
        if (configured) {
            L.tileLayer(configured, {
                attribution: session["leaflet.copyright"] || "",
                maxZoom: TILE_MAX_ZOOM,
            }).addTo(this.map);
            return;
        }
        let failCount = 0;
        let switched = false;
        const primary = L.tileLayer(TILE_PRIMARY, {
            attribution: "&copy; OpenStreetMap",
            maxZoom: TILE_MAX_ZOOM,
        });
        primary.on("tileerror", () => {
            failCount += 1;
            if (!switched && failCount >= TILE_FAIL_THRESHOLD) {
                switched = true;
                this.map.removeLayer(primary);
                L.tileLayer(TILE_FALLBACK, {
                    attribution: "&copy; OpenStreetMap &copy; CARTO",
                    maxZoom: TILE_MAX_ZOOM,
                    subdomains: "abcd",
                }).addTo(this.map);
            }
        });
        primary.addTo(this.map);
    }

    async _onMapClick(ev) {
        const { lat, lng } = ev.latlng;
        await this.props.record.update({
            [this.props.name]: lat,
            [this.lonField]: lng,
        });
        this._placeMarker(lat, lng);
    }

    /** 使用者直接改欄位數字時，把 marker 跟過去 */
    _syncMarkerFromRecord() {
        if (!this.map) {
            return;
        }
        if (!this.hasCoords) {
            if (this.marker) {
                this.map.removeLayer(this.marker);
                this.marker = null;
            }
            return;
        }
        this._placeMarker(this.latitude, this.longitude, false);
    }

    _placeMarker(lat, lng, recenter = true) {
        const L = window.L;
        if (this.marker) {
            this.marker.setLatLng([lat, lng]);
        } else {
            this.marker = L.marker([lat, lng]).addTo(this.map);
        }
        if (recenter) {
            this.map.setView([lat, lng], Math.max(this.map.getZoom(), PIN_ZOOM));
        }
    }

    onClearClick() {
        if (this.props.readonly) {
            return;
        }
        this.props.record.update({
            [this.props.name]: 0,
            [this.lonField]: 0,
        });
    }
}

export const latLngMapPicker = {
    component: LatLngMapPicker,
    displayName: "地圖點選座標",
    supportedTypes: ["float"],
    supportedOptions: [
        {
            label: "經度欄位",
            name: "longitude_field",
            type: "string",
            help: "存經度的欄位名稱，預設 longitude",
        },
    ],
    extractProps: ({ options }) => ({
        longitudeField: options.longitude_field || "longitude",
    }),
};

registry.category("fields").add("latlng_map_picker", latLngMapPicker);
