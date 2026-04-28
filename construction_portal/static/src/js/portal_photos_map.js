/**
 * Portal 照片地圖（行動端 Google Maps + Google Photos 風格）
 * - 全螢幕地圖 + 底部 bottom sheet
 * - 頂部 pill 篩選 → modal sheet 展開
 * - Google Photos 風 grid + 全螢幕 Lightbox（左右切換、pinch-zoom）
 */
(function () {
    'use strict';

    var mapContainer = document.getElementById('portalPhotoMap');
    if (!mapContainer) return;

    // =============================================
    // 設定
    // =============================================
    var appEl = document.querySelector('.cy-photos-map-app');
    var projectId = appEl ? appEl.dataset.projectId : '';
    var filterOptions = {};
    var projectCenter = { lat: 23.5, lng: 120.5 };

    try { filterOptions = JSON.parse(appEl.dataset.filterOptionsJson || '{}'); } catch (e) {}
    try { projectCenter = JSON.parse(appEl.dataset.projectCenterJson || '{}'); } catch (e) {}

    var API = {
        MARKERS: '/construction/' + projectId + '/photos/api/markers',
        AREA:    '/construction/' + projectId + '/photos/api/area-photos',
        NEARBY:  '/construction/' + projectId + '/photos/api/nearby',
    };

    var SOURCE_COLORS = {
        daily_log: '#3b82f6', inspection: '#22c55e', defect: '#ef4444',
        test: '#f59e0b', acceptance: '#8b5cf6', notification: '#06b6d4', other: '#6b7280',
    };
    var SOURCE_LABELS = {
        daily_log: '施工日誌', inspection: '自主檢查', defect: '缺失改善',
        test: '檢試驗', acceptance: '驗收', notification: '通報單', other: '其他',
    };

    // =============================================
    // 狀態
    // =============================================
    var state = {
        map: null,
        markerCluster: null,
        activeTab: 'area',
        sheetState: 'peek',  // peek | half | full
        userMarker: null,
        userCircle: null,
        userLat: null,
        userLng: null,
        nearbyRadius: 1,
        areaOffset: 0,
        areaTotal: 0,
        moveEndTimer: null,
        filters: {
            source_model: '',
            category: '',
            construction_phase: '',
            date_from: '',
            date_to: '',
            search: '',
        },
        // 目前用於 lightbox 的照片陣列
        gallery: [],
        galleryIndex: 0,
    };

    // =============================================
    // 工具
    // =============================================
    function jsonRpc(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {} }),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) { return data.result || {}; });
    }

    function escapeHtml(str) {
        var d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    function debounce(fn, ms) {
        var timer;
        return function () {
            clearTimeout(timer);
            timer = setTimeout(fn, ms);
        };
    }

    function $(id) { return document.getElementById(id); }

    // =============================================
    // 地圖初始化
    // =============================================
    function initMap() {
        if (!window.L) return;

        var defaultLat = projectCenter.lat || 23.5;
        var defaultLng = projectCenter.lng || 120.5;
        var defaultZoom = (defaultLat !== 23.5 || defaultLng !== 120.5) ? 14 : 8;

        state.map = L.map(mapContainer, {
            center: [defaultLat, defaultLng],
            zoom: defaultZoom,
            zoomControl: false,
        });
        L.control.zoom({ position: 'topleft' }).addTo(state.map);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap', maxZoom: 19,
        }).addTo(state.map);

        state.markerCluster = L.markerClusterGroup({
            maxClusterRadius: 50,
            showCoverageOnHover: false,
            chunkedLoading: true,
            spiderfyOnMaxZoom: false,
            zoomToBoundsOnClick: false,
            iconCreateFunction: function (cluster) {
                var count = cluster.getChildCount();
                var size = count < 10 ? 'small' : count < 50 ? 'medium' : 'large';
                return L.divIcon({
                    html: '<div class="photo-cluster cluster-' + size + '">' + count + '</div>',
                    className: 'photo-cluster-wrapper',
                    iconSize: L.point(44, 44),
                });
            },
        });
        state.map.addLayer(state.markerCluster);

        // Cluster click：Google Maps 行為
        // - 若子 marker 位置不同 → 縮放到 bounds
        // - 若全部同點 → 直接開 lightbox 看那批照片
        state.markerCluster.on('clusterclick', function (e) {
            var children = e.layer.getAllChildMarkers();
            var bounds = e.layer.getBounds();
            var ne = bounds.getNorthEast();
            var sw = bounds.getSouthWest();
            var samePoint = Math.abs(ne.lat - sw.lat) < 1e-6 && Math.abs(ne.lng - sw.lng) < 1e-6;

            if (samePoint) {
                // 全部同點：開 lightbox gallery
                var gallery = [];
                for (var i = 0; i < children.length; i++) {
                    if (children[i]._photo) gallery.push(children[i]._photo);
                }
                if (gallery.length) openLightbox(gallery, 0);
            } else {
                // 可以拉開：縮放到 bounds
                state.map.fitBounds(bounds, { padding: [60, 60], maxZoom: 19 });
            }
        });

        state.map.on('moveend', debounce(function () {
            if (state.activeTab === 'area') loadAreaPhotos(true);
        }, 600));
    }

    // =============================================
    // Marker 管理
    // =============================================
    function createMarkerIcon(sourceModel) {
        var color = SOURCE_COLORS[sourceModel] || SOURCE_COLORS.other;
        return L.divIcon({
            className: 'photo-marker-wrapper',
            html: '<div class="photo-marker-dot" style="background:' + color + '"><i class="fa fa-camera"></i></div>',
            iconSize: [30, 38],
            iconAnchor: [15, 38],
            popupAnchor: [0, -40],
        });
    }

    function renderMarkers(markers) {
        if (!state.markerCluster) return;
        state.markerCluster.clearLayers();
        var layers = [];
        for (var i = 0; i < markers.length; i++) {
            var m = markers[i];
            if (!m.lat || !m.lng) continue;
            var marker = L.marker([m.lat, m.lng], { icon: createMarkerIcon(m.source_model) });
            marker._photo = m;
            marker.on('click', onMarkerClick);
            layers.push(marker);
        }
        state.markerCluster.addLayers(layers);
    }

    function onMarkerClick(e) {
        var photo = e.target._photo;
        if (!photo) return;
        // 單點 marker → 直接開 lightbox（只含這一張）
        openLightbox([photo], 0);
    }

    function fitAllMarkers() {
        if (state.markerCluster && state.markerCluster.getLayers().length > 0) {
            state.map.fitBounds(state.markerCluster.getBounds(), { padding: [40, 40] });
        }
    }

    // =============================================
    // 資料載入
    // =============================================
    function collectFilters() {
        return {
            source_model: state.filters.source_model || '',
            category: state.filters.category || '',
            construction_phase: state.filters.construction_phase || '',
            date_from: state.filters.date_from || '',
            date_to: state.filters.date_to || '',
            search: state.filters.search || '',
        };
    }

    function loadMarkers() {
        var params = collectFilters();
        jsonRpc(API.MARKERS, params).then(function (res) {
            if (res.error) return;
            renderMarkers(res.markers || []);

            var filteredEl = $('filteredCount');
            var totalEl = $('totalCount');
            if (filteredEl) filteredEl.textContent = res.filtered || 0;
            if (totalEl) totalEl.textContent = res.total || 0;

            if ((res.markers || []).length > 0 && !state._fitOnce) {
                fitAllMarkers();
                state._fitOnce = true;
            }
            // 區域 tab 也同步刷新
            if (state.activeTab === 'area') loadAreaPhotos(true);
        });
    }

    function loadAreaPhotos(reset) {
        if (reset) {
            state.areaOffset = 0;
            state.areaTotal = 0;
            var g = $('areaGrid');
            if (g) g.innerHTML = '';
        }
        if (!state.map) return;

        var bounds = state.map.getBounds();
        var params = collectFilters();
        params.bounds = {
            north: bounds.getNorth(), south: bounds.getSouth(),
            east: bounds.getEast(), west: bounds.getWest(),
        };
        params.limit = 60;
        params.offset = state.areaOffset;

        jsonRpc(API.AREA, params).then(function (res) {
            if (res.error) return;
            state.areaTotal = res.total || 0;

            var countEl = $('areaCount');
            if (countEl) countEl.textContent = state.areaTotal;

            var photos = res.photos || [];
            appendGrid($('areaGrid'), photos, 'area');
            state.areaOffset += photos.length;

            var moreBtn = $('btnLoadMore');
            if (moreBtn) moreBtn.style.display = res.has_more ? 'block' : 'none';
        });
    }

    function loadNearbyPhotos(lat, lng, radius) {
        var statusEl = $('nearbyStatus');
        var gridEl = $('nearbyGrid');
        statusEl.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 搜尋附近照片...';
        gridEl.innerHTML = '';

        jsonRpc(API.NEARBY, { lat: lat, lng: lng, radius: radius }).then(function (res) {
            if (res.error) return;
            var photos = res.photos || [];
            if (photos.length === 0) {
                statusEl.innerHTML = '<i class="fa fa-info-circle"></i> 附近沒有照片';
                return;
            }
            statusEl.innerHTML = '<i class="fa fa-check-circle"></i> 找到 ' + photos.length + ' 張';
            appendGrid(gridEl, photos, 'nearby', true);
        });
    }

    // =============================================
    // Google Photos 風 Grid（日期分組）
    // =============================================
    function appendGrid(container, photos, tabKey, showDistance) {
        if (!container || !photos.length) return;

        // 依 shot_date 分組（此批次內）
        var groups = {};
        var order = [];
        for (var i = 0; i < photos.length; i++) {
            var key = photos[i].shot_date || '未標記日期';
            if (!groups[key]) {
                groups[key] = [];
                order.push(key);
            }
            groups[key].push(photos[i]);
        }

        for (var j = 0; j < order.length; j++) {
            var date = order[j];
            var existingHeader = container.querySelector('[data-group="' + date + '"]');
            var groupEl, gridEl;
            if (existingHeader) {
                gridEl = existingHeader.querySelector('.cy-photo-group-grid');
            } else {
                groupEl = document.createElement('div');
                groupEl.className = 'cy-photo-group';
                groupEl.setAttribute('data-group', date);
                groupEl.innerHTML = '<div class="cy-photo-group-title">' + escapeHtml(date) + '</div>' +
                                    '<div class="cy-photo-group-grid"></div>';
                container.appendChild(groupEl);
                gridEl = groupEl.querySelector('.cy-photo-group-grid');
            }
            for (var k = 0; k < groups[date].length; k++) {
                gridEl.appendChild(createGridItem(groups[date][k], tabKey, showDistance));
            }
        }
    }

    function createGridItem(photo, tabKey, showDistance) {
        photoDataMap[photo.id] = photo;
        var item = document.createElement('button');
        item.type = 'button';
        item.className = 'cy-photo-grid-item';
        item.setAttribute('data-photo-id', photo.id);

        var imgHtml = photo.thumbnail_url
            ? '<img src="' + photo.thumbnail_url + '" loading="lazy" alt=""/>'
            : '<div class="cy-grid-placeholder"><i class="fa fa-image"></i></div>';

        var sourceColor = SOURCE_COLORS[photo.source_model] || '#6b7280';
        var badge = '<span class="cy-grid-badge" style="background:' + sourceColor + '"></span>';

        var distLabel = '';
        if (showDistance && photo.distance_label) {
            distLabel = '<span class="cy-grid-distance">' + escapeHtml(photo.distance_label) + '</span>';
        }

        item.innerHTML = imgHtml + badge + distLabel;

        item.addEventListener('click', function () {
            // 整個 tab 的照片陣列作為 gallery
            var gridParent = tabKey === 'area' ? $('areaGrid') : $('nearbyGrid');
            var gallery = collectGalleryFromContainer(gridParent, tabKey);
            var idx = 0;
            for (var i = 0; i < gallery.length; i++) {
                if (gallery[i].id === photo.id) { idx = i; break; }
            }
            openLightbox(gallery, idx);

            // 同時飛到 marker
            if (photo.lat && photo.lng && state.map) {
                state.map.flyTo([photo.lat, photo.lng], Math.max(state.map.getZoom(), 16));
            }
        });

        return item;
    }

    // 從 DOM 收集照片完整資料（存在 photoDataMap 裡）
    var photoDataMap = {};
    function collectGalleryFromContainer(container, tabKey) {
        if (!container) return [];
        var items = container.querySelectorAll('.cy-photo-grid-item');
        var list = [];
        for (var i = 0; i < items.length; i++) {
            var id = parseInt(items[i].getAttribute('data-photo-id'));
            if (photoDataMap[id]) list.push(photoDataMap[id]);
        }
        return list;
    }

    // =============================================
    // Lightbox
    // =============================================
    var lightbox = {
        el: null,
        img: null,
        viewport: null,
        // pinch zoom state
        scale: 1,
        tx: 0,
        ty: 0,
        startDist: 0,
        startScale: 1,
        startTouches: null,
        panning: false,
        lastX: 0,
        lastY: 0,
    };

    function initLightbox() {
        lightbox.el = $('photoLightbox');
        lightbox.img = $('lightboxImg');
        lightbox.viewport = $('lightboxViewport');

        $('lightboxClose').addEventListener('click', closeLightbox);
        $('lightboxPrev').addEventListener('click', function () { navLightbox(-1); });
        $('lightboxNext').addEventListener('click', function () { navLightbox(1); });

        // 鍵盤
        document.addEventListener('keydown', function (e) {
            if (!lightbox.el.classList.contains('open')) return;
            if (e.key === 'Escape') closeLightbox();
            else if (e.key === 'ArrowLeft') navLightbox(-1);
            else if (e.key === 'ArrowRight') navLightbox(1);
        });

        // 觸控手勢：swipe 切換 + pinch zoom + pan
        var vp = lightbox.viewport;
        var swipeStartX = 0, swipeStartY = 0, swipeActive = false;

        vp.addEventListener('touchstart', function (e) {
            if (e.touches.length === 2) {
                // pinch 開始
                lightbox.startDist = getTouchDist(e.touches);
                lightbox.startScale = lightbox.scale;
                swipeActive = false;
            } else if (e.touches.length === 1) {
                if (lightbox.scale > 1) {
                    // 放大狀態 → pan
                    lightbox.panning = true;
                    lightbox.lastX = e.touches[0].clientX;
                    lightbox.lastY = e.touches[0].clientY;
                    swipeActive = false;
                } else {
                    // 未放大 → swipe
                    swipeActive = true;
                    swipeStartX = e.touches[0].clientX;
                    swipeStartY = e.touches[0].clientY;
                }
            }
        }, { passive: true });

        vp.addEventListener('touchmove', function (e) {
            if (e.touches.length === 2) {
                var d = getTouchDist(e.touches);
                if (lightbox.startDist > 0) {
                    lightbox.scale = clamp(lightbox.startScale * (d / lightbox.startDist), 1, 4);
                    applyTransform();
                }
                e.preventDefault();
            } else if (e.touches.length === 1 && lightbox.panning) {
                var dx = e.touches[0].clientX - lightbox.lastX;
                var dy = e.touches[0].clientY - lightbox.lastY;
                lightbox.tx += dx;
                lightbox.ty += dy;
                lightbox.lastX = e.touches[0].clientX;
                lightbox.lastY = e.touches[0].clientY;
                applyTransform();
                e.preventDefault();
            }
        }, { passive: false });

        vp.addEventListener('touchend', function (e) {
            if (swipeActive && e.changedTouches.length === 1) {
                var dx = e.changedTouches[0].clientX - swipeStartX;
                var dy = e.changedTouches[0].clientY - swipeStartY;
                if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
                    navLightbox(dx > 0 ? -1 : 1);
                }
            }
            swipeActive = false;
            lightbox.panning = false;
            // 若縮回 1，reset 位移
            if (lightbox.scale <= 1.01) {
                lightbox.scale = 1;
                lightbox.tx = 0;
                lightbox.ty = 0;
                applyTransform();
            }
        });

        // 桌機雙擊 toggle zoom
        lightbox.img.addEventListener('dblclick', function (e) {
            if (lightbox.scale > 1) {
                lightbox.scale = 1; lightbox.tx = 0; lightbox.ty = 0;
            } else {
                lightbox.scale = 2;
            }
            applyTransform();
        });
    }

    function getTouchDist(touches) {
        var dx = touches[0].clientX - touches[1].clientX;
        var dy = touches[0].clientY - touches[1].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }
    function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
    function applyTransform() {
        lightbox.img.style.transform =
            'translate(' + lightbox.tx + 'px, ' + lightbox.ty + 'px) scale(' + lightbox.scale + ')';
    }
    function resetTransform() {
        lightbox.scale = 1; lightbox.tx = 0; lightbox.ty = 0;
        applyTransform();
    }

    function openLightbox(gallery, idx) {
        state.gallery = gallery || [];
        state.galleryIndex = idx || 0;
        if (!state.gallery.length) return;
        lightbox.el.classList.add('open');
        document.body.classList.add('lightbox-open');
        renderLightbox();
    }

    function closeLightbox() {
        lightbox.el.classList.remove('open');
        document.body.classList.remove('lightbox-open');
        resetTransform();
    }

    function navLightbox(delta) {
        if (!state.gallery.length) return;
        var n = state.gallery.length;
        state.galleryIndex = (state.galleryIndex + delta + n) % n;
        resetTransform();
        renderLightbox();
    }

    function renderLightbox() {
        var p = state.gallery[state.galleryIndex];
        if (!p) return;
        // image_url 優先，退回 thumbnail
        lightbox.img.src = p.image_url || p.thumbnail_url || '';
        lightbox.img.alt = p.name || '';

        $('lightboxCounter').textContent = (state.galleryIndex + 1) + ' / ' + state.gallery.length;

        var srcLink = $('lightboxSource');
        srcLink.href = '/construction/photo/' + p.id;

        var srcLabel = SOURCE_LABELS[p.source_model] || '';
        var srcColor = SOURCE_COLORS[p.source_model] || '#6b7280';
        var caption = '<div class="cy-lightbox-cap-title">' + escapeHtml(p.name || '未命名') + '</div>';
        var meta = [];
        if (p.shot_date) meta.push('<i class="fa fa-calendar"></i> ' + p.shot_date);
        if (p.location_description) meta.push('<i class="fa fa-map-marker"></i> ' + escapeHtml(p.location_description));
        if (srcLabel) meta.push('<span class="cy-lightbox-chip" style="background:' + srcColor + '">' + srcLabel + '</span>');
        if (p.category_label) meta.push(escapeHtml(p.category_label));
        caption += '<div class="cy-lightbox-cap-meta">' + meta.join(' · ') + '</div>';
        $('lightboxCaption').innerHTML = caption;
    }

    // =============================================
    // 使用者定位
    // =============================================
    function locateMe(force) {
        if (!force && state.userLat && state.userLng) {
            state.map.flyTo([state.userLat, state.userLng], 18);
            switchTab('nearby');
            return;
        }
        if (!navigator.geolocation) return;

        var statusEl = $('nearbyStatus');
        if (statusEl) statusEl.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 正在取得位置...';
        switchTab('nearby');
        setSheetState('half');

        navigator.geolocation.getCurrentPosition(
            function (pos) {
                state.userLat = pos.coords.latitude;
                state.userLng = pos.coords.longitude;
                showUserLocation(state.userLat, state.userLng);
                state.map.flyTo([state.userLat, state.userLng], 18);
                loadNearbyPhotos(state.userLat, state.userLng, state.nearbyRadius);
            },
            function (err) {
                var msg = '無法取得位置';
                if (err.code === err.PERMISSION_DENIED) {
                    msg = window.location.protocol === 'https:' || window.location.hostname === 'localhost'
                        ? '請允許瀏覽器存取位置權限'
                        : '需要 HTTPS 才能使用定位功能';
                } else if (err.code === err.TIMEOUT) {
                    msg = '取得位置逾時，請重試';
                }
                if (statusEl) statusEl.innerHTML = '<i class="fa fa-exclamation-circle"></i> ' + msg;
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    function showUserLocation(lat, lng) {
        if (state.userMarker) state.map.removeLayer(state.userMarker);
        if (state.userCircle) state.map.removeLayer(state.userCircle);

        state.userMarker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'user-location-wrapper',
                html: '<div class="user-location-dot"></div><div class="user-location-pulse"></div>',
                iconSize: [20, 20], iconAnchor: [10, 10],
            }),
            zIndexOffset: 1000,
        }).addTo(state.map).bindPopup('<b>我的位置</b>');

        state.userCircle = L.circle([lat, lng], {
            radius: state.nearbyRadius * 1000,
            color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 0.08,
            weight: 2, dashArray: '6, 6',
        }).addTo(state.map);
    }

    // =============================================
    // 篩選 Modal
    // =============================================
    function renderFilterOptions() {
        var groups = [
            { key: 'source_model', containerId: 'filterSourceOptions' },
            { key: 'category', containerId: 'filterCategoryOptions' },
            { key: 'construction_phase', containerId: 'filterPhaseOptions' },
        ];
        for (var i = 0; i < groups.length; i++) {
            var g = groups[i];
            var cont = $(g.containerId);
            if (!cont) continue;
            var options = filterOptions[g.key] || [];
            var html = '<button type="button" class="cy-filter-opt" data-field="' + g.key + '" data-value="">全部</button>';
            for (var j = 0; j < options.length; j++) {
                var v = options[j][0], lbl = options[j][1];
                html += '<button type="button" class="cy-filter-opt" data-field="' + g.key + '" data-value="' + escapeHtml(v) + '">' + escapeHtml(lbl) + '</button>';
            }
            cont.innerHTML = html;
        }
        cont = document.getElementById('filterModal');
        cont.querySelectorAll('.cy-filter-opt').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var field = this.getAttribute('data-field');
                var value = this.getAttribute('data-value');
                // single-select within group
                cont.querySelectorAll('.cy-filter-opt[data-field="' + field + '"]').forEach(function (b) {
                    b.classList.remove('active');
                });
                this.classList.add('active');
                // staged change — only apply on 套用 button
                state._pendingFilters = state._pendingFilters || Object.assign({}, state.filters);
                state._pendingFilters[field] = value;
            });
        });
    }

    function openFilterModal(filterKey) {
        state._pendingFilters = Object.assign({}, state.filters);
        var modal = $('filterModal');
        modal.classList.add('open');
        // 顯示全部 panel，但捲動到目標
        var panels = modal.querySelectorAll('.cy-filter-panel');
        panels.forEach(function (p) { p.style.display = ''; });
        var titleMap = { source: '來源', category: '分類', phase: '階段', date: '日期' };
        $('filterModalTitle').textContent = '篩選 · ' + (titleMap[filterKey] || '全部');

        // highlight current values
        modal.querySelectorAll('.cy-filter-opt').forEach(function (btn) {
            var f = btn.getAttribute('data-field');
            var v = btn.getAttribute('data-value');
            btn.classList.toggle('active', (state.filters[f] || '') === v);
        });
        $('filterDateFrom').value = state.filters.date_from || '';
        $('filterDateTo').value = state.filters.date_to || '';

        // 捲動到對應 panel
        var target = modal.querySelector('.cy-filter-panel[data-panel="' + filterKey + '"]');
        if (target) setTimeout(function () { target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 50);
    }

    function closeFilterModal() {
        $('filterModal').classList.remove('open');
    }

    function applyFilters() {
        var pending = state._pendingFilters || {};
        state.filters.source_model = pending.source_model || '';
        state.filters.category = pending.category || '';
        state.filters.construction_phase = pending.construction_phase || '';
        state.filters.date_from = $('filterDateFrom').value || '';
        state.filters.date_to = $('filterDateTo').value || '';

        updatePillLabels();
        updateFilterSummary();
        closeFilterModal();
        loadMarkers();
    }

    function clearFilters() {
        state._pendingFilters = { source_model: '', category: '', construction_phase: '' };
        $('filterDateFrom').value = '';
        $('filterDateTo').value = '';
        var modal = $('filterModal');
        modal.querySelectorAll('.cy-filter-opt').forEach(function (b) {
            b.classList.toggle('active', !b.getAttribute('data-value'));
        });
    }

    function resetAllFilters() {
        state.filters = { source_model: '', category: '', construction_phase: '', date_from: '', date_to: '', search: '' };
        var si = document.getElementById('photoMapSearch');
        var sc = document.getElementById('photoMapSearchClear');
        if (si) si.value = '';
        if (sc) sc.hidden = true;
        updatePillLabels();
        updateFilterSummary();
        loadMarkers();
    }

    function updatePillLabels() {
        var map = {
            source: ['source_model', '來源', 'source_model'],
            category: ['category', '分類', 'category'],
            phase: ['construction_phase', '階段', 'construction_phase'],
        };
        document.querySelectorAll('.cy-pill[data-filter]').forEach(function (pill) {
            var k = pill.getAttribute('data-filter');
            var lblEl = pill.querySelector('.cy-pill-label');
            if (k === 'date') {
                if (state.filters.date_from || state.filters.date_to) {
                    lblEl.textContent = (state.filters.date_from || '…') + '~' + (state.filters.date_to || '…');
                    pill.classList.add('active');
                } else {
                    lblEl.textContent = '日期';
                    pill.classList.remove('active');
                }
                return;
            }
            var cfg = map[k];
            if (!cfg) return;
            var field = cfg[0], defaultLabel = cfg[1];
            var val = state.filters[field];
            if (val) {
                var options = filterOptions[cfg[2]] || [];
                var labelText = val;
                for (var i = 0; i < options.length; i++) {
                    if (options[i][0] === val) { labelText = options[i][1]; break; }
                }
                lblEl.textContent = labelText;
                pill.classList.add('active');
            } else {
                lblEl.textContent = defaultLabel;
                pill.classList.remove('active');
            }
        });
    }

    function updateFilterSummary() {
        var el = $('filterSummary');
        if (!el) return;
        var chips = [];
        var opts = {
            source_model: filterOptions.source_model || [],
            category: filterOptions.category || [],
            construction_phase: filterOptions.construction_phase || [],
        };
        function labelOf(field, val) {
            for (var i = 0; i < opts[field].length; i++) {
                if (opts[field][i][0] === val) return opts[field][i][1];
            }
            return val;
        }
        if (state.filters.source_model) chips.push('來源：' + labelOf('source_model', state.filters.source_model));
        if (state.filters.category) chips.push('分類：' + labelOf('category', state.filters.category));
        if (state.filters.construction_phase) chips.push('階段：' + labelOf('construction_phase', state.filters.construction_phase));
        if (state.filters.date_from || state.filters.date_to) chips.push('日期：' + (state.filters.date_from || '…') + '~' + (state.filters.date_to || '…'));

        if (!chips.length) {
            el.innerHTML = '<span class="cy-filter-empty">尚未套用任何篩選</span>';
        } else {
            el.innerHTML = chips.map(function (c) { return '<span class="cy-filter-chip">' + escapeHtml(c) + '</span>'; }).join('');
        }
    }

    // =============================================
    // Bottom Sheet
    // =============================================
    function setSheetState(s) {
        state.sheetState = s;
        var sheet = $('photoMapSheet');
        sheet.classList.remove('cy-map-sheet-peek', 'cy-map-sheet-half', 'cy-map-sheet-full');
        sheet.classList.add('cy-map-sheet-' + s);
        setTimeout(function () { if (state.map) state.map.invalidateSize(); }, 350);
    }

    function initSheetDrag() {
        var handle = $('sheetHandle');
        var sheet = $('photoMapSheet');
        var startY = 0, startState = 'peek';
        handle.addEventListener('touchstart', function (e) {
            startY = e.touches[0].clientY;
            startState = state.sheetState;
        }, { passive: true });
        handle.addEventListener('touchend', function (e) {
            var dy = (e.changedTouches[0].clientY - startY);
            if (dy < -40) {
                // 上拉
                setSheetState(startState === 'peek' ? 'half' : 'full');
            } else if (dy > 40) {
                // 下拉
                setSheetState(startState === 'full' ? 'half' : 'peek');
            }
        });
        handle.addEventListener('click', function () {
            // 點擊把手：循環 peek → half → full → peek
            if (state.sheetState === 'peek') setSheetState('half');
            else if (state.sheetState === 'half') setSheetState('full');
            else setSheetState('peek');
        });
    }

    // =============================================
    // Tab
    // =============================================
    function switchTab(tabName) {
        state.activeTab = tabName;
        document.querySelectorAll('.cy-seg-btn').forEach(function (b) {
            b.classList.toggle('active', b.dataset.tab === tabName);
        });
        document.querySelectorAll('.cy-sheet-tab').forEach(function (t) {
            t.classList.toggle('active', t.dataset.tabContent === tabName);
        });
        if (tabName === 'area') loadAreaPhotos(true);
        if (state.sheetState === 'peek') setSheetState('half');
    }

    // =============================================
    // 事件綁定
    // =============================================
    function bindEvents() {
        // 頂部搜尋列(Google Maps 風)
        var searchInput = $('photoMapSearch');
        var searchClear = $('photoMapSearchClear');
        if (searchInput && searchClear) {
            var searchTimer = null;
            searchInput.addEventListener('input', function () {
                var v = this.value;
                searchClear.hidden = !v;
                clearTimeout(searchTimer);
                searchTimer = setTimeout(function () {
                    state.filters.search = v.trim();
                    loadMarkers();
                }, 300);
            });
            searchClear.addEventListener('click', function () {
                searchInput.value = '';
                searchClear.hidden = true;
                state.filters.search = '';
                loadMarkers();
                searchInput.focus();
            });
            // Enter 立即觸發(略過 debounce)
            searchInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    clearTimeout(searchTimer);
                    state.filters.search = this.value.trim();
                    loadMarkers();
                    this.blur();
                }
            });
        }

        // Pill → 篩選 Modal
        document.querySelectorAll('.cy-pill[data-filter]').forEach(function (pill) {
            pill.addEventListener('click', function () { openFilterModal(this.dataset.filter); });
        });
        $('btnResetFilter').addEventListener('click', resetAllFilters);
        $('btnCloseFilterModal').addEventListener('click', closeFilterModal);
        document.querySelector('.cy-filter-modal-backdrop').addEventListener('click', closeFilterModal);
        $('btnFilterApply').addEventListener('click', applyFilters);
        $('btnFilterClear').addEventListener('click', clearFilters);

        // FAB
        $('btnMyLocation').addEventListener('click', function () { locateMe(true); });
        $('btnFitAll').addEventListener('click', fitAllMarkers);

        // 圖例 chip
        var legendChip = $('mapLegendChip');
        $('btnToggleLegend').addEventListener('click', function () {
            legendChip.classList.toggle('open');
        });

        // Segmented control
        document.querySelectorAll('.cy-seg-btn').forEach(function (b) {
            b.addEventListener('click', function () { switchTab(this.dataset.tab); });
        });

        // 載入更多
        $('btnLoadMore').addEventListener('click', function () { loadAreaPhotos(false); });

        // 半徑
        document.querySelectorAll('.cy-radius-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.cy-radius-btn').forEach(function (b) { b.classList.remove('active'); });
                this.classList.add('active');
                state.nearbyRadius = parseFloat(this.dataset.radius);
                if (state.userCircle) state.userCircle.setRadius(state.nearbyRadius * 1000);
                if (state.userLat) loadNearbyPhotos(state.userLat, state.userLng, state.nearbyRadius);
            });
        });
    }

    // =============================================
    // 初始化
    // =============================================
    initMap();
    renderFilterOptions();
    initLightbox();
    initSheetDrag();
    bindEvents();
    loadMarkers();
})();
