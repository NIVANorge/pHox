#! /usr/bin/python
import logging
import asyncio
import json
import random
import re
import time
import numpy as np
import pandas as pd
import udp
from precisions import precision as prec
from util import config_file, temp_probe_conf_path
try:
    import pigpio
    import RPi.GPIO as GPIO
    from ADCDifferentialPi import ADCDifferentialPi
    import seabreeze

    seabreeze.use("cseabreeze")
    from seabreeze.spectrometers import Spectrometer
    from seabreeze.spectrometers import list_devices
    import seabreeze.cseabreeze as sbb
except:
    pass

from pHox_gui import AsyncThreadWrapper


def get_linregress(x, y):
    a = np.vstack([x, np.ones(len(x))]).T
    slope, intercept = np.linalg.lstsq(a, y, rcond=None)[0]
    r_value = np.corrcoef(x, y)[0][1]
    return slope, intercept, r_value


class Spectrometer_localtest(object):
    def close(self):
        pass


class Spectro_localtest(object):
    def __init__(self,panelargs):
        self.args = panelargs
        self.spec = Spectrometer_localtest()
        if self.args.co3:
            self.spectro_type = "FLMT"
            self.test_spt = pd.read_csv("data_localtests/co3.spt")
        else:
            self.spectro_type = "STS"
            self.test_spt = pd.read_csv("data_localtests/20200213_105508.spt")

        x = self.test_spt.T
        x.columns = x.iloc[0]
        self.test_df = x[1:]
        self.integration_time = 100 / 1000

    def set_integration_time_not_async(self, time_millisec):
        microsec = time_millisec * 1000
        self.busy = True
        self.integration_time = time_millisec / 1000
        self.busy = False

    async def set_integration_time(self, time_millisec):
        while self.busy:
            await asyncio.sleep(0.0001)
        self.set_integration_time_not_async(time_millisec)
        # time.sleep(time_millisec/1.e3)

    def set_scans_average(self, num):
        pass

    def get_wavelengths(self):
        self.wvl = np.array([np.float(n) for n in self.test_spt.iloc[0].index.values[1:]])
        # wavelengths in (nm) corresponding to each pixel of the spectrom
        return self.wvl

    async def get_intensities(self, num_avg=1, correct=True):
        def _get_intensities():
            sp = self.test_df["0"].values + random.randrange(-1000, 1000, 1)
            return sp

        while self.busy:
            await asyncio.sleep(0.05)
        self.busy = True
        async_thread_wrapper = AsyncThreadWrapper(_get_intensities)
        sp = await async_thread_wrapper.result_returner()
        self.busy = False
        return sp

    def get_intensities_slow(self, num_avg=1, correct=True):
        sp = self.test_df["0"].values + random.randrange(-1000, 1000, 1)
        return sp

class Spectro_seabreeze(object):
    def __init__(self):
        self.busy = False
        self.spec = Spectrometer.from_first_available()
        self.spectro_type = None
        for sensor_code in ["STS", "FLMT"]:
            f = re.search(sensor_code, str(self.spec))
            if f:
                self.spectro_type = sensor_code
                break
        if not self.spectro_type:
            logging.info("could not get the spectro type, defaulting to FLMT")
            self.spectro_type = "FLMT"
        logging.debug("spectro_type set to '{}' for spec '{}'".format(self.spectro_type, self.spec))

    def set_integration_time_not_async(self, time_millisec):
        if self.busy:
            logging.info("set_integration_time was called twice, returning without doing anything")
        self.busy = True
        self.spec.integration_time_micros(time_millisec * 1000)
        self.busy = False

    async def set_integration_time(self, time_millisec):
        while self.busy:
            await asyncio.sleep(0.05)
        self.set_integration_time_not_async(time_millisec)

    def get_wavelengths(self):
        # wavelengths in (nm) corresponding to each pixel of the spectrom
        return self.spec.wavelengths()

    async def get_intensities(self, num_avg=1, correct=True):
        def _get_intensities():
            sp = self.spec.intensities(correct_nonlinearity=correct)
            if num_avg > 1:
                for _ in range(num_avg):
                    sp = np.vstack([sp, self.spec.intensities(correct_nonlinearity=correct)])
                sp = np.mean(np.array(sp), axis=0)
            return sp

        while self.busy:
            await asyncio.sleep(0.05)
        self.busy = True

        async_thread_wrapper = AsyncThreadWrapper(_get_intensities)
        sp = await async_thread_wrapper.result_returner()
        self.busy = False
        return sp

    def get_intensities_slow(self, num_avg=1, correct=True):

        sp = self.spec.intensities(correct_nonlinearity=correct)
        if num_avg > 1:
            for _ in range(num_avg):
                sp = np.vstack([sp, self.spec.intensities(correct_nonlinearity=correct)])
            sp = np.mean(np.array(sp), axis=0)
        return sp

    def set_scans_average(self, num):
        # not supported for FLAME spectrom
        self.spec.scans_to_average(num)

    @classmethod
    def __delete__(self):
        self.spec.close()
        return


