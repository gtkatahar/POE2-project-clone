# POE2 Crafting Helper

Python automation tools for Path of Exile 2 crafting on Windows.

This project can:
- scrape modifier databases from `poe2db.tw`
- read item tooltips from the game with `Ctrl+C`
- identify affixes and rolled tiers across **all mod sections** (base, runes, bonded, essence, corrupted, etc.)
- scan inventory contents and crafting mats
- build target-mod configs via a dark-themed GUI or the command line
- automate a few crafting loops with mouse and keyboard input

## Project Layout

- [gui_main.py](C:/Users/DjuDja/Desktop/POE2%20project/gui_main.py): **main GUI entry point** (PyQt6, dark theme)
- [gui_window.py](C:/Users/DjuDja/Desktop/POE2%20project/gui_window.py): main window and all tab widgets
- [gui_mod_builder.py](C:/Users/DjuDja/Desktop/POE2%20project/gui_mod_builder.py): target/mod-builder dialog with per-section mod picker
- [gui_worker.py](C:/Users/DjuDja/Desktop/POE2%20project/gui_worker.py): background worker threads for scan and craft operations
- [gui_settings.py](C:/Users/DjuDja/Desktop/POE2%20project/gui_settings.py): settings persistence and Settings tab
- [build_target.py](C:/Users/DjuDja/Desktop/POE2%20project/build_target.py): CLI target builder (alternative to the GUI)
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

- Windows 10 / 11
- Python 3.11+ (installed automatically by the setup script if missing)
- Path of Exile 2 running in a mode where item tooltips can be copied with `Ctrl+C`

## Installation

Run the setup script once — it handles everything, including Python if it isn't installed yet:

```powershell
.\setup.ps1
```

What it does:
1. Detects Python 3.11+; installs Python 3.13 via **winget** (or a direct download fallback) if not found
2. Creates a `.venv` virtual environment
3. Upgrades pip and installs all packages from `requirements.txt`
4. Runs a quick import smoke-test
5. Offers to launch the GUI immediately

## PowerShell Runner Scripts

Each entry point has a dedicated `.ps1` wrapper that always invokes the `.venv` Python, regardless of what Python is on the system `PATH`. Pass any arguments straight through.

| Script | Entry point | Purpose |
|--------|------------|---------|
| [run_gui.ps1](run_gui.ps1) | `gui_main.py` | Launch the GUI |
| [run_build_target.ps1](run_build_target.ps1) | `build_target.py` | CLI target builder |
| [run_identify.ps1](run_identify.ps1) | `identify.py` | Identify modifiers from a text file |
| [run_main_test.ps1](run_main_test.ps1) | `main_test.py` | Inventory scanner / mat snapshot |
| [run_craft_plan.ps1](run_craft_plan.ps1) | `craft_plan.py` | Crafting planner and automation |
| [run_calibrate.ps1](run_calibrate.ps1) | `calibrate.py` | Recalibrate inventory grid coordinates |
| [run_scrape.ps1](run_scrape.ps1) | `scrape.py` | Scrape one item type from poe2db |
| [run_scrape_all.ps1](run_scrape_all.ps1) | `scrape_all.py` | Scrape all item types from poe2db |

Run any of them from PowerShell in the project root — no activation step needed:

```powershell
.\run_gui.ps1
.\run_identify.ps1 myitem.txt --slug Talismans
.\run_main_test.ps1 --mats
```

> **Tip:** If you see a policy error, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first (same as the setup script does).

## GUI (recommended)

Launch the GUI:

```powershell
.\run_gui.ps1
```

The GUI has four tabs:

| Tab | Purpose |
|-----|---------|
| **Materials** | Scan your crafting-currency inventory and save a snapshot |
| **Targets** | Browse, create, edit, and activate saved target configs |
| **Craft** | Choose a strategy and run the crafting loop |
| **Settings** | Auto-minimize, font size, default strategy |

### Mod Builder — Section picker

When creating or editing a target the **Mod Builder** dialog shows a **Section** dropdown above the mod filter. It exposes every section present in the loaded item's modifier database:

| Section key | Display name |
|-------------|--------------|
| `normal` | Base Modifiers |
| `socketable` | Rune / Augment |
| `bonded` | Bonded (Shaman Runes) |
| `marksman` | Marksman |
| `corrupted` | Corrupted (Vaal Orb) |
| `essence` | Essence |
| `desecrated` | Desecrated Modifiers |
| `decay` | Decay |
| `perfect_essence` | Perfect Essence |

Switch the dropdown to browse and add mods from any section into your search target. The text filter and Prefix / Suffix filter still apply on top; set the type filter to **All** when browsing sections that use non-standard types such as `Type 0` or `Enchantment`.

> **Note:** Only Base Modifier (prefix/suffix) mods contribute to crafting-cost estimates. Mods from other sections are matched during item scans but are excluded from the aug/annul probability calculations.

## Common Commands

Identify one item from a text file:

```powershell
.\run_identify.ps1 myitem.txt --slug Talismans
```

Scan inventory and identify items (CLI):

```powershell
.\run_main_test.ps1 --slug Talismans
```

Capture a crafting-mat inventory snapshot (CLI):

```powershell
.\run_main_test.ps1 --mats
```

Run the crafting planner (CLI):

```powershell
.\run_craft_plan.ps1
```

Run tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

## Typical Flow

1. Launch `.\run_gui.ps1`.
2. Go to the **Materials** tab and click **Scan Inventory** to generate `crafting_mats.json`.
3. Go to the **Targets** tab, click **New**, and build your target — picking mods from any section via the Section dropdown.
4. Select the target and click **Set as Active**.
5. Put the base item in inventory cell `[0,0]`, go to the **Craft** tab, choose a strategy, and click **Start**.

## Safety Notes

- This project uses real mouse and keyboard automation through `pyautogui`.
- Make sure the game window and inventory are in the expected state before starting.
- The mouse failsafe is enabled in [windows/mouse.py](C:/Users/DjuDja/Desktop/POE2%20project/windows/mouse.py).
- Re-run `.\run_calibrate.ps1` if your inventory grid coordinates drift after changing resolution or UI scale.

## Generated Files

These files are produced during normal use:
- `crafting_mats.json`
- `inventory_scan.json`
- `item_mod_result.json`
- `_craft_plan.json`
- `settings.json`
- `saved_targets/*.json`

They are treated as local/generated artifacts by the `.gitignore`.
