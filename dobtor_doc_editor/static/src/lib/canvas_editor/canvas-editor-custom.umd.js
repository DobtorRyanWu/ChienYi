(function (global, factory) {
    typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
    typeof define === 'function' && define.amd ? define(['exports'], factory) :
    (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.DobtorCanvasEditor = {}));
})(this, (function (exports) { 'use strict';

    // DEFLATE is a complex format; to read this code, you should probably check the RFC first:
    // https://tools.ietf.org/html/rfc1951
    // You may also wish to take a look at the guide I made about this program:
    // https://gist.github.com/101arrowz/253f31eb5abc3d9275ab943003ffecad
    // Some of the following code is similar to that of UZIP.js:
    // https://github.com/photopea/UZIP.js
    // However, the vast majority of the codebase has diverged from UZIP.js to increase performance and reduce bundle size.
    // Sometimes 0 will appear where -1 would be more appropriate. This is because using a uint
    // is better for memory in most engines (I *think*).

    // aliases for shorter compressed code (most minifers don't do this)
    var u8 = Uint8Array, u16 = Uint16Array, i32 = Int32Array;
    // fixed length extra bits
    var fleb = new u8([0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0, /* unused */ 0, 0, /* impossible */ 0]);
    // fixed distance extra bits
    var fdeb = new u8([0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13, /* unused */ 0, 0]);
    // code length index map
    var clim = new u8([16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]);
    // get base, reverse index map from extra bits
    var freb = function (eb, start) {
        var b = new u16(31);
        for (var i = 0; i < 31; ++i) {
            b[i] = start += 1 << eb[i - 1];
        }
        // numbers here are at max 18 bits
        var r = new i32(b[30]);
        for (var i = 1; i < 30; ++i) {
            for (var j = b[i]; j < b[i + 1]; ++j) {
                r[j] = ((j - b[i]) << 5) | i;
            }
        }
        return { b: b, r: r };
    };
    var _a = freb(fleb, 2), fl = _a.b, revfl = _a.r;
    // we can ignore the fact that the other numbers are wrong; they never happen anyway
    fl[28] = 258, revfl[258] = 28;
    var _b = freb(fdeb, 0), fd = _b.b;
    // map of value to reverse (assuming 16 bits)
    var rev = new u16(32768);
    for (var i = 0; i < 32768; ++i) {
        // reverse table algorithm from SO
        var x = ((i & 0xAAAA) >> 1) | ((i & 0x5555) << 1);
        x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2);
        x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4);
        rev[i] = (((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)) >> 1;
    }
    // create huffman tree from u8 "map": index -> code length for code index
    // mb (max bits) must be at most 15
    // TODO: optimize/split up?
    var hMap = (function (cd, mb, r) {
        var s = cd.length;
        // index
        var i = 0;
        // u16 "map": index -> # of codes with bit length = index
        var l = new u16(mb);
        // length of cd must be 288 (total # of codes)
        for (; i < s; ++i) {
            if (cd[i])
                ++l[cd[i] - 1];
        }
        // u16 "map": index -> minimum code for bit length = index
        var le = new u16(mb);
        for (i = 1; i < mb; ++i) {
            le[i] = (le[i - 1] + l[i - 1]) << 1;
        }
        var co;
        if (r) {
            // u16 "map": index -> number of actual bits, symbol for code
            co = new u16(1 << mb);
            // bits to remove for reverser
            var rvb = 15 - mb;
            for (i = 0; i < s; ++i) {
                // ignore 0 lengths
                if (cd[i]) {
                    // num encoding both symbol and bits read
                    var sv = (i << 4) | cd[i];
                    // free bits
                    var r_1 = mb - cd[i];
                    // start value
                    var v = le[cd[i] - 1]++ << r_1;
                    // m is end value
                    for (var m = v | ((1 << r_1) - 1); v <= m; ++v) {
                        // every 16 bit value starting with the code yields the same result
                        co[rev[v] >> rvb] = sv;
                    }
                }
            }
        }
        else {
            co = new u16(s);
            for (i = 0; i < s; ++i) {
                if (cd[i]) {
                    co[i] = rev[le[cd[i] - 1]++] >> (15 - cd[i]);
                }
            }
        }
        return co;
    });
    // fixed length tree
    var flt = new u8(288);
    for (var i = 0; i < 144; ++i)
        flt[i] = 8;
    for (var i = 144; i < 256; ++i)
        flt[i] = 9;
    for (var i = 256; i < 280; ++i)
        flt[i] = 7;
    for (var i = 280; i < 288; ++i)
        flt[i] = 8;
    // fixed distance tree
    var fdt = new u8(32);
    for (var i = 0; i < 32; ++i)
        fdt[i] = 5;
    // fixed length map
    var flrm = /*#__PURE__*/ hMap(flt, 9, 1);
    // fixed distance map
    var fdrm = /*#__PURE__*/ hMap(fdt, 5, 1);
    // find max of array
    var max = function (a) {
        var m = a[0];
        for (var i = 1; i < a.length; ++i) {
            if (a[i] > m)
                m = a[i];
        }
        return m;
    };
    // read d, starting at bit p and mask with m
    var bits = function (d, p, m) {
        var o = (p / 8) | 0;
        return ((d[o] | (d[o + 1] << 8)) >> (p & 7)) & m;
    };
    // read d, starting at bit p continuing for at least 16 bits
    var bits16 = function (d, p) {
        var o = (p / 8) | 0;
        return ((d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)) >> (p & 7));
    };
    // get end of byte
    var shft = function (p) { return ((p + 7) / 8) | 0; };
    // typed array slice - allows garbage collector to free original reference,
    // while being more compatible than .slice
    var slc = function (v, s, e) {
        if (s == null || s < 0)
            s = 0;
        if (e == null || e > v.length)
            e = v.length;
        // can't use .constructor in case user-supplied
        return new u8(v.subarray(s, e));
    };
    // error codes
    var ec = [
        'unexpected EOF',
        'invalid block type',
        'invalid length/literal',
        'invalid distance',
        'stream finished',
        'no stream handler',
        ,
        'no callback',
        'invalid UTF-8 data',
        'extra field too long',
        'date not in range 1980-2099',
        'filename too long',
        'stream finishing',
        'invalid zip data'
        // determined by unknown compression method
    ];
    var err = function (ind, msg, nt) {
        var e = new Error(msg || ec[ind]);
        e.code = ind;
        if (Error.captureStackTrace)
            Error.captureStackTrace(e, err);
        if (!nt)
            throw e;
        return e;
    };
    // expands raw DEFLATE data
    var inflt = function (dat, st, buf, dict) {
        // source length       dict length
        var sl = dat.length, dl = dict ? dict.length : 0;
        if (!sl || st.f && !st.l)
            return buf || new u8(0);
        var noBuf = !buf;
        // have to estimate size
        var resize = noBuf || st.i != 2;
        // no state
        var noSt = st.i;
        // Assumes roughly 33% compression ratio average
        if (noBuf)
            buf = new u8(sl * 3);
        // ensure buffer can fit at least l elements
        var cbuf = function (l) {
            var bl = buf.length;
            // need to increase size to fit
            if (l > bl) {
                // Double or set to necessary, whichever is greater
                var nbuf = new u8(Math.max(bl * 2, l));
                nbuf.set(buf);
                buf = nbuf;
            }
        };
        //  last chunk         bitpos           bytes
        var final = st.f || 0, pos = st.p || 0, bt = st.b || 0, lm = st.l, dm = st.d, lbt = st.m, dbt = st.n;
        // total bits
        var tbts = sl * 8;
        do {
            if (!lm) {
                // BFINAL - this is only 1 when last chunk is next
                final = bits(dat, pos, 1);
                // type: 0 = no compression, 1 = fixed huffman, 2 = dynamic huffman
                var type = bits(dat, pos + 1, 3);
                pos += 3;
                if (!type) {
                    // go to end of byte boundary
                    var s = shft(pos) + 4, l = dat[s - 4] | (dat[s - 3] << 8), t = s + l;
                    if (t > sl) {
                        if (noSt)
                            err(0);
                        break;
                    }
                    // ensure size
                    if (resize)
                        cbuf(bt + l);
                    // Copy over uncompressed data
                    buf.set(dat.subarray(s, t), bt);
                    // Get new bitpos, update byte count
                    st.b = bt += l, st.p = pos = t * 8, st.f = final;
                    continue;
                }
                else if (type == 1)
                    lm = flrm, dm = fdrm, lbt = 9, dbt = 5;
                else if (type == 2) {
                    //  literal                            lengths
                    var hLit = bits(dat, pos, 31) + 257, hcLen = bits(dat, pos + 10, 15) + 4;
                    var tl = hLit + bits(dat, pos + 5, 31) + 1;
                    pos += 14;
                    // length+distance tree
                    var ldt = new u8(tl);
                    // code length tree
                    var clt = new u8(19);
                    for (var i = 0; i < hcLen; ++i) {
                        // use index map to get real code
                        clt[clim[i]] = bits(dat, pos + i * 3, 7);
                    }
                    pos += hcLen * 3;
                    // code lengths bits
                    var clb = max(clt), clbmsk = (1 << clb) - 1;
                    // code lengths map
                    var clm = hMap(clt, clb, 1);
                    for (var i = 0; i < tl;) {
                        var r = clm[bits(dat, pos, clbmsk)];
                        // bits read
                        pos += r & 15;
                        // symbol
                        var s = r >> 4;
                        // code length to copy
                        if (s < 16) {
                            ldt[i++] = s;
                        }
                        else {
                            //  copy   count
                            var c = 0, n = 0;
                            if (s == 16)
                                n = 3 + bits(dat, pos, 3), pos += 2, c = ldt[i - 1];
                            else if (s == 17)
                                n = 3 + bits(dat, pos, 7), pos += 3;
                            else if (s == 18)
                                n = 11 + bits(dat, pos, 127), pos += 7;
                            while (n--)
                                ldt[i++] = c;
                        }
                    }
                    //    length tree                 distance tree
                    var lt = ldt.subarray(0, hLit), dt = ldt.subarray(hLit);
                    // max length bits
                    lbt = max(lt);
                    // max dist bits
                    dbt = max(dt);
                    lm = hMap(lt, lbt, 1);
                    dm = hMap(dt, dbt, 1);
                }
                else
                    err(1);
                if (pos > tbts) {
                    if (noSt)
                        err(0);
                    break;
                }
            }
            // Make sure the buffer can hold this + the largest possible addition
            // Maximum chunk size (practically, theoretically infinite) is 2^17
            if (resize)
                cbuf(bt + 131072);
            var lms = (1 << lbt) - 1, dms = (1 << dbt) - 1;
            var lpos = pos;
            for (;; lpos = pos) {
                // bits read, code
                var c = lm[bits16(dat, pos) & lms], sym = c >> 4;
                pos += c & 15;
                if (pos > tbts) {
                    if (noSt)
                        err(0);
                    break;
                }
                if (!c)
                    err(2);
                if (sym < 256)
                    buf[bt++] = sym;
                else if (sym == 256) {
                    lpos = pos, lm = null;
                    break;
                }
                else {
                    var add = sym - 254;
                    // no extra bits needed if less
                    if (sym > 264) {
                        // index
                        var i = sym - 257, b = fleb[i];
                        add = bits(dat, pos, (1 << b) - 1) + fl[i];
                        pos += b;
                    }
                    // dist
                    var d = dm[bits16(dat, pos) & dms], dsym = d >> 4;
                    if (!d)
                        err(3);
                    pos += d & 15;
                    var dt = fd[dsym];
                    if (dsym > 3) {
                        var b = fdeb[dsym];
                        dt += bits16(dat, pos) & (1 << b) - 1, pos += b;
                    }
                    if (pos > tbts) {
                        if (noSt)
                            err(0);
                        break;
                    }
                    if (resize)
                        cbuf(bt + 131072);
                    var end = bt + add;
                    if (bt < dt) {
                        var shift = dl - dt, dend = Math.min(dt, end);
                        if (shift + bt < 0)
                            err(3);
                        for (; bt < dend; ++bt)
                            buf[bt] = dict[shift + bt];
                    }
                    for (; bt < end; ++bt)
                        buf[bt] = buf[bt - dt];
                }
            }
            st.l = lm, st.p = lpos, st.b = bt, st.f = final;
            if (lm)
                final = 1, st.m = lbt, st.d = dm, st.n = dbt;
        } while (!final);
        // don't reallocate for streams or user buffers
        return bt != buf.length && noBuf ? slc(buf, 0, bt) : buf.subarray(0, bt);
    };
    // empty
    var et = /*#__PURE__*/ new u8(0);
    // read 2 bytes
    var b2 = function (d, b) { return d[b] | (d[b + 1] << 8); };
    // read 4 bytes
    var b4 = function (d, b) { return (d[b] | (d[b + 1] << 8) | (d[b + 2] << 16) | (d[b + 3] << 24)) >>> 0; };
    var b8 = function (d, b) { return b4(d, b) + (b4(d, b + 4) * 4294967296); };
    /**
     * Expands DEFLATE data with no wrapper
     * @param data The data to decompress
     * @param opts The decompression options
     * @returns The decompressed version of the data
     */
    function inflateSync(data, opts) {
        return inflt(data, { i: 2 }, opts && opts.out, opts && opts.dictionary);
    }
    // text decoder
    var td = typeof TextDecoder != 'undefined' && /*#__PURE__*/ new TextDecoder();
    // text decoder stream
    var tds = 0;
    try {
        td.decode(et, { stream: true });
        tds = 1;
    }
    catch (e) { }
    // decode UTF8
    var dutf8 = function (d) {
        for (var r = '', i = 0;;) {
            var c = d[i++];
            var eb = (c > 127) + (c > 223) + (c > 239);
            if (i + eb > d.length)
                return { s: r, r: slc(d, i - 1) };
            if (!eb)
                r += String.fromCharCode(c);
            else if (eb == 3) {
                c = ((c & 15) << 18 | (d[i++] & 63) << 12 | (d[i++] & 63) << 6 | (d[i++] & 63)) - 65536,
                    r += String.fromCharCode(55296 | (c >> 10), 56320 | (c & 1023));
            }
            else if (eb & 1)
                r += String.fromCharCode((c & 31) << 6 | (d[i++] & 63));
            else
                r += String.fromCharCode((c & 15) << 12 | (d[i++] & 63) << 6 | (d[i++] & 63));
        }
    };
    /**
     * Converts a Uint8Array to a string
     * @param dat The data to decode to string
     * @param latin1 Whether or not to interpret the data as Latin-1. This should
     *               not need to be true unless encoding to binary string.
     * @returns The original UTF-8/Latin-1 string
     */
    function strFromU8(dat, latin1) {
        if (latin1) {
            var r = '';
            for (var i = 0; i < dat.length; i += 16384)
                r += String.fromCharCode.apply(null, dat.subarray(i, i + 16384));
            return r;
        }
        else if (td) {
            return td.decode(dat);
        }
        else {
            var _a = dutf8(dat), s = _a.s, r = _a.r;
            if (r.length)
                err(8);
            return s;
        }
    }
    // skip local zip header
    var slzh = function (d, b) { return b + 30 + b2(d, b + 26) + b2(d, b + 28); };
    // read zip header
    var zh = function (d, b, z) {
        var fnl = b2(d, b + 28), fn = strFromU8(d.subarray(b + 46, b + 46 + fnl), !(b2(d, b + 8) & 2048)), es = b + 46 + fnl, bs = b4(d, b + 20);
        var _a = z && bs == 4294967295 ? z64e(d, es) : [bs, b4(d, b + 24), b4(d, b + 42)], sc = _a[0], su = _a[1], off = _a[2];
        return [b2(d, b + 10), sc, su, fn, es + b2(d, b + 30) + b2(d, b + 32), off];
    };
    // read zip64 extra field
    var z64e = function (d, b) {
        for (; b2(d, b) != 1; b += 4 + b2(d, b + 2))
            ;
        return [b8(d, b + 12), b8(d, b + 4), b8(d, b + 20)];
    };
    /**
     * Synchronously decompresses a ZIP archive. Prefer using `unzip` for better
     * performance with more than one file.
     * @param data The raw compressed ZIP file
     * @param opts The ZIP extraction options
     * @returns The decompressed files
     */
    function unzipSync(data, opts) {
        var files = {};
        var e = data.length - 22;
        for (; b4(data, e) != 0x6054B50; --e) {
            if (!e || data.length - e > 65558)
                err(13);
        }
        var c = b2(data, e + 8);
        if (!c)
            return {};
        var o = b4(data, e + 16);
        var z = o == 4294967295 || c == 65535;
        if (z) {
            var ze = b4(data, e - 12);
            z = b4(data, ze) == 0x6064B50;
            if (z) {
                c = b4(data, ze + 32);
                o = b4(data, ze + 48);
            }
        }
        for (var i = 0; i < c; ++i) {
            var _a = zh(data, o, z), c_2 = _a[0], sc = _a[1], su = _a[2], fn = _a[3], no = _a[4], off = _a[5], b = slzh(data, off);
            o = no;
            {
                if (!c_2)
                    files[fn] = slc(data, b, b + sc);
                else if (c_2 == 8)
                    files[fn] = inflateSync(data.subarray(b, b + sc), { out: new u8(su) });
                else
                    err(14, 'unknown compression type ' + c_2);
            }
        }
        return files;
    }

    /**
     * PackageReader — OOXML ZIP 容器解包
     *
     * 職責：
     *   1. 解開 .docx (ZIP) 取出每份 part（XML / 圖片 / 等）
     *   2. 解析 [Content_Types].xml：建立 path → MIME type 對照
     *      - <Default Extension="xml" ContentType="..."> 預設規則
     *      - <Override PartName="/word/document.xml" ContentType="..."> 覆蓋規則
     *   3. 解析 _rels/.rels 與 <part>/_rels/<part>.rels：建立 rId → target 對照
     *
     * 重要設計：
     *   - 所有 part 路徑統一去除前導 "/"（OOXML 慣例）
     *   - relationship target 解析為「相對於 .rels 所屬 part 的目錄」的絕對路徑
     *   - 不在此處解任何 OOXML 內容語意（document.xml / styles.xml 留給上層 Parser）
     *
     * Sprint 1 實作完成；後續若 ZIP 體積大可改 unzipAsync。
     */
    // 註：[Content_Types].xml 與 .rels 都用「預設命名空間 + 無 prefix」結構，
    // 用 getElementsByTagName(localName) 在瀏覽器與 happy-dom 都能正確匹配；
    // 而 getElementsByTagNameNS 在 happy-dom 對預設命名空間實作有缺陷（回傳 0）。
    class PackageReader {
        /**
         * 解析 .docx ArrayBuffer 為結構化 OoxmlPackage。
         * @throws Error 如果 ZIP 損壞、缺 [Content_Types].xml、或 XML 解析失敗
         */
        parse(buffer) {
            const bytes = new Uint8Array(buffer);
            const entries = unzipSync(bytes);
            const parts = new Map();
            const relationships = new Map();
            // Step 1: [Content_Types].xml 必須存在
            const ctRaw = entries['[Content_Types].xml'];
            if (!ctRaw) {
                throw new Error('PackageReader: [Content_Types].xml not found — not a valid OOXML package');
            }
            const contentTypes = parseContentTypes(strFromU8(ctRaw));
            // Step 2: 走訪所有 entry，分類為 part 或 relationship
            for (const [rawPath, data] of Object.entries(entries)) {
                // 跳過 ZIP 目錄項目（fflate 通常已過濾，但保險）
                if (rawPath.endsWith('/'))
                    continue;
                // 標準化路徑：去除前導 "/"
                const path = rawPath.replace(/^\/+/, '');
                // 跳過 [Content_Types].xml 本身（不是 part）
                if (path === '[Content_Types].xml')
                    continue;
                // .rels 檔：解析後存入 relationships map，不放進 parts
                if (path.endsWith('.rels')) {
                    const ownerPart = relsOwnerPath(path);
                    const xml = strFromU8(data);
                    const rels = parseRelationships(xml, ownerPart);
                    relationships.set(ownerPart, rels);
                    continue;
                }
                // 其他檔案 → part；查 contentType
                const contentType = resolveContentType(path, contentTypes);
                parts.set(path, { path, contentType, data });
            }
            return makePackage(parts, relationships);
        }
    }
    function parseContentTypes(xml) {
        const doc = parseXml(xml);
        const defaults = new Map();
        const overrides = new Map();
        const defaultEls = doc.getElementsByTagName('Default');
        for (let i = 0; i < defaultEls.length; i++) {
            const el = defaultEls[i];
            const ext = el.getAttribute('Extension')?.toLowerCase();
            const ct = el.getAttribute('ContentType');
            if (ext && ct)
                defaults.set(ext, ct);
        }
        const overrideEls = doc.getElementsByTagName('Override');
        for (let i = 0; i < overrideEls.length; i++) {
            const el = overrideEls[i];
            const partName = el.getAttribute('PartName')?.replace(/^\/+/, '');
            const ct = el.getAttribute('ContentType');
            if (partName && ct)
                overrides.set(partName, ct);
        }
        return { defaults, overrides };
    }
    function resolveContentType(path, ct) {
        // Override 優先於 Default
        const override = ct.overrides.get(path);
        if (override)
            return override;
        const dotIdx = path.lastIndexOf('.');
        if (dotIdx === -1)
            return 'application/octet-stream';
        const ext = path.substring(dotIdx + 1).toLowerCase();
        return ct.defaults.get(ext) ?? 'application/octet-stream';
    }
    /**
     * 從 .rels 路徑反推它所屬 part 的路徑。
     *   "_rels/.rels"                    → ""                  (root)
     *   "word/_rels/document.xml.rels"   → "word/document.xml"
     *   "word/_rels/header1.xml.rels"    → "word/header1.xml"
     */
    function relsOwnerPath(relsPath) {
        // root rels：_rels/.rels
        if (relsPath === '_rels/.rels')
            return '';
        // 拆 dir/_rels/file.ext.rels → dir/file.ext
        const match = relsPath.match(/^(.*?)_rels\/(.+)\.rels$/);
        if (!match) {
            // 不符合預期格式，回傳本身去 .rels 後綴（fallback）
            return relsPath.replace(/\.rels$/, '');
        }
        const dir = match[1]; // 含結尾 "/" 或 ""
        const file = match[2];
        return `${dir}${file}`;
    }
    function parseRelationships(xml, ownerPart) {
        const doc = parseXml(xml);
        const out = new Map();
        const rels = doc.getElementsByTagName('Relationship');
        for (let i = 0; i < rels.length; i++) {
            const el = rels[i];
            const id = el.getAttribute('Id');
            const type = el.getAttribute('Type');
            const targetRaw = el.getAttribute('Target');
            const targetModeRaw = el.getAttribute('TargetMode');
            if (!id || !type || !targetRaw)
                continue;
            const targetMode = targetModeRaw === 'External' ? 'External' : 'Internal';
            const target = targetMode === 'External' ? targetRaw : resolveTarget(ownerPart, targetRaw);
            out.set(id, { id, type, target, targetMode });
        }
        return out;
    }
    /**
     * 把 relationship target（相對路徑）解析為絕對 part path。
     * ownerPart 為空字串（root rels）時，target 本來就是相對於套件根。
     *
     * 範例：
     *   ownerPart = "word/document.xml", target = "header1.xml"
     *     → "word/header1.xml"
     *   ownerPart = "word/document.xml", target = "media/image1.png"
     *     → "word/media/image1.png"
     *   ownerPart = "word/document.xml", target = "../customXml/item1.xml"
     *     → "customXml/item1.xml"
     *   ownerPart = "", target = "word/document.xml"
     *     → "word/document.xml"
     */
    function resolveTarget(ownerPart, target) {
        // target 開頭為 "/" 表示絕對路徑
        if (target.startsWith('/'))
            return target.replace(/^\/+/, '');
        // 取 ownerPart 的目錄（不含檔名）
        const lastSlash = ownerPart.lastIndexOf('/');
        const baseDir = lastSlash === -1 ? '' : ownerPart.substring(0, lastSlash + 1);
        // 拼接後正規化：處理 ".." 與 "."
        const combined = baseDir + target;
        return normalizePath(combined);
    }
    function normalizePath(path) {
        const parts = path.split('/');
        const stack = [];
        for (const part of parts) {
            if (part === '' || part === '.')
                continue;
            if (part === '..') {
                stack.pop();
                continue;
            }
            stack.push(part);
        }
        return stack.join('/');
    }
    /**
     * 統一 XML 解析入口。優先用 DOMParser（瀏覽器與 happy-dom/jsdom 環境）。
     * 若解析失敗（含 <parsererror>），丟錯。
     */
    function parseXml(xml) {
        if (typeof DOMParser === 'undefined') {
            throw new Error('PackageReader: DOMParser not available — Node tests must use happy-dom environment');
        }
        const doc = new DOMParser().parseFromString(xml, 'application/xml');
        // DOMParser 不會 throw；錯誤會放在 <parsererror>
        const errors = doc.getElementsByTagName('parsererror');
        if (errors.length > 0) {
            throw new Error(`PackageReader: XML parse error — ${errors[0].textContent}`);
        }
        return doc;
    }
    function makePackage(parts, relationships) {
        return {
            parts,
            relationships,
            getPart(path) {
                return parts.get(path.replace(/^\/+/, ''));
            },
            getRelationships(partPath) {
                return relationships.get(partPath.replace(/^\/+/, '')) ?? new Map();
            },
            partAsText(path) {
                const p = parts.get(path.replace(/^\/+/, ''));
                if (!p)
                    return undefined;
                return strFromU8(p.data);
            },
            resolveRelationship(partPath, rId) {
                const rels = relationships.get(partPath.replace(/^\/+/, ''));
                return rels?.get(rId)?.target;
            },
        };
    }

    /**
     * OoxmlParser — 對外總入口
     *
     * 把 ArrayBuffer (.docx) 一路解析成 DocumentNode。
     *
     * 內部組裝順序（Phase 1）：
     *   1. PackageReader 解 ZIP → parts + relationships + media
     *   2. StyleResolver 展開 styles.xml → StyleMap
     *   3. NumberingResolver 展開 numbering.xml → NumberingMap
     *   4. DocumentParser 走訪 document.xml body
     *      ├─ ParagraphParser
     *      ├─ TableParser → GridResolver
     *      ├─ SectionParser
     *      └─ DrawingParser
     *   5. HeaderFooterParser 處理 headerN/footerN.xml
     *   6. 組裝 DocumentNode
     *
     * Phase 1 Sprint 1 起逐步實作；目前為 stub。
     */
    class OoxmlParser {
        constructor() {
            this.packageReader = new PackageReader();
        }
        parse(_buffer, _options = {}) {
            throw new Error('OoxmlParser.parse() not implemented — Sprint 1');
        }
    }
    // 旁路：方便外部探測 stub 是否已連通
    const __DOBTOR_OOXML_STUB__ = 'phase-0';

    /**
     * DocumentParser — word/document.xml 主解析器
     *
     * 職責：
     *   - 走訪 <w:body> 子節點，分派到 ParagraphParser / TableParser / SectionParser
     *   - 串接 StyleResolver / NumberingResolver 把樣式繼承鏈展開到每個 Run/Paragraph
     *   - 輸出 DocumentNode（見 ast/types.ts）
     *
     * Phase 1 Sprint 1-2 實作；目前為 stub。
     */
    class DocumentParser {
        // TODO Sprint 1-2
        parse(_xml) {
            throw new Error('DocumentParser.parse() not implemented — Sprint 1-2');
        }
    }

    /**
     * units — OOXML 度量單位轉換工具
     *
     * OOXML 慣用單位：
     *   - twip (1/20 pt) — w:sz、w:tblW (w:dxa)
     *   - half-point (1/2 pt) — w:sz of w:rPr font size
     *   - eighth-point (1/8 pt) — w:sz of border width
     *   - EMU (English Metric Unit, 1/914400 inch) — DrawingML wp:extent
     *
     * 全模組一律以 pt 為標準（見 ast/types.ts: Pt）。
     */
    const TWIP_PER_PT = 20;
    const HALF_POINT_PER_PT = 2;
    const EIGHTH_POINT_PER_PT = 8;
    const EMU_PER_INCH = 914400;
    const PT_PER_INCH = 72;
    const EMU_PER_PT = EMU_PER_INCH / PT_PER_INCH; // 12700
    function twipToPt(twip) {
        return twip / TWIP_PER_PT;
    }
    function halfPointToPt(hp) {
        return hp / HALF_POINT_PER_PT;
    }
    function eighthPointToPt(ep) {
        return ep / EIGHTH_POINT_PER_PT;
    }
    function emuToPt(emu) {
        return emu / EMU_PER_PT;
    }
    function ptToPx(pt, dpi = 96) {
        return (pt / PT_PER_INCH) * dpi;
    }

    /**
     * ParagraphParser — 解析 <w:p>（段落）與內部 <w:r>（Run）
     *
     * 處理範圍（Sprint 1）：
     *   - w:pPr 段落屬性：jc, ind, spacing, pStyle, numPr, keepNext, pageBreakBefore
     *   - w:rPr Run 屬性：rFonts, sz, b, i, u, strike, color, highlight, vertAlign
     *   - w:t 文字（含 xml:space="preserve" 保留空白）
     *   - w:br type="line|page|column" → BreakNode
     *   - w:tab → 暫時當文字 "\t"
     *   - w:fldSimple instr="..." → FieldNode
     *
     * 設計原則：
     *   - 用 getElementsByTagName(qualifiedName) 而非 getElementsByTagNameNS
     *     （happy-dom 對預設命名空間 NS 查詢有缺陷；此 walker 全環境一致）
     *   - 只處理「直接子節點」，不遞迴尋找（OOXML 結構非 free-form HTML）
     *   - 樣式繼承鏈交給 StyleResolver 在 Sprint 2 處理；本 Parser 只解 in-line 屬性
     *
     * Sprint 1 issue #4 + #5 + #6
     */
    // ── 對外 ──────────────────────────────────────────────────────────────────────
    class ParagraphParser {
        /**
         * 解析單一 <w:p> Element 為 ParagraphNode。
         * @param p w:p 元素（已是 DOM Element）
         */
        parse(p) {
            const pPrEl = directChild(p, 'w:pPr');
            const props = pPrEl ? parseParagraphProps(pPrEl) : {};
            const styleId = pPrEl
                ? attr(directChild(pPrEl, 'w:pStyle'), 'w:val')
                : undefined;
            const runs = [];
            for (const child of directChildren(p)) {
                switch (child.tagName) {
                    case 'w:r':
                        for (const node of parseRun(child))
                            runs.push(node);
                        break;
                    case 'w:fldSimple':
                        runs.push(parseFldSimple(child));
                        break;
                    case 'w:hyperlink':
                        // hyperlink 內含 w:r，視同包裹 — 直接展平 runs
                        for (const r of directChildren(child)) {
                            if (r.tagName === 'w:r') {
                                for (const node of parseRun(r))
                                    runs.push(node);
                            }
                        }
                        break;
                    // w:pPr 已先處理；其他子節點 (w:bookmarkStart, w:proofErr) 暫時忽略
                }
            }
            const node = {
                type: 'paragraph',
                props,
                runs,
            };
            if (styleId)
                node.styleId = styleId;
            return node;
        }
    }
    // ── w:pPr ─────────────────────────────────────────────────────────────────────
    function parseParagraphProps(pPr) {
        const props = {};
        const jc = attr(directChild(pPr, 'w:jc'), 'w:val');
        if (jc) {
            const a = mapAlignment(jc);
            if (a)
                props.alignment = a;
        }
        const indEl = directChild(pPr, 'w:ind');
        if (indEl) {
            const indent = {};
            const left = attrTwip(indEl, 'w:left') ?? attrTwip(indEl, 'w:start');
            const right = attrTwip(indEl, 'w:right') ?? attrTwip(indEl, 'w:end');
            const firstLine = attrTwip(indEl, 'w:firstLine');
            const hanging = attrTwip(indEl, 'w:hanging');
            if (left !== undefined)
                indent.left = left;
            if (right !== undefined)
                indent.right = right;
            if (firstLine !== undefined)
                indent.firstLine = firstLine;
            if (hanging !== undefined)
                indent.hanging = hanging;
            if (Object.keys(indent).length > 0)
                props.indent = indent;
        }
        const spEl = directChild(pPr, 'w:spacing');
        if (spEl) {
            const spacing = {};
            const before = attrTwip(spEl, 'w:before');
            const after = attrTwip(spEl, 'w:after');
            if (before !== undefined)
                spacing.before = before;
            if (after !== undefined)
                spacing.after = after;
            const lineRaw = spEl.getAttribute('w:line');
            const ruleRaw = spEl.getAttribute('w:lineRule');
            if (lineRaw) {
                const line = parseInt(lineRaw, 10);
                if (Number.isFinite(line)) {
                    const rule = mapLineSpacingRule(ruleRaw);
                    // auto 規則用 240 分母（Word 慣例）；其餘 rule 與 exact/atLeast 用 twip
                    const value = rule === 'auto' ? line / 240 : twipToPt(line);
                    spacing.line = { rule, value };
                }
            }
            if (Object.keys(spacing).length > 0)
                props.spacing = spacing;
        }
        const numPrEl = directChild(pPr, 'w:numPr');
        if (numPrEl) {
            const ilvlVal = attr(directChild(numPrEl, 'w:ilvl'), 'w:val');
            const numIdVal = attr(directChild(numPrEl, 'w:numId'), 'w:val');
            if (ilvlVal !== undefined) {
                const n = parseInt(ilvlVal, 10);
                if (Number.isFinite(n))
                    props.ilvl = n;
            }
            if (numIdVal !== undefined) {
                const n = parseInt(numIdVal, 10);
                if (Number.isFinite(n))
                    props.numId = n;
            }
        }
        if (boolFlag(directChild(pPr, 'w:keepNext')))
            props.keepNext = true;
        if (boolFlag(directChild(pPr, 'w:keepLines')))
            props.keepLines = true;
        if (boolFlag(directChild(pPr, 'w:pageBreakBefore')))
            props.pageBreakBefore = true;
        return props;
    }
    // ── w:r → RunNode[]（單一 run 可能因 w:br 等切多筆） ─────────────────────────
    function parseRun(r) {
        const rPrEl = directChild(r, 'w:rPr');
        const baseProps = rPrEl ? parseRunProps(rPrEl) : {};
        const out = [];
        let textBuf = '';
        const flushText = () => {
            if (textBuf.length === 0)
                return;
            out.push({ type: 'run', text: textBuf, props: { ...baseProps } });
            textBuf = '';
        };
        for (const child of directChildren(r)) {
            switch (child.tagName) {
                case 'w:t': {
                    // xml:space="preserve" → 保留前後空白
                    // 注意：DOM 對缺省屬性取出可能是 null，不影響 textContent 讀取
                    textBuf += child.textContent ?? '';
                    break;
                }
                case 'w:br': {
                    flushText();
                    const t = child.getAttribute('w:type');
                    const breakType = t === 'page' ? 'page' : t === 'column' ? 'column' : 'line';
                    out.push({ type: 'break', breakType });
                    break;
                }
                case 'w:tab':
                    textBuf += '\t';
                    break;
                case 'w:noBreakHyphen':
                    textBuf += '‑'; // non-breaking hyphen
                    break;
                case 'w:softHyphen':
                    textBuf += '­'; // soft hyphen
                    break;
                case 'w:cr':
                    textBuf += '\n';
                    break;
                // w:rPr 已先處理；w:drawing / w:pict / w:fldChar 暫不處理（Sprint 3 Drawing）
            }
        }
        flushText();
        return out;
    }
    // ── w:rPr ─────────────────────────────────────────────────────────────────────
    function parseRunProps(rPr) {
        const props = {};
        const fontsEl = directChild(rPr, 'w:rFonts');
        if (fontsEl) {
            const ascii = fontsEl.getAttribute('w:ascii');
            const east = fontsEl.getAttribute('w:eastAsia');
            if (ascii)
                props.fontFamily = ascii;
            if (east)
                props.fontFamilyEastAsia = east;
        }
        // w:sz 與 w:szCs 都是 half-point；CS 給 complex script。先用 w:sz。
        const szVal = attr(directChild(rPr, 'w:sz'), 'w:val');
        if (szVal !== undefined) {
            const n = parseInt(szVal, 10);
            if (Number.isFinite(n))
                props.fontSize = halfPointToPt(n);
        }
        if (boolFlag(directChild(rPr, 'w:b')))
            props.bold = true;
        if (boolFlag(directChild(rPr, 'w:i')))
            props.italic = true;
        if (boolFlag(directChild(rPr, 'w:strike')))
            props.strike = true;
        if (boolFlag(directChild(rPr, 'w:dstrike')))
            props.dstrike = true;
        const uVal = attr(directChild(rPr, 'w:u'), 'w:val');
        if (uVal)
            props.underline = uVal;
        const colorVal = attr(directChild(rPr, 'w:color'), 'w:val');
        if (colorVal)
            props.color = colorVal;
        // w:highlight 用具名色（yellow/cyan/...）；w:shd val + w:fill 才是 hex shading
        const highlight = attr(directChild(rPr, 'w:highlight'), 'w:val');
        if (highlight)
            props.highlight = highlight;
        const vert = attr(directChild(rPr, 'w:vertAlign'), 'w:val');
        if (vert === 'superscript' || vert === 'subscript' || vert === 'baseline') {
            props.vertAlign = vert;
        }
        const spacing = attr(directChild(rPr, 'w:spacing'), 'w:val');
        if (spacing !== undefined) {
            const n = parseInt(spacing, 10);
            if (Number.isFinite(n))
                props.spacing = twipToPt(n);
        }
        const lang = attr(directChild(rPr, 'w:lang'), 'w:val');
        if (lang)
            props.lang = lang;
        return props;
    }
    // ── w:fldSimple → FieldNode ──────────────────────────────────────────────────
    function parseFldSimple(el) {
        const instruction = (el.getAttribute('w:instr') ?? '').trim();
        // 第一個非空字 token 視為 fieldType，並轉大寫
        const firstToken = instruction.split(/\s+/)[0]?.toUpperCase() ?? '';
        const knownTypes = ['PAGE', 'NUMPAGES', 'DATE', 'TIME', 'AUTHOR', 'FILENAME'];
        const fieldType = knownTypes.includes(firstToken)
            ? firstToken
            : 'unknown';
        // 快取值：fldSimple 內部的 w:r → w:t 串接
        let cached = '';
        for (const r of directChildren(el)) {
            if (r.tagName !== 'w:r')
                continue;
            for (const t of directChildren(r)) {
                if (t.tagName === 'w:t')
                    cached += t.textContent ?? '';
            }
        }
        const node = { type: 'field', instruction, fieldType };
        if (cached)
            node.cachedValue = cached;
        return node;
    }
    // ── 共用工具 ──────────────────────────────────────────────────────────────────
    function directChildren(el) {
        const out = [];
        const children = el.childNodes;
        for (let i = 0; i < children.length; i++) {
            const n = children[i];
            if (n.nodeType === 1)
                out.push(n);
        }
        return out;
    }
    function directChild(el, tagName) {
        if (!el)
            return undefined;
        for (const child of directChildren(el)) {
            if (child.tagName === tagName)
                return child;
        }
        return undefined;
    }
    function attr(el, name) {
        if (!el)
            return undefined;
        const v = el.getAttribute(name);
        return v === null ? undefined : v;
    }
    function attrTwip(el, name) {
        const v = attr(el, name);
        if (v === undefined)
            return undefined;
        const n = parseInt(v, 10);
        return Number.isFinite(n) ? twipToPt(n) : undefined;
    }
    /**
     * OOXML 布林屬性慣例：
     *   - 元素存在且無 w:val 屬性 → true
     *   - w:val="0" / "false" → false
     *   - w:val="1" / "true"  → true
     */
    function boolFlag(el) {
        if (!el)
            return false;
        const v = el.getAttribute('w:val');
        if (v === null)
            return true;
        return v !== '0' && v.toLowerCase() !== 'false';
    }
    function mapAlignment(jc) {
        switch (jc) {
            case 'left':
            case 'start':
                return 'left';
            case 'right':
            case 'end':
                return 'right';
            case 'center':
                return 'center';
            case 'both':
            case 'justify':
                return 'justify';
            case 'distribute':
                return 'distribute';
            default:
                return undefined;
        }
    }
    function mapLineSpacingRule(rule) {
        if (rule === 'exact')
            return 'exact';
        if (rule === 'atLeast')
            return 'atLeast';
        return 'auto';
    }

    /**
     * TableParser — 解析 <w:tbl>
     *
     * 職責：
     *   - 走訪 <w:tblGrid> 取得 grid column 寬度
     *   - 走訪 <w:tr> → <w:tc>，取得 cellRaw（含 gridSpan/vMerge 資訊）
     *   - 委派 GridResolver 計算每個 Cell 的 (gridCol, gridSpan, rowSpan, isContinuation)
     *
     * Phase 1 Sprint 3 實作；目前為 stub。
     */
    class TableParser {
        // TODO Sprint 3
        parse(_tableElement) {
            throw new Error('TableParser.parse() not implemented — Sprint 3');
        }
    }

    /**
     * GridResolver — vMerge 兩-pass 演算法
     *
     * 演算法（Sprint 3）：
     *   Pass 1：掃所有 row × cell，累計 gridCol（依 gridSpan 跨欄推進），
     *           標記每個 vMerge="restart" 為主格、vMerge="continue" 為延續格。
     *   Pass 2：自下而上回掃，對每個 vMerge 鏈計算主格的 rowSpan。
     *
     * 邊界情況（不可省略）：
     *   - 同一 column 跨多列 vMerge → 第一頁底邊框 omit、第二頁頂邊框 omit
     *   - 不可用陣列索引推 column，必須累加 gridSpan
     *   - 列高混合 atLeast/exact/auto 時，rowSpan 計算不變、僅 Renderer 負責拉伸
     *
     * 目前為 stub，Sprint 3 實作。
     */
    class GridResolver {
        // TODO Sprint 3
        resolve(_rows) {
            throw new Error('GridResolver.resolve() not implemented — Sprint 3');
        }
    }

    /**
     * StyleResolver — word/styles.xml 樣式繼承鏈展開
     *
     * 解析三層繼承鏈：docDefaults → pStyle (basedOn 鏈) → 直接屬性
     * Resolver 完成後輸出已展開的 StyleMap，供 ParagraphParser 直接合併。
     *
     * Phase 1 Sprint 2 實作；目前為 stub。
     */
    class StyleResolver {
        // TODO Sprint 2
        resolve(_xml) {
            throw new Error('StyleResolver.resolve() not implemented — Sprint 2');
        }
    }

    /**
     * NumberingResolver — word/numbering.xml 多層次清單編號
     *
     * 解析 numId → abstractNumId → levels[ilvl] 鏈，含：
     *   - lvlText 範本展開（"%1.%2." → "1.1." 等）
     *   - lvlRestart 重啟邏輯
     *   - isLgl 強制十進位
     *
     * Phase 1 Sprint 2 實作；目前為 stub。
     */
    class NumberingResolver {
        // TODO Sprint 2
        resolve(_xml) {
            throw new Error('NumberingResolver.resolve() not implemented — Sprint 2');
        }
    }

    /**
     * SectionParser — 解析 <w:sectPr>
     *
     * 職責：
     *   - 取得頁面尺寸 / margins / orientation
     *   - 取得欄位設定（cols count / space / equalWidth）
     *   - 取得 header/footer 引用 rId（default / first / even）
     *   - 取得 titlePg / evenAndOddHeaders 旗標
     *
     * Phase 1 Sprint 2 實作；目前為 stub。
     */
    class SectionParser {
        // TODO Sprint 2
        parse(_sectPrElement) {
            throw new Error('SectionParser.parse() not implemented — Sprint 2');
        }
    }

    /**
     * HeaderFooterParser — 解析 word/headerN.xml 與 word/footerN.xml
     *
     * 結構與 document.xml 的 body 相同（BlockNode[]），可重用 DocumentParser 的 body 走訪邏輯。
     *
     * Phase 1 Sprint 2 實作；目前為 stub。
     */
    class HeaderFooterParser {
        // TODO Sprint 2
        parse(_xml, _rId) {
            throw new Error('HeaderFooterParser.parse() not implemented — Sprint 2');
        }
    }

    /**
     * DrawingParser — 解析 <w:drawing> 內嵌與浮動圖片
     *
     * 處理 wp:inline → InlineImageNode、wp:anchor → FloatImageNode。
     * 圖片本身透過 rId 從 PackageReader 取出 blob，由 Renderer 載入。
     *
     * Phase 1 Sprint 3 實作；目前為 stub。
     * Phase 5 SmartArt / Charts 視為 fallback 圖片，仍經此 Parser。
     */
    class DrawingParser {
        // TODO Sprint 3
        parse(_drawingElement) {
            throw new Error('DrawingParser.parse() not implemented — Sprint 3');
        }
    }

    var index = /*#__PURE__*/Object.freeze({
        __proto__: null,
        EIGHTH_POINT_PER_PT: EIGHTH_POINT_PER_PT,
        EMU_PER_INCH: EMU_PER_INCH,
        EMU_PER_PT: EMU_PER_PT,
        HALF_POINT_PER_PT: HALF_POINT_PER_PT,
        PT_PER_INCH: PT_PER_INCH,
        TWIP_PER_PT: TWIP_PER_PT,
        eighthPointToPt: eighthPointToPt,
        emuToPt: emuToPt,
        halfPointToPt: halfPointToPt,
        ptToPx: ptToPx,
        twipToPt: twipToPt
    });

    exports.DocumentParser = DocumentParser;
    exports.DrawingParser = DrawingParser;
    exports.GridResolver = GridResolver;
    exports.HeaderFooterParser = HeaderFooterParser;
    exports.NumberingResolver = NumberingResolver;
    exports.OoxmlParser = OoxmlParser;
    exports.PackageReader = PackageReader;
    exports.ParagraphParser = ParagraphParser;
    exports.SectionParser = SectionParser;
    exports.StyleResolver = StyleResolver;
    exports.TableParser = TableParser;
    exports.Units = index;
    exports.__DOBTOR_OOXML_STUB__ = __DOBTOR_OOXML_STUB__;

}));
//# sourceMappingURL=canvas-editor-custom.umd.js.map
