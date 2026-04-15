from __future__ import annotations


def human_view_traffic_bytes(value: int | None) -> str | None:
    if value is None:
        return None

    bytes_value = int(value)
    gib = 1024 * 1024 * 1024
    mib = 1024 * 1024
    kib = 1024

    if bytes_value >= gib:
        gb_value = bytes_value / gib
        return f"{int(gb_value)} GB" if bytes_value % gib == 0 else f"{gb_value:.1f} GB"
    if bytes_value >= mib:
        mb_value = bytes_value / mib
        return f"{int(mb_value)} MB" if bytes_value % mib == 0 else f"{mb_value:.1f} MB"
    if bytes_value >= kib:
        kb_value = bytes_value / kib
        return f"{int(kb_value)} KB" if bytes_value % kib == 0 else f"{kb_value:.1f} KB"
    return f"{bytes_value} B"
