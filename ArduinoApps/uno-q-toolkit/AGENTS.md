# Repository Guidelines

## Project Structure & Module Organization

- `sketch/sketch.ino` is only `setup()`/`loop()`; it delegates to `apiV1Begin()`/`apiV1Poll()`/`apiV2Begin()`.
- `sketch/api_v1.h` / `sketch/api_v1.cpp` contain the `api/v1` (Arduino-style) RPC handlers, and the shared `STATUS_*` codes / `validDigitalPin()` that `api/v2` also depends on.
- `sketch/api_v2.h` / `sketch/api_v2.cpp` contain the `api/v2` DAQ RPC handlers and its dedicated sampling thread. New peripherals go in whichever of `api_v1`/`api_v2` matches their API version, not back into `sketch.ino`.
- `sketch/sketch.yaml` declares the Arduino Zephyr platform and sketch dependencies.
- `app.yaml` is the App Lab descriptor; `python/main.py` is the Linux-side entry point.
- `gateway/app.py` contains the Debian-side `WebUI` Brick REST gateway. Keep peripheral behavior in firmware; the gateway should validate JSON and forward RPC calls.
- `gateway/requirements.txt` records that HTTP serving is supplied by the App Lab Brick.
- `README.md` documents this app's scope and architecture for LabVIEW/App Lab users. It intentionally does **not** cover the CLI automation below — this file and `skills.md` are the authoritative references for that.
- `../../tests/test_gateway.py` (repo root `tests/`) contains gateway unit tests (mocked `Bridge`, no hardware required); it imports `gateway/app.py` from here.
- `../../tests/test_hardware.py` contains opt-in tests against a real UNO Q fitted with a Keyestudio Multi-purpose Shield V2; `../../tests/conftest.py` adds the `--uno-q-url` option they share with `uno_q.py`.
- `../../tests/test_uno_q_runner.py` unit-tests `../../tools/uno_q.py` itself, no hardware required.
- `../../tools/uno_q.py` is the automated check/deploy/run/stop/clean/test runner; `../../tools/test_rpc_milestone1.ps1` and `../../tools/blink_led3.sh` are supplementary REST smoke-test scripts. These live at the repo root because they are development tooling, not part of the deployed app.
- `../../skills.md` (repo root) is the full build/deploy/test runbook: host setup, ADB authorization, the shield fixture, and troubleshooting. Read it before changing any of the files above it in this list.

## Build, Test, and Development Commands

From this directory (`ArduinoApps/uno-q-toolkit`), for app-local checks:

```text
python -m py_compile gateway\app.py
```

From the repository root, for tests, the automated runner, and the smoke script:

```text
python -m pytest -q
python tools\uno_q.py check
python tools\uno_q.py all
.\tools\test_rpc_milestone1.ps1 -ForwardAdbPort -ConfirmA0Below3V3
```

`pytest -q` runs the gateway and runner unit tests, no hardware needed. `uno_q.py check` validates the app's source files (readable, non-empty, valid Python syntax) without a board. `uno_q.py all` is the full interactive build/deploy/run/test sequence against a real, USB-connected UNO Q fitted with a Keyestudio Multi-purpose Shield V2 — see `skills.md` (repo root) before running it the first time on a new machine; it covers host prerequisites, ADB authorization, and the shield wiring/safety notes (`-ConfirmA0Below3V3` and `UNO_Q_SHIELD_A0_SAFE=1` both confirm the A0 potentiometer signal was manually limited below 3.3 V, which software cannot verify itself). Firmware compilation and deployment happen through App Lab during `uno_q.py run`, or manually:

```bash
arduino-app-cli app start user:uno-q-toolkit
arduino-app-cli app logs user:uno-q-toolkit --follow
```

## CLI Robustness Notes

`tools/uno_q.py` is the only supported way to drive build/deploy/test from a script or CI; treat these as invariants when changing it, and as the first things to check when a run misbehaves:

