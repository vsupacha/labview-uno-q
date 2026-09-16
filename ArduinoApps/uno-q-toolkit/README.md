# UNO Q LabVIEW gateway

This project exposes a small REST/JSON surface through the Arduino App Lab `WebUI` Brick and forwards hardware operations to the STM32U585 through `Arduino_RouterBridge`.

Revision 0.1 implements digital I/O, analog input, PWM, pulse timing, UART, I2C, SPI, pin-change interrupts, the onboard RTC, and onboard RGB LED control.

- I2C (`lv.i2c.*`) uses a single onboard bus (channel 0), 7-bit addresses 1–127, and caps a single transfer at 32 bytes.
- SPI (`lv.spi.*`) uses a single onboard bus (channel 0); the caller supplies the chip-select pin per transfer (any digital pin except the bus pins D11/D12/D13), and `open` configures clock, mode (0–3), and bit order.
- Interrupts (`lv.interrupt.*`) let LabVIEW attach a trigger mode (LOW=0, HIGH=1, CHANGE=2, FALLING=3, RISING=4) to any digital pin. Firing is unsolicited, so LabVIEW cannot receive it directly over request/response HTTP: the gateway buffers fired `{pin, level, timestamp}` events (capped at 256) and LabVIEW drains them with `POST /api/v1/interrupt/poll`. `timestamp` is `time.time()` at the moment the gateway received the notification, not the actual STM32 edge time — it's stamped after the firmware's own ISR→loop()→Bridge.notify hop, which can lag the real edge by up to loop()'s ~20ms cycle. See "Interrupt event flow" below for why the firmware defers the notification instead of sending it straight from the ISR.
- RTC (`lv.rtc.*`) reads/writes the STM32's onboard real-time clock (LSE-backed, independent of any header pin). Whether it keeps time across a power cycle depends on the board's VBAT/backup-domain wiring, which this app doesn't assume either way — call `POST /api/v1/rtc/set` once at startup rather than assuming `POST /api/v1/rtc/get` already holds a meaningful value.

An experimental `api/v2` DAQ (block/streaming acquisition) surface is described in "DAQ (api/v2)" below. `POST /api/v2/daq/start` and `/stop` have been exercised on real hardware (see `skills.md`, root) in continuous mode (`sampleCount: 0`), confirming the sampling thread starts/stops cleanly and `api/v1` calls keep working while `api/v2` is active. **Not yet independently verified on hardware:** the `/api/v2/daq/ws` WebSocket data channel itself (no test reads from it), the one-shot path (`sampleCount > 0` and its `{"type": "done"}` message), and the `lv.daq.chunk`/`lv.daq.done` `Bridge.notify()` payloads actually decoding correctly under real acquisition traffic.

The REST service is intentionally unauthenticated for local development. Before exposing it beyond a trusted LAN, add authentication and bind/firewall it appropriately.

## Layout

- `app.yaml` — Arduino App Lab app descriptor
- `python/main.py` — App Lab Linux-side entry point
- `sketch/sketch.ino` — only `setup()`/`loop()`; delegates to `apiV1Begin()`/`apiV1Poll()`/`apiV2Begin()`
- `sketch/api_v1.h` / `sketch/api_v1.cpp` — the Arduino-style `api/v1` RPC handlers (digital/analog/PWM/pulse/I2C/SPI/UART/interrupts/RTC/LED/system), plus the shared `STATUS_*` codes and `validDigitalPin()` that `api/v2` also uses
- `sketch/api_v2.h` / `sketch/api_v2.cpp` — the `api/v2` DAQ RPC handlers and its dedicated sampling thread
- `sketch/sketch.yaml` — Arduino App Lab dependencies
- `gateway/app.py` — Debian-side WebUI Brick gateway

The WebUI Brick serves API routes on port 7000. Run the gateway on the UNO Q with the App Lab Python environment, not on the STM32.

## Interrupt event flow

`attachInterrupt()`'s callback runs in real Zephyr interrupt context on this core (confirmed in the core's `WInterrupts.cpp`), and `attachInterruptParam()` — which would let one shared ISR receive the pin as a runtime argument — is declared but never implemented here, so it isn't usable. Two consequences shape the firmware:

