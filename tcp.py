import socket
import select
import time
import threading
import os 
import argparse

# DataString is the string to be sent by the server to all connected clients
DataString = 'String to send'


# Default status.
Ferrybox = {
    "salinity": 33.5,
    "temperature": 25.0,
    "longitude": 0.0,
    "latitude": 0.0,
    "pumping": None,
    'udp_ok': False
}




# DataDict is the dictionary to update after a data string has been received from a remote server
# Must be defined and populated in the client
DataDict = {}

# Local server is the combined (host,port) were the local server should run and wait for clients for sending data
# Remote server is similar, but defines the remote server we want to connect to as client and get data from
LOCAL_SERVER = ('myip', 56801)
REMOTE_SERVER = ('herip', 56801)
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
                self.client.sendall(DataString.encode())
                time.sleep(1)
            except:
                pass
            done = stay_alive()
        return

class TCPServer(object):
    """
    The server itself will just wait for clients to connect and spawn threads to handle them.
    """
    def __init__(self, host, port):
        self.host = host
        self.port = port
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
    server = TCPServer(host, port)
    server.listen()
    return


def start_client(host, port):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((host, port))
    print("connected to {:s} on port {:-d}".format(host, port))
    done = stay_alive()
    while not done:
        try:
            data = client.recv(1024)
            print(data) # should populate DataDict here
        except:
            pass
        done = stay_alive()
    print("client is closing ", done)
    client.close()
    return


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