"""
BunLauncher — Полностью оффлайн лаунчер Minecraft.
PySide6 (Qt6) — прозрачный сайдбар, анимации, расширенные настройки.
"""
import json, os, re, sys, shutil, platform, subprocess
import tarfile, lzma, threading, math, time
import webbrowser, tempfile, signal
try:
    import psutil
except ImportError:
    psutil = None
import random as _rnd
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QProgressBar, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QSizePolicy, QDialog, QComboBox, QCheckBox, QMessageBox,
    QFileDialog, QGridLayout, QScrollArea, QSpinBox, QTabWidget,
    QSlider, QTextEdit, QListWidget
)
from PySide6.QtCore import (
    Qt, Signal, QThread, QTimer, QPropertyAnimation,
    QEasingCurve, QSequentialAnimationGroup, QParallelAnimationGroup,
    QRect, QPoint, Property, QPointF
)
from PySide6.QtGui import (
    QPixmap, QFont, QIcon, QColor, QPainter, QBrush, QPen,
    QLinearGradient, QPainterPath
)

# ── Пути ──
if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys._MEIPASS)
else:
    DATA_DIR = Path(__file__).parent

BUNDLE_ARCHIVE = DATA_DIR / "bundle.tar.xz"
BUNDLE_DIR = DATA_DIR / "bundle"
ASSETS_DIR = DATA_DIR / "assets"
DEFAULT_GAME_DIR = Path(os.environ.get("APPDATA", Path.home())) / "BunLauncher"


# ══════════════════════════════════
#  Config (расширенный)
# ══════════════════════════════════
DEFAULT_CFG = {
    "username": "Player",
    "memory_mb": 4096,
    "width": 854,
    "height": 480,
    "jvm_args": "",
    "fullscreen": False,
    "game_dir": "",
    "java_path": "",
    "close_on_launch": False,
    "auto_connect": False,
    "server_ip": "",
    "show_console": False,
    "check_files": True,
    "max_threads": 8,
}

def load_cfg(gd):
    p = gd / "launcher_config.json"
    d = {}
    if p.exists():
        try: d = json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return {**DEFAULT_CFG, **d}

def save_cfg(gd, cfg):
    p = gd / "launcher_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def effective_game_dir(cfg):
    gd = cfg.get("game_dir", "").strip()
    return Path(gd) if gd else DEFAULT_GAME_DIR

def detect_java():
    """Пробуем найти Java автоматически."""
    candidates = []
    # В бандле
    for jd in (DEFAULT_GAME_DIR / "runtime").glob("jre-*"):
        jb = jd / "bin" / ("java.exe" if platform.system() == "Windows" else "java")
        if jb.exists(): candidates.append(str(jb))
    # JAVA_HOME
    jh = os.environ.get("JAVA_HOME")
    if jh:
        jb = Path(jh) / "bin" / ("java.exe" if platform.system() == "Windows" else "java")
        if jb.exists(): candidates.append(str(jb))
    # PATH
    for p in os.environ.get("PATH", "").split(os.pathsep):
        jb = Path(p) / ("java.exe" if platform.system() == "Windows" else "java")
        if jb.exists(): candidates.append(str(jb))
    return candidates


# ══════════════════════════════════
#  Поиск версии для запуска
# ══════════════════════════════════
def find_game_version(game_dir, hint=""):
    """Находит реальный ID версии в versions/.
    Приоритет: точное совпадение hint → папка с 'neoforge' → любая папка с .json."""
    vdir = game_dir / "versions"
    if not vdir.exists():
        return hint

    # 1) Точное совпадение hint
    if hint and (vdir / hint / f"{hint}.json").exists():
        return hint

    # 2) Папка с 'neoforge' в имени
    for d in sorted(vdir.iterdir(), reverse=True):
        if d.is_dir() and "neoforge" in d.name.lower():
            if (d / f"{d.name}.json").exists():
                return d.name

    # 3) Любая папка с JSON (fallback)
    for d in sorted(vdir.iterdir(), reverse=True):
        if d.is_dir() and (d / f"{d.name}.json").exists():
            return d.name

    return hint


# ══════════════════════════════════
#  Офлайн установка
# ══════════════════════════════════
def install_from_bundle(game_dir, progress_cb=None):
    cb = progress_cb or (lambda *a: None)
    if BUNDLE_ARCHIVE.exists():
        cb("Установка файлов игры...", 0)
        game_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(BUNDLE_ARCHIVE, "r:xz") as tar:
            members = tar.getmembers()
            total = len(members)
            for i, m in enumerate(members):
                try: tar.extract(m, game_dir)
                except: pass
                if (i+1) % 100 == 0 or i+1 == total:
                    pct = (i+1)/total*100
                    cb(f"Установка... {int(pct)}%", pct)
    elif BUNDLE_DIR.exists():
        files = [f for f in BUNDLE_DIR.rglob("*") if f.is_file()]
        total = len(files)
        cb("Копирование файлов игры...", 0)
        for i, src in enumerate(files):
            dst = game_dir / src.relative_to(BUNDLE_DIR)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists(): shutil.copy2(src, dst)
            if (i+1) % 50 == 0 or i+1 == total:
                pct = (i+1)/total*100
                cb(f"Копирование... {int(pct)}%", pct)
    else:
        raise RuntimeError("Ни bundle.tar.xz, ни bundle/ не найдены")

    manifest = json.loads((game_dir / "manifest.json").read_text(encoding="utf-8"))
    mc_ver = manifest.get("minecraft_version")
    java_ver = manifest.get("java_version")
    neo_id_hint = manifest.get("_neo_id", f"neoforge-{manifest.get('neoforge_version')}")
    neo_id = find_game_version(game_dir, neo_id_hint)
    jd = game_dir / "runtime" / f"jre-{java_ver}"
    jb = jd / "bin" / ("java.exe" if platform.system() == "Windows" else "java")
    if not jb.exists(): raise RuntimeError(f"Java не найдена: {jb}")
    (game_dir / ".installed").write_text("ok", encoding="utf-8")
    return neo_id, str(jb), mc_ver

def is_installed(gd): return (gd / ".installed").exists()


