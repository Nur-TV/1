import collections
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests

GENERAL = [
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
 ("SpirtTV","https://spirt007.github.io/Tvru/Rus.m3u"),
 ("VeronaTV","https://raw.githubusercontent.com/IPTVSHARED/VeronaTV/refs/heads/main/VeronaTV.m3u"),
 ("ZabavaTV","https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-full.m3u"),
 ("Axenov","https://iptv.axenov.dev/so"),
 ("Loganet","https://loganet.vercel.app/LoganetXStrawberry.m3u"),
]
ADULT = [
 ("Xteen18+TV","https://tinyurl.com/xteen18"),
 ("Sexture18+TV","https://tinyurl.com/sexture18"),
 ("Adultip18+TV","https://tinyurl.com/adultip18"),
]
BASE = Path("playlist.m3u")
LOGOS = Path("channel-logos.json")
OUT = Path("playlist-preview.m3u")
BASE_GROUPS = set()
REPORT = Path("preview-report.md")

REMOVE_WORDS={"hd","fhd","uhd","4k","8k","sd","hdtv","tv","телеканал","канал","channel","online","онлайн","live","лайв"}
MEDIA_EXT=re.compile(r"\.(mp4|mkv|avi|mov|m4v|webm|flv|wmv|mpg|mpeg|m4a|aac|flac)(?:$|[?#])",re.I)
RADIO_EXT=re.compile(r"\.(mp3|aacp?)(?:$|[?#])",re.I)
RESTRICTED=re.compile(r"(?:mdrm|access_token=|username=|password=|(?:[?&])cid=|(?:[?&])did=)",re.I)
ADULT_WORDS=re.compile(r"(?:18\+|xxx|porn|porno|erotic|erotica|playboy|penthouse|brazzers|hustler|dorcel|adult|взросл|эрот|порно|порн)",re.I)
BAD_GROUP=re.compile(r"(?:\btest\b|тест|🔺\s*info|тех\s*поддерж|поддержать|premium playlist|премиальный плейлист|not\s*24/7|no\s*24/7|не\s*24/7|catcast.*not\s*24/7)",re.I)
PAID_GROUP=re.compile(r"(?:\bwink\b|ott\s*club)",re.I)
VOD_PATH=re.compile(r"/(?:hls/)?(?:film|films|movie|movies|serials|series|multfilm)(?:/|$)",re.I)

def norm(value):
    value=unicodedata.normalize("NFKC",value or "").lower().replace("ё","е")
    value=re.sub(r"\([^)]*\)|\[[^]]*\]|\{[^}]*\}"," ",value)
    value=re.sub(r"https?://\S+"," ",value)
    value=re.sub(r"[^0-9a-zа-яё]+"," ",value,flags=re.I)
    return " ".join(w for w in value.split() if w not in REMOVE_WORDS).strip()

def channel_id(name):
    n=norm(name) or (name or "unknown").strip().lower()
    return "nurtv-"+hashlib.sha1(n.encode("utf-8")).hexdigest()[:16]

def attr(info,key):
    m=re.search(rf'{re.escape(key)}="([^"]*)"',info,re.I)
    return m.group(1).strip() if m else ""

def set_attr(info,key,value):
    pat=rf'{re.escape(key)}="[^"]*"'
    repl=f'{key}="{value}"'
    if re.search(pat,info,re.I):
        return re.sub(pat,lambda _:repl,info,count=1,flags=re.I)
    comma=info.rfind(",")
    return info[:comma]+" "+repl+info[comma:] if comma>=0 else info

def parse_m3u(text):
    entries=[]; pending=None
    for line in text.splitlines():
        line=line.rstrip("\r")
        if line.startswith("#EXTINF:"):
            pending=[line]
        elif pending is not None:
            if line.startswith("#"):
                pending.append(line)
            elif line.strip():
                entries.append({"block":pending,"url":line.strip()})
                pending=None
    return entries

def is_adult(info,group,source):
    return source in {x[0] for x in ADULT} or bool(ADULT_WORDS.search(info+" "+group))

