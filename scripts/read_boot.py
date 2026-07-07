"""Читает boot-log ESP32 через pyserial. Сброс через EN (DTR/RTS)."""
from __future__ import annotations
import sys, time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM14"
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0

def reset(s: serial.Serial) -> None:
    s.setDTR(False); s.setRTS(True); time.sleep(0.1)
    s.setDTR(False); s.setRTS(False); time.sleep(0.05)

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with serial.Serial(PORT, BAUD, timeout=0.1) as s:
        reset(s)
        t0 = time.time()
        buf = b""
        while time.time() - t0 < SECS:
            b = s.read(4096)
            if b:
                buf += b
                try:
                    sys.stdout.write(b.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
                except Exception:
                    pass
        print(f"\n=== получено байт: {len(buf)} ===")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
