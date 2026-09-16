#include "api_v1.h"

#include <Wire.h>
#include <SPI.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>
#include <MsgPack.h>
#include <RTC.h>
#include <zephyr/sys/atomic.h>

constexpr int LED_PIN_MIN = 50;
constexpr int LED_PIN_MAX = 55;
constexpr uint8_t UART_CHANNEL = 0;
constexpr uint8_t I2C_CHANNEL = 0;
constexpr uint8_t I2C_MAX_TRANSFER = 32;
constexpr uint8_t SPI_CHANNEL = 0;
constexpr uint8_t SPI_MOSI_PIN = 11;
constexpr uint8_t SPI_MISO_PIN = 12;
constexpr uint8_t SPI_SCK_PIN = 13;
constexpr uint8_t INTERRUPT_PIN_COUNT = DIGITAL_PIN_MAX - DIGITAL_PIN_MIN + 1;

enum DeviceState : uint8_t {
  STATE_BOOTING = 0,
  STATE_RUNNING = 1,
};

Arduino_LED_Matrix matrix;
Rtc rtc;
DeviceState deviceState = STATE_BOOTING;
String displayMessage = "IP waiting";
uint8_t displayOffset = 0;
bool displayNeedsUpdate = true;
unsigned long nextBootDisplay = 0;

bool validDigitalPin(int pin) {
  return pin >= DIGITAL_PIN_MIN && pin <= DIGITAL_PIN_MAX;
}

bool validPwmPin(int pin) {
  return pin == 3 || pin == 5 || pin == 6 || pin == 9 || pin == 10 || pin == 11;
}

bool validLedPin(int pin) {
  return pin >= LED_PIN_MIN && pin <= LED_PIN_MAX;
}

bool validI2cAddress(int address) {
  return address >= 1 && address <= 127;
}

bool validSpiChipSelectPin(int pin) {
  return validDigitalPin(pin) && pin != SPI_MOSI_PIN && pin != SPI_MISO_PIN && pin != SPI_SCK_PIN;
}

bool validRtcDateTime(int year, int month, int day, int hour, int minute, int second) {
  return year >= 1970 && year <= 2099 &&
         month >= 1 && month <= 12 &&
         day >= 1 && day <= 31 &&
         hour >= 0 && hour <= 23 &&
         minute >= 0 && minute <= 59 &&
         second >= 0 && second <= 59;
}

bool i2cOpen = false;
bool spiOpen = false;
SPISettings spiSettings;

// Set only from an ISR (attachInterrupt runs the callback in real interrupt
// context on this core), drained only from apiV1Poll() (thread context). The
// atomic bit test-and-clear is what keeps that handoff race-free: an ISR can
// fire again mid-drain without losing or duplicating the event.
atomic_t pendingInterruptMask = ATOMIC_INIT(0);

inline void markPinInterrupt(uint8_t pin) {
  atomic_set_bit(&pendingInterruptMask, pin);
}

// attachInterrupt() on this Zephyr-based core only accepts a plain void(*)(void)
// callback -- attachInterruptParam() is declared in the core headers but has no
// implementation here, so it cannot be used to pass the pin as a runtime
// argument. One tiny trampoline per pin is the only way to know which pin fired.
#define DEFINE_PIN_ISR(N) void isrPin##N() { markPinInterrupt(N); }
DEFINE_PIN_ISR(0)  DEFINE_PIN_ISR(1)  DEFINE_PIN_ISR(2)  DEFINE_PIN_ISR(3)
DEFINE_PIN_ISR(4)  DEFINE_PIN_ISR(5)  DEFINE_PIN_ISR(6)  DEFINE_PIN_ISR(7)
DEFINE_PIN_ISR(8)  DEFINE_PIN_ISR(9)  DEFINE_PIN_ISR(10) DEFINE_PIN_ISR(11)
DEFINE_PIN_ISR(12) DEFINE_PIN_ISR(13)
#undef DEFINE_PIN_ISR