def map_group(group,name,adult,source):
    if adult: return "Взрослые"
    g=(group or "").strip()
    if source=="ZabavaTV":
        return "Федеральные" if norm(g)=="основные" else "Региональные"
    if source=="TivinorTV" and norm(g)=="вещание":
        return "Эфирные"
    if source=="TivinorTV" and norm(g)=="шоу":
        return "Развлекательные"
    if g in BASE_GROUPS and g not in {"Разное","Без категории"}: return g
    x=norm(g)
    country_aliases = {
      "беларусь":"Беларусь","казахстан":"Казахстан","узбекистан":"Узбекистан",
      "азербайджан":"Азербайджан","армения":"Армения","грузия":"Грузия",
      "кыргызстан":"Кыргызстан","кыргыз":"Кыргызстан","молдавия":"Молдавия","молдова":"Молдавия",
      "таджикистан":"Таджикистан","туркменистан":"Туркменистан","турция":"Турция","индия":"Индия",
      "сша":"США","германия":"Германия","италия":"Италия","испания":"Испания","франция":"Франция",
      "польша":"Польша","нидерланды":"Нидерланды","австралия":"Австралия","австрия":"Австрия",
      "болгария":"Болгария","бразилия":"Бразилия","великобритания":"Великобритания","венгрия":"Венгрия",
      "греция":"Греция","израиль":"Израиль","иран":"Иран","канада":"Канада","мексика":"Мексика",
      "португалия":"Португалия","румыния":"Румыния","сербия":"Сербия","словакия":"Словакия",
      "хорватия":"Хорватия","чехия":"Чехия","латвия":"Латвия","литва":"Литва","эстония":"Эстония",
      "украина":"Украина","аргентина":"Аргентина","албания":"Албания","африка":"Африка",
      "арабские":"Арабские","азия":"Азия","латинская америка":"Латинская Америка",
      "остальная европа":"Остальная Европа"
    }
    for alias,target in country_aliases.items():
        if alias in x: return target
    if re.search(r"арабск",x): return "Арабские"
    if re.search(r"латинск.*америк",x): return "Латинская Америка"
    if re.search(r"остальн.*европ",x): return "Остальная Европа"
    if re.search(r"вещан|эфир",x): return "Эфирные"
    if re.search(r"шоу|плюсов",x): return "Развлекательные"
    if re.search(r"российск",x): return "Федеральные"
    if re.search(r"радио|radio",x): return "Радио"
    if re.search(r"федерал|общероссий|основные|эфир ru",x): return "Федеральные"
    if re.search(r"эфир|broadcast",x): return "Эфирные"
    if re.search(r"развлек|entertain",x): return "Развлекательные"
    if re.search(r"кино|film|movie|cinema|сериал",x): return "Кино и сериалы"
    if re.search(r"детск|мульт|cartoon|kids|baby",x): return "Детские"
    if re.search(r"музык|music|dance",x): return "Музыкальные"
    if re.search(r"спорт|sport|football",x): return "Спорт"
    if re.search(r"познав|наук|discovery|history|animal|travel|природ",x): return "Познавательные"
    if re.search(r"новост|news",x): return "Новости"
    if re.search(r"регион|город|област|местн",x): return "Региональные"
    if re.search(r"обществен|public",x): return "Общественные"
    if re.search(r"религ|православ|церков",x): return "Религиозные"
    if re.search(r"досуг|хобби",x): return "Досуг"
    if re.search(r"мужск",x): return "Мужские"
    n=norm(name)
    rules=[
      ("Новости",r"новост|news|rbc|cnn|bbc|rt\b|россия 24|мир 24"),
      ("Спорт",r"спорт|sport|матч|eurosport|football|ufc|tennis"),
      ("Детские",r"детск|мульт|cartoon|kids|disney|nick|gulli|tiji"),
      ("Музыкальные",r"музык|music|mtv|bridge|muz|шансон|radio record"),
      ("Кино и сериалы",r"кино|film|movie|cinema|сериал|viju|tv1000|дом кино|кинохит"),
      ("Познавательные",r"discovery|history|nat geo|animal|travel|познав|наука"),
      ("Религиозные",r"спас|союз|церков|православ"),
      ("Развлекательные",r"развлек|тнт|стс|пятниц|домашний|комеди|юмор"),
      ("Региональные",r"губерн|городск|област|регион|телеканал|телевидение|край"),
      ("Федеральные",r"первый канал|россия 1|россия 24|нтв|рен тв|пятый канал|тв центр|звезда"),
    ]
    for target,pattern in rules:
        if re.search(pattern,n,re.I): return target
    return "Разное"

