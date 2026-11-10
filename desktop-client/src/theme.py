"""
غرفة تجارة كربلاء المقدسة – منظومة التبادل السحابي للمستندات
Karbala Chamber of Commerce – File Exchange & Official Archiving System
نظام التصميم المؤسسي الهادئ والواضح (Clean Institutional Design System)
"""
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect
# لوحة الألوان الرسمية الموحدة والهادئة لغرفة تجارة كربلاء المقدسة
GOV_GREEN = "#14372e"          # الأخضر المؤسسي الرسمي
GOV_GREEN_HOVER = "#1b493d"
GOV_GREEN_DARK = "#0e2720"
GOV_GREEN_LIGHT = "#EDF5F2"
GOV_GOLD = "#c59b27"           # الذهبي الرسمي للاعتماد والتمييز الهادئ
GOV_GOLD_HOVER = "#b08920"
GOV_GOLD_LIGHT = "#fdfaf3"
BG_CANVAS = "#F7F8FA"          # خلفية التطبيق الأساسية (رمادي فاتح جداً ومريح للعين)
BG_SURFACE = "#FFFFFF"         # سطح البطاقات والجداول والقوائم
BG_SURFACE_HOVER = "#F9FAFB"
BORDER_SUBTLE = "#E4E7EC"      # حدود ناعمة وواضحة بعرض 1px
BORDER_FOCUS = "#14372e"       # إطار التركيز الرسمي
TEXT_TITLE = "#1B1F24"         # النص الأساسي والعناوين وأسماء الملفات (تباين عالٍ)
TEXT_BODY = "#1B1F24"          # نصوص المحتوى والمستندات
TEXT_MUTED = "#667085"         # النص الثانوي (التواريخ، الأحجام، المسارات)
# ألوان الحالات الدلالية الواضحة
STATUS_SYNCED = "#12B76A"      # أخضر واضح للمزامنة المكتملة
STATUS_SYNCED_BG = "#EDF5F2"
STATUS_SYNCED_BORDER = "#A6F4C5"
STATUS_SYNCING = "#F79009"     # برتقالي هادئ للمزامنة الجارية
STATUS_SYNCING_BG = "#FFFAEB"
STATUS_SYNCING_BORDER = "#FEDF89"
STATUS_LOCKED = "#F04438"      # أحمر واضح للحذف أو التنبيه
STATUS_LOCKED_BG = "#FEF3F2"
STATUS_LOCKED_BORDER = "#FECDCA"
# ألوان أيقونات وصيغ الملفات القياسية
COLOR_WORD = "#2B579A"
COLOR_EXCEL = "#217346"
COLOR_ACCESS = "#A4373A"
COLOR_PDF = "#E5252A"
# ألوان وتصنيفات درجات التجار والأصناف (المطابقة لـ web-dashboard)
COLOR_EXCELLENT = "#B45309"      # ⭐ ممتاز (amber-700)
BG_EXCELLENT = "#FFFBEB"         # amber-50
BORDER_EXCELLENT = "#FCD34D"     # amber-300
COLOR_FIRST = "#065F46"          # 🥇 درجة أولى (emerald-800)
BG_FIRST = "#ECFDF5"             # emerald-50
BORDER_FIRST = "#6EE7B7"         # emerald-300
COLOR_SECOND = "#1E40AF"         # 🥈 درجة ثانية (blue-800)
BG_SECOND = "#EFF6FF"            # blue-50
BORDER_SECOND = "#93C5FD"        # blue-300
COLOR_THIRD = "#6B21A8"          # 🥉 درجة ثالثة (purple-800)
BG_THIRD = "#FAF5FF"             # purple-50
BORDER_THIRD = "#D8B4FE"         # purple-300
COLOR_FOURTH = "#334155"         # 4️⃣ درجة رابعة (slate-700)
BG_FOURTH = "#F1F5F9"            # slate-100
BORDER_FOURTH = "#CBD5E1"        # slate-300
COLOR_CARD_PHONE = "#027A48"     # أخضر الاتصال الفوري
BG_CARD_PHONE = "#ECFDF5"
BORDER_CARD_PHONE = "#A6F4C5"
def get_gov_stylesheet():
    """كود التنسيق الشامل للواجهة المؤسسية النظيفة والواضحة"""
    return f"""
    QMainWindow {{
        background-color: {BG_CANVAS};
    }}
    QWidget {{
        font-family: 'Segoe UI', 'Cairo', 'IBM Plex Sans Arabic', Tahoma, sans-serif;
    }}
    QLabel {{
        color: {TEXT_TITLE};
    }}
    /* شريط البحث المكتبي الواضح */
    QLineEdit#govSearch {{
        background-color: {BG_CANVAS};
        color: {TEXT_TITLE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 7px;
        padding: 5px 12px;
        font-size: 12.5px;
        selection-background-color: {GOV_GREEN};
    }}
    QLineEdit#govSearch:focus {{
        border: 1px solid {GOV_GREEN};
        background-color: #FFFFFF;
    }}
    /* الزر الرئيسي الرسمي (الأخضر المؤسسي) */
    QPushButton#btnGovPrimary {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
        border: 1px solid {GOV_GREEN};
        border-radius: 7px;
        padding: 5px 12px;
        font-size: 12px;
        font-weight: 600;
        min-width: 65px;
    }}
    QPushButton#btnGovPrimary:hover {{
        background-color: {GOV_GREEN_HOVER};
        border-color: {GOV_GREEN_HOVER};
    }}
    QPushButton#btnGovPrimary:pressed {{
        background-color: {GOV_GREEN_DARK};
    }}
    /* الأزرار الثانوية المسطحة والنظيفة */
    QPushButton#btnGovSecondary {{
        background-color: {BG_SURFACE};
        color: {TEXT_TITLE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 7px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 600;
        min-width: 50px;
    }}
    QPushButton#btnGovSecondary:hover {{
        background-color: {BG_CANVAS};
        border-color: #CBD5E1;
    }}
    QPushButton#btnGovSecondary:pressed {{
        background-color: #EDF0F5;
    }}
    /* زر الإعدادات في شريط الحالة */
    QPushButton#btnGovSettings {{
        background: transparent;
        color: {TEXT_MUTED};
        border: none;
        padding: 2px 4px;
        font-size: 13px;
    }}
    QPushButton#btnGovSettings:hover {{
        color: {TEXT_TITLE};
    }}
    /* تبويبات التصفية بشكل كبسولات حديثة متطابقة 100% مع واجهة الويب */
    QPushButton#govTab {{
        background-color: {BG_CANVAS};
        color: {TEXT_MUTED};
        border: none;
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#govTab:hover {{
        background-color: #EEF0F3;
        color: {TEXT_TITLE};
    }}
    QPushButton#govTab:checked {{
        color: #FFFFFF;
        background-color: {GOV_GREEN};
        font-weight: 700;
        border: none;
    }}
    /* جدول المستندات والبيانات مطابق لمنصة الويب 100% */
    QTableWidget {{
        background-color: #FFFFFF;
        alternate-background-color: #FFFFFF;
        border: 1px solid #E4E7EC;
        border-radius: 12px;
        gridline-color: transparent;
        font-size: 12.5px;
        outline: none;
        selection-background-color: #F9FAFB;
        selection-color: #14372e;
    }}
    QHeaderView::section {{
        background-color: #F7F8FA;
        color: #667085;
        font-weight: 600;
        padding: 10px 14px;
        border: none;
        border-bottom: 1px solid #E4E7EC;
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 8px 12px;
        border-bottom: 1px solid #E4E7EC;
    }}
    QTableWidget::item:selected {{
        background-color: #F9FAFB;
        color: #14372e;
    }}
    QTableWidget::item:hover {{
        background-color: #F7F8FA;
    }}
    /* محدد أسلوب العرض (قائمة / شبكة / مدمج) */
    QFrame#viewSwitcherFrame {{
        background-color: {BG_CANVAS};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 2px;
    }}
    QPushButton#btnViewMode {{
        background-color: transparent;
        color: {TEXT_MUTED};
        border: none;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#btnViewMode:hover {{
        color: {TEXT_TITLE};
    }}
    QPushButton#btnViewMode:checked {{
        background-color: {BG_SURFACE};
        color: {GOV_GREEN};
        font-weight: 700;
    }}
    /* حاويات منطقة العرض المخصصة للبطاقات والقوائم */
    QScrollArea#govScrollArea {{
        background-color: transparent;
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        outline: none;
    }}
    QWidget#govScrollContent {{
        background-color: transparent;
    }}
    /* بطاقة المستند (Grid Card) */
    QFrame#govCard {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
    }}
    QFrame#govCard:hover {{
        border: 1px solid {GOV_GREEN};
        background-color: #FFFFFF;
    }}
    QPushButton#btnCardOpen {{
        background-color: {GOV_GREEN_LIGHT};
        color: {GOV_GREEN};
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 5px 14px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#btnCardOpen:hover {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
    }}
    /* البلاطة المدمجة (Compact Tile) */
    QFrame#govCompactTile {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
    }}
    QFrame#govCompactTile:hover {{
        background-color: {BG_SURFACE_HOVER};
        border: 1px solid {GOV_GREEN};
    }}
    QPushButton#btnTileOpen {{
        background-color: {GOV_GREEN_LIGHT};
        color: {GOV_GREEN};
        border: none;
        border-radius: 6px;
        padding: 4px 12px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#btnTileOpen:hover {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
    }}
    /* شريط المسار والتنقل بين المجلدات (Breadcrumb Bar) */
    QFrame#breadcrumbFrame {{
        background-color: #FFFFFF;
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 7px;
        padding: 2px 8px;
    }}
    QPushButton#btnBreadcrumbUp {{
        background-color: {BG_CANVAS};
        color: {TEXT_TITLE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 5px;
        padding: 3px 10px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#btnBreadcrumbUp:hover {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
        border-color: {GOV_GREEN};
    }}
    QPushButton#btnBreadcrumbUp:disabled {{
        background-color: {BG_CANVAS};
        color: #98A2B3;
        border-color: {BORDER_SUBTLE};
    }}
    /* قسم إدارة وحذف الملفات (سلة المحذوفات) */
    QFrame#trashHeaderFrame {{
        background-color: #FFFFFF;
        border: 1px solid {STATUS_LOCKED_BORDER};
        border-right: 3px solid {STATUS_LOCKED};
        border-radius: 8px;
        padding: 10px 16px;
    }}
    QPushButton#btnTrashRestore {{
        background-color: {STATUS_SYNCED_BG};
        color: {GOV_GREEN};
        border: 1px solid {STATUS_SYNCED_BORDER};
        border-radius: 6px;
        padding: 5px 12px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#btnTrashRestore:hover {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
    }}
    QPushButton#btnTrashPurge {{
        background-color: {STATUS_LOCKED_BG};
        color: {STATUS_LOCKED};
        border: 1px solid {STATUS_LOCKED_BORDER};
        border-radius: 6px;
        padding: 5px 12px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#btnTrashPurge:hover {{
        background-color: {STATUS_LOCKED};
        color: #FFFFFF;
    }}
    QPushButton#btnEmptyTrash {{
        background-color: {STATUS_LOCKED_BG};
        color: {STATUS_LOCKED};
        border: 1px solid {STATUS_LOCKED_BORDER};
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#btnEmptyTrash:hover {{
        background-color: {STATUS_LOCKED};
        color: #FFFFFF;
    }}
    /* شرائح اقتراح أسماء المجلدات */
    QPushButton#btnSuggestionChip {{
        background-color: {BG_CANVAS};
        color: {TEXT_TITLE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11.5px;
        font-weight: 500;
    }}
    QPushButton#btnSuggestionChip:hover {{
        background-color: {GOV_GREEN_LIGHT};
        color: {GOV_GREEN};
        border-color: {GOV_GREEN};
    }}
    /* زر التبديل للقائمة الجانبية للأقسام */
    QPushButton#btnToggleSidebar {{
        background-color: {BG_SURFACE};
        color: {TEXT_TITLE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 7px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#btnToggleSidebar:hover {{
        background-color: {BG_CANVAS};
        border-color: {GOV_GREEN};
    }}
    QPushButton#btnToggleSidebar:checked {{
        background-color: {GOV_GREEN_LIGHT};
        color: {GOV_GREEN};
        border-color: {GOV_GREEN};
        font-weight: 700;
    }}
    /* القائمة الجانبية لأقسام الدائرة */
    QFrame#sidebarFrame {{
        background-color: #FFFFFF;
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 4px;
    }}
    QFrame#sidebarHeaderFrame {{
        background-color: {BG_CANVAS};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 6px;
        padding: 4px 6px;
    }}
    QPushButton#btnAddDept {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
        border: none;
        border-radius: 5px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#btnAddDept:hover {{
        background-color: {GOV_GREEN_HOVER};
    }}
    QPushButton#btnCloseSidebar {{
        background-color: transparent;
        color: {TEXT_MUTED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 4px;
        padding: 1px 6px;
        font-size: 10.5px;
        font-weight: 600;
    }}
    QPushButton#btnCloseSidebar:hover {{
        background-color: {STATUS_LOCKED_BG};
        border-color: {STATUS_LOCKED_BORDER};
        color: {STATUS_LOCKED};
    }}
    QListWidget#deptList {{
        background: transparent;
        border: none;
        outline: none;
    }}
    QListWidget#deptList::item {{
        background-color: #FFFFFF;
        color: {TEXT_TITLE};
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 6px 8px;
        margin-bottom: 2px;
        font-size: 12px;
        font-weight: 600;
    }}
    QListWidget#deptList::item:hover {{
        background-color: {BG_CANVAS};
        color: {GOV_GREEN};
    }}
    QListWidget#deptList::item:selected {{
        background-color: {GOV_GREEN_LIGHT};
        color: {GOV_GREEN};
        border: 1px solid #CBE3DA;
        border-right: 3px solid {GOV_GREEN};
        font-weight: 700;
    }}
    /* أزرار تعديل الاسم وإعادة التسمية للمستندات والمجلدات */
    QPushButton#btnCardRename, QPushButton#btnTileRename, QPushButton#btnTableRename {{
        background-color: {BG_CANVAS};
        color: {TEXT_MUTED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#btnCardRename:hover, QPushButton#btnTileRename:hover, QPushButton#btnTableRename:hover {{
        background-color: {GOV_GREEN_LIGHT};
        color: {GOV_GREEN};
        border-color: {GOV_GREEN};
    }}
    /* أزرار الحذف للمستندات والمجلدات */
    QPushButton#btnCardDelete, QPushButton#btnTileDelete, QPushButton#btnTableDelete {{
        background-color: #FFFFFF;
        color: {STATUS_LOCKED};
        border: 1px solid {STATUS_LOCKED_BORDER};
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QPushButton#btnCardDelete:hover, QPushButton#btnTileDelete:hover, QPushButton#btnTableDelete:hover {{
        background-color: {STATUS_LOCKED};
        color: #FFFFFF;
        border-color: {STATUS_LOCKED};
    }}
    /* شريط التمرير */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #D0D5DD;
        min-height: 28px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #98A2B3;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    /* شريط تمرير الحقول العرضي التفاعلي (Access Hub Field Navigation) */
    QFrame#horizontalFieldNavBar {{
        background-color: #EDF2EF;
        border-top: 1px solid #D0D5DD;
        border-bottom: 1px solid #D0D5DD;
        border-radius: 6px;
        padding: 3px 6px;
    }}
    QPushButton#btnScrollField {{
        background-color: #FFFFFF;
        color: #344054;
        border: 1px solid #D0D5DD;
        border-radius: 5px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnScrollField:hover {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
        border-color: {GOV_GREEN};
    }}
    QSlider#fieldRangeSlider::groove:horizontal {{
        height: 8px;
        background: #D0D5DD;
        border-radius: 4px;
    }}
    QSlider#fieldRangeSlider::sub-page:horizontal {{
        background: {GOV_GREEN};
        border-radius: 4px;
    }}
    QSlider#fieldRangeSlider::handle:horizontal {{
        background: {GOV_GREEN};
        border: 2px solid {GOV_GOLD};
        width: 22px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 6px;
    }}
    QSlider#fieldRangeSlider::handle:horizontal:hover {{
        background: {GOV_GOLD};
    }}
    /* بطاقة قيد مركز Access الذكية (Access Hub Record Card) */
    QFrame#accessRecordCard {{
        background-color: #FFFFFF;
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
    }}
    QFrame#accessRecordCard:hover {{
        border: 1px solid {GOV_GREEN};
        background-color: #FFFFFF;
    }}
    QLabel#cardRecordNum {{
        background-color: #F2F4F7;
        color: #667085;
        font-weight: bold;
        font-size: 10.5px;
        padding: 2px 6px;
        border-radius: 4px;
    }}
    QLabel#cardRecordFileBadge {{
        background-color: #EDF5F2;
        color: {GOV_GREEN};
        font-weight: 600;
        font-size: 10.5px;
        padding: 2px 6px;
        border-radius: 4px;
        border: 1px solid #CBE3DA;
    }}
    QLabel#cardRecordTableBadge {{
        background-color: #FFFBEB;
        color: #92400E;
        font-weight: 700;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        border: 1px solid #FCD34D;
    }}
    QLabel#cardRecordDateBadge {{
        color: #667085;
        font-size: 10px;
        font-family: 'Segoe UI', Tahoma, sans-serif;
    }}
    QLabel#cardRecordName {{
        color: {GOV_GREEN};
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#cardRecordCommercial {{
        color: #344054;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QLabel#cardRecordActivity {{
        color: #475467;
        font-size: 11px;
    }}
    QLabel#cardRecordAddress {{
        color: #667085;
        font-size: 10.5px;
    }}
    QPushButton#btnCardCall {{
        background-color: #ECFDF5;
        color: #065F46;
        border: 1px solid #A6F4C5;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#btnCardCall:hover {{
        background-color: #D1FAE5;
        border-color: #34D399;
    }}
    QPushButton#btnCardQuickAction {{
        background-color: #FFFFFF;
        color: #344054;
        border: 1px solid #E4E7EC;
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 11px;
    }}
    QPushButton#btnCardQuickAction:hover {{
        background-color: #F2F4F7;
        color: {GOV_GREEN};
    }}
    /* شارات الأصناف (Category Pills with Count) */
    QPushButton#btnCategoryPill {{
        background-color: #FFFFFF;
        color: #344054;
        border: 1px solid #E4E7EC;
        border-radius: 10px;
        padding: 4px 10px;
        font-size: 11.5px;
        font-weight: 700;
    }}
    QPushButton#btnCategoryPill:hover {{
        background-color: #F2F4F7;
        color: {GOV_GREEN};
    }}
    QPushButton#btnCategoryPill:checked {{
        background-color: {GOV_GREEN};
        color: #FFFFFF;
        border: 1px solid {GOV_GREEN};
    }}
    /* نافذة تفاصيل الرفع وسرعة النقل */
    QProgressBar#uploadProgressBar {{
        background-color: #EDF2EF;
        border: 1px solid #D0D5DD;
        border-radius: 6px;
        height: 14px;
        text-align: center;
        font-size: 10px;
        font-weight: bold;
        color: #1B1F24;
    }}
    QProgressBar#uploadProgressBar::chunk {{
        background-color: {GOV_GREEN};
        border-radius: 5px;
    }}
    """
def apply_gov_shadow(widget, blur=16, offset_y=3, alpha=15):
    """
    ملاحظة هندسية: تم تعطيل QGraphicsDropShadowEffect المتداخل في PyQt6
    لأنه يسبب بطئاً شديداً في الرسم (Software Gaussian Blur) وتوقفاً مفاجئاً (Painter Crash)
    عند التمرير السريع أو تحديث الجداول والبطاقات. يُستعاض عنه بإطارات CSS نظيفة وسريعة.
    """
    return
