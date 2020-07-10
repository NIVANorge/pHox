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
from util import config_file, base_folderpath
try:
    import pigpio
    import RPi.GPIO as GPIO
    from ADCDACPi import ADCDACPi
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
            await asyncio.sleep(0.1)
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
            time.sleep(self.integration_time)
            sp = self.test_df["0"].values + random.randrange(-1000, 1000, 1)
            return sp

        async_thread_wrapper = AsyncThreadWrapper(_get_intensities)
        return await async_thread_wrapper.result_returner()


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
        logging.info("spectro_type set to '{}' for spec '{}'".format(self.spectro_type, self.spec))

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

    def set_scans_average(self, num):
        # not supported for FLAME spectrom
        self.spec.scans_to_average(num)


class Common_instrument(object):
    """ This class is a parent class for pH instrument and CO3 instrument
        since both of these classes use spectrometers. Class for pure pCO2 version
        will be separate since there are too many differences
    """
    def __init__(self, panelargs):
        logging.getLogger()

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
            self.adcdac = ADCDACPi()

        # For signaling to threads
        self._exit = False

    def reset_lines(self):
        # set values in outputs of pins
        self.rpi.write(self.wpump_slot, 0)
        self.rpi.write(self.dyepump_slot, 0)
        self.rpi.write(self.stirrer_slot, 0)
        self.rpi.write(self.extra_slot, 0)

    async def set_Valve(self, status):
        chEn = self.valve_slots[0]
        ch1, ch2 = self.valve_slots[1], self.valve_slots[2]
        if status:
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
        if status:
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
        self._autostart = self.to_bool(conf_operational["AUTOSTART"])
        self._automode = conf_operational["AUTOSTART_MODE"]
        self.DURATION = int(conf_operational["DURATION"])
        self.vNTCch = int(conf_operational["T_PROBE_CH"])
        if not (self.vNTCch in range(9)):
            self.vNTCch = 8
        self.samplingInterval = int(conf_operational["SAMPLING_INTERVAL_MIN"])
        self.pumpTime = int(conf_operational["pumpTime"])
        self.mixT = int(conf_operational["mixTime"])
        self.waitT = int(conf_operational["waitTime"])
        self.ncycles = int(conf_operational["ncycles"])
        self.nshots = int(conf_operational["dye_nshots"])
        self.specAvScans = int(conf_operational["specAvScans"])
        self.wpump_slot = conf_operational["WPUMP_SLOT"]
        self.dyepump_slot = conf_operational["DYEPUMP_SLOT"]
        self.stirrer_slot = conf_operational["STIRR_SLOT"]
        self.extra_slot = conf_operational["SPARE_SLOT"]

        # TODO: Replace ssrlines with new lines
        # keep it for now since there is a loop dependent on self.ssrLines
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
        self.ship_code = conf_operational["Ship_Code"]

        if self.spectrometer_cls.spectro_type == "FLMT":
            self.THR = int(conf_operational["LIGHT_THRESHOLD_FLAME"])
        elif self.spectrometer_cls.spectro_type == "STS":
            self.THR = int(conf_operational["LIGHT_THRESHOLD_STS"])

    def update_temp_probe_coef(self):
        path = 'configs/temperature_sensors_config.json'
        with open(path) as json_file:
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

    async def cycle_line(self, line, nCycles):
        for nCy in range(nCycles):
            self.turn_on_relay(line)
            await asyncio.sleep(self.waitT)
            self.turn_off_relay(line)
            await asyncio.sleep(self.waitT)

    async def pump_dye(self, nshots):
        for shot in range(nshots):
            self.turn_on_relay(self.dyepump_slot)
            await asyncio.sleep(0.3)
            self.turn_off_relay(self.dyepump_slot)
            await asyncio.sleep(0.3)
        return

    # COMMON
    def get_wvlPixels(self, wvls_spectrum):
        self.wvlPixels = []
        for wl in self.wvl_needed:
            self.wvlPixels.append(self.find_nearest(wvls_spectrum, wl))

    def print_Com(self, port, txtData):
        port.write(txtData)

    def get_Vd(self, nAver, channel):
        V = 0.0000
        for i in range(nAver):
            try:
                V += self.adc.read_voltage(channel)
            except TimeoutError:
                print('Timeout error in get_Vd')
                pass
        return V / nAver

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

        self.light_slot = conf["LIGHT_SLOT"]
        self.dye = conf["Default_DYE"]
        self.wvl_needed = (self.wvl1, self.wvl2, 350)

    async def auto_adjust(self, *args):

        adjusted = False
        pixelLevel = await self.get_sp_levels(self.wvlPixels[1])

        increment = (self.specIntTime * self.THR / pixelLevel) - self.specIntTime

        maxval = self.THR * 1.05
        minval = self.THR * 0.95

        while adjusted == False:

            await self.spectrometer_cls.set_integration_time(self.specIntTime)
            await asyncio.sleep(self.specIntTime * 1.0e-3)
            pixelLevel = await self.get_sp_levels(self.wvlPixels[1])

            if self.specIntTime > 5000:
                logging.info("Too high spec int time value,break")
                break

            elif self.specIntTime < 100:
                logging.info("Something is wrong, specint time is too low,break ")
                break

            elif pixelLevel < minval:
                self.specIntTime += increment
                increment = increment / 2

            elif pixelLevel > maxval:
                self.specIntTime -= increment
                increment = increment / 2

            else:
                adjusted = True

        return adjusted, pixelLevel

    def calc_CO3(self, absSp, vNTC, dilution, vol_injected, manual_salinity):

        vNTC = round(vNTC, prec["vNTC"])

        T_cuvette = round((self.TempCalCoef[0] * vNTC) + self.TempCalCoef[1], prec["fb_temperature"])
        # T = 273.15 + T_cuvette
        A1 = round(absSp[self.wvlPixels[0]], prec["A1"])
        A2 = round(absSp[self.wvlPixels[1]], prec["A2"])
        A_350 = round(absSp[self.wvlPixels[2]], prec["A2"])
        print ('A350', A_350)
        # volume in ml

        if manual_salinity is None:
            sal = round(self.fb_data["salinity"], prec["salinity"])
        else:
            sal = round(manual_salinity, prec["salinity"])

        S_corr = round(sal * dilution, prec["salinity"])
        logging.debug(f"S_corr {S_corr}")
        R = A2 / A1
        # coefficients from Patsavas et al. 2015
        e1 = 0.311907 - 0.002396 * S_corr + 0.000080 * S_corr ** 2
        e2e3 = 3.061 - 0.0873 * S_corr + 0.0009363 * S_corr ** 2
        log_beta1_e2 = 5.507074 - 0.041259 * S_corr + 0.000180 * S_corr ** 2

        logging.debug(f"R {R}e1 {e1} e2e3{e2e3}")
        arg = (R - e1) / (1 - R * e2e3)
        logging.debug(f"arg {arg}")
        # CO3 = dilution * 1.e6*(10**-(log_beta1_e2 + np.log10(arg)))  # umol/kg
        CO3 = 1.0e6 * (10 ** -(log_beta1_e2 + np.log10(arg)))  # umol/kg
        logging.debug(f"[CO3--] = {CO3} umol/kg, T = {T_cuvette}")

        return [
            CO3,
            e1,
            e2e3,
            log_beta1_e2,
            vNTC,
            self.fb_data["salinity"],
            A1,
            A2,
            R,
            T_cuvette,
            vol_injected,
            S_corr,
            A_350,
        ]

    def calc_final_co3(self, co3_eval):
        print (co3_eval)
        x = co3_eval["Vol_injected"].values
        y = co3_eval["CO3"].values
        try:
            slope1, intercept, r_value = get_linregress(x, y)
            logging.debug(f"slope = {slope1}, intercept = {intercept}, r2= {r_value}")
        except:
            logging.error('could not find CO3 intercept, FIX')
        (slope1, intercept, r_value) = 999, 999, 999
        return [slope1, intercept, r_value]


