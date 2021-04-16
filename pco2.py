#! /usr/bin/python
import serial
import serial.tools.list_ports
import logging

try:
    import pigpio
    import RPi.GPIO as GPIO
    from ADCDifferentialPi import ADCDifferentialPi
except:
    pass

import os, sys
from util import get_base_folderpath, box_id

import struct
try:
    import warnings, time, RPi.GPIO
    import RPi.GPIO as GPIO
except:
    pass

from datetime import datetime
from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QLineEdit, QTabWidget, QWidget, QPushButton, QComboBox
from PyQt5.QtWidgets import (QGroupBox, QMessageBox, QLabel, QGridLayout, QRadioButton,
                              QApplication, QMainWindow)

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
from asyncqt import QEventLoop, asyncSlot, asyncClose
import asyncio

class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [datetime.fromtimestamp(value) for value in values]
        
class pco2_instrument(object):
    def __init__(self, base_folderpath, panelargs):
        ports = list(serial.tools.list_ports.comports())
        self.args = panelargs
        if not self.args.localdev:
            self.port = ports[0]
        self.base_folderpath = base_folderpath
        self.path = self.base_folderpath + "/data_pCO2/"

        self.co2 = 990
        self.co2_temp = 999
        self.buff = None
        #self.serial_data = pd.DataFrame

        if not os.path.exists(self.path):
            os.mkdir(self.path)

        try:
            self.connection = serial.Serial(self.port.device, baudrate=115200, timeout=5,
                                            parity=serial.PARITY_NONE,
                                            stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
                                            rtscts=False, dsrdtr=False,
                                            xonxoff=False)
            logging.debug(self.connection)
        except:
            logging.debug('Was not able to find connection to the instrument')
            self.connection = None

        f = config_file["pCO2"]

        self.ship_code = config_file['Operational']["Ship_Code"]
        self.ppco2_string_version = f['PPCO2_STRING_VERSION']

    async def save_pCO2_data(self, data, values):
        data['time'] = data['time'].dt.strftime("%Y%m%d_%H%M%S")

        columns1 = list(data.columns)
        row = list(data.iloc[0])


        logfile = os.path.join(self.path, "pCO2.log")
        columns2 = ["Lon", "Lat", "fb_temp", "fb_sal", "Tw", "Ta_mem", "Qw", "Pw", "Pa_env", "Ta_env"]
        columnss = columns1 + columns2

        self.pco2_df = pd.DataFrame(columns=columnss)
        pco2_row = row + [fbox["longitude"], fbox["latitude"],
                    fbox["temperature"], fbox["salinity"]] + values

        self.pco2_df.loc[0] = pco2_row
        logging.debug('Saving pco2 data')

        if not os.path.exists(logfile):
            self.pco2_df.to_csv(logfile, index=False, header=True)
        else:
            self.pco2_df.to_csv(logfile, mode='a', index=False, header=False)

        return self.pco2_df


class testconnection():
    def __init__(self):
        pass

    def read(self,val):
        return b'\x07'

    def flushInput(self):
        pass


class only_pco2_instrument(pco2_instrument):
    # Class for communication with Raspberry PI for the only pco2 case
    def __init__(self, base_folderpath, panelargs):
        super().__init__(base_folderpath, panelargs)
        self.adc = ADCDifferentialPi(0x68, 0x69, 14)
        self.adc.set_pga(1)

    def get_Voltage(self, nAver, channel):
        v = 0.0000
        for i in range(nAver):
            v += self.adc.read_voltage(channel)
        Voltage = round(v / nAver, prec["Voltage"])
        return Voltage


