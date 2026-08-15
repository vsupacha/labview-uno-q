# 😀 UNO Q toolkit

This UNO Q app implements a **gateway between LabVIEW and the STM32U585 peripherals**. Instead of using the Serial/TCP Remote I/O protocol of the original LabVIEW Hobbyist Toolkit, LabVIEW accesses the UNO Q through a **REST API with JSON messages**. The app runs on the Debian side, translates each REST request into an UNO Q RPC call, and invokes the corresponding peripheral function exposed by the STM32U585 firmware through `Bridge.provide()`.

The initial revision focuses on compatibility with the core peripheral operations of the LabVIEW Hobbyist Toolkit:

| LabVIEW I/O  | REST API            | STM32 RPC      |
| ------------ | ------------------- | -------------- |
| Digital I/O  | `/api/v1/digital/*` | `lv.digital.*` |
| Analog Input | `/api/v1/analog/*`  | `lv.analog.*`  |
| PWM          | `/api/v1/pwm/*`     | `lv.pwm.*`     |
| I2C          | `/api/v1/i2c/*`     | `lv.i2c.*`     |
| SPI          | `/api/v1/spi/*`     | `lv.spi.*`     |
| UART         | `/api/v1/uart/*`    | `lv.uart.*`    |

The architecture separates the external LabVIEW interface from the internal UNO Q communication mechanism:

`LabVIEW VI → REST/JSON → Debian Gateway → RPC → STM32U585 → Peripheral`

This allows the LabVIEW VIs to retain the familiar Hobbyist Toolkit programming model while using the native heterogeneous architecture of the UNO Q.