def fetch_entries(name,url):
    r=requests.get(url,timeout=(15,70),headers={"User-Agent":"NurTV-Candidate-Builder/1.0"})
    r.raise_for_status()
    return parse_m3u(r.content[:40*1024*1024].decode("utf-8-sig",errors="replace")),r.url

def keep_entry(source,e):
    info=e["block"][0]; url=e["url"]; group=attr(info,"group-title")
    adult=is_adult(info,group,source)
    path=urlparse(url).path
    lower=(group+" "+info+" "+url).lower()
    if "127.0.0.1" in lower or "localhost" in lower or "/ace/getstream" in lower:
        return False,"local_ace"
    if RESTRICTED.search(url):
        return False,"restricted_credentials"
    if MEDIA_EXT.search(path) or MEDIA_EXT.search(url):
        return False,"direct_media_file"
    if RADIO_EXT.search(url) and not re.search(r"радио|radio",group+" "+info,re.I):
        return False,"audio_file_not_radio"
    if VOD_PATH.search(path):
        return False,"vod_url_path"
    if BAD_GROUP.search(group+" "+info):
        return False,"test_info_support_or_not24x7"
    if PAID_GROUP.search(group):
        return False,"paid_provider_group"
    if source=="KinomixTV" and norm(group) in {"фильмы","мультфильмы"}:
        return False,"kinomix_on_demand_group"
    if source=="VeronaTV" and "iptvplay" in group.lower():
        return False,"iptvplay_on_demand_group"
    if source=="ZunoTV" and re.search(r"кино уз party",norm(group)):
        return False,"zuno_movie_library"
    if source=="Sexture18+TV" and norm(group)!="взрослые":
        return False,"adult_vod_group"
    if source=="Adultip18+TV" and norm(group)!="каналы":
        return False,"adult_vod_group"
    # Adult sources Xteen contains only channel entries; the two mixed sources
    # are restricted to the explicit TV-channel groups above.
    return True,"adult_channel" if adult else "kept"

