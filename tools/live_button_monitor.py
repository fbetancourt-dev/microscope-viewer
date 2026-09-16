#!/usr/bin/env python3
import socket
import time
import sys

HOST = "192.168.29.1"
CMD_PORT = 20000
DATA_PORT = 10900

cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
cmd_sock.bind(("0.0.0.0", CMD_PORT))
cmd_sock.setblocking(False)

data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
data_sock.bind(("0.0.0.0", DATA_PORT))
data_sock.setblocking(False)

print(f"[{time.strftime('%H:%M:%S')}] Connecting to JoyHonest stream at {HOST}...")
cmd_sock.sendto(b"JHCMD\x10\x00", (HOST, CMD_PORT))
cmd_sock.sendto(b"JHCMD\x20\x00", (HOST, CMD_PORT))
cmd_sock.sendto(b"JHCMD\xd0\x01", (HOST, CMD_PORT))
cmd_sock.sendto(b"JHCMD\xd0\x01", (HOST, CMD_PORT))

last_hb = time.time()
last_header_bytes = None
header_changes = 0
port_20000_count = 0

print("Stream initialized. Listening for 10 seconds...")
print("==================================================")
sys.stdout.flush()

t_end = time.time() + 10.0

try:
    while time.time() < t_end:
        now = time.time()
        if now - last_hb >= 1.0:
            cmd_sock.sendto(b"JHCMD\xd0\x01", (HOST, CMD_PORT))
            last_hb = now

        # Check port 20000
        try:
            while True:
                sdata, saddr = cmd_sock.recvfrom(512)
                port_20000_count += 1
                print(f"[PORT 20000] #{port_20000_count} Len={len(sdata)} from {saddr}: {sdata.hex()} ({repr(sdata)})", flush=True)
        except (BlockingIOError, TimeoutError):
            pass

        # Check port 10900 header bytes
        try:
            while True:
                pdata, _ = data_sock.recvfrom(2048)
                if len(pdata) >= 8:
                    hdr = pdata[:8]
                    pkt_idx = hdr[3]
                    stat_bytes = bytes([hdr[0], hdr[1], hdr[2], hdr[4], hdr[5], hdr[6], hdr[7]])
                    if pkt_idx == 0:
                        if last_header_bytes is not None and stat_bytes != last_header_bytes:
                            header_changes += 1
                            print(f"[VIDEO HDR CHANGE #{header_changes}] Old={last_header_bytes.hex()} New={stat_bytes.hex()} (Full={hdr.hex()})", flush=True)
                        last_header_bytes = stat_bytes
        except (BlockingIOError, TimeoutError):
            pass

        time.sleep(0.005)

finally:
    cmd_sock.sendto(b"JHCMD\xd0\x02", (HOST, CMD_PORT))
    cmd_sock.close()
    data_sock.close()

print("==================================================")
print(f"Monitoring finished. Port 20000 packets: {port_20000_count}, Header changes: {header_changes}")