class Common_instrument(object):
    """ This class is a parent class for pH instrument and CO3 instrument
        since both of these classes use spectrometers. Class for pure pCO2 version
        will be separate since there are too many differences
    """
    def __init__(self, panelargs):
        logging.getLogger()
        logging.getLogger().setLevel(logging.INFO)

        self.args = panelargs
        self.spectrometer_cls = Spectro_seabreeze() if not self.args.localdev else Spectro_localtest(panelargs)

        # initialize PWM lines
        if not self.args.localdev:
            self.rpi = pigpio.pi()

        self.fb_data = udp.Ferrybox

        self.load_config()
        self.spectrometer_cls.set_integration_time_not_async(self.specIntTime)
        if not self.args.localdev:
            self.adc = ADCDifferentialPi(0x68, 0x69, 14)
            self.adc.set_pga(1)

        # For signaling to threads
        self._exit = False

    def reset_lines(self):
        # set values in outputs of pins
        self.rpi.write(self.wpump_slot, 0)
        self.rpi.write(self.dyepump_slot, 0)
        self.rpi.write(self.stirrer_slot, 0)
        self.rpi.write(self.extra_slot, 0)

    async def set_Valve(self, status):
        # Here False mean close
        chEn = self.valve_slots[0]
        ch1, ch2 = self.valve_slots[1], self.valve_slots[2]

        if not status:
            logging.info("Closing the valve")
            ch1, ch2 = self.valve_slots[2], self.valve_slots[1]
        else:
            logging.info("Opening the valve")
        self.rpi.write(ch1, True)
        self.rpi.write(ch2, False)
        self.rpi.write(chEn, True)
        await asyncio.sleep(0.3)
        self.rpi.write(ch1, False)
        self.rpi.write(ch2, False)
        self.rpi.write(chEn, False)

    def set_Valve_sync(self, status):
        chEn = self.valve_slots[0]
        ch1, ch2 = self.valve_slots[1], self.valve_slots[2]
        if not status:
            logging.info("Closing the valve")
            ch1, ch2 = self.valve_slots[2], self.valve_slots[1]
        else:
            logging.info("Opening the valve")
        self.rpi.write(ch1, True)
        self.rpi.write(ch2, False)
        self.rpi.write(chEn, True)
        time.sleep(0.3)
        self.rpi.write(ch1, False)
        self.rpi.write(ch2, False)
        self.rpi.write(chEn, False)

    def to_bool(self, var):
        if var == 'True':
            return True
        else:
            return False

    def load_config(self):
        conf_operational = config_file["Operational"]
        self.autostart = self.to_bool(conf_operational["AUTOSTART"])
        self.automode = conf_operational["AUTOSTART_MODE"]
        self.Voltagech = int(conf_operational["T_PROBE_CH"])
        self.samplingInterval = int(conf_operational["SAMPLING_INTERVAL_MIN"])
        self.valid_samplingIintervals = conf_operational["VALID_SAMPLING_INTERVALS"]
        self.pumpTime = int(conf_operational["pumpTime_sec"])
        self.calibration_pump_time = int(config_file["TrisBuffer"]["Calibration_pump_time"])
        self.mixT = int(conf_operational["mixTime"])
        self.waitT = int(conf_operational["waitTime"])
        self.ncycles = int(conf_operational["ncycles"])
        self.nshots = int(conf_operational["dye_nshots"])
        self.specAvScans = int(conf_operational["specAvScans"])
        self.wpump_slot = conf_operational["WPUMP_SLOT"]
        self.dyepump_slot = conf_operational["DYEPUMP_SLOT"]
        self.stirrer_slot = conf_operational["STIRR_SLOT"]
        self.extra_slot = conf_operational["SPARE_SLOT"]
        self.autoadj_opt = conf_operational["Autoadjust_state"]

        self.ssrLines = [
            self.wpump_slot,
            self.dyepump_slot,
            self.stirrer_slot,
            self.extra_slot,
        ]

        self.valve_slots = conf_operational["VALVE_SLOTS"]

        self.TempProbe_id = conf_operational["TEMP_PROBE_ID"]
        self.update_temp_probe_coef()

        self.Cuvette_V = conf_operational["CUVETTE_V"]  # ml
        self.dye_vol_inj = conf_operational["DYE_V_INJ"]
        self.specIntTime = conf_operational["Spectro_Integration_time"]
        self.drain_mode = conf_operational['drain_mode']
        self.ship_code = conf_operational["Ship_Code"]
        self.valid_ship_codes = conf_operational["Valid_ship_codes"]

        if self.spectrometer_cls.spectro_type == "FLMT":
            self.THR = int(conf_operational["LIGHT_THRESHOLD_FLAME"])
        elif self.spectrometer_cls.spectro_type == "STS":
            self.THR = int(conf_operational["LIGHT_THRESHOLD_STS"])

    def update_temp_probe_coef(self):
        with open(temp_probe_conf_path) as json_file:
            j = json.load(json_file)
            self.temp_iscalibrated = j[self.TempProbe_id]["is_calibrated"]
            if self.temp_iscalibrated == 'True':
                self.TempCalCoef = j[self.TempProbe_id]["Calibr_coef"]
            else:
                self.TempCalCoef = j["Probe_Default"]["Calibr_coef"]

    def turn_on_relay(self, line):
        self.rpi.write(line, True)

    def turn_off_relay(self, line):
        self.rpi.write(line, False)

    async def pumping(self, pumpTime):
        self.turn_on_relay(self.wpump_slot)  # start the instrument pump
        self.turn_on_relay(self.stirrer_slot)  # start the stirrer
        await asyncio.sleep(pumpTime)
        self.turn_off_relay(self.stirrer_slot)  # turn off the pump
        self.turn_off_relay(self.wpump_slot)  # turn off the stirrer
        return

    '''async def cycle_line(self, line, nCycles):
        for nCy in range(nCycles):
            self.turn_on_relay(line)
            await asyncio.sleep(self.waitT)
            self.turn_off_relay(line)
            await asyncio.sleep(self.waitT)'''

    async def pump_dye(self, nshots):
        for shot in range(nshots):
            self.turn_on_relay(self.dyepump_slot)
            logging.debug('inject dye shot {}'.format(shot))
            await asyncio.sleep(0.15)
            self.turn_off_relay(self.dyepump_slot)
            await asyncio.sleep(0.35)
        return

    # COMMON
    def get_wvlPixels(self, wvls_spectrum):
        self.wvlPixels = []
        for wl in self.wvl_needed:
            self.wvlPixels.append(self.find_nearest(wvls_spectrum, wl))

    def print_Com(self, port, txtData):
        port.write(txtData)

    def get_Voltage(self, nAver, channel):
        v = 0.0000
        for i in range(nAver):
            try:
                v += self.adc.read_voltage(channel)
            except Exception as e:
                logging.error(e)
                nAver -= 1
                pass
        try:
            Voltage = round(v / nAver, prec["Voltage"])
        except Exception as e:
            print (e)
            Voltage = -999
        
        if nAver < 3:
            logging.error(' num of Volt measurements: {}'.format(str(nAver)))
            
        return Voltage

    def calc_wavelengths(self):
        """
        assign wavelengths to pixels
        and find pixel number of reference wavelengths
        """
        wvls = self.spectrometer_cls.get_wavelengths()
        return wvls

    def find_nearest(self, items, value):
        idx = (abs(items - value)).argmin()
        return idx

    async def get_sp_levels(self, pixel):

        self.spectrum = await self.spectrometer_cls.get_intensities()

        return self.spectrum[pixel]


