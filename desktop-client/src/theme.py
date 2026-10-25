"""
غرفة تجارة كربلاء المقدسة – منظومة التبادل السحابي للمستندات
Karbala Chamber of Commerce – File Exchange & Official Archiving System
نظام التصميم الحكومي الرسمي والرصين (Official Institutional Theme)
"""
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect

# 🎨 لوحة الألوان الرسمية المعتمدة لغرفة تجارة كربلاء المقدسة
GOV_GREEN = "#14372e"          # الأخضر المؤسسي الداكن
GOV_GREEN_HOVER = "#1b473b"
GOV_GREEN_DARK = "#0e2720"
GOV_GREEN_LIGHT = "#f0f6f4"

GOV_GOLD = "#c59b27"           # الذهبي الدبلوماسي العريق
GOV_GOLD_HOVER = "#d4af37"
GOV_GOLD_LIGHT = "#fdfaf3"

BG_CANVAS = "#f4f7f6"          # خلفية إدارية هادئة وفاتحة ومريحة للعين
BG_SURFACE = "#ffffff"         # بياض ناصع للبطاقات والجداول
BG_SURFACE_HOVER = "#f8fbf9"

BORDER_SUBTLE = "#d5dfdb"      # إطارات ناعمة وأنيقة
BORDER_FOCUS = "#14372e"       # إطار التركيز الرسمي

TEXT_TITLE = "#162420"         # نصوص العناوين الرسمية
TEXT_BODY = "#2d3d38"          # نصوص المحتوى والمستندات
TEXT_MUTED = "#566c65"         # نصوص التفاصيل والمعلومات الثانوية

# ألوان الحالات الرسمية
STATUS_SYNCED = "#0d8a55"      # أخضر وقائي هادئ
STATUS_SYNCED_BG = "#eaf7f0"
STATUS_SYNCED_BORDER = "#a8dfc4"

STATUS_SYNCING = "#b45309"     # كهرماني رصين
STATUS_SYNCING_BG = "#fffbeb"
STATUS_SYNCING_BORDER = "#fde68a"

STATUS_LOCKED = "#a33820"      # أحمر تأميني وقائي
STATUS_LOCKED_BG = "#fdf2ef"
STATUS_LOCKED_BORDER = "#f8c9bd"

# ألوان برامج Office الرسمية
COLOR_WORD = "#185abd"
COLOR_EXCEL = "#107c41"
COLOR_ACCESS = "#a4373a"
COLOR_PDF = "#d9381e"

def get_gov_stylesheet():
    """كود التنسيق الشامل للواجهة الحكومية الرسمية"""
    return f"""
    QMainWindow {{
        background-color: {BG_CANVAS};
    }}
    QWidget {{
        font-family: 'Segoe UI', 'Cairo', Tahoma, sans-serif;
    }}
    QLabel {{
        color: {TEXT_TITLE};
    }}

    /* شريط البحث المكتبي الرصين */
    QLineEdit#govSearch {{
        background-color: {BG_SURFACE};
        color: {TEXT_TITLE};
        border: 1.5px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 9px 16px;
        font-size: 13px;
        selection-background-color: {GOV_GREEN};
    }}
    QLineEdit#govSearch:focus {{
        border: 1.5px solid {GOV_GREEN};
        background-color: #ffffff;
    }}

    /* الزر الرئيسي الرسمي (الأخضر المؤسسي) */
    QPushButton#btnGovPrimary {{
        background-color: {GOV_GREEN};
        color: #ffffff;
        border: 1px solid #0c231c;
        border-radius: 7px;
        padding: 9px 22px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton#btnGovPrimary:hover {{
        background-color: {GOV_GREEN_HOVER};
        box-shadow: 0 2px 6px rgba(20, 55, 46, 0.2);
    }}
    QPushButton#btnGovPrimary:pressed {{
        background-color: {GOV_GREEN_DARK};
    }}

    /* الأزرار الثانوية الرسمية */
    QPushButton#btnGovSecondary {{
        background-color: {BG_SURFACE};
        color: {GOV_GREEN};
        border: 1.5px solid #c2d3cc;
        border-radius: 7px;
        padding: 8px 18px;
        font-size: 12.5px;
        font-weight: 700;
    }}
    QPushButton#btnGovSecondary:hover {{
        background-color: {GOV_GREEN_LIGHT};
        border-color: {GOV_GREEN};
    }}
    QPushButton#btnGovSecondary:pressed {{
        background-color: #e2ede8;
    }}

    /* زر الإعدادات المكتوم في شريط الحالة */
    QPushButton#btnGovSettings {{
        background: transparent;
        color: {TEXT_MUTED};
        border: none;
        padding: 4px;
        font-size: 14px;
    }}
    QPushButton#btnGovSettings:hover {{
        color: {TEXT_TITLE};
    }}

    /* تبويبات التصنيف الرسمية */
    QPushButton#govTab {{
        background-color: transparent;
        color: {TEXT_MUTED};
        border: none;
        border-bottom: 3px solid transparent;
        padding: 10px 18px;
        font-size: 12.5px;
        font-weight: 600;
    }}
    QPushButton#govTab:hover {{
        color: {GOV_GREEN};
    }}
    QPushButton#govTab:checked {{
        color: {GOV_GREEN};
        border-bottom: 3px solid {GOV_GOLD};
        font-weight: 800;
        background-color: #ffffff;
    }}

    /* جدول المستندات الحكومي الرصين */
    QTableWidget {{
        background-color: {BG_SURFACE};
        border: 1.5px solid {BORDER_SUBTLE};
        border-radius: 10px;
        gridline-color: #f1f5f3;
        font-size: 13px;
        outline: none;
    }}
    QHeaderView::section {{
        background-color: #eef3f1;
        color: {GOV_GREEN};
        font-weight: 800;
        padding: 12px 16px;
        border: none;
        border-bottom: 2px solid {BORDER_SUBTLE};
        font-size: 12.5px;
    }}
    QTableWidget::item {{
        padding: 12px 14px;
        border-bottom: 1px solid #edf3f0;
    }}
    QTableWidget::item:selected {{
        background-color: #f0f6f4;
        color: {GOV_GREEN};
    }}

    /* شريط التمرير */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #cbd8d3;
        min-height: 28px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #9ab3aa;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """

def apply_gov_shadow(widget, blur=16, offset_y=3, alpha=15):
    """إضفاء تأثير الظل الهادئ والوقور"""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(20, 55, 46, alpha))
    shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)
