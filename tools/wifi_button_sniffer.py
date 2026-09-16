#!/usr/bin/env python3
import socket
import time
import sys

HOST = "192.168.29.1"
SPORT = 20000
RPORT = 10900

print(f"[*] Binding UDP sockets on port {SPORT} (control) and {RPORT} (data)...")
cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
cmd_sock.bind(("0.0.0.0", SPORT))
cmd_sock.setblocking(False)

data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
data_sock.bind(("0.0.0.0", RPORT))
data_sock.setblocking(False)

# Initial handshake
cmd_sock.sendto(b"JHCMD\x10\x00", (HOST, SPORT))
cmd_sock.sendto(b"JHCMD\x20\x00", (HOST, SPORT))
cmd_sock.sendto(b"JHCMD\xd0\x01", (HOST, SPORT))
cmd_sock.sendto(b"JHCMD\xd0\x01", (HOST, SPORT))

print("\n=======================================================")
print(">>> ESCUCHANDO DURANTE 25 SEGUNDOS                    <<<")
print(">>> ¡PRESIONA VARIAS VECES EL BOTÓN FÍSICO DE FOTO!   <<<")
print("=======================================================\n", flush=True)

start = time.time()
last_hb = time.time()
frame_count = 0
base_identity = None

try:
    while time.time() - start < 25.0:
        now = time.time()
        # Keepalive every 500ms
        if now - last_hb >= 0.5:
            cmd_sock.sendto(b"JHCMD\xd0\x01", (HOST, SPORT))
            cmd_sock.sendto(b"JHCMD\x10\x00", (HOST, SPORT))
            last_hb = now

        # 1. Listen on control/status socket (port 20000)
        try:
            while True:
                sdata, saddr = cmd_sock.recvfrom(512)
                t_str = time.strftime('%H:%M:%S')
                if len(sdata) == 105 and sdata.startswith(b"JHCMD \x00"):
                    if base_identity is None:
                        base_identity = sdata
                        print(f"[{t_str}] [INIT-STATUS] Identity registered ({len(sdata)} bytes)")
                    elif sdata != base_identity:
                        # Find diff!
                        diffs = [f"byte[{i}]: {base_identity[i]:02x}->{sdata[i]:02x}" for i in range(len(sdata)) if sdata[i] != base_identity[i]]
                        print(f"[{t_str}] [STATUS-CHANGED] Diff in identity packet: {', '.join(diffs)}", flush=True)
                else:
                    print(f"[{t_str}] [CMD-PACKET] len={len(sdata)} hex={sdata.hex()} ascii={repr(sdata)}", flush=True)
        except (BlockingIOError, socket.error):
            pass

        # 2. Listen on video data socket (port 10900)
        try:
            while True:
                pdata, _ = data_sock.recvfrom(2048)
                if len(pdata) > 8:
                    pkt_idx = pdata[3]
                    # Check first packet of frame for any non-standard flags
                    if pkt_idx == 0:
                        frame_count += 1
                        # standard is often 01 00 08 00 31 14 00 00
                        flags = pdata[4:8]
                        if flags != b"\x31\x14\x00\x00" and flags != b"\x00\x00\x00\x00":
                            print(f"[{time.strftime('%H:%M:%S')}] [DATA-HEADER] Frame {frame_count} flag altered: {flags.hex()}", flush=True)
        except (BlockingIOError, socket.error):
            pass

        time.sleep(0.002)

finally:
    print(f"\n[*] Total frames recibidos: {frame_count}")
    cmd_sock.sendto(b"JHCMD\xd0\x02", (HOST, SPORT))
    cmd_sock.close()
    data_sock.close()
    print("[*] Sniffer terminado.")
