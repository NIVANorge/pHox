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
import random,udp
from scipy import stats
from precisions import precision as prec 
import seabreeze
seabreeze.use('cseabreeze')
from seabreeze.spectrometers import Spectrometer
from seabreeze.spectrometers import list_devices
import seabreeze.cseabreeze as sbb 
from asyncqt import QEventLoop, asyncSlot, asyncClose
import asyncio
import re

class Spectro_seabreeze(object):
    def __init__(self):
        #self.spec =  Spectrometer.from_serial_number('S06356')
        #print (self.spec)
        # try to reset devices
        self.spec =  Spectrometer.from_first_available()
        print (self.spec,'spec')
        f = re.search('STS',str(self.spec))
        if f == None :
            re.search('Flame',str(self.spec))    
        self.spectro_type = f.group()

    @asyncSlot()
    async def set_integration_time(self,time_millisec):
        microsec = time_millisec * 1000
        self.spec.integration_time_micros(microsec)  # 0.1 seconds
        #time.sleep(time_millisec/1.e3)

    def get_wavelengths(self):
        #wavelengths in (nm) corresponding to each pixel of the spectrom
        return self.spec.wavelengths()

    def get_intensities(self,num_avg = 1, correct = True):
        sp = self.spec.intensities(correct_nonlinearity = correct)
        if num_avg > 1: 
            for _ in range(num_avg):
                sp = np.vstack([sp,self.spec.intensities(
                            correct_nonlinearity = correct)])
            sp = np.mean(np.array(sp),axis = 0)        
        return sp

    def set_scans_average(self,num):
        # not supported for FLAME spectrom
        self.spec.scans_to_average(num)
        
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
        print ('inside func set_scans_average nscans',nscans)
        msgType= b'\x10\x00\x12\x00'
        immDataLength = b'\x02'
        immData = struct.pack('<H',int(nscans)) + b'\x00\x00'
        print ('send message to instr, set scan average')
        self._dev.write(self.EP1_out, self.build_packet(msgType, immDataLength, immData))
        time.sleep(5)

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

