"""
udp.py
"""

import os
import time
import socket
import threading

from datetime import datetime

# 59801 for pH ,  59803 for CO3, 59802 for pCO2
UDP_SEND = 56801 #config_file["Operational"]['UDP_SEND']
UDP_RECV = 56800 # all FB PC should be always on
UDP_EXIT = False

FERRYBOX = {
    'salinity'   : 33.5,
    'temperature': 15.0,
    'longitude'  : 0.0,
    'latitude'   : 0.0,
    'pumping'    : 1,
    'udp_ok'     : False
    }
DATA_STRING = '$PHOX,-998'


def udp_receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    sock.bind(("", UDP_RECV))
    print('UDP receiver has started.')
    while not UDP_EXIT:
        try:
            (data, _) = sock.recvfrom(500) # 500 is a buffer size
            data = data.decode("utf-8")
            w = data.split(",")
            if data.startswith("$PFBOX,TIME,"):
                try:
                    v = datetime.strptime(w[2], "%Y-%m-%dT%H:%M:%S")
                except Exception as e:
                    print (e)
                    print ('UNable to get time in the format w[2]')
                t = datetime.now()
                if abs(t - v).total_seconds() > 60 :
                    # 1 hour difference:
                    print("will correct time")
                    os.system("sudo date +'%Y-%m-%dT%H:%M:%S' --set={:s}".format(w[2]))
            elif data.startswith("$PFBOX,SAL,"):
                v = float(w[2])
                FERRYBOX["salinity"] = v
            elif data.startswith("$PFBOX,PUMP,"):
                v = int(w[2])
                FERRYBOX["pumping"] = v
            elif data.startswith("$PFBOX,TEMP,"):
                v = float(w[2])
                FERRYBOX["temperature"] = v
            elif data.startswith("$PFBOX,LAT,"):
                v = float(w[2])
                FERRYBOX["latitude"] = v
            elif data.startswith("$PFBOX,LON,"):
                v = float(w[2])
                FERRYBOX["longitude"] = v
            FERRYBOX['udp_ok'] = True
        except socket.timeout:
            FERRYBOX['udp_ok'] = False
        else:
            pass
    sock.close()
    print("UDP receiver has stopped.")


def udp_sender():
    print('UDP sender has started.')
    n = 0
    while not UDP_EXIT:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s = DATA_STRING
        time.sleep(10)
        sock.sendto(bytes(s, encoding='utf8'), ('<broadcast>', UDP_SEND))
        print(f'DATA_STRING: {s}')
        sock.close()
    print("UDP sender has stopped.")

receiver = threading.Thread(target=udp_receiver)
receiver.start()

sender = threading.Thread(target=udp_sender)
sender.start()