typedef void (*IsrFuncPtr)();
const IsrFuncPtr pinIsrTable[INTERRUPT_PIN_COUNT] = {
  isrPin0, isrPin1, isrPin2, isrPin3, isrPin4, isrPin5, isrPin6,
  isrPin7, isrPin8, isrPin9, isrPin10, isrPin11, isrPin12, isrPin13,
};

std::tuple<int, MsgPack::arr_t<int>> lvDigitalRead(MsgPack::arr_t<int> pins);
int lvDigitalWrite(MsgPack::arr_t<int> pins, MsgPack::arr_t<int> values);
int lvDigitalMode(MsgPack::arr_t<int> pins, MsgPack::arr_t<int> modes);
int lvLedCtrl(MsgPack::arr_t<int> leds, MsgPack::arr_t<int> states);
std::tuple<int, MsgPack::arr_t<int>> lvAnalogRead(MsgPack::arr_t<int> channels);
int lvPwmWrite(MsgPack::arr_t<int> pins, MsgPack::arr_t<float> duty);
std::tuple<int, uint32_t> lvPulseIn(uint8_t pin, uint8_t state, uint32_t timeout);
std::tuple<int, uint32_t> lvI2cOpen(uint8_t channel, uint32_t frequency);
int lvI2cWrite(uint8_t channel, uint8_t address, MsgPack::bin_t<uint8_t> data);
std::tuple<int, MsgPack::bin_t<uint8_t>> lvI2cRead(uint8_t channel, uint8_t address, uint16_t count);
int lvI2cClose(uint8_t channel);
std::tuple<int, uint32_t> lvSpiOpen(uint8_t channel, uint32_t frequency, uint8_t mode, bool msbFirst);
std::tuple<int, MsgPack::bin_t<uint8_t>> lvSpiTransfer(uint8_t channel, uint8_t chipSelect, MsgPack::bin_t<uint8_t> txData);
int lvSpiClose(uint8_t channel);
std::tuple<int, uint32_t> lvUartOpen(uint8_t channel, uint32_t baudRate);
std::tuple<int, uint32_t> lvUartAvailable(uint8_t channel);
std::tuple<int, MsgPack::bin_t<uint8_t>> lvUartRead(uint8_t channel, uint16_t count);
int lvUartWrite(uint8_t channel, MsgPack::bin_t<uint8_t> data);
int lvUartClose(uint8_t channel);
int lvInterruptAttach(uint8_t pin, uint8_t mode);
int lvInterruptDetach(uint8_t pin);
std::tuple<int, int, int, int, int, int, int> lvRtcGet();
int lvRtcSet(int year, int month, int day, int hour, int minute, int second);
int lvSystemSetIp(String ip);
int lvSystemRunning();

const uint8_t* glyph(char c) {
  static const uint8_t blank[] = {0, 0, 0, 0, 0};
  static const uint8_t digits[][5] = {
    {0x1E, 0x21, 0x21, 0x21, 0x1E}, {0x00, 0x22, 0x3F, 0x20, 0x00},
    {0x32, 0x29, 0x29, 0x29, 0x26}, {0x12, 0x21, 0x25, 0x25, 0x1A},
    {0x0C, 0x0A, 0x09, 0x3F, 0x08}, {0x17, 0x25, 0x25, 0x25, 0x19},
    {0x1E, 0x25, 0x25, 0x25, 0x18}, {0x01, 0x01, 0x31, 0x0D, 0x03},
    {0x1A, 0x25, 0x25, 0x25, 0x1A}, {0x06, 0x29, 0x29, 0x29, 0x1E}
  };
  static const uint8_t colon[] = {0, 0x0A, 0, 0x0A, 0};
  static const uint8_t dot[] = {0, 0, 0, 0x20, 0};
  static const uint8_t dash[] = {0, 0x08, 0x08, 0x08, 0};
  static const uint8_t i[] = {0, 0x21, 0x3F, 0x21, 0};
  static const uint8_t p[] = {0x3E, 0x09, 0x09, 0x09, 0x06};
  static const uint8_t o[] = {0x1E, 0x21, 0x21, 0x21, 0x1E};
  static const uint8_t k[] = {0x3F, 0x08, 0x14, 0x22, 0x01};
  static const uint8_t r[] = {0x3F, 0x09, 0x19, 0x29, 0x06};
  static const uint8_t u[] = {0x1F, 0x20, 0x20, 0x20, 0x1F};
  static const uint8_t n[] = {0x3F, 0x02, 0x0C, 0x10, 0x3F};
  if (c >= '0' && c <= '9') return digits[c - '0'];
  if (c == ':') return colon;
  if (c == '.') return dot;
  if (c == '-') return dash;
  if (c == 'I') return i;
  if (c == 'P') return p;
  if (c == 'O') return o;
  if (c == 'K') return k;
  if (c == 'R') return r;
  if (c == 'U') return u;
  if (c == 'N') return n;
  return blank;
}

