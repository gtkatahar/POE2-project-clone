import json
from item_parsing.parser import parse_item_text
from item_parsing.identifier import build_lookup, identify

item_text = (
    "Item Class: Talismans\n"
    "Rarity: Rare\n"
    "Wildwood Urge\n"
    "Maji Talisman\n"
    "--------\n"
    "Quality: +8% (augmented)\n"
    "Physical Damage: 256-480 (augmented)\n"
    "Critical Hit Chance: 8.00%\n"
    "Attacks per Second: 1.25\n"
    "--------\n"
    "Requires: Level 79, 100 Str, 67 Int\n"
    "--------\n"
    "Sockets: S S \n"
    "--------\n"
    "Item Level: 82\n"
    "--------\n"
    "Can have 1 additional Crafted Modifier (rune)\n"
    "--------\n"
    "{ Implicit Modifier }\n"
    "+10(7-10) to Maximum Rage\n"
    "--------\n"
    '{ Fractured Prefix Modifier "Merciless" (Tier: 1) -- Damage, Physical, Attack }\n'
    "176(170-179)% increased Physical Damage\n"
    '{ Prefix Modifier "Annealed" (Tier: 4) -- Damage, Physical, Attack }\n'
    "Adds 25(19-29) to 47(33-49) Physical Damage\n"
    "--------\n"
    "Fractured Item\n"
)

import os; os.chdir(os.path.dirname(os.path.abspath(__file__)))
db = json.load(open('data/talismans_modifiers_tiered.json'))
lookup = build_lookup(db['modifiers'])

item = parse_item_text(item_text)
print('stat_lines:', item.get('stat_lines'))
results = identify(item.get('stat_lines', []), lookup)
for r in results:
    print()
    print('line:', r['item_stat'])
    print('values:', r['item_values'])
    print('template:', r['template'])
    print('matched:')
    for m in r['matched']:
        t = m['matched_tier']
        print(f"  section={m['section']} family={m['family']} tier={t['tier']} name={t['name']}")
    print('unmatched:', len(r['unmatched']))
