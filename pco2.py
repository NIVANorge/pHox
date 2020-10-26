import serial
import serial.tools.list_ports
import logging
import numpy as np
from PyQt5 import QtCore
from PyQt5.QtGui import QPixmap
import struct
from precisions import precision as prec
try:
    import pigpio
    import RPi.GPIO as GPIO
    from ADCDifferentialPi import ADCDifferentialPi
except:
    pass
from PyQt5.QtWidgets import QLineEdit, QWidget
from PyQt5.QtWidgets import QGroupBox, QMessageBox, QLabel, QGridLayout
from PyQt5 import QtGui, QtCore, QtWidgets
import os
import pandas as pd

from datetime import datetime

from util import config_file
logging.getLogger()
logging.getLogger().setLevel(logging.DEBUG)

class tab_pco2_class(QWidget):
    def __init__(self):
        super(QWidget, self).__init__()
        
        groupbox = QGroupBox('Updates from pCO2')
        self.group_layout = QGridLayout()
        layout = QGridLayout()

        self.Tw_pco2_live = QLineEdit()
        self.Ta_mem_pco2_live = QLineEdit()
        self.Qw_pco2_live = QLineEdit()
        self.Pw_pco2_live = QLineEdit()
        self.Pa_env_pco2_live = QLineEdit()
        self.Ta_env_pco2_live = QLineEdit()
        self.CO2_pco2_live = QLineEdit()
        self.TCO2_pco2_live = QLineEdit()

        self.pco2_params = [self.Tw_pco2_live, self.Ta_mem_pco2_live, self.Qw_pco2_live,
                            self.Pw_pco2_live, self.Pa_env_pco2_live, self.Ta_env_pco2_live,
                            self.CO2_pco2_live, self.TCO2_pco2_live]

        self.pco2_labels = ['Water temperature', 'Air Temperature membr', 'Water Flow',
                            'Water Pressure', 'Air Pressure env', 'Air Temperature env',
                            'C02 ppm', 'T CO2 sensor']
        [layout.addWidget(self.pco2_params[n], n, 1) for n in range(len(self.pco2_params))]
        [layout.addWidget(QLabel(self.pco2_labels[n]), n, 0) for n in range(len(self.pco2_params))]

        groupbox.setLayout(layout)
        self.group_layout.addWidget(groupbox)


    async def update_tab_values(self, values):
        [self.pco2_params[n].setText(str(values[n])) for n in range(len(values))]