void displayText(const String& text, bool resetOffset = true) {
  displayMessage = text;
  if (resetOffset) displayOffset = 0;
  uint32_t frame[4] = {0, 0, 0, 0};
  for (uint8_t column = 0; column < 13; ++column) {
    uint16_t source = displayOffset + column;
    uint8_t character = source / 6;
    uint8_t glyphColumn = source % 6;
    const uint8_t* bitmap = character < displayMessage.length() ? glyph(displayMessage[character]) : glyph(' ');
    for (uint8_t row = 0; row < 6; ++row) {
      if (glyphColumn < 5 && (bitmap[glyphColumn] & (1 << row))) {
        uint8_t pixel = row * 13 + column;
        frame[pixel / 32] |= (1UL << (31 - (pixel % 32)));
      }
    }
  }
  matrix.loadFrame(frame);
}

void apiV1Begin() {
  Monitor.begin(115200);
  Wire.begin();
  SPI.begin();
  rtc.begin();
  matrix.begin();
  displayText(displayMessage);

  pinMode(LED3_R, OUTPUT); digitalWrite(LED3_R, HIGH);
  pinMode(LED3_G, OUTPUT); digitalWrite(LED3_G, HIGH);
  pinMode(LED3_B, OUTPUT); digitalWrite(LED3_B, HIGH);
  pinMode(LED4_R, OUTPUT); digitalWrite(LED4_R, HIGH);
  pinMode(LED4_G, OUTPUT); digitalWrite(LED4_G, HIGH);
  pinMode(LED4_B, OUTPUT); digitalWrite(LED4_B, HIGH);

  Bridge.provide_safe("lv.digital.read", lvDigitalRead);
  Bridge.provide_safe("lv.digital.write", lvDigitalWrite);
  Bridge.provide_safe("lv.digital.mode", lvDigitalMode);
  Bridge.provide_safe("lv.led.ctrl", lvLedCtrl);
  Bridge.provide_safe("lv.analog.read", lvAnalogRead);
  Bridge.provide_safe("lv.pwm.write", lvPwmWrite);
  Bridge.provide_safe("lv.pulse.in", lvPulseIn);
  Bridge.provide_safe("lv.i2c.open", lvI2cOpen);
  Bridge.provide_safe("lv.i2c.write", lvI2cWrite);
  Bridge.provide_safe("lv.i2c.read", lvI2cRead);
  Bridge.provide_safe("lv.i2c.close", lvI2cClose);
  Bridge.provide_safe("lv.spi.open", lvSpiOpen);
  Bridge.provide_safe("lv.spi.transfer", lvSpiTransfer);
  Bridge.provide_safe("lv.spi.close", lvSpiClose);
  Bridge.provide_safe("lv.uart.open", lvUartOpen);
  Bridge.provide_safe("lv.uart.available", lvUartAvailable);
  Bridge.provide_safe("lv.uart.read", lvUartRead);
  Bridge.provide_safe("lv.uart.write", lvUartWrite);
  Bridge.provide_safe("lv.uart.close", lvUartClose);
  Bridge.provide_safe("lv.interrupt.attach", lvInterruptAttach);
  Bridge.provide_safe("lv.interrupt.detach", lvInterruptDetach);
  Bridge.provide_safe("lv.rtc.get", lvRtcGet);
  Bridge.provide_safe("lv.rtc.set", lvRtcSet);
  Bridge.provide_safe("lv.system.set.ip", lvSystemSetIp);
  Bridge.provide_safe("lv.system.running", lvSystemRunning);
}

