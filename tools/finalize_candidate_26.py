import collections,csv,json
from pathlib import Path

PLAYLIST=Path("playlist-preview.m3u")
RESULTS=Path("probe-results.csv")
META=Path("candidate-additions.json")
OUT=Path("playlist-final-test.m3u")
REPORT=Path("candidate-final-report.md")
REMOVE={"http_404","http_410","http_401"}

def main():
    rows={}
    with RESULTS.open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f): rows[row["url"]]=row
    meta=json.loads(META.read_text(encoding="utf-8"))
    base_count=meta["base_entries"]
    lines=PLAYLIST.read_text(encoding="utf-8-sig").splitlines()
    out=[]; current=[]; idx=0; removed=collections.Counter(); kept_add=0
    for line in lines:
        if line.startswith("#EXTINF:"):
            if current: out.extend(current)
            current=[line]
        elif current:
            if line.startswith("#"): current.append(line)
            elif line.strip():
                idx+=1
                url=line.strip()
                status=rows.get(url,{}).get("status","not_probed")
                # Never rewrite/drop any of the original baseline records.
                if idx<=base_count or status not in REMOVE:
                    out.extend(current); out.append(url)
                    if idx>base_count: kept_add+=1
                else:
                    removed[status]+=1
                current=[]
        elif not out and line.startswith("#EXTM3U"):
            out.append(line)
    if current: out.extend(current)
    OUT.write_text("\n".join(out)+"\n",encoding="utf-8")
    counts=collections.Counter(x["status"] for x in rows.values())
    total=idx
    report=[
      "# Итоговый тестовый плейлист Nur-TV",
      "",
      "Базовые записи исходного плейлиста сохранены без удаления и без дедупликации. Из добавлений удалены только URL с однозначными HTTP 404/410/401. 403, тайм-ауты, DNS/5xx и неопределённые ошибки сохранены как потенциально региональные/временные.",
      f"- Исходная база: {base_count}",
      f"- Всего записей до проверки: {total}",
      f"- Удалено добавленных записей: {sum(removed.values())} (404={removed['http_404']}, 410={removed['http_410']}, 401={removed['http_401']})",
      f"- Добавлений осталось: {kept_add}",
      f"- Всего в итоговом файле: {base_count+kept_add}",
      f"- Уникальных URL проверено: {len(rows)}",
      f"- ffprobe OK: {counts['ok']}",
      f"- HTTP 404: {counts['http_404']}; 410: {counts['http_410']}; 401: {counts['http_401']}; 403: {counts['http_403']}",
      f"- Тайм-аут: {counts['timeout']}; прочие ошибки: {counts['no_media_or_other_error']+counts['probe_error']}",
      "",
      "Важно: проверка выполнена на GitHub runner вне России. Успешный ffprobe означает наличие медиапотока, но не гарантирует линейный эфир; 403 и тайм-ауты не удалялись.",
    ]
    REPORT.write_text("\n".join(report)+"\n",encoding="utf-8")
    print("\n".join(report))
if __name__=="__main__": main()
