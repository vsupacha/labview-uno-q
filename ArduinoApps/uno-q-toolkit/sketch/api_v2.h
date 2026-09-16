#pragma once

// Starts the DAQ sampling thread and registers the lv.daq.* RPC handlers.
// Call once from setup(), after Bridge.begin().
void apiV2Begin();
