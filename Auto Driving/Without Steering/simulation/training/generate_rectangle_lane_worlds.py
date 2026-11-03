"""Generate one expert-data collection world for each rectangle lane."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORLDS = PROJECT_ROOT / "worlds"
SOURCE = WORLDS / "test_track_rectangle.wbt"


def main():
    source = SOURCE.read_text(encoding="utf-8")
    old_car = '''BlueRCCar {
  translation 0 2.0 0.145
  customData "learned_test_rectangle"
}'''
    if old_car not in source:
        raise RuntimeError("The expected RC car block was not found in the source world")

    for lane_number, start_y in ((1, 1.4), (2, 2.0), (3, 2.6)):
        new_car = f'''BlueRCCar {{
  translation 0 {start_y:.1f} 0.145
  customData "expert_rectangle_lane_{lane_number}"
}}'''
        destination = WORLDS / f"collect_rectangle_lane_{lane_number}.wbt"
        destination.write_text(source.replace(old_car, new_car), encoding="utf-8")
        print(destination)


if __name__ == "__main__":
    main()