class Common_instrument(object):
    def __init__(self,panelargs,config_name):
        self.args = panelargs
        self.config_name = config_name
        if self.args.seabreeze:
            self.spectrom = Spectro_seabreeze()    
        else:
            self.spectrom = STSVIS()

        #initialize PWM lines
        self.rpi = pigpio.pi()
        self.fb_data = udp.Ferrybox

        self.load_config()
        self.spectrom.set_integration_time(self.specIntTime)

        self.adc = ADCDifferentialPi(0x68, 0x69, 14)
        self.adc.set_pga(1)
        self.adcdac = ADCDACPi()

        # For signaling to threads
        self._exit = False 

    def reset_lines(self):
        # set values in outputs of pins 
        self.rpi.write(   self.wpump_slot, 0)
        self.rpi.write( self.dyepump_slot, 0)
        self.rpi.write( self.stirrer_slot, 0)
        self.rpi.write(   self.extra_slot, 0)
        
    async def set_Valve(self, status):
        chEn = self.valve_slots[0]
        ch1 =  self.valve_slots[1]
        ch2 =  self.valve_slots[2]
        if status:
            ch1= self.valve_slots[2]
            ch2= self.valve_slots[1]
        self.rpi.write(ch1, True)
        self.rpi.write(ch2 , False)
        self.rpi.write(chEn , True)
        await asyncio.sleep(0.3)
        self.rpi.write(ch1, False)
        self.rpi.write(ch2 , False)
        self.rpi.write(chEn , False)

    def load_config(self):

        with open(self.config_name) as json_file:
            j = json.load(json_file)  

        conf_operational = j['Operational']
        self._autostart = bool(conf_operational['AUTOSTART'])
        self._automode  = conf_operational['AUTOSTART_MODE']
        self.DURATION =  int(conf_operational['DURATION'])
        self.vNTCch =    int(conf_operational['T_PROBE_CH'])
        if not(self.vNTCch in range(9)):
            self.vNTCch = 8
        self.samplingInterval = int(conf_operational["SAMPLING_INTERVAL_SEC"])
        self.pumpTime = int(conf_operational["pumpTime"])
        self.mixT = int(conf_operational["mixTime"])
        self.waitT = int(conf_operational["waitTime"])
        self.ncycles= int(conf_operational["ncycles"])
        self.nshots = int(conf_operational["dye_nshots"])
        self.specAvScans = int(conf_operational["specAvScans"])
        self.wpump_slot = conf_operational["WPUMP_SLOT"]
        self.dyepump_slot = conf_operational["DYEPUMP_SLOT"]
        self.stirrer_slot = conf_operational["STIRR_SLOT"]
        self.extra_slot = conf_operational["SPARE_SLOT"] 

        #TODO: Replace ssrlines with new lines 
        # keep it for now since there is a loop dependent on self.ssrLines
        self.ssrLines = [self.wpump_slot,self.dyepump_slot,self.stirrer_slot,self.extra_slot]

        self.valve_slots = conf_operational['VALVE_SLOTS']
        self.TempProbe_id = conf_operational["TEMP_PROBE_ID"]
        temp = j["TempProbes"][self.TempProbe_id]
        self.temp_iscalibrated = bool(temp["is_calibrated"])
        if self.temp_iscalibrated:
            self.TempCalCoef =  temp["Calibr_coef"]  
        else:
            self.TempCalCoef = conf_operational['"DEF_TEMP_CAL_COEF"']

        self.Cuvette_V = conf_operational["CUVETTE_V"] #ml
        self.dye_vol_inj = conf_operational["DYE_V_INJ"]        
        self.specIntTime = conf_operational['Spectro_Integration_time']
        self.deployment = conf_operational['Deployment_mode']
        self.ship_code = conf_operational['Ship_Code']

        if self.spectrom.spectro_type == "FLAME":
            self.THR = int(conf_operational["LIGHT_THRESHOLD_FLAME"])     
        elif self.spectrom.spectro_type == "STS":
            self.THR = int(conf_operational["LIGHT_THRESHOLD_STS"])     
    def turn_on_relay (self, line):
        self.rpi.write(line, True)

    def turn_off_relay (self, line):
        self.rpi.write(line, False)

    async def pumping(self,pumpTime):    
        self.turn_on_relay(self.wpump_slot) # start the instrument pump
        self.turn_on_relay(self.stirrer_slot) # start the stirrer
        await asyncio.sleep(pumpTime)
        self.turn_off_relay(self.stirrer_slot) # turn off the pump
        self.turn_off_relay(self.wpump_slot) # turn off the stirrer

    def cycle_line (self, line, nCycles):
        ON = 0.3
        OFF = 0.3
        for nCy in range(nCycles):
            self.turn_on_relay(line)
            time.sleep(ON)
            self.turn_off_relay(line)
            time.sleep(OFF)
        pass

    def print_Com(self, port, txtData):
        port.write(txtData)

    def get_Vd(self, nAver, channel):
        V = 0.0000
        for i in range (nAver):
            V += self.adc.read_voltage(channel)
        return V/nAver  

    '''def get_V(self, nAver, ch):
        V = 0.0000
        for i in range (nAver):
            V += self.instrument.adcdac.read_adc_voltage(ch,0) #1: read channel in differential mode
        return V/nAver'''

    def calc_wavelengths(self):   
        '''
        assign wavelengths to pixels 
        and find pixel number of reference wavelengths
        '''
        if not self.args.seabreeze: 
            coeffs =  self.spectrom.wvlCalCoeff
            wvls = np.zeros(self.spectrom.pixels, dtype=float)
            pixels = np.arange(self.spectrom.pixels)
            wvls = (coeffs[0] + coeffs[1]* pixels + 
            coeffs[2]*(pixels**2) + coeffs[3]*(pixels**3))
        else: 
            wvls = self.spectrom.get_wavelengths()
            print ('wvl got from seabreeze ',wvls)   
        return wvls

    def find_nearest(self, items, value):
        idx = (abs(items-value)).argmin()
        return idx

    async def get_sp_levels(self,pixel):
        if not self.args.seabreeze:
            self.spectrum = self.spectrom.get_corrected_spectra()
        else: 
            self.spectrum = self.spectrom.get_intensities()
            print ('inside sp levels',self.spectrum[pixel])
        return self.spectrum[pixel]

