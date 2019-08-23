#! /usr/bin/python

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

UDP_SEND = 6801
UDP_RECV = 6802
UDP_IP   = '192.168.0.2'

#i2c_helper = ABEHelpers()
#bus = i2c_helper.get_smbus()
adc = ADCDifferentialPi(0x68, 0x69, 14)
adc.set_pga(1)
adcdac = ADCDACPi()

ports = list(serial.tools.list_ports.comports()) #locate serial port
SENS_EXIST = False
HOST_EXIST = False
FIA_EXIST = False

USE_FIA_TA = False

print ports
for i in range (len(ports)):
   name=ports[i][2]
   port=ports[i][0]
   if name == 'USB VID:PID=0403:6001 SNR=FTZ1SAJ3': #USB-RS485 CO2 sensor
      portSens = serial.Serial(port,
                              baudrate=9600,
                              parity=serial.PARITY_NONE,
                              stopbits=serial.STOPBITS_ONE,
                              bytesize=serial.EIGHTBITS,
                              writeTimeout = 0,
                              timeout = 0.5,
                              rtscts=False,
                              dsrdtr=False,
                              xonxoff=False)
      SENS_EXIST = True
            
   if name == 'USB VID:PID=0403:6001 SNR=FTZ0GOLZ': #USB-RS232 host
      host = serial.Serial(port,
                              baudrate=9600,
                              parity=serial.PARITY_NONE,
                              stopbits=serial.STOPBITS_ONE,
                              bytesize=serial.EIGHTBITS,
                              writeTimeout = 0,
                              timeout = 0.25,
                              rtscts=False,
                              dsrdtr=False,
                              xonxoff=False)
      HOST_EXIST = True

   if name == 'USB VID:PID=0557:2008': #USB-RS232 Alkalinity sensor
      portFIA = serial.Serial(port,
                              baudrate=115200,
                              parity=serial.PARITY_NONE,
                              stopbits=serial.STOPBITS_ONE,
                              bytesize=serial.EIGHTBITS,
                              writeTimeout = 0,
                              timeout = 0.1,
                              rtscts=False,
                              dsrdtr=False,
                              xonxoff=False)
      FIA_EXIST = True
   


# ----------- Rpi pins 
#PWM: LEDs
GPIO_PWM = [12,13,19,16]
#SSR: dye and water pump and stirrer 
GPIO_SSR = [17,18,27,22]
#TV: toggle Valve
GPIO_TV = [23,24,25]

# ------- SSR settings
# water pump slot
WPUM = 1
# dye pump slot
DYEP = 2
# stirrer slot
STIP = 3
#
INTV = 9


VAR_NAMES = ['Water temperature \xB0C','Water flow l/m','Water pressure ','Air temperature \xB0C','Air pressure mbar','Water detect','C02 ppm','T CO2 sensor \xB0C']

# ----------- definition of global constants 

# PUCK mode strings
PRD = 'PUCKRDY\r'
PRM = 'PUCKRM'
PTO = 'PUCKTMO\r'
PSB = '@@@@@@!!!!!!'
PCK = 'PUCK'
PSZ = 'PUCKSZ'
PSA = 'PUCKSA'
PIM = 'PUCKIM'

# Instrument mode strings
CBG = 'CBON:GET'

# Franatech query strings
QUERY_CO2='\x2A\x4D\x31\x0A\x0D'
QUERY_T='\x2A\x41\x32\x0A\x0D'

# KM strings
TCHAR = '\r\n'
SET_SAL = '$KMSALINITY,W,'
SET_SAMPLE_NAME = '$KMNAME,W,'
RUN = '$KMRUN,W,MEASURE'+TCHAR
STOP = '$KMRUN,W,STOP'+TCHAR

# sampling intervals (seconds)
TA_SAMP_INT = 600
pH_SAMP_INT = 600



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
      
      