class CO3_instrument(Common_instrument):
    def __init__(self, panelargs):
        super().__init__(panelargs)
        self.load_config_co3()

    def load_config_co3(self):
        conf = config_file["CO3"]
        self.wvl1 = conf["WL_1"]
        self.wvl2 = conf["WL_2"]
        self.wvl3 = conf["WL_3"]
        self.wvl_needed = (self.wvl1, self.wvl2, self.wvl3)

        self.light_slot = conf["LIGHT_SLOT"]
        self.dye = conf["Default_DYE"]

        self.PCO3_string_version = str(conf["PCO3_string_version"])


    async def precheck_auto_adj(self):

        pixelLevel = await self.get_sp_levels(self.wvlPixels)

        logging.debug('precheck pixel level:' + str(pixelLevel))
        #print(self.THR * 0.95, self.THR * 1.05)
        min_cond = min(pixelLevel) > self.THR * 0.95
        max_cond = max(pixelLevel) < self.THR * 1.05
        #print (self.wvlPixels,pixelLevel,min_cond,max_cond ,'precheck')
        return (min_cond and max_cond)

    async def auto_adjust(self, *args):
        # CO3!!
        adjusted = False
        maxval = self.THR * 1.05
        minval = self.THR * 0.95
        logging.debug('Autoadjusting into range' + str(minval) + ',' + str(maxval))

        increment = 500

        n = 0
        while n < 20:
            n += 1

            self.specIntTime = max(1, self.specIntTime)
            logging.debug("Trying Integration time: " + str(self.specIntTime))
            await self.spectrometer_cls.set_integration_time(self.specIntTime)
            await asyncio.sleep(0.5)

            #print(self.wvlPixels, pixelLevel, 'autadj')
            pixelLevel = await self.get_sp_levels(self.wvlPixels)
            logging.debug('max pixellevel'+str(max(pixelLevel)))

            if increment == 0:
                logging.info('increment is 0,something is wrong')
                break

            if self.specIntTime > 5000:
                logging.info("Too high spec int time value,break")
                break

            elif self.specIntTime < 1:
                logging.info("Something is wrong, specint time is too low,break ")
                break

            elif max(pixelLevel) < minval:
                logging.debug(str(pixelLevel) + 'lover than' + str(minval) + 'adding increment' + str(increment))
                self.specIntTime += increment
                increment = increment / 2

            elif max(pixelLevel) > maxval:
                logging.debug(str(pixelLevel)+'higher than' + str(maxval) + ' subtracting increment' + str(increment))
                self.specIntTime -= increment
                increment = increment / 2

            else:
                adjusted = True
                break

        return adjusted, pixelLevel

    def get_co3_pars(self, a0, b0, b1, c0, c1, d0, S, T):
        p = a0 * 10**-1 + b0 * 10**-3*S + b1 * 10**-4 * S**2 + c0*10**-3 * T + c1*10**-5*T**2 + d0*S*T*10**-5

    def calc_CO3(self, Absorbance, voltage, dilution, vol_injected, manual_salinity):

        #voltage = round(voltage, prec["Voltage"])

        T_cuvette = (self.TempCalCoef[0] * voltage) + self.TempCalCoef[1] #, prec["fb_temperature"])
        # temperature in celsius degres for Sharp and Byrne 2019
        T = T_cuvette

        A1, A2, A3 = Absorbance

        if manual_salinity is None:
            sal = self.fb_data["salinity"]   #round(, prec["salinity"])
            print ('fbox sal', self.fb_data["salinity"])
        else:
            sal = manual_salinity               #round(, prec["salinity"])

        S_corr = sal * dilution                 #round(, prec["salinity"])
        logging.debug(f"S_corr {S_corr}")

        R = (A2 - A3) / (A1 - A3)

        # coefficients from Patsavas et al. 2015 (salinity correction only)
        #e1 = 0.311907 - 0.002396 * S_corr + 0.000080 * S_corr ** 2
        #e3e2 = 3.061 - 0.0873 * S_corr + 0.0009363 * S_corr ** 2
        #log_beta1_e2 = 5.507074 - 0.041259 * S_corr + 0.000180 * S_corr ** 2
        
        # sharp and Byrne 2019 (temperature and salinity correction) ( 17<S<40)

        e1 = (1.09519*10**-1) + (4.49666*10**-3)*S_corr + (1.95519*10**-3)*T + (2.44460*10**-5)*T**2 + (-2.01796*10**-5)*S_corr*T
        e3e2 = (32.4812*10**-1) + (-79.7676*10**-3)*S_corr + (6.28521*10**-4)*S_corr**2 + (-11.8691*10**-3)*T + (-3.58709*10**-5)*T**2 + (32.5849*10**-5)*S_corr*T
        log_beta1_e2 = (55.6674*10**-1) + (-51.0194*10**-3)*S_corr + (4.61423*10**-4)*S_corr**2 + (-13.6998*10**-5)*S_corr*T


        logging.debug(f"R {R} e1 {e1} e3e2{e3e2}")
        arg = (R - e1) / (1 - R * e3e2)
        logging.debug(f"arg {arg}")
        # CO3 = dilution * 1.e6*(10**-(log_beta1_e2 + np.log10(arg)))  # umol/kg
        CO3 = 1.0e6 * (10 ** -(log_beta1_e2 + np.log10(arg)))  # umol/kg
        logging.debug(f"[CO3--] = {CO3} umol/kg, T = {T_cuvette}")

        return [
            CO3,
            e1,
            e3e2,
            log_beta1_e2,
            voltage,
            self.fb_data["salinity"],
            A1,
            A2,
            R,
            T_cuvette,
            vol_injected,
            S_corr,
            A3,
        ]

    def calc_final_co3(self, co3_eval):

        x = co3_eval["Vol_injected"].values
        y = co3_eval["CO3"].values
        try:
            slope1, intercept, r_value = get_linregress(x, y)
            logging.debug(f"slope = {slope1}, intercept = {intercept}, r2= {r_value}")
        except:
            logging.error('could not find CO3 intercept, FIX')
            (slope1, intercept, r_value) = 999, 999, 999
        intercept = y[0]
        return [slope1, intercept, r_value]


