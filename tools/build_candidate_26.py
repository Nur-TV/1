import collections, hashlib, json, re, unicodedata
from pathlib import Path
from urllib.parse import urlparse
import requests

BASE=Path("playlist.m3u")
CATALOG=Path("tools/source_catalog_26.json")
LOGOS=Path("channel-logos.json")
OUT=Path("playlist-preview.m3u")
ADD_META=Path("candidate-additions.json")
REPORT=Path("candidate-build-report.md")

MEDIA_EXT=re.compile(r"\.(mp4|mkv|avi|mov|m4v|webm|flv|wmv|mpg|mpeg|mp3|m4a|aac|flac)(?:$|[?#])",re.I)
VOD_GROUP=re.compile(r"(кинозал|медиатек|фильм|мультфильм|сериал|movies|films|series|vod|on.?demand|ролики)",re.I)
VOD_PATH=re.compile(r"/(?:hls/)?(?:film|films|movie|movies|serials|series|multfilm|vod)(?:/|\.|$)",re.I)
VOD_NAME=re.compile(r"(\b\d+\s*(?:серия|сезон|эпизод)\b|\bs\d{1,2}e\d{1,2}\b|смотреть онлайн|полная версия|фильм целиком)",re.I)
BAD=re.compile(r"(\btest\b|тест|техподдерж|поддержать|playlist information|not\s*24/7|no\s*24/7|не\s*24/7|🔺\s*info)",re.I)
LOCAL=re.compile(r"(127\.0\.0\.1|localhost|/ace/getstream)",re.I)
RESTRICTED=re.compile(r"(?:mdrm|drmreq=|access_token=|username=|password=|[?&](?:cid|did|mac|play_token)=)",re.I)
REMOVE_WORDS={"hd","fhd","uhd","4k","8k","sd","hdtv","tv","телеканал","канал","channel","online","онлайн","live","лайв"}

def norm(s):
    s=unicodedata.normalize("NFKC",s or "").lower().replace("ё","е")
    s=re.sub(r"\([^)]*\)|\[[^]]*\]|\{[^}]*\}"," ",s)
    s=re.sub(r"https?://\S+"," ",s)
    s=re.sub(r"[^0-9a-zа-яё]+"," ",s,flags=re.I)
    return " ".join(x for x in s.split() if x not in REMOVE_WORDS).strip()

def attr(line,key):
    m=re.search(rf'{re.escape(key)}="([^"]*)"',line,re.I)
    return m.group(1).strip() if m else ""

def set_attr(line,key,value):
    pat=rf'{re.escape(key)}="[^"]*"'
    repl=f'{key}="{value}"'
    if re.search(pat,line,re.I):
        return re.sub(pat,lambda _:repl,line,count=1,flags=re.I)
    comma=line.rfind(",")
    return line[:comma]+" "+repl+line[comma:] if comma>=0 else line

def parse(text):
    entries=[]; block=[]
    for line in text.splitlines():
        if line.startswith("#EXTINF:"):
            if block: entries.append((block,None))
            block=[line]
        elif block:
            if line.startswith("#"): block.append(line)
            elif line.strip():
                entries.append((block,line.strip())); block=[]
    if block: entries.append((block,None))
    return entries

def adult_keep(source,group):
    g=norm(group)
    if source=="Xteen18+TV": return True
    if source=="Sexture18+TV": return g=="взрослые"
    if source=="Adultip18+TV": return g in {"каналы","телеканалы"}
    return False

def accept(source,group,title,url,category):
    if not url.startswith(("http://","https://")): return False,"unsupported_url"
    if LOCAL.search(url): return False,"local_ace"
    if RESTRICTED.search(url): return False,"restricted_credentials"
    if MEDIA_EXT.search(url): return False,"direct_media_file"
    path=urlparse(url).path
    if VOD_PATH.search(path): return False,"vod_url_path"
    if VOD_NAME.search(title): return False,"episode_or_vod_title"
    if BAD.search(group+" "+title): return False,"test_info_or_not24x7"
    if category=="adult":
        if not adult_keep(source,group): return False,"adult_vod_or_non_tv_group"
        return True,"adult_channel"
    if VOD_GROUP.search(group) and "/live/" not in path.lower(): return False,"vod_group"
    return True,"kept_for_stream_probe"

