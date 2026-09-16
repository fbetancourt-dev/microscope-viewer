# 📁 Hardware Datasheets & Schematics Archive

This directory contains the official technical PDF documents, schematics, and companion Markdown analytical guides for all silicon components, programmer hardware, and serial protocols utilized in the **MS5 / MS5B Digital Microscope** reverse engineering project.

---

## 📑 PDF Archive & Companion Technical Guides

Every official PDF is paired with a dedicated Markdown guide explaining its critical sections and practical application to this microscope project:

| PDF Document | Companion Guide | Format / Pages | Practical Project Relevance |
| :--- | :--- | :---: | :--- |
| [**Winbond_W25Q16JV_Datasheet.pdf**](Winbond_W25Q16JV_Datasheet.pdf) | [**Winbond_W25Q16JV_Datasheet.md**](Winbond_W25Q16JV_Datasheet.md) | PDF (2.8 MB) / 74p | Complete command set (0x9F JEDEC, 0x03 Read, 0x20 Erase) for the microscope's onboard 2MB firmware chip. |
| [**CH341A_Mini_Programmer_Schematic.pdf**](CH341A_Mini_Programmer_Schematic.pdf) | [**CH341A_Mini_Programmer_Schematic.md**](CH341A_Mini_Programmer_Schematic.md) | PDF (643 KB) / 8p | Circuit schematic and step-by-step instructions for the **essential 3.3V logic modification** to avoid frying 3.3V chips. |
| [**CH341DS1_Datasheet_UART_Printer.pdf**](CH341DS1_Datasheet_UART_Printer.pdf) | [**CH341DS1_Datasheet_UART_Printer.md**](CH341DS1_Datasheet_UART_Printer.md) | PDF (208 KB) / 12p | Reconfiguring the programmer into a USB-TTL bridge to read microscope boot logs on internal UART pads (115200 8N1). |
| [**CH341DS2_Datasheet_SPI_I2C.pdf**](CH341DS2_Datasheet_SPI_I2C.pdf) | [**CH341DS2_Datasheet_SPI_I2C.md**](CH341DS2_Datasheet_SPI_I2C.md) | PDF (183 KB) / 11p | Specifications of the synchronous serial SPI master engine used by `flashrom -p ch341a_spi` for full chip dumping. |
| [**CH341_English_Manual.pdf**](CH341_English_Manual.pdf) | [**CH341_English_Manual.md**](CH341_English_Manual.md) | PDF (204 KB) / 35p | Comprehensive USB vendor request codes, register manual, and instructions for resolving Linux kernel driver contention. |

---

## 🔬 Silicon & Hardware Overview References

* [**WINBOND_W25QXX_SPI_FLASH.md**](WINBOND_W25QXX_SPI_FLASH.md): Quick reference for SOIC-8 pinouts, electrical specifications, and JEDEC verification table across W25Q16 and W25Q32.
* [**CH341A_PROGRAMMER_PINOUT.md**](CH341A_PROGRAMMER_PINOUT.md): Hardware wiring matrix between the CH341A 16-pin ZIF socket, SOIC-8 Pomona test clip, and the flash chip.
* [**GENERALPLUS_SOC_REFERENCE.md**](GENERALPLUS_SOC_REFERENCE.md): Architecture block diagram of the Generalplus multimedia processor, boot stages, and USB Mask ROM ISP recovery mode.