class pco2_instrument(object):
    def __init__(self, base_folderpath, panelargs):
        self.base_folderpath = base_folderpath
        self.path = self.base_folderpath + "/data_pCO2/"
        self.args = panelargs
        self.co2 = 990
        self.co2_temp = 999
        self.buff = None
        self.data = {}

        if not os.path.exists(self.path):
            os.mkdir(self.path)


        try:

            ports = list(serial.tools.list_ports.comports())
            connection_types = [port[1] for port in ports]

            self.port = ports[0]

            #ind = connection_types.index('USB-RS485 Cable')
            #port = ports[ind][0]
            logging.debug(f'Connected port is {self.port}')

            self.connection = serial.Serial(self.port[0], baudrate=115200, timeout=5,
                                            parity=serial.PARITY_NONE,
                                            stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
                                            rtscts=False, dsrdtr=False,
                                            xonxoff=False)
            '''self.connection = serial.Serial(port,
                                      baudrate=9600,
                                      parity=serial.PARITY_NONE,
                                      stopbits=serial.STOPBITS_ONE,
                                      bytesize=serial.EIGHTBITS,
                                      writeTimeout=0,
                                      timeout=0.5,
                                      rtscts=False,
                                      dsrdtr=False,
                                      xonxoff=False)'''
            logging.debug(self.connection)
        except:
            logging.debug('Was not able to find connection to the instrument')
            self.connection = None

        f = config_file["pCO2"]


        self.ship_code = config_file['Operational']["Ship_Code"]
        self.save_pco2_interv = f["pCO2_Sampling_interval"]
        self.ppco2_string_version = f['PPCO2_STRING_VERSION']

        self.QUERY_CO2 = b"\x2A\x4D\x31\x0A\x0D"
        self.QUERY_T = b"\x2A\x41\x32\x0A\x0D"

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

        self.pco2_df = pd.DataFrame(columns=["Time", "Lon", "Lat", "fb_temp", "fb_sal",
                                             "Tw", "Flow", "Pw", "Ta", "Pa", "Leak", "CO2", "TCO2"])



    async def get_pco2_values(self):
        self.connection.flushInput()
        self.data = {}
        synced = False
        count = 100
        while not synced:
            b = self.connection.read(1)
            if len(b) and (b[0] == b'\x07'[0]):
                synced = True
            count = count - 1
            if count < 0:
                self.data['CH1_Vout'] = -999.0
                self.data['ppm'] = -999.0
                self.data['type'] = b'\x81'
                self.data['range'] = -999.0
                self.data['sn'] = b'no_sync'
                self.data['VP'] = -999.0
                self.data['VT'] = -999.0
                self.data['mode'] = b'\x80'
                # raise ValueError('cannot sync to CO2 detector')
                return (self.data)
        try:
            self.buff = self.connection.read(37)
            print (self.butt)
            self.data['CH1_Vout'] = struct.unpack('<f', self.buff[0:4])[0]
            self.data['ppm'] = struct.unpack('<f', self.buff[4:8])[0]
            self.data['type'] = self.buff[8:9]
            self.data['range'] = struct.unpack('<f', self.buff[9:13])[0]
            self.data['sn'] = self.buff[13:27]
            self.data['VP'] = struct.unpack('<f', self.buff[27:31])[0]
            self.data['VT'] = struct.unpack('<f', self.buff[31:35])[0]
            self.data['mode'] = self.buff[35:36]
            if self.data['type'][0] != b'\x81'[0]:
                raise ValueError('the gas type is not correct')
            if self.data['mode'][0] != b'\x80'[0]:
                raise ValueError('the detector mode is not correct')
        except:
            raise
        return (self.data)


    '''async def get_pco2_values(self):
        if self.connection:
            self.connection.write(self.QUERY_CO2)
            response_co2 = self.connection.read(15)
            logging.debug(f'full response_co2 {response_co2}')
            try:
                value = float(response_co2[3:])
                self.Co2_CalCoef = config_file["pCO2"]["CO2"]["Calibr"]
                value = float(self.Co2_CalCoef[0]) + float(self.Co2_CalCoef[1]) * value
            except ValueError:
                value = 0
            self.co2 = round(value, prec['pCO2'])

            self.connection.write(self.QUERY_T)
            response_t = self.connection.read(15)
            logging.debug('response_t {response_t}')
            try:
                self.co2_temp = round(float(response_t[3:]), prec['T_cuvette'])
            except ValueError:
                self.co2_temp = 0'''

    async def save_pCO2_data(self, values, fbox):
        labelSample = datetime.now().isoformat("_")[0:19]
        logfile = os.path.join(self.path, "pCO2.log")

        pco2_row = [labelSample, fbox["longitude"], fbox["latitude"],
                    fbox["temperature"], fbox["salinity"]] + values
        self.pco2_df.loc[0] = pco2_row
        logging.debug('Saving pco2 data')

        if not os.path.exists(logfile):
            self.pco2_df.to_csv(logfile, index=False, header=True)
        else:
            self.pco2_df.to_csv(logfile, mode='a', index=False, header=False)

        return self.pco2_df


class only_pco2_instrument(pco2_instrument):
    # Class for communication with Raspberry PI for the only pco2 case
    def __init__(self, base_folderpath, panelargs):
        super().__init__(base_folderpath, panelargs)

        if not self.args.localdev:
            self.adc = ADCDifferentialPi(0x68, 0x69, 14)
            self.adc.set_pga(1)

    def get_Voltage(self, nAver, channel):
        v = 0.0000
        for i in range(nAver):
            v += self.adc.read_voltage(channel)
        Voltage = round(v / nAver, prec["Voltage"])
        return Voltage


class test_pco2_instrument(pco2_instrument):
    def __init__(self, base_folderpath, panelargs):
        super().__init__(base_folderpath, panelargs)
        self.save_pco2_interv = 2

    async def get_pco2_values(self):
        self.co2 = np.random.randint(400, 600)
        self.co2_temp = np.random.randint(1, 10)

    def get_Voltage(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        return v / nAver

    def close(self):
        print ('close connection, localtest')
        logging.debug('close connection, localtest')