# Capstone project handoff rules

Read the relevant README in Gesture/, Auto Driving/With Steering/ or
Auto Driving/Without Steering/. See docs/repository-map.md for old path mappings.

The wiring in `Auto Driving/Without Steering/legacy_rover/motor_module.py` is authoritative for that old robot. Never
change its GPIO pin pairs, motor ordering, or forward/backward polarity unless
the user explicitly supplies new physical wiring information and requests it.
Shared gesture code and models live only in Gesture/. Keep PC and Flask callers
compatible with that implementation. Keep simulation adapters separate from
physical hardware code. Historical instructions do not authorize hardware runs.

On a new PC, inspect the environment first and help the user install missing
Git, GitHub CLI, Python dependencies, and Webots. Verify one Webots world before
starting a long dataset run. Dataset images under `Auto Driving/Without Steering/simulation/dataset/runs`
are intentionally not tracked by Git and must be preserved from this archive.
