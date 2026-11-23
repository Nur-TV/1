import collections
import concurrent.futures
import re
import requests
from urllib.parse import urlparse

SOURCES = [
 ("UfoTV","https://raw.githubusercontent.com/UFOTVM/TV/refs/heads/main/ufo.m3u"),
 ("FreeTV","https://raw.githubusercontent.com/Dimonovich/TV/Dimonovich/FREE/TV"),
 ("EndikTV","https://bit.ly/Endik1"),
 ("KinomixTV","https://tinyurl.com/KinomixTV"),
 ("VivamaxTV","https://bit.ly/vivamax-m3u"),
 ("ShamsTV","https://tinyurl.com/shamsiptv"),
 ("TivinorTV","https://raw.githubusercontent.com/Tivinor/tivinor/refs/heads/main/tivinor.m3u"),
 ("MaxTV","https://raw.githubusercontent.com/MaxTVNew01/Maxtvvhs/refs/heads/main/LICENSE.m3u"),
 ("ZunoTV","https://raw.githubusercontent.com/iptv-free/TV/refs/heads/FREE/TV"),
 ("DolovTV","https://raw.githubusercontent.com/Dolov07KBR/DF_IPTV/refs/heads/main/07.m3u"),
 ("MainTV","https://raw.githubusercontent.com/premiumtvam/sp.server.ru/refs/heads/main/README.md"),
 ("WinkTV","https://tinyurl.com/ruwink"),
 ("SpirtTV","https://spirt007.github.io/Tvru/Rus.m3u"),
 ("VeronaTV","https://raw.githubusercontent.com/IPTVSHARED/VeronaTV/refs/heads/main/VeronaTV.m3u"),
 ("ZabavaTV","https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-full.m3u"),
]
MEDIA_SOURCES = [
 ("Max Mediateka","https://raw.githubusercontent.com/MaxTVNew01/maxtv-uz-media-index/refs/heads/main/README.m3u"),
 ("Drive Mediateka","https://tinyurl.com/drivemediateka2"),
 ("Multfilm Mediateka","http://dmi3y-tv.online/iptv/multfilm.m3u"),
 ("NashyMultiki Mediateka","https://raw.githubusercontent.com/user797/Playlists/refs/heads/main/Cartoons.m3u8"),
 ("Suzus Mediateka","https://raw.githubusercontent.com/iptv-free/TV/refs/heads/FREE/KINO/RU"),
 ("Dmi3y Mediateka","http://dmi3y-tv.online/iptv/film.m3u"),
 ("Films Mediateka","https://raw.githubusercontent.com/Dimonovich/TV/refs/heads/Dimonovich/FREE/FILMS.m3u"),
 ("Filmd Mediateka","http://dmi3y-tv.online/iptv/film_d-tv.m3u"),
]
ADULT_SOURCES = [
 ("Xteen18+TV","https://tinyurl.com/xteen18"),
 ("Sexture18+TV","https://tinyurl.com/sexture18"),
 ("Adultip18+TV","https://tinyurl.com/adultip18"),
]
VOD_GROUP=re.compile(r"(медиатек|кинозал|фильм|сериал|видео.?по.?запрос|vod|movies|series|films|cinema|kino.?zal|мультфильм.?онлайн)",re.I)
VOD_NAME=re.compile(r"(смотреть онлайн|полная версия|фильм целиком|серия \d+|сезон \d+|мультфильм целиком|vod|movie on demand)",re.I)
MEDIA_EXT=re.compile(r"\.(mp4|mkv|avi|mov|mp3|m4v|webm|flv|wmv|mpg|mpeg|m4a|aac|flac)(?:$|[?#])",re.I)

def audit(item):
 name,url=item
 try:
  r=requests.get(url,timeout=(15,60),headers={"User-Agent":"NurTV-Source-Audit/1.0"})
  r.raise_for_status()
  data=r.content[:30*1024*1024].decode("utf-8-sig",errors="replace")
  entries=[]; pending=None
  for line in data.splitlines():
   line=line.strip()
   if not line: continue
   if line.startswith("#EXTINF"):
    pending=line
   elif pending and not line.startswith("#"):
    info=pending; stream=line; pending=None
    m=re.search(r'group-title="([^"]*)"',info,re.I)
    group=m.group(1).strip() if m else "(без группы)"
    title=info.rsplit(",",1)[-1].strip()
    flags=[]
    if VOD_GROUP.search(group): flags.append("VOD_GROUP")
    if VOD_NAME.search(title): flags.append("VOD_NAME")
    if MEDIA_EXT.search(stream): flags.append("MEDIA_FILE_EXT")
    entries.append((group,title,stream,flags))
  gc=collections.Counter(x[0] for x in entries)
  ex=collections.Counter(urlparse(x[2]).path.rsplit(".",1)[-1].lower() if "." in urlparse(x[2]).path.rsplit("/",1)[-1] else "(none)" for x in entries)
  bad=[x for x in entries if x[3]]
  flagged=collections.defaultdict(list)
  for item in bad: flagged[item[0]].append(item)
  out=[f"## {name}",f"- HTTP: {r.status_code}; конечный URL: {r.url}",f"- Прочитано байт (лимит 30 MiB): {min(len(r.content),30*1024*1024)}",f"- Записей EXTINF: {len(entries)}",f"- Групп: {len(gc)}","- Расширения: "+", ".join(f"{k}={v}" for k,v in ex.most_common(12)),"- Группы: "+"; ".join(f"{k} ({v})" for k,v in gc.most_common(35)),f"- Пометки VOD/файловых записей (нужна ручная проверка, это не автоудаление): {len(bad)}"]
  for group, items in sorted(flagged.items(), key=lambda kv:(-len(kv[1]),kv[0]))[:30]:
   out.append(f"  - Группа «{group}»: {len(items)} пометок")
   for g,t,u,flags in items[:5]:
    out.append(f"    - [{'+'.join(flags)}] {t} | {u[:180]}")
  return name,"\n".join(out),len(entries),None
 except Exception as e:
  return name,f"## {name}\n- ОШИБКА: {type(e).__name__}: {e}",0,str(e)

def main():
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
  results=list(ex.map(audit,SOURCES))
  adult_results=list(ex.map(audit,ADULT_SOURCES))
 total=sum(x[2] for x in results); errors=sum(bool(x[3]) for x in results)
 adult_total=sum(x[2] for x in adult_results); adult_errors=sum(bool(x[3]) for x in adult_results)
 report=["# Nur-TV — аудит источников IPTV","","Предварительный структурный аудит (автоматическая инвентаризация источников). Это НЕ проверка воспроизведения и НЕ автоматическое разрешение на импорт. Наличие .m3u8 само по себе не доказывает, что запись является линейным телеканалом.",f"- Общие источники: {len(SOURCES)}; успешно: {len(SOURCES)-errors}; ошибок: {errors}; записей EXTINF: {total}",f"- Источники 18+: {len(ADULT_SOURCES)}; успешно: {len(ADULT_SOURCES)-adult_errors}; ошибок: {adult_errors}; записей EXTINF: {adult_total}","", "## Общие источники", "\n\n".join(x[1] for x in results), "", "## Отдельная проверка 18+ (все записи при сборке должны попасть в одну группу «Взрослые»)", "\n\n".join(x[1] for x in adult_results)]
 with open("source-audit.md","w",encoding="utf-8") as f: f.write("\n".join(report)+"\n")
 print("\n".join(report))
if __name__=="__main__": main()