class pH_instrument(Common_instrument):
    def __init__(self, panelargs):
        super().__init__(panelargs)
        self.load_config_pH()

        self.maxval = self.THR * 1.05
        self.minval = self.THR * 0.95

        # setup PWM and SSR lines
        if not self.args.localdev:
            for pin in range(4):
                self.rpi.set_mode(self.led_slots[pin], pigpio.OUTPUT)
                self.rpi.set_PWM_frequency(self.led_slots[pin], 100)
                self.rpi.set_PWM_dutycycle(self.led_slots[pin], 0)
                self.rpi.set_mode(self.ssrLines[pin], pigpio.OUTPUT)
            self.reset_lines()

    def load_config_pH(self):

        conf_pH = config_file["pH"]
        calibr = config_file["TrisBuffer"]
        self.buffer_sal = calibr["S_tris_buffer"]
        self.dye = conf_pH["Default_DYE"]
        if self.dye == "MCP":
            self.HI = int(conf_pH["MCP_wl_HI"])
            self.I2 = int(conf_pH["MCP_wl_I2"])
        elif self.dye == "TB":
            self.HI = int(conf_pH["TB_wl_HI"])
            self.I2 = int(conf_pH["TB_wl_I2"])

        self.NIR = int(conf_pH["wl_NIR-"])
        self.wvl_needed = (self.HI, self.I2, self.NIR)
        self.led_slots = conf_pH["LED_SLOTS"]
        self.LEDS = [int(conf_pH["LED1"]), int(conf_pH["LED2"]), int(conf_pH["LED3"])]
        self.PPHOX_string_version = conf_pH['PPHOX_STRING_VERSION']

    def adjust_LED(self, led, LED):
        self.rpi.set_PWM_dutycycle(self.led_slots[led], LED)

    async def find_LED(self, led_ind, adj, LED):

        if led_ind == 2:
            self.minval = self.THR * 0.90

        logging.debug(f"led_ind {led_ind}")
        step = 0

        increment = 50
        self.led_action = None
        # Increment is decreased twice in case we change the direction
        # of decrease/increase
        while not adj:
            logging.debug(f"step is {step}")
            step += 1
            self.adjust_LED(led_ind, LED)
            await asyncio.sleep(0.1)
            pixelLevel = await self.get_sp_levels(self.wvlPixels[led_ind])
            await asyncio.sleep(0.1)
            logging.debug(f"pixelLevel {pixelLevel}")

            if pixelLevel > self.maxval and LED > 15:
                logging.debug("case0  Too high pixellevel, decrease LED ")
                if self.led_action == "increase":
                    increment = increment / 2
                LED = max(1, LED - increment)
                self.led_action = "decrease"

            elif pixelLevel < self.minval and LED < 90:
                logging.debug("case3 Too low pixellevel, increase LED")
                if self.led_action == "decrease":
                    increment = increment / 2
                LED = min(99, LED + increment)
                self.led_action = "increase"

            elif pixelLevel > self.maxval and LED <= 15:
                logging.debug("case1 decrease int time")
                res = "decrease int time"
                break

            elif pixelLevel < self.minval and LED >= 90:
                logging.debug("case2 Too low pixellevel and high LED")
                res = "increase int time"
                break
            else:
                adj = True
                res = "adjusted"

        return LED, adj, res

    async def precheck_leds_to_adj(self):
        logging.debug('precheck leds')
        self.spectrum = await self.spectrometer_cls.get_intensities()
        led_vals = np.array(self.spectrum)[self.wvlPixels]
        max_cond = all(n < self.maxval for n in led_vals)
        if self.autoadj_opt == 'ON_NORED':
            min_cond = (led_vals[0] > self.minval and led_vals[1] > self.minval)
        else:
            min_cond = all(n >self.THR for n in led_vals)
        logging.debug(f"precheck result {max_cond,min_cond,led_vals}")
        return (max_cond and min_cond)

    async def auto_adjust(self, *args):
        self.adj_action = None
        increment_sptint = 200
        n = 0
        while n < 15:
            n += 1

            logging.debug("inside call adjust ")
            adj1, adj2, adj3 = False, False, False
            #LED1, LED2, LED3 = None, None, None
            res1, res2, res3 = None, None, None
            await self.spectrometer_cls.set_integration_time(self.specIntTime)
            await asyncio.sleep(0.5)
            logging.info(f"Trying {self.specIntTime} ms integration time...")

            LED1, adj1, res1 = await self.find_LED(led_ind=0, adj=adj1, LED=self.LEDS[0])

            if adj1:
                logging.debug("*** adj1 = True")

                LED2, adj2, res2 = await self.find_LED(led_ind=1, adj=adj2, LED=self.LEDS[1])

                if adj2:
                    logging.debug("*** adj2 = True")

                    if self.autoadj_opt == 'ON_NORED':
                        LED3, adj3, res = 99, True, "READ adjusting disabled"
                    else:
                        LED3, adj3, res3 = await self.find_LED(led_ind=2, adj=adj3, LED=self.LEDS[2])

                else:
                    LED3 = 50
            else:
                LED2 = 50
                LED3 = 50

            if any(t == "decrease int time" for t in [res1, res2, res3]):
                if self.adj_action == "increase":
                    increment_sptint = increment_sptint / 2
                self.adj_action = "decrease"
                self.specIntTime -= increment_sptint
                if self.specIntTime < 50:
                    logging.info("self.specIntTime < 50, stop")
                    break

            elif any(t == "increase int time" for t in [res1, res2, res3]):
                if self.specIntTime < 5000:
                    if self.adj_action == "decrease":
                        increment_sptint = increment_sptint / 2

                    self.specIntTime += increment_sptint
                    self.adj_action = "increase"

                else:
                    logging.info("too high spt, stop")
                    break

            elif adj1 and adj2 and adj3:
                logging.info("Levels adjusted")
                break

        if not adj1 or not adj2 or not adj3:
            result = False
        else:
            result = True

        return LED1, LED2, LED3, result

    def calc_pH(self, Absorbance, voltage, dilution, vol_injected, manual_salinity=None):
        A1, A2, Anir = Absorbance
        #voltage = round(voltage, prec["Voltage"])
        T_cuvette = round((self.TempCalCoef[0] * voltage) + self.TempCalCoef[1], prec["T_cuvette"])
        T = 273.15 + T_cuvette

        if manual_salinity is None:
            fb_sal = round(self.fb_data["salinity"], prec["salinity"])
        else:
            fb_sal = manual_salinity #round(, prec["salinity"])

        S_corr = fb_sal * dilution #round(, prec["salinity"])

        R = A2 / A1

        if self.dye == "TB":
            e1 = -0.00132 + 1.6e-5 * T
            e2 = 7.2326 + -0.0299717 * T + 4.6e-5 * (T ** 2)
            e3 = 0.0223 + 0.0003917 * T
            pK = 4.706 * (S_corr / T) + 26.3300 - 7.17218 * np.log10(T) - 0.017316 * S_corr
            arg = (R - e1) / (e2 - R * e3)
            pH = 0.0047 + pK + np.log10(arg)

        elif self.dye == "MCP":
            e1 = -0.007762 + (4.5174 * 10 ** -5) * T
            e2e3 = -0.020813 + ((2.60262 * 10 ** -4) * T) + (1.0436 * 10 ** -4) * (S_corr - 35)
            arg = (R - e1) / (1 - R * e2e3)
            pK = (
                    5.561224
                    - (0.547716 * S_corr ** 0.5)
                    + (0.123791 * S_corr)
                    - (0.0280156 * S_corr ** 1.5)
                    + (0.00344940 * S_corr ** 2)
                    - (0.000167297 * S_corr ** 2.5)
                    + ((52.640726 * S_corr ** 0.5) * T ** -1)
                    + (815.984591 * T ** -1)
            )
            if arg > 0:
                pH = pK + np.log10(arg)
            else:
                pH = 99.9999

            ## to fit the log file
            e2, e3 = e2e3, -99
        else:
            raise ValueError("wrong DYE: " + self.dye)

        '''pH = round(pH, prec["pH"])
        pK = round(pK, prec["pK"])
        e1 = round(e1, prec["e1"])
        e2 = round(e2, prec["e2"])
        e3 = round(e3, prec["e3"])'''

        return [
            pH,
            pK,
            e1,
            e2,
            e3,
            voltage,
            fb_sal,
            A1,
            A2,
            T_cuvette,
            S_corr,
            Anir,
            vol_injected,
            self.TempProbe_id,
            self.temp_iscalibrated,
            self.TempCalCoef[0],
            self.TempCalCoef[1],
            self.dye,
        ]

    def calc_pH_buffer_theo(self, evalPar_df):
        # Recalculate buffer pH to cuvette temperature
        t_cuv_K = evalPar_df["T_cuvette"][0] + 273.15
        par1 = (11911.08 - 18.2499 * 35 - 0.039336 * 35 ** 2) / (t_cuv_K)
        par2 = (64.52243-0.084041*35)*np.log(t_cuv_K)
        sal = 35
        pH_buffer_theoretical = par1 - 366.27059+0.53993607*sal+0.00016329*sal**2 + par2 - 0.11149858*(t_cuv_K)
        return pH_buffer_theoretical

    def pH_correction(self, evalPar_df):
        """
        This function is for calculation of the final corrected pH value from 4 measurements,
        Find a best fit.
        :param evalPar_df: input dataframe is 4 measurements
        :return: final pH and other params
        """

        dpH_dT = -0.0155
        evalAnir = evalPar_df["Anir"].mean()     #, prec["evalAnir"]
        t_cuvette = evalPar_df["T_cuvette"][0]


        # pH_t_corr - List with pH values corrected for temperature drift inside the cuvette while it's measuring
        # reference is the first temperature

        if self.args.localdev:
            logging.info("ph eval local mode")
            x = evalPar_df["Vol_injected"].values
            pH_t_corr = [7.3, 7.2, 7.22, 7.19]
            y = pH_t_corr
        else:
            x = evalPar_df["Vol_injected"].values
            pH_t_corr = evalPar_df["pH"] + dpH_dT * (t_cuvette - evalPar_df["T_cuvette"])
            y = pH_t_corr.values

        meas_std = np.std(y)
        logging.info('Measurement Standard Deviation {}'.format(meas_std))
        # Check std between different measurement
        if meas_std > 0.001:
            # If std is high, get the linear regression to estimate the slope (perturbations)
            # generated by adding the dye into the sample

            slope_all, intercept_all, r_value_all = get_linregress(x, y)
            r_values, slopes, intercepts, x_vars, y_vars = [], [], [], [], []

            #Calculate fit for different combinations fo measurements to find outliers
            for n in [0, self.ncycles - 1]: #range(self.ncycles)
                new_x = np.delete(x, n)
                new_y = np.delete(y, n)
                slope_all, intercept, r_value = get_linregress(new_x, new_y)

                r_values.append(r_value)
                slopes.append(slope_all)
                intercepts.append(intercept)
                x_vars.append(new_x)
                y_vars.append(new_y)

            # Find the best fit
            r2_remove_1point = [n ** 2 for n in r_values]
            r2_value2_best = np.max(r2_remove_1point)

            if r_value_all**2 > r2_value2_best:
                # all point give the best fit
                intercept = intercept_all
                slope = slope_all
                r_value = r_value_all

            else:
                # removing one of the point give better fit
                idx_of_best_fit = np.argmax(r2_remove_1point)

                intercept = intercepts[idx_of_best_fit]
                slope = slopes[idx_of_best_fit]
                r_value = r_values[idx_of_best_fit]
                x = x_vars[idx_of_best_fit]
                y = y_vars[idx_of_best_fit]

            #if r_value ** 2 < 0.9:
            #    intercept = np.mean(y)
        else:
            intercept = np.mean(y)
            r_value = 0
            slope = 0

        intercept = round(intercept, prec['pH'])

        pH_insitu = round(intercept + dpH_dT * (
                self.fb_data["temperature"] - t_cuvette), prec['pH'])
        pH_cuvette = intercept

        logging.debug("leave pH eval")
        return (
            pH_cuvette, t_cuvette,
            slope, evalAnir,
            pH_insitu, x, y, intercept, r_value**2, pH_t_corr
        )


