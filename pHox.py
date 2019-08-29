#! /usr/bin/python

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
   
# ------- SSR settings
WPUM = 1 # water pump slot
DYEP = 2 # dye pump slot
STIP = 3 # stirrer slot
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

class STSVIS(object): 
    ## Ocean Optics STS protocol manager ##
    # DO NOT CHANGE WITHOUT PROPER KNOWLEDGE OF THE DEVICE USB PROTOCOL #
    # spectrophotometer functions, used for pH 

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

class Cbon(object):
    # Instrument constructor #
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

        #TODO: em heritage,to fix
        # HEll line 
        self.BOTTLE='00_5_3_1111'

        self.UNDERWAY='00_5_3_1111'

        self.load_config()

        #setup PWM and SSR lines
        for pin in range (4):
            self.rpi.set_mode(self.pwmLines[pin],pigpio.OUTPUT)
            self.rpi.set_PWM_frequency(self.pwmLines[pin], 100)
            self.rpi.set_PWM_dutycycle(self.pwmLines[pin],0)
            self.rpi.set_mode(self.ssrLines[pin], pigpio.OUTPUT)

        print 'calculating wavelengths...\n'
        self.wvls = self.calc_wavelengths(self.spectrometer.wvlCalCoeff)
        
        self.reset_lines()
        
        udp = threading.Thread(target=self.udp_server)
        udp.start()

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
        with open('config.json') as json_file:
            j = json.load(json_file)

        default =   j['default']
        franatech = j['franatech']

        print ('Loading pHaro parameters...')

        self.HI =  int(default['HI-'])
        self.I2 =  int(default['I2-'])
        self.Iso = int(default['ISO'])
        self.NIR = int(default['NIR-'])
        self._autostart = bool(default['AUTOSTART'])
        self._automode  = default['AUTOSTART_MODE']

        print ('AUTOSTART',self._autostart,'AUTOSTART_MODE',self._automode)
        self.DURATION =  int(default['DURATION'])

        #TODO: should be replaced by value from config?
        self.AUTODARK =  int(default['AUTODARK'])
        self._autodark  = None

        self.vNTCch =    int(default['T_PROBE_CH'])
        if not(self.vNTCch in range(9)):
            self.vNTCch = 8

        self._autotime  = None
        self._autolen   = None
        self._autostop  = None

        self._deployed  = False
        self.last_dark  = None

        self.molAbsRats = default['MOL_ABS_RATIOS']
        print ('Molar absorption ratios: ',self.molAbsRats)

        self.pwmLines =  default['PWM_LINES']
        print ('Using default BCM lines for PWM LEDs: ',self.pwmLines)
        print ('0 = will be skipped')

        self.ssrLines = default['GPIO_SSR']
        print ('Using default BCM lines for SSRs: ',self.ssrLines)

        self.GPIO_TV = default['GPIO_TV']
        print ('Using default BCM lines for bistable valve driver: ',self.GPIO_TV)

        # NTC calibration coefficients
        self.ntcCalCoef = default['NTC_CAL_COEF']
        # this was cardcoded if Value Error self.ntcCalCoef = [91.377, 18.676,0,0]
        print ('NTC calibration coefficients :',self.ntcCalCoef, '\n')

        self.dye = default['DYE'] 
        #type of dye(default value, will be changed inside gui )
        self.dyeCal = default['DYE_CAL']
        print ('Dye calibration coefficients (ml_dye/Aiso, S, ml):')
        print (self.dyeCal,'\n')

        self.LED1 = default["LED1"]
        self.LED2 = default["LED2"]
        self.LED3 = default["LED3"]
        ### Franatech calibration coefficients ###

        # Why do we need 10 row here?
        self.ftCalCoef = np.zeros((10, 2))
        self.ftCalCoef[0] = franatech['WAT_TEMP_CAL']
        print ('Water temperature calibration coefficients :',self.ftCalCoef[0])

        self.ftCalCoef[1] = franatech['WAT_FLOW_CAL']
        print ('Water flow calibration coefficients :', self.ftCalCoef[1])

        self.ftCalCoef[2] = franatech['WAT_PRES_CAL']
        print ('Water pressure calibration coefficients :',self.ftCalCoef[2])

        #nominal self.ftCalCoef[3] = [-75,53.2368]
        self.ftCalCoef[3] = franatech['AIR_TEMP_CAL']
        print ('Air temperature calibration coefficients :',self.ftCalCoef[3])

        self.ftCalCoef[4] = franatech['AIR_PRES_CAL']
        print ('Air pressure calibration coefficients :',self.ftCalCoef[4])

        self.ftCalCoef[5] = franatech['WAT_DETECT']
        print ('Water detection voltage threshold :',self.ftCalCoef[5])

        self.ftCalCoef[6] = franatech['CO2_FRAC_CAL']
        print ('CO2 molar fraction calibration coefficients :',self.ftCalCoef[6])
        print (self.ftCalCoef)

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
            arg = (R - e1)/(e2 - R*e3)
            pH = 0.0047 + pK + log10(arg)
        elif self.dye == 'MCP':
            e1=-0.007762+(4.5174*10**-5)*T
            e2e3=-0.020813+((2.60262*10**-4)*T)+(1.0436*10**-4)*(fcS-35)
            arg = (R - e1)/(1 - R*e2e3)
            pK = (5.561224-(0.547716*fcS**0.5)+(0.123791*fcS)-(0.0280156*fcS**1.5)+
                 (0.00344940*fcS**2)-(0.000167297*fcS**2.5)+
                 ((52.640726*fcS**0.5)*T**-1)+(815.984591*T**-1))
            pH= pK + np.log10(arg)
            print 'pK = ', pK,'  e1 = ',e1, '  e2e3 = ',e2e3, ' Anir = ',Anir
           
            ## to fit the log file
            e2=e2e3
            e3=-99
        else:
            raise ValueError('wrong DYE: ' + self.dye)

        print 'R = %.5f,  Aiso = %.3f' %(R,Aiso)
        print ('dye: ', self.dye)
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