class CO3_instrument(Common_instrument):
    def __init__(self,panelargs,config_name):
        super().__init__(panelargs,config_name)
        self.load_config_co3() 

    def load_config_co3(self):      
        with open(self.config_name) as json_file:
            j = json.load(json_file)  

        conf = j['CO3']

        self.wvl1 = conf["WL_1"]
        self.wvl2 = conf["WL_2"]
        self.light_slot = conf["LIGHT_SLOT"]
        self.dye = conf["Default_DYE"] 

        self.folderPath ='/home/pi/pHox/data_co3/' # relative path
        if not os.path.exists(self.folderPath):
            os.makedirs(self.folderPath)

    def get_wvlPixels(self,wvls):
        self.wvlPixels = []
        for wl in (self.wvl1, self.wvl2):      
            self.wvlPixels.append(
                self.find_nearest(wvls,wl))

    async def auto_adjust(self,*args):
        print ('try slee async in subfunc')
        await asyncio.sleep(10)
        print ('finished')
        adjusted = False 





        while adjusted == False: 
            self.spectrom.set_integration_time(self.specIntTime)

            print ('init self.specIntTime', self.specIntTime)
            pixelLevel = self.get_sp_levels(self.wvlPixels[1])

            print ('new level,max from spectro')
            print (pixelLevel)

            print ('integration time')
            print (self.specIntTime)
   
            if (pixelLevel < self.THR * 0.95 or pixelLevel > self.THR * 1.05):

                new_specintTime = self.specIntTime * self.THR / pixelLevel

                if new_specintTime < 50: 
                    print ('Something is wrong, specint time is too low ')
                elif new_specintTime > 5000:
                    print ('Too high specint time value') 
                    break 

                self.specIntTime = new_specintTime

                await asyncio.sleep(self.specIntTime*1.e-3)
               
            else: 
                adjusted = True 

        return adjusted,pixelLevel 

    def calc_CO3(self,absSp, vNTC,dilution,vol_injected):
        
        vNTC = round(vNTC, prec['vNTC'])
        print (vNTC)
        Tdeg = round((self.TempCalCoef[0]*vNTC) + self.TempCalCoef[1], prec['Tdeg'])
        #T = 273.15 + Tdeg
        A1   = round(absSp[self.wvlPixels[0]], prec['A1'])
        A2   = round(absSp[self.wvlPixels[1]], prec['A2'])       
        # volume in ml
        S_corr = round(self.fb_data['salinity'] * dilution , prec['salinity'])
        print (S_corr)
        R = A2/A1
        # coefficients from Patsavas et al. 2015
        e1 = 0.311907-0.002396*S_corr+0.000080*S_corr**2
        e2e3 = 3.061-0.0873*S_corr+0.0009363*S_corr**2
        log_beta1_e2 = 5.507074-0.041259*S_corr + 0.000180*S_corr**2

        print ('R',R,'e1',e1,'e2e3',e2e3)
        arg = (R - e1)/(1 - R*e2e3) 
        print (arg)
        #CO3 = dilution * 1.e6*(10**-(log_beta1_e2 + np.log10(arg)))  # umol/kg
        CO3 = 1.e6*(10**-(log_beta1_e2 + np.log10(arg)))  # umol/kg
        print (r'[CO3--] = {} umol/kg, T = {}'.format(CO3, Tdeg))

        return  [CO3, e1, e2e3, 
                log_beta1_e2, vNTC, self.fb_data['salinity'],
                A1,A2,R,Tdeg,
                vol_injected, S_corr]

    def eval_co3(self,co3_eval):
        x = co3_eval['Vol_injected'].values
        y = co3_eval['CO3'].values
        slope1, intercept, r_value, _, _ = stats.linregress(x,y) 
        print ('slope = ', slope1, "  intercept = ",intercept, " r2=", r_value)
        return  [slope1, intercept, r_value]

