import serial
import serial.tools.list_ports
#from ADCDACPi import ADCDACPi
#from ADCDifferentialPi import ADCDifferentialPi
import json
import numpy as np
from PyQt4 import QtGui, QtCore
import time

class CO2_instrument(object):
   def __init__(self):
      #locate serial port
      ports = list(serial.tools.list_ports.comports())

      print (ports)
      for i in range (len(ports)):
         name=ports[i][2]
         port=ports[i][0]
         #USB-RS485 CO2 sensor
         # Delete condition or not? 
         if name == 'USB VID:PID=0403:6001 SNR=FTZ1SAJ3': 
            self.portSens = serial.Serial(port,
                                    baudrate=9600,
                                    parity=serial.PARITY_NONE,
                                    stopbits=serial.STOPBITS_ONE,
                                    bytesize=serial.EIGHTBITS,
                                    writeTimeout = 0,
                                    timeout = 0.5,
                                    rtscts=False,
                                    dsrdtr=False,
                                    xonxoff=False)

         if name == 'USB VID:PID=0403:6001 SNR=FTZ0GOLZ': #USB-RS232 host
            self.host = serial.Serial(port,
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
      SENS_EXIST = True
      self.load_config()

   """def get_V(self, nAver, ch):
      V = 0.0000
      for i in range (nAver):
            #1: read channel in differential mode
         V += adcdac.read_adc_voltage(ch,0) 
      return V/nAver
      
   def get_Vd(self, nAver, ch):
      V = 0.0000
      for i in range (nAver):
         V += adc.read_voltage(ch)
      return V/nAver"""

   def load_config(self):
      with open('config.json') as json_file:
         j = json.load(json_file)
      franatech =   j['franatech']

      # Why do we need 10 row here?
      self.ftCalCoef = np.zeros((10, 2))
      self.franatech = [0]*10

      self.ftCalCoef[0] = franatech['WAT_TEMP_CAL']
      self.ftCalCoef[1] = franatech['WAT_FLOW_CAL']
      self.ftCalCoef[2] = franatech['WAT_PRES_CAL']
      self.ftCalCoef[3] = franatech['AIR_TEMP_CAL']
      self.ftCalCoef[4] = franatech['AIR_PRES_CAL']
      self.ftCalCoef[5] = franatech['WAT_DETECT']
      self.ftCalCoef[6] = franatech['CO2_FRAC_CAL']

      self.QUERY_CO2='\x2A\x4D\x31\x0A\x0D'
      self.QUERY_T='\x2A\x41\x32\x0A\x0D'
      self.UDP_SEND = 6801
      self.UDP_RECV = 6802
      self.UDP_IP   = '192.168.0.1'
      self.VAR_NAMES = ['Water temperature \xB0C','Water flow l/m',
               'Water pressure ','Air temperature \xB0C',
               'Air pressure mbar','Water detect','C02 ppm',
               'T CO2 sensor \xB0C']

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
      print( 'listening to self.host...') #750ms and 500ms sleep intervals seem to work with PUCK timing
      try:
         rx = self.host.read(6)
         #print( '<-- '+ rx)
         if rx == '@@@@@@':
            time.sleep(0.75)
            rx = self.host.read(7)
            #print( '<-- '+ rx)
            if rx == '!!!!!!':
               time.sleep(0.5)
               self.host.write(PRD)
               self.timerHostPoll.stop()
               self.enter_puckmode()
            else:
               self.host.flushInput()
         elif (rx in self.instDictHints):
            rRx = self.host.read(10)
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
         self.host.close()
         
   def enter_puckmode(self):
      print( 'Puckmode')
      #listen to self.host until some data arrive
      self.puckMode= True
      flInt = ['','\r'] #flow interruption marks
      cmd =''
      t0 = time.time()
      elapsed = time.time()-t0
      while (elapsed < self.PT) and (cmd != PIM) :
         received = ''
         fromHost = self.host.read(1)
         while not(fromHost in flInt) and (elapsed < self.PT) and (received != PSB):
            received += fromHost
            fromHost = self.host.read(1)
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
         self.host.write(PTO+PRD)     
      self.enter_instrument_mode([])
      

   def send_data(self, args):
      t = datetime.now()
      dateTime = t.isoformat('_')
      dataString = dateTime[0:10]+','+dateTime[11:19]
      # dataString header: pCO2,pH,TA,lat,lon,sal_ref,pCO2_Tref_meas,pH_Tref_meas
      dataString = '%.1f,%.4f,%.1f,9999.9999,8888.8888,%.2f,%.2f,%.2f\r' %(self.LAST_CO2,self.LAST_pH,self.LAST_TA,self.LAST_PAR[0],self.LAST_PAR[1],self.LAST_PAR[2])
      self.host.write(dataString)
      dataString = dateTime[0:10]+','+dateTime[11:19]+','+dataString
      with open('data/Cbon.log','a') as flnm:
         flnm.write(dataString+'\n')      


   def enter_instrument_mode(self, args):
      print( 'Entering instrument mode...')
      self.puckMode = False
      self.timerHostPoll.start(30000)  #poll self.host for instrument specific commands, 1000ms seems to work with timing
      
   def puck(self,args):
      self.host.write(PRD)
      print( 'PUCK query')

   def puck_memory_size(self,args):
      self.host.write(str(self.PUCK_MEM_SIZE)+'\r')
      self.host.write(PRD)

   def puck_set_address(self, args):
      self.memPtr = int(args[0])
      self.host.write(PRD)
         
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
      
      self.host.write('['+bytesRead+']')
      self.host.write(PRD)
      
   def puck_write_memory(self, args):
      print( 'Writing PUCK memory')
      nBytesToWrite = int(args[0])
      packet = ''
      for i in range (nBytesToWrite):
         packet += self.host.read(1)
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






