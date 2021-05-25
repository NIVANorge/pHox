#! /usr/bin/python
from contextlib import asynccontextmanager

from pHox import *
from pco2 import pco2_instrument, test_pco2_instrument, tab_pco2_class
import os, sys
from util import get_base_folderpath, box_id, config_name, rgb_lookup

try:
    import warnings, time, RPi.GPIO
    import RPi.GPIO as GPIO
except:
    pass

from datetime import datetime, timedelta
from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QLineEdit, QTabWidget, QWidget, QPushButton, QPlainTextEdit
from PyQt5.QtWidgets import (QGroupBox, QMessageBox, QLabel, QTableWidgetItem, QGridLayout, QProgressBar,
                             QTableWidget, QHeaderView, QComboBox, QCheckBox, QDialog,
                             QSlider, QInputDialog, QApplication, QMainWindow)
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QPixmap
import numpy as np
import pyqtgraph as pg
import argparse
import pandas as pd
from util import config_file
import udp
from udp import Ferrybox as fbox
from precisions import precision as prec
from asyncqt import QEventLoop, asyncSlot
import asyncio


class AfterCuvetteCleaning(QDialog):

    def __init__(self, Panel):
        super(AfterCuvetteCleaning, self).__init__(Panel)
        self.main_qt_panel = Panel

        # Class functionality
        # The Dialog will be opened when the user reach the step of cleaning the Cuvette.
        # Button Update Plot: measure led intensity and plot it.
        # So the user can understand if the cuvette was cleaned well or not
        # Since during the calibration process the automatic real time updates of the plot
        # Are turned off
        # Other functionality : Ok and Cancel
        # If clicked OK, the program will continue the calibration cycle
        # If Cancel, the calibration will be stopped.

        self.setWindowTitle("Calibration Step After cleaning the Cuvette")

        self.btn_update_plots = QPushButton('Update Intensity Plots')
        self.btn_update_plots.clicked.connect(self.button_clicked)
        self.btn_update_plots.setCheckable(True)
        layout = QtGui.QGridLayout()

        pixmap = QPixmap(QPixmap('utils/pHox_idea.png')).scaledToHeight(100, QtCore.Qt.SmoothTransformation)

        self.image = QLabel("Hello")
        self.image.setPixmap(pixmap)

        self.setWindowIcon(QtGui.QIcon('utils/phox_logo.png'))

        self.text =  QLabel("<br>Please, clean the cuvette.\
                <br>\
                <br>Click <b>OK</b> When you are ready.\
                <br>Click Cancel to stop calibration")


        self.buttonBox = QtWidgets.QDialogButtonBox()
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.plotwidget = pg.PlotWidget()
        self.plotSpc = self.plotwidget.plot()
        self.plotwidget.setBackground("#19232D")
        self.plotwidget.showGrid(x=True, y=True)
        self.plotwidget.setYRange(1000, self.main_qt_panel.instrument.THR * 1.05)

        layout.addWidget(self.image, 0, 0, 1, 1)
        layout.addWidget(self.text, 0, 1, 1, 1)
        layout.addWidget(self.plotwidget,1,1,1,1,)
        layout.addWidget(self.btn_update_plots, 2, 1 ,1, 1 )
        layout.addWidget(self.buttonBox, 3, 0, 1, 2)
        self.setLayout(layout)

        #cuvette_is_clean = self.valve_message(type='After cuvette cleaning')
        import threading
        #b = threading.Thread(target=self.button_clicked)
        #b.start()


    def button_clicked(self):
        self.spectrum = self.main_qt_panel.instrument.spectrometer_cls.get_intensities_slow()
        self.plotSpc.setData(self.main_qt_panel.wvls, self.spectrum)
        self.btn_update_plots.setChecked(False)
        return


class BatchNumber(QDialog):

    def __init__(self, parent=None):
        super(BatchNumber, self).__init__(parent)

        self.setWindowTitle("Calibration solution Batch Number")

        self.batch_number_widget = QtGui.QLineEdit()
        self.batch_number = 1

        self.batch_number_widget.setText(str(self.batch_number))

        self.layout = QtGui.QGridLayout()
        label_text = 'Please Enter the Calibration Solution Batch Number'

        self.plus_one = QPushButton('+1')
        self.plus_ten = QPushButton('+10')
        self.minus_one = QPushButton('-1')
        self.minus_ten = QPushButton('-10')

        self.btns = {self.plus_one : 1,
                self.minus_one: -1,
                self.plus_ten: +10,
                self.minus_ten: -10 }

        [btn.clicked.connect(self.button_clicked) for btn in self.btns.keys()]

        self.layout.addWidget(QLabel(label_text), 0, 0, 1, 3)
        self.layout.addWidget(self.batch_number_widget, 1, 0, 2, 1)
        self.layout.addWidget(self.plus_one,  1, 1)
        self.layout.addWidget(self.plus_ten,  1, 2)
        self.layout.addWidget(self.minus_one, 2, 1)
        self.layout.addWidget(self.minus_ten, 2, 2)

        self.buttonBox = QtWidgets.QDialogButtonBox()
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout.addWidget(self.buttonBox, 3, 2, 1, 2)
        self.setLayout(self.layout)

    @pyqtSlot()
    def button_clicked(self):

        new_value = self.batch_number + self.btns[self.sender()]

        if new_value > 0:
            self.batch_number = new_value
            self.batch_number_widget.setText(str(self.batch_number))


