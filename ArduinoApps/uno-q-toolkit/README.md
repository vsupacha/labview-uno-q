# UNO Q LabVIEW gateway

This project exposes a small REST/JSON surface through the Arduino App Lab `WebUI` Brick and forwards hardware operations to the STM32U585 through `Arduino_RouterBridge`.

Revision 0.1 implements digital I/O and onboard RGB LED control. Analog, PWM, I2C, SPI, and UART RPCs are registered as explicit `-2` (not implemented) responses until their STM32 peripheral behavior is added.

The REST service is intentionally unauthenticated for local development. Before exposing it beyond a trusted LAN, add authentication and bind/firewall it appropriately.

## Layout

- `app.yaml` — Arduino App Lab app descriptor
- `python/main.py` — App Lab Linux-side entry point
- `sketch/sketch.ino` — STM32 firmware and safe RPC handlers
- `sketch/sketch.yaml` — Arduino App Lab dependencies
- `gateway/app.py` — Debian-side WebUI Brick gateway

The WebUI Brick serves API routes on port 7000. Run the gateway on the UNO Q with the App Lab Python environment, not on the STM32.
