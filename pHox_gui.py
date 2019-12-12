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

class Sample_thread(QtCore.QThread):
    def __init__(self,mainclass):
        self.mainclass = mainclass
        super(Sample_thread, self).__init__(mainclass)

    def run(self):
        self.mainclass.sample()

class Panel(QtGui.QWidget):
    def __init__(self,parent):
        super(QtGui.QWidget, self).__init__(parent)
        #super(Panel, self).__init__()

        parser = argparse.ArgumentParser()
        parser.add_argument("--debug",
                            action="store_true")
        parser.add_argument("--pco2",
                            action="store_true")

        self.args = parser.parse_args()
        self.create_timers()
        self.instrument = pH_instrument()

        self.wvls = self.instrument.calc_wavelengths(self.instrument.spectrometer.wvlCalCoeff)
        self.spCounts_df = pd.DataFrame(columns=['Wavelengths','dark','blank'])
        self.spCounts_df['Wavelengths'] = ["%.2f" % w for w in self.wvls]  

        print ('instrument created')
        if self.args.pco2:
            self.CO2_instrument = CO2_instrument()

        self.init_ui()

    def init_ui(self):

        self.tabs = QtGui.QTabWidget()

        self.tab1 =        QtGui.QWidget()
        self.tab_progress =    QtGui.QWidget()        
        self.tab_manual =  QtGui.QWidget()
        self.tab_log =     QtGui.QWidget()
        self.tab_config =  QtGui.QWidget()
        self.tab_calibr =  QtGui.QWidget()

        # Add tabs
        self.tabs.addTab(self.tab1,       "Home")
        self.tabs.addTab(self.tab_progress, "Progress")          
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
        self.make_tab_progress()        
        self.make_tab_config()
        self.make_plotwidgets()

        # combine layout for plots and buttons
        hboxPanel = QtGui.QHBoxLayout()
        hboxPanel.addWidget(self.plotwdigets_groupbox)    
        hboxPanel.addWidget(self.tabs)
    
        self.setLayout(hboxPanel)
        #self.showMaximized()

    def create_timers(self):
        self.timerSpectra_plot = QtCore.QTimer()
        self.timer_contin_mode = QtCore.QTimer()
        self.timerSensUpd = QtCore.QTimer()
        self.timerSave = QtCore.QTimer()
        self.timerAuto = QtCore.QTimer()
        self.timerSpectra_plot.timeout.connect(self.update_spectra_plot)
        self.timer_contin_mode.timeout.connect(self.continuous_mode_timer_finished)
        self.timerSensUpd.timeout.connect(self.update_sensors_info)
        if self.args.pco2:
            self.timerSave.timeout.connect(self.save_pCO2_data)

    def make_plotwidgets(self):
        #create plotwidgets
        self.plotwdigets_groupbox = QtGui.QGroupBox()

        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget1.setYRange(1000,16200)
        self.plotwidget1.setBackground('#19232D')
        self.plotwidget1.showGrid(x=True, y=True)

        self.plotwidget2 = pg.PlotWidget()
        self.plotwidget2.setYRange(0,1.3)
        self.plotwidget2.setXRange(410,610)
        self.plotwidget2.showGrid(x=True, y=True)
        self.plotwidget2.setBackground('#19232D')     

        vboxPlot = QtGui.QVBoxLayout()
        vboxPlot.addWidget(self.plotwidget1)
        vboxPlot.addWidget(self.plotwidget2)
        self.plotwidget1.addLine(x=None, y=self.instrument.THR, pen=pg.mkPen('w', width=1, style=QtCore.Qt.DotLine))
        self.plotwidget1.addLine(x=self.instrument.HI, y=None, pen=pg.mkPen('b', width=1, style=QtCore.Qt.DotLine))        
        self.plotwidget1.addLine(x=self.instrument.I2, y=None, pen=pg.mkPen('#eb8934', width=1, style=QtCore.Qt.DotLine))   
        self.plotwidget1.addLine(x=self.instrument.NIR, y=None, pen=pg.mkPen('r', width=1, style=QtCore.Qt.DotLine))

        self.plotSpc= self.plotwidget1.plot()
        self.plotAbs= self.plotwidget2.plot()

        self.plotwdigets_groupbox.setLayout(vboxPlot)

    def make_tab_progress(self):

        self.sample_steps_groupBox = QtWidgets.QGroupBox("Measuring Progress")

        self.sample_steps = [  
                        QtWidgets.QCheckBox('0. Start new sample'),
                        QtWidgets.QCheckBox('1. step'),
                        QtWidgets.QCheckBox('2  step?'),

                        QtWidgets.QCheckBox('3. step'), 
                        QtWidgets.QCheckBox('4. step'),                        
                        QtWidgets.QCheckBox('5. step'),

                        QtWidgets.QCheckBox("6. step"),
                        QtWidgets.QCheckBox("7. step"),
                        QtWidgets.QCheckBox("8. step")
                        ]

        ###self.calibr_timer = QLineEdit()
        ####self.calibr_timer.setText('Next calibration after N samples')
        
        layout = QtGui.QGridLayout() 
        
        self.tab_progress.layout = QtGui.QGridLayout()

        [step.setEnabled (False) for step in self.sample_steps]      
        [layout.addWidget(step) for step in self.sample_steps]

        self.sample_steps_groupBox.setLayout(layout)
        self.tab_progress.layout.addWidget(self.sample_steps_groupBox)
        self.tab_progress.setLayout(self.tab_progress.layout)
        
        #self.tab3.layout.addWidget(self.calibr_progressbars_groupBox,0,0,1,1)  

    def make_tab1(self):
        self.tab1.layout = QtGui.QGridLayout()
        self.textBox = QtGui.QTextEdit()
        self.textBox.setOverwriteMode(True)

        self.nextSampleBox = QtGui.QLineEdit()

        self.textBoxSens = QtGui.QTextEdit()
        self.textBoxSens.setOverwriteMode(True)
        self.textBox.setText('Loading...')

        if self.args.debug:
            self.logTextBox.appendPlainText('Starting in debug mode')
        #self.tab_log.layout.addWidget(self.logTextBox) 

        self.btn_cont_meas = self.create_button('Continuous measurements',True)
        self.btn_single_meas = self.create_button('Single measurement',False)   
        self.btn_single_meas.clicked.connect(self.btn_single_meas_clicked)        
        self.btn_cont_meas.clicked.connect(self.btn_cont_meas_clicked)

        self.tab1.layout.addWidget(self.btn_cont_meas,0, 0, 1, 1)
        self.tab1.layout.addWidget(self.btn_single_meas, 0, 1)
        self.tab1.layout.addWidget(self.nextSampleBox,  1, 0, 1, 2)     
        self.tab1.layout.addWidget(self.textBox,      2, 0, 1, 2)
        self.tab1.layout.addWidget(self.textBoxSens,  3, 0, 1, 2)
 
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
            
        self.dye_combo.currentIndexChanged.connect(self.dye_combo_chngd)
        
        self.tableWidget = QtGui.QTableWidget()

        self.tableWidget.setRowCount(7)
        self.tableWidget.setColumnCount(2)

        self.fill_table(0,0,'DYE type')
        self.tableWidget.setCellWidget(0,1,self.dye_combo)

        self.fill_table(1,0,'NIR:')
        self.fill_table(1,1,str(self.instrument.NIR))

        self.fill_table(2,0,'HI-')
        self.fill_table(2,1,str(self.instrument.HI))

        self.fill_table(3,0,'I2-')
        self.fill_table(3,1, str(self.instrument.I2))

        self.fill_table(4,0,'Last calibration:')
        self.fill_table(4,1,' not used yet:')        

        self.fill_table(5,0,'pH sampling interval (min)')


        self.fill_table(6,0,'Spectroph intergration time')
        self.fill_table(6,1,str(self.instrument.specIntTime))

        self.samplingInt_combo = QtGui.QComboBox()
        self.samplingInt_combo.addItem('5')
        self.samplingInt_combo.addItem('10')       
        self.tableWidget.setCellWidget(5,1,self.samplingInt_combo)

        index = self.samplingInt_combo.findText(str(self.instrument.samplingInterval), 
                                QtCore.Qt.MatchFixedString)
        if index >= 0: 
            self.samplingInt_combo.setCurrentIndex(index)

        self.samplingInt_combo.currentIndexChanged.connect(self.sampling_int_chngd)
            
        self.tableWidget.horizontalHeader().setStretchLastSection(True)

        self.tab_config.layout.addWidget(self.reload_config,0,0,1,1)   
        self.tab_config.layout.addWidget(self.tableWidget,1,0,1,1)

        self.tab_config.setLayout(self.tab_config.layout)  

    def sampling_int_chngd(self,ind):
        print ('value chaged',ind)
        minutes = int(self.samplingInt_combo.currentText())
        self.instrument.samplingInterval = int(minutes)*60

    def make_btngroupbox(self):
        # Define widgets for main tab 
        # Create checkabple buttons
        self.buttons_groupBox = QtGui.QGroupBox("Buttons GroupBox")
        btn_grid = QtGui.QGridLayout()

        self.btn_adjust_leds = self.create_button('Adjust Leds',True) 
        self.btn_t_dark = self.create_button('Take dark',False)
        self.btn_leds = self.create_button('LEDs',True)
        self.btn_valve = self.create_button('Inlet valve',True)   
        self.btn_stirr = self.create_button('Stirrer',True)
        self.btn_dye_pmp = self.create_button('Dye pump',False)        
        self.btn_wpump = self.create_button('Water pump',True)


        btn_grid.addWidget(self.btn_dye_pmp, 0, 0)

        btn_grid.addWidget(self.btn_adjust_leds,1,0)
        btn_grid.addWidget(self.btn_leds,    1, 1)

        btn_grid.addWidget(self.btn_valve, 2, 0)
        btn_grid.addWidget(self.btn_stirr, 2, 1)

        btn_grid.addWidget(self.btn_wpump, 4, 0)
        btn_grid.addWidget(self.btn_t_dark , 4, 1)

        # Define connections Button clicked - Result 
        self.btn_leds.clicked.connect(self.btn_leds_checked)
        self.btn_valve.clicked.connect(self.btn_valve_clicked)
        self.btn_stirr.clicked.connect(self.btn_stirr_clicked)
        self.btn_wpump.clicked.connect(self.btn_wpump_clicked)
        self.btn_adjust_leds.clicked.connect(self.on_autoAdjust_clicked)
        self.btn_t_dark.clicked.connect(self.on_dark_clicked)
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
        self.update_LEDs()
        self.set_LEDs(state)

    def btn_stirr_clicked(self):
        self.instrument.set_line(self.instrument.stirrer_slot,
        self.btn_stirr.isChecked())

    def btn_wpump_clicked(self):
        self.instrument.set_line(self.instrument.wpump_slot,
        self.btn_wpump.isChecked())

    def btn_dye_pmp_clicked(self):
        self.instrument.cycle_line(self.instrument.dyepump_slot,3)

    def btn_valve_clicked(self):
        self.instrument.set_Valve(self.btn_valve.isChecked())

    def load_config_file(self):
        with open('config.json') as json_file:
            j = json.load(json_file)
            default =   j['default']
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
        self.logTextBox.appendPlainText('Measuring dark...')
        self.set_LEDs(False)
        self.btn_leds.setChecked(False)
        print ('self.instrument.specAvScans',self.instrument.specAvScans)
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans) 
        self.spCounts_df['dark'] = self.instrument.spectrometer.get_corrected_spectra()        
        self.instrument.spectrometer.set_scans_average(1)

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

    def update_spectra_plot(self):
        datay = self.instrument.spectrometer.get_corrected_spectra()
        self.plotSpc.setData(self.wvls,datay)                  

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

    def plot_sp_levels(self):
        pixelLevel_0, _ = self.instrument.get_sp_levels(self.instrument.wvlPixels[0])
        pixelLevel_1, _ = self.instrument.get_sp_levels(self.instrument.wvlPixels[1])
        pixelLevel_2, _ = self.instrument.get_sp_levels(self.instrument.wvlPixels[2])   
        self.plotwidget1.plot(
        [self.instrument.HI,self.instrument.I2,self.instrument.NIR],
        [pixelLevel_0,pixelLevel_1,pixelLevel_2], pen=None, symbol='+') 

    def on_autoAdjust_clicked(self):
        #
        self.logTextBox.appendPlainText('on_autoAdjust_clicked')
        DC1,DC2,DC3,sptIt,result  = self.instrument.auto_adjust()
        print (DC1,DC2,DC3)
        if result:
            self.sliders[0].setValue(DC1)
            self.sliders[1].setValue(DC2)
            self.sliders[2].setValue(DC3)

            #self.plot_sp_levels()
            self.instrument.specIntTime = sptIt
            self.tableWidget.setItem(6,1,QtGui.QTableWidgetItem(str(self.instrument.specIntTime)))  
            self.instrument.specAvScans = 3000/sptIt
        else:
            pass
            #self.textBox.setText('Could not adjust leds')
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

    def get_next_sample(self):
        t = datetime.now()
        self.instrument.timeStamp  = t.isoformat('_')
        tsBegin = (t-datetime(1970,1,1)).total_seconds()
        nextSamplename = datetime.fromtimestamp(tsBegin + self.instrument.samplingInterval)
        return str(nextSamplename.strftime("%H:%M"))    

    def get_filename(self):
        t = datetime.now()
        self.instrument.timeStamp  = t.isoformat('_')
        self.instrument.flnmStr =  datetime.now().strftime("%Y%m%d%H%M") 
        return

    def btn_cont_meas_clicked(self):
        state = self.btn_cont_meas.isChecked()
        if state:
            nextSamplename = self.get_next_sample()
            self.nextSampleBox.setText("Next sample at {}".format(nextSamplename))
            self.timer_contin_mode.start(self.instrument.samplingInterval*1000)
        else:
            self.nextSampleBox.clear()            
            self.timer_contin_mode.stop()

    def btn_single_meas_clicked(self):
        #self.timerSpectra_plot.stop()
        self.get_filename()

        # dialog sample name  
        text, ok = QtGui.QInputDialog.getText(None, 'Sample name', 
                                        self.instrument.flnmStr)
        if ok:
            if text != '':
                self.instrument.flnmStr = text
            self.instrument.reset_lines()
            self.sample_thread = Sample_thread(self)
            self.sample_thread.start()
            self.thread.finished.connect(self.sample_finished)
            #self.sample()

    def sample_finished(self):
        self.nextSampleBox.clear()  

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

    def continuous_mode_timer_finished(self):
        self.logTextBox.appendPlainText('Inside continuous_mode...')
        #self.timerSpectra_plot.stop()
        self.instrument.reset_lines()

        #self.sample()
        self.sample_thread = Sample_thread(self)
        self.sample_thread.start()
        #
        self.sample_thread.finished.connect(self.sample_finished)



    
    def update_LEDs(self):
        self.sliders[0].setValue(self.instrument.LED1)
        self.sliders[1].setValue(self.instrument.LED2)
        self.sliders[2].setValue(self.instrument.LED3)

    def _autostart(self):
        self.logTextBox.appendPlainText('Inside _autostart...')
        self.textBox.setText('Inside _autostart...')
        self.timerSpectra_plot.start()
        # Take dark for the first time 
        self.textBox.setText('Taking dark...')
        self.on_dark_clicked()
        self.update_LEDs()

        ##self.btn_spectro.setChecked(True)
        #self.spectro_clicked()
        # turn on leds 
        self.btn_leds.setChecked(True)
        self.timerSpectra_plot.start(500)

        if not self.args.debug:
            self.btn_cont_meas.setChecked(True)
            self.btn_cont_meas_clicked()
            self.textBox.setText('The instrument is ready for use')
            #self.on_deploy_clicked(True)
        if self.args.pco2:
            # change to config file 
            self.timerSave.start(self.CO2_instrument.save_pco2_interv * 1.e6) #milliseconds
        return

    def _autostop(self):
        #self.logTextBox.appendPlainText('Inside _autostop...')
        time.sleep(10)
        self.timerSpectra_plot.stop()
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

    def sample(self):   

        self.sample_steps[0].setChecked(True)
        
        print ('Start sample')
        #self.textBox.setText('Start sample')
        self.logTextBox.appendPlainText('Start sample')
        ## SAMPLE SHOULD BE IN A THREAD

        if not fbox['pumping']:
            return
        if self.instrument._autodark:
            now = datetime.now()
            # self.instrument._autodark should be interval 
            if (self.instrument.last_dark is None) or (
                (now - self.instrument.last_dark) >= self.instrument._autodark):
                self.logTextBox.appendPlainText('New dark required')
                self.on_dark_clicked()
            else:
                self.logTextBox.appendPlainText('next dark at time..x') 
                #%s' % ((self.instrument.last_dark + dt).strftime('%Y-%m%d %H:%S'))

        # take dark on every sample
        print ('dark')        
        self.on_dark_clicked() 
        self.on_autoAdjust_clicked()      
        self.set_LEDs(True)
        self.btn_leds.setChecked(True)

        self.instrument.evalPar =[]
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans)
        if self.instrument.pumpTime > 0: # pump time
            self.instrument.set_line(self.instrument.wpump_slot,True) # start the instrument pump
            self.instrument.set_line(self.instrument.stirrer_slot,True) # start the stirrer
            #self.logTextBox.appendPlainText("Pumping")
            #self.textBox.setText('Pumping')
            time.sleep(self.instrument.pumpTime)
            #self.instrument.wait(self.instrument.pumpTime) 
            self.instrument.set_line(self.instrument.stirrer_slot,False) # turn off the pump
            self.instrument.set_line(self.instrument.wpump_slot,False) # turn off the stirrer

        # close the valve
        print ('valve')
        self.instrument.set_Valve(True)
        #self.logTextBox.appendPlainText("Waiting...")
        #self.textBox.setText("Waiting...")
        time.sleep(self.instrument.waitT)
        #self.instrument.wait()

        # Take the last measured dark
        dark = self.spCounts_df['dark']

        #self.logTextBox.appendPlainText('Measuring blank...')
        #self.textBox.setText('Measuring blank...')
        
        blank = self.instrument.spectrometer.get_corrected_spectra()
        
        blank_min_dark= np.clip(blank - dark,1,16000)
        self.spCounts_df['blank'] = blank 

        #self.logTextBox.appendPlainText(' ')
        #self.logTextBox.appendPlainText(
        #    'Start new cycle of {} measurements'.format( self.instrument.nshots))
        for pinj in range(self.instrument.ncycles):
            shots = self.instrument.nshots
            # shots= number of dye injection for each cycle ( now 1 for all cycles)
            print ('Injection %d:' %(pinj+1))
            #self.logTextBox.appendPlainText('Injection %d:' %(pinj+1))
            #self.textBox.setText('Injection %d:' %(pinj+1))
            # turn on the stirrer                 
            self.instrument.set_line(self.instrument.stirrer_slot, True)

            if not self.args.debug:
                # inject dye 
                self.instrument.cycle_line(self.instrument.dyepump_slot, shots)

            self.logTextBox.appendPlainText("Mixing")
            time.sleep(self.instrument.mixT)
            #self.instrument.wait(self.instrument.mixT)
            # turn off the stirrer
            self.instrument.set_line(self.instrument.stirrer_slot, False)

            #self.logTextBox.appendPlainText("wait before starting the measurment")
            time.sleep(self.instrument.waitT)
            #self.instrument.wait(self.instrument.waitT)

            # measure spectrum after injecting nshots of dye 
            postinj = self.instrument.spectrometer.get_corrected_spectra()

            # measuring Voltage for temperature probe
            vNTC = self.get_Vd(3, self.instrument.vNTCch)

            # Write spectrum to the file 
            self.spCounts_df[str(pinj)] = postinj 

            # postinjection minus dark     
            postinj_min_dark = np.clip(postinj - dark,1,16000)
            print ('postinj_min_dark')
            # coefficient for blank ??? 
            cfb = (self.instrument.nlCoeff[0] + 
                    self.instrument.nlCoeff[1] * blank_min_dark + 
                    self.instrument.nlCoeff[2] * blank_min_dark**2)

            cfp = (self.instrument.nlCoeff[0] +
                    self.instrument.nlCoeff[1] * postinj_min_dark + 
                    self.instrument.nlCoeff[2] * postinj_min_dark**2)

            bmdCorr = blank_min_dark * cfb
            pmdCorr = postinj_min_dark * cfp
            spAbs = np.log10(bmdCorr/pmdCorr)
            sp = np.log10(blank_min_dark/postinj_min_dark)            
            # moving average 
            """  spAbsMA = spAbs
                nPoints = 3
                for i in range(3,len(spAbs)-3):
                    v = spAbs[i-nPoints:i+nPoints+1]
                    spAbsMA[i]= np.mean(v)"""

            self.plotAbs.setData(self.wvls,spAbs)
            Tdeg, pK, e1, e2, e3, Anir,R, dye, pH = self.instrument.calc_pH(spAbs,vNTC,pinj)
            
            '''self.logTextBox.appendPlainText(
                'Tdeg = {:.4f}, pK = {:.4f}, e1= {:.6f}, e2= {:.6f}, e3 = {:.6f}'.format(Tdeg, pK, e1, e2, e3))
            self.logTextBox.appendPlainText(
                'Anir = {:.2f},R = {}, dye = {}, pH = {:.4f}'.format(Anir,R, dye, pH))'''

        # opening the valve
        self.instrument.set_Valve(False)
        print ('create sptfile ')
        time.sleep(2)
        self.spCounts_df.T.to_csv(
            self.instrument.folderPath + self.instrument.flnmStr + '.spt',
            index = True, header=False)

        # 4 measurements for each measure *product of spectrums 
        # Write Temp_probe calibration coefficients , ntc cal now, a,b 
        # T_probe_coef_a, T_probe_coef_b 
        print ('evl file save')
        flnm = open(self.instrument.folderPath + self.instrument.flnmStr+'.evl','w')
        strFormat = '%.4f,%.4f,%.6f,%.6f,%.6f,%.5f,%.2f,%.5f,%.5f,%.4f,%.2f,%.2f,%.2f\n'
        txtData = ''    
        for i in range(len(self.instrument.evalPar)):
            txtData += strFormat % tuple(self.instrument.evalPar[i])
            pass
        flnm.write(txtData)    
        flnm.close()
        
        #matrix with 4 samples pH eval averages something, produces final value
        pHeval = self.instrument.pH_eval()  
        pH_t, refT, pert, evalAnir = pHeval

        #returns: pH evaluated at reference temperature 
        # (cuvette water temperature), reference temperature, salinity, 
        # estimated dye perturbation

        ########self.logTextBox.appendPlainText('pH_t = {}, refT = {}, pert = {}, evalAnir = {}'.format(pH_t, refT, pert, evalAnir))




        print ('log')
        self.logTextBox.appendPlainText('data saved in %s' % (self.instrument.folderPath +'pH.log'))

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
        print ('udp')
        udp.send_data('PH,' + s)

        #self.textBox.setText('pH_t= %.4f, \nTref= %.4f, \npert= %.3f, \nAnir= %.1f' %pHeval)
        self.instrument.spectrometer.set_scans_average(1)        
        self.logTextBox.appendPlainText('Single measurement is done...')

class boxUI(QtGui.QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        self.setWindowTitle('NIVA - pH')

        self.main_widget = Panel(self)
        self.setCentralWidget(self.main_widget)
        self.showMaximized()        
        self.main_widget.autorun()

if __name__ == '__main__':

    app = QtGui.QApplication(sys.argv)
    qss_file = open('styles.qss').read()
    app.setStyleSheet(qss_file)
    ui  = boxUI()
    app.exec_()

    #udp.UDP_EXIT = True
    #udp.server.join()
    #if not udp.server.is_alive():
    #    print ('UDP server closed')

    '''self.main_widget.timerSpectra_plot.stop()
    print ('timer is stopped')
    self.main_widget.timer_contin_mode.stop()
    self.main_widget.timerSensUpd.stop()
    self.main_widget.close()
    print ('ended')'''
#app.quit()
