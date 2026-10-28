"""
تبادل الملفات – File Exchange System
مولد أيقونات الملفات والمجلدات الواضحة وعالية الدقة (High-DPI Crisp Vector File Icons)
تصميم مسطح وواضح بدون تشويش، مع ألوان قياسية مميزة لكل نوع ملف
"""
import os
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPointF

_icon_cache = {}
_thumb_cache = {}

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tif', 'tiff', 'jfif'}
VIDEO_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv', 'flv', 'm4v'}
AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma'}
ARCHIVE_EXTENSIONS = {'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'}


def get_type_key(filename, is_folder=False):
    if is_folder or filename == '__folder__':
        return 'folder'
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    if ext in ('docx', 'doc', 'dotx', 'rtf', 'odt'):
        return 'word'
    if ext in ('xlsx', 'xls', 'csv', 'xlsm', 'ods'):
        return 'excel'
    if ext in ('accdb', 'mdb', 'accde'):
        return 'access'
    if ext == 'pdf':
        return 'pdf'
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    if ext in VIDEO_EXTENSIONS:
        return 'video'
    if ext in AUDIO_EXTENSIONS:
        return 'audio'
    if ext in ARCHIVE_EXTENSIONS:
        return 'archive'
    return 'other'


def create_stitch_office_pixmap(app_type, size=64):
    """
    توليد أيقونة واضحة وحادة بدقة عالية لكل نوع ملف أو مجلد:
    - مربعات بحواف دائرية ناعمة وألوان قياسية مميزة فوراً بالعين
    - رسم متجهي نظيف للمجلدات وشارات واضحة للصيغ (W, X, A, PDF, IMG, VID, AUD, ZIP, DOC)
    """
    key = f"clean_{app_type}_{size}_px"
    if key in _icon_cache:
        return _icon_cache[key]

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    padding = max(2, int(size * 0.06))
    r = QRectF(padding, padding, size - (padding * 2), size - (padding * 2))
    corner_radius = max(6, int(size * 0.22))

    if app_type == 'folder':
        # خلفية خضراء مؤسسية فاتحة مع رسم متجهي واضح للمجلد باللون الأخضر الرسمي والذهبي
        bg_path = QPainterPath()
        bg_path.addRoundedRect(r, corner_radius, corner_radius)
        painter.fillPath(bg_path, QBrush(QColor("#EDF5F2")))
        painter.setPen(QPen(QColor("#CBE3DA"), 1.0))
        painter.drawRoundedRect(r, corner_radius, corner_radius)

        # رسم شكل المجلد داخل المربع
        fx = r.x() + r.width() * 0.20
        fy = r.y() + r.height() * 0.26
        fw = r.width() * 0.60
        fh = r.height() * 0.48

        folder_path = QPainterPath()
        tab_w = fw * 0.42
        tab_h = fh * 0.22
        # اللسان العلوي للمجلد
        folder_path.moveTo(fx, fy + tab_h)
        folder_path.lineTo(fx, fy + 2)
        folder_path.lineTo(fx + tab_w - 3, fy + 2)
        folder_path.lineTo(fx + tab_w + 3, fy + tab_h)
        folder_path.lineTo(fx + fw, fy + tab_h)
        folder_path.lineTo(fx + fw, fy + fh)
        folder_path.lineTo(fx, fy + fh)
        folder_path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#14372e")))
        painter.drawPath(folder_path)

        # شريط ذهبي خفيف أسفل لسان المجلد لتمييزه بصرياً
        accent_rect = QRectF(fx + 2, fy + tab_h + 2, fw - 4, max(2.0, fh * 0.12))
        painter.setBrush(QBrush(QColor("#c59b27")))
        painter.drawRoundedRect(accent_rect, 1.5, 1.5)

        painter.end()
        _icon_cache[key] = pixmap
        return pixmap

    # تحديد اللون والتسمية القياسية لكل صيغة ملف
    palette = {
        'word':    ("#2B579A", "W",   0.44),
        'excel':   ("#217346", "X",   0.44),
        'access':  ("#A4373A", "A",   0.44),
        'pdf':     ("#E5252A", "PDF", 0.26),
        'image':   ("#7C3AED", "IMG", 0.25),
        'video':   ("#4F46E5", "VID", 0.25),
        'audio':   ("#DB2777", "AUD", 0.24),
        'archive': ("#D97706", "ZIP", 0.26),
        'other':   ("#475467", "DOC", 0.25),
    }
    hex_color, label, font_ratio = palette.get(app_type, ("#475467", "DOC", 0.25))
    bg_color = QColor(hex_color)

    # جسم الأيقونة المسطح والواضح
    body_path = QPainterPath()
    body_path.addRoundedRect(r, corner_radius, corner_radius)
    painter.fillPath(body_path, QBrush(bg_color))

    # إطار داخلي خفيف جداً لإبراز الحواف
    painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
    painter.drawRoundedRect(r, corner_radius, corner_radius)

    # كتابة رمز الصيغة بوضوح عالٍ في المنتصف
    font_px = max(8, int(size * font_ratio))
    font = QFont("Segoe UI", font_px, QFont.Weight.Bold)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

    painter.end()
    _icon_cache[key] = pixmap
    return pixmap