class CalibrationProgess(QDialog):
    # Adapt dialog depending on the answer clean cuvette or not 
    def __init__(self, parent=None, with_cuvette_cleaning=True):
        super(CalibrationProgess, self).__init__(parent)

        self.setWindowTitle("Calibration check progress window")

        #QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        progress_steps_style = """
            QCheckBox::indicator::checked {
            background-color: #32414B;}
            """

        if with_cuvette_cleaning:
            n_steps = 6
        else:
            n_steps = 3

        self.progress_checkboxes = [QCheckBox('Calibration check {}'.format(n+1)) for n in range(n_steps)]
        self.result_checkboxes = [QCheckBox('result'.format(n+1)) for n in range(n_steps)]

        for n in self.progress_checkboxes:
            n.setStyleSheet(progress_steps_style)
            n.setEnabled(False)

        for n in self.result_checkboxes:
            n.setEnabled(False)
            n.setTristate()

        self.no_cleaning_groupbox = QGroupBox('Before Cuvette cleaning')
        layout_1 = QtGui.QGridLayout()
        for n in range(3):
            layout_1.addWidget(self.progress_checkboxes[n], n, 0)
            layout_1.addWidget(self.result_checkboxes[n], n, 1)
        self.no_cleaning_groupbox.setLayout(layout_1)

        self.layout = QtGui.QGridLayout()
        self.layout.addWidget(self.no_cleaning_groupbox)

        if with_cuvette_cleaning:

            self.with_cleaning_groupbox = QGroupBox('After Cuvette cleaning')
            layout_2 = QtGui.QGridLayout()
            for n in range(3, 6):
                layout_2.addWidget(self.progress_checkboxes[n], n-3, 0)
                layout_2.addWidget(self.result_checkboxes[n], n-3, 1)
            self.with_cleaning_groupbox.setLayout(layout_2)
            self.layout.addWidget(self.with_cleaning_groupbox)

        self.stop_calibr_btn = QPushButton('Stop Calibration')
        self.stop_calibr_btn.setCheckable(True)
        self.layout.addWidget(self.stop_calibr_btn)

        self.setLayout(self.layout)

    def closeEvent(self, event):
        self.stop_calibr_btn.setChecked(True)


class TimerManager:
    def __init__(self, input_timer):
        self.input_timer = input_timer
        logging.debug('TimerManager init method called')

    def __enter__(self):
        self.input_timer.start(1000)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.input_timer.stop()
        logging.debug('TimerManager method called')


class QTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super().__init__()
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)


class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [datetime.fromtimestamp(value) for value in values]


class SimpleThread(QtCore.QThread):
    finished = QtCore.pyqtSignal(object)

    def __init__(self, slow_function, callback):
        super(SimpleThread, self).__init__()
        self.caller = slow_function
        self.finished.connect(callback)

    def run(self):
        self.finished.emit(self.caller())


class AsyncThreadWrapper:
    def __init__(self, slow_function):
        self.callback_returned, self.result = False, None
        self.thread = SimpleThread(slow_function, self.result_setter)
        self.thread.start()

    def result_setter(self, res):
        self.result, self.callback_returned = res, True

    async def result_returner(self):
        while not self.callback_returned:
            await asyncio.sleep(0.1)
            self.thread.quit()
            self.thread.wait()
        return self.result


class Panel(QWidget):
    def __init__(self, parent, panelargs):
        super(QWidget, self).__init__(parent)
        self.major_modes = set()
        self.valid_modes = ["Measuring", "Adjusting", "Manual",
                            "Continuous", "Calibration", "Flowcheck",
                            "Paused"]

        self.args = panelargs

        self.starttime = datetime.now()
        self.fformat = "%Y%m%d_%H%M%S"
        self.init_instrument()

        self.wvls = self.instrument.calc_wavelengths()
        self.instrument.get_wvlPixels(self.wvls)
        self.noWheelCombos = []
        self.t_insitu_live = QLineEdit()
        self.s_insitu_live = QLineEdit()
        self.t_cuvette_live = QLineEdit()
        self.voltage_live = QLineEdit()
        self.btn_calibr = QPushButton()

        if self.args.pco2:
            self.pen = pg.mkPen(width=0.5, style=QtCore.Qt.DashLine)
            self.symbolSize = 10
            if self.args.localdev:
                self.pco2_instrument = test_pco2_instrument(base_folderpath, panelargs)
            else:
                self.pco2_instrument = pco2_instrument(base_folderpath, panelargs)

        self.init_ui()
        self.create_timers()
        self.updater = SensorStateUpdateManager(self)

        self.infotimer_step = 15  # seconds
        self.manual_limit = 3     # 3 minutes, time when we turn off manual mode if continuous is clicked

    def init_ui(self):
        self.tabs = QTabWidget()
        self.tab_home = QWidget()
        self.tab_manual = QWidget()
        self.tab_status = QWidget()
        self.tab_config = QWidget()
        self.tab_log = QWidget()
        self.plots = QWidget()

        self.tabs.addTab(self.tab_home, "Home")
        self.tabs.addTab(self.tab_manual, "Manual")
        self.tabs.addTab(self.tab_config, "Config")
        self.tabs.addTab(self.tab_status, "Status")
        self.tabs.addTab(self.tab_log, "Log")


        if self.args.pco2:
            self.tab_pco2 = tab_pco2_class()

            self.tabs.addTab(self.tab_pco2, "pCO2")
            self.tab_pco2.setLayout(self.tab_pco2.group_layout)

            self.tab_pco2_plot = QTabWidget()
            self.tabs.addTab(self.tab_pco2_plot, "pCO2 plot")

            v = QtGui.QVBoxLayout()
            date_axis = TimeAxisItem(orientation='bottom')
            self.plotwidget_pco2 = pg.PlotWidget(axisItems={'bottom': date_axis})
            v.addWidget(self.plotwidget_pco2)

            self.tab_pco2_plot.setLayout(v)
            self.pco2_list, self.pco2_times = [], []
            self.pco2_data_line = self.plotwidget_pco2.plot(symbol='o', pen=self.pen)

            self.plotwidget_pco2.setBackground("#19232D")
            self.plotwidget_pco2.showGrid(x=True, y=True)
            self.plotwidget_pco2.setTitle("pCO2 value time series")

        self.make_tab_log()
        self.make_tab_home()
        self.make_tab_manual()
        self.make_tab_config()
        self.make_plotwidgets()

        l = QGridLayout()
        l.addWidget(self.logTextBox.widget)
        self.tab_log.setLayout(l)

        # combine layout for plots and buttons
        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addWidget(self.plotwdigets_groupbox)
        hboxPanel.addWidget(self.tabs)

        # Disable all manual buttons in the Automatic mode
        self.manual_widgets_set_enabled(False)
        self.setLayout(hboxPanel)

    def refill_dye(self):
        if self.dye_level < 2000:
            if self.dye_level >= 1000:
                self.dye_level = 2000
            else:
                self.dye_level = 1000
        self.dye_level_bar.setValue(self.dye_level)
        self.update_config('dye_level', 'pH', self.dye_level)

    def empty_all_dye(self):
        self.dye_level = 0
        self.dye_level_bar.setValue(self.dye_level)
        self.update_config('dye_level', 'pH', self.dye_level)

    def update_dye_level_bar(self, nshots=1):
        self.dye_level -= self.dye_step_1meas * nshots

        self.dye_level_bar.setValue(self.dye_level)
        self.update_config('dye_level', 'pH', self.dye_level)

    def update_config(self, parameter, group, value):
        with open(config_name, "r+") as json_file:
            j = json.load(json_file)
            j[group][parameter] = value
            json_file.seek(0)  # rewind
            json.dump(j, json_file, indent=4)
            json_file.truncate()

    def make_tab_log(self):
        self.tab_status.layout = QGridLayout()

        self.logTextBox = QTextEditLogger(self)

        dye_level_group = QGroupBox('Dye Level ')
        l = QGridLayout()
        self.dye_level_bar = QProgressBar()
        self.dye_refill_btn = QPushButton('1 bag \nRefilled')
        self.dye_empty_btn = QPushButton('Clear \nall')
        l.addWidget(self.dye_empty_btn, 0, 0)
        l.addWidget(self.dye_refill_btn, 0, 1)
        l.addWidget(self.dye_level_bar, 0, 2)
        dye_level_group.setLayout(l)

        self.dye_level = config_file['Operational']['dye_level']
        self.dye_level_bar.setMaximum(2000)
        self.dye_level_bar.setValue(self.dye_level)

        self.dye_step_1meas = (config_file['Operational']["ncycles"] * config_file['Operational']["DYE_V_INJ"] *
                                config_file['Operational']["dye_nshots"])

        self.dye_refill_btn.clicked.connect(self.refill_dye)
        self.dye_empty_btn.clicked.connect(self.empty_all_dye)
        #self.dye_empty_btn.setToolTip("Selected Icon")
        # Volume 1 shot 0.03 ml
        #  1 measurement 1 shot * "dye_nshots" * "ncycles"  = 0.03 ml *  1 * 4 = 0.12 ml

        # You can format what is printed to text box
        self.logTextBox.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(self.logTextBox)
        if self.args.debug:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

        meas_qc_groupbox = QGroupBox('Last Measurement Quality Control')
        l = QGridLayout()
        self.flow_qc_chk = QCheckBox('Flow')
        self.dye_qc_chk = QCheckBox('Dye')
        self.biofouling_qc_chk = QCheckBox('Biofouling')
        self.temp_alive_qc_chk = QCheckBox('Temp sensor')
        qc_checks = [self.flow_qc_chk, self.dye_qc_chk,
                     self.biofouling_qc_chk, self.temp_alive_qc_chk]
        for n in qc_checks:
            n.setTristate()
            n.setEnabled(False)

        l.addWidget(self.flow_qc_chk, 0, 0)
        l.addWidget(self.dye_qc_chk, 0, 1)
        l.addWidget(self.biofouling_qc_chk, 1, 0)
        l.addWidget(self.temp_alive_qc_chk, 1, 1)
        meas_qc_groupbox.setLayout(l)



        if self.args.localdev:
            logging.info("Starting in local debug mode")

        self.dye_level_bar.setToolTip("Dye level, 100% is two full bags of dye")
        self.tab_status.layout.addWidget(dye_level_group, 0, 0)
        self.tab_status.layout.addWidget(meas_qc_groupbox, 1, 0)

        if not self.args.co3:
            calibration_group = self.make_calibration_groupbox()
            self.tab_status.layout.addWidget(calibration_group, 2, 0)

        self.tab_status.setLayout(self.tab_status.layout)

    def create_timers(self):

        self.timer_contin_mode = QtCore.QTimer()
        self.timer_contin_mode.timeout.connect(self.continuous_mode_timer_finished)

        self.infotimer_contin_mode = QtCore.QTimer()
        self.infotimer_contin_mode.timeout.connect(self.update_contin_mode_info)

        self.timerSpectra_plot = QtCore.QTimer()
        self.timerSpectra_plot.timeout.connect(self.update_spectra_plot)

        self.timerTemp_info = QtCore.QTimer()
        self.timerTemp_info.timeout.connect(self.update_sensors_info)

        self.timerAuto = QtCore.QTimer()
        self.timer2 = QtCore.QTimer()
        self.timer2.timeout.connect(self.update_plot_no_request)
        if self.args.pco2:
            self.timerSave_pco2 = QtCore.QTimer()
            self.timerSave_pco2.timeout.connect(self.update_pco2_data)

    def btn_manual_mode_clicked(self):
        if self.btn_manual_mode.isChecked():
            self.set_major_mode("Manual")
        else:
            self.unset_major_mode("Manual")

    def set_major_mode(self, mode_set):
        """Refer to Panel.valid_modes for a list of allowed modes"""
        logging.debug(f"Current mode:{self.major_modes}")
        if mode_set not in self.valid_modes:
            logging.info(f"ERROR, '{mode_set}' is not a valid mode, valid modes: {self.valid_modes}")
            return False
        if mode_set in self.major_modes:
            logging.info(f"ERROR, '{mode_set}' is already in major_modes: {self.major_modes}")
            return False
        # TODO Add more invalidating checks
        if mode_set == "Manual":
            self.manual_widgets_set_enabled(True)
            self.btn_single_meas.setEnabled(False)
            #if 'Continuous' in self.major_modes:
            #    self.btn_adjust_light_intensity.setEnabled(False)
            #    #self.btn_checkflow.setEnabled(False)

        if mode_set == "Continuous":
            self.until_next_sample = self.instrument.samplingInterval
            self.timer_contin_mode.start(self.instrument.samplingInterval * 1000 * 60)
            self.StatusBox.setText(f'Next sample in {self.until_next_sample} minutes ')
            self.infotimer_contin_mode.start(self.infotimer_step * 1000)

            self.btn_single_meas.setEnabled(False)
            self.btn_calibr.setEnabled(False)
            self.config_widgets_set_state(False)
            self.manual_widgets_set_enabled(False)

            if 'Manual' in self.major_modes:
                self.btn_adjust_light_intensity.setEnabled(False)
                #self.btn_checkflow.setEnabled(False)

        if mode_set == 'Calibration':
            self.btn_single_meas.setEnabled(False)
            self.btn_calibr.setEnabled(False)
            self.config_widgets_set_state(False)
            self.btn_manual_mode.setEnabled(False)

        if mode_set in ["Measuring", "Adjusting"]:
            self.btn_manual_mode.setEnabled(False)
            self.btn_single_meas.setEnabled(False)
            self.btn_calibr.setEnabled(False)

            if "Continuous" not in self.major_modes:
                self.btn_cont_meas.setEnabled(False)

            self.manual_widgets_set_enabled(False)
            self.config_widgets_set_state(False)

        if mode_set == 'Paused':
            self.btn_manual_mode.setEnabled(True)

        self.major_modes.add(mode_set)
        logging.debug(f"New mode:{self.major_modes}")
        return True

    def unset_major_mode(self, mode_unset):
        """Refer to Panel.valid_modes for a list of allowed modes"""
        logging.debug(f"Current mode:{self.major_modes}")
        if mode_unset not in self.major_modes:
            logging.info(f"ERROR, '{mode_unset}' is currently not in major_modes: '{self.major_modes}'")
            return False
        # TODO Add more invalidating checks
        if mode_unset == "Manual":
            if 'Continuous' in self.major_modes and self.until_next_sample <= self.manual_limit:
                self.btn_manual_mode.setChecked(False)
                self.btn_manual_mode.setEnabled(False)
            self.btn_drain.setChecked(False)
            self.manual_widgets_set_enabled(False)
            self.btn_single_meas.setEnabled(True)

        if mode_unset == "Continuous":

            self.infotimer_contin_mode.stop()
            self.StatusBox.clear()
            self.timer_contin_mode.stop()

            self.btn_manual_mode.setEnabled(True)

            if "Measuring" not in self.major_modes:
                if self.args.co3:
                    self.btn_light.setChecked(False)
                    self.btn_light_clicked()

                if 'Manual' not in self.major_modes:
                    self.btn_single_meas.setEnabled(True)
                    self.btn_calibr.setEnabled(True)

                if 'Manual' in self.major_modes:
                    self.btn_adjust_light_intensity.setEnabled(True)
                    # self.btn_checkflow.setEnabled(True)
                self.config_widgets_set_state(True)

        if mode_unset == "Calibration":
            self.btn_single_meas.setEnabled(True)
            self.btn_calibr.setEnabled(True)
            self.config_widgets_set_state(True)
            self.btn_manual_mode.setEnabled(True)
            self.btn_cont_meas.setEnabled(True)

        if mode_unset == "Measuring":
            if "Calibration" not in self.major_modes:
                if "Continuous" not in self.major_modes:
                    self.btn_single_meas.setEnabled(True)
                    self.btn_calibr.setEnabled(True)
                    self.config_widgets_set_state(True)
                self.btn_manual_mode.setEnabled(True)
                self.btn_cont_meas.setEnabled(True)
                self.config_widgets_set_state(True)

        if mode_unset == 'Adjusting' and "Measuring" not in self.major_modes:
            logging.debug('unset mode adjusting')
            if 'Manual' in self.major_modes:
                self.btn_manual_mode.setEnabled(True)
                self.manual_widgets_set_enabled(True)
            self.config_widgets_set_state(True)
            self.btn_calibr.setEnabled(True)
            self.btn_single_meas.setEnabled(True)
            self.btn_cont_meas.setEnabled(True)

        if mode_unset == 'Flowcheck':
            if 'Manual' in self.major_modes:
                self.manual_widgets_set_enabled(True)
            self.btn_cont_meas.setEnabled(True)
            self.btn_single_meas.setEnabled(True)
            self.btn_calibr.setEnabled(True)
            self.config_widgets_set_state(True)
            self.btn_manual_mode.setEnabled(True)

        self.major_modes.remove(mode_unset)
        logging.debug(f"New mode:{self.major_modes}")
        return True

    def make_plotwidgets(self):
        # create plotwidgets
        self.plotwdigets_groupbox = QGroupBox()
        pg.setConfigOptions(background="#19232D", crashWarning=True)
        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget2 = pg.PlotWidget()

        self.plotwidget1.setYRange(1000, self.instrument.THR * 1.05)

        self.plotwidget1.showGrid(x=True, y=True)
        self.plotwidget1.setTitle("Lightsource intensities")

        self.plotwidget2.showGrid(x=True, y=True)
        self.plotwidget2.setTitle("Last pH measurement")


        vboxPlot = QtGui.QVBoxLayout()
        vboxPlot.addWidget(self.plotwidget1)
        vboxPlot.addWidget(self.plotwidget2)

        self.plotSpc = self.plotwidget1.plot()
        self.plot_calc_pH = self.plotwidget2.plot()
        self.after_calc_pH = self.plotwidget2.plot()
        self.lin_fit_pH = self.plotwidget2.plot()

        self.plotwidget1.setMouseEnabled(x=False, y=False)
        self.plotwidget2.setMouseEnabled(x=False, y=False)

        self.plotwdigets_groupbox.setLayout(vboxPlot)

    def make_steps_groupBox(self):

        self.sample_steps_groupBox = QGroupBox("Measuring Progress")

        # read the number of repetitions and adapt
        self.sample_steps2 = [QCheckBox("Measurement {}".format(n)) for n in range(1,self.instrument.ncycles +1)]
        self.sample_steps = [QCheckBox("1. Adjusting Light"), QCheckBox("2 Dark and blank")] + self.sample_steps2

        layout = QGridLayout()

        [step.setEnabled(False) for step in self.sample_steps]
        [layout.addWidget(step) for step in self.sample_steps]
        self.sample_steps_groupBox.setLayout(layout)

    def make_tab_home(self):

        self.make_steps_groupBox()
        self.make_last_measurement_table()
        self.tab_home.layout = QGridLayout()

        self.StatusBox = QtGui.QTextEdit()
        self.StatusBox.setReadOnly(True)

        self.ferrypump_box = QCheckBox("Ferrybox pump is on")
        self.ferrypump_box.setEnabled(False)

        if fbox['pumping']:
            self.ferrypump_box.setChecked(True)

        self.table_grid = QGridLayout()
        self.table_grid.addWidget(self.last_measurement_table)

        self.live_updates_grid = QGridLayout()

        live_widgets = [self.t_insitu_live, self.s_insitu_live, self.t_cuvette_live, self.voltage_live]
        [n.setReadOnly(True) for n in live_widgets]

        self.live_updates_grid.addWidget(QLabel('T insitu'), 0, 0)
        self.live_updates_grid.addWidget(self.t_insitu_live, 0, 1)
        self.live_updates_grid.addWidget(QLabel('S insitu'), 0, 2)
        self.live_updates_grid.addWidget(self.s_insitu_live, 0, 3)

        self.live_updates_grid.addWidget(QLabel('T cuvette'), 1, 0)
        self.live_updates_grid.addWidget(self.t_cuvette_live, 1, 1)
        self.live_updates_grid.addWidget(QLabel('Voltage'), 1, 2)
        self.live_updates_grid.addWidget(self.voltage_live, 1, 3)

        self.live_updates_grid.addWidget(self.ferrypump_box, 2, 2, 1, 2)
        self.live_updates_grid.addWidget(self.StatusBox, 3, 0, 1, 4)

        self.live_update_groupbox.setLayout(self.live_updates_grid)
        self.last_measurement_table_groupbox.setLayout(self.table_grid)

        self.btn_cont_meas = self.create_button("Continuous measurements", True)
        self.btn_single_meas = self.create_button("Single measurement", True)

        self.btn_single_meas.clicked.connect(self.btn_single_meas_clicked)
        self.btn_cont_meas.clicked.connect(self.btn_cont_meas_clicked)

        self.tab_home.layout.addWidget(self.btn_cont_meas, 0, 0, 1, 1)
        self.tab_home.layout.addWidget(self.btn_single_meas, 0, 1)

        self.tab_home.layout.addWidget(self.sample_steps_groupBox, 1, 0, 1, 1)
        self.tab_home.layout.addWidget(self.last_measurement_table_groupbox, 1, 1, 1, 1)

        self.tab_home.layout.addWidget(self.live_update_groupbox, 2, 0, 1, 2)
        self.tab_home.setLayout(self.tab_home.layout)

    def fill_table_measurement(self, x, y, item):
        self.last_measurement_table.setItem(x, y, QTableWidgetItem(item))

    def fill_live_updates_table(self, x, y, item):
        self.live_updates_table.setItem(x, y, QTableWidgetItem(item))

    def fill_table_config(self, x, y, item):
        self.tableConfigWidget.setItem(x, y, QTableWidgetItem(item))

    def eventFilter(self, source, event):
        """ Filter all mouse scrolling for the defined comboboxes """
        if (event.type() == QtCore.QEvent.Wheel and
                source in self.noWheelCombos):
            return True
        return super(Panel, self).eventFilter(source, event)

    def make_tab_config(self):
        self.tab_config.layout = QGridLayout()
        # Define widgets for config tab
        self.btn_save_config = self.create_button("Save config", False)
        self.btn_save_config.clicked.connect(self.btn_save_config_clicked)

        self.btn_test_udp = self.create_button('Test UDP', True)
        self.timer_test_udp = QtCore.QTimer()
        self.timer_test_udp.timeout.connect(self.send_test_udp)
        self.btn_test_udp.clicked.connect(self.test_udp)

        self.tableConfigWidget = QTableWidget()
        self.tableConfigWidget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tableConfigWidget.verticalHeader().hide()
        self.tableConfigWidget.horizontalHeader().hide()
        self.tableConfigWidget.setRowCount(9)
        self.tableConfigWidget.setColumnCount(2)
        self.tableConfigWidget.horizontalHeader().setResizeMode(QHeaderView.Stretch)

        self.fill_table_config(0, 0, "DYE type")
        self.config_dye_info()

        self.fill_table_config(1, 0, "Autoadjust state")
        self.autoadjState_combo = QComboBox()

        self.combo_in_config(self.autoadjState_combo, "Autoadjust_state")
        self.tableConfigWidget.setCellWidget(1, 1, self.autoadjState_combo)

        self.fill_table_config(2, 0, 'Pumping time (seconds)')
        self.fill_table_config(2, 1, str(self.instrument.pumpTime))

        self.fill_table_config(3, 0, "Sampling interval (min)")
        self.samplingInt_combo = QComboBox()
        self.combo_in_config(self.samplingInt_combo, 'Sampling interval')

        self.tableConfigWidget.setCellWidget(3, 1, self.samplingInt_combo)

        self.fill_table_config(4, 0, "Spectro integration time")
        self.specIntTime_combo = QComboBox()

        self.combo_in_config(self.specIntTime_combo, "Spectro integration time")
        self.tableConfigWidget.setCellWidget(4, 1, self.specIntTime_combo)

        self.fill_table_config(5, 0, "Ship")
        self.ship_code_combo = QComboBox()
        self.combo_in_config(self.ship_code_combo, "Ship")
        self.tableConfigWidget.setCellWidget(5, 1, self.ship_code_combo)

        self.fill_table_config(6, 0, 'Temp probe id')
        self.temp_id_combo = QComboBox()
        self.combo_in_config(self.temp_id_combo, 'Temp probe id')
        self.tableConfigWidget.setCellWidget(6, 1, self.temp_id_combo)

        self.fill_table_config(7, 0, 'Temp probe is calibrated')
        self.temp_id_is_calibr = QtGui.QCheckBox()

        self.fill_table_config(8, 0, "Drain mode")
        self.drain_mode_combo = QComboBox()
        self.combo_in_config(self.drain_mode_combo, 'Drain_mode')

        self.tableConfigWidget.setCellWidget(8, 1, self.drain_mode_combo)

        if self.instrument.temp_iscalibrated:
            self.temp_id_is_calibr.setChecked(True)
        self.temp_id_is_calibr.setEnabled(False)
        self.tableConfigWidget.setCellWidget(7, 1, self.temp_id_is_calibr)


        self.create_manual_sal_group()

        self.tab_config.layout.addWidget(self.btn_save_config, 0, 0, 1, 1)
        self.tab_config.layout.addWidget(self.btn_test_udp, 0, 1, 1, 1)

        self.tab_config.layout.addWidget(self.tableConfigWidget, 1, 0, 1, 3)

        self.tab_config.layout.addWidget(self.manual_sal_group, 3, 0, 2, 3)
        self.tab_config.setLayout(self.tab_config.layout)


    def config_dye_info(self):
        self.dye_combo = QComboBox()
        self.combo_in_config(self.dye_combo, "DYE type pH")
        self.tableConfigWidget.setCellWidget(0, 1, self.dye_combo)

    def combo_in_config(self, combo, name):
        combo_dict = {
            "Ship": [
                self.instrument.valid_ship_codes,
                self.ship_code_changed,
                self.instrument.ship_code],

            'Temp probe id': [
                ["Probe_" + str(n) for n in range(1, 16)],
                self.temp_id_combo_changed,
                self.instrument.TempProbe_id],

            'Sampling interval': [
                self.instrument.valid_samplingIintervals,
                self.sampling_int_chngd,
                int(self.instrument.samplingInterval)],

            "Autoadjust_state": [
                ['ON', 'OFF', 'ON_NORED'],
                 self.autoadj_opt_chgd,
                 self.instrument.autoadj_opt
                 ],
            "Drain_mode": [
                ['ON', 'OFF'],
                self.drain_mode_chgd,
                self.instrument.drain_mode
            ],

            "Spectro integration time": [list(range(1, 20, 1)) + list(range(20, 100, 10)) + list(range(100, 5000, 100)),
                self.specIntTime_combo_chngd,
                self.instrument.specIntTime
            ],
            "DYE type pH": [
                ["TB", "MCP"],
                self.dye_combo_chngd,
                self.instrument.dye
            ],
            "DYE type CO3": [
                ['Pb_perchlor'],
                self.dye_combo_chngd,
                self.instrument.dye
            ]
        }

        self.noWheelCombos.append(combo)
        combo.installEventFilter(self)

        [combo.addItem(str(item)) for item in combo_dict[name][0]]
        combo.currentIndexChanged.connect(combo_dict[name][1])
        self.set_combo_index(combo, combo_dict[name], name)

    def create_manual_sal_group(self):
        self.manual_sal_group = QGroupBox('Salinity used for manual measurement')
        l = QtGui.QHBoxLayout()
        self.whole_sal = QComboBox()
        self.first_decimal = QComboBox()
        self.second_decimal = QComboBox()
        self.third_decimal = QComboBox()

        [self.whole_sal.addItem(str(n)) for n in np.arange(0, 40)]
        self.whole_sal.setCurrentIndex(self.whole_sal.findText('35', QtCore.Qt.MatchFixedString))
        for combo in [self.first_decimal, self.second_decimal, self.third_decimal]:
            [combo.addItem(str(n)) for n in np.arange(0, 10)]
        l.addWidget(self.whole_sal)
        l.addWidget(QLabel('.'))
        l.addWidget(self.first_decimal)
        l.addWidget(self.second_decimal)
        l.addWidget(self.third_decimal)

        self.manual_sal_group.setLayout(l)
        return self.manual_sal_group

    def get_salinity_manual(self):

        if 'Continuous' not in self.major_modes and 'Calibration' not in self.major_modes:
             salinity_manual = (int(self.whole_sal.currentText()) + int(self.first_decimal.currentText()) / 10
                           + int(self.second_decimal.currentText()) / 100 +
                           int(self.third_decimal.currentText()) / 1000)
        elif 'Calibration' in self.major_modes:
            salinity_manual = self.instrument.buffer_sal
        else:
            salinity_manual = None

        return salinity_manual

    def set_combo_index(self, combo, combo_info, combotype):
        text = combo_info[2]
        valid_intervals = combo_info[0]
        index = combo.findText(str(text), QtCore.Qt.MatchFixedString)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            if combotype in ("Spectro integration time",'Sampling interval'):

                diffs = np.abs(np.array(list(map(float, valid_intervals))) - float(text))

                idx2 = np.argpartition(diffs, 2)[:2]
                text_idx1 = float(valid_intervals[idx2[0]])
                text_idx2 = float(valid_intervals[idx2[1]])

                if text_idx1 < text_idx2:
                    idx = idx2[0]
                    text = text_idx1
                else:
                    idx = idx2[1]
                    text = text_idx2

                logging.error('Assigning a new value which is the closest from the list of valid values: {}'.
                              format(text))
                combo.setCurrentIndex(idx)
            else:
                logging.error('was not able to set value from the config file,combo is {}, value is {}'.format(
                combo, str(text)))


    def sampling_int_chngd(self, ind):
        self.instrument.samplingInterval = float(self.samplingInt_combo.currentText())

    @asyncSlot()
    async def specIntTime_combo_chngd(self):
        new_int_time = float(self.specIntTime_combo.currentText())
        await self.updater.set_specIntTime(new_int_time)

    def ship_code_changed(self):
        self.instrument.ship_code = self.ship_code_combo.currentText()

    def drain_mode_chgd(self):
        self.instrument.drain_mode = self.drain_mode_combo.currentText()

    def autoadj_opt_chgd(self):
        self.instrument.autoadj_opt = self.autoadjState_combo.currentText()

    def temp_id_combo_changed(self):
        self.instrument.TempProbe_id = self.temp_id_combo.currentText()
        #self.instrument.temp_iscalibrated = config_file[self.TempProbe_id]["is_calibrated"]
        self.instrument.update_temp_probe_coef()

        logging.info('new temp sensor, calibrated:' + str(self.instrument.temp_iscalibrated))
        #if self.instrument.temp_iscalibrated:
        #    self.temp_id_is_calibr.setChecked(True)
        #self.temp_id_is_calibr.setChecked(False)

    def config_widgets_set_state(self, state):
        self.dye_combo.setEnabled(state)
        self.specIntTime_combo.setEnabled(state)
        self.samplingInt_combo.setEnabled(state)
        self.btn_save_config.setEnabled(state)
        self.ship_code_combo.setEnabled(state)
        self.temp_id_combo.setEnabled(state)

    def manual_widgets_set_enabled(self, state):
        logging.debug(f"widgets_enabled_change, state is '{state}'")
        buttons = [
            self.btn_adjust_light_intensity,
            self.btn_light,
            self.btn_valve,
            self.btn_stirr,
            self.btn_dye_pmp,
            self.btn_wpump,
            self.btn_drain,
            self.btn_shutter,

        ]
        for widget in [*buttons, *self.plus_btns, *self.minus_btns, *self.sliders, *self.spinboxes]:
            widget.setEnabled(state)

    def make_btngroupbox(self):
        # Define widgets for main tab
        # Create checkabple buttons
        self.buttons_groupBox = QGroupBox("Manual Control")
        btn_grid = QGridLayout()

        self.btn_adjust_light_intensity = self.create_button("Adjust Light", True)
        self.btn_light = self.create_button("Light", True)
        self.btn_light.clicked.connect(self.btn_light_clicked)


        self.btn_valve = self.create_button("Inlet valve", True)
        self.btn_stirr = self.create_button("Stirrer", True)
        self.btn_dye_pmp = self.create_button("Dye pump", True)
        self.btn_wpump = self.create_button("Water pump", True)
        self.btn_drain = self.create_button("Drain", True)
        if self.args.co3:
            self.btn_shutter = self.create_button('Shutter',True)
            self.btn_shutter.clicked.connect(self.btn_shutter_clicked)
            btn_grid.addWidget(self.btn_shutter, 3, 1)

        btn_grid.addWidget(self.btn_dye_pmp, 0, 0)
        btn_grid.addWidget(self.btn_wpump, 0, 1)
        btn_grid.addWidget(self.btn_adjust_light_intensity, 1, 0)
        btn_grid.addWidget(self.btn_light, 1, 1)

        btn_grid.addWidget(self.btn_valve, 2, 0)
        btn_grid.addWidget(self.btn_stirr, 2, 1)
        btn_grid.addWidget(self.btn_drain, 3, 0)


        #btn_grid.addWidget(self.btn_checkflow, 4, 1)

        # Define connections Button clicked - Result

        self.btn_valve.clicked.connect(self.btn_valve_clicked)
        self.btn_stirr.clicked.connect(self.btn_stirr_clicked)
        self.btn_wpump.clicked.connect(self.btn_wpump_clicked)
        self.btn_drain.clicked.connect(self.btn_drain_clicked)

        # self.btn_checkflow.clicked.connect(self.btn_checkflow_clicked)

        self.btn_adjust_light_intensity.clicked.connect(self.btn_autoAdjust_clicked)
        self.btn_dye_pmp.clicked.connect(self.btn_dye_pmp_clicked)

        self.buttons_groupBox.setLayout(btn_grid)

    def make_slidergroupbox(self):
        self.sliders_groupBox = QGroupBox("LED values")

        sldNames = ["Blue", "Orange", "Red"]
        self.sliders = []
        self.sldLabels, self.spinboxes = [], []
        self.plus_btns, self.minus_btns = [], []

        for ind in range(3):
            self.plus_btns.append(QPushButton(" + "))
            self.minus_btns.append(QPushButton(" - "))
            self.plus_btns[ind].clicked.connect(self.led_plus_btn_clicked)
            self.minus_btns[ind].clicked.connect(self.led_minus_btn_clicked)
            self.sliders.append(QSlider(QtCore.Qt.Horizontal))
            self.sliders[ind].setFocusPolicy(QtCore.Qt.NoFocus)
            self.sliders[ind].setTracking(True)
            self.spinboxes.append(QtGui.QSpinBox())

            # create connections
            if not self.args.co3:
                self.sliders[ind].valueChanged[int].connect(self.sld_change)
                self.spinboxes[ind].valueChanged[int].connect(self.spin_change)
                self.spinboxes[ind].adjustSize()

        grid = QGridLayout()

        grid.addWidget(QLabel("Blue:"), 0, 0)
        grid.addWidget(QLabel("Orange:"), 1, 0)
        grid.addWidget(QLabel("Red:"), 2, 0)

        for n in range(3):
            grid.addWidget(self.sliders[n], n, 1)
            grid.addWidget(self.spinboxes[n], n, 2)
            grid.addWidget(self.minus_btns[n], n, 3)
            grid.addWidget(self.plus_btns[n], n, 4)

        self.sliders_groupBox.setLayout(grid)

    def create_button(self, name, check):
        Btn = QPushButton(name)
        Btn.setObjectName(name)
        if check:
            Btn.setCheckable(True)
        return Btn

    def close_shutter(self):
        logging.debug('in func close shutter')
        self.btn_shutter.setChecked(False)
        self.instrument.turn_off_relay(config_file["CO3"]["SHUTTER_SLOT"])

    def open_shutter(self):
        self.btn_shutter.setChecked(True)
        self.instrument.turn_on_relay(config_file["CO3"]["SHUTTER_SLOT"])

    def btn_stirr_clicked(self):
        if self.btn_stirr.isChecked():
            self.instrument.turn_on_relay(
                self.instrument.stirrer_slot)
        else:
            self.instrument.turn_off_relay(
                self.instrument.stirrer_slot)
                

    @asyncSlot()
    async def btn_drain_clicked(self):
        if self.btn_valve.isChecked():
            self.btn_valve.setChecked(False)
            await self.instrument.set_Valve(False)
        await self.drain()
        self.btn_drain.setChecked(False)

        # Open the inlet valve after draining
        if not self.args.co3:
            await self.instrument.set_Valve(True)
            self.btn_valve.setChecked(True)

    def btn_wpump_clicked(self):
        if self.btn_wpump.isChecked():
            self.instrument.turn_on_relay(self.instrument.wpump_slot)
        else:
            self.instrument.turn_off_relay(self.instrument.wpump_slot)

    @asyncSlot()
    async def btn_dye_pmp_clicked(self):
        state = self.btn_dye_pmp.isChecked()
        if not self.args.nodye:
            if state:
                async with self.updater.disable_live_plotting():
                    logging.debug("in pump dye clicked")
                    await self.instrument.pump_dye(3)
                    self.update_dye_level_bar(nshots=3)
                    self.btn_dye_pmp.setChecked(False)
                    datay = await self.instrument.spectrometer_cls.get_intensities()
                    await self.update_spectra_plot_manual(datay)
                    #await self.update_spectra_plot()
        else:
            logging.info('Trying to pump in no pump mode')
            self.btn_dye_pmp.setChecked(False)

    @asyncSlot()
    async def btn_valve_clicked(self):
        logging.debug('Valve button clicked')
        await self.instrument.set_Valve(self.btn_valve.isChecked())

    @asyncSlot()
    async def btn_autoAdjust_clicked(self):
        if not self.args.co3:
            self.instrument.specIntTime = 700
        self.combo_in_config(self.specIntTime_combo, "Spectro integration time")
        await self.updater.set_specIntTime(self.instrument.specIntTime)
        await self.call_autoAdjust()

    def btn_save_config_clicked(self):

        with open(config_name, "r+") as json_file:
            j = json.load(json_file)

            j["pH"]["Default_DYE"] = self.dye_combo.currentText()

            j["Operational"]["Spectro_Integration_time"] = self.instrument.specIntTime
            j["Operational"]["Ship_Code"] = self.instrument.ship_code

            j["Operational"]["TEMP_PROBE_ID"] = self.instrument.TempProbe_id

            if not self.args.co3:
                j["pH"]["LED1"] = self.instrument.LEDS[0]
                j["pH"]["LED2"] = self.instrument.LEDS[1]
                j["pH"]["LED3"] = self.instrument.LEDS[2]

            j["Operational"]["SAMPLING_INTERVAL_MIN"] = int(self.samplingInt_combo.currentText())
            json_file.seek(0)  # rewind
            json.dump(j, json_file, indent=4)
            json_file.truncate()


    def dye_combo_chngd(self, ind):
        self.instrument.dye = self.dye_combo.currentText()
        default = config_file['pH']
        #self.load_config_file()

        if self.instrument.dye == "MCP":
            self.instrument.HI = int(default["MCP_wl_HI"])
            self.instrument.I2 = int(default["MCP_wl_I2"])
        elif self.instrument.dye == "TB":
            self.instrument.HI = int(default["TB_wl_HI"])
            self.instrument.I2 = int(default["TB_wl_I2"])

    def change_plus_minus_butn(self, ind, dif):
        value = self.spinboxes[ind].value() + dif
        if value < 0:
            value = 0
        self.instrument.adjust_LED(ind, value)
        self.sliders[ind].setValue(value)
        self.spinboxes[ind].setValue(value)
        self.instrument.LEDS[ind] = value

    def led_plus_btn_clicked(self):
        dif = 1
        ind = self.plus_btns.index(self.sender())
        self.change_plus_minus_butn(ind, dif)

    def led_minus_btn_clicked(self):
        dif = -1
        ind = self.minus_btns.index(self.sender())
        self.change_plus_minus_butn(ind, dif)

    def spin_change(self, value):
        source = self.sender()
        ind = self.spinboxes.index(source)
        self.instrument.adjust_LED(ind, value)
        self.sliders[ind].setValue(value)
        self.btn_light.setChecked(True)
        self.instrument.LEDS[ind] = value

    def sld_change(self, value):
        source = self.sender()
        ind = self.sliders.index(source)
        self.instrument.adjust_LED(ind, value)
        self.spinboxes[ind].setValue(value)
        self.btn_light.setChecked(True)
        self.instrument.LEDS[ind] = value

    def save_stability_test(self, datay):
        stabfile = os.path.join("/home/pi/pHox/data/data_pH/sp_stability.log")

        stabfile_df = pd.DataFrame(
            {
                "datetime": [datetime.now().strftime(self.fformat)],
                "led0": [datay[self.instrument.wvlPixels[0]]],
                "led1": [datay[self.instrument.wvlPixels[1]]],
                "led2": [datay[self.instrument.wvlPixels[2]]],
                "specint": [self.instrument.specIntTime],
            }
        )

        if os.path.exists(stabfile):
            stabfile_df.to_csv(stabfile, mode="a", index=False, header=False)
        else:
            stabfile_df.to_csv(stabfile, index=False, header=True)

    async def update_absorbance_plot(self, n_inj, spAbs):
        logging.debug('update_absorbance_plot')
        spAbs_to_plot = spAbs[(self.wvls > 220) & (self.wvls < 360)]
        self.abs_lines[n_inj].setData(self.wvls_to_plot, spAbs_to_plot)
        await asyncio.sleep(0.005)

    async def reset_absorp_plot(self):
        z = np.zeros(len(self.wvls))

        for n_inj in range(self.instrument.ncycles):
            await self.update_absorbance_plot(n_inj, z)

    @asyncSlot()
    async def update_spectra_plot(self):
        #logging.debug('Upd spectra, Time since start {}'.format((datetime.now() - self.starttime)))


        self.updater.update_spectra_in_progress = True

        try:
            # I don't think this if statement is required
            if "Adjusting" not in self.major_modes and "Measuring" not in self.major_modes:
                datay = await self.instrument.spectrometer_cls.get_intensities()
                if (self.args.localdev and self.btn_light.isChecked() == False):
                    datay = datay * 0.001 + 1000
                if self.args.stability:
                    self.save_stability_test(datay)
                self.plotSpc.setData(self.wvls, datay)
                # self.update_sensors_info()
        except Exception as e:
            logging.exception("could not read and set Data")
        finally:
            self.updater.update_spectra_in_progress = False


    def update_corellation_plot(self):

        self.plot_calc_pH.setData(self.evalPar_df["Vol_injected"].values, self.pH_t_corr, pen=None,
                                  symbol="o", clear=True)

        self.after_calc_pH.setData(self.x, self.y, pen=None, symbol="o", symbolBrush='#30663c')

        self.lin_fit_pH.setData(self.x, self.intercept + self.slope * self.x)


    def update_sensors_info(self):
        self.t_insitu_live.setText(str(round(fbox['temperature'], prec["T_cuvette"])))
        self.s_insitu_live.setText(str(round(fbox['salinity'], prec['salinity'])))

        voltage = round(self.instrument.get_Voltage(3,
                                               self.instrument.Voltagech), prec["Voltage"])

        t_cuvette = round((self.instrument.TempCalCoef[0] * voltage)
                          + self.instrument.TempCalCoef[1], prec["T_cuvette"])

        self.t_cuvette_live.setText(str(t_cuvette))
        self.voltage_live.setText(str(voltage))

        if fbox['pumping']:
            self.ferrypump_box.setChecked(True)
        else:
            self.ferrypump_box.setChecked(False)

    def get_value_pco2_from_voltage(self, type):
        channel = config_file['CO2'][type]["Channel"]
        coef = config_file['CO2'][type]["Calibr"]

        if self.args.localdev:
            x = np.random.randint(0, 100)
        else:
            v = self.instrument.get_Voltage(2, channel)
            x = 0
            for i in range(2):
                x += coef[i] * pow(v, i)
            x = round(x, 3)
        return x

    @asyncSlot()
    async def update_pco2_data(self):
        print ("update pco2 data")
        # UPDATE VALUES
        self.wat_temp = self.get_value_pco2_from_voltage(type="Tw")
        self.air_temp_mem = self.get_value_pco2_from_voltage(type="Ta_mem")
        self.wat_flow = self.get_value_pco2_from_voltage(type="Qw")
        self.wat_pres = self.get_value_pco2_from_voltage(type="Pw")
        self.air_pres = self.get_value_pco2_from_voltage(type="Pa_env")
        self.air_temp_env = self.get_value_pco2_from_voltage(type="Ta_env")

        values = [self.wat_temp, self.wat_flow, self.wat_pres,
                  self.air_temp, self.air_pres, self.leak_detect,
                  self.pco2_instrument.co2, self.pco2_instrument.co2_temp]

        await self.get_pco2_values()

        await self.tab_pco2.update_tab_values(values)

        await self.update_pco2_plot()

        # if returnnot self.args.localdev:
        self.pco2_df = await self.pco2_instrument.save_pCO2_data(values, fbox)
        self.send_pco2_to_ferrybox()

    async def update_pco2_plot(self):
        # UPDATE PLOT WIDGETS

        if len(self.pco2_times) == 5:
            self.symbolSize = 5

        if len(self.pco2_times) == 300:
            self.pen = pg.mkPen(None)

        if len(self.pco2_times) > 7000:
            self.pco2_times = self.pco2_times[1:]
            self.pco2_list = self.pco2_list[1:]

        self.pco2_times.append(datetime.now().timestamp())
        self.pco2_list.append(self.pco2_instrument.co2)
        self.pco2_data_line.setData(self.pco2_times, self.pco2_list, symbolBrush= 'w', symbol='o',
                                    symbolSize = self.symbolSize, pen=self.pen)

    def send_pco2_to_ferrybox(self):
        row_to_string = self.pco2_df.to_csv(index=False, header=False).rstrip()
        v = self.pco2_instrument.ppco2_string_version
        string_to_udp = "$PPCO2," + str(v) + ',' + row_to_string + ",*\n"
        udp.send_data(string_to_udp, self.instrument.ship_code)



    async def autoAdjust_IntTime(self):
        # Function calls autoadjust without leds
        check_passed = await self.instrument.precheck_auto_adj()
        if not check_passed:
            adj, pixelLevel = await self.instrument.auto_adjust()
            if adj:
                logging.info("Finished Autoadjust LEDS")

                self.combo_in_config(self.specIntTime_combo, "Spectro integration time")
                #self.plotwidget1.plot([self.instrument.wvl2], [pixelLevel], pen=None, symbol="+")
            else:
                self.StatusBox.setText('Was not able do auto adjust')
        else:
            adj = check_passed
        return adj

    @asyncSlot()
    async def update_plot_no_request(self):
        # During auto adjustment and measurements, the plots are updated with spectrums
        # from the "buffer" to avoid crashing of the software
        logging.debug('update plot no request')
        try:
            await self.update_spectra_plot_manual(self.instrument.spectrum)
        except:
            logging.error('Could not plot data in update_plot_no_request')
            pass

    async def autoAdjust_LED(self):
        with TimerManager(self.timer2):
            check_passed = await self.instrument.precheck_leds_to_adj()
            if self.args.localdev:
                check_passed = False
            if not check_passed:
                (
                    self.instrument.LEDS[0], self.instrument.LEDS[1], self.instrument.LEDS[2],
                    result,
                ) = await self.instrument.auto_adjust()


                self.combo_in_config(self.specIntTime_combo, "Spectro integration time")

                if result:
                    logging.info(f"values after autoadjust: '{self.instrument.LEDS}'")
                    self.timerSpectra_plot.setInterval(self.instrument.specIntTime)
                    if self.args.localdev:
                        self.instrument.LEDS = [55, 55, 55]
                    [self.sliders[n].setValue(self.instrument.LEDS[n]) for n in range(3)]
                    await asyncio.sleep(0.1)

                    self.update_config('LED1', 'pH', self.instrument.LEDS[0])
                    self.update_config('LED2', 'pH', self.instrument.LEDS[1])
                    self.update_config('LED3', 'pH', self.instrument.LEDS[2])
                    self.update_config("Spectro_Integration_time", "Operational", self.instrument.specIntTime)
                    logging.info("Adjusted LEDS with intergration time {}".format(self.instrument.specIntTime))
                    datay = await self.instrument.spectrometer_cls.get_intensities()
                    await self.update_spectra_plot_manual(datay)
                else:
                    self.StatusBox.setText('Not able to adjust LEDs automatically')

            else:
                result = check_passed
                logging.debug('LED values are within the range, no need to call auto adjust')
        return result

    async def call_autoAdjust(self):
        if not self.instrument.autoadj_opt == 'OFF':

            if 'Manual' not in self.major_modes:
                self.sample_steps[0].setChecked(True)
            else:
                self.StatusBox.setText("Autoadjusting LEDS")
            logging.info("Autoadjust LEDS")

            async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Adjusting"):
                self.btn_adjust_light_intensity.setChecked(True)
                await asyncio.sleep(2)
                try:
                    if self.args.co3:
                        res = await self.autoAdjust_IntTime()
                    else:
                        res = await self.autoAdjust_LED()
                finally:
                    self.btn_adjust_light_intensity.setChecked(False)
            logging.info(f"res after autoadjust: '{res}")
            if 'Manual' in self.major_modes:
                self.StatusBox.setText("Finished Autoadjusting LEDS")
        else:
            res = True
            logging.info("Measure sample without autoadjustment")
        return res

    def get_next_sample(self):
        return (datetime.now() + timedelta(seconds=self.instrument.samplingInterval)).strftime("%H:%M")

    def get_filename(self):
        t = datetime.now()
        timeStamp = t.isoformat("_")
        flnmStr = datetime.now().strftime(self.fformat)
        return flnmStr, timeStamp

    def btn_cont_meas_clicked(self):
        if self.btn_cont_meas.isChecked():
            if 'Continuous' not in self.major_modes:
                self.set_major_mode("Continuous")
        else:
            self.unset_major_mode("Continuous")

            if "Paused" in self.major_modes:
                self.unset_major_mode('Paused')

    @asyncSlot()
    async def btn_single_meas_clicked(self):
        async with self.updater.disable_live_plotting():
            if self.args.pco2:
                self.timerSave_pco2.stop()
            # Start single sampling process
            logging.debug("clicked single meas ")
            message = self.valve_message('Single measurement')

            if message == QMessageBox.No:
                self.btn_single_meas.setChecked(False)
                return

            flnmStr, timeStamp = self.get_filename()

            dlg = QInputDialog(self)
            dlg.setInputMode(QtGui.QInputDialog.TextInput)

            dlg.setWindowIcon(QtGui.QIcon('utils/pHox_logo.png'))

            dlg.setWindowTitle('Important')
            dlg.setLabelText("File name for the sample will be {}, \nType the name below if you want to change it".format(flnmStr))

            ok = dlg.exec_()
            text = dlg.textValue()


        if ok:
            if text != "":
                flnmStr = text
            else:
                flnmStr = None
            folderpath = self.get_folderpath()
            # disable all btns in manual tab (There are way more buttons now)
            self.btn_cont_meas.setEnabled(False)
            self.btn_single_meas.setEnabled(False)
            self.btn_calibr.setEnabled(False)
            if (not self.btn_light.isChecked() and self.args.co3):
                await self.wait_for_warming()
            await self.sample_cycle(folderpath, flnmStr)

        self.btn_single_meas.setChecked(False)

    async def wait_for_warming(self):
        #self.updater.start_live_plot()

        self.btn_light.setChecked(True)
        self.btn_light_clicked()
        self.open_shutter()
        logging.debug('Wait for the lamp warming')
        self.StatusBox.setText('Wait for the lamp warming')
        await asyncio.sleep(3 * 60)
        self.StatusBox.setText('start the measurement')
        logging.debug('start the measurement')
        #self.updater.stop_live_plot()


    def update_contin_mode_info(self):
        print (self.until_next_sample)
        if self.until_next_sample <= self.manual_limit and self.btn_manual_mode.isEnabled():
            logging.debug('<= 3 min Until next sample,disable Manual control button ')
            if 'Manual' in self.major_modes:
                self.unset_major_mode("Manual")
            else:
                self.btn_manual_mode.setChecked(False)
                self.btn_manual_mode.setEnabled(False)

        elif (self.until_next_sample > self.manual_limit and not self.btn_manual_mode.isEnabled()
              and "Measuring" not in self.major_modes):
            logging.debug('> 3 min Until next sample, Reenable Manual control button ')
            self.btn_manual_mode.setEnabled(True)

        if 'Measuring' not in self.major_modes:
            self.StatusBox.setText(f'Next sample in {self.until_next_sample} minutes ')

        if self.args.co3 and not self.btn_light.isChecked():
            self.lamp_time = config_file["CO3"]["lamp_time"]
            if self.until_next_sample <= self.lamp_time:
                self.btn_light.setChecked(True)
                self.btn_light_clicked()
                self.open_shutter()
                #self.btn_light.click()
        if self.args.co3 and not self.btn_valve.isChecked():
            self.lamp_time = config_file["CO3"]["lamp_time"]
            if self.until_next_sample <= self.lamp_time:
                logging.info('open the valve')
                self.instrument.set_Valve_sync(True)
                self.btn_valve.setChecked(True)
        self.until_next_sample -= round(self.infotimer_step/60, 3)

    @asyncSlot()
    async def continuous_mode_timer_finished(self):
        logging.info("continuous_mode_timer_finished")
        self.until_next_sample = self.instrument.samplingInterval
        if "Measuring" not in self.major_modes:
            folderpath = self.get_folderpath()
            await self.sample_cycle(folderpath)

        else:
            logging.info("Skipped a sample because the previous measurement is still ongoing")
            pass  # TODO Increase interval

    def save_results(self, folderpath, flnmStr):
        logging.info('saving results')

        if not self.args.co3:
            import json
            upload_RT_dict = {"spt": {},
                           "eval": {},
                           "final_pH": {}}

            for col in self.spCounts_df.columns:
                upload_RT_dict['spt'][col] = self.spCounts_df[col].values.tolist()

            for col in self.evalPar_df.columns:
                upload_RT_dict['eval'][col] = self.evalPar_df[col].values.tolist()

            for col in self.data_log_row.columns:
                upload_RT_dict["final_pH"][col] = self.data_log_row[col].values.tolist()[0]

            upload_RT_path = os.path.join(folderpath, "upload")

            if not os.path.exists(upload_RT_path):
                os.makedirs(upload_RT_path)

            with open(os.path.join(upload_RT_path, flnmStr +".json"), 'w') as fp:
                json.dump(upload_RT_dict, fp, indent=4)

        logging.debug("Save spectrum data to file")
        self.save_spt(folderpath, flnmStr)
        logging.debug("Save evl data to file")
        self.save_evl(folderpath, flnmStr)

        if 'Calibration' not in self.major_modes:
            logging.info("Send pH data to ferrybox")
            self.send_to_ferrybox()
            self.save_logfile_df(folderpath)

    def update_LEDs(self):
        [self.sliders[n].setValue(self.instrument.LEDS[n]) for n in range(3)]

    def _autostart(self, restart=False):
        logging.info("Inside _autostart...")
        self.instrument.set_Valve_sync(False)
        self.btn_valve.setChecked(False)

        if not restart:
            logging.debug('Check that drain is closed')
            self.btn_drain.setChecked(False)
            self.instrument.turn_off_relay(config_file['Operational']['air_slot'])
            self.instrument.turn_off_relay(config_file['Operational']['drain_slot'])

            if not self.args.co3:
                self.StatusBox.setText("Turn on LEDs")
                self.update_LEDs()

                self.btn_light.setChecked(True)
                self.btn_light_clicked()

            self.updater.start_live_plot()
            self.timerTemp_info.start(500)

            logging.info("Starting continuous mode in Autostart")
            self.StatusBox.setText("Starting continuous mode")

        if fbox['pumping'] or fbox['pumping'] is None or self.instrument.ship_code == "Standalone":
            self.btn_cont_meas.setChecked(True)
            self.btn_cont_meas_clicked()

        if self.args.pco2:
            # change to config file
            self.timerSave_pco2.start(self.pco2_instrument.save_pco2_interv * 1.0e3)  # milliseconds
        return

    def autostart_pump(self):
        logging.debug("Initial automatic start at pump enabled")

        self.timerAuto.stop()
        self.timerAuto.timeout.disconnect(self.autostart_pump)
        self._autostart()
        # Continuously checking if pump is still working or not
        self.timerAuto.timeout.connect(self.check_autostop_pump)
        self.timerAuto.start(10000)
        return

    def check_autostop_pump(self):
        if self.btn_cont_meas.isChecked():

            if fbox['pumping'] is None:
                logging.debug('No udp connection')

            elif fbox['pumping'] == 0:
                if ('Paused' not in self.major_modes and self.instrument.ship_code != "Standalone"):
                    self.timer_contin_mode.stop()
                    self.set_major_mode('Paused')
                    logging.debug('Pause continuous mode, since pump is off')
                    self.infotimer_contin_mode.stop()
                    self.until_next_sample = self.instrument.samplingInterval
                    self.StatusBox.setText("Continuous mode paused")
                else:
                    pass
            elif fbox['pumping'] == 1:
                if 'Paused' in self.major_modes:
                    logging.debug("Going back to continuous mode, the pump is working now")
                    self.unset_major_mode('Paused')
                    self._autostart(restart=True)
                else:
                    pass

        return

    def autorun(self):
        #self.logger.debug('testt autorunw')
        logging.info("start autorun")
        if self.instrument.autostart:
            if self.instrument.automode == "pump":
                self.StatusBox.setText("Automatic start at pump enabled")
                self.timerAuto.timeout.connect(self.autostart_pump)
                self.timerAuto.start(1000)

            elif self.instrument.automode == "time":
                self.StatusBox.setText("Automatic scheduled start enabled")
                self.timerAuto.timeout.connect(self.autostart_time)
                self.timerAuto.start(1000)

            elif self.instrument.automode == "now":
                self.StatusBox.setText("Immediate automatic start enabled")
                self._autostart()
        else:
            pass

        return

    def valve_message(self, type='Turn valve into calibration mode'):
        types = {'Turn valve into calibration mode':
                     "<br> 1. Turn both valves (white) to the Calibration position (see picture)\
                      <br>2. Place the tube in the Tris buffer bottle\
                      <br>3. Turn the yellow valve to empty the cuvette\
                      <br>\
                      <br><img src=utils/calibrationmode.png>\
                      <br>\
                      <br> Click <b>Ok</b> to continue when you are ready, or <b>Cancel</b> to exit",

                    'Close drain valve':
                        '<br> Close the drain (yellow) valve when the cuvette is empty\
                         <br>\
                         <br><img src=utils/drain.png>',

                    'Calibration_second_step':
                         "Do you want calibration check to include cuvette cleaning?",

                    "Valve back to ferrybox mode":
                         "Please turn the valves back into the ferrybox mode\
                         <br>\
                         <br><img src=utils/ferryboxmode.png>",

                    "After calibration valve angry":
                         "ARE YOU SURE YOU TURNED THE VALVES BACK???",

                    "Single measurement":
                         "Did you pump to flush the sampling chamber?",

                    "Confirm Exit":
                         "Are you sure you want to exit ?",

                    "Too dirty cuvette":
                         "The cuvette is too dirty, unable to adjust LEDS\
                         <br>\
                         <br> calibration steps 1-3 will be skipped",

                     "Too dirty cuvette after cleaning":
                     "The cuvette is still too dirty\
                     <br> Stopping the calibration"
                    }

        msg = QMessageBox()

        if type == "After calibration valve angry":
            image = 'utils/angry_phox.png'
        elif type in ('Calibration_second_step', "Single measurement", "Confirm Exit"):
            image = 'utils/pHox_question.png'
        else:
            image = 'utils/pHox_idea.png'

        pixmap = QPixmap(QPixmap(image)).scaledToHeight(100, QtCore.Qt.SmoothTransformation)

        msg.setIconPixmap(pixmap)

        msg.setWindowIcon(QtGui.QIcon('utils/pHox_logo.png'))

        msg.setWindowTitle('Important')
        msg.setText(types[type])
        if type in ('After cuvette cleaning',
                    'Turn valve into calibration mode', 'Close drain valve'):
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        elif type in ('Valve back to ferrybox mode',
                      'Too dirty cuvette', "Too dirty cuvette after cleaning"):
            msg.setStandardButtons(QMessageBox.Ok)

        elif type == "After calibration valve angry":
            msg.setStandardButtons(QMessageBox.Yes)
        else:
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        return msg.exec_()

    #def click_from_code(self,btn):
    #    btn.setChecked(True)
    #    btn.click()

    #def unclick_from_code(self,btn):
    #    btn.setChecked(False)
    #    btn.click()

    @asynccontextmanager
    async def ongoing_major_mode_contextmanager(self, mode):
        self.set_major_mode(mode)
        try:
            yield None
        finally:
            self.unset_major_mode(mode)

    async def sample_cycle(self, folderpath, flnmStr_manual = None):

        flnmStr, timeStamp = self.get_filename()
        if flnmStr_manual != None:
            flnmStr = flnmStr_manual
        print(self.timerSpectra_plot.isActive())
        async with self.ongoing_major_mode_contextmanager("Measuring"), self.updater.disable_live_plotting():

            # Step 0. Start measurement, create new df,
            logging.info(f"sample, mode is {self.major_modes}")
            self.StatusBox.setText("Ongoing measurement")
            self.create_new_df()

            if self.args.co3:
                # reset Absorption plot
                await self.reset_absorp_plot()

            # pump if single or calibration , close the valve
            await self.pump_if_needed()
            await self.instrument.set_Valve(False)
            self.btn_valve.setChecked(False)
            # Step 1. Autoadjust LEDS
            self.res_autoadjust = await self.call_autoAdjust()

            #TODO: testing, change later
            if self.args.localdev and "Calibration" in self.major_modes:
                if self.ncalibr in (0, 1, 2):
                    self.res_autoadjust = False
                elif self.ncalibr in (3, 4, 5):
                    self.res_autoadjust = False

            if self.res_autoadjust:
                # Step 2. Take dark and blank
                self.sample_steps[1].setChecked(True)
                await asyncio.sleep(0.05)
                dark = await self.measure_dark()
                blank_min_dark = await self.measure_blank(dark)

                # Steps 3,4,5,6 Pump dye, measure intensity, calculate Absorbance
                await self.absorbance_measurement_cycle(blank_min_dark, dark)
                await self.get_final_value(timeStamp)
                self.update_dye_level_bar()

            if self.instrument.drain_mode == 'ON':
                logging.info('Draining')
                self.StatusBox.setText('Draining')
                # self.instrument.turn_on_relay(self.instrument.stirrer_slot)
                await self.drain()

            # Step 7 Open valve
            if not self.args.co3:
                await self.instrument.set_Valve(True)
                self.btn_valve.setChecked(True)
            if self.res_autoadjust:
                if 'Calibration' not in self.major_modes:
                    self.update_table_last_meas()
                    self.update_corellation_plot()

                # Save led levels to config file
                # Save dye level to config file
                await self.qc()
                logging.debug('Saving results')
                self.save_results(folderpath, flnmStr)
                self.StatusBox.setText('The measurement is finished')
            else:
                self.StatusBox.setText('Was not able to do the measurement, the cuvette is dirty')
                await asyncio.sleep(0.001)

        [step.setChecked(False) for step in self.sample_steps]
        if self.args.co3:
            self.btn_light.setChecked(False)
            self.btn_light_clicked()
            self.close_shutter()
            #self.btn_light.click()

        return

    async def drain(self):
        logging.debug('Start draining')
        self.instrument.turn_on_relay(config_file['Operational']['drain_slot'])
        self.instrument.turn_on_relay(config_file['Operational']['air_slot'])
        await asyncio.sleep(config_file['Operational']['drain_time'])
        self.instrument.turn_off_relay(config_file['Operational']['air_slot'])
        self.instrument.turn_off_relay(config_file['Operational']['drain_slot'])
        logging.debug('Stop draining drain func')

    async def qc(self):

        # Flow check
        await asyncio.sleep(3)  # Seconds

        blue_ind = self.instrument.wvlPixels[0]
        last_injection = self.spCounts_df[str(self.instrument.ncycles-1)][blue_ind]
        current_blue = await self.instrument.get_sp_levels(blue_ind)
        diff = current_blue - last_injection

        flow_threshold = config_file['QC']["flow_threshold"]
        if diff > flow_threshold:
            flow_is_good = True
            self.flow_qc_chk.setCheckState(2)
        else:
            flow_is_good = False
            self.flow_qc_chk.setCheckState(rgb_lookup['red'])
        self.data_log_row['flow_QC'] = flow_is_good

        # Dye is coming check
        dye_threshold = 5
        # Correct by the pixel we are using in the measurement
        if (self.spCounts_df['blank'] - self.spCounts_df['0']).mean() > dye_threshold:
            dye_is_coming = True
            self.dye_qc_chk.setCheckState(rgb_lookup['green'])
        else:
            dye_is_coming = False
            self.dye_qc_chk.setCheckState(rgb_lookup['red'])
        self.data_log_row['dye_coming_qc'] = dye_is_coming

        # Spectro integration time check
        if self.instrument.specIntTime > 2000:
            biofouling_qc = False
            self.biofouling_qc_chk.setCheckState(rgb_lookup['red'])
        else:
            biofouling_qc = True
            self.biofouling_qc_chk.setCheckState(rgb_lookup['green'])
        self.data_log_row['biofouling_qc'] = biofouling_qc

        # Temperature is alive check
        if self.evalPar_df['Voltage'].mean() == self.evalPar_df['Voltage'][0]:
            temp_alive = False
            self.temp_alive_qc_chk.setCheckState(rgb_lookup['red'])
        else:
            temp_alive = True
            self.temp_alive_qc_chk.setCheckState(rgb_lookup['green'])
        self.data_log_row['temp_sens_qc'] = temp_alive

        if fbox['pumping'] is None:
            udp_qc = False
        else:
            udp_qc = True

        self.data_log_row['UDP_conn_qc'] = udp_qc

        overall_qc = all([flow_is_good, dye_is_coming, biofouling_qc, temp_alive, udp_qc])
        self.data_log_row['overall_qc'] = overall_qc

        return

    def get_folderpath(self):
        if "Calibration" in self.major_modes:
            folderpath = base_folderpath + "/data_pH_calibr/"
        else:
            folderpath = base_folderpath + "/data_pH/"

        if not os.path.exists(folderpath):
            os.makedirs(folderpath)
        return folderpath

    def create_new_df(self):
        self.spCounts_df = pd.DataFrame(columns=["Wavelengths", "dark", "blank"])
        self.spCounts_df["Wavelengths"] = [float("%.2f" % w) for w in self.wvls]
        self.evalPar_df = pd.DataFrame(
            columns=[
                "pH", "pK", "e1", "e2", "e3",
                "Voltage", "salinity", "A1", "A2", "T_cuvette", "S_corr", "Anir",
                "Vol_injected", "TempProbe_id", "Probe_iscalibr", "TempCalCoef1",
                "TempCalCoef2", "DYE"]
        )

    async def pump_if_needed(self):
        if (
                self.instrument.ship_code == "Standalone" and "Continuous" in self.major_modes
        ):
            logging.info("pumping")
            await self.instrument.pumping(self.instrument.pumpTime)
        else:
            logging.info("additional pumping is not needed ")

    async def update_spectra_plot_manual(self, spectrum):
        self.plotSpc.setData(self.wvls, spectrum)
        await asyncio.sleep(0.05)

    async def measure_blank(self, dark):
        logging.info("Measuring blank...")
        blank = await self.instrument.spectrometer_cls.get_intensities(self.instrument.specAvScans, correct=True)
        logging.debug('max blank' + str(np.max(blank)))
        blank_min_dark = blank - dark

        self.instrument.spectrum = blank
        self.spCounts_df["blank"] = blank
        await self.update_spectra_plot_manual(blank)
        return blank_min_dark

    async def absorbance_measurement_cycle(self, blank_min_dark, dark):
        """
        This function is called after each injection of dye.
        Here the volume of injected dye is calculated and the dilution
        Then the absorbance spectrum is calculated

        :param blank_min_dark: spectrum intensities of distilled  water
        :param dark: spectrum of intensities of the dark ( and empty?)
        :return: updates evl file ( file with a middle step for pH calculation, containing
        the values for each dye injection)
        """

        for n_inj in range(self.instrument.ncycles):

            self.sample_steps[n_inj + 2].setChecked(True)
            await asyncio.sleep(0.001)
            vol_injected = round(
                self.instrument.dye_vol_inj * (n_inj + 1) * self.instrument.nshots, prec["vol_injected"],
            )
            dilution = self.instrument.Cuvette_V / (vol_injected + self.instrument.Cuvette_V)
            Voltage = await self.inject_dye(n_inj)
            absorbance = await self.calc_absorbance(n_inj, blank_min_dark, dark)
            manual_salinity = self.get_salinity_manual()
            self.update_evl_file(absorbance, Voltage, dilution, vol_injected, manual_salinity, n_inj)

        return

    async def inject_dye(self, n_inj):
        # create dataframe and store

        logging.debug("Start stirrer")
        self.instrument.turn_on_relay(self.instrument.stirrer_slot)
        logging.info("Dye Injection %d:" % (n_inj + 1))

        if not self.args.nodye:
            await self.instrument.pump_dye(self.instrument.nshots)

        logging.debug("Mixing")
        await asyncio.sleep(self.instrument.mixT)

        logging.debug("Stop stirrer")
        self.instrument.turn_off_relay(self.instrument.stirrer_slot)

        logging.debug("Wait")
        await asyncio.sleep(self.instrument.waitT)

        # measuring Voltage for temperature probe
        Voltage = self.instrument.get_Voltage(3, self.instrument.Voltagech)
        return Voltage

    async def calc_absorbance(self, n_inj, blank_min_dark, dark):
        """
        :param n_inj: number of injected dye shots
        :param blank_min_dark: intensity spectrum of blank minus intensity spectrum of dark
        :param dark: intensity spectrum of dark
        :return: Absorbance at 3 wavelengths that will be used later for pH calculation

        """
        logging.info("Calculate Absorbance")

        postinj_instensity_spectrum = await self.instrument.spectrometer_cls.get_intensities(
            self.instrument.specAvScans, correct=True)
        await self.update_spectra_plot_manual(postinj_instensity_spectrum)

        if self.args.localdev:
            absorbance_spectrum = postinj_instensity_spectrum
        else:
            self.instrument.spectrum = postinj_instensity_spectrum
            postinj_instensity_spectrum_min_dark = postinj_instensity_spectrum - dark
            absorbance_spectrum = -np.log10(postinj_instensity_spectrum_min_dark / blank_min_dark)

        if self.args.co3:
            logging.debug(absorbance_spectrum[20:40])
            await self.update_absorbance_plot(n_inj, absorbance_spectrum)

        # Save intensity spectrum to spt file
        self.spCounts_df[str(n_inj)] = postinj_instensity_spectrum

        abs_1 = round(absorbance_spectrum[self.instrument.wvlPixels[0]], prec["A1"])
        abs_2 = round(absorbance_spectrum[self.instrument.wvlPixels[1]], prec["A2"])
        abs_3 = round(absorbance_spectrum[self.instrument.wvlPixels[2]], prec["A3"])

        return [abs_1, abs_2, abs_3]

    def save_spt(self, folderpath, flnmStr):
        sptpath = folderpath + "/spt/"
        if not os.path.exists(sptpath):
            os.makedirs(sptpath)
        self.spCounts_df.T.to_csv(sptpath + flnmStr + ".spt", index=True, header=False)

    def save_evl(self, folderpath, flnmStr):
        evlpath = folderpath + "/evl/"
        if not os.path.exists(evlpath):
            os.makedirs(evlpath)
        flnm = evlpath + flnmStr + ".evl"

        self.evalPar_df.to_csv(flnm, index=False, header=True)

    def save_logfile_df(self, folderpath):
        logging.info("save log file df")

        logfile = self.get_logfile_name(folderpath)
        if os.path.exists(logfile):
            self.data_log_row.to_csv(logfile, mode='a', index=False, header=False)
        else:
            self.data_log_row.to_csv(logfile, index=False, header=True)


class Panel_pH(Panel):
    def __init__(self, parent, panelargs):
        super().__init__(parent, panelargs)

        line_specs = [
            [None, self.instrument.THR, "w"],
            [self.instrument.HI, None, "b"],
            [self.instrument.I2, None, "#eb8934"],
            [self.instrument.NIR, None, "r"],
        ]
        for x, y, color in line_specs:
            self.plotwidget1.addLine(x=x, y=y, pen=pg.mkPen(color, width=1, style=QtCore.Qt.DotLine))

    def init_instrument(self):
        if self.args.localdev:
            self.instrument = Test_pH_instrument(self.args)
        else:
            self.instrument = pH_instrument(self.args)

    def make_last_measurement_table(self):
        self.last_measurement_table_groupbox = QGroupBox("Last Measurement")
        self.live_update_groupbox = QGroupBox("Live Updates")
        self.last_measurement_table = QTableWidget(5, 2)
        self.last_measurement_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.last_measurement_table.verticalHeader().setResizeMode(QHeaderView.Stretch)

        self.last_measurement_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.last_measurement_table.verticalHeader().hide()
        self.last_measurement_table.horizontalHeader().hide()

        [self.fill_table_measurement(k, 0, v)
         for k, v in enumerate(["pH cuvette", "T cuvette", "pH insitu", "T insitu", "S insitu"])]

    def make_tab_manual(self):
        self.tab_manual.layout = QGridLayout()
        self.btn_manual_mode = self.create_button("Manual Control", True)
        self.btn_manual_mode.clicked.connect(self.btn_manual_mode_clicked)
        self.make_btngroupbox()
        self.make_slidergroupbox()
        self.tab_manual.layout.addWidget(self.btn_manual_mode)
        self.tab_manual.layout.addWidget(self.sliders_groupBox)
        self.tab_manual.layout.addWidget(self.buttons_groupBox)
        self.tab_manual.setLayout(self.tab_manual.layout)

    async def measure_dark(self):
        # turn off light and LED
        self.set_LEDs(False)
        logging.info("turn on leds")
        await asyncio.sleep(1)

        # grab spectrum
        dark = await self.instrument.spectrometer_cls.get_intensities(self.instrument.specAvScans, correct=True)

        self.set_LEDs(False)
        logging.info("turn on the leds")
        await asyncio.sleep(2)

        self.instrument.spectrum = dark
        self.spCounts_df["dark"] = dark
        await self.update_spectra_plot_manual(dark)
        return dark


    def update_table_last_meas(self):

        [
            self.fill_table_measurement(k, 1, str(self.data_log_row[v].values[0]))
            for k, v in enumerate(["pH_cuvette", "T_cuvette", "pH_insitu", "fb_temp", "fb_sal"], 0)
        ]

    async def get_final_value(self, timeStamp):
        # get final pH
        logging.debug(f'get final pH ')
        p = self.instrument.pH_correction(self.evalPar_df)

        (pH_cuvette, t_cuvette, self.slope, evalAnir, pH_insitu, self.x, self.y,  self.intercept, rsquare,
         self.pH_t_corr) = p

        self.data_log_row = pd.DataFrame(
            {
                "Time": [timeStamp[0:16]],
                "Lon": [round(fbox["longitude"], prec["longitude"])],
                "Lat": [round(fbox["latitude"], prec["latitude"])],
                "fb_temp": [round(fbox["temperature"], prec["T_cuvette"])],
                "fb_sal": [round(fbox["salinity"], prec["salinity"])],
                "SHIP": [self.instrument.ship_code],
                "pH_cuvette": [pH_cuvette],
                "T_cuvette": [t_cuvette],
                "perturbation": [self.slope],
                "evalAnir": [evalAnir],
                "pH_insitu": [pH_insitu],
                'r_square': [rsquare],
                "box_id": [box_id]
            }
        )


    def update_evl_file(self, Absorbance, Voltage,dilution, vol_injected, manual_salinity, n_inj):

        self.evalPar_df.loc[n_inj] = self.instrument.calc_pH(
            Absorbance, Voltage, dilution, vol_injected, manual_salinity)

    def get_logfile_name(self, folderpath):
        if 'Calibration' in self.major_modes:
            return (os.path.join(folderpath, 'pH_cal.log'))
        else:
            return (os.path.join(folderpath, 'pH.log'))


    @asyncSlot()
    async def btn_light_clicked(self):
        state = self.btn_light.isChecked()
        self.set_LEDs(state)

    def set_LEDs(self, state):
        for i, slider in enumerate(self.sliders):
            self.instrument.adjust_LED(i, state * slider.value())
        logging.info("Leds {}".format(str(state)))

    @asyncSlot()
    async def btn_calibr_clicked(self):

        async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Calibration"):
            logging.info("clicked calibration")
            await asyncio.sleep(0.1)
            self.BatchNumberDialog = BatchNumber(self)

            res_ok = self.BatchNumberDialog.exec_()
            self.BatchNumberDialog.close()
            if res_ok:
                self.batch_number = self.BatchNumberDialog.batch_number
                await asyncio.sleep(1)
                valve_turned = self.valve_message('Turn valve into calibration mode')

                if valve_turned == QMessageBox.Ok:
                    close_drain_value = self.valve_message('Close drain valve')
                    if close_drain_value == QMessageBox.Ok:
                        with_cuvette_cleaning = self.valve_message('Calibration_second_step')
                        if with_cuvette_cleaning == QMessageBox.Yes:
                            with_cuvette_cleaning = True
                        else:
                            with_cuvette_cleaning = False


                        self.calibr_state_dialog = CalibrationProgess(self, with_cuvette_cleaning)
                        self.calibr_state_dialog.show()

                        res = await self.calibration_check_cycle(with_cuvette_cleaning)
                        if not res == 'white':

                            self.btn_calibr_checkbox.setCheckState(int(rgb_lookup[res]))
                            self.last_calibr_date.setText(str(datetime.now().date()))

                        self.calibr_state_dialog.close()

                    self.valve_message("Valve back to ferrybox mode")
                    self.valve_message('After calibration valve angry')

                self.btn_calibr.setChecked(False)
            else:
                self.btn_calibr.setChecked(False)


    async def calibration_check_cycle(self, with_cuvette_cleaning):

        flnmStr, timeStamp = self.get_filename()
        folderpath = self.get_folderpath()

        self.skip_calibration_step = False
        self.calibration_step = 'before cleaning'

        self.instrument.autoadj_opt = 'ON'
        self.combo_in_config(self.autoadjState_combo, "Autoadjust_state")

        self.df_mean_log_row = []

        for n in range(3):
            if self.skip_calibration_step:
                break
            await self.one_calibration_step(n, folderpath)

        self.skip_calibration_step = False
        # Ask the user to clean the cuvette:
        if not self.calibr_state_dialog.stop_calibr_btn.isChecked():
            if with_cuvette_cleaning:

                cuvette_is_clean = await self.cuvette_cleaning_step()
                self.calibration_step = 'after cleaning'
                if cuvette_is_clean: # == QMessageBox.Ok:
                    for k, v in enumerate(range(3, 6)):
                        if self.skip_calibration_step:
                            break
                        await self.one_calibration_step(v, folderpath)
                else:
                    pass

        if self.res_autoadjust:
            self.data_log_row = pd.concat(self.df_mean_log_row)
            mean_result = self.data_log_row['cal_result'][-3:].mean()

            self.data_log_row['batch_number'] = self.batch_number

            self.save_logfile_df(folderpath)

            if mean_result < 0.5: #majority of tests with clean cuvette (last 3) is true
                res = 'red' #1 #False
            else:
                res = 'green' #2 #True, green
        else:
            res = 'white'
        return res

    async def cuvette_cleaning_step(self):

        cuvette_cleaning_dlg = AfterCuvetteCleaning(self)
        result = cuvette_cleaning_dlg.exec_()
        print ('RESULT', result)
        return result


    async def get_calibration_results(self):
        """
            Function for checking the results of calibration check

            The checkbox for showing the result of the calibration check is a tristate checkbox
            For the simplicity and for reusing the existing styles (white unchecked, green for checked)
            # state 0 - white, no calibration
            # state 1 - red, failed calibration check
            # state 2 - green, succeeded in calibration check
            :return:
        """

        cal_temp_tris = config_file["TrisBuffer"]["T_tris_buffer"]

        # pH theoretical at  20 C
        pH_buffer_theoretical = (11911.08 - 18.2499 * 35 - 0.039336 * 35 ** 2)/(
                cal_temp_tris + 273.15) - 366.27059 + 0.53993607 * 35 + \
                0.00016329 * 35 ** 2 + (64.52243 - 0.084041 * 35) * np.log(cal_temp_tris
                + 273.15) - 0.11149858 * (cal_temp_tris + 273.15)

        self.data_log_row['Buffer_theoretical_val'] = pH_buffer_theoretical
        self.data_log_row['Buffer_temp'] = cal_temp_tris

        dpH_dT = -0.0155

        # measured pH, corrected to the temperature
        pH_at_cal_temp = self.data_log_row['pH_cuvette'].values + dpH_dT * (
                cal_temp_tris - self.data_log_row['T_cuvette'].values)

        pH_at_cal_temp = round(pH_at_cal_temp[0], prec['pH'])
        self.data_log_row["pH_insitu"] = pH_at_cal_temp
        dif_pH = pH_at_cal_temp - pH_buffer_theoretical
        self.data_log_row['difference'] = dif_pH
        calibration_threshold = config_file["TrisBuffer"]["Calibration_threshold"]

        if abs(dif_pH) < calibration_threshold:
            result_to_checkbox = 'green'
            check_passed = 1
        else:
            result_to_checkbox = 'red'
            check_passed = 0

        return result_to_checkbox, check_passed

    def test_udp(self, state):
        timeStamp = datetime.utcnow().isoformat("_")[0:16]
        self.test_data_log_row = pd.DataFrame(
            {
                "Time": [timeStamp],
                "Lon": [fbox["longitude"]],
                "Lat": [fbox["latitude"]],
                "fb_temp": [round(fbox["temperature"], prec["T_cuvette"])],
                "fb_sal": [round(fbox["salinity"], prec["salinity"])],
                "SHIP": [self.instrument.ship_code],
                "pH_cuvette": [0],
                "T_cuvette": [0],
                "perturbation": [0],
                "evalAnir": [0],
                "pH_insitu": [0],
                "box_id": ['box_test']
            }
        )
        if state:
            self.timer_test_udp.start(10000)
        else:
            self.timer_test_udp.stop()

    def send_test_udp(self):

        string_to_udp = ("$PPHOX," + self.instrument.PPHOX_string_version + ',' +
                     self.test_data_log_row.to_csv(index=False, header=False).rstrip() + ",*\n")

        udp.send_data(string_to_udp, self.instrument.ship_code)

    def send_to_ferrybox(self):
        row_to_string = self.data_log_row.to_csv(index=False, header=False).rstrip()
        string_to_udp = ("$PPHOX," + self.instrument.PPHOX_string_version + ',' +
                         row_to_string + ",*\n")
        #udp.send_data(string_to_udp, self.instrument.ship_code)

    async def one_calibration_step(self, n, folderpath):
        # Check if stop is clicked
        if not self.calibr_state_dialog.stop_calibr_btn.isChecked():
            if self.args.localdev:
                self.ncalibr = n
            self.calibr_state_dialog.progress_checkboxes[n].setChecked(True)
            if n == 0 or n == 3:
                await self.instrument.pumping(self.instrument.pumpTime)
            else:
                await self.instrument.pumping(self.instrument.calibration_pump_time)

            if n == 3:
                self.instrument.specIntTime = 700
                self.combo_in_config(self.specIntTime_combo, "Spectro integration time")
                await self.updater.set_specIntTime(self.instrument.specIntTime)

            await self.sample_cycle(folderpath)

            if self.res_autoadjust:

                result_to_checkbox, self.data_log_row['cal_result'] = await self.get_calibration_results()

                self.calibr_state_dialog.result_checkboxes[n].setCheckState(rgb_lookup[result_to_checkbox])
                self.df_mean_log_row.append(self.data_log_row)
            else:
                self.skip_calibration_step = True
                if self.calibration_step == 'before cleaning':
                    _ = self.valve_message('Too dirty cuvette')
                else:
                    _ = self.valve_message('Too dirty cuvette after cleaning')

        else:
            pass

    def make_calibration_groupbox(self):
        cal_group = QGroupBox('Calibration')
        l = QGridLayout()

        self.btn_calibr = self.create_button("Make calibration\n check", True)
        self.btn_calibr_checkbox = QCheckBox('Last Calibration check result')
        self.btn_calibr_checkbox.setEnabled(False)
        self.btn_calibr_checkbox.setTristate()
        self.btn_calibr.clicked.connect(self.btn_calibr_clicked)

        # In this checkbox, state 0 - unchecked means no calibration
        # state 1 - calibration check failed
        # state 2 - calibration check is sucessfull

        self.last_calibr_date = QLabel('Date')
        l.addWidget(self.btn_calibr, 0, 0, 1, 1)
        l.addWidget(self.btn_calibr_checkbox, 0, 1, 1, 1)
        l.addWidget(self.last_calibr_date, 0, 2, 1, 1)
        cal_group.setLayout(l)

        return cal_group


class Panel_CO3(Panel):
    def __init__(self, parent, panelargs):
        super().__init__(parent, panelargs)

        self.plotwidget1.setXRange(220, 360)
        self.plotwidget2.setXRange(220, 360)
        #self.plotwidget2.setYRange(0,1)
        self.plotwidget2.setTitle("Last CO3 measurement")

        for widget in [self.plotwidget1, self.plotwidget2]:
            for instrument, color in [[self.instrument.wvl1, "b"], [
                                    self.instrument.wvl2, "#eb8934"],[
                                    self.instrument.wvl3, "w"]]:
                widget.addLine(x=instrument, y=None, pen=pg.mkPen(color, width=1, style=QtCore.Qt.DotLine))

        self.plotAbs = self.plotwidget2.plot()
        color = ["r", "g", "b", "m", "y"]
        self.abs_lines = []
        self.wvls_to_plot = self.wvls[(self.wvls > 220) & (self.wvls < 360)]
        for n_inj in range(self.instrument.ncycles):
            self.abs_lines.append(
                self.plotwidget2.plot(x=self.wvls_to_plot, y=np.zeros(len(self.wvls_to_plot)), pen=pg.mkPen(color[n_inj]))
            )
    def init_instrument(self):
        if self.args.localdev:
            self.instrument = Test_CO3_instrument(self.args)
        else:
            self.instrument = CO3_instrument(self.args)

    def create_new_df(self):

        self.spCounts_df = pd.DataFrame(columns=["Wavelengths", "dark", "blank"])
        self.spCounts_df["Wavelengths"] = ["%.2f" % w for w in self.wvls]
        self.evalPar_df = pd.DataFrame(
                columns=["CO3", "e1", "e3e2", "log_beta1_e2", "Voltage", "S", "A1", "A2",
                         "R", "T_cuvette", "Vol_injected", " S_corr", 'A350']
            )

    def make_tab_manual(self):
        self.tab_manual.layout = QGridLayout()
        self.btn_manual_mode = self.create_button("Manual Control", True)
        self.btn_manual_mode.clicked.connect(self.btn_manual_mode_clicked)
        self.make_btngroupbox()
        self.make_slidergroupbox()
        self.tab_manual.layout.addWidget(self.btn_manual_mode)
        self.tab_manual.layout.addWidget(self.buttons_groupBox)
        self.tab_manual.setLayout(self.tab_manual.layout)

    def config_dye_info(self):
        self.dye_combo = QComboBox()
        self.combo_in_config(self.dye_combo, "DYE type CO3")
        self.tableConfigWidget.setCellWidget(0, 1, self.dye_combo)

    def dye_combo_chngd(self):
        pass

    @asyncSlot()
    async def btn_light_clicked(self):
        if self.btn_light.isChecked():
            logging.debug('open shutter and turn on the light source')
            #self.open_shutter()
            self.instrument.turn_on_relay(self.instrument.light_slot)
        else:
            logging.debug('closing shutter and turing off the light')
            #self.close_shutter()
            self.instrument.turn_off_relay(self.instrument.light_slot)

    @asyncSlot()
    async def btn_shutter_clicked(self):
        if self.btn_shutter.isChecked():
            logging.debug('open shutter')

            self.instrument.turn_on_relay(config_file["CO3"]["SHUTTER_SLOT"])
            #self.open_shutter()
        else:
            logging.debug('close shutter')
            logging.debug(config_file["CO3"]["SHUTTER_SLOT"])
            self.instrument.turn_off_relay(config_file["CO3"]["SHUTTER_SLOT"])
            #self.close_shutter()

    def get_folderpath(self):

        if "Calibration" in self.major_modes:
            folderpath = base_folderpath + "/data_co3_calibr/"
        else:
            folderpath = base_folderpath + "/data_co3/"

        if not os.path.exists(folderpath):
            os.makedirs(folderpath)
        return folderpath

    async def measure_dark(self):
        #self.instrument.turn_off_relay(self.instrument.light_slot)
        self.close_shutter()
        logging.info("close the Shutter to measure dark")
        await asyncio.sleep(1)
        # grab spectrum
        dark = await self.instrument.spectrometer_cls.get_intensities(self.instrument.specAvScans, correct=True)
        await self.update_spectra_plot_manual(dark)
        await asyncio.sleep(2)
        # Turn on LEDs after taking dark
        logging.debug(str(np.max(dark)))
        logging.info("open the Shutter")
        #self.instrument.turn_on_relay(self.instrument.light_slot)
        self.open_shutter()
        self.instrument.spectrum = dark
        self.spCounts_df["dark"] = dark

        return dark

    def save_stability_test(self, datay):

        stabfile = os.path.join("/home/pi/pHox/data/data_co3/sp_stability.log")

        stabfile_df = pd.DataFrame(
                {
                    "datetime": [datetime.now().strftime(self.fformat)],
                    "wvl1": [datay[self.instrument.wvlPixels[0]]],
                    "wvl2": [datay[self.instrument.wvlPixels[1]]],
                    "specint": [self.instrument.specIntTime],
                }
            )

        if os.path.exists(stabfile):
            stabfile_df.to_csv(stabfile, mode="a", index=False, header=False)
        else:
            stabfile_df.to_csv(stabfile, index=False, header=True)

    def make_last_measurement_table(self):
        self.last_measurement_table_groupbox = QGroupBox("Last Measurement")
        self.live_update_groupbox = QGroupBox("Live Updates")
        self.last_measurement_table = QTableWidget(5, 2)
        self.last_measurement_table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.last_measurement_table.verticalHeader().setResizeMode(QHeaderView.Stretch)

        self.last_measurement_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.last_measurement_table.verticalHeader().hide()
        self.last_measurement_table.horizontalHeader().hide()

        [self.fill_table_measurement(k, 0, v)
         for k, v in enumerate(["co3_slope", 'co3_rvalue', 'co3_intercept', "T insitu", "S insitu"])]

    def update_evl_file(self, spAbs_min_blank, Voltage, dilution, vol_injected, manual_salinity, n_inj):
        self.evalPar_df.loc[n_inj] = self.instrument.calc_CO3(spAbs_min_blank, Voltage,
                                                         dilution, vol_injected, manual_salinity)

    def update_corellation_plot(self):
        logging.debug('No correllation plot for CO3 yet')

    async def get_final_value(self, timeStamp):
        # This function should
        # create a dataframe from CO3 log file
        # and call the function for getting final CO3 values

        logging.debug(f'get final CO3')
        p = self.instrument.calc_final_co3(self.evalPar_df)
        (slope1, intercept, r_value) = p

        self.data_log_row = pd.DataFrame(
            {
                "Time": [timeStamp[0:16]],
                "Lon": [round(fbox["longitude"], prec["longitude"])],
                "Lat": [round(fbox["latitude"], prec["latitude"])],
                "fb_temp": [round(fbox["temperature"], prec["T_cuvette"])],
                "fb_sal": [round(fbox["salinity"], prec["salinity"])],
                "SHIP": [self.instrument.ship_code],
                "co3_slope": [slope1],
                'co3_intercept': [intercept],
                'co3_rvalue': [r_value],
                "box_id": [box_id]
            }
        )

    def update_table_last_meas(self):

        [
            self.fill_table_measurement(k, 1, str(self.data_log_row[v].values[0]))
            for k, v in enumerate(["co3_slope", 'co3_rvalue', 'co3_intercept', "fb_temp", "fb_sal"], 0)
        ]

    def get_logfile_name(self,folderpath):
        return (os.path.join(folderpath, 'CO3.log'))

    def get_calibration_results(self):
        logging.info('Calibration dif for CO3 is not impplemented yet ')
        #dif_CO3 = self.data_log_row['CO3_insitu'].values - #reference value
        self.fill_table_config(9, 1, "None")

    def test_udp(self, state):

        timeStamp = datetime.utcnow().isoformat("_")[0:16]
        self.test_data_log_row = pd.DataFrame(
            {
                "Time": [timeStamp],
                "Lon": [fbox["longitude"]],
                "Lat": [fbox["latitude"]],
                "fb_temp": [round(fbox["temperature"], prec["T_cuvette"])],
                "fb_sal": [round(fbox["salinity"], prec["salinity"])],
                "SHIP": [self.instrument.ship_code],
                "co3_slope": [999],
                'co3_intercept': [999],
                'co3_rvalue': [999],
                "box_id": ['box_test']
            })
        if state:
            self.timer_test_udp.start(10000)
        else:
            self.timer_test_udp.stop()

    def send_test_udp(self):
        print ('send test udp CO3')
        string_to_udp = ("$PCO3," + self.instrument.PCO3_string_version + ',' +
                     self.test_data_log_row.to_csv(index=False, header=False).rstrip() + ",*\n")

        udp.send_data(string_to_udp, self.instrument.ship_code)

    def send_to_ferrybox(self):

        logging.info('Sending CO3 data to ferrybox')
        row_to_string = self.data_log_row.to_csv(index=False, header=False).rstrip()
        string_to_udp = ("$PCO3," + self.instrument.PCO3_string_version + ',' + row_to_string + ",*\n")
        udp.send_data(string_to_udp, self.instrument.ship_code)

        #print (row_to_string)
        #udp.send_data("$PPHOX," + row_to_string + ",*\n", self.instrument.ship_code)


class SensorStateUpdateManager:
    """
    This class should control reading values from sensors and if new values have been fetched, it is responsible for
    updating the relevant Widgets in the main panel.

    In addition an object of this class control if the updating is done via a live loop or if the live loop is disabled
    and the updates have to be called manually.
    """

    def __init__(self, main_qt_panel: Panel):
        self.main_qt_panel = main_qt_panel
        self.update_spectra_in_progress = False
        # Number of UI elements that have entered the 'disable_live_plotting' CM
        self.disable_requests = 0

    def get_interval_time(self):
        time_buffer = min(max(self.main_qt_panel.instrument.specIntTime * 2, 200), 1000)
        return self.main_qt_panel.instrument.specIntTime + time_buffer

    @asynccontextmanager
    async def disable_live_plotting(self):
        self.disable_requests += 1
        await self.stop_live_plot()
        try:
            yield None
        finally:
            self.disable_requests -= 1
            if self.disable_requests == 0:
                # self.live_button.setEnabled(True)
                self.start_live_plot()

    def start_live_plot(self):
        self.main_qt_panel.timerSpectra_plot.start(self.get_interval_time())

    async def stop_live_plot(self):
        self.main_qt_panel.timerSpectra_plot.stop()
        while self.update_spectra_in_progress:
            await asyncio.sleep(0.05)

    async def set_specIntTime(self, new_int_time):
        await self.main_qt_panel.instrument.spectrometer_cls.set_integration_time(new_int_time)
        self.main_qt_panel.instrument.specIntTime = new_int_time
        self.main_qt_panel.timerSpectra_plot.setInterval(self.get_interval_time())


class boxUI(QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parser = argparse.ArgumentParser()

        arguments = ["--nodye", "--pco2", "--co3", "--debug",
                     "--localdev", "--stability", "--onlypco2"]
        [parser.add_argument(ar, action="store_true") for ar in arguments]
        self.args = parser.parse_args()
        global base_folderpath
        base_folderpath = get_base_folderpath(self.args)

        logging.root.level = logging.DEBUG #INFO  # logging.DEBUG if self.args.debug else
        for name, logger in logging.root.manager.loggerDict.items():
            if 'asyncqt' in name:  # disable debug logging on 'asyncqt' library since it's too much lines
                logger.level = logging.INFO

        self.setWindowIcon(QtGui.QIcon('utils/pHox_logo.png'))
        self.set_title()
        self.main_widget = self.create_main_widget()
        self.setCentralWidget(self.main_widget)

        self.showMaximized()
        self.main_widget.autorun()

        with loop:
            sys.exit(loop.run_forever())

    def set_title(self):
        if self.args.pco2:
            self.setWindowTitle(f"{box_id}, parameters pH and pCO2")
        elif self.args.co3:
            self.setWindowTitle(f"{box_id}, parameter CO3")
        else:
            self.setWindowTitle(f"{box_id}")

    def create_main_widget(self):
        if self.args.co3:
            main_widget = Panel_CO3(self, self.args)
        else:
            main_widget = Panel_pH(self, self.args)
        return main_widget

    def closeEvent(self, event):
        result = self.main_widget.valve_message("Confirm Exit")
        event.ignore()

        if result == QMessageBox.Yes:
            logging.info('The program was closed by user')
            if self.args.co3:
                self.main_widget.instrument.turn_off_relay(
                    self.main_widget.instrument.light_slot)
                self.main_widget.close_shutter()
            if not self.args.onlypco2:
                self.main_widget.timer_contin_mode.stop()
                self.main_widget.timerSpectra_plot.stop()
                logging.info("timers are stopped")

            udp.UDP_EXIT = True
            udp.server.join()
            if not udp.server.is_alive():
                logging.info("UDP server closed")
            try:
                self.main_widget.instrument.spectrometer_cls.spec.close()
            except:
                logging.info('Error while closing spectro')
            if self.main_widget.btn_drain.isChecked():
                self.main_widget.btn_drain.setChecked(False)
                self.main_widget.btn_drain_clicked()
            self.main_widget.close()
            QApplication.quit()
            sys.exit()

            handlers = self.logger.handlers[:]
            for handler in handlers:
                handler.close()
                self.logger.removeHandler(handler)
            event.accept()


# loop has to be declared for testing to work
loop = None
if __name__ == "__main__":
    app = QApplication(sys.argv)
    d = os.getcwd()
    qss_file = open("styles.qss").read()
    app.setStyleSheet(qss_file)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    ui = boxUI()

    app.exec_()
