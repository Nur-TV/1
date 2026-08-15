$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Apktool = Join-Path $Root 'apktool_3.0.3.jar'
$OriginalApk = Join-Path $Root 'dTelevizo.apk'
$Signed = Join-Path $Root 'Televizo_NurTV.apk'
$Unsigned = Join-Path $Root 'Televizo_NurTV_unsigned.apk'
$Aligned = Join-Path $Root 'Televizo_NurTV_aligned.apk'
$Keystore = Join-Path $Root 'nurtv-release.keystore'
$Project = Join-Path $Root 'Televizo_NurTV'
$Res1Zip = Join-Path $Root '_res1.zip'
$Res1Work = Join-Path $Root '_res1_work'
$Res1New = Join-Path $Root '_res1_new.zip'
$M3U = Join-Path $Root '_nurtv_playlist.m3u'

function Fail([string]$m) { throw $m }
function Need([string]$p,[string]$w) { if (!(Test-Path -LiteralPath $p)) { Fail ("Missing {0}: {1}" -f $w,$p) } }
function SqlQ([string]$s) { if ($null -eq $s) { return "NULL" }; return "'" + $s.Replace("'","''") + "'" }

Write-Host ''
Write-Host '============================================================'
Write-Host '             NUR-TV TELE VIZO FINAL BUILDER'
Write-Host '============================================================'
Write-Host ''

Need $OriginalApk 'dTelevizo.apk'
Need $Apktool 'apktool_3.0.3.jar'

$JavaExe=$null;$JavaHome=$null
$c=Get-Command java.exe -ErrorAction SilentlyContinue
if($c){$JavaExe=$c.Source;$JavaHome=Split-Path (Split-Path $JavaExe -Parent) -Parent}
if(!$JavaExe){$f=Get-ChildItem 'C:\Program Files\Eclipse Adoptium\jdk-21*\bin\java.exe' -ErrorAction SilentlyContinue|Select-Object -First 1;if($f){$JavaExe=$f.FullName;$JavaHome=Split-Path (Split-Path $JavaExe -Parent) -Parent}}
if(!$JavaExe){Fail 'Java 21 not found.'}
$env:JAVA_HOME=$JavaHome;$env:Path=(Join-Path $JavaHome 'bin')+';'+$env:Path
Write-Host ("Java: {0}" -f $JavaExe)
& $JavaExe -jar $Apktool --version
if($LASTEXITCODE -ne 0){Fail 'Apktool did not start.'}

foreach($p in @($Project,$Unsigned,$Aligned,$Signed,$Res1Zip,$Res1Work,$Res1New,$M3U)){if(Test-Path -LiteralPath $p){Remove-Item -LiteralPath $p -Recurse -Force}}

Write-Host ''
Write-Host '1/6  DECODING dTelevizo.apk'
& $JavaExe -jar $Apktool d -f $OriginalApk -o $Project
if($LASTEXITCODE -ne 0){Fail 'Apktool decode failed.'}

Write-Host ''
Write-Host '2/6  BUILDING NUR-TV PLAYLIST + EPG SEED DATABASES'
$res1=Join-Path $Project 'assets\res1'
Need $res1 'assets/res1'
Copy-Item -LiteralPath $res1 -Destination $Res1Zip -Force
New-Item -ItemType Directory -Path $Res1Work -Force | Out-Null
Expand-Archive -LiteralPath $Res1Zip -DestinationPath $Res1Work -Force
$dbDir=Join-Path $Res1Work 'databases'
Need $dbDir 'res1 databases'

Write-Host 'Downloading current Nur-TV playlist...'
Invoke-WebRequest -Uri 'https://nur-tv.github.io/1/playlist.m3u' -OutFile $M3U -UseBasicParsing -Headers @{ 'User-Agent'='Mozilla/5.0 Nur-TV Televizo Builder' }
Need $M3U 'downloaded Nur-TV playlist'

