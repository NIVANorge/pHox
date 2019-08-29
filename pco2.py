# Franatech query strings
QUERY_CO2='\x2A\x4D\x31\x0A\x0D'
QUERY_T='\x2A\x41\x32\x0A\x0D'

VAR_NAMES = ['Water temperature \xB0C','Water flow l/m','Water pressure ','Air temperature \xB0C','Air pressure mbar','Water detect','C02 ppm','T CO2 sensor \xB0C']

ports = list(serial.tools.list_ports.comports()) #locate serial port
SENS_EXIST = False
HOST_EXIST = False
FIA_EXIST = False
USE_FIA_TA = False

#self.franatech = [0]*10
#self.ftCalCoef = [[0]*2]*10

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


"""        ### Franatech calibration coefficients ###

        with open('config.json') as json_file:
            j = json.load(json_file)

        default =   j['default']
        #franatech = j['franatech']
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
    print (self.ftCalCoef)"""