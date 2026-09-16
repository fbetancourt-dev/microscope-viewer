# 📖 Technical Companion: WCH CH341DS2 (Synchronous Serial SPI & I2C Mode)

* **Companion PDF**: [CH341DS2_Datasheet_SPI_I2C.pdf](CH341DS2_Datasheet_SPI_I2C.pdf) (11 pages, 183 KB)
* **Manufacturer**: Nanjing Qinheng Microelectronics (WCH)
* **Topic**: Synchronous Serial Interface (SPI Master & I2C Master) Specifications

---

## 🎯 Why This Document is Critical to the Project

1. **The Engine Behind `flashrom -p ch341a_spi`**: When dumping or reflashing the microscope's Winbond SPI Flash memory, the CH341 operates exclusively in the synchronous serial mode described in this document.
2. **SPI Master Timing & Clock Phasing**: Details the SPI clock parameters (SPI Mode 0: clock idles low, data shifts in on rising edge, shifts out on falling edge), which match the exact requirements of the W25Q16JV / W25Q32JV Flash chips.
3. **Multi-Chip Select Support**: Explains how the chip can drive multiple chip-select lines (`CS0`, `CS1`, `CS2`), ensuring you understand which pin must be hooked up to the flash chip's `/CS` pin 1.

---

## 🔑 Key Technical Takeaways from the Datasheet

### 1. Synchronous Serial Hardware Signals:
In SPI Mode, the CH341 multiplexes its pins into dedicated SPI Master lines:

| Signal | CH341 Pin | Pin Type | Function | Connected to Flash Pin |
| :--- | :---: | :---: | :--- | :---: |
| **`SCK`** | Pin 21 | Output | SPI Serial Clock (up to ~2 MHz) | Pin 6 (`CLK`) |
| **`SDO` / `MOSI`** | Pin 20 | Output | Serial Data Output (Host to Flash) | Pin 5 (`MOSI` / `DI`) |
| **`SDI` / `MISO`** | Pin 22 | Input | Serial Data Input (Flash to Host) | Pin 2 (`MISO` / `DO`) |
| **`CS0`** | Pin 23 | Output | Chip Select 0 (Active Low) | Pin 1 (`/CS`) |
| **`GND`** | Pin 19 | Power | Ground Reference | Pin 4 (`GND`) |

### 2. Clock Speeds and Read Performance:
* The CH341 hardware SPI engine transfers data at approx **1.5 MHz to 2.0 MHz**.
* Dumping a 2MB (16M-bit) flash image via `flashrom` takes approximately:
  $$\text{Time} \approx \frac{2 \times 10^6 \times 8 \text{ bits}}{1.5 \times 10^6 \text{ bps}} \approx 10.6 \text{ seconds}$$
* This provides a predictable, reliable baseline for diagnosing whether a dump is hanging or proceeding normally.

### 3. Bit-Order and Transfer Protocol:
* Transmits **MSB First** (Most Significant Bit first), complying with the standard Serial Flash specification.
* Supports arbitrary length continuous byte-stream reads, essential for whole-chip firmware imaging (`0x03 Read Data` command).

---

## 🛠️ Practical Application for this Project

### Flashrom SPI Programmer Configuration:
When executing `flashrom`, it directly interfaces with the CH341's USB bulk endpoints configured according to this datasheet:
```bash
# Probe SPI flash status and identify JEDEC ID:
flashrom -p ch341a_spi

# Write modified firmware image with erase-block optimization:
flashrom -p ch341a_spi -c "W25Q16.V" -w modified_firmware.bin
```
