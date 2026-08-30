#!/usr/bin/env python3
"""Add BOA rogue stat endpoints to ScalingStatDistribution.dbc.

The rows make the level-80 client tooltip use the selected heroic ICC/RS stat
budget. The companion server module remains authoritative for the nonlinear
Warglaive level-70 breakpoint and exact equipped values.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


HEADER = struct.Struct("<4s4I")
ROW = struct.Struct("<I10i11I")

# Custom distribution ID, level-80 stat multiplier, (stat type, target value).
# Stat types: 3 agility, 7 stamina, 31 hit, 32 crit, 36 haste,
# 37 expertise, 38 attack power, 44 armor penetration.
ENDPOINTS = (
    (9100, 56, ((38, 95), (3, 84), (7, 84), (32, 56), (36, 48))),
    (9101, 56, ((38, 88), (3, 78), (7, 78), (32, 52), (44, 44))),
    (9102, 131, ((38, 228), (3, 167), (7, 183), (31, 114), (37, 106))),
    (9103, 97, ((38, 165), (3, 128), (7, 136), (44, 90), (36, 74))),
    (9104, 131, ((38, 196), (3, 183), (7, 183), (32, 114), (44, 106))),
    (9105, 131, ((38, 228), (3, 167), (7, 183), (32, 122), (31, 98))),
    (9106, 97, ((38, 165), (3, 136), (7, 136), (32, 90), (31, 82))),
    (9107, 97, ((38, 120), (3, 102), (7, 102), (32, 60), (44, 68))),
    (9108, 97, ((38, 181), (3, 120), (7, 136), (32, 90), (44, 74))),
    (9109, 97, ((38, 181), (3, 120), (7, 136), (32, 90), (44, 74))),
    (9110, 73, ((38, 120), (3, 102), (7, 102), (44, 68), (36, 60))),
    (9111, 73, ((38, 114), (3, 97), (7, 97), (32, 65), (44, 57))),
    (9112, 73, ((38, 145), (3, 109), (7, 109), (32, 73), (31, 57))),
    (9113, 73, ((38, 135), (3, 88), (7, 84), (32, 59), (31, 59))),
    (9114, 97, ((44, 184),)),
    (9115, 97, ((44, 167),)),
    (9116, 41, ((38, 66), (3, 62), (7, 62), (32, 41), (44, 33))),
)


def modifier_for(target: int, multiplier: int) -> int:
    """Return the smallest modifier whose integer endpoint equals target."""
    modifier = (target * 10_000 + multiplier - 1) // multiplier
    if multiplier * modifier // 10_000 != target:
        raise ValueError(f"cannot encode target {target} with multiplier {multiplier}")
    return modifier


def make_row(distribution_id: int, multiplier: int, stats: tuple[tuple[int, int], ...]):
    stat_types = [-1] * 10
    modifiers = [0] * 10
    for index, (stat_type, target) in enumerate(stats):
        stat_types[index] = stat_type
        modifiers[index] = modifier_for(target, multiplier)
    return (distribution_id, *stat_types, *modifiers, 80)


def update_dbc(source: Path, destination: Path) -> None:
    raw = source.read_bytes()
    if len(raw) < HEADER.size:
        raise ValueError(f"{source} is too small to be a DBC file")

    magic, record_count, field_count, record_size, string_size = HEADER.unpack_from(raw)
    if magic != b"WDBC":
        raise ValueError(f"{source} is not a WDBC file")
    if field_count != 22 or record_size != ROW.size:
        raise ValueError(
            "unexpected ScalingStatDistribution.dbc layout: "
            f"fields={field_count}, record_size={record_size}"
        )

    records_start = HEADER.size
    records_end = records_start + record_count * record_size
    strings_end = records_end + string_size
    if strings_end != len(raw):
        raise ValueError(
            f"invalid DBC size: header describes {strings_end} bytes, found {len(raw)}"
        )

    records = [
        ROW.unpack_from(raw, records_start + index * record_size)
        for index in range(record_count)
    ]
    by_id = {record[0]: record for record in records}
    for distribution_id, multiplier, stats in ENDPOINTS:
        by_id[distribution_id] = make_row(distribution_id, multiplier, stats)

    updated_records = [by_id[record_id] for record_id in sorted(by_id)]
    strings = raw[records_end:strings_end]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        output.write(
            HEADER.pack(magic, len(updated_records), field_count, record_size, string_size)
        )
        for record in updated_records:
            output.write(ROW.pack(*record))
        output.write(strings)

    print(
        f"Wrote {destination} with {len(updated_records)} rows "
        f"({len(ENDPOINTS)} BOA rogue rows present)."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="stock ScalingStatDistribution.dbc")
    parser.add_argument("destination", type=Path, help="patched DBC output")
    args = parser.parse_args()
    update_dbc(args.source, args.destination)


if __name__ == "__main__":
    main()
