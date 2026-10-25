"""
تبادل الملفات – File Exchange System
مولد أيقونات Office بأسلوب Google Stitch (High-DPI Minimalist Fluent Icons)
تصميم نقي، ألوان متناسقة، ودقة وضوح فائقة للأجهزة وشاشات Retina/4K
"""
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QLinearGradient
from PyQt6.QtCore import Qt, QRectF, QPointF

_icon_cache = {}

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

    # 4. كتابة الحرف الرئيسي
    if letter == "📄":
        font = QFont("Segoe UI Emoji", int(size * 0.40))
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "📄")
    else:
        font = QFont("Segoe UI", int(size * 0.46), QFont.Weight.Bold)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        painter.setFont(font)

        # الحرف الأبيض الناصع بوضوح تام
        painter.setPen(QColor("#ffffff"))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, letter)

    painter.end()
    _icon_cache[key] = pixmap
    return pixmap

def create_office_icon(app_type, size=64):
    key = f"stitch_{app_type}_{size}_ico"
    if key in _icon_cache:
        return _icon_cache[key]

    pm = create_stitch_office_pixmap(app_type, size)
    icon = QIcon(pm)
    _icon_cache[key] = icon
    return icon

def get_file_office_icon(filename, size=64, is_folder=False):
    if is_folder or filename == '__folder__':
        return create_office_icon('folder', size)
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    if ext in ['docx', 'doc', 'dotx']:
        return create_office_icon('word', size)
    elif ext in ['xlsx', 'xls', 'csv', 'xlsm']:
        return create_office_icon('excel', size)
    elif ext in ['accdb', 'mdb', 'accde']:
        return create_office_icon('access', size)
    elif ext in ['pdf']:
        return create_office_icon('pdf', size)
    return create_office_icon('other', size)

def get_file_office_pixmap(filename, size=64, is_folder=False):
    if is_folder or filename == '__folder__':
        return create_stitch_office_pixmap('folder', size)
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    if ext in ['docx', 'doc', 'dotx']:
        return create_stitch_office_pixmap('word', size)
    elif ext in ['xlsx', 'xls', 'csv', 'xlsm']:
        return create_stitch_office_pixmap('excel', size)
    elif ext in ['accdb', 'mdb', 'accde']:
        return create_stitch_office_pixmap('access', size)
    elif ext in ['pdf']:
        return create_stitch_office_pixmap('pdf', size)
    return create_stitch_office_pixmap('other', size)
