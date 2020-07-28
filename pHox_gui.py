#! /usr/bin/python
import logging
from contextlib import asynccontextmanager

from pHox import *
from pco2 import pco2_instrument, test_pco2_instrument, tab_pco2_class, only_pco2_instrument
import os, sys
from util import get_base_folderpath, box_id, config_name
#

try:
    import warnings, time, RPi.GPIO
    import RPi.GPIO as GPIO
except:
    pass

from datetime import datetime, timedelta
from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QLineEdit, QTabWidget, QWidget, QPushButton, QPlainTextEdit, QFileDialog
from PyQt5.QtWidgets import (QGroupBox, QMessageBox, QLabel, QTableWidgetItem, QGridLayout,
                             QTableWidget, QHeaderView, QComboBox, QCheckBox,
                             QSlider, QInputDialog, QApplication, QMainWindow)
from PyQt5.QtGui import QIcon, QPixmap
import numpy as np
import pyqtgraph as pg
import argparse
import pandas as pd

import udp  # Ferrybox data
from udp import Ferrybox as fbox
from precisions import precision as prec
from asyncqt import QEventLoop, asyncSlot, asyncClose
import asyncio


class TimerManager:
    def __init__(self, input_timer):
        self.input_timer = input_timer
        print('TimerManager init method called')

    def __enter__(self):
        self.input_timer.start(1000)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.input_timer.stop()
        print('TimerManager method called')


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