# ══════════════════════════════════
#  Запуск игры
# ══════════════════════════════════
def launch_game(cfg, game_dir, java_path, neo_id, mc_version):
    # Перепроверяем neo_id — ищем реальную папку
    neo_id = find_game_version(game_dir, neo_id)
    ver_json = game_dir / "versions" / neo_id / f"{neo_id}.json"
    if not ver_json.exists():
        vdir = game_dir / "versions"
        found = list(vdir.iterdir()) if vdir.exists() else []
        raise FileNotFoundError(
            f"Version JSON не найден: {ver_json}\n"
            f"Содержимое versions/: {[d.name for d in found]}"
        )
    libs = game_dir/"libraries"; assets = game_dir/"assets"
    natives = game_dir/"versions"/neo_id/"natives"
    neo_j = json.loads(ver_json.read_text(encoding="utf-8"))

    # Пробуем загрузить vanilla JSON отдельно (если neo_id != mc_version)
    van_j = {}
    if neo_id != mc_version:
        try: van_j = json.loads((game_dir/"versions"/mc_version/f"{mc_version}.json").read_text(encoding="utf-8"))
        except: pass

    mc = neo_j.get("mainClass", "cpw.mods.bootstraplauncher.BootstrapLauncher")
    ai = neo_j.get("assetIndex",{}).get("id") or van_j.get("assetIndex",{}).get("id","17")

    # Classpath: собираем ВСЕ jar из libraries/ рекурсивно и убираем дубликаты старых версий
    cp_p = []
    lib_map = {}  # "package/name" -> {"version": (tuple), "path": str}

    if libs.exists():
        for jar in libs.rglob("*.jar"):
            s = str(jar)
            rel_path = jar.relative_to(libs).parts
            if len(rel_path) >= 3:
                name = rel_path[-3]
                version_str = rel_path[-2]
                pkg = "/".join(rel_path[:-3])
                
                # Имя файла обычно: name-version[-classifier].jar
                prefix = f"{name}-{version_str}"
                classifier = ""
                # Если файл строго начинается с prefix
                if jar.name.startswith(prefix) and jar.name.endswith(".jar"):
                    classifier = jar.name[len(prefix):-4] # может быть пустой, или "-natives-windows", и т.д.
                    
                uid = f"{pkg}/{name}{classifier}"
                
                def parse_ver(v):
                    nums = re.findall(r'\d+', v)
                    return tuple(int(n) for n in nums) if nums else (0,)

                ver_tuple = parse_ver(version_str)
                
                if uid in lib_map:
                    if ver_tuple > lib_map[uid]["version"]:
                        lib_map[uid] = {"version": ver_tuple, "path": s}
                else:
                    lib_map[uid] = {"version": ver_tuple, "path": s}
            else:
                if s not in cp_p:
                    cp_p.append(s)

        for uid, data in lib_map.items():
            if data["path"] not in cp_p:
                if "commons-collections4" not in data["path"]:
                    cp_p.append(data["path"])
                    
        cp_p = [p for p in cp_p if "commons-collections4" not in p]
        cp_p.sort()

    # НЕ добавляем версионный jar (neoforge-21.1.216.jar из versions/) на classpath —
    # его содержимое уже есть в client-srg.jar + neoforge-client.jar

    # Восстанавливаем universal.jar если он был переименован ранее
    universal_bak = libs / "net" / "neoforged" / "neoforge" / neo_j.get("id","21.1.216").replace("neoforge-","") / f"{neo_id}-universal.jar.bak"
    universal_jar = universal_bak.with_suffix("") if universal_bak.suffix == ".bak" else universal_bak
    # Пробуем путь напрямую
    for p in libs.rglob(f"{neo_id}-universal.jar.bak"):
        try: p.rename(p.with_name(p.name.replace(".jar.bak", ".jar")))
        except: pass

    sep = ";" if platform.system()=="Windows" else ":"
    cp = sep.join(cp_p)
    
    # ═══════════════════════════════════════════════════════════════════
    # ignoreList — КРИТИЧЕСКИ ВАЖНО для Java 21 + NeoForge!
    # BootstrapLauncher сканирует libraryDirectory и добавляет найденные JAR
    # в boot module layer. Если два JAR-а определяют один и тот же модуль
    # (например, neoforge-client.jar и neoforge-universal.jar оба → "neoforge"),
    # Java 21 ломается с ResolutionException.
    # ignoreList использует substring matching по ИМЕНИ файла.
    # JAR-ы из ignoreList не попадут в boot layer, но FML загрузит их
    # сам через свои локаторы в правильный GAME layer.
    # ═══════════════════════════════════════════════════════════════════
    
    # Извлекаем neoform version для паттерна client JAR-ов
    neoform_ver = neo_j.get("arguments",{}).get("game",[])
    neoform_str = ""
    for i, item in enumerate(neoform_ver):
        if item == "--fml.neoFormVersion" and i+1 < len(neoform_ver):
            neoform_str = neoform_ver[i+1]
            break
    if not neoform_str:
        neoform_str = "20240808.144430"  # fallback
    mc_version = neo_j.get("inheritsFrom", "1.21.1")
    
    custom_ignore = {
        "client-extra",                                      # client-extra JAR-ы
        f"{neo_id}.jar",                                     # версионный JAR из versions/
        f"{neo_id}-universal",                               # neoforge-universal → загрузится через FML PathBasedLocator
        f"{neo_id}-client",                                  # neoforge-client → загрузится через FML production client provider
        f"client-{mc_version}-{neoform_str}",                # ВСЕ vanilla client JAR-ы (slim, srg, extra)
        "commons-collections4",                              # конфликт с glsl.transformer
    }
    
    args = [
        f"-Xmx{cfg.get('memory_mb',4096)}M",
        f"-Xms{cfg.get('memory_mb',4096)}M",
        
        # --- ОПТИМИЗАЦИЯ JVM ДЛЯ МАКСИМАЛЬНОГО ФПС ---
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        "-XX:G1NewSizePercent=30",
        "-XX:G1MaxNewSizePercent=40",
        "-XX:G1HeapRegionSize=8M",
        "-XX:G1ReservePercent=20",
        "-XX:G1HeapWastePercent=5",
        "-XX:G1MixedGCCountTarget=4",
        "-XX:InitiatingHeapOccupancyPercent=15",
        "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5",
        "-XX:SurvivorRatio=32",
        "-XX:+PerfDisableSharedMem",
        "-XX:MaxTenuringThreshold=1",
        
        f"-Djava.library.path={natives}",
        "-Dcpw.mods.modlauncher.securejarhandler.AllowDuplicatePackages=true",
    ]
    jx = cfg.get("jvm_args","").strip()
    if jx:
        for jxx in jx.split():
            if jxx.startswith("-DignoreList="):
                # Собираем записи из конфига
                custom_ignore.update(jxx.split("=",1)[1].split(","))
            else:
                args.append(jxx)
    auth_uuid = "00000000-0000-0000-0000-000000000000"
    auth_name = cfg.get("username", "Player")
    def sub(s):
        for k,v in [("${version_name}",neo_id),("${game_directory}",str(game_dir)),
                     ("${assets_root}",str(assets)),("${assets_index_name}",ai),
                     ("${library_directory}",str(libs)),("${classpath_separator}",sep),
                     ("${natives_directory}",str(natives)),("${classpath}",cp),
                     ("${auth_player_name}",auth_name),("${auth_uuid}",auth_uuid),
                     ("${auth_access_token}","0"),("${user_type}","offline"),
                     ("${version_type}","BunLauncher")]:
            s = s.replace(k,v)
        return s
    os_n = {"Linux":"linux","Darwin":"osx","Windows":"windows"}.get(platform.system(),"windows")
    
    def _append_val(val):
        """Добавляет значение в args, перехватывая -DignoreList и сливая его в custom_ignore."""
        if val.startswith("-DignoreList="):
            # НЕ добавляем в args — сливаем в наш набор
            custom_ignore.update(val.split("=",1)[1].split(","))
        else:
            args.append(val)
    
    def collect(arr):
        for it in arr:
            if isinstance(it,str): 
                _append_val(sub(it))
            elif isinstance(it,dict):
                ok=True; rules=it.get("rules")
                if rules:
                    r=False
                    for ru in rules:
                        m=True; o=ru.get("os")
                        if o and o.get("name") and o["name"]!=os_n: m=False
                        if o and o.get("arch") and o["arch"]!=platform.machine().lower().replace("amd64","x86_64"): m=False
                        if m: r=(ru.get("action","allow")=="allow")
                    ok=r
                if not ok: continue
                val=it.get("value")
                if isinstance(val,str): 
                    _append_val(sub(val))
                elif isinstance(val,list):
                    for v in val:
                        if isinstance(v,str): 
                            _append_val(sub(v))
    jvm_a = neo_j.get("arguments",{}).get("jvm")
    if jvm_a: collect(jvm_a)
    
    # Теперь вставляем ЕДИНЫЙ -DignoreList с ОБЪЕДИНЁННЫМИ записями
    # Вставляем перед -cp, чтобы Java точно видела
    args.insert(0, f"-DignoreList={','.join(custom_ignore)}")
    
    if not any(a in ("-cp","-classpath") for a in args) and not any("legacyClassPath" in a for a in args):
        args.extend(["-cp", cp])
    args.append(mc)
    ga = neo_j.get("arguments",{}).get("game"); vga = van_j.get("arguments",{}).get("game")
    if ga: collect(ga)
    elif vga: collect(vga)
    
    # Жестко удаляем --demo и quickPlay
    clean_args = []
    skip_next = False
    for a in args:
        if skip_next: skip_next = False; continue
        if a == "--demo": continue
        if a.startswith("--quickPlay"): 
            skip_next = True
            continue
        clean_args.append(a)
    args = clean_args

    j=" ".join(args)
    for fl,vl in [("--username",cfg.get("username","Player")),("--version",neo_id),
                   ("--gameDir",str(game_dir)),("--assetsDir",str(assets)),
                   ("--assetIndex",ai),("--uuid","00000000-0000-0000-0000-000000000000"),
                   ("--accessToken","0"),("--userType","offline")]:
        if fl not in j: args.extend([fl,vl])
    args.extend(["--width",str(cfg.get("width",854)),"--height",str(cfg.get("height",480))])
    if cfg.get("fullscreen"): args.append("--fullscreen")
    if cfg.get("auto_connect") and cfg.get("server_ip","").strip():
        parts = cfg["server_ip"].strip().split(":")
        args.extend(["--server", parts[0]])
        if len(parts) > 1: args.extend(["--port", parts[1]])

    creation_flags = 0
    if platform.system() == "Windows" and not cfg.get("show_console"):
        creation_flags = subprocess.CREATE_NO_WINDOW

    # Пишем логи запуска в файл для дебага
    log_file = game_dir / "latest_launch.log"
    with open(log_file, "w", encoding="utf-8") as lf:
        lf.write(f"--- BUNLAUNCHER LAUNCH LOG ---\n")
        lf.write(f"VERSION: {neo_id}, MC: {mc_version}\n")
        lf.write(f"JAVA: {java_path}\n")
        lf.write(f"ARGS:\n" + "\n".join(args) + "\n-------------------------\n\n")

    log_file_handle = open(log_file, "a", encoding="utf-8")
    
    try:
        # Проверяем не запущен ли уже Minecraft
        lock_file = game_dir / ".launcher_lock"
        if lock_file.exists():
            try:
                # Если файл пустой или с PID, попробуем понять жив ли процесс
                old_pid = int(lock_file.read_text(encoding="utf-8").strip())
                alive = False
                if psutil:
                    try: alive = psutil.pid_exists(old_pid)
                    except: pass
                else:
                    try: os.kill(old_pid, 0); alive = True
                    except (ProcessLookupError, PermissionError, OSError): pass
                if alive:
                    raise RuntimeError("Игра уже запущена! Закройте предыдущую копию.")
            except (ValueError, RuntimeError) as e:
                if isinstance(e, RuntimeError): raise
                # Процесс мертв или невалидный PID, можно удалять лок
                pass

        proc = subprocess.Popen([java_path]+args, cwd=str(game_dir),
                          stdin=subprocess.DEVNULL,
                          stdout=log_file_handle,
                          stderr=subprocess.STDOUT,
                          creationflags=creation_flags)

        lock_file.write_text(str(proc.pid), encoding="utf-8")

        # Проверяем не упал ли процесс мгновенно
        time.sleep(2)
        ret = proc.poll()
        if ret is not None and ret != 0:
            log_file_handle.close()
            lock_file.unlink(missing_ok=True)
            err_txt = ""
            try: err_txt = log_file.read_text(encoding="utf-8")[-1000:]
            except: pass
            raise RuntimeError(f"Minecraft завершился с кодом {ret} сразу после запуска.\n\nПоследние логи:\n{err_txt}\n\nПолный лог: {log_file}")
            
        # Ждем завершения в отдельном потоке
        def wait_and_unlock():
            proc.wait()
            log_file_handle.close()
            lock_file.unlink(missing_ok=True)
            
        t = threading.Thread(target=wait_and_unlock, daemon=True)
        t.start()
        
    except Exception as e:
        log_file_handle.close()
        raise RuntimeError(f"Ошибка запуска Java: {e}")


# ══════════════════════════════════
#  Worker Thread
# ══════════════════════════════════
class WorkerThread(QThread):
    progress = Signal(str, float)
    finished_ok = Signal()
    finished_err = Signal(str)

    def __init__(self, cfg, game_dir):
        super().__init__()
        self.cfg = cfg
        self.game_dir = game_dir

    def run(self):
        try:
            gd = effective_game_dir(self.cfg)
            if not is_installed(gd):
                neo_id, java_path, mc_ver = install_from_bundle(
                    gd, progress_cb=lambda s,p: self.progress.emit(s, p))
            else:
                m = json.loads((gd/"manifest.json").read_text(encoding="utf-8"))
                mc_ver = m.get("minecraft_version")
                jv = m.get("java_version")
                neo_id_hint = m.get("_neo_id", f"neoforge-{m.get('neoforge_version','')}") 
                neo_id = find_game_version(gd, neo_id_hint)
                # Используем путь Java из настроек или из бандла
                custom_java = self.cfg.get("java_path","").strip()
                if custom_java and Path(custom_java).exists():
                    java_path = custom_java
                else:
                    java_path = str(gd/"runtime"/f"jre-{jv}"/"bin"/
                                     ("java.exe" if platform.system()=="Windows" else "java"))

            self.progress.emit("Запуск игры...", 100)
            launch_game(self.cfg, gd, java_path, neo_id, mc_ver)
            self.finished_ok.emit()
        except Exception as ex:
            self.finished_err.emit(str(ex))


# ══════════════════════════════════
#  QSS
# ══════════════════════════════════
GLOBAL_QSS = """
* { font-family: "Segoe UI", sans-serif; }

#sidebar {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(14,12,10,200), stop:1 rgba(20,18,15,180));
    border-right: 1px solid rgba(80,70,55,60);
}

#nickLabel {
    color: rgba(160,150,135,200); font-size: 10px;
    font-weight: bold; letter-spacing: 2px;
}

#nickInput {
    background: rgba(35,30,25,180); border: 1px solid rgba(80,70,55,100);
    border-radius: 8px; color: #e8e0d4; font-size: 14px;
    padding: 10px 12px 10px 44px;
}
#nickInput:focus { border-color: rgba(38,119,59,200); }

#statusLabel { color: #4ade80; font-size: 10px; padding-left: 2px; }
#statusLabelError { color: #ef4444; font-size: 10px; padding-left: 2px; }

#playBtn {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #2d9a4e, stop:1 #26773B);
    border: none; border-radius: 14px; color: white;
    font-size: 16px; font-weight: bold; padding: 16px 24px;
    letter-spacing: 3px;
}
#playBtn:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #34b05a, stop:1 #2C8844);
}
#playBtn:pressed { background: #1f6830; }
#playBtn:disabled { background: #1a4a2a; color: rgba(255,255,255,100); }

#progressBar {
    background: rgba(40,35,30,150); border: none;
    border-radius: 3px; max-height: 6px;
}
#progressBar::chunk { background: #4ade80; border-radius: 3px; }
#progressLabel { color: #4ade80; font-size: 10px; }

#menuBtn {
    background: transparent; border: none; border-radius: 8px;
    color: rgba(180,170,155,200); font-size: 13px; font-weight: bold;
    letter-spacing: 1px; padding: 10px 16px; text-align: left;
}
#menuBtn:hover {
    background: rgba(60,50,40,120); color: rgba(240,230,215,240);
}

#exitBtn {
    background: transparent; border: none; border-radius: 8px;
    color: rgba(120,110,100,180); font-size: 13px; font-weight: bold;
    letter-spacing: 1px; padding: 10px 16px; text-align: left;
}
#exitBtn:hover { background: rgba(80,30,30,100); color: #ef4444; }

#promoCard {
    background: rgba(20,18,16,200); border: 1px solid rgba(80,70,55,60);
    border-radius: 22px;
}
#promoTitle { color: rgba(255,255,255,235); font-size: 18px; font-weight: bold; }
#promoSub { color: rgba(180,170,155,180); font-size: 12px; }

#footer { background: rgba(8,6,4,220); }
#footerText { color: rgba(120,110,100,150); font-size: 9px; }
"""