def create_image_thumbnail_pixmap(abs_path, size=64):
    """توليد مصغّرة حقيقية (Thumbnail) بحواف دائرية للصور الموجودة على القرص."""
    try:
        path_str = str(abs_path)
        if not os.path.isfile(path_str):
            return None
        st = os.stat(path_str)
        if st.st_size <= 0 or st.st_size > 25 * 1024 * 1024:
            return None
        cache_key = (path_str, int(st.st_mtime), size)
        if cache_key in _thumb_cache:
            return _thumb_cache[cache_key]

        src = QPixmap(path_str)
        if src.isNull():
            return None

        padding = max(2, int(size * 0.06))
        box = size - (padding * 2)
        scaled = src.scaled(
            box,
            box,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        sx = max(0, (scaled.width() - box) // 2)
        sy = max(0, (scaled.height() - box) // 2)
        cropped = scaled.copy(sx, sy, box, box)

        out = QPixmap(size, size)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        r = QRectF(padding, padding, box, box)
        corner_radius = max(6, int(size * 0.20))

        clip = QPainterPath()
        clip.addRoundedRect(r, corner_radius, corner_radius)
        painter.setClipPath(clip)
        painter.drawPixmap(int(padding), int(padding), cropped)
        painter.setClipping(False)

        painter.setPen(QPen(QColor("#E4E7EC"), 1.2))
        painter.drawRoundedRect(r, corner_radius, corner_radius)
        painter.end()

        if len(_thumb_cache) > 400:
            _thumb_cache.clear()
        _thumb_cache[cache_key] = out
        return out
    except Exception:
        return None


def create_office_icon(app_type, size=64):
    key = f"clean_{app_type}_{size}_ico"
    if key in _icon_cache:
        return _icon_cache[key]

    pm = create_stitch_office_pixmap(app_type, size)
    icon = QIcon(pm)
    _icon_cache[key] = icon
    return icon


def get_file_office_icon(filename, size=64, is_folder=False, abs_path=None):
    app_type = get_type_key(filename, is_folder=is_folder)
    if app_type == 'image' and abs_path:
        thumb = create_image_thumbnail_pixmap(abs_path, size=size)
        if thumb is not None:
            return QIcon(thumb)
    return create_office_icon(app_type, size)


def get_file_office_pixmap(filename, size=64, is_folder=False, abs_path=None):
    app_type = get_type_key(filename, is_folder=is_folder)
    if app_type == 'image' and abs_path:
        thumb = create_image_thumbnail_pixmap(abs_path, size=size)
        if thumb is not None:
            return thumb
    return create_stitch_office_pixmap(app_type, size)