if(!(Test-Path -LiteralPath "$env:WINDIR\System32\winsqlite3.dll")){Fail 'winsqlite3.dll was not found in Windows System32.'}

Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class WinSQLite {
    [DllImport("winsqlite3.dll", CharSet=CharSet.Unicode)]
    static extern int sqlite3_open16(string filename, out IntPtr db);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern int sqlite3_close(IntPtr db);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern int sqlite3_exec(IntPtr db, IntPtr sql, IntPtr cb, IntPtr arg, out IntPtr err);
    [DllImport("winsqlite3.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern void sqlite3_free(IntPtr p);
    public static void Exec(string file, string sql) {
        IntPtr db; int rc=sqlite3_open16(file,out db);
        if(rc!=0) throw new Exception("sqlite3_open failed: "+rc);
        try {
            byte[] b=Encoding.UTF8.GetBytes(sql+"\0");
            IntPtr p=Marshal.AllocHGlobal(b.Length); Marshal.Copy(b,0,p,b.Length);
            try { IntPtr err; rc=sqlite3_exec(db,p,IntPtr.Zero,IntPtr.Zero,out err); if(rc!=0){string msg=err!=IntPtr.Zero?Marshal.PtrToStringUni(err):"unknown SQLite error"; if(err!=IntPtr.Zero)sqlite3_free(err); throw new Exception("sqlite3_exec failed: "+rc+" "+msg);}} finally {Marshal.FreeHGlobal(p);}
        } finally {sqlite3_close(db);}
    }
}
'@

$lines=Get-Content -LiteralPath $M3U -Encoding UTF8
$items=New-Object System.Collections.Generic.List[object]
$cur=$null
foreach($line0 in $lines){
    $line=$line0.Trim(); if(!$line){continue}
    if($line.StartsWith('#EXTINF:')){$cur=$line;continue}
    if($line.StartsWith('#')){continue}
    if($cur -and ($line.StartsWith('http://') -or $line.StartsWith('https://') -or $line.StartsWith('rtmp://'))){
        $info=$cur;$comma=$info.IndexOf(',');$name=if($comma -ge 0){$info.Substring($comma+1).Trim()}else{'Без названия'}
        $g='Без группы';$gm=[regex]::Match($info,'group-title="([^"]*)"');if($gm.Success -and $gm.Groups[1].Value.Trim()){$g=$gm.Groups[1].Value.Trim()}
        $tm=[regex]::Match($info,'tvg-id="([^"]*)"');$identity=if($tm.Success -and $tm.Groups[1].Value.Trim()){$tm.Groups[1].Value.Trim()}else{($name.ToLower() -replace '\s+',' ').Trim()}
        $lm=[regex]::Match($info,'tvg-logo="([^"]*)"');$logo=if($lm.Success){$lm.Groups[1].Value}else{''}
        $items.Add([pscustomobject]@{Name=$name;Group=$g;Identity=$identity;Logo=$logo;Url=$line});$cur=$null
    }
}
if($items.Count -eq 0){Fail 'Nur-TV playlist downloaded but no channels were parsed.'}

$playlistDb=Join-Path $dbDir 'playlist-data';$epgDb=Join-Path $dbDir 'epg-data'
$sql="PRAGMA foreign_keys=OFF; BEGIN; DELETE FROM channels; DELETE FROM groups; DELETE FROM playlists; DELETE FROM sqlite_sequence WHERE name IN ('channels','groups','playlists');"
$sql += " INSERT INTO playlists(id,name,source,user_agent,catchup_type,catchup_days_manual_max,catchup_days_playlist_max,is_enabled,is_load_epg,is_default,update_frequency,last_updated,xc_login,xc_password,xc_stream_type,xc_channels,xc_movies,xc_series,xc_timezone,use_all_epgs,selected_epgs,cached_date,update_failed) VALUES(1,"+(SqlQ 'Nur-TV')+","+(SqlQ 'https://nur-tv.github.io/1/playlist.m3u')+",'',0,0,3,1,1,1,1,0,'','',0,0,0,0,'',1,'[]',0,0);"
$sql += " INSERT INTO groups(id,playlist_id,group_name,channel_count,type) VALUES(1,1,'televizo-all',"+$items.Count+",0),(2,1,'televizo-recently-watched',0,0),(3,1,'televizo-fav',0,0);"
$groups=@{};$gid=4
foreach($x in $items){if(!$groups.ContainsKey($x.Group)){$groups[$x.Group]=$gid;$sql += " INSERT INTO groups(id,playlist_id,group_name,channel_count,type) VALUES($gid,1,"+(SqlQ $x.Group)+",0,0);";$gid++}}
foreach($k in $groups.Keys){$cnt=($items|Where-Object Group -eq $k).Count;$sql += " UPDATE groups SET channel_count=$cnt WHERE id=$($groups[$k]);"}
$n=1
foreach($x in $items){
    $gjson='["'+$x.Group.Replace('"','\"').Replace('\','\\')+'"]'
    $sql += " INSERT INTO channels(playlist_id,identity,number,group_number,name,item_type,shift,source,image,playlist_user_agent,http_referer,catchup_days,catchup_type,catchup_source,playlist_name,playlist_source,playlist_xc_timezone,group_name,group_names_found_for_channel,xc_series_id,xc_vod_id,xc_last_modified,xc_rating_5based,xc_rating) VALUES(1,"+(SqlQ $x.Identity)+",$n,0,"+(SqlQ $x.Name)+",0,0,"+(SqlQ $x.Url)+","+(SqlQ $x.Logo)+",'','',0,0,'','Nur-TV','https://nur-tv.github.io/1/playlist.m3u','',"+(SqlQ $x.Group)+","+(SqlQ $gjson)+",0,0,'',0.0,'');"
    $n++
}
$sql += " UPDATE sqlite_sequence SET seq=$($items.Count) WHERE name='channels'; UPDATE sqlite_sequence SET seq=$($gid-1) WHERE name='groups'; UPDATE sqlite_sequence SET seq=1 WHERE name='playlists'; COMMIT;"
[WinSQLite]::Exec($playlistDb,$sql)

$epgSql="PRAGMA foreign_keys=OFF; BEGIN; DELETE FROM epg_programs; DELETE FROM channel_names; DELETE FROM channel_identifiers; DELETE FROM epg_sources; DELETE FROM sqlite_sequence WHERE name IN ('epg_programs','channel_names','channel_identifiers','epg_sources');"
$epgSql += " INSERT INTO epg_sources(id,name,url,update_frequency,last_updated,is_active,time_offset,cached_date,update_failed) VALUES(1,'Nur-TV EPG','https://nur-tv.github.io/1/epg.xml.gz',1,0,1,0,0,0);"
$eid=1
foreach($x in $items){$epgSql += " INSERT INTO channel_identifiers(id,channel_identity,source_id,channel_icon) VALUES($eid,"+(SqlQ $x.Identity)+",1,"+(SqlQ $x.Logo)+");";$epgSql += " INSERT INTO channel_names(channel_id,channel_name) VALUES($eid,"+(SqlQ $x.Name)+");";$eid++}
$epgSql += " UPDATE sqlite_sequence SET seq=$($items.Count) WHERE name='channel_identifiers'; UPDATE sqlite_sequence SET seq=$($items.Count) WHERE name='channel_names'; UPDATE sqlite_sequence SET seq=1 WHERE name='epg_sources'; COMMIT;"
[WinSQLite]::Exec($epgDb,$epgSql)

foreach($name in @('playlist-data-shm','playlist-data-wal','epg-data-shm','epg-data-wal')){$p=Join-Path $dbDir $name;if(Test-Path -LiteralPath $p){Remove-Item -LiteralPath $p -Force}}
Write-Host ("Nur-TV playlist channels inserted: {0}" -f $items.Count)
Write-Host ("Nur-TV EPG channel identifiers inserted: {0}" -f $items.Count)

if(Test-Path -LiteralPath $Res1New){Remove-Item -LiteralPath $Res1New -Force}
Compress-Archive -Path (Join-Path $Res1Work '*') -DestinationPath $Res1New -CompressionLevel Optimal -Force
Copy-Item -LiteralPath $Res1New -Destination $res1 -Force

Write-Host ''
Write-Host '3/6  REMOVING ALL GoblinMini COMPONENTS'
$oo=Get-ChildItem -LiteralPath $Project -Recurse -Filter 'OoOo.smali'|Select-Object -First 1
if($oo){
  $sm=[System.IO.File]::ReadAllText($oo.FullName)
  $methodRx='(?ms)^\.method\s+([^\r\n]+)\s*$.*?^\.end method\s*$'
  $matches=[regex]::Matches($sm,$methodRx);$changed=$false
  foreach($m in $matches){
    $body=$m.Value
    if($body -notmatch '(?i)GoblinMini|SocksFactory|telegram|Поделка'){continue}
    $header=($body -split "`r?`n")[0]
    $ret='V';$rm=[regex]::Match($header,'\)([VZBSCIJFD]|L[^;]+;|\[[^\r\n]+)$');if($rm.Success){$ret=$rm.Groups[1].Value}
    $reg=[regex]::Match($body,'(?m)^\s*\.(locals|registers)\s+\d+\s*$');$directive=if($reg.Success){$reg.Value.Trim()}else{'.registers 1'}
    if($ret -eq 'V'){$replacement=$header+"`r`n    "+$directive+"`r`n    return-void`r`n.end method"}
    elseif($ret -match '^[ZBSCI]$'){$replacement=$header+"`r`n    "+$directive+"`r`n    const/4 v0, 0x0`r`n    return v0`r`n.end method"}
    elseif($ret -eq 'J'){$replacement=$header+"`r`n    "+$directive+"`r`n    const-wide/16 v0, 0x0`r`n    return-wide v0`r`n.end method"}
    elseif($ret -eq 'F'){$replacement=$header+"`r`n    "+$directive+"`r`n    const/4 v0, 0x0`r`n    return v0`r`n.end method"}
    elseif($ret -eq 'D'){$replacement=$header+"`r`n    "+$directive+"`r`n    const-wide/16 v0, 0x0`r`n    return-wide v0`r`n.end method"}
    else{$replacement=$header+"`r`n    "+$directive+"`r`n    const/4 v0, 0x0`r`n    return-object v0`r`n.end method"}
    $sm=$sm.Replace($body,$replacement);$changed=$true
  }
  if($changed){[System.IO.File]::WriteAllText($oo.FullName,$sm,(New-Object System.Text.UTF8Encoding($false)));Write-Host 'GoblinMini methods disabled.'}
}
# Remove obvious GoblinMini preference/resource files and blank hard-coded GoblinMini labels anywhere in decoded XML resources.
Get-ChildItem -LiteralPath $Project -Recurse -File | ForEach-Object {
  $ext=$_.Extension.ToLowerInvariant()
  if($ext -in '.xml','.smali','.json','.txt'){try{$t=[System.IO.File]::ReadAllText($_.FullName);if($t -match '(?i)GoblinMini|SocksFactory'){$t=[regex]::Replace($t,'(?i)GoblinMini|SocksFactory','');[System.IO.File]::WriteAllText($_.FullName,$t,(New-Object System.Text.UTF8Encoding($false)))}}catch{}}
}
$gxml=Join-Path $Project 'assets\res1\shared_prefs\GoblinMini.xml';if(Test-Path -LiteralPath $gxml){Remove-Item -LiteralPath $gxml -Force;Write-Host 'GoblinMini shared preferences removed.'}

Write-Host ''
Write-Host '4/6  BUILDING APK'
& $JavaExe -jar $Apktool b $Project -o $Unsigned
if($LASTEXITCODE -ne 0){Fail 'Apktool build failed.'}

$zipalign=$null;$apksigner=$null;$sdkCandidates=@();if($env:ANDROID_SDK_ROOT){$sdkCandidates+=$env:ANDROID_SDK_ROOT};if($env:ANDROID_HOME){$sdkCandidates+=$env:ANDROID_HOME};if($env:LOCALAPPDATA){$sdkCandidates+=(Join-Path $env:LOCALAPPDATA 'Android\Sdk')}
foreach($sdk in ($sdkCandidates|Where-Object{$_}|Select-Object -Unique)){$bt=Join-Path $sdk 'build-tools';if(Test-Path $bt){foreach($v in (Get-ChildItem $bt -Directory|Sort-Object Name -Descending)){if(!$zipalign){$z=Join-Path $v.FullName 'zipalign.exe';if(Test-Path $z){$zipalign=$z}};if(!$apksigner){$a=Join-Path $v.FullName 'apksigner.bat';if(Test-Path $a){$apksigner=$a}};if($zipalign -and $apksigner){break}}};if($zipalign -and $apksigner){break}}

Write-Host ''
Write-Host '5/6  SIGNING APK'
if(!(Test-Path -LiteralPath $Keystore)){& keytool -genkeypair -v -keystore $Keystore -alias nurtv -keyalg RSA -keysize 2048 -validity 10000 -storepass nurtv123 -keypass nurtv123 -dname 'CN=Nur-TV, OU=Nur-TV, O=Nur-TV, C=RU';if($LASTEXITCODE -ne 0){Fail 'Could not create signing key.'}}
if($zipalign -and $apksigner){& $zipalign -f -p 4 $Unsigned $Aligned;if($LASTEXITCODE -ne 0){Fail 'zipalign failed.'};& $apksigner sign --ks $Keystore --ks-key-alias nurtv --ks-pass pass:nurtv123 --key-pass pass:nurtv123 --out $Signed $Aligned;if($LASTEXITCODE -ne 0){Fail 'apksigner failed.'}}else{& jarsigner -verbose -sigalg SHA256withRSA -digestalg SHA-256 -keystore $Keystore -storepass nurtv123 -keypass nurtv123 -signedjar $Signed $Unsigned nurtv;if($LASTEXITCODE -ne 0){Fail 'jarsigner failed.'}}

Write-Host ''
Write-Host '6/6  VERIFYING APK'
if($apksigner){& $apksigner verify --verbose $Signed;if($LASTEXITCODE -ne 0){Fail 'Final APK signature verification failed.'}}
Write-Host ''
Write-Host '============================================================'
Write-Host '                         SUCCESS'
Write-Host '============================================================'
Write-Host ("Ready APK: {0}" -f $Signed)
Write-Host ("Size: {0} bytes" -f (Get-Item -LiteralPath $Signed).Length)
Read-Host 'Press Enter to close'