def main():
    # Preview only: no publication and no URL deduplication.
    base_text=BASE.read_text(encoding="utf-8-sig")
    base_lines=base_text.splitlines()
    header=next((x for x in base_lines if x.startswith("#EXTM3U")),'#EXTM3U url-tvg="https://nur-tv.github.io/1/epg.xml.gz"')
    base_entries=parse_m3u(base_text)
    global BASE_GROUPS
    BASE_GROUPS={attr(e["block"][0],"group-title") or "Без категории" for e in base_entries}
    logo_map=json.loads(LOGOS.read_text(encoding="utf-8"))
    grouped=collections.defaultdict(list)
    base_order=[]
    for e in base_entries:
        info=e["block"][0]; group=attr(info,"group-title") or "Без категории"
        if group not in base_order: base_order.append(group)
        grouped[group].append(e)

    report=[]; source_stats=[]; imported=0
    for source,url in GENERAL+ADULT:
        try:
            entries,final_url=fetch_entries(source,url)
        except Exception as exc:
            source_stats.append((source,0,0,0,str(exc)))
            continue
        kept=0; dropped=collections.Counter(); added_groups=collections.Counter()
        for e in entries:
            ok,reason=keep_entry(source,e)
            if not ok:
                dropped[reason]+=1
                continue
            info=e["block"][0]
            name=info.rsplit(",",1)[-1].strip()
            adult=is_adult(info,attr(info,"group-title"),source)
            group=map_group(attr(info,"group-title"),name,adult,source)
            info=set_attr(info,"group-title",group)
            cid=channel_id(name)
            info=set_attr(info,"tvg-id",cid)
            logo=logo_map.get(cid,"")
            if logo: info=set_attr(info,"tvg-logo",logo)
            e["block"][0]=info
            grouped[group].append(e)
            if group not in base_order: base_order.append(group)
            kept+=1; imported+=1; added_groups[group]+=1
        source_stats.append((source,len(entries),kept,sum(dropped.values()),""))
        report.append(f"### {source}\n- Получено: {len(entries)}; добавлено в черновик: {kept}; исключено: {sum(dropped.values())}\n- Причины исключения: "+(", ".join(f"{k}={v}" for k,v in dropped.most_common()) or "нет")+"\n- Группы добавленных записей: "+(", ".join(f"{k}={v}" for k,v in added_groups.most_common()) or "нет"))
    # Keep the original baseline group sequence first, then any new canonical groups.
    preferred_order = [
      "Федеральные","Развлекательные","Кино и сериалы","Детские","Музыкальные","Спорт",
      "Познавательные","Новости","Региональные","Эфирные","Религиозные","Общественные",
      "Мужские","Досуг","Культура","Христианские","Хобби и увлечения","Медитативные","Радио",
      "Беларусь","Казахстан","Узбекистан","Азербайджан","Армения","Грузия","Кыргызстан",
      "Молдавия","Таджикистан","Туркменистан","Турция","Индия","Австралия","Австрия","Азия",
      "Албания","Арабские","Аргентина","Африка","Болгария","Бразилия","Великобритания",
      "Венгрия","Германия","Греция","Израиль","Иран","Испания","Италия","Канада",
      "Латинская Америка","Мексика","Нидерланды","Остальная Европа","Польша","Португалия",
      "Румыния","Сербия","Словакия","США","Франция","Хорватия","Чехия","Латвия","Литва",
      "Эстония","Украина","Разное","Без категории","Взрослые"
    ]
    order=[g for g in preferred_order if g in grouped]
    for g in base_order:
        if g in grouped and g not in order: order.append(g)
    for g in sorted(grouped):
        if g not in order: order.append(g)
    lines=[header]
    group_counts={}
    for group in order:
        for e in grouped.get(group,[]):
            block=e["block"][:]
            block[0]=set_attr(block[0],"group-title",group)
            lines.extend(block)
            lines.append(e["url"])
            group_counts[group]=group_counts.get(group,0)+1
    OUT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    total=sum(group_counts.values())
    report_head=[
      "# Черновая сборка Nur-TV — без публикации",
      "",
      "Основа — восстановленный исходный плейлист. Альтернативные потоки и повторы намеренно сохранены; дедупликация не выполнялась.",
      "Исключались прямые файлы VOD, известные URL-пути медиатек, локальные AceStream-ссылки, явные тестовые/информационные записи и группы платных Wink/OTT Club. Это предварительная фильтрация, не подтверждение воспроизведения.",
      f"- База: {len(base_entries)} записей",
      f"- Добавлено из источников: {imported}",
      f"- Всего в черновике: {total}",
      f"- Групп: {len(group_counts)}",
      f"- Уникальных URL: {len(set(e['url'] for g in grouped.values() for e in g))} (повторы в M3U сохранены)",
      "",
      "## Статистика по источникам",
      "",
      "| Источник | Получено | Добавлено | Исключено | Ошибка |",
      "|---|---:|---:|---:|---|",
    ]
    for s,n,k,d,err in source_stats:
        report_head.append(f"| {s} | {n} | {k} | {d} | {err or '—'} |")
    report_head += ["","## Состав групп",""]+[f"- {g}: {n}" for g,n in sorted(group_counts.items(),key=lambda x:(order.index(x[0]),x[0]))]
    REPORT.write_text("\n".join(report_head+["","## Фильтрация по источникам",""]+report)+"\n",encoding="utf-8")
    print("\n".join(report_head+["","## Фильтрация по источникам",""]+report))

if __name__=="__main__":
    # Candidate only: this script never writes playlist.m3u or commits to main.
    main()
