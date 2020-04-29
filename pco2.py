import serial
import serial.tools.list_ports
import json
import numpy as np
from PyQt5.QtWidgets import QLineEdit, QWidget
from PyQt5.QtWidgets import (QGroupBox, QLabel, QGridLayout)
import precisions as prec
try:
    import pigpio
    import RPi.GPIO as GPIO
    from ADCDACPi import ADCDACPi
    from ADCDifferentialPi import ADCDifferentialPi
except:
    pass
from util import config_file


class tab_pco2_class(QWidget):
    def __init__(self):
        super(QWidget, self).__init__()
        self.layout2 = QGridLayout()
        groupbox = QGroupBox('Updates from pCO2')
        layout = QGridLayout()

        self.Tw_pco2_live = QLineEdit()
        self.flow_pco2_live = QLineEdit()
        self.Pw_pco2_live = QLineEdit()
        self.Ta_pco2_live = QLineEdit()
        self.Pa_pco2_live = QLineEdit()
        self.Leak_pco2_live = QLineEdit()
        self.CO2_pco2_live = QLineEdit()
        self.TCO2_pco2_live = QLineEdit()

        self.pco2_params = [self.Tw_pco2_live, self.flow_pco2_live, self.Pw_pco2_live,
                            self.Ta_pco2_live, self.Pa_pco2_live, self.Leak_pco2_live,
                            self.CO2_pco2_live, self.TCO2_pco2_live]
        self.pco2_labels = ['Water temperature', 'Water flow l/m', 'Water pressure"',
                            'Air temperature', 'Air pressure mbar', 'Leak Water detect',
                            'C02 ppm', 'T CO2 sensor']
        [layout.addWidget(self.pco2_params[n], n, 1) for n in range(len(self.pco2_params))]
        [layout.addWidget(QLabel(self.pco2_labels[n]), n, 0) for n in range(len(self.pco2_params))]

        groupbox.setLayout(layout)
        self.layout2.addWidget(groupbox)

    async def update_tab_values(self, values):
        [self.pco2_params[n].setText(str(values[n])) for n in range(len(values))]


class pco2_instrument(object):
    def __init__(self):

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
            print(self.portSens)

        f = config_file["pCO2"]

        self.shipcode = config_file['Operational']["Ship_Code"]
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
            self.co2 = round(value, prec['pCO2'])

            self.portSens.write(self.QUERY_T)
            response_t = self.portSens.read(15)
            print('response_t', response_t)
            try:
                self.co2_temp = round(float(response_t[3:]), prec['Tdeg'])
            except ValueError:
                self.co2_temp = 0


class onlyPco2instrument(pco2_instrument):
    def __init__(self):
        super().__init__()

        if not self.args.localdev:
            self.adc = ADCDifferentialPi(0x68, 0x69, 14)
            self.adc.set_pga(1)
            self.adcdac = ADCDACPi()

    def get_Vd(self, nAver, channel):
        V = 0.0000
        for i in range(nAver):
            V += self.adc.read_voltage(channel)
        return V / nAver

class test_pco2_instrument(pco2_instrument):
    def __init__(self):
        super().__init__()
        self.save_pco2_interv = 2

    async def get_pco2_values(self):
        self.co2 = np.random.randint(400, 600)
        self.co2_temp = np.random.randint(1, 10)

    def get_Vd(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        return v / nAver