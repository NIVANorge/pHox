from datetime import datetime, timedelta
import socket
import threading
import os

UDP_SEND = 6801
UDP_RECV = 6802
UDP_IP   = '192.168.0.2'  # Should be the IP of the Ferrybox
UDP_EXIT = False

Ferrybox = {
    'salinity'   : 33.5,
    'temperature': 15.0,
    'longitude'  : 0.0,
    'latitude'   : 0.0,
    'pumping'    : 1
    }

def udp_server():
    global Ferrybox
    global UDP_EXIT
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    sock.bind(('', UDP_RECV))
    print ('UDP server started')
    while not UDP_EXIT:
        try:
            (data,addr) = sock.recvfrom(500)
        except:
            pass
        else:
            print ('received: %s' % (data.strip()))
            w = data.split(',')
            if data.startswith('$PFBOX,TIME,'):
                v = datetime.strptime(w[2], '%Y-%m-%dT%H:%M:%S')
                t = datetime.now()
                if abs(t-v).total_seconds() > 5:
                    print ('will correct time')
                    os.system("date +'%Y-%m-%dT%H:%M:%S' --set={:s}".format(w[2]))
            elif data.startswith('$PFBOX,SAL,'):
                v = float(w[2])
                Ferrybo['salinity'] = v
            elif data.startswith('$PFBOX,PUMP,'):
                v = int(w[2])
                Ferrybox['pumping'] = v
            elif data.startswith('$PFBOX,TEMP,'):
                v = float(w[2])
                Ferrybox['temperature'] = v
            elif data.startswith('$PFBOX,LAT,'):
                v = float(w[2])
                Ferrybox['latitude'] = v
            elif data.startswith('$PFBOX,LON,'):
                v = float(w[2])
                Ferrybox['longitude'] = v
    sock.close()


def send_data(s):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
    sock.sendto(s, (UDP_IP, UDP_SEND))
    sock.close()
    return 
    
server = threading.Thread(target=udp_server)
server.start()