class PuckManager(object):
   
   def __init__(self):
      self.timerHostPoll = QtCore.QTimer()
      #self.timerHostPoll.timeout.connect(self.poll_host_softbreak)
      #self.timerHostPoll.timeout.connect(self.save_data)
       # define PUCK dictionary  
      self.puckDict = {PCK: self.puck,
                       PSZ: self.puck_memory_size,
                       PRM: self.puck_read_memory,
                       PSA: self.puck_set_address,
                       PIM: self.enter_instrument_mode}
      self.instDict = {CBG: self.send_data} 

      self.instDictHints = {CBG[0:6]}
      self.memPtr = 0
      self.PUCK_MEM_SIZE = 10000 #set larger than the actual puckmem file size
      self.memDumpStr = ''
      self.dump_puck_memory()
      self.PT= 120  #PUCK timeout in seconds
      self.puckMode = False
      self.LAST_pH = 1
      self.LAST_CO2 = 1
      self.LAST_TA = 1
      self.LAST_PAR=[0,0,0]

   # Instrument mode -------------------------
   def poll_host_softbreak(self):   
      print( 'listening to host...') #750ms and 500ms sleep intervals seem to work with PUCK timing
      try:
         rx = host.read(6)
         #print( '<-- '+ rx)
         if rx == '@@@@@@':
            time.sleep(0.75)
            rx = host.read(7)
            #print( '<-- '+ rx)
            if rx == '!!!!!!':
               time.sleep(0.5)
               host.write(PRD)
               self.timerHostPoll.stop()
               self.enter_puckmode()
            else:
               host.flushInput()
         elif (rx in self.instDictHints):
            rRx = host.read(10)
            sentence = (rx+rRx).split()
            cmd = sentence[0]
            parList=[]
            if len(sentence)>1:
               parList = sentence[1:]
            if cmd in self.instDict:
               print( 'Instrument command valid')
               self.instDict[cmd].__call__(parList)                 
         else:
            host.flushInput()
            
      except KeyboardInterrupt:
         self.timerHostPoll.stop()
         host.close()
         
   
   def enter_puckmode(self):
      print( 'Puckmode')
      #listen to host until some data arrive
      self.puckMode= True
      flInt = ['','\r'] #flow interruption marks
      cmd =''
      t0 = time.time()
      elapsed = time.time()-t0
      while (elapsed < self.PT) and (cmd != PIM) :
         received = ''
         fromHost = host.read(1)
         while not(fromHost in flInt) and (elapsed < self.PT) and (received != PSB):
            received += fromHost
            fromHost = host.read(1)
         print( 'received: '+received)
         if len(received) > 0:
            sentence = received.split()
            cmd = sentence[0]
            parList=[]
            if len(sentence)>1:
               parList = sentence[1:]
            if cmd in self.puckDict:
               print('PUCK command valid')
               self.puckDict[cmd].__call__(parList)
               t0 = time.time()
         elapsed = time.time()-t0
               
      if cmd != PIM:
         host.write(PTO+PRD)     
      self.enter_instrument_mode([])
      

   def send_data(self, args):
      t = datetime.now()
      dateTime = t.isoformat('_')
      dataString = dateTime[0:10]+','+dateTime[11:19]
      # dataString header: pCO2,pH,TA,lat,lon,sal_ref,pCO2_Tref_meas,pH_Tref_meas
      dataString = '%.1f,%.4f,%.1f,9999.9999,8888.8888,%.2f,%.2f,%.2f\r' %(self.LAST_CO2,self.LAST_pH,self.LAST_TA,self.LAST_PAR[0],self.LAST_PAR[1],self.LAST_PAR[2])
      host.write(dataString)
      dataString = dateTime[0:10]+','+dateTime[11:19]+','+dataString
      with open('data/pH.log','a') as flnm:
         flnm.write(dataString+'\n')      


   def enter_instrument_mode(self, args):
      print( 'Entering instrument mode...')
      self.puckMode = False
      self.timerHostPoll.start(30000)  #poll host for instrument specific commands, 1000ms seems to work with timing
      
   def puck(self,args):
      host.write(PRD)
      print( 'PUCK query')

   def puck_memory_size(self,args):
      host.write(str(self.PUCK_MEM_SIZE)+'\r')
      host.write(PRD)

   def puck_set_address(self, args):
      self.memPtr = int(args[0])
      host.write(PRD)
         
   def puck_read_memory(self, args):
      print( 'Reading PUCK memory')
      nBytesToRead = 0
      bytesRead = ''
      try:
         nBytesToRead = int(args[0])
      except IndexError:
         print 'Missing argument'
      for n in range (nBytesToRead):
         bytesRead += self.memDumpStr[self.memPtr]
         self.memPtr += 1
         if self.memPtr == self.PUCK_MEM_SIZE:    #wrapping memory pointer
            self.memPtr = 0
       
      print('PUCK memory pointer : %u ' %self.memPtr)
      
      host.write('['+bytesRead+']')
      host.write(PRD)
      
   def puck_write_memory(self, args):
      print( 'Writing PUCK memory')
      nBytesToWrite = int(args[0])
      packet = ''
      for i in range (nBytesToWrite):
         packet += host.read(1)
      partMem = self.memDumpStr[0:self.memPtr] + packet
      self.memPtr += len(packet)
      print('PUCK memory pointer : %u ' %self.memPtr)
      partMem += self.memDumpStr[self.memPtr:]
      self.memDumpStr = partMem
      print('Redumping PUCK memory...')
      self.dump_puck_memory()
      
   def dump_puck_memory(self):
      with open('puckmem','r') as puckMem:
         self.memDumpStr = puckMem.read()
      self.PUCK_MEM_SIZE = len(self.memDumpStr)     #assign actual puck memory size
      frmt = '>'+str(self.PUCK_MEM_SIZE)+'B'
      self.puckM = np.array(struct.unpack(frmt,self.memDumpStr))


#####################               Ocean Optics STS protocol manager ###################################
##################### DO NOT CHANGE WITHOUT PROPER KNOWLEDGE OF THE DEVICE USB PROTOCOL #################

class STSVIS(object):
    def __init__(self):
        self._dev = usb.core.find(idVendor=0x2457, idProduct=0x4000)
        if (self._dev == None):
            raise ValueError ('OceanOptics STS: device not found\n')
        else:
            print ('Initializing STS spectrophotometer...')
        
        self.EP1_out = 0x01
        self.EP1_in = 0x81
        self.EP2_in = 0x82
        self.EP2_out = 0x02

        self.gcsCmd = self.build_packet('\x00\x10\x10\x00','\x00','\x00\x00\x00\x00')
        self.pixels = 1024
        self.nWvlCalCoeff = '\x00\x01\x02\x03'
        self.reset_device()
        time.sleep(0.5)
        self.wvlCalCoeff = self.get_wvlCalCoeff()
               
    def build_packet(self,messageType, immediateDataLength, immediateData):
        headerTop = '\xC1\xC0'
        protocolVersion = '\x00\x10'
        flags = '\x00\x00'
        errorNumber = '\x00\x00'
        regarding = '\x00'*4
        reserved = '\x00'*6
        checksumType = '\x00'
        unused = '\x00'*12
        bytesRemaining = '\x14\x00\x00\x00'
        checksum = '\x00'*16
        footer = '\xC5\xC4\xC3\xC2'
        packet = headerTop + protocolVersion + flags + errorNumber + messageType +\
            regarding + reserved + checksumType + immediateDataLength +\
            immediateData + unused + bytesRemaining + checksum + footer
        return packet
    
    def reset_device (self):
        msgType = '\x00'*4
        immDataLength = '\x00'
        immData = '\x00'*4
        try:
            self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        except usb.core.USBError:
            pass
        time.sleep(1.5)
        self._dev = usb.core.find(idVendor=0x2457, idProduct=0x4000)
        if self._dev is None:
            raise ValueError('Device not found')        
            
    def set_integration_time(self,time_ms):
        msgType= '\x10\x00\x11\x00'
        immDataLength = '\x04'
        immData = struct.pack('<I',time_ms*1000)
        self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        time.sleep(0.5)

    def set_scans_average(self,nscans):
        msgType= '\x10\x00\x12\x00'
        immDataLength = '\x02'
        immData = struct.pack('<H',nscans)+'\x00\x00'
        self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        time.sleep(0.5)

    def get_wvlCalCoeff(self):
        #msgType = '\x00\x01\x18\x00'
        #immDataLength= '\x00'
        #immData = '\x00' *4
        #self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        #nWvlCoeff = self._dev.read(self.EP1_in, 64, timeout=10000)[24]
        #get the coefficients
        print 'Getting wavelength calibration coefficients...'
        msgType = '\x01\x01\x18\x00'
        immDataLength= '\x01'
        #wvlCalCoeff = np.zeros(4, dtype=float)
        wvlCalCoeff = []
        for i in range(4):
            immData = struct.pack('B',i)+'\x00\x00\x00'
            self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
            rx_packet = self._dev.read(self.EP1_in, 64, timeout=1000)
            #wvlCalCoeff.append(float(struct.unpack('<f',struct.pack('4B',*rx_packet[24:28]))[0]))
            wvlCalCoeff.append(float(struct.unpack('<f',struct.pack('4B',*rx_packet[24:28]))[0]))
        print 'calibration coefficients: ', wvlCalCoeff,'\n'
        return wvlCalCoeff
          
    def get_corrected_spectra(self):
        self._dev.write(self.EP1_out, self.gcsCmd)
        rx_packet = self._dev.read(self.EP1_in, 64+2048, timeout=10000)
        spec = rx_packet[44:2092]
        spectralCounts = struct.unpack('<1024H',struct.pack('2048B',*spec))
        spectralCounts = np.array(spectralCounts,dtype=float)
        return spectralCounts

