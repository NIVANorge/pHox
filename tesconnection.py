import seabreeze
seabreeze.use("cseabreeze")
from seabreeze.spectrometers import Spectrometer
from seabreeze.spectrometers import list_devices
first = Spectrometer.from_first_available()
print (first)
all = list_devices()
print (all)