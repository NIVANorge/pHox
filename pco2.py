import serial
import serial.tools.list_ports
import json
import numpy as np


class pco2_instrument(object):
    def __init__(self, config_name):
        self.config_name = config_name
        ports = list(serial.tools.list_ports.comports())
        self.portSens = None
        for i in range(len(ports)):
            print (ports[i])
            name = ports[i][2]
            port = ports[i][0]
            print('name', name)
            print('index 1', ports[i][1])
            print('port',port)
            # USB-RS485 CO2 sensor
            # Delete condition or not?
            if name == "USB VID:PID=0403:6001 SER=FTZ1SAJ3 LOCATION=1-1.3":
                #if name == 'USB VID:PID=0403:6001 SNR=FTZ1SAJ3':
                self.portSens = serial.Serial(port,
                                              baudrate=9600,
                                              parity=serial.PARITY_NONE,
                                              stopbits=serial.STOPBITS_ONE,
                                              bytesize=serial.EIGHTBITS,
                                              writeTimeout=0,
                                              timeout=0.5,
                                              rtscts=False,
                                              dsrdtr=False,
                                              xonxoff=False)
            '''if name == 'USB VID:PID=0403:6001 SER=FTZ0GOLZ LOCATION=1-1.4':
                #if name == 'USB VID:PID=0403:6001 SNR=FTZ0GOLZ':  # USB-RS232 host
                self.host = serial.Serial(port,
                                          baudrate=9600,
                                          parity=serial.PARITY_NONE,
                                          stopbits=serial.STOPBITS_ONE,
                                          bytesize=serial.EIGHTBITS,
                                          writeTimeout=0,
                                          timeout=0.25,
                                          rtscts=False,
                                          dsrdtr=False,
                                          xonxoff=False)'''
        #HOST_EXIST = True
        #SENS_EXIST = True

        with open(self.config_name) as json_file:
            j = json.load(json_file)
        f = j["pCO2"]
        # Why do we need 10 row here?
        self.ftCalCoef = np.zeros((10, 2))
        self.franatech = [0] * 10


        self.save_pco2_interv = f["pCO2_Sampling_interval"]
        self.ftCalCoef[0] = f["water_temperature"]["WAT_TEMP_CAL"]
        self.ftCalCoef[1] = f["WAT_FLOW_CAL"]
        self.ftCalCoef[2] = f["WAT_PRES_CAL"]
        self.ftCalCoef[3] = f["AIR_TEMP_CAL"]
        self.ftCalCoef[4] = f["AIR_PRES_CAL"]
        self.ftCalCoef[5] = f["WAT_DETECT"]

        self.ftCalCoef[6] = f["CO2_FRAC_CAL"]
        self.Co2_CalCoef = f["CO2_FRAC_CAL"]

        self.QUERY_CO2 = b"\x2A\x4D\x31\x0A\x0D"
        self.QUERY_T = b"\x2A\x41\x32\x0A\x0D"
        self.UDP_SEND = 6801
        self.UDP_RECV = 6802
        self.UDP_IP = "192.168.0.1"
        self.VAR_NAMES = [
            "Water temperature \xB0C",
            "Water flow l/m",
            "Water pressure",
            "Air temperature \xB0C",
            "Air pressure mbar",
            "Water detect",
            "C02 ppm",
            "T CO2 sensor \xB0C",
        ]


    async def get_pco2_values(self):
        if self.portSens:
            self.portSens.write(self.QUERY_CO2)
            response_co2 = self.portSens.read(15)
            print(response_co2)
            try:
                value = float(response_co2[3:])
                value = self.ftCalCoef[6][0] + self.ftCalCoef[6][1] * value
            except ValueError:
                value = 0
            self.franatech[6] = value

            self.portSens.write(self.QUERY_T)
            response_t = self.portSens.read(15)
            print(response_t)
            try:
                self.franatech[7] = float(response_t[3:])
            except ValueError:
                self.franatech[7] = 0

class test_pco2_instrument(pco2_instrument):
    def __init__(self, config_name):
        super().__init__(config_name)
        self.save_pco2_interv = 2
        self.config_name = config_name

    async def get_pco2_values(self):

        #CO2
        self.franatech[5] = np.random.randint(1, 10)
        #TEMP
        self.franatech[6] = np.random.randint(1, 10)

        # 0,1,2,3,4
        for ch in range(5):
            V = self.get_Vd(2, ch + 1)
            X = 0
            for i in range(2):
                X += self.ftCalCoef[ch][i] * pow(V, i)
            self.franatech[ch] = round(X, 3)
        return self.franatech

    def get_Vd(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        return v / nAver
