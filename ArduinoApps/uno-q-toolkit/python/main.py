import time

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

# Initialize the Web UI server
print("Booting")
web_ui = WebUI()


# Define callback functions
def digital_read_callback(body:dict):
    pins = body.get("pins", [])
    
    for pin in pins:
        if pin > 13:
            return {
                "status": -1,
                "error": f"Exceed digital pin: {pin}"
            }
    
    resp = Bridge.call(
        "lv.digital.read",
        pins
    )
    
    return {
        "status": resp[0],
        "values": resp[1]
    }

def digital_write_callback(body:dict):
    pins = body.get("pins", [])
    values = body.get("values", [])

    if len(pins) != len(values):
        return {
            "status": -1, 
            "error": "pins and values must have the same length"
        }
    
    for pin in pins:
        if pin > 13:
            return {
                "status": -1,
                "error": f"Exceed digital pin: {pin}"
            }
    
    status = Bridge.call(
        "lv.digital.write",
        pins,
        values
    )
    return {
        "status": status
    }

def digital_mode_callback(body:dict):
    pins = body.get("pins", [])
    modes = body.get("modes", [])

    if len(pins) != len(modes):
        return {
            "status": -1, 
            "error": "pins and modes must have the same length"
        }

    for pin in pins:
        if pin > 13:
            return {
                "status": -1,
                "error": f"Exceed digital pin: {pin}"
            }
    
    status = Bridge.call(
        "lv.digital.mode",
        pins,
        modes
    )
    return {
        "status": 0
    }


def led_ctrl_callback(body:dict):   
    leds = body.get("leds", [])
    states = body.get("states", [])

    if len(leds) != len(states):
        return {
            "status": -1, 
            "error": "leds and states must have the same length"
        }

    LED_MAPPING = {
        "LED3_R": 50,
        "LED3_G": 51,
        "LED3_B": 52,
        "LED4_R": 53,
        "LED4_G": 54,
        "LED4_B": 55,
    }
    try:
        rpc_leds = [LED_MAPPING[led] for led in leds]
    except KeyError as e:
        return {
            "status": -1,
            "error": f"unknown LED: {e.args[0]}"
        }
    rpc_states = [0 if state else 1 for state in states]
        
    status = Bridge.call(
        "lv.led.ctrl",
        rpc_leds,
        rpc_states
    )
    return {
        "status": status
    }

# Add REST API endpoints
web_ui.expose_api(
    "POST",
    "/api/v1/digital/read",
    digital_read_callback
)

web_ui.expose_api(
    "POST",
    "/api/v1/digital/write",
    digital_write_callback
)

web_ui.expose_api(
    "POST",
    "/api/v1/digital/mode",
    digital_mode_callback
)

web_ui.expose_api(
    "POST",
    "/api/v1/led/ctrl",
    led_ctrl_callback
)

# Start the server
web_ui.start()

def loop():
    """This function is called repeatedly by the App framework."""
    time.sleep(1)

# See: https://docs.arduino.cc/software/app-lab/tutorials/getting-started/#app-run
App.run(user_loop=loop)
