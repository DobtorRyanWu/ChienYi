(function (global, factory) {
    typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
    typeof define === 'function' && define.amd ? define(['exports'], factory) :
    (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.DobtorSpreadsheetEditor = {}));
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
    var _b = freb(fdeb, 0), fd = _b.b, revfd = _b.r;
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
    var flm = /*#__PURE__*/ hMap(flt, 9, 0), flrm = /*#__PURE__*/ hMap(flt, 9, 1);
    // fixed distance map
    var fdm = /*#__PURE__*/ hMap(fdt, 5, 0), fdrm = /*#__PURE__*/ hMap(fdt, 5, 1);
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
    // starting at p, write the minimum number of bits that can hold v to d
    var wbits = function (d, p, v) {
        v <<= p & 7;
        var o = (p / 8) | 0;
        d[o] |= v;
        d[o + 1] |= v >> 8;
    };
    // starting at p, write the minimum number of bits (>8) that can hold v to d
    var wbits16 = function (d, p, v) {
        v <<= p & 7;
        var o = (p / 8) | 0;
        d[o] |= v;
        d[o + 1] |= v >> 8;
        d[o + 2] |= v >> 16;
    };
    // creates code lengths from a frequency table
    var hTree = function (d, mb) {
        // Need extra info to make a tree
        var t = [];
        for (var i = 0; i < d.length; ++i) {
            if (d[i])
                t.push({ s: i, f: d[i] });
        }
        var s = t.length;
        var t2 = t.slice();
        if (!s)
            return { t: et, l: 0 };
        if (s == 1) {
            var v = new u8(t[0].s + 1);
            v[t[0].s] = 1;
            return { t: v, l: 1 };
        }
        t.sort(function (a, b) { return a.f - b.f; });
        // after i2 reaches last ind, will be stopped
        // freq must be greater than largest possible number of symbols
        t.push({ s: -1, f: 25001 });
        var l = t[0], r = t[1], i0 = 0, i1 = 1, i2 = 2;
        t[0] = { s: -1, f: l.f + r.f, l: l, r: r };
        // efficient algorithm from UZIP.js
        // i0 is lookbehind, i2 is lookahead - after processing two low-freq
        // symbols that combined have high freq, will start processing i2 (high-freq,
        // non-composite) symbols instead
        // see https://reddit.com/r/photopea/comments/ikekht/uzipjs_questions/
        while (i1 != s - 1) {
            l = t[t[i0].f < t[i2].f ? i0++ : i2++];
            r = t[i0 != i1 && t[i0].f < t[i2].f ? i0++ : i2++];
            t[i1++] = { s: -1, f: l.f + r.f, l: l, r: r };
        }
        var maxSym = t2[0].s;
        for (var i = 1; i < s; ++i) {
            if (t2[i].s > maxSym)
                maxSym = t2[i].s;
        }
        // code lengths
        var tr = new u16(maxSym + 1);
        // max bits in tree
        var mbt = ln(t[i1 - 1], tr, 0);
        if (mbt > mb) {
            // more algorithms from UZIP.js
            // TODO: find out how this code works (debt)
            //  ind    debt
            var i = 0, dt = 0;
            //    left            cost
            var lft = mbt - mb, cst = 1 << lft;
            t2.sort(function (a, b) { return tr[b.s] - tr[a.s] || a.f - b.f; });
            for (; i < s; ++i) {
                var i2_1 = t2[i].s;
                if (tr[i2_1] > mb) {
                    dt += cst - (1 << (mbt - tr[i2_1]));
                    tr[i2_1] = mb;
                }
                else
                    break;
            }
            dt >>= lft;
            while (dt > 0) {
                var i2_2 = t2[i].s;
                if (tr[i2_2] < mb)
                    dt -= 1 << (mb - tr[i2_2]++ - 1);
                else
                    ++i;
            }
            for (; i >= 0 && dt; --i) {
                var i2_3 = t2[i].s;
                if (tr[i2_3] == mb) {
                    --tr[i2_3];
                    ++dt;
                }
            }
            mbt = mb;
        }
        return { t: new u8(tr), l: mbt };
    };
    // get the max length and assign length codes
    var ln = function (n, l, d) {
        return n.s == -1
            ? Math.max(ln(n.l, l, d + 1), ln(n.r, l, d + 1))
            : (l[n.s] = d);
    };
    // length codes generation
    var lc = function (c) {
        var s = c.length;
        // Note that the semicolon was intentional
        while (s && !c[--s])
            ;
        var cl = new u16(++s);
        //  ind      num         streak
        var cli = 0, cln = c[0], cls = 1;
        var w = function (v) { cl[cli++] = v; };
        for (var i = 1; i <= s; ++i) {
            if (c[i] == cln && i != s)
                ++cls;
            else {
                if (!cln && cls > 2) {
                    for (; cls > 138; cls -= 138)
                        w(32754);
                    if (cls > 2) {
                        w(cls > 10 ? ((cls - 11) << 5) | 28690 : ((cls - 3) << 5) | 12305);
                        cls = 0;
                    }
                }
                else if (cls > 3) {
                    w(cln), --cls;
                    for (; cls > 6; cls -= 6)
                        w(8304);
                    if (cls > 2)
                        w(((cls - 3) << 5) | 8208), cls = 0;
                }
                while (cls--)
                    w(cln);
                cls = 1;
                cln = c[i];
            }
        }
        return { c: cl.subarray(0, cli), n: s };
    };
    // calculate the length of output from tree, code lengths
    var clen = function (cf, cl) {
        var l = 0;
        for (var i = 0; i < cl.length; ++i)
            l += cf[i] * cl[i];
        return l;
    };
    // writes a fixed block
    // returns the new bit pos
    var wfblk = function (out, pos, dat) {
        // no need to write 00 as type: TypedArray defaults to 0
        var s = dat.length;
        var o = shft(pos + 2);
        out[o] = s & 255;
        out[o + 1] = s >> 8;
        out[o + 2] = out[o] ^ 255;
        out[o + 3] = out[o + 1] ^ 255;
        for (var i = 0; i < s; ++i)
            out[o + i + 4] = dat[i];
        return (o + 4 + s) * 8;
    };
    // writes a block
    var wblk = function (dat, out, final, syms, lf, df, eb, li, bs, bl, p) {
        wbits(out, p++, final);
        ++lf[256];
        var _a = hTree(lf, 15), dlt = _a.t, mlb = _a.l;
        var _b = hTree(df, 15), ddt = _b.t, mdb = _b.l;
        var _c = lc(dlt), lclt = _c.c, nlc = _c.n;
        var _d = lc(ddt), lcdt = _d.c, ndc = _d.n;
        var lcfreq = new u16(19);
        for (var i = 0; i < lclt.length; ++i)
            ++lcfreq[lclt[i] & 31];
        for (var i = 0; i < lcdt.length; ++i)
            ++lcfreq[lcdt[i] & 31];
        var _e = hTree(lcfreq, 7), lct = _e.t, mlcb = _e.l;
        var nlcc = 19;
        for (; nlcc > 4 && !lct[clim[nlcc - 1]]; --nlcc)
            ;
        var flen = (bl + 5) << 3;
        var ftlen = clen(lf, flt) + clen(df, fdt) + eb;
        var dtlen = clen(lf, dlt) + clen(df, ddt) + eb + 14 + 3 * nlcc + clen(lcfreq, lct) + 2 * lcfreq[16] + 3 * lcfreq[17] + 7 * lcfreq[18];
        if (bs >= 0 && flen <= ftlen && flen <= dtlen)
            return wfblk(out, p, dat.subarray(bs, bs + bl));
        var lm, ll, dm, dl;
        wbits(out, p, 1 + (dtlen < ftlen)), p += 2;
        if (dtlen < ftlen) {
            lm = hMap(dlt, mlb, 0), ll = dlt, dm = hMap(ddt, mdb, 0), dl = ddt;
            var llm = hMap(lct, mlcb, 0);
            wbits(out, p, nlc - 257);
            wbits(out, p + 5, ndc - 1);
            wbits(out, p + 10, nlcc - 4);
            p += 14;
            for (var i = 0; i < nlcc; ++i)
                wbits(out, p + 3 * i, lct[clim[i]]);
            p += 3 * nlcc;
            var lcts = [lclt, lcdt];
            for (var it = 0; it < 2; ++it) {
                var clct = lcts[it];
                for (var i = 0; i < clct.length; ++i) {
                    var len = clct[i] & 31;
                    wbits(out, p, llm[len]), p += lct[len];
                    if (len > 15)
                        wbits(out, p, (clct[i] >> 5) & 127), p += clct[i] >> 12;
                }
            }
        }
        else {
            lm = flm, ll = flt, dm = fdm, dl = fdt;
        }
        for (var i = 0; i < li; ++i) {
            var sym = syms[i];
            if (sym > 255) {
                var len = (sym >> 18) & 31;
                wbits16(out, p, lm[len + 257]), p += ll[len + 257];
                if (len > 7)
                    wbits(out, p, (sym >> 23) & 31), p += fleb[len];
                var dst = sym & 31;
                wbits16(out, p, dm[dst]), p += dl[dst];
                if (dst > 3)
                    wbits16(out, p, (sym >> 5) & 8191), p += fdeb[dst];
            }
            else {
                wbits16(out, p, lm[sym]), p += ll[sym];
            }
        }
        wbits16(out, p, lm[256]);
        return p + ll[256];
    };
    // deflate options (nice << 13) | chain
    var deo = /*#__PURE__*/ new i32([65540, 131080, 131088, 131104, 262176, 1048704, 1048832, 2114560, 2117632]);
    // empty
    var et = /*#__PURE__*/ new u8(0);
    // compresses data into a raw DEFLATE buffer
    var dflt = function (dat, lvl, plvl, pre, post, st) {
        var s = st.z || dat.length;
        var o = new u8(pre + s + 5 * (1 + Math.ceil(s / 7000)) + post);
        // writing to this writes to the output buffer
        var w = o.subarray(pre, o.length - post);
        var lst = st.l;
        var pos = (st.r || 0) & 7;
        if (lvl) {
            if (pos)
                w[0] = st.r >> 3;
            var opt = deo[lvl - 1];
            var n = opt >> 13, c = opt & 8191;
            var msk_1 = (1 << plvl) - 1;
            //    prev 2-byte val map    curr 2-byte val map
            var prev = st.p || new u16(32768), head = st.h || new u16(msk_1 + 1);
            var bs1_1 = Math.ceil(plvl / 3), bs2_1 = 2 * bs1_1;
            var hsh = function (i) { return (dat[i] ^ (dat[i + 1] << bs1_1) ^ (dat[i + 2] << bs2_1)) & msk_1; };
            // 24576 is an arbitrary number of maximum symbols per block
            // 424 buffer for last block
            var syms = new i32(25000);
            // length/literal freq   distance freq
            var lf = new u16(288), df = new u16(32);
            //  l/lcnt  exbits  index          l/lind  waitdx          blkpos
            var lc_1 = 0, eb = 0, i = st.i || 0, li = 0, wi = st.w || 0, bs = 0;
            for (; i + 2 < s; ++i) {
                // hash value
                var hv = hsh(i);
                // index mod 32768    previous index mod
                var imod = i & 32767, pimod = head[hv];
                prev[imod] = pimod;
                head[hv] = imod;
                // We always should modify head and prev, but only add symbols if
                // this data is not yet processed ("wait" for wait index)
                if (wi <= i) {
                    // bytes remaining
                    var rem = s - i;
                    if ((lc_1 > 7000 || li > 24576) && (rem > 423 || !lst)) {
                        pos = wblk(dat, w, 0, syms, lf, df, eb, li, bs, i - bs, pos);
                        li = lc_1 = eb = 0, bs = i;
                        for (var j = 0; j < 286; ++j)
                            lf[j] = 0;
                        for (var j = 0; j < 30; ++j)
                            df[j] = 0;
                    }
                    //  len    dist   chain
                    var l = 2, d = 0, ch_1 = c, dif = imod - pimod & 32767;
                    if (rem > 2 && hv == hsh(i - dif)) {
                        var maxn = Math.min(n, rem) - 1;
                        var maxd = Math.min(32767, i);
                        // max possible length
                        // not capped at dif because decompressors implement "rolling" index population
                        var ml = Math.min(258, rem);
                        while (dif <= maxd && --ch_1 && imod != pimod) {
                            if (dat[i + l] == dat[i + l - dif]) {
                                var nl = 0;
                                for (; nl < ml && dat[i + nl] == dat[i + nl - dif]; ++nl)
                                    ;
                                if (nl > l) {
                                    l = nl, d = dif;
                                    // break out early when we reach "nice" (we are satisfied enough)
                                    if (nl > maxn)
                                        break;
                                    // now, find the rarest 2-byte sequence within this
                                    // length of literals and search for that instead.
                                    // Much faster than just using the start
                                    var mmd = Math.min(dif, nl - 2);
                                    var md = 0;
                                    for (var j = 0; j < mmd; ++j) {
                                        var ti = i - dif + j & 32767;
                                        var pti = prev[ti];
                                        var cd = ti - pti & 32767;
                                        if (cd > md)
                                            md = cd, pimod = ti;
                                    }
                                }
                            }
                            // check the previous match
                            imod = pimod, pimod = prev[imod];
                            dif += imod - pimod & 32767;
                        }
                    }
                    // d will be nonzero only when a match was found
                    if (d) {
                        // store both dist and len data in one int32
                        // Make sure this is recognized as a len/dist with 28th bit (2^28)
                        syms[li++] = 268435456 | (revfl[l] << 18) | revfd[d];
                        var lin = revfl[l] & 31, din = revfd[d] & 31;
                        eb += fleb[lin] + fdeb[din];
                        ++lf[257 + lin];
                        ++df[din];
                        wi = i + l;
                        ++lc_1;
                    }
                    else {
                        syms[li++] = dat[i];
                        ++lf[dat[i]];
                    }
                }
            }
            for (i = Math.max(i, wi); i < s; ++i) {
                syms[li++] = dat[i];
                ++lf[dat[i]];
            }
            pos = wblk(dat, w, lst, syms, lf, df, eb, li, bs, i - bs, pos);
            if (!lst) {
                st.r = (pos & 7) | w[(pos / 8) | 0] << 3;
                // shft(pos) now 1 less if pos & 7 != 0
                pos -= 7;
                st.h = head, st.p = prev, st.i = i, st.w = wi;
            }
        }
        else {
            for (var i = st.w || 0; i < s + lst; i += 65535) {
                // end
                var e = i + 65535;
                if (e >= s) {
                    // write final block
                    w[(pos / 8) | 0] = lst;
                    e = s;
                }
                pos = wfblk(w, pos + 1, dat.subarray(i, e));
            }
            st.i = s;
        }
        return slc(o, 0, pre + shft(pos) + post);
    };
    // CRC32 table
    var crct = /*#__PURE__*/ (function () {
        var t = new Int32Array(256);
        for (var i = 0; i < 256; ++i) {
            var c = i, k = 9;
            while (--k)
                c = ((c & 1) && -306674912) ^ (c >>> 1);
            t[i] = c;
        }
        return t;
    })();
    // CRC32
    var crc = function () {
        var c = -1;
        return {
            p: function (d) {
                // closures have awful performance
                var cr = c;
                for (var i = 0; i < d.length; ++i)
                    cr = crct[(cr & 255) ^ d[i]] ^ (cr >>> 8);
                c = cr;
            },
            d: function () { return ~c; }
        };
    };
    // deflate with opts
    var dopt = function (dat, opt, pre, post, st) {
        if (!st) {
            st = { l: 1 };
            if (opt.dictionary) {
                var dict = opt.dictionary.subarray(-32768);
                var newDat = new u8(dict.length + dat.length);
                newDat.set(dict);
                newDat.set(dat, dict.length);
                dat = newDat;
                st.w = dict.length;
            }
        }
        return dflt(dat, opt.level == null ? 6 : opt.level, opt.mem == null ? (st.l ? Math.ceil(Math.max(8, Math.min(13, Math.log(dat.length))) * 1.5) : 20) : (12 + opt.mem), pre, post, st);
    };
    // Walmart object spread
    var mrg = function (a, b) {
        var o = {};
        for (var k in a)
            o[k] = a[k];
        for (var k in b)
            o[k] = b[k];
        return o;
    };
    // read 2 bytes
    var b2 = function (d, b) { return d[b] | (d[b + 1] << 8); };
    // read 4 bytes
    var b4 = function (d, b) { return (d[b] | (d[b + 1] << 8) | (d[b + 2] << 16) | (d[b + 3] << 24)) >>> 0; };
    var b8 = function (d, b) { return b4(d, b) + (b4(d, b + 4) * 4294967296); };
    // write bytes
    var wbytes = function (d, b, v) {
        for (; v; ++b)
            d[b] = v, v >>>= 8;
    };
    /**
     * Compresses data with DEFLATE without any wrapper
     * @param data The data to compress
     * @param opts The compression options
     * @returns The deflated version of the data
     */
    function deflateSync(data, opts) {
        return dopt(data, opts || {}, 0, 0);
    }
    /**
     * Expands DEFLATE data with no wrapper
     * @param data The data to decompress
     * @param opts The decompression options
     * @returns The decompressed version of the data
     */
    function inflateSync(data, opts) {
        return inflt(data, { i: 2 }, opts && opts.out, opts && opts.dictionary);
    }
    // flatten a directory structure
    var fltn = function (d, p, t, o) {
        for (var k in d) {
            var val = d[k], n = p + k, op = o;
            if (Array.isArray(val))
                op = mrg(o, val[1]), val = val[0];
            if (val instanceof u8)
                t[n] = [val, op];
            else {
                t[n += '/'] = [new u8(0), op];
                fltn(val, n, t, o);
            }
        }
    };
    // text encoder
    var te = typeof TextEncoder != 'undefined' && /*#__PURE__*/ new TextEncoder();
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
     * Converts a string into a Uint8Array for use with compression/decompression methods
     * @param str The string to encode
     * @param latin1 Whether or not to interpret the data as Latin-1. This should
     *               not need to be true unless decoding a binary string.
     * @returns The string encoded in UTF-8/Latin-1 binary
     */
    function strToU8(str, latin1) {
        var i; 
        if (te)
            return te.encode(str);
        var l = str.length;
        var ar = new u8(str.length + (str.length >> 1));
        var ai = 0;
        var w = function (v) { ar[ai++] = v; };
        for (var i = 0; i < l; ++i) {
            if (ai + 5 > ar.length) {
                var n = new u8(ai + 8 + ((l - i) << 1));
                n.set(ar);
                ar = n;
            }
            var c = str.charCodeAt(i);
            if (c < 128 || latin1)
                w(c);
            else if (c < 2048)
                w(192 | (c >> 6)), w(128 | (c & 63));
            else if (c > 55295 && c < 57344)
                c = 65536 + (c & 1023 << 10) | (str.charCodeAt(++i) & 1023),
                    w(240 | (c >> 18)), w(128 | ((c >> 12) & 63)), w(128 | ((c >> 6) & 63)), w(128 | (c & 63));
            else
                w(224 | (c >> 12)), w(128 | ((c >> 6) & 63)), w(128 | (c & 63));
        }
        return slc(ar, 0, ai);
    }
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
    // extra field length
    var exfl = function (ex) {
        var le = 0;
        if (ex) {
            for (var k in ex) {
                var l = ex[k].length;
                if (l > 65535)
                    err(9);
                le += l + 4;
            }
        }
        return le;
    };
    // write zip header
    var wzh = function (d, b, f, fn, u, c, ce, co) {
        var fl = fn.length, ex = f.extra, col = co && co.length;
        var exl = exfl(ex);
        wbytes(d, b, ce != null ? 0x2014B50 : 0x4034B50), b += 4;
        if (ce != null)
            d[b++] = 20, d[b++] = f.os;
        d[b] = 20, b += 2; // spec compliance? what's that?
        d[b++] = (f.flag << 1) | (c < 0 && 8), d[b++] = u && 8;
        d[b++] = f.compression & 255, d[b++] = f.compression >> 8;
        var dt = new Date(f.mtime == null ? Date.now() : f.mtime), y = dt.getFullYear() - 1980;
        if (y < 0 || y > 119)
            err(10);
        wbytes(d, b, (y << 25) | ((dt.getMonth() + 1) << 21) | (dt.getDate() << 16) | (dt.getHours() << 11) | (dt.getMinutes() << 5) | (dt.getSeconds() >> 1)), b += 4;
        if (c != -1) {
            wbytes(d, b, f.crc);
            wbytes(d, b + 4, c < 0 ? -c - 2 : c);
            wbytes(d, b + 8, f.size);
        }
        wbytes(d, b + 12, fl);
        wbytes(d, b + 14, exl), b += 16;
        if (ce != null) {
            wbytes(d, b, col);
            wbytes(d, b + 6, f.attrs);
            wbytes(d, b + 10, ce), b += 14;
        }
        d.set(fn, b);
        b += fl;
        if (exl) {
            for (var k in ex) {
                var exf = ex[k], l = exf.length;
                wbytes(d, b, +k);
                wbytes(d, b + 2, l);
                d.set(exf, b + 4), b += 4 + l;
            }
        }
        if (col)
            d.set(co, b), b += col;
        return b;
    };
    // write zip footer (end of central directory)
    var wzf = function (o, b, c, d, e) {
        wbytes(o, b, 0x6054B50); // skip disk
        wbytes(o, b + 8, c);
        wbytes(o, b + 10, c);
        wbytes(o, b + 12, d);
        wbytes(o, b + 16, e);
    };
    /**
     * Synchronously creates a ZIP file. Prefer using `zip` for better performance
     * with more than one file.
     * @param data The directory structure for the ZIP archive
     * @param opts The main options, merged with per-file options
     * @returns The generated ZIP archive
     */
    function zipSync(data, opts) {
        if (!opts)
            opts = {};
        var r = {};
        var files = [];
        fltn(data, '', r, opts);
        var o = 0;
        var tot = 0;
        for (var fn in r) {
            var _a = r[fn], file = _a[0], p = _a[1];
            var compression = p.level == 0 ? 0 : 8;
            var f = strToU8(fn), s = f.length;
            var com = p.comment, m = com && strToU8(com), ms = m && m.length;
            var exl = exfl(p.extra);
            if (s > 65535)
                err(11);
            var d = compression ? deflateSync(file, p) : file, l = d.length;
            var c = crc();
            c.p(file);
            files.push(mrg(p, {
                size: file.length,
                crc: c.d(),
                c: d,
                f: f,
                m: m,
                u: s != fn.length || (m && (com.length != ms)),
                o: o,
                compression: compression
            }));
            o += 30 + s + exl + l;
            tot += 76 + 2 * (s + exl) + (ms || 0) + l;
        }
        var out = new u8(tot + 22), oe = o, cdl = tot - o;
        for (var i = 0; i < files.length; ++i) {
            var f = files[i];
            wzh(out, f.o, f, f.f, f.u, f.c.length);
            var badd = 30 + f.f.length + exfl(f.extra);
            out.set(f.c, f.o + badd);
            wzh(out, o, f, f.f, f.u, f.c.length, f.o, f.m), o += 16 + badd + (f.m ? f.m.length : 0);
        }
        wzf(out, o, files.length, cdl, oe);
        return out;
    }
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

    var validator$1 = {};

    var util$3 = {};

    (function (exports) {

    	const nameStartChar = ':A-Za-z_\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD';
    	const nameChar = nameStartChar + '\\-.\\d\\u00B7\\u0300-\\u036F\\u203F-\\u2040';
    	const nameRegexp = '[' + nameStartChar + '][' + nameChar + ']*';
    	const regexName = new RegExp('^' + nameRegexp + '$');

    	const getAllMatches = function (string, regex) {
    	  const matches = [];
    	  let match = regex.exec(string);
    	  while (match) {
    	    const allmatches = [];
    	    allmatches.startIndex = regex.lastIndex - match[0].length;
    	    const len = match.length;
    	    for (let index = 0; index < len; index++) {
    	      allmatches.push(match[index]);
    	    }
    	    matches.push(allmatches);
    	    match = regex.exec(string);
    	  }
    	  return matches;
    	};

    	const isName = function (string) {
    	  const match = regexName.exec(string);
    	  return !(match === null || typeof match === 'undefined');
    	};

    	exports.isExist = function (v) {
    	  return typeof v !== 'undefined';
    	};

    	exports.isEmptyObject = function (obj) {
    	  return Object.keys(obj).length === 0;
    	};

    	/**
    	 * Copy all the properties of a into b.
    	 * @param {*} target
    	 * @param {*} a
    	 */
    	exports.merge = function (target, a, arrayMode) {
    	  if (a) {
    	    const keys = Object.keys(a); // will return an array of own properties
    	    const len = keys.length; //don't make it inline
    	    for (let i = 0; i < len; i++) {
    	      if (arrayMode === 'strict') {
    	        target[keys[i]] = [a[keys[i]]];
    	      } else {
    	        target[keys[i]] = a[keys[i]];
    	      }
    	    }
    	  }
    	};
    	/* exports.merge =function (b,a){
    	  return Object.assign(b,a);
    	} */

    	exports.getValue = function (v) {
    	  if (exports.isExist(v)) {
    	    return v;
    	  } else {
    	    return '';
    	  }
    	};

    	/**
    	 * Dangerous property names that could lead to prototype pollution or security issues
    	 */
    	const DANGEROUS_PROPERTY_NAMES = [
    	  // '__proto__',
    	  // 'constructor',
    	  // 'prototype',
    	  'hasOwnProperty',
    	  'toString',
    	  'valueOf',
    	  '__defineGetter__',
    	  '__defineSetter__',
    	  '__lookupGetter__',
    	  '__lookupSetter__'
    	];

    	const criticalProperties = ["__proto__", "constructor", "prototype"];

    	exports.isName = isName;
    	exports.getAllMatches = getAllMatches;
    	exports.nameRegexp = nameRegexp;
    	exports.DANGEROUS_PROPERTY_NAMES = DANGEROUS_PROPERTY_NAMES;
    	exports.criticalProperties = criticalProperties; 
    } (util$3));

    const util$2 = util$3;

    const defaultOptions$1 = {
      allowBooleanAttributes: false, //A tag can have attributes without any value
      unpairedTags: []
    };

    //const tagsPattern = new RegExp("<\\/?([\\w:\\-_\.]+)\\s*\/?>","g");
    validator$1.validate = function (xmlData, options) {
      options = Object.assign({}, defaultOptions$1, options);

      //xmlData = xmlData.replace(/(\r\n|\n|\r)/gm,"");//make it single line
      //xmlData = xmlData.replace(/(^\s*<\?xml.*?\?>)/g,"");//Remove XML starting tag
      //xmlData = xmlData.replace(/(<!DOCTYPE[\s\w\"\.\/\-\:]+(\[.*\])*\s*>)/g,"");//Remove DOCTYPE
      const tags = [];
      let tagFound = false;

      //indicates that the root tag has been closed (aka. depth 0 has been reached)
      let reachedRoot = false;

      if (xmlData[0] === '\ufeff') {
        // check for byte order mark (BOM)
        xmlData = xmlData.substr(1);
      }
      
      for (let i = 0; i < xmlData.length; i++) {

        if (xmlData[i] === '<' && xmlData[i+1] === '?') {
          i+=2;
          i = readPI(xmlData,i);
          if (i.err) return i;
        }else if (xmlData[i] === '<') {
          //starting of tag
          //read until you reach to '>' avoiding any '>' in attribute value
          let tagStartPos = i;
          i++;
          
          if (xmlData[i] === '!') {
            i = readCommentAndCDATA(xmlData, i);
            continue;
          } else {
            let closingTag = false;
            if (xmlData[i] === '/') {
              //closing tag
              closingTag = true;
              i++;
            }
            //read tagname
            let tagName = '';
            for (; i < xmlData.length &&
              xmlData[i] !== '>' &&
              xmlData[i] !== ' ' &&
              xmlData[i] !== '\t' &&
              xmlData[i] !== '\n' &&
              xmlData[i] !== '\r'; i++
            ) {
              tagName += xmlData[i];
            }
            tagName = tagName.trim();
            //console.log(tagName);

            if (tagName[tagName.length - 1] === '/') {
              //self closing tag without attributes
              tagName = tagName.substring(0, tagName.length - 1);
              //continue;
              i--;
            }
            if (!validateTagName(tagName)) {
              let msg;
              if (tagName.trim().length === 0) {
                msg = "Invalid space after '<'.";
              } else {
                msg = "Tag '"+tagName+"' is an invalid name.";
              }
              return getErrorObject('InvalidTag', msg, getLineNumberForPosition(xmlData, i));
            }

            const result = readAttributeStr(xmlData, i);
            if (result === false) {
              return getErrorObject('InvalidAttr', "Attributes for '"+tagName+"' have open quote.", getLineNumberForPosition(xmlData, i));
            }
            let attrStr = result.value;
            i = result.index;

            if (attrStr[attrStr.length - 1] === '/') {
              //self closing tag
              const attrStrStart = i - attrStr.length;
              attrStr = attrStr.substring(0, attrStr.length - 1);
              const isValid = validateAttributeString(attrStr, options);
              if (isValid === true) {
                tagFound = true;
                //continue; //text may presents after self closing tag
              } else {
                //the result from the nested function returns the position of the error within the attribute
                //in order to get the 'true' error line, we need to calculate the position where the attribute begins (i - attrStr.length) and then add the position within the attribute
                //this gives us the absolute index in the entire xml, which we can use to find the line at last
                return getErrorObject(isValid.err.code, isValid.err.msg, getLineNumberForPosition(xmlData, attrStrStart + isValid.err.line));
              }
            } else if (closingTag) {
              if (!result.tagClosed) {
                return getErrorObject('InvalidTag', "Closing tag '"+tagName+"' doesn't have proper closing.", getLineNumberForPosition(xmlData, i));
              } else if (attrStr.trim().length > 0) {
                return getErrorObject('InvalidTag', "Closing tag '"+tagName+"' can't have attributes or invalid starting.", getLineNumberForPosition(xmlData, tagStartPos));
              } else if (tags.length === 0) {
                return getErrorObject('InvalidTag', "Closing tag '"+tagName+"' has not been opened.", getLineNumberForPosition(xmlData, tagStartPos));
              } else {
                const otg = tags.pop();
                if (tagName !== otg.tagName) {
                  let openPos = getLineNumberForPosition(xmlData, otg.tagStartPos);
                  return getErrorObject('InvalidTag',
                    "Expected closing tag '"+otg.tagName+"' (opened in line "+openPos.line+", col "+openPos.col+") instead of closing tag '"+tagName+"'.",
                    getLineNumberForPosition(xmlData, tagStartPos));
                }

                //when there are no more tags, we reached the root level.
                if (tags.length == 0) {
                  reachedRoot = true;
                }
              }
            } else {
              const isValid = validateAttributeString(attrStr, options);
              if (isValid !== true) {
                //the result from the nested function returns the position of the error within the attribute
                //in order to get the 'true' error line, we need to calculate the position where the attribute begins (i - attrStr.length) and then add the position within the attribute
                //this gives us the absolute index in the entire xml, which we can use to find the line at last
                return getErrorObject(isValid.err.code, isValid.err.msg, getLineNumberForPosition(xmlData, i - attrStr.length + isValid.err.line));
              }

              //if the root level has been reached before ...
              if (reachedRoot === true) {
                return getErrorObject('InvalidXml', 'Multiple possible root nodes found.', getLineNumberForPosition(xmlData, i));
              } else if(options.unpairedTags.indexOf(tagName) !== -1); else {
                tags.push({tagName, tagStartPos});
              }
              tagFound = true;
            }

            //skip tag text value
            //It may include comments and CDATA value
            for (i++; i < xmlData.length; i++) {
              if (xmlData[i] === '<') {
                if (xmlData[i + 1] === '!') {
                  //comment or CADATA
                  i++;
                  i = readCommentAndCDATA(xmlData, i);
                  continue;
                } else if (xmlData[i+1] === '?') {
                  i = readPI(xmlData, ++i);
                  if (i.err) return i;
                } else {
                  break;
                }
              } else if (xmlData[i] === '&') {
                const afterAmp = validateAmpersand(xmlData, i);
                if (afterAmp == -1)
                  return getErrorObject('InvalidChar', "char '&' is not expected.", getLineNumberForPosition(xmlData, i));
                i = afterAmp;
              }else {
                if (reachedRoot === true && !isWhiteSpace(xmlData[i])) {
                  return getErrorObject('InvalidXml', "Extra text at the end", getLineNumberForPosition(xmlData, i));
                }
              }
            } //end of reading tag text value
            if (xmlData[i] === '<') {
              i--;
            }
          }
        } else {
          if ( isWhiteSpace(xmlData[i])) {
            continue;
          }
          return getErrorObject('InvalidChar', "char '"+xmlData[i]+"' is not expected.", getLineNumberForPosition(xmlData, i));
        }
      }

      if (!tagFound) {
        return getErrorObject('InvalidXml', 'Start tag expected.', 1);
      }else if (tags.length == 1) {
          return getErrorObject('InvalidTag', "Unclosed tag '"+tags[0].tagName+"'.", getLineNumberForPosition(xmlData, tags[0].tagStartPos));
      }else if (tags.length > 0) {
          return getErrorObject('InvalidXml', "Invalid '"+
              JSON.stringify(tags.map(t => t.tagName), null, 4).replace(/\r?\n/g, '')+
              "' found.", {line: 1, col: 1});
      }

      return true;
    };

    function isWhiteSpace(char){
      return char === ' ' || char === '\t' || char === '\n'  || char === '\r';
    }
    /**
     * Read Processing insstructions and skip
     * @param {*} xmlData
     * @param {*} i
     */
    function readPI(xmlData, i) {
      const start = i;
      for (; i < xmlData.length; i++) {
        if (xmlData[i] == '?' || xmlData[i] == ' ') {
          //tagname
          const tagname = xmlData.substr(start, i - start);
          if (i > 5 && tagname === 'xml') {
            return getErrorObject('InvalidXml', 'XML declaration allowed only at the start of the document.', getLineNumberForPosition(xmlData, i));
          } else if (xmlData[i] == '?' && xmlData[i + 1] == '>') {
            //check if valid attribut string
            i++;
            break;
          } else {
            continue;
          }
        }
      }
      return i;
    }

    function readCommentAndCDATA(xmlData, i) {
      if (xmlData.length > i + 5 && xmlData[i + 1] === '-' && xmlData[i + 2] === '-') {
        //comment
        for (i += 3; i < xmlData.length; i++) {
          if (xmlData[i] === '-' && xmlData[i + 1] === '-' && xmlData[i + 2] === '>') {
            i += 2;
            break;
          }
        }
      } else if (
        xmlData.length > i + 8 &&
        xmlData[i + 1] === 'D' &&
        xmlData[i + 2] === 'O' &&
        xmlData[i + 3] === 'C' &&
        xmlData[i + 4] === 'T' &&
        xmlData[i + 5] === 'Y' &&
        xmlData[i + 6] === 'P' &&
        xmlData[i + 7] === 'E'
      ) {
        let angleBracketsCount = 1;
        for (i += 8; i < xmlData.length; i++) {
          if (xmlData[i] === '<') {
            angleBracketsCount++;
          } else if (xmlData[i] === '>') {
            angleBracketsCount--;
            if (angleBracketsCount === 0) {
              break;
            }
          }
        }
      } else if (
        xmlData.length > i + 9 &&
        xmlData[i + 1] === '[' &&
        xmlData[i + 2] === 'C' &&
        xmlData[i + 3] === 'D' &&
        xmlData[i + 4] === 'A' &&
        xmlData[i + 5] === 'T' &&
        xmlData[i + 6] === 'A' &&
        xmlData[i + 7] === '['
      ) {
        for (i += 8; i < xmlData.length; i++) {
          if (xmlData[i] === ']' && xmlData[i + 1] === ']' && xmlData[i + 2] === '>') {
            i += 2;
            break;
          }
        }
      }

      return i;
    }

    const doubleQuote = '"';
    const singleQuote = "'";

    /**
     * Keep reading xmlData until '<' is found outside the attribute value.
     * @param {string} xmlData
     * @param {number} i
     */
    function readAttributeStr(xmlData, i) {
      let attrStr = '';
      let startChar = '';
      let tagClosed = false;
      for (; i < xmlData.length; i++) {
        if (xmlData[i] === doubleQuote || xmlData[i] === singleQuote) {
          if (startChar === '') {
            startChar = xmlData[i];
          } else if (startChar !== xmlData[i]) ; else {
            startChar = '';
          }
        } else if (xmlData[i] === '>') {
          if (startChar === '') {
            tagClosed = true;
            break;
          }
        }
        attrStr += xmlData[i];
      }
      if (startChar !== '') {
        return false;
      }

      return {
        value: attrStr,
        index: i,
        tagClosed: tagClosed
      };
    }

    /**
     * Select all the attributes whether valid or invalid.
     */
    const validAttrStrRegxp = new RegExp('(\\s*)([^\\s=]+)(\\s*=)?(\\s*([\'"])(([\\s\\S])*?)\\5)?', 'g');

    //attr, ="sd", a="amit's", a="sd"b="saf", ab  cd=""

    function validateAttributeString(attrStr, options) {
      //console.log("start:"+attrStr+":end");

      //if(attrStr.trim().length === 0) return true; //empty string

      const matches = util$2.getAllMatches(attrStr, validAttrStrRegxp);
      const attrNames = {};

      for (let i = 0; i < matches.length; i++) {
        if (matches[i][1].length === 0) {
          //nospace before attribute name: a="sd"b="saf"
          return getErrorObject('InvalidAttr', "Attribute '"+matches[i][2]+"' has no space in starting.", getPositionFromMatch(matches[i]))
        } else if (matches[i][3] !== undefined && matches[i][4] === undefined) {
          return getErrorObject('InvalidAttr', "Attribute '"+matches[i][2]+"' is without value.", getPositionFromMatch(matches[i]));
        } else if (matches[i][3] === undefined && !options.allowBooleanAttributes) {
          //independent attribute: ab
          return getErrorObject('InvalidAttr', "boolean attribute '"+matches[i][2]+"' is not allowed.", getPositionFromMatch(matches[i]));
        }
        /* else if(matches[i][6] === undefined){//attribute without value: ab=
                        return { err: { code:"InvalidAttr",msg:"attribute " + matches[i][2] + " has no value assigned."}};
                    } */
        const attrName = matches[i][2];
        if (!validateAttrName(attrName)) {
          return getErrorObject('InvalidAttr', "Attribute '"+attrName+"' is an invalid name.", getPositionFromMatch(matches[i]));
        }
        if (!attrNames.hasOwnProperty(attrName)) {
          //check for duplicate attribute.
          attrNames[attrName] = 1;
        } else {
          return getErrorObject('InvalidAttr', "Attribute '"+attrName+"' is repeated.", getPositionFromMatch(matches[i]));
        }
      }

      return true;
    }

    function validateNumberAmpersand(xmlData, i) {
      let re = /\d/;
      if (xmlData[i] === 'x') {
        i++;
        re = /[\da-fA-F]/;
      }
      for (; i < xmlData.length; i++) {
        if (xmlData[i] === ';')
          return i;
        if (!xmlData[i].match(re))
          break;
      }
      return -1;
    }

    function validateAmpersand(xmlData, i) {
      // https://www.w3.org/TR/xml/#dt-charref
      i++;
      if (xmlData[i] === ';')
        return -1;
      if (xmlData[i] === '#') {
        i++;
        return validateNumberAmpersand(xmlData, i);
      }
      let count = 0;
      for (; i < xmlData.length; i++, count++) {
        if (xmlData[i].match(/\w/) && count < 20)
          continue;
        if (xmlData[i] === ';')
          break;
        return -1;
      }
      return i;
    }

    function getErrorObject(code, message, lineNumber) {
      return {
        err: {
          code: code,
          msg: message,
          line: lineNumber.line || lineNumber,
          col: lineNumber.col,
        },
      };
    }

    function validateAttrName(attrName) {
      return util$2.isName(attrName);
    }

    // const startsWithXML = /^xml/i;

    function validateTagName(tagname) {
      return util$2.isName(tagname) /* && !tagname.match(startsWithXML) */;
    }

    //this function returns the line number for the character at the given index
    function getLineNumberForPosition(xmlData, index) {
      const lines = xmlData.substring(0, index).split(/\r?\n/);
      return {
        line: lines.length,

        // column number is last line's length + 1, because column numbering starts at 1:
        col: lines[lines.length - 1].length + 1
      };
    }

    //this function returns the position of the first character of match within attrStr
    function getPositionFromMatch(match) {
      return match.startIndex + match[1].length;
    }

    var OptionsBuilder = {};

    const { DANGEROUS_PROPERTY_NAMES, criticalProperties } = util$3;

    const defaultOnDangerousProperty = (name) => {
      if (DANGEROUS_PROPERTY_NAMES.includes(name)) {
        return "__" + name;
      }
      return name;
    };
    const defaultOptions = {
      preserveOrder: false,
      attributeNamePrefix: '@_',
      attributesGroupName: false,
      textNodeName: '#text',
      ignoreAttributes: true,
      removeNSPrefix: false, // remove NS from tag name or attribute name if true
      allowBooleanAttributes: false, //a tag can have attributes without any value
      //ignoreRootElement : false,
      parseTagValue: true,
      parseAttributeValue: false,
      trimValues: true, //Trim string values of tag and attributes
      cdataPropName: false,
      numberParseOptions: {
        hex: true,
        leadingZeros: true,
        eNotation: true
      },
      tagValueProcessor: function (tagName, val) {
        return val;
      },
      attributeValueProcessor: function (attrName, val) {
        return val;
      },
      stopNodes: [], //nested tags will not be parsed even for errors
      alwaysCreateTextNode: false,
      isArray: () => false,
      commentPropName: false,
      unpairedTags: [],
      processEntities: true,
      htmlEntities: false,
      ignoreDeclaration: false,
      ignorePiTags: false,
      transformTagName: false,
      transformAttributeName: false,
      updateTag: function (tagName, jPath, attrs) {
        return tagName
      },
      // skipEmptyListItem: false
      captureMetaData: false,
      maxNestedTags: 100,
      strictReservedNames: true,
      onDangerousProperty: defaultOnDangerousProperty
    };
    /**
     * Validates that a property name is safe to use
     * @param {string} propertyName - The property name to validate
     * @param {string} optionName - The option field name (for error message)
     * @throws {Error} If property name is dangerous
     */
    function validatePropertyName(propertyName, optionName) {
      if (typeof propertyName !== 'string') {
        return; // Only validate string property names
      }

      const normalized = propertyName.toLowerCase();
      if (DANGEROUS_PROPERTY_NAMES.some(dangerous => normalized === dangerous.toLowerCase())) {
        throw new Error(
          `[SECURITY] Invalid ${optionName}: "${propertyName}" is a reserved JavaScript keyword that could cause prototype pollution`
        );
      }

      if (criticalProperties.some(dangerous => normalized === dangerous.toLowerCase())) {
        throw new Error(
          `[SECURITY] Invalid ${optionName}: "${propertyName}" is a reserved JavaScript keyword that could cause prototype pollution`
        );
      }
    }

    /**
     * Normalizes processEntities option for backward compatibility
     * @param {boolean|object} value 
     * @returns {object} Always returns normalized object
     */
    function normalizeProcessEntities(value) {
      // Boolean backward compatibility
      if (typeof value === 'boolean') {
        return {
          enabled: value, // true or false
          maxEntitySize: 10000,
          maxExpansionDepth: 10,
          maxTotalExpansions: 1000,
          maxExpandedLength: 100000,
          allowedTags: null,
          tagFilter: null
        };
      }

      // Object config - merge with defaults
      if (typeof value === 'object' && value !== null) {
        return {
          enabled: value.enabled !== false,
          maxEntitySize: Math.max(1, value.maxEntitySize ?? 10000),
          maxExpansionDepth: Math.max(1, value.maxExpansionDepth ?? 10000),
          maxTotalExpansions: Math.max(1, value.maxTotalExpansions ?? Infinity),
          maxExpandedLength: Math.max(1, value.maxExpandedLength ?? 100000),
          maxEntityCount: Math.max(1, value.maxEntityCount ?? 1000),
          allowedTags: value.allowedTags ?? null,
          tagFilter: value.tagFilter ?? null
        };
      }

      // Default to enabled with limits
      return normalizeProcessEntities(true);
    }

    const buildOptions$1 = function (options) {
      const built = Object.assign({}, defaultOptions, options);


      // Validate property names to prevent prototype pollution
      const propertyNameOptions = [
        { value: built.attributeNamePrefix, name: 'attributeNamePrefix' },
        { value: built.attributesGroupName, name: 'attributesGroupName' },
        { value: built.textNodeName, name: 'textNodeName' },
        { value: built.cdataPropName, name: 'cdataPropName' },
        { value: built.commentPropName, name: 'commentPropName' }
      ];

      for (const { value, name } of propertyNameOptions) {
        if (value) {
          validatePropertyName(value, name);
        }
      }

      if (built.onDangerousProperty === null) {
        built.onDangerousProperty = defaultOnDangerousProperty;
      }

      // Always normalize processEntities for backward compatibility and validation
      built.processEntities = normalizeProcessEntities(built.processEntities);
      //console.debug(built.processEntities)
      return built;
    };

    OptionsBuilder.buildOptions = buildOptions$1;
    OptionsBuilder.defaultOptions = defaultOptions;

    class XmlNode{
      constructor(tagname) {
        this.tagname = tagname;
        this.child = []; //nested tags, text, cdata, comments in order
        this[":@"] = {}; //attributes map
      }
      add(key,val){
        // this.child.push( {name : key, val: val, isCdata: isCdata });
        if(key === "__proto__") key = "#__proto__";
        this.child.push( {[key]: val });
      }
      addChild(node) {
        if(node.tagname === "__proto__") node.tagname = "#__proto__";
        if(node[":@"] && Object.keys(node[":@"]).length > 0){
          this.child.push( { [node.tagname]: node.child, [":@"]: node[":@"] });
        }else {
          this.child.push( { [node.tagname]: node.child });
        }
      };
    }

    var xmlNode$1 = XmlNode;

    const util$1 = util$3;

    let DocTypeReader$1 = class DocTypeReader {
        constructor(options) {
            this.suppressValidationErr = !options;
            this.options = options || {};
        }

        readDocType(xmlData, i) {
            const entities = Object.create(null);
            let entityCount = 0;

            if (xmlData[i + 3] === 'O' &&
                xmlData[i + 4] === 'C' &&
                xmlData[i + 5] === 'T' &&
                xmlData[i + 6] === 'Y' &&
                xmlData[i + 7] === 'P' &&
                xmlData[i + 8] === 'E') {

                i = i + 9;
                let angleBracketsCount = 1;
                let hasBody = false, comment = false;
                let exp = "";

                for (; i < xmlData.length; i++) {
                    if (xmlData[i] === '<' && !comment) { //Determine the tag type
                        if (hasBody && hasSeq(xmlData, "!ENTITY", i)) {
                            i += 7;
                            let entityName, val;
                            [entityName, val, i] = this.readEntityExp(xmlData, i + 1, this.suppressValidationErr);
                            if (val.indexOf("&") === -1) { //Parameter entities are not supported
                                if (this.options.enabled !== false &&
                                    this.options.maxEntityCount != null &&
                                    entityCount >= this.options.maxEntityCount) {
                                    throw new Error(
                                        `Entity count (${entityCount + 1}) exceeds maximum allowed (${this.options.maxEntityCount})`
                                    );
                                }
                                //const escaped = entityName.replace(/[.\-+*:]/g, '\\.');
                                const escaped = entityName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                                entities[entityName] = {
                                    regx: RegExp(`&${escaped};`, "g"),
                                    val: val
                                };
                                entityCount++;
                            }
                        } else if (hasBody && hasSeq(xmlData, "!ELEMENT", i)) {
                            i += 8; //Not supported
                            const { index } = this.readElementExp(xmlData, i + 1);
                            i = index;
                        } else if (hasBody && hasSeq(xmlData, "!ATTLIST", i)) {
                            i += 8; //Not supported
                            // const {index} = this.readAttlistExp(xmlData,i+1);
                            // i = index;
                        } else if (hasBody && hasSeq(xmlData, "!NOTATION", i)) {
                            i += 9; //Not supported
                            const { index } = this.readNotationExp(xmlData, i + 1, this.suppressValidationErr);
                            i = index;
                        } else if (hasSeq(xmlData, "!--", i)) {
                            comment = true;
                        } else {
                            throw new Error(`Invalid DOCTYPE`);
                        }

                        angleBracketsCount++;
                        exp = "";
                    } else if (xmlData[i] === '>') { //Read tag content
                        if (comment) {
                            if (xmlData[i - 1] === "-" && xmlData[i - 2] === "-") {
                                comment = false;
                                angleBracketsCount--;
                            }
                        } else {
                            angleBracketsCount--;
                        }
                        if (angleBracketsCount === 0) {
                            break;
                        }
                    } else if (xmlData[i] === '[') {
                        hasBody = true;
                    } else {
                        exp += xmlData[i];
                    }
                }

                if (angleBracketsCount !== 0) {
                    throw new Error(`Unclosed DOCTYPE`);
                }
            } else {
                throw new Error(`Invalid Tag instead of DOCTYPE`);
            }

            return { entities, i };
        }

        readEntityExp(xmlData, i) {
            //External entities are not supported
            //    <!ENTITY ext SYSTEM "http://normal-website.com" >

            //Parameter entities are not supported
            //    <!ENTITY entityname "&anotherElement;">

            //Internal entities are supported
            //    <!ENTITY entityname "replacement text">

            // Skip leading whitespace after <!ENTITY
            i = skipWhitespace(xmlData, i);

            // Read entity name
            let entityName = "";
            while (i < xmlData.length && !/\s/.test(xmlData[i]) && xmlData[i] !== '"' && xmlData[i] !== "'") {
                entityName += xmlData[i];
                i++;
            }
            validateEntityName(entityName);

            // Skip whitespace after entity name
            i = skipWhitespace(xmlData, i);

            // Check for unsupported constructs (external entities or parameter entities)
            if (!this.suppressValidationErr) {
                if (xmlData.substring(i, i + 6).toUpperCase() === "SYSTEM") {
                    throw new Error("External entities are not supported");
                } else if (xmlData[i] === "%") {
                    throw new Error("Parameter entities are not supported");
                }
            }

            // Read entity value (internal entity)
            let entityValue = "";
            [i, entityValue] = this.readIdentifierVal(xmlData, i, "entity");

            // Validate entity size
            if (this.options.enabled !== false &&
                this.options.maxEntitySize != null &&
                entityValue.length > this.options.maxEntitySize) {
                throw new Error(
                    `Entity "${entityName}" size (${entityValue.length}) exceeds maximum allowed size (${this.options.maxEntitySize})`
                );
            }

            i--;
            return [entityName, entityValue, i];
        }

        readNotationExp(xmlData, i) {
            // Skip leading whitespace after <!NOTATION
            i = skipWhitespace(xmlData, i);

            // Read notation name
            let notationName = "";
            while (i < xmlData.length && !/\s/.test(xmlData[i])) {
                notationName += xmlData[i];
                i++;
            }
            !this.suppressValidationErr && validateEntityName(notationName);

            // Skip whitespace after notation name
            i = skipWhitespace(xmlData, i);

            // Check identifier type (SYSTEM or PUBLIC)
            const identifierType = xmlData.substring(i, i + 6).toUpperCase();
            if (!this.suppressValidationErr && identifierType !== "SYSTEM" && identifierType !== "PUBLIC") {
                throw new Error(`Expected SYSTEM or PUBLIC, found "${identifierType}"`);
            }
            i += identifierType.length;

            // Skip whitespace after identifier type
            i = skipWhitespace(xmlData, i);

            // Read public identifier (if PUBLIC)
            let publicIdentifier = null;
            let systemIdentifier = null;

            if (identifierType === "PUBLIC") {
                [i, publicIdentifier] = this.readIdentifierVal(xmlData, i, "publicIdentifier");

                // Skip whitespace after public identifier
                i = skipWhitespace(xmlData, i);

                // Optionally read system identifier
                if (xmlData[i] === '"' || xmlData[i] === "'") {
                    [i, systemIdentifier] = this.readIdentifierVal(xmlData, i, "systemIdentifier");
                }
            } else if (identifierType === "SYSTEM") {
                // Read system identifier (mandatory for SYSTEM)
                [i, systemIdentifier] = this.readIdentifierVal(xmlData, i, "systemIdentifier");

                if (!this.suppressValidationErr && !systemIdentifier) {
                    throw new Error("Missing mandatory system identifier for SYSTEM notation");
                }
            }

            return { notationName, publicIdentifier, systemIdentifier, index: --i };
        }

        readIdentifierVal(xmlData, i, type) {
            let identifierVal = "";
            const startChar = xmlData[i];
            if (startChar !== '"' && startChar !== "'") {
                throw new Error(`Expected quoted string, found "${startChar}"`);
            }
            i++;

            while (i < xmlData.length && xmlData[i] !== startChar) {
                identifierVal += xmlData[i];
                i++;
            }

            if (xmlData[i] !== startChar) {
                throw new Error(`Unterminated ${type} value`);
            }
            i++;
            return [i, identifierVal];
        }

        readElementExp(xmlData, i) {
            // <!ELEMENT br EMPTY>
            // <!ELEMENT div ANY>
            // <!ELEMENT title (#PCDATA)>
            // <!ELEMENT book (title, author+)>
            // <!ELEMENT name (content-model)>

            // Skip leading whitespace after <!ELEMENT
            i = skipWhitespace(xmlData, i);

            // Read element name
            let elementName = "";
            while (i < xmlData.length && !/\s/.test(xmlData[i])) {
                elementName += xmlData[i];
                i++;
            }

            // Validate element name
            if (!this.suppressValidationErr && !util$1.isName(elementName)) {
                throw new Error(`Invalid element name: "${elementName}"`);
            }

            // Skip whitespace after element name
            i = skipWhitespace(xmlData, i);
            let contentModel = "";

            // Expect '(' to start content model
            if (xmlData[i] === "E" && hasSeq(xmlData, "MPTY", i)) {
                i += 4;
            } else if (xmlData[i] === "A" && hasSeq(xmlData, "NY", i)) {
                i += 2;
            } else if (xmlData[i] === "(") {
                i++; // Move past '('

                // Read content model
                while (i < xmlData.length && xmlData[i] !== ")") {
                    contentModel += xmlData[i];
                    i++;
                }
                if (xmlData[i] !== ")") {
                    throw new Error("Unterminated content model");
                }
            } else if (!this.suppressValidationErr) {
                throw new Error(`Invalid Element Expression, found "${xmlData[i]}"`);
            }

            return {
                elementName,
                contentModel: contentModel.trim(),
                index: i
            };
        }

        readAttlistExp(xmlData, i) {
            // Skip leading whitespace after <!ATTLIST
            i = skipWhitespace(xmlData, i);

            // Read element name
            let elementName = "";
            while (i < xmlData.length && !/\s/.test(xmlData[i])) {
                elementName += xmlData[i];
                i++;
            }

            // Validate element name
            validateEntityName(elementName);

            // Skip whitespace after element name
            i = skipWhitespace(xmlData, i);

            // Read attribute name
            let attributeName = "";
            while (i < xmlData.length && !/\s/.test(xmlData[i])) {
                attributeName += xmlData[i];
                i++;
            }

            // Validate attribute name
            if (!validateEntityName(attributeName)) {
                throw new Error(`Invalid attribute name: "${attributeName}"`);
            }

            // Skip whitespace after attribute name
            i = skipWhitespace(xmlData, i);

            // Read attribute type
            let attributeType = "";
            if (xmlData.substring(i, i + 8).toUpperCase() === "NOTATION") {
                attributeType = "NOTATION";
                i += 8; // Move past "NOTATION"

                // Skip whitespace after "NOTATION"
                i = skipWhitespace(xmlData, i);

                // Expect '(' to start the list of notations
                if (xmlData[i] !== "(") {
                    throw new Error(`Expected '(', found "${xmlData[i]}"`);
                }
                i++; // Move past '('

                // Read the list of allowed notations
                let allowedNotations = [];
                while (i < xmlData.length && xmlData[i] !== ")") {
                    let notation = "";
                    while (i < xmlData.length && xmlData[i] !== "|" && xmlData[i] !== ")") {
                        notation += xmlData[i];
                        i++;
                    }

                    // Validate notation name
                    notation = notation.trim();
                    if (!validateEntityName(notation)) {
                        throw new Error(`Invalid notation name: "${notation}"`);
                    }

                    allowedNotations.push(notation);

                    // Skip '|' separator or exit loop
                    if (xmlData[i] === "|") {
                        i++; // Move past '|'
                        i = skipWhitespace(xmlData, i); // Skip optional whitespace after '|'
                    }
                }

                if (xmlData[i] !== ")") {
                    throw new Error("Unterminated list of notations");
                }
                i++; // Move past ')'

                // Store the allowed notations as part of the attribute type
                attributeType += " (" + allowedNotations.join("|") + ")";
            } else {
                // Handle simple types (e.g., CDATA, ID, IDREF, etc.)
                while (i < xmlData.length && !/\s/.test(xmlData[i])) {
                    attributeType += xmlData[i];
                    i++;
                }

                // Validate simple attribute type
                const validTypes = ["CDATA", "ID", "IDREF", "IDREFS", "ENTITY", "ENTITIES", "NMTOKEN", "NMTOKENS"];
                if (!this.suppressValidationErr && !validTypes.includes(attributeType.toUpperCase())) {
                    throw new Error(`Invalid attribute type: "${attributeType}"`);
                }
            }

            // Skip whitespace after attribute type
            i = skipWhitespace(xmlData, i);

            // Read default value
            let defaultValue = "";
            if (xmlData.substring(i, i + 8).toUpperCase() === "#REQUIRED") {
                defaultValue = "#REQUIRED";
                i += 8;
            } else if (xmlData.substring(i, i + 7).toUpperCase() === "#IMPLIED") {
                defaultValue = "#IMPLIED";
                i += 7;
            } else {
                [i, defaultValue] = this.readIdentifierVal(xmlData, i, "ATTLIST");
            }

            return {
                elementName,
                attributeName,
                attributeType,
                defaultValue,
                index: i
            };
        }
    };

    // Helper functions
    const skipWhitespace = (data, index) => {
        while (index < data.length && /\s/.test(data[index])) {
            index++;
        }
        return index;
    };

    function hasSeq(data, seq, i) {
        for (let j = 0; j < seq.length; j++) {
            if (seq[j] !== data[i + j + 1]) return false;
        }
        return true;
    }

    function validateEntityName(name) {
        if (util$1.isName(name))
            return name;
        else
            throw new Error(`Invalid entity name ${name}`);
    }

    var DocTypeReader_1 = DocTypeReader$1;

    const hexRegex = /^[-+]?0x[a-fA-F0-9]+$/;
    const numRegex = /^([\-\+])?(0*)([0-9]*(\.[0-9]*)?)$/;
    // const octRegex = /^0x[a-z0-9]+/;
    // const binRegex = /0x[a-z0-9]+/;

     
    const consider = {
        hex :  true,
        // oct: false,
        leadingZeros: true,
        decimalPoint: "\.",
        eNotation: true,
        //skipLike: /regex/
    };

    function toNumber$1(str, options = {}){
        options = Object.assign({}, consider, options );
        if(!str || typeof str !== "string" ) return str;
        
        let trimmedStr  = str.trim();
        
        if(options.skipLike !== undefined && options.skipLike.test(trimmedStr)) return str;
        else if(str==="0") return 0;
        else if (options.hex && hexRegex.test(trimmedStr)) {
            return parse_int(trimmedStr, 16);
        // }else if (options.oct && octRegex.test(str)) {
        //     return Number.parseInt(val, 8);
        }else if (trimmedStr.search(/[eE]/)!== -1) { //eNotation
            const notation = trimmedStr.match(/^([-\+])?(0*)([0-9]*(\.[0-9]*)?[eE][-\+]?[0-9]+)$/); 
            // +00.123 => [ , '+', '00', '.123', ..
            if(notation){
                // console.log(notation)
                if(options.leadingZeros){ //accept with leading zeros
                    trimmedStr = (notation[1] || "") + notation[3];
                }else {
                    if(notation[2] === "0" && notation[3][0]=== ".");else {
                        return str;
                    }
                }
                return options.eNotation ? Number(trimmedStr) : str;
            }else {
                return str;
            }
        // }else if (options.parseBin && binRegex.test(str)) {
        //     return Number.parseInt(val, 2);
        }else {
            //separate negative sign, leading zeros, and rest number
            const match = numRegex.exec(trimmedStr);
            // +00.123 => [ , '+', '00', '.123', ..
            if(match){
                const sign = match[1];
                const leadingZeros = match[2];
                let numTrimmedByZeros = trimZeros(match[3]); //complete num without leading zeros
                //trim ending zeros for floating number
                
                if(!options.leadingZeros && leadingZeros.length > 0 && sign && trimmedStr[2] !== ".") return str; //-0123
                else if(!options.leadingZeros && leadingZeros.length > 0 && !sign && trimmedStr[1] !== ".") return str; //0123
                else if(options.leadingZeros && leadingZeros===str) return 0; //00
                
                else {//no leading zeros or leading zeros are allowed
                    const num = Number(trimmedStr);
                    const numStr = "" + num;

                    if(numStr.search(/[eE]/) !== -1){ //given number is long and parsed to eNotation
                        if(options.eNotation) return num;
                        else return str;
                    }else if(trimmedStr.indexOf(".") !== -1){ //floating number
                        if(numStr === "0" && (numTrimmedByZeros === "") ) return num; //0.0
                        else if(numStr === numTrimmedByZeros) return num; //0.456. 0.79000
                        else if( sign && numStr === "-"+numTrimmedByZeros) return num;
                        else return str;
                    }
                    
                    if(leadingZeros){
                        return (numTrimmedByZeros === numStr) || (sign+numTrimmedByZeros === numStr) ? num : str
                    }else  {
                        return (trimmedStr === numStr) || (trimmedStr === sign+numStr) ? num : str
                    }
                }
            }else { //non-numeric string
                return str;
            }
        }
    }

    /**
     * 
     * @param {string} numStr without leading zeros
     * @returns 
     */
    function trimZeros(numStr){
        if(numStr && numStr.indexOf(".") !== -1){//float
            numStr = numStr.replace(/0+$/, ""); //remove ending zeros
            if(numStr === ".")  numStr = "0";
            else if(numStr[0] === ".")  numStr = "0"+numStr;
            else if(numStr[numStr.length-1] === ".")  numStr = numStr.substr(0,numStr.length-1);
            return numStr;
        }
        return numStr;
    }

    function parse_int(numStr, base){
        //polyfill
        if(parseInt) return parseInt(numStr, base);
        else if(Number.parseInt) return Number.parseInt(numStr, base);
        else if(window && window.parseInt) return window.parseInt(numStr, base);
        else throw new Error("parseInt, Number.parseInt, window.parseInt are not supported")
    }

    var strnum = toNumber$1;

    function getIgnoreAttributesFn$1(ignoreAttributes) {
        if (typeof ignoreAttributes === 'function') {
            return ignoreAttributes
        }
        if (Array.isArray(ignoreAttributes)) {
            return (attrName) => {
                for (const pattern of ignoreAttributes) {
                    if (typeof pattern === 'string' && attrName === pattern) {
                        return true
                    }
                    if (pattern instanceof RegExp && pattern.test(attrName)) {
                        return true
                    }
                }
            }
        }
        return () => false
    }

    var ignoreAttributes = getIgnoreAttributesFn$1;

    ///@ts-check

    const util = util$3;
    const xmlNode = xmlNode$1;
    const DocTypeReader = DocTypeReader_1;
    const toNumber = strnum;
    const getIgnoreAttributesFn = ignoreAttributes;

    // const regx =
    //   '<((!\\[CDATA\\[([\\s\\S]*?)(]]>))|((NAME:)?(NAME))([^>]*)>|((\\/)(NAME)\\s*>))([^<]*)'
    //   .replace(/NAME/g, util.nameRegexp);

    //const tagsRegx = new RegExp("<(\\/?[\\w:\\-\._]+)([^>]*)>(\\s*"+cdataRegx+")*([^<]+)?","g");
    //const tagsRegx = new RegExp("<(\\/?)((\\w*:)?([\\w:\\-\._]+))([^>]*)>([^<]*)("+cdataRegx+"([^<]*))*([^<]+)?","g");

    let OrderedObjParser$1 = class OrderedObjParser {
      constructor(options) {
        this.options = options;
        this.currentNode = null;
        this.tagsNodeStack = [];
        this.docTypeEntities = {};
        this.lastEntities = {
          "apos": { regex: /&(apos|#39|#x27);/g, val: "'" },
          "gt": { regex: /&(gt|#62|#x3E);/g, val: ">" },
          "lt": { regex: /&(lt|#60|#x3C);/g, val: "<" },
          "quot": { regex: /&(quot|#34|#x22);/g, val: "\"" },
        };
        this.ampEntity = { regex: /&(amp|#38|#x26);/g, val: "&" };
        this.htmlEntities = {
          "space": { regex: /&(nbsp|#160);/g, val: " " },
          // "lt" : { regex: /&(lt|#60);/g, val: "<" },
          // "gt" : { regex: /&(gt|#62);/g, val: ">" },
          // "amp" : { regex: /&(amp|#38);/g, val: "&" },
          // "quot" : { regex: /&(quot|#34);/g, val: "\"" },
          // "apos" : { regex: /&(apos|#39);/g, val: "'" },
          "cent": { regex: /&(cent|#162);/g, val: "¢" },
          "pound": { regex: /&(pound|#163);/g, val: "£" },
          "yen": { regex: /&(yen|#165);/g, val: "¥" },
          "euro": { regex: /&(euro|#8364);/g, val: "€" },
          "copyright": { regex: /&(copy|#169);/g, val: "©" },
          "reg": { regex: /&(reg|#174);/g, val: "®" },
          "inr": { regex: /&(inr|#8377);/g, val: "₹" },
          "num_dec": { regex: /&#([0-9]{1,7});/g, val: (_, str) => fromCodePoint(str, 10, "&#") },
          "num_hex": { regex: /&#x([0-9a-fA-F]{1,6});/g, val: (_, str) => fromCodePoint(str, 16, "&#x") },
        };
        this.addExternalEntities = addExternalEntities;
        this.parseXml = parseXml$1;
        this.parseTextData = parseTextData;
        this.resolveNameSpace = resolveNameSpace;
        this.buildAttributesMap = buildAttributesMap;
        this.isItStopNode = isItStopNode;
        this.replaceEntitiesValue = replaceEntitiesValue;
        this.readStopNodeData = readStopNodeData;
        this.saveTextToParentTag = saveTextToParentTag;
        this.addChild = addChild;
        this.ignoreAttributesFn = getIgnoreAttributesFn(this.options.ignoreAttributes);
        this.entityExpansionCount = 0;
        this.currentExpandedLength = 0;

        if (this.options.stopNodes && this.options.stopNodes.length > 0) {
          this.stopNodesExact = new Set();
          this.stopNodesWildcard = new Set();
          for (let i = 0; i < this.options.stopNodes.length; i++) {
            const stopNodeExp = this.options.stopNodes[i];
            if (typeof stopNodeExp !== 'string') continue;
            if (stopNodeExp.startsWith("*.")) {
              this.stopNodesWildcard.add(stopNodeExp.substring(2));
            } else {
              this.stopNodesExact.add(stopNodeExp);
            }
          }
        }
      }

    };

    function addExternalEntities(externalEntities) {
      const entKeys = Object.keys(externalEntities);
      for (let i = 0; i < entKeys.length; i++) {
        const ent = entKeys[i];
        const escaped = ent.replace(/[.\-+*:]/g, '\\.');
        this.lastEntities[ent] = {
          regex: new RegExp("&" + escaped + ";", "g"),
          val: externalEntities[ent]
        };
      }
    }

    /**
     * @param {string} val
     * @param {string} tagName
     * @param {string} jPath
     * @param {boolean} dontTrim
     * @param {boolean} hasAttributes
     * @param {boolean} isLeafNode
     * @param {boolean} escapeEntities
     */
    function parseTextData(val, tagName, jPath, dontTrim, hasAttributes, isLeafNode, escapeEntities) {
      if (val !== undefined) {
        if (this.options.trimValues && !dontTrim) {
          val = val.trim();
        }
        if (val.length > 0) {
          if (!escapeEntities) val = this.replaceEntitiesValue(val, tagName, jPath);

          const newval = this.options.tagValueProcessor(tagName, val, jPath, hasAttributes, isLeafNode);
          if (newval === null || newval === undefined) {
            //don't parse
            return val;
          } else if (typeof newval !== typeof val || newval !== val) {
            //overwrite
            return newval;
          } else if (this.options.trimValues) {
            return parseValue(val, this.options.parseTagValue, this.options.numberParseOptions);
          } else {
            const trimmedVal = val.trim();
            if (trimmedVal === val) {
              return parseValue(val, this.options.parseTagValue, this.options.numberParseOptions);
            } else {
              return val;
            }
          }
        }
      }
    }

    function resolveNameSpace(tagname) {
      if (this.options.removeNSPrefix) {
        const tags = tagname.split(':');
        const prefix = tagname.charAt(0) === '/' ? '/' : '';
        if (tags[0] === 'xmlns') {
          return '';
        }
        if (tags.length === 2) {
          tagname = prefix + tags[1];
        }
      }
      return tagname;
    }

    //TODO: change regex to capture NS
    //const attrsRegx = new RegExp("([\\w\\-\\.\\:]+)\\s*=\\s*(['\"])((.|\n)*?)\\2","gm");
    const attrsRegx = new RegExp('([^\\s=]+)\\s*(=\\s*([\'"])([\\s\\S]*?)\\3)?', 'gm');

    function buildAttributesMap(attrStr, jPath, tagName) {
      if (this.options.ignoreAttributes !== true && typeof attrStr === 'string') {
        // attrStr = attrStr.replace(/\r?\n/g, ' ');
        //attrStr = attrStr || attrStr.trim();

        const matches = util.getAllMatches(attrStr, attrsRegx);
        const len = matches.length; //don't make it inline
        const attrs = {};
        for (let i = 0; i < len; i++) {
          const attrName = this.resolveNameSpace(matches[i][1]);
          if (this.ignoreAttributesFn(attrName, jPath)) {
            continue
          }
          let oldVal = matches[i][4];
          let aName = this.options.attributeNamePrefix + attrName;
          if (attrName.length) {
            if (this.options.transformAttributeName) {
              aName = this.options.transformAttributeName(aName);
            }
            aName = sanitizeName(aName, this.options);
            if (oldVal !== undefined) {
              if (this.options.trimValues) {
                oldVal = oldVal.trim();
              }
              oldVal = this.replaceEntitiesValue(oldVal, tagName, jPath);
              const newVal = this.options.attributeValueProcessor(attrName, oldVal, jPath);
              if (newVal === null || newVal === undefined) {
                //don't parse
                attrs[aName] = oldVal;
              } else if (typeof newVal !== typeof oldVal || newVal !== oldVal) {
                //overwrite
                attrs[aName] = newVal;
              } else {
                //parse
                attrs[aName] = parseValue(
                  oldVal,
                  this.options.parseAttributeValue,
                  this.options.numberParseOptions
                );
              }
            } else if (this.options.allowBooleanAttributes) {
              attrs[aName] = true;
            }
          }
        }
        if (!Object.keys(attrs).length) {
          return;
        }
        if (this.options.attributesGroupName) {
          const attrCollection = {};
          attrCollection[this.options.attributesGroupName] = attrs;
          return attrCollection;
        }
        return attrs
      }
    }

    const parseXml$1 = function (xmlData) {
      xmlData = xmlData.replace(/\r\n?/g, "\n"); //TODO: remove this line
      const xmlObj = new xmlNode('!xml');
      let currentNode = xmlObj;
      let textData = "";
      let jPath = "";

      // Reset entity expansion counters for this document
      this.entityExpansionCount = 0;
      this.currentExpandedLength = 0;

      const docTypeReader = new DocTypeReader(this.options.processEntities);
      for (let i = 0; i < xmlData.length; i++) {//for each char in XML data
        const ch = xmlData[i];
        if (ch === '<') {
          // const nextIndex = i+1;
          // const _2ndChar = xmlData[nextIndex];
          if (xmlData[i + 1] === '/') {//Closing Tag
            const closeIndex = findClosingIndex(xmlData, ">", i, "Closing Tag is not closed.");
            let tagName = xmlData.substring(i + 2, closeIndex).trim();

            if (this.options.removeNSPrefix) {
              const colonIndex = tagName.indexOf(":");
              if (colonIndex !== -1) {
                tagName = tagName.substr(colonIndex + 1);
              }
            }

            if (this.options.transformTagName) {
              tagName = this.options.transformTagName(tagName);
            }

            if (currentNode) {
              textData = this.saveTextToParentTag(textData, currentNode, jPath);
            }

            //check if last tag of nested tag was unpaired tag
            const lastTagName = jPath.substring(jPath.lastIndexOf(".") + 1);
            if (tagName && this.options.unpairedTags.indexOf(tagName) !== -1) {
              throw new Error(`Unpaired tag can not be used as closing tag: </${tagName}>`);
            }
            let propIndex = 0;
            if (lastTagName && this.options.unpairedTags.indexOf(lastTagName) !== -1) {
              propIndex = jPath.lastIndexOf('.', jPath.lastIndexOf('.') - 1);
              this.tagsNodeStack.pop();
            } else {
              propIndex = jPath.lastIndexOf(".");
            }
            jPath = jPath.substring(0, propIndex);

            currentNode = this.tagsNodeStack.pop();//avoid recursion, set the parent tag scope
            textData = "";
            i = closeIndex;
          } else if (xmlData[i + 1] === '?') {

            let tagData = readTagExp(xmlData, i, false, "?>");
            if (!tagData) throw new Error("Pi Tag is not closed.");

            textData = this.saveTextToParentTag(textData, currentNode, jPath);
            if ((this.options.ignoreDeclaration && tagData.tagName === "?xml") || this.options.ignorePiTags) ; else {

              const childNode = new xmlNode(tagData.tagName);
              childNode.add(this.options.textNodeName, "");

              if (tagData.tagName !== tagData.tagExp && tagData.attrExpPresent) {
                childNode[":@"] = this.buildAttributesMap(tagData.tagExp, jPath, tagData.tagName);
              }
              this.addChild(currentNode, childNode, jPath, i);
            }


            i = tagData.closeIndex + 1;
          } else if (xmlData.substr(i + 1, 3) === '!--') {
            const endIndex = findClosingIndex(xmlData, "-->", i + 4, "Comment is not closed.");
            if (this.options.commentPropName) {
              const comment = xmlData.substring(i + 4, endIndex - 2);

              textData = this.saveTextToParentTag(textData, currentNode, jPath);

              currentNode.add(this.options.commentPropName, [{ [this.options.textNodeName]: comment }]);
            }
            i = endIndex;
          } else if (xmlData.substr(i + 1, 2) === '!D') {
            const result = docTypeReader.readDocType(xmlData, i);
            this.docTypeEntities = result.entities;
            i = result.i;
          } else if (xmlData.substr(i + 1, 2) === '![') {
            const closeIndex = findClosingIndex(xmlData, "]]>", i, "CDATA is not closed.") - 2;
            const tagExp = xmlData.substring(i + 9, closeIndex);

            textData = this.saveTextToParentTag(textData, currentNode, jPath);

            let val = this.parseTextData(tagExp, currentNode.tagname, jPath, true, false, true, true);
            if (val == undefined) val = "";

            //cdata should be set even if it is 0 length string
            if (this.options.cdataPropName) {
              currentNode.add(this.options.cdataPropName, [{ [this.options.textNodeName]: tagExp }]);
            } else {
              currentNode.add(this.options.textNodeName, val);
            }

            i = closeIndex + 2;
          } else {//Opening tag
            let result = readTagExp(xmlData, i, this.options.removeNSPrefix);
            let tagName = result.tagName;
            const rawTagName = result.rawTagName;
            let tagExp = result.tagExp;
            let attrExpPresent = result.attrExpPresent;
            let closeIndex = result.closeIndex;

            if (this.options.transformTagName) {
              //console.log(tagExp, tagName)
              const newTagName = this.options.transformTagName(tagName);
              if (tagExp === tagName) {
                tagExp = newTagName;
              }
              tagName = newTagName;
            }

            if (this.options.strictReservedNames &&
              (tagName === this.options.commentPropName
                || tagName === this.options.cdataPropName
                || tagName === this.options.textNodeName
                || tagName === this.options.attributesGroupName
              )) {
              throw new Error(`Invalid tag name: ${tagName}`);
            }

            //save text as child node
            if (currentNode && textData) {
              if (currentNode.tagname !== '!xml') {
                //when nested tag is found
                textData = this.saveTextToParentTag(textData, currentNode, jPath, false);
              }
            }

            //check if last tag was unpaired tag
            const lastTag = currentNode;
            if (lastTag && this.options.unpairedTags.indexOf(lastTag.tagname) !== -1) {
              currentNode = this.tagsNodeStack.pop();
              jPath = jPath.substring(0, jPath.lastIndexOf("."));
            }
            if (tagName !== xmlObj.tagname) {
              jPath += jPath ? "." + tagName : tagName;
            }
            const startIndex = i;
            if (this.isItStopNode(this.stopNodesExact, this.stopNodesWildcard, jPath, tagName)) {
              let tagContent = "";
              //self-closing tag
              if (tagExp.length > 0 && tagExp.lastIndexOf("/") === tagExp.length - 1) {
                if (tagName[tagName.length - 1] === "/") { //remove trailing '/'
                  tagName = tagName.substr(0, tagName.length - 1);
                  jPath = jPath.substr(0, jPath.length - 1);
                  tagExp = tagName;
                } else {
                  tagExp = tagExp.substr(0, tagExp.length - 1);
                }
                i = result.closeIndex;
              }
              //unpaired tag
              else if (this.options.unpairedTags.indexOf(tagName) !== -1) {

                i = result.closeIndex;
              }
              //normal tag
              else {
                //read until closing tag is found
                const result = this.readStopNodeData(xmlData, rawTagName, closeIndex + 1);
                if (!result) throw new Error(`Unexpected end of ${rawTagName}`);
                i = result.i;
                tagContent = result.tagContent;
              }

              const childNode = new xmlNode(tagName);
              if (tagName !== tagExp && attrExpPresent) {
                childNode[":@"] = this.buildAttributesMap(tagExp, jPath, tagName);
              }
              if (tagContent) {
                tagContent = this.parseTextData(tagContent, tagName, jPath, true, attrExpPresent, true, true);
              }

              jPath = jPath.substr(0, jPath.lastIndexOf("."));
              childNode.add(this.options.textNodeName, tagContent);

              this.addChild(currentNode, childNode, jPath, startIndex);
            } else {
              //selfClosing tag
              if (tagExp.length > 0 && tagExp.lastIndexOf("/") === tagExp.length - 1) {
                if (tagName[tagName.length - 1] === "/") { //remove trailing '/'
                  tagName = tagName.substr(0, tagName.length - 1);
                  jPath = jPath.substr(0, jPath.length - 1);
                  tagExp = tagName;
                } else {
                  tagExp = tagExp.substr(0, tagExp.length - 1);
                }

                if (this.options.transformTagName) {
                  const newTagName = this.options.transformTagName(tagName);
                  if (tagExp === tagName) {
                    tagExp = newTagName;
                  }
                  tagName = newTagName;
                }

                const childNode = new xmlNode(tagName);
                if (tagName !== tagExp && attrExpPresent) {
                  childNode[":@"] = this.buildAttributesMap(tagExp, jPath, tagName);
                }
                this.addChild(currentNode, childNode, jPath, startIndex);
                jPath = jPath.substr(0, jPath.lastIndexOf("."));
              }
              else if (this.options.unpairedTags.indexOf(tagName) !== -1) {//unpaired tag
                const childNode = new xmlNode(tagName);
                if (tagName !== tagExp && attrExpPresent) {
                  childNode[":@"] = this.buildAttributesMap(tagExp, jPath);
                }
                this.addChild(currentNode, childNode, jPath, startIndex);
                jPath = jPath.substr(0, jPath.lastIndexOf("."));
                i = result.closeIndex;
                // Continue to next iteration without changing currentNode
                continue;
              }
              //opening tag
              else {
                const childNode = new xmlNode(tagName);
                if (this.tagsNodeStack.length > this.options.maxNestedTags) {
                  throw new Error("Maximum nested tags exceeded");
                }
                this.tagsNodeStack.push(currentNode);

                if (tagName !== tagExp && attrExpPresent) {
                  childNode[":@"] = this.buildAttributesMap(tagExp, jPath, tagName);
                }
                this.addChild(currentNode, childNode, jPath);
                currentNode = childNode;
              }
              textData = "";
              i = closeIndex;
            }
          }
        } else {
          textData += xmlData[i];
        }
      }
      return xmlObj.child;
    };

    function addChild(currentNode, childNode, jPath, startIndex) {
      // unset startIndex if not requested
      if (!this.options.captureMetaData) startIndex = undefined;
      const result = this.options.updateTag(childNode.tagname, jPath, childNode[":@"]);
      if (result === false) ; else if (typeof result === "string") {
        childNode.tagname = result;
        currentNode.addChild(childNode, startIndex);
      } else {
        currentNode.addChild(childNode, startIndex);
      }
    }

    const replaceEntitiesValue = function (val, tagName, jPath) {
      // Performance optimization: Early return if no entities to replace
      if (val.indexOf('&') === -1) {
        return val;
      }

      const entityConfig = this.options.processEntities;

      if (!entityConfig.enabled) {
        return val;
      }

      // Check tag-specific filtering
      if (entityConfig.allowedTags) {
        if (!entityConfig.allowedTags.includes(tagName)) {
          return val; // Skip entity replacement for current tag as not set
        }
      }

      if (entityConfig.tagFilter) {
        if (!entityConfig.tagFilter(tagName, jPath)) {
          return val; // Skip based on custom filter
        }
      }

      // Replace DOCTYPE entities
      for (let entityName in this.docTypeEntities) {
        const entity = this.docTypeEntities[entityName];
        const matches = val.match(entity.regx);

        if (matches) {
          // Track expansions
          this.entityExpansionCount += matches.length;

          // Check expansion limit
          if (entityConfig.maxTotalExpansions &&
            this.entityExpansionCount > entityConfig.maxTotalExpansions) {
            throw new Error(
              `Entity expansion limit exceeded: ${this.entityExpansionCount} > ${entityConfig.maxTotalExpansions}`
            );
          }

          // Store length before replacement
          const lengthBefore = val.length;
          val = val.replace(entity.regx, entity.val);

          // Check expanded length immediately after replacement
          if (entityConfig.maxExpandedLength) {
            this.currentExpandedLength += (val.length - lengthBefore);

            if (this.currentExpandedLength > entityConfig.maxExpandedLength) {
              throw new Error(
                `Total expanded content size exceeded: ${this.currentExpandedLength} > ${entityConfig.maxExpandedLength}`
              );
            }
          }
        }
      }
      if (val.indexOf('&') === -1) return val;  // Early exit

      // Replace standard entities
      for (const entityName of Object.keys(this.lastEntities)) {
        const entity = this.lastEntities[entityName];
        const matches = val.match(entity.regex);
        if (matches) {
          this.entityExpansionCount += matches.length;
          if (entityConfig.maxTotalExpansions &&
            this.entityExpansionCount > entityConfig.maxTotalExpansions) {
            throw new Error(
              `Entity expansion limit exceeded: ${this.entityExpansionCount} > ${entityConfig.maxTotalExpansions}`
            );
          }
        }
        val = val.replace(entity.regex, entity.val);
      }
      if (val.indexOf('&') === -1) return val;  // Early exit

      // Replace HTML entities if enabled
      if (this.options.htmlEntities) {
        for (const entityName of Object.keys(this.htmlEntities)) {
          const entity = this.htmlEntities[entityName];
          const matches = val.match(entity.regex);
          if (matches) {
            //console.log(matches);
            this.entityExpansionCount += matches.length;
            if (entityConfig.maxTotalExpansions &&
              this.entityExpansionCount > entityConfig.maxTotalExpansions) {
              throw new Error(
                `Entity expansion limit exceeded: ${this.entityExpansionCount} > ${entityConfig.maxTotalExpansions}`
              );
            }
          }
          val = val.replace(entity.regex, entity.val);
        }
      }

      // Replace ampersand entity last
      val = val.replace(this.ampEntity.regex, this.ampEntity.val);

      return val;
    };

    function saveTextToParentTag(textData, parentNode, jPath, isLeafNode) {
      if (textData) { //store previously collected data as textNode
        if (isLeafNode === undefined) isLeafNode = parentNode.child.length === 0;

        textData = this.parseTextData(textData,
          parentNode.tagname,
          jPath,
          false,
          parentNode[":@"] ? Object.keys(parentNode[":@"]).length !== 0 : false,
          isLeafNode);

        if (textData !== undefined && textData !== "")
          parentNode.add(this.options.textNodeName, textData);
        textData = "";
      }
      return textData;
    }

    //TODO: use jPath to simplify the logic
    /**
     * @param {Set} stopNodesExact
     * @param {Set} stopNodesWildcard
     * @param {string} jPath
     * @param {string} currentTagName
     */
    function isItStopNode(stopNodesExact, stopNodesWildcard, jPath, currentTagName) {
      if (stopNodesWildcard && stopNodesWildcard.has(currentTagName)) return true;
      if (stopNodesExact && stopNodesExact.has(jPath)) return true;
      return false;
    }

    /**
     * Returns the tag Expression and where it is ending handling single-double quotes situation
     * @param {string} xmlData 
     * @param {number} i starting index
     * @returns 
     */
    function tagExpWithClosingIndex(xmlData, i, closingChar = ">") {
      let attrBoundary;
      let tagExp = "";
      for (let index = i; index < xmlData.length; index++) {
        let ch = xmlData[index];
        if (attrBoundary) {
          if (ch === attrBoundary) attrBoundary = "";//reset
        } else if (ch === '"' || ch === "'") {
          attrBoundary = ch;
        } else if (ch === closingChar[0]) {
          if (closingChar[1]) {
            if (xmlData[index + 1] === closingChar[1]) {
              return {
                data: tagExp,
                index: index
              }
            }
          } else {
            return {
              data: tagExp,
              index: index
            }
          }
        } else if (ch === '\t') {
          ch = " ";
        }
        tagExp += ch;
      }
    }

    function findClosingIndex(xmlData, str, i, errMsg) {
      const closingIndex = xmlData.indexOf(str, i);
      if (closingIndex === -1) {
        throw new Error(errMsg)
      } else {
        return closingIndex + str.length - 1;
      }
    }

    function readTagExp(xmlData, i, removeNSPrefix, closingChar = ">") {
      const result = tagExpWithClosingIndex(xmlData, i + 1, closingChar);
      if (!result) return;
      let tagExp = result.data;
      const closeIndex = result.index;
      const separatorIndex = tagExp.search(/\s/);
      let tagName = tagExp;
      let attrExpPresent = true;
      if (separatorIndex !== -1) {//separate tag name and attributes expression
        tagName = tagExp.substring(0, separatorIndex);
        tagExp = tagExp.substring(separatorIndex + 1).trimStart();
      }

      const rawTagName = tagName;
      if (removeNSPrefix) {
        const colonIndex = tagName.indexOf(":");
        if (colonIndex !== -1) {
          tagName = tagName.substr(colonIndex + 1);
          attrExpPresent = tagName !== result.data.substr(colonIndex + 1);
        }
      }

      return {
        tagName: tagName,
        tagExp: tagExp,
        closeIndex: closeIndex,
        attrExpPresent: attrExpPresent,
        rawTagName: rawTagName,
      }
    }
    /**
     * find paired tag for a stop node
     * @param {string} xmlData 
     * @param {string} tagName 
     * @param {number} i 
     */
    function readStopNodeData(xmlData, tagName, i) {
      const startIndex = i;
      // Starting at 1 since we already have an open tag
      let openTagCount = 1;

      for (; i < xmlData.length; i++) {
        if (xmlData[i] === "<") {
          if (xmlData[i + 1] === "/") {//close tag
            const closeIndex = findClosingIndex(xmlData, ">", i, `${tagName} is not closed`);
            let closeTagName = xmlData.substring(i + 2, closeIndex).trim();
            if (closeTagName === tagName) {
              openTagCount--;
              if (openTagCount === 0) {
                return {
                  tagContent: xmlData.substring(startIndex, i),
                  i: closeIndex
                }
              }
            }
            i = closeIndex;
          } else if (xmlData[i + 1] === '?') {
            const closeIndex = findClosingIndex(xmlData, "?>", i + 1, "StopNode is not closed.");
            i = closeIndex;
          } else if (xmlData.substr(i + 1, 3) === '!--') {
            const closeIndex = findClosingIndex(xmlData, "-->", i + 3, "StopNode is not closed.");
            i = closeIndex;
          } else if (xmlData.substr(i + 1, 2) === '![') {
            const closeIndex = findClosingIndex(xmlData, "]]>", i, "StopNode is not closed.") - 2;
            i = closeIndex;
          } else {
            const tagData = readTagExp(xmlData, i, '>');

            if (tagData) {
              const openTagName = tagData && tagData.tagName;
              if (openTagName === tagName && tagData.tagExp[tagData.tagExp.length - 1] !== "/") {
                openTagCount++;
              }
              i = tagData.closeIndex;
            }
          }
        }
      }//end for loop
    }

    function parseValue(val, shouldParse, options) {
      if (shouldParse && typeof val === 'string') {
        //console.log(options)
        const newval = val.trim();
        if (newval === 'true') return true;
        else if (newval === 'false') return false;
        else return toNumber(val, options);
      } else {
        if (util.isExist(val)) {
          return val;
        } else {
          return '';
        }
      }
    }

    function fromCodePoint(str, base, prefix) {
      const codePoint = Number.parseInt(str, base);

      if (codePoint >= 0 && codePoint <= 0x10FFFF) {
        return String.fromCodePoint(codePoint);
      } else {
        return prefix + str + ";";
      }
    }

    function sanitizeName(name, options) {
      if (util.criticalProperties.includes(name)) {
        throw new Error(`[SECURITY] Invalid name: "${name}" is a reserved JavaScript keyword that could cause prototype pollution`);
      } else if (util.DANGEROUS_PROPERTY_NAMES.includes(name)) {
        return options.onDangerousProperty(name);
      }
      return name;
    }

    var OrderedObjParser_1 = OrderedObjParser$1;

    var node2json = {};

    /**
     * 
     * @param {array} node 
     * @param {any} options 
     * @returns 
     */
    function prettify$1(node, options){
      return compress( node, options);
    }

    /**
     * 
     * @param {array} arr 
     * @param {object} options 
     * @param {string} jPath 
     * @returns object
     */
    function compress(arr, options, jPath){
      let text;
      const compressedObj = {};
      for (let i = 0; i < arr.length; i++) {
        const tagObj = arr[i];
        const property = propName(tagObj);
        let newJpath = "";
        if(jPath === undefined) newJpath = property;
        else newJpath = jPath + "." + property;

        if(property === options.textNodeName){
          if(text === undefined) text = tagObj[property];
          else text += "" + tagObj[property];
        }else if(property === undefined){
          continue;
        }else if(tagObj[property]){
          
          let val = compress(tagObj[property], options, newJpath);
          const isLeaf = isLeafTag(val, options);

          if(tagObj[":@"]){
            assignAttributes( val, tagObj[":@"], newJpath, options);
          }else if(Object.keys(val).length === 1 && val[options.textNodeName] !== undefined && !options.alwaysCreateTextNode){
            val = val[options.textNodeName];
          }else if(Object.keys(val).length === 0){
            if(options.alwaysCreateTextNode) val[options.textNodeName] = "";
            else val = "";
          }

          if(compressedObj[property] !== undefined && compressedObj.hasOwnProperty(property)) {
            if(!Array.isArray(compressedObj[property])) {
                compressedObj[property] = [ compressedObj[property] ];
            }
            compressedObj[property].push(val);
          }else {
            //TODO: if a node is not an array, then check if it should be an array
            //also determine if it is a leaf node
            if (options.isArray(property, newJpath, isLeaf )) {
              compressedObj[property] = [val];
            }else {
              compressedObj[property] = val;
            }
          }
        }
        
      }
      // if(text && text.length > 0) compressedObj[options.textNodeName] = text;
      if(typeof text === "string"){
        if(text.length > 0) compressedObj[options.textNodeName] = text;
      }else if(text !== undefined) compressedObj[options.textNodeName] = text;
      return compressedObj;
    }

    function propName(obj){
      const keys = Object.keys(obj);
      for (let i = 0; i < keys.length; i++) {
        const key = keys[i];
        if(key !== ":@") return key;
      }
    }

    function assignAttributes(obj, attrMap, jpath, options){
      if (attrMap) {
        const keys = Object.keys(attrMap);
        const len = keys.length; //don't make it inline
        for (let i = 0; i < len; i++) {
          const atrrName = keys[i];
          if (options.isArray(atrrName, jpath + "." + atrrName, true, true)) {
            obj[atrrName] = [ attrMap[atrrName] ];
          } else {
            obj[atrrName] = attrMap[atrrName];
          }
        }
      }
    }

    function isLeafTag(obj, options){
      const { textNodeName } = options;
      const propCount = Object.keys(obj).length;
      
      if (propCount === 0) {
        return true;
      }

      if (
        propCount === 1 &&
        (obj[textNodeName] || typeof obj[textNodeName] === "boolean" || obj[textNodeName] === 0)
      ) {
        return true;
      }

      return false;
    }
    node2json.prettify = prettify$1;

    const { buildOptions} = OptionsBuilder;
    const OrderedObjParser = OrderedObjParser_1;
    const { prettify} = node2json;
    const validator = validator$1;

    let XMLParser$1 = class XMLParser{
        
        constructor(options){
            this.externalEntities = {};
            this.options = buildOptions(options);
            
        }
        /**
         * Parse XML dats to JS object 
         * @param {string|Buffer} xmlData 
         * @param {boolean|Object} validationOption 
         */
        parse(xmlData,validationOption){
            if(typeof xmlData === "string");else if( xmlData.toString){
                xmlData = xmlData.toString();
            }else {
                throw new Error("XML data is accepted in String or Bytes[] form.")
            }
            if( validationOption){
                if(validationOption === true) validationOption = {}; //validate with default options
                
                const result = validator.validate(xmlData, validationOption);
                if (result !== true) {
                  throw Error( `${result.err.msg}:${result.err.line}:${result.err.col}` )
                }
              }
            const orderedObjParser = new OrderedObjParser(this.options);
            orderedObjParser.addExternalEntities(this.externalEntities);
            const orderedResult = orderedObjParser.parseXml(xmlData);
            if(this.options.preserveOrder || orderedResult === undefined) return orderedResult;
            else return prettify(orderedResult, this.options);
        }

        /**
         * Add Entity which is not by default supported by this library
         * @param {string} key 
         * @param {string} value 
         */
        addEntity(key, value){
            if(value.indexOf("&") !== -1){
                throw new Error("Entity value can't have '&'")
            }else if(key.indexOf("&") !== -1 || key.indexOf(";") !== -1){
                throw new Error("An entity must be set without '&' and ';'. Eg. use '#xD' for '&#xD;'")
            }else if(value === "&"){
                throw new Error("An entity with value '&' is not permitted");
            }else {
                this.externalEntities[key] = value;
            }
        }
    };

    var XMLParser_1 = XMLParser$1;

    const XMLParser = XMLParser_1;

    var fxp = {
      XMLParser: XMLParser};

    // xml_util.ts — OOXML XML 解析共用工具
    //
    // 全 parser 共用一份 fast-xml-parser 設定與 helper，避免各檔重複。
    const ATTR_PREFIX = '@_';
    const TEXT_NODE = '#text';
    const parser = new fxp.XMLParser({
        ignoreAttributes: false,
        attributeNamePrefix: ATTR_PREFIX,
        textNodeName: TEXT_NODE,
        parseAttributeValue: false, // 屬性一律當字串，由各 parser 自行轉型
        parseTagValue: false, // 文字節點保留原字串（避免 "1.1.1" 被當數字）
        trimValues: false, // 保留空白（sharedStrings xml:space="preserve" 需要）
    });
    /** 解析 XML 字串成物件樹（保留命名空間前綴，如 r:id）。*/
    function parseXml(text) {
        return parser.parse(text);
    }
    // theme1.xml 全程 a: 前綴；去前綴後存取較乾淨（dk1/srgbClr 而非 a:dk1）。
    const parserNoNs = new fxp.XMLParser({
        ignoreAttributes: false,
        attributeNamePrefix: ATTR_PREFIX,
        textNodeName: TEXT_NODE,
        parseAttributeValue: false,
        parseTagValue: false,
        trimValues: false,
        removeNSPrefix: true,
    });
    /** 解析 XML 字串並移除命名空間前綴（給 DrawingML theme 用，勿用於 r:id 相關）。*/
    function parseXmlNoNs(text) {
        return parserNoNs.parse(text);
    }
    /** fast-xml-parser 對單一/多個同名節點回傳 object/array 不一致，統一轉陣列。*/
    function toArray(node) {
        if (node === undefined || node === null)
            return [];
        return Array.isArray(node) ? node : [node];
    }
    /** 讀屬性字串（自動補 ATTR_PREFIX）；無回 undefined。*/
    function attr(obj, name) {
        if (obj === null || typeof obj !== 'object')
            return undefined;
        const v = obj[ATTR_PREFIX + name];
        return v === undefined || v === null ? undefined : String(v);
    }
    /** 讀屬性並轉整數；無或非數字回 undefined。*/
    function intAttr(obj, name) {
        const s = attr(obj, name);
        if (s === undefined)
            return undefined;
        const n = Number.parseInt(s, 10);
        return Number.isNaN(n) ? undefined : n;
    }
    /** 讀屬性並轉布林（"1"/"true" → true）。預設 false。*/
    function boolAttr(obj, name) {
        const s = attr(obj, name);
        return s === '1' || s === 'true';
    }
    /** 取文字節點內容。*/
    function textOf(obj) {
        if (obj === null || obj === undefined)
            return '';
        if (typeof obj === 'string')
            return obj;
        if (typeof obj === 'object') {
            const v = obj[TEXT_NODE];
            return v === undefined || v === null ? '' : String(v);
        }
        return String(obj);
    }
    /**
     * 解碼 OOXML 的 `_xHHHH_` 控制字元跳脫（ECMA-376 §22.4.2.4）。
     * 例：`_x000D_` → CR。單次左到右掃描即可正確處理 `_x005F_`（跳脫的底線）：
     *   `_x005F_x000D_`（字面 "_x000D_"）→ 先還原 `_x005F_`→`_`，剩 `x000D_` 不再被吃，得字面 `_x000D_`。
     */
    function decodeOoxmlEscapes(s) {
        if (s.indexOf('_x') === -1)
            return s;
        return s.replace(/_x([0-9A-Fa-f]{4})_/g, (_m, hex) => String.fromCharCode(Number.parseInt(hex, 16)));
    }

    // package_reader.ts — OPC（Open Packaging Conventions）容器讀取（規劃書 §1.1）
    //
    // xlsx = 一個 zip（OPC package），內含多個 part：
    //   [Content_Types].xml      每個 part 的 MIME type（Default by extension + Override by name）
    //   _rels/.rels              package 層級關聯（根 → xl/workbook.xml）
    //   xl/workbook.xml          活頁簿主檔
    //   xl/_rels/workbook.xml.rels   workbook → 各 worksheet / sharedStrings / styles 的關聯
    //   xl/worksheets/sheetN.xml ...
    //
    // 本層只負責：解 zip、取 part bytes/text、解析 Content_Types、解析 .rels（含相對路徑解析）。
    // 不解析任何試算表語意（那是 §1.3+ 各 parser 的工作）。
    const CONTENT_TYPES_PART = '[Content_Types].xml';
    /** 正規化 part 名稱：去前導斜線，作為 zip entry key。*/
    function normalizePart(name) {
        return name.replace(/^\/+/, '');
    }
    /**
     * 解析相對 target：以 sourcePart 所在目錄為基準，支援 `../`。
     * 例：source = 'xl/workbook.xml'、target = 'worksheets/sheet1.xml'
     *     → 'xl/worksheets/sheet1.xml'
     * 例：source = 'xl/worksheets/sheet1.xml'、target = '../sharedStrings.xml'
     *     → 'xl/sharedStrings.xml'
     */
    function resolveRelativeTarget(sourcePart, target) {
        if (target.startsWith('/'))
            return normalizePart(target); // package 絕對路徑
        const baseDir = sourcePart.includes('/') ? sourcePart.replace(/\/[^/]*$/, '') : '';
        const stack = baseDir ? baseDir.split('/') : [];
        for (const seg of target.split('/')) {
            if (seg === '' || seg === '.')
                continue;
            if (seg === '..')
                stack.pop();
            else
                stack.push(seg);
        }
        return stack.join('/');
    }
    class PackageReader {
        constructor(parts) {
            this.contentTypesCache = null;
            this.relsCache = new Map();
            this.parts = parts;
        }
        /** 從 xlsx 二進位（ArrayBuffer 或 Uint8Array）建立 reader。*/
        static fromBuffer(buffer) {
            const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
            const parts = unzipSync(bytes);
            if (!(CONTENT_TYPES_PART in parts)) {
                throw new Error(`Invalid xlsx: missing ${CONTENT_TYPES_PART}`);
            }
            return new PackageReader(parts);
        }
        /** 列出所有 part 名稱（zip entry，無前導斜線）。*/
        listParts() {
            return Object.keys(this.parts);
        }
        hasPart(name) {
            return normalizePart(name) in this.parts;
        }
        /** 取 part 原始 bytes；不存在回 undefined。*/
        getPart(name) {
            return this.parts[normalizePart(name)];
        }
        /** 取 part 並 UTF-8 解碼成字串；不存在則丟錯。*/
        getPartText(name) {
            const bytes = this.getPart(name);
            if (bytes === undefined)
                throw new Error(`Part not found: ${name}`);
            return strFromU8(bytes);
        }
        buildContentTypesIndex() {
            const xml = parseXml(this.getPartText(CONTENT_TYPES_PART));
            const types = (xml['Types'] ?? {});
            const defaults = new Map();
            const overrides = new Map();
            for (const d of toArray(types['Default'])) {
                const ext = attr(d, 'Extension');
                const ct = attr(d, 'ContentType');
                if (ext && ct)
                    defaults.set(ext.toLowerCase(), ct);
            }
            for (const o of toArray(types['Override'])) {
                const part = attr(o, 'PartName');
                const ct = attr(o, 'ContentType');
                if (part && ct)
                    overrides.set(part, ct);
            }
            return { defaults, overrides };
        }
        /**
         * 取得 part 的 content type：Override（依完整 part 名）優先，否則 Default（依副檔名）。
         * 查無回 undefined。
         */
        getContentType(name) {
            if (this.contentTypesCache === null) {
                this.contentTypesCache = this.buildContentTypesIndex();
            }
            const withSlash = '/' + normalizePart(name);
            const override = this.contentTypesCache.overrides.get(withSlash);
            if (override)
                return override;
            const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : '';
            return this.contentTypesCache.defaults.get(ext);
        }
        /**
         * 取得某 part 的關聯清單。對 part `dir/name.xml` 讀 `dir/_rels/name.xml.rels`。
         * 傳入空字串或 '/' 取 package 根關聯（`_rels/.rels`）。查無回空陣列。
         */
        getRels(partName) {
            const part = normalizePart(partName);
            const cached = this.relsCache.get(part);
            if (cached)
                return cached;
            const slash = part.lastIndexOf('/');
            const dir = slash >= 0 ? part.slice(0, slash) : '';
            const file = slash >= 0 ? part.slice(slash + 1) : part;
            const relsPath = (dir ? dir + '/' : '') + '_rels/' + file + '.rels';
            const rels = [];
            if (this.hasPart(relsPath)) {
                const xml = parseXml(this.getPartText(relsPath));
                const container = (xml['Relationships'] ?? {});
                for (const r of toArray(container['Relationship'])) {
                    const target = attr(r, 'Target') ?? '';
                    const mode = attr(r, 'TargetMode') === 'External' ? 'External' : 'Internal';
                    rels.push({
                        id: attr(r, 'Id') ?? '',
                        type: attr(r, 'Type') ?? '',
                        target,
                        targetMode: mode,
                        resolvedTarget: mode === 'External' ? target : resolveRelativeTarget(part, target),
                    });
                }
            }
            this.relsCache.set(part, rels);
            return rels;
        }
        /** 取得 package 根關聯（`_rels/.rels`）的捷徑。*/
        getRootRels() {
            return this.getRels('');
        }
    }

    // units.ts — OOXML SpreadsheetML 單位系統（規劃書 §1.2）
    //
    // xlsx 內混用多種長度單位，渲染前需統一轉成 pixel：
    //   - EMU（English Metric Unit）：DrawingML 圖形/圖片座標，1 inch = 914400 EMU
    //   - point（pt）：字級、列高，1 inch = 72 pt
    //   - pixel（px）：螢幕渲染基準，預設 96 DPI
    //   - column-width units：Excel 特殊單位 =「以最大數字字元寬度為基準的字元數」
    //
    // 參考：ECMA-376 Part 1 §18.3.1.13（col width）、§22.1.2（EMU）
    // ── 不可變常數（紀律：禁止 magic number）──────────────────────────────
    const EMU_PER_INCH = 914400;
    const POINTS_PER_INCH = 72;
    const EMU_PER_POINT = EMU_PER_INCH / POINTS_PER_INCH; // 12700
    const DEFAULT_DPI = 96;
    /**
     * Calibri 11pt @ 96 DPI 的「最大數字字元寬度」(Maximum Digit Width, MDW)。
     * Excel 預設字型下 MDW = 7px，column width 的字元單位以此為基準。
     * 不同預設字型 MDW 不同（Arial 10 = 7、Calibri 11 = 7），故開放為參數。
     */
    const DEFAULT_MDW = 7;
    /** Excel column width 字元數 → pixel 的固定 padding（左右邊距），單位 px。*/
    const COL_WIDTH_PADDING_PX = 5;
    // ── point ↔ pixel ────────────────────────────────────────────────────
    function pointsToPixels(pt, dpi = DEFAULT_DPI) {
        return (pt * dpi) / POINTS_PER_INCH;
    }
    function pixelsToPoints(px, dpi = DEFAULT_DPI) {
        return (px * POINTS_PER_INCH) / dpi;
    }
    // ── EMU ↔ pixel ──────────────────────────────────────────────────────
    function emuToPixels(emu, dpi = DEFAULT_DPI) {
        return (emu * dpi) / EMU_PER_INCH;
    }
    function pixelsToEmu(px, dpi = DEFAULT_DPI) {
        return Math.round((px * EMU_PER_INCH) / dpi);
    }
    // ── EMU ↔ point ──────────────────────────────────────────────────────
    function emuToPoints(emu) {
        return emu / EMU_PER_POINT;
    }
    function pointsToEmu(pt) {
        return Math.round(pt * EMU_PER_POINT);
    }
    // ── 列高（row ht 屬性 = point）↔ pixel ────────────────────────────────
    // 注意：規劃書 §1.2 寫「half-points」，但 ECMA-376 §18.3.1.73 明定 row@ht 單位為
    // point（半點是 WordprocessingML 的慣例）。此處依規格以 point 處理。
    function rowHeightToPixels(ht, dpi = DEFAULT_DPI) {
        return pointsToPixels(ht, dpi);
    }
    // ── 欄寬（col width 屬性 = 字元數）↔ pixel ────────────────────────────
    /**
     * 儲存的 column width（字元數）→ pixel。
     * ECMA-376 §18.3.1.13 note 反算式：
     *   pixels = Truncate( ( (256 * width + Truncate(128 / MDW)) / 256 ) * MDW )
     */
    function columnWidthToPixels(width, mdw = DEFAULT_MDW) {
        return Math.trunc(((256 * width + Math.trunc(128 / mdw)) / 256) * mdw);
    }
    /**
     * pixel → 儲存的 column width（字元數），為 columnWidthToPixels 的近似反函式。
     * 用於 Phase 6 匯出對稱性。
     */
    function pixelsToColumnWidth(px, mdw = DEFAULT_MDW) {
        return Math.trunc(((px - COL_WIDTH_PADDING_PX) / mdw) * 100 + 0.5) / 100;
    }

    // workbook_parser.ts — 解析 xl/workbook.xml（規劃書 §1.3）
    //
    // 產出活頁簿層級結構：sheet 清單（含隱藏狀態與對應 worksheet part）、
    // definedNames（含 _xlnm 保留名）、workbookView（啟用 tab）、calcPr（refMode）。
    // sheet 的 r:id 透過 workbook 的 .rels 解析成實際 worksheet part 路徑。
    const REL_SHARED_STRINGS = '/sharedStrings';
    const REL_STYLES = '/styles';
    const REL_THEME = '/theme';
    const REL_OFFICE_DOCUMENT = '/officeDocument';
    const RESERVED_NAME_PREFIX = '_xlnm.';
    function toSheetState(raw) {
        return raw === 'hidden' || raw === 'veryHidden' ? raw : 'visible';
    }
    class WorkbookParser {
        constructor(pkg) {
            this.pkg = pkg;
        }
        /** 取 workbook part 路徑（root officeDocument 關聯）。查無丟錯。*/
        workbookPart() {
            const office = this.pkg
                .getRootRels()
                .find((r) => r.type.endsWith(REL_OFFICE_DOCUMENT));
            if (!office)
                throw new Error('workbook.xml not found: missing officeDocument relationship');
            return office.resolvedTarget;
        }
        /** rId → resolvedTarget 對照（workbook 層級關聯）。*/
        relMap() {
            const map = new Map();
            for (const r of this.pkg.getRels(this.workbookPart())) {
                map.set(r.id, r.resolvedTarget);
            }
            return map;
        }
        parse() {
            const xml = parseXml(this.pkg.getPartText(this.workbookPart()));
            const wb = (xml['workbook'] ?? {});
            const relMap = this.relMap();
            // ── sheets ──
            const sheetsContainer = (wb['sheets'] ?? {});
            const sheets = toArray(sheetsContainer['sheet']).map((s) => {
                const rId = attr(s, 'r:id') ?? '';
                return {
                    name: attr(s, 'name') ?? '',
                    sheetId: intAttr(s, 'sheetId') ?? 0,
                    rId,
                    state: toSheetState(attr(s, 'state')),
                    target: relMap.get(rId),
                };
            });
            // ── definedNames ──
            const dnContainer = (wb['definedNames'] ?? {});
            const definedNames = toArray(dnContainer['definedName']).map((d) => {
                const name = attr(d, 'name') ?? '';
                return {
                    name,
                    localSheetId: intAttr(d, 'localSheetId'),
                    hidden: boolAttr(d, 'hidden'),
                    formula: textOf(d),
                    reserved: name.startsWith(RESERVED_NAME_PREFIX),
                };
            });
            // ── workbookView（取第一個 bookView）──
            const bookViews = (wb['bookViews'] ?? {});
            const firstView = toArray(bookViews['workbookView'])[0];
            const view = {
                activeTab: intAttr(firstView, 'activeTab') ?? 0,
                firstSheet: intAttr(firstView, 'firstSheet') ?? 0,
            };
            // ── calcPr ──
            const calcPr = wb['calcPr'];
            const calc = {
                refMode: attr(calcPr, 'refMode') === 'R1C1' ? 'R1C1' : 'A1',
                iterate: boolAttr(calcPr, 'iterate'),
            };
            return { sheets, definedNames, view, calc };
        }
        // ── 相關 part 解析（供後續 sprint 使用）─────────────────────────────
        partByRelType(suffix) {
            return this.pkg
                .getRels(this.workbookPart())
                .find((r) => r.type.endsWith(suffix))?.resolvedTarget;
        }
        /** worksheet part 路徑清單（依 workbook sheets 順序）。*/
        worksheetParts() {
            return this.parse()
                .sheets.map((s) => s.target)
                .filter((t) => t !== undefined);
        }
        sharedStringsPart() {
            return this.partByRelType(REL_SHARED_STRINGS);
        }
        stylesPart() {
            return this.partByRelType(REL_STYLES);
        }
        themePart() {
            return this.partByRelType(REL_THEME);
        }
    }

    // shared_strings_parser.ts — 解析 xl/sharedStrings.xml（規劃書 §1.4）
    //
    // sst 是字串池，worksheet cell（t="s"）以索引引用。每個 <si> 可能是：
    //   純文字：  <si><t>text</t></si>
    //   空字串：  <si><t/></si>
    //   保留空白：<si><t xml:space="preserve"> a </t></si>
    //   rich text：<si><r><t>..</t></r><r><rPr>..</rPr><t>..</t></r></si>（多 run、各有字型樣式）
    //
    // 本層攤平出純文字（text，供 cell value 提取），並保留 rich run 結構（runs，Phase 2 套樣式用）。
    // 同時解碼 OOXML 的 _xHHHH_ 控制字元跳脫。
    /** 判斷 rPr 旗標型子元素（如 <b/>、<b val="0"/>）。存在且 val≠"0" 即 true。*/
    function flag(rPr, tag) {
        if (!(tag in rPr))
            return undefined;
        return attr(rPr[tag], 'val') !== '0';
    }
    function parseRunProperties(rPrRaw) {
        if (rPrRaw === null || typeof rPrRaw !== 'object')
            return undefined;
        const rPr = rPrRaw;
        const props = {};
        const b = flag(rPr, 'b');
        if (b !== undefined)
            props.bold = b;
        const i = flag(rPr, 'i');
        if (i !== undefined)
            props.italic = i;
        if ('strike' in rPr)
            props.strike = flag(rPr, 'strike') ?? true;
        if ('u' in rPr)
            props.underline = attr(rPr['u'], 'val') !== 'none';
        const sz = attr(rPr['sz'], 'val');
        if (sz !== undefined) {
            const n = Number(sz);
            if (!Number.isNaN(n))
                props.size = n;
        }
        const rgb = attr(rPr['color'], 'rgb');
        if (rgb !== undefined)
            props.color = rgb;
        const font = attr(rPr['rFont'], 'val');
        if (font !== undefined)
            props.font = font;
        const family = attr(rPr['family'], 'val');
        if (family !== undefined)
            props.family = Number.parseInt(family, 10);
        const charset = attr(rPr['charset'], 'val');
        if (charset !== undefined)
            props.charset = Number.parseInt(charset, 10);
        const va = attr(rPr['vertAlign'], 'val');
        if (va === 'superscript' || va === 'subscript' || va === 'baseline')
            props.vertAlign = va;
        return Object.keys(props).length > 0 ? props : undefined;
    }
    /**
     * 解析單一 string item（`<si>` 或 worksheet 的 inline `<is>`，兩者結構相同）。
     * 攤平出純文字並保留 rich run。
     */
    function parseStringItem(si) {
        // rich text：含 <r> run
        if ('r' in si) {
            const runs = toArray(si['r']).map((r) => {
                const run = (r ?? {});
                const text = decodeOoxmlEscapes(textOf(run['t']));
                const props = parseRunProperties(run['rPr']);
                return props ? { text, props } : { text };
            });
            return { text: runs.map((r) => r.text).join(''), runs };
        }
        // 純文字 <t>（可能含 xml:space="preserve"、可能為空）
        return { text: decodeOoxmlEscapes(textOf(si['t'])) };
    }
    class SharedStringsParser {
        /** 解析 sharedStrings.xml 字串 → SharedString[]（索引 = sst 索引）。*/
        static parse(xmlText) {
            const xml = parseXml(xmlText);
            const sst = (xml['sst'] ?? {});
            return toArray(sst['si']).map((si) => parseStringItem((si ?? {})));
        }
    }

    // cell_ref.ts — A1 表示法與 (row, col) 數值座標互轉
    //
    // 全程 1-based（A=1、row 1=1），與 OOXML cell ref 一致。
    const CHAR_A = 65; // 'A'
    const ALPHABET = 26;
    /** 欄字母 → 1-based 欄索引。'A'→1、'Z'→26、'AA'→27。*/
    function columnLetterToIndex(letters) {
        let n = 0;
        for (let i = 0; i < letters.length; i++) {
            n = n * ALPHABET + (letters.charCodeAt(i) - CHAR_A + 1);
        }
        return n;
    }
    /** 1-based 欄索引 → 欄字母。1→'A'、27→'AA'。*/
    function columnIndexToLetter(index) {
        let n = index;
        let s = '';
        while (n > 0) {
            const rem = (n - 1) % ALPHABET;
            s = String.fromCharCode(CHAR_A + rem) + s;
            n = Math.floor((n - 1) / ALPHABET);
        }
        return s;
    }
    const REF_RE = /^([A-Z]+)(\d+)$/;
    /** 解析 "C5" → { row: 5, col: 3 }。格式不符丟錯。*/
    function parseCellRef(ref) {
        const m = REF_RE.exec(ref);
        if (!m)
            throw new Error(`Invalid cell ref: ${ref}`);
        return { col: columnLetterToIndex(m[1]), row: Number.parseInt(m[2], 10) };
    }
    function parseRange(ref) {
        const colon = ref.indexOf(':');
        if (colon === -1) {
            const c = parseCellRef(ref);
            return { start: c, end: c };
        }
        return {
            start: parseCellRef(ref.slice(0, colon)),
            end: parseCellRef(ref.slice(colon + 1)),
        };
    }

    // color.ts — OOXML 色彩參照（規劃書 §1.5 / §2.2）
    //
    // Excel 色彩有四種來源，互斥出現在 <color>/<fgColor>/<bgColor>：
    //   rgb="FFFFFF00"            ARGB 直接色
    //   theme="7" tint="0.799"    主題色 token + 明暗調整（tint -1..1）
    //   indexed="64"             舊版 56 色 palette 索引
    //   auto="1"                 系統自動色（通常黑字白底）
    // 本層只「保真擷取」，實際解析成 RGB（theme/tint/indexed → 具體色）是 §2.2 ThemeResolver 的工作。
    /** 從 color 類元素（fgColor/bgColor/color）擷取 Color；無任何色彩屬性回 undefined。*/
    function parseColor(node) {
        if (node === null || node === undefined)
            return undefined;
        const color = {};
        const rgb = attr(node, 'rgb');
        if (rgb !== undefined)
            color.rgb = rgb;
        const theme = attr(node, 'theme');
        if (theme !== undefined)
            color.theme = Number.parseInt(theme, 10);
        const tint = attr(node, 'tint');
        if (tint !== undefined)
            color.tint = Number(tint);
        const indexed = attr(node, 'indexed');
        if (indexed !== undefined)
            color.indexed = Number.parseInt(indexed, 10);
        if (attr(node, 'auto') === '1')
            color.auto = true;
        return Object.keys(color).length > 0 ? color : undefined;
    }

    // cf_parser.ts — 解析 worksheet 的 <conditionalFormatting>（規劃書 §1.7）
    //
    // CF 規則本體在 worksheet XML，格式（dxfId）指向 styles.xml 的 dxfs。
    // 本層解析規則結構；套用渲染/解 dxf 由上層（Phase 4）處理。
    //
    // 實檔分布（ChienYi）：cellIs / expression / duplicateValues。
    // 完整規格另含 colorScale / dataBar / iconSet / containsText 系列 / top10，一併解析。
    function parseCfvo(node) {
        return { type: attr(node, 'type') ?? '', val: attr(node, 'val') };
    }
    function parseCfvoList(container) {
        if (container === null || typeof container !== 'object')
            return [];
        return toArray(container['cfvo']).map(parseCfvo);
    }
    function parseRule(node) {
        const r = (node ?? {});
        const rule = {
            type: attr(r, 'type') ?? '',
            priority: intAttr(r, 'priority') ?? 0,
            dxfId: intAttr(r, 'dxfId'),
            operator: attr(r, 'operator'),
            text: attr(r, 'text'),
            formulas: toArray(r['formula']).map((f) => textOf(f)),
            stopIfTrue: boolAttr(r, 'stopIfTrue'),
            percent: boolAttr(r, 'percent'),
            rank: intAttr(r, 'rank'),
            bottom: boolAttr(r, 'bottom'),
            colorScale: undefined,
            dataBar: undefined,
            iconSet: undefined,
            timePeriod: attr(r, 'timePeriod'),
        };
        if ('colorScale' in r) {
            const cs = r['colorScale'];
            rule.colorScale = {
                cfvo: parseCfvoList(cs),
                colors: toArray(cs['color'])
                    .map((c) => parseColor(c))
                    .filter((c) => c !== undefined),
            };
        }
        if ('dataBar' in r) {
            const db = r['dataBar'];
            rule.dataBar = {
                cfvo: parseCfvoList(db),
                color: parseColor(db['color']),
                minLength: intAttr(db, 'minLength'),
                maxLength: intAttr(db, 'maxLength'),
                showValue: attr(db, 'showValue') !== '0',
            };
        }
        if ('iconSet' in r) {
            const is = r['iconSet'];
            rule.iconSet = {
                iconSet: attr(is, 'iconSet') ?? '3TrafficLights1',
                cfvo: parseCfvoList(is),
                reverse: boolAttr(is, 'reverse'),
                showValue: attr(is, 'showValue') !== '0',
            };
        }
        return rule;
    }
    /** 從已解析的 worksheet 節點取出全部 conditionalFormatting。*/
    function parseConditionalFormattings(ws) {
        return toArray(ws['conditionalFormatting']).map((cfNode) => {
            const cf = (cfNode ?? {});
            const sqref = attr(cf, 'sqref') ?? '';
            return {
                sqref,
                ranges: sqref.split(/\s+/).filter((s) => s.length > 0),
                rules: toArray(cf['cfRule']).map(parseRule),
            };
        });
    }
    class CFParser {
        /** 從 worksheet XML 字串獨立解析 CF（測試/獨立使用）。*/
        static parse(xmlText) {
            const xml = parseXml(xmlText);
            const ws = (xml['worksheet'] ?? {});
            return parseConditionalFormattings(ws);
        }
    }

    // dv_parser.ts — worksheet <dataValidations> → DataValidation[]（規劃書 §1.8）
    function parseOne(dv) {
        const sqref = attr(dv, 'sqref');
        if (!sqref)
            return undefined;
        const f1 = dv['formula1'];
        const f2 = dv['formula2'];
        return {
            type: attr(dv, 'type') ?? 'none',
            operator: attr(dv, 'operator'),
            ranges: sqref.split(/\s+/).filter((s) => s.length > 0),
            formula1: f1 !== undefined ? textOf(f1) : undefined,
            formula2: f2 !== undefined ? textOf(f2) : undefined,
            allowBlank: boolAttr(dv, 'allowBlank'),
        };
    }
    /** 解析 worksheet 的 <dataValidations>。*/
    function parseDataValidations(ws) {
        const container = ws['dataValidations'];
        if (!container)
            return [];
        return toArray(container['dataValidation'])
            .map(parseOne)
            .filter((d) => d !== undefined && d.ranges.length > 0);
    }

    // worksheet_parser.ts — 解析 xl/worksheets/sheetN.xml（規劃書 §1.6，核心）
    //
    // 提取 cell value（含型別解析 + sharedString 解參照）、公式、合併儲存格、欄資訊、凍結窗格。
    // cell value 是 Phase 1 Exit「提取率 > 95%」的量測對象，對照 calamine golden 比對。
    function parseCols(wsData) {
        const colsContainer = wsData['cols'];
        if (colsContainer === undefined)
            return [];
        return toArray(colsContainer['col']).map((c) => {
            const w = attr(c, 'width');
            return {
                min: intAttr(c, 'min') ?? 0,
                max: intAttr(c, 'max') ?? 0,
                width: w !== undefined ? Number(w) : undefined,
                customWidth: boolAttr(c, 'customWidth'),
                hidden: boolAttr(c, 'hidden'),
                bestFit: boolAttr(c, 'bestFit'),
            };
        });
    }
    function parseFreeze(wsData) {
        const views = wsData['sheetViews'];
        if (views === undefined)
            return undefined;
        const view = toArray(views['sheetView'])[0];
        if (view === undefined || typeof view !== 'object')
            return undefined;
        const pane = view['pane'];
        if (pane === undefined)
            return undefined;
        const xSplit = intAttr(pane, 'xSplit') ?? 0;
        const ySplit = intAttr(pane, 'ySplit') ?? 0;
        if (xSplit === 0 && ySplit === 0)
            return undefined;
        return { xSplit, ySplit, topLeftCell: attr(pane, 'topLeftCell') };
    }
    function parseCell(cRaw) {
        const c = (cRaw ?? {});
        const ref = attr(c, 'r') ?? '';
        const coord = ref ? parseCellRef(ref) : { row: 0, col: 0 };
        const type = (attr(c, 't') ?? 'n');
        let raw;
        let inline;
        if (type === 'inlineStr') {
            const is = c['is'];
            if (is !== undefined)
                inline = parseStringItem(is);
        }
        else if ('v' in c) {
            raw = textOf(c['v']);
        }
        let formula;
        if ('f' in c) {
            const f = textOf(c['f']);
            formula = f === '' ? undefined : f;
        }
        return {
            ref,
            row: coord.row,
            col: coord.col,
            type,
            styleIndex: intAttr(c, 's'),
            raw,
            formula,
            inline,
        };
    }
    class WorksheetParser {
        static parse(xmlText) {
            const xml = parseXml(xmlText);
            const ws = (xml['worksheet'] ?? {});
            const dimensionRef = attr(ws['dimension'], 'ref');
            const cols = parseCols(ws);
            const freeze = parseFreeze(ws);
            const showGridLines = attr(toArray(ws['sheetViews']?.['sheetView'])[0], 'showGridLines') !==
                '0';
            // ── sheetData → cells ──
            const sheetData = (ws['sheetData'] ?? {});
            const cells = [];
            const rowHeights = new Map();
            let maxRow = 0;
            let maxCol = 0;
            for (const rowRaw of toArray(sheetData['row'])) {
                const row = (rowRaw ?? {});
                // 自訂列高（customHeight=1 才視為使用者設定）
                const rIdx = intAttr(row, 'r');
                const ht = attr(row, 'ht');
                if (rIdx !== undefined && ht !== undefined && boolAttr(row, 'customHeight')) {
                    rowHeights.set(rIdx, Number(ht));
                }
                for (const cRaw of toArray(row['c'])) {
                    const cell = parseCell(cRaw);
                    // 收有值/公式/inline 的 cell；另收「有樣式的空白格」（邊框/填色/粗體等，匯出與渲染保真需要）。
                    // 對 cell value 提取無害：buildValueMap/buildValueMapStyled 對空值回 '' 不入 map。
                    const hasContent = cell.raw !== undefined || cell.formula !== undefined || cell.inline !== undefined;
                    if (hasContent || cell.styleIndex !== undefined) {
                        cells.push(cell);
                        if (cell.row > maxRow)
                            maxRow = cell.row;
                        if (cell.col > maxCol)
                            maxCol = cell.col;
                    }
                }
            }
            // ── mergeCells ──
            const mergeContainer = ws['mergeCells'];
            const merges = mergeContainer
                ? toArray(mergeContainer['mergeCell'])
                    .map((m) => attr(m, 'ref'))
                    .filter((r) => r !== undefined)
                : [];
            return {
                dimensionRef,
                cols,
                cells,
                merges,
                rowHeights,
                conditionalFormatting: parseConditionalFormattings(ws),
                dataValidations: parseDataValidations(ws),
                freeze,
                showGridLines,
                maxRow,
                maxCol,
            };
        }
    }
    /**
     * 解析單一 cell 的型別化 value（依 t 屬性 + sharedStrings 解參照）。
     * 空格回 ''（與 calamine to_python 對齊）。
     * 注意：日期序號（type='n' 但格式為日期）此層不轉日期字串，待 §2.3 NumberFormatCompiler。
     */
    function resolveCellValue(cell, sharedStrings) {
        switch (cell.type) {
            case 'inlineStr':
                return cell.inline?.text ?? '';
            case 's': {
                if (cell.raw === undefined)
                    return '';
                const idx = Number.parseInt(cell.raw, 10);
                return sharedStrings[idx]?.text ?? '';
            }
            case 'str':
                return cell.raw !== undefined ? decodeOoxmlEscapes(cell.raw) : '';
            case 'b':
                return cell.raw === '1';
            case 'e':
                return cell.raw ?? '';
            case 'd':
                return cell.raw ?? '';
            case 'n':
            default: {
                if (cell.raw === undefined || cell.raw === '')
                    return '';
                const n = Number(cell.raw);
                return Number.isNaN(n) ? cell.raw : n;
            }
        }
    }
    /**
     * 建 (row,col) → CellValue 的對照表（1-based），供 golden grid 逐格比對。
     */
    function buildValueMap(parsed, sharedStrings) {
        const map = new Map();
        for (const cell of parsed.cells) {
            const v = resolveCellValue(cell, sharedStrings);
            if (v !== '')
                map.set(`${cell.row}:${cell.col}`, v);
        }
        return map;
    }
    /** 解析 dimension ref（"A1:J41"）的列數/欄數；無則回 maxRow/maxCol。*/
    function worksheetBounds(parsed) {
        if (parsed.dimensionRef) {
            const { end } = parseRange(parsed.dimensionRef);
            return { rows: end.row, cols: end.col };
        }
        return { rows: parsed.maxRow, cols: parsed.maxCol };
    }

    // styles_parser.ts — 解析 xl/styles.xml（規劃書 §1.5，★ Phase 1 內容最大）
    //
    // styles.xml 是樣式索引池：cell 的 s 屬性 → cellXfs[s] → 指向 fontId/fillId/borderId/numFmtId。
    // 本層完整解析各池與 cellXfs/cellStyleXfs/dxfs，並提供 numFmt 解析（自訂 + 內建表）與日期格式判定。
    // 注意：把 xf 串接攤平成單一 ResolvedStyle 是 §2.1 StyleResolver 的工作，本層只「解析」不「解析串接」。
    const CUSTOM_NUMFMT_MIN_ID = 164; // ≥164 為自訂格式
    /** 內建數字格式 ID → formatCode（ECMA-376 §18.8.30）。*/
    const BUILTIN_NUMFMTS = {
        0: 'General',
        1: '0',
        2: '0.00',
        3: '#,##0',
        4: '#,##0.00',
        9: '0%',
        10: '0.00%',
        11: '0.00E+00',
        12: '# ?/?',
        13: '# ??/??',
        14: 'mm-dd-yy',
        15: 'd-mmm-yy',
        16: 'd-mmm',
        17: 'mmm-yy',
        18: 'h:mm AM/PM',
        19: 'h:mm:ss AM/PM',
        20: 'h:mm',
        21: 'h:mm:ss',
        22: 'm/d/yy h:mm',
        37: '#,##0 ;(#,##0)',
        38: '#,##0 ;[Red](#,##0)',
        39: '#,##0.00;(#,##0.00)',
        40: '#,##0.00;[Red](#,##0.00)',
        45: 'mm:ss',
        46: '[h]:mm:ss',
        47: 'mmss.0',
        48: '##0.0E+0',
        49: '@',
    };
    /** 內建日期/時間格式 ID（ECMA-376）。*/
    const BUILTIN_DATE_IDS = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47]);
    function parseFont$1(node) {
        const f = (node ?? {});
        const font = {};
        if ('b' in f)
            font.bold = attr(f['b'], 'val') !== '0';
        if ('i' in f)
            font.italic = attr(f['i'], 'val') !== '0';
        if ('strike' in f)
            font.strike = attr(f['strike'], 'val') !== '0';
        if ('u' in f)
            font.underline = attr(f['u'], 'val') ?? 'single';
        const sz = attr(f['sz'], 'val');
        if (sz !== undefined)
            font.size = Number(sz);
        const name = attr(f['name'], 'val');
        if (name !== undefined)
            font.name = name;
        const family = attr(f['family'], 'val');
        if (family !== undefined)
            font.family = Number.parseInt(family, 10);
        const charset = attr(f['charset'], 'val');
        if (charset !== undefined)
            font.charset = Number.parseInt(charset, 10);
        const va = attr(f['vertAlign'], 'val');
        if (va === 'superscript' || va === 'subscript' || va === 'baseline')
            font.vertAlign = va;
        const color = parseColor(f['color']);
        if (color !== undefined)
            font.color = color;
        return font;
    }
    function parseFill(node) {
        const fillObj = (node ?? {});
        const pf = (fillObj['patternFill'] ?? {});
        const fill = {};
        const pt = attr(pf, 'patternType');
        if (pt !== undefined)
            fill.patternType = pt;
        const fg = parseColor(pf['fgColor']);
        if (fg !== undefined)
            fill.fgColor = fg;
        const bg = parseColor(pf['bgColor']);
        if (bg !== undefined)
            fill.bgColor = bg;
        return fill;
    }
    function parseEdge(node) {
        if (node === null || node === undefined)
            return undefined;
        const edge = {};
        const style = attr(node, 'style');
        if (style !== undefined)
            edge.style = style;
        const color = parseColor(node['color']);
        if (color !== undefined)
            edge.color = color;
        return Object.keys(edge).length > 0 ? edge : undefined;
    }
    function parseBorder(node) {
        const b = (node ?? {});
        const border = {};
        const left = parseEdge(b['left']);
        if (left)
            border.left = left;
        const right = parseEdge(b['right']);
        if (right)
            border.right = right;
        const top = parseEdge(b['top']);
        if (top)
            border.top = top;
        const bottom = parseEdge(b['bottom']);
        if (bottom)
            border.bottom = bottom;
        const diagonal = parseEdge(b['diagonal']);
        if (diagonal)
            border.diagonal = diagonal;
        if (boolAttr(b, 'diagonalUp'))
            border.diagonalUp = true;
        if (boolAttr(b, 'diagonalDown'))
            border.diagonalDown = true;
        return border;
    }
    function parseAlignment(node) {
        if (node === null || node === undefined)
            return undefined;
        const a = {};
        const h = attr(node, 'horizontal');
        if (h !== undefined)
            a.horizontal = h;
        const v = attr(node, 'vertical');
        if (v !== undefined)
            a.vertical = v;
        if (boolAttr(node, 'wrapText'))
            a.wrapText = true;
        const rot = intAttr(node, 'textRotation');
        if (rot !== undefined)
            a.textRotation = rot;
        const indent = intAttr(node, 'indent');
        if (indent !== undefined)
            a.indent = indent;
        if (boolAttr(node, 'shrinkToFit'))
            a.shrinkToFit = true;
        return Object.keys(a).length > 0 ? a : undefined;
    }
    function parseXf(node) {
        const x = (node ?? {});
        return {
            numFmtId: intAttr(x, 'numFmtId') ?? 0,
            fontId: intAttr(x, 'fontId') ?? 0,
            fillId: intAttr(x, 'fillId') ?? 0,
            borderId: intAttr(x, 'borderId') ?? 0,
            xfId: intAttr(x, 'xfId'),
            applyNumberFormat: boolAttr(x, 'applyNumberFormat'),
            applyFont: boolAttr(x, 'applyFont'),
            applyFill: boolAttr(x, 'applyFill'),
            applyBorder: boolAttr(x, 'applyBorder'),
            applyAlignment: boolAttr(x, 'applyAlignment'),
            alignment: parseAlignment(x['alignment']),
        };
    }
    function childArray(parent, container, child) {
        const c = parent[container];
        if (c === undefined)
            return [];
        return toArray(c[child]);
    }
    class StylesParser {
        static parse(xmlText) {
            const xml = parseXml(xmlText);
            const ss = (xml['styleSheet'] ?? {});
            const customNumFmts = new Map();
            for (const nf of childArray(ss, 'numFmts', 'numFmt')) {
                const id = intAttr(nf, 'numFmtId');
                const code = attr(nf, 'formatCode');
                if (id !== undefined && code !== undefined)
                    customNumFmts.set(id, code);
            }
            const fonts = childArray(ss, 'fonts', 'font').map(parseFont$1);
            const fills = childArray(ss, 'fills', 'fill').map(parseFill);
            const borders = childArray(ss, 'borders', 'border').map(parseBorder);
            const cellStyleXfs = childArray(ss, 'cellStyleXfs', 'xf').map(parseXf);
            const cellXfs = childArray(ss, 'cellXfs', 'xf').map(parseXf);
            const dxfs = childArray(ss, 'dxfs', 'dxf').map((d) => {
                const dd = (d ?? {});
                const dxf = {};
                if ('font' in dd)
                    dxf.font = parseFont$1(dd['font']);
                if ('fill' in dd)
                    dxf.fill = parseFill(dd['fill']);
                if ('border' in dd)
                    dxf.border = parseBorder(dd['border']);
                const id = intAttr(dd['numFmt'], 'numFmtId');
                const code = attr(dd['numFmt'], 'formatCode');
                if (id !== undefined)
                    dxf.numFmtId = id;
                if (code !== undefined)
                    dxf.numFmtCode = code;
                return dxf;
            });
            return { customNumFmts, fonts, fills, borders, cellXfs, cellStyleXfs, dxfs };
        }
    }
    /** 取 numFmtId 的 formatCode：自訂優先、否則內建表；查無回 undefined。*/
    function numberFormatCode(styles, numFmtId) {
        return styles.customNumFmts.get(numFmtId) ?? BUILTIN_NUMFMTS[numFmtId];
    }
    /** 判定某 formatCode 是否為日期/時間格式（移除引號/方括號/跳脫後檢 y/m/d/h/s token）。*/
    function isDateFormatCode(code) {
        const stripped = code
            .replace(/\[[^\]]*\]/g, '') // [$-404]、[Red]、[h]
            .replace(/"[^"]*"/g, '') // "年" 等字面
            .replace(/\\./g, '') // \年 跳脫字面
            .toLowerCase();
        return /[ymdhs]/.test(stripped);
    }
    /** 判定某 numFmtId 是否為日期/時間格式（供 §2.3 序號轉日期使用）。*/
    function isDateNumberFormat(styles, numFmtId) {
        if (BUILTIN_DATE_IDS.has(numFmtId))
            return true;
        if (numFmtId < CUSTOM_NUMFMT_MIN_ID)
            return false;
        const code = styles.customNumFmts.get(numFmtId);
        return code !== undefined && isDateFormatCode(code);
    }

    // number_format.ts — Excel 日期序號 → 日期字串（規劃書 §2.3 最小版）
    //
    // 範圍：只做「日期序號 → YYYY-MM-DD」，補 §1.6 提取率的日期缺口。
    // 完整 number format 渲染（千分位/貨幣/百分比/自訂 token）是 §2.3 後續工作。
    //
    // Excel 1900 日期系統：serial 1 = 1900-01-01，但 Excel 誤把 1900 當閏年（serial 60 = 不存在的
    // 1900-02-29）。以 1899-12-30 為 day 0 的基準，可對 serial ≥ 61（即 ≥ 1900-03-01）正確還原——
    // 涵蓋所有現代日期。serial ≤ 60 的邊界（1900 年初）本最小版不保證，營造資料用不到。
    const EXCEL_EPOCH_TO_UNIX_DAYS = 25569; // 1899-12-30 → 1970-01-01 的天數
    const DAYS_PER_ERA = 146097; // 400 年的天數
    const ERA_SHIFT = 719468; // Hinnant 演算法：1970-01-01 對齊到 0000-03-01 era 起點
    /**
     * days since 1970-01-01 → 民曆 (y, m, d)。
     * Howard Hinnant civil_from_days 演算法（純整數、無時區、可處理負值）。
     */
    function civilFromDays(z) {
        const zz = z + ERA_SHIFT;
        const era = Math.floor((zz >= 0 ? zz : zz - (DAYS_PER_ERA - 1)) / DAYS_PER_ERA);
        const doe = zz - era * DAYS_PER_ERA; // [0, 146096]
        const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365); // [0,399]
        const y = yoe + era * 400;
        const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100)); // [0,365]
        const mp = Math.floor((5 * doy + 2) / 153); // [0,11]
        const d = doy - Math.floor((153 * mp + 2) / 5) + 1; // [1,31]
        const m = mp < 10 ? mp + 3 : mp - 9; // [1,12]
        return { y: m <= 2 ? y + 1 : y, m, d };
    }
    /** Excel 日期序號 → (y, m, d)（取整數部分，1899-12-30 基準）。*/
    function excelSerialToYmd(serial) {
        const unixDays = Math.floor(serial) - EXCEL_EPOCH_TO_UNIX_DAYS;
        return civilFromDays(unixDays);
    }
    function pad2(n) {
        return n < 10 ? '0' + n : String(n);
    }
    /** Excel 日期序號 → "YYYY-MM-DD"（對齊 python-calamine 的 str(date) 輸出）。*/
    function formatExcelDate(serial) {
        const { y, m, d } = excelSerialToYmd(serial);
        return `${String(y).padStart(4, '0')}-${pad2(m)}-${pad2(d)}`;
    }

    // number_formatter.ts — Excel number format code → 顯示字串（規劃書 §2.3 完整版子集）
    //
    // 僅供「視覺渲染」（VR / o-spreadsheet 顯示）；cell value 提取仍用原始數字（與 calamine 對齊）。
    // 涵蓋常用 token：# 0 ? , .（千分位/小數）、%（百分比）、"字面" \跳脫 [$貨幣] _寬度 *填充、
    // 多段 正;負;零;文字。日期 token（y/m/d/h/s）不在此（走 number_format.ts 的日期路徑）。
    const GROUP_SIZE = 3;
    /** 從 [$NT$-404] 取貨幣符號 "NT$"；[$-404]（純 locale）或 [Red] 等 → ''。*/
    function bracketLiteral(inner) {
        if (inner.startsWith('$')) {
            const rest = inner.slice(1);
            const dash = rest.indexOf('-');
            return dash >= 0 ? rest.slice(0, dash) : rest;
        }
        return ''; // 顏色 / 條件 / locale → 不輸出
    }
    /** 以 ; 分段，忽略引號/方括號內的分號。*/
    function splitSections(code) {
        const sections = [];
        let cur = '';
        let i = 0;
        while (i < code.length) {
            const c = code[i];
            if (c === '"') {
                const j = code.indexOf('"', i + 1);
                const end = j < 0 ? code.length : j;
                cur += code.slice(i, end + 1);
                i = end + 1;
            }
            else if (c === '[') {
                const j = code.indexOf(']', i);
                const end = j < 0 ? code.length : j;
                cur += code.slice(i, end + 1);
                i = end + 1;
            }
            else if (c === '\\') {
                cur += code.slice(i, i + 2);
                i += 2;
            }
            else if (c === ';') {
                sections.push(cur);
                cur = '';
                i++;
            }
            else {
                cur += c;
                i++;
            }
        }
        sections.push(cur);
        return sections;
    }
    function tokenize(section) {
        const tokens = [];
        let num = '';
        const flush = () => {
            if (num) {
                tokens.push({ t: 'num', pat: num });
                num = '';
            }
        };
        let i = 0;
        while (i < section.length) {
            const c = section[i];
            if (c === '#' || c === '0' || c === '?' || ((c === ',' || c === '.') && num !== '')) {
                num += c;
                i++;
                continue;
            }
            flush();
            if (c === '"') {
                const j = section.indexOf('"', i + 1);
                const end = j < 0 ? section.length : j;
                tokens.push({ t: 'lit', s: section.slice(i + 1, end) });
                i = end + 1;
            }
            else if (c === '\\') {
                tokens.push({ t: 'lit', s: section[i + 1] ?? '' });
                i += 2;
            }
            else if (c === '[') {
                const j = section.indexOf(']', i);
                const end = j < 0 ? section.length : j;
                tokens.push({ t: 'lit', s: bracketLiteral(section.slice(i + 1, end)) });
                i = end + 1;
            }
            else if (c === '_') {
                tokens.push({ t: 'lit', s: ' ' }); // 下一字元的寬度 ≈ 空白
                i += 2;
            }
            else if (c === '*') {
                i += 2; // 填充字元：跳過
            }
            else if (c === '%') {
                tokens.push({ t: 'pct' });
                i++;
            }
            else if (c === '@') {
                tokens.push({ t: 'text' });
                i++;
            }
            else {
                tokens.push({ t: 'lit', s: c });
                i++;
            }
        }
        flush();
        return tokens;
    }
    function groupThousands(intStr) {
        let out = '';
        for (let i = 0; i < intStr.length; i++) {
            if (i > 0 && (intStr.length - i) % GROUP_SIZE === 0)
                out += ',';
            out += intStr[i];
        }
        return out;
    }
    /** 依 number pattern（如 "#,##0.00"）格式化非負數。*/
    function renderNumber(n, pat) {
        const dot = pat.indexOf('.');
        const intPat = dot >= 0 ? pat.slice(0, dot) : pat;
        const decPat = dot >= 0 ? pat.slice(dot + 1) : '';
        const decDigits = (decPat.match(/[0#?]/g) ?? []).length;
        const thousands = intPat.includes(',');
        const minInt = (intPat.match(/0/g) ?? []).length;
        const fixed = n.toFixed(decDigits);
        const [rawInt, rawDec = ''] = fixed.split('.');
        let intStr = rawInt;
        if (intStr.length < minInt)
            intStr = '0'.repeat(minInt - intStr.length) + intStr;
        if (thousands)
            intStr = groupThousands(intStr);
        return decDigits > 0 ? `${intStr}.${rawDec}` : intStr;
    }
    /** Excel General：整數不帶小數、浮點原樣（去尾零）。*/
    function generalFormat(value) {
        if (Number.isInteger(value))
            return String(value);
        return String(value);
    }
    /**
     * 把數值依 format code 渲染成顯示字串。
     * @param value     數值（非日期；日期走 number_format.ts）
     * @param code      formatCode（如 "#,##0.00"、"0%"、'"NT$"#,##0'）
     */
    function formatNumber(value, code) {
        if (code === '' || code === 'General' || code === '@')
            return generalFormat(value);
        const sections = splitSections(code);
        let section;
        let prependMinus = false;
        if (value > 0) {
            section = sections[0];
        }
        else if (value < 0) {
            if (sections[1] !== undefined) {
                section = sections[1]; // 負數段（自帶括號/負號為字面）
            }
            else {
                section = sections[0];
                prependMinus = true;
            }
        }
        else {
            section = sections[2] ?? sections[0];
        }
        const tokens = tokenize(section);
        const pctCount = tokens.filter((t) => t.t === 'pct').length;
        const numTok = tokens.find((t) => t.t === 'num');
        const minus = prependMinus ? '-' : '';
        if (!numTok || numTok.pat === undefined) {
            // 純文字/字面段
            const body = tokens.map((t) => (t.t === 'lit' ? t.s ?? '' : t.t === 'pct' ? '%' : '')).join('');
            return minus + body;
        }
        const scaled = Math.abs(value) * Math.pow(100, pctCount);
        const formatted = renderNumber(scaled, numTok.pat);
        const out = tokens
            .map((t) => (t.t === 'lit' ? t.s ?? '' : t.t === 'num' ? formatted : t.t === 'pct' ? '%' : ''))
            .join('');
        return minus + out;
    }

    // value_resolver.ts — 結合 worksheet + styles 的 cell value 解析（規劃書 §2.3）
    //
    // §1.6 的 resolveCellValue 不認識樣式（純語意層），日期序號維持 number。
    // 本層引入 styles：當 cell 為數字且其 numFmt 為日期格式時，序號 → 日期字串，補上提取缺口。
    // 放獨立模組以避免 worksheet_parser 反向相依 styles_parser。
    /**
     * 解析 cell value，並在「數字 + 日期格式」時轉成日期字串。
     * styles 為 undefined 時退化為 §1.6 純語意解析。
     */
    function resolveCellValueStyled(cell, sharedStrings, styles) {
        const base = resolveCellValue(cell, sharedStrings);
        if (typeof base !== 'number' || styles === undefined || cell.styleIndex === undefined) {
            return base;
        }
        const xf = styles.cellXfs[cell.styleIndex];
        if (xf && isDateNumberFormat(styles, xf.numFmtId)) {
            return formatExcelDate(base);
        }
        return base;
    }
    /** 建 (row,col) → CellValue 對照表，套用日期格式轉換。*/
    function buildValueMapStyled(parsed, sharedStrings, styles) {
        const map = new Map();
        for (const cell of parsed.cells) {
            const v = resolveCellValueStyled(cell, sharedStrings, styles);
            if (v !== '')
                map.set(`${cell.row}:${cell.col}`, v);
        }
        return map;
    }

    // style_resolver.ts — xf cascade 攤平成 ResolvedStyle（規劃書 §2.1）
    //
    // cell 的 s 屬性 → cellXfs[s]（直接格式）→ 可繼承 cellStyleXfs[xfId]（named style 基底）。
    // 各屬性群（numFmt/font/fill/border/alignment）依 cellXf 的 applyX 旗標決定：
    //   applyX=1 → 用 cellXf 自身的 id；否則繼承 named style 的 id。
    // 無 named style（xfId 未定義）時一律用 cellXf 自身 id。
    // 輸出攤平後的單一 ResolvedStyle（具體 font/fill/border 物件 + numFmt 解析 + isDate）。
    //
    // 注意：theme/indexed color → 具體 RGB 是 §2.2 ThemeResolver；本層只攤平索引、不解色。
    const EMPTY_FONT = {};
    const EMPTY_FILL = {};
    const EMPTY_BORDER = {};
    class StyleResolver {
        constructor(styles) {
            this.styles = styles;
            this.cache = new Map();
        }
        /**
         * 解析 cell 的 styleIndex（s 屬性）→ ResolvedStyle。
         * styleIndex 未定義（cell 無 s）→ 用預設 cellXf（index 0）或全空樣式。
         */
        resolve(styleIndex) {
            const idx = styleIndex ?? 0;
            const cached = this.cache.get(idx);
            if (cached)
                return cached;
            const xf = this.styles.cellXfs[idx];
            const resolved = xf ? this.resolveXf(xf) : this.defaultStyle();
            this.cache.set(idx, resolved);
            return resolved;
        }
        /** 對單一 cellXf 做 cascade 攤平。*/
        resolveXf(xf) {
            const parent = xf.xfId !== undefined ? this.styles.cellStyleXfs[xf.xfId] : undefined;
            const hasParent = parent !== undefined;
            // 各屬性依 applyX 旗標取 cellXf 或 named style 的 id（無 parent 時恆用 cellXf）
            const numFmtId = hasParent && !xf.applyNumberFormat ? parent.numFmtId : xf.numFmtId;
            const fontId = hasParent && !xf.applyFont ? parent.fontId : xf.fontId;
            const fillId = hasParent && !xf.applyFill ? parent.fillId : xf.fillId;
            const borderId = hasParent && !xf.applyBorder ? parent.borderId : xf.borderId;
            const alignment = hasParent && !xf.applyAlignment ? parent.alignment : xf.alignment;
            return {
                numFmtId,
                numFmtCode: numberFormatCode(this.styles, numFmtId),
                isDate: isDateNumberFormat(this.styles, numFmtId),
                font: this.styles.fonts[fontId] ?? EMPTY_FONT,
                fill: this.styles.fills[fillId] ?? EMPTY_FILL,
                border: this.styles.borders[borderId] ?? EMPTY_BORDER,
                alignment,
            };
        }
        defaultStyle() {
            return {
                numFmtId: 0,
                numFmtCode: numberFormatCode(this.styles, 0),
                isDate: false,
                font: this.styles.fonts[0] ?? EMPTY_FONT,
                fill: this.styles.fills[0] ?? EMPTY_FILL,
                border: this.styles.borders[0] ?? EMPTY_BORDER,
                alignment: undefined,
            };
        }
    }

    // theme_parser.ts — 解析 xl/theme/theme1.xml（規劃書 §1.9）
    //
    // 取 clrScheme 的 12 色 token（dk1/lt1/dk2/lt2/accent1-6/hlink/folHlink）與 fontScheme
    // （major/minor 的 latin/ea/cs 字型）。色彩值：srgbClr 取 val、sysClr 取 lastClr（已解析值）。
    // 解析結果供 §2.2 ThemeResolver 把 cell 的 theme color → 具體 RGB。
    const SCHEME_KEYS = [
        'dk1', 'lt1', 'dk2', 'lt2',
        'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6',
        'hlink', 'folHlink',
    ];
    // Office 預設主題（fallback：theme 缺失或某色未定義時用）
    const DEFAULT_SCHEME = {
        dk1: '000000', lt1: 'FFFFFF', dk2: '44546A', lt2: 'E7E6E6',
        accent1: '4472C4', accent2: 'ED7D31', accent3: 'A5A5A5',
        accent4: 'FFC000', accent5: '5B9BD5', accent6: '70AD47',
        hlink: '0563C1', folHlink: '954F72',
    };
    /** 從 scheme 色元素（如 <dk1><srgbClr val=../sysClr lastClr=..>）取 6-hex。*/
    function colorFromElement(el) {
        if (el === null || typeof el !== 'object')
            return undefined;
        const e = el;
        const srgb = attr(e['srgbClr'], 'val');
        if (srgb !== undefined)
            return srgb.toUpperCase();
        const sys = attr(e['sysClr'], 'lastClr');
        if (sys !== undefined)
            return sys.toUpperCase();
        return undefined;
    }
    function parseFont(node) {
        if (node === null || typeof node !== 'object')
            return {};
        const n = node;
        const font = {};
        const latin = attr(n['latin'], 'typeface');
        if (latin)
            font.latin = latin;
        const ea = attr(n['ea'], 'typeface');
        if (ea)
            font.ea = ea;
        const cs = attr(n['cs'], 'typeface');
        if (cs)
            font.cs = cs;
        return font;
    }
    class ThemeParser {
        static parse(xmlText) {
            const xml = parseXmlNoNs(xmlText);
            const theme = (xml['theme'] ?? {});
            const elements = (theme['themeElements'] ?? {});
            const clr = (elements['clrScheme'] ?? {});
            const colorScheme = { ...DEFAULT_SCHEME };
            for (const key of SCHEME_KEYS) {
                const c = colorFromElement(clr[key]);
                if (c !== undefined)
                    colorScheme[key] = c;
            }
            const fontScheme = (elements['fontScheme'] ?? {});
            const major = toArray(fontScheme['majorFont'])[0];
            const minor = toArray(fontScheme['minorFont'])[0];
            return {
                colorScheme,
                majorFont: parseFont(major),
                minorFont: parseFont(minor),
            };
        }
        /** Office 預設主題（無 theme part 時 fallback）。*/
        static default() {
            return { colorScheme: { ...DEFAULT_SCHEME }, majorFont: {}, minorFont: {} };
        }
    }

    // theme_resolver.ts — Color（theme/indexed/rgb/auto）→ 具體 RGB（規劃書 §2.2）
    //
    // tint/shade 用 HSL luminance 演算法（沿用 dobtor_doc_editor Sprint 130 邏輯，OOXML §20.1.2.3.20）：
    //   SpreadsheetML 的 tint 屬性範圍 -1..1：
    //     tint > 0（變亮）：L' = L + (1 - L) * tint
    //     tint < 0（變暗）：L' = L * (1 + tint)
    //   只調亮度 L、保留 hue/saturation，避免 vivid 色被洗成灰。
    // <color theme="N"> 的索引順序：注意 0/1 與 2/3 相對 clrScheme XML 順序「互換」
    // （Excel：theme 0 = Background1 = lt1、theme 1 = Text1 = dk1）。
    const THEME_INDEX = [
        'lt1', 'dk1', 'lt2', 'dk2',
        'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6',
        'hlink', 'folHlink',
    ];
    // 舊版 indexed 56 色 palette（ECMA-376 §18.8.27）。64/65 為系統前/背景色（context 相關）。
    const INDEXED_PALETTE = {
        0: '000000', 1: 'FFFFFF', 2: 'FF0000', 3: '00FF00', 4: '0000FF', 5: 'FFFF00', 6: 'FF00FF', 7: '00FFFF',
        8: '000000', 9: 'FFFFFF', 10: 'FF0000', 11: '00FF00', 12: '0000FF', 13: 'FFFF00', 14: 'FF00FF', 15: '00FFFF',
        16: '800000', 17: '008000', 18: '000080', 19: '808000', 20: '800080', 21: '008080', 22: 'C0C0C0', 23: '808080',
        24: '9999FF', 25: '993366', 26: 'FFFFCC', 27: 'CCFFFF', 28: '660066', 29: 'FF8080', 30: '0066CC', 31: 'CCCCFF',
        32: '000080', 33: 'FF00FF', 34: 'FFFF00', 35: '00FFFF', 36: '800080', 37: '800000', 38: '008080', 39: '0000FF',
        40: '00CCFF', 41: 'CCFFFF', 42: 'CCFFCC', 43: 'FFFF99', 44: '99CCFF', 45: 'FF99CC', 46: 'CC99FF', 47: 'FFCC99',
        48: '3366FF', 49: '33CCCC', 50: '99CC00', 51: 'FFCC00', 52: 'FF9900', 53: 'FF6600', 54: '666699', 55: '969696',
        56: '003366', 57: '339966', 58: '003300', 59: '333300', 60: '993300', 61: '993366', 62: '333399', 63: '333333',
    };
    // ── HSL 色彩數學（port 自 dobtor_doc_editor ThemeResolver Sprint 130）──────
    function clamp01(x) {
        return Math.max(0, Math.min(1, x));
    }
    function hexToRgb(hex) {
        const h = hex.replace('#', '').padStart(6, '0');
        return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
    }
    function rgbToHex(rgb) {
        return rgb
            .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0').toUpperCase())
            .join('');
    }
    function rgbToHsl(r, g, b) {
        const rn = r / 255, gn = g / 255, bn = b / 255;
        const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
        const l = (max + min) / 2;
        if (max === min)
            return [0, 0, l];
        const d = max - min;
        const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        let h;
        switch (max) {
            case rn:
                h = ((gn - bn) / d + (gn < bn ? 6 : 0)) / 6;
                break;
            case gn:
                h = ((bn - rn) / d + 2) / 6;
                break;
            default:
                h = ((rn - gn) / d + 4) / 6;
                break;
        }
        return [h, s, l];
    }
    function hueToRgb(p, q, t) {
        let tt = t;
        if (tt < 0)
            tt += 1;
        if (tt > 1)
            tt -= 1;
        if (tt < 1 / 6)
            return p + (q - p) * 6 * tt;
        if (tt < 1 / 2)
            return q;
        if (tt < 2 / 3)
            return p + (q - p) * (2 / 3 - tt) * 6;
        return p;
    }
    function hslToRgb(h, s, l) {
        const lc = clamp01(l), sc = clamp01(s);
        if (sc === 0) {
            const v = lc * 255;
            return [v, v, v];
        }
        const q = lc < 0.5 ? lc * (1 + sc) : lc + sc - lc * sc;
        const p = 2 * lc - q;
        const hMod = ((h % 1) + 1) % 1;
        return [hueToRgb(p, q, hMod + 1 / 3) * 255, hueToRgb(p, q, hMod) * 255, hueToRgb(p, q, hMod - 1 / 3) * 255];
    }
    /** 對 6-hex 套 SpreadsheetML tint（-1..1）。*/
    function applyTint(hex, tint) {
        if (tint === 0)
            return hex.toUpperCase();
        const [r, g, b] = hexToRgb(hex);
        const [h, s, l] = rgbToHsl(r, g, b);
        const lNew = tint > 0 ? l + (1 - l) * clamp01(tint) : l * (1 + Math.max(-1, tint));
        return rgbToHex(hslToRgb(h, s, lNew));
    }
    /** ARGB（8-hex）或 RGB（6-hex）→ 6-hex（去 alpha、大寫）。*/
    function normalizeRgb(rgb) {
        const h = rgb.replace('#', '').toUpperCase();
        return h.length === 8 ? h.slice(2) : h.padStart(6, '0');
    }
    class ThemeResolver {
        constructor(theme) {
            this.theme = theme;
        }
        /**
         * Color → 6-hex RGB。
         * auto / indexed 64-65（系統色）/ 無效 theme 索引 → undefined（系統相關、由 caller 決定）。
         */
        resolveColor(color) {
            if (color === undefined)
                return undefined;
            if (color.auto)
                return undefined;
            if (color.rgb !== undefined) {
                const hex = normalizeRgb(color.rgb);
                return color.tint !== undefined ? applyTint(hex, color.tint) : hex;
            }
            if (color.theme !== undefined) {
                const key = THEME_INDEX[color.theme];
                if (key === undefined)
                    return undefined;
                const base = this.theme.colorScheme[key];
                return color.tint !== undefined ? applyTint(base, color.tint) : base;
            }
            if (color.indexed !== undefined) {
                const hex = INDEXED_PALETTE[color.indexed];
                if (hex === undefined)
                    return undefined; // 64/65 系統色或越界
                return color.tint !== undefined ? applyTint(hex, color.tint) : hex;
            }
            return undefined;
        }
    }

    // concrete_style.ts — 把 ResolvedStyle 的抽象 Color 全部解成具體 RGB（Phase 4.5 對接層前置）
    //
    // 串接 §2.1 StyleResolver（xf cascade → ResolvedStyle，色彩仍為抽象 Color）
    //      + §2.2 ThemeResolver（Color → 6-hex RGB）
    // → ConcreteStyle：font/fill/border 全部具體 hex（或 undefined = 系統/auto 色，由渲染層補黑/白）。
    // 這是餵 o-spreadsheet model commands / VR 像素比對前的「完全具體化」樣式。
    function concreteFont(font, toRgb) {
        const f = {};
        if (font.name !== undefined)
            f.name = font.name;
        if (font.size !== undefined)
            f.size = font.size;
        if (font.bold !== undefined)
            f.bold = font.bold;
        if (font.italic !== undefined)
            f.italic = font.italic;
        if (font.underline !== undefined)
            f.underline = font.underline;
        if (font.strike !== undefined)
            f.strike = font.strike;
        if (font.family !== undefined)
            f.family = font.family;
        if (font.charset !== undefined)
            f.charset = font.charset;
        if (font.vertAlign !== undefined)
            f.vertAlign = font.vertAlign;
        const color = toRgb(font.color);
        if (color !== undefined)
            f.color = color;
        return f;
    }
    function concreteFill(fill, toRgb) {
        const f = {};
        if (fill.patternType !== undefined)
            f.patternType = fill.patternType;
        const fg = toRgb(fill.fgColor);
        if (fg !== undefined)
            f.fgColor = fg;
        const bg = toRgb(fill.bgColor);
        if (bg !== undefined)
            f.bgColor = bg;
        return f;
    }
    function concreteEdge(edge, toRgb) {
        if (edge === undefined)
            return undefined;
        const e = {};
        if (edge.style !== undefined)
            e.style = edge.style;
        const color = toRgb(edge.color);
        if (color !== undefined)
            e.color = color;
        return Object.keys(e).length > 0 ? e : undefined;
    }
    function concreteBorder(border, toRgb) {
        const b = {};
        const left = concreteEdge(border.left, toRgb);
        if (left)
            b.left = left;
        const right = concreteEdge(border.right, toRgb);
        if (right)
            b.right = right;
        const top = concreteEdge(border.top, toRgb);
        if (top)
            b.top = top;
        const bottom = concreteEdge(border.bottom, toRgb);
        if (bottom)
            b.bottom = bottom;
        const diagonal = concreteEdge(border.diagonal, toRgb);
        if (diagonal)
            b.diagonal = diagonal;
        if (border.diagonalUp)
            b.diagonalUp = true;
        if (border.diagonalDown)
            b.diagonalDown = true;
        return b;
    }
    /**
     * 解 cell 樣式為完全具體（色彩皆 RGB）。組合 StyleResolver + ThemeResolver、結果快取。
     */
    class ConcreteStyleResolver {
        constructor(styles, theme) {
            this.cache = new Map();
            this.styleResolver = new StyleResolver(styles);
            this.themeResolver = new ThemeResolver(theme);
        }
        resolve(styleIndex) {
            const key = styleIndex ?? 0;
            const cached = this.cache.get(key);
            if (cached)
                return cached;
            const concrete = this.concretize(this.styleResolver.resolve(styleIndex));
            this.cache.set(key, concrete);
            return concrete;
        }
        concretize(rs) {
            const toRgb = (c) => this.themeResolver.resolveColor(c);
            const style = {
                numFmtId: rs.numFmtId,
                isDate: rs.isDate,
                font: concreteFont(rs.font, toRgb),
                fill: concreteFill(rs.fill, toRgb),
                border: concreteBorder(rs.border, toRgb),
            };
            if (rs.numFmtCode !== undefined)
                style.numFmtCode = rs.numFmtCode;
            if (rs.alignment !== undefined)
                style.alignment = rs.alignment;
            return style;
        }
    }
    /**
     * 取 fill 的「可見背景色」：solid → fgColor 才是顯示色（OOXML 慣例）；
     * none → undefined；其他 pattern → bgColor（圖樣後方底色）。
     */
    function fillBackgroundColor(fill) {
        if (fill.patternType === undefined || fill.patternType === 'none')
            return undefined;
        if (fill.patternType === 'solid')
            return fill.fgColor;
        return fill.bgColor;
    }

    // font_map.ts — Excel 字型名 → 渲染字型堆疊（VR 字型保真）
    //
    // golden 由 LibreOffice 渲染、走 fontconfig 字型替換。我方 puppeteer Chrome 也走 fontconfig，
    // 但若 CSS 加通用 fallback（sans-serif）會讓 Chrome 自選回退、與 LibreOffice 不一致。
    // 本模組把 Excel 字型釘死到 LibreOffice 慣用的 metric-compatible 替換 + 一致的 CJK 回退鏈。
    // Latin metric-compatible 替換（與原字型字寬一致，LibreOffice/系統內建）：
    //   Calibri→Carlito、Arial→Liberation Sans、Times New Roman→Liberation Serif ...
    const METRIC_COMPATIBLE = {
        Calibri: 'Carlito',
        'Calibri Light': 'Carlito',
        Cambria: 'Caladea',
        Arial: 'Liberation Sans',
        'Arial Narrow': 'Liberation Sans Narrow',
        Helvetica: 'Liberation Sans',
        'Times New Roman': 'Liberation Serif',
        Georgia: 'Liberation Serif',
        'Courier New': 'Liberation Mono',
    };
    // 系統實際存在的 CJK 字型（fc-list 確認）；CJK 字元的最終回退，確保與 LibreOffice 同源。
    const CJK_FALLBACK = "'WenQuanYi Zen Hei','Droid Sans Fallback',sans-serif";
    /**
     * Excel 字型名 → CSS font-family 堆疊。
     * - Latin 有 metric-compatible 替換 → 用替換 + CJK 回退
     * - CJK / 未知字型 → 原名（讓 fontconfig 比照 LibreOffice 替換）+ CJK 回退
     */
    function fontFamilyStack(name) {
        if (!name)
            return CJK_FALLBACK;
        const mc = METRIC_COMPATIBLE[name];
        const primary = mc ?? name;
        return `'${primary.replace(/'/g, '')}',${CJK_FALLBACK}`;
    }

    // html_render.ts — ParsedWorksheet + ConcreteStyle → HTML 表格（VR pipeline 的 render 路徑）
    //
    // 這是「model → DOM」的第一條 render 路徑：把解析出的 cell 值 + 具體樣式 render 成 HTML <table>，
    // 供 puppeteer 光柵化成 PNG。注意：HTML 佈局引擎與 LibreOffice 不同，與 golden 的像素差異會偏高，
    // 本路徑用於建立 VR 管線與自洽回歸基準，而非一步到位的 LibreOffice 像素對等。
    // 安全上限放寬以涵蓋完整 sheet（golden 為完整首 sheet），避免截斷造成尺寸不匹配假性差異。
    const DEFAULT_MAX_ROWS = 500;
    const DEFAULT_MAX_COLS = 80;
    const DEFAULT_COL_WIDTH_CHARS = 8.43;
    const DEFAULT_ROW_HEIGHT_PT = 15;
    const BORDER_WIDTH = {
        hair: 1, thin: 1, dotted: 1, dashed: 1,
        medium: 2, mediumDashed: 2,
        thick: 3, double: 3,
    };
    function esc(s) {
        return s
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    function valueToText(v) {
        if (v === undefined)
            return '';
        if (typeof v === 'boolean')
            return v ? 'TRUE' : 'FALSE';
        return String(v);
    }
    function edgeCss(side, edge) {
        if (!edge || !edge.style || edge.style === 'none')
            return '';
        const w = BORDER_WIDTH[edge.style] ?? 1;
        const kind = edge.style === 'double' ? 'double' : edge.style.includes('dash') ? 'dashed' : edge.style === 'dotted' ? 'dotted' : 'solid';
        const color = edge.color ? `#${edge.color}` : '#000';
        return `border-${side}:${w}px ${kind} ${color};`;
    }
    function cellCss(style, colW, rowH) {
        let css = `width:${colW}px;height:${rowH}px;`;
        const bg = fillBackgroundColor(style.fill);
        if (bg)
            css += `background:#${bg};`;
        const f = style.font;
        if (f.color)
            css += `color:#${f.color};`;
        if (f.bold)
            css += 'font-weight:bold;';
        if (f.italic)
            css += 'font-style:italic;';
        if (f.size)
            css += `font-size:${(f.size * 96) / 72}px;`;
        if (f.name)
            css += `font-family:${fontFamilyStack(f.name)};`;
        const deco = [];
        if (f.underline && f.underline !== 'none')
            deco.push('underline');
        if (f.strike)
            deco.push('line-through');
        if (deco.length)
            css += `text-decoration:${deco.join(' ')};`;
        const a = style.alignment;
        if (a?.horizontal)
            css += `text-align:${a.horizontal};`;
        css += `vertical-align:${a?.vertical ?? 'bottom'};`;
        css += a?.wrapText ? 'white-space:normal;' : 'white-space:nowrap;overflow:hidden;';
        css += edgeCss('left', style.border.left);
        css += edgeCss('right', style.border.right);
        css += edgeCss('top', style.border.top);
        css += edgeCss('bottom', style.border.bottom);
        return css;
    }
    /** 建合併資訊：anchor "r:c" → {rowspan,colspan}；covered "r:c" → true（跳過）。*/
    function buildMergeMaps(merges) {
        const anchors = new Map();
        const covered = new Set();
        for (const ref of merges) {
            const { start, end } = parseRange(ref);
            anchors.set(`${start.row}:${start.col}`, {
                rowspan: end.row - start.row + 1,
                colspan: end.col - start.col + 1,
            });
            for (let r = start.row; r <= end.row; r++) {
                for (let c = start.col; c <= end.col; c++) {
                    if (r === start.row && c === start.col)
                        continue;
                    covered.add(`${r}:${c}`);
                }
            }
        }
        return { anchors, covered };
    }
    /** 建欄索引（1-based）→ 寬度 px 的對照（依 ws.cols，否則預設）。*/
    function buildColWidths(ws, maxCol, defaultChars) {
        const widths = new Array(maxCol + 1).fill(columnWidthToPixels(defaultChars, DEFAULT_MDW));
        for (const col of ws.cols) {
            if (col.width === undefined)
                continue;
            const px = columnWidthToPixels(col.width, DEFAULT_MDW);
            for (let c = col.min; c <= col.max && c <= maxCol; c++)
                widths[c] = px;
        }
        return widths;
    }
    /** ParsedWorksheet → 完整 HTML 文件字串。*/
    function renderWorksheetHtml(ws, sharedStrings, styles, theme, opts = {}) {
        const maxRows = opts.maxRows ?? DEFAULT_MAX_ROWS;
        const maxCols = opts.maxCols ?? DEFAULT_MAX_COLS;
        const defaultChars = opts.defaultColWidthChars ?? DEFAULT_COL_WIDTH_CHARS;
        const rowHpx = rowHeightToPixels(opts.defaultRowHeightPt ?? DEFAULT_ROW_HEIGHT_PT);
        // 用 dimension 的完整 used range（涵蓋 golden 的全 sheet 範圍），而非僅有值的 cell 範圍
        const bounds = worksheetBounds(ws);
        const nRows = Math.min(maxRows, Math.max(bounds.rows, ws.maxRow, 1));
        const nCols = Math.min(maxCols, Math.max(bounds.cols, ws.maxCol, 1));
        const resolver = new ConcreteStyleResolver(styles, theme);
        const valueMap = buildValueMapStyled(ws, sharedStrings, styles);
        const styleIndexMap = new Map();
        for (const cell of ws.cells)
            styleIndexMap.set(`${cell.row}:${cell.col}`, cell.styleIndex);
        const colW = buildColWidths(ws, nCols, defaultChars);
        const { anchors, covered } = buildMergeMaps(ws.merges);
        const rowsHtml = [];
        for (let r = 1; r <= nRows; r++) {
            const cells = [];
            for (let c = 1; c <= nCols; c++) {
                const key = `${r}:${c}`;
                if (covered.has(key))
                    continue;
                const merge = anchors.get(key);
                const span = merge ? ` colspan="${merge.colspan}" rowspan="${merge.rowspan}"` : '';
                const style = resolver.resolve(styleIndexMap.get(key));
                const raw = valueMap.get(key);
                // 數字 + 非 General numFmt → 套完整 number format（千分位/貨幣/百分比）；其餘原樣
                const display = typeof raw === 'number' && style.numFmtCode && style.numFmtCode !== 'General'
                    ? formatNumber(raw, style.numFmtCode)
                    : valueToText(raw);
                cells.push(`<td${span} style="${cellCss(style, colW[c], rowHpx)}">${esc(display)}</td>`);
            }
            rowsHtml.push(`<tr>${cells.join('')}</tr>`);
        }
        return (`<!DOCTYPE html><html><head><meta charset="utf-8"><style>` +
            `*{box-sizing:border-box;margin:0;padding:0}` +
            `body{background:#fff}` +
            `table{border-collapse:collapse;table-layout:fixed;font-family:${CJK_FALLBACK};font-size:14.667px}` +
            `td{padding:0 2px;border:1px solid #d4d4d4}` +
            `</style></head><body><table>${rowsHtml.join('')}</table></body></html>`);
    }

    // cf_compiler.ts — CFParser AST → o-spreadsheet conditionalFormats（規劃書 §4.1）
    //
    // 把解析出的條件格式編譯成 o-spreadsheet 的 CF 物件，讓匯入的 xlsx CF 在可編輯試算表顯示。
    // v1 範圍：CellIsRule（cellIs operator + dxf 樣式）+ containsText 系列（o-spreadsheet 確定支援）。
    // colorScale/dataBar/iconSet/duplicateValues/expression 暫不編譯（o-spreadsheet 無直接對應或色彩格式待確認）。
    // Excel cellIs operator → o-spreadsheet operator
    const OPERATOR_MAP = {
        equal: 'Equal',
        notEqual: 'NotEqual',
        greaterThan: 'GreaterThan',
        greaterThanOrEqual: 'GreaterThanOrEqual',
        lessThan: 'LessThan',
        lessThanOrEqual: 'LessThanOrEqual',
        between: 'Between',
        notBetween: 'NotBetween',
    };
    // containsText 系列 type → o-spreadsheet operator
    const TEXT_TYPE_MAP = {
        containsText: 'ContainsText',
        notContainsText: 'NotContains',
        beginsWith: 'BeginsWith',
        endsWith: 'EndsWith',
    };
    /** dxf 的填色（CF dxf 慣例色彩在 bgColor，退而求 fgColor）→ 具體 RGB。*/
    function dxfFillColor(fill, theme) {
        if (!fill)
            return undefined;
        return theme.resolveColor(fill.bgColor) ?? theme.resolveColor(fill.fgColor);
    }
    function dxfToStyle(dxf, theme) {
        const style = {};
        if (dxf.font) {
            if (dxf.font.bold)
                style.bold = true;
            if (dxf.font.italic)
                style.italic = true;
            if (dxf.font.strike)
                style.strikethrough = true;
            if (dxf.font.underline && dxf.font.underline !== 'none')
                style.underline = true;
            const tc = theme.resolveColor(dxf.font.color);
            if (tc)
                style.textColor = `#${tc}`;
        }
        const fc = dxfFillColor(dxf.fill, theme);
        if (fc)
            style.fillColor = `#${fc}`;
        return style;
    }
    /** 將 range 的結尾列/欄夾到 sheet 範圍內（避免 D1:D1048576 這類超大範圍）。*/
    function clampRange(ref, maxRow, maxCol) {
        try {
            const { start, end } = parseRange(ref);
            const er = Math.min(end.row, Math.max(maxRow, start.row));
            const ec = Math.min(end.col, Math.max(maxCol, start.col));
            const s = `${columnIndexToLetter(start.col)}${start.row}`;
            const e = `${columnIndexToLetter(ec)}${er}`;
            return s === e ? s : `${s}:${e}`;
        }
        catch {
            return undefined;
        }
    }
    // Excel cfvo type → o-spreadsheet threshold type
    const CFVO_TYPE_MAP = {
        min: 'value',
        max: 'value',
        num: 'number',
        percent: 'percentage',
        percentile: 'percentile',
        formula: 'formula',
    };
    /** Excel Color → o-spreadsheet RGB 整數（colorScale/dataBar 用）。*/
    function colorToNumber(c, theme) {
        const hex = theme.resolveColor(c);
        if (!hex)
            return 0xffffff;
        const rgb = hex.length === 8 ? hex.slice(2) : hex; // 去 alpha
        const n = parseInt(rgb, 16);
        return Number.isFinite(n) ? n : 0xffffff;
    }
    function toThreshold(cfvo, color, theme) {
        const type = CFVO_TYPE_MAP[cfvo.type] ?? 'value';
        const t = { type, color: colorToNumber(color, theme) };
        // 'value'（min/max 自動）不帶 value；其餘帶閾值
        if (type !== 'value' && cfvo.val !== undefined)
            t.value = cfvo.val;
        return t;
    }
    function compileColorScale(rule, theme) {
        const cs = rule.colorScale;
        if (!cs || cs.cfvo.length < 2 || cs.colors.length < 2)
            return undefined;
        const last = cs.cfvo.length - 1;
        const minimum = toThreshold(cs.cfvo[0], cs.colors[0], theme);
        const maximum = toThreshold(cs.cfvo[last], cs.colors[last], theme);
        const midpoint = cs.cfvo.length >= 3 ? toThreshold(cs.cfvo[1], cs.colors[1], theme) : null;
        return { type: 'ColorScaleRule', minimum, midpoint, maximum };
    }
    function compileRule(rule, dxfs, theme) {
        const style = rule.dxfId !== undefined && dxfs[rule.dxfId] ? dxfToStyle(dxfs[rule.dxfId], theme) : {};
        if (rule.type === 'cellIs') {
            const operator = rule.operator ? OPERATOR_MAP[rule.operator] : undefined;
            if (!operator)
                return undefined;
            return { type: 'CellIsRule', operator, values: rule.formulas.slice(), style };
        }
        if (rule.type in TEXT_TYPE_MAP) {
            const operator = TEXT_TYPE_MAP[rule.type];
            const value = rule.text ?? '';
            return { type: 'CellIsRule', operator, values: [value], style };
        }
        if (rule.type === 'colorScale') {
            return compileColorScale(rule, theme);
        }
        if (rule.type === 'dataBar' && rule.dataBar) {
            // o-spreadsheet DataBarRule：{type, color(RGB 整數)}；bar 長度由 CF range 值自動推算
            return { type: 'DataBarRule', color: colorToNumber(rule.dataBar.color, theme) };
        }
        return undefined; // iconSet/duplicateValues/expression v1 不編譯
    }
    /**
     * 編譯 worksheet 的 CF → o-spreadsheet conditionalFormats。
     * @param idPrefix CF id 前綴（跨 sheet 唯一，如 sheet id）。
     */
    function compileConditionalFormats(cfBlocks, dxfs, theme, maxRow, maxCol, idPrefix = 'cf') {
        const out = [];
        let n = 1;
        for (const block of cfBlocks) {
            const ranges = block.ranges
                .map((r) => clampRange(r, maxRow, maxCol))
                .filter((r) => r !== undefined);
            if (ranges.length === 0)
                continue;
            for (const rule of block.rules) {
                const compiled = compileRule(rule, dxfs, theme);
                if (compiled) {
                    out.push({ id: `${idPrefix}_${n++}`, ranges, rule: compiled });
                }
            }
        }
        return out;
    }

    // dv_compiler.ts — DataValidation → o-spreadsheet dataValidationRules（規劃書 §4.2）
    //
    // v1：list（inline 清單 → isValueInList、range → isValueInRange）+ 數值/日期 operator
    // （between/equal/greaterThan）。custom/textLength 等暫不編譯。
    // Excel operator → o-spreadsheet criterion type（數值/日期）
    const OP_MAP = {
        between: 'isBetween',
        equal: 'isEqual',
        greaterThan: 'isGreaterThan',
    };
    function compileOne(dv, id) {
        if (dv.type === 'list') {
            const f1 = (dv.formula1 ?? '').trim();
            if (!f1)
                return undefined;
            if (f1.startsWith('"') && f1.endsWith('"')) {
                // inline：逗號分隔（Excel list 內選項不含逗號）
                const values = f1
                    .slice(1, -1)
                    .split(',')
                    .map((s) => s.trim())
                    .filter((s) => s.length > 0);
                if (values.length === 0)
                    return undefined;
                return { id, criterion: { type: 'isValueInList', values, displayStyle: 'arrow' }, ranges: dv.ranges };
            }
            // 範圍參照（如 $X$1:$X$5 或 Sheet!$A$1:$A$5）
            return { id, criterion: { type: 'isValueInRange', values: [f1], displayStyle: 'arrow' }, ranges: dv.ranges };
        }
        const type = dv.operator ? OP_MAP[dv.operator] : undefined;
        if (type && ['whole', 'decimal', 'date', 'time', 'textLength'].includes(dv.type)) {
            const values = type === 'isBetween' ? [dv.formula1 ?? '', dv.formula2 ?? ''] : [dv.formula1 ?? ''];
            if (values.some((v) => v === ''))
                return undefined;
            return { id, criterion: { type, values }, ranges: dv.ranges };
        }
        return undefined; // custom / textLength 無 operator / 其他 v1 不編譯
    }
    /** DataValidation[] → o-spreadsheet dataValidationRules（idPrefix 跨 sheet 唯一）。*/
    function compileDataValidations(dvs, idPrefix = 'dv') {
        const out = [];
        let n = 1;
        for (const dv of dvs) {
            const rule = compileOne(dv, `${idPrefix}_${n}`);
            if (rule) {
                out.push(rule);
                n++;
            }
        }
        return out;
    }

    // to_ospreadsheet.ts — ParsedWorksheet + ConcreteStyle → o-spreadsheet WorkbookData（Phase 4.5 對接）
    //
    // 產出 o-spreadsheet 的正規化 WorkbookData（styles/formats 池化、cell 以 id 參照），
    // 由 OWL 端 `new Model(load(data))` 載入成可編輯試算表。
    //
    // 範圍（v1）：
    //   - content：用萃取值（resolveCellValueStyled）而非原始公式 → 避免 o-spreadsheet 函數覆蓋率落差導致
    //     #BAD_EXPR；公式 round-trip 待 Phase 3。
    //   - style：bold/italic/strike/underline/fontSize/textColor/fillColor/align/verticalAlign/wrapping
    //   - format：numFmtCode（非日期、非 General）
    //   - merges、cols 寬度、colNumber/rowNumber
    //   - 邊框 v1 不輸出（正規化形狀待瀏覽器驗證後補；無邊框 o-spreadsheet 仍正常渲染）
    const MAX_COLS = 200;
    const MAX_ROWS = 2000;
    // Excel 邊框 style → o-spreadsheet（僅 thin/medium/thick/dashed/dotted）
    const BORDER_STYLE_MAP = {
        thin: 'thin', hair: 'thin',
        medium: 'medium', mediumDashed: 'medium', mediumDashDot: 'medium', mediumDashDotDot: 'medium',
        double: 'medium', thick: 'thick',
        dashed: 'dashed', dashDot: 'dashed', dashDotDot: 'dashed', slantDashDot: 'dashed',
        dotted: 'dotted',
    };
    function edgeDescr(edge) {
        if (!edge || !edge.style || edge.style === 'none')
            return undefined;
        const style = BORDER_STYLE_MAP[edge.style] ?? 'thin';
        return { style, color: edge.color ? `#${edge.color}` : '#000000' };
    }
    function toOBorder(cb) {
        const b = {};
        const left = edgeDescr(cb.left);
        if (left)
            b.left = left;
        const right = edgeDescr(cb.right);
        if (right)
            b.right = right;
        const top = edgeDescr(cb.top);
        if (top)
            b.top = top;
        const bottom = edgeDescr(cb.bottom);
        if (bottom)
            b.bottom = bottom;
        return Object.keys(b).length > 0 ? b : undefined;
    }
    /** 以 JSON key 去重的池（1-based id）。*/
    class Pool {
        constructor() {
            this.map = new Map();
            this.items = [];
        }
        intern(value) {
            const key = JSON.stringify(value);
            const existing = this.map.get(key);
            if (existing !== undefined)
                return existing;
            const id = this.items.length + 1;
            this.map.set(key, id);
            this.items.push(value);
            return id;
        }
        toRecord() {
            const out = {};
            this.items.forEach((v, i) => {
                out[i + 1] = v;
            });
            return out;
        }
    }
    function mapAlign(h) {
        if (h === 'left' || h === 'right' || h === 'center')
            return h;
        if (h === 'centerContinuous')
            return 'center';
        return undefined;
    }
    function mapVerticalAlign(v) {
        if (v === 'top' || v === 'bottom')
            return v;
        if (v === 'center' || v === 'middle')
            return 'middle';
        return undefined;
    }
    function toOStyle(cs) {
        const s = {};
        if (cs.font.bold)
            s.bold = true;
        if (cs.font.italic)
            s.italic = true;
        if (cs.font.strike)
            s.strikethrough = true;
        if (cs.font.underline && cs.font.underline !== 'none')
            s.underline = true;
        if (cs.font.size)
            s.fontSize = cs.font.size;
        if (cs.font.color)
            s.textColor = `#${cs.font.color}`;
        const bg = fillBackgroundColor(cs.fill);
        if (bg)
            s.fillColor = `#${bg}`;
        const align = mapAlign(cs.alignment?.horizontal);
        if (align)
            s.align = align;
        const valign = mapVerticalAlign(cs.alignment?.vertical);
        if (valign)
            s.verticalAlign = valign;
        if (cs.alignment?.wrapText)
            s.wrapping = 'wrap';
        return Object.keys(s).length > 0 ? s : undefined;
    }
    /** cell value → o-spreadsheet content 字串。*/
    function toContent(value) {
        if (typeof value === 'boolean')
            return value ? 'TRUE' : 'FALSE';
        return String(value);
    }
    // o-spreadsheet 已實作、且 ChienYi 公式會用到的函數（已逐一對 o_spreadsheet.js word-boundary 確認定義）。
    // 公式只用這些函數（或純算式無函數）時餵公式 → 即時運算；否則 fallback cached 值，避免 #BAD_EXPR。
    // CHOOSE 由本模組 spreadsheet_functions/choose.js 以 functionRegistry shim 補上 → 納入白名單。
    // 已知 o-spreadsheet 18.0.48 仍缺：MROUND / REPT / SIGN（保持排除，走 cached）。
    const SUPPORTED_FUNCTIONS = new Set([
        // lookup / reference
        'VLOOKUP', 'HLOOKUP', 'XLOOKUP', 'INDEX', 'MATCH', 'OFFSET', 'INDIRECT', 'CHOOSE',
        // logic
        'IF', 'IFS', 'IFERROR', 'IFNA', 'AND', 'OR', 'NOT',
        // math / agg
        'ROUND', 'ROUNDUP', 'ROUNDDOWN', 'CEILING', 'FLOOR', 'TRUNC', 'POWER', 'SQRT', 'ABS', 'INT', 'MOD', 'DELTA',
        'SUM', 'SUMIF', 'SUMIFS', 'SUMPRODUCT', 'PRODUCT',
        'COUNT', 'COUNTA', 'COUNTBLANK', 'COUNTIF', 'COUNTIFS',
        'AVERAGE', 'AVERAGEIF', 'AVERAGEIFS', 'MEDIAN', 'MIN', 'MAX', 'MINIFS', 'MAXIFS',
        'RANK', 'LARGE', 'SMALL', 'PERCENTILE', 'QUARTILE', 'STDEV',
        'ROW', 'COLUMN',
        // text
        'LEFT', 'RIGHT', 'MID', 'LEN', 'FIND', 'SEARCH', 'SUBSTITUTE', 'REPLACE', 'EXACT',
        'CONCATENATE', 'CONCAT', 'TEXTJOIN', 'TEXT', 'TRIM', 'UPPER', 'LOWER', 'PROPER', 'VALUE', 'CHAR',
        // date
        'TODAY', 'NOW', 'DATE', 'DATEVALUE', 'YEAR', 'MONTH', 'DAY', 'HOUR', 'MINUTE', 'SECOND',
        'WEEKDAY', 'EOMONTH', 'EDATE', 'DATEDIF', 'YEARFRAC', 'NETWORKDAYS', 'WORKDAY',
        // info
        'ISNUMBER', 'ISERROR', 'ISBLANK', 'ISTEXT', 'ISNA', 'CELL',
    ]);
    /** 公式是否只用支援函數（純算式無函數 → true）。去 _xlfn./_xlws. 前綴後比對。*/
    function formulaUsesOnlySupported(formula) {
        for (const m of formula.matchAll(/([A-Za-z_][A-Za-z0-9_.]*)\s*\(/g)) {
            const name = m[1].replace(/^_xl(fn|ws)\./i, '').toUpperCase();
            if (!SUPPORTED_FUNCTIONS.has(name))
                return false;
        }
        return true;
    }
    /**
     * o-spreadsheet 的 format 引擎只吃純數字格式（# 0 , . % 與空白）。
     * Excel 自訂格式含 `\` 跳脫、`"字面"`、CJK、`[$貨幣]`、`_`、`*` 會讓 o-spreadsheet 該格 #ERROR，
     * 故只放行純數字格式；其餘跳過（cell 顯示原始數字）。
     */
    function isOSpreadsheetSafeFormat(code) {
        return /^[#0,.%\s]+$/.test(code);
    }
    function buildSheet(sheetId, name, ws, ss, styles, resolver, themeResolver, stylePool, borderPool, figures = []) {
        const bounds = worksheetBounds(ws);
        const colNumber = Math.min(MAX_COLS, Math.max(bounds.cols, ws.maxCol, 1));
        const rowNumber = Math.min(MAX_ROWS, Math.max(bounds.rows, ws.maxRow, 1));
        const cells = {};
        for (const cell of ws.cells) {
            if (cell.col > colNumber || cell.row > rowNumber)
                continue;
            const value = resolveCellValueStyled(cell, ss, styles);
            const concrete = resolver.resolve(cell.styleIndex);
            const oStyle = toOStyle(concrete);
            const oCell = { content: '' };
            // 公式 round-trip：安全公式 → 餵公式（o-spreadsheet 即時運算）；否則 fallback cached 值
            if (cell.formula && formulaUsesOnlySupported(cell.formula)) {
                oCell.content = '=' + cell.formula.replace(/_xl(fn|ws)\./gi, '');
            }
            else if (value !== '') {
                oCell.content = toContent(value);
            }
            if (oStyle)
                oCell.style = stylePool.intern(oStyle);
            const oBorder = toOBorder(concrete.border);
            if (oBorder)
                oCell.border = borderPool.intern(oBorder);
            // 數字（非日期）且有非 General 格式 → 套 format
            if (typeof value === 'number' &&
                !isDateNumberFormat(styles, concrete.numFmtId) &&
                concrete.numFmtCode &&
                concrete.numFmtCode !== 'General' &&
                isOSpreadsheetSafeFormat(concrete.numFmtCode)) {
                oCell.format = concrete.numFmtCode; // o-spreadsheet load 以 getItemId intern 字串
            }
            // 只收有內容/樣式/邊框的 cell
            if (oCell.content !== '' || oCell.style !== undefined || oCell.border !== undefined) {
                cells[`${columnIndexToLetter(cell.col)}${cell.row}`] = oCell;
            }
        }
        const cols = {};
        for (const col of ws.cols) {
            if (col.width === undefined)
                continue;
            const size = columnWidthToPixels(col.width, DEFAULT_MDW);
            for (let c = col.min; c <= col.max && c <= colNumber; c++) {
                cols[c - 1] = { size }; // o-spreadsheet 用 0-based 欄索引
            }
        }
        // merges：超出 colNumber/rowNumber 的丟棄（避免 o-spreadsheet 校驗失敗）
        const merges = ws.merges.filter((ref) => {
            try {
                const { end } = parseRange(ref);
                return end.col <= colNumber && end.row <= rowNumber;
            }
            catch {
                return false;
            }
        });
        return {
            id: sheetId,
            name,
            colNumber,
            rowNumber,
            cells,
            merges,
            cols,
            rows: {},
            conditionalFormats: compileConditionalFormats(ws.conditionalFormatting, styles.dxfs, themeResolver, rowNumber, colNumber, sheetId),
            dataValidationRules: compileDataValidations(ws.dataValidations, sheetId),
            figures,
        };
    }
    /** 多工作表 → o-spreadsheet WorkbookData。*/
    function buildOSpreadsheetData(sheets, ss, styles, theme) {
        const resolver = new ConcreteStyleResolver(styles, theme);
        const themeResolver = new ThemeResolver(theme);
        const stylePool = new Pool();
        const borderPool = new Pool();
        const oSheets = sheets.map((s, i) => buildSheet(`sheet${i + 1}`, s.name, s.ws, ss, styles, resolver, themeResolver, stylePool, borderPool, s.figures ?? []));
        return {
            version: 1,
            sheets: oSheets.length > 0 ? oSheets : [emptySheet()],
            styles: stylePool.toRecord(),
            formats: {}, // o-spreadsheet load 由 cell.format 字串自行 intern 成池
            borders: borderPool.toRecord(),
        };
    }
    function emptySheet() {
        return {
            id: 'sheet1',
            name: 'Sheet1',
            colNumber: 26,
            rowNumber: 100,
            cells: {},
            merges: [],
            cols: {},
            rows: {},
            conditionalFormats: [],
            dataValidationRules: [],
            figures: [],
        };
    }

    // cf_writer.ts — ConditionalFormatting + dxfs → OOXML（Phase 6 §6.2 CF 匯出回 xlsx）
    //
    // exportXlsxFromBuffer 的反向：把解析的 CF AST 與 dxfs 序列化回 worksheet 的 <conditionalFormatting>
    // 與 styles.xml 的 <dxfs>，達成 CF 雙向 round-trip。
    function escAttr$1(s) {
        return s
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    function escText$1(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    /** Color → `<tag .../>`（rgb / theme+tint / indexed / auto）。回空字串表示無色。*/
    function colorXml$1(tag, c) {
        if (!c)
            return '';
        const a = [];
        if (c.rgb)
            a.push(`rgb="${c.rgb}"`);
        else if (c.theme !== undefined) {
            a.push(`theme="${c.theme}"`);
            if (c.tint !== undefined && c.tint !== 0)
                a.push(`tint="${c.tint}"`);
        }
        else if (c.indexed !== undefined)
            a.push(`indexed="${c.indexed}"`);
        else if (c.auto)
            a.push(`auto="1"`);
        else
            return '';
        return `<${tag} ${a.join(' ')}/>`;
    }
    function fontXml(f) {
        let s = '';
        if (f.bold)
            s += '<b/>';
        if (f.italic)
            s += '<i/>';
        if (f.strike)
            s += '<strike/>';
        if (f.underline && f.underline !== 'none') {
            s += f.underline === 'single' ? '<u/>' : `<u val="${escAttr$1(f.underline)}"/>`;
        }
        s += colorXml$1('color', f.color);
        if (f.size !== undefined)
            s += `<sz val="${f.size}"/>`;
        if (f.name)
            s += `<name val="${escAttr$1(f.name)}"/>`;
        return `<font>${s}</font>`;
    }
    function fillXml(fill) {
        const pattern = fill.patternType ?? 'solid';
        return (`<fill><patternFill patternType="${escAttr$1(pattern)}">` +
            colorXml$1('fgColor', fill.fgColor) +
            colorXml$1('bgColor', fill.bgColor) +
            `</patternFill></fill>`);
    }
    function edgeXml(tag, e) {
        if (!e || !e.style)
            return `<${tag}/>`;
        return `<${tag} style="${escAttr$1(e.style)}">${colorXml$1('color', e.color)}</${tag}>`;
    }
    function borderXml(b) {
        return (`<border>` +
            edgeXml('left', b.left) +
            edgeXml('right', b.right) +
            edgeXml('top', b.top) +
            edgeXml('bottom', b.bottom) +
            (b.diagonal ? edgeXml('diagonal', b.diagonal) : '') +
            `</border>`);
    }
    function dxfXml(dxf) {
        let s = '';
        if (dxf.font)
            s += fontXml(dxf.font);
        // dxf numFmt（罕見，CF 多用 font/fill）
        if (dxf.numFmtId !== undefined && dxf.numFmtCode)
            s += `<numFmt numFmtId="${dxf.numFmtId}" formatCode="${escAttr$1(dxf.numFmtCode)}"/>`;
        if (dxf.fill)
            s += fillXml(dxf.fill);
        if (dxf.border)
            s += borderXml(dxf.border);
        return `<dxf>${s}</dxf>`;
    }
    /** dxfs → `<dxfs>`（保留原索引順序，cfRule 的 dxfId 仍有效）。回空字串表示無 dxf。*/
    function writeDxfs(dxfs) {
        if (!dxfs || dxfs.length === 0)
            return '';
        return `<dxfs count="${dxfs.length}">${dxfs.map(dxfXml).join('')}</dxfs>`;
    }
    function cfvoXml(v) {
        return `<cfvo type="${escAttr$1(v.type)}"${v.val !== undefined ? ` val="${escAttr$1(v.val)}"` : ''}/>`;
    }
    function ruleXml(rule) {
        const a = [`type="${escAttr$1(rule.type)}"`];
        if (rule.dxfId !== undefined)
            a.push(`dxfId="${rule.dxfId}"`);
        a.push(`priority="${rule.priority}"`);
        if (rule.operator)
            a.push(`operator="${escAttr$1(rule.operator)}"`);
        if (rule.text !== undefined)
            a.push(`text="${escAttr$1(rule.text)}"`);
        if (rule.percent)
            a.push('percent="1"');
        if (rule.rank !== undefined)
            a.push(`rank="${rule.rank}"`);
        if (rule.stopIfTrue)
            a.push('stopIfTrue="1"');
        let inner = '';
        if (rule.colorScale) {
            inner +=
                `<colorScale>` +
                    rule.colorScale.cfvo.map(cfvoXml).join('') +
                    rule.colorScale.colors.map((c) => colorXml$1('color', c)).join('') +
                    `</colorScale>`;
        }
        else if (rule.dataBar) {
            inner +=
                `<dataBar>` + rule.dataBar.cfvo.map(cfvoXml).join('') + colorXml$1('color', rule.dataBar.color) + `</dataBar>`;
        }
        else if (rule.iconSet) {
            inner += `<iconSet iconSet="${escAttr$1(rule.iconSet.iconSet)}">` + rule.iconSet.cfvo.map(cfvoXml).join('') + `</iconSet>`;
        }
        inner += rule.formulas.map((f) => `<formula>${escText$1(f)}</formula>`).join('');
        return `<cfRule ${a.join(' ')}>${inner}</cfRule>`;
    }
    /** ConditionalFormatting[] → 串接的 `<conditionalFormatting>` XML（放在 mergeCells 之後）。*/
    function writeConditionalFormattings(blocks) {
        if (!blocks || blocks.length === 0)
            return '';
        return blocks
            .filter((b) => b.ranges.length > 0 && b.rules.length > 0)
            .map((b) => `<conditionalFormatting sqref="${escAttr$1(b.ranges.join(' '))}">${b.rules.map(ruleXml).join('')}</conditionalFormatting>`)
            .join('');
    }

    // dv_writer.ts — DataValidation[] → OOXML <dataValidations>（Phase 6 §6.2 DV 匯出回 xlsx）
    function escAttr(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function escText(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function dvXml(dv) {
        const a = [`type="${escAttr(dv.type)}"`];
        if (dv.operator)
            a.push(`operator="${escAttr(dv.operator)}"`);
        if (dv.allowBlank)
            a.push('allowBlank="1"');
        a.push(`sqref="${escAttr(dv.ranges.join(' '))}"`);
        let inner = '';
        if (dv.formula1 !== undefined && dv.formula1 !== '')
            inner += `<formula1>${escText(dv.formula1)}</formula1>`;
        if (dv.formula2 !== undefined && dv.formula2 !== '')
            inner += `<formula2>${escText(dv.formula2)}</formula2>`;
        return inner ? `<dataValidation ${a.join(' ')}>${inner}</dataValidation>` : `<dataValidation ${a.join(' ')}/>`;
    }
    /** DataValidation[] → `<dataValidations>`（放在 conditionalFormatting 之後）。*/
    function writeDataValidations(dvs) {
        if (!dvs || dvs.length === 0)
            return '';
        const valid = dvs.filter((d) => d.ranges.length > 0);
        if (valid.length === 0)
            return '';
        return `<dataValidations count="${valid.length}">${valid.map(dvXml).join('')}</dataValidations>`;
    }

    // xlsx_writer.ts — 寫出最小但合法的 xlsx（規劃書 Phase 6 雙向 round-trip）
    //
    // 範圍（v1）：cell 值（number/string/boolean）、公式（<f>+cached <v>）、合併儲存格、多工作表、
    // sharedStrings 去重。樣式 v1 寫 minimal styles.xml（單一預設 cellXf）——值/結構 round-trip 優先，
    // 樣式回寫待後續（需把 ConcreteStyle 反編成 styles.xml 各池）。
    //
    // 用 fflate zipSync 打包成 OOXML zip。
    const CUSTOM_NUMFMT_BASE = 164;
    /** ARGB（FF 前綴）。輸入 6-hex（無 #）或已含 #。*/
    function argb(hex) {
        const h = hex.replace('#', '').toUpperCase();
        return h.length === 8 ? h : `FF${h.padStart(6, '0')}`;
    }
    function colorXml(tag, hex) {
        return hex ? `<${tag} rgb="${argb(hex)}"/>` : '';
    }
    /**
     * 從 ConcreteStyle 反編 styles.xml 各池（numFmts/fonts/fills/borders/cellXfs），
     * cell 以 cellXf index 參照。fills[0]=none、fills[1]=gray125（Excel 慣例）。
     */
    class StyleSheetBuilder {
        constructor() {
            this.numFmts = new Map(); // code → id（custom，164+）
            this.fonts = new Map();
            this.fontXml = [];
            this.fills = new Map();
            this.fillXml = [];
            this.borders = new Map();
            this.borderXml = [];
            this.xfs = new Map();
            this.xfDef = [];
            /** CF 用的 dxfs（exportXlsxFromBuffer 由原始 styles 帶入；保留原索引）。*/
            this.dxfs = [];
            // 預設池項（index 0 / Excel 慣例）
            this.fontXml.push('<font><sz val="11"/><name val="Calibri"/></font>');
            this.fillXml.push('<fill><patternFill patternType="none"/></fill>');
            this.fillXml.push('<fill><patternFill patternType="gray125"/></fill>');
            this.borderXml.push('<border><left/><right/><top/><bottom/><diagonal/></border>');
        }
        internNumFmt(code, originalId) {
            // 內建（id<164 且非 0）直接用原 id、不入 numFmts；自訂則配 164+
            if (originalId > 0 && originalId < CUSTOM_NUMFMT_BASE)
                return originalId;
            const existing = this.numFmts.get(code);
            if (existing !== undefined)
                return existing;
            const id = CUSTOM_NUMFMT_BASE + this.numFmts.size;
            this.numFmts.set(code, id);
            return id;
        }
        internFont(f) {
            const parts = [];
            if (f.bold)
                parts.push('<b/>');
            if (f.italic)
                parts.push('<i/>');
            if (f.strike)
                parts.push('<strike/>');
            if (f.underline && f.underline !== 'none')
                parts.push('<u/>');
            if (f.size)
                parts.push(`<sz val="${f.size}"/>`);
            if (f.color)
                parts.push(colorXml('color', f.color));
            parts.push(`<name val="${f.name ? f.name.replace(/"/g, '') : 'Calibri'}"/>`);
            if (f.family !== undefined)
                parts.push(`<family val="${f.family}"/>`);
            if (f.charset !== undefined)
                parts.push(`<charset val="${f.charset}"/>`);
            const xml = `<font>${parts.join('')}</font>`;
            if (xml === '<font><name val="Calibri"/></font>' || xml === this.fontXml[0])
                return 0;
            const existing = this.fonts.get(xml);
            if (existing !== undefined)
                return existing;
            const id = this.fontXml.length;
            this.fonts.set(xml, id);
            this.fontXml.push(xml);
            return id;
        }
        internFill(fill) {
            const bg = fillBackgroundColor(fill);
            if (!bg)
                return 0; // none
            const xml = `<fill><patternFill patternType="solid"><fgColor rgb="${argb(bg)}"/><bgColor indexed="64"/></patternFill></fill>`;
            const existing = this.fills.get(xml);
            if (existing !== undefined)
                return existing;
            const id = this.fillXml.length;
            this.fills.set(xml, id);
            this.fillXml.push(xml);
            return id;
        }
        internBorder(b) {
            const edge = (side, e) => {
                if (!e || !e.style)
                    return `<${side}/>`;
                return `<${side} style="${e.style}">${colorXml('color', e.color ?? '000000')}</${side}>`;
            };
            const xml = `<border>${edge('left', b.left)}${edge('right', b.right)}${edge('top', b.top)}` +
                `${edge('bottom', b.bottom)}<diagonal/></border>`;
            if (xml === this.borderXml[0])
                return 0;
            const existing = this.borders.get(xml);
            if (existing !== undefined)
                return existing;
            const id = this.borderXml.length;
            this.borders.set(xml, id);
            this.borderXml.push(xml);
            return id;
        }
        /** ConcreteStyle → cellXf index（0 = 預設無樣式）。*/
        intern(cs) {
            if (!cs)
                return 0;
            const numFmtId = cs.numFmtCode && cs.numFmtCode !== 'General'
                ? this.internNumFmt(cs.numFmtCode, cs.numFmtId)
                : 0;
            const fontId = this.internFont(cs.font);
            const fillId = this.internFill(cs.fill);
            const borderId = this.internBorder(cs.border);
            const align = cs.alignment;
            const key = JSON.stringify({ numFmtId, fontId, fillId, borderId, align: align ?? null });
            if (numFmtId === 0 && fontId === 0 && fillId === 0 && borderId === 0 && !align)
                return 0;
            const existing = this.xfs.get(key);
            if (existing !== undefined)
                return existing;
            const id = this.xfDef.length + 1; // index 0 = 預設 xf
            this.xfs.set(key, id);
            this.xfDef.push({ numFmtId, fontId, fillId, borderId, align });
            return id;
        }
        toXml() {
            const numFmtsXml = this.numFmts.size > 0
                ? `<numFmts count="${this.numFmts.size}">` +
                    [...this.numFmts.entries()]
                        .map(([code, id]) => `<numFmt numFmtId="${id}" formatCode="${code.replace(/"/g, '&quot;').replace(/&(?!quot;)/g, '&amp;')}"/>`)
                        .join('') +
                    `</numFmts>`
                : '';
            const xfXml = [`<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>`]
                .concat(this.xfDef.map((x) => {
                const flags = (x.numFmtId ? ' applyNumberFormat="1"' : '') +
                    (x.fontId ? ' applyFont="1"' : '') +
                    (x.fillId ? ' applyFill="1"' : '') +
                    (x.borderId ? ' applyBorder="1"' : '') +
                    (x.align ? ' applyAlignment="1"' : '');
                let alignXml = '';
                if (x.align) {
                    const a = [];
                    if (x.align.horizontal)
                        a.push(`horizontal="${x.align.horizontal}"`);
                    if (x.align.vertical)
                        a.push(`vertical="${x.align.vertical}"`);
                    if (x.align.wrapText)
                        a.push('wrapText="1"');
                    alignXml = `<alignment ${a.join(' ')}/>`;
                }
                return `<xf numFmtId="${x.numFmtId}" fontId="${x.fontId}" fillId="${x.fillId}" borderId="${x.borderId}" xfId="0"${flags}>${alignXml}</xf>`;
            }))
                .join('');
            return (`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
                `<styleSheet xmlns="${XMLNS_MAIN}">` +
                numFmtsXml +
                `<fonts count="${this.fontXml.length}">${this.fontXml.join('')}</fonts>` +
                `<fills count="${this.fillXml.length}">${this.fillXml.join('')}</fills>` +
                `<borders count="${this.borderXml.length}">${this.borderXml.join('')}</borders>` +
                `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` +
                `<cellXfs count="${this.xfDef.length + 1}">${xfXml}</cellXfs>` +
                `<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>` +
                writeDxfs(this.dxfs) +
                `</styleSheet>`);
        }
    }
    const XMLNS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
    const XMLNS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
    const CT = 'http://schemas.openxmlformats.org/package/2006/content-types';
    const PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships';
    function xmlEscape(s) {
        return s
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    /** sharedStrings 去重池。*/
    class StringPool {
        constructor() {
            this.map = new Map();
            this.items = [];
        }
        intern(s) {
            const existing = this.map.get(s);
            if (existing !== undefined)
                return existing;
            const id = this.items.length;
            this.map.set(s, id);
            this.items.push(s);
            return id;
        }
    }
    function cellXml(cell, pool, styles) {
        const ref = `${columnIndexToLetter(cell.col)}${cell.row}`;
        const v = cell.value;
        const sIdx = styles.intern(cell.style);
        const s = sIdx > 0 ? ` s="${sIdx}"` : '';
        if (cell.formula !== undefined) {
            const f = `<f>${xmlEscape(cell.formula)}</f>`;
            if (typeof v === 'number')
                return `<c r="${ref}"${s}>${f}<v>${v}</v></c>`;
            if (typeof v === 'boolean')
                return `<c r="${ref}"${s} t="b">${f}<v>${v ? 1 : 0}</v></c>`;
            if (typeof v === 'string')
                return `<c r="${ref}"${s} t="str">${f}<v>${xmlEscape(v)}</v></c>`;
            return `<c r="${ref}"${s}>${f}</c>`;
        }
        if (typeof v === 'number')
            return `<c r="${ref}"${s}><v>${v}</v></c>`;
        if (typeof v === 'boolean')
            return `<c r="${ref}"${s} t="b"><v>${v ? 1 : 0}</v></c>`;
        if (typeof v === 'string' && v !== '') {
            return `<c r="${ref}"${s} t="s"><v>${pool.intern(v)}</v></c>`;
        }
        return sIdx > 0 ? `<c r="${ref}"${s}/>` : `<c r="${ref}"/>`;
    }
    function sheetXml(sheet, pool, styles) {
        // 依列分組
        const byRow = new Map();
        let maxRow = 1;
        let maxCol = 1;
        for (const c of sheet.cells) {
            if (!byRow.has(c.row))
                byRow.set(c.row, []);
            byRow.get(c.row).push(c);
            if (c.row > maxRow)
                maxRow = c.row;
            if (c.col > maxCol)
                maxCol = c.col;
        }
        // 列 = 有 cell 的列 ∪ 有自訂列高的列（只有列高的空列也要寫出）
        const rowSet = new Set(byRow.keys());
        if (sheet.rowHeights)
            for (const r of sheet.rowHeights.keys())
                rowSet.add(r);
        const rows = [...rowSet].sort((a, b) => a - b);
        const rowsXml = rows
            .map((r) => {
            const cells = (byRow.get(r) ?? [])
                .sort((a, b) => a.col - b.col)
                .map((c) => cellXml(c, pool, styles))
                .join('');
            const h = sheet.rowHeights?.get(r);
            const rowAttrs = h !== undefined ? ` ht="${h}" customHeight="1"` : '';
            return `<row r="${r}"${rowAttrs}>${cells}</row>`;
        })
            .join('');
        const colsXml = sheet.cols && sheet.cols.length > 0
            ? `<cols>${sheet.cols
            .map((c) => `<col min="${c.min}" max="${c.max}" width="${c.width}" customWidth="1"/>`)
            .join('')}</cols>`
            : '';
        const dim = `A1:${columnIndexToLetter(maxCol)}${maxRow}`;
        const mergeXml = sheet.merges.length > 0
            ? `<mergeCells count="${sheet.merges.length}">${sheet.merges
            .map((m) => `<mergeCell ref="${m}"/>`)
            .join('')}</mergeCells>`
            : '';
        return (`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
            `<worksheet xmlns="${XMLNS_MAIN}" xmlns:r="${XMLNS_R}">` +
            `<dimension ref="${dim}"/>` +
            colsXml +
            `<sheetData>${rowsXml}</sheetData>` +
            mergeXml +
            writeConditionalFormattings(sheet.conditionalFormats) +
            writeDataValidations(sheet.dataValidations) +
            (sheet.drawingTarget ? `<drawing r:id="rId1"/>` : '') +
            `</worksheet>`);
    }
    /**
     * 寫出 xlsx bytes。
     * @param opts.dxfs CF 用的 differential formats
     * @param opts.rawParts 直通複製的原始 parts（圖表/drawing/media + 其 _rels）
     * @param opts.extraOverrides Content_Types 的 <Override> 片段（圖表/drawing parts）
     * @param opts.extraDefaults Content_Types 的 <Default> 片段（圖片副檔名）
     */
    function buildXlsx(sheets, opts) {
        const list = sheets.length > 0 ? sheets : [{ name: 'Sheet1', cells: [], merges: [] }];
        const pool = new StringPool();
        const styleBuilder = new StyleSheetBuilder();
        if (opts?.dxfs)
            styleBuilder.dxfs = opts.dxfs;
        const sheetFiles = {};
        const sheetRelsFiles = {};
        list.forEach((s, i) => {
            sheetFiles[`xl/worksheets/sheet${i + 1}.xml`] = sheetXml(s, pool, styleBuilder);
            // 有 drawing 的 sheet：重建 worksheet→drawing 關聯（rId1）
            if (s.drawingTarget) {
                sheetRelsFiles[`xl/worksheets/_rels/sheet${i + 1}.xml.rels`] =
                    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
                        `<Relationships xmlns="${PKG_REL}">` +
                        `<Relationship Id="rId1" Type="${XMLNS_R}/drawing" Target="${s.drawingTarget}"/>` +
                        `</Relationships>`;
            }
        });
        const sharedStrings = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
            `<sst xmlns="${XMLNS_MAIN}" count="${pool.items.length}" uniqueCount="${pool.items.length}">` +
            pool.items.map((t) => `<si><t xml:space="preserve">${xmlEscape(t)}</t></si>`).join('') +
            `</sst>`;
        const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
            `<workbook xmlns="${XMLNS_MAIN}" xmlns:r="${XMLNS_R}"><sheets>` +
            list
                .map((s, i) => `<sheet name="${xmlEscape(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`)
                .join('') +
            `</sheets></workbook>`;
        const wbRelItems = list
            .map((_s, i) => `<Relationship Id="rId${i + 1}" Type="${XMLNS_R}/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`)
            .join('');
        const ssId = list.length + 1;
        const stylesId = list.length + 2;
        const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
            `<Relationships xmlns="${PKG_REL}">` +
            wbRelItems +
            `<Relationship Id="rId${ssId}" Type="${XMLNS_R}/sharedStrings" Target="sharedStrings.xml"/>` +
            `<Relationship Id="rId${stylesId}" Type="${XMLNS_R}/styles" Target="styles.xml"/>` +
            `</Relationships>`;
        const styles = styleBuilder.toXml();
        const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
            `<Relationships xmlns="${PKG_REL}">` +
            `<Relationship Id="rId1" Type="${XMLNS_R}/officeDocument" Target="xl/workbook.xml"/>` +
            `</Relationships>`;
        const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
            `<Types xmlns="${CT}">` +
            `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
            `<Default Extension="xml" ContentType="application/xml"/>` +
            (opts?.extraDefaults ?? '') +
            `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
            list
                .map((_s, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`)
                .join('') +
            `<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>` +
            `<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>` +
            (opts?.extraOverrides ?? '') +
            `</Types>`;
        const files = {
            '[Content_Types].xml': strToU8(contentTypes),
            '_rels/.rels': strToU8(rootRels),
            'xl/workbook.xml': strToU8(workbook),
            'xl/_rels/workbook.xml.rels': strToU8(workbookRels),
            'xl/sharedStrings.xml': strToU8(sharedStrings),
            'xl/styles.xml': strToU8(styles),
            ...Object.fromEntries(Object.entries(sheetFiles).map(([k, v]) => [k, strToU8(v)])),
            ...Object.fromEntries(Object.entries(sheetRelsFiles).map(([k, v]) => [k, strToU8(v)])),
            ...(opts?.rawParts ?? {}),
        };
        return zipSync(files);
    }

    // chart_parser.ts — xl/charts/chartN.xml（DrawingML chartSpace）→ ChartAst（規劃書 §5.2）
    //
    // 解析圖表類型、series（categories/values cell ref）、title。用 parseXmlNoNs 去前綴（c:/a:）。
    // Excel chartSpace 內的 chart 元素 → o-spreadsheet 類型（去前綴後的 key）
    const TYPE_MAP = {
        barChart: 'bar',
        bar3DChart: 'bar',
        lineChart: 'line',
        line3DChart: 'line',
        stockChart: 'line',
        areaChart: 'line',
        area3DChart: 'line',
        pieChart: 'pie',
        pie3DChart: 'pie',
        doughnutChart: 'pie',
        ofPieChart: 'pie',
        scatterChart: 'scatter',
        bubbleChart: 'scatter',
    };
    /** 取 c:cat / c:val / c:tx 內的 cell ref（numRef/strRef/multiLvlStrRef 的 <c:f>），排除 #REF!。*/
    function refOf(node) {
        const n = node;
        if (!n)
            return undefined;
        const r = (n['numRef'] ?? n['strRef'] ?? n['multiLvlStrRef']);
        if (!r)
            return undefined;
        const f = textOf(r['f']).trim();
        return f && !f.includes('#REF!') ? f : undefined;
    }
    function parseSeries(ser) {
        const tx = ser['tx'];
        const literalName = tx ? textOf(tx['v']).trim() : '';
        return {
            name: literalName || undefined,
            categoriesRef: refOf(ser['cat']),
            valuesRef: refOf(ser['val']),
        };
    }
    /** 從 c:title 抽出標題文字（title>tx>rich>p>r>t，去前綴後遞迴收集 t）。*/
    function extractTitle(title) {
        if (!title || typeof title !== 'object')
            return undefined;
        const texts = [];
        const walk = (node) => {
            if (Array.isArray(node)) {
                node.forEach(walk);
                return;
            }
            if (node && typeof node === 'object') {
                const o = node;
                for (const [k, v] of Object.entries(o)) {
                    if (k === 't')
                        texts.push(textOf(v));
                    else if (typeof v === 'object')
                        walk(v);
                }
            }
        };
        walk(title);
        const s = texts.join('').trim();
        return s || undefined;
    }
    /** chartN.xml → ChartAst。無法辨識類型/無 series 時回 undefined。*/
    function parseChart(xml) {
        const root = parseXmlNoNs(xml);
        const chartSpace = root['chartSpace'];
        const chart = chartSpace?.['chart'];
        const plotArea = chart?.['plotArea'];
        if (!plotArea)
            return undefined;
        let type;
        let typeNode;
        for (const [key, mapped] of Object.entries(TYPE_MAP)) {
            if (plotArea[key]) {
                type = mapped;
                typeNode = plotArea[key];
                break;
            }
        }
        if (!type || !typeNode)
            return undefined;
        const series = toArray(typeNode['ser'])
            .map(parseSeries)
            .filter((s) => s.valuesRef || s.categoriesRef);
        if (series.length === 0)
            return undefined;
        return { type, title: extractTitle(chart?.['title']), series };
    }

    // drawing_parser.ts — xl/drawings/drawingN.xml → 圖表錨點（規劃書 §5.3 最小版）
    //
    // 只取「含圖表（graphicFrame → c:chart r:id）」的 anchor，供 chart 定位。圖片/shape v1 略過。
    function intText(node, key) {
        if (!node)
            return 0;
        const n = parseInt(textOf(node[key]), 10);
        return Number.isFinite(n) ? n : 0;
    }
    /** 從 anchor 找 graphicFrame 內的 chart r:id（去前綴後 r:id → id）。*/
    function chartRIdOf(anchor) {
        const gf = anchor['graphicFrame'];
        const graphic = gf?.['graphic'];
        const gData = graphic?.['graphicData'];
        const chart = gData?.['chart'];
        if (!chart)
            return undefined;
        return attr(chart, 'id') ?? attr(chart, 'r:id');
    }
    /** drawingN.xml → 圖表錨點清單。*/
    function parseDrawing(xml) {
        const root = parseXmlNoNs(xml);
        const wsDr = root['wsDr'];
        if (!wsDr)
            return [];
        const out = [];
        for (const anchorKey of ['twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor']) {
            for (const a of toArray(wsDr[anchorKey])) {
                const chartRId = chartRIdOf(a);
                if (!chartRId)
                    continue;
                const from = a['from'];
                const to = a['to'];
                const fromCol = intText(from, 'col');
                const fromRow = intText(from, 'row');
                out.push({
                    fromCol,
                    fromRow,
                    toCol: to ? intText(to, 'col') : fromCol + 8,
                    toRow: to ? intText(to, 'row') : fromRow + 15,
                    chartRId,
                });
            }
        }
        return out;
    }

    // chart_compiler.ts — ChartAst + drawing anchor → o-spreadsheet figure（規劃書 §5.2 ChartMapper）
    //
    // 解析鏈：worksheet rels → drawingN.xml → drawing rels → chartN.xml → ChartAst → figure。
    // 錨點格座標 → px 估算（o-spreadsheet 預設欄寬/列高近似）
    const COL_PX = 64;
    const ROW_PX = 20;
    const MIN_W = 300;
    const MIN_H = 200;
    function chartToFigure(ast, anchor, id) {
        const dataSets = ast.series.filter((s) => s.valuesRef).map((s) => ({ dataRange: s.valuesRef }));
        if (dataSets.length === 0)
            return undefined; // 無數值 ref → 無法成圖
        const labelRange = ast.series.find((s) => s.categoriesRef)?.categoriesRef;
        const x = anchor.fromCol * COL_PX;
        const y = anchor.fromRow * ROW_PX;
        const width = Math.max((anchor.toCol - anchor.fromCol) * COL_PX, MIN_W);
        const height = Math.max((anchor.toRow - anchor.fromRow) * ROW_PX, MIN_H);
        const data = {
            type: ast.type,
            title: { text: ast.title ?? '' },
            background: '#FFFFFF',
            dataSets,
            legendPosition: 'top',
            labelRange,
            dataSetsHaveTitle: false,
        };
        if (ast.type === 'bar' || ast.type === 'line') {
            data.verticalAxisPosition = 'left';
            data.stacked = false;
        }
        return { id, x, y, width, height, tag: 'chart', data };
    }
    /** 解析某 worksheet part 連結的所有圖表 → o-spreadsheet figures。*/
    function resolveSheetCharts(pkg, sheetPart, idPrefix) {
        const figures = [];
        let n = 0;
        const drawingRels = pkg.getRels(sheetPart).filter((r) => r.type.endsWith('/drawing'));
        for (const dr of drawingRels) {
            const drawingPart = dr.resolvedTarget;
            if (!drawingPart || !pkg.hasPart(drawingPart))
                continue;
            const anchors = parseDrawing(pkg.getPartText(drawingPart));
            if (anchors.length === 0)
                continue;
            const relMap = new Map(pkg.getRels(drawingPart).map((r) => [r.id, r.resolvedTarget]));
            for (const anchor of anchors) {
                const chartPart = relMap.get(anchor.chartRId);
                if (!chartPart || !pkg.hasPart(chartPart))
                    continue;
                const ast = parseChart(pkg.getPartText(chartPart));
                if (!ast)
                    continue;
                const fig = chartToFigure(ast, anchor, `${idPrefix}_fig${n}`);
                if (fig) {
                    figures.push(fig);
                    n++;
                }
            }
        }
        return figures;
    }

    // dobtor_spreadsheet_editor — OOXML SpreadsheetML Parser entry
    //
    // Sprint 0：空殼 export
    // Sprint 2（Phase 1 §1.1-1.2）：PackageReader（OPC 容器）+ units（單位系統）
    // Sprint 3（Phase 1 §1.3-1.4）：WorkbookParser + SharedStringsParser
    // Sprint 4（Phase 1 §1.6）：WorksheetParser（cell value 提取）+ cell_ref
    // Sprint 5（Phase 1 §1.5）：StylesParser（numFmts/fonts/fills/borders/cellXfs/dxfs）+ color
    // Sprint 6（§2.3 最小版）：日期序號 → 日期字串（number_format + value_resolver）
    // Sprint 7（§2.1）：StyleResolver（xf cascade 攤平成 ResolvedStyle）
    // Sprint 8（§1.9 + §2.2）：ThemeParser + ThemeResolver（theme/indexed/tint → 具體 RGB）
    // Sprint 9（§1.7）：CFParser（條件格式 rules）
    // Sprint 10：ConcreteStyleResolver（StyleResolver + ThemeResolver → 全具體 RGB 樣式，Phase 4.5 對接前置）
    //
    // 對接層：parser → ast → style/formula/cf/... compiler → XlsxModelBridge → o-spreadsheet model commands
    const SPRINT = 21;
    const BUILD_DATE = '2026-06-07';
    const TARGET_FIDELITY = 'Google Sheets / Excel A- (95%)';
    /**
     * 解析 xlsx 並把指定工作表渲染成 HTML 預覽（Odoo 前端用）。
     * @param buffer     xlsx ArrayBuffer
     * @param sheetIndex 要渲染的工作表索引（預設 0）
     */
    function importXlsxToHtmlPreview(buffer, sheetIndex = 0) {
        const pkg = PackageReader.fromBuffer(buffer);
        const wbp = new WorkbookParser(pkg);
        const wb = wbp.parse();
        const ssPart = wbp.sharedStringsPart();
        const ss = ssPart && pkg.hasPart(ssPart) ? SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
        const stPart = wbp.stylesPart();
        const styles = stPart && pkg.hasPart(stPart)
            ? StylesParser.parse(pkg.getPartText(stPart))
            : StylesParser.parse('<styleSheet/>');
        const thPart = wbp.themePart();
        const theme = thPart && pkg.hasPart(thPart)
            ? ThemeParser.parse(pkg.getPartText(thPart))
            : ThemeParser.default();
        const idx = Math.max(0, Math.min(sheetIndex, wb.sheets.length - 1));
        const target = wb.sheets[idx]?.target;
        let html = '';
        if (target && pkg.hasPart(target)) {
            const ws = WorksheetParser.parse(pkg.getPartText(target));
            html = renderWorksheetHtml(ws, ss, styles, theme);
        }
        return { sheets: wb.sheets.map((s) => s.name), activeSheet: idx, html };
    }
    /**
     * 解析 xlsx → o-spreadsheet WorkbookData（可編輯試算表用，OWL 端 new Model(load(data))）。
     */
    function importXlsxToOSpreadsheetData(buffer) {
        const pkg = PackageReader.fromBuffer(buffer);
        const wbp = new WorkbookParser(pkg);
        const wb = wbp.parse();
        const ssPart = wbp.sharedStringsPart();
        const ss = ssPart && pkg.hasPart(ssPart) ? SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
        const stPart = wbp.stylesPart();
        const styles = stPart && pkg.hasPart(stPart)
            ? StylesParser.parse(pkg.getPartText(stPart))
            : StylesParser.parse('<styleSheet/>');
        const thPart = wbp.themePart();
        const theme = thPart && pkg.hasPart(thPart)
            ? ThemeParser.parse(pkg.getPartText(thPart))
            : ThemeParser.default();
        const sheets = wb.sheets
            .filter((s) => s.target && pkg.hasPart(s.target))
            .map((s, i) => ({
            name: s.name,
            ws: WorksheetParser.parse(pkg.getPartText(s.target)),
            figures: resolveSheetCharts(pkg, s.target, `sheet${i + 1}`),
        }));
        return buildOSpreadsheetData(sheets, ss, styles, theme);
    }
    /**
     * 解析 xlsx → 用我方 writer 重新寫出 xlsx（Phase 6 round-trip）。
     * 值用原始萃取（數字保持數字、日期保持序號）以利 round-trip 一致。
     */
    function exportXlsxFromBuffer(buffer) {
        const pkg = PackageReader.fromBuffer(buffer);
        const wbp = new WorkbookParser(pkg);
        const wb = wbp.parse();
        const ssPart = wbp.sharedStringsPart();
        const ss = ssPart && pkg.hasPart(ssPart) ? SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
        const stPart = wbp.stylesPart();
        const styles = stPart && pkg.hasPart(stPart)
            ? StylesParser.parse(pkg.getPartText(stPart))
            : StylesParser.parse('<styleSheet/>');
        const thPart = wbp.themePart();
        const theme = thPart && pkg.hasPart(thPart)
            ? ThemeParser.parse(pkg.getPartText(thPart))
            : ThemeParser.default();
        const styleResolver = new ConcreteStyleResolver(styles, theme);
        const sheets = wb.sheets
            .filter((s) => s.target && pkg.hasPart(s.target))
            .map((s) => {
            const ws = WorksheetParser.parse(pkg.getPartText(s.target));
            const cells = ws.cells.map((cell) => {
                const value = resolveCellValue(cell, ss);
                const wc = { row: cell.row, col: cell.col };
                if (value !== '')
                    wc.value = value;
                if (cell.formula !== undefined)
                    wc.formula = cell.formula;
                if (cell.styleIndex !== undefined)
                    wc.style = styleResolver.resolve(cell.styleIndex);
                return wc;
            });
            const cols = ws.cols
                .filter((c) => c.width !== undefined)
                .map((c) => ({ min: c.min, max: c.max, width: c.width }));
            // chart/drawing 直通：重建 worksheet→drawing 關聯（相對 target）
            const drawingRel = pkg.getRels(s.target).find((r) => r.type.endsWith('/drawing'));
            const drawingTarget = drawingRel?.resolvedTarget
                ? `../drawings/${drawingRel.resolvedTarget.split('/').pop()}`
                : undefined;
            return {
                name: s.name,
                cells,
                merges: ws.merges,
                cols,
                rowHeights: ws.rowHeights,
                conditionalFormats: ws.conditionalFormatting,
                dataValidations: ws.dataValidations,
                drawingTarget,
            };
        });
        // 直通複製原始 drawing/chart/media parts + Content_Types 片段
        const rawParts = {};
        for (const p of pkg.listParts()) {
            if (/^xl\/(drawings|charts|media)\//.test(p)) {
                const bytes = pkg.getPart(p);
                if (bytes)
                    rawParts[p] = bytes;
            }
        }
        let extraOverrides = '';
        let extraDefaults = '';
        if (pkg.hasPart('[Content_Types].xml')) {
            const ct = pkg.getPartText('[Content_Types].xml');
            extraOverrides = (ct.match(/<Override[^>]*PartName="\/xl\/(?:drawings|charts)\/[^"]*"[^>]*\/>/g) ?? []).join('');
            extraDefaults = (ct.match(/<Default[^>]*\/>/g) ?? []).filter((d) => !/Extension="(?:rels|xml)"/.test(d)).join('');
        }
        return buildXlsx(sheets, { dxfs: styles.dxfs, rawParts, extraOverrides, extraDefaults });
    }

    exports.BUILD_DATE = BUILD_DATE;
    exports.CFParser = CFParser;
    exports.ConcreteStyleResolver = ConcreteStyleResolver;
    exports.DEFAULT_DPI = DEFAULT_DPI;
    exports.DEFAULT_MDW = DEFAULT_MDW;
    exports.EMU_PER_INCH = EMU_PER_INCH;
    exports.EMU_PER_POINT = EMU_PER_POINT;
    exports.POINTS_PER_INCH = POINTS_PER_INCH;
    exports.PackageReader = PackageReader;
    exports.SPRINT = SPRINT;
    exports.SharedStringsParser = SharedStringsParser;
    exports.StyleResolver = StyleResolver;
    exports.StylesParser = StylesParser;
    exports.TARGET_FIDELITY = TARGET_FIDELITY;
    exports.ThemeParser = ThemeParser;
    exports.ThemeResolver = ThemeResolver;
    exports.WorkbookParser = WorkbookParser;
    exports.WorksheetParser = WorksheetParser;
    exports.applyTint = applyTint;
    exports.buildOSpreadsheetData = buildOSpreadsheetData;
    exports.buildValueMap = buildValueMap;
    exports.buildValueMapStyled = buildValueMapStyled;
    exports.buildXlsx = buildXlsx;
    exports.civilFromDays = civilFromDays;
    exports.columnIndexToLetter = columnIndexToLetter;
    exports.columnLetterToIndex = columnLetterToIndex;
    exports.columnWidthToPixels = columnWidthToPixels;
    exports.emuToPixels = emuToPixels;
    exports.emuToPoints = emuToPoints;
    exports.excelSerialToYmd = excelSerialToYmd;
    exports.exportXlsxFromBuffer = exportXlsxFromBuffer;
    exports.fillBackgroundColor = fillBackgroundColor;
    exports.formatExcelDate = formatExcelDate;
    exports.formatNumber = formatNumber;
    exports.importXlsxToHtmlPreview = importXlsxToHtmlPreview;
    exports.importXlsxToOSpreadsheetData = importXlsxToOSpreadsheetData;
    exports.isDateFormatCode = isDateFormatCode;
    exports.isDateNumberFormat = isDateNumberFormat;
    exports.numberFormatCode = numberFormatCode;
    exports.parseCellRef = parseCellRef;
    exports.parseColor = parseColor;
    exports.parseConditionalFormattings = parseConditionalFormattings;
    exports.parseRange = parseRange;
    exports.parseStringItem = parseStringItem;
    exports.pixelsToColumnWidth = pixelsToColumnWidth;
    exports.pixelsToEmu = pixelsToEmu;
    exports.pixelsToPoints = pixelsToPoints;
    exports.pointsToEmu = pointsToEmu;
    exports.pointsToPixels = pointsToPixels;
    exports.resolveCellValue = resolveCellValue;
    exports.resolveCellValueStyled = resolveCellValueStyled;
    exports.rowHeightToPixels = rowHeightToPixels;
    exports.worksheetBounds = worksheetBounds;

}));
//# sourceMappingURL=dobtor_spreadsheet_editor.umd.js.map