#_________________________________________________________________________________________________________________

##########################  Instrument constructor ###############################################################
    

class Cbon(object):
    def __init__(self):
        # For signaling to threads
        self._exit = False 
        
        #initialize PWM lines      
        self.rpi = pigpio.pi()
         
        # load instrument general configuration   
      
        self.evalPar = []
        self.ledDC = [0]*4 
        self.spectrometer = STSVIS()
        self.wvlPixels = []
        self.spCounts = np.zeros((6,1024))
        self.nlCoeff = [1.0229, -9E-6, 6E-10]
        self.specIntTime = 500 #spectrometer integration time (ms)
        self.specAvScans = 6

        
        self.samplingInterval = pH_SAMP_INT
        self.salinity = 33.5
        self.pumping = 1
        self.tsBegin = float
        self.status = [False]*16
        self.intvStatus = False
        
        self.franatech = [0]*10
        self.ftCalCoef= [[0]*2]*10
        
        self.CO2UpT = 5
        
        self.flnmStr = ''
        self.timeStamp = ''
        self.spectrometer.set_integration_time(self.specIntTime)
        self.spectrometer.set_scans_average(1)
        self.BOTTLE='00_5_3_1111'
        self.UNDERWAY='00_5_3_1111'
        self._autostart = False
        self._autotime  = None
        self._autolen   = None
        self._autostop  = None
        self._automode  = 'DISABLED'
        self._autodark  = None
        self._deployed  = False
        self.last_dark  = None
        self.LED1 = 21
        self.LED2 = 70
        self.LED3 = 99
        self.load_config()

        #setup PWM and SSR lines
        for pin in range (4):
           if self.pwmLines[pin] in GPIO_PWM:
              self.rpi.set_mode(self.pwmLines[pin],pigpio.OUTPUT)
              self.rpi.set_PWM_frequency(self.pwmLines[pin], 100)
              self.rpi.set_PWM_dutycycle(self.pwmLines[pin],0)

        for pin in range (4):
           if self.ssrLines[pin] in GPIO_SSR:
              self.rpi.set_mode(self.ssrLines[pin], pigpio.OUTPUT)

        print 'calculating wavelengths...\n'
        self.wvls = self.calc_wavelengths(self.spectrometer.wvlCalCoeff)
        
        self.reset_lines()
        
        udp = threading.Thread(target=self.udp_server)
        udp.start()
        
        #status is a list of boolean keeping track of the status of the isntrument
        #detailed assigning can be written here
        #status 1-4: Darlington lines
        #status 9: input toggle valve
        #status 6: spectrophotometer free running
        #status 7: LEDs
        #status 0: operation mode

    def udp_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', UDP_RECV))
        print 'UDP server started'
        while not self._exit:
            (data,addr) = sock.recvfrom(500)
            print 'received: %s' % (data.strip())
            w = data.split(',')
            if data.startswith('$PFBOX,TIME,'):
                v = datetime.strptime(w[2], '%Y-%m-%dT%H:%M:%S')
                t = datetime.now()
                if abs(t-v).total_seconds() > 5:
                    print 'will correct time'
                    os.system("date +'%Y-%m-%dT%H:%M:%S' --set={:s}".format(w[2]))
            elif data.startswith('$PFBOX,SAL,'):
                v = float(w[2])
                self.salinity = v
            elif data.startswith('$PFBOX,PUMP,'):
                v = int(w[2])
                self.pumping = v
        sock.close()
            

        
    def load_config(self):
        print 'Loading pHaro parameters...'
        with open('Cbon_pja_v9.cfg','r') as cfgF:
            text = (cfgF.read()).replace(' ','')
        parLines = text.split()
        pars = []
        for i in range(len(parLines)):
            pars += parLines[i].split('=')
        params = []
        for i in range(len(pars)):
            params += pars[i].split(',')
            
        try:
            paramIndex = params.index('HI-')+1
            self.HI = int(params[paramIndex])         
        except ValueError:
                self.HI = 435
        try:
            paramIndex = params.index('I2-')+1
            self.I2 = int(params[paramIndex])
        except ValueError:
                self.I2 = 596
        try:
            paramIndex = params.index('ISO')+1
            self.Iso = int(params[paramIndex])
        except ValueError:
                self.Iso = 494
        try:
            paramIndex = params.index('NIR-')+1
            self.NIR = int(params[paramIndex])
        except ValueError:
                self.NIR = 730