class Panel_PCO2_only(QWidget):
    # Class for ONLY PCO2 Instrument
    def __init__(self, parent, panelargs):
        super(QWidget, self).__init__(parent)
        self.args = panelargs

        if self.args.localdev:
            self.pco2_instrument = test_pco2_instrument(base_folderpath)
        else:
            self.pco2_instrument = only_pco2_instrument(base_folderpath)

        self.pco2_timeseries = {'times': [], 'values': []}

        self.tabs = QTabWidget()
        self.tab_pco2 = tab_pco2_class()
        self.tab_pco2_calibration = QWidget()
        self.tab_pco2_config = QWidget()

        l = QGridLayout()
        self.clear_plot_btn = QPushButton('Clear plot')
        self.clear_plot_btn.clicked.connect(self.clear_plot_btn_clicked)
        l.addWidget(self.clear_plot_btn)
        self.tab_pco2_config.setLayout(l)

        self.tabs.addTab(self.tab_pco2, "pCO2")
        self.tabs.addTab(self.tab_pco2_calibration, "Calibrate")
        self.tabs.addTab(self.tab_pco2_config, "Config")

        self.make_tab_pco2_calibration()
        self.make_tab_plotwidget()

        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addWidget(self.plotwidget_pco2)
        hboxPanel.addWidget(self.tabs)

        self.timerSave_pco2 = QtCore.QTimer()
        self.timerSave_pco2.timeout.connect(self.update_pco2_data)
        self.timerSave_pco2.start(1000)

        self.tab_pco2.setLayout(self.tab_pco2.layout2)
        self.setLayout(hboxPanel)

    def clear_plot_btn_clicked(self):
        self.pco2_timeseries['times'] = []
        self.pco2_timeseries['values'] = []

    def make_tab_plotwidget(self):
        date_axis = TimeAxisItem(orientation='bottom')
        self.plotwidget_pco2 = pg.PlotWidget(axisItems={'bottom': date_axis})
        self.pco2_data_line = self.plotwidget_pco2.plot()
        self.plotwidget_pco2.setBackground("#19232D")
        self.plotwidget_pco2.showGrid(x=True, y=True)
        self.plotwidget_pco2.setTitle("pCO2 value time series")
        self.pen = pg.mkPen(width=0.5, style=QtCore.Qt.DashLine)
        self.symbolSize = 10

    def make_tab_pco2_calibration(self):
        l = QGridLayout()
        self.btns = [QPushButton('Point 1'), QPushButton('Point 2'),
                     QPushButton('Point 3'), QPushButton('Point 4')]

        [l.addWidget(v, k, 0) for k, v in enumerate(self.btns)]

        self.tab_pco2_calibration.setLayout(l)

    def get_value_pco2(self, channel, coef):
        if self.args.localdev:
            x = np.random.randint(0, 100)
        else:
            v = self.instrument.get_Vd(2, channel)
            x = 0
            for i in range(2):
                x += coef[i] * pow(v, i)
            x = round(x, 3)
        return x

    @asyncSlot()
    async def update_pco2_data(self):

        # UPDATE VALUES
        self.wat_temp = self.get_value_pco2(channel=1, coef=self.pco2_instrument.wat_temp_cal_coef)
        self.wat_flow = self.get_value_pco2(channel=2, coef=self.pco2_instrument.wat_flow_cal)
        self.wat_pres = self.get_value_pco2(channel=3, coef=self.pco2_instrument.wat_pres_cal)
        self.air_temp = self.get_value_pco2(channel=4, coef=self.pco2_instrument.air_temp_cal)
        self.air_pres = self.get_value_pco2(channel=5, coef=self.pco2_instrument.air_pres_cal)
        self.leak_detect = 999
        await self.pco2_instrument.get_pco2_values()

        values = [self.wat_temp, self.wat_flow, self.wat_pres,
                  self.air_temp, self.air_pres, self.leak_detect,
                  self.pco2_instrument.co2, self.pco2_instrument.co2_temp]
        await self.tab_pco2.update_tab_values(values)
        await self.update_pco2_plot()
        self.pco2_df = await self.pco2_instrument.save_pCO2_data(values, fbox)
        await self.send_pco2_to_ferrybox()
        return

    async def send_pco2_to_ferrybox(self):
        row_to_string = self.pco2_df.to_csv(index=False, header=False).rstrip()
        #TODO: add pco2 string version
        v = self.pco2_instrument.ppco2_string_version
        udp.send_data("$PPCO2," + row_to_string + ",*\n", self.pco2_instrument.ship_code)

    async def update_pco2_plot(self):
        # UPDATE PLOT WIDGETS
        # only pco2 plot

        legth = len(self.pco2_timeseries['times'])
        if legth == 5:
            self.symbolSize = 5
        elif legth == 300:
            self.pen = pg.mkPen(None)

        if legth > 7000:
            self.pco2_timeseries['times'] = self.pco2_timeseries['times'][1:]
            self.pco2_timeseries['values'] = self.pco2_timeseries['values'][1:]

        self.pco2_timeseries['times'].append(datetime.now().timestamp())
        self.pco2_timeseries['values'].append(self.pco2_instrument.co2)

        self.pco2_data_line.setData(self.pco2_timeseries['times'],
                                    self.pco2_timeseries['values'],
                                    symbolBrush='w', alpha=0.3, size=1, symbol='o',
                                    symbolSize=self.symbolSize, pen=self.pen)



    def autorun(self):
        pass


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

        if self.args.pco2:
            self.pen = pg.mkPen(width=0.5, style=QtCore.Qt.DashLine)
            self.symbolSize = 10
            if self.args.localdev:
                self.pco2_instrument = test_pco2_instrument(base_folderpath)
            else:
                self.pco2_instrument = pco2_instrument(base_folderpath)

        self.init_ui()
        self.create_timers()
        self.updater = SensorStateUpdateManager(self)

        self.until_next_sample = None
        self.infotimer_step = 15  # seconds
        self.manual_limit = 3     # 3 minutes, time when we turn off manual mode if continuous is clicked

    def init_ui(self):
        self.tabs = QTabWidget()
        self.tab_home = QWidget()
        self.tab_manual = QWidget()
        self.tab_log = QWidget()
        self.tab_config = QWidget()
        self.plots = QWidget()

        self.tabs.addTab(self.tab_home, "Home")
        self.tabs.addTab(self.tab_manual, "Manual")
        self.tabs.addTab(self.tab_config, "Config")
        self.tabs.addTab(self.tab_log, "Log")

        if self.args.pco2:
            self.tab_pco2 = tab_pco2_class()
            self.tabs.addTab(self.tab_pco2, "pCO2")
            self.tab_pco2.setLayout(self.tab_pco2.layout2)
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

        # combine layout for plots and buttons
        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addWidget(self.plotwdigets_groupbox)
        hboxPanel.addWidget(self.tabs)

        # Disable all manual buttons in the Automatic mode
        self.manual_widgets_set_enabled(False)
        self.setLayout(hboxPanel)

    def make_tab_log(self):
        self.tab_log.layout = QGridLayout()

        self.logTextBox = QTextEditLogger(self)
        # You can format what is printed to text box
        self.logTextBox.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(self.logTextBox)
        logging.getLogger().setLevel(logging.DEBUG)

        if self.args.localdev:
            logging.info("Starting in local debug mode")
        self.tab_log.layout.addWidget(self.logTextBox.widget)
        self.tab_log.setLayout(self.tab_log.layout)

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
            if 'Continuous' in self.major_modes:
                self.btn_adjust_leds.setEnabled(False)
                self.btn_checkflow.setEnabled(False)

        if mode_set == "Continuous":
            self.btn_single_meas.setEnabled(False)
            self.btn_calibr.setEnabled(False)
            self.config_widgets_set_state(False)
            self.manual_widgets_set_enabled(False)
            if 'Manual' in self.major_modes:
                self.btn_adjust_leds.setEnabled(False)
                self.btn_checkflow.setEnabled(False)

        if mode_set == 'Calibration':
            self.btn_single_meas.setEnabled(False)
            self.btn_calibr.setEnabled(False)
            self.config_widgets_set_state(False)
            self.btn_manual_mode.setEnabled(False)

        if mode_set == 'Flowcheck':
            self.btn_cont_meas.setEnabled(False)
            self.btn_single_meas.setEnabled(False)
            self.btn_calibr.setEnabled(False)
            self.config_widgets_set_state(False)
            self.btn_manual_mode.setEnabled(False)
            self.manual_widgets_set_enabled(False)

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

            self.manual_widgets_set_enabled(False)
            self.btn_single_meas.setEnabled(True)

        if mode_unset == "Continuous":
            if "Measuring" not in self.major_modes:
                if 'Manual' not in self.major_modes:
                    self.btn_single_meas.setEnabled(True)
                    self.btn_calibr.setEnabled(True)
                self.config_widgets_set_state(True)
                if 'Manual' in self.major_modes:
                    self.btn_adjust_leds.setEnabled(True)
                    # self.btn_checkflow.setEnabled(True)

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
        self.plotwidget1.setTitle("LEDs intensities")

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

        self.sample_steps = [QCheckBox(f) for f in [
            "1. Adjusting LEDS", "2  Measuring dark,blank",
            "3. Measurement 1", "4. Measurement 2",
            "5. Measurement 3", "6. Measurement 4"]]
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

        if self.args.debug:
            logging.info("Starting in debug mode")

        self.btn_cont_meas = self.create_button("Continuous measurements", True)
        self.btn_single_meas = self.create_button("Single measurement", True)
        self.btn_calibr = self.create_button("Make calibration\n check", True)

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
            print(source, event)
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
        self.tableConfigWidget.setRowCount(8)
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

        if self.instrument.temp_iscalibrated:
            self.temp_id_is_calibr.setChecked(True)
        self.temp_id_is_calibr.setEnabled(False)
        self.tableConfigWidget.setCellWidget(7, 1, self.temp_id_is_calibr)


        self.create_manual_sal_group()
        self.btn_calibr_checkbox = QCheckBox('Calibration check result')
        self.btn_calibr_checkbox.setEnabled(False)
        # In this checkbox, state 0 - unchecked means no calibration
        # state 1 - calibration check failed
        # state 2 - calibration check is sucessfull
        self.btn_calibr_checkbox.setTristate()


        self.tab_config.layout.addWidget(self.btn_save_config, 0, 0, 1, 1)
        self.tab_config.layout.addWidget(self.btn_test_udp, 0, 1, 1, 1)

        self.tab_config.layout.addWidget(self.tableConfigWidget, 1, 0, 1, 2)

        self.tab_config.layout.addWidget(self.btn_calibr, 2, 0, 1, 1)
        self.tab_config.layout.addWidget(self.btn_calibr_checkbox, 2, 1, 1, 1)

        self.tab_config.layout.addWidget(self.manual_sal_group, 3, 0, 1, 2)
        self.tab_config.setLayout(self.tab_config.layout)




    def config_dye_info(self):
        self.dye_combo = QComboBox()
        self.combo_in_config(self.dye_combo, "DYE type pH")
        self.tableConfigWidget.setCellWidget(0, 1, self.dye_combo)

    def combo_in_config(self, combo, name):
        combo_dict = {
            "Ship": [
                ['Standalone', 'NB', 'FA', 'TF'],
                self.ship_code_changed,
                self.instrument.ship_code],

            'Temp probe id': [
                ["Probe_" + str(n) for n in range(1, 10)],
                self.temp_id_combo_changed,
                self.instrument.TempProbe_id],

            'Sampling interval': [
                ['5', '7', '10', '15', '20', '30', '60'],
                self.sampling_int_chngd,
                int(self.instrument.samplingInterval)],

            "Autoadjust_state": [
                ['ON', 'OFF', 'ON_NORED'],
                 self.autoadj_opt_chgd,
                 self.instrument.autoadj_opt
                 ],
            "Spectro integration time": [
                list(range(100, 5000, 100)),
                self.specIntTime_combo_chngd,
                self.instrument.specIntTime
            ],
            "DYE type pH" : [
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
        self.set_combo_index(combo, combo_dict[name][2])

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

    def set_combo_index(self, combo, text):
        index = combo.findText(str(text), QtCore.Qt.MatchFixedString)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            logging.error('was not able to set value from the config file,combo is {}, value is {}'.format(
                combo, str(text)))

    def sampling_int_chngd(self, ind):
        self.instrument.samplingInterval = int(self.samplingInt_combo.currentText())

    @asyncSlot()
    async def specIntTime_combo_chngd(self):
        new_int_time = int(self.specIntTime_combo.currentText())
        await self.updater.set_specIntTime(new_int_time)

    def ship_code_changed(self):
        self.instrument.ship_code = self.ship_code_combo.currentText()

    def autoadj_opt_chgd(self):
        self.instrument.autoadj_opt = self.autoadjState_combo.currentText()

    def temp_id_combo_changed(self):
        self.instrument.TempProbe_id = self.temp_id_combo.currentText()
        self.instrument.update_temp_probe_coef()

    def config_widgets_set_state(self, state):
        self.dye_combo.setEnabled(state)
        self.specIntTime_combo.setEnabled(state)
        self.samplingInt_combo.setEnabled(state)
        self.btn_save_config.setEnabled(state)
        self.ship_code_combo.setEnabled(state)
        self.temp_id_combo.setEnabled(state)

    def manual_widgets_set_enabled(self, state):
        logging.info(f"widgets_enabled_change, state is '{state}'")
        buttons = [
            self.btn_adjust_leds,
            self.btn_leds,
            self.btn_valve,
            self.btn_stirr,
            self.btn_dye_pmp,
            self.btn_wpump,
            self.btn_checkflow,

        ]
        for widget in [*buttons, *self.plus_btns, *self.minus_btns, *self.sliders, *self.spinboxes]:
            widget.setEnabled(state)
        if self.args.co3:
            self.btn_lightsource.setEnabled(state)

    def make_btngroupbox(self):
        # Define widgets for main tab
        # Create checkabple buttons
        self.buttons_groupBox = QGroupBox("Buttons GroupBox")
        btn_grid = QGridLayout()

        self.btn_adjust_leds = self.create_button("Adjust Leds", True)

        # self.btn_t_dark = self.create_button('Take dark',False)
        self.btn_leds = self.create_button("LEDs", True)
        self.btn_valve = self.create_button("Inlet valve", True)
        self.btn_stirr = self.create_button("Stirrer", True)
        self.btn_dye_pmp = self.create_button("Dye pump", True)
        self.btn_wpump = self.create_button("Water pump", True)
        self.btn_checkflow = self.create_button("Check flow", True)

        btn_grid.addWidget(self.btn_dye_pmp, 0, 0)

        btn_grid.addWidget(self.btn_adjust_leds, 1, 0)
        btn_grid.addWidget(self.btn_leds, 1, 1)

        btn_grid.addWidget(self.btn_valve, 2, 0)
        btn_grid.addWidget(self.btn_stirr, 2, 1)

        btn_grid.addWidget(self.btn_wpump, 4, 0)
        btn_grid.addWidget(self.btn_checkflow, 4, 1)

        # Define connections Button clicked - Result
        if not self.args.co3:
            self.btn_leds.clicked.connect(self.btn_leds_checked)
        self.btn_valve.clicked.connect(self.btn_valve_clicked)
        self.btn_stirr.clicked.connect(self.btn_stirr_clicked)
        self.btn_wpump.clicked.connect(self.btn_wpump_clicked)
        # self.btn_checkflow.clicked.connect(self.btn_checkflow_clicked)

        if self.args.co3:
            self.btn_lightsource = self.create_button("light source", True)
            btn_grid.addWidget(self.btn_lightsource, 4, 1)
            self.btn_lightsource.clicked.connect(self.btn_lightsource_clicked)

        self.btn_adjust_leds.clicked.connect(self.on_autoAdjust_clicked)
        self.btn_calibr.clicked.connect(self.btn_calibr_clicked)
        self.btn_dye_pmp.clicked.connect(self.btn_dye_pmp_clicked)

        self.buttons_groupBox.setLayout(btn_grid)

    def make_slidergroupbox(self):
        self.sliders_groupBox = QGroupBox("LED values")

        sldNames = ["Blue", "Orange", "Red"]
        self.sliders = []
        self.sldLabels, self.spinboxes = [], []
        self.plus_btns, self.minus_btns = [], []

        for ind in range(3):
            self.plus_btns.append(QPushButton("+"))
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

    def btn_stirr_clicked(self):
        if self.btn_stirr.isChecked():
            self.instrument.turn_on_relay(self.instrument.stirrer_slot)
        else:
            self.instrument.turn_off_relay(self.instrument.stirrer_slot)

    def btn_wpump_clicked(self):
        if self.btn_wpump.isChecked():
            self.instrument.turn_on_relay(self.instrument.wpump_slot)
        else:
            self.instrument.turn_off_relay(self.instrument.wpump_slot)

    @asyncSlot()
    async def btn_lightsource_clicked(self):

        if self.btn_lightsource.isChecked():
            self.instrument.turn_on_relay(self.instrument.light_slot)
        else:
            self.instrument.turn_off_relay(self.instrument.light_slot)

    @asyncSlot()
    async def btn_dye_pmp_clicked(self):
        state = self.btn_dye_pmp.isChecked()
        if not self.args.nodye:
            if state:
                async with self.updater.disable_live_plotting():
                    #TODO:stop updating the graph
                    logging.info("in pump dye clicked")
                    await self.instrument.pump_dye(3)
                    self.btn_dye_pmp.setChecked(False)
                    # updat plot after pumping
                    await self.update_spectra_plot()
        else:
            logging.info('Trying to pump in no pump mode')
            self.btn_dye_pmp.setChecked(False)

    @asyncSlot()
    async def btn_valve_clicked(self):
        logging.debug('Valve button clicked')
        await self.instrument.set_Valve(self.btn_valve.isChecked())

    def btn_save_config_clicked(self):

        with open(config_name, "r+") as json_file:
            j = json.load(json_file)

            j["pH"]["Default_DYE"] = self.dye_combo.currentText()

            j["Operational"]["Spectro_Integration_time"] = self.instrument.specIntTime
            j["Operational"]["Ship_Code"] = self.instrument.ship_code

            j["Operational"]["TEMP_PROBE_ID"] = self.instrument.TempProbe_id

            j["pH"]["LED1"] = self.instrument.LEDS[0]
            j["pH"]["LED2"] = self.instrument.LEDS[1]
            j["pH"]["LED3"] = self.instrument.LEDS[2]

            j["Operational"]["SAMPLING_INTERVAL_MIN"] = int(self.samplingInt_combo.currentText())
            json_file.seek(0)  # rewind
            json.dump(j, json_file, indent=4)
            json_file.truncate()

    def load_config_file(self):
        with open(config_name) as json_file:
            j = json.load(json_file)
            default = j["pH"]
            return default

    def dye_combo_chngd(self, ind):
        self.instrument.dye = self.dye_combo.currentText()
        default = self.load_config_file()
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
        dif = 10
        ind = self.plus_btns.index(self.sender())
        self.change_plus_minus_butn(ind, dif)

    def led_minus_btn_clicked(self):
        dif = -10
        ind = self.minus_btns.index(self.sender())
        self.change_plus_minus_butn(ind, dif)

    def spin_change(self, value):
        source = self.sender()
        ind = self.spinboxes.index(source)
        self.instrument.adjust_LED(ind, value)
        self.sliders[ind].setValue(value)
        self.btn_leds.setChecked(True)
        self.instrument.LEDS[ind] = value

    def sld_change(self, value):
        source = self.sender()
        ind = self.sliders.index(source)
        self.instrument.adjust_LED(ind, value)
        self.spinboxes[ind].setValue(value)
        self.btn_leds.setChecked(True)
        self.instrument.LEDS[ind] = value

    def set_LEDs(self, state):
        for i, slider in enumerate(self.sliders):
            self.instrument.adjust_LED(i, state * slider.value())
        logging.info("Leds {}".format(str(state)))

    def btn_leds_checked(self):
        state = self.btn_leds.isChecked()
        self.set_LEDs(state)

    def save_stability_test(self, datay):
        stabfile = os.path.join("/home/pi/pHox/sp_stability.log")

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
        self.abs_lines[n_inj].setData(self.wvls, spAbs)
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
                if self.args.stability:
                    self.save_stability_test(datay)
                self.plotSpc.setData(self.wvls, datay)
                # self.update_sensors_info()
        except Exception as e:
            logging.exception("could not read and set Data")
        finally:
            self.updater.update_spectra_in_progress = False

    def update_pH_plot(self):
        logging.info("update pH plot")

        self.plot_calc_pH.setData(self.evalPar_df["Vol_injected"].values, self.pH_t_corr, pen=None,
                                  symbol="o", clear=True)
        self.after_calc_pH.setData(self.x, self.y, pen=None, symbol="o", symbolBrush='#30663c')

        self.lin_fit_pH.setData(self.x, self.intercept + self.slope * self.x)

    def update_sensors_info(self):
        self.t_insitu_live.setText(str(round(fbox['temperature'], prec["T_cuvette"])))
        self.s_insitu_live.setText(str(round(fbox['salinity'], prec['salinity'])))

        voltage = round(self.instrument.get_Vd(3,
                                               self.instrument.vNTCch), prec["vNTC"])

        t_cuvette = round((self.instrument.TempCalCoef[0] * voltage)
                          + self.instrument.TempCalCoef[1], prec["T_cuvette"])

        self.t_cuvette_live.setText(str(t_cuvette))
        self.voltage_live.setText(str(voltage))

        if fbox['pumping']:
            self.ferrypump_box.setChecked(True)
        else:
            self.ferrypump_box.setChecked(False)

    def get_value_pco2_from_voltage(self, channel, coef):
        if self.args.localdev:
            x = np.random.randint(0, 100)
        else:
            v = self.instrument.get_Vd(2, channel)
            x = 0
            for i in range(2):
                x += coef[i] * pow(v, i)
            x = round(x, 3)
        return x

    @asyncSlot()
    async def update_pco2_data(self):

        # UPDATE VALUES
        self.wat_temp = self.get_value_pco2_from_voltage(channel=1, coef=self.pco2_instrument.wat_temp_cal_coef)
        self.wat_flow = self.get_value_pco2_from_voltage(channel=2, coef=self.pco2_instrument.wat_flow_cal)
        self.wat_pres = self.get_value_pco2_from_voltage(channel=3, coef=self.pco2_instrument.wat_pres_cal)
        self.air_temp = self.get_value_pco2_from_voltage(channel=4, coef=self.pco2_instrument.air_temp_cal)
        self.air_pres = self.get_value_pco2_from_voltage(channel=5, coef=self.pco2_instrument.air_pres_cal)
        self.leak_detect = 999
        await self.pco2_instrument.get_pco2_values()

        values = [self.wat_temp, self.wat_flow, self.wat_pres,
                  self.air_temp, self.air_pres, self.leak_detect,
                  self.pco2_instrument.co2, self.pco2_instrument.co2_temp]
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
        adj, pixelLevel = await self.instrument.auto_adjust()
        if adj:
            logging.info("Finished Autoadjust LEDS")
            self.set_combo_index(self.specIntTime_combo, self.instrument.specIntTime)
            self.plotwidget1.plot([self.instrument.wvl2], [pixelLevel], pen=None, symbol="+")
        else:
            self.StatusBox.setText('Was not able do auto adjust')
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
            if not check_passed:
                (
                    self.instrument.LEDS[0], self.instrument.LEDS[1], self.instrument.LEDS[2],
                    result,
                ) = await self.instrument.auto_adjust()

                logging.info(f"values after autoadjust: '{self.instrument.LEDS}'")
                self.set_combo_index(self.specIntTime_combo, self.instrument.specIntTime)

                if result:
                    self.timerSpectra_plot.setInterval(self.instrument.specIntTime)
                    [self.sliders[n].setValue(self.instrument.LEDS[n]) for n in range(3)]
                    logging.info("Adjusted LEDS with intergration time {}".format(self.instrument.specIntTime))
                    datay = await self.instrument.spectrometer_cls.get_intensities()
                    await self.update_spectra_plot_manual(datay)
                else:
                    self.StatusBox.setText('Not able to adjust LEDs automatically')

            else:
                result = check_passed
                logging.debug('LED values are within the range, no need to call auto adjust')
        return result

    @asyncSlot()
    async def on_autoAdjust_clicked(self):
        await self.call_autoAdjust()

    async def call_autoAdjust(self):
        async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Adjusting"):
            self.btn_adjust_leds.setChecked(True)
            await asyncio.sleep(2)
            try:
                if self.args.co3:
                    res = await self.autoAdjust_IntTime()
                else:
                    res = await self.autoAdjust_LED()
            finally:
                self.btn_adjust_leds.setChecked(False)
            return res

    @asyncSlot()
    async def btn_checkflow_clicked(self):
        if self.btn_checkflow.isChecked():
            if not self.args.debug and fbox["pumping"] != 1:
                logging.info('Not doing flowcheck because the pump is off')
                self.btn_checkflow.setChecked(False)
                return

            async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Flowcheck"):
                logging.debug(f'Start flowcheck preparations')

                # Closing the valve
                await self.instrument.set_Valve(True)
                # Getting a baseline spectrum
                baseline_spectrum = await self.instrument.spectrometer_cls.get_intensities()
                # inject die twice (with n shots determined by config), this includes stirring
                await self.inject_dye(3)
                await self.inject_dye(3)

                dyed_spectrum = await self.instrument.spectrometer_cls.get_intensities()
                rms_spectrum_difference = np.sqrt(np.mean(np.square(baseline_spectrum - dyed_spectrum)))
                logging.debug(f'Initial diff: {rms_spectrum_difference}')
                # Re-open the valve
                await self.instrument.set_Valve(False)

                # Start the flow check
                start = datetime.utcnow()
                check_succeeded = False
                while datetime.utcnow() - start < timedelta(seconds=20):
                    diluted_spectrum = await self.instrument.spectrometer_cls.get_intensities()
                    new_rms_spectrum_difference = np.sqrt(np.mean(np.square(baseline_spectrum - diluted_spectrum)))
                    logging.debug(f'got another spectrum, new diff: {new_rms_spectrum_difference}')
                    if rms_spectrum_difference * .2 > new_rms_spectrum_difference:
                        check_succeeded = True
                        break
                logging.debug(f'Final result of check: {check_succeeded}')
                self.btn_checkflow.setChecked(False)
                return check_succeeded

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
            if "Measuring" not in self.major_modes:
                self.until_next_sample = self.instrument.samplingInterval

            self.timer_contin_mode.start(self.instrument.samplingInterval * 1000 * 60)

            self.StatusBox.setText(f'Next sample in {self.until_next_sample} minutes ')
            self.infotimer_contin_mode.start(self.infotimer_step * 1000)
        else:
            self.unset_major_mode("Continuous")
            self.StatusBox.clear()
            self.timer_contin_mode.stop()
            self.until_next_sample = self.instrument.samplingInterval
            self.infotimer_contin_mode.stop()
            if "Paused" in self.major_modes:
                self.unset_major_mode('Paused')

    @asyncSlot()
    async def btn_calibr_clicked(self):

        async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Calibration"):
            logging.info("clicked calibration")

            valve_turned_msg = QMessageBox()
            valve_turned_msg.setIconPixmap(QPixmap("Figure_1.png"))
            valve_turned_msg.setWindowTitle('Message')
            valve_turned_msg.setText(
                "Turn the input valve (white) to internal input water position " +
                "  (Get water from calibration solution)")
            valve_turned_msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            valve_turned = valve_turned_msg.exec_()
            #QMessageBox.question, "important message",
            #"Turn the input valve (white) to calibration position",
            #, parent = self


            if valve_turned == QMessageBox.Yes:
                folderpath = self.get_folderpath()
                flnmStr, timeStamp = self.get_filename()
                await self.sample(folderpath, flnmStr, timeStamp)

                v = QMessageBox.question(self, "important message",
                                         "Manually turn the valve back to ferrybox mode",
                                         QMessageBox.Yes | QMessageBox.No)

                v = QMessageBox.question(self, "important message!!!",
                                         "ARE YOU SURE YOU TURNED THE VALVE???",
                                         QMessageBox.Yes | QMessageBox.No)
            self.btn_calibr.setChecked(False)

    @asyncSlot()
    async def btn_single_meas_clicked(self):
        async with self.updater.disable_live_plotting():
            if self.args.pco2:
                self.timerSave_pco2.stop()
            # Start single sampling process
            logging.info("clicked single meas ")
            message = QMessageBox.question(
                self,
                "important message!!!",
                "Did you pump to flush the sampling chamber?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if message == QMessageBox.No:
                self.btn_single_meas.setChecked(False)
                return

            flnmStr, timeStamp = self.get_filename()

            text, ok = QInputDialog.getText(None, "Enter Sample name", flnmStr)
            if self.args.pco2:
                self.timerSave_pco2.start()
            if ok:
                if text != "":
                    flnmStr = text
                folderpath = self.get_folderpath()
                # disable all btns in manual tab (There are way more buttons now)
                self.btn_cont_meas.setEnabled(False)
                self.btn_single_meas.setEnabled(False)
                self.btn_calibr.setEnabled(False)  # what does calibration do?

                await self.sample(folderpath, flnmStr, timeStamp)
            self.btn_single_meas.setChecked(False)

    def update_contin_mode_info(self):

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

        self.until_next_sample -= round(self.infotimer_step/60, 3)

    @asyncSlot()
    async def continuous_mode_timer_finished(self):
        logging.info("continuous_mode_timer_finished")
        self.until_next_sample = self.instrument.samplingInterval
        if "Measuring" not in self.major_modes:
            flnmStr, timeStamp = self.get_filename()
            folderpath = self.get_folderpath()
            if fbox["pumping"] == 1 or fbox["pumping"] is None:  # None happens when not connected to the ferrybox
                await self.sample(folderpath, flnmStr, timeStamp)
        else:
            logging.info("Skipped a sample because the previous measurement is still ongoing")
            pass  # TODO Increase interval

    def save_results(self, folderpath, flnmStr):
        logging.info('saving results')

        logging.info("Save spectrum data to file")
        self.save_spt(folderpath, flnmStr)
        logging.info("Save evl data to file")
        self.save_evl(folderpath, flnmStr)

        logging.info("Send pH data to ferrybox")
        self.send_to_ferrybox()

        self.save_logfile_df(folderpath, flnmStr)

    def update_LEDs(self):
        [self.sliders[n].setValue(self.instrument.LEDS[n]) for n in range(3)]

    def _autostart(self, restart=False):
        logging.info("Inside _autostart...")
        self.instrument.set_Valve_sync(False)
        self.btn_valve.setChecked(False)
        if not restart:
            if self.args.co3:
                logging.info("turn on light source")
                self.instrument.turn_on_relay(self.instrument.light_slot)
                self.btn_lightsource.setChecked(True)
            else:
                self.StatusBox.setText("Turn on LEDs")
                self.update_LEDs()
                self.btn_leds.setChecked(True)
                self.btn_leds_checked()

            self.updater.start_live_plot()
            self.timerTemp_info.start(500)

            logging.info("Starting continuous mode in Autostart")
            self.StatusBox.setText("Starting continuous mode")
            self.btn_cont_meas.setChecked(True)

        if fbox['pumping'] or fbox['pumping'] is None:
            self.btn_cont_meas_clicked()

        if self.args.pco2:
            # change to config file
            self.timerSave_pco2.start(self.pco2_instrument.save_pco2_interv * 1.0e3)  # milliseconds
        return

    def autostart_pump(self):
        logging.info("Initial automatic start at pump enabled")

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
                if 'Paused' not in self.major_modes:
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

    @asynccontextmanager
    async def ongoing_major_mode_contextmanager(self, mode):
        self.set_major_mode(mode)
        try:
            yield None
        finally:
            self.unset_major_mode(mode)

    async def sample(self, folderpath, flnmStr, timeStamp):
        async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Measuring"):
            # Step 0. Start measurement, create new df,
            # reset Absorption plot

            logging.info(f"sample, mode is {self.major_modes}")
            self.StatusBox.setText("Ongoing measurement")

            self.create_new_df()

            if self.args.co3:
                await self.reset_absorp_plot()
            # pump if single, close the valve
            await self.pump_if_needed()

            logging.info("Closing the valve ...")
            await self.instrument.set_Valve(True)

            # Step 1. Autoadjust LEDS

            if not self.instrument.autoadj_opt == 'OFF':
                self.sample_steps[0].setChecked(True)
                logging.info("Autoadjust LEDS")
                res = await self.call_autoAdjust()
                logging.info(f"res after autoadjust: '{res}")
            else:
                res = True
                logging.info("Measure sample without autoadjustment")
            if res:
                # Step 2. Take dark and blank
                self.sample_steps[1].setChecked(True)
                await asyncio.sleep(0.05)
                dark = await self.measure_dark()
                blank_min_dark = await self.measure_blank(dark)

                # Steps 3,4,5,6 Pump dye, measure intensity, calculate Absorbance
                await self.absorbance_measurement_cycle(blank_min_dark, dark)

                await self.get_final_value(timeStamp)
                logging.info("The measurement is finished...")


            # Step 7 Open valve
            logging.info("Opening the valve ...")
            await self.instrument.set_Valve(False)

        if res:
            self.save_results(folderpath, flnmStr)
            logging.debug('Saving results')
            self.update_table_last_meas()

        if not self.args.co3 and res:
            self.update_pH_plot()



        self.StatusBox.setText('Finished the measurement')
        [step.setChecked(False) for step in self.sample_steps]

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
        self.spCounts_df["Wavelengths"] = ["%.2f" % w for w in self.wvls]
        self.evalPar_df = pd.DataFrame(
            columns=[
                "pH", "pK", "e1", "e2", "e3",
                "vNTC", "salinity", "A1", "A2", "T_cuvette", "S_corr", "Anir",
                "Vol_injected", "TempProbe_id", "Probe_iscalibr", "TempCalCoef1",
                "TempCalCoef2", "DYE"]
        )

    async def pump_if_needed(self):
        if (
                self.instrument.ship_code == "Standalone" and "Continuous" in self.major_modes
        ) or "Calibration" in self.major_modes:
            logging.info("pumping")
            await self.instrument.pumping(self.instrument.pumpTime)
        else:
            logging.info("pumping is not needed ")

    async def measure_dark(self):

        logging.info("turn off LEDS to measure dark")
        self.set_LEDs(False)

        # grab spectrum
        dark = await self.instrument.spectrometer_cls.get_intensities(self.instrument.specAvScans, correct=True)

        # Turn on LEDs after taking dark
        self.set_LEDs(True)
        logging.info("turn on LEDs")

        self.instrument.spectrum = dark
        self.spCounts_df["dark"] = dark
        await self.update_spectra_plot_manual(dark)
        return dark

    async def update_spectra_plot_manual(self, spectrum):
        self.plotSpc.setData(self.wvls, spectrum)
        await asyncio.sleep(0.05)

    async def measure_blank(self, dark):
        logging.info("Measuring blank...")

        blank = await self.instrument.spectrometer_cls.get_intensities(self.instrument.specAvScans, correct=True)
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
            logging.info(f"dye injection n ='{n_inj}")
            self.sample_steps[n_inj + 2].setChecked(True)
            await asyncio.sleep(0.05)
            vol_injected = round(
                self.instrument.dye_vol_inj * (n_inj + 1) * self.instrument.nshots, prec["vol_injected"],
            )
            dilution = self.instrument.Cuvette_V / (vol_injected + self.instrument.Cuvette_V)
            vNTC = await self.inject_dye(n_inj)
            absorbance = await self.calc_absorbance(n_inj, blank_min_dark, dark)
            manual_salinity = self.get_salinity_manual()
            self.update_evl_file(absorbance, vNTC, dilution, vol_injected, manual_salinity, n_inj)

        return

    async def inject_dye(self, n_inj):
        # create dataframe and store

        logging.info("Start stirrer")
        self.instrument.turn_on_relay(self.instrument.stirrer_slot)
        logging.info("Dye Injection %d:" % (n_inj + 1))

        if not self.args.nodye:
            await self.instrument.pump_dye(self.instrument.nshots)

        logging.info("Mixing")
        await asyncio.sleep(self.instrument.mixT)

        logging.info("Stop stirrer")
        self.instrument.turn_off_relay(self.instrument.stirrer_slot)

        logging.info("Wait")
        await asyncio.sleep(self.instrument.waitT)

        # measuring Voltage for temperature probe
        Voltage = self.instrument.get_Vd(3, self.instrument.vNTCch)
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
            logging.info("in debug")
            absorbance_spectrum = postinj_instensity_spectrum
        else:
            self.instrument.spectrum = postinj_instensity_spectrum
            postinj_instensity_spectrum_min_dark = postinj_instensity_spectrum - dark
            absorbance_spectrum = -np.log10(postinj_instensity_spectrum_min_dark / blank_min_dark)

        if self.args.co3:
            await self.update_absorbance_plot(n_inj, absorbance_spectrum)

        # Save intensity spectrum to spt file
        self.spCounts_df[str(n_inj)] = postinj_instensity_spectrum

        abs_1 = round(absorbance_spectrum[self.instrument.wvlPixels[0]], prec["A1"])
        abs_2 = round(absorbance_spectrum[self.instrument.wvlPixels[1]], prec["A2"])
        abs_3 = round(absorbance_spectrum[self.instrument.wvlPixels[2]], prec["Anir"])

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

    def save_logfile_df(self, folderpath, flnmStr):
        logging.info("save log file df")
        hour_log_path = folderpath + "/logs/"
        if not os.path.exists(hour_log_path):
            os.makedirs(hour_log_path)

        hour_log_flnm = os.path.join(hour_log_path, datetime.now().strftime("%Y%m%d_%H")) + '.log'
        if not os.path.exists(hour_log_flnm):
            self.data_log_row.to_csv(hour_log_flnm, index=False, header=True)
        else:
            self.data_log_row.to_csv(hour_log_flnm, mode='a', index=False, header=False)

        logging.info(f"hour_log_path: {hour_log_path}")
        hour_log_flnm = hour_log_path + flnmStr + ".log"
        logging.info(f"hour_log_flnm: {hour_log_flnm}")

        logfile = self.get_logfile_name(folderpath)

        if os.path.exists(logfile):
            self.data_log_row.to_csv(logfile, mode='a', index=False, header=False)
        else:
            self.data_log_row.to_csv(logfile, index=False, header=True)

        logging.info("saved log_df")


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
            self.instrument = Test_instrument(self.args)
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

    def update_table_last_meas(self):

        [
            self.fill_table_measurement(k, 1, str(self.data_log_row[v].values[0]))
            for k, v in enumerate(["pH_cuvette", "T_cuvette", "pH_insitu", "fb_temp", "fb_sal"], 0)
        ]

    async def get_final_value(self, timeStamp):
        # get final pH
        logging.debug(f'get final pH ')
        p = self.instrument.pH_eval(self.evalPar_df)
        (pH_cuvette, t_cuvette, perturbation, evalAnir, pH_insitu, self.x, self.y, self.slope, self.intercept,
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
                "perturbation": [perturbation],
                "evalAnir": [evalAnir],
                "pH_insitu": [pH_insitu],
                "box_id": [box_id]
            }
        )

        if 'Calibration' in self.major_modes:
            calibration_check_res = await self.get_calibration_results()
            self.data_log_row['cal_result'] = calibration_check_res


    def update_evl_file(self, Absorbance, vNTC,dilution, vol_injected, manual_salinity, n_inj):

        self.evalPar_df.loc[n_inj] = self.instrument.calc_pH(
            Absorbance, vNTC, dilution, vol_injected, manual_salinity)

    def get_logfile_name(self,folderpath):
        return (os.path.join(folderpath, 'pH.log'))

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

        pH_buffer_theoretical = 0
        dif_pH = self.data_log_row['pH_cuvette'].values - pH_buffer_theoretical
        calibration_threshold = 0.05

       # Check if dif_pH is smaller than the threshold and see if the calibration was passed or not
        if abs(dif_pH) < calibration_threshold:
            result_to_checkbox = 2
            check_passed = True
        else:
            result_to_checkbox = 1
            check_passed = False
        self.btn_calibr_checkbox.setCheckState(result_to_checkbox)
        await asyncio.sleep(0.001)
        return check_passed

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
        print ('send test udp')
        string_to_udp = ("$PPHOX," + self.instrument.PPHOX_string_version + ',' +
                     self.test_data_log_row.to_csv(index=False, header=False).rstrip() + ",*\n")
        print (string_to_udp)
        udp.send_data(string_to_udp, self.instrument.ship_code)

    def send_to_ferrybox(self):
        row_to_string = self.data_log_row.to_csv(index=False, header=False).rstrip()
        string_to_udp = ("$PPHOX," + self.instrument.PPHOX_string_version + ',' +
                         row_to_string + ",*\n")
        #udp.send_data(string_to_udp, self.instrument.ship_code)


class Panel_CO3(Panel):
    def __init__(self, parent, panelargs):
        super().__init__(parent, panelargs)

        self.plotwidget1.setXRange(220, 260)
        self.plotwidget2.setXRange(220, 260)
        self.plotwidget2.setTitle("Last CO3 measurement")

        for widget in [self.plotwidget1, self.plotwidget2]:
            for instrument, color in [[self.instrument.wvl1, "b"], [
                                    self.instrument.wvl2, "#eb8934"]]:
                widget.addLine(x=instrument, y=None, pen=pg.mkPen(color, width=1, style=QtCore.Qt.DotLine))

        self.plotAbs = self.plotwidget2.plot()
        color = ["r", "g", "b", "m", "y"]
        self.abs_lines = []
        for n_inj in range(self.instrument.ncycles):
            self.abs_lines.append(
                self.plotwidget2.plot(x=self.wvls, y=np.zeros(len(self.wvls)), pen=pg.mkPen(color[n_inj]))
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
                columns=["CO3", "e1", "e2e3", "log_beta1_e2", "vNTC", "S", "A1", "A2",
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

    def get_folderpath(self):

        if "Calibration" in self.major_modes:
            folderpath = base_folderpath + "/data_co3_calibr/"
        else:
            folderpath = base_folderpath + "/data_co3/"

        if not os.path.exists(folderpath):
            os.makedirs(folderpath)
        return folderpath


    async def measure_dark(self):
        # turn off light and LED
        self.instrument.turn_off_relay(self.instrument.light_slot)
        logging.info("turn off the light source to measure dark")
        await asyncio.sleep(1)

        # grab spectrum
        dark = await self.instrument.spectrometer_cls.get_intensities(self.instrument.specAvScans, correct=True)

        self.instrument.turn_on_relay(self.instrument.light_slot)
        logging.info("turn on the light source")
        await asyncio.sleep(2)

        self.instrument.spectrum = dark
        self.spCounts_df["dark"] = dark
        await self.update_spectra_plot_manual(dark)
        return dark

    def save_stability_test(self, datay):
        stabfile = os.path.join("/home/pi/pHox/data_co3/sp_stability.log")

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

    def update_evl_file(self, spAbs_min_blank, vNTC, dilution, vol_injected, manual_salinity, n_inj):
        self.evalPar_df.loc[n_inj] = self.instrument.calc_CO3(spAbs_min_blank, vNTC,
                                                         dilution, vol_injected, manual_salinity)

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
        print (state)
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

        logging.root.level = logging.DEBUG if self.args.debug else logging.INFO
        self.logger = logging.getLogger('general_logger')
        fh = logging.FileHandler('errors.log')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        fh.setLevel(logging.DEBUG)
        self.logger.addHandler(fh)
        for name, logger in logging.root.manager.loggerDict.items():
            if 'asyncqt' in name:  # disable debug logging on 'asyncqt' library since it's too much lines
                logger.level = logging.INFO

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
        if self.args.onlypco2:
            main_widget = Panel_PCO2_only(self, self.args)
        elif self.args.co3:
            main_widget = Panel_CO3(self, self.args)
        else:
            main_widget = Panel_pH(self, self.args)
        return main_widget

    def closeEvent(self, event):
        result = QMessageBox.question(
            self, "Confirm Exit...", "Are you sure you want to exit ?", QMessageBox.Yes | QMessageBox.No,
        )
        event.ignore()

        if result == QMessageBox.Yes:
            logging.info('The program was closed by user')
            if self.args.co3:
                self.main_widget.instrument.turn_off_relay(
                    self.main_widget.instrument.light_slot)
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