# ══════════════════════════════════
#  Аватар
# ══════════════════════════════════
class AvatarBadge(QWidget):
    def __init__(self, letter="P", color="#26773B", size=30):
        super().__init__()
        self.letter = letter
        self.color = QColor(color)
        self.setFixedSize(size, size)
        self._size = size

    def setLetter(self, l, color="#26773B"):
        self.letter = l; self.color = QColor(color); self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(self.color)); p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self._size, self._size)
        p.setPen(QPen(QColor("#ffffff")))
        p.setFont(QFont("Segoe UI", self._size // 3, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, self.letter)
        p.end()


# ══════════════════════════════════
#  Плавающие частицы (Canvas overlay)
# ══════════════════════════════════
class ParticleOverlay(QWidget):
    """Полупрозрачный виджет с плавающими тёплыми частицами."""
    def __init__(self, parent, count=12):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.particles = []
        for _ in range(count):
            self.particles.append({
                "x": _rnd.randint(0, 600),
                "y": _rnd.randint(0, 600),
                "vx": _rnd.uniform(-0.15, 0.15),
                "vy": _rnd.uniform(-0.3, -0.05),
                "r": _rnd.uniform(1.5, 3.5),
                "br": _rnd.randint(60, 120),
                "phase": _rnd.uniform(0, 6.28),
            })
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _tick(self):
        w, h = self.width(), self.height()
        for p in self.particles:
            p["x"] += p["vx"] + math.sin(p["phase"]) * 0.1
            p["y"] += p["vy"]
            p["phase"] += 0.012
            if p["y"] < -10:
                p["y"] = h + 10
                p["x"] = _rnd.randint(0, max(w, 1))
            if p["x"] < -10: p["x"] = w + 10
            if p["x"] > w + 10: p["x"] = -10
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for p in self.particles:
            br = p["br"]
            color = QColor(br, max(br-15, 0), max(br-35, 0), 80)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(p["x"]-p["r"]), int(p["y"]-p["r"]),
                                 int(p["r"]*2), int(p["r"]*2))
        painter.end()


# ══════════════════════════════════
#  Главное окно
# ══════════════════════════════════
def nick_ok(n):
    if not n: return "Введите никнейм"
    if len(n)<3: return "Мин. 3 символа"
    if len(n)>16: return "Макс. 16"
    if not re.match(r"^[a-zA-Z0-9_]+$", n): return "a-z, 0-9, _"
    return ""


class BunLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Launcher")
        self.setMinimumSize(889, 631)
        self.resize(889, 631)
        self._cfg = load_cfg(DEFAULT_GAME_DIR)
        self._running = False
        self._worker = None

        ico_path = ASSETS_DIR / "bun.png"
        if ico_path.exists(): self.setWindowIcon(QIcon(str(ico_path)))

        central = QWidget()
        self.setCentralWidget(central)

        # Фон
        self._bg_label = QLabel(central)
        self._bg_label.setScaledContents(True)
        self._bg_label.lower()
        bg_path = ASSETS_DIR / "note.jpg"
        if bg_path.exists():
            self._bg_pixmap = QPixmap(str(bg_path))
        else:
            self._bg_pixmap = QPixmap(889, 631)
            self._bg_pixmap.fill(QColor("#2a1e14"))
        self._bg_label.setPixmap(self._bg_pixmap)

        # Частицы поверх фона
        self._particles = ParticleOverlay(central, count=10)

        # Layout
        main_h = QHBoxLayout(central)
        main_h.setContentsMargins(0, 0, 0, 0)
        main_h.setSpacing(0)

        sidebar = self._build_sidebar()
        main_h.addWidget(sidebar)

        right = QWidget()
        right.setAttribute(Qt.WA_TranslucentBackground)
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(0)

        content = QWidget()
        content.setAttribute(Qt.WA_TranslucentBackground)
        content_layout = QVBoxLayout(content)
        content_layout.setAlignment(Qt.AlignCenter)
        self._promo = self._build_promo_card()
        content_layout.addWidget(self._promo, alignment=Qt.AlignCenter)
        right_v.addWidget(content, 1)

        footer = self._build_footer()
        right_v.addWidget(footer)
        main_h.addWidget(right, 1)

        self._nick_input.setText(self._cfg.get("username", "Player"))

        # Анимация появления после показа
        QTimer.singleShot(100, self._animate_in)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg_label.setGeometry(0, 0, self.width(), self.height())
        self._particles.setGeometry(0, 0, self.width(), self.height())

    # ── Анимации ──
    def _animate_in(self):
        """Fade-in + slide для сайдбара и карточки."""
        # Sidebar slide-in
        self._sidebar_anim = QPropertyAnimation(self._sidebar_widget, b"pos")
        self._sidebar_anim.setDuration(500)
        self._sidebar_anim.setStartValue(QPoint(-400, 0))
        self._sidebar_anim.setEndValue(QPoint(0, 0))
        self._sidebar_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._sidebar_anim.start()

        # Promo card fade-in + float up
        self._card_opacity = QGraphicsOpacityEffect(self._promo)
        self._promo.setGraphicsEffect(self._card_opacity)
        self._card_fade = QPropertyAnimation(self._card_opacity, b"opacity")
        self._card_fade.setDuration(800)
        self._card_fade.setStartValue(0.0)
        self._card_fade.setEndValue(1.0)
        self._card_fade.setEasingCurve(QEasingCurve.OutCubic)
        self._card_fade.start()

        # Card floating animation (gentle up-down)
        QTimer.singleShot(1000, self._start_float)

    def _start_float(self):
        """Лёгкое покачивание карточки."""
        self._float_timer = QTimer(self)
        self._float_phase = 0.0
        self._promo_base_y = self._promo.y()
        self._float_timer.timeout.connect(self._float_tick)
        self._float_timer.start(50)

    def _float_tick(self):
        self._float_phase += 0.03
        offset = int(math.sin(self._float_phase) * 4)
        self._promo.move(self._promo.x(), self._promo_base_y + offset)

    # ── Sidebar ──
    def _build_sidebar(self):
        self._sidebar_widget = QFrame()
        self._sidebar_widget.setObjectName("sidebar")
        self._sidebar_widget.setFixedWidth(400)

        v = QVBoxLayout(self._sidebar_widget)
        v.setContentsMargins(32, 28, 32, 20)
        v.setSpacing(0)

        # Logo
        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        ico_path = ASSETS_DIR / "bun.png"
        if ico_path.exists():
            logo_icon = QLabel()
            pm = QPixmap(str(ico_path)).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_icon.setPixmap(pm)
            logo_row.addWidget(logo_icon)
        logo_text = QLabel("Bun Launcher")
        logo_text.setStyleSheet("color: rgba(220,210,195,220); font-size: 15px; font-weight: bold;")
        logo_row.addWidget(logo_text)
        logo_row.addStretch()
        v.addLayout(logo_row)

        v.addSpacing(28)

        # НИКНЕЙМ
        nick_label = QLabel("НИКНЕЙМ")
        nick_label.setObjectName("nickLabel")
        v.addWidget(nick_label)
        v.addSpacing(8)

        # Nick input
        nick_container = QWidget()
        nick_container.setFixedHeight(48)
        nick_grid = QGridLayout(nick_container)
        nick_grid.setContentsMargins(0, 0, 0, 0)

        self._avatar = AvatarBadge("P", "#26773B", 30)
        self._nick_input = QLineEdit()
        self._nick_input.setObjectName("nickInput")
        self._nick_input.setPlaceholderText("Введите никнейм...")
        nick_grid.addWidget(self._nick_input, 0, 0)

        avatar_wrapper = QWidget(self._nick_input)
        avatar_wrapper.setGeometry(8, 9, 30, 30)
        av_layout = QHBoxLayout(avatar_wrapper)
        av_layout.setContentsMargins(0, 0, 0, 0)
        av_layout.addWidget(self._avatar)
        v.addWidget(nick_container)

        self._status_label = QLabel("")
        self._status_label.setObjectName("statusLabel")
        v.addWidget(self._status_label)

        v.addSpacing(16)

        # ИГРАТЬ
        self._play_btn = QPushButton("  ▶   ИГРАТЬ")
        self._play_btn.setObjectName("playBtn")
        self._play_btn.setFixedHeight(56)
        self._play_btn.setCursor(Qt.PointingHandCursor)
        play_shadow = QGraphicsDropShadowEffect()
        play_shadow.setBlurRadius(24); play_shadow.setOffset(0, 8)
        play_shadow.setColor(QColor(0, 0, 0, 80))
        self._play_btn.setGraphicsEffect(play_shadow)
        v.addWidget(self._play_btn)

        # Progress
        self._progress_container = QWidget()
        self._progress_container.setVisible(False)
        pc_v = QVBoxLayout(self._progress_container)
        pc_v.setContentsMargins(0, 8, 0, 0)
        pc_v.setSpacing(4)
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("progressBar")
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        pc_v.addWidget(self._progress_bar)
        self._progress_label = QLabel("")
        self._progress_label.setObjectName("progressLabel")
        pc_v.addWidget(self._progress_label)
        v.addWidget(self._progress_container)

        v.addSpacing(24)

        # Навигация
        nav_items = [
            ("📦", "РЕСУРСЫ", self._open_resources),
            ("🗺", "КАРТА", self._open_map),
            ("⚙", "НАСТРОЙКИ", self._open_settings),
        ]
        for icon, text, slot in nav_items:
            btn = QPushButton(f"  {icon}    {text}")
            btn.setObjectName("menuBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            v.addWidget(btn)

        v.addStretch()

        # ВЫХОД
        exit_btn = QPushButton("  ↩    ВЫХОД")
        exit_btn.setObjectName("exitBtn")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.clicked.connect(self.close)
        v.addWidget(exit_btn)

        self._nick_input.textChanged.connect(self._on_nick_changed)
        self._nick_input.returnPressed.connect(self._on_play)
        self._play_btn.clicked.connect(self._on_play)

        # Проверяем не запущена ли уже игра при старте лаунчера
        self._check_game_running_on_start()

        return self._sidebar_widget

    # ── News Card ──
    def _build_promo_card(self):
        card = QFrame()
        card.setObjectName("promoCard")
        card.setFixedSize(320, 200)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40); shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 100))
        card.setGraphicsEffect(shadow)

        v = QVBoxLayout(card)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(8)

        self._news_items = [
            ("🐉", "Дракон Края сбежал!", "Местные жители Нижнего мира\nсообщают о странных звуках."),
            ("💎", "Алмазы подорожали!", "Курс алмаза вырос на 300%\nпосле обновления генерации пещер."),
            ("🐑", "Овцы объявили забастовку", "Все овцы сервера отказались\nдавать шерсть до пятницы."),
            ("🧟", "Зомби открыл кафе", "Первое зомби-кафе предлагает\nсвежие мозги и кофе за 2 изумруда."),
            ("🏗", "Стив построил небоскрёб", "999 блоков высотой —\nновый мировой рекорд!"),
        ]
        self._news_idx = 0

        icon_badge = QLabel(self._news_items[0][0])
        icon_badge.setStyleSheet("background:rgba(50,45,38,200);border-radius:14px;padding:6px 8px;font-size:18px;")
        icon_badge.setFixedSize(36, 36)
        icon_badge.setAlignment(Qt.AlignCenter)
        v.addWidget(icon_badge)
        v.addSpacing(8)
        self._news_icon = icon_badge

        title = QLabel(self._news_items[0][1])
        title.setObjectName("promoTitle")
        v.addWidget(title)
        self._news_title = title

        sub = QLabel(self._news_items[0][2])
        sub.setObjectName("promoSub"); sub.setWordWrap(True)
        v.addWidget(sub)
        self._news_sub = sub
        v.addStretch()

        dots_h = QHBoxLayout()
        dots_h.setSpacing(6)
        
        # Кнопка "Назад"
        self._news_prev = QPushButton("‹")
        self._news_prev.setCursor(Qt.PointingHandCursor)
        self._news_prev.setFixedSize(20, 20)
        self._news_prev.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; font-size: 16px; font-weight: bold; } QPushButton:hover { color: white; }")
        self._news_prev.clicked.connect(lambda: self._rotate_news(-1))
        dots_h.addWidget(self._news_prev)

        self._news_dots = []
        for i in range(len(self._news_items)):
            dot = QLabel(); dot.setFixedSize(6, 6)
            dot.setStyleSheet(f"background:{'#4ade80' if i==0 else 'rgba(120,110,100,100)'};border-radius:3px;")
            dots_h.addWidget(dot)
            self._news_dots.append(dot)
            
        # Кнопка "Вперед"
        self._news_next = QPushButton("›")
        self._news_next.setCursor(Qt.PointingHandCursor)
        self._news_next.setFixedSize(20, 20)
        self._news_next.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; font-size: 16px; font-weight: bold; } QPushButton:hover { color: white; }")
        self._news_next.clicked.connect(lambda: self._rotate_news(1))
        dots_h.addWidget(self._news_next)
        
        dots_h.addStretch()
        v.addLayout(dots_h)

        self._news_timer = QTimer(self)
        self._news_timer.timeout.connect(lambda: self._rotate_news(1))
        self._news_timer.start(5000)

        return card

    def _rotate_news(self, direction=1):
        self._news_idx = (self._news_idx + direction) % len(self._news_items)
        icon, title, sub = self._news_items[self._news_idx]
        self._news_icon.setText(icon)
        self._news_title.setText(title)
        self._news_sub.setText(sub)
        for i, dot in enumerate(self._news_dots):
            dot.setStyleSheet(f"background:{'#4ade80' if i==self._news_idx else 'rgba(120,110,100,100)'};border-radius:3px;")
        # Сбрасываем таймер при ручном перелистывании
        self._news_timer.start(5000)

    # ── Footer ──
    def _build_footer(self):
        footer = QFrame(); footer.setObjectName("footer"); footer.setFixedHeight(28)
        h = QHBoxLayout(footer); h.setContentsMargins(12, 0, 12, 0)
        h.addWidget(QLabel("BunLauncher  ·  NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG",
                            objectName="footerText"))
        h.addStretch()
        h.addWidget(QLabel("v1", objectName="footerText"))
        return footer

    # ── Nick ──
    def _on_nick_changed(self, text):
        if not text:
            self._avatar.setLetter("?", "#444444"); self._status_label.setText(""); return
        colors = ["#26773B","#2563eb","#7c3aed","#ea580c"]
        idx = ord(text[0]) % len(colors)
        self._avatar.setLetter(text[0].upper(), colors[idx])
        err = nick_ok(text)
        if err:
            self._status_label.setObjectName("statusLabelError")
            self._status_label.setStyle(self._status_label.style())
            self._status_label.setText(err)
        else:
            self._status_label.setObjectName("statusLabel")
            self._status_label.setStyle(self._status_label.style())
            self._status_label.setText("✓ Готово к игре")

    def _check_game_running_on_start(self):
        """При старте лаунчера проверяем — может игра уже запущена."""
        gd = effective_game_dir(self._cfg)
        lock = gd / ".launcher_lock"
        if not lock.exists():
            return
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
            alive = False
            if psutil:
                try: alive = psutil.pid_exists(pid)
                except: pass
            else:
                try: os.kill(pid, 0); alive = True
                except (ProcessLookupError, PermissionError, OSError): pass
            if alive:
                self._play_btn.setText("  🎮   ИГРА ЗАПУЩЕНА")
                self._play_btn.setEnabled(False)
                self._game_poll_timer = QTimer(self)
                self._game_poll_timer.timeout.connect(self._poll_game)
                self._game_poll_timer.start(2000)
            else:
                lock.unlink(missing_ok=True)
        except (ValueError, OSError):
            lock.unlink(missing_ok=True)

    # ── Play ──
    def _on_play(self):
        name = self._nick_input.text().strip()
        err = nick_ok(name)
        if err: QMessageBox.warning(self, "Ошибка", err); return
        if self._running: return

        self._running = True
        self._play_btn.setText("  ⏳   ЗАГРУЗКА..."); self._play_btn.setEnabled(False)
        self._progress_container.setVisible(True)
        self._progress_bar.setValue(0); self._progress_label.setText("Подготовка...")

        self._cfg["username"] = name
        gd = effective_game_dir(self._cfg)
        save_cfg(gd, self._cfg)

        self._worker = WorkerThread(self._cfg, gd)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.finished_err.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, text, pct):
        self._progress_bar.setValue(int(min(pct, 100)))
        self._progress_label.setText(text)

    def _on_done(self):
        self._running = False
        self._play_btn.setText("  🎮   ИГРА ЗАПУЩЕНА")
        self._play_btn.setEnabled(False)
        self._play_btn.setStyleSheet("")
        self._progress_container.setVisible(False)
        if self._cfg.get("close_on_launch"):
            QTimer.singleShot(1000, self.close)
        else:
            # Мониторим процесс игры через lock-файл
            self._game_poll_timer = QTimer(self)
            self._game_poll_timer.timeout.connect(self._poll_game)
            self._game_poll_timer.start(2000)

    def _poll_game(self):
        """Проверяем жив ли процесс игры по PID из lock-файла."""
        gd = effective_game_dir(self._cfg)
        lock = gd / ".launcher_lock"
        if not lock.exists():
            self._game_poll_timer.stop()
            self._reset_play()
            return
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
            alive = False
            if psutil:
                try: alive = psutil.pid_exists(pid)
                except: pass
            else:
                try: os.kill(pid, 0); alive = True
                except (ProcessLookupError, PermissionError, OSError): pass
            if not alive:
                lock.unlink(missing_ok=True)
                self._game_poll_timer.stop()
                self._reset_play()
        except (ValueError, OSError):
            lock.unlink(missing_ok=True)
            self._game_poll_timer.stop()
            self._reset_play()

    def _on_error(self, msg):
        self._running = False; self._reset_play()
        self._progress_container.setVisible(False)
        QMessageBox.critical(self, "Ошибка", msg)

    def _reset_play(self):
        self._play_btn.setText("  ▶   ИГРАТЬ"); self._play_btn.setEnabled(True)
        self._play_btn.setStyleSheet("")

    def _open_settings(self):
        dlg = SettingsDialog(self, self._cfg, effective_game_dir(self._cfg))
        if dlg.exec(): self._cfg = dlg.result_cfg

    def _open_resources(self):
        """Анализатор установленных модов."""
        gd = effective_game_dir(self._cfg)
        mods_dir = gd / "mods"
        dlg = QDialog(self)
        dlg.setWindowTitle("📦 Ресурсы — Установленные моды")
        dlg.setFixedSize(540, 460)
        dlg.setStyleSheet(
            "QDialog{background:#1e1c1a;} QLabel{color:white;background:transparent;}"
            "QScrollArea{background:transparent;border:none;}"
            "QPushButton#modAction{background:#2a2622;border:1px solid #3a352e;border-radius:6px;color:#ccc;padding:4px 8px;font-size:11px;}"
            "QPushButton#modAction:hover{background:#3a352e;color:white;border-color:#4ade80;}"
            "QPushButton#delAction{background:#2a2622;border:1px solid #3a352e;border-radius:6px;color:#ff6b6b;padding:4px 8px;font-size:11px;}"
            "QPushButton#delAction:hover{background:#3a2020;border-color:#ff6b6b;}"
        )
        v = QVBoxLayout(dlg); v.setContentsMargins(24, 20, 24, 20); v.setSpacing(12)
        t = QLabel("📦 Установленные моды"); t.setStyleSheet("font-size:18px;font-weight:bold;color:white;"); v.addWidget(t)

        def _refresh_list():
            # Очищаем scroll area
            for i in reversed(range(mods_layout.count())):
                w = mods_layout.itemAt(i).widget()
                if w: w.deleteLater()

            if mods_dir.exists():
                jar_files = sorted([f for f in mods_dir.iterdir() if f.suffix.lower() == ".jar"])
                info_lbl.setText(f"Найдено модов: {len(jar_files)}  •  {mods_dir}")
                if jar_files:
                    for jar in jar_files:
                        row = QWidget(); row.setStyleSheet("background:transparent;")
                        rh = QHBoxLayout(row); rh.setContentsMargins(0, 2, 0, 2); rh.setSpacing(8)
                        size_mb = jar.stat().st_size / (1024*1024)
                        name = jar.stem.replace("-", " ").replace("_", " ")
                        lbl = QLabel(f"🧩 {name}  ({size_mb:.1f} MB)")
                        lbl.setStyleSheet("color:#ddd;font-size:12px;background:transparent;")
                        rh.addWidget(lbl, 1)
                        # Кнопка поиска
                        search_btn = QPushButton("🔍"); search_btn.setObjectName("modAction")
                        search_btn.setFixedSize(32, 28); search_btn.setCursor(Qt.PointingHandCursor)
                        search_btn.setToolTip("Найти в Google")
                        _name = jar.stem
                        search_btn.clicked.connect(lambda _, n=_name: webbrowser.open(f"https://www.google.com/search?q=minecraft+mod+{n}"))
                        rh.addWidget(search_btn)
                        # Кнопка удаления
                        del_btn = QPushButton("🗑"); del_btn.setObjectName("delAction")
                        del_btn.setFixedSize(32, 28); del_btn.setCursor(Qt.PointingHandCursor)
                        del_btn.setToolTip("Удалить мод")
                        _jar = jar
                        def _do_del(_, j=_jar):
                            if QMessageBox.question(dlg, "Удаление", f"Удалить {j.name}?") == QMessageBox.Yes:
                                try: j.unlink()
                                except: pass
                                _refresh_list()
                        del_btn.clicked.connect(_do_del)
                        rh.addWidget(del_btn)
                        mods_layout.addWidget(row)
                else:
                    no = QLabel("Моды не найдены.\nПоложите .jar файлы в папку mods.")
                    no.setStyleSheet("color:#888;font-size:13px;"); no.setAlignment(Qt.AlignCenter)
                    mods_layout.addWidget(no)
            else:
                no = QLabel(f"Папка модов не найдена.\nОна появится после первого запуска игры.")
                no.setStyleSheet("color:#888;font-size:13px;"); no.setAlignment(Qt.AlignCenter)
                mods_layout.addWidget(no)

        info_lbl = QLabel(""); info_lbl.setStyleSheet("font-size:11px;color:#888;"); v.addWidget(info_lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        mods_w = QWidget(); mods_w.setStyleSheet("background:transparent;")
        mods_layout = QVBoxLayout(mods_w); mods_layout.setContentsMargins(0,0,0,0); mods_layout.setSpacing(4)
        mods_layout.addStretch()
        scroll.setWidget(mods_w); v.addWidget(scroll, 1)

        _refresh_list()

        # Нижние кнопки
        bh = QHBoxLayout()
        open_btn = QPushButton("📂 Открыть папку модов"); open_btn.setObjectName("modAction")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(lambda: (mods_dir.mkdir(parents=True, exist_ok=True), os.startfile(str(mods_dir)) if platform.system()=="Windows" else None))
        bh.addWidget(open_btn)
        bh.addStretch()
        close_btn = QPushButton("Закрыть"); close_btn.setObjectName("nextBtn"); close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(dlg.accept); bh.addWidget(close_btn)
        v.addLayout(bh)
        dlg.exec()

    def _open_map(self):
        QMessageBox.information(self, "🗺 Карта мира", "Эта функция скоро появится!\n\nВ будущих обновлениях здесь будет\nинтерактивная карта вашего мира.")


# ══════════════════════════════════
#  Настройки (расширенные, с табами)
# ══════════════════════════════════
RAM_OPTS = [1024,2048,3072,4096,6144,8192,12288,16384]
RES_PRESETS = {"854×480":(854,480),"1280×720":(1280,720),"1366×768":(1366,768),
               "1600×900":(1600,900),"1920×1080":(1920,1080),"2560×1440":(2560,1440)}

SETTINGS_QSS = """
QDialog { background: #1a1816; }
QTabWidget::pane { background: #1a1816; border: none; border-top: 1px solid rgba(80,70,55,60); }
QTabBar::tab {
    background: transparent; color: #888; padding: 8px 16px;
    border: none; border-bottom: 2px solid transparent;
    font-weight: bold; font-size: 11px;
}
QTabBar::tab:selected { color: #4ade80; border-bottom-color: #4ade80; }
QTabBar::tab:hover { color: #ccc; }

QLabel { color: #ccc; font-size: 12px; }
QLabel#sectionLabel { color: #666; font-size: 10px; font-weight: bold; margin-top: 8px; }
QLineEdit, QComboBox, QSpinBox {
    background: #2a2622; color: white; border: 1px solid #3a352e;
    border-radius: 6px; padding: 7px 10px; font-size: 12px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #26773B; }
QComboBox::drop-down { border: none; padding-right: 8px; }
QComboBox QAbstractItemView { background: #2a2622; color: white; selection-background-color: #26773B; }
QCheckBox { color: #ccc; font-size: 12px; spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border: 1px solid #3a352e;
    border-radius: 4px; background: #2a2622;
}
QCheckBox::indicator:checked { background: #26773B; border-color: #26773B; }
QSlider::groove:horizontal { background: #2a2622; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #4ade80; width: 14px; height: 14px;
    border-radius: 7px; margin: -5px 0;
}
QSlider::sub-page:horizontal { background: #26773B; border-radius: 2px; }
QPushButton#saveBtn {
    background: #26773B; color: white; border: none; border-radius: 8px;
    padding: 10px 24px; font-size: 12px; font-weight: bold;
}
QPushButton#saveBtn:hover { background: #2C8844; }
QPushButton#cancelBtn {
    background: #2a2622; color: #ccc; border: none; border-radius: 8px;
    padding: 10px 24px; font-size: 12px;
}
QPushButton#cancelBtn:hover { background: #3a352e; color: white; }
QPushButton#browseBtn {
    background: #2a2622; color: #aaa; border: 1px solid #3a352e;
    border-radius: 6px; padding: 7px 12px; font-size: 11px;
}
QPushButton#browseBtn:hover { background: #3a352e; color: white; }
"""


class SettingsDialog(QDialog):
    def __init__(self, parent, cfg, game_dir):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setFixedSize(540, 560)
        self.setStyleSheet(SETTINGS_QSS)
        self.result_cfg = cfg.copy()
        self._game_dir = game_dir
        self._build(cfg)

    def _build(self, cfg):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet("background:#1e1c18;border-bottom:1px solid rgba(80,70,55,60);")
        hdr.setFixedHeight(48)
        hdr_h = QHBoxLayout(hdr); hdr_h.setContentsMargins(20, 0, 20, 0)
        hdr_h.addWidget(QLabel("⚙  Настройки", styleSheet="color:white;font-size:14px;font-weight:bold;"))
        hdr_h.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setStyleSheet("background:none;border:none;color:#666;font-size:16px;")
        close_btn.setCursor(Qt.PointingHandCursor); close_btn.clicked.connect(self.reject)
        hdr_h.addWidget(close_btn)
        v.addWidget(hdr)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._tab_general(cfg), "🎮 Игра")
        tabs.addTab(self._tab_performance(cfg), "⚡ Производительность")
        tabs.addTab(self._tab_paths(cfg), "📁 Пути")
        tabs.addTab(self._tab_network(cfg), "🌐 Сеть")
        tabs.addTab(self._tab_advanced(cfg), "🔧 Дополнительно")
        v.addWidget(tabs, 1)

        # Buttons
        btn_frame = QWidget()
        btn_frame.setStyleSheet("background:#1a1816;border-top:1px solid rgba(80,70,55,60);")
        btn_h = QHBoxLayout(btn_frame); btn_h.setContentsMargins(20,12,20,12)
        cancel = QPushButton("Отмена"); cancel.setObjectName("cancelBtn")
        cancel.setCursor(Qt.PointingHandCursor); cancel.clicked.connect(self.reject)
        btn_h.addWidget(cancel)
        btn_h.addStretch()
        save = QPushButton("💾  Сохранить"); save.setObjectName("saveBtn")
        save.setCursor(Qt.PointingHandCursor); save.clicked.connect(self._save)
        btn_h.addWidget(save)
        v.addWidget(btn_frame)

    def _section(self, layout, text):
        lbl = QLabel(text); lbl.setObjectName("sectionLabel"); layout.addWidget(lbl)

    def _tab_general(self, cfg):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20,16,20,16); v.setSpacing(8)

        self._section(v, "РАЗРЕШЕНИЕ ЭКРАНА")
        self._res_combo = QComboBox()
        cw, ch = cfg.get("width",854), cfg.get("height",480)
        sel_idx = 0
        for i, (name, (rw,rh)) in enumerate(RES_PRESETS.items()):
            self._res_combo.addItem(name, (rw,rh))
            if rw == cw and rh == ch: sel_idx = i
        self._res_combo.setCurrentIndex(sel_idx)
        v.addWidget(self._res_combo)

        # Custom resolution
        res_h = QHBoxLayout()
        self._w_spin = QSpinBox(); self._w_spin.setRange(640,3840); self._w_spin.setValue(cw)
        self._h_spin = QSpinBox(); self._h_spin.setRange(480,2160); self._h_spin.setValue(ch)
        res_h.addWidget(QLabel("Ширина:")); res_h.addWidget(self._w_spin)
        res_h.addWidget(QLabel("×")); res_h.addWidget(self._h_spin)
        v.addLayout(res_h)

        self._res_combo.currentIndexChanged.connect(lambda: self._on_res_preset())

        self._section(v, "ПОЛНОЭКРАННЫЙ РЕЖИМ")
        self._fs_check = QCheckBox("Запускать в полноэкранном режиме")
        self._fs_check.setChecked(cfg.get("fullscreen", False))
        v.addWidget(self._fs_check)

        self._section(v, "ПОСЛЕ ЗАПУСКА")
        self._close_check = QCheckBox("Закрыть лаунчер после запуска игры")
        self._close_check.setChecked(cfg.get("close_on_launch", False))
        v.addWidget(self._close_check)

        v.addStretch()
        return w

    def _tab_performance(self, cfg):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20,16,20,16); v.setSpacing(8)

        self._section(v, "ОПЕРАТИВНАЯ ПАМЯТЬ")
        ram_h = QHBoxLayout()
        self._ram_slider = QSlider(Qt.Horizontal)
        self._ram_slider.setRange(0, len(RAM_OPTS)-1)
        cur_ram = cfg.get("memory_mb", 4096)
        idx = RAM_OPTS.index(cur_ram) if cur_ram in RAM_OPTS else 3
        self._ram_slider.setValue(idx)
        self._ram_label = QLabel(ram_label(RAM_OPTS[idx]))
        self._ram_label.setStyleSheet("color:#4ade80;font-size:16px;font-weight:bold;min-width:60px;")
        self._ram_slider.valueChanged.connect(lambda v: self._ram_label.setText(ram_label(RAM_OPTS[v])))
        ram_h.addWidget(self._ram_slider, 1)
        ram_h.addWidget(self._ram_label)
        v.addLayout(ram_h)
        v.addWidget(QLabel("Рекомендуется: 4-8 GB для модпаков", styleSheet="color:#666;font-size:10px;"))

        self._section(v, "JVM АРГУМЕНТЫ")
        self._jvm_input = QLineEdit(cfg.get("jvm_args",""))
        self._jvm_input.setPlaceholderText("-XX:+UnlockExperimentalVMOptions ...")
        v.addWidget(self._jvm_input)
        v.addWidget(QLabel("Дополнительные аргументы для Java VM", styleSheet="color:#666;font-size:10px;"))

        self._section(v, "ПОТОКИ ЗАГРУЗКИ")
        th_h = QHBoxLayout()
        self._threads_spin = QSpinBox(); self._threads_spin.setRange(1, 32)
        self._threads_spin.setValue(cfg.get("max_threads", 8))
        th_h.addWidget(self._threads_spin)
        th_h.addWidget(QLabel("потоков (для скачивания ассетов)"))
        th_h.addStretch()
        v.addLayout(th_h)

        v.addStretch()
        return w

    def _tab_paths(self, cfg):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20,16,20,16); v.setSpacing(8)

        self._section(v, "ПАПКА ИГРЫ")
        gd_h = QHBoxLayout()
        self._gd_input = QLineEdit(cfg.get("game_dir","") or str(DEFAULT_GAME_DIR))
        gd_h.addWidget(self._gd_input, 1)
        gd_browse = QPushButton("📂 Обзор"); gd_browse.setObjectName("browseBtn")
        gd_browse.setCursor(Qt.PointingHandCursor)
        gd_browse.clicked.connect(lambda: self._browse(self._gd_input))
        gd_h.addWidget(gd_browse)
        v.addLayout(gd_h)
        v.addWidget(QLabel("Пустое = по умолчанию: " + str(DEFAULT_GAME_DIR), styleSheet="color:#555;font-size:9px;"))

        self._section(v, "ПУТЬ К JAVA")
        jp_h = QHBoxLayout()
        self._jp_input = QLineEdit(cfg.get("java_path",""))
        self._jp_input.setPlaceholderText("Авто-определение из бандла")
        jp_h.addWidget(self._jp_input, 1)
        jp_browse = QPushButton("📂 Обзор"); jp_browse.setObjectName("browseBtn")
        jp_browse.setCursor(Qt.PointingHandCursor)
        jp_browse.clicked.connect(lambda: self._browse_file(self._jp_input))
        jp_h.addWidget(jp_browse)
        v.addLayout(jp_h)

        # Авто-поиск Java
        detect_btn = QPushButton("🔍 Найти Java автоматически"); detect_btn.setObjectName("browseBtn")
        detect_btn.setCursor(Qt.PointingHandCursor)
        detect_btn.clicked.connect(self._auto_detect_java)
        v.addWidget(detect_btn)

        self._java_list = QLabel(""); self._java_list.setStyleSheet("color:#888;font-size:10px;")
        self._java_list.setWordWrap(True)
        v.addWidget(self._java_list)

        v.addStretch()
        return w

    def _tab_network(self, cfg):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20,16,20,16); v.setSpacing(8)

        self._section(v, "АВТО-ПОДКЛЮЧЕНИЕ К СЕРВЕРУ")
        self._ac_check = QCheckBox("Подключаться к серверу при запуске")
        self._ac_check.setChecked(cfg.get("auto_connect", False))
        v.addWidget(self._ac_check)

        self._section(v, "АДРЕС СЕРВЕРА")
        self._server_input = QLineEdit(cfg.get("server_ip",""))
        self._server_input.setPlaceholderText("play.example.com:25565")
        v.addWidget(self._server_input)
        v.addWidget(QLabel("Формат: адрес или адрес:порт", styleSheet="color:#666;font-size:10px;"))

        v.addStretch()
        return w

    def _tab_advanced(self, cfg):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20,16,20,16); v.setSpacing(8)

        self._section(v, "КОНСОЛЬ")
        self._console_check = QCheckBox("Показывать консоль Java при запуске")
        self._console_check.setChecked(cfg.get("show_console", False))
        v.addWidget(self._console_check)
        v.addWidget(QLabel("Полезно для отладки проблем с запуском", styleSheet="color:#666;font-size:10px;"))

        self._section(v, "ПРОВЕРКА ФАЙЛОВ")
        self._check_files = QCheckBox("Проверять целостность файлов перед запуском")
        self._check_files.setChecked(cfg.get("check_files", True))
        v.addWidget(self._check_files)

        self._section(v, "СБРОС")
        reset_btn = QPushButton("🗑  Сбросить настройки")
        reset_btn.setObjectName("browseBtn")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_settings)
        v.addWidget(reset_btn)

        reinstall_btn = QPushButton("🔄  Переустановить игру")
        reinstall_btn.setObjectName("browseBtn")
        reinstall_btn.setCursor(Qt.PointingHandCursor)
        reinstall_btn.clicked.connect(self._reinstall)
        v.addWidget(reinstall_btn)

        v.addStretch()

        # Info
        info = QLabel(f"BunLauncher v1.0\nPython {sys.version.split()[0]}\n"
                       f"Qt {__import__('PySide6.QtCore', fromlist=['__version__']).__version__}\n"
                       f"Платформа: {platform.system()} {platform.machine()}")
        info.setStyleSheet("color:#444;font-size:9px;"); info.setWordWrap(True)
        v.addWidget(info)

        return w

    # ── Helpers ──
    def _on_res_preset(self):
        data = self._res_combo.currentData()
        if data:
            self._w_spin.setValue(data[0]); self._h_spin.setValue(data[1])

    def _browse(self, line_edit):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку", line_edit.text())
        if d: line_edit.setText(d)

    def _browse_file(self, line_edit):
        f, _ = QFileDialog.getOpenFileName(self, "Выберите файл", "",
                                            "Java (java.exe java);;All (*)")
        if f: line_edit.setText(f)

    def _auto_detect_java(self):
        found = detect_java()
        if found:
            self._jp_input.setText(found[0])
            self._java_list.setText("Найдено:\n" + "\n".join(found[:5]))
        else:
            self._java_list.setText("Java не найдена в системе")

    def _reset_settings(self):
        r = QMessageBox.question(self, "Сброс", "Сбросить все настройки?")
        if r == QMessageBox.Yes:
            self.result_cfg = DEFAULT_CFG.copy()
            save_cfg(self._game_dir, self.result_cfg)
            self.accept()

    def _reinstall(self):
        gd = effective_game_dir(self.result_cfg)
        marker = gd / ".installed"
        r = QMessageBox.question(self, "Переустановка",
                                  f"Удалить маркер установки?\nИгра будет переустановлена при следующем запуске.\n\n{gd}")
        if r == QMessageBox.Yes:
            if marker.exists(): marker.unlink()
            QMessageBox.information(self, "Готово", "Маркер удалён.\nПри следующем запуске игра будет переустановлена.")

    def _save(self):
        self.result_cfg["memory_mb"] = RAM_OPTS[self._ram_slider.value()]
        self.result_cfg["width"] = self._w_spin.value()
        self.result_cfg["height"] = self._h_spin.value()
        self.result_cfg["jvm_args"] = self._jvm_input.text().strip()
        self.result_cfg["fullscreen"] = self._fs_check.isChecked()
        self.result_cfg["close_on_launch"] = self._close_check.isChecked()
        gd = self._gd_input.text().strip()
        self.result_cfg["game_dir"] = gd if gd != str(DEFAULT_GAME_DIR) else ""
        self.result_cfg["java_path"] = self._jp_input.text().strip()
        self.result_cfg["auto_connect"] = self._ac_check.isChecked()
        self.result_cfg["server_ip"] = self._server_input.text().strip()
        self.result_cfg["show_console"] = self._console_check.isChecked()
        self.result_cfg["check_files"] = self._check_files.isChecked()
        self.result_cfg["max_threads"] = self._threads_spin.value()
        save_cfg(effective_game_dir(self.result_cfg), self.result_cfg)
        self.accept()


