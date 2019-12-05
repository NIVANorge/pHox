#! /usr/bin/python

from pHox import *
from pco2 import CO2_instrument
import os,sys
os.chdir('/home/pi/pHox')
os.system('clear')
import warnings
import time
import RPi.GPIO as GPIO
from datetime import datetime, timedelta
import pigpio
from PyQt4 import QtGui, QtCore
import numpy as np
import pyqtgraph as pg 
import argparse
import socket
import pandas as pd 

import udp # Ferrybox data
from udp import Ferrybox as fbox

class Console(QtGui.QWidget):
   
   def __init__(self):
      super(Console, self).__init__()
      self.init_ui()

   def init_ui(self):
      self.setWindowTitle('Console')
      self.textBox = QtGui.QTextEdit()
      grid = QtGui.QGridLayout()
      grid.addWidget(self.textBox)
      self.setLayout(grid)
      self.resize(800,200)
      self.show()

   def printText(self, text):
      self.textBox.append(text)

class Panel(QtGui.QWidget):
    def __init__(self):
        super(Panel, self).__init__()

        parser = argparse.ArgumentParser()
        parser.add_argument("--debug",
                            action="store_true")
        parser.add_argument("--pco2",
                            action="store_true")

        self.args = parser.parse_args()
        self.create_timers()
        
        self.instrument = pH_instrument()
        if self.args.pco2:
            self.CO2_instrument = CO2_instrument()

        self.init_ui()

        self.timerSensUpd.start(2000)


    def init_ui(self):

        self.setWindowTitle('NIVA - pH')

        self.tabs = QtGui.QTabWidget()

        self.tab1 =        QtGui.QWidget()
        self.tab_manual =  QtGui.QWidget()
        self.tab_log =     QtGui.QWidget()
        self.tab_config =  QtGui.QWidget()
        self.tab_calibr =  QtGui.QWidget()

        # Add tabs
        self.tabs.addTab(self.tab1,       "Home")
        self.tabs.addTab(self.tab_manual, "Manual")
        self.tabs.addTab(self.tab_log,    "Log")
        self.tabs.addTab(self.tab_config, "Config")
        self.tabs.addTab(self.tab_calibr, "Calibr")

        self.tab_log.layout =     QtGui.QGridLayout()
        self.logTextBox = QtGui.QPlainTextEdit()
        self.logTextBox.setReadOnly(True)
        if self.args.debug:
            self.logTextBox.appendPlainText('Starting in debug mode')
        self.tab_log.layout.addWidget(self.logTextBox) 
        self.tab_log.setLayout(self.tab_log.layout)


        self.tab_manual.layout  = QtGui.QGridLayout()
        self.make_btngroupbox()
        self.make_slidergroupbox()
        self.tab_manual.layout.addWidget(self.sliders_groupBox)
        self.tab_manual.layout.addWidget(self.buttons_groupBox)
        self.tab_manual.setLayout(self.tab_manual.layout)

        self.make_tab1()
        self.make_tab_config()
        self.make_plotwidgets()

        # combine layout for plots and buttons
        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addWidget(self.plotwdigets_groupbox)    
        hboxPanel.addWidget(self.tabs)
    
        self.setLayout(hboxPanel)
        self.showMaximized()

    def create_timers(self):
        self.timerSpectra = QtCore.QTimer()
        self.timer_contin_mode = QtCore.QTimer()
        self.timerSensUpd = QtCore.QTimer()
        self.timerSave = QtCore.QTimer()
        #self.timerFIA = QtCore.QTimer()
        self.timerAuto = QtCore.QTimer()
        self.timerSpectra.timeout.connect(self.update_spectra)
        self.timer_contin_mode.timeout.connect(self.continuous_mode)
        self.timerSensUpd.timeout.connect(self.update_sensors_info)
        if self.args.pco2:
            self.timerSave.timeout.connect(self.save_pCO2_data)

    def make_plotwidgets(self):
        #create plotwidgets
        self.plotwdigets_groupbox = QtGui.QGroupBox()

        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget1.setYRange(0,16000)
        self.plotwidget1.setBackground('#19232D')

        self.plotwidget2 = pg.PlotWidget()
        self.plotwidget2.setYRange(0,1.3)
        self.plotwidget2.setXRange(410,610)
        self.plotwidget2.setBackground('#19232D')     

        vboxPlot = QtGui.QVBoxLayout()
        vboxPlot.addWidget(self.plotwidget1)
        vboxPlot.addWidget(self.plotwidget2)
        self.plotwidget1.addLine(x=None, y=11500, pen=pg.mkPen('w', width=3, style=QtCore.Qt.DotLine))
        self.plotSpc= self.plotwidget1.plot()

        self.plotAbs= self.plotwidget2.plot()

        self.plotwdigets_groupbox.setLayout(vboxPlot)

    def make_tab1(self):
        self.tab1.layout = QtGui.QGridLayout()
        self.textBox = QtGui.QTextEdit()
        self.textBox.setOverwriteMode(True)

        self.textBoxSens = QtGui.QTextEdit()
        self.textBoxSens.setOverwriteMode(True)

        self.btn_cont_meas = self.create_button('Continuous measurements',True)
        self.btn_sigle_meas = self.create_button('Single measurement',False)   
        self.btn_cont_meas.clicked.connect(self.btn_cont_meas_clicked)

        self.tab1.layout.addWidget(self.btn_cont_meas,0, 0, 1, 1)
        self.tab1.layout.addWidget(self.btn_sigle_meas, 0, 1)
        self.tab1.layout.addWidget(self.textBox,      1,0)
        self.tab1.layout.addWidget(self.textBoxSens,  1,1)
        self.tab1.setLayout(self.tab1.layout)

    def make_tab_config(self):
        self.tab_config.layout =  QtGui.QGridLayout()
        # Define widgets for config tab 
        self.reload_config = self.create_button('Reload config',False)     
        self.reload_config.clicked.connect(self.btn_reload_config_clicked) 

        self.dye_combo = QtGui.QComboBox()
        self.dye_combo.addItem('TB')
        self.dye_combo.addItem('MCP')        
        index = self.dye_combo.findText(self.instrument.dye, 
                                QtCore.Qt.MatchFixedString)
        if index >= 0: 
            self.dye_combo.setCurrentIndex(index)
            
        #self.dye_combo.valueChanged.connect(self.dye_combo_chngd)
        
        self.tableWidget = QtGui.QTableWidget()
        self.tableWidget.setHorizontalHeaderLabels(QtCore.QString("Parameter;Value").split(";"))
        header = self.tableWidget.horizontalHeader()
        header.setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
        self.tableWidget.setRowCount(8)
        self.tableWidget.setColumnCount(2)

        self.fill_table(0,0,'DYE type')
        self.tableWidget.setCellWidget(0,1,self.dye_combo)

        self.fill_table(1,0,'NIR:')
        self.fill_table(1,1,str(self.instrument.NIR))

        self.fill_table(2,0,'HI-')
        self.fill_table(2,1,str(self.instrument.HI))

        self.fill_table(3,0,'I2-')
        self.fill_table(3,1, str(self.instrument.I2))

        self.fill_table(4,0,'Cuvette volume:')
        self.fill_table(4,1, str(self.instrument.Cuvette_V))

        self.fill_table(5,0,'DYE calibration:')
        self.fill_table(5,1,' not used yet:')        

        self.fill_table(6,0,'Dye injection volume: ')
        self.fill_table(6,1, str(self.instrument.dye_vol_inj))

        self.fill_table(7,0,'pH sampling interval')
        self.fill_table(7,1, str(self.instrument.samplingInterval))
        self.tableWidget.horizontalHeader().setStretchLastSection(True)

        self.tab_config.layout.addWidget(self.reload_config,0,0,1,1)   
        self.tab_config.layout.addWidget(self.tableWidget,1,0,1,1)

        self.tab_config.setLayout(self.tab_config.layout)   

    def make_btngroupbox(self):
        # Define widgets for main tab 
        # Create checkabple buttons
        self.buttons_groupBox = QtGui.QGroupBox("Buttons GroupBox")
        btn_grid = QtGui.QGridLayout()


        self.btn_adjust_leds = self.create_button('Adjust Leds',True) 

        self.btn_t_dark = self.create_button('Take dark',False)
        self.btn_spectro = self.create_button('Spectrophotometer',True)
        self.btn_leds = self.create_button('LEDs',True)
        self.btn_valve = self.create_button('Inlet valve',True)
        self.btn_sampl_int = self.create_button( 'Set sampling interval',False)     
        self.btn_stirr = self.create_button('Stirrer',True)
        self.btn_dye_pmp = self.create_button('Dye pump',False)        
        self.btn_wpump = self.create_button('Water pump',True)

        # Unchecable buttons
        btn_grid.addWidget(self.btn_adjust_leds,0,0)
        btn_grid.addWidget(self.btn_spectro, 1, 0)
        btn_grid.addWidget(self.btn_leds,    1, 1)

        btn_grid.addWidget(self.btn_valve, 2, 0)
        btn_grid.addWidget(self.btn_stirr, 2, 1)

        btn_grid.addWidget( self.btn_sampl_int, 3, 0)
        btn_grid.addWidget(self.btn_dye_pmp, 3, 1)

        btn_grid.addWidget(self.btn_wpump, 4, 0)
        btn_grid.addWidget(self.btn_t_dark , 4, 1)


        # Define connections Button clicked - Result 
        self.btn_spectro.clicked.connect(self.spectro_clicked)
        self.btn_leds.clicked.connect(self.btn_leds_checked)
        self.btn_valve.clicked.connect(self.btn_valve_clicked)
        self.btn_stirr.clicked.connect(self.btn_stirr_clicked)
        self.btn_wpump.clicked.connect(self.btn_wpump_clicked)
        self.btn_adjust_leds.clicked.connect(self.on_autoAdjust_clicked)
        
        # Define connections for Unchecable buttons
        self.btn_t_dark.clicked.connect(self.on_dark_clicked)
        self.btn_sampl_int.clicked.connect(self.on_sampl_int_clicked)
        self.btn_dye_pmp.clicked.connect(self.btn_dye_pmp_clicked)

        self.buttons_groupBox.setLayout(btn_grid)

    def make_slidergroupbox(self):    
        self.sliders_groupBox = QtGui.QGroupBox("LED values")

        sldNames = ['Blue','Orange','Red']
        self.sliders = []
        self.sldLabels, self.spinboxes =  [], []
        self.plus_btns, self.minus_btns = [], []

        # create widgets
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

    def fill_table(self,x,y,item):
        self.tableWidget.setItem(x,y,QtGui.QTableWidgetItem(item))

    def btn_reload_config_clicked(self):
        self.logTextBox.appendPlainText('Button reload config was clicked')
        self.instrument.load_config()
        state = self.btn_leds.isChecked()
        self.sliders[0].setValue(self.instrument.LED1)
        self.sliders[1].setValue(self.instrument.LED2)
        self.sliders[2].setValue(self.instrument.LED3)
        self.set_LEDs(state)

    def btn_stirr_clicked(self):
        self.instrument.set_line(self.instrument.stirrer_slot,
        self.btn_stirr.isChecked())

    def btn_wpump_clicked(self):
        self.instrument.set_line(self.instrument.wpump_slot,
        self.btn_wpump.isChecked())

    def btn_cont_meas_clicked(self):
        state = self.btn_cont_meas.isChecked()
        self.logTextBox.appendPlainText('Continuous measerement mode is {}'.format(str(state)))
        if state:
           self.instrument.flnmStr=''
           self.tsBegin = (datetime.now()-datetime(1970,1,1)).total_seconds()
           nextSample = datetime.fromtimestamp(self.tsBegin + self.instrument.samplingInterval)
           self.logTextBox.appendPlainText("Start timer for the next sample at {}".format(str(nextSample)))
           self.timer_contin_mode.start(self.instrument.samplingInterval*1000)
        else:
           self.timer_contin_mode.stop()

    def btn_dye_pmp_clicked(self):
        self.instrument.cycle_line(self.instrument.dyepump_slot,3)

    def btn_valve_clicked(self):
        self.instrument.set_Valve(self.btn_valve.isChecked())

    def spectro_clicked(self):
        if self.btn_spectro.isChecked():
            self.timerSpectra.start(500)
        else:
            self.timerSpectra.stop()
            
    # not sure about connections, 
    # do we need it?
    # if yes, then wavelengths and pixels should
    # be also recalculated 
    # comment out for now       
    """def dye_combo_chngd(self,value):
        self.dye = value
        print (value)
        if self.dye == 'MCP':
            self.HI =  int(default['MCP_wl_HI'])
            self.I2 =  int(default['MCP_wl_I2-'])         
        elif self.dye == "TB":   
            self.HI =  int(default['TB_wl_HI-'])
            self.I2 =  int(default['TB_wl_I2-'])"""

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

    def on_dark_clicked(self):
        self.logTextBox.appendPlainText('Taking dark level...')
        self.set_LEDs(False)
        self.btn_leds.setChecked(False)

        self.logTextBox.appendPlainText('Measuring dark...')
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans) 
        dark = self.instrument.spectrometer.get_corrected_spectra()
        self.instrument.spCounts[0] = dark #self.instrument.spectrometer.get_corrected_spectra()
        self.instrument.spCounts_df['dark'] = dark #self.instrument.spectrometer.get_corrected_spectra()        
        self.instrument.spectrometer.set_scans_average(1)
        self.logTextBox.appendPlainText('Done')

        self.btn_t_dark.setText('Take dark ({} ms, n= {})'.format(
            str(self.instrument.specIntTime),
            str(self.instrument.specAvScans)))

    def set_LEDs(self, state):
        for i in range(0,3):
           self.instrument.adjust_LED(i, state*self.sliders[i].value())
        self.logTextBox.appendPlainText('Leds {}'.format(str(state)))

    def btn_leds_checked(self):
        state = self.btn_leds.isChecked()
        self.set_LEDs(state)

    def on_selFolderBtn_released(self):
        self.folderDialog = QtGui.QFileDialog()
        folder = self.folderDialog.getExistingDirectory(self,'Select directory')
        self.instrument.folderPath = folder+'/'

    def on_sampl_int_clicked(self): 
        time, ok = QtGui.QInputDialog.getInt(
            None, 'Set sampling interval',
            'Interval in seconds',
            value = self.instrument.samplingInterval,
            min = 200,max = 6000,step = 60)
        if ok:
            self.instrument.samplingInterval = time

    def update_spectra(self):
        datay = self.instrument.spectrometer.get_corrected_spectra()
        self.plotSpc.setData(self.instrument.wvls,datay)                  

    def save_pCO2_data(self, pH = None):
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
        
    '''def on_intTime_clicked(self):
        # Not used now
        intTime, ok = QtGui.QInputDialog.getInt(
            None, 'Set spectrophotometer integration time',
             'ms',self.instrument.specIntTime,100,3000,100)
        if ok:
            self.instrument.specIntTime = intTime
            self.instrument.spectrometer.set_integration_time(intTime)
            self.btn_spectro.setText('Spectrophotometer {} ms'.format(str(intTime)))
            #self.chkBox_caption('Spectrophotometer','%d ms' %intTime)'''
        
    '''def on_scans_clicked(self): 
        # Not used now
        scans, ok = QtGui.QInputDialog.getInt(None,
         'Set spectrophotometer averaging scans','',self.instrument.specAvScans,1,20,1)
        if ok:
            self.instrument.specAvScans = scans'''

    def on_autoAdjust_clicked(self):
        DC1,DC2,DC3,sptIt,result  = self.instrument.auto_adjust()
        if result:
            self.sliders[0].setValue(DC1)
            self.sliders[1].setValue(DC2)
            self.sliders[2].setValue(DC3)
            self.instrument.specIntTime = sptIt
            self.instrument.specAvScans = 3000/sptIt
        else:
            self.textBox.setText('Could not adjust leds')
        self.btn_adjust_leds.setChecked(False)

    def add_pco2_info(self,text):
        self.CO2_instrument.portSens.write(
            self.CO2_instrument.QUERY_CO2)
        resp = self.CO2_instrument.portSens.read(15)
        try:
            value =  float(resp[3:])
            value = self.CO2_instrument.ftCalCoef[6][0]+self.CO2_instrument.ftCalCoef[6][1]*value
        except ValueError:
            value = 0
        self.CO2_instrument.franatech[6] = value
        #self.puckEm.LAST_CO2 = self.CO2_instrument.franatech[6]

        self.CO2_instrument.portSens.write(self.CO2_instrument.QUERY_T)
        resp = self.CO2_instrument.portSens.read(15)
        try:
                self.CO2_instrument.franatech[7] = float(resp[3:])
        except ValueError:
                self.CO2_instrument.franatech[7] = 0

        for ch in range(5):
            V = self.get_Vd(2,ch+1)
            X = 0
            for i in range(2):
                X += self.CO2_instrument.ftCalCoef[ch][i] * pow(V,i)
            self.CO2_instrument.franatech[ch] = X
            text += self.CO2_instrument.VAR_NAMES[ch]+': %.2f\n'%X

        #self.puckEm.LAST_PAR[2] = self.instrument.salinity
        #self.puckEm.LAST_PAR[0]= self.instrument.franatech[0]   #pCO2 water loop temperature
        WD = self.get_Vd(1,6)
        text += self.CO2_instrument.VAR_NAMES[5]+ str (WD<0.04) + '\n'
        text += (self.CO2_instrument.VAR_NAMES[6]+': %.1f\n'%self.CO2_instrument.franatech[6] +
                    self.CO2_instrument.VAR_NAMES[7]+': %.1f\n'%self.CO2_instrument.franatech[7])
        self.textBoxSens.setText(text)

    def update_sensors_info(self):
        vNTC = self.get_Vd(3, self.instrument.vNTCch)
        #Tntc = 0
        Tntc = (self.instrument.ntcCalCoef[0]*vNTC) +self.instrument.ntcCalCoef[1]
        for i in range(2):
            Tntc += self.instrument.ntcCalCoef[i] * pow(vNTC,i)
            
           #Tntc = vNTC*(23.1/0.4173)
        text = 'Cuvette temperature \xB0C: %.4f  (%.4f V)\n' %(Tntc,vNTC)
        fmt  = 'FBPumping={:-d}\nFBTemperature={:-.2f}\nFBSalinity={:-.2f}\n'
        fmt += 'FBLongitude={:-.4f}\nFBLatitude={:-.4f}\n'
        text += fmt.format(fbox['pumping'], 
                           fbox['temperature'], 
                           fbox['salinity'],
                           fbox['longitude'], 
                           fbox['latitude'])
        self.textBoxSens.setText(text)

        if self.args.pco2:
            self.add_pco2_info(text)

    def on_sigle_meas_clicked(self):
        # Button "single" is clicked
        self.btn_spectro.setChecked(False)
        #self.check('Spectrophotometer',False)
        #self.timerSpectra.stop()
        t = datetime.now()
        self.instrument.timeStamp = t.isoformat('_')
        self.instrument.flnmStr =   t.strftime("%Y%m%d%H%M") 
        # dialog sample name  
        text, ok = QtGui.QInputDialog.getText(None, 'Sample name', 
                                        self.instrument.flnmStr)
        if ok:
            if text != '':
                self.instrument.flnmStr = text
            self.instrument.reset_lines()
            self.logTextBox.appendPlainText(
                'Start single measurement ')
            self.sample()
            self.logTextBox.appendPlainText('Single Measurement is Done')
            self.instrument.spectrometer.set_scans_average(1)
        self.timerSpectra.start()
        self.btn_spectro.setChecked(True)

    def get_V(self, nAver, ch):
        V = 0.0000
        for i in range (nAver):
            V += self.instrument.adcdac.read_adc_voltage(ch,0) #1: read channel in differential mode
        return V/nAver

    def get_Vd(self, nAver, ch):
        V = 0.0000
        for i in range (nAver):
            V += self.instrument.adc.read_voltage(ch)
        return V/nAver

    def continuous_mode(self):
        #former Underway
        self.logTextBox.appendPlainText('Inside continuous_mode...')
        # stop the spectrophotometer update precautionally
        ###self.btn_spectro.setChecked(False)
        
        self.timerSpectra.stop()
        [self.instrument.adjust_LED(n,self.sliders[n].value()) for n in range(3)]
        self.instrument.reset_lines()
        # write (reques) 6 times smth to the device 
        self.instrument.spectrometer.set_scans_average(
                                  self.instrument.specAvScans)
        t = datetime.now()
        self.instrument.timeStamp = t.isoformat('_')
        self.instrument.flnmStr =   t.strftime("%Y%m%d%H%M") 
        self.tsBegin = (t-datetime(1970,1,1)).total_seconds()

        self.logTextBox.appendPlainText('sampling...')
        self.sample()
        self.logTextBox.appendPlainText('done...')

        self.instrument.spectrometer.set_scans_average(1)
        
        nextSample = datetime.fromtimestamp(self.tsBegin + self.instrument.samplingInterval)
        oldText = self.textBox.toPlainText()
        self.textBox.setText(oldText + '\n\nNext pH sample %s' % nextSample.isoformat())
        # TODO:should it be FAlse here??
        self.btn_spectro.setChecked(True) # stop the spectrophotometer update precautionally
        #self.check('Spectrophotometer',True)    
        self.timerSpectra.start()
    
    def sample(self):
        ## SAMPLE SHOULD BE IN A THREAD

        if not fbox['pumping']:
            return
        if self.instrument._autodark:
            now = datetime.now()
            # self.instrument._autodark should be interval 
            if (self.instrument.last_dark is None) or ((now - self.instrument.last_dark) >= self.instrument._autodark):
                self.logTextBox.appendPlainText('New dark required')
                self.on_dark_clicked()
            else:
                self.logTextBox.appendPlainText('next dark at time..x') 
                #%s' % ((self.instrument.last_dark + dt).strftime('%Y-%m%d %H:%S'))

        # take dark on every sample         
        self.on_dark_clicked()       
        self.set_LEDs(True)
        self.btn_leds.setChecked(True)

        self.instrument.evalPar =[]
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans)
        if self.instrument.pumpT > 0: # pump time
            self.instrument.set_line(self.instrument.wpump_slot,True) # start the instrument pump
            self.instrument.set_line(self.instrument.stirrer_slot,True) # start the stirrer
            self.logTextBox.appendPlainText("wait for pumping time")
            self.instrument.wait(self.instrument.pumpT) 
            self.instrument.set_line(self.instrument.stirrer_slot,False) # turn off the pump
            self.instrument.set_line(self.instrument.wpump_slot,False) # turn off the stirrer

        # close the valve
        self.instrument.set_Valve(True)
        self.logTextBox.appendPlainText("wait for instrument waiting time")
        self.instrument.wait(self.instrument.waitT)

        # Take the last measured dark
        dark = self.instrument.spCounts[0]

        self.logTextBox.appendPlainText('Measuring blank...')
        blank = self.instrument.spectrometer.get_corrected_spectra()
        self.instrument.spCounts[1] = blank 
        self.instrument.spCounts_df['blank'] = blank 
        # limit the number by the range 1,16000
        # blank minus dark 
        blank_min_dark= np.clip(self.instrument.spCounts[1] - dark,1,16000)

        # lenght of dA = numbers of cycles (4)
        for pinj in range(self.instrument.ncycles):
            shots = self.instrument.nshots
            # shots= number of dye injection for each cycle ( now 1 for all cycles)
            self.logTextBox.appendPlainText('Injection %d:, shots %d' %(pinj, self.instrument.nshots))
            # turn on the stirrer
            self.instrument.set_line(self.instrument.stirrer_slot, True)
            
            if not self.args.debug:
                # inject dye 
                self.instrument.cycle_line(self.instrument.dyepump_slot, shots)

            self.logTextBox.appendPlainText("wait for mixing time")
            self.instrument.wait(self.instrument.mixT)
            # turn off the stirrer
            self.instrument.set_line(self.instrument.stirrer_slot, False)

            self.logTextBox.appendPlainText("wait before to start the measurment")
            self.instrument.wait(self.instrument.waitT)

            # measure spectrum after injecting nshots of dye 
            postinj = self.instrument.spectrometer.get_corrected_spectra()

            self.instrument.spCounts[2+pinj] = postinj 
            self.instrument.spCounts_df[str(pinj)] = postinj 
            # measuring Voltage for temperature probe
            vNTC = self.get_Vd(3, self.instrument.vNTCch)

            # postinjection minus dark     
            postinj_min_dark = np.clip(postinj - dark,1,16000)
            # self.nlCoeff = [1.0229, -9E-6, 6E-10]
            # coefficient for blank ??? 
            cfb = self.instrument.nlCoeff[0] + self.instrument.nlCoeff[1]*blank_min_dark+ self.instrument.nlCoeff[2] * blank_min_dark**2
            cfp = self.instrument.nlCoeff[0] + self.instrument.nlCoeff[1]*postinj_min_dark + self.instrument.nlCoeff[2] * postinj_min_dark**2
            bmdCorr = blank_min_dark* cfb
            pmdCorr = postinj_min_dark * cfp
            spAbs = np.log10(bmdCorr/pmdCorr)
            sp = np.log10(bmd/postinj_min_dark)            
            # moving average 
            """  spAbsMA = spAbs
                nPoints = 3
                for i in range(3,len(spAbs)-3):
                    v = spAbs[i-nPoints:i+nPoints+1]
                    spAbsMA[i]= np.mean(v)"""

            self.plotAbs.setData(self.instrument.wvls,spAbs)
            Tdeg, pK, e1, e2, e3, Anir,R, dye, pH = self.instrument.calc_pH(spAbs,vNTC)
            
            self.logTextBox.appendPlainText(
                'Tdeg = {:.4f}, pK = {:.4f}, e1= {:.6f}, e2= {:.6f}, e3 = {:.6f}'.format(Tdeg, pK, e1, e2, e3))
            self.logTextBox.appendPlainText(
                'Anir = {:.2f},R = {}, dye = {}, pH = {:.4f}'.format(Anir,R, dye, pH))

        # opening the valve
        self.instrument.set_Valve(False)
        self.instrument.spCounts_df.T.to_csv(
            self.instrument.folderPath + self.instrument.flnmStr + '.spt',
            index = True, header=False)
        # LOg files
        #  
        # 4 full spectrums for all mesaurements 
        '''flnm = open(self.instrument.folderPath + self.instrument.flnmStr +'.spt','w')
        txtData = ''
        for i in range(2+self.instrument.ncycles):
            for j in range (self.instrument.spectrometer.pixels):
                txtData += str(self.instrument.spCounts[i,j]) + ','
            txtData += '\n'
        flnm.write(txtData)    
        flnm.close()'''

        # 4 measurements for each measure *product of spectrums 
        # Write Temp_probe calibration coefficients , ntc cal now, a,b 
        # T_probe_coef_a, T_probe_coef_b 
        flnm = open(self.instrument.folderPath + self.instrument.flnmStr+'.evl','w')
        strFormat = '%.4f,%.4f,%.6f,%.6f,%.6f,%.5f,%.2f,%.5f,%.5f,%.4f,%.2f,%.2f,%.2f\n'
        txtData = ''    
        for i in range(len(self.instrument.evalPar)):
            txtData += strFormat % tuple(self.instrument.evalPar[i])
            pass
        flnm.write(txtData)    
        flnm.close()

        pHeval = self.instrument.pH_eval()
        pH_t, refT, pert, evalAnir = pHeval

        #returns: pH evaluated at reference temperature 
        # (cuvette water temperature), reference temperature, salinity, 
        # estimated dye perturbation

        self.logTextBox.appendPlainText('pH_t = {}, refT = {}, pert = {}, evalAnir = {}'.format(pH_t, refT, pert, evalAnir))
        self.logTextBox.appendPlainText('data saved in %s' % (self.instrument.folderPath +'pH.log'))
        # add boat code 
        # add temperature Calibrated (TRUE or FALSE)
        logfile = os.path.join(self.instrument.folderPath, 'pH.log')
        hdr  = ''
        if not os.path.exists(logfile):
            hdr = 'Time,Lon,Lat,fbT,fbS,pH_t,Tref,pert,Anir'
        s = self.instrument.timeStamp[0:16]
        s+= ',%.6f,%.6f,%.3f,%.3f' % (fbox['longitude'], 
            fbox['latitude'], fbox['temperature'], fbox['salinity'])
        s+= ',%.4f,%.4f,%.3f,%.3f' %pHeval
        s+= '\n'
        with open(logfile,'a') as logFile:
            if hdr:
                logFile.write(hdr + '\n')
            logFile.write(s)
        udp.send_data('PH,' + s)
        self.textBox.setText('pH_t= %.4f, Tref= %.4f, pert= %.3f, Anir= %.1f' %pHeval)
        #self.puckEm.LAST_PAR[1]= pHeval[1]
        #self.puckEm.LAST_pH = pHeval[0]
        
    def _autostart(self):
        self.logTextBox.appendPlainText('Inside _autostart...')
        time.sleep(10)
        # Take dark for the first time 
        self.on_dark_clicked()
        self.sliders[0].setValue(self.instrument.LED1)
        self.sliders[1].setValue(self.instrument.LED2)
        self.sliders[2].setValue(self.instrument.LED3)

        self.btn_spectro.setChecked(True)
        #self.spectro_clicked()
        self.btn_leds.setChecked(True)
        #self.btn_leds_checked()
        self.timerSpectra.start(500)
        if not self.args.debug:
            self.btn_cont_meas.setChecked(True)
            self.btn_cont_meas_clicked()
            #self.on_deploy_clicked(True)
        if self.args.pco2:
            # change to config file 
            self.timerSave.start(self.CO2_instrument.save_pco2_interv * 1.e6) #milliseconds
        return

    def _autostop(self):
        #self.logTextBox.appendPlainText('Inside _autostop...')
        time.sleep(10)
        #TODO: why do we need it 
        self.sliders[0].setValue(0)
        self.sliders[1].setValue(0)
        self.sliders[2].setValue(0) 

        self.btn_spectro.setChecked(False)
        self.btn_leds.setChecked(False)
        self.btn_cont_meas.setChecked(False)
        self.btn_cont_meas_clicked()
        #self.on_deploy_clicked(False)
        self.timerSpectra.stop()
        self.timer_contin_mode.stop()
        #self.timerSensUpd.stop()
        #self.timerSave.stop()
        return

    def autostop_time(self):
        self.logTextBox.appendPlainText('Inside autostop_time...')
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
        self.logTextBox.appendPlainText('Inside _autostart_time...')
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
        self.logTextBox.appendPlainText('Inside _autostart_pump...')
        self.logTextBox.appendPlainText('Automatic start at pump enabled')
        self.textBox.setText('Automatic start at pump enabled')
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
        #self.logTextBox.appendPlainText('Inside autostop_pump...')
        #self.logTextBox.appendPlainText("Ferrybox pump is {}".format(str(fbox['pumping'])))
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
        self.logTextBox.appendPlainText('Inside continuous_mode...')
        # Why do we need this 10 seconds? 
        time.sleep(10)

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

if __name__ == '__main__':

    app = QtGui.QApplication(sys.argv)
    #app.setStyleSheet(" * {font-size: 14 pt} QPushButton:checked{ background-color: #56b8a4 }")
    qss_file = open('styles.qss').read()
    app.setStyleSheet(qss_file)
    myPanel = Panel()
    myPanel.autorun()
    app.exec_()
    udp.UDP_EXIT = True
    udp.server.join()
    if not udp.server.is_alive():
        print ('UDP server closed')
    myPanel.timerSpectra.stop()
    print ('timer is stopped')
    myPanel.timer_contin_mode.stop()

    myPanel.timerSensUpd.stop()
    myPanel.close()
    print ('ended')
    app.quit()
