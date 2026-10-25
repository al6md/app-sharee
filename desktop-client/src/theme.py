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
        padding: 8px 12px;
        font-size: 12px;
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

    /* محدد أسلوب العرض (جدول تفصيلي / بطاقات / قائمة مدمجة) */
    QFrame#viewSwitcherFrame {{
        background-color: #eaefed;
        border: 1px solid #d0ded8;
        border-radius: 8px;
        padding: 2px;
    }}
    QPushButton#btnViewMode {{
        background-color: transparent;
        color: {TEXT_MUTED};
        border: none;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#btnViewMode:hover {{
        background-color: #dce7e3;
        color: {GOV_GREEN};
    }}
    QPushButton#btnViewMode:checked {{
        background-color: {GOV_GREEN};
        color: #ffffff;
        font-weight: 700;
    }}

    /* حاويات منطقة العرض المخصصة للبطاقات والقوائم */
    QScrollArea#govScrollArea {{
        background-color: transparent;
        border: 1.5px solid {BORDER_SUBTLE};
        border-radius: 10px;
        outline: none;
    }}
    QWidget#govScrollContent {{
        background-color: transparent;
    }}

    /* بطاقة المستند الحكومية (Grid Card) */
    QFrame#govCard {{
        background-color: {BG_SURFACE};
        border: 1.5px solid {BORDER_SUBTLE};
        border-radius: 12px;
    }}
    QFrame#govCard:hover {{
        border: 1.5px solid {GOV_GREEN};
        background-color: #fbfdfc;
    }}
    QPushButton#btnCardOpen {{
        background-color: #f0f6f4;
        color: {GOV_GREEN};
        border: 1px solid #c8d9d2;
        border-radius: 6px;
        padding: 5px 14px;
        font-size: 11.5px;
        font-weight: 700;
    }}
    QPushButton#btnCardOpen:hover {{
        background-color: {GOV_GREEN};
        color: #ffffff;
        border-color: {GOV_GREEN};
    }}

    /* البلاطة المدمجة (Compact Tile) */
    QFrame#govCompactTile {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
    }}
    QFrame#govCompactTile:hover {{
        background-color: #f4f8f6;
        border: 1px solid {GOV_GREEN};
    }}
    QPushButton#btnTileOpen {{
        background-color: #f0f6f4;
        color: {GOV_GREEN};
        border: 1px solid #cbdcd5;
        border-radius: 6px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnTileOpen:hover {{
        background-color: {GOV_GREEN};
        color: #ffffff;
        border-color: {GOV_GREEN};
    }}

    /* شريط المسار والتنقل بين المجلدات (Breadcrumb Bar) */
    QFrame#breadcrumbFrame {{
        background-color: #ffffff;
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 4px 12px;
    }}
    QPushButton#btnBreadcrumbUp {{
        background-color: #f0f6f4;
        color: {GOV_GREEN};
        border: 1px solid #c2d3cc;
        border-radius: 6px;
        padding: 5px 12px;
        font-size: 11.5px;
        font-weight: 700;
    }}
    QPushButton#btnBreadcrumbUp:hover {{
        background-color: {GOV_GREEN};
        color: #ffffff;
        border-color: {GOV_GREEN};
    }}
    QPushButton#btnBreadcrumbUp:disabled {{
        background-color: #f8fafc;
        color: #94a3b8;
        border-color: #e2e8f0;
    }}

    /* قسم إدارة وحذف الملفات (سلة المحذوفات) */
    QFrame#trashHeaderFrame {{
        background-color: #ffffff;
        border: 1.5px solid #fecaca;
        border-right: 4px solid #dc2626;
        border-radius: 8px;
        padding: 12px 18px;
    }}
    QPushButton#btnTrashRestore {{
        background-color: #eaf7f0;
        color: #0d8a55;
        border: 1px solid #a8dfc4;
        border-radius: 6px;
        padding: 5px 12px;
        font-size: 11.5px;
        font-weight: 700;
    }}
    QPushButton#btnTrashRestore:hover {{
        background-color: #0d8a55;
        color: #ffffff;
    }}
    QPushButton#btnTrashPurge {{
        background-color: #fef2f2;
        color: #dc2626;
        border: 1px solid #fecaca;
        border-radius: 6px;
        padding: 5px 12px;
        font-size: 11.5px;
        font-weight: 700;
    }}
    QPushButton#btnTrashPurge:hover {{
        background-color: #dc2626;
        color: #ffffff;
    }}
    QPushButton#btnEmptyTrash {{
        background-color: #fee2e2;
        color: #991b1b;
        border: 1px solid #fca5a5;
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 12px;
        font-weight: 700;
    }}
    QPushButton#btnEmptyTrash:hover {{
        background-color: #dc2626;
        color: #ffffff;
    }}

    /* شرائح اقتراح أسماء المجلدات الحكومية */
    QPushButton#btnSuggestionChip {{
        background-color: #f0f6f4;
        color: {GOV_GREEN};
        border: 1px solid #cbdcd5;
        border-radius: 14px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#btnSuggestionChip:hover {{
        background-color: {GOV_GREEN};
        color: #ffffff;
        border-color: {GOV_GREEN};
    }}

    /* زر التبديل للقائمة الجانبية للأقسام (Hamburger Button ☰) */
    QPushButton#btnToggleSidebar {{
        background-color: #f0f6f4;
        color: {GOV_GREEN};
        border: 1.5px solid #c2d5cd;
        border-radius: 7px;
        padding: 7px 14px;
        font-size: 12.5px;
        font-weight: 700;
    }}
    QPushButton#btnToggleSidebar:hover {{
        background-color: {GOV_GREEN};
        color: #ffffff;
        border-color: {GOV_GREEN};
    }}
    QPushButton#btnToggleSidebar:checked {{
        background-color: {GOV_GREEN};
        color: #f7e6a7;
        border-color: {GOV_GOLD};
        font-weight: 800;
    }}

    /* القائمة الجانبية لأقسام الدائرة */
    QFrame#sidebarFrame {{
        background-color: #ffffff;
        border: 1.5px solid {BORDER_SUBTLE};
        border-radius: 12px;
        padding: 6px;
    }}
    QFrame#sidebarHeaderFrame {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14372e, stop:1 #1c4d40);
        border-radius: 8px;
        padding: 7px 10px;
    }}
    QPushButton#btnAddDept {{
        background-color: #fdfaf3;
        color: #855f0b;
        border: 1px solid #e9d59f;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnAddDept:hover {{
        background-color: #c59b27;
        color: #ffffff;
        border-color: #c59b27;
    }}
    QPushButton#btnCloseSidebar {{
        background-color: rgba(255, 255, 255, 0.15);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.25);
        border-radius: 4px;
        padding: 2px 7px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton#btnCloseSidebar:hover {{
        background-color: #dc2626;
        border-color: #dc2626;
        color: #ffffff;
    }}
    QListWidget#deptList {{
        background: transparent;
        border: none;
        outline: none;
    }}
    QListWidget#deptList::item {{
        background-color: #f8faf9;
        color: #162420;
        border: 1px solid #e2ece8;
        border-radius: 8px;
        padding: 8px 10px;
        margin-bottom: 4px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QListWidget#deptList::item:hover {{
        background-color: #eaf3f0;
        border-color: #14372e;
        color: #14372e;
    }}
    QListWidget#deptList::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14372e, stop:1 #1b473b);
        color: #ffffff;
        border: 1px solid #0e2720;
        border-right: 4px solid #c59b27;
    }}

    /* أزرار تعديل الاسم وإعادة التسمية للمستندات والمجلدات */
    QPushButton#btnCardRename, QPushButton#btnTileRename {{
        background-color: #f0fdf4;
        color: #166534;
        border: 1px solid #bbf7d0;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnCardRename:hover, QPushButton#btnTileRename:hover {{
        background-color: #166534;
        color: #ffffff;
        border-color: #166534;
    }}
    QPushButton#btnTableRename {{
        background-color: #f0fdf4;
        color: #166534;
        border: 1px solid #bbf7d0;
        border-radius: 5px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnTableRename:hover {{
        background-color: #166534;
        color: #ffffff;
    }}

    /* أزرار الحذف السريع للمستندات والمجلدات */
    QPushButton#btnCardDelete, QPushButton#btnTileDelete {{
        background-color: #fef2f2;
        color: #dc2626;
        border: 1px solid #fecaca;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnCardDelete:hover, QPushButton#btnTileDelete:hover {{
        background-color: #dc2626;
        color: #ffffff;
        border-color: #dc2626;
    }}
    QPushButton#btnTableDelete {{
        background-color: #fef2f2;
        color: #dc2626;
        border: 1px solid #fecaca;
        border-radius: 5px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnTableDelete:hover {{
        background-color: #dc2626;
        color: #ffffff;
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