- One tiny trampoline ISR per pin (`isrPin0`..`isrPin13`) is registered via `attachInterrupt()`, since the callback can't carry a runtime parameter. Each just sets an atomic bit for its own pin.
- `Bridge.notify()` takes a Zephyr mutex and can yield — both illegal from real interrupt context — so the ISRs never call it directly. `loop()` (thread context) drains the atomic bitmask with `atomic_test_and_clear_bit()` each iteration and calls `Bridge.notify("lv.interrupt.fired", pin, level)` from there instead.

On the Debian side, `gateway/app.py` registers a single `Bridge.provide("lv.interrupt.fired", ...)` handler that appends `(pin, level)` to an in-memory queue; `POST /api/v1/interrupt/poll` is how LabVIEW retrieves them, since it has no way to receive a Python-side push.

## DAQ (api/v2)

Unlike `api/v1`, which is pure request/response, `api/v2/daq/*` splits **commands** (REST) from **data** (a raw WebSocket) so a continuous acquisition doesn't have to be polled:

- `POST /api/v2/daq/start` — `{"channels": [{"pin": 0, "type": "analog"}, {"pin": 3, "type": "digital"}], "intervalMicros": 2000, "sampleCount": 100}`. `sampleCount: 0` (or omitted) means continuous; a channel list mixes analog (`A0`–`A5`) and digital (`D0`–`D13`) entries, 1–8 channels total.
- `POST /api/v2/daq/stop` — stops the current acquisition (one-shot or continuous).
- `GET` (WebSocket upgrade) `/api/v2/daq/ws` — the data channel. Each configured sampling pass is broadcast as `{"type": "chunk", "index": <first sample index in this chunk>, "values": [...]}` (values interleaved per channel, in channel order), and a one-shot acquisition ends with `{"type": "done"}`.

This is a **raw FastAPI WebSocket** (`web_ui.app.add_api_websocket_route`), not the WebUI Brick's own Socket.IO instance (`self.sio`, used elsewhere for the UI). Socket.IO has its own handshake/framing on top of the WebSocket upgrade that a generic WebSocket client can't speak without a Socket.IO-aware library — a plain WebSocket is the only choice that doesn't assume LabVIEW (or anything else) has that library.

### Why sampling runs on its own thread, and what that bounds

`analogRead()` on this core calls `adc_channel_setup()` and `adc_read()` **every single call** (confirmed in `wiring_analog.cpp`) — it blocks on the ADC driver and is not ISR-safe. That rules out a hardware-timer ISR driving acquisition (the same way `attachInterrupt` does for pin changes) for any channel list that includes an analog channel. Instead, `sketch.ino` runs a dedicated low-priority Zephyr thread (`daqThreadEntry`, started once in `setup()`) that loops: read each configured channel, `k_usleep(intervalMicros)`, repeat — parked on a semaphore between acquisitions. This is a best-effort spaced loop, **not** a real-time sample clock: `analogRead()`'s own per-call setup overhead (plus however many channels are configured) bounds the realistically achievable rate well below what a large `intervalMicros` value alone would suggest, and jitter increases with channel count.

Chunking is mandatory, not a tuning choice: the STM32↔gateway link is a single UART running `Arduino_RouterBridge`'s MessagePack RPC framing, and its frame budget (`DECODER_BUFFER_SIZE / 4` = 256 bytes, confirmed in `Arduino_RPClite`) leaves room for roughly 32 sample values per `Bridge.notify("lv.daq.chunk", ...)` call after framing overhead — that's why `DAQ_CHUNK_MAX_VALUES` is 32 and chunks span multiple channels' worth of time-slices, not one sample each.

## Building, deploying, and running

**Arduino App Lab is the tool for this app.** Open the UNO Q in App Lab, open `uno-q-toolkit`, and use App Lab's own Start/Stop controls: it compiles and uploads `sketch/*` to the STM32U585 and starts the `gateway/app.py` WebUI Brick as one step — there is no separate build command and no other tool needed for normal use.

To exercise the REST API once the app is running, either point LabVIEW at it (see `labview/` at the repository root) or send requests manually, e.g. with the Postman/Insomnia collection in `API_test/` (repository root) or a plain HTTP client against `http://<board-address>:7000/api/v1/...` (and `/api/v2/...` for DAQ).

A separate, CLI-based automation path (ADB, `tools/uno_q.py`, hardware pytest suites) exists for contributors and repeatable verification without opening App Lab by hand — see `AGENTS.md` and `skills.md` (repository root). It's a development convenience, not a requirement for using or deploying this app.
