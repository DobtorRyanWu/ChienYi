/**
 * ChienYi Portal v10 — vanilla JS 互動
 * 不用 OWL、不用 jQuery、不需要 build 工具
 *
 * 使用 readyState 檢查：如果 DOM 還在載入就等，已載入就直接執行。
 * 這樣無論 Odoo asset bundle 何時執行都能正確綁定事件。
 */
(function () {
    'use strict';

    function initPortalV10() {
        // 只在 v10 app 頁面執行
        if (!document.querySelector('.cy-v10-app')) return;

    // === 快速新增下拉 toggle ===
    var quickTrigger = document.getElementById('quickAddTrigger');
    var quickMenu = document.getElementById('quickAddMenu');
    if (quickTrigger && quickMenu) {
        // 選單項目：點擊時阻止冒泡，讓 <a> 正常導航
        quickMenu.querySelectorAll('.cy-quick-add-item').forEach(function (item) {
            item.addEventListener('click', function (e) {
                e.stopPropagation();
                // 不 preventDefault → <a> 正常跳轉
            });
        });
        // 觸發按鈕：toggle 選單顯示/隱藏
        quickTrigger.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var isOpen = quickMenu.style.display !== 'none';
            quickMenu.style.display = isOpen ? 'none' : '';
            quickTrigger.style.background = isOpen ? '' : 'rgba(230,160,32,0.12)';
            quickTrigger.style.borderColor = isOpen ? '' : 'var(--wb-amber)';
        });
        // 點擊其他地方關閉
        document.addEventListener('click', function (e) {
            if (!quickTrigger.contains(e.target)) {
                quickMenu.style.display = 'none';
                quickTrigger.style.background = '';
                quickTrigger.style.borderColor = '';
            }
        });
    }

    // === 底部導航點擊 → HUD logo pulse 動畫 ===
    var hudLogoBox = document.getElementById('hudLogoBox');
    if (hudLogoBox) {
        document.querySelectorAll('.cy-nav-item').forEach(function (navItem) {
            navItem.addEventListener('click', function () {
                hudLogoBox.classList.remove('pulse');
                // 強制 reflow 讓動畫可重複觸發
                void hudLogoBox.offsetWidth;
                hudLogoBox.classList.add('pulse');
            });
        });
    }

    // === FAB 相機 — 照片頁隱藏，其他頁顯示 ===
    var fabCamera = document.querySelector('.cy-fab-camera');
    if (fabCamera && window.location.pathname.match(/\/photos/)) {
        fabCamera.style.display = 'none';
    }

    // === FAB 相機 — 拍照後導向上傳頁 ===
    var fabInput = document.getElementById('fab_camera_input');
    if (fabInput) {
        fabInput.addEventListener('change', function () {
            if (fabInput.files && fabInput.files[0]) {
                // 找到 project id（從 URL 解析）
                var m = window.location.pathname.match(/\/my\/construction\/(\d+)/);
                if (m) {
                    window.location.href = '/my/construction/' + m[1] + '/photo/upload';
                }
            }
        });
    }

    // === 事件卡片 dismiss ===
    document.querySelectorAll('[data-dismiss-event]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var card = btn.closest('.cy-event-card');
            if (card) {
                card.style.transition = 'opacity 0.3s, max-height 0.3s';
                card.style.opacity = '0';
                card.style.maxHeight = '0';
                card.style.overflow = 'hidden';
                card.style.marginBottom = '0';
                card.style.padding = '0';
                setTimeout(function () { card.remove(); }, 300);
            }
        });
    });

    // === 可摺疊區塊 ===
    document.querySelectorAll('[data-collapse-toggle]').forEach(function (trigger) {
        trigger.addEventListener('click', function () {
            var targetId = trigger.getAttribute('data-collapse-toggle');
            var target = document.getElementById(targetId);
            if (!target) return;
            var isHidden = target.style.display === 'none';
            target.style.display = isHidden ? '' : 'none';
            var icon = trigger.querySelector('.fa-chevron-down, .fa-chevron-up');
            if (icon) {
                icon.classList.toggle('fa-chevron-down');
                icon.classList.toggle('fa-chevron-up');
            }
        });
    });

    // === 安全衛生 yes/no 按鈕 toggle（Selection 型別）===
    document.querySelectorAll('.cy-yesno-group').forEach(function (group) {
        var hidden = group.querySelector('input[type="hidden"]');
        var btns = group.querySelectorAll('.cy-yesno-btn');

        btns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                var val = btn.getAttribute('data-value');
                // 取消所有 active
                btns.forEach(function (b) { b.classList.remove('active'); });
                // 設定當前
                btn.classList.add('active');
                if (hidden) hidden.value = val;
            });
        });
    });

    // === 問題標記 checkbox → 條件顯示 issue_description ===
    document.querySelectorAll('.issue-checkbox').forEach(function (cb) {
        var wrap = cb.closest('.cy-card-body') || cb.parentElement.parentElement;
        var descWrap = wrap.querySelector('.issue-desc-wrap');
        if (!descWrap) return;

        cb.addEventListener('change', function () {
            descWrap.style.display = cb.checked ? '' : 'none';
        });
    });

    // === 工項下拉 / 自行輸入切換 ===
    // 初始化時備份原始 select HTML（避免切換後找不到原始下拉）
    var _origSelectHTML = '';
    var _origSelect = document.querySelector('.work-line-item[data-index="0"] select.work-item-select');
    if (_origSelect) {
        _origSelectHTML = _origSelect.outerHTML;
    }

    document.querySelectorAll('.toggle-input-mode').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var card = btn.closest('.work-line-item');
            if (!card) return;
            var sel = card.querySelector('.work-item-select');
            if (!sel) return;
            var idx = card.getAttribute('data-index');

            if (sel.tagName === 'SELECT') {
                // 切換為手動輸入
                var input = document.createElement('input');
                input.type = 'text';
                input.name = sel.name;
                input.className = 'form-control work-item-select';
                input.placeholder = '輸入工項名稱';
                sel.parentElement.replaceChild(input, sel);
                btn.textContent = '切換下拉選擇';
            } else {
                // 切換回下拉（用備份的 HTML 還原）
                if (_origSelectHTML) {
                    var temp = document.createElement('div');
                    temp.innerHTML = _origSelectHTML;
                    var newSel = temp.firstChild;
                    newSel.name = 'line_work_item_id_' + idx;
                    sel.parentElement.replaceChild(newSel, sel);
                }
                btn.textContent = '切換自行輸入';
            }
        });
    });

    // === 新增/刪除工項行 ===
    var lineContainer = document.getElementById('work_lines_container');
    var addLineBtn = document.getElementById('btn_add_line');
    var lineCount = 1; // 已有第 0 行

    if (addLineBtn && lineContainer) {
        addLineBtn.addEventListener('click', function () {
            var idx = lineCount;
            lineCount++;

            // 複製第一行的結構
            var firstLine = lineContainer.querySelector('.work-line-item');
            if (!firstLine) return;
            var newLine = firstLine.cloneNode(true);

            // 更新 index
            newLine.setAttribute('data-index', idx);
            newLine.querySelector('span').textContent = '工項 #' + (idx + 1);

            // 更新 name 屬性
            var inputs = newLine.querySelectorAll('input, select, textarea');
            inputs.forEach(function (inp) {
                if (inp.name) {
                    inp.name = inp.name.replace(/_\d+$/, '_' + idx);
                }
                if (inp.id) {
                    inp.id = inp.id.replace(/_\d+$/, '_' + idx);
                }
                // 清空值
                if (inp.tagName === 'SELECT') {
                    inp.selectedIndex = 0;
                } else if (inp.type === 'checkbox') {
                    inp.checked = false;
                } else {
                    inp.value = '';
                }
            });

            // 隱藏問題說明
            var issueWrap = newLine.querySelector('.issue-desc-wrap');
            if (issueWrap) issueWrap.style.display = 'none';

            // 重新綁定事件
            var issueCb = newLine.querySelector('.issue-checkbox');
            if (issueCb && issueWrap) {
                issueCb.addEventListener('change', function () {
                    issueWrap.style.display = issueCb.checked ? '' : 'none';
                });
            }

            var toggleBtn = newLine.querySelector('.toggle-input-mode');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', function () {
                    var sel = newLine.querySelector('.work-item-select');
                    if (!sel) return;
                    if (sel.tagName === 'SELECT') {
                        var input = document.createElement('input');
                        input.type = 'text';
                        input.name = sel.name;
                        input.className = 'form-control work-item-select';
                        input.placeholder = '輸入工項名稱';
                        sel.parentElement.replaceChild(input, sel);
                        toggleBtn.textContent = '切換下拉選擇';
                    }
                });
            }

            lineContainer.appendChild(newLine);
        });

        // 刪除工項行（事件委派）
        lineContainer.addEventListener('click', function (e) {
            var btn = e.target.closest('.btn-remove-line');
            if (!btn) return;
            var items = lineContainer.querySelectorAll('.work-line-item');
            if (items.length <= 1) return; // 至少保留一行
            var card = btn.closest('.work-line-item');
            if (card) card.remove();
        });
    }

    // === 自主檢查：三按鈕 toggle (pass/defect/na) + 計數更新 ===
    function updateInspCounts() {
        var passCount = document.querySelectorAll('.insp-check-btn.active[data-result="pass"]').length;
        var defectCount = document.querySelectorAll('.insp-check-btn.active[data-result="defect"]').length;
        var naCount = document.querySelectorAll('.insp-check-btn.active[data-result="na"]').length;
        var passEl = document.querySelector('.insp-count-pass');
        var defectEl = document.querySelector('.insp-count-defect');
        var naEl = document.querySelector('.insp-count-na');
        if (passEl) passEl.textContent = passCount;
        if (defectEl) defectEl.textContent = defectCount;
        if (naEl) naEl.textContent = naCount;
    }

    document.querySelectorAll('.insp-check-group').forEach(function (group) {
        var hidden = group.querySelector('input[type="hidden"]');
        var btns = group.querySelectorAll('.insp-check-btn');

        btns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                btns.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                if (hidden) hidden.value = btn.getAttribute('data-result');
                updateInspCounts();
            });
        });
    });

    // 頁面載入時計算初始計數
    updateInspCounts();

    // === 批次照片上傳 ===
    var batchCameraInput = document.getElementById('photo_camera_input');
    var batchGalleryInput = document.getElementById('photo_gallery_input');
    var btnCamera = document.getElementById('btn_camera');
    var btnGallery = document.getElementById('btn_gallery');
    var btnBatchUpload = document.getElementById('btn_batch_upload');

    if (btnCamera && batchCameraInput) {
        var batchFiles = [];
        var batchIdCounter = 0;
        var BATCH_MAX = 50;
        var isUploading = false;

        // 觸發拍照
        btnCamera.addEventListener('click', function () {
            batchCameraInput.click();
        });

        // 觸發相簿選擇
        btnGallery.addEventListener('click', function () {
            batchGalleryInput.click();
        });

        // 拍照回傳（單張）
        batchCameraInput.addEventListener('change', function () {
            if (batchCameraInput.files.length > 0) {
                addFilesToBatch([batchCameraInput.files[0]]);
                batchCameraInput.value = '';
            }
        });

        // 相簿回傳（多張）
        batchGalleryInput.addEventListener('change', function () {
            if (batchGalleryInput.files.length > 0) {
                var files = Array.prototype.slice.call(batchGalleryInput.files);
                addFilesToBatch(files);
                batchGalleryInput.value = '';
            }
        });

        // 將檔案加入批次
        function addFilesToBatch(files) {
            var remaining = BATCH_MAX - batchFiles.length;
            if (remaining <= 0) {
                alert('一次最多上傳 ' + BATCH_MAX + ' 張照片');
                return;
            }
            var toAdd = files.slice(0, remaining);
            if (toAdd.length < files.length) {
                alert('已達上限，僅加入前 ' + toAdd.length + ' 張（上限 ' + BATCH_MAX + ' 張）');
            }
            toAdd.forEach(function (file) {
                if (!file.type.startsWith('image/')) return;
                var id = ++batchIdCounter;
                var item = { file: file, id: id, thumbnail: '' };
                batchFiles.push(item);
                // 產生縮圖
                generateThumbnail(file, function (dataUrl) {
                    item.thumbnail = dataUrl;
                    renderBatchGrid();
                });
                // 嘗試從 EXIF 自動填入 GPS（欄位為空才填）
                tryFillGpsFromExif(file);
            });
            renderBatchGrid();
        }

        // 從照片 EXIF 讀取 GPS 並自動填入欄位（欄位已有值則不覆寫）
        function tryFillGpsFromExif(file) {
            var latInput = document.getElementById('photo_latitude');
            var lngInput = document.getElementById('photo_longitude');
            if (!latInput || !lngInput) return;
            if (latInput.value && lngInput.value) return;
            readExifGps(file).then(function (gps) {
                if (!gps) return;
                if (!latInput.value) latInput.value = gps.lat.toFixed(6);
                if (!lngInput.value) lngInput.value = gps.lng.toFixed(6);
                var statusEl = document.getElementById('gps_status');
                if (statusEl) {
                    statusEl.textContent = '✓ 已從照片 EXIF 讀取';
                    statusEl.style.color = 'var(--wb-green)';
                }
            }).catch(function () { /* 靜默失敗 */ });
        }

        // 純 vanilla JS 解析 JPEG EXIF 的 GPS 座標
        // 回傳 Promise<{lat, lng} | null>，任何失敗都 resolve(null)
        function readExifGps(file) {
            return new Promise(function (resolve) {
                if (!file || !/jpe?g$/i.test(file.type)) {
                    resolve(null);
                    return;
                }
                // 只讀前 256KB，EXIF 在開頭
                var blob = file.slice(0, 256 * 1024);
                var reader = new FileReader();
                reader.onerror = function () { resolve(null); };
                reader.onload = function (e) {
                    try {
                        var view = new DataView(e.target.result);
                        // JPEG SOI
                        if (view.getUint16(0, false) !== 0xFFD8) { resolve(null); return; }
                        var length = view.byteLength;
                        var offset = 2;
                        var tiffOffset = -1;
                        while (offset < length) {
                            if (view.getUint8(offset) !== 0xFF) { resolve(null); return; }
                            var marker = view.getUint8(offset + 1);
                            if (marker === 0xE1) {
                                // APP1 — 檢查 "Exif\0\0"
                                if (view.getUint32(offset + 4, false) !== 0x45786966) { resolve(null); return; }
                                tiffOffset = offset + 10;
                                break;
                            }
                            offset += 2 + view.getUint16(offset + 2, false);
                        }
                        if (tiffOffset < 0) { resolve(null); return; }
                        // TIFF header: byte order
                        var bom = view.getUint16(tiffOffset, false);
                        var little;
                        if (bom === 0x4949) little = true;
                        else if (bom === 0x4D4D) little = false;
                        else { resolve(null); return; }
                        if (view.getUint16(tiffOffset + 2, little) !== 0x002A) { resolve(null); return; }
                        var ifd0Offset = tiffOffset + view.getUint32(tiffOffset + 4, little);
                        // 掃 IFD0，找 GPS IFD (tag 0x8825)
                        var gpsIfdOffset = findTag(view, ifd0Offset, little, 0x8825);
                        if (!gpsIfdOffset) { resolve(null); return; }
                        gpsIfdOffset = tiffOffset + gpsIfdOffset;
                        // 抓 GPS IFD 裡的 lat/lng 與 ref
                        var gps = parseGpsIfd(view, gpsIfdOffset, tiffOffset, little);
                        resolve(gps);
                    } catch (err) {
                        resolve(null);
                    }
                };
                reader.readAsArrayBuffer(blob);
            });
        }

        // 在指定 IFD 中尋找 tag 的 value（只支援 LONG 型）
        function findTag(view, ifdOffset, little, targetTag) {
            var entries = view.getUint16(ifdOffset, little);
            for (var i = 0; i < entries; i++) {
                var entry = ifdOffset + 2 + i * 12;
                var tag = view.getUint16(entry, little);
                if (tag === targetTag) {
                    return view.getUint32(entry + 8, little);
                }
            }
            return 0;
        }

        // 解析 GPS IFD，回傳 {lat, lng} 或 null
        function parseGpsIfd(view, ifdOffset, tiffOffset, little) {
            var entries = view.getUint16(ifdOffset, little);
            var latRef = null, lngRef = null, lat = null, lng = null;
            for (var i = 0; i < entries; i++) {
                var entry = ifdOffset + 2 + i * 12;
                var tag = view.getUint16(entry, little);
                var type = view.getUint16(entry + 2, little);
                var count = view.getUint32(entry + 4, little);
                var valueOffset = entry + 8;
                if (tag === 0x0001 && type === 2) {
                    latRef = String.fromCharCode(view.getUint8(valueOffset));
                } else if (tag === 0x0003 && type === 2) {
                    lngRef = String.fromCharCode(view.getUint8(valueOffset));
                } else if (tag === 0x0002 && type === 5 && count === 3) {
                    lat = readRational3(view, tiffOffset + view.getUint32(valueOffset, little), little);
                } else if (tag === 0x0004 && type === 5 && count === 3) {
                    lng = readRational3(view, tiffOffset + view.getUint32(valueOffset, little), little);
                }
            }
            if (lat === null || lng === null || !latRef || !lngRef) return null;
            var latDec = dmsToDec(lat);
            var lngDec = dmsToDec(lng);
            if (latRef === 'S') latDec = -latDec;
            if (lngRef === 'W') lngDec = -lngDec;
            if (isNaN(latDec) || isNaN(lngDec)) return null;
            return { lat: latDec, lng: lngDec };
        }

        // 讀取 3 個 RATIONAL (度/分/秒)
        function readRational3(view, offset, little) {
            var out = [];
            for (var i = 0; i < 3; i++) {
                var num = view.getUint32(offset + i * 8, little);
                var den = view.getUint32(offset + i * 8 + 4, little);
                out.push(den === 0 ? 0 : num / den);
            }
            return out;
        }

        // 度分秒 → 十進制
        function dmsToDec(dms) {
            return dms[0] + dms[1] / 60 + dms[2] / 3600;
        }

        // canvas 縮圖產生（避免載入原圖到 DOM）
        function generateThumbnail(file, callback) {
            var reader = new FileReader();
            reader.onload = function (e) {
                var img = new Image();
                img.onload = function () {
                    var canvas = document.createElement('canvas');
                    var maxW = 200;
                    var scale = Math.min(maxW / img.width, maxW / img.height);
                    if (scale > 1) scale = 1;
                    canvas.width = img.width * scale;
                    canvas.height = img.height * scale;
                    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                    callback(canvas.toDataURL('image/jpeg', 0.7));
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }

        // 渲染縮圖網格
        function renderBatchGrid() {
            var grid = document.getElementById('photo_batch_grid');
            var empty = document.getElementById('photo_batch_empty');
            var countEl = document.getElementById('photo_batch_count');
            var countNum = document.getElementById('batch_count_num');
            var btnCount = document.getElementById('upload_btn_count');

            if (!grid) return;
            grid.innerHTML = '';

            if (batchFiles.length === 0) {
                if (empty) empty.style.display = '';
                if (countEl) countEl.style.display = 'none';
                if (btnBatchUpload) btnBatchUpload.disabled = true;
            } else {
                if (empty) empty.style.display = 'none';
                if (countEl) countEl.style.display = '';
                if (countNum) countNum.textContent = batchFiles.length;
                if (btnCount) btnCount.textContent = batchFiles.length;
                if (btnBatchUpload) btnBatchUpload.disabled = false;
            }

            batchFiles.forEach(function (item) {
                var div = document.createElement('div');
                div.className = 'batch-photo-item';

                var imgEl = document.createElement('img');
                imgEl.alt = item.file.name;
                imgEl.src = item.thumbnail || 'data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==';
                div.appendChild(imgEl);

                // 移除按鈕
                var removeBtn = document.createElement('button');
                removeBtn.className = 'batch-photo-remove';
                removeBtn.type = 'button';
                removeBtn.innerHTML = '&times;';
                removeBtn.setAttribute('data-id', item.id);
                removeBtn.addEventListener('click', function () {
                    removeBatchFile(item.id);
                });
                div.appendChild(removeBtn);

                // 檔名
                var nameDiv = document.createElement('div');
                nameDiv.className = 'batch-photo-name';
                nameDiv.textContent = item.file.name;
                div.appendChild(nameDiv);

                // 大檔警告
                if (item.file.size > 10 * 1024 * 1024) {
                    var warnDiv = document.createElement('div');
                    warnDiv.style.cssText = 'font-size: 0.7rem; color: var(--wb-amber); padding: 0 4px 2px;';
                    warnDiv.textContent = '⚠ ' + (item.file.size / 1024 / 1024).toFixed(1) + 'MB';
                    div.appendChild(warnDiv);
                }

                grid.appendChild(div);
            });
        }

        // 移除單張照片
        function removeBatchFile(id) {
            batchFiles = batchFiles.filter(function (item) { return item.id !== id; });
            renderBatchGrid();
        }

        // 檔案轉 base64
        function fileToBase64(file) {
            return new Promise(function (resolve, reject) {
                var reader = new FileReader();
                reader.onload = function () {
                    // 去掉 data:image/...;base64, 前綴
                    var result = reader.result;
                    var idx = result.indexOf(',');
                    resolve(idx >= 0 ? result.substring(idx + 1) : result);
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
        }

        // 批次上傳按鈕
        if (btnBatchUpload) {
            btnBatchUpload.addEventListener('click', function () {
                if (isUploading || batchFiles.length === 0) return;
                startBatchUpload();
            });
        }

        // 開始批次上傳
        function startBatchUpload() {
            isUploading = true;
            btnBatchUpload.disabled = true;
            btnCamera.disabled = true;
            btnGallery.disabled = true;

            // 收集共用 metadata
            var form = document.getElementById('batch_upload_form');
            var metadata = {
                project_id: parseInt(form.querySelector('input[name="project_id"]').value),
                description: (form.querySelector('textarea[name="description"]').value || '').trim(),
                category: form.querySelector('select[name="category"]').value || '',
                construction_phase: form.querySelector('select[name="construction_phase"]').value || '',
                source_model: form.querySelector('select[name="source_model"]').value || '',
                location_description: (form.querySelector('input[name="location_description"]').value || '').trim(),
                latitude: form.querySelector('input[name="latitude"]').value || '',
                longitude: form.querySelector('input[name="longitude"]').value || '',
                photo_date: form.querySelector('input[name="photo_date"]').value || ''
            };

            var overlay = document.getElementById('upload_progress_overlay');
            var progressBar = document.getElementById('upload_progress_bar');
            var progressText = document.getElementById('upload_progress_text');
            var progressFile = document.getElementById('upload_progress_file');

            if (overlay) overlay.style.display = '';

            var total = batchFiles.length;
            var successCount = 0;
            var failedFiles = [];

            // 防止離開頁面
            window.addEventListener('beforeunload', preventUnload);

            // 逐張上傳
            var chain = Promise.resolve();
            batchFiles.slice().forEach(function (item, index) {
                chain = chain.then(function () {
                    // 更新進度
                    var pct = Math.round(((index) / total) * 100);
                    if (progressBar) progressBar.style.width = pct + '%';
                    if (progressText) progressText.textContent = (index + 1) + ' / ' + total;
                    if (progressFile) progressFile.textContent = item.file.name;

                    return fileToBase64(item.file).then(function (b64) {
                        var params = {};
                        // 合併 metadata
                        for (var k in metadata) {
                            if (metadata.hasOwnProperty(k)) params[k] = metadata[k];
                        }
                        params.photo_data = b64;
                        params.filename = item.file.name;

                        return fetch('/my/construction/photo/upload/ajax', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                jsonrpc: '2.0',
                                method: 'call',
                                params: params
                            })
                        });
                    }).then(function (res) { return res.json(); })
                      .then(function (data) {
                          if (data.result && data.result.success) {
                              successCount++;
                          } else {
                              failedFiles.push(item.file.name);
                          }
                      })
                      .catch(function () {
                          failedFiles.push(item.file.name);
                      });
                });
            });

            chain.then(function () {
                // 上傳完成
                if (progressBar) progressBar.style.width = '100%';
                window.removeEventListener('beforeunload', preventUnload);
                isUploading = false;

                if (failedFiles.length === 0) {
                    // 全部成功 → 跳轉
                    window.location.href = '/my/construction/' + metadata.project_id + '/photos?message=uploaded&count=' + successCount;
                } else {
                    // 部分失敗
                    if (overlay) overlay.style.display = 'none';
                    // 移除成功的，保留失敗的
                    batchFiles = batchFiles.filter(function (item) {
                        return failedFiles.indexOf(item.file.name) >= 0;
                    });
                    renderBatchGrid();
                    btnBatchUpload.disabled = false;
                    btnCamera.disabled = false;
                    btnGallery.disabled = false;
                    alert('上傳完成：' + successCount + ' 張成功，' + failedFiles.length + ' 張失敗\n失敗檔案：' + failedFiles.join(', '));
                }
            });
        }

        function preventUnload(e) {
            e.preventDefault();
            e.returnValue = '';
        }
    }

    // === 通用 GPS 定位(供 photos block 等使用)===
    // 用法: <button onclick="cyGetGeo(this);"> — 會找最近 form 內的 .cy-photos-lat / .cy-photos-lng
    window.cyGetGeo = function (btn) {
        var form = btn.closest('form');
        if (!form) return;
        var latInput = form.querySelector('.cy-photos-lat');
        var lngInput = form.querySelector('.cy-photos-lng');
        if (!navigator.geolocation) {
            btn.textContent = '不支援 GPS';
            return;
        }
        var origText = btn.innerHTML;
        btn.innerHTML = '<i class="fa fa-spinner fa-spin"/> 定位中...';
        navigator.geolocation.getCurrentPosition(
            function (pos) {
                if (latInput) latInput.value = pos.coords.latitude.toFixed(6);
                if (lngInput) lngInput.value = pos.coords.longitude.toFixed(6);
                btn.innerHTML = '<i class="fa fa-check"/> 已取得';
            },
            function () {
                btn.innerHTML = origText;
                alert('無法取得位置');
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    };

    // === GPS 定位 ===
    var gpsBtn = document.getElementById('btn_get_gps');
    if (gpsBtn) {
        gpsBtn.addEventListener('click', function () {
            var latInput = document.getElementById('photo_latitude');
            var lngInput = document.getElementById('photo_longitude');
            var statusEl = document.getElementById('gps_status');

            if (!navigator.geolocation) {
                if (statusEl) statusEl.textContent = '瀏覽器不支援 GPS';
                return;
            }

            // HTTP 環境瀏覽器會擋 geolocation，先預檢避免使用者卡在「定位中...」
            var isSecure = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
            if (!isSecure) {
                if (statusEl) {
                    statusEl.textContent = '此網址非 HTTPS，無法取得 GPS — 請改用相機拍攝（自動帶 EXIF 座標）或手動輸入';
                    statusEl.style.color = 'var(--wb-red)';
                }
                return;
            }

            if (statusEl) statusEl.textContent = '定位中...';

            navigator.geolocation.getCurrentPosition(
                function (pos) {
                    if (latInput) latInput.value = pos.coords.latitude.toFixed(6);
                    if (lngInput) lngInput.value = pos.coords.longitude.toFixed(6);
                    if (statusEl) statusEl.textContent = '✓ 已取得';
                    if (statusEl) statusEl.style.color = 'var(--wb-green)';
                },
                function (err) {
                    var msg = '定位失敗';
                    if (err.code === 1) msg = '使用者拒絕定位';
                    else if (err.code === 2) msg = '無法取得位置';
                    else if (err.code === 3) msg = '定位逾時';
                    if (statusEl) statusEl.textContent = msg;
                    if (statusEl) statusEl.style.color = 'var(--wb-red)';
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        });
    }

    // === 缺失類型按鈕 toggle ===
    var defectTypeBtns = document.getElementById('defect_type_btns');
    var defectTypeHidden = document.getElementById('defect_type_hidden');
    if (defectTypeBtns && defectTypeHidden) {
        defectTypeBtns.querySelectorAll('.cy-type-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                defectTypeBtns.querySelectorAll('.cy-type-btn').forEach(function (b) {
                    b.style.background = 'var(--wb-bg3)';
                    b.style.color = 'var(--wb-t2)';
                });
                btn.style.background = 'var(--wb-amber)';
                btn.style.color = '#fff';
                defectTypeHidden.value = btn.getAttribute('data-value');
            });
        });
    }

    // === 缺失照片預覽 ===
    var defectPhotoInput = document.getElementById('defect_photo_input');
    var defectPhotoPreview = document.getElementById('defect_photo_preview');
    var defectPhotoImg = document.getElementById('defect_photo_preview_img');
    if (defectPhotoInput && defectPhotoPreview && defectPhotoImg) {
        defectPhotoInput.addEventListener('change', function () {
            var file = defectPhotoInput.files[0];
            if (file && file.type.startsWith('image/')) {
                var reader = new FileReader();
                reader.onload = function (e) {
                    defectPhotoImg.src = e.target.result;
                    defectPhotoPreview.style.display = '';
                };
                reader.readAsDataURL(file);
            } else {
                defectPhotoPreview.style.display = 'none';
            }
        });
    }

    // === 自主檢查表單：選類型後 AJAX 載入 checklist items ===
    var inspTypeSelect = document.getElementById('inspection_type_select');
    var checklistContainer = document.getElementById('checklist_container');
    if (inspTypeSelect && checklistContainer) {
        inspTypeSelect.addEventListener('change', function () {
            var typeId = inspTypeSelect.value;
            if (!typeId) {
                checklistContainer.innerHTML = '<div class="cy-empty" style="padding: 20px;"><div class="cy-empty-text">請先選擇檢查類型</div></div>';
                return;
            }

            checklistContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--wb-t3);">載入中...</div>';

            fetch('/my/construction/inspection/get-items', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: { type_id: parseInt(typeId) }
                })
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var result = data.result || {};
                var items = result.items || [];
                var stages = result.stages || [];

                if (items.length === 0) {
                    checklistContainer.innerHTML = '<div class="cy-empty" style="padding: 20px;"><div class="cy-empty-text">此類型沒有預設檢查項目</div></div>';
                    updateSubmitCount(0, 0);
                    return;
                }

                var html = '';
                var itemIdx = 0;

                stages.forEach(function (stage) {
                    html += '<div style="font-size: 0.85rem; font-weight: 700; color: var(--wb-amber); margin: 12px 0 8px;">' + stage.label + '</div>';

                    items.forEach(function (item) {
                        if (item.stage !== stage.key) return;

                        html += '<div class="cy-card" style="margin-bottom: 8px;">';
                        html += '<div class="cy-card-body" style="padding: 12px 14px;">';
                        html += '<div style="font-weight: 700; font-size: 0.9rem; margin-bottom: 4px;">' + escHtml(item.name) + '</div>';
                        if (item.standard) {
                            html += '<div style="font-size: 0.8rem; color: var(--wb-t3); margin-bottom: 8px;">標準：' + escHtml(item.standard) + '</div>';
                        }

                        // 隱藏欄位
                        html += '<input type="hidden" name="checklist_item_id_' + itemIdx + '" value="' + item.id + '"/>';
                        html += '<input type="hidden" name="checklist_result_' + itemIdx + '" value="pass" class="checklist-result-hidden"/>';

                        // 三按鈕 toggle
                        html += '<div class="insp-check-group">';
                        html += '<button type="button" class="insp-check-btn active" data-result="pass" data-idx="' + itemIdx + '">合格</button>';
                        html += '<button type="button" class="insp-check-btn" data-result="defect" data-idx="' + itemIdx + '">有缺失</button>';
                        html += '<button type="button" class="insp-check-btn" data-result="na" data-idx="' + itemIdx + '">無此項</button>';
                        html += '</div>';

                        // 實際結果 textarea
                        html += '<div style="margin-top: 8px;">';
                        html += '<input type="text" name="checklist_actual_' + itemIdx + '" class="form-control" placeholder="實際檢查情形" style="min-height: 40px; font-size: 0.85rem;"/>';
                        html += '</div>';

                        html += '</div></div>';
                        itemIdx++;
                    });
                });

                checklistContainer.innerHTML = html;
                updateSubmitCount(0, itemIdx);

                // 綁定三按鈕事件
                checklistContainer.querySelectorAll('.insp-check-group').forEach(function (group) {
                    var btns = group.querySelectorAll('.insp-check-btn');
                    btns.forEach(function (btn) {
                        btn.addEventListener('click', function () {
                            btns.forEach(function (b) { b.classList.remove('active'); });
                            btn.classList.add('active');
                            var idx = btn.getAttribute('data-idx');
                            var hidden = checklistContainer.querySelector('input[name="checklist_result_' + idx + '"]');
                            if (hidden) hidden.value = btn.getAttribute('data-result');
                            // 更新計數
                            var filled = checklistContainer.querySelectorAll('.insp-check-btn.active').length;
                            var total = checklistContainer.querySelectorAll('.insp-check-group').length;
                            updateSubmitCount(filled, total);
                            updateInspCounts();
                        });
                    });
                });

                // 初始計數
                updateInspCounts();
            })
            .catch(function () {
                checklistContainer.innerHTML = '<div class="cy-empty" style="padding: 20px;"><div class="cy-empty-text" style="color: var(--wb-red);">載入失敗</div></div>';
            });
        });
    }

    function escHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function updateSubmitCount(filled, total) {
        var submitBtn = document.querySelector('.cy-v10-app form button[type="submit"]');
        if (submitBtn && total > 0) {
            var text = submitBtn.textContent.replace(/\s*\(\d+\/\d+\)/, '');
            submitBtn.textContent = text + ' (' + filled + '/' + total + ')';
        }
    }

    // === 14天鎖定：鎖定的日誌 disable 所有 input ===
    var lockedBanner = document.querySelector('.cy-event-card .fa-lock');
    if (lockedBanner) {
        var appForm = document.querySelector('.cy-v10-app form');
        if (appForm) {
            appForm.querySelectorAll('input, select, textarea, button[type="submit"]').forEach(function (el) {
                el.disabled = true;
                el.style.opacity = '0.6';
            });
        }
    }

    } // end initPortalV10

    // 安全的 DOM ready 檢查：涵蓋所有載入時機
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPortalV10);
    } else {
        // DOM 已載入（interactive 或 complete），直接執行
        initPortalV10();
    }
})();
