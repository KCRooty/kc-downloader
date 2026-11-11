"""Tema: paleta clara/oscura + color de acento, aplicado con QSS sobre Fusion."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    surface: str
    surface2: str
    border: str
    text: str
    dim: str
    ok: str
    warn: str
    err: str


DARK = Palette(True, "#0E1014", "#161920", "#1D212A", "#2A2F3A", "#E7E9EE", "#8D93A3",
               "#3DD68C", "#F5B544", "#F06A6A")
LIGHT = Palette(False, "#F3F4F7", "#FFFFFF", "#F7F8FA", "#DCDFE6", "#1A1D24", "#616878",
                "#178A55", "#B7791F", "#C53030")


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return QApplication.palette().window().color().lightness() < 128


def resolve(theme: str) -> Palette:
    if theme == "dark":
        return DARK
    if theme == "light":
        return LIGHT
    return DARK if system_is_dark() else LIGHT


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def on_accent(accent: str) -> str:
    """Texto legible encima del acento."""
    c = QColor(accent)
    lum = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return "#0B0D10" if lum > 0.55 else "#FFFFFF"


_ICONS = {
    "down": '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
            '<path d="M3 4.5l3 3 3-3" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round"/></svg>',
    "up": '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
          '<path d="M3 7.5l3-3 3 3" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" '
          'stroke-linejoin="round"/></svg>',
    "check": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
             '<path d="M3 7.2l2.6 2.6L11 4.4" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"/></svg>',
}


def _icons(text: str, check: str) -> dict[str, str]:
    """QSS solo acepta imágenes de archivo: se generan con los colores del tema."""
    from .. import paths
    d = paths.data_dir() / "theme"
    d.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, svg in _ICONS.items():
        col = check if name == "check" else text
        f = d / f"{name}-{col.lstrip('#')}.svg"
        if not f.is_file():
            f.write_text(svg.replace("{c}", col), encoding="utf-8")
        out[name] = f.as_posix()
    return out


def apply(app: QApplication, theme: str, accent: str, font_size: int) -> Palette:
    p = resolve(theme)
    accent = QColor(accent).name() if QColor(accent).isValid() else "#7B61FF"
    ic = _icons(p.dim, on_accent(accent))
    app.setStyle("Fusion")

    pal = QPalette()
    for role, col in ((QPalette.Window, p.bg), (QPalette.WindowText, p.text), (QPalette.Base, p.surface),
                      (QPalette.AlternateBase, p.surface2), (QPalette.Text, p.text), (QPalette.Button, p.surface2),
                      (QPalette.ButtonText, p.text), (QPalette.ToolTipBase, p.surface2), (QPalette.ToolTipText, p.text),
                      (QPalette.Highlight, accent), (QPalette.HighlightedText, on_accent(accent)),
                      (QPalette.PlaceholderText, p.dim), (QPalette.Link, accent)):
        pal.setColor(role, QColor(col))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(p.dim))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p.dim))
    app.setPalette(pal)

    f = QFont(app.font())
    f.setPointSize(font_size)
    app.setFont(f)

    hover = _mix(p.surface2, p.text, 0.06)
    accent_hover = _mix(accent, "#FFFFFF" if p.dark else "#000000", 0.12)
    accent_soft = _mix(p.surface, accent, 0.16)
    sm, lg = font_size - 1, font_size + 6
    app.setStyleSheet(f"""
    QWidget {{ color: {p.text}; }}
    QMainWindow, QDialog {{ background: {p.bg}; }}
    QToolTip {{ background: {p.surface2}; color: {p.text}; border: 1px solid {p.border}; padding: 4px 6px; }}

    #Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
    #Title {{ font-size: {lg}pt; font-weight: 600; }}
    #Dim, QLabel[dim="true"] {{ color: {p.dim}; }}
    #Small {{ color: {p.dim}; font-size: {sm}pt; }}
    #SectionTitle {{ font-weight: 600; font-size: {font_size + 1}pt; }}

    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
        background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px;
        padding: 6px 8px; selection-background-color: {accent}; selection-color: {on_accent(accent)};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {accent}; }}
    QLineEdit#UrlInput {{ font-size: {font_size + 1}pt; padding: 10px 12px; border-radius: 10px; }}
    QComboBox {{ padding-right: 26px; }}
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 24px; }}
    QComboBox::down-arrow {{ image: url("{ic['down']}"); width: 12px; height: 12px; }}
    QSpinBox {{ padding-right: 24px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 22px; border: none; background: transparent; }}
    QSpinBox::up-button {{ subcontrol-position: top right; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QSpinBox::up-arrow {{ image: url("{ic['up']}"); width: 10px; height: 10px; }}
    QSpinBox::down-arrow {{ image: url("{ic['down']}"); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
        selection-background-color: {accent_soft}; selection-color: {p.text}; outline: 0; }}

    QPushButton, QToolButton {{
        background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px; padding: 6px 12px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {hover}; }}
    QPushButton:disabled {{ color: {p.dim}; }}
    QPushButton#Primary {{ background: {accent}; color: {on_accent(accent)}; border: none; font-weight: 600; padding: 8px 18px; }}
    QPushButton#Primary:hover {{ background: {accent_hover}; }}
    QPushButton#Primary:disabled {{ background: {_mix(accent, p.bg, 0.55)}; }}
    QPushButton#Ghost, QToolButton#Ghost {{ background: transparent; border: none; padding: 4px 8px; color: {p.dim}; }}
    QPushButton#Ghost:hover, QToolButton#Ghost:hover {{ color: {p.text}; background: {hover}; }}

    QPushButton#Segment {{ border-radius: 0; padding: 6px 16px; }}
    QPushButton#Segment[pos="first"] {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
    QPushButton#Segment[pos="last"] {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
    QPushButton#Segment:checked {{ background: {accent_soft}; border-color: {accent}; color: {p.text}; font-weight: 600; }}

    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p.border}; background: {p.surface2}; }}
    QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{ic['check']}"); }}
    QCheckBox {{ spacing: 8px; }}

    QProgressBar {{ background: {p.surface2}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
    QProgressBar[state="done"]::chunk {{ background: {p.ok}; }}
    QProgressBar[state="error"]::chunk {{ background: {p.err}; }}

    QListWidget {{ background: transparent; border: none; outline: 0; }}
    QListWidget::item {{ border: none; padding: 0; }}
    QListWidget::item:selected {{ background: transparent; }}
    QListWidget#Nav {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; padding: 6px; }}
    QListWidget#Nav::item {{ padding: 8px 12px; border-radius: 8px; }}
    QListWidget#Nav::item:selected {{ background: {accent_soft}; color: {p.text}; }}
    QListWidget#Nav::item:hover:!selected {{ background: {hover}; }}

    #JobRow {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
    #Badge {{ border-radius: 6px; padding: 2px 8px; font-size: {sm}pt; font-weight: 600; }}
    #StatusOk {{ color: {p.ok}; }} #StatusWarn {{ color: {p.warn}; }} #StatusErr {{ color: {p.err}; }}

    QTableWidget {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; gridline-color: {p.border}; }}
    QHeaderView::section {{ background: {p.surface2}; color: {p.dim}; border: none; border-bottom: 1px solid {p.border}; padding: 6px; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.dim}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """)
    return p


SOURCE_COLORS = {"youtube": "#FF3B30", "ytmusic": "#FF2D55", "spotify": "#1DB954", "pinterest": "#E60023"}
