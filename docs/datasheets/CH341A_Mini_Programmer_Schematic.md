# 📖 Technical Companion: CH341A Mini Programmer Schematic & Circuit Analysis

* **Companion PDF**: [CH341A_Mini_Programmer_Schematic.pdf](CH341A_Mini_Programmer_Schematic.pdf) (8 pages, 643 KB)
* **Author / Reference**: One Transistor / Hardware Analysis Archive
* **Topic**: Circuit Schematic, Board Layout, and Voltage Rail Analysis of the CH341A Mini Programmer

---

## 🎯 Why This Document is Critical to the Project

1. **Root Cause of the 5V Danger**: Generic black-PCB CH341A programmers are notorious for exposing 3.3V chips to destructive 5.0V signal levels. This schematic reveals the exact PCB routing error: while the power jumper switches the ZIF VCC pin, the CH341A chip's main supply pin (Pin 28) remains permanently wired to the 5V USB rail, causing its internal I/O drivers to output 5V logic pulses on `MOSI`, `CLK`, and `/CS`.
2. **Safe Hardware Modification Blueprint**: The schematic provides the exact circuit reference needed to perform the "3.3V mod" (cutting the 5V trace to Pin 28 and jumping it to the 3.3V LDO output) before connecting a test clip to the microscope's flash chip.
3. **ZIF Socket Pin Mapping**: Details which pins of the 16-pin lever socket route to SPI versus I2C EEPROM channels.

---

## 🔑 Key Technical Takeaways from the Schematic

### 1. Power Supply Architecture & The 5V Design Flaw
* **USB 5V In**: Comes directly from the USB connector VBUS pin (5.0V).
* **LDO Regulator**: An onboard AMS1117-3.3 steps down 5V to 3.3V for low-voltage target chips.
* **The PCB Routing Flaw**:
  ```text
  USB VBUS (5V) ------------> Pin 28 (VCC) of CH341A IC  <-- FORCES 5V I/O LOGIC!
                            |
                            v
                      [AMS1117-3.3] 
                            |
                            v
                        3.3V Rail ---> Jumper Selector ---> Pin 8 (VCC) of Flash Socket
  ```
  Even when the jumper is set to 3.3V, Pin 28 is still connected to 5V, meaning the data lines (`MOSI`, `CLK`, `/CS`) output 5.0V high-level logic signals!

### 2. Performing the Safe 3.3V Modification:
1. Desolder or lift **Pin 28 (VCC)** of the CH341A IC from the PCB pad.
2. Solder a thin insulated wire from lifted Pin 28 to the **3.3V output pin (middle tab/pin 2) of the AMS1117-3.3 regulator**.
3. Verify with a multimeter: with the programmer connected to USB, probe between GND and Pin 28; it must read `3.3V ± 0.05V`.

### 3. ZIF Socket Internal Wiring to CH341A Pins:
| Signal Name | CH341A IC Pin | ZIF Socket Position | Direction |
| :--- | :---: | :---: | :--- |
| **CS0** | Pin 23 (`ACT#`) | 25xx Pin 1 | Output (Programmer -> Flash) |
| **MISO / DIN** | Pin 22 (`SDI`) | 25xx Pin 2 | Input (Flash -> Programmer) |
| **GND** | Pin 19 (`GND`) | 25xx Pin 4 | Ground Reference |
| **MOSI / DOUT**| Pin 20 (`SDO`) | 25xx Pin 5 | Output (Programmer -> Flash) |
| **CLK / SCK** | Pin 21 (`SCK`) | 25xx Pin 6 | Output (Clock) |
| **VCC** | Regulator / Jumper | 25xx Pin 8 | Power (3.3V) |

---

## 🛠️ Practical Application for this Project
Before connecting the SOIC-8 Pomona test clip to the microscope's W25Q16JV Flash chip, use page 2 and page 5 of this PDF to verify your programmer's PCB traces and ensure data line voltages will not exceed 3.6V.
