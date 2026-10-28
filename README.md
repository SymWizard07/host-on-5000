# host-on-5000

Right-click any file in Explorer and host it on a temporary web server.

- **Port:** 5000  
- **Timeout:** 5 minutes (then auto-stops)  
- **Scope:** only that file (not the whole folder)  
- **Single instance:** hosting another file stops the previous server  

## Install

```powershell
cd $env:USERPROFILE\source\repos\host-on-5000
.\install.ps1
```

Requires Python 3 on your PATH (`python` or the `py` launcher).

## Use

1. Right-click a file → **Host on web server (port 5000)**
2. A console shows local and LAN URLs, e.g.  
   `http://127.0.0.1:5000/myfile.zip`  
   `http://192.168.x.x:5000/myfile.zip`
3. `/` serves the same file.
4. Forward **TCP 5000** on your router if sharing over the internet.
5. Ctrl+C stops early; otherwise it exits after 5 minutes.

## Uninstall

```powershell
.\uninstall.ps1
```

## Manual run

```powershell
.\host.cmd "C:\path\to\file.zip"
# or
python host_file.py "C:\path\to\file.zip" --port 5000 --timeout 300
```
