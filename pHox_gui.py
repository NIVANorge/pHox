#! /usr/bin/python
import logging
from contextlib import asynccontextmanager

from pHox import *
from pco2 import pco2_instrument, test_pco2_instrument
import os, sys

try:
    import warnings, time, RPi.GPIO
    import RPi.GPIO as GPIO
except:
    pass

from datetime import datetime, timedelta
from PyQt5 import QtGui, QtCore, QtWidgets
import numpy as np
import pyqtgraph as pg
import argparse, socket
import pandas as pd
import time
import udp  # Ferrybox data
from udp import Ferrybox as fbox
from precisions import precision as prec
from asyncqt import QEventLoop, asyncSlot, asyncClose
import asyncio

class QTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super().__init__()
        self.widget = QtWidgets.QPlainTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)


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
        return self.result

class Panel(QtGui.QWidget):
    def __init__(self, parent, panelargs, config_name):
        super(QtGui.QWidget, self).__init__(parent)
        self.major_modes = set()
        self.valid_modes = ["Measuring", "Adjusting", "Manual", "Continuous", "Calibration", "Flowcheck",
                            "Paused"]

        self.args = panelargs
        self.config_name = config_name

        self.fformat = "%Y%m%d_%H%M%S"
        if self.args.co3:
            self.instrument = CO3_instrument(self.args, self.config_name)
        elif self.args.localdev:
            self.instrument = Test_instrument(self.args, self.config_name)
        else:
            self.instrument = pH_instrument(self.args, self.config_name)

        self.wvls = self.instrument.calc_wavelengths()
        self.instrument.get_wvlPixels(self.wvls)
        self.t_insitu_live = QtGui.QLineEdit()
        self.s_insitu_live = QtGui.QLineEdit()

        self.t_lab_live = QtGui.QLineEdit()
        self.voltage_live = QtGui.QLineEdit()
        if self.args.pco2:
            if self.args.localdev:
                self.pco2_instrument = test_pco2_instrument(self.config_name)
            else:
                self.pco2_instrument = pco2_instrument(self.config_name)
        self.init_ui()
        self.create_timers()
        self.updater = SensorStateUpdateManager(self)

        self.until_next_sample = None
        self.infotimer_step = 15  # seconds
        self.manual_limit = 60*3  # 3 minutes, time when we turn off manual mode if continuous is clicked

    def init_ui(self):
        self.tabs = QtGui.QTabWidget()
        self.tab1 = QtGui.QWidget()
        self.tab_manual = QtGui.QWidget()
        self.tab_log = QtGui.QWidget()
        self.tab_config = QtGui.QWidget()
        self.plots = QtGui.QWidget()

        # Add tabs
        self.tabs.addTab(self.tab1, "Home")
        self.tabs.addTab(self.tab_log, "Log")
        self.tabs.addTab(self.tab_manual, "Manual")
        self.tabs.addTab(self.tab_config, "Config")

        if self.args.pco2:
            self.tab_pco2 = QtGui.QTabWidget()
            self.tabs.addTab(self.tab_pco2,"pCO2")
            self.make_tab_pco2()

        self.make_tab_log()
        self.make_tab1()
        self.make_tab_manual()
        self.make_tab_config()
        self.make_plotwidgets()
        # disable all manual control buttons

        # combine layout for plots and buttons
        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addWidget(self.plotwdigets_groupbox)
        hboxPanel.addWidget(self.tabs)

        # Disable all manual buttons in the Automatic mode
        self.manual_widgets_set_enabled(False)
        self.setLayout(hboxPanel)

    def make_tab_manual(self):
        self.tab_manual.layout = QtGui.QGridLayout()
        self.btn_manual_mode = self.create_button("Manual Control", True)
        self.btn_manual_mode.clicked.connect(self.btn_manual_mode_clicked)
        self.make_btngroupbox()
        self.make_slidergroupbox()
        self.tab_manual.layout.addWidget(self.btn_manual_mode)
        self.tab_manual.layout.addWidget(self.sliders_groupBox)
        self.tab_manual.layout.addWidget(self.buttons_groupBox)
        self.tab_manual.setLayout(self.tab_manual.layout)

    def make_tab_log(self):
        self.tab_log.layout = QtGui.QGridLayout()

        self.logTextBox = QTextEditLogger(self) # QtGui.QPlainTextEdit()
        # You can format what is printed to text box
        self.logTextBox.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(self.logTextBox)
        logging.getLogger().setLevel(logging.DEBUG)
        ##self.logTextBox.setReadOnly(True)
        if self.args.debug:
            logging.info("Starting in debug mode")
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

        if self.args.pco2:
            self.timerSave_pco2 = QtCore.QTimer()
            self.timerSave_pco2.timeout.connect(self.update_pCO2_data)

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
                    #self.btn_checkflow.setEnabled(True)

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
            print('unset adjusting')
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
        self.plotwdigets_groupbox = QtGui.QGroupBox()

        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget2 = pg.PlotWidget()

        self.plotwidget1.setYRange(1000, self.instrument.THR * 1.05)

        if self.args.co3:
            # self.plotwidget1.setYRange(1000,67000)
            self.plotwidget2.setYRange(0, 1)
            self.plotwidget1.setXRange(220, 260)
            self.plotwidget2.setXRange(220, 260)

        self.plotwidget1.setBackground("#19232D")
        self.plotwidget1.showGrid(x=True, y=True)
        self.plotwidget1.setTitle("LEDs intensities")

        # self.plotwidget2.setYRange(0,1.3)

        # self.plotwidget2.setXRange(410,610)
        self.plotwidget2.showGrid(x=True, y=True)
        self.plotwidget2.setBackground("#19232D")
        self.plotwidget2.setTitle("Last pH measurement")

        vboxPlot = QtGui.QVBoxLayout()
        vboxPlot.addWidget(self.plotwidget1)
        vboxPlot.addWidget(self.plotwidget2)
        if self.args.co3:
            for widget in [self.plotwidget1, self.plotwidget2]:
                for instrument, color in [[self.instrument.wvl1, "b"], [self.instrument.wvl2, "#eb8934"]]:
                    widget.addLine(x=instrument, y=None, pen=pg.mkPen(color, width=1, style=QtCore.Qt.DotLine))
        else:
            # Format for line spec is [x, y, color]
            line_specs = [
                [None, self.instrument.THR, "w"],
                [self.instrument.HI, None, "b"],
                [self.instrument.I2, None, "#eb8934"],
                [self.instrument.NIR, None, "r"],
            ]
            for x, y, color in line_specs:
                self.plotwidget1.addLine(x=x, y=y, pen=pg.mkPen(color, width=1, style=QtCore.Qt.DotLine))

        self.plotSpc = self.plotwidget1.plot()

        self.plot_calc_pH = self.plotwidget2.plot()
        self.after_calc_pH = self.plotwidget2.plot()
        self.lin_fit_pH = self.plotwidget2.plot()

        if self.args == "co3":
            self.plotAbs = self.plotwidget2.plot()
            color = ["r", "g", "b", "m", "y"]
            self.abs_lines = []
            for n_inj in range(self.instrument.ncycles):
                self.abs_lines.append(
                    self.plotwidget2.plot(x=self.wvls, y=np.zeros(len(self.wvls)), pen=pg.mkPen(color[n_inj]) )
                )

        self.plotwdigets_groupbox.setLayout(vboxPlot)

    def make_steps_groupBox(self):

        self.sample_steps_groupBox = QtWidgets.QGroupBox("Measuring Progress")

        self.sample_steps = [
            QtWidgets.QCheckBox("1. Adjusting LEDS"),
            QtWidgets.QCheckBox("2  Measuring dark,blank"),
            QtWidgets.QCheckBox("3. Measurement 1"),
            QtWidgets.QCheckBox("4. Measurement 2"),
            QtWidgets.QCheckBox("5. Measurement 3"),
            QtWidgets.QCheckBox("6. Measurement 4"),
        ]

        layout = QtGui.QGridLayout()

        [step.setEnabled(False) for step in self.sample_steps]
        [layout.addWidget(step) for step in self.sample_steps]
        self.sample_steps_groupBox.setLayout(layout)

    def make_tab1(self):

        self.make_steps_groupBox()

        self.tab1.layout = QtGui.QGridLayout()
        #self.textBox = QtGui.QTextEdit()
        #self.textBox.setReadOnly(True)
        #self.textBox.setOverwriteMode(True)

        self.StatusBox = QtGui.QTextEdit()
        #self.StatusBox.setReadOnly(True)

        self.last_measurement_table_groupbox = QtGui.QGroupBox("Last Measurement")
        self.live_update_groupbox = QtGui.QGroupBox("Live Updates")
        self.last_measurement_table = QtGui.QTableWidget(5, 2)
        self.last_measurement_table.horizontalHeader().setResizeMode(QtWidgets.QHeaderView.Stretch)
        self.last_measurement_table.verticalHeader().setResizeMode(QtWidgets.QHeaderView.Stretch)

        self.last_measurement_table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        self.last_measurement_table.verticalHeader().hide()
        self.last_measurement_table.horizontalHeader().hide()

        [self.fill_table_measurement(k, 0, v)
         for k, v in enumerate(["pH lab", "T lab", "pH insitu", "T insitu", "S insitu"])]

        self.ferrypump_box = QtWidgets.QCheckBox("Ferrybox pump is on")
        self.ferrypump_box.setEnabled(False)

        if fbox['pumping']:
            self.ferrypump_box.setChecked(True)

        self.table_grid = QtGui.QGridLayout()
        self.table_grid.addWidget(self.last_measurement_table)

        self.live_updates_grid = QtGui.QGridLayout()

        live_widgets = [self.t_insitu_live, self.s_insitu_live, self.t_lab_live, self.voltage_live]
        [n.setReadOnly(True) for n in live_widgets]

        #[self.live_updates_grid.addWidget(v, k, 1) for k, v in enumerate(live_widgets)]

        self.live_updates_grid.addWidget(QtGui.QLabel('T insitu'), 0, 0)
        self.live_updates_grid.addWidget(self.t_insitu_live, 0, 1)
        self.live_updates_grid.addWidget(QtGui.QLabel('S insitu'), 0, 2)
        self.live_updates_grid.addWidget(self.s_insitu_live, 0, 3)

        self.live_updates_grid.addWidget(QtGui.QLabel('T lab'), 1, 0)
        self.live_updates_grid.addWidget(self.t_lab_live, 1, 1)
        self.live_updates_grid.addWidget(QtGui.QLabel('Voltage'), 1, 2)
        self.live_updates_grid.addWidget(self.voltage_live, 1, 3)

        self.live_updates_grid.addWidget(self.ferrypump_box, 2, 2, 1, 2)
        self.live_updates_grid.addWidget(self.StatusBox, 3, 0, 1, 4)

        self.live_update_groupbox.setLayout(self.live_updates_grid)
        self.last_measurement_table_groupbox.setLayout(self.table_grid)

        if self.args.debug:
            logging.info("Starting in debug mode")

        self.btn_cont_meas = self.create_button("Continuous measurements", True)
        self.btn_single_meas = self.create_button("Single measurement", True)
        self.btn_calibr = self.create_button("Make calibration", True)

        self.btn_single_meas.clicked.connect(self.btn_single_meas_clicked)
        if not self.args.co3:
            self.btn_cont_meas.clicked.connect(self.btn_cont_meas_clicked)

        self.tab1.layout.addWidget(self.btn_cont_meas, 0, 0, 1, 1)
        self.tab1.layout.addWidget(self.btn_single_meas, 0, 1)

        self.tab1.layout.addWidget(self.sample_steps_groupBox, 1, 0, 1, 1)
        self.tab1.layout.addWidget(self.last_measurement_table_groupbox, 1, 1, 1, 1)

        self.tab1.layout.addWidget(self.live_update_groupbox, 2, 0, 1, 2)
        self.tab1.setLayout(self.tab1.layout)


    def append_logbox(self, message):
        t = datetime.now().strftime("%b-%d %H:%M:%S")
        logging.info(t + "  " + message)

    def fill_table_measurement(self, x, y, item):
        self.last_measurement_table.setItem(x, y, QtGui.QTableWidgetItem(item))

    def fill_live_updates_table(self, x, y, item):
        self.live_updates_table.setItem(x, y, QtGui.QTableWidgetItem(item))

    def fill_table_config(self, x, y, item):
        self.tableConfigWidget.setItem(x, y, QtGui.QTableWidgetItem(item))

    def make_tab_pco2(self):
        layout2 = QtGui.QGridLayout()
        groupbox = QtGui.QGroupBox('Updates from pCO2')
        layout = QtGui.QGridLayout()

        self.Tw_pco2_live= QtGui.QLineEdit()
        self.flow_pco2_live = QtGui.QLineEdit()
        self.Pw_pco2_live = QtGui.QLineEdit()
        self.Ta_pco2_live = QtGui.QLineEdit()
        self.Pa_pco2_live = QtGui.QLineEdit()
        self.Leak_pco2_live = QtGui.QLineEdit()
        self.CO2_pco2_live = QtGui.QLineEdit()
        self.TCO2_pco2_live = QtGui.QLineEdit()

        self.pco2_params = [self.Tw_pco2_live, self.flow_pco2_live, self.Pw_pco2_live,
                            self.Ta_pco2_live, self.Pa_pco2_live, self.Leak_pco2_live,
                            self.CO2_pco2_live, self.TCO2_pco2_live]
        self.pco2_labels = ['Water temperature', 'Water flow l/m', 'Water pressure"',
                            'Air temperature', 'Air pressure mbar', 'Leak Water detect',
                            'C02 ppm', 'T CO2 sensor']
        [layout.addWidget(self.pco2_params[n], n, 1) for n in range(len(self.pco2_params))]
        [layout.addWidget(QtGui.QLabel(self.pco2_labels[n]), n, 0) for n in range(len(self.pco2_params))]

        groupbox.setLayout(layout)
        layout2.addWidget(groupbox)
        self.tab_pco2.setLayout(layout2)

    def make_tab_config(self):
        self.tab_config.layout = QtGui.QGridLayout()
        # Define widgets for config tab
        self.btn_save_config = self.create_button("Save config", False)
        self.btn_save_config.clicked.connect(self.btn_save_config_clicked)

        self.dye_combo = QtGui.QComboBox()
        self.dye_combo.addItem("TB")
        self.dye_combo.addItem("MCP")

        index = self.dye_combo.findText(self.instrument.dye, QtCore.Qt.MatchFixedString)
        if index >= 0:
            self.dye_combo.setCurrentIndex(index)

        self.dye_combo.currentIndexChanged.connect(self.dye_combo_chngd)

        self.tableConfigWidget = QtGui.QTableWidget()
        self.tableConfigWidget.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        self.tableConfigWidget.verticalHeader().hide()
        self.tableConfigWidget.horizontalHeader().hide()
        self.tableConfigWidget.setRowCount(10)
        self.tableConfigWidget.setColumnCount(2)
        self.tableConfigWidget.horizontalHeader().setResizeMode(QtWidgets.QHeaderView.Stretch)


        self.fill_table_config(0, 0, "DYE type")
        self.tableConfigWidget.setCellWidget(0, 1, self.dye_combo)

        if not self.args.co3:
            [self.fill_table_config(k, 0, v) for k, v in enumerate(["NIR:", "HI-", "I2-"], 1)]
            [self.fill_table_config(k, 1, str(v)) for k, v in enumerate([self.instrument.NIR,
                                                                        self.instrument.HI,
                                                                        self.instrument.I2], 1)]
        self.fill_table_config(4, 0, "pH sampling interval (min)")
        self.samplingInt_combo = QtGui.QComboBox()
        [self.samplingInt_combo.addItem(n) for n in ['5', '7', '10','15', '20', '30', '60']]
        self.set_combo_index(self.samplingInt_combo, self.instrument.samplingInterval/60)
        self.tableConfigWidget.setCellWidget(4, 1, self.samplingInt_combo)
        self.samplingInt_combo.currentIndexChanged.connect(self.sampling_int_chngd)

        self.fill_table_config(5, 0, "Spectroph intergration time")
        self.specIntTime_combo = QtGui.QComboBox()
        [self.specIntTime_combo.addItem(str(n)) for n in range(100, 5000, 100)]
        self.update_spec_int_time_table()
        self.specIntTime_combo.currentIndexChanged.connect(self.specIntTime_combo_chngd)
        self.tableConfigWidget.setCellWidget(5, 1, self.specIntTime_combo)

        self.fill_table_config(6, 0, "Ship")
        self.ship_code_combo = QtGui.QComboBox()
        [self.ship_code_combo.addItem(t_id) for t_id in ['Standalone', 'NB', 'FA', 'TF']]
        self.tableConfigWidget.setCellWidget(6, 1, self.ship_code_combo)
        self.ship_code_combo.currentIndexChanged.connect(self.ship_code_changed)

        self.fill_table_config(7, 0, 'Temp probe id')
        self.temp_id_combo = QtGui.QComboBox()
        [self.temp_id_combo.addItem("Probe_" + str(n)) for n in range(1,10)]
        self.set_combo_index(self.temp_id_combo, self.instrument.TempProbe_id)
        self.tableConfigWidget.setCellWidget(7, 1, self.temp_id_combo)
        self.temp_id_combo.currentIndexChanged.connect(self.temp_id_combo_changed)

        self.fill_table_config(8, 0, 'Temp probe is calibrated')
        self.temp_id_is_calibr = QtGui.QCheckBox()

        if self.instrument.temp_iscalibrated:
            self.temp_id_is_calibr.setChecked(True)
        self.temp_id_is_calibr.setEnabled(False)
        self.tableConfigWidget.setCellWidget(8, 1, self.temp_id_is_calibr)
        self.set_combo_index(self.ship_code_combo, self.instrument.ship_code)

        self.fill_table_config(9, 0, 'Calibration check passed')
        self.fill_table_config(9, 1, "Didn't run calibration yet")

        self.manual_sal_group = QtGui.QGroupBox('Salinity used for manual measurement')
        l = QtGui.QHBoxLayout()
        self.whole_sal = QtGui.QComboBox()
        self.first_decimal = QtGui.QComboBox()
        self.second_decimal = QtGui.QComboBox()
        self.third_decimal = QtGui.QComboBox()

        [self.whole_sal.addItem(str(n)) for n in np.arange(0, 40)]
        self.whole_sal.setCurrentIndex(self.whole_sal.findText('35', QtCore.Qt.MatchFixedString))
        for combo in [self.first_decimal, self.second_decimal, self.third_decimal]:
            [combo.addItem(str(n)) for n in np.arange(0, 10)]
        l.addWidget(self.whole_sal)
        l.addWidget(QtGui.QLabel('.'))
        l.addWidget(self.first_decimal)
        l.addWidget(self.second_decimal)
        l.addWidget(self.third_decimal)

        self.manual_sal_group.setLayout(l)

        self.tab_config.layout.addWidget(self.btn_save_config, 0, 0, 1, 1)
        self.tab_config.layout.addWidget(self.tableConfigWidget, 1, 0, 1, 1)
        self.tab_config.layout.addWidget(self.btn_calibr, 2, 0)
        self.tab_config.layout.addWidget(self.manual_sal_group, 3, 0)
        self.tab_config.setLayout(self.tab_config.layout)

    def get_salinity_manual(self):
        salinity_manual = (int(self.whole_sal.currentText()) + int(self.first_decimal.currentText())/10
                                + int(self.second_decimal.currentText())/100 + int(self.third_decimal.currentText())/1000)
        return salinity_manual

    def set_combo_index(self, combo, text):
        index = combo.findText(str(text), QtCore.Qt.MatchFixedString)
        if index >= 0:
            combo.setCurrentIndex(index)

    def update_spec_int_time_table(self):
        index = self.specIntTime_combo.findText(str(self.instrument.specIntTime), QtCore.Qt.MatchFixedString)

        if index >= 0:
            self.specIntTime_combo.setCurrentIndex(index)

    def sampling_int_chngd(self, ind):
        minutes = int(self.samplingInt_combo.currentText())
        self.instrument.samplingInterval = int(minutes) * 60

    @asyncSlot()
    async def specIntTime_combo_chngd(self):
        new_int_time = int(self.specIntTime_combo.currentText())
        await self.updater.set_specIntTime(new_int_time)

    def ship_code_changed(self):
        self.instrument.ship_code = self.ship_code_combo.currentText()

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
        self.buttons_groupBox = QtGui.QGroupBox("Buttons GroupBox")
        btn_grid = QtGui.QGridLayout()

        self.btn_adjust_leds = self.create_button("Adjust Leds", True)
        self.btn_enbable_autoadj = self.create_button("Enable autoadjust", True)
        # self.btn_t_dark = self.create_button('Take dark',False)
        self.btn_leds = self.create_button("LEDs", True)
        self.btn_valve = self.create_button("Inlet valve", True)
        self.btn_stirr = self.create_button("Stirrer", True)
        self.btn_dye_pmp = self.create_button("Dye pump", True)
        self.btn_wpump = self.create_button("Water pump", True)

        self.btn_checkflow = self.create_button("Check flow", True)

        btn_grid.addWidget(self.btn_dye_pmp, 0, 0)
        #btn_grid.addWidget(self.btn_enbable_autoadj, 0, 1)
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
        self.sliders_groupBox = QtGui.QGroupBox("LED values")

        sldNames = ["Blue", "Orange", "Red"]
        self.sliders = []
        self.sldLabels, self.spinboxes = [], []
        self.plus_btns, self.minus_btns = [], []

        for ind in range(3):
            self.plus_btns.append(QtGui.QPushButton("+"))
            self.minus_btns.append(QtGui.QPushButton(" - "))
            self.plus_btns[ind].clicked.connect(self.led_plus_btn_clicked)
            self.minus_btns[ind].clicked.connect(self.led_minus_btn_clicked)
            self.sliders.append(QtGui.QSlider(QtCore.Qt.Horizontal))
            self.sliders[ind].setFocusPolicy(QtCore.Qt.NoFocus)
            self.sliders[ind].setTracking(True)
            self.spinboxes.append(QtGui.QSpinBox())
            # create connections
            if not self.args.co3:
                self.sliders[ind].valueChanged[int].connect(self.sld_change)
                self.spinboxes[ind].valueChanged[int].connect(self.spin_change)

        grid = QtGui.QGridLayout()

        grid.addWidget(QtGui.QLabel("Blue:"), 0, 0)
        grid.addWidget(QtGui.QLabel("Orange:"), 1, 0)
        grid.addWidget(QtGui.QLabel("Red:"), 2, 0)

        for n in range(3):
            grid.addWidget(self.sliders[n], n, 1)
            grid.addWidget(self.spinboxes[n], n, 2)
            grid.addWidget(self.minus_btns[n], n, 3)
            grid.addWidget(self.plus_btns[n], n, 4)

        self.sliders_groupBox.setLayout(grid)

    def create_button(self, name, check):
        Btn = QtGui.QPushButton(name)
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
                logging.info("in pump dye clicked")
                await self.instrument.pump_dye(3)
                self.btn_dye_pmp.setChecked(False)
        else:
            logging.info('Trying to pump in no pump mode')
            self.btn_dye_pmp.setChecked(False)

    @asyncSlot()
    async def btn_valve_clicked(self):
        await self.instrument.set_Valve(self.btn_valve.isChecked())

    def btn_save_config_clicked(self):

        with open(self.config_name, "r+") as json_file:
            j = json.load(json_file)

            j["pH"]["Default_DYE"] = self.dye_combo.currentText()

            j["Operational"]["Spectro_Integration_time"] = self.instrument.specIntTime
            j["Operational"]["Ship_Code"] = self.instrument.ship_code

            j["Operational"]["TEMP_PROBE_ID"] = self.instrument.TempProbe_id

            j["pH"]["LED1"] = self.instrument.LED1
            j["pH"]["LED3"] = self.instrument.LED2
            j["pH"]["LED4"] = self.instrument.LED3

            minutes = int(self.samplingInt_combo.currentText())
            j["Operational"]["SAMPLING_INTERVAL_SEC"] = minutes * 60
            json_file.seek(0)  # rewind
            json.dump(j, json_file, indent=4)
            json_file.truncate()

    def load_config_file(self):
        with open(self.config_name) as json_file:
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

        self.tableConfigWidget.setItem(2, 1, QtGui.QTableWidgetItem(str(self.instrument.HI)))
        self.tableConfigWidget.setItem(3, 1, QtGui.QTableWidgetItem(str(self.instrument.I2)))

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
        self.append_logbox("Leds {}".format(str(state)))

    def btn_leds_checked(self):
        state = self.btn_leds.isChecked()
        self.set_LEDs(state)

    def on_selFolderBtn_released(self):
        self.folderDialog = QtGui.QFileDialog()
        folder = self.folderDialog.getExistingDirectory(self, "Select directory")
        self.instrument.folderPath = folder + "/"

    def save_stability_test(self, datay):
        stabfile = os.path.join("/home/pi/pHox/sp_stability.log")
        if not self.args.co3:
            stabfile_df = pd.DataFrame(
                {
                    "datetime": [datetime.now().strftime(self.fformat)],
                    "led0": [datay[self.instrument.wvlPixels[0]]],
                    "led1": [datay[self.instrument.wvlPixels[1]]],
                    "led2": [datay[self.instrument.wvlPixels[2]]],
                    "specint": [self.instrument.specIntTime],
                }
            )
        elif self.args.co3:
            stabfile_df = pd.DataFrame(
                {
                    "wvl1": [datay[self.instrument.wvlPixels[0]]],
                    "wvl2": [datay[self.instrument.wvlPixels[1]]],
                    "specint": [self.instrument.specIntTime],
                }
            )

        if os.path.exists(stabfile):
            stabfile_df.to_csv(stabfile, mode="a", index=False, header=False)
        else:
            if not self.args.co3:
                stabfile_df = pd.DataFrame(columns=["datetime", "led0", "led1", "led2", "specint"])
            else:
                stabfile_df = pd.DataFrame(columns=["datetime", "wvl1", "wvl2", "specint"])

            stabfile_df.to_csv(stabfile, index=False, header=True)

    async def update_absorbance_plot(self, n_inj, spAbs):
        self.abs_lines[n_inj].setData(self.wvls, spAbs)
        await asyncio.sleep(0.005)

    def reset_absorp_plot(self):
        z = np.zeros(len(self.wvls))
        [self.update_absorbance_plot(n_inj, z) for n_inj in range(self.instrument.ncycles)]

    @asyncSlot()
    async def update_spectra_plot(self):
        self.updater.update_spectra_in_progress = True
        try:
            # I don't think this if statement is required
            if "Adjusting" not in self.major_modes and "Measuring" not in self.major_modes:
                datay = await self.instrument.spectrom.get_intensities()
                if self.args.stability:
                    self.save_stability_test(datay)
                self.plotSpc.setData(self.wvls, datay)
                # self.update_sensors_info()
        except Exception as e:
            logging.exception("could not read and set Data")
        finally:
            self.updater.update_spectra_in_progress = False

    def update_pH_plot(self):
        logging.info("in update pH plot")
        logging.info(f"self.x='{self.x}', self.y='{self.y}'")

        self.plot_calc_pH.setData(self.evalPar_df["Vol_injected"].values, self.pH_t_corr, pen=None,
                                  symbol="o", clear=True)
        self.after_calc_pH.setData(self.x, self.y, pen=None, symbol="o", symbolBrush='#30663c')

        logging.info("after first plot")
        logging.info(f"intercept {self.intercept}")
        self.lin_fit_pH.setData(self.x, self.intercept + self.slope * self.x)

    def update_sensors_info(self):
        t = datetime.now().strftime('%Y%M')
        self.t_insitu_live.setText(str(fbox['temperature']))
        self.s_insitu_live.setText(str(fbox['salinity']))

        voltage = round(self.instrument.get_Vd(3,
                                               self.instrument.vNTCch), prec["vNTC"])

        t_lab = round((self.instrument.TempCalCoef[0] * voltage)
                      + self.instrument.TempCalCoef[1], prec["Tdeg"])

        self.t_lab_live.setText(str(t_lab))
        self.voltage_live.setText(str(voltage))

        if fbox['pumping']:
            self.ferrypump_box.setChecked(True)
        else:
            self.ferrypump_box.setChecked(False)

    @asyncSlot()
    async def update_pCO2_data(self, pH=None):
        # update values
        for ch in range(5):
            V = self.instrument.get_Vd(2, ch + 1)
            X = 0
            for i in range(2):
                X += self.pco2_instrument.ftCalCoef[ch][i] * pow(V, i)
            self.pco2_instrument.franatech[ch] = round(X, 3)

        await self.pco2_instrument.get_pco2_values()
        d = self.pco2_instrument.franatech

        [v.setText("{}".format(d[k])) for k, v in enumerate(self.pco2_params)]
        if not self.args.localdev:
            self.save_pCO2_data(d)
        return

    def save_pCO2_data(self, d):
        t = datetime.now()
        label = t.isoformat("_")
        labelSample = label[0:19]
        logfile = os.path.join("/home/pi/pHox/data/", "pCO2.log")
        hdr = ""
        s = labelSample
        s += ",%.6f,%.6f,%.3f,%.3f" % (fbox["longitude"], fbox["latitude"], fbox["temperature"], fbox["salinity"],)
        s += ",%.2f,%.1f,%.1f,%.2f,%d,%.1f,%d" % (d[0], d[1], d[2], d[3], d[4], d[5], d[6])
        s += "\n"

        if not os.path.exists(logfile):
            self.pco2_df = pd.DataFrame(pd.DataFrame(d, columns=["Time,Lon,Lat,fbT,fbS,Tw,Flow,Pw,Ta,Pa,Leak,CO2,TCO2"]))

        else:
            self.pco2_df.loc[self.pco2_df.index.max() + 1] = d

        if not self.args.localdev:
            udp.send_data("PCO2," + s, self.instrument.ship_code)

    async def autoAdjust_IntTime(self):
        # Function calls autoadjust without leds
        adj, pixelLevel = await self.instrument.auto_adjust()
        if adj:
            self.append_logbox("Finished Autoadjust LEDS")
            self.update_spec_int_time_table()
            self.plotwidget1.plot([self.instrument.wvl2], [pixelLevel], pen=None, symbol="+")
        else:
            self.StatusBox.setText('Was not able do auto adjust')
        return adj

    @asyncSlot()
    async def update_plot_no_request(self):
        try:
            await self.update_spectra_plot_manual(self.instrument.spectrum)
        except:
            pass

    async def autoAdjust_LED(self):
        self.timer2 = QtCore.QTimer()
        self.timer2.start(1000)
        self.timer2.timeout.connect(self.update_plot_no_request)

        check = await self.instrument.precheck_leds_to_adj()
        if not check:
            (
                self.instrument.LED1,
                self.instrument.LED2,
                self.instrument.LED3,
                result,
            ) = await self.instrument.auto_adjust()

            logging.info(f"values after autoadjust: '{self.instrument.LEDS}'")
            if result:
                self.sliders[0].setValue(self.instrument.LED1)
                self.sliders[1].setValue(self.instrument.LED2)
                self.sliders[2].setValue(self.instrument.LED3)
                self.timerSpectra_plot.setInterval(self.instrument.specIntTime)
                self.timer2.stop()
                # self.plot_sp_levels()
                self.update_spec_int_time_table()
                self.append_logbox("Adjusted LEDS with intergration time {}".format(self.instrument.specIntTime))

                datay = await self.instrument.spectrom.get_intensities()
                await self.update_spectra_plot_manual(datay)
            else:
                self.StatusBox.setText('Not able to adjust LEDs automatically')
            self.timer2.stop()
        else:
            result = check
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
                baseline_spectrum = await self.instrument.spectrom.get_intensities()
                # inject die twice (with n shots determined by config), this includes stirring
                await self.inject_dye(3)
                await self.inject_dye(3)

                dyed_spectrum = await self.instrument.spectrom.get_intensities()
                rms_spectrum_difference = np.sqrt(np.mean(np.square(baseline_spectrum-dyed_spectrum)))
                logging.debug(f'Initial diff: {rms_spectrum_difference}')
                # Re-open the valve
                await self.instrument.set_Valve(False)

                # Start the flow check
                start = datetime.utcnow()
                check_succeeded = False
                while datetime.utcnow()-start < timedelta(seconds=20):
                    diluted_spectrum = await self.instrument.spectrom.get_intensities()
                    new_rms_spectrum_difference = np.sqrt(np.mean(np.square(baseline_spectrum - diluted_spectrum)))
                    logging.debug(f'got another spectrum, new diff: {new_rms_spectrum_difference}')
                    if rms_spectrum_difference*.2 > new_rms_spectrum_difference:
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
            self.set_major_mode("Continuous")
            if "Measuring" not in self.major_modes:
                self.until_next_sample = self.instrument.samplingInterval

            self.timer_contin_mode.start(self.instrument.samplingInterval * 1000)

            self.StatusBox.setText(f'Next sample in {self.until_next_sample / 60} minutes ')
            self.infotimer_contin_mode.start(self.infotimer_step * 1000)
        else:
            self.unset_major_mode("Continuous")
            self.StatusBox.clear()
            self.timer_contin_mode.stop()
            self.until_next_sample = self.instrument.samplingInterval
            self.infotimer_contin_mode.stop()

    @asyncSlot()
    async def btn_calibr_clicked(self):

        async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Calibration"):
            logging.info("clicked calibration")

            valve_turned = QtGui.QMessageBox.question(self, "important message!!!",
                                                      "Manually turn the valve to calibration mode",
                                                      QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
            valve_turned_confirm = QtGui.QMessageBox.question(self, "important message!!!",
                                                              "ARE YOU SURE YOU TURNED THE VALVE???",
                                                              QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)

            if valve_turned == QtGui.QMessageBox.Yes and valve_turned_confirm == QtGui.QMessageBox.Yes:
                folderPath = self.get_folderPath()
                flnmStr, timeStamp = self.get_filename()
                await self.sample(folderPath, flnmStr, timeStamp)

                v = QtGui.QMessageBox.question(self, "important message!!!",
                                               "Manually turn the valve back to ferrybox mode",
                                           QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)

                v = QtGui.QMessageBox.question(self, "important message!!!",
                                               "ARE YOU SURE YOU TURNED THE VALVE???",
                                           QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
            self.btn_calibr.setChecked(False)


    @asyncSlot()
    async def btn_single_meas_clicked(self):
        async with self.updater.disable_live_plotting():
            # Start single sampling process
            logging.info("clicked single meas ")
            message = QtGui.QMessageBox.question(
                self,
                "important message!!!",
                "Did you pump to flush the sampling chamber?",
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
            )
            if message == QtGui.QMessageBox.No:
                self.btn_single_meas.setChecked(False)
                return

            flnmStr, timeStamp = self.get_filename()

            text, ok = QtGui.QInputDialog.getText(None, "Enter Sample name", flnmStr)
            if ok:
                if text != "":
                    flnmStr = text
                folderPath = self.get_folderPath()
                # disable all btns in manual tab (There are way more buttons now)
                self.btn_cont_meas.setEnabled(False)
                self.btn_single_meas.setEnabled(False)
                self.btn_calibr.setEnabled(False)  # what does calibration do?

                await self.sample(folderPath, flnmStr, timeStamp)
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
              and "Measurement" not in self.major_modes):
            logging.debug('> 3 min Until next sample, Reenable Manual control button ')
            self.btn_manual_mode.setEnabled(True)

        if 'Measurement' not in self.major_modes:
            if self.until_next_sample > 60:
                self.StatusBox.setText(f'Next sample in {self.until_next_sample/60} minutes ')
            else:
                self.StatusBox.setText(f'Next sample in {self.until_next_sample} seconds ')

        self.until_next_sample -= self.infotimer_step


    @asyncSlot()
    async def continuous_mode_timer_finished(self):
        logging.info("continuous_mode_timer_finished")
        self.append_logbox("continuous_mode_timer_finished")
        self.until_next_sample = self.instrument.samplingInterval
        if "Measuring" not in self.major_modes:
            flnmStr, timeStamp = self.get_filename()
            folderPath = self.get_folderPath()
            if fbox["pumping"] == 1 or fbox["pumping"] is None:  # None happens when not connected to the ferrybox
                await self.sample(folderPath, flnmStr, timeStamp)
        else:
            logging.info("Skipped a sample because the previous measurement is still ongoing")
            pass  # TODO Increase interval

    def get_final_pH(self, timeStamp):
        # get final pH
        logging.debug(f'get final pH {self.evalPar_df}')
        p = self.instrument.pH_eval(self.evalPar_df)
        (pH_lab, T_lab, perturbation, evalAnir, pH_insitu, self.x, self.y, self.slope, self.intercept, self.pH_t_corr) = p

        self.pH_log_row = pd.DataFrame(
            {
                "Time": [timeStamp[0:16]],
                "Lon": [fbox["longitude"]],
                "Lat": [fbox["latitude"]],
                "fb_temp": [fbox["temperature"]],
                "fb_sal": [fbox["salinity"]],
                "SHIP": [self.instrument.ship_code],
                "pH_lab": [pH_lab],
                "T_lab": [T_lab],
                "perturbation": [perturbation],
                "evalAnir": [evalAnir],
                "pH_insitu": [pH_insitu],
            }
        )

    def save_results(self, folderPath, flnmStr):
        logging.info('saving results')
        if self.args.localdev:
            logging.debug('saving results localdev')
            folderPath = os.getcwd()
            self.save_logfile_df(folderPath, flnmStr)
            self.send_to_ferrybox()
            return
        # self.sample_steps[7].setChecked(True)
        self.append_logbox("Save spectrum data to file")
        self.save_spt(folderPath, flnmStr)
        self.append_logbox("Save evl data to file")
        self.save_evl(folderPath, flnmStr)
        logging.info("Send data to ferrybox")
        self.append_logbox("Send data to ferrybox")
        self.send_to_ferrybox()

        self.append_logbox("Save final data in %s" % (folderPath + "pH.log"))
        self.save_logfile_df(folderPath, flnmStr)

    def update_table_last_meas(self):
        if not self.args.co3:
            [
                self.fill_table_measurement(k, 1, str(self.pH_log_row[v].values[0]))
                for k, v in enumerate(["pH_lab", "T_lab", "pH_insitu", "fb_temp", "fb_sal"], 0)
            ]

        else:
            logging.info("to be filled with data")

    def update_LEDs(self):
        self.sliders[0].setValue(self.instrument.LED1)
        self.sliders[1].setValue(self.instrument.LED2)
        self.sliders[2].setValue(self.instrument.LED3)

    def _autostart(self, restart=False):
        self.append_logbox("Inside _autostart...")
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
        self.append_logbox("Initial automatic start at pump enabled")
        self.timerAuto.stop()
        self.timerAuto.timeout.disconnect(self.autostart_pump)
        self._autostart()
        # Continuously checking if pump is still working or not
        self.timerAuto.timeout.connect(self.check_autostop_pump)
        self.timerAuto.start(10000)
        return

    def check_autostop_pump(self):

        if fbox['pumping'] is None:
            print ('non')
            self.StatusBox.setText("No data from UDP fbox['pumping'] is None")
            logging.debug('No udp connection')

        elif fbox['pumping'] == 0:
            if 'Paused' not in self.major_modes:
                self.timer_contin_mode.stop()
                self.set_major_mode('Paused on pump')
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
        self.append_logbox("Inside autorun func...")
        logging.info("start autorun")
        if self.instrument._autostart:
            if self.instrument._automode == "time":
                self.StatusBox.setText("Automatic scheduled start enabled")
                self.timerAuto.timeout.connect(self.autostart_time)
                self.timerAuto.start(1000)

            elif self.instrument._automode == "pump":
                self.StatusBox.setText("Automatic start at pump enabled")
                self.timerAuto.timeout.connect(self.autostart_pump)
                self.timerAuto.start(1000)

            elif self.instrument._autostart and self.instrument._automode == "now":
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

    async def sample(self, folderPath, flnmStr, timeStamp):
        async with self.updater.disable_live_plotting(), self.ongoing_major_mode_contextmanager("Measuring"):
            # Step 0. Start measurement, create new df,
            # reset Absorption plot
            # pump if single, close the valve
            logging.info(f"sample, mode is {self.major_modes}")
            self.StatusBox.setText("Ongoing measurement")

            self.create_new_df()

            if self.args == "co3":
                self.reset_absorp_plot()

            await self.pump_if_needed()

            self.append_logbox("Closing the valve ...")
            await self.instrument.set_Valve(True)

            # Step 1. Autoadjust LEDS
            self.sample_steps[0].setChecked(True)
            self.append_logbox("Autoadjust LEDS")
            res = await self.call_autoAdjust()
            logging.info(f"res after autoadjust: '{res}")
            if res:
                #logging.info("could not adjust leds")

                # Step 2. Take dark and blank
                self.sample_steps[1].setChecked(True)
                await asyncio.sleep(0.05)
                dark = await self.measure_dark()
                blank_min_dark = await self.measure_blank(dark)

                # Steps 3,4,5,6 Measurement cycle
                await self.measurement_cycle(blank_min_dark, dark)

                # Step 7 Open valve
                logging.info("Opening the valve ...")
                self.append_logbox("Opening the valve ...")
                await self.instrument.set_Valve(False)

        if not self.args.co3 and res:
            self.get_final_pH(timeStamp)
            self.append_logbox("Single measurement is done...")
            self.append_logbox('Saving results')
            self.save_results(folderPath, flnmStr)
            self.update_pH_plot()
            self.update_table_last_meas()
            if 'Calibration' in self.major_modes:

                dif_pH = self.pH_log_row['pH_insitu'].values - self.instrument.buffer_pH_value
                self.fill_table_config(9, 1, f"pH diff after calibration {dif_pH}")

        self.StatusBox.setText('Finished the measurement')
        [step.setChecked(False) for step in self.sample_steps]

    def get_folderPath(self):
        if self.args.localdev:
            return "IN_LOCALDEV_MODE__NOT_A_FILE"
        if self.args == "co3":
            if "Calibration" in self.major_modes:
                folderPath = "/home/pi/pHox/data_co3_calibr/"
            else:
                folderPath = "/home/pi/pHox/data_co3/"
        else:
            if "Calibration" in self.major_modes:
                folderPath = "/home/pi/pHox/data_calibr/"
            else:
                folderPath = "/home/pi/pHox/data/"

        if not os.path.exists(folderPath):
            os.makedirs(folderPath)
        return folderPath

    def create_new_df(self):

        self.spCounts_df = pd.DataFrame(columns=["Wavelengths", "dark", "blank"])
        self.spCounts_df["Wavelengths"] = ["%.2f" % w for w in self.wvls]
        if self.args == "co3":
            self.CO3_eval = pd.DataFrame(
                columns=["CO3", "e1", "e2e3", "log_beta1_e2", "vNTC", "S", "A1", "A2", "R", "Tdeg", "Vinj", " S_corr", ]
            )
        else:
            self.evalPar_df = pd.DataFrame(
                columns=[
                    "pH",
                    "pK",
                    "e1",
                    "e2",
                    "e3",
                    "vNTC",
                    "salinity",
                    "A1",
                    "A2",
                    "Tdeg",
                    "S_corr",
                    "Anir",
                    "Vol_injected",
                    "TempProbe_id",
                    "Probe_iscalibr",
                    "TempCalCoef1",
                    "TempCalCoef2",
                    "DYE",
                ]
            )

    async def pump_if_needed(self):
        if (
                self.instrument.ship_code == "Standalone" and "Continuous" in self.major_modes
        ) or "Calibration" in self.major_modes:
            self.append_logbox("pumping")
            await self.instrument.pumping(self.instrument.pumpTime)
        else:
            self.append_logbox("pumping is not needed ")

    async def measure_dark(self):
        # turn off light and LED
        if self.args.co3:
            self.instrument.turn_off_relay(self.instrument.light_slot)
            logging.info("turn of the light source")
            await asyncio.sleep(1)
        else:
            self.set_LEDs(False)

        # grab spectrum
        dark = await self.instrument.spectrom.get_intensities(self.instrument.specAvScans, correct=True)

        if self.args.co3:
            # Turn on the light source
            self.instrument.turn_on_relay(self.instrument.light_slot)
            logging.info("turn on the light source")
            await asyncio.sleep(2)
        else:
            # Turn on LEDs after taking dark
            self.set_LEDs(True)
        self.instrument.spectrum = dark
        self.spCounts_df["dark"] = dark
        await self.update_spectra_plot_manual(dark)
        return dark

    async def update_spectra_plot_manual(self, spectrum):
        self.plotSpc.setData(self.wvls, spectrum)
        await asyncio.sleep(0.05)

    async def measure_blank(self, dark):
        logging.info("Measuring blank...")
        self.append_logbox("Measuring blank...")

        blank = await self.instrument.spectrom.get_intensities(self.instrument.specAvScans, correct=True)
        blank_min_dark = blank - dark

        self.instrument.spectrum = blank
        self.spCounts_df["blank"] = blank
        await self.update_spectra_plot_manual(blank)
        return blank_min_dark

    async def measurement_cycle(self, blank_min_dark, dark):
        for n_inj in range(self.instrument.ncycles):
            logging.info(f"n_inj='{n_inj}")
            self.sample_steps[n_inj + 2].setChecked(True)
            await asyncio.sleep(0.05)
            vol_injected = round(
                self.instrument.dye_vol_inj * (n_inj + 1) * self.instrument.nshots, prec["vol_injected"],
            )
            dilution = self.instrument.Cuvette_V / (vol_injected + self.instrument.Cuvette_V)

            vNTC = await self.inject_dye(n_inj)
            spAbs_min_blank = await self.calc_spectrum(n_inj, blank_min_dark, dark)
            # self.append_logbox('Calculate init pH')
            logging.info("Calculate init pH")

            if self.args == "co3":
                self.CO3_eval.loc[n_inj] = self.instrument.calc_CO3(spAbs_min_blank, vNTC, dilution, vol_injected)
                await self.update_absorbance_plot(n_inj, spAbs_min_blank)
            else:
                if 'Continuous' not in self.major_modes and 'Calibration' not in self.major_modes:
                    manual_salinity = self.get_salinity_manual()
                elif 'Calibration' in self.major_modes:
                    manual_salinity = self.instrument.buffer_sal
                else:
                    manual_salinity = None
                self.evalPar_df.loc[n_inj] = self.instrument.calc_pH(spAbs_min_blank, vNTC,
                                                                     dilution, vol_injected, manual_salinity)
        return

    async def inject_dye(self, n_inj):
        # create dataframe and store

        self.append_logbox("Start stirrer")
        self.instrument.turn_on_relay(self.instrument.stirrer_slot)
        self.append_logbox("Dye Injection %d:" % (n_inj + 1))

        if not self.args.nodye:
            await self.instrument.pump_dye(self.instrument.nshots)

        self.append_logbox("Mixing")
        await asyncio.sleep(self.instrument.mixT)

        self.append_logbox("Stop stirrer")
        self.instrument.turn_off_relay(self.instrument.stirrer_slot)

        self.append_logbox("Wait")
        await asyncio.sleep(self.instrument.waitT)

        # measuring Voltage for temperature probe
        vNTC = self.instrument.get_Vd(3, self.instrument.vNTCch)
        return vNTC

    async def calc_spectrum(self, n_inj, blank_min_dark, dark):
        self.append_logbox("Get spectrum")
        # measure spectrum after injecting nshots of dye
        # Write spectrum to the file
        if self.args.localdev:
            logging.info("in debug")
            postinj_spec = await self.instrument.spectrom.get_intensities(self.instrument.specAvScans, correct=True)
            postinj_spec_min_dark = postinj_spec  # - dark
            spAbs_min_blank = postinj_spec_min_dark
            await self.update_spectra_plot_manual(postinj_spec)
        else:
            postinj_spec = await self.instrument.spectrom.get_intensities(self.instrument.specAvScans, correct=True)
            self.instrument.spectrum = postinj_spec
            await self.update_spectra_plot_manual(postinj_spec)

            postinj_spec_min_dark = postinj_spec - dark
            # Absorbance
            spAbs_min_blank = -np.log10(postinj_spec_min_dark / blank_min_dark)

        self.spCounts_df[str(n_inj)] = postinj_spec
        return spAbs_min_blank

    def save_evl(self, folderPath, flnmStr):
        evlpath = folderPath + "evl/"
        if not os.path.exists(evlpath):
            os.makedirs(evlpath)
        flnm = evlpath + flnmStr + ".evl"
        if self.args.co3:
            self.CO3_eval.to_csv(flnm, index=False, header=True)
        else:
            self.evalPar_df.to_csv(flnm, index=False, header=True)

    def save_spt(self, folderPath, flnmStr):
        sptpath = folderPath + "spt/"
        if not os.path.exists(sptpath):
            os.makedirs(sptpath)
        self.spCounts_df.T.to_csv(sptpath + flnmStr + ".spt", index=True, header=False)

    def save_logfile_df(self, folderPath, flnmStr):
        logging.info("save log file df")
        hour_log_path = folderPath + "/logs/"
        if not os.path.exists(hour_log_path):
            os.makedirs(hour_log_path)

        hour_log_flnm = os.path.join(hour_log_path, datetime.now().strftime("%Y%m%d_%H")) + '.log'
        if not os.path.exists(hour_log_flnm):
            self.pH_log_row.to_csv(hour_log_flnm, index=False, header=True)
        else:
            self.pH_log_row.to_csv(hour_log_flnm, mode='a', index=False, header=False)

        logging.info(f"hour_log_path: {hour_log_path}")
        hour_log_flnm = hour_log_path + flnmStr + ".log"
        logging.info(f"hour_log_flnm: {hour_log_flnm}")

        logfile = os.path.join(folderPath, 'pH.log')

        if os.path.exists(logfile):
            self.pH_log_row.to_csv(logfile, mode='a', index=False, header=False)
        else:
            self.pH_log_row.to_csv(logfile, index=False, header=True)

        logging.info("saved log_df")

    def send_to_ferrybox(self):
        row_to_string = self.pH_log_row.to_csv(index=False, header=True).rstrip()
        udp.send_data("$PPHOX," + row_to_string + ",*\n", self.instrument.ship_code)


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
        await self.main_qt_panel.instrument.spectrom.set_integration_time(new_int_time)
        self.main_qt_panel.instrument.specIntTime = new_int_time
        self.main_qt_panel.timerSpectra_plot.setInterval(self.get_interval_time())


class boxUI(QtGui.QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parser = argparse.ArgumentParser()

        try:
            box_id = open("/home/pi/box_id.txt", "r").read()
        except:
            box_id = "template"
        config_name = "configs/config_" + box_id + ".json"

        parser.add_argument("--nodye", action="store_true")
        parser.add_argument("--pco2", action="store_true")
        parser.add_argument("--co3", action="store_true")
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("--localdev", action="store_true")
        parser.add_argument("--stability", action="store_true")

        self.args = parser.parse_args()

        # logging.basicConfig(level=logging.DEBUG if self.args.debug else logging.INFO,
        #                     format=" %(asctime)s - %(name)s - %(levelname)s - %(message)s")
        logging.root.level = logging.DEBUG if self.args.debug else logging.INFO
        if self.args.debug:
            for name, logger in logging.root.manager.loggerDict.items():
                if 'asyncqt' in name:  # disable debug logging on 'asyncqt' library since it's too much lines
                    logger.level = logging.INFO

        if self.args.pco2:
            self.setWindowTitle("pH Box Instrument, parameters pH and pCO2")
        elif self.args.co3:
            self.setWindowTitle("Box Instrument, parameter CO3")
        else:
            self.setWindowTitle("pH box")

        self.main_widget = Panel(self, self.args, config_name)
        self.setCentralWidget(self.main_widget)
        self.showMaximized()
        self.main_widget.autorun()

        with loop:
            sys.exit(loop.run_forever())

    def closeEvent(self, event):
        result = QtGui.QMessageBox.question(
            self, "Confirm Exit...", "Are you sure you want to exit ?", QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
        )
        event.ignore()

        if result == QtGui.QMessageBox.Yes:
            if self.args.co3:
                self.main_widget.instrument.turn_off_relay(self.main_widget.instrument.light_slot)

            self.main_widget.timer_contin_mode.stop()
            self.main_widget.timerSpectra_plot.stop()
            logging.info("timers are stopped")

            udp.UDP_EXIT = True
            udp.server.join()
            if not udp.server.is_alive():
                logging.info("UDP server closed")
            try:
                self.main_widget.instrument.spectrom.spec.close()
            except:
                logging.info('Erroe while closing spectro')
            self.main_widget.close()
            QtGui.QApplication.quit()
            try:
                sys.exit()
            except:
                print("Exiting")

            event.accept()


# loop has to be declared for testing to work
loop = None
if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    d = os.getcwd()
    qss_file = open("styles.qss").read()
    app.setStyleSheet(qss_file)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    ui = boxUI()

    app.exec_()