class pH_instrument(Common_instrument):
    def __init__(self,panelargs,config_name):
        super().__init__(panelargs,config_name)
        #self.args = panelargs
        self.load_config_pH()       

        if not self.args.seabreeze:
            self.spectrom.set_scans_average(1)
        
        #setup PWM and SSR lines
        for pin in range (4):
            self.rpi.set_mode(self.led_slots[pin],pigpio.OUTPUT)
            self.rpi.set_PWM_frequency(self.led_slots[pin], 100)
            self.rpi.set_PWM_dutycycle(self.led_slots[pin],0)
            self.rpi.set_mode(self.ssrLines[pin], pigpio.OUTPUT)
        self.reset_lines()

    def load_config_pH(self):
        with open(self.config_name) as json_file:
            j = json.load(json_file)

        conf_pH = j['pH']
        try: 
            self.textBox.append('Loading pH related config')
        except: 
            pass

        self.dye = conf_pH["Default_DYE"] 
        if self.dye == 'MCP':
            self.HI =  int(conf_pH['MCP_wl_HI'])
            self.I2 =  int(conf_pH['MCP_wl_I2'])         
        elif self.dye == "TB":   
            self.HI =  int(conf_pH['TB_wl_HI'])
            self.I2 =  int(conf_pH['TB_wl_I2'])

        self.THR = int(conf_pH["LED_THRESHOLD"])
        self.NIR = int(conf_pH['wl_NIR-'])

        #self.molAbsRats = default['MOL_ABS_RATIOS']
        self.led_slots =  conf_pH['LED_SLOTS']
        self.LED1 = conf_pH["LED1"]
        self.LED2 = conf_pH["LED2"]
        self.LED3 = conf_pH["LED3"]
        
        self.folderPath ='/home/pi/pHox/data/' # relative path

        if not os.path.exists(self.folderPath):
            os.makedirs(self.folderPath)

    def get_wvlPixels(self,wvls):
        self.wvlPixels = []
        for wl in (self.HI, self.I2, self.NIR):      
            self.wvlPixels.append(
                self.find_nearest(wvls,wl))

    async def adjust_LED(self, led, LED):
        self.rpi.set_PWM_dutycycle(self.led_slots[led],LED)

    async def find_LED(self,led_ind,adj,LED):
        maxval = self.THR * 1.05
        if led_ind = 2:      
            minval = self.THR * 0.90
        else:
            minval = self.THR * 0.95


        print ('led_ind',led_ind)
        print ('Threshold',thrLevel)
        pixelLevel =  await self.get_sp_levels(self.wvlPixels[led_ind])          
        while adj == False: 
        
            maxlevel = np.max(self.spectrum)
            print (maxlevel)
            print (pixelLevel,LED)
            if pixelLevel ==  maxlevel and LED >20:
                print ('case0')
                print ('saturated,reduce LED to half')
                LED = LED/2 
                r = await self.adjust_LED(led_ind, LED )  
                #await asyncio.sleep(10)
                print ("new_LED", LED)    
                pixelLevel =  await self.get_sp_levels(self.wvlPixels[led_ind])     
                print('new pixel level',pixelLevel)                  

            elif pixelLevel ==  maxlevel and LED <= 20:
                print ('case1')                
                res = 'decrease int time' 
                break
            elif (pixelLevel < minval or pixelLevel > maxval): 
                print ('case2')
                new_LED = thrLevel*LED/pixelLevel

                LED = new_LED  
                if new_LED >= 95: 
                    res = 'increase int time'              
                    break
                elif new_LED <= 5:
                    res = 'decrease int time'                                       
                    break     
                else: 
                    print ('ch led')
                    LED = new_LED     
                    r = await self.adjust_LED(led_ind, new_LED)  
                    #await asyncio.sleep(10)
                    print ("new_LED", new_LED)    
                    pixelLevel =  await self.get_sp_levels(self.wvlPixels[led_ind])     
                    print('new pixel level',pixelLevel)  
            else: 
                adj = True  
                res = 'adjusted'      

        return LED,adj,res

    async def auto_adjust(self,*args):
 
        sptIt = self.specIntTime
        if not self.args.seabreeze:
            self.spectrom.set_scans_average(1)

        n = 0
        while n < 100:
            n += 1

            print ('inside call adjust ')
            adj1,adj2,adj3 = False, False, False
            LED1,LED2,LED3 = None, None, None
            res1,res2,res3 = None, None, None
            self.spectrom.set_integration_time(sptIt)
            print ('Trying %i ms integration time...' % sptIt)

            LED1,adj1,res1 = await self.find_LED(
                led_ind = 0,adj = adj1,
                LED = self.LED1)
            if adj1:
                print ('adj1 = True')
                LED2,adj2,res2 = await self.find_LED(
                    led_ind = 1,adj = adj2,
                    LED = self.LED2)
                if adj2:    
                    print ('adj2 = True')
                    LED3,adj3,res3 = await self.find_LED(
                        led_ind = 2,adj = adj3, 
                        LED = self.LED3)    

            if any(t == 'decrease int time' for t in [res1,res2,res3]):
                print ('decreasing time') 
                sptIt -= 100
            elif any(t == 'increase int time' for t in [res1,res2,res3]) : 
                print ('increasing time')
                sptIt += 100
            elif (adj1 and adj2 and adj3):
               print ('Levels adjusted')
               break 

        if not adj1 or not adj2 or not adj3:
            result = False
        else:
            result = True 

        return LED1,LED2,LED3,sptIt,result

    def calc_pH(self,absSp, vNTC,dilution,vol_injected):

        vNTC = round(vNTC, prec['vNTC'])
        Tdeg = round((self.TempCalCoef[0]*vNTC) + self.TempCalCoef[1], prec['Tdeg'])

        T = 273.15 + Tdeg
        A1   = round(absSp[self.wvlPixels[0]], prec['A1'])
        A2   = round(absSp[self.wvlPixels[1]], prec['A2'])
        Anir = round(absSp[self.wvlPixels[2]], prec['Anir']) 

        fb_sal = round(self.fb_data['salinity'], prec['salinity'])
        S_corr = round(fb_sal * dilution , prec['salinity'])

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
            
        pH = round(pH, prec['pH'])
        pK = round(pK, prec['pK'])
        e1 = round(e1, prec['e1'])  
        e2 = round(e2, prec['e2'])  
        e3 = round(e3, prec['e3']) 

        return  [pH, pK, e1, e2, e3, vNTC,
                fb_sal, A1, A2, Tdeg, S_corr, 
                Anir,vol_injected,self.TempProbe_id,
                self.temp_iscalibrated,
                self.TempCalCoef[0],
                self.TempCalCoef[1],self.dye]
 
    def pH_eval(self,evalPar_df):

        dpH_dT = -0.0155
        evalAnir =   round(evalPar_df['Anir'].mean(), prec['evalAnir'])
        T_lab = evalPar_df["Tdeg"][0]
        pH_lab = evalPar_df["pH"][0]
        pH_t_corr = evalPar_df["pH"] + dpH_dT * (evalPar_df["Tdeg"] - T_lab) 

        nrows = evalPar_df.shape[0]

        if nrows>1:
            x = evalPar_df['Vol_injected'].values
            y = pH_t_corr.values
            slope1, intercept, r_value, _, _ = stats.linregress(x,y) 
            final_slope = slope1
            if r_value**2  > 0.9 :
                pH_lab = intercept 
                print ('r_value **2 > 0.9')
            else: 
                print ('r_value **2 < 0.9 take two last measurements')                
                x = x[:-2]
                y = y[:-2]
                slope2, intercept, r_value,_, _ = stats.linregress(x,y) 
                final_slope = slope2
                if r_value**2  > 0.9 :  
                    pH_lab = intercept
                else: 
                    pH_lab = pH_t_corr[0]

        pH_insitu = pH_lab + dpH_dT * (T_lab - self.fb_data['temperature'])

        perturbation = round(slope1, prec['perturbation'])        
        pH_insitu = round(pH_insitu , prec['pH'])
        pH_lab = round(pH_lab , prec['pH'])

        return (pH_lab, T_lab, perturbation, evalAnir,
                 pH_insitu,x,y,final_slope, intercept)      