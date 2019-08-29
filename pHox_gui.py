#! /usr/bin/python

# Check not used functions
from pHox import *
import json
import socket
import threading
import os,sys
os.chdir('/home/pi/pHox')
os.system('clear')
import warnings
import usb.core
import usb
import serial
import serial.tools.list_ports
import struct
import time
import RPi.GPIO as GPIO
from ADCDACPi import ADCDACPi
from ADCDifferentialPi import ADCDifferentialPi
#from helpers import ABEHelpers
from datetime import datetime, timedelta
import pigpio
from PyQt4 import QtGui, QtCore
import numpy as np
from numpy import *
import random
import pyqtgraph as pg 


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

'''class inputDialog(QtGui.QDialog):
    # Panel Constructor #
    # Dialog window for settings 
    def __init__(self, parent=None, title='user input', parString='30_5_3_1111'):
        QtGui.QWidget.__init__(self, parent)
        layout = QtGui.QFormLayout()
        self.line = QtGui.QLineEdit(parString)
        # in input mask blanks are _ 9 is ascii 
        self.line.setInputMask('99_9_9_9999')
        self.line.returnPressed.connect(self.check_parameters)
        layout.addRow(self.line)
        self.setLayout(layout)
        self.setWindowTitle(title)
        
    def check_parameters(self):
        self.parString= '%s' %self.line.text()'''
        
