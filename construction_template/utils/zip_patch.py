#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""就地更新 zip 內的特定 entry，未修改的 entry 保留原始壓縮位元組。

## 為什麼需要這個

Python 的 `zipfile` 重打包時會把每個 entry 重新壓縮，而且用自己的預設值覆蓋
ZipInfo 欄位。實測（progress_schedule.xlsx，內容一個字都沒改）：

    原始         23834 bytes
    zipfile 重打包 20023 bytes    ← 少了 3811
    create_system  0 → 3          (Windows → Unix)
    create_version 45 → 20
    flag_bits      6 → 0
    external_attr  0 → 25165824

即使把原始 ZipInfo 物件直接傳給 writestr()，flag_bits 與 external_attr 仍會
被 zipfile 內部覆寫。也就是說**只要經過 zipfile 重打包，容器層就必然改變**，
而 Excel 對 OOXML 容器的容忍度未知。

本模組直接操作 zip 的位元組結構：未修改的 entry 連壓縮後的 bytes 都原封複製，
只有真正要改的 entry 重新壓縮。

## 自我驗證

`patch(src, dst, {})`（不改任何東西）必須產生與 src **byte-identical** 的檔案。
這個性質讓我們不必開 Excel 就能確認容器層沒被動過。

支援含 data descriptor 的 entry（13 個樣板中有 10 個是這種）。不支援 ZIP64，
遇到不認識的壓縮方式會直接拋錯而不是默默產生壞檔。

實測：19 個來源檔（staging/raw + staging/converted）零修改自我測試全部
byte-identical。
"""
import struct
import zipfile
import zlib

LOCAL_SIG = 0x04034b50
CENTRAL_SIG = 0x02014b50
EOCD_SIG = 0x06054b50
FLAG_DATA_DESCRIPTOR = 0x08


def patch(src, dst, updates):
    """updates: {entry 名稱: 新的未壓縮 bytes}；未列出的 entry 原封複製。"""
    with open(src, 'rb') as fh:
        blob = fh.read()
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()

    out = bytearray()
    central = bytearray()
    count = 0

    for info in infos:
        off = info.header_offset
        (sig, ver, flag, comp, mtime, mdate, crc, csize, usize,
         fnlen, extralen) = struct.unpack('<IHHHHHIIIHH', blob[off:off + 30])
        if sig != LOCAL_SIG:
            raise ValueError(f'{info.filename}: local header 簽章不符')

        name_extra = blob[off + 30: off + 30 + fnlen + extralen]
        data_start = off + 30 + fnlen + extralen
        new_offset = len(out)

        # 含 data descriptor 的 entry（flag bit 3）：local header 的
        # crc/csize/usize 都是 0，真值在資料後面的 descriptor 裡。
        # 實測 13 個樣板中有 10 個是這種（Excel 與 LibreOffice 都會產生）。
        # 原封複製時要連 descriptor 一起帶走，長度視有無 0x08074b50 簽章而定。
        desc_len = 0
        if flag & FLAG_DATA_DESCRIPTOR:
            csize = info.compress_size          # 真值只能從 central directory 拿
            crc, usize = info.CRC, info.file_size
            tail_at = data_start + csize
            desc_len = 16 if blob[tail_at:tail_at + 4] == b'PK\x07\x08' else 12

        if info.filename in updates:
            raw = updates[info.filename]
            if comp == zipfile.ZIP_DEFLATED:
                compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
                body = compressor.compress(raw) + compressor.flush()
            elif comp == zipfile.ZIP_STORED:
                body = raw
            else:
                raise ValueError(f'{info.filename}: 不支援的壓縮方式 {comp}')
            new_crc = zlib.crc32(raw) & 0xFFFFFFFF
            # 被改寫的 entry 一律寫成一般格式：真值放進 local header、
            # 清掉 data descriptor 旗標。只有這個 entry 的 flag 會變，其餘不動。
            new_flag = flag & ~FLAG_DATA_DESCRIPTOR
            header = struct.pack('<IHHHHHIIIHH', sig, ver, new_flag, comp, mtime,
                                 mdate, new_crc, len(body), len(raw),
                                 fnlen, extralen)
            out += header + name_extra + body
            e_crc, e_csize, e_usize, e_flag = new_crc, len(body), len(raw), new_flag
        else:
            # 位元組原封複製：local header + 檔名 + extra + 壓縮資料 + descriptor
            out += blob[off: data_start + csize + desc_len]
            e_crc, e_csize, e_usize, e_flag = crc, csize, usize, flag

        # central directory 記錄（沿用原本的欄位，只換 offset 與大小）
        cd_off = _find_central(blob, info)
        (c_sig, c_verby, c_verneed, c_flag, c_comp, c_mtime, c_mdate, c_crc,
         c_csize, c_usize, c_fnlen, c_extralen, c_cmtlen, c_disk,
         c_iattr, c_eattr, c_off) = struct.unpack('<IHHHHHHIIIHHHHHII',
                                                  blob[cd_off:cd_off + 46])
        tail = blob[cd_off + 46: cd_off + 46 + c_fnlen + c_extralen + c_cmtlen]
        central += struct.pack('<IHHHHHHIIIHHHHHII', c_sig, c_verby, c_verneed,
                               e_flag, c_comp, c_mtime, c_mdate, e_crc,
                               e_csize, e_usize, c_fnlen, c_extralen,
                               c_cmtlen, c_disk, c_iattr, c_eattr,
                               new_offset) + tail
        count += 1

    cd_offset = len(out)
    out += central
    # EOCD：沿用原檔的註解
    eocd_pos = blob.rfind(struct.pack('<I', EOCD_SIG))
    comment_len = struct.unpack('<H', blob[eocd_pos + 20:eocd_pos + 22])[0]
    comment = blob[eocd_pos + 22: eocd_pos + 22 + comment_len]
    out += struct.pack('<IHHHHIIH', EOCD_SIG, 0, 0, count, count,
                       len(central), cd_offset, comment_len) + comment

    with open(dst, 'wb') as fh:
        fh.write(bytes(out))


def _find_central(blob, info):
    """找出該 entry 在 central directory 的位置。"""
    name = info.filename.encode('utf-8')
    pos = blob.rfind(struct.pack('<I', EOCD_SIG))
    cd_off = struct.unpack('<I', blob[pos + 16:pos + 20])[0]
    p = cd_off
    while p < len(blob) - 4 and struct.unpack('<I', blob[p:p + 4])[0] == CENTRAL_SIG:
        fnlen, extralen, cmtlen = struct.unpack('<HHH', blob[p + 28:p + 34])
        if blob[p + 46:p + 46 + fnlen] == name:
            return p
        p += 46 + fnlen + extralen + cmtlen
    raise ValueError(f'{info.filename}: 在 central directory 找不到')


if __name__ == '__main__':
    import sys
    import filecmp
    src = sys.argv[1]
    patch(src, '/tmp/_zip_patch_selftest.xlsx', {})
    ok = filecmp.cmp(src, '/tmp/_zip_patch_selftest.xlsx', shallow=False)
    print('零修改自我測試：', '✅ byte-identical' if ok else '❌ 位元組不同')
    sys.exit(0 if ok else 1)