def ram_label(mb):
    return f"{mb//1024} GB" if mb >= 1024 else f"{mb} MB"


# ══════════════════════════════════════════════════
#  Встроенный установщик (мастер при первом запуске)
# ══════════════════════════════════════════════════

INSTALL_MARKER = DEFAULT_GAME_DIR / ".launcher_installed"


def _generate_check_icon():
    """Генерирует иконку галочки (✓) и возвращает путь к файлу."""
    check_path = Path(tempfile.gettempdir()) / "bunlauncher_check.png"
    if not check_path.exists():
        pm = QPixmap(20, 20)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#ffffff"), 2.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        # Рисуем галочку ✓
        p.drawLine(QPointF(4, 10), QPointF(8, 15))
        p.drawLine(QPointF(8, 15), QPointF(16, 5))
        p.end()
        pm.save(str(check_path), "PNG")
    return str(check_path).replace("\\", "/")


def _get_installer_qss():
    check_icon = _generate_check_icon()
    return f"""
QDialog {{ background: #1a1816; }}
QLabel {{ color: #e0dcd4; }}
QLabel#title {{ font-size: 22px; font-weight: bold; color: white; }}
QLabel#subtitle {{ font-size: 13px; color: rgba(200,190,175,200); }}
QLabel#stepLabel {{ font-size: 10px; color: #666; font-weight: bold; letter-spacing: 2px; }}
QLabel#pathDisplay {{ font-size: 10px; color: #888; }}
QLabel#progress_status {{ font-size: 12px; color: #4ade80; }}

QLineEdit#pathInput {{
    background: #2a2622; color: white; border: 1px solid #3a352e;
    border-radius: 8px; padding: 10px 14px; font-size: 13px;
}}
QLineEdit#pathInput:focus {{ border-color: #26773B; }}

QPushButton#nextBtn {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4ade80, stop:1 #2d9a4e);
    border: 1px solid #5aff90; border-radius: 10px; color: white;
    font-size: 14px; font-weight: bold; padding: 12px 32px;
}}
QPushButton#nextBtn:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #6aff9a, stop:1 #3dbf60);
    border-color: #7affaa;
}}
QPushButton#nextBtn:disabled {{ background: #1a4a2a; color: rgba(255,255,255,80); border-color: #1a4a2a; }}

QPushButton#backBtn {{
    background: transparent; border: 1px solid #555; border-radius: 10px;
    color: #ccc; font-size: 13px; padding: 12px 24px;
}}
QPushButton#backBtn:hover {{ background: #3a352e; color: white; border-color: #4ade80; }}

QPushButton#browseBtn2 {{
    background: #2a2622; border: 1px solid #3a352e; border-radius: 8px;
    color: #ccc; font-size: 12px; padding: 10px 16px;
}}
QPushButton#browseBtn2:hover {{ background: #3a352e; color: white; }}

QCheckBox {{ color: #ccc; font-size: 13px; spacing: 10px; }}
QCheckBox::indicator {{
    width: 20px; height: 20px; border: 1px solid #3a352e;
    border-radius: 5px; background: #2a2622;
}}
QCheckBox::indicator:checked {{
    background: #26773B; border-color: #26773B;
    image: url({check_icon});
}}

QProgressBar#installProgress {{
    background: #2a2622; border: 1px solid #3a352e; border-radius: 7px; height: 14px;
}}
QProgressBar#installProgress::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #26773B, stop:0.5 #4ade80, stop:1 #26773B);
    border-radius: 6px;
}}
"""


