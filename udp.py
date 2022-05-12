from datetime import datetime, timedelta
import socket
import threading
import os
import time
import logging
logging.getLogger()
from util import config_file
## type smth on the command line to stop the thread  
#
# MYIP = '192.168.0.200' # would be different on different boxes and should come from the config
# we dont need it if we loop through all interfaces

UDP_SEND = config_file["Operational"]['UDP_SEND'] 
# 59801 for pH ,  59803 for CO3, 59802 for pCO2
UDP_RECV = 56800 # all FB PC should be always on
UDP_IP   = '255.255.255.255'  # Should be the IP of the Ferrybox
UDP_EXIT = False

Ferrybox = {
    'salinity'   : 33.5,
    'temperature': 15.0,
    'longitude'  : 0.0,
    'latitude'   : 0.0,
    'pumping'    : 1,
    'udp_ok'     : False
    }
Data_String = '$PHOX,12345'

def udp_receiver():
    global UDP_EXIT
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    sock.bind(("", UDP_RECV))
    logging.debug('UDP receiver started')
    print ('udp receiver')
    while not UDP_EXIT:
        try:
            (data,addr) = sock.recvfrom(500) # 500 is a buffer size
            data = data.decode("utf-8") 
            w = data.split(",")
            if data.startswith("$PFBOX,TIME,"):
                try:
                    v = datetime.strptime(w[2], "%Y-%m-%dT%H:%M:%S")
                except Exception as e:
                    print (e)
                    print ('UNable to get time in the format w[2]')
                t = datetime.now()
                if abs(t - v).total_seconds() > 60*60 :
                    # 1 hour difference:
                    print("will correct time")
                    os.system("date +'%Y-%m-%dT%H:%M:%S' --set={:s}".format(w[2]))
            elif data.startswith("$PFBOX,SAL,"):
                v = float(w[2])
                Ferrybox["salinity"] = v
            elif data.startswith("$PFBOX,PUMP,"):
                v = int(w[2])
                Ferrybox["pumping"] = v
            elif data.startswith("$PFBOX,TEMP,"):
                v = float(w[2])
                Ferrybox["temperature"] = v
            elif data.startswith("$PFBOX,LAT,"):
                v = float(w[2])
                Ferrybox["latitude"] = v
            elif data.startswith("$PFBOX,LON,"):
                v = float(w[2])
                Ferrybox["longitude"] = v
            Ferrybox['udp_ok'] = True
        except Exception as e:
            # print ('Error with udp', e)
            Ferrybox['udp_ok'] = False
        else:
            pass
    sock.close()


def send_data(s):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
    sock.sendto(bytes(s, encoding='utf8'), (UDP_IP, UDP_SEND))
    sock.close()
    return 
    

def udp_sender():
    global UDP_EXIT
    #  global Data_String

    interfaces = socket.getaddrinfo(host=socket.gethostname(), port=None,family=socket.AF_INET)
    allips = [ip[-1][0] for ip in interfaces]

    logging.debug('UDP sender started')
    n = 0
    while not UDP_EXIT:
        for ip in allips:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((ip, 0))
            s = Data_String # 'hello {:-d}'.format(n)
            # logging.info(f'send to {ip}, {UDP_SEND}, {s}')
            time.sleep(1)
            sock.sendto(bytes(s, encoding='utf8'), ('255.255.255.255', UDP_SEND))
            sock.close()


        #s = 'hello {:-d}'.format(n)
        #print(f'send to {UDP_SEND}')
        #sock.sendto(bytes(s, encoding='utf8'), ('255.255.255.255', UDP_SEND))
        time.sleep(5)
        n = n+1


receiver = threading.Thread(target=udp_receiver)
receiver.start()

sender = threading.Thread(target=udp_sender)
sender.start()


'''while True:
    try:
        s = input()
        if len(s) > 0:
            break
    except:
        break
    time.sleep(1)
    
UDP_EXIT = True'''


    
