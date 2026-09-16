#include <Arduino_RouterBridge.h>

#include "api_v1.h"
#include "api_v2.h"

void setup() {
  Bridge.begin();
  apiV1Begin();
  apiV2Begin();
}

void loop() {
  apiV1Poll();
  delay(20);
}