# ═══════════════════════════════════════════
#  Minecraft-частицы для установщика
# ═══════════════════════════════════════════
MC_COLORS = [
    QColor(76, 175, 80, 140),   # зелёный (крипер)
    QColor(100, 200, 100, 100), # трава
    QColor(139, 90, 43, 120),   # дерево
    QColor(180, 160, 100, 80),  # песок
    QColor(120, 120, 120, 100), # камень
    QColor(60, 60, 60, 80),     # уголь
    QColor(40, 200, 120, 90),   # изумруд
    QColor(80, 160, 220, 70),   # алмаз
]

class InstallerParticles(QWidget):
    """Плавающие Minecraft-частицы (квадратные пиксели)."""
    def __init__(self, parent=None, count=40):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._particles = []
        for _ in range(count):
            self._particles.append({
                "x": _rnd.random(), "y": _rnd.random(),
                "vx": (_rnd.random() - 0.5) * 0.003,
                "vy": -_rnd.random() * 0.002 - 0.0005,
                "size": _rnd.randint(3, 8),
                "color": _rnd.choice(MC_COLORS),
                "alpha": _rnd.random() * 0.6 + 0.2,
            })
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tick(self):
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["y"] < -0.05:
                p["y"] = 1.05; p["x"] = _rnd.random()
            if p["x"] < -0.05 or p["x"] > 1.05:
                p["x"] = _rnd.random(); p["y"] = 1.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()
        for pt in self._particles:
            c = QColor(pt["color"])
            c.setAlphaF(pt["alpha"])
            p.fillRect(int(pt["x"]*w), int(pt["y"]*h), pt["size"], pt["size"], c)
        p.end()