##        try:
##            paramIndex = params.index('LED1')+1
##            self.LED2 = int(params[paramIndex])
##        except ValueError:
##                self.LED1 = 0
##        try:
##            paramIndex = params.index('LED2')+1
##            self.LED2 = int(params[paramIndex])
##        except ValueError:
##                self.LED2 = 0
##        try:
##            paramIndex = params.index('LED3')+1
##            self.LED2 = int(params[paramIndex])
##        except ValueError:
##                self.LED3 = 0
##       print 'LED1: ', self.LED1, ' LED2: ', self.LED2,' LED3: ', self.LED3,'\n'
        try:
            paramIndex = params.index('AUTOSTART')+1
            paramValue = params[paramIndex]
            print 'autostart: ', paramValue
            if paramValue.lower() == 'yes':
                self._autostart = True
        except Exception:
            print 'no autostart'
        if self._autostart:
            try:
                paramIndex = params.index('AUTOSTART_MODE')+1
                paramValue = params[paramIndex]
                print 'autostart mode: ', paramValue
                if paramValue.lower() in ('pump', 'time', 'now'):
                    self._automode = paramValue.lower()
            except Exception:
                raise ValueError('error reading AUTOSTART MODE')
                self._autostart = None
        if self._automode == 'time':
            try:
                paramIndex = params.index('AUTOSTART_TIME')+1
                paramValue = params[paramIndex]
                print 'autostart time: ', paramValue
                self._autotime = datetime.strptime(paramValue, '%Y-%m-%dT%H:%M:%S')
            except Exception:
                error('error reading absolute start time') 
                self._autostart = None
            try:
                paramIndex = params.index('AUTOSTART_LEN')+1
                paramValue = int(params[paramIndex])
                print 'autostart length: ', paramValue
                self._autolen = paramValue
            except Exception:
                error('error reading duration length') 
                self._autostart = None
                        
        try:
            paramIndex = params.index('AUTODARK')+1
            self._autodark = timedelta(minutes=int(params[paramIndex]))
        except Exception as err:
            raise err
            print 'no auto dark time'
        try:
            paramIndex = params.index('T_PROBE_CH')+1
            self.vNTCch = int(params[paramIndex])
            if not(self.vNTCch in range(9)):
                self.vNTCch = 8
        except ValueError:
            self.vNTCch = 8
        try:
            paramIndex = params.index('MOL_ABS_RATIOS')+1
            self.molAbsRats = [float(params[paramIndex+i]) for i in range(9)]
            print 'Molar absorption ratios: '
        except ValueError:
            self.molAbsRats = [-0.00132,1.6E-5, 0, 7.2326, -0.0299717, 4.6E-5, 0.0223, 0.0003917, 0]
            print 'Using default molar absorption ratios: '
        finally:
            print self.molAbsRats, '\n'

        try:
            paramIndex = params.index('PWM_LINES')+1
            self.pwmLines = [int(params[paramIndex+i]) for i in range (4)]
            print 'BCM lines for PWM LEDs: '
        except ValueError:
            self.pwmLines = GPIO_PWM
            print 'Using default BCM lines for PWM LEDs: '
        finally:
            print self.pwmLines
            print '0 = will be skipped'
           
        try:
            paramIndex = params.index('GPIO_SSR')+1
            self.ssrLines = [int(params[paramIndex+i]) for i in range(4)]
            print 'BCM lines for SSRs: '
        except ValueError:
            self.ssrLines = GPIO_SSR
            print 'Using default BCM lines for SSRs: '
        finally:
            print self.ssrLines 
            print '0 = will be skipped'

        try:
            paramIndex = params.index('GPIO_TV')+1
            self.GPIO_TV = [int(params[paramIndex+i]) for i in range(4)]
            print 'BCM lines for bistable valve driver: '
        except ValueError:
            self.GPIO_TV = GPIO_TV
            print 'Using default BCM lines for bistable valve driver: '
        finally:
            print self.GPIO_TV
    
            
        # NTC calibration coefficients
        try:
            paramIndex = params.index('NTC_CAL_COEF')+1
            self.ntcCalCoef = [float(params[paramIndex+i]) for i in range(4)]
            print 'NTC calibration coefficients :'
        except ValueError:
            self.ntcCalCoef = [91.377, 18.676,0,0]
            print 'Using default NTC calibration coefficients:'
        finally:
            print self.ntcCalCoef, '\n'

        try:
            paramIndex = params.index('DYE_CAL')+1
            self.dyeCal = [float(params[paramIndex+i]) for i in range(3)]
            print 'Dye calibration coefficients (ml_dye/Aiso, S, ml):'
        except ValueError:
            self.dyeCal = [0.22, 0, 4] #to be confirmed
            print 'Using default dye calibration coefficients:'
        finally:
            print self.dyeCal,'\n'

        try:
            paramIndex = params.index('DYE')+1
            self.dye = params[paramIndex]
            print 'Dye method::'
        except ValueError:
            self.dye = 'TB'
            print 'Using default dye calibration coefficients:'
        finally:
            print self.dye,'\n'

        #Franatech calibration coefficients
      
        #nominal self.ftCalCoef[0] = [-25,28.604]
        self.ftCalCoef[0] = [-25.779,29.84] #after calibration
        print 'Water temperature calibration coefficients :',self.ftCalCoef[0]

        self.ftCalCoef[1] = [-1.25,1.6682] #nominal
        print 'Water flow calibration coefficients :', self.ftCalCoef[1]

        self.ftCalCoef[2] = [-2.5,1.75562] #nominal
        print 'Water pressure calibration coefficients :',self.ftCalCoef[2]

        #nominal self.ftCalCoef[3] = [-75,53.2368]
        self.ftCalCoef[3] = [80.329,17.415] # after calibration
        print 'Air temperature calibration coefficients :',self.ftCalCoef[3]

        self.ftCalCoef[4] = [781.2273,302.2975]
        print 'Air pressure calibration coefficients :',self.ftCalCoef[4]

        self.ftCalCoef[5] = [0,1]
        print 'Water detection voltage threshold :',self.ftCalCoef[5]

        self.ftCalCoef[6] = [-30.439,1.4352]
        print 'CO2 molar fraction calibration coefficients :',self.ftCalCoef[6]
                
            
    def calc_wavelengths(self,coeffs):   # assign wavelengths to pixels and find pixel number of reference wavelengths
        wvls = np.zeros(self.spectrometer.pixels, dtype=float)
        pixels = np.arange(self.spectrometer.pixels)
        wvls = coeffs[0] + coeffs[1]* pixels + coeffs[2]*(pixels**2) + coeffs[3]*(pixels**3)
        self.wvlPixels = []
        for wl in (self.HI, self.Iso, self.I2, self.NIR):
            self.wvlPixels.append(self.find_nearest(wvls,wl))
        print 'Analysis pixels : ', self.wvlPixels
        return wvls

    def find_nearest(self, items, value):
        idx = (abs(items-value)).argmin()
        return idx
                
    def get_spectral_data(self):
        return self.spectrometer.get_corrected_spectra()

    def get_sp_levels(self,pixel):
        spec = self.get_spectral_data()
        return spec[pixel],spec.max()
    
           
    def get_V(self, nAver, ch):
        V = 0.0000
        for i in range (nAver):
            V += adcdac.read_adc_voltage(ch,0) #1: read channel in differential mode
        return V/nAver
      
    def get_Vd(self, nAver, ch):
        V = 0.0000
        for i in range (nAver):
            V += adc.read_voltage(ch)
        return V/nAver
      
    def adjust_LED(self, led, DC):
        self.rpi.set_PWM_dutycycle(self.pwmLines[led],DC)

   # auto adjust integration time, scans and light levels #
    def auto_adjust(self):
        THR = 11500
        STEP = 5
        sptItRange = [500,750,1000,1500,3000]
        self.spectrometer.set_scans_average(1)
        print 'Adjusting light levels with %i spectral counts threshold...' %THR
        for sptIt in sptItRange:
            adj1,adj2,adj3 = False, False, False
            self.adjust_LED(0,0)
            self.adjust_LED(1,0)
            self.adjust_LED(2,0)
            self.spectrometer.set_integration_time(sptIt)
            print 'Trying %i ms integration time...' % sptIt
            print 'Adjusting LED 1'
            for DC1 in range(5,100,STEP):
               self.adjust_LED(1, DC1)
               pixelLevel, maxLevel = self.get_sp_levels(self.wvlPixels[0])
               print pixelLevel, maxLevel
               if (pixelLevel>THR) and (maxLevel<15500):  
                  adj1 = True
                  print 'Led 1 adjusted'
                  break
            if adj1:
               STEP2 = 3
               print 'Adjusting LED 2'            
               for DC2 in range(5,100,STEP2):
                  self.adjust_LED(2, DC2)
                  pixelLevel, maxLevel = self.get_sp_levels(self.wvlPixels[2])
                  print pixelLevel,maxLevel
                  if (pixelLevel>THR) and (maxLevel<15500):  
                     adj2 = True
                     print 'LED 2 adjusted'
                     break
            if adj2:
               STEP2 = 3
               print 'Adjusting LED 3'            
               for DC3 in range(5,100,STEP2):
                  self.adjust_LED(3, DC3)
                  pixelLevel, maxLevel = self.get_sp_levels(self.wvlPixels[3])
                  print pixelLevel,maxLevel
                  if (pixelLevel>THR) and (maxLevel<15500):  
                     adj3 = True
                     print 'LED 3 adjusted'
                     break
            if (adj1 and adj2 and adj3):
               print 'Levels adjusted'
               break
               #self.specIntTime = sptIt
               #self.specAvScans = 3000/sptIt
        return DC1,DC2,DC3,sptIt,adj1 & adj2 % adj3
                                                  
        
    def print_Com(self, port, txtData):
        port.write(txtData)

    def wait(self, secs):
        t0 = time.time()
        print('Waiting...')
        while (time.time()-t0)<secs:
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                print('skipped')
                break

    def reset_lines(self):
        for pin in range(len(self.ssrLines)):
            if self.ssrLines[pin] in GPIO_SSR:
               self.rpi.write(self.ssrLines[pin], 0)
                             
    def set_line (self, line, status):
        self.rpi.write(self.ssrLines[line-1], status)
        
    def cycle_line (self, line, nCycles):
        ON = 0.3
        OFF = 0.3
        for nCy in range(nCycles):
            self.set_line(line, True)
            time.sleep(ON)
            self.set_line(line, False)
            time.sleep(OFF)
        pass

    def set_TV (self, status):
        chEn = GPIO_TV[0]
        ch1 = GPIO_TV[1]
        ch2 = GPIO_TV[2]
        if status:
            ch1= GPIO_TV[2]
            ch2= GPIO_TV[1]   
        self.rpi.write(ch1, True)
        self.rpi.write(ch2 , False)       
        self.rpi.write(chEn , True)
        time.sleep(0.3)
        self.rpi.write(ch1, False)
        self.rpi.write(ch2 , False)       
        self.rpi.write(chEn , False)

                
    def movAverage(self, dataSet, nPoints):
        spAbsMA = dataSet
        for i in range(3,len(dataSet)-3):
            v = dataSet[i-nPoints:i+nPoints+1]
            spAbsMA[i]= np.mean(v)
        return spAbsMA

    def calc_pH(self,absSp, vNTC):
        Tdeg = 0
        for i in range(4):
           vNTC2 = 0
           vNTC2 = self.get_Vd(3, self.vNTCch)
           Tdeg = 0
           Tdeg = (self.ntcCalCoef[0]*vNTC2) +self.ntcCalCoef[1]
        #for i in range(2):
            #Tntc += self.instrument.ntcCalCoef[i] * pow(vNTC,i)
            
            #Tdeg += self.ntcCalCoef[i] * pow(vNTC,i)

        print 'T sample : %.2f' %Tdeg

        T = 273.15 + Tdeg
        S = self.salinity
        Kind = self.dyeCal[0]
        dyeS = self.dyeCal[1]
        sVol = self.dyeCal[2]
        
        A1,Aiso,A2,Anir = absSp[self.wvlPixels[0]], absSp[self.wvlPixels[1]], absSp[self.wvlPixels[2]], absSp[self.wvlPixels[3]]
        mARs = reshape(np.array(self.molAbsRats),[3,3])

       # to be corrected (SAM)
        Vinj = Aiso * Kind
        fcS = S* (sVol - Vinj)/ sVol + dyeS * Vinj/sVol
        
        R = A2/A1
        
        if self.dye == 'TB':
            pK = 4.706*(fcS/T) + 26.3300 - 7.17218*log10(T) - 0.017316*fcS
            e1, e2, e3 = mARs[0,0] + mARs[0,1]*T, mARs[1,0] + mARs[1,1]*T + mARs[1,2]*(T**2), mARs[2,0] + mARs[2,1]*T                   
            print 'pK = ', pK,'  e1 = ',e1, '  e2 = ',e2, '  e3 = ',e3, ' Anir = ',Anir
            print 'R = %.5f,  Aiso = %.3f' %(R,Aiso)                   
            arg = (R - e1)/(e2 - R*e3)
            pH = 0.0047 + pK + log10(arg)
        elif self.dye == 'MCP':        
            e1=-0.007762+(4.5174*10^-5)*Temp
            e2e3=-0.020813+((2.60262*10^-4)*Temp)+(1.0436*10^-4)*(fcS-35)
            arg = (R - e1)/(1 - R*e2e3)
            pk= 5.561224-(0.547716*fcS^0.5)+(0.123791*fcS)-(0.0280156*fcS^1.5)+(0.00344940*fcS^2)-(0.000167297*fcS^2.5)+((52.640726*fcS^0.5)*Temp^-1)+(815.984591*Temp^-1)
            pH= pk + log10(arg)
            print 'pK = ', pK,'  e1 = ',e1, '  e2e3 = ',e2e3, ' Anir = ',Anir
        else:
            raise ValueError('wrong DYE: ' + self.dye)
        # # mouais.. tu auras peut etre une meilleure idee
        # e2=e2e3
        # e3=-99
        
        ###### end if
        

        print 'pH = %.4f, T = %.2f' % (pH,Tdeg) 
        self.evalPar.append([pH, pK, e1, e2, e3, vNTC, S, A1, A2, Aiso, Tdeg, Vinj, fcS, Anir])
        
    def pH_eval(self):
        # pH ref
        dpH_dT = -0.0155
        n = len(self.evalPar)
        evalAnir = [self.evalPar[i][13] for i in range(n)]
        evalAnir = np.mean(evalAnir)
        print 'Anir = %.4f' % (evalAnir)
        evalAiso = [self.evalPar[i][9] for i in range(n)]
        evalT = [self.evalPar[i][10] for i in range(n)]
        refT = np.mean(evalT)
        #print refT
        evalpH = [self.evalPar[i][0] for i in range(n)]
        pH_t = evalpH[0]
        refpH = [evalpH[i] + dpH_dT *(evalT[i]-evalT[1] ) for i in range(n)]
        # temperature drift correction based on the 1st measurment SAM 
        
        #print refpH
        if n>1:
            x = np.array(range(4)) # fit on equally spaced points instead of Aiso SAM 
            y = np.array(refpH)
            A = np.vstack([x, np.ones(len(x))]).T
            pert,pH_t = np.linalg.lstsq(A, y)[0]

        return (pH_t, refT, self.salinity, pert, evalAnir)
            
            
    
