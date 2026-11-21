import hashlib
import json
import re
import unicodedata
from pathlib import Path

SOURCE = Path("backups/playlist-original-2026-11-21.m3u")
LOGOS = Path("channel-logos.json")
OUTPUT = Path("playlist.m3u")

REMOVE_WORDS = {
    "hd", "fhd", "uhd", "4k", "8k", "sd", "hdtv", "tv",
    "телеканал", "канал", "channel", "online", "онлайн", "live", "лайв",
}

def norm(value):
    value = unicodedata.normalize("NFKC", value or "").lower().replace("ё", "е")
    value = re.sub(r"\([^)]*\)|\[[^]]*\]|\{[^}]*\}", " ", value)
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^0-9a-zа-яё]+", " ", value, flags=re.I)
    return " ".join(word for word in value.split() if word not in REMOVE_WORDS).strip()

def canonical_id(name):
    normalized = norm(name) or (name or "unknown").strip().lower()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"nurtv-{digest}"

def set_attr(info, attr, value):
    pattern = rf'{re.escape(attr)}="[^"]*"'
    replacement = f'{attr}="{value}"'
    if re.search(pattern, info, flags=re.I):
        return re.sub(pattern, lambda _: replacement, info, count=1, flags=re.I)
    comma = info.rfind(",")
    if comma >= 0:
        return info[:comma] + " " + replacement + info[comma:]
    return info

def main():
    original = SOURCE.read_text(encoding="utf-8-sig")
    logo_map = json.loads(LOGOS.read_text(encoding="utf-8"))
    if not isinstance(logo_map, dict):
        raise RuntimeError("channel-logos.json is not a JSON object")

    out = []
    entry_count = 0
    urls_before = []
    urls_after = []
    ids = set()
    names_to_ids = {}
    logos_applied = 0
    for line in original.splitlines():
        if line.startswith("#EXTINF:"):
            name = line.rsplit(",", 1)[-1].strip()
            cid = canonical_id(name)
            ids.add(cid)
            normalized = norm(name)
            previous = names_to_ids.setdefault(normalized, cid)
            if previous != cid:
                raise RuntimeError(f"Non-deterministic ID for channel name: {name}")
            line = set_attr(line, "tvg-id", cid)
            logo = logo_map.get(cid, "")
            if logo:
                line = set_attr(line, "tvg-logo", logo)
                logos_applied += 1
            entry_count += 1
        elif line and not line.startswith("#"):
            urls_before.append(line.strip())
            urls_after.append(line.strip())
        out.append(line)

    if entry_count != 2976:
        raise RuntimeError(f"Expected 2976 baseline entries, got {entry_count}")
    if urls_before != urls_after:
        raise RuntimeError("Stream URLs/order changed unexpectedly")
    if len(ids) != len(names_to_ids):
        raise RuntimeError("Canonical ID count does not match normalized channel names")

    OUTPUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Baseline entries preserved: {entry_count}")
    print(f"Unique canonical tvg-id values: {len(ids)}")
    print(f"Distinct normalized channel names: {len(names_to_ids)}")
    print(f"Playlist entries with EPG logo applied: {logos_applied}")
    print(f"Available logo-map IDs: {len(logo_map)}")
    print("Stream URLs, order, and original backup were not changed.")

if __name__ == "__main__":
    main()