class Panel(QtGui.QWidget):
    def __init__(self):
        super(Panel, self).__init__()
        self.instrument = Cbon()
        #self.puckEm = PuckManager()
        self.timer = QtCore.QTimer()
        self.timerUnderway = QtCore.QTimer()
        self.timerSens = QtCore.QTimer()
        self.timerSave = QtCore.QTimer()
        #self.timerFIA = QtCore.QTimer()
        self.timerAuto = QtCore.QTimer()
        #self.timerFlowCell = QtCore.QTimer()
        self.init_ui()
        self.plotSpc= self.plotwidget1.plot()
        self.plotAbs= self.plotwidget2.plot()
        
        self.folderPath ='/home/pi/pHox/data/'
        
        self.timerSens.start(2000)
        
        #self.timerSave.start(10000)
        #if USE_FIA_TA:
        #    self.statusFIA = True 
        #self.puckEm.enter_instrument_mode([])
        
    def init_ui(self):
        self.setWindowTitle('NIVA - pH')
        self.timer.timeout.connect(self.update_spectra)
        self.timerUnderway.timeout.connect(self.underway)
        self.timerSens.timeout.connect(self.update_sensors)
        #self.timerSave.timeout.connect(self.save_pCO2_data)
        #self.timerFIA.timeout.connect(self.sample_alkalinity)
        #self.timerFlowCell.timeout.connect(self.update_Tntc)

        #set grid layout and size columns
        grid = QtGui.QGridLayout()
        grid.setColumnStretch(0,1)
        grid.setColumnStretch(1,1)

        self.group = QtGui.QButtonGroup()
        self.group.setExclusive(False)

        self.chkBoxList = []
        self.sliders = []
        self.sldLabels = []
        
        self.ButtonsNames = ['Spectrophotometer','Take dark','LEDs','Inlet valve','Stirrer','Dye pump','Water pump','Deploy','Single']
        sldNames = ['Blue','Orange','Red','LED4']

        for idx,name in enumerate(self.ButtonsNames):
            row = 0
            BtnBox = QtGui.QPushButton(name)
            BtnBox.setCheckable(True)
            BtnBox.setObjectName(name)
            #idx = self.ButtonsNames.index(name)
            self.group.addButton(BtnBox, idx)
            if idx == 5:
                 row = 0
                 col = 1
            else: 
                col = 0
            grid.addWidget(BtnBox, row, col)
            row += 1  
        self.group.buttonClicked.connect(self.BtnPressed)
        
        sldRow = len(self.ButtonsNames)+1
        for sldInd in range(3):
            self.sliders.append(QtGui.QSlider(QtCore.Qt.Horizontal))
            self.sliders[sldInd].setFocusPolicy(QtCore.Qt.NoFocus)
            grid.addWidget(self.sliders[sldInd],sldRow+sldInd,0)
            self.sldLabels.append(QtGui.QLabel(sldNames[sldInd]))
            grid.addWidget(self.sldLabels[sldInd],sldRow+sldInd,1)
        
        self.sliders[0].valueChanged[int].connect(self.sld0_change)
        self.sliders[1].valueChanged[int].connect(self.sld1_change)
        self.sliders[2].valueChanged[int].connect(self.sld2_change)
        #self.sliders[3].valueChanged[int].connect(self.sld3_change)

        #self.selFolderBtn = QtGui.QPushButton('Select data folder')
        #grid.addWidget(self.selFolderBtn,sldRow+4,0)
        #self.selFolderBtn.released.connect(self.on_selFolderBtn_released)
                                         
        #self.combo = QtGui.QComboBox(self)
        #comboItems=['Set integration time','Set averaging scans','Set sampling interval',
                    #'Auto adjust','Set pCO2 data saving rate','BOTTLE setup', 'UNDERWAY setup']
        #for i in range(len(comboItems)):
            #self.combo.addItem(comboItems[i])
        #self.combo.activated[str].connect(self.on_combo_clicked)
        #grid.addWidget(self.combo, sldRow+4,1)

        self.textBox = QtGui.QTextEdit()
        self.textBox.setOverwriteMode(True)
        grid.addWidget(self.textBox, sldRow+4,0)

        self.textBoxSens = QtGui.QTextEdit()
        self.textBoxSens.setOverwriteMode(True)
        grid.addWidget(self.textBoxSens, sldRow+4,1)

        hboxPanel = QtGui.QHBoxLayout()
        vboxPlot = QtGui.QVBoxLayout()
        vboxComm = QtGui.QVBoxLayout()
        vboxComm.addLayout(grid)    
        
        self.plotwidget1 = pg.PlotWidget()
        self.plotwidget1.setYRange(0,16000)
        vboxPlot.addWidget(self.plotwidget1)
        self.plotwidget2 = pg.PlotWidget()
        self.plotwidget2.setYRange(0,1.3)
        self.plotwidget2.setXRange(410,610)
        vboxPlot.addWidget(self.plotwidget2)
        hboxPanel.addLayout(vboxPlot)
        hboxPanel.addLayout(vboxComm)
        self.setLayout(hboxPanel)

        #self.setGeometry(20, 150, 1200, 650)
        self.showMaximized()

    def BtnPressed(self, sender):

        btn = sender.objectName()

        if btn == 'Spectrophotometer':
           if sender.isChecked():
              self.timer.start(500)
           else:
              self.timer.stop()
        elif btn == 'Take dark':
           self.on_dark_clicked()
           sender.setChecked(False)
        elif btn == 'LEDs':
           self.set_LEDs(sender.isChecked())
        elif btn == 'Stirrer':
           self.instrument.set_line(self.stirrer_slot, sender.isChecked())
        elif btn == 'Dye pump':
           self.instrument.cycle_line(self.dyepump_slot, 2)
           sender.setChecked(False)
        elif btn == 'Water pump':
           self.instrument.set_line(self.wpump_slot, sender.isChecked())
        elif btn == 'Deploy':
           self.on_deploy_clicked(sender.isChecked())
        elif btn == 'Single':
           self.on_bottle_clicked()
           sender.setChecked(False)

        '''if btn == 'Inlet valve':
           self.instrument.set_TV(sender.isChecked())'''


    
    def chkBox_caption(self, chkBoxName, appended):
        self.group.button(self.ButtonsNames.index(chkBoxName)).setText(chkBoxName+'   '+appended)

    def check(self, chkBoxName, newChk):
        self.group.button(self.ButtonsNames.index(chkBoxName)).setChecked(newChk)
   
    def sld0_change(self,DC): #get the value from the connect method
        self.instrument.adjust_LED(0,DC)
        self.check('LEDs',True)
        
    def sld1_change(self,DC): #get the value from the connect method
        self.instrument.adjust_LED(1,DC)
        self.check('LEDs',True)
        
    def sld2_change(self,DC): #get the value from the connect method
        self.instrument.adjust_LED(2,DC)
        self.check('LEDs',True)

    def on_dark_clicked(self):
        print 'Taking dark level...'
        self.set_LEDs(False)
        self.check('LEDs',False)
       
        print 'Measuring...'
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans)   
        self.instrument.spCounts[0] = self.instrument.spectrometer.get_corrected_spectra()
        self.instrument.spectrometer.set_scans_average(1)
        print 'Done'
        self.chkBox_caption('Take dark','(%s ms, n=%s)' % (str(self.instrument.specIntTime), str(self.instrument.specAvScans)))
        
    def set_LEDs(self, state):
        for i in range(0,3):
           self.instrument.adjust_LED(i, state*self.sliders[i].value())
        print 'Leds ',state
        
    def on_selFolderBtn_released(self):
        self.folderDialog = QtGui.QFileDialog()
        folder = self.folderDialog.getExistingDirectory(self,'Select directory')
        if folder == '':
            self.folderPath ='/home/pi/pHox/data/'
        else:
            self.folderPath = folder+'/'
        
    def update_spectra(self):
        datay = self.instrument.spectrometer.get_corrected_spectra()
        self.plotSpc.setData(self.instrument.wvls,datay)                  

    '''def simulate(self):
        self.puckEm.LAST_pH = 8+random.gauss(0,0.05)
        self.puckEm.LAST_CO2 = 350+random.gauss(0,10)
        self.puckEm.LAST_TA = 2200+random.gauss(0,25)
        print '%.1f %.4f %.1f' %(self.puckEm.LAST_CO2,self.puckEm.LAST_pH,self.puckEm.LAST_TA)'''

    '''def on_combo_clicked(self, text):
        comboItems = ['Set integration time','Set averaging scans',
                      'Set sampling interval','Auto adjust',
                      'Set pCO2 data saving rate',
                      'BOTTLE setup','UNDERWAY setup']
        choice = comboItems.index(text)
        if choice == 0:
            self.on_intTime_clicked()
        elif choice == 1:
            self.on_scans_clicked() 
        elif choice == 2:
            self.on_samT_clicked()
        elif choice == 4:
            self.on_data_saving_rate_clicked()
        elif choice == 3:
            self.on_autoAdjust_clicked()
        elif choice == 5:
            dialog = inputDialog(parent= self, title='BOTTLE setup', parString=self.instrument.BOTTLE)
            dialog.exec_()
            try:
               self.instrument.BOTTLE = dialog.parString
            except AttributeError:
               pass
            print self.instrument.BOTTLE
        if choice == 6:
            dialog = inputDialog(parent= self, title='UNDERWAY setup', parString= self.instrument.UNDERWAY)
            dialog.exec_()
            try:
               self.instrument.UNDERWAY = dialog.parString
            except AttributeError:
               pass
            print self.instrument.UNDERWAY'''
            
    def on_intTime_clicked(self):  
        intTime, ok = QtGui.QInputDialog.getInt(None, 'Set spectrophotometer integration time', 'ms',self.instrument.specIntTime,100,3000,100)
        if ok:
            self.instrument.specIntTime = intTime
            self.instrument.spectrometer.set_integration_time(intTime)
            self.chkBox_caption('Spectrophotometer','%d ms' %intTime)
        
    def on_scans_clicked(self): 
        scans, ok = QtGui.QInputDialog.getInt(None, 'Set spectrophotometer averaging scans','',self.instrument.specAvScans,1,20,1)
        if ok:
            self.instrument.specAvScans = scans

    def on_samT_clicked(self):  
        time, ok = QtGui.QInputDialog.getInt(None, 'Set sampling interval','min',self.instrument.samplingInterval,2,60,1)
        if ok:
            self.instrument.samplingInterval = time*60

    def on_autoAdjust_clicked(self):
        DC1,DC2, sptIt, Ok  = self.instrument.auto_adjust()
        self.sliders[0].setValue(DC1)
        self.sliders[1].setValue(DC2)
        self.instrument.specIntTime = sptIt
        self.instrument.specAvScans = 3000/sptIt

    def refresh_settings(self):
        settings = 'Settings:\nSpectrophotometer integration time : %d ms\nSpectrophotometer averaging scans : %d\nPumping time : %d\nWaiting time before scans : %d\nMixing time : %d\nDye addition sequence : %s\nSampling interval : %d\nData folder : %s' % (self.instrument.specIntTime, self.instrument.specAvScans,self.instrument.pumpT, self.instrument.waitT, self.instrument.mixT, self.instrument.dyeAdditions, self.instrument.samplingInterval, self.folderPath)
        self.textBox.setText(settings)

    def update_sensors(self):
        vNTC = self.instrument.get_Vd(3, self.instrument.vNTCch)
        Tntc = 0
        Tntc = (self.instrument.ntcCalCoef[0]*vNTC) +self.instrument.ntcCalCoef[1]
        #for i in range(2):
            #Tntc += self.instrument.ntcCalCoef[i] * pow(vNTC,i)
            
           #Tntc = vNTC*(23.1/0.4173)
        text = 'Cuvette temperature \xB0C: %.4f  (%.4f V)\n' %(Tntc,vNTC)
        text += 'Salinity=%-.2f\nPumping=%-d\n' % (self.instrument.salinity, self.instrument.pumping)        
        LED1 = self.sliders[0].value()
        LED2 = self.sliders[1].value()
        LED3 = self.sliders[2].value()
        text += 'LED1 = %-d\nLED2 = %-d\nLED3 = %-d\n' % (LED1, LED2, LED3) 

        self.textBoxSens.setText(text)

    def on_deploy_clicked(self, state):
        newText =''
        if state:
           self.instrument.flnmStr=''
           self.tsBegin = (datetime.now()-datetime(1970,1,1)).total_seconds()
           nextSample = datetime.fromtimestamp(self.tsBegin + self.instrument.samplingInterval)
           nextSampleTA = datetime.fromtimestamp(self.tsBegin + TA_SAMP_INT)
           text = 'instrument deployed\nNext sample %s\n\n' %(nextSample.isoformat())
           #if FIA_EXIST:
           #   #self.timerFIA.start(TA_SAMP_INT*1000)
           #   #text += 'HydroFIA-TA deployed\nNext sample %s' % (nextSampleTA.isoformat())
           self.textBox.setText(text)
           self.timerUnderway.start(self.instrument.samplingInterval*1000)     
        else:
           self.timerUnderway.stop()
           #self.timerFIA.stop()
           self.textBox.setText('Cbon is not deployed')
                
    def on_bottle_clicked(self):
        # Button "single" is clicked
        self.check('Spectrophotometer',False)
        self.timer.stop()
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
            print 'Start single measurement ', self.instrument.flnmStr
            # call sample func, where second parameter is a hell line 
            self.sample()
            print 'Done'
            self.check('Single',False)
            self.instrument.spectrometer.set_scans_average(1)
        self.timer.start()
        self.check('Spectrophotometer',True)

    def underway(self):
        print('Inside underway...')
        # stop the spectrophotometer update precautionally
        self.check('Spectrophotometer',False)    
        self.timer.stop()
        self.instrument.adjust_LED(0,self.sliders[0].value())
        self.instrument.adjust_LED(1,self.sliders[1].value())
        self.instrument.adjust_LED(2,self.sliders[2].value())
        self.instrument.reset_lines()
        self.instrument.spectrometer.set_scans_average(
                                  self.instrument.specAvScans)
        t = datetime.now()
        self.instrument.timeStamp = t.isoformat('_')
        self.instrument.flnmStr =   t.strftime("%Y%m%d%H%M") 
        self.tsBegin = (t-datetime(1970,1,1)).total_seconds()

        print 'sampling...'
        self.sample()
        print 'done...'

        #self.set_LEDs(False)
        #self.check('LEDs',False)
        self.instrument.spectrometer.set_scans_average(1)
        
        nextSample = datetime.fromtimestamp(self.tsBegin + self.instrument.samplingInterval)
        oldText = self.textBox.toPlainText()
        self.textBox.setText(oldText + '\n\nNext pH sample %s' % nextSample.isoformat())
        self.check('Spectrophotometer',True)    # stop the spectrophotometer update precautionally
        self.timer.start()
    
    def sample(self): #parString pT, mT, wT, dA
        if not self.instrument.pumping:
            return
        if self.instrument._autodark:
            now = datetime.now()
            if (self.instrument.last_dark is None) or ((now - self.instrument.last_dark) >= self.instrument._autodark):
				print 'New dark required'
				self.on_dark_clicked()
        else:
            print 'next dark at' #%s' % ((self.instrument.last_dark + dt).strftime('%Y-%m%d %H:%S'))
        self.set_LEDs(True)
        self.check('LEDs', True)

        self.instrument.evalPar =[]
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans)
        if self.instrument.pT > 0:
            self.instrument.set_line(self.wpump_slot,True) # start the instrument pump
            self.instrument.set_line(self.stirrer_slot,True) # start the stirrer
            self.instrument.wait(self.instrument.pT) # wait for pumping time
            self.instrument.set_line(self.stirrer_slot,False) # turn off the pump
            self.instrument.set_line(self.wpump_slot,False) # turn off the stirrer

        # close the valve
        self.instrument.set_TV(True)
        self.instrument.wait(self.instrument.wT)

        print 'Measuring blank...'
        self.instrument.spCounts[1] = self.instrument.spectrometer.get_corrected_spectra()
        dark = self.instrument.spCounts[0]
        bmd = np.clip(self.instrument.spCounts[1] - dark,1,16000)

        # lenght of dA = numbers of cycles (4)
        for pinj in range(dA):
            shots = self.instrument.nshots
            # shots= number of dye injection for each cycle ( now 1 for all cycles)
            print 'Injection %d:, shots %d' %(pinj, self.instrument.nshots)
            # turn on the stirrer
            self.instrument.set_line(self.stirrer_slot, True)
            # inject dye 
            self.instrument.cycle_line(self.dyepump_slot, shots)
            # wait for mixing time
            self.instrument.wait(self.instrument.mT)
            # turn off the stirrer
            self.instrument.set_line(self.stirrer_slot, False)
            # wait before to start the measurment
            self.instrument.wait(self.instrument.wT)
            # measure spectrum
            postinj = self.instrument.spectrometer.get_corrected_spectra()
            self.instrument.spCounts[2+pinj] = postinj 
            # measuring Voltage for temperature probe
            vNTC = self.instrument.get_Vd(3, self.instrument.vNTCch)
                
            pmd = np.clip(postinj - dark,1,16000)
            cfb = self.instrument.nlCoeff[0] + self.instrument.nlCoeff[1]*bmd + self.instrument.nlCoeff[2] * bmd**2
            cfp = self.instrument.nlCoeff[0] + self.instrument.nlCoeff[1]*pmd + self.instrument.nlCoeff[2] * pmd**2
            bmdCorr = bmd * cfb
            pmdCorr = pmd * cfp
            spAbs = np.log10(bmdCorr/pmdCorr)
            spAbsMA = spAbs
            nPoints = 3
            for i in range(3,len(spAbs)-3):
                v = spAbs[i-nPoints:i+nPoints+1]
                spAbsMA[i]= np.mean(v)
    
            self.plotAbs.setData(self.instrument.wvls,spAbs)
            self.instrument.calc_pH(spAbs,vNTC)
        # opening the valve
        self.instrument.set_TV(False)

        flnm = open(self.folderPath + self.instrument.flnmStr +'.spt','w')
        txtData = ''
        for i in range(2+dA):
            for j in range (self.instrument.spectrometer.pixels):
                txtData += str(self.instrument.spCounts[i,j]) + ','
            txtData += '\n'
        flnm.write(txtData)    
        flnm.close()

        flnm = open(self.folderPath + self.instrument.flnmStr+'.evl','w')
        strFormat = '%.4f,%.4f,%.6f,%.6f,%.6f,%.5f,%.2f,%.5f,%.5f,%.5f,%.4f,%.2f,%.2f,%.2f\n'
        txtData = ''    
        for i in range(len(self.instrument.evalPar)):
            txtData += strFormat % tuple(self.instrument.evalPar[i])
            pass
        flnm.write(txtData)    
        flnm.close()

        pHeval = self.instrument.pH_eval()  #returns: pH evaluated at reference temperature (cuvette water temperature), reference temperature, salinity, estimated dye perturbation
        print 'pH_t= %.4f, Tref= %.4f, S= %.2f, pert= %.3f, Anir= %.1f' % pHeval
        
        print 'data saved in %s' % (self.folderPath +'pH.log')
        with open(self.folderPath + 'pH.log','a') as logFile:
            logFile.write(self.instrument.timeStamp[0:16] + ',%.4f,%.4f,%.4f,%.3f,%.3f\n' %pHeval)
        self.textBox.setText('pH_t= %.4f, Tref= %.4f, S= %.2f, pert= %.3f, Anir= %.1f' %pHeval)
        #self.puckEm.LAST_PAR[1]= pHeval[1]
        #self.puckEm.LAST_pH = pHeval[0]
        
    def _autostart(self):
        print 'Inside _autostart...'
        time.sleep(10)
        self.on_dark_clicked()
        self.sliders[0].setValue(self.instrument.LED1)
        self.sliders[1].setValue(self.instrument.LED2)
        self.sliders[2].setValue(self.instrument.LED3) 
        self.check('Spectrophotometer', True)
        self.check('LEDs', True)
        self.timer.start(500)        
        self.check('Deploy', True)
        self.on_deploy_clicked(True)
        #self.timerSave.start()
        return

    def _autostop(self):
        print 'Inside _autostop...'
        time.sleep(10)
        self.sliders[0].setValue(0)
        self.sliders[1].setValue(0)
        self.sliders[2].setValue(0) 
        self.check('Spectrophotometer', False)
        self.check('LEDs', False)
        self.check('Deploy', False)
        self.on_deploy_clicked(False)
        self.timer.stop()
        self.timerUnderway.stop()
        #self.timerSens.stop()
        #self.timerSave.stop()
        return

    def autostop_time(self):
        print 'Inside autostop_time...'
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
        print 'Inside _autostart_time...'
        self.timerAuto.stop()
        now  = datetime.now()
        if now < self.instrument._autotime:
            self.timerAuto.timeout.connect(self.autostart_time)
            dt = self.instrument._autotime - now
            self.timerAuto.start(int(dt.total_seconds()*1000))
            print 'Instrument will start at ' + self.instrument._autostart.strftime('%Y-%m-%dT%H:%M:%S')
        else:
            self.timerAuto.timeout.disconnect(self.autostart_time)
            self.timerAuto.timeout.connect(self.autostop_time)
            t0 = self.instrument._autotime + self.instrument._autolen
            dt = t0 - now
            self.timerAuto.start(int(dt.total_seconds()*1000))
            print 'Instrument will stop at ' + t0.strftime('%Y-%m:%dT%H:%M:%S') 
            self._autostart()
        return
    
    def autostart_pump(self):
        print 'Inside _autostart_pump...'
        self.textBox.setText('Automatic start at pump enabled')
        if self.instrument.pumping:
            self.timerAuto.stop()
            self.timerAuto.timeout.disconnect(self.autostart_pump)
            self.timerAuto.timeout.connect(self.autostop_pump)
            self.timerAuto.start(10000)
            self._autostart()
        else:
            pass
        return
        
    def autostop_pump(self):
        print 'Inside autostop_pump...'        
        if not self.instrument.pumping:
            self.timerAuto.stop()
            self.timerAuto.timeout.disconnect(self.autostop_pump)
            self.timerAuto.timeout.connect(self.autostart_pump)
            self.timerAuto.start(10000)
            self._autostop()
        else:
            pass
        return
        
    
    def autorun(self):
        print 'Inside underway...'
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
    print 'ending'
    myPanel.instrument._exit = True
    myPanel.timer.stop()
    myPanel.timerUnderway.stop()
    myPanel.timerSens.stop()
    #myPanel.timerSave.stop()