#______________________________________________________________________________________________________________________

#################################### Panel Constructor ################################################################

class inputDialog(QtGui.QDialog):
    def __init__(self, parent=None, title='user input', parString='30_5_3_1111'):
        QtGui.QWidget.__init__(self, parent)
        layout = QtGui.QFormLayout()
        self.line = QtGui.QLineEdit(parString)
        self.line.setInputMask('99_9_9_9999')
        self.line.returnPressed.connect(self.check_parameters)
        layout.addRow(self.line)
        self.setLayout(layout)
        self.setWindowTitle(title)
        
    def check_parameters(self):
        self.parString= '%s' %self.line.text()      
        
           
class Panel(QtGui.QWidget):
    def __init__(self):
        super(Panel, self).__init__()
        self.instrument = Cbon()
        self.puckEm = PuckManager()
        self.timer = QtCore.QTimer()
        self.timerUnderway = QtCore.QTimer()
        self.timerSens = QtCore.QTimer()
        self.timerSave = QtCore.QTimer()
        self.timerFIA = QtCore.QTimer()
        self.timerAuto = QtCore.QTimer()
        #self.timerFlowCell = QtCore.QTimer()
        self.init_ui()
        self.plotSpc= self.plotwidget1.plot()
        self.plotAbs= self.plotwidget2.plot()
        
        self.folderPath ='/home/pi/pHox/data/'
        
        self.timerSens.start(2000)
        
        #self.timerSave.start(10000)
        if USE_FIA_TA:
            self.statusFIA = True 
        self.puckEm.enter_instrument_mode([])
        
    def init_ui(self):
        self.setWindowTitle('NIVA - pH')
        self.timer.timeout.connect(self.update_spectra)
        self.timerUnderway.timeout.connect(self.underway)
        self.timerSens.timeout.connect(self.update_sensors)
        #self.timerSave.timeout.connect(self.save_pCO2_data)
        self.timerFIA.timeout.connect(self.sample_alkalinity)
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
        
        #self.chkBoxNames = ['Spectrophotometer','Take dark','Deploy','Enable PUCK protocol',
                           # 'Bottle','LEDs','Water pump','Inlet valve','Stirrer','Dye pump']
                            
        self.chkBoxNames = ['Spectrophotometer','Take dark','LEDs','Inlet valve','Stirrer','Dye pump','Water pump','Deploy','Single']
                            
        sldNames = ['Blue','Orange','Red','LED4']

        for name in self.chkBoxNames:
           chkBox = QtGui.QPushButton(name)
           chkBox.setCheckable(True)
           chkBox.setObjectName(name)
           idx = self.chkBoxNames.index(name)
           self.group.addButton(chkBox, idx)
           grid.addWidget(chkBox, idx, 0)
        self.group.buttonClicked.connect(self.checked)
        
        sldRow = len(self.chkBoxNames)+1
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
        
        
        

    def checked(self, sender):
        if sender.objectName() == 'Spectrophotometer':
           if sender.isChecked():
              self.timer.start(500)
           else:
              self.timer.stop()
              
        if sender.objectName() == 'Take dark':
           self.on_dark_clicked()
           sender.setChecked(False)

        if sender.objectName() == 'Stirrer':
           self.instrument.set_line(STIP, sender.isChecked())

        if sender.objectName() == 'Water pump':
           self.instrument.set_line(WPUM, sender.isChecked())

        if sender.objectName() == 'LEDs':
           self.set_LEDs(sender.isChecked())

        if sender.objectName() == 'Dye pump':
           self.instrument.cycle_line(DYEP, 2)
           sender.setChecked(False)

        if sender.objectName() == 'Inlet valve':
           self.instrument.set_TV(sender.isChecked())

        if sender.objectName() == 'Deploy':
           self.on_deploy_clicked(sender.isChecked())

        if sender.objectName() == 'Single':
           self.on_bottle_clicked()
           sender.setChecked(False)

        if sender.objectName() == 'Enable PUCK protocol':
           if sender.isChecked():
              if HOST_EXIST:
                 self.puckEm.enter_instrument_mode([])
              else:
                 sender.setChecked(False)
           else:
              self.puckEm.puckMode = False
              self.puckEm.timerHostPoll.stop() 
    
           
    def chkBox_caption(self, chkBoxName, appended):
        self.group.button(self.chkBoxNames.index(chkBoxName)).setText(chkBoxName+'   '+appended)

    def check(self, chkBoxName, newChk):
        self.group.button(self.chkBoxNames.index(chkBoxName)).setChecked(newChk)
   
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

    def simulate(self):
        self.puckEm.LAST_pH = 8+random.gauss(0,0.05)
        self.puckEm.LAST_CO2 = 350+random.gauss(0,10)
        self.puckEm.LAST_TA = 2200+random.gauss(0,25)
        print '%.1f %.4f %.1f' %(self.puckEm.LAST_CO2,self.puckEm.LAST_pH,self.puckEm.LAST_TA)

 #________________________________________________________________________________________________________               

    #### combo box management #############################
    def on_combo_clicked(self, text):
        
        comboItems = ['Set integration time','Set averaging scans',
                      'Set sampling interval','Auto adjust','Set pCO2 data saving rate',
                      'BOTTLE setup','UNDERWAY setup']
        choice = comboItems.index(text)
        if choice == 0:
            self.on_intTime_clicked()
        if choice == 1:
            self.on_scans_clicked() 
        if choice == 2:
            self.on_samT_clicked()
        if choice == 4:
            self.on_data_saving_rate_clicked()
        if choice == 3:
            self.on_autoAdjust_clicked()
        if choice == 5:
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
            print self.instrument.UNDERWAY
            
            
        
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
        time, ok = QtGui.QInputDialog.getInt(None, 'Set underway sampling interval','s',self.instrument.samplingInterval,30,3600,30)
        if ok:
            self.instrument.samplingInterval = time
            
    
    def on_autoAdjust_clicked(self):
        
        DC1,DC2, sptIt, Ok  = self.instrument.auto_adjust()
        self.sliders[0].setValue(DC1)
        self.sliders[1].setValue(DC2)
        self.instrument.specIntTime = sptIt
        self.instrument.specAvScans = 3000/sptIt
        
      
    #__________________________________________________   

    def refresh_settings(self):
        settings = 'Settings:\nSpectrophotometer integration time : %d ms\nSpectrophotometer averaging scans : %d\nPumping time : %d\nWaiting time before scans : %d\nMixing time : %d\nDye addition sequence : %s\nSampling interval : %d\nData folder : %s' % (self.instrument.specIntTime, self.instrument.specAvScans,self.instrument.pumpT, self.instrument.waitT, self.instrument.mixT, self.instrument.dyeAdditions, self.instrument.samplingInterval, self.folderPath)
        self.textBox.setText(settings)
            
                
    
        
      