class CreeperGame(QWidget):
    """Мини-игра: криперы гонятся за Стивом, кликай чтобы взрывать их!"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(180)
        self.setMinimumWidth(300)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self._score = 0
        self._creepers = []  # [{x, y, speed}]
        self._explosions = []  # [{x, y, frame}]
        
        self._steve_x = 400.0
        self._steve_y = 60.0
        self._steve_vx = 3.0
        self._steve_vy = 1.0
        self._frame = 0

        self._spawn_timer = QTimer(self)
        self._spawn_timer.timeout.connect(self._spawn)
        self._spawn_timer.start(800)  # Faster spawn rate
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(35)  # Slightly slower tick rate for easier clicking

        for _ in range(3): self._spawn()

    def _spawn(self):
        if len(self._creepers) > 7: return
        side = _rnd.choice(["left", "right"])
        self._creepers.append({
            "x": -20 if side == "left" else self.width() + 20,
            "y": _rnd.randint(10, self.height() - 30),
            "speed": _rnd.uniform(2.5, 4.5)  # Higher base speed
        })

    def _tick(self):
        self._frame = (self._frame + 1) % 4
        w, h = self.width(), self.height()
        
        # Стив бежит (быстрее!)
        self._steve_x += self._steve_vx * 1.5
        self._steve_y += self._steve_vy * 1.5
        if self._steve_x < 20: self._steve_x = 20; self._steve_vx = abs(self._steve_vx) * _rnd.uniform(0.8, 1.3)
        if self._steve_x > w - 50: self._steve_x = w - 50; self._steve_vx = -abs(self._steve_vx) * _rnd.uniform(0.8, 1.3)
        if self._steve_y < 10: self._steve_y = 10; self._steve_vy = abs(self._steve_vy) * _rnd.uniform(0.8, 1.3)
        if self._steve_y > h - 50: self._steve_y = h - 50; self._steve_vy = -abs(self._steve_vy) * _rnd.uniform(0.8, 1.3)
        
        # Случайная смена направления Стива (чаще)
        if _rnd.random() < 0.1:
            self._steve_vx = _rnd.choice([-1, 1]) * _rnd.uniform(3, 5)
            self._steve_vy = _rnd.uniform(-3, 3)

        # Криперы бегут за Стивом
        for c in self._creepers:
            dx = self._steve_x - c["x"]
            dy = self._steve_y - c["y"]
            dist = max(1.0, (dx**2 + dy**2)**0.5)
            # Иногда крипер дергается или ускоряется
            speed_mult = 1.6 if _rnd.random() < 0.05 else 1.0
            
            # Добавляем случайный зигзаг
            if _rnd.random() < 0.2:
                dx += _rnd.uniform(-30, 30)
                dy += _rnd.uniform(-30, 30)
                
            # Не подходим вплотную к Стиву, чтобы не пересекаться визуально
            if dist > 45:
                c["x"] += (dx / dist) * c["speed"] * speed_mult
                c["y"] += (dy / dist) * c["speed"] * speed_mult

        self._explosions = [e for e in self._explosions if e["frame"] < 8]
        for e in self._explosions: e["frame"] += 1
        self.update()

    def mousePressEvent(self, ev):
        mx, my = ev.position().x(), ev.position().y()
        # Проверка клика по криперу
        for c in self._creepers[:]:
            cx, cy = c["x"], c["y"]
            if cx - 10 <= mx <= cx + 45 and cy - 10 <= my <= cy + 50:
                self._explosions.append({"x": cx, "y": cy, "frame": 0})
                self._creepers.remove(c)
                self._score += 1
                break

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        s = 3

        # Криперы
        for c in self._creepers:
            cx, cy = int(c["x"]), int(c["y"])
            p.fillRect(cx, cy+1*s, 4*s, 3*s, QColor(60,140,60))
            p.fillRect(cx+s, cy+1*s, s, s, QColor(15,15,15))
            p.fillRect(cx+2*s, cy+1*s, s, s, QColor(15,15,15))
            p.fillRect(cx, cy+4*s, 4*s, 3*s, QColor(76,175,80))
            cleg = [0, s, 0, -s][self._frame]
            p.fillRect(cx+cleg, cy+7*s, s, 2*s, QColor(50,120,50))
            p.fillRect(cx+3*s-cleg, cy+7*s, s, 2*s, QColor(50,120,50))

        # Стив
        sx, sy = int(self._steve_x), int(self._steve_y)
        p.fillRect(sx+2*s, sy, 4*s, 4*s, QColor(139,90,43))
        p.fillRect(sx+2*s, sy+2*s, 4*s, 2*s, QColor(200,160,120))
        p.fillRect(sx+3*s, sy+2*s, s, s, QColor(40,30,15))
        p.fillRect(sx+5*s, sy+2*s, s, s, QColor(40,30,15))
        p.fillRect(sx+2*s, sy+4*s, 4*s, 3*s, QColor(60,160,220))
        leg = [-s, s, s, -s][self._frame]
        p.fillRect(sx+2*s+leg, sy+7*s, 2*s, 3*s, QColor(80,50,130))
        p.fillRect(sx+4*s-leg, sy+7*s, 2*s, 3*s, QColor(80,50,130))

        # Взрывы
        for e in self._explosions:
            r = e["frame"] * 4 + 8
            alpha = max(0, 255 - e["frame"] * 35)
            ex, ey = int(e["x"]) + 10, int(e["y"]) + 15
            p.setBrush(QColor(255, 200, 50, alpha))
            p.setPen(Qt.NoPen)
            p.drawEllipse(ex - r, ey - r, r * 2, r * 2)
            p.setBrush(QColor(255, 100, 30, alpha // 2))
            p.drawEllipse(ex - r//2, ey - r//2, r, r)

        p.setPen(QColor(200, 190, 170, 180))
        p.drawText(self.rect(), Qt.AlignRight | Qt.AlignTop, f"💥 Счёт: {self._score}")
        p.end()


class UpdateCheckSplash(QDialog):
    """Заглушка проверки обновлений (5 сек таймаут)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BunLauncher")
        self.setFixedSize(380, 180)
        self.setStyleSheet("QDialog{background:#1a1a1a;} QLabel{color:white;background:transparent;}")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 30, 40, 30)
        v.addStretch()
        t = QLabel("🔄  Проверка обновлений...")
        t.setStyleSheet("font-size:16px;font-weight:bold;color:white;background:transparent;")
        t.setAlignment(Qt.AlignCenter); v.addWidget(t)
        v.addSpacing(10)
        self._status = QLabel("Подключение к серверу...")
        self._status.setStyleSheet("font-size:12px;color:rgba(180,180,180,200);background:transparent;")
        self._status.setAlignment(Qt.AlignCenter); v.addWidget(self._status)
        v.addSpacing(10)
        bar = QProgressBar()
        bar.setFixedHeight(4); bar.setRange(0, 0)  # indeterminate
        bar.setTextVisible(False)
        bar.setStyleSheet("QProgressBar{background:#333;border:none;border-radius:2px;} QProgressBar::chunk{background:#4ade80;}")
        v.addWidget(bar)
        v.addStretch()
        # 2 сек — "ищем", потом "не найдено", потом закрыть
        QTimer.singleShot(2000, lambda: self._status.setText("Обновления не найдены ✓"))
        QTimer.singleShot(4000, self.accept)


