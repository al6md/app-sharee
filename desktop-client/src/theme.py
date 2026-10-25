"""
تبادل الملفات – File Exchange System
نظام التصميم بأسلوب Google Stitch (Modern Minimalist & Windows 11 Fluent 2)
تدرجات هادئة، خطوط عصرية، بطاقات زجاجية ناعمة، وعناصر تفاعلية عالية الدقة
"""
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect

# 🎨 لوحة ألوان Google Stitch (Stitch Minimalist Palette)
BG_CANVAS = "#f8fafc"         # خلفية بيضاء لؤلؤية هادئة (Slate-50)
BG_SURFACE = "#ffffff"        # أسطح البطاقات والحاويات النقية
BG_SURFACE_HOVER = "#f1f5f9"  # رمادي ناعم عند التحويم (Slate-100)
BG_MUTED = "#f1f5f9"

BORDER_SUBTLE = "#e2e8f0"     # إطار فائق النعومة 1px (Slate-200)
BORDER_FOCUS = "#0f172a"      # إطار التركيز الداكن الأنيق (Slate-900)
BORDER_ACTIVE = "#2563eb"     # إطار التفاعل النشط

TEXT_TITLE = "#0f172a"        # نصوص العناوين الرئيسية شديدة الوضوح
TEXT_BODY = "#334155"         # نصوص المحتوى (Slate-700)
TEXT_MUTED = "#64748b"        # نصوص الشروحات والتفاصيل (Slate-500)
TEXT_FAINT = "#94a3b8"        # نصوص مساعدة (Slate-400)

PRIMARY_ACCENT = "#0f172a"    # نمط Stitch الحديث: الأسود الفاخر / الكحلي الغامق للأزرار
PRIMARY_HOVER = "#1e293b"
PRIMARY_TEXT = "#ffffff"

BLUE_ACCENT = "#2563eb"       # أزرق تقني نقي للروابط والتركيز

# ألوان الحالات (Status Indicators)
STATUS_SYNCED = "#10b981"     # أخضر نقي
STATUS_SYNCED_BG = "#ecfdf5"
STATUS_SYNCED_BORDER = "#a7f3d0"

STATUS_SYNCING = "#f59e0b"    # برتقالي دافئ
STATUS_SYNCING_BG = "#fffbeb"
STATUS_SYNCING_BORDER = "#fde68a"

STATUS_LOCKED = "#ef4444"     # أحمر ياقوتي
STATUS_LOCKED_BG = "#fef2f2"
STATUS_LOCKED_BORDER = "#fecaca"

# ألوان أيقونات Office بأسلوب Stitch النظيف
COLOR_WORD = "#185abd"
COLOR_EXCEL = "#107c41"
COLOR_ACCESS = "#a4373a"
COLOR_PDF = "#d9381e"

def get_stitch_stylesheet():
    """كود التنسيق الشامل بأسلوب Google Stitch العصري"""
    return f"""
    QMainWindow {{
        background-color: {BG_CANVAS};
    }}
    QWidget {{
        font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Cairo', -apple-system, sans-serif;
    }}
    QLabel {{
        color: {TEXT_TITLE};
    }}

    /* شريط البحث النظيف المستوحى من Stitch */
    QLineEdit#stitchSearch {{
        background-color: {BG_SURFACE};
        color: {TEXT_TITLE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 10px 16px;
        font-size: 13px;
        selection-background-color: {BLUE_ACCENT};
    }}
    QLineEdit#stitchSearch:focus {{
        border: 1.5px solid {BLUE_ACCENT};
        background-color: #ffffff;
    }}

    /* الزر الأساسي بأسلوب Stitch (Deep Elegant Slate) */
    QPushButton#btnStitchPrimary {{
        background-color: {PRIMARY_ACCENT};
        color: {PRIMARY_TEXT};
        border: 1px solid {PRIMARY_ACCENT};
        border-radius: 9px;
        padding: 9px 20px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton#btnStitchPrimary:hover {{
        background-color: {PRIMARY_HOVER};
        border-color: {PRIMARY_HOVER};
    }}
    QPushButton#btnStitchPrimary:pressed {{
        background-color: #020617;
    }}

    /* الأزرار الثانوية الشفافة والأنيقة */
    QPushButton#btnStitchSecondary {{
        background-color: {BG_SURFACE};
        color: {TEXT_BODY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 9px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#btnStitchSecondary:hover {{
        background-color: {BG_SURFACE_HOVER};
        border-color: #cbd5e1;
        color: {TEXT_TITLE};
    }}
    QPushButton#btnStitchSecondary:pressed {{
        background-color: #e2e8f0;
    }}

    /* أزرار التصفية الدائرية الناعمة (Filter Chips) */
    QPushButton#stitchChip {{
        background-color: {BG_SURFACE};
        color: {TEXT_MUTED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 16px;
        padding: 5px 14px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#stitchChip:hover {{
        background-color: {BG_SURFACE_HOVER};
        color: {TEXT_TITLE};
    }}
    QPushButton#stitchChip:checked {{
        background-color: #0f172a;
        color: #ffffff;
        border: 1px solid #0f172a;
        font-weight: 700;
    }}

    /* زر فتح الملف داخل البطاقة */
    QPushButton#btnCardAction {{
        background-color: {BLUE_ACCENT};
        color: #ffffff;
        border: none;
        border-radius: 8px;
        padding: 7px 16px;
        font-size: 12px;
        font-weight: 700;
    }}
    QPushButton#btnCardAction:hover {{
        background-color: #1d4ed8;
    }}

    /* شريط التمرير فائق النعومة */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #cbd5e1;
        min-height: 28px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #94a3b8;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* جدول العرض المنظم بأسلوب Stitch */
    QTableWidget {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
        gridline-color: #f8fafc;
        font-size: 13px;
    }}
    QHeaderView::section {{
        background-color: #f8fafc;
        color: {TEXT_MUTED};
        font-weight: 700;
        padding: 10px 14px;
        border: none;
        border-bottom: 1px solid {BORDER_SUBTLE};
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 10px 12px;
        border-bottom: 1px solid #f1f5f9;
    }}
    QTableWidget::item:selected {{
        background-color: #eff6ff;
        color: {BLUE_ACCENT};
    }}
    """

def apply_stitch_shadow(widget, blur=18, offset_y=4, alpha=10):
    """إضفاء تأثير الظل الدقيق والخفيف (Ambient Diffuse Shadow) المعتمد في Google Stitch"""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(15, 23, 42, alpha))
    shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)