#******************************************************************************************************************

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
        
        if SENS_EXIST:
           portSens.write(QUERY_CO2)
           resp = portSens.read(15)
           try:
               value =  float(resp[3:])
               value = self.instrument.ftCalCoef[6][0]+self.instrument.ftCalCoef[6][1]*value
           except ValueError:
               value = 0
           self.instrument.franatech[6] = value
           self.puckEm.LAST_CO2 = self.instrument.franatech[6]
        
           portSens.write(QUERY_T)
           resp = portSens.read(15)
           try:
               self.instrument.franatech[7] = float(resp[3:])
           except ValueError:
               self.instrument.franatech[7] = 0
         
           for ch in range(5):
              V = self.instrument.get_Vd(2,ch+1)
              X = 0
              for i in range(2):
                   X += self.instrument.ftCalCoef[ch][i] * pow(V,i)
              self.instrument.franatech[ch] = X
              text += VAR_NAMES[ch]+': %.2f\n'%X

           self.puckEm.LAST_PAR[2] = self.instrument.salinity
           self.puckEm.LAST_PAR[0]= self.instrument.franatech[0]   #pCO2 water loop temperature
           WD = self.instrument.get_Vd(3,6)  
           text += VAR_NAMES[5]+ str (WD<0.04) + '\n'
           text += VAR_NAMES[6]+': %.1f\n'%self.instrument.franatech[6] + VAR_NAMES[7]+': %.1f\n'%self.instrument.franatech[7]
           
        self.textBoxSens.setText(text)

        if FIA_EXIST: 
           # polling HydroFIA-TA 
           rx = portFIA.read(300)
           if rx != '':
              sentence = rx.split(',')
              logFile = open(self.folderPath + 'FIA-TA.log','a')
              logFile.write(rx+'\n')
              if len(sentence)>10:
                 sample_name = sentence[4]
                 portFIA.write(STOP)
                 rx = portFIA.read(300)
                 logFile.write(rx+'\n')
                 self.statusFIA = True
                 try:
                    self.puckEm.LAST_TA = float(sentence[7])
                 except ValueError:
                    self.puckEm.LAST_TA = 1   
                 print self.puckEm.LAST_TA
              logFile.close()
           
           
    def save_pCO2_data(self):
        d = self.instrument.franatech
        t = datetime.now() 
        label = t.isoformat('_')
        labelSample = label[0:19]
        logStr = '%s,%.2f,%.1f,%.1f,%.2f,%d,%.1f,%d\n' %(labelSample,d[0],d[1],d[2],d[3],d[4],d[6],d[7])
        with open(self.folderPath + 'pCO2.log','a') as logFile:
            logFile.write(logStr)
         
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        sock.sendto(logStr, (UDP_IP, UDP_SEND))
        sock.close()   

    def sample_alkalinity(self):
        if self.statusFIA:
           print 'Sampling alkalinity'
           self.statusFIA = False
           portFIA.write(SET_SAL+'%.2f\r\n' %self.instrument.salinity)
           print portFIA.read(100)
           t = datetime.now()
           flnmString = t.isoformat('-')
           sampleName = flnmString[0:4]+flnmString[5:7]+flnmString[8:13]+flnmString[14:16]+flnmString[17:19]
           portFIA.write(SET_SAMPLE_NAME + sampleName +TCHAR)
           print portFIA.read(100)
           portFIA.write(RUN)
           print portFIA.read(100)

        
    def on_deploy_clicked(self, state):
        newText =''
        if state:
           self.instrument.flnmStr=''
           self.tsBegin = (datetime.now()-datetime(1970,1,1)).total_seconds()
           nextSample = datetime.fromtimestamp(self.tsBegin + self.instrument.samplingInterval)
           nextSampleTA = datetime.fromtimestamp(self.tsBegin + TA_SAMP_INT)
           text = 'instrument deployed\nNext sample %s\n\n' %(nextSample.isoformat())
           if FIA_EXIST:
              self.timerFIA.start(TA_SAMP_INT*1000)
              text += 'HydroFIA-TA deployed\nNext sample %s' % (nextSampleTA.isoformat())
           self.textBox.setText(text)
           self.timerUnderway.start(self.instrument.samplingInterval*1000)     
        else:
           self.timerUnderway.stop()
           self.timerFIA.stop()
           self.textBox.setText('Cbon is not deployed')
                
    def on_bottle_clicked(self):
        self.check('Spectrophotometer',False)
        self.timer.stop()
        t = datetime.now()
        flnmString = t.isoformat('_')
        self.instrument.timeStamp = flnmString
        self.instrument.flnmStr = flnmString[0:4]+flnmString[5:7]+flnmString[8:10]+flnmString[11:13]+flnmString[14:16]    
        text, ok = QtGui.QInputDialog.getText(None, 'Sample name', self.instrument.flnmStr)
        if ok:
            if text != '':
                self.instrument.flnmStr = text
            self.instrument.reset_lines()
            print 'Start bottle ',self.instrument.flnmStr
            self.sample(self.instrument.BOTTLE)
            print 'Done'
            self.check('Single',False)
            self.instrument.spectrometer.set_scans_average(1)
        self.timer.start()
        self.check('Spectrophotometer',True)

            
    def underway(self):
        print('Inside underway...')
        self.check('Spectrophotometer',False)    # stop the spectrophotometer update precautionally
        self.timer.stop()
        self.instrument.adjust_LED(0,self.sliders[0].value())
        self.instrument.adjust_LED(1,self.sliders[1].value())
        self.instrument.adjust_LED(2,self.sliders[2].value())
        self.instrument.reset_lines()
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans)
        
        t = datetime.now()
        flnmString = t.isoformat('_')
        self.instrument.flnmStr = flnmString[0:4]+flnmString[5:7]+flnmString[8:13]+flnmString[14:16]+flnmString[17:19]
        self.instrument.timeStamp = flnmString
        self.tsBegin = (datetime.now()-datetime(1970,1,1)).total_seconds()

        print 'sampling...'
        self.sample(self.instrument.UNDERWAY)
        print 'done...'

        #self.set_LEDs(False)
        #self.check('LEDs',False)
        self.instrument.spectrometer.set_scans_average(1)
        
        nextSample = datetime.fromtimestamp(self.tsBegin + self.instrument.samplingInterval)
        oldText = self.textBox.toPlainText()
        self.textBox.setText(oldText + '\n\nNext pH sample %s' % nextSample.isoformat())
        self.check('Spectrophotometer',True)    # stop the spectrophotometer update precautionally
        self.timer.start()
    
        
    def sample(self, parString):

        if not self.instrument.pumping:
            return
        if self.instrument._autodark:
            now = datetime.now()
            if (self.instrument.last_dark is None) or ((now - self.instrument.last_dark) >= self.instrument._autodark):
				print 'New dark required'
				self.on_dark_clicked()
        else:
            print 'next dark at %s' % ((self.instrument.last_dark + dt).strftime('%Y-%m%d %H:%S'))
        self.set_LEDs(True)
        self.check('LEDs', True)

        parList = parString.split('_')
        pT, mT, wT, dA = int(parList[0]),int(parList[1]),int(parList[2]),str(parList[3])

        self.instrument.evalPar =[]
        self.instrument.spectrometer.set_scans_average(self.instrument.specAvScans)
        if pT>0:
            self.instrument.set_line(WPUM,True)
            self.instrument.set_line(STIP,True)
            self.instrument.wait(pT)
            self.instrument.set_line(STIP,False)
            self.instrument.set_line(WPUM,False)
        self.instrument.set_TV(True)
        self.instrument.wait(wT)

        print 'Measuring blank...'
        self.instrument.spCounts[1] = self.instrument.spectrometer.get_corrected_spectra()
        dark = self.instrument.spCounts[0]
        bmd = np.clip(self.instrument.spCounts[1] - dark,1,16000)
        for pinj in range(len(dA)):
            shots = int(dA[pinj])
            print 'Injection %d:, shots %d' %(pinj, shots)
            self.instrument.set_line(STIP, True)
            self.instrument.cycle_line(DYEP, shots)
            self.instrument.wait(mT)
            self.instrument.set_line(STIP, False)
            self.instrument.wait(wT)
            postinj = self.instrument.spectrometer.get_corrected_spectra()
            self.instrument.spCounts[2+pinj] = postinj    
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

        self.instrument.set_TV(False)

        flnm = open(self.folderPath + self.instrument.flnmStr +'.spt','w')
        txtData = ''
        for i in range(2+len(dA)):
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
        self.puckEm.LAST_PAR[1]= pHeval[1]
        self.puckEm.LAST_pH = pHeval[0]
        
        

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
                
        
    
def main():
    
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
        
if __name__ == '__main__':
    main()
