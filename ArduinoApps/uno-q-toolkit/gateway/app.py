"""UNO Q WebUI Brick gateway: validate JSON, call Bridge, and return JSON."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

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
    ui.expose_api("POST", "/api/v1/system/connect", system_connect_callback)
    ui.on_connect(_web_client_connected)
    return ui


web_ui = create_web_ui()
_call("lv.system.set.ip", _display_host(getattr(web_ui, "url", None)))


if __name__ == "__main__":
    App.run()
