import pyqtgraph as pg
import sys
import os
import matplotlib.pyplot as plt

import PyQt5
dirname = os.path.dirname(PyQt5.__file__)
plugin_path = os.path.join(dirname, 'plugins', 'platforms')
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path

from PyQt5.QtWidgets import (QApplication, QLabel, QPushButton,
                               QVBoxLayout, QWidget)
from PyQt5 import QtGui


class MyWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        self.hello = ["Hallo Welt", "你好，世界", "Hei maailma",
            "Hola Mundo", "Привет мир"]

        #self.button = QPushButton("Click me!")
        #self.text = QLabel("Hello World")
        #self.text.setAlignment(Qt.AlignCenter)

        plotwidget2 = pg.PlotWidget()
        plotAbs = plotwidget2.plot()
        plotwidget2.addLine(x=[1, 2, 3], y=None, pen=pg.mkPen(width=1))
        plt.show()

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.button)
        self.setLayout(self.layout)

        # Connecting the signal
        self.button.clicked.connect(self.magic)

    #@Slot()
    #def magic(self):
    #    self.text.setText(random.choice(self.hello))

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)



    widget = MyWidget()
    widget.resize(800, 600)
    widget.show()

    app.exec_()