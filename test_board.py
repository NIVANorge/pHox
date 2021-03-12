import pigpio
import RPi.GPIO as GPIO
from ADCDifferentialPi import ADCDifferentialPi
    
rpi = pigpio.pi()
adc = ADCDifferentialPi(0x68, 0x69, 14)
adc.set_pga(1)