- **Exactly-one-device requirement.** `select_device()` refuses to proceed unless exactly one ADB device is in `device` state, or `--serial SERIAL` names one explicitly. `Need one authorized device or --serial; found {...}` means either zero devices, more than one, or one that's `unauthorized`/`offline` — the fix is always `--serial`, not retrying.
- **Ephemeral ADB forwarding.** `Board.connect()` uses `adb forward tcp:0 tcp:7000` (port `0` = let ADB pick a free port), never a fixed port — it cannot clobber a forward LabVIEW or another session already has open. Every code path (`test`, `pytest_board`, top-level `main`) removes its own forward in a `finally` block, including on `KeyboardInterrupt`. If a run is killed hard enough to skip that (e.g., the process itself is killed, not just interrupted), a stale forward can remain — `adb forward --list` shows it, `adb forward --remove tcp:<port>` clears it; it does not affect a subsequent run, which allocates its own new port.
- **Hardware env vars are scoped per-subprocess, not inherited.** `run()` always pops `UNO_Q_HARDWARE`/`UNO_Q_SHIELD_A0_SAFE` from the environment first, then re-adds both only when `hardware=True`. This is deliberate: it stops a stray exported env var from silently making an unrelated `pytest -q` invocation try to run hardware tests.
- **Shield cleanup runs even on failure, but can itself fail.** `Board.test()`'s cleanup is in a `finally` block and always attempts every cleanup POST even if an earlier one raised; if cleanup itself fails when the test body didn't, that failure is re-raised (rather than silently swallowed) so a half-reset shield state is never mistaken for a clean pass.
- **`deploy` is safe to interrupt and re-run.** Each source file is pushed independently (no transaction); an interrupted deploy leaves some files updated and some not, but a subsequent `deploy` overwrites all of them again from the same local sources — there's no partial-state cleanup step because none is needed.
- **`run`/`stop` never silently deploy the wrong app.** `--app APP_ID` only affects an already-installed app; if it's absent, both fail with an explicit error rather than deploying over it. Only the no-`--app` default path (the project's own app) auto-deploys when absent.

See `skills.md` (repo root) for host-level troubleshooting (ADB permissions, sandboxed vs. host execution, driver issues) that lives below the CLI itself.

## Coding Style & Naming Conventions

Use four spaces for Python indentation and `snake_case` for Python functions and variables. Use C++ two-space indentation, `PascalCase` only for library types, and `camelCase` for firmware helpers. RPC names use lowercase dotted paths such as `lv.digital.write`. Keep status-only callbacks returning `int`; read callbacks return `std::tuple<int, T>`.

Prefer clear validation helpers over duplicated checks. Preserve explicit status codes: `0` means success, `-1` invalid input, and `-2` not implemented (no RPC currently uses `-2`; keep it available for future peripherals). Run `pytest` after Python changes.

## Testing Guidelines

Tests use `pytest` and are located under the repo root `tests/` (not under this folder). Name files `test_*.py` and test functions `test_<behavior>`. Add coverage for malformed JSON, mismatched parallel arrays, invalid pins, Bridge exceptions, and active-low LED mapping. Hardware-dependent behavior should be tested on a connected UNO Q, not mocked as successful — against the Keyestudio Multi-purpose Shield V2 fixture `tests/test_hardware.py` already assumes (LEDs D8–D13, 74HC595 display pins D2/D4/D5, potentiometer A0, switches A1–A3, buzzer D3). From the repo root, both env vars are required — `UNO_Q_SHIELD_A0_SAFE=1` is a manual confirmation that A0 was limited below 3.3 V, since software cannot verify that itself:

```powershell
$env:UNO_Q_HARDWARE = "1"
$env:UNO_Q_SHIELD_A0_SAFE = "1"
python -m pytest tests\test_hardware.py -q
```

Prefer `python tools\uno_q.py test --hardware` over calling pytest directly for a full hardware run: it also handles ADB port-forwarding, starts the app if needed, and cleans up shield outputs afterward. New DAQ (`api/v2`) test coverage should not assume the WebSocket data channel or one-shot completion have been verified yet — see the caveat in `README.md`'s DAQ section.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects, for example `Validate digital RPC pin ranges`. Pull requests should describe the firmware and gateway impact, list verification commands and results, identify any required UNO Q/App Lab version, and include serial or App Lab logs when hardware behavior changes.

## Security & Configuration Tips

The REST gateway is currently unauthenticated and should remain on a trusted interface only. Add authentication and network restrictions before exposing it beyond a trusted LAN. Never commit credentials, board passwords, or generated App Lab caches.
