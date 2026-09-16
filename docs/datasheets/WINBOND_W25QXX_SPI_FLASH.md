# 📄 Datasheet Summary: Winbond W25Q16JV / W25Q32JV SPI NOR Flash

This datasheet summary covers the standard 16M-bit (2MB) and 32M-bit (4MB) Serial NOR Flash memory chips commonly populated on the **MS5 / MS5B Digital Microscope** mainboard.

---

## ⚡ Key Electrical Characteristics

* **Power Supply Voltage ($V_{CC}$)**: 2.7V to 3.6V (Nominal: **3.3V DC**).
* **Operating Current**: 1mA active read, 15µA standby, 1µA deep power-down.
* **Clock Frequency ($f_C$)**: Up to 133 MHz Standard SPI, Dual/Quad SPI support.
* **Erase/Program Architecture**:
  - Uniform 4KB Sectors (4096 bytes per sector).
  - Uniform 32KB / 64KB Blocks.
  - 256-Byte Page Programming (0.4 ms typical page write time).
  - Sector Erase time: 45 ms typical.

---

## 📌 SOIC-8 (208-mil / 150-mil) Package Pinout

```text
                     SOIC-8 Top View (Pin 1 Dot at Top-Left)
                                +---v---+
            (Chip Select)  /CS -| 1   8 |- VCC (2.7V - 3.6V)
   (Data Output / MISO)   MISO -| 2   7 |- /HOLD or /RESET (IO3)
       (Write Protect)     /WP -| 3   6 |- CLK (Clock)
              (Ground)     GND -| 4   5 |- MOSI (Data Input / IO0)
                                +-------+
```

### Pin Descriptions:

| Pin No. | Pin Name | Signal Type | Description |
| :---: | :---: | :---: | :--- |
| **1** | `/CS` | Input | **Chip Select (Active Low)**: Driving low selects device; driving high deselects. |
| **2** | `DO` (`MISO`) | Output | **Serial Data Output**: Data shifts out on falling edge of CLK. |
| **3** | `/WP` | Input | **Write Protect (Active Low)**: Protects status register bits when low. |
| **4** | `GND` | Ground | **0V Reference Ground**. |
| **5** | `DI` (`MOSI`) | Input | **Serial Data Input**: Instructions, addresses, and data shift in on rising edge of CLK. |
| **6** | `CLK` | Input | **Serial Clock**: Synchronizes all bus operations (SPI Mode 0 or Mode 3). |
| **7** | `/HOLD` | Input | **Hold / Reset**: Pauses device operation without deselecting `/CS`. |
| **8** | `VCC` | Power | **Device Core & I/O Power Supply (3.3V)**. |

---

## ⚙️ Standard SPI Instruction Command Set

| Command Name | Byte 1 (Opcode) | Byte 2 | Byte 3 | Byte 4 | Byte 5..N | Function |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Write Enable** | `0x06` | - | - | - | - | Sets `WEL` bit in status register |
| **Write Disable** | `0x04` | - | - | - | - | Clears `WEL` bit |
| **Read Status Reg-1** | `0x05` | `(S7-S0)` | - | - | - | Polls `BUSY` bit (bit 0) |
| **Read Data** | `0x03` | `A23-A16` | `A15-A8` | `A7-A0` | `(D7-D0)...` | Continuous memory read at up to 50 MHz |
| **Fast Read** | `0x0B` | `A23-A16` | `A15-A8` | `A7-A0` | Dummy byte | High-speed read up to 133 MHz |
| **Page Program** | `0x02` | `A23-A16` | `A15-A8` | `A7-A0` | `D7-D0...` | Writes up to 256 bytes into a page |
| **Sector Erase (4KB)** | `0x20` | `A23-A16` | `A15-A8` | `A7-A0` | - | Erases 4KB sector to all `0xFF` |
| **Block Erase (64KB)** | `0xD8` | `A23-A16` | `A15-A8` | `A7-A0` | - | Erases 64KB block to all `0xFF` |
| **Chip Erase** | `0xC7` or `0x60` | - | - | - | - | Erases entire flash array |
| **Read JEDEC ID** | `0x9F` | `Mfg ID` | `Mem Type` | `Capacity` | - | Reads manufacturer (Winbond: `0xEF`) and device ID |

---

## 🆔 JEDEC ID Verification Reference

When running `flashrom` or custom SPI dump tools, query opcode `0x9F`:
* **Winbond W25Q16JV (2MB)**:
  - Manufacturer ID: `0xEF`
  - Memory Type: `0x40`
  - Capacity: `0x15` (16 Mbit)
* **Winbond W25Q32JV (4MB)**:
  - Manufacturer ID: `0xEF`
  - Memory Type: `0x40`
  - Capacity: `0x16` (32 Mbit)
* **GigaDevice GD25Q16 (2MB)**:
  - Manufacturer ID: `0xC8`
  - Memory Type: `0x40`
  - Capacity: `0x15`
