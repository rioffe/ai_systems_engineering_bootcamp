def parse_config(raw: str, delimiter: str = "=") -> dict:
    """Parse `raw` key=value lines into a dict.

    Lines that are blank or that contain no `delimiter` are ignored; every
    other line is split on the *first* `delimiter` into (key, value), with
    both sides stripped. This is the canonical (repaired) implementation:
    `test_parse_basic` and `test_ignores_blank_lines` both pass.
    """
    out = {}
    for line in raw.splitlines():
        if line == "" or delimiter not in line:
            continue
        k, v = line.split(delimiter, 1)
        out[k.strip()] = v.strip()
    return out
