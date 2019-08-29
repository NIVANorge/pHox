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

import random


UDP_SEND = 6801
UDP_RECV = 6802
UDP_IP   = '192.168.0.2'

#i2c_helper = ABEHelpers()
#bus = i2c_helper.get_smbus()
adc = ADCDifferentialPi(0x68, 0x69, 14)
adc.set_pga(1)
adcdac = ADCDACPi()

   
# ------- SSR settings
#WPUM = 1 # water pump slot
#DYEP = 2 # dye pump slot
#STIP = 3 # stirrer slot

# sampling intervals (seconds)
# TODO: to config file
pH_SAMP_INT = 600


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
        
        self.CO2UpT = 5
        
        self.flnmStr = ''
        self.timeStamp = ''
        self.spectrometer.set_integration_time(self.specIntTime)
        self.spectrometer.set_scans_average(1)

        #TODO: em heritage,to fix
        # HEll line 
        # self.BOTTLE='00_5_3_1111'
        # self.UNDERWAY='00_5_3_1111'

        self.load_config()

        #setup PWM and SSR lines
        for pin in range (4):
            self.rpi.set_mode(self.pwmLines[pin],pigpio.OUTPUT)
            self.rpi.set_PWM_frequency(self.pwmLines[pin], 100)
            self.rpi.set_PWM_dutycycle(self.pwmLines[pin],0)
            self.rpi.set_mode(self.ssrLines[pin], pigpio.OUTPUT)

        print 'calculating wavelengths...\n'
        self.wvls = self.calc_wavelengths(self.spectrometer.wvlCalCoeff)
        print ("wavelengths", self.wvls)
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

        self.pT = 0 
        self.mT = 5
        self.wT = 3
        self.dA = 4
        self.nshots = 1
        
        self.molAbsRats = default['MOL_ABS_RATIOS']
        print ('Molar absorption ratios: ',self.molAbsRats)

        self.pwmLines =  default['PWM_LINES']
        print ('Using default BCM lines for PWM LEDs: ',self.pwmLines)
        print ('0 = will be skipped')

        self.ssrLines = default['GPIO_SSR']
        #TODO: Replace ssrlines with new lines 
        self.wpump_slot = default["WPUMP_SLOT"]
        self.dyepump_slot = default["DYEPUMP_SLOT"]
        self.stirrer_slot = default["STIRR_SLOT"]
        self.extra_slot = default["EXTRA_SLOT"] #empty for now
  
        #WPUM = 1 # water pump slot
        #DYEP = 2 # dye pump slot
        #STIP = 3 # stirrer slot

        self.GPIO_TV = default['GPIO_TV']

        # NTC Temperature calibration coefficients
        self.ntcCalCoef = default['NTC_CAL_COEF']
        print ('NTC calibration coefficients :',self.ntcCalCoef, '\n')

        self.dye = default['DYE'] 
        #type of dye(default value, will be changed inside gui )
        print ('Dye type',self.dye,'\n')

        # self.dyeCal = default['DYE_CAL']
        self.Cuvette_V = default["CUVETTE_V"] #ml
        self.dye_vol_inj = default["DYE_V_INJ"]

        self.LED1 = default["LED1"]
        self.LED2 = default["LED2"]
        self.LED3 = default["LED3"]


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
    #
    def reset_lines(self):
        # set values in outputs of pins 
        self.rpi.write(   self.wpump_slot, 0)
        self.rpi.write(self.dyepump_slot, 0)
        self.rpi.write(self.stirrer_slot, 0)
        self.rpi.write(  self.extra_slot, 0)

    def set_line (self, line, status):
        # change status of the relay 
        self.rpi.write(line, status)

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
        chEn = self.GPIO_TV[0]
        ch1 =  self.GPIO_TV[1]
        ch2 =  self.GPIO_TV[2]
        if status:
            ch1= self.GPIO_TV[2]
            ch2= self.GPIO_TV[1]
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
        for i in range(4):
           vNTC2 = self.get_Vd(3, self.vNTCch)
           Tdeg = (self.ntcCalCoef[0]*vNTC2) + self.ntcCalCoef[1]
        print 'T sample : %.2f' %Tdeg

        T = 273.15 + Tdeg

        A1,Aiso,A2,Anir = (absSp[self.wvlPixels[0]], absSp[self.wvlPixels[1]],
                           absSp[self.wvlPixels[2]], absSp[self.wvlPixels[3]])

        # volume in ml
        fcS = self.salinity * (
              (self.Cuvette_V)/(self.dye_vol_inj+self.Cuvette_V))
        R = A2/A1
        
        if self.dye == 'TB':
            e1 = -0.00132 + 1.6E-5*T
            e2 = 7.2326 + -0.0299717*T + 4.6E-5*(T**2)
            e3 = 0.0223 + 0.0003917*T
            pK = 4.706*(fcS/T) + 26.3300 - 7.17218*log10(T) - 0.017316*fcS
            arg = (R - e1)/(e2 - R*e3)
            pH = 0.0047 + pK + log10(arg)
            print 'pK = ', pK,'  e1 = ',e1, '  e2 = ',e2, '  e3 = ',e3, ' Anir = ',Anir
        elif self.dye == 'MCP':
            e1=-0.007762+(4.5174*10**-5)*T
            e2e3=-0.020813+((2.60262*10**-4)*T)+(1.0436*10**-4)*(fcS-35)
            arg = (R - e1)/(1 - R*e2e3)
            pK = (5.561224-(0.547716*fcS**0.5)+(0.123791*fcS)-(0.0280156*fcS**1.5)+
                 (0.00344940*fcS**2)-(0.000167297*fcS**2.5)+
                 ((52.640726*fcS**0.5)*T**-1)+(815.984591*T**-1))
            pH = pK + np.log10(arg)
            print 'pK = ', pK,'  e1 = ',e1, '  e2e3 = ',e2e3, ' Anir = ',Anir
            ## to fit the log file
            e2,e3 =e2e3,-99
        else:
            raise ValueError('wrong DYE: ' + self.dye)

        print 'R = %.5f,  Aiso = %.3f' %(R,Aiso)
        print ('dye: ', self.dye)
        print 'pH = %.4f, T = %.2f' % (pH,Tdeg) 
        self.evalPar.append([pH, pK, e1, e2, e3, vNTC, self.salinity, A1, A2, Aiso, Tdeg, self.dye_vol_inj, fcS, Anir])
        
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

        if n>1:
            x = np.array(range(4)) # fit on equally spaced points instead of Aiso SAM 
            y = np.array(refpH)
            A = np.vstack([x, np.ones(len(x))]).T
            pert,pH_t = np.linalg.lstsq(A, y)[0]

        return (pH_t, refT, self.salinity, pert, evalAnir)