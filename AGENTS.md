# Capstone project handoff rules

Read `Dataset Project/HANDOFF.md` before changing or running this project.

The existing hardware wiring in `Lee/motor_module.py` is authoritative. Never
change its GPIO pin pairs, motor ordering, or forward/backward polarity unless
the user explicitly supplies new physical wiring information and requests it.
Do not modify the existing Lee camera/gesture code as part of autonomous-driving
dataset work. Keep simulation adapters separate from physical hardware code.

On a new PC, inspect the environment first and help the user install missing
Git, GitHub CLI, Python dependencies, and Webots. Verify one Webots world before
starting a long dataset run. Dataset images under `Dataset Project/dataset/runs`
are intentionally not tracked by Git and must be preserved from this archive.
