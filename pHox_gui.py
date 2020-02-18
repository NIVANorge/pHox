#! /usr/bin/python

from pHox import *
from pco2 import CO2_instrument
import os,sys
#os.chdir('/home/pi/pHox')
#os.system('clear')    
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
            await asyncio.sleep(.1)
        return self.result


class Panel(QtGui.QWidget):
    def __init__(self, parent, panelargs, config_name):
        super(QtGui.QWidget, self).__init__(parent)

        self.continous_mode_is_on = False
        self.update_spectra_in_progress = False
        self.args = panelargs
        self.config_name = config_name
        self.adjusting = False 
        self.create_timers()
        self.fformat = "%Y%m%d_%H%M%S"
        if self.args.co3:
            self.instrument = CO3_instrument(self.args,self.config_name)
        elif self.args.debug:
            self.instrument = Test_instrument(self.args,self.config_name)            
        else:
            self.instrument = pH_instrument(self.args,self.config_name)

        self.wvls = self.instrument.calc_wavelengths()
        self.instrument.get_wvlPixels(self.wvls)

        if self.args.pco2:
            self.CO2_instrument = CO2_instrument(self.config_name)
        self.measuring = False
        self.init_ui()

    def init_ui(self):

        self.tabs = QtGui.QTabWidget()

        self.tab1       =  QtGui.QWidget()
        self.tab_manual =  QtGui.QWidget()
        self.tab_log    =  QtGui.QWidget()
        self.tab_config =  QtGui.QWidget()
        self.plots      =  QtGui.QWidget()

        # Add tabs
        self.tabs.addTab(self.tab1,       "Home")  
        self.tabs.addTab(self.tab_log,    "Log") 
        self.tabs.addTab(self.tab_manual, "Manual")
        self.tabs.addTab(self.tab_config, "Config") 
                
        self.make_tab_log()    
        self.make_tab1()
        self.make_tab_manual()
        self.make_tab_config()   
        self.make_plotwidgets()

        # combine layout for plots and buttons
        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addWidget(self.plotwdigets_groupbox)    
        hboxPanel.addWidget(self.tabs)
    
        self.setLayout(hboxPanel)
        #self.showMaximized()

    def make_tab_manual(self):
        
        self.tab_manual.layout  = QtGui.QGridLayout()
        self.make_btngroupbox()
        self.make_slidergroupbox()
        self.tab_manual.layout.addWidget(self.sliders_groupBox)
        self.tab_manual.layout.addWidget(self.buttons_groupBox)
        self.tab_manual.setLayout(self.tab_manual.layout)

    def make_tab_log(self):
        self.tab_log.layout =     QtGui.QGridLayout()
        self.logTextBox = QtGui.QPlainTextEdit()
        self.logTextBox.setReadOnly(True)
        if self.args.debug:
            self.logTextBox.appendPlainText('Starting in debug mode')
        self.tab_log.layout.addWidget(self.logTextBox)
        self.tab_log.setLayout(self.tab_log.layout)

    def create_timers(self):

        self.timer_contin_mode = QtCore.QTimer()
        self.timer_contin_mode.timeout.connect(
            self.continuous_mode_timer_finished)  

        self.timerSpectra_plot = QtCore.QTimer()
        self.timerSpectra_plot.timeout.connect(self.update_spectra_plot)   

        self.timerTemp_info = QtCore.QTimer()
        self.timerTemp_info.timeout.connect(self.update_T_lab)    

        self.timerAuto = QtCore.QTimer()

        if self.args.pco2:
            self.timerSave = QtCore.QTimer()            
            self.timerSave.timeout.connect(self.save_pCO2_data)

    def make_plotwidgets(self):
        #create plotwidgets
        self.plotwdigets_groupbox = QtGui.QGroupBox()

        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget2 = pg.PlotWidget()
                

        self.plotwidget1.setYRange(1000,self.instrument.THR*1.05)

        if self.args.co3: 
            #self.plotwidget1.setYRange(1000,67000)
            self.plotwidget2.setYRange(0,1)
            self.plotwidget1.setXRange(220,260)   
            self.plotwidget2.setXRange(220,260)   

        self.plotwidget1.setBackground('#19232D')
        self.plotwidget1.showGrid(x=True, y=True)
        self.plotwidget1.setTitle("LEDs intensities")


        #self.plotwidget2.setYRange(0,1.3)
 
        #self.plotwidget2.setXRange(410,610)
        self.plotwidget2.showGrid(x=True, y=True)
        self.plotwidget2.setBackground('#19232D')     
        self.plotwidget2.setTitle("Last pH measurement")

        vboxPlot = QtGui.QVBoxLayout()
        vboxPlot.addWidget(self.plotwidget1)
        vboxPlot.addWidget(self.plotwidget2)
        if self.args.co3:
            self.plotwidget2.addLine(x=self.instrument.wvl1, y=None, pen=pg.mkPen('b', width=1, style=QtCore.Qt.DotLine))  
            self.plotwidget2.addLine(x=self.instrument.wvl2, y=None, pen=pg.mkPen('#eb8934', width=1, style=QtCore.Qt.DotLine))                            
            #self.plotwidget1.addLine(x=None, y=self.instrument.THR, pen=pg.mkPen('w', width=1, style=QtCore.Qt.DotLine))
            self.plotwidget1.addLine(x=self.instrument.wvl1, y=None, pen=pg.mkPen('b', width=1, style=QtCore.Qt.DotLine))        
            self.plotwidget1.addLine(x=self.instrument.wvl2, y=None, pen=pg.mkPen('#eb8934', width=1, style=QtCore.Qt.DotLine))    
        else:
            
            self.plotwidget1.addLine(x=None, y=self.instrument.THR, pen=pg.mkPen('w', width=1, style=QtCore.Qt.DotLine))
            self.plotwidget1.addLine(x=self.instrument.HI, y=None, pen=pg.mkPen('b', width=1, style=QtCore.Qt.DotLine))        
            self.plotwidget1.addLine(x=self.instrument.I2, y=None, pen=pg.mkPen('#eb8934', width=1, style=QtCore.Qt.DotLine))   
            self.plotwidget1.addLine(x=self.instrument.NIR, y=None, pen=pg.mkPen('r', width=1, style=QtCore.Qt.DotLine))

        self.plotSpc = self.plotwidget1.plot()
        self.plotAbs = self.plotwidget2.plot()

        if self.args == 'co3': 
            color = ['r','g','b','m','y']
            self.abs_lines = []
            for n_inj in range(self.instrument.ncycles):
                self.abs_lines.append(self.plotwidget2.plot(x = self.wvls,y = np.zeros(len(self.wvls)), pen=pg.mkPen(color[n_inj])))

        self.plotwdigets_groupbox.setLayout(vboxPlot)

    def make_steps_groupBox(self):

        self.sample_steps_groupBox = QtWidgets.QGroupBox("Measuring Progress")

        self.sample_steps = [  
                        QtWidgets.QCheckBox('0. Start new measurement'),
                        QtWidgets.QCheckBox('1. Adjusting LEDS'),
                        QtWidgets.QCheckBox('2  Measuring dark and blank'),
                        QtWidgets.QCheckBox('3. Measurement 1'), 
                        QtWidgets.QCheckBox('4. Measurement 2'),                        
                        QtWidgets.QCheckBox('5. Measurement 3'),
                        QtWidgets.QCheckBox("6. Measurement 4"),
                        QtWidgets.QCheckBox("7. Save the Data")]

        layout = QtGui.QGridLayout() 

        [step.setEnabled (False) for step in self.sample_steps]      
        [layout.addWidget(step) for step in self.sample_steps]
        self.sample_steps_groupBox.setLayout(layout)

    def make_tab1(self):

        self.make_steps_groupBox() 

        self.tab1.layout = QtGui.QGridLayout()
        self.textBox = QtGui.QTextEdit()
        self.textBox.setOverwriteMode(True)

        self.StatusBox = QtGui.QLineEdit()

        self.table_pH = QtGui.QTableWidget(6,2)
        self.table_pH.verticalHeader().hide()
        self.table_pH.horizontalHeader().hide()    
        self.table_pH.horizontalHeader().setResizeMode(QtWidgets.QHeaderView.Stretch)
        self.fill_table_pH(0,0,'pH lab')
        self.fill_table_pH(1,0,'T lab')
        self.fill_table_pH(2,0,'pH insitu')
        self.fill_table_pH(3,0,'T insitu')
        self.fill_table_pH(4,0,'S insitu')
        self.fill_table_pH(5,0,'Voltage')           
   

        self.textBox_LastpH = QtGui.QTextEdit()
        self.textBox_LastpH.setOverwriteMode(True)
        #self.textBox.setText('Last .')

        if self.args.debug:
            self.logTextBox.appendPlainText('Starting in debug mode')
        #self.tab_log.layout.addWidget(self.logTextBox) 

        self.btn_cont_meas = self.create_button('Continuous measurements',True)
        self.btn_single_meas = self.create_button('Single measurement', True)   
        self.btn_single_meas.clicked.connect(self.btn_single_meas_clicked)    
        if not self.args.co3:    
            self.btn_cont_meas.clicked.connect(self.btn_cont_meas_clicked)

        self.ferrypump_box = QtWidgets.QCheckBox('Ferrybox pump is on')
        self.ferrypump_box.setEnabled(False)
        self.ferrypump_box.setChecked(True)

        self.tab1.layout.addWidget(self.btn_cont_meas,   0, 0, 1, 1)
        self.tab1.layout.addWidget(self.btn_single_meas, 0, 1)

        self.tab1.layout.addWidget(self.StatusBox,  1, 0, 1, 1)    
        self.tab1.layout.addWidget(self.ferrypump_box,  1, 1, 1, 1)
        self.tab1.layout.addWidget(self.sample_steps_groupBox,2,0,1,1) 
        self.tab1.layout.addWidget(self.table_pH,2,1,1,1)

        self.tab1.setLayout(self.tab1.layout)

    def append_logbox(self,message):
        t = datetime.now().strftime('%b-%d %H:%M:%S')
        self.logTextBox.appendPlainText(t + '  ' + message)

    def fill_table_pH(self,x,y,item):
        self.table_pH.setItem(x,y,QtGui.QTableWidgetItem(item))

    def make_tab_config(self):
        self.tab_config.layout =  QtGui.QGridLayout()
        # Define widgets for config tab 
        self.btn_save_config= self.create_button('Save config',False)     
        self.btn_save_config.clicked.connect(self.btn_save_config_clicked) 

        self.dye_combo = QtGui.QComboBox()
        self.dye_combo.addItem('TB')
        self.dye_combo.addItem('MCP')       
         
        index = self.dye_combo.findText(self.instrument.dye, 
                                QtCore.Qt.MatchFixedString)
        if index >= 0: 
            self.dye_combo.setCurrentIndex(index)
            
        self.dye_combo.currentIndexChanged.connect(self.dye_combo_chngd)
        
        self.tableWidget = QtGui.QTableWidget()

        self.tableWidget.verticalHeader().hide()
        self.tableWidget.horizontalHeader().hide()    

        self.tableWidget.setRowCount(8)
        self.tableWidget.setColumnCount(2)
        self.tableWidget.horizontalHeader().setResizeMode(QtWidgets.QHeaderView.Stretch)
        #self.tableWidget.horizontalHeader().setStretchLastSection(True)

        self.fill_table_config(0,0,'DYE type')
        self.tableWidget.setCellWidget(0,1,self.dye_combo)
        if not self.args.co3: 
            self.fill_table_config(1,0,'NIR:')
            self.fill_table_config(1,1,str(self.instrument.NIR))

            self.fill_table_config(2,0,'HI-')
            self.fill_table_config(2,1,str(self.instrument.HI))

            self.fill_table_config(3,0,'I2-')
            self.fill_table_config(3,1, str(self.instrument.I2))

        self.fill_table_config(4,0,'Temp Sensor is calibrated:')
        self.fill_table_config(4,1,str(self.instrument.temp_iscalibrated))        

        self.fill_table_config(5,0,'pH sampling interval (min)')

        self.fill_table_config(6,0,'Spectroph intergration time')

        self.fill_table_config(7,0,'Ship')     
        self.fill_table_config(7,1,self.instrument.ship_code)



        self.specIntTime_combo = QtGui.QComboBox()
        [self.specIntTime_combo.addItem(str(n)) for n in range(100,5000,100)]
        self.update_spec_int_time_table()

            
        self.specIntTime_combo.currentIndexChanged.connect(self.specIntTime_combo_chngd)
        self.tableWidget.setCellWidget(6,1,self.specIntTime_combo)

        self.samplingInt_combo = QtGui.QComboBox()
        self.samplingInt_combo.addItem('5')
        self.samplingInt_combo.addItem('10')       
        self.tableWidget.setCellWidget(5,1,self.samplingInt_combo)

        index = self.samplingInt_combo.findText(str(self.instrument.samplingInterval), 
                                QtCore.Qt.MatchFixedString)
        if index >= 0: 
            self.samplingInt_combo.setCurrentIndex(index)

        self.samplingInt_combo.currentIndexChanged.connect(self.sampling_int_chngd)
            
        self.tab_config.layout.addWidget(self.btn_save_config,0,0,1,1)   
        self.tab_config.layout.addWidget(self.tableWidget,1,0,2,2)

        self.tab_config.setLayout(self.tab_config.layout)  

    def update_spec_int_time_table(self):
        index = self.specIntTime_combo.findText(str(self.instrument.specIntTime), 
                                QtCore.Qt.MatchFixedString)

        if index >= 0: 
            self.specIntTime_combo.setCurrentIndex(index)

    def fill_table_config(self,x,y,item):
        self.tableWidget.setItem(x,y,QtGui.QTableWidgetItem(item))

    def sampling_int_chngd(self,ind):

        minutes = int(self.samplingInt_combo.currentText())
        self.instrument.samplingInterval = int(minutes)*60

    def specIntTime_combo_chngd(self,ind):
        new_int_time = int(self.specIntTime_combo.currentText())
        self.instrument.specIntTime = new_int_time
        self.instrument.spectrom.set_integration_time(new_int_time)
        self.timerSpectra_plot.setInterval(new_int_time*2)

    def make_btngroupbox(self):
        # Define widgets for main tab 
        # Create checkabple buttons
        self.buttons_groupBox = QtGui.QGroupBox("Buttons GroupBox")
        btn_grid = QtGui.QGridLayout()

        self.btn_adjust_leds = self.create_button('Adjust Leds',True) 
        #self.btn_t_dark = self.create_button('Take dark',False)
        self.btn_leds = self.create_button('LEDs',True)
        self.btn_valve = self.create_button('Inlet valve',True)   
        self.btn_stirr = self.create_button('Stirrer',True)
        self.btn_dye_pmp = self.create_button('Dye pump',True)        
        self.btn_wpump = self.create_button('Water pump',True)
        self.btn_calibr = self.create_button('Make calibration',True)
        self.btn_liveplot = self.create_button('Live plot',True)

        btn_grid.addWidget(self.btn_dye_pmp, 0, 0)
        btn_grid.addWidget(self.btn_calibr, 0, 1)

        btn_grid.addWidget(self.btn_adjust_leds,1,0)
        btn_grid.addWidget(self.btn_leds,    1, 1)

        btn_grid.addWidget(self.btn_valve, 2, 0)
        btn_grid.addWidget(self.btn_stirr, 2, 1)

        btn_grid.addWidget(self.btn_wpump, 4, 0)
        btn_grid.addWidget(self.btn_liveplot, 4,1) 
        # Define connections Button clicked - Result 
        if not self.args.co3:
            self.btn_leds.clicked.connect(self.btn_leds_checked)
        self.btn_valve.clicked.connect(self.btn_valve_clicked)
        self.btn_stirr.clicked.connect(self.btn_stirr_clicked)
        self.btn_wpump.clicked.connect(self.btn_wpump_clicked)
        self.btn_liveplot.clicked.connect(self.btn_liveplot_clicked)

        if self.args.co3 :
            self.btn_lightsource = self.create_button('light source',True)
            btn_grid.addWidget(self.btn_lightsource , 4, 1)
            self.btn_lightsource.clicked.connect(self.btn_lightsource_clicked)

        self.btn_adjust_leds.clicked.connect(self.on_autoAdjust_clicked)
        self.btn_calibr.clicked.connect(self.btn_calibr_clicked)
        #self.btn_t_dark.clicked.connect(self.on_dark_clicked)
        self.btn_dye_pmp.clicked.connect(self.btn_dye_pmp_clicked)

        self.buttons_groupBox.setLayout(btn_grid)

    def make_slidergroupbox(self):    
        self.sliders_groupBox = QtGui.QGroupBox("LED values")

        sldNames = ['Blue','Orange','Red']
        self.sliders = []
        self.sldLabels, self.spinboxes =  [], []
        self.plus_btns, self.minus_btns = [], []

        for ind in range(3):
            self.plus_btns.append(QtGui.QPushButton('+'))
            self.minus_btns.append(QtGui.QPushButton(' - '))
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

        grid.addWidget(QtGui.QLabel('Blue:'),0,0)
        grid.addWidget(QtGui.QLabel('Orange:'),1,0)   
        grid.addWidget(QtGui.QLabel('Red:'),2,0)       

        for n in range(3):
            grid.addWidget(self.sliders[n],n,1)
            grid.addWidget(self.spinboxes[n],n,2)
            grid.addWidget(self.minus_btns[n],n,3)
            grid.addWidget(self.plus_btns[n],n,4)

        self.sliders_groupBox.setLayout(grid)

    def create_button(self,name,check):
        Btn = QtGui.QPushButton(name)
        Btn.setObjectName(name)
        if check:
            Btn.setCheckable(True)
        return Btn

    def btn_stirr_clicked(self):
        if self.btn_stirr.isChecked():
            self.instrument.turn_on_relay(
                self.instrument.stirrer_slot)
        else: 
            self.instrument.turn_off_relay(
                self.instrument.stirrer_slot)
  
    def btn_wpump_clicked(self):
        if self.btn_wpump.isChecked():
            self.instrument.turn_on_relay(
                self.instrument.wpump_slot)
        else: 
            self.instrument.turn_off_relay(
                self.instrument.wpump_slot)

    def btn_liveplot_clicked(self):
        state = self.btn_liveplot.isChecked()
        if state:
            self.timerSpectra_plot.start(self.instrument.specIntTime+100)
        else: 
            self.timerSpectra_plot.stop()

    @asyncSlot
    async def btn_lightsource_clicked(self):

        if self.btn_lightsource.isChecked():  
            self.instrument.turn_on_relay(
                self.instrument.light_slot)
        else: 
            self.instrument.turn_off_relay(
                self.instrument.light_slot)        

    #TODO: async
    @asyncSlot()
    async def btn_dye_pmp_clicked(self):
        state = self.btn_dye_pmp.isChecked()
        if state:
            print ('in pump dye clicked')
            await self.instrument.pump_dye(3)
            self.btn_dye_pmp.setChecked(False)

    #TODO: async
    @asyncSlot()    
    async def btn_valve_clicked(self):
        await self.instrument.set_Valve(self.btn_valve.isChecked())

    def btn_save_config_clicked(self):

        with open(self.config_name,'r+') as json_file:
            j = json.load(json_file)

            j['pH']['Default_DYE'] = self.dye_combo.currentText()

            j['Operational']["Spectro_Integration_time"] = self.instrument.specIntTime

            minutes = int(self.samplingInt_combo.currentText())
            j['Operational']["SAMPLING_INTERVAL_SEC"] = minutes*60
            json_file.seek(0)  # rewind
            json.dump(j, json_file, indent=4)
            json_file.truncate()

    def load_config_file(self):
        with open(self.config_name) as json_file:
            j = json.load(json_file)
            default =   j['pH']
            return default
   
    def dye_combo_chngd(self,ind):

        self.dye = self.dye_combo.currentText()
        default = self.load_config_file()
        if self.dye == 'MCP':
            self.instrument.HI =  int(default['MCP_wl_HI'])
            self.instrument.I2 =  int(default['MCP_wl_I2'])         
        elif self.dye == "TB":   
            self.instrument.HI =  int(default['TB_wl_HI'])
            self.instrument.I2 =  int(default['TB_wl_I2'])

        self.tableWidget.setItem(2,1, 
          QtGui.QTableWidgetItem(str(
              self.instrument.HI)))  

        self.tableWidget.setItem(3,1, 
          QtGui.QTableWidgetItem(str(
              self.instrument.I2)))          

    def change_plus_minus_butn(self,ind,dif):
        value = self.spinboxes[ind].value() + dif
        if value < 0: 
            value = 0
        self.instrument.adjust_LED(ind,value)
        self.sliders[ind].setValue(value)
        self.spinboxes[ind].setValue(value)

    def led_plus_btn_clicked(self):
        dif = 10 
        ind = self.plus_btns.index(self.sender())
        self.change_plus_minus_butn(
            ind,dif)

    def led_minus_btn_clicked(self):  
        dif = -10 
        ind = self.minus_btns.index(self.sender())        
        self.change_plus_minus_butn(
            ind,dif)

    def spin_change(self,value):
        source = self.sender()
        ind = self.spinboxes.index(source)
        self.instrument.adjust_LED(ind,value)
        self.sliders[ind].setValue(value)
        self.btn_leds.setChecked(True)

    def sld_change(self,value):
        source = self.sender()
        ind = self.sliders.index(source)       
        self.instrument.adjust_LED(ind,value)
        self.spinboxes[ind].setValue(value)
        self.btn_leds.setChecked(True)        

    def set_LEDs(self, state):
        for i in range(0,3):
            self.instrument.adjust_LED(i, state*self.sliders[i].value())
        self.append_logbox('Leds {}'.format(str(state)))

    def btn_leds_checked(self):
        state = self.btn_leds.isChecked()
        self.set_LEDs(state)

    def on_selFolderBtn_released(self):
        self.folderDialog = QtGui.QFileDialog()
        folder = self.folderDialog.getExistingDirectory(self,'Select directory')
        self.instrument.folderPath = folder+'/'

    def save_stability_test(self,datay):
        stabfile = os.path.join('/home/pi/pHox/sp_stability.log')        
        if not self.args.co3:
            stabfile_df = pd.DataFrame({
            'datetime' : [datetime.now().strftime(self.fformat) ],
            "led0" : [datay[self.instrument.wvlPixels[0]]],
            "led1" : [datay[self.instrument.wvlPixels[1]]],
            "led2" : [datay[self.instrument.wvlPixels[2]]],
            "specint": [self.instrument.specIntTime]})
        elif self.args.co3: 
            stabfile_df = pd.DataFrame({
            "wvl1" : [datay[self.instrument.wvlPixels[0]]],
            "wvl2" : [datay[self.instrument.wvlPixels[1]]],
            "specint": [self.instrument.specIntTime]})    

        if os.path.exists(stabfile):
            stabfile_df.to_csv(stabfile, mode = 'a', index = False, header=False) 
        else: 
            if not self.args.co3:
                stabfile_df = pd.DataFrame(columns = ['datetime',"led0","led1","led2","specint"])
            else: 
                stabfile_df = pd.DataFrame(columns = ['datetime',"wvl1","wvl2","specint"])    
                           
            stabfile_df.to_csv(stabfile, index = False, header=True) 

    async def update_absorbance_plot(self, n_inj, spAbs):
        self.abs_lines[n_inj].setData(self.wvls, spAbs)
        await asyncio.sleep(0.005)
        return

    @asyncSlot()
    async def update_spectra_plot(self):
        self.update_spectra_in_progress = True
        if not self.adjusting and not self.measuring:
            if self.args.seabreeze or self.args.debug:
                try:
                    datay = await self.instrument.spectrom.get_intensities()
                    if self.args.stability:
                        self.save_stability_test(datay)
                except:
                    print('Exception error')
                    pass
            else:
                datay = self.instrument.spectrom.get_corrected_spectra()
        else:
            try:
                datay = self.instrument.spectrum
                await asyncio.sleep(self.instrument.specIntTime*1.e-3)
            except:
                pass
        try:
            self.plotSpc.setData(self.wvls, datay)
        except:
            print('could not set Data')
            pass
        self.update_spectra_in_progress = False

    def reset_absorp_plot(self):
        z = np.zeros(len(self.wvls))
        [self.update_absorbance_plot(n_inj,z) for n_inj 
            in range(self.instrument.ncycles)]

    def save_pCO2_data(self, pH = None):
        self.add_pco2_info()
        d = self.CO2_instrument.franatech 
        t = datetime.now() 
        label = t.isoformat('_')
        labelSample = label[0:19]
        logfile = os.path.join(self.instrument.folderPath, 'pCO2.log')
        hdr  = ''
        if not os.path.exists(logfile):
            hdr = 'Time,Lon,Lat,fbT,fbS,Tw,Flow,Pw,Ta,Pa,Leak,CO2,TCO2'
        s = labelSample
        s+= ',%.6f,%.6f,%.3f,%.3f' % (fbox['longitude'], fbox['latitude'], 
                fbox['temperature'], fbox['salinity'])
        s+= ',%.2f,%.1f,%.1f,%.2f,%d,%.1f,%d' %(d[0],d[1],d[2],d[3],d[4],d[6],d[7])
        s+= '\n'
        with open(logfile,'a') as logFile:
            if hdr:
                logFile.write(hdr + '\n')
            logFile.write(s)
        udp.send_data('PCO2,' + s)
        return

    async def autoAdjust_IntTime(self):
        # Function calls autoadjust without leds
        adj,pixelLevel = await self.instrument.auto_adjust()  
        if adj: 
            self.append_logbox('Finished Autoadjust LEDS')
            self.update_spec_int_time_table()
            self.plotwidget1.plot([self.instrument.wvl2],[pixelLevel], 
                                                pen=None, symbol='+') 
        return adj                                        

    async def autoAdjust_LED(self):
        self.instrument.LED1,self.instrument.LED2,self.instrument.LED3,result  = await self.instrument.auto_adjust()
        print ('values after autoadjust', self.instrument.LED1,self.instrument.LED2,self.instrument.LED3)
        if result:
            self.sliders[0].setValue(self.instrument.LED1)
            self.sliders[1].setValue(self.instrument.LED2)
            self.sliders[2].setValue(self.instrument.LED3)
            self.timerSpectra_plot.setInterval(self.instrument.specIntTime)
            
            #self.plot_sp_levels()
            self.update_spec_int_time_table()             
            self.append_logbox(
                'Adjusted LEDS with intergration time {}'.format(
                    self.instrument.specIntTime))


            datay = await self.instrument.spectrom.get_intensities() 
            await asyncio.sleep(0.1)
            self.plotSpc.setData(self.wvls,datay)
            if not self.args.seabreeze:    
                self.instrument.specAvScans = 3000/self.instrument.specIntTime
        else:
            result = False

        return result

    @asyncSlot()
    async def on_autoAdjust_clicked(self):
        self.btn_adjust_leds.setChecked(True)        
        self.adjusting = True
        if self.args.co3:
            res = await self.autoAdjust_IntTime()
        else:
            res = await self.autoAdjust_LED() 

        self.adjusting = False
        self.btn_adjust_leds.setChecked(False)
        return res

    async def call_autoAdjust(self):
        self.btn_adjust_leds.setChecked(True)        
        self.adjusting = True
        if self.args.co3:
            res = await self.autoAdjust_IntTime()
        else:
            res = await self.autoAdjust_LED() 

        self.adjusting = False
        self.btn_adjust_leds.setChecked(False)
        return res

    def add_pco2_info(self):
        self.CO2_instrument.portSens.write(
            self.CO2_instrument.QUERY_CO2)
        resp = self.CO2_instrument.portSens.read(15)
        try:
            value =  float(resp[3:])
            value = self.CO2_instrument.ftCalCoef[6][0]+self.CO2_instrument.ftCalCoef[6][1]*value
        except ValueError:
            value = 0
        self.CO2_instrument.franatech[6] = value

        self.CO2_instrument.portSens.write(self.CO2_instrument.QUERY_T)
        resp = self.CO2_instrument.portSens.read(15)
        try:
                self.CO2_instrument.franatech[7] = float(resp[3:])
        except ValueError:
                self.CO2_instrument.franatech[7] = 0

        for ch in range(5):
            V = self.instrument.get_Vd(2,ch+1)
            X = 0
            for i in range(2):
                X += self.CO2_instrument.ftCalCoef[ch][i] * pow(V,i)
            self.CO2_instrument.franatech[ch] = X

    def get_next_sample(self):
        t = datetime.now()
        #self.instrument.timeStamp  = t.isoformat('_')
        tsBegin = (t-datetime(1970,1,1)).total_seconds()
        nextSamplename = datetime.fromtimestamp(tsBegin + self.instrument.samplingInterval)
        return str(nextSamplename.strftime("%H:%M"))    

    def get_filename(self):
        t = datetime.now()
        timeStamp  = t.isoformat('_')
        flnmStr =  datetime.now().strftime(self.fformat) 
        return flnmStr, timeStamp

    def btn_cont_meas_clicked(self):

        self.mode = 'Continuous'
        state = self.btn_cont_meas.isChecked()
        if state:
            print ('btn_cont_meas_clicked')
            self.btn_single_meas.setEnabled(False) 
            self.btn_calibr.setEnabled(False) 
            # disable all btns in manual tab 
            nextSamplename = self.get_next_sample()
            self.StatusBox.setText("Next sample at {}".format(nextSamplename))
            self.timer_contin_mode.start(self.instrument.samplingInterval*1000)
        else:
            print ('btn_cont_meas_Unclicked')
            self.StatusBox.clear()            
            self.timer_contin_mode.stop()
            if not self.continous_mode_is_on:
                self.btn_single_meas.setEnabled(True) 
                self.btn_calibr.setEnabled(True)

    def change_widget_state(self,state):
        self.dye_combo.setEnabled(state)
        self.specIntTime_combo.setEnabled(state)
        # add mroe 


    @asyncSlot()
    async def btn_calibr_clicked(self):
        self.change_widget_state(False)
        state = self.btn_calibr.isChecked()
        if state:
            message = QtGui.QMessageBox.question(self,
                    "Crazy important message!!!",
                    "Switch the valve to calibration mode",
                    QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)
            if message == QtGui.QMessageBox.No:
                return

            self.btn_cont_meas.setEnabled(False)
            self.btn_single_meas.setEnabled(False) 
            # disable all btns in manual tab 

            self.mode = 'Calibration'
            folderPath = self.get_folderPath() 
            flnmStr, timeStamp = self.get_filename()    

            r = await self.sample(folderPath, flnmStr, timeStamp)
            self.single_sample_finished(folderPath,timeStamp,flnmStr)

    @asyncSlot()
    async def btn_single_meas_clicked(self):
        self.change_widget_state(False)
        # Disable live updating and block button
        if self.btn_liveplot.isChecked():
            self.btn_liveplot.click()
        self.btn_liveplot.setEnabled(False)
        self.measuring = True
        # Wait for last live update to finish
        while self.update_spectra_in_progress:
            await asyncio.sleep(.1)
        # Start single sampling process
        print ('clicked single meas ')
        message = QtGui.QMessageBox.question(self,
                    "important message!!!",
                    "Did you pump to clean?",
                    QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)
        if message == QtGui.QMessageBox.No:
            self.btn_single_meas.setChecked(False)  
            self.measuring = False         
            return

        flnmStr, timeStamp = self.get_filename()        
        text, ok = QtGui.QInputDialog.getText(None, 'Enter Sample name', 
                                        flnmStr)
        if ok:
            if text != '':
                flnmStr = text

            self.mode = 'Single'
            folderPath = self.get_folderPath() 
            # disable all btns in manual tab 
            self.btn_cont_meas.setEnabled(False)
            self.btn_single_meas.setEnabled(False) 
            self.btn_calibr.setEnabled(False) 


            await self.sample(folderPath, flnmStr, timeStamp)
            self.single_sample_finished(folderPath,timeStamp,flnmStr)

        else: 
            self.btn_single_meas.setChecked(False)
        # Re-enable live update button and start it
        self.btn_liveplot.setEnabled(True)
        self.btn_liveplot.click()

    @asyncSlot()
    async def continuous_mode_timer_finished(self):
        self.measuring = True
        print ('continuous_mode_timer_finished')
        self.append_logbox('continuous_mode_timer_finished')

        flnmStr, timeStamp = self.get_filename()          
        self.continous_mode_is_on = True
        folderPath = self.get_folderPath() 

        await self.sample(folderPath, flnmStr, timeStamp)
        self.continuous_sample_finished(folderPath,timeStamp,flnmStr) 

    def unclick_enable(self,btns):
        for btn in btns:
            btn.setChecked(False)    
            btn.setEnabled(True)            

    def get_final_pH(self,timeStamp):
        # get final pH
        p = self.instrument.pH_eval(self.evalPar_df)
        pH_lab, T_lab, perturbation, evalAnir, pH_insitu,self.x,self.y,self.slope, self.intercept = p

        self.pH_log_row = pd.DataFrame({
            "Time"         : [timeStamp[0:16]],
            "Lon"          : [fbox['longitude']], 
            "Lat"          : [fbox['latitude']] ,
            "fb_temp"      : [fbox['temperature']], 
            "fb_sal"       : [fbox['salinity']],         
            "SHIP"         : [self.instrument.ship_code],
            "pH_lab"       : [pH_lab], 
            "T_lab"        : [T_lab],
            "perturbation" : [perturbation],
            "evalAnir"     : [evalAnir],
            "pH_insitu"    : [pH_insitu]})

        self.append_logbox('Single measurement is done...')
        #self.sample_steps[8].setChecked(True)
                 
    def save_results(self,folderPath,flnmStr):

        #self.sample_steps[7].setChecked(True)    
        self.append_logbox('Save spectrum data to file')
        self.save_spt(folderPath,flnmStr)
        self.append_logbox('Save evl data to file')
        self.save_evl(folderPath,flnmStr)   
        print ('Send data to ferrybox')
        self.append_logbox('Send data to ferrybox')        
        self.send_to_ferrybox()

        self.append_logbox('Save final data in %s' % (folderPath+'pH.log'))
        self.save_logfile_df(folderPath,flnmStr)
  
    def update_pH_plot(self):
        print ('in update pH plot')
        print ('self.x,self.y',self.x,self.y)
        self.plotwidget2.plot(self.x,self.y, pen=None, symbol='o', clear=True)  
        print ('after first plot')
        print ('intercept',self.intercept)
        self.plotwidget2.plot(self.x,self.intercept + self.slope*self.x)   

    def single_sample_finished(self,folderPath,timeStamp,flnmStr):
        self.change_widget_state(True)
        print ('single sample finished inside func')   
        self.measuring = False 
        if not self.args.co3 :
            print ('get final pH')
            self.get_final_pH(timeStamp)
            if not self.args.debug:
                self.save_results(folderPath,flnmStr)            
                print ('save results')
            print ('update pH plot')
            self.update_pH_plot()     
            print ('update infotable ')   
            self.update_infotable()

        self.StatusBox.setText('Measurement is finished')       

        self.unclick_enable([self.btn_single_meas,self.btn_calibr,self.btn_cont_meas])
        [step.setChecked(False) for step in self.sample_steps]

        if self.mode == 'Calibration':
            res = QtGui.QMessageBox.question(self,
                        "Crazy important message",
                        "Turn back the valve to Ferrybox mode",
                        QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)

            res = QtGui.QMessageBox.question(self,
                        "Crazy important message",
                        "Are you sure??????",
                        QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)

    def continuous_sample_finished(self,folderPath,timeStamp,flnmStr):
        self.change_widget_state(True)
        print ('inside continuous_sample_finished')
        self.continous_mode_is_on = False
        self.measuring = False 
        if not self.args == 'co3':
            self.get_final_pH(timeStamp)
            self.StatusBox.setText('Measurement is finished') 
            if not self.args.debug:
                self.save_results(folderPath,flnmStr)
            self.update_pH_plot()
            self.update_infotable()   

        [step.setChecked(False) for step in self.sample_steps]

        print ('start timer spectra plot')
        
        if not self.btn_cont_meas.isChecked():
            self.StatusBox.setText('Continuous mode is off')
            self.btn_single_meas.setEnabled(True) 
            self.btn_calibr.setEnabled(True)
            # enable all btns in manual tab 
        else:
            nextSamplename = self.get_next_sample()
            self.StatusBox.setText("Next sample at {}".format(nextSamplename))

    def update_T_lab(self):
        Voltage = self.instrument.get_Vd(3, self.instrument.vNTCch)
        Voltage = round(Voltage, prec['vNTC'])
        T_lab= round((
            self.instrument.TempCalCoef[0]*Voltage) + self.instrument.TempCalCoef[1],
             prec['Tdeg'])
        self.fill_table_pH(1,1, str(T_lab))
        self.fill_table_pH(5,1,str(Voltage)) 
        
    def update_infotable(self):
        print ('inside update infotable')
        if not self.args.co3:
            pH_lab = str(self.pH_log_row["pH_lab"].values[0])
            self.fill_table_pH(0,1,pH_lab)

            T_lab = str(self.pH_log_row["T_lab"].values[0])
            self.fill_table_pH(1,1, T_lab)

            pH_insitu = str(self.pH_log_row["pH_insitu"].values[0])
            self.fill_table_pH(2,1,pH_insitu)

            T_insitu = str(self.pH_log_row["fb_temp"].values[0])
            self.fill_table_pH(3,1,T_insitu)

            S_insitu = str(self.pH_log_row["fb_sal"].values[0])
            self.fill_table_pH(4,1,S_insitu)      

            Voltage = self.instrument.get_Vd(3, self.instrument.vNTCch)

            self.fill_table_pH(5,1,str(Voltage))                  
        else: 
            print ('to be filled with data')

    def update_LEDs(self):
        self.sliders[0].setValue(self.instrument.LED1)
        self.sliders[1].setValue(self.instrument.LED2)
        self.sliders[2].setValue(self.instrument.LED3)

    def _autostart(self):
        self.append_logbox('Inside _autostart...')
        self.textBox.setText('Turn on LEDs')
        if self.args.co3:
            print ('turn on light source')
            self.instrument.turn_on_relay(self.instrument.light_slot)  
            self.btn_lightsource.setChecked(True)     

        elif not self.args.co3:
            self.update_LEDs()
            self.btn_leds.setChecked(True)
            self.btn_leds_checked()

        self.btn_liveplot.click()
        #self.timerSpectra_plot.start(600)
        #self.timerTemp_info.start(600)

        if not self.args.co3 or not self.args.debug: 
            print ('Starting continuous mode ')
            self.textBox.setText('Starting continuous mode ')
            self.btn_cont_meas.setChecked(True)
            self.btn_cont_meas_clicked()

        if not self.args.debug:
            self.textBox.setText('The instrument is ready')

        if self.args.pco2:
            # change to config file 
            self.timerSave.start(self.CO2_instrument.save_pco2_interv * 1.e3) #milliseconds
        return

    def _autostop(self):
        self.append_logbox('Inside _autostop...')
        time.sleep(10)

        self.btn_leds.setChecked(False)
        self.btn_cont_meas.setChecked(False)
        self.btn_cont_meas_clicked()
        #self.on_deploy_clicked(False)
        self.timerSpectra_plot.stop()
        self.timer_contin_mode.stop()
        #self.timerSensUpd.stop()
        #self.timerSave.stop()
        return

    def autostop_time(self):
        self.append_logbox('Inside autostop_time...')
        self.timerAuto.stop()
        self._autostop()
        now  = datetime.now()
        dt   = now - self.instrument._autotime
        days = int(dt.total_seconds()/86400) + 1
        self.instrument._autotime += timedelta(days=days)
        self.timerAuto.timeout.disconnect(self.autostop_time)
        self.timerAuto.timeout.connect(self.autostart_time)
        self.timerAuto.start(1000)
        return
        
    def autostart_time(self):
        self.append_logbox('Inside _autostart_time...')
        self.timerAuto.stop()
        now  = datetime.now()
        if now < self.instrument._autotime:
            self.timerAuto.timeout.connect(self.autostart_time)
            dt = self.instrument._autotime - now
            self.timerAuto.start(int(dt.total_seconds()*1000))
            self.logTextBox.appendPlainText('Instrument will start at ' + self.instrument._autostart.strftime('%Y-%m-%dT%H:%M:%S'))
        else:
            self.timerAuto.timeout.disconnect(self.autostart_time)
            self.timerAuto.timeout.connect(self.autostop_time)
            t0 = self.instrument._autotime + self.instrument._autolen
            dt = t0 - now
            self.timerAuto.start(int(dt.total_seconds()*1000))
            self.logTextBox.appendPlainText('Instrument will stop at ' + t0.strftime('%Y-%m:%dT%H:%M:%S')) 
            self._autostart()
        return
    
    def autostart_pump(self):
        self.append_logbox('Automatic start at pump enabled')

        if fbox['pumping']:
            self.timerAuto.stop()
            self.timerAuto.timeout.disconnect(self.autostart_pump)
            self.timerAuto.timeout.connect(self.autostop_pump)
            self.timerAuto.start(10000)
            self._autostart()
        else:
            pass
        return
        
    def autostop_pump(self):
        if not fbox['pumping']:
            self.timerAuto.stop()
            self.timerAuto.timeout.disconnect(self.autostop_pump)
            self.timerAuto.timeout.connect(self.autostart_pump)
            self.timerAuto.start(10000)
            self._autostop()
        else:
            pass
        return
        
    def autorun(self):
        self.append_logbox('Inside continuous_mode...')
        print ('start autorun')
        if (self.instrument._autostart) and (self.instrument._automode == 'time'):
            self.textBox.setText('Automatic scheduled start enabled')
            self.timerAuto.timeout.connect(self.autostart_time)
            self.timerAuto.start(1000)

        elif (self.instrument._autostart) and (self.instrument._automode == 'pump'):
            self.textBox.setText('Automatic start at pump enabled')
            self.timerAuto.timeout.connect(self.autostart_pump)
            self.timerAuto.start(1000)
            
        elif (self.instrument._autostart) and (self.instrument._automode == 'now'):
            self.textBox.setText('Immediate automatic start enabled')
            self._autostart()
        return

    async def sample(self,folderPath,flnmStr, timeStamp):

        # Step 0. Start mesurement, create new df,
        # reset Absorption plot
        # pump if single, close the valve 
        if self.mode == 'Continuous' or self.mode == 'Calibration': 
            if not fbox['pumping']:
                return               
        self.sampling = True
        print ('sample, mode is {}'.format(self.mode))
        self.StatusBox.setText('Ongoing measurement')
        self.sample_steps[0].setChecked(True)

        self.create_new_df()  
        

        if self.args == 'co3':
            self.reset_absorp_plot()

        await self.pump_if_needed()

        self.append_logbox('Closing valve ...')
        await self.instrument.set_Valve(True)

        # Step 1. Autoadjust LEDS
        self.sample_steps[1].setChecked(True)        
        self.append_logbox('Autoadjust LEDS')
        res = await self.call_autoAdjust()
        print ('res after autoadjust', res )
        if not res: 
            print ('could not adjust leds')
            return 

        # Step 2. Take dark and blank 
        self.sample_steps[2].setChecked(True)    
        await asyncio.sleep(0.05)       
        dark = await self.measure_dark()
        blank_min_dark = await self.measure_blank(dark) 

        # Steps 3,4,5,6 Measurement cycle 
        await self.measurement_cycle(blank_min_dark,dark)

        # Step 7 Open valve 
        self.sample_steps[7].setChecked(True)  
        await asyncio.sleep(0.05) 
        print ('Opening the valve ...')
        self.append_logbox('Opening the valve ...')
        await self.instrument.set_Valve(False)

        return 'Finished'

    def continue_after_dark(self, dark):
        pass
    def continue_after_blank(self, blank):
        pass

    def get_folderPath(self):

        if self.args == 'co3': 
            if self.mode == 'Calibration': 
                folderPath = '/home/pi/pHox/data_co3_calibr/'
            else:
                folderPath = '/home/pi/pHox/data_co3/'
        else:
            if self.mode == 'Calibration': 
                folderPath = '/home/pi/pHox/data_calibr/'  
            else:
                folderPath ='/home/pi/pHox/data/' 

        if not os.path.exists(folderPath):
            os.makedirs(folderPath)

        return folderPath

    def create_new_df(self):

        self.spCounts_df = pd.DataFrame(columns=['Wavelengths','dark','blank'])
        self.spCounts_df['Wavelengths'] = ["%.2f" % w for w in self.wvls] 
        if self.args == 'co3':
            self.CO3_eval = pd.DataFrame(columns=["CO3", "e1", "e2e3",
                                        "log_beta1_e2", "vNTC", "S", 
                                        "A1", "A2", "R", "Tdeg", 
                                        "Vinj", " S_corr"])  
        else:
            self.evalPar_df = pd.DataFrame(columns=["pH", "pK", "e1",
                                                "e2", "e3", "vNTC",
                                        'salinity', "A1", "A2","Tdeg",  
                                       "S_corr", "Anir",'Vol_injected',
                                       "TempProbe_id","Probe_iscalibr",
                                        'TempCalCoef1','TempCalCoef2','DYE'])

    async def pump_if_needed(self):

        if self.instrument.deployment == 'Standalone' and self.mode == 'Continuous':
            self.append_logbox('pumping')            
            await self.instrument.pumping(self.instrument.pumpTime) 

        elif self.mode == 'Calibration':
            self.append_logbox('pumping')
            await self.instrument.pumping(self.instrument.pumpTime) 

        else: 
            self.append_logbox('pumping is not needed ')

    async def measure_dark(self):
        # turn off light and LED
        if self.args.co3:
            self.instrument.turn_off_relay(self.instrument.light_slot)
            print ('turn of the light source')
            await asyncio.sleep(1)
        else: 
            self.set_LEDs(False)

        # grab spectrum
        if not self.args.seabreeze:
            dark = await self.instrument.spectrom.get_intensities()
        elif self.args.seabreeze:
            #raw = str(n_inj)+'raw'
            #self.spCounts_df[raw] = await self.instrument.spectrom.get_intensities(
            #        self.instrument.specAvScans,correct=False)
            # time.sleep(0.5)
            dark = await self.instrument.spectrom.get_intensities(
                    self.instrument.specAvScans,correct=True)

        if self.args.co3:
            # Turn on the light source
            self.instrument.turn_on_relay(self.instrument.light_slot)
            print ('turn on the light source')
            await asyncio.sleep(2)
        else: 
            # Turn on LEDs after taking dark 
            self.set_LEDs(True)
        self.instrument.spectrum = dark
        self.spCounts_df['dark'] = dark
        await self.update_spectra_plot_manual(dark)
        return dark 

    async def update_spectra_plot_manual(self,spectrum):
        self.plotSpc.setData(self.wvls,spectrum)
        await asyncio.sleep(0.05)

    async def measure_blank(self,dark):    
        print ('Measuring blank...')
        self.append_logbox('Measuring blank...')

        if not self.args.seabreeze:
            self.nlCoeff = [1.0229, -9E-6, 6E-10] # we don't know what it is  
            blank = await self.instrument.spectrom.get_intensities()
            
            blank_min_dark= np.clip(blank,1,16000)
        else: 
            blank = await self.instrument.spectrom.get_intensities(
                    self.instrument.specAvScans,correct=True)    
            print ('blank',blank)
            blank_min_dark =   blank - dark  

        self.instrument.spectrum = blank  
        self.spCounts_df['blank'] = blank
        self.plotSpc.setData(self.wvls,blank)  
        return blank_min_dark

    async def measurement_cycle(self,blank_min_dark,dark):
        for n_inj in range(self.instrument.ncycles):
            print ('n_inj',n_inj)            
            self.sample_steps[n_inj+3].setChecked(True)
            await asyncio.sleep(0.05)     
            vol_injected = round(
                self.instrument.dye_vol_inj*(n_inj+1)*self.instrument.nshots,
                 prec['vol_injected'])
            dilution = (self.instrument.Cuvette_V) / (
                    vol_injected  + self.instrument.Cuvette_V)      

            vNTC = await self.inject_dye(n_inj)
            spAbs_min_blank = await self.calc_spectrum(n_inj,blank_min_dark,dark)
            #self.append_logbox('Calculate init pH') 
            print ('Calculate init pH') 

            if self.args == 'co3':
                self.CO3_eval.loc[n_inj] = self.instrument.calc_CO3(
                                spAbs_min_blank,vNTC,dilution,vol_injected) 
                await self.update_absorbance_plot(n_inj, spAbs_min_blank)
            else:                                  
                self.evalPar_df.loc[n_inj] = self.instrument.calc_pH(
                                spAbs_min_blank,vNTC,dilution,vol_injected)
        return 

    async def inject_dye(self,n_inj): 
        # create dataframe and store 

        self.append_logbox('Start stirrer')               
        self.instrument.turn_on_relay(self.instrument.stirrer_slot)
        self.append_logbox('Dye Injection %d:' %(n_inj+1)) 

        if not self.args.debug:       
            #self.instrument.cycle_line(self.instrument.dyepump_slot, shots)
            await self.instrument.pump_dye(self.instrument.nshots)

        self.append_logbox("Mixing")
        await asyncio.sleep(self.instrument.mixT)

        self.append_logbox('Stop stirrer')    
        self.instrument.turn_off_relay(self.instrument.stirrer_slot)

        self.append_logbox('Wait')            
        await asyncio.sleep(self.instrument.waitT)

        # measuring Voltage for temperature probe
        vNTC = self.instrument.get_Vd(3, self.instrument.vNTCch)
        return vNTC 

    async def calc_spectrum(self,n_inj,blank_min_dark,dark):    
        self.append_logbox('Get spectrum')
        # measure spectrum after injecting nshots of dye 
        #Write spectrum to the file 
        if self.args.seabreeze:
            #raw = str(n_inj)+'raw'
            #self.spCounts_df[raw] = await self.instrument.spectrom.get_intensities(
            #        self.instrument.specAvScans,correct=False)
            # time.sleep(0.5)
            postinj_spec = await self.instrument.spectrom.get_intensities(
                    self.instrument.specAvScans,correct=True)
            self.instrument.spectrum = postinj_spec
            self.plotSpc.setData(self.wvls,postinj_spec)
            await asyncio.sleep(0.05)
            postinj_spec_min_dark = postinj_spec - dark
            # Absorbance 
            if not self.args.debug: 
                spAbs_min_blank = - np.log10 (postinj_spec_min_dark / blank_min_dark)
            else: 
                print ('WRONG VALUES')
                spAbs_min_blank = postinj_spec 
            #blank

        elif self.args.debug:
            print ('in debug')
            postinj_spec = await self.instrument.spectrom.get_intensities(
                    self.instrument.specAvScans,correct=True)
            postinj_spec_min_dark = postinj_spec # - dark
            spAbs_min_blank = postinj_spec_min_dark 
            self.plotSpc.setData(self.wvls,postinj_spec)
            await asyncio.sleep(0.05)            
            #blank
        else :
            postinj = await self.instrument.spectrom.get_intensities()
            # postinjection minus dark     
            postinj_min_dark = np.clip(postinj,1,16000)
            #print ('postinj_min_dark')
            cfb =  (self.nlCoeff[0] + 
                    self.nlCoeff[1] * blank_min_dark + 
                    self.nlCoeff[2] * blank_min_dark**2)

            cfp =  (self.nlCoeff[0] +
                    self.nlCoeff[1] * postinj_min_dark + 
                    self.nlCoeff[2] * postinj_min_dark**2)

            bmdCorr = blank_min_dark * cfb
            pmdCorr = postinj_min_dark * cfp
            spAbs_min_blank = np.log10((bmdCorr/pmdCorr).astype(int))
            sp = np.log10((blank_min_dark/postinj_min_dark).astype(int))    
        self.spCounts_df[str(n_inj)] = postinj_spec
        return spAbs_min_blank

    def save_evl(self, folderPath, flnmStr):
        evlpath = folderPath + 'evl/'
        if not os.path.exists(evlpath):
            os.makedirs(evlpath)
        flnm = evlpath + flnmStr +'.evl'
        if self.args.co3:
            self.CO3_eval.to_csv(flnm, index = False, header=True) 
        else:
            self.evalPar_df.to_csv(flnm, index = False, header=True) 

    def save_spt(self,folderPath,flnmStr):
        sptpath = folderPath + 'spt/'
        if not os.path.exists(sptpath):
            os.makedirs(sptpath)
        self.spCounts_df.T.to_csv(
            sptpath + flnmStr + '.spt',
            index = True, header=False)

    def save_logfile_df(self,folderPath,flnmStr):
        print ('save log file df')
        # check time of cration of the last log file 
        # if more than one hour,
        # create new file and write data there .
        # in the separate logs folder .  
        # additionaly to regular common Ph log  
        hour_log_path = folderPath + 'logs/'
        hour_log_flnm = hour_log_path + flnmStr +'.log'  

        if not os.path.exists(hour_log_path):
            os.makedirs(hour_log_path)

            self.pH_log_row.to_csv(hour_log_flnm, index = False, header=True)                                     
            # and create logfile 
        else: 
            # list all files in the directory  
            files_in_path = os.listdir(hour_log_path)

            # convert names to datetimes 
            file_times = [datetime.strptime(n[:-4], self.fformat) for n in files_in_path]

            #find latest file            
            last_file_time =max(file_times)
            print ('last_file_time',last_file_time)
            # and its index
            ind_last_file = np.argmax(file_times)

            # get the name 
            last_file_name = files_in_path[ind_last_file]  

            # convert filename (newcoming) to datetime 
            new_time = datetime.strptime(flnmStr, self.fformat)

            # calculate delta in hours 
            delta = (new_time - last_file_time).seconds // 3600
            print ('delta in times log file',delta)
            if delta > 1: 
                # if more than hour, create a new file
                self.pH_log_row.to_csv(hour_log_flnm, index = False, header=True)    
            else: 
                # else append the old hourly file 
                self.pH_log_row.to_csv(last_file_name, mode = 'a', index = False, header=False) 

        logfile = os.path.join(folderPath, 'pH.log')
        #logfile_hourly = 
        if os.path.exists(logfile):
            self.pH_log_row.to_csv(logfile, mode = 'a', index = False, header=False) 
        else: 
            '''log_df = pd.DataFrame(
                columns= ["Time","Lon","Lat","fb_temp",
                         "fb_sal",'SHIP',"pH_lab", 
                          "T_lab", "perturbation",
                          "evalAnir", "pH_insitu"])'''
            self.pH_log_row.to_csv(logfile, index = False, header=True) 
        print ('saved log_df')

    def send_to_ferrybox(self):
        row_to_string = self.pH_log_row.to_csv(index = False, header=True).rstrip()
        udp.send_data('$PPHOX,' + row_to_string + ',*\n')   


