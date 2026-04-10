# POE2 Crafting Helper

Python automation tools for Path of Exile 2 crafting on Windows.

This project can:
- scrape modifier databases from `poe2db.tw`
- read item tooltips from the game with `Ctrl+C`
- identify affixes and rolled tiers
- scan inventory contents and crafting mats
- build target-mod configs
- automate a few crafting loops with mouse and keyboard input

## Project Layout

- [build_target.py](C:/Users/DjuDja/Desktop/POE2%20project/build_target.py): interactive target builder for desired mods
- [identify.py](C:/Users/DjuDja/Desktop/POE2%20project/identify.py): identify modifiers from a pasted item text file
- [main_test.py](C:/Users/DjuDja/Desktop/POE2%20project/main_test.py): inventory scanner and mat snapshot generator
- [craft_plan.py](C:/Users/DjuDja/Desktop/POE2%20project/craft_plan.py): crafting planner and automation entry point
- [crafting](C:/Users/DjuDja/Desktop/POE2%20project/crafting): crafting-specific modules
- [item_parsing](C:/Users/DjuDja/Desktop/POE2%20project/item_parsing): item text parsing and modifier identification
- [scraping](C:/Users/DjuDja/Desktop/POE2%20project/scraping): poe2db scraping logic
- [windows](C:/Users/DjuDja/Desktop/POE2%20project/windows): Windows input, clipboard, and inventory-grid helpers
- [data](C:/Users/DjuDja/Desktop/POE2%20project/data): cached modifier databases and inventory calibration
- [tests](C:/Users/DjuDja/Desktop/POE2%20project/tests): automated tests

## Requirements

- Windows
- Python 3.14-compatible environment
- Path of Exile 2 running in a mode where item tooltips can be copied with `Ctrl+C`

Install dependencies with:

```powershell
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Common Commands

Build or edit a target:

```powershell
py build_target.py
```

Identify one item from a text file:

```powershell
py identify.py myitem.txt --slug Talismans
```

Scan inventory and identify items:

```powershell
py main_test.py --slug Talismans
```

Capture a crafting-mat inventory snapshot:

```powershell
py main_test.py --mats
```

Run the crafting planner:

```powershell
py craft_plan.py
```

Run tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

## Typical Flow

1. Run `py main_test.py --mats` once to generate `crafting_mats.json`.
2. Run `py build_target.py` to define target mods.
3. Put the base item in inventory cell `[0,0]`.
4. Run `py craft_plan.py` and choose a strategy.

## Safety Notes

- This project uses real mouse and keyboard automation through `pyautogui`.
- Make sure the game window and inventory are in the expected state before starting.
- The mouse failsafe is enabled in [windows/mouse.py](C:/Users/DjuDja/Desktop/POE2%20project/windows/mouse.py).
- Re-run `py calibrate.py` if your inventory grid coordinates drift after changing resolution or UI scale.

## Generated Files

These files are produced during normal use:
- `crafting_mats.json`
- `inventory_scan.json`
- `item_mod_result.json`
- `_craft_plan.json`

They are treated as local/generated artifacts by the `.gitignore`.
