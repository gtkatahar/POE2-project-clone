"""
calibrate.py
------------
Measure POE2 inventory grid coordinates for your screen.

Usage:
    py calibrate.py

Steps:
  1. Launch POE2 and open your inventory (default key: I).
  2. Alt+Tab back to this terminal and run the script.
  3. Follow the 3 prompts — hover to the TOP-LEFT corner of each
     indicated cell and press Enter.
  4. Paste the printed values into windows/inventory.py.
"""

from windows.inventory import calibrate

if __name__ == "__main__":
    calibrate()
