#include <Wire.h>
#include <SPI.h>

// -----------------------------------------------------------------------------
// Digital I/O
// -----------------------------------------------------------------------------

std::tuple<int, MsgPack::arr_t<int>>
lvDigitalRead(
    MsgPack::arr_t<int> pins
);

int lvDigitalWrite(
    MsgPack::arr_t<int> pins,
    MsgPack::arr_t<int> values
);

int lvDigitalMode(
    MsgPack::arr_t<int> pins,
    MsgPack::arr_t<int> modes
);


// -----------------------------------------------------------------------------
// LED control
// -----------------------------------------------------------------------------

int lvLedCtrl(
  MsgPack::arr_t<int> leds,
  MsgPack::arr_t<int> states
);

// -----------------------------------------------------------------------------
// Analog Input
// -----------------------------------------------------------------------------

std::tuple<int, MsgPack::arr_t<int>>
lvAnalogRead(
    MsgPack::arr_t<int> channels
);


// -----------------------------------------------------------------------------
// PWM
// -----------------------------------------------------------------------------

int lvPwmWrite(
    MsgPack::arr_t<int> pins,
    MsgPack::arr_t<float> duty
);


// -----------------------------------------------------------------------------
// I2C
// -----------------------------------------------------------------------------

std::tuple<int, uint32_t>
lvI2cOpen(
    uint8_t channel,
    uint32_t frequency
);

int lvI2cWrite(
    uint8_t channel,
    uint8_t address,
    MsgPack::bin_t<uint8_t> data
);

std::tuple<int, MsgPack::bin_t<uint8_t>>
lvI2cRead(
    uint8_t channel,
    uint8_t address,
    uint16_t count
);

int lvI2cClose(
    uint8_t channel
);


// -----------------------------------------------------------------------------
// SPI
// -----------------------------------------------------------------------------

std::tuple<int, uint32_t>
lvSpiOpen(
    uint8_t channel,
    uint32_t frequency,
    uint8_t mode,
    bool msbFirst
);

std::tuple<int, MsgPack::bin_t<uint8_t>>
lvSpiTransfer(
    uint8_t channel,
    uint8_t chipSelect,
    MsgPack::bin_t<uint8_t> txData
);

int lvSpiClose(
    uint8_t channel
);


// -----------------------------------------------------------------------------
// UART
// -----------------------------------------------------------------------------

std::tuple<int, uint32_t>
lvUartOpen(
    uint8_t channel,
    uint32_t baudRate
);

std::tuple<int, uint32_t>
lvUartAvailable(
    uint8_t channel
);

std::tuple<int, MsgPack::bin_t<uint8_t>>
lvUartRead(
    uint8_t channel,
    uint16_t count
);

int lvUartWrite(
    uint8_t channel,
    MsgPack::bin_t<uint8_t> data
);

int lvUartClose(
    uint8_t channel
);


void setup() {
  Bridge.begin();
  Monitor.begin(115200);

  // Digital I/O
  Bridge.provide_safe("lv.digital.read",  lvDigitalRead);
  Bridge.provide_safe("lv.digital.write", lvDigitalWrite);
  Bridge.provide_safe("lv.digital.mode",  lvDigitalMode);
  Bridge.provide_safe("lv.led.ctrl",  lvLedCtrl);

  // Analog / PWM
  Bridge.provide_safe("lv.analog.read", lvAnalogRead);
  Bridge.provide_safe("lv.pwm.write",   lvPwmWrite);

  // I2C
  Bridge.provide_safe("lv.i2c.open",  lvI2cOpen);
  Bridge.provide_safe("lv.i2c.write", lvI2cWrite);
  Bridge.provide_safe("lv.i2c.read",  lvI2cRead);
  Bridge.provide_safe("lv.i2c.close", lvI2cClose);

  // SPI
  Bridge.provide_safe("lv.spi.open",     lvSpiOpen);
  Bridge.provide_safe("lv.spi.transfer", lvSpiTransfer);
  Bridge.provide_safe("lv.spi.close",    lvSpiClose);

  // UART
  Bridge.provide_safe("lv.uart.open",      lvUartOpen);
  Bridge.provide_safe("lv.uart.available", lvUartAvailable);
  Bridge.provide_safe("lv.uart.read",      lvUartRead);
  Bridge.provide_safe("lv.uart.write",     lvUartWrite);
  Bridge.provide_safe("lv.uart.close",     lvUartClose);
}

