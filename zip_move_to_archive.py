import zipfile
import os
from os import listdir
from os.path import isfile, join
import glob
from datetime import datetime, timedelta
import shutil

path_archive = '/home/pi/pHox/data/archive/'

if not os.path.exists(path_archive):
	os.mkdir(path_archive)
if not os.path.exists(path_archive+'/evl/'):
	os.mkdir(path_archive+'/evl/')
if not os.path.exists(path_archive+'/spt/'):
	os.mkdir(path_archive+'/spt/')
if not os.path.exists(path_archive+'/logs/'):
	os.mkdir(path_archive+'/logs/')


files_evl = glob.glob('/home/pi/pHox/data/evl/*', recursive=True)
files_spt = glob.glob('/home/pi/pHox/data/spt/*', recursive=True)
files_logs = glob.glob('/home/pi/pHox/data/logs/*', recursive=True)
files_pH = glob.glob('/home/pi/pHox/data/pH.log')

files_to_zip = files_evl + files_spt + files_logs + files_pH
if len(files_to_zip) > 1:

	timeStamp = datetime.now().strftime('%Y%m%d_%H')
	zf = zipfile.ZipFile(f'{path_archive}_{timeStamp}.zip', mode='a')

	try:
		zf.debug = 3
		for file in files_to_zip: 
			zf.write(file)
	finally:
		zf.close()


	# move files to archive folder 
	for f in files_evl:
		shutil.move(f, path_archive+'/evl/')
	for f in files_spt:
		print (f)
		shutil.move(f, path_archive+'/spt/')
	for f in files_logs:
		shutil.move(f, path_archive+'/logs/')
else:
	print ("No files to archive")


    