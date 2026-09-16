# 📖 Technical Companion: Winbond W25Q16JV SPI NOR Flash

* **Companion PDF**: [Winbond_W25Q16JV_Datasheet.pdf](Winbond_W25Q16JV_Datasheet.pdf) (74 pages, 2.8 MB)
* **Manufacturer**: Winbond Electronics Corporation
* **Device**: W25Q16JV (16M-bit / 2M-byte 3V Serial Flash Memory with Dual/Quad SPI)

---

## 🎯 Why This Document is Critical to the Project

1. **Firmware Residence**: In the MS5 / MS5B microscope, the entire embedded RTOS (uC/OS-II or FreeRTOS), WiFi network stack, camera calibration matrices, and Generalplus stage-1 bootloader are stored inside this specific SPI NOR Flash IC.
2. **Flash Dump Integrity**: When reading or modifying the microscope firmware with `flashrom` or hardware programmers, you must understand the chip's internal structure (e.g. 4KB sector alignment, 256-byte page programming boundaries) to prevent corrupted writes.
3. **Silicon Protection**: The datasheet details the absolute maximum ratings. Powering the chip with 5.0V from an unmodified programmer will permanently damage the silicon.

---

## 🔑 Key Technical Takeaways from the Datasheet

### 1. Electrical & Voltage Limits
* **Operating Voltage ($V_{CC}$)**: `2.7V` to `3.6V` (Nominal: `3.3V`).
* **Absolute Maximum Voltage**: `4.6V` (Exceeding 4.6V causes gate oxide breakdown).
* **Power-Down Current**: `< 1 µA` typical (important for the microscope's internal 3.7V battery life).

### 2. Physical Pinout (SOIC-8 150-mil / 208-mil)
```text
               Winbond SOIC-8 Pinout (Top View)
                           +---v---+
       (Chip Select)  /CS -| 1   8 |- VCC (3.3V DC)
       (Data Out)    MISO -| 2   7 |- /HOLD (Pause bus)
       (Write Protect)/WP -| 3   6 |- CLK (SPI Clock)
       (Ground)       GND -| 4   5 |- MOSI (Data In)
                           +-------+
```

### 3. Memory Architecture
* **Total Capacity**: 16,777,216 bits (2,097,152 bytes / 2 MB).
* **Pages**: 8,192 programmable pages of 256 bytes each.
* **Sectors**: 512 uniform erasable sectors of 4,096 bytes (4 KB) each.
* **Blocks**: 32 uniform erasable blocks of 64 KB (or 64 blocks of 32 KB).

### 4. Essential SPI Opcodes (Command Set)
| Opcode | Command Name | Function in Reverse Engineering |
| :---: | :--- | :--- |
| `0x9F` | **JEDEC ID Read** | Returns `EF 40 15`. Verifies proper SOIC-8 test clip connection before dumping. |
| `0x03` | **Read Data** | Standard linear memory dump (up to 50 MHz). |
| `0x0B` | **Fast Read** | High-speed read with 1 dummy byte (up to 133 MHz). |
| `0x06` | **Write Enable** | Must be executed before every page program or sector erase. |
| `0x20` | **Sector Erase (4KB)**| Erases individual 4KB sector to `0xFF` prior to reprogramming. |
| `0x02` | **Page Program** | Writes up to 256 bytes into a previously erased page. |
| `0x05` | **Read Status Reg-1**| Polls the `BUSY` bit (Bit 0) to detect when an internal erase/program cycle completes. |

---

## 🛠️ Practical Application for Firmware Dumping
When using `flashrom`:
```bash
# Verify chip presence via JEDEC ID (0x9F) and dump 2MB image:
flashrom -p ch341a_spi -c "W25Q16.V" -r microscope_factory_firmware.bin
```
