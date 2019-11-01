#! /usr/bin/python
# Check not used functions
from pHox import *
from pco2 import *
import os,sys
os.chdir('/home/pi/pHox')
os.system('clear')
import warnings
#import usb.core
#import usb
import time
import RPi.GPIO as GPIO

from datetime import datetime, timedelta
import pigpio
from PyQt4 import QtGui, QtCore
import numpy as np
#import random
import pyqtgraph as pg 
import argparse
import socket
import pandas as pd 
# Ferrybox data
import udp
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
        self.instrument = pH_instrument()
        parser = argparse.ArgumentParser()
        parser.add_argument("--debug",
                            action="store_true")
        parser.add_argument("--pco2",
                            action="store_true")

        self.args = parser.parse_args()

        if self.args.pco2:
            self.CO2_instrument = CO2_instrument()

        #self.puckEm = PuckManager()
        self.timerSpectra = QtCore.QTimer()
        self.timer_contin_mode = QtCore.QTimer()
        self.timerSensUpd = QtCore.QTimer()
        self.timerSave = QtCore.QTimer()
        #self.timerFIA = QtCore.QTimer()
        self.timerAuto = QtCore.QTimer()

        self.init_ui()
        self.plotSpc= self.plotwidget1.plot()
        self.plotAbs= self.plotwidget2.plot()
        self.plotAbs_non_corr = self.plotwidget2.plot()

        self.timerSensUpd.start(2000)

    def init_ui(self):

        self.setWindowTitle('NIVA - pH')
        self.timerSpectra.timeout.connect(self.update_spectra)
        self.timer_contin_mode.timeout.connect(self.continuous_mode)
        self.timerSensUpd.timeout.connect(self.update_sensors)
        if self.args.pco2:
            self.timerSave.timeout.connect(self.save_pCO2_data)

        #set grid layout and size columns
        tabs_layout = QtGui.QVBoxLayout()
        self.tabs = QtGui.QTabWidget()
        self.tab1 = QtGui.QWidget()
    	self.tab_manual = QtGui.QWidget()
        self.tab2 = QtGui.QWidget()
        self.tab3 = QtGui.QWidget()

        # Add tabs
        self.tabs.addTab(self.tab1,"Home")
        self.tabs.addTab(self.tab_manual,"Manual mode")
        self.tabs.addTab(self.tab2,"Log")
        self.tabs.addTab(self.tab3,"Config")


        self.tab1.layout = QtGui.QGridLayout()
        self.tab_manual.layout  = QtGui.QGridLayout()
        self.tab2.layout = QtGui.QGridLayout() #.addLayout(grid)
        self.tab3.layout = QtGui.QGridLayout() #.addLayout(grid)

        self.logTextBox = QtGui.QPlainTextEdit()
        self.logTextBox.setReadOnly(True)
        self.logTextBox.appendPlainText('Text message in log')
        if self.args.debug:
            self.logTextBox.appendPlainText('Starting in debug mode')

        self.tab2.layout.addWidget(self.logTextBox) 

        self.group = QtGui.QButtonGroup()
        self.group.setExclusive(False)

        def create_button(name,check):
            Btn = QtGui.QPushButton(name)
            Btn.setObjectName(name)
            if check:
                Btn.setCheckable(True)
            return Btn

        # Define widgets for main tab 
        # Create checkabple buttons
        self.btn_spectro = create_button('Spectrophotometer',True)
        self.btn_leds = create_button('LEDs',True)
        self.btn_valve = create_button('Inlet valve',True)
        self.btn_stirr = create_button('Stirrer',True)
        self.btn_wpump = create_button('Water pump',True)
        self.btn_cont_meas = create_button('Continuous measurements',True)
        # Unchecable buttons
        self.btn_t_dark = create_button('Take dark',False)
        self.btn_sampl_int = create_button( 'Set sampling interval',False)
        self.btn_sigle_meas = create_button('Single measurement',False)
        self.btn_dye_pmp = create_button('Dye pump',False)
   
        self.buttons_ch = [self.btn_spectro,self.btn_leds, self.btn_valve,
                            self.btn_stirr, self.btn_wpump]

        self.buttons_unch = [self.btn_t_dark, self.btn_sampl_int,
                             self.btn_sigle_meas, self.btn_dye_pmp] 

        self.tab1.layout.addWidget(self.btn_cont_meas,0, 0, 1, 2)

        for idx,btn in enumerate(self.buttons_ch):
            self.group.addButton(btn, idx)
            self.tab_manual.layout.addWidget(btn, idx, 1) #row,col

        for idx,btn in enumerate(self.buttons_unch):
            self.group.addButton(btn, idx)
            self.tab_manual.layout.addWidget(btn, idx, 2)

        sldRow = 6
        sldNames = ['Blue','Orange','Red']
        self.sliders = []
        self.sldLabels = []
        for sldInd in range(3):
            self.sliders.append(QtGui.QSlider(QtCore.Qt.Horizontal))
            self.sliders[sldInd].setFocusPolicy(QtCore.Qt.NoFocus)
            self.sliders[sldInd].setTracking(True) # to track changes on sliders
            # otherwise value change is triggere only when you unclick slider 
            self.sldLabels.append(QtGui.QLabel(sldNames[sldInd]))
            self.tab_manual.layout.addWidget(self.sliders[sldInd],sldRow+sldInd,1)
            self.tab_manual.layout.addWidget(self.sldLabels[sldInd],sldRow+sldInd,2)

        self.sliders[0].valueChanged[int].connect(self.sld0_change)
        self.sliders[1].valueChanged[int].connect(self.sld1_change)
        self.sliders[2].valueChanged[int].connect(self.sld2_change)

        self.textBox = QtGui.QTextEdit()
        self.textBox.setOverwriteMode(True)

        self.textBoxSens = QtGui.QTextEdit()
        self.textBoxSens.setOverwriteMode(True)

        self.tab1.layout.addWidget(self.textBox, sldRow+4,0)
        self.tab1.layout.addWidget(self.textBoxSens, sldRow+4,1)

        #create plotwidgets
        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget1.setYRange(0,16000)

        self.plotwidget2 = pg.PlotWidget()
        self.plotwidget2.setYRange(0,1.3)
        self.plotwidget2.setXRange(410,610)
        
        vboxPlot = QtGui.QVBoxLayout()
        vboxPlot.addWidget(self.plotwidget1)
        vboxPlot.addWidget(self.plotwidget2)

        # Define widgets for config tab 
        self.reload_config = create_button('Reload config',False)     
        self.dye_label = QtGui.QLabel('DYE: ')
        self.dye_value = QtGui.QComboBox()
        self.dye_value.addItem('TB')
        self.dye_value.addItem('MCP')        
        index = self.dye_value.findText(self.instrument.dye, 
                                QtCore.Qt.MatchFixedString)
        if index >= 0: 
            self.dye_value.setCurrentIndex(index)

        self.nir_label = QtGui.QLabel('NIR: ')
        self.nir_value = QtGui.QSpinBox()
        self.nir_value.setValue(self.instrument.NIR)

        self.hi_label = QtGui.QLabel('HI-: ')
        self.hi_value = QtGui.QSpinBox()
        self.nir_value.setValue(self.instrument.HI)

        self.i2_label = QtGui.QLabel('I2-: ')
        self.i2_value = QtGui.QSpinBox()

        self.dyecal_label = QtGui.QLabel('DYE calibration: ')
        self.dyecal_value = QtGui.QLabel('to be added')
        
        self.dyev_inj_label = QtGui.QLabel('Dye injection volume: ')
        self.dyev_inj_value = QtGui.QSpinBox()

        self.cuv_v_label = QtGui.QLabel('Cuvette volume: ')
        self.cuv_v_value = QtGui.QSpinBox()

        # print 'calibration coefficients: ', wvlCalCoeff,'\n'
        # print ('Using default BCM lines for PWM LEDs: ',self.pwmLines)
        # print ('0 = will be skipped')
        # print ('NTC calibration coefficients :',self.ntcCalCoef, '\n')
        # print 'Analysis pixels : ', self.wvlPixels


        self.tab3.layout.addWidget(self.reload_config,0,0,1,1)

        self.tab3.layout.addWidget(self.dye_label,1,0,1,1)
        self.tab3.layout.addWidget(self.dye_value,1,1,1,1)

        self.tab3.layout.addWidget(self.nir_label,2,0,1,1)
        self.tab3.layout.addWidget(self.nir_value,2,1,1,1)

        self.tab3.layout.addWidget(self.hi_label,3,0,1,1)
        self.tab3.layout.addWidget(self.hi_value,3,1,1,1)

        self.tab3.layout.addWidget(self.i2_label,4,0,1,1)
        self.tab3.layout.addWidget(self.i2_value,4,1,1,1)

        self.tab3.layout.addWidget(self.dyecal_label,5,0,1,1)
        self.tab3.layout.addWidget(self.dyecal_value,5,1,1,1)

        self.tab3.layout.addWidget(self.dyev_inj_label,6,0,1,1)
        self.tab3.layout.addWidget(self.dyev_inj_value,6,1,1,1)

        self.tab3.layout.addWidget(self.cuv_v_label,7,0,1,1)
        self.tab3.layout.addWidget(self.cuv_v_value,7,1,1,1)

        #self.tab3.layout.addWidget(self.list_config)       


        self.tab1.setLayout(self.tab1.layout)
        self.tab_manual.setLayout(self.tab_manual.layout)
        self.tab2.setLayout(self.tab2.layout)
        self.tab3.setLayout(self.tab3.layout)   

        tabs_layout.addWidget(self.tabs)

        # combine layout for plots and buttons
        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addLayout(vboxPlot)
        hboxPanel.addLayout(tabs_layout)
        self.setLayout(hboxPanel)

        #self.setLayout(self.layout)
        #self.setGeometry(20, 150, 1200, 650)
        self.showMaximized()

        # Define connections Button clicked - Result 
        self.btn_spectro.clicked.connect(self.spectro_clicked)
        self.btn_leds.clicked.connect(self.btn_leds_checked)
        self.btn_valve.clicked.connect(self.btn_valve_clicked)
        self.btn_stirr.clicked.connect(self.btn_stirr_clicked)
        self.btn_wpump.clicked.connect(self.btn_wpump_clicked)
        self.btn_cont_meas.clicked.connect(self.btn_cont_meas_clicked)
        self.reload_config.clicked.connect(self.btn_reload_config_clicked) 

        # Define connections for Unchecable buttons
        self.btn_t_dark.clicked.connect(self.on_dark_clicked)
        self.btn_sampl_int.clicked.connect(self.on_samT_clicked)
        self.btn_sigle_meas.clicked.connect(self.on_sigle_meas_clicked)
        self.btn_dye_pmp.clicked.connect(self.btn_dye_pmp_clicked)

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

        #self.on_deploy_clicked(state)

    '''def on_deploy_clicked(self, state):
        newText =''
        if state:
           self.instrument.flnmStr=''
           self.tsBegin = (datetime.now()-datetime(1970,1,1)).total_seconds()
           nextSample = datetime.fromtimestamp(self.tsBegin + self.instrument.samplingInterval)
           self.timer_contin_mode.start(self.instrument.samplingInterval*1000)
        else:
           self.timer_contin_mode.stop()'''

    def btn_dye_pmp_clicked(self):
        self.instrument.cycle_line(self.instrument.dyepump_slot,3)

    def btn_valve_clicked(self):
        self.instrument.set_Valve(self.btn_valve.isChecked())

    def spectro_clicked(self):
        if self.btn_spectro.isChecked():
            self.timerSpectra.start(500)
        else:
            self.timerSpectra.stop()

    def sld0_change(self,DC): 
        #get the value from the connect method
        self.instrument.adjust_LED(0,DC)
        self.btn_leds.setChecked(True)

    def sld1_change(self,DC): 
        #get the value from the connect method
        self.instrument.adjust_LED(1,DC)
        self.btn_leds.setChecked(True)

    def sld2_change(self,DC): 
        #get the value from the connect method
        self.instrument.adjust_LED(2,DC)
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
            # state is 1 or 0 
           self.instrument.adjust_LED(i, state*self.sliders[i].value())
        self.logTextBox.appendPlainText('Leds {}'.format(str(state)))

    def btn_leds_checked(self):
        state = self.btn_leds.isChecked()
        self.set_LEDs(state)

    def on_selFolderBtn_released(self):
        self.folderDialog = QtGui.QFileDialog()
        folder = self.folderDialog.getExistingDirectory(self,'Select directory')
        self.instrument.folderPath = folder+'/'

    def on_samT_clicked(self): 
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
        logf = os.path.join(self.instrument.folderPath, 'pCO2.log')
        hdr  = ''
        if not os.path.exists(logf):
            hdr = 'Time,Lon,Lat,fbT,fbS,Tw,Flow,Pw,Ta,Pa,Leak,CO2,TCO2'
        s = labelSample
        s+= ',%.6f,%.6f,%.3f,%.3f' % (fbox['longitude'], fbox['latitude'], 
                fbox['temperature'], fbox['salinity'])
        s+= ',%.2f,%.1f,%.1f,%.2f,%d,%.1f,%d' %(d[0],d[1],d[2],d[3],d[4],d[6],d[7])
        s+= '\n'
        with open(logf,'a') as logFile:
            if hdr:
                logFile.write(hdr + '\n')
            logFile.write(s)
        udp.send_data('PCO2,' + s)
        return
        

    def on_intTime_clicked(self):
        # Not used now
        intTime, ok = QtGui.QInputDialog.getInt(
            None, 'Set spectrophotometer integration time',
             'ms',self.instrument.specIntTime,100,3000,100)
        if ok:
            self.instrument.specIntTime = intTime
            self.instrument.spectrometer.set_integration_time(intTime)
            self.btn_spectro.setText('Spectrophotometer {} ms'.format(str(intTime)))
            #self.chkBox_caption('Spectrophotometer','%d ms' %intTime)
        
    def on_scans_clicked(self): 
        # Not used now
        scans, ok = QtGui.QInputDialog.getInt(None, 'Set spectrophotometer averaging scans','',self.instrument.specAvScans,1,20,1)
        if ok:
            self.instrument.specAvScans = scans

    def on_autoAdjust_clicked(self):
        # Not used now
        DC1,DC2, sptIt, Ok  = self.instrument.auto_adjust()
        self.sliders[0].setValue(DC1)
        self.sliders[1].setValue(DC2)
        self.instrument.specIntTime = sptIt
        self.instrument.specAvScans = 3000/sptIt

    def refresh_settings(self):
        settings = ('Settings:\nSpectrophotometer integration time : %d ms\nSpectrophotometer averaging scans : %d\nPumping time : %d\nWaiting time before scans : %d\nMixing time : %d\nDye addition sequence : %s\nSampling interval : %d\nData folder : %s' % (
                    self.instrument.specIntTime, self.instrument.specAvScans,self.instrument.pumpT, self.instrument.waitT, self.instrument.mixT, self.instrument.dyeAdditions, 
                    self.instrument.samplingInterval, self.instrument.folderPath))
        self.textBox.setText(settings)

    def update_sensors(self):
        vNTC = self.get_Vd(3, self.instrument.vNTCch)
        Tntc = 0
        Tntc = (self.instrument.ntcCalCoef[0]*vNTC) +self.instrument.ntcCalCoef[1]
        #for i in range(2):
            #Tntc += self.instrument.ntcCalCoef[i] * pow(vNTC,i)
            
           #Tntc = vNTC*(23.1/0.4173)
        text = 'Cuvette temperature \xB0C: %.4f  (%.4f V)\n' %(Tntc,vNTC)
        fmt  = 'FBPumping={:-d}\nFBTemperature={:-.2f}\nFBSalinity={:-.2f}\n'
        fmt += 'FBLongitude={:-.4f}\nFBLatitude={:-.4f}\n'
        text += fmt.format(fbox['pumping'], 
                           fbox['temperature'], 
                           fbox['salinity'],
                           fbox['longitude'], 
                           fbox['latitude'])
        LED1 = self.sliders[0].value()
        LED2 = self.sliders[1].value()
        LED3 = self.sliders[2].value()
        text += 'LED1 = %-d\nLED2 = %-d\nLED3 = %-d\n' % (LED1, LED2, LED3) 
        self.textBoxSens.setText(text)

        if self.args.pco2:
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


               
    def on_sigle_meas_clicked(self):
        # Button "single" is clicked
        self.btn_spectro.setChecked(False)
        #self.check('Spectrophotometer',False)
        self.timerSpectra.stop()
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
    
    def sample(self): #parString pT, mT, wT, dA
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
                
        self.set_LEDs(True)
        self.btn_leds.setChecked(True)

        self.instrument.evalPar =[]
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans)
        if self.instrument.pT > 0: # pump time
            self.instrument.set_line(self.instrument.wpump_slot,True) # start the instrument pump
            self.instrument.set_line(self.instrument.stirrer_slot,True) # start the stirrer
            self.logTextBox.appendPlainText("wait for pumping time")
            self.instrument.wait(self.instrument.pT) 
            self.instrument.set_line(self.instrument.stirrer_slot,False) # turn off the pump
            self.instrument.set_line(self.instrument.wpump_slot,False) # turn off the stirrer

        # close the valve
        self.instrument.set_Valve(True)
        self.logTextBox.appendPlainText("wait for instrument waiting time")
        self.instrument.wait(self.instrument.wT)

        # Take the last measured dark
        dark = self.instrument.spCounts[0]

        self.logTextBox.appendPlainText('Measuring blank...')
        blank = self.instrument.spectrometer.get_corrected_spectra()
        self.instrument.spCounts[1] = blank  #self.instrument.spectrometer.get_corrected_spectra()
        self.instrument.spCounts_df['blank'] = blank  #self.instrument.spectrometer.get_corrected_spectra()
        # limit the number by the range 1,16000
        # blank minus dark 
        bmd = np.clip(self.instrument.spCounts[1] - dark,1,16000)

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
            self.instrument.wait(self.instrument.mT)
            # turn off the stirrer
            self.instrument.set_line(self.instrument.stirrer_slot, False)

            self.logTextBox.appendPlainText("wait before to start the measurment")
            self.instrument.wait(self.instrument.wT)

            # measure spectrum after injecting nshots of dye 
            postinj = self.instrument.spectrometer.get_corrected_spectra()

            self.instrument.spCounts[2+pinj] = postinj 
            self.instrument.spCounts_df[str(pinj)] = postinj 
            # measuring Voltage for temperature probe
            vNTC = self.get_Vd(3, self.instrument.vNTCch)

            # postinjection minus dark     
            pmd = np.clip(postinj - dark,1,16000)
            # self.nlCoeff = [1.0229, -9E-6, 6E-10]
            # coefficient for blank ??? 
            cfb = self.instrument.nlCoeff[0] + self.instrument.nlCoeff[1]*bmd + self.instrument.nlCoeff[2] * bmd**2
            cfp = self.instrument.nlCoeff[0] + self.instrument.nlCoeff[1]*pmd + self.instrument.nlCoeff[2] * pmd**2
            bmdCorr = bmd * cfb
            pmdCorr = pmd * cfp
            spAbs = np.log10(bmdCorr/pmdCorr)
            sp = np.log10(bmd/pmd)            
            # moving average 
            """  spAbsMA = spAbs
                nPoints = 3
                for i in range(3,len(spAbs)-3):
                    v = spAbs[i-nPoints:i+nPoints+1]
                    spAbsMA[i]= np.mean(v)"""

            self.plotAbs.setData(self.instrument.wvls,spAbs)
            Tdeg, pK, e1, e2, e3, Anir,R, dye, pH = self.instrument.calc_pH(spAbs,vNTC)
            
            self.logTextBox.appendPlainText(
                'Tdeg = {.4f}, pK = {.4f}, e1= {.6f}, e2= {.6f}, e3 = {.6f}'.format(Tdeg, pK, e1, e2, e3))
            self.logTextBox.appendPlainText(
                'Anir = {.2f},R = {}, dye = {}, pH = {.4f}'.format(Anir,R, dye, pH))

        # opening the valve
        self.instrument.set_Valve(False)
        self.instrument.spCounts_df.T.to_csv('spcounts.spt',index = True, header=False)
        # LOg files 
        # 4 full spectrums for all mesaurements 
        flnm = open(self.instrument.folderPath + self.instrument.flnmStr +'.spt','w')
        txtData = ''
        # spcoounts is np.array  np.zeros((6,1024))
        for i in range(2+self.instrument.ncycles):
            for j in range (self.instrument.spectrometer.pixels):
                txtData += str(self.instrument.spCounts[i,j]) + ','
            txtData += '\n'
        flnm.write(txtData)    
        flnm.close()

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
        # add temperature Caliblrated (TRUE or FALSE)
        logf = os.path.join(self.instrument.folderPath, 'pH.log')
        hdr  = ''
        if not os.path.exists(logf):
            hdr = 'Time,Lon,Lat,fbT,fbS,pH_t,Tref,pert,Anir'
        s = self.instrument.timeStamp[0:16]
        s+= ',%.6f,%.6f,%.3f,%.3f' % (fbox['longitude'], 
            fbox['latitude'], fbox['temperature'], fbox['salinity'])
        s+= ',%.4f,%.4f,%.3f,%.3f' %pHeval
        s+= '\n'
        with open(logf,'a') as logFile:
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
    myPanel = Panel()
    myPanel.autorun()
    app.exec_()
    print ('ending')
    udp.UDP_EXIT = True
    udp.server.join()
    if not udp.server.is_alive():
        print 'UDP server closed'
    myPanel.timerSpectra.stop()
    print ('timer is stopped')
    myPanel.timer_contin_mode.stop()

    myPanel.timerSensUpd.stop()
    myPanel.close()

    print ('ended')
    app.quit()
