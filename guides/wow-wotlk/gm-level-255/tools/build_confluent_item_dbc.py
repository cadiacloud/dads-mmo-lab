#!/usr/bin/env python3
"""Add the Confluent Vanguard items to a WotLK 3.3.5a Item.dbc.

The server obtains the full item template from SQL, but the 3.3.5a client uses
Item.dbc for equipment-class checks. Without these rows, client-side spell
validation does not recognize the custom sword or shield.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


HEADER = struct.Struct("<4s4I")
ITEM = struct.Struct("<IIIiiIII")

# ID, class, subclass, sound override subclass, material, display ID,
# inventory type, sheath type. These fields mirror the source templates in
# confluent_vanguard_paladin.sql.
CONFLUENT_ITEMS = (
    (900001, 4, 4, -1, 4, 64692, 1, 0),
    (900002, 4, 4, -1, 6, 65000, 3, 0),
    (900003, 4, 4, -1, 1, 64695, 5, 0),
    (900004, 4, 4, -1, 1, 64694, 10, 0),
    (900005, 4, 4, -1, 6, 64674, 7, 0),
    (900006, 4, 4, -1, 1, 64702, 6, 0),
    (900007, 4, 4, -1, 1, 64789, 8, 0),
    (900008, 4, 4, -1, 6, 64799, 9, 0),
    (900009, 2, 8, -1, 1, 64397, 17, 1),
    (900010, 2, 7, -1, 1, 64539, 13, 3),
    (900011, 4, 6, -1, 6, 65055, 14, 4),
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
    by_id.update({record[0]: record for record in CONFLUENT_ITEMS})
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
        f"({len(CONFLUENT_ITEMS)} Confluent rows present)."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="stock WotLK 3.3.5a Item.dbc")
    parser.add_argument("destination", type=Path, help="patched Item.dbc output")
    args = parser.parse_args()
    update_dbc(args.source, args.destination)


if __name__ == "__main__":
    main()
