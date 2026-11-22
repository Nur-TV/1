import collections
import csv
import re
from pathlib import Path

PLAYLIST = Path("playlist-preview.m3u")
RESULTS = Path("probe-results.csv")
OUT = Path("playlist-review.m3u")
REPORT = Path("probe-cleanup-report.md")
REMOVE_STATUSES = {"http_404", "http_410", "http_401"}


def load_results():
    with RESULTS.open(encoding="utf-8-sig", newline="") as f:
        return {row["url"]: row for row in csv.DictReader(f)}


def parse_playlist(text):
    lines = text.splitlines()
    header = next((line for line in lines if line.startswith("#EXTM3U")), "#EXTM3U")
    entries = []
    pending = []
    for line in lines:
        if line.startswith("#EXTINF:"):
            if pending:
                entries.append((pending, None))
            pending = [line]
        elif pending:
            if line.startswith("#"):
                pending.append(line)
            elif line.strip():
                entries.append((pending, line.strip()))
                pending = []
    if pending:
        entries.append((pending, None))
    return header, entries


def group_of(block):
    m = re.search(r'group-title="([^"]*)"', block[0], re.I)
    return m.group(1) if m else "Без категории"


def name_of(block):
    return block[0].rsplit(",", 1)[-1].strip() if "," in block[0] else "(без названия)"


def main():
    results = load_results()
    header, entries = parse_playlist(PLAYLIST.read_text(encoding="utf-8-sig"))
    kept_lines = [header]
    removed = collections.Counter()
    removed_groups = collections.Counter()
    removed_names = collections.Counter()
    total = 0
    for block, url in entries:
        if url is None:
            kept_lines.extend(block)
            continue
        total += 1
        row = results.get(url)
        status = row["status"] if row else "not_probed"
        name = name_of(block)
        group = group_of(block)
        if status in REMOVE_STATUSES:
            removed[status] += 1
            removed_groups[group] += 1
            removed_names[(name, status)] += 1
            continue
        kept_lines.extend(block)
        kept_lines.append(url)
    OUT.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")

    unique_removed = collections.Counter(
        row["status"] for row in results.values()
        if row["status"] in REMOVE_STATUSES
    )
    counts = collections.Counter(row["status"] for row in results.values())
    lines = [
        "# Консервативная очистка черновика по результатам проверки", "",
        "Создан отдельный файл playlist-review.m3u. Опубликованный playlist.m3u не изменяется.",
        "Удаляются только URL, для которых ffprobe получил явный HTTP 404, 410 или 401. Повторяющиеся записи и альтернативные URL, прошедшие проверку, сохраняются.",
        "HTTP 403, тайм-ауты, 5xx, ошибки DNS/соединения и неопределённые ошибки оставлены: проверка выполнялась вне России и такие результаты нельзя надёжно трактовать как окончательную недоступность.", "",
        f"- Записей в исходном черновике: {total}",
        f"- Удалено записей: {sum(removed.values())} (404: {removed['http_404']}; 410: {removed['http_410']}; 401: {removed['http_401']})",
        f"- Осталось записей: {total - sum(removed.values())}",
        f"- Уникальных URL с удалённым статусом: {sum(unique_removed.values())} (404: {unique_removed['http_404']}; 410: {unique_removed['http_410']}; 401: {unique_removed['http_401']})",
        f"- Уникальных URL без подтверждённого отказа (включая неопределённые): {len(results) - sum(unique_removed.values())}", "",
        "## Удалено по группам", ""
    ]
    lines += [f"- {group}: {count}" for group, count in removed_groups.most_common()]
    lines += ["", "## Что оставлено для дополнительной проверки", "",
        f"- HTTP 403: {counts['http_403']} уникальных URL",
        f"- Тайм-аут: {counts['timeout']} уникальных URL",
        f"- Нет медиапотока / другие ошибки: {counts['no_media_or_other_error'] + counts['probe_error']} уникальных URL",
        f"- Успешно обнаружен аудио/видеопоток: {counts['ok']} уникальных URL", "",
        "Успешный ffprobe подтверждает наличие аудио/видеопотока в момент проверки, но не доказывает, что это линейный канал и что он воспроизводится из России.", "",
        "## Примеры удалённых записей", ""
    ]
    for (name, status), count in removed_names.most_common(40):
        lines.append(f"- [{status}] {name} — записей: {count}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
