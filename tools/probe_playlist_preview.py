import csv
import concurrent.futures
import collections
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

PLAYLIST=Path("playlist-preview.m3u")
REPORT=Path("probe-report.md")
CSV=Path("probe-results.csv")
WORKERS=40
TIMEOUT=8

def entries_from_m3u(path):
    lines=path.read_text(encoding="utf-8").splitlines()
    current=None
    for line in lines:
        if line.startswith("#EXTINF:"):
            current=line
        elif current is not None and line.strip() and not line.startswith("#"):
            name=current.rsplit(",",1)[-1].strip()
            yield name,line.strip()
            current=None

def probe(item):
    name,url=item
    cmd=[
      "ffprobe","-v","error","-rw_timeout","6000000",
      "-user_agent","Mozilla/5.0 NurTV-Stream-Audit",
      "-analyzeduration","1000000","-probesize","1000000",
      "-show_entries","stream=codec_type","-of","csv=p=0","-i",url
    ]
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
        types=sorted(set(x.strip() for x in r.stdout.splitlines() if x.strip()))
        if r.returncode==0 and any(x in {"video","audio"} for x in types):
            return (url,name,"ok","+".join(types),r.stderr[:300])
        err=(r.stderr or "").lower()
        if "404 not found" in err or "server returned 404" in err or "http error 404" in err:
            status="http_404"
        elif "410 gone" in err or "http error 410" in err:
            status="http_410"
        elif "401 unauthorized" in err or "http error 401" in err:
            status="http_401"
        elif "403 forbidden" in err or "http error 403" in err:
            status="http_403"
        elif "timed out" in err or "timeout" in err:
            status="timeout"
        else:
            status="no_media_or_other_error"
        return (url,name,status,"",r.stderr[:300])
    except subprocess.TimeoutExpired:
        return (url,name,"timeout","","ffprobe timed out")
    except Exception as exc:
        return (url,name,"probe_error","",str(exc)[:300])

def main():
    all_entries=list(entries_from_m3u(PLAYLIST))
    first_name={}
    for name,url in all_entries:
        first_name.setdefault(url,name)
    urls=list(first_name)
    print(f"Entries including alternatives: {len(all_entries)}")
    print(f"Unique stream URLs to probe once: {len(urls)}")
    results=[]
    start=time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for offset in range(0,len(urls),500):
            batch=urls[offset:offset+500]
            futures=[pool.submit(probe,(first_name[url],url)) for url in batch]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())
            print(f"Probed {min(offset+len(batch),len(urls))}/{len(urls)} unique URLs")
    counts=collections.Counter(x[2] for x in results)
    hosts=collections.defaultdict(collections.Counter)
    for url,name,status,types,err in results:
        hosts[urlparse(url).netloc][status]+=1
    with CSV.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["status","stream_types","channel_name","url","error"])
        for url,name,status,types,err in sorted(results,key=lambda x:(x[2],x[1].lower())):
            w.writerow([status,types,name,url,err])
    duration=round(time.time()-start,1)
    lines=[
      "# Проверка потоков чернового плейлиста",
      "",
      "Проверка выполнялась один раз на каждый уникальный URL. Дубли и альтернативные записи в самом плейлисте не удалялись.",
      "Результат отражает доступность из GitHub Actions runner, а не из России. HTTP 403/timeout могут быть геоблокировкой или временной недоступностью; это не автоматическое доказательство, что поток не работает у пользователя.",
      f"- Записей плейлиста: {len(all_entries)}",
      f"- Уникальных URL проверено: {len(urls)}",
      f"- Время проверки: {duration} сек.",
      f"- Поток с аудио/видео обнаружен: {counts.get('ok',0)}",
      f"- HTTP 404: {counts.get('http_404',0)}",
      f"- HTTP 410: {counts.get('http_410',0)}",
      f"- HTTP 401: {counts.get('http_401',0)}",
      f"- HTTP 403: {counts.get('http_403',0)}",
      f"- Тайм-аут: {counts.get('timeout',0)}",
      f"- Нет медиапотока/другая ошибка: {counts.get('no_media_or_other_error',0)+counts.get('probe_error',0)}",
      "",
      "## Хосты с наибольшим числом ошибок",
      "",
    ]
    for host,c in sorted(hosts.items(),key=lambda x:(-sum(v for k,v in x[1].items() if k!="ok"),x[0]))[:30]:
        failed=sum(v for k,v in c.items() if k!="ok")
        if failed: lines.append(f"- {host}: ошибок {failed}; "+", ".join(f"{k}={v}" for k,v in c.items()))
    lines += ["","## Примеры непроверенных/ошибочных URL",""]
    for url,name,status,types,err in [x for x in results if x[2]!="ok"][:100]:
        lines.append(f"- [{status}] {name} — {url} — {err[:160].replace(chr(10),' ')}")
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__":
    main()
