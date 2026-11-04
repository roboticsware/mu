"""
Compatibility layer for PyQt5 and PyQt6.
This module attempts to load PyQt6 first, and falls back to PyQt5.
It maps the imported modules into sys.modules under 'mu.qt' so that
code can do `from mu.qt.QtWidgets import ...` safely.
"""

import sys

try:
    import PyQt6
    from PyQt6 import QtCore, QtWidgets, QtGui, QtSerialPort, Qsci
    try:
        from PyQt6 import QtCharts
    except ImportError:
        QtCharts = None
    QT_VERSION = 6
    QT_API = "PyQt6"
except ImportError:
    import PyQt5
    from PyQt5 import QtCore, QtWidgets, QtGui, QtSerialPort, Qsci
    try:
        from PyQt5 import QtChart as QtCharts
    except ImportError:
        QtCharts = None
    QT_VERSION = 5
    QT_API = "PyQt5"

    # PyQt5 <-> PyQt6 compatibility bridging:
    # In PyQt6, QAction and QShortcut were moved from QtWidgets to QtGui.
    # Expose them under QtGui for PyQt5 so PyQt6-style imports work transparently.
    for _cls_name in ("QAction", "QActionGroup", "QShortcut", "QUndoCommand", "QUndoStack"):
        if hasattr(QtWidgets, _cls_name) and not hasattr(QtGui, _cls_name):
            setattr(QtGui, _cls_name, getattr(QtWidgets, _cls_name))

if QT_VERSION == 6:
    # Also expose QAction and QShortcut in QtWidgets for backward-compatibility
    for _cls_name in ("QAction", "QActionGroup", "QShortcut", "QUndoCommand", "QUndoStack"):
        if hasattr(QtGui, _cls_name) and not hasattr(QtWidgets, _cls_name):
            setattr(QtWidgets, _cls_name, getattr(QtGui, _cls_name))

    # In PyQt6, enum values on QProcess were scoped into scoped enums:
    # e.g., QProcess.ProcessChannelMode.MergedChannels -> QProcess.MergedChannels
    # e.g., QProcess.ExitStatus.NormalExit -> QProcess.NormalExit
    for enum_cls in (QtCore.QProcess.ProcessChannelMode, QtCore.QProcess.ExitStatus, QtCore.QProcess.ProcessState):
        for member in enum_cls:
            if not hasattr(QtCore.QProcess, member.name):
                setattr(QtCore.QProcess, member.name, member)

# Register the modules under the mu.qt namespace so that imports like
# `from mu.qt.QtCore import ...` work transparently.
sys.modules['mu.qt.QtCore'] = QtCore
sys.modules['mu.qt.QtWidgets'] = QtWidgets
sys.modules['mu.qt.QtGui'] = QtGui
sys.modules['mu.qt.QtSerialPort'] = QtSerialPort
sys.modules['mu.qt.Qsci'] = Qsci

if QtCharts:
    sys.modules['mu.qt.QtCharts'] = QtCharts