class boxUI(QtGui.QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parser = argparse.ArgumentParser()

        try: 
            box_id = open('/home/pi/box_id.txt', "r").read()
        except:
            box_id = 'template'
        config_name = 'configs/config_'+ box_id + '.json'

        parser.add_argument("--pco2",
                            action="store_true")     
        parser.add_argument("--co3",
                            action="store_true")    
        parser.add_argument("--debug",
                            action="store_true")
        parser.add_argument("--seabreeze",
                            action="store_true") 
        parser.add_argument("--stability",
                            action="store_true")                            

        self.args = parser.parse_args()

        if self.args.pco2:
            self.setWindowTitle('pH Box Instrument, parameters pH and pCO2')
        elif self.args.co3: 
            self.setWindowTitle('Box Instrument, parameter CO3')
        else: 
            self.setWindowTitle('Box Instrument, NIVA - pH')

        self.main_widget = Panel(self,self.args,config_name)
        self.setCentralWidget(self.main_widget)
        self.showMaximized()  
        self.main_widget.autorun()

        with loop:
            sys.exit(loop.run_forever())
            
    def closeEvent(self,event):
        result = QtGui.QMessageBox.question(self,
                      "Confirm Exit...",
                      "Are you sure you want to exit ?",
                      QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)
        event.ignore()

        if result == QtGui.QMessageBox.Yes:
            if self.args.co3:
                self.main_widget.instrument.turn_off_relay(self.main_widget.instrument.light_slot)
            if self.args.seabreeze:
                self.main_widget.instrument.spectrom.spec.close()          

            print ('timer is stopped')
            self.main_widget.timer_contin_mode.stop()                
            udp.UDP_EXIT = True
            udp.server.join()
            if not udp.server.is_alive():
                print ('UDP server closed')
                udp.server.join()       
            self.main_widget.close()
            QtGui.QApplication.quit()  
            sys.exit()
            event.accept()


loop = None
if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    d = os.getcwd()
    qss_file = open('styles.qss').read()
    app.setStyleSheet(qss_file)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)  

    ui  = boxUI()
    
    app.exec_()