void loop() {
  delay(1000);
}

// -----------------------------------------------------------------------------
// Digital I/O
// -----------------------------------------------------------------------------

std::tuple<int, MsgPack::arr_t<int>> lvDigitalRead(MsgPack::arr_t<int> pins) {
  MsgPack::arr_t<int> values;

  values.reserve(pins.size());
  for (int pin : pins) {
    int value = digitalRead(pin);
    values.push_back(value);
  }

  return std::make_tuple(0, values);  
}

int lvDigitalWrite(MsgPack::arr_t<int> pins, MsgPack::arr_t<int> values) {

  for (int i=0; i < pins.size(); i++) {
    digitalWrite(pins[i], values[i] ? HIGH : LOW);
  }
  return 0;
}

int lvDigitalMode(MsgPack::arr_t<int> pins, MsgPack::arr_t<int> modes) {

  for (int i=0; i < pins.size(); i++) {
    pinMode(pins[i], modes[i] ? OUTPUT : INPUT);
  }
  return 0;
}

int lvLedCtrl(MsgPack::arr_t<int> leds, MsgPack::arr_t<int> states) {
  
  for (int i=0; i < leds.size(); i++) {
    pinMode(leds[i], OUTPUT);
    digitalWrite(leds[i], states[i] ? HIGH : LOW);
  }
  return 0;
}

// -----------------------------------------------------------------------------
// Analog Input
// -----------------------------------------------------------------------------

std::tuple<int, MsgPack::arr_t<int>> lvAnalogRead(MsgPack::arr_t<int> channels) {
  MsgPack::arr_t<int> values;
  
  return std::make_tuple(0, values);  
}


// -----------------------------------------------------------------------------
// PWM
// -----------------------------------------------------------------------------

int lvPwmWrite(MsgPack::arr_t<int> pins, MsgPack::arr_t<float> duty) {
  return 0;
}


// -----------------------------------------------------------------------------
// I2C
// -----------------------------------------------------------------------------

std::tuple<int, uint32_t> lvI2cOpen(uint8_t channel, uint32_t frequency) {
  return std::make_tuple(0, 0);  
}

int lvI2cWrite(uint8_t channel, uint8_t address, MsgPack::bin_t<uint8_t> data) {
  return 0;
}

std::tuple<int, MsgPack::bin_t<uint8_t>> lvI2cRead(uint8_t channel, uint8_t address, uint16_t count) {
  MsgPack::arr_t<uint8_t> values;

  return std::make_tuple(0, values);  
}

int lvI2cClose(uint8_t channel) {
  return 0;
}


// -----------------------------------------------------------------------------
// SPI
// -----------------------------------------------------------------------------

std::tuple<int, uint32_t> lvSpiOpen(uint8_t channel, uint32_t frequency, uint8_t mode, bool msbFirst) {
  return std::make_tuple(0, 0);  
}

std::tuple<int, MsgPack::bin_t<uint8_t>> lvSpiTransfer(uint8_t channel, uint8_t chipSelect, MsgPack::bin_t<uint8_t> txData) {
  MsgPack::arr_t<uint8_t> values;

  return std::make_tuple(0, values);  
}

int lvSpiClose(uint8_t channel) {
  return 0;
}


// -----------------------------------------------------------------------------
// UART
// -----------------------------------------------------------------------------

std::tuple<int, uint32_t> lvUartOpen(uint8_t channel, uint32_t baudRate) {

  return std::make_tuple(0, 0); 
}

std::tuple<int, uint32_t> lvUartAvailable(uint8_t channel) {

  return std::make_tuple(0, 0); 
}

std::tuple<int, MsgPack::bin_t<uint8_t>> lvUartRead(uint8_t channel, uint16_t count) {
  MsgPack::arr_t<uint8_t> values;

  return std::make_tuple(0, values); 
}

int lvUartWrite(uint8_t channel, MsgPack::bin_t<uint8_t> data) {
  return 0;
}

int lvUartClose(uint8_t channel) {
  return 0;
}