def main():
    base_text=BASE.read_text(encoding="utf-8-sig")
    base=parse(base_text)
    base_valid=[(b,u) for b,u in base if u]
    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    logos=json.loads(LOGOS.read_text(encoding="utf-8"))
    existing={}
    for block,url in base_valid:
        name=block[0].rsplit(",",1)[-1].strip()
        if norm(name): existing.setdefault(norm(name),(attr(block[0],"tvg-id"),attr(block[0],"tvg-logo")))
    all_sources=[]
    for category,key in (("tv","ordinary_tv"),("media","media_libraries"),("adult","adult_tv")):
        all_sources += [(category,n,u) for n,u in catalog[key]]
    additions=[]; stats=[]; errors=[]
    session=requests.Session()
    for category,source,url in all_sources:
        try:
            r=session.get(url,timeout=(15,70),headers={"User-Agent":"NurTV-CandidateBuilder/2.0"})
            r.raise_for_status()
            text=r.content[:40*1024*1024].decode("utf-8-sig",errors="replace")
            found=parse(text); kept=0; dropped=collections.Counter()
            for block,stream in found:
                if not stream or not block[0].startswith("#EXTINF:"):
                    continue
                info=block[0]
                title=info.rsplit(",",1)[-1].strip()
                group=attr(info,"group-title") or "Без категории"
                ok,reason=accept(source,group,title,stream,category)
                if not ok:
                    dropped[reason]+=1; continue
                adult=category=="adult"
                target_group="Взрослые" if adult else group
                known=existing.get(norm(title))
                cid=(known[0] if known and known[0] else "nurtv-"+hashlib.sha1((norm(title) or title.lower()).encode()).hexdigest()[:16])
                info=set_attr(info,"group-title",target_group)
                info=set_attr(info,"tvg-id",cid)
                logo=(known[1] if known else "") or logos.get(cid,"")
                if logo: info=set_attr(info,"tvg-logo",logo)
                else:
                    info=re.sub(r'\s+tvg-logo="[^"]*"','',info,flags=re.I)
                additions.append({"source":source,"category":category,"group":target_group,"name":title,"block":block,"url":stream})
                kept+=1
            stats.append((source,category,len(found),kept,dropped))
        except Exception as e:
            errors.append((source,str(e)))
            stats.append((source,category,0,0,collections.Counter({"source_error":1})))
    header=next((x for x in base_text.splitlines() if x.startswith("#EXTM3U")),"#EXTM3U")
    lines=[header]
    for block,url in base:
        lines.extend(block)
        if url: lines.append(url)
    for item in additions:
        lines.extend(item["block"])
        lines.append(item["url"])
    OUT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    ADD_META.write_text(json.dumps({"base_entries":len(base_valid),"additions":additions},ensure_ascii=False),encoding="utf-8")
    report=["# Сборка кандидата из 26 источников","","Базовый плейлист сохранён целиком и без изменения записей. Дубли и альтернативные URL не удалялись. Источники 18+ объединены в группу «Взрослые».","Фильтрация исключает явные VOD-группы/пути, прямые медиафайлы, эпизодные названия, локальные AceStream URL и служебные записи. Это ещё не подтверждение live-эфира: следующий этап — ffprobe каждого уникального URL.",f"- База: {len(base_valid)} записей",f"- Добавлено до проверки потоков: {len(additions)}",f"- Всего в кандидате до проверки: {len(base_valid)+len(additions)}","", "| Источник | Тип | Получено | Кандидат | Исключено | Причины |","|---|---|---:|---:|---:|---|"]
    for s,c,n,k,d in stats:
        report.append(f"| {s} | {c} | {n} | {k} | {sum(d.values())} | "+(", ".join(f"{a}={b}" for a,b in d.most_common()) or "—")+" |")
    if errors: report += ["","## Ошибки источников"]+[f"- {s}: {e}" for s,e in errors]
    REPORT.write_text("\n".join(report)+"\n",encoding="utf-8")
    print("\n".join(report))

if __name__=="__main__": main()
