#!/usr/bin/env python3
"""Add the BOA rogue heirlooms to a WotLK 3.3.5a Item.dbc.

The server sends names and scaling data from item_template, but the client uses
Item.dbc for equipment type, weapon subclass, display, and sheath validation.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


HEADER = struct.Struct("<4s4I")
ITEM = struct.Struct("<IIIiiIII")

# Custom ID, class, subclass, sound override subclass, material, display ID,
# inventory type, sheath. Each row mirrors its documented stock source item.
BOA_ROGUE_ITEMS = (
    (900100, 2, 7, -1, 1, 45479, 21, 1),
    (900101, 2, 7, -1, 1, 45481, 22, 1),
    (900102, 4, 2, -1, 8, 59057, 5, 0),
    (900103, 4, 2, -1, 8, 59340, 10, 0),
    (900104, 4, 2, -1, 8, 59341, 1, 0),
    (900105, 4, 2, -1, 8, 59342, 7, 0),
    (900106, 4, 2, -1, 8, 59344, 3, 0),
    (900107, 4, 2, -1, 8, 64421, 9, 0),
    (900108, 4, 2, -1, 8, 64430, 6, 0),
    (900109, 4, 2, -1, 8, 64437, 8, 0),
    (900110, 4, 0, -1, 3, 64216, 2, 0),
    (900111, 4, 1, -1, 7, 64304, 16, 0),
    (900112, 4, 0, -1, 5, 64225, 11, 0),
    (900113, 4, 0, -1, 5, 64227, 11, 0),
    (900114, 4, 0, -1, 4, 68109, 12, 0),
    (900115, 4, 0, -1, 4, 64244, 12, 0),
    (900116, 2, 18, -1, 2, 64371, 26, 0),
)


def update_dbc(source: Path, destination: Path) -> None:
    raw = source.read_bytes()
    if len(raw) < HEADER.size:
        raise ValueError(f"{source} is too small to be a DBC file")

    magic, record_count, field_count, record_size, string_size = HEADER.unpack_from(raw)
    if magic != b"WDBC":
        raise ValueError(f"{source} is not a WDBC file")
    if field_count != 8 or record_size != ITEM.size:
        raise ValueError(
            f"unexpected Item.dbc layout: fields={field_count}, record_size={record_size}"
        )

    records_start = HEADER.size
    records_end = records_start + record_count * record_size
    strings_end = records_end + string_size
    if strings_end != len(raw):
        raise ValueError(
            f"invalid Item.dbc size: header describes {strings_end} bytes, found {len(raw)}"
        )

    records = [
        ITEM.unpack_from(raw, records_start + index * record_size)
        for index in range(record_count)
    ]
    by_id = {record[0]: record for record in records}
    by_id.update({record[0]: record for record in BOA_ROGUE_ITEMS})
    updated_records = [by_id[item_id] for item_id in sorted(by_id)]
    strings = raw[records_end:strings_end]

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        output.write(
            HEADER.pack(
                magic,
                len(updated_records),
                field_count,
                record_size,
                string_size,
            )
        )
        for record in updated_records:
            output.write(ITEM.pack(*record))
        output.write(strings)

    print(
        f"Wrote {destination} with {len(updated_records)} rows "
        f"({len(BOA_ROGUE_ITEMS)} BOA rogue rows present)."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="WotLK 3.3.5a Item.dbc")
    parser.add_argument("destination", type=Path, help="patched Item.dbc output")
    args = parser.parse_args()
    update_dbc(args.source, args.destination)


if __name__ == "__main__":
    main()