# ═══════════════════════════════════════════
#  УСТАНОВЩИК (переопределяем класс)
# ═══════════════════════════════════════════

class InstallerWizard(QDialog):
    """Мастер установки — тёмный фон, Minecraft-частицы."""

    def __init__(self):
        QDialog.__init__(self)
        self.setWindowTitle("BunLauncher — Установка")
        self.setFixedSize(854, 480)
        self.setStyleSheet(_get_installer_qss() + "\nQDialog{background:#0e0c0a;}")
        self.install_path = str(DEFAULT_GAME_DIR)
        self.create_desktop = True
        self.create_startmenu = True
        self._page = 0

        ico = ASSETS_DIR / "bun.png"
        if ico.exists(): self.setWindowIcon(QIcon(str(ico)))

        main_v = QVBoxLayout(self)
        main_v.setContentsMargins(0, 0, 0, 0)
        main_v.setSpacing(0)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(50, 40, 50, 20)
        self._content_layout.setSpacing(14)
        main_v.addWidget(self._content, 1)

        self._btn_frame = QWidget()
        self._btn_frame.setObjectName("btnFrame")
        self._btn_frame.setFixedHeight(60)
        self._btn_frame.setStyleSheet("QWidget#btnFrame { background:rgba(14,12,10,240); border-top:1px solid rgba(80,70,55,60); }")
        bh = QHBoxLayout(self._btn_frame)
        bh.setContentsMargins(50, 8, 50, 8)
        self._back_btn = QPushButton("← Назад"); self._back_btn.setObjectName("backBtn")
        self._back_btn.setCursor(Qt.PointingHandCursor); self._back_btn.clicked.connect(self._prev_page)
        self._next_btn = QPushButton("Далее →"); self._next_btn.setObjectName("nextBtn")
        self._next_btn.setCursor(Qt.PointingHandCursor); self._next_btn.clicked.connect(self._next_page)
        sh = QGraphicsDropShadowEffect(); sh.setBlurRadius(20); sh.setOffset(0,4); sh.setColor(QColor(0,0,0,80))
        self._next_btn.setGraphicsEffect(sh)
        bh.addWidget(self._back_btn); bh.addStretch(); bh.addWidget(self._next_btn)
        main_v.addWidget(self._btn_frame)

        mc_colors = [QColor(76,175,80,120), QColor(139,90,43,100), QColor(100,100,100,80),
                     QColor(60,140,60,100), QColor(200,180,60,60), QColor(80,160,220,70)]
        self._px = []
        for _ in range(40):
            self._px.append({
                "x": _rnd.uniform(0, 854), "y": _rnd.uniform(0, 480),
                "vx": _rnd.uniform(-0.5, 0.5), "vy": _rnd.uniform(-0.3, 0.3),
                "sz": _rnd.randint(2, 5), "c": _rnd.choice(mc_colors)
            })
        self._ptimer = QTimer(self)
        self._ptimer.timeout.connect(self._tick_particles)
        self._ptimer.start(50)

        self._show_page(0)

    def _tick_particles(self):
        for p in self._px:
            p["x"] += p["vx"]; p["y"] += p["vy"]
            if p["x"] < -5: p["x"] = 859
            if p["x"] > 859: p["x"] = -5
            if p["y"] < -5: p["y"] = 485
            if p["y"] > 485: p["y"] = -5
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        for pt in self._px:
            p.fillRect(int(pt["x"]), int(pt["y"]), pt["sz"], pt["sz"], pt["c"])
        p.end()
        super().paintEvent(event)


    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout(): InstallerWizard._clear_layout(item.layout())

    _T = ""

    def _show_page(self, page):
        self._page = page
        # Плавная анимация перехода — fade out → swap → fade in
        eff = QGraphicsOpacityEffect(self._content)
        self._content.setGraphicsEffect(eff)
        fade_out = QPropertyAnimation(eff, b"opacity")
        fade_out.setDuration(150)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        def _swap():
            self._clear_layout(self._content_layout)
            [self._pg_welcome, self._pg_path, self._pg_install, self._pg_finish][page](self._content_layout)
            fade_in = QPropertyAnimation(eff, b"opacity")
            fade_in.setDuration(250)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.start()
            self._fade_in_anim = fade_in  # prevent GC
        fade_out.finished.connect(_swap)
        fade_out.start()
        self._fade_out_anim = fade_out  # prevent GC

        self._back_btn.setVisible(0 < page < 2)
        self._next_btn.setVisible(page != 2)
        if page == 0: self._next_btn.setText("Далее →")
        elif page == 1: self._next_btn.setText("Установить →")
        elif page == 3: self._next_btn.setText("Запустить BunLauncher ▶")

    def _pg_welcome(self, v):
        v.addStretch()
        s = QLabel("⛏  УСТАНОВКА"); s.setStyleSheet(f"color:#4ade80;font-size:11px;font-weight:bold;letter-spacing:3px;{self._T}")
        v.addWidget(s)
        t = QLabel("Добро пожаловать\nв BunLauncher!")
        t.setStyleSheet(f"color:white;font-size:30px;font-weight:bold;{self._T}"); v.addWidget(t)
        v.addSpacing(8)
        d = QLabel("Этот мастер установит BunLauncher на ваш компьютер.\nВсе файлы Minecraft будут извлечены автоматически.\nИнтернет-подключение не требуется.")
        d.setStyleSheet(f"color:rgba(220,210,195,200);font-size:14px;{self._T}"); d.setWordWrap(True); v.addWidget(d)
        v.addStretch()
        i = QLabel(f"Размер: ~1-2 GB  •  v1.0  •  {platform.system()} {platform.machine()}")
        i.setStyleSheet(f"color:rgba(150,140,125,150);font-size:10px;{self._T}"); v.addWidget(i)

    def _pg_path(self, v):
        s = QLabel("📂  НАСТРОЙКА"); s.setStyleSheet(f"color:#4ade80;font-size:11px;font-weight:bold;letter-spacing:3px;{self._T}")
        v.addWidget(s)
        t = QLabel("Выберите папку установки"); t.setStyleSheet(f"color:white;font-size:22px;font-weight:bold;{self._T}"); v.addWidget(t)
        d = QLabel("Игра и все файлы будут установлены в эту папку:")
        d.setStyleSheet(f"color:rgba(200,190,175,200);font-size:13px;{self._T}"); v.addWidget(d)
        v.addSpacing(8)
        ph = QHBoxLayout()
        self._path_input = QLineEdit(self.install_path); self._path_input.setObjectName("pathInput"); ph.addWidget(self._path_input, 1)
        b = QPushButton("📂 Обзор"); b.setObjectName("browseBtn2"); b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self._browse_path); ph.addWidget(b); v.addLayout(ph)
        fl = QLabel(f"Свободно: {self._free_space()} GB"); fl.setStyleSheet(f"color:#888;font-size:10px;{self._T}"); v.addWidget(fl)
        v.addSpacing(12)
        self._desk_check = QCheckBox("Создать ярлык на рабочем столе"); self._desk_check.setChecked(self.create_desktop); v.addWidget(self._desk_check)
        self._start_check = QCheckBox("Добавить в меню «Пуск»"); self._start_check.setChecked(self.create_startmenu); v.addWidget(self._start_check)
        v.addStretch()

    def _pg_install(self, v):
        # Креативная надпись наверху — белая, крупная
        self._fun_msgs = [
            "✨ Подождите, происходит магия...", "⛏ Добываем алмазы для вас...",
            "🌍 Генерируем чанки мира...", "🐑 Стрижём овец для текстур...",
            "🔥 Выплавляем железные слитки...", "🏗 Строим Нижний мир...",
            "🎵 Настраиваем нотные блоки...", "🌳 Сажаем деревья в биомах...",
            "💎 Зачаровываем предметы...", "🐉 Будим дракона Края...",
            "🧱 Укладываем красный камень...", "🗡 Точим мечи из незерита...",
        ]
        self._fun_idx = 0
        self._fun_label = QLabel(self._fun_msgs[0])
        self._fun_label.setStyleSheet(f"color:white;font-size:20px;font-weight:bold;{self._T}")
        v.addWidget(self._fun_label)
        v.addSpacing(10)

        # Прогресс
        self._install_bar = QProgressBar(); self._install_bar.setObjectName("installProgress")
        self._install_bar.setFixedHeight(14); self._install_bar.setTextVisible(False); self._install_bar.setRange(0,100); v.addWidget(self._install_bar)
        self._install_status = QLabel("Подготовка..."); self._install_status.setStyleSheet(f"color:#4ade80;font-size:14px;{self._T}")
        v.addWidget(self._install_status)
        v.addSpacing(8)

        # Мини-игра
        gl = QLabel("🎮 Лови и взрывай криперов пока ждёшь!")
        gl.setStyleSheet(f"color:rgba(220,210,195,180);font-size:12px;{self._T}"); gl.setAlignment(Qt.AlignCenter); v.addWidget(gl)
        self._creeper_game = CreeperGame(); v.addWidget(self._creeper_game)

        # Стив (удален, так как он теперь в мини-игре)
        v.addStretch()

        # Таймер сообщений
        self._msg_timer = QTimer(self); self._msg_timer.timeout.connect(self._rotate_msg); self._msg_timer.start(3000)
        QTimer.singleShot(300, self._do_install)

    def _rotate_msg(self):
        self._fun_idx = (self._fun_idx + 1) % len(self._fun_msgs)
        try: self._fun_label.setText(self._fun_msgs[self._fun_idx])
        except: pass


    def _pg_finish(self, v):
        v.addStretch()
        s = QLabel("✓  ГОТОВО"); s.setStyleSheet(f"color:#4ade80;font-size:13px;font-weight:bold;letter-spacing:3px;{self._T}"); v.addWidget(s)
        t = QLabel("BunLauncher установлен!"); t.setStyleSheet(f"color:white;font-size:28px;font-weight:bold;{self._T}"); v.addWidget(t)
        v.addSpacing(8)
        d = QLabel(f"Все файлы установлены в:\n{self.install_path}\n\nНажмите «Запустить BunLauncher» чтобы начать.")
        d.setStyleSheet(f"color:rgba(220,210,195,200);font-size:14px;{self._T}"); d.setWordWrap(True); v.addWidget(d)
        v.addStretch()

    def _browse_path(self):
        d = QFileDialog.getExistingDirectory(self, "Папка", self._path_input.text())
        if d: self._path_input.setText(d)

    def _free_space(self):
        try: return f"{shutil.disk_usage(Path(self.install_path).anchor or 'C:')[2]//(1024**3)}"
        except: return "?"

    def _next_page(self):
        if self._page == 0: self._show_page(1)
        elif self._page == 1:
            self.install_path = self._path_input.text().strip()
            self.create_desktop = self._desk_check.isChecked()
            self.create_startmenu = self._start_check.isChecked()
            if not self.install_path: QMessageBox.warning(self,"Ошибка","Укажите папку"); return
            self._show_page(2)
        elif self._page == 3: self.accept()

    def _prev_page(self):
        if self._page > 0: self._show_page(self._page - 1)

    def _do_install(self):
        self._thr = InstallerThread(self.install_path, self.create_desktop, self.create_startmenu)
        self._thr.progress.connect(lambda t,p: (self._install_bar.setValue(int(min(p,100))), self._install_status.setText(t)))
        self._thr.finished_ok.connect(self._on_done)
        self._thr.finished_err.connect(lambda m: (QMessageBox.critical(self,"Ошибка",m), self._show_page(1)))
        self._thr.start()

    def _on_done(self):
        INSTALL_MARKER.parent.mkdir(parents=True, exist_ok=True)
        INSTALL_MARKER.write_text(self.install_path, encoding="utf-8")
        self._show_page(3)


