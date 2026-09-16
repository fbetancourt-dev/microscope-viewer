# 📖 Technical Companion: WCH CH341DS1 (USB to Serial UART Mode)

* **Companion PDF**: [CH341DS1_Datasheet_UART_Printer.pdf](CH341DS1_Datasheet_UART_Printer.pdf) (12 pages, 208 KB)
* **Manufacturer**: Nanjing Qinheng Microelectronics (WCH)
* **Topic**: USB to Asynchronous Serial (UART) & Parallel Printer Interface Specifications

---

## 🎯 Why This Document is Critical to the Project

1. **Dual-Use Hardware (Serial Console Access)**: The CH341A programmer is not just an SPI flash flasher; by moving its jumper from pins 1-2 to pins 2-3, it instantly reconfigures into a high-speed **USB-to-TTL Serial UART Adapter**.
2. **Connecting to Microscope UART Test Pads**: On the internal microscope PCB, the Generalplus SoC outputs bootloader messages and interactive RTOS logs on dedicated serial test pads (`TX`, `RX`, `GND`) at 115200 baud. This datasheet provides the pinout and timing specifications needed to connect the programmer directly to those serial test pads without purchasing a separate FTDI or CP2102 dongle.
3. **Baud Rate Support**: Details the internal baud rate generator, confirming precision timing for standard embedded speeds (115200, 57600, 38400, 9600 bps) with error < 0.3%.

---

## 🔑 Key Technical Takeaways from the Datasheet

### 1. Serial Mode Hardware Configuration
* The CH341 determines its operating mode at power-up based on the state of pin `SCL` and `SDA`:
  - When `SCL` and `SDA` are left floating (or configured via the yellow mode jumper), the chip identifies as **USB to UART Serial device** (Linux driver: `ch341`).
  - It creates a standard Linux tty device: `/dev/ttyUSB*`.

### 2. Header Pinout in UART Mode:
When the jumper is moved to the **Serial (TTL)** position:
```text
           CH341A Front Pin Header (UART Mode)
                     +-----------+
              Pin 1  |    5V     | (Do NOT connect to 3.3V SoC pads!)
              Pin 2  |   VCC_3V3 | (3.3V output reference)
              Pin 3  |    TXD    | ---> Connect to Microscope RX test pad
              Pin 4  |    RXD    | <--- Connect to Microscope TX test pad
              Pin 5  |    GND    | <--- Connect to Microscope GND
                     +-----------+
```

### 3. Electrical Characteristics for Serial Lines:
* **Input High Level ($V_{IH}$)**: Minimum `2.0V` (compatible with 3.3V SoC logic).
* **Input Low Level ($V_{IL}$)**: Maximum `0.8V`.
* **Output Voltage ($V_{OH}$)**: Matches VCC supply rail (ensure 3.3V is used to protect SoC GPIOs).

---

## 🛠️ Practical Application for this Project

### Capturing Microscope Boot Logs via Terminal:
1. Move the CH341A yellow jumper to the **UART / Serial** position.
2. Solder thin wires from `GND`, `TXD`, and `RXD` to the test pads on the microscope PCB.
3. Plug the CH341A into your PC and launch `picocom`:
   ```bash
   picocom -b 115200 /dev/ttyUSB0
   ```
4. Power on the microscope; you will observe the Generalplus Stage-0/Stage-1 boot logs, RAM initialization, and sensor probe messages streaming in real time.
