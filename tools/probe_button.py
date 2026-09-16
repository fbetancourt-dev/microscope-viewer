#!/usr/bin/env python3
import socket
import time
import sys

HOST = "192.168.29.1"
SPORT = 20000
RPORT = 10900

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 20000))
s.setblocking(False)

r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
r.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
r.bind(("0.0.0.0", RPORT))
r.setblocking(False)

print(f"[{time.strftime('%H:%M:%S')}] Initializing stream to {HOST}...")
s.sendto(b"JHCMD\x10\x00", (HOST, SPORT))
s.sendto(b"JHCMD\x20\x00", (HOST, SPORT))
s.sendto(b"JHCMD\xd0\x01", (HOST, SPORT))
s.sendto(b"JHCMD\xd0\x01", (HOST, SPORT))

print(f"[{time.strftime('%H:%M:%S')}] Stream active! Listening on port 20000 for 12 seconds...")
print(">>> PRESS THE PHOTO BUTTON ON THE MICROSCOPE NOW! <<<", flush=True)

last_hb = time.time()
t_end = time.time() + 12.0
packet_count = 0

try:
    while time.time() < t_end:
        now = time.time()
        if now - last_hb >= 1.0:
            s.sendto(b"JHCMD\xd0\x01", (HOST, SPORT))
            last_hb = now

        # Drain port 20000
        try:
            while True:
                data, addr = s.recvfrom(512)
                packet_count += 1
                hex_str = data.hex()
                text_repr = repr(data)
                print(f"\n[EVENT #{packet_count}] Time={time.strftime('%H:%M:%S')} Len={len(data)}")
                print(f"  Hex:  {hex_str}")
                print(f"  Repr: {text_repr}")
                if len(data) == 7 and data.startswith(b"JHCMD"):
                    cmd5 = data[5]
                    cmd6 = data[6]
                    print(f"  --> JHCMD 7-byte packet: cmd5=0x{cmd5:02x} ({cmd5}), cmd6=0x{cmd6:02x} ({cmd6})")
        except (BlockingIOError, TimeoutError):
            pass

        # Drain video socket
        try:
            while True:
                vdata, _ = r.recvfrom(2048)
        except (BlockingIOError, TimeoutError):
            pass

        time.sleep(0.005)
finally:
    s.sendto(b"JHCMD\xd0\x02", (HOST, SPORT))
    s.close()
    r.close()

print(f"\n[{time.strftime('%H:%M:%S')}] Probe finished. Total events captured on 20000: {packet_count}")
