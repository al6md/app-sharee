"""
تبادل الملفات – File Exchange System
مولد أيقونات Office بأسلوب Google Stitch (High-DPI Minimalist Fluent Icons)
تصميم نقي، ألوان متناسقة، ودقة وضوح فائقة للأجهزة وشاشات Retina/4K
"""
import os
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QLinearGradient
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
    توليد صورة نقطية فائقة النقاء بأسلوب Google Stitch:
    - بلاطة حديثة بحواف دائرية ناعمة (Modern Squircle)
    - ألوان غنية ومريحة للعين مع إطار خفيف
    """
    key = f"stitch_{app_type}_{size}_px"
    if key in _icon_cache:
        return _icon_cache[key]

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    padding = max(2, int(size * 0.05))
    r = QRectF(padding, padding, size - (padding * 2), size - (padding * 2))
    corner_radius = max(6, int(size * 0.22))

    if app_type == 'word':
        c_top = QColor("#2b579a")
        c_bottom = QColor("#185abd")
        letter = "W"
    elif app_type == 'excel':
        c_top = QColor("#107c41")
        c_bottom = QColor("#0e6133")
        letter = "X"
    elif app_type == 'access':
        c_top = QColor("#a4373a")
        c_bottom = QColor("#842a2d")
        letter = "A"
    elif app_type == 'pdf':
        c_top = QColor("#d9381e")
        c_bottom = QColor("#b3260f")
        letter = "P"
    elif app_type == 'image':
        c_top = QColor("#8b5cf6")
        c_bottom = QColor("#6d28d9")
        letter = "🖼️"
    elif app_type == 'video':
        c_top = QColor("#6366f1")
        c_bottom = QColor("#4338ca")
        letter = "🎬"
    elif app_type == 'audio':
        c_top = QColor("#ec4899")
        c_bottom = QColor("#be185d")
        letter = "🎵"
    elif app_type == 'archive':
        c_top = QColor("#f97316")
        c_bottom = QColor("#c2410c")
        letter = "📦"
    elif app_type == 'folder':
        c_top = QColor("#d4af37")
        c_bottom = QColor("#b8860b")
        letter = "📁"
    else:
        c_top = QColor("#475569")
        c_bottom = QColor("#334155")
        letter = "📄"

    # 1. ظل سفلي هادئ وخفيف
    shadow_rect = QRectF(r.x(), r.y() + max(1.5, size * 0.04), r.width(), r.height())
    shadow_path = QPainterPath()
    shadow_path.addRoundedRect(shadow_rect, corner_radius, corner_radius)
    painter.fillPath(shadow_path, QBrush(QColor(15, 23, 42, 35)))

    # 2. جسم البلاطة مع تدرج لوني فخم وهادئ
    grad = QLinearGradient(0, r.top(), 0, r.bottom())
    grad.setColorAt(0.0, c_top)
    grad.setColorAt(1.0, c_bottom)

    body_path = QPainterPath()
    body_path.addRoundedRect(r, corner_radius, corner_radius)
    painter.fillPath(body_path, QBrush(grad))

    # 3. إطار خارجي دقيق فائق النعومة
    painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
    painter.drawRoundedRect(r, corner_radius, corner_radius)

    # 4. كتابة الحرف أو الرمز الرئيسي
    if letter in ("📄", "🖼️", "🎬", "🎵", "📦", "📁"):
        font = QFont("Segoe UI Emoji", int(size * 0.40))
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, letter)
    else:
        font = QFont("Segoe UI", int(size * 0.46), QFont.Weight.Bold)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, letter)

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

        padding = max(2, int(size * 0.05))
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

        painter.setPen(QPen(QColor(139, 92, 246, 160), 1.5))
        painter.drawRoundedRect(r, corner_radius, corner_radius)
        painter.end()

        if len(_thumb_cache) > 400:
            _thumb_cache.clear()
        _thumb_cache[cache_key] = out
        return out
    except Exception:
        return None


def create_office_icon(app_type, size=64):
    key = f"stitch_{app_type}_{size}_ico"
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
