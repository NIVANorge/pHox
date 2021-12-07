import seabreeze
seabreeze.use("cseabreeze")
from seabreeze.spectrometers import Spectrometer
from seabreeze.spectrometers import list_devices
first = Spectrometer.from_first_available()
minmax = first.integration_time_micros_limits
print (first, minmax)
all = list_devices()
print (all)