class pH_instrument(Common_instrument):
    def __init__(self, panelargs):
        super().__init__(panelargs)
        # self.args = panelargs
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
        self.buffer_pH_value = calibr["pH_tris_buffer"]
        self.dye = conf_pH["Default_DYE"]
        if self.dye == "MCP":
            self.HI = int(conf_pH["MCP_wl_HI"])
            self.I2 = int(conf_pH["MCP_wl_I2"])
        elif self.dye == "TB":
            self.HI = int(conf_pH["TB_wl_HI"])
            self.I2 = int(conf_pH["TB_wl_I2"])

        self.NIR = int(conf_pH["wl_NIR-"])
        self.wvl_needed = (self.HI, self.I2, self.NIR)

        # self.molAbsRats = default['MOL_ABS_RATIOS']
        self.led_slots = conf_pH["LED_SLOTS"]
        self.LED1 = int(conf_pH["LED1"])
        self.LED2 = int(conf_pH["LED2"])
        self.LED3 = int(conf_pH["LED3"])
        self.LEDS = [self.LED1, self.LED2, self.LED3]
        self.PPHOX_string_version = conf_pH['PPHOX_STRING_VERSION']

    def adjust_LED(self, led, LED):
        self.rpi.set_PWM_dutycycle(self.led_slots[led], LED)

    async def find_LED(self, led_ind, adj, LED):

        if led_ind == 2:
            self.minval = self.THR * 0.90

        logging.info(f"led_ind {led_ind}")
        step = 0

        increment = 50
        self.led_action = None
        # Increment is decreased twice in case we change the direction
        # of decrease/increase
        while not adj:
            logging.info(f"step is {step}")
            step += 1
            self.adjust_LED(led_ind, LED)
            await asyncio.sleep(0.1)
            pixelLevel = await self.get_sp_levels(self.wvlPixels[led_ind])
            await asyncio.sleep(0.1)
            logging.info(f"pixelLevel {pixelLevel}")

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
        min_cond = (led_vals[0] > self.minval and led_vals[1] > self.minval and led_vals[2] > self.THR * 0.90)
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

            LED1, adj1, res1 = await self.find_LED(led_ind=0, adj=adj1, LED=self.LED1)

            if adj1:
                logging.info("*** adj1 = True")
                LED2, adj2, res2 = await self.find_LED(led_ind=1, adj=adj2, LED=self.LED2)

                if adj2:
                    logging.info("*** adj2 = True")
                    LED3, adj3, res3 = await self.find_LED(led_ind=2, adj=adj3, LED=self.LED3)
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
                    logging.info("self.specIntTime < 50")
                    break

            elif any(t == "increase int time" for t in [res1, res2, res3]):
                if self.specIntTime < 5000:
                    if self.adj_action == "decrease":
                        increment_sptint = increment_sptint / 2

                    self.specIntTime += increment_sptint
                    self.adj_action = "increase"

                else:
                    logging.info("too high spt")
                    break

            elif adj1 and adj2 and adj3:
                logging.info("Levels adjusted")
                break

        if not adj1 or not adj2 or not adj3:
            result = False
        else:
            result = True

        return LED1, LED2, LED3, result

    def calc_pH(self, absSp, vNTC, dilution, vol_injected, manual_salinity=None):

        vNTC = round(vNTC, prec["vNTC"])
        T_cuvette = round((self.TempCalCoef[0] * vNTC) + self.TempCalCoef[1], prec["T_cuvette"])

        T = 273.15 + T_cuvette
        A1 = round(absSp[self.wvlPixels[0]], prec["A1"])
        A2 = round(absSp[self.wvlPixels[1]], prec["A2"])
        Anir = round(absSp[self.wvlPixels[2]], prec["Anir"])
        if manual_salinity is None:
            fb_sal = round(self.fb_data["salinity"], prec["salinity"])
        else:
            fb_sal = round(manual_salinity, prec["salinity"])

        S_corr = round(fb_sal * dilution, prec["salinity"])

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

        pH = round(pH, prec["pH"])
        pK = round(pK, prec["pK"])
        e1 = round(e1, prec["e1"])
        e2 = round(e2, prec["e2"])
        e3 = round(e3, prec["e3"])

        return [
            pH,
            pK,
            e1,
            e2,
            e3,
            vNTC,
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



    def pH_eval(self, evalPar_df):
        logging.debug(f'evalPar_df["T_cuvette"] {evalPar_df["T_cuvette"]}')
        dpH_dT = -0.0155
        evalAnir = round(evalPar_df["Anir"].mean(), prec["evalAnir"])
        t_cuvette = evalPar_df["T_cuvette"][0]
        pH_lab = evalPar_df["pH"][0]
        pH_t_corr = evalPar_df["pH"] + dpH_dT * (t_cuvette - evalPar_df["T_cuvette"])

        nrows = evalPar_df.shape[0]

        if self.args.localdev:
            logging.info("ph eval local mode")
            x = evalPar_df["Vol_injected"].values
            pH_t_corr = [7.1, 7.2, 7.31, 7.2]
            y = pH_t_corr
            final_slope = 1
            perturbation = 1
            pH_insitu = 999
            pH_lab = 999
            slope1, intercept, r_value = get_linregress(x, y)

        else:
            if nrows > 1:
                x = evalPar_df["Vol_injected"].values
                y = pH_t_corr.values

                slope1, intercept, r_value = get_linregress(x, y)
                final_slope = slope1
                if r_value ** 2 > 0.9:
                    pH_lab = intercept
                    logging.info("r_value **2 > 0.9")
                else:
                    logging.info("r_value **2 < 0.9 take three first measurements")
                    x = x[1:]
                    y = y[1:]

                    slope2, intercept, r_value = get_linregress(x, y)
                    final_slope = slope2
                    if r_value ** 2 > 0.9:
                        pH_lab = intercept
                    else:
                        pH_lab = pH_t_corr[1]

            pH_insitu = round(pH_lab + dpH_dT * (self.fb_data["temperature"] - t_cuvette), prec["pH"])
            perturbation = round(slope1, prec["perturbation"])
            pH_lab = round(pH_lab, prec["pH"])

        logging.info("leave pH eval")
        return (
            pH_lab, t_cuvette,
            perturbation, evalAnir,
            pH_insitu, x, y, final_slope, intercept, pH_t_corr
        )


class Test_CO3_instrument(CO3_instrument):
    def __init__(self, panelargs):
        super().__init__(panelargs)
        pass

    async def auto_adjust(self, *args):
        adjusted = True
        pixelLevel = 500
        return adjusted, pixelLevel

    def calc_CO3(self, absSp, vNTC, dilution, vol_injected,manual_salinity):
        return [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    def reset_lines(self):
        pass

    async def set_Valve(self, status):
        pass
        if status:
            logging.info("Closing the valve ...")
        await asyncio.sleep(0.3)

    def set_Valve_sync(self, status):
        if status:
            logging.info("Closing the valve")
        else:
            logging.info("Opening the valve")
        time.sleep(0.3)

    def turn_on_relay(self, line):
        pass

    def turn_off_relay(self, line):
        pass

    async def pumping(self, pumpTime):
        self.turn_on_relay(self.wpump_slot)  # start the instrument pump
        self.turn_on_relay(self.stirrer_slot)  # start the stirrer
        await asyncio.sleep(pumpTime)
        self.turn_off_relay(self.stirrer_slot)  # turn off the pump
        self.turn_off_relay(self.wpump_slot)  # turn off the stirrer
        return

    def get_Vd(self, nAver, channel):
        v = 0
        for i in range(nAver):
            v += 0.6
        return v / nAver


class Test_instrument(pH_instrument):
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
        return LED1, LED2, LED3, result

    def reset_lines(self):
        pass

    async def set_Valve(self, status):
        pass
        if status:
            logging.info("Closing the valve ...")
        await asyncio.sleep(0.3)

    def set_Valve_sync(self, status):
        if status:
            logging.info("Closing the valve")
        else:
            logging.info("Opening the valve")
        time.sleep(0.3)

    def turn_on_relay(self, line):
        pass

    def turn_off_relay(self, line):
        pass

    async def pumping(self, pumpTime):
        self.turn_on_relay(self.wpump_slot)  # start the instrument pump
        self.turn_on_relay(self.stirrer_slot)  # start the stirrer
        await asyncio.sleep(pumpTime)
        self.turn_off_relay(self.stirrer_slot)  # turn off the pump
        self.turn_off_relay(self.wpump_slot)  # turn off the stirrer
        return

    async def cycle_line(self, line, nCycles):
        for nCy in range(nCycles):
            self.turn_on_relay(line)
            await asyncio.sleep(self.waitT)
            self.turn_off_relay(line)
            await asyncio.sleep(self.waitT)

    async def pump_dye(self, nshots):
        # biochemical valve solenoid pump
        for shot in range(nshots):
            logging.info("inject shot {}".format(shot))
            self.turn_on_relay(self.dyepump_slot)
            await asyncio.sleep(0.15)
            self.turn_off_relay(self.dyepump_slot)
            await asyncio.sleep(0.35)
        return

    def print_Com(self, port, txtData):
        pass

    def get_Vd(self, nAver, channel):
        V = 0
        for i in range(nAver):
            V += 0.6
        return V / nAver

    def calc_wavelengths(self):
        """
        assign wavelengths to pixels 
        and find pixel number of reference wavelengths
        """
        wvls = self.spectrometer_cls.get_wavelengths()

        return wvls

    def get_sp_levels(self, pixel):
        self.spectrum = self.spectrometer_cls.get_intensities()
        return self.spectrum[pixel]