void apiV1Poll() {
  if (deviceState == STATE_BOOTING && millis() >= nextBootDisplay) {
    displayText(displayMessage, false);
    displayOffset = (displayOffset + 1) % (displayMessage.length() * 6 + 13);
    nextBootDisplay = millis() + 250;
  } else if (deviceState == STATE_RUNNING && displayNeedsUpdate) {
    displayText("OK");
    displayNeedsUpdate = false;
  }

  // Deferred from the ISRs: Bridge.notify() takes a Zephyr mutex and can
  // yield, which is only valid from thread context (apiV1Poll() is called
  // from loop(), which runs as a thread here), never from the real
  // interrupt context attachInterrupt() callbacks run in on this core.
  for (uint8_t pin = 0; pin < INTERRUPT_PIN_COUNT; ++pin) {
    if (atomic_test_and_clear_bit(&pendingInterruptMask, pin)) {
      Bridge.notify("lv.interrupt.fired", pin, static_cast<int>(digitalRead(pin)));
    }
  }
}

std::tuple<int, MsgPack::arr_t<int>> lvDigitalRead(MsgPack::arr_t<int> pins) {
  MsgPack::arr_t<int> values;
  values.reserve(pins.size());
  for (int pin : pins) {
    if (!validDigitalPin(pin)) return std::make_tuple(STATUS_INVALID_ARGUMENT, values);
    values.push_back(digitalRead(pin));
  }
  return std::make_tuple(STATUS_OK, values);
}

int lvDigitalWrite(MsgPack::arr_t<int> pins, MsgPack::arr_t<int> values) {
  if (pins.size() != values.size()) return STATUS_INVALID_ARGUMENT;
  for (size_t i = 0; i < pins.size(); ++i) {
    if (!validDigitalPin(pins[i])) return STATUS_INVALID_ARGUMENT;
  }
  for (size_t i = 0; i < pins.size(); ++i) digitalWrite(pins[i], values[i] ? HIGH : LOW);
  return STATUS_OK;
}

int lvDigitalMode(MsgPack::arr_t<int> pins, MsgPack::arr_t<int> modes) {
  if (pins.size() != modes.size()) return STATUS_INVALID_ARGUMENT;
  for (size_t i = 0; i < pins.size(); ++i) {
    if (!validDigitalPin(pins[i])) return STATUS_INVALID_ARGUMENT;
  }
  for (size_t i = 0; i < pins.size(); ++i) pinMode(pins[i], modes[i] ? OUTPUT : INPUT);
  return STATUS_OK;
}

int lvLedCtrl(MsgPack::arr_t<int> leds, MsgPack::arr_t<int> states) {
  if (leds.size() != states.size()) return STATUS_INVALID_ARGUMENT;
  for (size_t i = 0; i < leds.size(); ++i) {
    if (!validLedPin(leds[i])) return STATUS_INVALID_ARGUMENT;
  }
  for (size_t i = 0; i < leds.size(); ++i) {
    pinMode(leds[i], OUTPUT);
    digitalWrite(leds[i], states[i] ? HIGH : LOW);
  }
  return STATUS_OK;
}

std::tuple<int, MsgPack::arr_t<int>> lvAnalogRead(MsgPack::arr_t<int> channels) {
  MsgPack::arr_t<int> values;
  values.reserve(channels.size());
  for (int channel : channels) {
    if (channel < 0 || channel > 5) {
      return std::make_tuple(STATUS_INVALID_ARGUMENT, values);
    }
    values.push_back(analogRead(A0 + channel));
  }
  return std::make_tuple(STATUS_OK, values);
}

int lvPwmWrite(MsgPack::arr_t<int> pins, MsgPack::arr_t<float> duty) {
  if (pins.size() != duty.size()) return STATUS_INVALID_ARGUMENT;
  for (size_t i = 0; i < pins.size(); ++i) {
    if (!validPwmPin(pins[i]) || duty[i] < 0.0f || duty[i] > 1.0f) return STATUS_INVALID_ARGUMENT;
  }
  for (size_t i = 0; i < pins.size(); ++i) {
    analogWrite(pins[i], static_cast<int>(duty[i] * 255.0f + 0.5f));
  }
  return STATUS_OK;
}

