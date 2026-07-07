# PyInstaller spec — onefile Windows build.
# Название .exe по имени git-репо: atomspectra-waterfall-esp32.exe
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()
FIRMWARE = ROOT / "firmware" / "atomspectra-waterfall-esp32"
ICON = ROOT / "assets" / "icon.ico"

_datas = []
for p in FIRMWARE.iterdir():
    if p.is_file():
        _datas.append((str(p), "firmware/atomspectra-waterfall-esp32"))

_esp_datas, _esp_bin, _esp_hidden = collect_all("esptool")
_qt_datas, _qt_bin, _qt_hidden = collect_all("PySide6")

# Модули PySide6 не нужны Flasher-у: только QtCore/QtGui/QtWidgets.
_QT_MODULE_EXCLUDES = [
    "WebEngineCore", "WebEngineWidgets", "WebEngineQuick",
    "WebChannel", "WebSockets", "WebView", "NetworkAuth",
    "Qml", "Quick", "Quick3D", "QuickWidgets", "QuickControls2",
    "QuickEffects", "QuickLayouts", "QuickParticles", "QuickShapes",
    "QuickTest", "QuickTimeline", "QuickVectorImage",
    "Multimedia", "MultimediaWidgets", "MultimediaQuick",
    "Charts", "ChartsQml", "DataVisualization", "DataVisualizationQml",
    "Graphs", "GraphsWidgets", "Pdf", "PdfWidgets", "PdfQuick",
    "Sql", "Bluetooth", "Positioning", "PositioningQuick",
    "3DCore", "3DRender", "3DAnimation", "3DInput", "3DLogic", "3DExtras",
    "Sensors", "SensorsQuick", "SerialBus", "SerialPort",
    "RemoteObjects", "RemoteObjectsQml", "Test", "Designer",
    "DesignerComponents", "SvgWidgets", "OpenGL", "OpenGLWidgets",
    "Help", "HttpServer", "SpatialAudio",
    "StateMachine", "StateMachineQml", "TextToSpeech",
    "Scxml", "ScxmlQml", "Location", "Nfc",
    "PrintSupport", "UiTools", "VirtualKeyboard", "VirtualKeyboardQml",
    "VirtualKeyboardSettings", "CanvasPainter", "Concurrent",
    "Lottie", "LottieVectorImageGenerator", "LottieVectorImageHelpers",
    "LabsAnimation", "LabsFolderListModel", "LabsPlatform",
    "LabsQmlModels", "LabsSettings", "LabsSharedImage",
    "LabsStyleKit", "LabsStyleKitImpl", "LabsSynchronizer",
    "LabsWavefrontMesh", "ShaderTools",
]

def _is_excluded_qt(path_str):
    for m in _QT_MODULE_EXCLUDES:
        # Prefix-match без разделителя, чтобы ловить Qt6WebChannelQuick.dll,
        # Qt6QuickTimelineBlendTrees.dll и т.п.
        if f"Qt6{m}" in path_str:
            return True
        # Python-модуль: PySide6\QtWebEngineCore.pyd
        if f"Qt{m}." in path_str:
            return True
    # QML / WebEngine поддеревья (plugins/qml/, Qt6QmlX).
    subtree_hits = ("\\qml\\", "/qml/",
                    "\\WebEngine", "/WebEngine",
                    "Qt6QmlCompiler", "Qt6QmlMeta", "Qt6QmlCore",
                    "Qt6QmlNetwork", "Qt6QmlLocalStorage",
                    "Qt6QmlModels", "Qt6QmlWorkerScript",
                    "Qt6QmlXmlListModel", "Qt6Qml.dll")
    return any(h in path_str for h in subtree_hits)

_QT_HIDDEN_EXCLUDES = [f"PySide6.Qt{m}" for m in _QT_MODULE_EXCLUDES]

a = Analysis(
    ["run_flasher.py"],
    pathex=[str(ROOT)],
    binaries=_esp_bin + _qt_bin,
    datas=_datas + _esp_datas + _qt_datas,
    hiddenimports=_esp_hidden + _qt_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pytest",
              "espefuse", "espsecure"] + _QT_HIDDEN_EXCLUDES,
    noarchive=False,
)

# Post-Analysis фильтр: убираем ненужные Qt6*.dll / модули / QML / plugins.
def _flt(items):
    out = []
    for entry in items:
        src = entry[1] if len(entry) >= 2 else ""
        dst = entry[0] if len(entry) >= 1 else ""
        s = str(src) + "|" + str(dst)
        if _is_excluded_qt(s):
            continue
        out.append(entry)
    return out

a.binaries = _flt(a.binaries)
a.datas = _flt(a.datas)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="atomspectra-waterfall-esp32",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON),
)
