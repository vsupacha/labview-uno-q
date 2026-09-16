# Using UNO Q with LabVIEW

This project adapts the **LabVIEW Hobbyist Toolkit Remote I/O model** to the **Arduino UNO Q**.

Instead of communicating directly with a conventional Arduino firmware over a serial link, LabVIEW communicates with a gateway running on the UNO Q's Debian/Linux side. The gateway translates LabVIEW requests into RPC calls executed by the STM32U585, where the actual Arduino-compatible hardware operations are performed.

Project article: https://www.hackster.io/vsupacha/using-uno-q-with-labview-cd8c2f

## Using this repo

### 1. Install the app on the UNO Q

The board-side app is `ArduinoApps/uno-q-toolkit/` — STM32 firmware in `sketch/`, the Debian-side gateway in `gateway/`, and the App Lab entry point in `python/`. Install it with **Arduino App Lab**: open App Lab on the UNO Q, create or open the `uno-q-toolkit` app, and copy the contents of each file under `ArduinoApps/uno-q-toolkit/` into the matching file in App Lab's own editor (`app.yaml`, `python/main.py`, `gateway/app.py`, `gateway/requirements.txt`, and everything under `sketch/`). Press Start — App Lab compiles the STM32 sketch and starts the Python gateway together, no separate build step.

### 2. Open the LabVIEW project

Open `labview/LabVIEW UNO Q toolkit.lvproj` in **LabVIEW 2021 or later**. It contains the hardware-access API VIs (`UNO Q connect`/`disconnect`, `PinMode`, `DigitalRead`/`DigitalWrite`, `AnalogRead`, `LED control`) and demo VIs (`Demo - blink`, `Demo - din`, `Demo - dout`, `Demo - plot`) showing how to call them from a LabVIEW application.

## Why LabVIEW?

LabVIEW is designed for measurement, instrumentation, automation, and hardware interfacing. Its graphical dataflow model makes it convenient to combine:

- sensor and data acquisition,
- hardware control,
- visualization,
- instrument communication, and
- operator interfaces.

LabVIEW Community Edition also includes the Hobbyist Toolkit, which provides maker-oriented hardware abstractions for platforms such as Arduino and Raspberry Pi.

## Background: LabVIEW Hobbyist Toolkit

The Hobbyist Toolkit exposes common hardware functions such as:

- Digital I/O
- Analog I/O
- PWM
- I2C
- SPI
- UART

For conventional Arduino boards, LabVIEW normally runs on the host PC and controls firmware on the target through the **Remote I/O** model.

The UNO Q differs from a conventional Arduino because it contains two processing domains:

- **Qualcomm QRB2210** running Debian Linux
- **STM32U585** running Arduino-compatible firmware

Because of this architecture, directly porting the original Arduino Remote I/O design is not the most natural approach.

## UNO Q Toolkit Architecture

This project adapts the Remote I/O concept into a gateway architecture:

```text
LabVIEW
   |
   | HTTP + JSON
   v
Debian / Qualcomm QRB2210
WebUI gateway
   |
   | Arduino RouterBridge RPC
   v
STM32U585
Arduino APIs
   |
   v
GPIO / ADC / PWM / I2C / SPI / UART
```

LabVIEW keeps the familiar hardware abstraction, while the communication implementation is changed from the original serial-oriented approach to REST-based requests.

## STM32U585 Layer

The STM32U585 performs the actual low-level hardware access.

Arduino operations are exposed as named RPC functions using `Bridge.provide_safe()`.

Example:

```cpp
void setup() {
    Bridge.provide_safe("lv.digital.read",  lvDigitalRead);
    Bridge.provide_safe("lv.digital.write", lvDigitalWrite);
    Bridge.provide_safe("lv.digital.mode",  lvDigitalMode);
    Bridge.provide_safe("lv.led.ctrl",      lvLedCtrl);
    Bridge.provide_safe("lv.analog.read",   lvAnalogRead);
}
```

RPC names follow the convention:

```text
lv.<peripheral>.<operation>
```

For example:

```text
lv.digital.write
lv.digital.read
lv.analog.read
lv.led.ctrl
```

The RPC interface uses arrays where appropriate so that one call can operate on either a single channel or multiple channels.

### Status values

Each RPC operation returns an explicit status:

| Status | Meaning |
|---:|---|
| `0` | Operation completed successfully |
| `-1` | Invalid argument or unsupported hardware request |
| `-2` | Function declared but not implemented |

Read operations return both status and data.

Example:

```text
(0, [1, 0, 1])
```

for a successful digital read of three pins.

## Qualcomm / Debian Layer

The Qualcomm QRB2210 acts as the gateway between LabVIEW and the STM32.

The gateway is implemented using the Arduino App Lab **WebUI Brick** and exposes REST endpoints such as:

```text
POST /api/v1/digital/write
POST /api/v1/analog/read
POST /api/v1/system/connect
```

A typical gateway operation is:

1. Receive a JSON request from LabVIEW.
2. Validate the request.
3. Convert user-facing parameters when required.
4. Call the corresponding STM32 RPC using `Bridge.call()`.
5. Convert the RPC result into JSON.
6. Return status and data to LabVIEW.

Example:

```python
def analog_read_callback(body):
    channels, error = _entities(body, "channels", "channel")

    if error:
        return {"status": -1, "error": error}

    status, values = Bridge.call("lv.analog.read", channels)

    return {
        "status": status,
        "values": values
    }
```

This separation keeps hardware control on the STM32 while allowing the Debian-side service to evolve independently.

## Initial API Coverage

The first revision targets the main peripheral operations expected from the LabVIEW Hobbyist Toolkit:

- Digital I/O
- Analog input
- PWM
- I2C
- SPI
- UART
- Onboard LED control

Some UNO Q-specific details are handled by the gateway rather than exposed directly to LabVIEW. For example, onboard RGB LED behavior can be represented using symbolic LED names instead of requiring applications to know the underlying hardware mapping.

## Design Goal

The main objective is to preserve the familiar LabVIEW programming model while adapting it to the heterogeneous UNO Q architecture.

From the LabVIEW application's point of view, the user should work with reusable hardware-access VIs rather than manually handling:

- HTTP requests,
- JSON encoding,
- RouterBridge RPC,
- processor-specific pin mappings, or
- STM32 firmware implementation details.

This makes the UNO Q usable as a LabVIEW-controlled measurement and automation platform while keeping the responsibilities of the Linux and MCU domains clearly separated.

## Current Status

This project is a **proof of concept**. The current implementation focuses on adapting Remote I/O-style LabVIEW access to the UNO Q software architecture.

Potential future extensions include:

- additional LabVIEW wrapper VIs,
- higher-level hardware APIs,
- streaming data transfer,
- support for more UNO Q services, and
- integration with additional sensors, shields, and peripherals.

## Reference

Full project description:

**Using UNO Q with LabVIEW**  
Hackster.io  
https://www.hackster.io/vsupacha/using-uno-q-with-labview-cd8c2f