std::tuple<int, uint32_t> lvPulseIn(uint8_t pin, uint8_t state, uint32_t timeout) {
  if (!validDigitalPin(pin) || timeout == 0) return std::make_tuple(STATUS_INVALID_ARGUMENT, 0U);
  pinMode(pin, INPUT);
  return std::make_tuple(STATUS_OK, pulseIn(pin, state ? HIGH : LOW, timeout));
}

std::tuple<int, uint32_t> lvI2cOpen(uint8_t channel, uint32_t frequency) {
  if (channel != I2C_CHANNEL || frequency == 0 || frequency > 1000000UL) {
    return std::make_tuple(STATUS_INVALID_ARGUMENT, 0U);
  }
  Wire.setClock(frequency);
  i2cOpen = true;
  return std::make_tuple(STATUS_OK, frequency);
}

int lvI2cWrite(uint8_t channel, uint8_t address, MsgPack::bin_t<uint8_t> data) {
  if (channel != I2C_CHANNEL || !i2cOpen || !validI2cAddress(address) ||
      data.size() == 0 || data.size() > I2C_MAX_TRANSFER) {
    return STATUS_INVALID_ARGUMENT;
  }
  Wire.beginTransmission(address);
  for (uint8_t value : data) Wire.write(value);
  return Wire.endTransmission() == 0 ? STATUS_OK : STATUS_INVALID_ARGUMENT;
}

std::tuple<int, MsgPack::bin_t<uint8_t>> lvI2cRead(uint8_t channel, uint8_t address, uint16_t count) {
  MsgPack::arr_t<uint8_t> values;
  if (channel != I2C_CHANNEL || !i2cOpen || !validI2cAddress(address) ||
      count == 0 || count > I2C_MAX_TRANSFER) {
    return std::make_tuple(STATUS_INVALID_ARGUMENT, values);
  }
  uint8_t received = Wire.requestFrom(static_cast<uint8_t>(address), static_cast<uint8_t>(count));
  values.reserve(received);
  while (Wire.available() > 0) values.push_back(Wire.read());
  if (received != count) return std::make_tuple(STATUS_INVALID_ARGUMENT, values);
  return std::make_tuple(STATUS_OK, values);
}

int lvI2cClose(uint8_t channel) {
  if (channel != I2C_CHANNEL || !i2cOpen) return STATUS_INVALID_ARGUMENT;
  i2cOpen = false;
  return STATUS_OK;
}

std::tuple<int, uint32_t> lvSpiOpen(uint8_t channel, uint32_t frequency, uint8_t mode, bool msbFirst) {
  if (channel != SPI_CHANNEL || frequency == 0 || mode > 3) {
    return std::make_tuple(STATUS_INVALID_ARGUMENT, 0U);
  }
  spiSettings = SPISettings(frequency, msbFirst ? MSBFIRST : LSBFIRST, mode);
  spiOpen = true;
  return std::make_tuple(STATUS_OK, frequency);
}

std::tuple<int, MsgPack::bin_t<uint8_t>> lvSpiTransfer(uint8_t channel, uint8_t chipSelect, MsgPack::bin_t<uint8_t> txData) {
  MsgPack::arr_t<uint8_t> rxData;
  if (channel != SPI_CHANNEL || !spiOpen || !validSpiChipSelectPin(chipSelect) || txData.size() == 0) {
    return std::make_tuple(STATUS_INVALID_ARGUMENT, rxData);
  }
  rxData.reserve(txData.size());
  pinMode(chipSelect, OUTPUT);
  digitalWrite(chipSelect, HIGH);
  SPI.beginTransaction(spiSettings);
  digitalWrite(chipSelect, LOW);
  for (uint8_t value : txData) rxData.push_back(SPI.transfer(value));
  digitalWrite(chipSelect, HIGH);
  SPI.endTransaction();
  return std::make_tuple(STATUS_OK, rxData);
}

