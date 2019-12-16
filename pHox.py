#! /usr/bin/python

import json, warnings
import os,sys
os.chdir('/home/pi/pHox')
os.system('clear')
import usb, usb.core
from ADCDACPi import ADCDACPi
from ADCDifferentialPi import ADCDifferentialPi
import struct, time
import RPi.GPIO as GPIO
from datetime import datetime, timedelta
import pigpio
from PyQt5 import QtGui, QtCore
import numpy as np
import pandas as pd 
import util,random,udp
from scipy import stats

class STSVIS(object): 
    ## Ocean Optics STS protocol manager ##
    # DO NOT CHANGE WITHOUT PROPER KNOWLEDGE OF THE DEVICE USB PROTOCOL #
    # spectrophotometer functions, used for pH 

    def __init__(self):
        # Create object (connection) for the device 
        self._dev = usb.core.find(idVendor=0x2457, idProduct=0x4000)
        if (self._dev == None):
            raise ValueError ('OceanOptics STS: device not found\n')
        else:
            print ('Initializing STS spectrophotometer...')
        
        self.EP1_out = 0x01 # endpoint address 
        self.EP1_in = 0x81
        self.EP2_in = 0x82
        self.EP2_out = 0x02

        self.gcsCmd = self.build_packet(b'\x00\x10\x10\x00',b'\x00',b'\x00\x00\x00\x00')
        self.pixels = 1024
        self.nWvlCalCoeff = b'\x00\x01\x02\x03'
        self.reset_device()
        time.sleep(0.5)
        self.wvlCalCoeff = self.get_wvlCalCoeff()
               
    def build_packet(self,messageType, immediateDataLength, immediateData):
        headerTop = b'\xC1\xC0'
        protocolVersion = b'\x00\x10'
        flags = b'\x00\x00'
        errorNumber = b'\x00\x00'
        regarding = b'\x00'*4
        reserved = b'\x00'*6
        checksumType = b'\x00'
        unused = b'\x00'*12
        bytesRemaining = b'\x14\x00\x00\x00'
        checksum = b'\x00'*16
        footer = b'\xC5\xC4\xC3\xC2'
        packet = headerTop + protocolVersion + flags + errorNumber + messageType +\
            regarding + reserved + checksumType + immediateDataLength +\
            immediateData + unused + bytesRemaining + checksum + footer
        return packet
    
    def reset_device (self):
        msgType = b'\x00'*4
        immDataLength = b'\x00'
        immData = b'\x00'*4
        try:
            self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        except usb.core.USBError:
            pass
        time.sleep(1.5)
        self._dev = usb.core.find(idVendor=0x2457, idProduct=0x4000)
        if self._dev is None:
            raise ValueError('Device not found')        
            
    def set_integration_time(self,time_ms):
        msgType= b'\x10\x00\x11\x00'
        immDataLength = b'\x04'
        immData = struct.pack('<I',time_ms*1000)
        self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        time.sleep(0.5)

    def set_scans_average(self,nscans):
        print ('nscans',nscans)
        msgType= b'\x10\x00\x12\x00'
        immDataLength = b'\x02'
        print ('set_scans_average, struct pack')
        immData = struct.pack('<H',int(nscans)) + b'\x00\x00'
        print ('send message to instr, set scan average')
        self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        time.sleep(0.5)

    def get_wvlCalCoeff(self):
        #get the coefficients
        print ('Getting wavelength calibration coefficients...')
        msgType = b'\x01\x01\x18\x00'
        immDataLength= b'\x01'

        wvlCalCoeff = []
        for i in range(4):
            immData = struct.pack('B',i) + b'\x00\x00\x00'
            self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
            rx_packet = self._dev.read(self.EP1_in, 64, timeout=1000) #receive message 
            wvlCalCoeff.append(float(struct.unpack('<f',struct.pack('4B',*rx_packet[24:28]))[0]))
        return wvlCalCoeff
          
    def get_corrected_spectra(self):
        self._dev.write(self.EP1_out, self.gcsCmd)
        rx_packet = self._dev.read(self.EP1_in, 64+2048, timeout=10000)
        spec = rx_packet[44:2092]
        spectralCounts = struct.unpack('<1024H',struct.pack('2048B',*spec))
        spectralCounts = np.array(spectralCounts,dtype=float)
        return spectralCounts

