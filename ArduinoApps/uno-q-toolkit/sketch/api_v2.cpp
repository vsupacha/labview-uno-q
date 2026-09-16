#include "api_v2.h"

#include "api_v1.h" // STATUS_OK / STATUS_INVALID_ARGUMENT / validDigitalPin()

#include <Arduino_RouterBridge.h>
#include <MsgPack.h>
#include <zephyr/kernel.h>

constexpr uint8_t DAQ_ANALOG_CHANNEL_MAX = 5;
constexpr uint8_t DAQ_MAX_CHANNELS = 8;
// Sized to stay comfortably under the ~256-byte Arduino_RPClite RPC frame
// budget (DECODER_BUFFER_SIZE / 4) once MsgPack overhead is accounted for.
constexpr size_t DAQ_CHUNK_MAX_VALUES = 32;
constexpr size_t DAQ_THREAD_STACK_SIZE = 1024;
constexpr int DAQ_THREAD_PRIORITY = 7; // lower priority than the bridge's own update thread (5)

enum DaqChannelType : uint8_t {
  DAQ_CHANNEL_DIGITAL = 0,
  DAQ_CHANNEL_ANALOG = 1,
};

bool validDaqChannels(const MsgPack::arr_t<int>& pins, const MsgPack::arr_t<int>& types) {
  if (pins.size() != types.size() || pins.size() == 0 || pins.size() > DAQ_MAX_CHANNELS) return false;
  for (size_t i = 0; i < pins.size(); ++i) {
    if (types[i] == DAQ_CHANNEL_DIGITAL) {
      if (!validDigitalPin(pins[i])) return false;
    } else if (types[i] == DAQ_CHANNEL_ANALOG) {
      if (pins[i] < 0 || pins[i] > DAQ_ANALOG_CHANNEL_MAX) return false;
    } else {
      return false;
    }
  }
  return true;
}

struct DaqConfig {
  uint8_t channelCount = 0;
  uint8_t pins[DAQ_MAX_CHANNELS] = {};
  uint8_t types[DAQ_MAX_CHANNELS] = {};
  uint32_t intervalMicros = 0;
  uint32_t sampleCount = 0; // 0 means continuous
};

DaqConfig daqConfig;
volatile bool daqRunning = false;
volatile bool daqStopRequested = false;
struct k_thread daqThreadData;
K_SEM_DEFINE(daqStartSem, 0, 1);

// Runs on its own low-priority thread rather than loop(), since analogRead()
// on this core blocks on the ADC driver (adc_channel_setup + adc_read) and
// is not ISR-safe, and would otherwise fight loop()'s own display/interrupt
// duties for CPU time. Sampling here is a best-effort k_usleep() spaced
// loop, not a hardware timer: analogRead()'s own per-call setup overhead
// bounds the realistically achievable rate well below intervalMicros=0-class
// figures, especially with multiple channels configured.
void daqThreadEntry(void*, void*, void*) {
  while (true) {
    k_sem_take(&daqStartSem, K_FOREVER);

    const size_t slicesPerChunk = DAQ_CHUNK_MAX_VALUES / daqConfig.channelCount;
    int chunkValues[DAQ_CHUNK_MAX_VALUES];
    size_t chunkSlices = 0;
    uint32_t sampleIndex = 0;
    uint32_t chunkStartIndex = 0;

    auto flushChunk = [&]() {
      if (chunkSlices == 0) return;
      MsgPack::arr_t<int> values;
      values.reserve(chunkSlices * daqConfig.channelCount);
      for (size_t i = 0; i < chunkSlices * daqConfig.channelCount; ++i) {
        values.push_back(chunkValues[i]);
      }
      Bridge.notify("lv.daq.chunk", chunkStartIndex, values);
      chunkSlices = 0;
      chunkStartIndex = sampleIndex;
    };

    while (daqRunning && !daqStopRequested &&
           (daqConfig.sampleCount == 0 || sampleIndex < daqConfig.sampleCount)) {
      for (uint8_t ch = 0; ch < daqConfig.channelCount; ++ch) {
        chunkValues[chunkSlices * daqConfig.channelCount + ch] =
            (daqConfig.types[ch] == DAQ_CHANNEL_ANALOG)
                ? analogRead(A0 + daqConfig.pins[ch])
                : digitalRead(daqConfig.pins[ch]);
      }
      ++chunkSlices;
      ++sampleIndex;

      if (chunkSlices >= slicesPerChunk) flushChunk();

      k_usleep(daqConfig.intervalMicros);
    }

    flushChunk();
    Bridge.notify("lv.daq.done");
    daqRunning = false;
    daqStopRequested = false;
  }
}

int lvDaqStart(MsgPack::arr_t<int> pins, MsgPack::arr_t<int> types, uint32_t intervalMicros, uint32_t sampleCount) {
  if (daqRunning) return STATUS_INVALID_ARGUMENT;
  if (!validDaqChannels(pins, types) || intervalMicros == 0) return STATUS_INVALID_ARGUMENT;

  daqConfig.channelCount = pins.size();
  for (size_t i = 0; i < pins.size(); ++i) {
    daqConfig.pins[i] = pins[i];
    daqConfig.types[i] = types[i];
    if (types[i] == DAQ_CHANNEL_DIGITAL) pinMode(pins[i], INPUT);
  }
  daqConfig.intervalMicros = intervalMicros;
  daqConfig.sampleCount = sampleCount;

  daqStopRequested = false;
  daqRunning = true;
  k_sem_give(&daqStartSem);
  return STATUS_OK;
}

int lvDaqStop() {
  if (!daqRunning) return STATUS_INVALID_ARGUMENT;
  daqStopRequested = true;
  return STATUS_OK;
}

void apiV2Begin() {
  k_thread_stack_t* daqStack = k_thread_stack_alloc(DAQ_THREAD_STACK_SIZE, 0);
  k_thread_create(&daqThreadData, daqStack, DAQ_THREAD_STACK_SIZE,
                  daqThreadEntry, NULL, NULL, NULL,
                  DAQ_THREAD_PRIORITY, 0, K_NO_WAIT);
  k_thread_name_set(&daqThreadData, "daq");

  Bridge.provide_safe("lv.daq.start", lvDaqStart);
  Bridge.provide_safe("lv.daq.stop", lvDaqStop);
}
