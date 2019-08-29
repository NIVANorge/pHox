# KM strings, for alkalinity 
TCHAR = '\r\n'
SET_SAL = '$KMSALINITY,W,'
SET_SAMPLE_NAME = '$KMNAME,W,'
RUN = '$KMRUN,W,MEASURE'+TCHAR
STOP = '$KMRUN,W,STOP'+TCHAR


# PUCK mode strings
PRD = 'PUCKRDY\r'
PRM = 'PUCKRM'
PTO = 'PUCKTMO\r'
PSB = '@@@@@@!!!!!!'
PCK = 'PUCK'
PSZ = 'PUCKSZ'
PSA = 'PUCKSA'
PIM = 'PUCKIM'

# sampling intervals (seconds)
TA_SAMP_INT = 600

# Instrument mode strings
CBG = 'CBON:GET'

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