class pH_instrument(object):
    # Instrument constructor #
    def __init__(self):
        # For signaling to threads
        self._exit = False 
        
        #initialize PWM lines
        self.rpi = pigpio.pi()

        self.evalPar = []
        

        self.spectrometer = STSVIS()

        self.nlCoeff = [1.0229, -9E-6, 6E-10] # we don't know what it is  

         #spectrometer integration time (ms)
        self.specAvScans = 6 # Spectrums to take, they will be averaged to make one measurement 

        # Ferrybox data
        self.fb_data = udp.Ferrybox
        
        self.tsBegin = float
        self.status = [False]*16
        self.intvStatus = False
        
        #self.CO2UpT = 5
        
        self.flnmStr = ''
        self.timeStamp = ''
        
        self.load_config()        
        self.spectrometer.set_integration_time(self.specIntTime)
        self.spectrometer.set_scans_average(1)
        
        self.adc = ADCDifferentialPi(0x68, 0x69, 14)
        self.adc.set_pga(1)
        self.adcdac = ADCDACPi()


        #setup PWM and SSR lines
        for pin in range (4):
            self.rpi.set_mode(self.pwmLines[pin],pigpio.OUTPUT)
            self.rpi.set_PWM_frequency(self.pwmLines[pin], 100)
            self.rpi.set_PWM_dutycycle(self.pwmLines[pin],0)
            self.rpi.set_mode(self.ssrLines[pin], pigpio.OUTPUT)

        self.reset_lines()

    def load_config(self):
        with open('config.json') as json_file:
            j = json.load(json_file)
        default =   j['default']
        try: 
            self.textBox.append('Loading config.json')
        except: 
            pass

        self.dye = default['DYE'] 

        if self.dye == 'MCP':
            self.HI =  int(default['MCP_wl_HI'])
            self.I2 =  int(default['MCP_wl_I2'])         
        elif self.dye == "TB":   
            self.HI =  int(default['TB_wl_HI'])
            self.I2 =  int(default['TB_wl_I2'])
        self.THR = int(default["LED_THRESHOLD"])
        self.NIR = int(default['NIR-'])
        self._autostart = bool(default['AUTOSTART'])
        self._automode  = default['AUTOSTART_MODE']

        self.DURATION =  int(default['DURATION'])

        #TODO: should be replaced by value from config?
        self.AUTODARK =  int(default['AUTODARK'])
        
        self._autodark  = None
        self._autotime  = None
        self._autolen   = None
        #self._autostop  = None #Not used
        #self._deployed  = False #Not used
        self.last_dark  = None #Not used

        self.vNTCch =    int(default['T_PROBE_CH'])
        if not(self.vNTCch in range(9)):
            self.vNTCch = 8

        self.samplingInterval = int(default["PH_SAMPLING_INTERVAL_SEC"])
        self.pumpTime = int(default["pumpTime"])
        self.mixT = int(default["mixTime"])
        self.waitT = int(default["waitTime"])
        self.ncycles= int(default["ncycles"]) # Former dA
        self.nshots = int(default["dye_nshots"])
         
        self.molAbsRats = default['MOL_ABS_RATIOS']

        self.pwmLines =  default['PWM_LINES']
        self.ssrLines = default['GPIO_SSR']
        #TODO: Replace ssrlines with new lines 
        self.wpump_slot = default["WPUMP_SLOT"]
        self.dyepump_slot = default["DYEPUMP_SLOT"]
        self.stirrer_slot = default["STIRR_SLOT"]

        self.extra_slot = default["EXTRA_SLOT"] #empty for now
        self.GPIO_TV = default['GPIO_TV']

        # NTC Temperature calibration coefficients
        self.TempCalCoef = default['NTC_CAL_COEF']

        # self.dyeCal = default['DYE_CAL']
        self.Cuvette_V = default["CUVETTE_V"] #ml
        self.dye_vol_inj = default["DYE_V_INJ"]

        self.LED1 = default["LED0"]
        self.LED2 = default["LED1"]
        self.LED3 = default["LED2"]
        self.specIntTime = default['Spectro_Integration_time']
        self.deployment = default['Deployment_mode']
        self.folderPath ='/home/pi/pHox/data/' # relative path

        if not os.path.exists(self.folderPath):
            os.makedirs(self.folderPath)

    def calc_wavelengths(self,coeffs):   # assign wavelengths to pixels and find pixel number of reference wavelengths
        wvls = np.zeros(self.spectrometer.pixels, dtype=float)
        pixels = np.arange(self.spectrometer.pixels)

        # all wvl we get from the instrument, calculated from the coefficients 
        #TODO:  wvls should be a header for the .spt log file 1024 wv values 
        wvls = coeffs[0] + coeffs[1]* pixels + coeffs[2]*(pixels**2) + coeffs[3]*(pixels**3)
        
        self.wvlPixels = []

        # find the indices of pixels that give 
        # the wavelength corresponding to 
        # self.HI, self.I2, self.NIR

        for wl in (self.HI, self.I2, self.NIR):
            self.wvlPixels.append(self.find_nearest(wvls,wl))
        return wvls

    def find_nearest(self, items, value):
        idx = (abs(items-value)).argmin()
        return idx

    def get_sp_levels(self,pixel):
        spec = self.spectrometer.get_corrected_spectra()
        return spec[pixel],spec.max()

    def adjust_LED(self, led, LED):
        self.rpi.set_PWM_dutycycle(self.pwmLines[led],LED)

    def find_LED(self,led_ind,adj,curr_value):
        print ('led_ind',led_ind)
        SAT = 16000
        LED = curr_value 

        while LED < 100: 
            self.adjust_LED(led_ind, LED)
            pixelLevel,maxLevel =  self.get_sp_levels(self.wvlPixels[led_ind])
            dif_counts = self.THR - pixelLevel

            if (dif_counts > 500 and LED < 99) : 
                dif_LED = (dif_counts * 30 / maxLevel)            
                LED += dif_LED  
                LED = min(99,LED)

            elif dif_counts > 500 and LED == 99: 
                break

            elif dif_counts < -500 and LED>1:
                dif_LED = (dif_counts * 30 / maxLevel)              
                LED += dif_LED  
                LED = max(1,LED)

            elif dif_counts < -500 and LED == 1: 
                print ('too high values')
                break   

            elif dif_counts < 500 and dif_counts > -500: 
                adj = True
                break            

            elif dif_counts < (self.THR - SAT): 
                print ('saturation')
                break

        return LED,adj

    def auto_adjust(self):
        
        #self.textBox.setText('Autoadjusting leds')
        sptItRange = [500,750,1000,1500,3000]
        self.spectrometer.set_scans_average(1)

        for sptIt in sptItRange:
            adj1,adj2,adj3 = False, False, False
            LED1,LED2,LED3 = None, None, None

            self.spectrometer.set_integration_time(sptIt)
            print ('Trying %i ms integration time...' % sptIt)

            LED1,adj1 = self.find_LED(led_ind = 0,adj = adj1,
                                    curr_value = self.LED1)
            if adj1:
                LED2,adj2 = self.find_LED(led_ind = 1,adj = adj2,
                                        curr_value = self.LED2)

                if adj2:    
                    LED3,adj3 = self.find_LED(led_ind = 2,adj = adj3, 
                                        curr_value = self.LED3)    

            if (adj1 and adj2 and adj3):
               print ('Levels adjusted')
               break 

        if not adj1 or not adj2 or not adj3:
            result = False
        else:
            result = True 

        return LED1,LED2,LED3,sptIt,result

    def print_Com(self, port, txtData):
        port.write(txtData)

    def wait(self, secs):
        t0 = time.time()
        while (time.time()-t0)<secs:
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                print('skipped')
                break

    def reset_lines(self):
        # set values in outputs of pins 
        self.rpi.write(   self.wpump_slot, 0)
        self.rpi.write( self.dyepump_slot, 0)
        self.rpi.write( self.stirrer_slot, 0)
        self.rpi.write(   self.extra_slot, 0)

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
     
    def set_Valve(self, status):
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

    '''def movAverage(self, dataSet, nPoints):
        spAbsMA = dataSet
        for i in range(3,len(dataSet)-3):
            v = dataSet[i-nPoints:i+nPoints+1]
            spAbsMA[i]= np.mean(v)
        return spAbsMA'''

    def get_Vd(self, nAver, channel):
        V = 0.0000
        for i in range (nAver):
            V += self.adc.read_voltage(channel)
        return V/nAver

    def calc_pH_no_eval(self,absSp, vNTC,dilution,vol_injected):
        #for i in range(4):
        vNTC2 = self.get_Vd(3, self.vNTCch)
        Tdeg = (self.TempCalCoef[0]*vNTC2) + self.TempCalCoef[1]

        T = 273.15 + Tdeg
        A1,A2,Anir =   (absSp[self.wvlPixels[0]], 
                        absSp[self.wvlPixels[1]],
                        absSp[self.wvlPixels[2]])

        S_corr = self.fb_data['salinity'] * dilution 

        R = A2/A1
        
        if self.dye == 'TB':
            e1 = -0.00132 + 1.6E-5*T
            e2 = 7.2326 + -0.0299717*T + 4.6E-5*(T**2)
            e3 = 0.0223 + 0.0003917*T
            pK = 4.706*(S_corr/T) + 26.3300 - 7.17218*np.log10(T) - 0.017316*S_corr
            arg = (R - e1)/(e2 - R*e3)
            pH = 0.0047 + pK + np.log10(arg)

        elif self.dye == 'MCP':
            e1=-0.007762+(4.5174*10**-5)*T
            e2e3=-0.020813+((2.60262*10**-4)*T)+(1.0436*10**-4)*(S_corr-35)
            arg = (R - e1)/(1 - R*e2e3)
            pK = (5.561224-(0.547716*S_corr**0.5)+(0.123791*S_corr)-(0.0280156*S_corr**1.5)+
                 (0.00344940*S_corr**2)-(0.000167297*S_corr**2.5)+
                 ((52.640726*S_corr**0.5)*T**-1)+(815.984591*T**-1))
            if arg > 0: 
                pH = pK + np.log10(arg)
            else:
                pH = 99.9999

            ## to fit the log file
            e2,e3 =e2e3,-99
        else:
            raise ValueError('wrong DYE: ' + self.dye)
            
        return  [pH, pK, e1, e2, e3, vNTC,
                            self.fb_data['salinity'], A1, A2,
                            Tdeg, S_corr, Anir,vol_injected]

    def pH_eval(self,evalPar_df):

        dpH_dT = -0.0155
        evalAnir =  evalPar_df['Anir'].mean()
        T_lab = evalPar_df["Tdeg"][0]
        pH_lab = evalPar_df["pH"][0]
        pH_t_corr = evalPar_df["pH"] + dpH_dT * (evalPar_df["Tdeg"] -T_lab) 
        nrows = evalPar_df.shape[0]

        if nrows>1:
            x = evalPar_df['Vol_injected'].values
            y = pH_t_corr.values
            slope1, intercept, r_value,_, _ = stats.linregress(x,y) 
            if r_value**2  > 0.9 :
                pH_lab = intercept 
                print ('r_value **2 > 0.9')
            else: 
                x = x[:-2]
                y = y[:-2]
                slope2, intercept, r_value,_, _ = stats.linregress(x,y) 
                if r_value**2  > 0.9 :  
                    pH_lab = intercept
                else: 
                    pH_t_corr[0]

        perturbation = slope1 
        pH_insitu = pH_lab + dpH_dT * (T_lab - self.fb_data['temperature'])
        return (pH_lab, T_lab, perturbation, evalAnir) #pH_insitu,self.fb_data['temperature']       