class InstallerThread(QThread):
    progress = Signal(str, float)
    finished_ok = Signal()
    finished_err = Signal(str)

    def __init__(self, path, desk, start):
        super().__init__()
        self.gd = Path(path); self.desk = desk; self.start_menu = start

    def run(self):
        try:
            self.gd.mkdir(parents=True, exist_ok=True)
            self.progress.emit("Создание папок...", 5)
            if not is_installed(self.gd):
                install_from_bundle(self.gd, progress_cb=lambda s,p: self.progress.emit(s, p*0.9))
            self.progress.emit("Создание ярлыков...", 92)
            exe = str(Path(sys.executable if not getattr(sys,"frozen",False) else sys.argv[0]).resolve())
            if platform.system() == "Windows":
                self._shortcuts(exe)
            self.progress.emit("Сохранение...", 98)
            cfg = load_cfg(self.gd); cfg["game_dir"] = str(self.gd); save_cfg(self.gd, cfg)
            self.progress.emit("Готово!", 100); self.finished_ok.emit()
        except Exception as ex: self.finished_err.emit(str(ex))

    def _shortcuts(self, exe):
        try:
            if self.desk:
                self._lnk(exe, str(Path(os.environ.get("USERPROFILE",""))/("Desktop/BunLauncher.lnk")))
            if self.start_menu:
                sm = Path(os.environ.get("APPDATA",""))/"Microsoft/Windows/Start Menu/Programs"
                sm.mkdir(parents=True, exist_ok=True)
                self._lnk(exe, str(sm/"BunLauncher.lnk"))
        except: pass

    def _lnk(self, target, link):
        subprocess.run(["powershell","-NoProfile","-Command",
            f'$w=New-Object -ComObject WScript.Shell;$s=$w.CreateShortcut("{link}");'
            f'$s.TargetPath="{target}";$s.WorkingDirectory="{Path(target).parent}";$s.Save()'],
            capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system()=="Windows" else 0)


def is_first_launch():
    return not INSTALL_MARKER.exists()


# ══════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    if is_first_launch():
        app.setStyleSheet(_get_installer_qss())
        wiz = InstallerWizard()
        if wiz.exec() != QDialog.Accepted: sys.exit(0)
        _override = Path(wiz.install_path)
    else:
        # Уже установлен — спрашиваем что делать
        app.setStyleSheet(GLOBAL_QSS)
        msg = QMessageBox()
        msg.setWindowTitle("BunLauncher")
        msg.setText("BunLauncher уже установлен.")
        msg.setInformativeText("Что вы хотите сделать?")
        launch_btn = msg.addButton("▶ Запустить", QMessageBox.AcceptRole)
        repair_btn = msg.addButton("🔧 Переустановить", QMessageBox.ActionRole)
        remove_btn = msg.addButton("🗑 Удалить", QMessageBox.DestructiveRole)
        cancel_btn = msg.addButton("Отмена", QMessageBox.RejectRole)
        msg.setDefaultButton(launch_btn)
        msg.exec()
        clicked = msg.clickedButton()

        if clicked == cancel_btn:
            sys.exit(0)
        elif clicked == remove_btn:
            try:
                gd = DEFAULT_GAME_DIR
                if INSTALL_MARKER.exists():
                    saved = INSTALL_MARKER.read_text(encoding="utf-8").strip()
                    if saved: gd = Path(saved)
                if QMessageBox.warning(None, "Удаление",
                    f"Удалить BunLauncher и все файлы из:\n{gd}?\n\nЭто действие нельзя отменить!",
                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                    shutil.rmtree(gd, ignore_errors=True)
                    INSTALL_MARKER.unlink(missing_ok=True)
                    QMessageBox.information(None, "Готово", "BunLauncher удалён.")
            except Exception as ex:
                QMessageBox.critical(None, "Ошибка", str(ex))
            sys.exit(0)
        elif clicked == repair_btn:
            INSTALL_MARKER.unlink(missing_ok=True)
            app.setStyleSheet(_get_installer_qss())
            wiz = InstallerWizard()
            if wiz.exec() != QDialog.Accepted: sys.exit(0)
            _override = Path(wiz.install_path)
        else:
            _override = None

    # Проверка обновлений (заглушка)
    app.setStyleSheet(GLOBAL_QSS)
    splash = UpdateCheckSplash()
    splash.exec()

    w = BunLauncher()
    if _override:
        w._game_dir = _override; w._cfg["game_dir"] = str(_override)
    w.show()
    sys.exit(app.exec())
