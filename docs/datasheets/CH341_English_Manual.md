# 📖 Technical Companion: WCH CH341 English Technical & Register Manual

* **Companion PDF**: [CH341_English_Manual.pdf](CH341_English_Manual.pdf) (35 pages, 204 KB)
* **Manufacturer**: Nanjing Qinheng Microelectronics (WCH)
* **Topic**: Comprehensive Chip Architecture, USB Control Protocol, Registers & API Reference

---

## 🎯 Why This Document is Critical to the Project

1. **Low-Level Protocol Decoupling**: While simple tools interact through generic drivers, writing custom Python scripts (using `pyusb` or `libusb`) to automate microscope testing, flash dumping, or I/O manipulation requires knowledge of the CH341's USB Vendor-Specific Control Requests. This manual documents those exact USB request codes.
2. **Troubleshooting Kernel Conflicts**: In Linux, the kernel automatically attaches the `ch341.ko` serial driver when the device is plugged in. This manual explains why tools like `flashrom` must detach the kernel driver (`libusb_detach_kernel_driver`) to access raw SPI/I2C endpoints.
3. **Register Mapping & Diagnostic Status**: Explains internal status register bits (e.g. buffer full, bus busy, parity error) useful for diagnosing loose test clips or poor ground contacts.

---

## 🔑 Key Technical Takeaways from the Manual

### 1. USB Interface Architecture
* **Vendor ID (VID)**: `0x1A86` (Nanjing Qinheng Microelectronics)
* **Product ID (PID)**: `0x5512` (CH341 in Synchronous Serial / Parallel Mode) or `0x7523` (CH341 in Standard Serial Mode).
* **Endpoints**:
  - `Endpoint 0`: Control Endpoint (handles setup packets and vendor commands).
  - `Endpoint 1 / 2`: Bulk IN & Bulk OUT endpoints (used for high-speed SPI/UART data streaming).

### 2. USB Vendor Control Requests (Low-Level Protocol):
When custom software drives the SPI bus over USB:
* `bRequest = 0xBF` (`CMD_UIO_STREAM`): Controls user I/O pins and executes bit-bang operations.
* `bRequest = 0xA1` (`CMD_SPI_STREAM`): Streams high-speed SPI data directly into the chip's internal FIFO.
* `bRequest = 0xA4` (`CMD_I2C_STREAM`): Controls synchronous 2-wire serial clocking.

### 3. Resolving Linux Driver Contention:
```mermaid
graph TD
    A[CH341A Plugged into Linux USB] --> B{Default Kernel Action}
    B -->|Binds to ch341.ko| C[/dev/ttyUSB0 Serial Node Created]
    C -->|Blocks SPI Mode!| D[Flashrom Error: Could not claim USB interface]

    E[Flashrom / libusb Command] -->|Issues libusb_detach_kernel_driver| F[Kernel Driver Detached]
    F -->|Claims Interface 0| G[Raw Bulk Endpoints Activated for SPI Flash Dump]
```

---

## 🛠️ Practical Application for this Project

### Writing Custom Python SPI Tool with PyUSB:
If you build a lightweight standalone Python script to read the microscope's JEDEC ID without installing `flashrom`:
```python
import usb.core
import usb.util

# 1. Locate CH341 device
dev = usb.core.find(idVendor=0x1a86, idProduct=0x5512)
if dev is None:
    raise ValueError("CH341A programmer not detected!")

# 2. Detach kernel driver if active
if dev.is_kernel_driver_active(0):
    dev.detach_kernel_driver(0)

# 3. Claim interface
dev.set_configuration()
usb.util.claim_interface(dev, 0)
print("CH341A connected in raw SPI mode!")
```
