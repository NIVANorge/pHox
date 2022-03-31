import socket
import select
import time
import threading
import os 
import argparse
import datetime 

# DataString is the string to be sent by the server to all connected clients
DataString_from_box = 'String to send'

# DataDict is the dictionary to update after a data string has been received from a remote server
# Must be defined and populated in the client
#DataDict = {}

# Default status.to receive 
Ferrybox = {
    "salinity": 33.5,
    "temperature": 25.0,
    "longitude": 0.0,
    "latitude": 0.0,
    "pumping": None,
    'tcp_ok': False
}

# Local server is the combined (host,port) were the local server should run and wait for clients for sending data
# Remote server is similar, but defines the remote server we want to connect to as client and get data from
#LOCAL_SERVER = ('myip', 56801)
#REMOTE_SERVER = ('herip', 56801)
MAX_CLIENTS = 10


# File for exiting smoothly in case we have to...
EXIT_FILE = 'status.tcp'

if os.path.exists(EXIT_FILE):
    os.unlink(EXIT_FILE)


def stay_alive():
    """
    This is a rescue for shutting down the server and all clients in a smooth way
    """
    try:
        fd = open('status.tcp', 'rb')
        status = b"".join(fd.readlines()).strip().lower()
        fd.close()
        return status != 'exit'
    except:
        pass
    return False

def stop_everything():
    try:
        fd = open('status.tcp', 'w')
        fd.writelines('exit')
    except: 
        pass
    return False     

class ClientHandler(threading.Thread):
    """
    This class help handles multiple clients connected to the server
    It will send at specific intervals the content of variable DataString (see overriden method run())
    """
    def __init__(self, client, addr):
        super().__init__()
        self.client = client
        self.address = addr
        return

    def run(self):
        done = stay_alive()
        while not done:
            try:
                # send message every 1 second 
                # here DataString is the message for pH box
                self.client.sendall(DataString_from_box.encode())
                time.sleep(1)
            except:
                pass
            done = stay_alive()
        return

class TCPServer(object):
    """
    The server itself will just wait for clients to connect and spawn threads to handle them.
    in this code the server is pH box??
    """
    def __init__(self, host, port):
        self.host = host
        self.port = port
        print (host,port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        return

    def listen(self):
        self.sock.listen(5)
        done = stay_alive()
        while not done:
            try:
                rlst, wlst, elst = select.select([self.sock], [], [], 1)
                if self.sock in rlst:
                    client, address = self.sock.accept()
                    print("New connection from {:s}:{:-d}".format(address[0], address[1]))
                    t = ClientHandler(client, address)
                    t.start()
            except:
                pass
            done = stay_alive()
        self.sock.close()
        return

def start_server(host, port):
    try:
        server = TCPServer(host, port)
        server.listen()
    except Exception as e:
        print (e)
        print ('Unable to start TCP server on the BOX')

    return

def data_to_ferrybox_dict(data):
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
    return Ferrybox 

def start_client(host, port):
    # client to get data from FB computer 
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # host is an IP of Ferrybox computer, port is a port 56801
    try: 
        client.connect((host, port))
        print("connected to {:s} on port {:-d}".format(host, port))
        done = stay_alive()
        while not done:
            try:
                data = client.recv(1024)

                print(data) # should populate DataDict here
                Ferrybox = data_to_ferrybox_dict(data) # trasformed # decode into dictionary
            except:
                pass
            done = stay_alive()
        print("client is closing ", done)
        client.close()
        return
    except: 
        print('NO Connection to the FB PC')


if __name__ == "__main__":
    """
    For testing...
    """

    

    p = argparse.ArgumentParser()
    p.add_argument("command")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=56801)
    p.add_argument("--interval", type=int, default=5)
    args = p.parse_args()

    if args.command == "server":
        start_server(args.host, args.port)
    elif args.command == "client":
        start_client(args.host, args.port)