class test_pco2_instrument(pco2_instrument):
    def __init__(self, base_folderpath, panelargs):
        super().__init__(base_folderpath, panelargs)

        self.connection = testconnection()
        print (self.connection)

    '''async def get_pco2_values(self):
        self.co2 = np.random.randint(400, 600)
        self.co2_temp = np.random.randint(1, 10)'''

    def get_Voltage(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        return v / nAver

    def close(self):
        print ('close connection, localtest')
        logging.debug('close connection, localtest')


class tab_pco2_class(QWidget):
    def __init__(self):
        super(QWidget, self).__init__()
        
        groupbox = QGroupBox('Updates from pCO2')
        self.group_layout = QGridLayout()
        layout = QGridLayout()

        self.Tw_pco2_live = QLineEdit()
        self.Ta_mem_pco2_live = QLineEdit()
        self.Qw_pco2_live = QLineEdit()
        self.Pw_pco2_live = QLineEdit()
        self.Pa_env_pco2_live = QLineEdit()
        self.Ta_env_pco2_live = QLineEdit()
        self.CO2_pco2_live = QLineEdit()
        self.VP_Vout_live = QLineEdit()
        self.VT_Vout_live = QLineEdit()

        self.fbox_temp_live = QLineEdit()
        self.fbox_sal_live = QLineEdit()

        self.pco2_params = [self.Tw_pco2_live, self.Ta_mem_pco2_live, self.Qw_pco2_live,
                            self.Pw_pco2_live, self.Pa_env_pco2_live, self.Ta_env_pco2_live,
                            self.VP_Vout_live, self.VT_Vout_live,self.CO2_pco2_live]

        self.pco2_labels = ['Water_temperature', 'Air_Temperature_membr', 'Water_Flow',
                            'Water_Pressure', 'Air_Pressure_env', 'Air_Temperature_env',
                            'VP_Vout_live', 'VT_Vout_live','C02_ppm' ]

        '''self.rbtns = []
        for k,n in enumerate(self.pco2_labels[:-1]):
            b = QRadioButton(n)
            #self.rbtns.append(b)
            #b.toggled.connect(self.onClicked_radio)
            layout.addWidget(b, k, 0)'''

        #self.rbtns[0].setChecked(True)
        self.parameter_to_plot = 'Water_temperature'
        [layout.addWidget(self.pco2_params[n], n, 1) for n in range(len(self.pco2_params))]
        [layout.addWidget(QLabel(self.pco2_labels[n]), n, 0) for n in range(len(self.pco2_params))]

        #layout.addWidget(QLabel(self.pco2_labels[-1]), 8, 0)
        layout.addWidget(QLabel('fbox_temp'), 9, 0)
        layout.addWidget(QLabel('fbox_sal'), 10, 0)
        layout.addWidget(self.fbox_temp_live, 9, 1)
        layout.addWidget(self.fbox_sal_live, 10, 1)

        #layout.addWidget(QLabel(self.pco2_labels[-3]), 6, 0)
        #layout.addWidget(QLabel(self.pco2_labels[-2]), 7, 0)
        groupbox.setLayout(layout)
        self.group_layout.addWidget(groupbox, 0, 0, 1, 2)


    def onClicked_radio(self):
        radioBtn = self.sender()

        if radioBtn.isChecked():
            self.parameter_to_plot = radioBtn.text()

    async def update_tab_ai_values(self, values):
        all_val = values
        [self.pco2_params[n].setText(str(all_val[n])) for n in range(len(values))]
        self.fbox_temp_live.setText(str(fbox['temperature']))
        self.fbox_sal_live.setText(str(fbox['salinity']))

    async def update_tab_serial_values(self, data):
        all_val = [ data['VP'].values[0], data['VT'].values[0],data['ppm'].values[0]]
        [self.pco2_params[n].setText(str(all_val[n])) for n in range(5,len(all_val))]

class Panel_PCO2_only(QWidget):
    # Class for ONLY PCO2 Instrument
    def __init__(self, parent, panelargs):
        super(QWidget, self).__init__(parent)
        self.args = panelargs
        self.measuring = False
        if self.args.localdev:
            self.pco2_instrument = test_pco2_instrument(base_folderpath, panelargs)
        else:
            self.pco2_instrument = only_pco2_instrument(base_folderpath, panelargs)

        self.pco2_timeseries = pd.DataFrame(columns = [
            'times','CO2_values','Water_temperature',
            'Air_Temperature_membr','Water_Pressure','Air_Pressure_env',
            'Water_Flow','Air_Temperature_env','VP_Vout_live', 'VT_Vout_live', 'fbox_temp', 'fbox_sal'])

        self.tabs = QTabWidget()
        self.tab_pco2 = tab_pco2_class()
        self.Co2_CalCoef = config_file['pCO2']["CO2"]["Calibr"]
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

        hboxPanel = QtGui.QGridLayout()
        hboxPanel.addWidget(self.plotwidget_pco2, 0, 0)
        hboxPanel.addWidget(self.plotwidget_var, 1, 0)
        hboxPanel.addWidget(self.plotwidget_var2, 2, 0)
        hboxPanel.addWidget(self.tabs, 0, 1, 3, 1)

        self.timerSave_pco2 = QtCore.QTimer()
        self.timerSave_pco2.timeout.connect(self.timer_finished)

        self.btn_measure = QPushButton('Measure')
        self.btn_measure.setCheckable(True)
        self.btn_measure.clicked[bool].connect(self.btn_measure_clicked)

        self.btn_measure_once = QPushButton('Measure Once')
        self.btn_measure_once.setCheckable(True)
        self.btn_measure_once.clicked[bool].connect(self.btn_measure_once_clicked)

        self.StatusBox = QtGui.QTextEdit()
        self.StatusBox.setReadOnly(True)


        self.plotvar1_combo = QComboBox()
        [self.plotvar1_combo.addItem(str(item)) for item in self.tab_pco2.pco2_labels[:-1]+['fbox_temp','fbox_sal']]
        self.plotvar2_combo = QComboBox()
        [self.plotvar2_combo.addItem(str(item)) for item in self.tab_pco2.pco2_labels[:-1]+['fbox_temp','fbox_sal']]

        self.tab_pco2.group_layout.addWidget(QLabel('plot 2'), 1, 0)
        self.tab_pco2.group_layout.addWidget(self.plotvar1_combo, 1, 1)

        self.tab_pco2.group_layout.addWidget(QLabel('plot 3'), 2, 0)
        self.tab_pco2.group_layout.addWidget(self.plotvar2_combo, 2, 1)

        self.tab_pco2.group_layout.addWidget(self.btn_measure, 3, 0)
        self.tab_pco2.group_layout.addWidget(self.btn_measure_once, 3, 1)
        self.tab_pco2.group_layout.addWidget(self.StatusBox, 4, 0,1,1)

        self.no_serial = QPushButton('Ignore Serial Connection')
        self.no_serial.setCheckable(True)
        self.tab_pco2.group_layout.addWidget(self.no_serial, 4, 1,1,1)
        self.tab_pco2.setLayout(self.tab_pco2.group_layout)

        self.setLayout(hboxPanel)


    def close(self):
        try:
            self.pco2_instrument.connection.close()
        except:
            pass
        return

    def valve_message(self, type="Confirm Exit"):

        msg = QMessageBox()

        image = 'utils/pHox_question.png'

        pixmap = QPixmap(QPixmap(image)).scaledToHeight(100, QtCore.Qt.SmoothTransformation)

        msg.setIconPixmap(pixmap)
        msg.setWindowIcon(QtGui.QIcon('utils/pHox_logo.png'))

        msg.setWindowTitle('Important')
        msg.setText("Are you sure you want to exit ?")

        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        return msg.exec_()

    @asyncSlot()
    async def btn_measure_once_clicked(self):
        self.btn_measure.setEnabled(False)
        await self.update_data()
        self.btn_measure.setEnabled(True)

    def btn_measure_clicked(self):
        if self.btn_measure.isChecked():
            self.btn_measure_once.setEnabled(False)
            interval = float(config_file['pCO2']['interval'])
            self.timerSave_pco2.start(interval * 1000)
        else:
            self.btn_measure_once.setEnabled(True)
            self.timerSave_pco2.stop()

    def clear_plot_btn_clicked(self):
        self.pco2_timeseries = pd.DataFrame(columns=self.pco2_timeseries.columns)

    def make_tab_plotwidget(self):
        date_axis = TimeAxisItem(orientation='bottom')
        date_axis2 = TimeAxisItem(orientation='bottom')
        date_axis3 = TimeAxisItem(orientation='bottom')

        self.plotwidget_pco2 = pg.PlotWidget(axisItems={'bottom': date_axis})
        self.plotwidget_var = pg.PlotWidget(axisItems={'bottom': date_axis2})
        self.plotwidget_var2 = pg.PlotWidget(axisItems={'bottom': date_axis3})

        self.plotwidget_pco2.setMouseEnabled(x=False, y=False)
        self.plotwidget_var.setMouseEnabled(x=False, y=False)
        self.plotwidget_var2.setMouseEnabled(x=False, y=False)


        self.plotwidget_line2 = self.plotwidget_var2.plot()
        self.plotwidget_line2_avg = self.plotwidget_var2.plot()

        self.plotwidget_line = self.plotwidget_var.plot()
        self.plotwidget_line_avg = self.plotwidget_var.plot()

        self.pco2_data_line = self.plotwidget_pco2.plot()
        self.pco2_data_averaged_line = self.plotwidget_pco2.plot()

        self.plotwidget_pco2.setBackground("#19232D")
        self.plotwidget_pco2.showGrid(x=True, y=True)
        self.plotwidget_pco2.setTitle("pCO2 value time series")

        self.plotwidget_var.setBackground("#19232D")
        self.plotwidget_var.showGrid(x=True, y=True)
        self.plotwidget_var2.setBackground("#19232D")
        self.plotwidget_var2.showGrid(x=True, y=True)

        self.pen = pg.mkPen(width=0.3, style=QtCore.Qt.DashLine)
        self.pen_avg = pg.mkPen(width=0.7)
        self.symbolSize = 5

    def make_tab_pco2_calibration(self):
        l = QGridLayout()
        self.btns = [QPushButton('Point 1'), QPushButton('Point 2'),
                     QPushButton('Point 3'), QPushButton('Point 4')]

        [l.addWidget(v, k, 0) for k, v in enumerate(self.btns)]

        self.tab_pco2_calibration.setLayout(l)

    def get_value_pco2_from_voltage(self, type):
        channel = config_file['pCO2'][type]["Channel"]
        coef = config_file['pCO2'][type]["Calibr"]
        if self.args.localdev:
            x = np.random.randint(0, 100)
        else:
            v = self.pco2_instrument.get_Voltage(2, channel)
            x = coef[0] * v + coef[1]
            x = round(x, 3)
        return x

    @asyncSlot()
    async def timer_finished(self):
        
        if self.btn_measure.isChecked():
            if not self.measuring:
                await self.update_data()
            else:
                print('Skipping',datetime.now()
                )
        else:
            self.timerSave_pco2.stop()

    async def update_data(self):
        self.measuring = True
        start = datetime.now()
        # UPDATE VALUES
        self.wat_temp = self.get_value_pco2_from_voltage(type="Tw")
        self.air_temp_mem = self.get_value_pco2_from_voltage(type="Ta_mem")
        self.wat_flow = self.get_value_pco2_from_voltage(type="Qw")
        self.wat_pres = self.get_value_pco2_from_voltage(type="Pw")
        self.air_pres = self.get_value_pco2_from_voltage(type="Pa_env")
        self.air_temp_env = self.get_value_pco2_from_voltage(type="Ta_env")

        values = [self.wat_temp, self.air_temp_mem, self.wat_flow, self.wat_pres,
                  self.air_pres, self.air_temp_env]
        await self.tab_pco2.update_tab_ai_values(values)


        #F = False
        #if measure_co2:
        if not self.no_serial.isChecked():
            synced_serial = await self.get_pco2_values()
            if synced_serial:
                await self.tab_pco2.update_tab_serial_values(self.serial_data)
                await asyncio.sleep(0.0001)
                self.pco2_df = await self.update_pco2_plot()
                await self.pco2_instrument.save_pCO2_data(self.serial_data, values)
                #await self.send_pco2_to_ferrybox()

            else:
                self.StatusBox.setText('Could not measure using serial connection')
        else:

            self.serial_data = pd.DataFrame(data={'time':['nan'], 'timestamp': ['nan'],
                                                'ppm': ['nan'], 'type': ['nan'],
                                                'range': ['nan'], 'sn': ['nan'],
                                                'VP':['nan'], 'VT': ['nan'],
                                                'mode':['nan']})

            self.serial_data['time'] = datetime.now()
            d = datetime.now().timestamp()
            self.serial_data['timestamp'] = [d]


            await self.pco2_instrument.save_pCO2_data(self.serial_data, values)

        self.measuring = False
        #print ('measurement took', datetime.now() - start)


    async def sync_pco2(self):
        self.pco2_instrument.connection.flushInput()
        for n in range(100):
            if (not self.btn_measure.isChecked() and not self.btn_measure_once.isChecked()):
                return
            b = self.pco2_instrument.connection.read(1)
            if len(b) and (b[0] == b'\x07'[0]):
                return True
            if n == 99:
                return False
        

    async def get_pco2_values(self):

        self.serial_data = pd.DataFrame(columns=['time', 'timestamp', 'ppm', 'type',
                                          'range', 'sn', 'VP', 'VT', 'mode'])

        self.serial_data['time'] = datetime.now()
        d = datetime.now().timestamp()
        self.serial_data['timestamp'] = [d]

        synced = await self.sync_pco2()  # False

        if synced:
            if self.args.localdev:
               self.serial_data['CH1_Vout'] = 999
               import random
               self.serial_data['ppm'] = random.randint(400,500)
               self.serial_data['type'] = 999
               self.serial_data['range'] = 999
               self.serial_data['sn'] = 999
               self.serial_data['VP'] = 999
               self.serial_data['VT'] = 999
               self.serial_data['mode'] = 999
            else:
                try:
                    #self.StatusBox.setText('Trying to read data')
                    self.buff = self.pco2_instrument.connection.read(37)

                    self.serial_data['CH1_Vout'] = struct.unpack('<f', self.buff[0:4])[0]

                    self.serial_data['ppm'] = struct.unpack('<f', self.buff[4:8])[0]
                    self.serial_data['ppm'] = self.serial_data['ppm']*float(self.Co2_CalCoef[0]) + float(self.Co2_CalCoef[1])

                    self.serial_data['type'] = self.buff[8:9]
                    self.serial_data['range'] = struct.unpack('<f', self.buff[9:13])[0]
                    self.serial_data['sn'] = self.buff[13:27]
                    self.serial_data['VP'] = struct.unpack('<f', self.buff[27:31])[0]
                    self.serial_data['VT'] = struct.unpack('<f', self.buff[31:35])[0]
                    self.serial_data['mode'] = self.buff[35:36]
                    if self.buff[8:9][0] != b'\x81'[0]:
                        print('the gas type is not correct')
                        synced = False
                    # if self.serial_data['mode'][0] != b'\x80'[0]:
                    #    raise ValueError('the detector mode is not correct')
                except:
                    raise
            self.serial_data = self.serial_data.round({'CH1_Vout': 3, 'ppm': 3, 'range':3, 'VP': 3, 'VT': 3})
        else:
            synced = False
            # raise ValueError('cannot sync to CO2 detector')
        if self.btn_measure_once.isChecked():
            self.btn_measure_once.setChecked(False)

        return synced

    async def send_pco2_to_ferrybox(self):
        row_to_string = self.pco2_df.to_csv(index=False, header=False).rstrip()
        # TODO: add pco2 string version
        v = self.pco2_instrument.ppco2_string_version
        udp.send_data("$PPCO2," + row_to_string + ",*\n", self.pco2_instrument.ship_code)

    async def update_pco2_plot(self):
        # UPDATE PLOT WIDGETS
        # only pco2 plot

        length = len(self.pco2_timeseries['times'])
        time_limit = config_file["pCO2"]["timeaxis_limit"]

        self.par1_to_plot = self.plotvar1_combo.currentText()
        self.par2_to_plot = self.plotvar2_combo.currentText()

        self.plotwidget_var.setTitle(self.par1_to_plot)
        self.plotwidget_var2.setTitle(self.par2_to_plot)
        await asyncio.sleep(0.001)

        if length == 300:
            self.pen = pg.mkPen(None)
            self.symbolSize = 2

        if length > time_limit:
            self.pco2_timeseries = self.pco2_timeseries.drop([0], axis=0).reset_index(drop=True)

        row = [self.serial_data['timestamp'].values[0], self.serial_data['ppm'].values[0], self.wat_temp,
               self.air_temp_mem, self.wat_pres, self.air_pres, self.wat_flow, self.air_temp_env,
               self.serial_data['VP'].values, self.serial_data['VT'].values, fbox["temperature"], fbox["salinity"]]

        # add one row with all values
        self.pco2_timeseries.loc[length] = row

        for n in [self.plotwidget_pco2, self.plotwidget_var, self.plotwidget_var2]:
            n.setXRange(self.pco2_timeseries['times'].values[0], self.pco2_timeseries['times'].values[-1])

        
        self.plotwidget_var2.setYRange(np.min(self.pco2_timeseries[self.par2_to_plot].values) - 0.001,
                                      np.max(self.pco2_timeseries[self.par2_to_plot].values) + 0.001)
        self.plotwidget_var.setYRange(np.min(self.pco2_timeseries[self.par1_to_plot].values) - 0.001,
                                      np.max(self.pco2_timeseries[self.par1_to_plot].values) + 0.001)
                                      
        self.pco2_data_line.setData(self.pco2_timeseries['times'].values,
                                    self.pco2_timeseries['CO2_values'].values,
                                    symbolBrush='w', alpha=0.3, size=1, symbol='o',
                                    symbolSize=1, pen=self.pen)


        self.plotwidget_line.setData(self.pco2_timeseries['times'],
                                     self.pco2_timeseries[self.par1_to_plot],
                                     symbolBrush='w', alpha=0.3, size=1, symbol='o',
                                     symbolSize=1, pen=self.pen)

        self.plotwidget_line2.setData(self.pco2_timeseries['times'],
                                     self.pco2_timeseries[self.par2_to_plot],
                                     symbolBrush='w', alpha=0.3, size=1, symbol='o',
                                     symbolSize=1, pen=self.pen)

        if self.par1_to_plot == self.par2_to_plot:
            
            subset = self.pco2_timeseries[['times', 'CO2_values', self.par1_to_plot]]
        else:
            subset = self.pco2_timeseries[['times', 'CO2_values', self.par1_to_plot,self.par2_to_plot]]
        subset.set_index('times', inplace=True)

        self.pco2_timeseries_averaged = subset.rolling(10).mean().dropna()
        #print (self.pco2_timeseries_averaged)
        self.pco2_data_averaged_line.setData(self.pco2_timeseries_averaged.index.values,
                                self.pco2_timeseries_averaged['CO2_values'].values,
                                symbolBrush='y', alpha=0.5, size=2, symbol='o',
                                symbolSize=self.symbolSize, pen=self.pen_avg)

        self.plotwidget_line_avg.setData(self.pco2_timeseries_averaged.index.values,
                                self.pco2_timeseries_averaged[self.par1_to_plot].values,
                                symbolBrush='y', alpha=0.5, size=2, symbol='o',
                                symbolSize=self.symbolSize, pen=self.pen_avg)

        self.plotwidget_line2_avg.setData(self.pco2_timeseries_averaged.index.values,
                                self.pco2_timeseries_averaged[self.par2_to_plot].values,
                                symbolBrush='y', alpha=0.5, size=2, symbol='o',
                                symbolSize=self.symbolSize, pen=self.pen_avg)

    def autorun(self):
        self.btn_measure.setChecked(True)

        if fbox['pumping'] or fbox['pumping'] is None:
            self.btn_measure_clicked()


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

        logging.root.level = logging.DEBUG
        for name, logger in logging.root.manager.loggerDict.items():
            if 'asyncqt' in name:
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
        main_widget = Panel_PCO2_only(self, self.args)
        return main_widget

    def closeEvent(self, event):
        result = self.main_widget.valve_message("Confirm Exit")
        #"result = QMessageBox.question(
        #"    self, "Confirm Exit...", "Are you sure you want to exit ?", QMessageBox.Yes | QMessageBox.No,
        #)""
        event.ignore()

        if result == QMessageBox.Yes:
            logging.info('The program was closed by user')

            udp.UDP_EXIT = True
            udp.server.join()
            if not udp.server.is_alive():
                logging.info("UDP server closed")

            self.main_widget.timerSave_pco2.stop()
            self.main_widget.btn_measure.setChecked(False)
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

