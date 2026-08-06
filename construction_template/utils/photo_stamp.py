# -*- coding: utf-8 -*-
"""照片浮水印——把拍攝日期印在右下角。

EAGLE 原系統 `models/errorRecord.js / imageGenerator()` 的行為
（2026-08-06 由 TKU source map 還原）：

    maxHeight = maxHeight || 10      // 公分
    maxWidth  = maxWidth  || 14
    …等比縮放，長邊不超過上限…
    if (imageDate) {
      imageDate = `${y}/${m}/${d}`                    // 西元，不補零
      image.print(紅色 Arial 32, 右下角, imageDate)    // 印在原圖上
    }

原系統用 Jimp + FONT_ARIAL_32_RED.fnt（點陣字型）。這裡用 Pillow 重現：
紅字、靠右下、字級依圖寬縮放（原系統固定 32px 是因為它的來源圖尺寸固定，
我們的照片尺寸不一，固定字級在大圖上會小到看不見）。
"""

import io
import logging

_logger = logging.getLogger(__name__)

# 原系統的預設上限（公分）
DEFAULT_MAX_WIDTH_CM = 14
DEFAULT_MAX_HEIGHT_CM = 10

WATERMARK_COLOR = (255, 0, 0)
# 字高佔圖高的比例——原系統在其來源圖上約是這個比例
FONT_HEIGHT_RATIO = 0.045
MIN_FONT_SIZE = 12
MARGIN_RATIO = 0.01


def fit_size_cm(width_px, height_px,
                max_width_cm=DEFAULT_MAX_WIDTH_CM,
                max_height_cm=DEFAULT_MAX_HEIGHT_CM):
    """等比縮放到不超過上限，回傳 (寬 cm, 高 cm)。

    照抄原系統的算法：先各自依單邊算，哪一邊超了就用另一邊回推。
    """
    if not width_px or not height_px:
        return max_width_cm, max_height_cm
    height = height_px * max_width_cm / width_px
    width = width_px * max_height_cm / height_px
    if height > max_height_cm:
        height = width * height_px / width_px
    elif width > max_width_cm:
        width = height * width_px / height_px
    return width, height


def _load_font(size):
    from PIL import ImageFont
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def stamp_date(raw, taken_on):
    """在照片右下角印上拍攝日期（西元 Y/M/D，紅字）。

    :param raw: 原始圖檔 bytes
    :param taken_on: date / datetime；None 就原樣回傳
    :return: 新的圖檔 bytes（失敗時回原圖，不讓報表因為一張照片壞掉）
    """
    if not raw or not taken_on:
        return raw
    try:
        from PIL import Image, ImageDraw
        image = Image.open(io.BytesIO(raw))
        fmt = image.format or 'JPEG'
        if image.mode not in ('RGB', 'RGBA'):
            image = image.convert('RGB')

        text = '%s/%s/%s' % (taken_on.year, taken_on.month, taken_on.day)
        font = _load_font(max(int(image.height * FONT_HEIGHT_RATIO), MIN_FONT_SIZE))
        draw = ImageDraw.Draw(image)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        margin = int(image.width * MARGIN_RATIO)
        draw.text((image.width - (right - left) - margin,
                   image.height - (bottom - top) - margin),
                  text, fill=WATERMARK_COLOR, font=font)

        out = io.BytesIO()
        image.save(out, format='PNG' if fmt == 'PNG' else 'JPEG')
        return out.getvalue()
    except Exception as exc:                   # 影像壞掉不該讓整份報表產不出來
        _logger.warning('照片浮水印失敗，改用原圖：%s', exc)
        return raw


def image_size_px(raw):
    """讀出圖片像素尺寸；讀不到回 (None, None)"""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            return image.size
    except Exception:
        return None, None
