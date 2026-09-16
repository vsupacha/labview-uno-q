"""UNO Q WebUI Brick gateway: validate JSON, call Bridge, and return JSON."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

from fastapi import WebSocket, WebSocketDisconnect

from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge

STATUS_ERROR = -1
LED_MAPPING = {
    "LED3_R": 50,
    "LED3_G": 51,
    "LED3_B": 52,
    "LED4_R": 53,
    "LED4_G": 54,
    "LED4_B": 55,
}

# LabVIEW is a plain HTTP request/response client, so a firmware-side interrupt
# cannot be pushed to it directly: fired events are buffered here and drained
# by LabVIEW polling POST /api/v1/interrupt/poll. Bounded so an unpolled queue
# cannot grow forever.
_INTERRUPT_QUEUE_MAXLEN = 256
_interrupt_lock = threading.Lock()
_interrupt_events: deque[dict[str, Any]] = deque(maxlen=_INTERRUPT_QUEUE_MAXLEN)


def _on_interrupt_fired(pin: int, level: int) -> None:
    """Handles the fire-and-forget lv.interrupt.fired notification from the STM32.

    The timestamp is stamped here, when the gateway receives the notification,
    not when the STM32 actually detected the edge: the firmware only reports
    (pin, level), and loop() batches notifications up to ~20ms late (its own
    poll interval), so this is a "received at" time, not a precise edge time.
    """
    with _interrupt_lock:
        _interrupt_events.append({"pin": pin, "level": level, "timestamp": time.time()})


def _require_lists(body: dict[str, Any], *names: str) -> str | None:
    for name in names:
        if not isinstance(body.get(name), list):
            return f"{name} must be a list"
    return None


def _entities(body: dict[str, Any], plural: str, singular: str) -> tuple[list[Any] | None, str | None]:
    """Normalize one JSON entity or an array to the array expected by RPC."""
    if plural in body:
        if isinstance(body[plural], list):
            return body[plural], None
        if plural == singular:
            return [body[plural]], None
        if not isinstance(body[plural], list):
            return None, f"{plural} must be a list"
    if singular in body:
        return [body[singular]], None
    return None, f"{plural} or {singular} is required"


def _validate_pins(pins: list[Any]) -> str | None:
    if any(not isinstance(pin, int) or isinstance(pin, bool) or pin < 0 or pin > 13 for pin in pins):
        return "pins must contain integers from 0 through 13"
    return None


def _call(name: str, *args: Any) -> dict[str, Any]:
    try:
        return {"status": Bridge.call(name, *args)}
    except Exception as exc:  # Bridge implementations expose several exception types.
        return {"status": STATUS_ERROR, "error": str(exc)}


def digital_read_callback(body: dict[str, Any]) -> dict[str, Any]:
    pins, error = _entities(body, "pins", "pin")
    error = error or _validate_pins(pins)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    try:
        status, values = Bridge.call("lv.digital.read", pins)
        return {"status": status, "values": values}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def analog_read_callback(body: dict[str, Any]) -> dict[str, Any]:
    channels, error = _entities(body, "channels", "channel")
    if error:
        return {"status": STATUS_ERROR, "error": error}
    if any(not isinstance(channel, int) or isinstance(channel, bool) or channel < 0 or channel > 5 for channel in channels):
        return {"status": STATUS_ERROR, "error": "channels must contain integers from 0 through 5"}
    try:
        status, values = Bridge.call("lv.analog.read", channels)
        return {"status": status, "values": values}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def digital_write_callback(body: dict[str, Any]) -> dict[str, Any]:
    pins, error = _entities(body, "pins", "pin")
    values, value_error = _entities(body, "values", "value")
    error = error or value_error
    if error:
        return {"status": STATUS_ERROR, "error": error}
    error = _validate_pins(pins)
    if error or len(pins) != len(values):
        return {"status": STATUS_ERROR, "error": error or "pins and values must have the same length"}
    return _call("lv.digital.write", pins, values)


def digital_mode_callback(body: dict[str, Any]) -> dict[str, Any]:
    pins, error = _entities(body, "pins", "pin")
    modes, mode_error = _entities(body, "modes", "mode")
    error = error or mode_error
    if error:
        return {"status": STATUS_ERROR, "error": error}
    error = _validate_pins(pins)
    if error or len(pins) != len(modes):
        return {"status": STATUS_ERROR, "error": error or "pins and modes must have the same length"}
    return _call("lv.digital.mode", pins, modes)


def led_ctrl_callback(body: dict[str, Any]) -> dict[str, Any]:
    leds, error = _entities(body, "leds", "led")
    states, state_error = _entities(body, "states", "state")
    error = error or state_error
    if error:
        return {"status": STATUS_ERROR, "error": error}
    if not leds:
        return {"status": STATUS_ERROR, "error": "leds must not be empty"}
    if len(leds) != len(states):
        return {"status": STATUS_ERROR, "error": "leds and states must have the same length"}
    try:
        rpc_leds = [LED_MAPPING[led] for led in leds]
    except (KeyError, TypeError) as exc:
        return {"status": STATUS_ERROR, "error": f"unknown LED: {exc.args[0]}"}
    # UNO Q RGB LEDs are active-low: a requested ON state is sent as 0.
    rpc_states = [0 if state else 1 for state in states]
    return _call("lv.led.ctrl", rpc_leds, rpc_states)


def _validate_uart_channel(body: dict[str, Any]) -> str | None:
    channel = body.get("channel")
    if not isinstance(channel, int) or isinstance(channel, bool) or channel != 0:
        return "channel must be 0 (D0/D1 Serial1)"
    return None


def uart_open_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_uart_channel(body)
    baud_rate = body.get("baudRate")
    if error or not isinstance(baud_rate, int) or isinstance(baud_rate, bool) or baud_rate <= 0:
        return {"status": STATUS_ERROR, "error": error or "baudRate must be a positive integer"}
    try:
        status, actual_baud_rate = Bridge.call("lv.uart.open", 0, baud_rate)
        return {"status": status, "baudRate": actual_baud_rate}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def uart_available_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_uart_channel(body)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    try:
        status, count = Bridge.call("lv.uart.available", 0)
        return {"status": status, "count": count}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def uart_read_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_uart_channel(body)
    count = body.get("count")
    if error or not isinstance(count, int) or isinstance(count, bool) or count < 0 or count > 65535:
        return {"status": STATUS_ERROR, "error": error or "count must be an integer from 0 through 65535"}
    try:
        status, data = Bridge.call("lv.uart.read", 0, count)
        return {"status": status, "data": list(data)}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def uart_write_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_uart_channel(body)
    data = body.get("data")
    if "data" not in body and "byte" in body:
        data = [body["byte"]]
    if error or not isinstance(data, list):
        return {"status": STATUS_ERROR, "error": error or "data or byte is required"}
    if any(not isinstance(byte, int) or isinstance(byte, bool) or byte < 0 or byte > 255 for byte in data):
        return {"status": STATUS_ERROR, "error": "data must contain integers from 0 through 255"}
    return _call("lv.uart.write", 0, bytes(data))


def uart_close_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_uart_channel(body)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    return _call("lv.uart.close", 0)


def _validate_interrupt_pin(body: dict[str, Any]) -> str | None:
    pin = body.get("pin")
    if not isinstance(pin, int) or isinstance(pin, bool) or not 0 <= pin <= 13:
        return "pin must be an integer from 0 through 13"
    return None


def interrupt_attach_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_interrupt_pin(body)
    mode = body.get("mode")
    if error or not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 4:
        return {
            "status": STATUS_ERROR,
            "error": error or "mode must be an integer from 0 through 4 (LOW=0, HIGH=1, CHANGE=2, FALLING=3, RISING=4)",
        }
    return _call("lv.interrupt.attach", body["pin"], mode)


def interrupt_detach_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_interrupt_pin(body)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    return _call("lv.interrupt.detach", body["pin"])


def interrupt_poll_callback(body: dict[str, Any]) -> dict[str, Any]:
    max_events = body.get("max", 32)
    if not isinstance(max_events, int) or isinstance(max_events, bool) or not 1 <= max_events <= _INTERRUPT_QUEUE_MAXLEN:
        return {"status": STATUS_ERROR, "error": f"max must be an integer from 1 through {_INTERRUPT_QUEUE_MAXLEN}"}
    events: list[dict[str, Any]] = []
    with _interrupt_lock:
        while _interrupt_events and len(events) < max_events:
            events.append(_interrupt_events.popleft())
    return {"status": 0, "events": events}


_RTC_FIELD_BOUNDS = {
    "year": (1970, 2099),
    "month": (1, 12),
    "day": (1, 31),
    "hour": (0, 23),
    "minute": (0, 59),
    "second": (0, 59),
}


def _validate_rtc_datetime(body: dict[str, Any]) -> str | None:
    for field, (low, high) in _RTC_FIELD_BOUNDS.items():
        value = body.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            return f"{field} must be an integer from {low} through {high}"
    return None


def rtc_get_callback(body: dict[str, Any]) -> dict[str, Any]:
    del body
    try:
        status, year, month, day, hour, minute, second = Bridge.call("lv.rtc.get")
        return {
            "status": status,
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "second": second,
        }
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def rtc_set_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_rtc_datetime(body)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    return _call(
        "lv.rtc.set",
        body["year"], body["month"], body["day"],
        body["hour"], body["minute"], body["second"],
    )


# --- DAQ (api/v2): block/continuous acquisition, data delivered over a raw
# WebSocket rather than REST. A plain FastAPI @app.websocket route is used
# instead of the WebUI Brick's own Socket.IO instance (self.sio): Socket.IO
# has its own handshake/framing on top of the WebSocket upgrade, which a
# generic WebSocket client (LabVIEW included) cannot speak without a
# Socket.IO-aware library. The event loop is captured lazily from the first
# connected client rather than via a FastAPI startup hook, since it must be
# the one Uvicorn is actually running requests on.
_daq_loop: asyncio.AbstractEventLoop | None = None
_daq_ws_lock = threading.Lock()
_daq_ws_clients: set[WebSocket] = set()
_DAQ_TYPE_CODES = {"digital": 0, "analog": 1}
_DAQ_MAX_CHANNELS = 8


async def _daq_send(client: WebSocket, message: dict[str, Any]) -> None:
    try:
        await client.send_json(message)
    except Exception:
        with _daq_ws_lock:
            _daq_ws_clients.discard(client)


def _daq_broadcast(message: dict[str, Any]) -> None:
    if _daq_loop is None:
        return  # No client has connected yet; nothing to deliver to.
    with _daq_ws_lock:
        clients = list(_daq_ws_clients)
    for client in clients:
        asyncio.run_coroutine_threadsafe(_daq_send(client, message), _daq_loop)


def _on_daq_chunk(index: int, values: list[int]) -> None:
    """Handles the fire-and-forget lv.daq.chunk notification from the STM32."""
    _daq_broadcast({"type": "chunk", "index": index, "values": values})


def _on_daq_done() -> None:
    """Handles the fire-and-forget lv.daq.done notification from the STM32."""
    _daq_broadcast({"type": "done"})


async def daq_ws_route(websocket: WebSocket) -> None:
    global _daq_loop
    await websocket.accept()
    _daq_loop = asyncio.get_running_loop()
    with _daq_ws_lock:
        _daq_ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # Only used to detect disconnects; payload is ignored.
    except WebSocketDisconnect:
        pass
    finally:
        with _daq_ws_lock:
            _daq_ws_clients.discard(websocket)


def _validate_daq_channels(body: dict[str, Any]) -> tuple[list[int] | None, list[int] | None, str | None]:
    channels = body.get("channels")
    if not isinstance(channels, list) or not 1 <= len(channels) <= _DAQ_MAX_CHANNELS:
        return None, None, f"channels must be a list of 1 through {_DAQ_MAX_CHANNELS} entries"
    pins: list[int] = []
    types: list[int] = []
    for entry in channels:
        if not isinstance(entry, dict):
            return None, None, "each channel must be an object with 'pin' and 'type'"
        type_name = entry.get("type")
        if type_name not in _DAQ_TYPE_CODES:
            return None, None, "type must be 'digital' or 'analog'"
        pin = entry.get("pin")
        max_pin = 13 if type_name == "digital" else 5
        if not isinstance(pin, int) or isinstance(pin, bool) or not 0 <= pin <= max_pin:
            return None, None, f"pin must be an integer from 0 through {max_pin} for type '{type_name}'"
        pins.append(pin)
        types.append(_DAQ_TYPE_CODES[type_name])
    return pins, types, None


def daq_start_callback(body: dict[str, Any]) -> dict[str, Any]:
    pins, types, error = _validate_daq_channels(body)
    interval = body.get("intervalMicros")
    sample_count = body.get("sampleCount", 0)
    if not error and (not isinstance(interval, int) or isinstance(interval, bool) or interval <= 0):
        error = "intervalMicros must be a positive integer"
    if not error and (not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 0):
        error = "sampleCount must be a non-negative integer (0 = continuous)"
    if error:
        return {"status": STATUS_ERROR, "error": error}
    return _call("lv.daq.start", pins, types, interval, sample_count)


def daq_stop_callback(body: dict[str, Any]) -> dict[str, Any]:
    del body
    return _call("lv.daq.stop")


def _validate_i2c_channel(body: dict[str, Any]) -> str | None:
    channel = body.get("channel")
    if not isinstance(channel, int) or isinstance(channel, bool) or channel != 0:
        return "channel must be 0 (single onboard I2C bus)"
    return None


def _validate_i2c_address(body: dict[str, Any]) -> str | None:
    address = body.get("address")
    if not isinstance(address, int) or isinstance(address, bool) or not 1 <= address <= 127:
        return "address must be an integer from 1 through 127"
    return None


def i2c_open_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_i2c_channel(body)
    frequency = body.get("frequency")
    if error or not isinstance(frequency, int) or isinstance(frequency, bool) or not 0 < frequency <= 1000000:
        return {"status": STATUS_ERROR, "error": error or "frequency must be an integer from 1 through 1000000"}
    try:
        status, actual_frequency = Bridge.call("lv.i2c.open", 0, frequency)
        return {"status": status, "frequency": actual_frequency}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def i2c_write_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_i2c_channel(body) or _validate_i2c_address(body)
    data = body.get("data")
    if error or not isinstance(data, list) or not data:
        return {"status": STATUS_ERROR, "error": error or "data must be a non-empty list"}
    if any(not isinstance(byte, int) or isinstance(byte, bool) or byte < 0 or byte > 255 for byte in data):
        return {"status": STATUS_ERROR, "error": "data must contain integers from 0 through 255"}
    return _call("lv.i2c.write", 0, body["address"], bytes(data))


def i2c_read_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_i2c_channel(body) or _validate_i2c_address(body)
    count = body.get("count")
    if error or not isinstance(count, int) or isinstance(count, bool) or not 0 < count <= 32:
        return {"status": STATUS_ERROR, "error": error or "count must be an integer from 1 through 32"}
    try:
        status, data = Bridge.call("lv.i2c.read", 0, body["address"], count)
        return {"status": status, "data": list(data)}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def i2c_close_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_i2c_channel(body)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    return _call("lv.i2c.close", 0)


def _validate_spi_channel(body: dict[str, Any]) -> str | None:
    channel = body.get("channel")
    if not isinstance(channel, int) or isinstance(channel, bool) or channel != 0:
        return "channel must be 0 (single onboard SPI bus)"
    return None


def spi_open_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_spi_channel(body)
    frequency = body.get("frequency")
    mode = body.get("mode", 0)
    msb_first = body.get("msbFirst", True)
    if error or not isinstance(frequency, int) or isinstance(frequency, bool) or frequency <= 0:
        return {"status": STATUS_ERROR, "error": error or "frequency must be a positive integer"}
    if not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 3:
        return {"status": STATUS_ERROR, "error": "mode must be an integer from 0 through 3"}
    if not isinstance(msb_first, bool):
        return {"status": STATUS_ERROR, "error": "msbFirst must be a boolean"}
    try:
        status, actual_frequency = Bridge.call("lv.spi.open", 0, frequency, mode, msb_first)
        return {"status": status, "frequency": actual_frequency}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def spi_transfer_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_spi_channel(body)
    chip_select = body.get("chipSelect")
    data = body.get("data")
    if error or not isinstance(chip_select, int) or isinstance(chip_select, bool) or not 0 <= chip_select <= 13:
        return {"status": STATUS_ERROR, "error": error or "chipSelect must be an integer from 0 through 13"}
    if chip_select in (11, 12, 13):
        return {"status": STATUS_ERROR, "error": "chipSelect must not be an SPI bus pin (11, 12, 13)"}
    if not isinstance(data, list) or not data:
        return {"status": STATUS_ERROR, "error": "data must be a non-empty list"}
    if any(not isinstance(byte, int) or isinstance(byte, bool) or byte < 0 or byte > 255 for byte in data):
        return {"status": STATUS_ERROR, "error": "data must contain integers from 0 through 255"}
    try:
        status, rx_data = Bridge.call("lv.spi.transfer", 0, chip_select, bytes(data))
        return {"status": status, "data": list(rx_data)}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def spi_close_callback(body: dict[str, Any]) -> dict[str, Any]:
    error = _validate_spi_channel(body)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    return _call("lv.spi.close", 0)


def analog_write_callback(body: dict[str, Any]) -> dict[str, Any]:
    pins, error = _entities(body, "pins", "pin")
    duty, duty_error = _entities(body, "duty", "duty")
    error = error or duty_error
    if error:
        return {"status": STATUS_ERROR, "error": error}
    if len(pins) != len(duty):
        return {"status": STATUS_ERROR, "error": "pins and duty must have the same length"}
    error = _validate_pins(pins)
    if error:
        return {"status": STATUS_ERROR, "error": error}
    pwm_pins = {3, 5, 6, 9, 10, 11}
    if any(pin not in pwm_pins for pin in pins):
        return {"status": STATUS_ERROR, "error": "pins must be PWM-capable: 3, 5, 6, 9, 10, or 11"}
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 or value > 1 for value in duty):
        return {"status": STATUS_ERROR, "error": "duty values must be numbers from 0.0 through 1.0"}
    return _call("lv.pwm.write", pins, [float(value) for value in duty])


def pulse_in_callback(body: dict[str, Any]) -> dict[str, Any]:
    pin = body.get("pin")
    state = body.get("state", 1)
    timeout = body.get("timeout", 1000000)
    if not isinstance(pin, int) or isinstance(pin, bool) or not 0 <= pin <= 13:
        return {"status": STATUS_ERROR, "error": "pin must be an integer from 0 through 13"}
    if state not in (0, 1, False, True):
        return {"status": STATUS_ERROR, "error": "state must be 0/1 or false/true"}
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 0 < timeout <= 4294967295:
        return {"status": STATUS_ERROR, "error": "timeout must be an integer from 1 through 4294967295"}
    try:
        status, duration = Bridge.call("lv.pulse.in", pin, int(bool(state)), timeout)
        return {"status": status, "duration": duration}
    except Exception as exc:
        return {"status": STATUS_ERROR, "error": str(exc)}


def _display_host(url: Any) -> str:
    """Return a useful board address for the booting LED-matrix display."""
    if isinstance(url, str):
        host = urlparse(url).hostname
        if host and host not in {"0.0.0.0", "127.0.0.1", "localhost"}:
            return host
    return os.getenv("HOST_IP", "UNO-Q")


def _web_client_connected(session_id: str) -> None:
    """A WebUI connection is the explicit booting -> running transition."""
    del session_id
    _call("lv.system.running")


def system_connect_callback(body: dict[str, Any]) -> dict[str, Any]:
    """Provide a curl/pytest-friendly equivalent of a WebUI connection."""
    del body
    return _call("lv.system.running")


def create_web_ui() -> WebUI:
    """Create the App Lab WebUI Brick and register REST endpoints."""
    ui = WebUI(port=7000, assets_dir_path="/app/assets", api_path_prefix="")
    ui.expose_api("POST", "/api/v1/digital/read", digital_read_callback)
    ui.expose_api("POST", "/api/v1/analog/read", analog_read_callback)
    ui.expose_api("POST", "/api/v1/analog/write", analog_write_callback)
    ui.expose_api("POST", "/api/v1/pulse/in", pulse_in_callback)
    ui.expose_api("POST", "/api/v1/digital/write", digital_write_callback)
    ui.expose_api("POST", "/api/v1/digital/mode", digital_mode_callback)
    ui.expose_api("POST", "/api/v1/led/ctrl", led_ctrl_callback)
    ui.expose_api("POST", "/api/v1/uart/open", uart_open_callback)
    ui.expose_api("POST", "/api/v1/uart/available", uart_available_callback)
    ui.expose_api("POST", "/api/v1/uart/read", uart_read_callback)
    ui.expose_api("POST", "/api/v1/uart/write", uart_write_callback)
    ui.expose_api("POST", "/api/v1/uart/close", uart_close_callback)
    ui.expose_api("POST", "/api/v1/i2c/open", i2c_open_callback)
    ui.expose_api("POST", "/api/v1/i2c/write", i2c_write_callback)
    ui.expose_api("POST", "/api/v1/i2c/read", i2c_read_callback)
    ui.expose_api("POST", "/api/v1/i2c/close", i2c_close_callback)
    ui.expose_api("POST", "/api/v1/spi/open", spi_open_callback)
    ui.expose_api("POST", "/api/v1/spi/transfer", spi_transfer_callback)
    ui.expose_api("POST", "/api/v1/spi/close", spi_close_callback)
    ui.expose_api("POST", "/api/v1/interrupt/attach", interrupt_attach_callback)
    ui.expose_api("POST", "/api/v1/interrupt/detach", interrupt_detach_callback)
    ui.expose_api("POST", "/api/v1/interrupt/poll", interrupt_poll_callback)
    ui.expose_api("POST", "/api/v1/rtc/get", rtc_get_callback)
    ui.expose_api("POST", "/api/v1/rtc/set", rtc_set_callback)
    ui.expose_api("POST", "/api/v2/daq/start", daq_start_callback)
    ui.expose_api("POST", "/api/v2/daq/stop", daq_stop_callback)
    ui.expose_api("POST", "/api/v1/system/connect", system_connect_callback)
    ui.on_connect(_web_client_connected)
    return ui


web_ui = create_web_ui()
# expose_api() only registers REST routes; the DAQ data channel is a raw
# WebSocket, which needs the underlying FastAPI app directly.
web_ui.app.add_api_websocket_route("/api/v2/daq/ws", daq_ws_route)
Bridge.provide("lv.interrupt.fired", _on_interrupt_fired)
Bridge.provide("lv.daq.chunk", _on_daq_chunk)
Bridge.provide("lv.daq.done", _on_daq_done)
_call("lv.system.set.ip", _display_host(getattr(web_ui, "url", None)))


if __name__ == "__main__":
    App.run()
