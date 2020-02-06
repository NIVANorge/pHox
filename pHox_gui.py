#! /usr/bin/python

from pHox import *
from pco2 import CO2_instrument
import os,sys
os.chdir('/home/pi/pHox')
os.system('clear')

import warnings, time, RPi.GPIO 
import RPi.GPIO as GPIO
from datetime import datetime, timedelta
from PyQt5 import QtGui, QtCore, QtWidgets
import numpy as np
import pyqtgraph as pg 
import argparse, socket
import pandas as pd 
import time 
import udp # Ferrybox data
from udp import Ferrybox as fbox
from precisions import precision as prec 

from asyncqt import QEventLoop, asyncSlot, asyncClose
import asyncio


class Panel(QtGui.QWidget):
    def __init__(self,parent,panelargs,config_name):
        super(QtGui.QWidget, self).__init__(parent)
        #super(Panel, self).__init__()
                                                                                    
        self.continous_mode_is_on = False
        self.args = panelargs
        self.config_name = config_name
        self.adjusting = False 
        self.create_timers()

        if self.args.co3:
            self.instrument = CO3_instrument(self.args,self.config_name)
        else:
            self.instrument = pH_instrument(self.args,self.config_name)

        self.wvls = self.instrument.calc_wavelengths()
        self.instrument.get_wvlPixels(self.wvls)

        print ('instrument created')
        if self.args.pco2:
            self.CO2_instrument = CO2_instrument(self.config_name)

        self.init_ui()

    def init_ui(self):

        self.tabs = QtGui.QTabWidget()

        self.tab1 =        QtGui.QWidget()
        self.tab_manual =  QtGui.QWidget()
        self.tab_log =     QtGui.QWidget()
        self.tab_config =  QtGui.QWidget()

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
        self.timerSpectra_plot = QtCore.QTimer()
        self.timerTemp_info = QtCore.QTimer()
        self.timerSave = QtCore.QTimer()
        self.timerAuto = QtCore.QTimer()
        self.timerSpectra_plot.setInterval(1.e3) # 10 sec     
        self.timer_contin_mode.timeout.connect(self.continuous_mode_timer_finished)
        self.timerSpectra_plot.timeout.connect(self.update_spectra_plot)
        self.timerTemp_info.timeout.connect(self.update_T_lab)

        if self.args.pco2:
            self.timerSave.timeout.connect(self.save_pCO2_data)

    def make_plotwidgets(self):
        #create plotwidgets
        self.plotwdigets_groupbox = QtGui.QGroupBox()

        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget2 = pg.PlotWidget()
                
        if not self.args.co3:
            self.plotwidget1.setYRange(1000,16200)
        if self.args.co3: 
            #self.plotwidget1.setYRange(1000,67000)
            self.plotwidget2.setYRange(0,1)
            self.plotwidget1.setXRange(220,260)   
            self.plotwidget2.setXRange(220,260)   

        self.plotwidget1.setBackground('#19232D')
        self.plotwidget1.showGrid(x=True, y=True)
        self.plotwidget1.settTtle="LEDs intensities"


        #self.plotwidget2.setYRange(0,1.3)
 
        #self.plotwidget2.setXRange(410,610)
        self.plotwidget2.showGrid(x=True, y=True)
        self.plotwidget2.setBackground('#19232D')     

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
                        QtWidgets.QCheckBox('2  Measuring blank'),
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
        print (str(self.instrument.specIntTime))
        print (index)
        if index >= 0: 
            self.specIntTime_combo.setCurrentIndex(index)

    def fill_table_config(self,x,y,item):
        self.tableWidget.setItem(x,y,QtGui.QTableWidgetItem(item))

    def sampling_int_chngd(self,ind):
        print ('value chaged',ind)
        minutes = int(self.samplingInt_combo.currentText())
        self.instrument.samplingInterval = int(minutes)*60

    def specIntTime_combo_chngd(self,ind):
        new_int_time = int(self.specIntTime_combo.currentText())
        self.instrument.specIntTime = new_int_time
        self.instrument.spectrom.set_integration_time(new_int_time)

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
        self.btn_dye_pmp = self.create_button('Dye pump',False)        
        self.btn_wpump = self.create_button('Water pump',True)
        self.btn_calibr = self.create_button('Make calibration',True)
        self.test_button = self.create_button('Test async',False)

        btn_grid.addWidget(self.btn_dye_pmp, 0, 0)
        btn_grid.addWidget(self.btn_calibr, 0, 1)

        btn_grid.addWidget(self.btn_adjust_leds,1,0)
        btn_grid.addWidget(self.btn_leds,    1, 1)

        btn_grid.addWidget(self.btn_valve, 2, 0)
        btn_grid.addWidget(self.btn_stirr, 2, 1)

        btn_grid.addWidget(self.btn_wpump, 4, 0)
        btn_grid.addWidget(self.test_button,4,1)

        # Define connections Button clicked - Result 
        self.btn_leds.clicked.connect(self.btn_leds_checked)
        self.btn_valve.clicked.connect(self.btn_valve_clicked)
        self.btn_stirr.clicked.connect(self.btn_stirr_clicked)
        self.btn_wpump.clicked.connect(self.btn_wpump_clicked)
        self.test_button.clicked.connect(self.test_btn_clicked)
        if self.args.co3 :
            self.btn_lightsource = self.create_button('light source',True)
            btn_grid.addWidget(self.btn_lightsource , 4, 1)
            self.btn_lightsource.clicked.connect(self.btn_lightsource_clicked)

        self.btn_adjust_leds.clicked.connect(self.on_autoAdjust_clicked)
        self.btn_calibr.clicked.connect(self.btn_calibr_clicked)
        #self.btn_t_dark.clicked.connect(self.on_dark_clicked)
        self.btn_dye_pmp.clicked.connect(self.btn_dye_pmp_clicked)

        self.buttons_groupBox.setLayout(btn_grid)

    @asyncSlot()
    async def test_btn_clicked(self):
        print ('Start waiting 15 seconds to test async')
        self.StatusBox.setText('Start waiting 15 seconds to test async')
        #self.logTextBox.appendPlainText('Start waiting 15 seconds to test async')
        await asyncio.sleep(15)
        print ('stop')
        self.StatusBox.setText('stop')
        #self.logTextBox.appendPlainText('Stop waiting to test async')

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

    def btn_lightsource_clicked(self):
        print ('btn_lightsource_clicked')
        print (self.btn_lightsource.isChecked())

        if self.btn_lightsource.isChecked():  
            self.instrument.turn_on_relay(
                self.instrument.light_slot)
        else: 
            self.instrument.turn_off_relay(
                self.instrument.light_slot)        

    def btn_dye_pmp_clicked(self):
        self.instrument.cycle_line(self.instrument.dyepump_slot,3)

    def btn_valve_clicked(self):
        self.instrument.set_Valve(self.btn_valve.isChecked())

    def btn_save_config_clicked(self):
        
        with open(self.config_name,'r+') as json_file:
            j = json.load(json_file)

            j['pH']['Default_DYE'] = self.dye_combo.currentText()

            j['Operational']["Spectro_Integration_time"] = self.instrument.specIntTime
            minutes = int(self.samplingInt_combo.currentText())
            print ('minute',minutes,type(minutes))
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
        print ('value chaged',ind)
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

    @asyncSlot()
    async def spin_change(self,value):
        source = self.sender()
        ind = self.spinboxes.index(source)
        value = self.spinboxes[ind].value()
        _ = await self.instrument.adjust_LED(ind,value)
        self.sliders[ind].setValue(value)
        self.btn_leds.setChecked(True)

    @asyncSlot()
    async def sld_change(self):
        source = self.sender()
        ind = self.sliders.index(source)
        value = self.sliders[ind].value()
        _ = await self.instrument.adjust_LED(ind,value)
        self.spinboxes[ind].setValue(value)
        self.btn_leds.setChecked(True)        
        _ = await self.update_spectra_plot()

    @asyncSlot()
    async def set_LEDs(self, state):
        for i in range(0,3):
            r = await self.instrument.adjust_LED(i, state*self.sliders[i].value())
        self.append_logbox('Leds {}'.format(str(state)))

    def btn_leds_checked(self):
        state = self.btn_leds.isChecked()
        self.set_LEDs(state)
        self.update_spectra_plot()

    def on_selFolderBtn_released(self):
        self.folderDialog = QtGui.QFileDialog()
        folder = self.folderDialog.getExistingDirectory(self,'Select directory')
        self.instrument.folderPath = folder+'/'

    def save_stability_test(self,datay):
        stabfile = os.path.join('/home/pi/pHox/sp_stability.log')        
        if not self.args.co3:
            stabfile_df = pd.DataFrame({
            'datetime' : [datetime.now().strftime("%Y%m%d_%H%M%S") ],
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

    @asyncSlot()
    async def update_absorption_plot(self,n_inj,spAbs):
        self.abs_lines[n_inj].setData(self.wvls,spAbs) 


    @asyncSlot()
    async def update_spectra_plot(self):
        if self.adjusting == False:  
            if not self.args.seabreeze:
                datay = self.instrument.spectrom.get_corrected_spectra()      
            else:
                try: 
                    datay = self.instrument.spectrom.get_intensities()   
                    if self.args.stability:
                        self.save_stability_test(datay)
                except:
                    print ('Exception error') 
                    pass
            await asyncio.sleep(self.instrument.specIntTime*1.e-6)
        elif self.adjusting == True: 
            try: 
                datay = self.instrument.spectrum
            except: 
                pass
        try:    
            self.plotSpc.setData(self.wvls,datay) 
        except: 
            pass 

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

    @asyncSlot()
    async def on_autoAdjust_clicked(self):
        print ('on_autoAdjust_clicked')
        self.adjusting = True
        if self.args.co3:
            adj,pixelLevel = await self.instrument.auto_adjust()  
            if adj: 
                self.append_logbox('Finished Autoadjust LEDS')
                self.update_spec_int_time_table()
                self.plotwidget1.plot([self.instrument.wvl2],[pixelLevel], 
                                                    pen=None, symbol='+') 
                self.update_spectra_plot()

        else: 

            self.LED1,self.LED2,self.LED3,sptIt,result  = await self.instrument.auto_adjust()
            print (self.LED1,self.LED2,self.LED3)
            if result:
                self.sliders[0].setValue(self.LED1)
                self.sliders[1].setValue(self.LED2)
                self.sliders[2].setValue(self.LED3)

                #self.plot_sp_levels()
                self.instrument.specIntTime = sptIt
                self.append_logbox('Adjusted LEDS with intergration time {}'.format(sptIt))
                self.tableWidget.setItem(6,1,QtGui.QTableWidgetItem(
                    str(self.instrument.specIntTime)))  
                if not self.args.seabreeze:    
                    self.instrument.specAvScans = 3000/sptIt
            else:
                pass
                #self.textBox.setText('Could not adjust leds')
        self.adjusting = False
        self.btn_adjust_leds.setChecked(False)
        
        return 'Finished'

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
        self.instrument.timeStamp  = t.isoformat('_')
        tsBegin = (t-datetime(1970,1,1)).total_seconds()
        nextSamplename = datetime.fromtimestamp(tsBegin + self.instrument.samplingInterval)
        return str(nextSamplename.strftime("%H:%M"))    

    def get_filename(self):
        t = datetime.now()
        self.instrument.timeStamp  = t.isoformat('_')
        self.instrument.flnmStr =  datetime.now().strftime("%Y%m%d_%H%M%S") 
        return

    def btn_cont_meas_clicked(self):
        print ('btn_cont_meas_clicked')
        self.mode = 'Continuous'
        state = self.btn_cont_meas.isChecked()
        if state:
            self.btn_single_meas.setEnabled(False) 
            self.btn_calibr.setEnabled(False) 
            # disable all btns in manual tab 
            nextSamplename = self.get_next_sample()
            self.StatusBox.setText("Next sample at {}".format(nextSamplename))
            self.timer_contin_mode.start(self.instrument.samplingInterval*1000)
        else:
            self.StatusBox.clear()            
            self.timer_contin_mode.stop()
            if not self.continous_mode_is_on:
                self.btn_single_meas.setEnabled(True) 
                self.btn_calibr.setEnabled(True) 

    def btn_calibr_clicked(self):
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

        self.instrument.reset_lines()

        self.sample()
        self.single_sample_finished()

        #self.sample_thread = Sample_thread(self,self.args)
        #self.sample_thread.start()
        #self.sample_thread.finished.connect(self.single_sample_finished)

    @asyncSlot()
    async def btn_single_meas_clicked(self):

        message = QtGui.QMessageBox.question(self,
                    "important message!!!",
                    "Did you pump to clean?",
                    QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)
        if message == QtGui.QMessageBox.No:
            self.btn_single_meas.setChecked(False)             
            return

        self.get_filename()        
        text, ok = QtGui.QInputDialog.getText(None, 'Enter Sample name', 
                                        self.instrument.flnmStr)
        if ok:
            if text != '':
                self.instrument.flnmStr = text

            self.btn_cont_meas.setEnabled(False)
            self.btn_single_meas.setEnabled(False) 
            self.btn_calibr.setEnabled(False) 
            # disable all btns in manual tab 

            self.mode = 'Single'

            #self.instrument.reset_lines()
            self.timerSpectra_plot.stop()
            if self.args.co3 :
                await self.co3_sample()
            else: 
                await self.sample()
                self.single_sample_finished()

        else: 
            self.btn_single_meas.setChecked(False) 

    def continuous_mode_timer_finished(self):
        print ('start continuous mode')
        self.append_logbox('Inside continuous_mode...')

        self.instrument.reset_lines()
        self.timerSpectra_plot.stop()
        self.sample_thread = Sample_thread(self,self.args)
        self.continous_mode_is_on = True

        self.sample()
        self.continuous_sample_finished() 



    def unclick_enable(self,btns):
        for btn in btns:
            btn.setChecked(False)    
            btn.setEnabled(True)            

    def get_final_pH(self):
        # get final pH
        p = self.instrument.pH_eval(self.evalPar_df)
        pH_lab, T_lab, perturbation, evalAnir, pH_insitu,self.x,self.y,self.slope, self.intercept = p

        self.pH_log_row = pd.DataFrame({
            "Time"         : [self.instrument.timeStamp[0:16]],
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
         
        #print (self.x,self.y,self.intercept,self.slope)        

    def save_results(self):
    
        if self.mode == 'Calibration':
            folderPath = '/home/pi/pHox/data_calibr/'            
        else: 
            folderPath = self.instrument.folderPath   

        self.append_logbox('Save spectrum data to file')
        #self.sample_steps[7].setChecked(True)
        self.save_spt(folderPath)

        self.append_logbox('Save evl data to file')
        self.save_evl(folderPath)   

        self.append_logbox('Send data to ferrybox')        
        self.send_to_ferrybox()

        self.append_logbox('Save final data in %s' % (folderPath+'pH.log'))
        self.save_logfile_df(folderPath)
  
    def update_pH_plot(self):
        self.plotwidget2.plot(self.x,self.y, pen=None, symbol='o', clear=True)  
        self.plotwidget2.plot(self.x,self.intercept + self.slope*self.x)   

    def single_sample_finished(self):

        print ('single sample finished inside func')    

        self.get_final_pH()
        self.StatusBox.setText('Measurement is finished')       

        self.save_results()
        self.update_pH_plot()        
        self.update_infotable()

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

    def continuous_sample_finished(self):

        print ('inside continuous_sample_finished')
        self.continous_mode_is_on = False

        self.get_final_pH() 
        self.StatusBox.setText('Measurement is finished') 

        self.save_results()
        self.update_pH_plot()
        self.update_infotable()   

        [step.setChecked(False) for step in self.sample_steps]

        print ('start timer spectra plot')
        self.timerSpectra_plot.start(1000)
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
            self.set_LEDs(True)
            self.update_LEDs()
            self.btn_leds.setChecked(True)
            self.btn_leds_checked()

        self.timerSpectra_plot.start(3.e3)
        self.timerTemp_info.start(1.e3)
        #print ('run autoadjust')        
        #self.textBox.setText('Adjusting LEDs')
        #self.on_autoAdjust_clicked()

        if not self.args.co3 or not self.args.debug: 
            print ('Starting continuous mode ')
            self.textBox.setText('Starting continuous mode ')
            self.btn_cont_meas.setChecked(True)
            self.btn_cont_meas_clicked()

        if not self.args.debug:
            self.update_spectra_plot()
            self.textBox.setText('The instrument is ready')
            #self.on_deploy_clicked(True)
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
        #self.timerSpectra_plot.stop()
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

    def co3_sample(self):   
        z = np.zeros(len(self.wvls))
        [self.update_absorption_plot(n_inj,z) for n_inj in range(self.instrument.ncycles)]
        self.CO3_eval = pd.DataFrame(columns=["CO3", "e1", "e2e3",
                                     "log_beta1_e2", "vNTC", "S", 
                                     "A1", "A2", "R", "Tdeg", 
                                     "Vinj", " S_corr"])   
                                          
        QtGui.QApplication.processEvents()   
        if self.mode == 'Calibration': 
            folderPath = '/home/pi/pHox/data_co3_calibr/'
        else:
            folderPath = self.instrument.folderPath        
        print ('co3_sample')
        #self.get_filename()
        #time.sleep(2)

        self.StatusBox.setText('Ongoing measurement')
        self.sample_steps[0].setChecked(True)
        print ('self.sample_steps[0].setChecked(True)')
        #time.sleep(2)

        self.spCounts_df = pd.DataFrame(columns=['Wavelengths','blank'])
        self.spCounts_df['Wavelengths'] = ["%.2f" % w for w in self.wvls] 
        print ('self.spCounts_df')
        #time.sleep(2)

        if not fbox['pumping']:
            return

        self.append_logbox('Start new measurement')


        '''if self.instrument.deployment == 'Standalone' and self.mode == 'Continuous':
            self.pumping(self.instrument.pumpTime) 
            self.append_logbox('Pumping, Standalone, Continous')

        elif self.mode == 'Calibration':
            self.pumping(self.instrument.pumpTime) 
            self.append_logbox('Pumping, Calibration') '''   



        self.append_logbox('Autoadjust LEDS')
        self.sample_steps[1].setChecked(True)

        self.on_autoAdjust_clicked()




        #reset light source 
        '''self.instrument.turn_off_relay(self.instrument.light_slot)    
        self.btn_lightsource.setChecked(False)        
        time.sleep(0.1)     
        self.instrument.turn_on_relay(self.instrument.light_slot)  
        self.btn_lightsource.setChecked(True) '''


        self.update_spectra_plot()   
        QtGui.QApplication.processEvents() 
        print ('before blank', self.instrument.specIntTime)
        blank_min_dark, dark = self.valve_and_blank()
        print ('after blank', self.instrument.specIntTime)       
        QtGui.QApplication.processEvents()  
        self.update_spectra_plot()        
        QtGui.QApplication.processEvents()   

        for n_inj in range(self.instrument.ncycles):  
            print ('n_inj in co3 sample')
          
            vol_injected = round(
                self.instrument.dye_vol_inj*(n_inj+1)*self.instrument.nshots,
                 prec['vol_injected'])
            dilution = (self.instrument.Cuvette_V) / (
                    vol_injected  + self.instrument.Cuvette_V)      

            spAbs,vNTC = self.inject_measure(n_inj,blank_min_dark,dark)
            self.update_spectra_plot()  
            self.update_absorption_plot(n_inj,spAbs)
            self.append_logbox('Calculate init CO3') 
            QtGui.QApplication.processEvents()  

            self.CO3_eval.loc[n_inj] = self.instrument.calc_CO3(
                                spAbs,vNTC,dilution,vol_injected)

        self.append_logbox('Opening the valve ...')
        QtGui.QApplication.processEvents()
        self.instrument.set_Valve(False)
        self.timerSpectra_plot.start()   
        self.unclick_enable([self.btn_single_meas,
        self.btn_calibr,self.btn_cont_meas])
        [step.setChecked(False) for step in self.sample_steps]

        self.append_logbox('Save spectrum data to file')
        #self.sample_steps[7].setChecked(True)
        self.save_spt(folderPath)

        self.append_logbox('Save evl data to file')
        self.save_evl(folderPath)          
        #self.append_logbox('Autoadjust LEDS')'''
        print ('finished sample')


    def create_new_df(self):
        self.spCounts_df = pd.DataFrame(columns=['Wavelengths','dark','blank'])
        self.spCounts_df['Wavelengths'] = ["%.2f" % w for w in self.wvls] 

        self.evalPar_df = pd.DataFrame(columns=["pH", "pK", "e1",
                                                "e2", "e3", "vNTC",
                                        'salinity', "A1", "A2","Tdeg",  
                                       "S_corr", "Anir",'Vol_injected',
                                       "TempProbe_id","Probe_iscalibr",
                                        'TempCalCoef1','TempCalCoef2','DYE'])

    async def sample(self):
   
        _= await self.start_pump_adjustleds()

        blank_min_dark,dark =  await self.valve_and_blank()


        for n_inj in range(self.instrument.ncycles):  
            vol_injected = round(
                self.instrument.dye_vol_inj*(n_inj+1)*self.instrument.nshots,
                 prec['vol_injected'])
            dilution = (self.instrument.Cuvette_V) / (
                    vol_injected  + self.instrument.Cuvette_V)      

            spAbs,vNTC = await self.inject_measure(n_inj,blank_min_dark,dark)

            #self.append_logbox('Calculate init pH') 
            print ('Calculate init pH') 
            self.evalPar_df.loc[n_inj] = self.instrument.calc_pH(
                                spAbs,vNTC,dilution,vol_injected)
        print ('Opening the valve ...')
        #self.append_logbox('Opening the valve ...')

        self.instrument.set_Valve(False)

    async def start_pump_adjustleds(self):
        print ('pH_sample, mode is {}'.format(self.mode))

        self.StatusBox.setText('Ongoing measurement')
        self.sample_steps[0].setChecked(True)

        if self.mode == 'Continuous' or self.mode == 'Calibration': 
            if not fbox['pumping']:
                return               
            self.get_filename() 

        self.create_new_df()

        self.append_logbox('Start new measurement')
        if self.instrument.deployment == 'Standalone' and self.mode == 'Continuous':
            _ = await self.instrument.pumping(self.instrument.pumpTime) 
            #self.append_logbox('Pumping, Standalone, Continous')

        elif self.mode == 'Calibration':
            self.instrument.pumping(self.instrument.pumpTime) 
            #self.append_logbox('Pumping, Calibration') 

        self.append_logbox('Autoadjust LEDS')
        self.sample_steps[1].setChecked(True)
        _ = await self.on_autoAdjust_clicked()  
        #self.append_logbox('Finished Autoadjust LEDS')
        self.set_LEDs(True)
        self.btn_leds.setChecked(True)

    async def valve_and_blank(self):
        #self.append_logbox('Closing valve ...')
        print ("Closing valve ...")
        self.instrument.set_Valve(True)
        #time.sleep(self.instrument.waitT)
        
        ### take the dark
        if self.args.co3:
            self.instrument.turn_off_relay(self.instrument.light_slot)
            print ('turn of the light source')
            time.sleep(5)
        else: 
            self.set_LEDs(False)
            # turn off light and LED
            # grab spectrum
            
        if not self.args.seabreeze:
            dark = await self.instrument.spectrom.get_corrected_spectra()

        elif self.args.seabreeze:
            #raw = str(n_inj)+'raw'
            #self.spCounts_df[raw] = self.instrument.spectrom.get_intensities(
            #        self.instrument.specAvScans,correct=False)
            # time.sleep(0.5)
            dark = self.instrument.spectrom.get_intensities(
                    self.instrument.specAvScans,correct=True)
        
        #turn on the light and LED
        if self.args.co3:
            _ = await self.instrument.turn_on_relay(self.instrument.light_slot)
            print ('turn on the light source')
            await asyncio.sleep(5)
        else: 
            self.set_LEDs(True)


        print ('Measuring blank...')
        #self.append_logbox('Measuring blank...')
        self.sample_steps[2].setChecked(True)
        if not self.args.seabreeze:
            self.nlCoeff = [1.0229, -9E-6, 6E-10] # we don't know what it is  
            blank = await self.instrument.spectrom.get_corrected_spectra()
            blank_min_dark= np.clip(blank,1,16000)
        else: 
            blank = self.instrument.spectrom.get_intensities(
                    self.instrument.specAvScans,correct=True)    
            blank_min_dark =   blank - dark    
            print ('max blank',np.max(blank))

        self.spCounts_df['blank'] = blank
        self.spCounts_df['dark'] = dark
        
        return blank_min_dark , dark 

    async def inject_measure(self,n_inj,blank_min_dark,dark): 
        # create dataframe and store 
        print ('n_inj',n_inj)            
        self.sample_steps[n_inj+3].setChecked(True)

        shots = self.instrument.nshots

        self.append_logbox('Start stirrer')               
        _ = await self.instrument.turn_on_relay(self.instrument.stirrer_slot)

        if not self.args.debug:
            self.append_logbox('Dye Injection %d:' %(n_inj+1)) 
            self.instrument.cycle_line(self.instrument.dyepump_slot, shots)

        #self.append_logbox("Mixing")
        await asyncio.sleep(self.instrument.mixT)
        #self.append_logbox('Stop stirrer')    
        self.instrument.turn_off_relay(self.instrument.stirrer_slot)
        #self.append_logbox('Wait')            
        await asyncio.sleep(self.instrument.waitT)

        # measuring Voltage for temperature probe
        vNTC = self.instrument.get_Vd(3, self.instrument.vNTCch)
        self.append_logbox('Get spectrum')
        # measure spectrum after injecting nshots of dye 
        if not self.args.seabreeze:
            postinj = await self.instrument.spectrom.get_corrected_spectra()
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
            spAbs = np.log10((bmdCorr/pmdCorr).astype(int))
            sp = np.log10((blank_min_dark/postinj_min_dark).astype(int))         
                
        # Write spectrum to the file 
        elif self.args.seabreeze:
            #raw = str(n_inj)+'raw'
            #self.spCounts_df[raw] = self.instrument.spectrom.get_intensities(
            #        self.instrument.specAvScans,correct=False)
            # time.sleep(0.5)
            postinj_spec = await self.instrument.spectrom.get_intensities(
                    self.instrument.specAvScans,correct=True)
            postinj_spec_min_dark = postinj_spec - dark
            # Absorbance 
            spAbs_min_blank = - np.log10 (postinj_spec_min_dark / blank_min_dark)
            #blank
        self.spCounts_df[str(n_inj)] = postinj_spec
        return (spAbs_min_blank,vNTC)

    def save_evl(self,folderPath):
        evlpath = folderPath + 'evl/'
        if not os.path.exists(evlpath):
            os.makedirs(evlpath)
        flnm = evlpath + self.instrument.flnmStr +'.evl'
        if self.args.co3:
            self.CO3_eval.to_csv(flnm, index = False, header=True) 
        else:
            self.evalPar_df.to_csv(flnm, index = False, header=True) 

    def save_spt(self,folderPath):
        sptpath = folderPath + 'spt/'
        if not os.path.exists(sptpath):
            os.makedirs(sptpath)
        self.spCounts_df.T.to_csv(
            sptpath + self.instrument.flnmStr + '.spt',
            index = True, header=False)

    def save_logfile_df(self,folderPath):
        logfile = os.path.join(folderPath, 'pH.log')
        if os.path.exists(logfile):
            self.pH_log_row.to_csv(logfile, mode = 'a', index = False, header=False) 
        else: 
            log_df = pd.DataFrame(
                columns= ["Time","Lon","Lat","fb_temp",
                         "fb_sal",'SHIP',"pH_lab", 
                          "T_lab", "perturbation",
                          "evalAnir", "pH_insitu"])
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
        print (config_name)
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

if __name__ == '__main__':

    app = QtGui.QApplication(sys.argv)
    qss_file = open('styles.qss').read()
    app.setStyleSheet(qss_file)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)  

    ui  = boxUI()
    
    app.exec_()




