import serial
import serial.tools.list_ports
import json
import numpy as np


class pco2_instrument(object):
    def __init__(self, config_name):

        self.config_name = config_name
        ports = list(serial.tools.list_ports.comports())
        connection_types = [port[1] for port in ports]
        try:
            ind = connection_types.index('USB-RS485 Cable')
            port = ports[ind][0]
            print (port)
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
            print (self.portSens)
        except:
            self.portSens = None
            print (self.portSens)

        with open(self.config_name) as json_file:
            j = json.load(json_file)
        f = j["pCO2"]

        self.save_pco2_interv = f["pCO2_Sampling_interval"]

        self.wat_temp_cal_coef = f["water_temperature"]["WAT_TEMP_CAL"]
        self.wat_flow_cal = f["WAT_FLOW_CAL"]
        self.wat_pres_cal = f["WAT_PRES_CAL"]
        self.air_temp_cal = f["AIR_TEMP_CAL"]
        self.air_pres_cal = f["AIR_PRES_CAL"]
        self.water_detect = f["WAT_DETECT"]
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
            print('full response_co2', response_co2)
            try:
                value = float(response_co2[3:])
                value = float(self.Co2_CalCoef[0]) + float(self.Co2_CalCoef[1]) * value
            except ValueError:
                value = 0
            self.co2 = value

            self.portSens.write(self.QUERY_T)
            response_t = self.portSens.read(15)
            print('response_t', response_t)
            try:
                self.co2_temp = float(response_t[3:])
            except ValueError:
                self.co2_temp = 0


class test_pco2_instrument(pco2_instrument):
    def __init__(self, config_name):
        super().__init__(config_name)
        self.save_pco2_interv = 2
        self.config_name = config_name

    async def get_pco2_values(self):
        self.co2 = np.random.randint(1, 10)
        self.co2_temp = np.random.randint(1, 10)

    def get_Vd(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        return v / nAver