int lvSpiClose(uint8_t channel) {
  if (channel != SPI_CHANNEL || !spiOpen) return STATUS_INVALID_ARGUMENT;
  spiOpen = false;
  return STATUS_OK;
}

std::tuple<int, uint32_t> lvUartOpen(uint8_t channel, uint32_t baudRate) {
  if (channel != UART_CHANNEL || baudRate == 0) return std::make_tuple(STATUS_INVALID_ARGUMENT, 0U);
  Serial1.begin(baudRate);
  return std::make_tuple(STATUS_OK, baudRate);
}

std::tuple<int, uint32_t> lvUartAvailable(uint8_t channel) {
  if (channel != UART_CHANNEL) return std::make_tuple(STATUS_INVALID_ARGUMENT, 0U);
  return std::make_tuple(STATUS_OK, static_cast<uint32_t>(Serial1.available()));
}

std::tuple<int, MsgPack::bin_t<uint8_t>> lvUartRead(uint8_t channel, uint16_t count) {
  MsgPack::arr_t<uint8_t> values;
  if (channel != UART_CHANNEL) return std::make_tuple(STATUS_INVALID_ARGUMENT, values);
  values.reserve(count);
  while (Serial1.available() > 0 && values.size() < count) {
    values.push_back(static_cast<uint8_t>(Serial1.read()));
  }
  return std::make_tuple(STATUS_OK, values);
}

int lvUartWrite(uint8_t channel, MsgPack::bin_t<uint8_t> data) {
  if (channel != UART_CHANNEL) return STATUS_INVALID_ARGUMENT;
  for (uint8_t byte : data) Serial1.write(byte);
  return STATUS_OK;
}

int lvUartClose(uint8_t channel) {
  if (channel != UART_CHANNEL) return STATUS_INVALID_ARGUMENT;
  Serial1.flush();
  Serial1.end();
  return STATUS_OK;
}

int lvInterruptAttach(uint8_t pin, uint8_t mode) {
  // mode matches Arduino's PinStatus values directly: LOW=0, HIGH=1,
  // CHANGE=2, FALLING=3, RISING=4.
  if (!validDigitalPin(pin) || mode > RISING) return STATUS_INVALID_ARGUMENT;
  pinMode(pin, INPUT);
  atomic_clear_bit(&pendingInterruptMask, pin);
  attachInterrupt(digitalPinToInterrupt(pin), pinIsrTable[pin], static_cast<PinStatus>(mode));
  return STATUS_OK;
}

int lvInterruptDetach(uint8_t pin) {
  if (!validDigitalPin(pin)) return STATUS_INVALID_ARGUMENT;
  detachInterrupt(digitalPinToInterrupt(pin));
  atomic_clear_bit(&pendingInterruptMask, pin);
  return STATUS_OK;
}

std::tuple<int, int, int, int, int, int, int> lvRtcGet() {
  int year, month, day, hour, minute, second;
  if (rtc.getTime(year, month, day, hour, minute, second) != 0) {
    return std::make_tuple(STATUS_INVALID_ARGUMENT, 0, 0, 0, 0, 0, 0);
  }
  return std::make_tuple(STATUS_OK, year, month, day, hour, minute, second);
}

int lvRtcSet(int year, int month, int day, int hour, int minute, int second) {
  if (!validRtcDateTime(year, month, day, hour, minute, second)) return STATUS_INVALID_ARGUMENT;
  return rtc.setTime(year, month, day, hour, minute, second) == 0 ? STATUS_OK : STATUS_INVALID_ARGUMENT;
}

int lvSystemSetIp(String ip) {
  if (ip.length() == 0 || ip.length() > 64) return STATUS_INVALID_ARGUMENT;
  displayMessage = "IP " + ip;
  displayOffset = 0;
  nextBootDisplay = 0;
  return STATUS_OK;
}

int lvSystemRunning() {
  deviceState = STATE_RUNNING;
  displayNeedsUpdate = true;
  return STATUS_OK;
}
