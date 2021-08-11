
from datetime import datetime
import socket
import threading
import os
import logging
logging.getLogger()

UDP_SEND = 56801   # was 6801
UDP_RECV = 56802   # was 6802
UDP_IP = "192.168.0.1"  # Should be the IP of the Ferrybox
UDP_EXIT = False

SHIP_IP_DICT = {'TF': "192.168.0.1",
                "RA": "192.168.0.1",
                "KH": "192.168.13.3"}


Ferrybox = {
    "salinity": 33.5,
    "temperature": 25.0,
    "longitude": 0.0,
    "latitude": 0.0,
    "pumping": None,
    'udp_ok': False
}


def udp_server():
    logging.debug('in udp server')
    global Ferrybox
    global UDP_EXIT
    sock_listen = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_listen.settimeout(1)


    try:
        sock_listen.bind(("", UDP_RECV))
    except Exception as e:
        print ('Could not start the UDP listener')
        print (e)
        logging.info('Could not start the UDP listener'
                     'kill the process: '
                     'sudo netstat -tulpn'
                     'sudo kill <PID>')
    logging.info("UDP server started")

    while not UDP_EXIT:
        try:
            Ferrybox['udp_ok'] = False
            (data, addr) = sock_listen.recvfrom(500)
            print (data,addr)
        except:
            # add time
            pass
        else:
            Ferrybox['udp_ok'] = True
            data = data.decode('utf-8')

            w = data.split(",")
            if data.startswith("$PFBOX,TIME,"):
                try:
                    v = datetime.strptime(w[2], "%Y-%m-%dT%H:%M:%S")
                except Exception as e:
                    print (e)
                    print ('UNable to get time in the format w[2]')
                t = datetime.now()
                if abs(t - v).total_seconds() > 5:
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
    sock_listen.close()


def send_data(s, ship_code=None):
    logging.debug('send udp data')
    #print("send UDP: " + s)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # my_dict.get(key, default_value) if key is missing 'default_value' is used
    sock.sendto(bytes(s, encoding="utf8"), (SHIP_IP_DICT.get(ship_code, UDP_IP), UDP_SEND))
    sock.close()
    return


server = threading.Thread(target=udp_server)
server.start()
