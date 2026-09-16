#pragma once

#include <Arduino.h>

// RPC status codes shared with the gateway. Shared across api/v1 and api/v2:
// 0 means success, -1 invalid input, -2 not implemented (currently unused).
constexpr int STATUS_OK = 0;
constexpr int STATUS_INVALID_ARGUMENT = -1;
constexpr int STATUS_NOT_IMPLEMENTED = -2;

constexpr int DIGITAL_PIN_MIN = 0;
constexpr int DIGITAL_PIN_MAX = 13;

// Shared with api/v2 (DAQ digital-channel bounds use the same pin range).
bool validDigitalPin(int pin);

// Registers Wire/SPI/RTC/LED-matrix peripherals and every lv.* RPC handler
// except lv.daq.*. Call once from setup(), after Bridge.begin().
void apiV1Begin();

// Drains pending interrupt notifications and updates the boot/status
// LED-matrix display. Call every loop() iteration.
void apiV1Poll();
