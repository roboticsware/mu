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

# Register the modules under the mu.qt namespace so that imports like
# `from mu.qt.QtCore import ...` work transparently.
sys.modules['mu.qt.QtCore'] = QtCore
sys.modules['mu.qt.QtWidgets'] = QtWidgets
sys.modules['mu.qt.QtGui'] = QtGui
sys.modules['mu.qt.QtSerialPort'] = QtSerialPort
sys.modules['mu.qt.Qsci'] = Qsci

if QtCharts:
    sys.modules['mu.qt.QtCharts'] = QtCharts
