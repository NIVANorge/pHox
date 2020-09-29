
from ADCDACPi import ADCDACPi
from ADCDifferentialPi import ADCDifferentialPi
import serial
import serial.tools.list_ports
import time
import struct
import sys


adc = ADCDifferentialPi(0x68, 0x69, 14)
adc.set_pga(1)


class Voltage(object):
	
	def __init__(self, chn, name):
		self.channel = chn
		self.name = name
		self.value = None
		return
		
	def read(self):
		self.value = adc.read_voltage(self.channel)
		return(self.value)
		

		

class CO2Detector(object):
	
	def __init__(self):
		ports = list(serial.tools.list_ports.comports())
		self.port = ports[0]
		self.conn = None
		self.buff = None
		self.data = {}
		return
	
		
	def open(self):
		self.conn = serial.Serial(self.port[0],baudrate=115200,timeout=5, parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE,bytesize=serial.EIGHTBITS,rtscts=False,dsrdtr=False,xonxoff=False)
		return
		
	def close(self):
		self.conn.close()
		return
		
	def read(self):
		self.conn.flushInput()
		synced = False
		count  = 100
		while not synced:
			b = self.conn.read(1)
			if len(b) and (b[0] == b'\x07'[0]):
				synced = True
			count = count - 1
			if count < 0:
				self.data['CH1_Vout'] = -999.0
				self.data['ppm']      = -999.0
				self.data['type']     = b'\x81'
				self.data['range']    = -999.0
				self.data['sn']       = b'no_sync'
				self.data['VP']       = -999.0
				self.data['VT']       = -999.0
				self.data['mode']     = b'\x80'
				#raise ValueError('cannot sync to CO2 detector')
				return(self.data) 
		try:
			self.buff=self.conn.read(37)
			self.data['CH1_Vout'] = struct.unpack('<f',self.buff[0:4])[0]
			self.data['ppm']      = struct.unpack('<f',self.buff[4:8])[0]
			self.data['type']     = self.buff[8:9]
			self.data['range']    = struct.unpack('<f',self.buff[9:13])[0]
			self.data['sn']       = self.buff[13:27]
			self.data['VP']       = struct.unpack('<f',self.buff[27:31])[0]
			self.data['VT']       = struct.unpack('<f',self.buff[31:35])[0]
			self.data['mode']     = self.buff[35:36]
			if self.data['type'][0] != b'\x81'[0]:
				raise ValueError('the gas type is not correct')
			if self.data['mode'][0] != b'\x80'[0]:
				raise ValueError('the detector mode is not correct')
		except:
			raise
		return(self.data)
		
	def toString(self):
		l  = ('CH1_Vout', 'ppm', 'range', 'VP', 'VT')
		s  = [ '{:s}={:-.3f}'.format(x,self.data[x]) for x in l ]
		#s += [ 'SN={0}'.format(self.data['sn']) ]
		s += [ 'SN={0}'.format(self.data['sn'].decode('ascii').strip()) ]
		return(s)
		
		
Tw   = Voltage(1, 'Tw')
Ta   = Voltage(2, 'Ta')
Pw   = Voltage(3, 'Pw')	
Flow = Voltage(4, 'Flow')	
Pa   = Voltage(5, 'Pa')
CO = CO2Detector()
CO.open()

while True:
	try:
		Ta.read()
		Tw.read()
		Pw.read()
		Flow.read()
		Pa.read()
		CO.read()
		s = [ '{:s}={:-.3f}'.format(x.name, x.value) for x in (Ta,Tw,Pw,Flow,Pa) ]
		#s = []
		s += CO.toString()
		print('  '.join(s))		
		time.sleep(1)
	except KeyboardInterrupt:
		CO.close()
		print('')
		sys.exit(0)
	except Exception as err:
		raise
		
		