class Test_CO3_instrument(CO3_instrument):
    def __init__(self, panelargs):
        super().__init__(panelargs)
        pass

    async def auto_adjust(self, *args):
        adjusted = True
        pixelLevel = 500
        return adjusted, pixelLevel

    def calc_CO3(self, absSp, voltage, dilution, vol_injected,manual_salinity):
        return [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    def reset_lines(self):
        pass

    async def set_Valve(self, status):
        if not status:
            logging.info("Closing the inlet valve localdev")
        await asyncio.sleep(0.3)

    def set_Valve_sync(self, status):
        if not status:
            logging.info("Closing the inlet  valve localdev ")
        else:
            logging.info("Opening the valve localdev ")
        time.sleep(0.3)

    def turn_on_relay(self, line):
        pass

    def turn_off_relay(self, line):
        pass

    async def pumping(self, pumpTime):
        self.turn_on_relay(self.wpump_slot)  # start the instrument pump
        if not self.args.co3:
            self.turn_on_relay(self.stirrer_slot)  # start the stirrer
        await asyncio.sleep(pumpTime)
        if not self.args.co3:
            self.turn_off_relay(self.stirrer_slot)  # turn off the pump
        self.turn_off_relay(self.wpump_slot)  # turn off the stirrer
        return

    def get_Voltage(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        Voltage = round(v / nAver, prec["Voltage"])
        return Voltage


class Test_pH_instrument(pH_instrument):
    def __init__(self, panelargs):
        super().__init__(panelargs)
        pass

    def adjust_LED(self, led, LED):
        pass

    async def find_LED(self, led_ind, adj, LED):
        LED = 50
        adj = True
        res = "adjusted"

        return LED, adj, res

    async def auto_adjust(self, *args):
        result = True
        LED1, LED2, LED3 = 50, 60, 70

        if self.autoadj_opt == 'ON_NORED':
            logging.debug('NO RED in adjusting')
            LED3, adj3, res = 99, True, "READ adjusting disabled"

        return LED1, LED2, LED3, result

    def reset_lines(self):
        pass

    async def set_Valve(self, status):
        if not status:
            logging.info("Closing the valve localdev pH")
        else:
            logging.info("Opening the valve localdev pH")
        await asyncio.sleep(0.01)

    def set_Valve_sync(self, status):
        if not status:
            logging.info("Closing the valve localdev pH")
        else:
            logging.info("Opening the valve localdev pH")
        time.sleep(0.01)

    def turn_on_relay(self, line):
        pass

    def turn_off_relay(self, line):
        pass

    async def pumping(self, pumpTime):
        self.turn_on_relay(self.wpump_slot)  # start the instrument pump
        self.turn_on_relay(self.stirrer_slot)  # start the stirrer
        await asyncio.sleep(0.01)
        self.turn_off_relay(self.stirrer_slot)  # turn off the pump
        self.turn_off_relay(self.wpump_slot)  # turn off the stirrer
        return

    '''async def cycle_line(self, line, nCycles):
        for nCy in range(nCycles):
            self.turn_on_relay(line)
            await asyncio.sleep(0.01)
            self.turn_off_relay(line)
            await asyncio.sleep(0.01)'''

    async def precheck_leds_to_adj(self):
        logging.info('returning True in precheck leds localdev')
        return True

    async def pump_dye(self, nshots):
        # biochemical valve solenoid pump
        for shot in range(nshots):
            logging.debug("inject shot {}".format(shot))
            self.turn_on_relay(self.dyepump_slot)
            await asyncio.sleep(0.05)
            self.turn_off_relay(self.dyepump_slot)
            await asyncio.sleep(0.05)
        return

    def print_Com(self, port, txtData):
        pass

    def get_Voltage(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        Voltage = round(v / nAver, prec["Voltage"])
        return Voltage

    def calc_wavelengths(self):
        """
        assign wavelengths to pixels
        and find pixel number of reference wavelengths
        """
        wvls = self.spectrometer_cls.get_wavelengths()

        return wvls

    async def get_sp_levels(self, pixel):
        self.spectrum = await self.spectrometer_cls.get_intensities()
        return self.spectrum[pixel]
