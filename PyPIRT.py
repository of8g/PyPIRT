import json
import subprocess
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional, Dict
import re
import datetime
import sys
import os
# --------- UI ---------
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox, filedialog
import tkinter.simpledialog

# Profil resmi için PIL importu - hata kontrolü ile
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL/Pillow kütüphanesi bulunamadı. Profil resimleri devre dışı.")


APP_NAME = "PyPIRT"
DATA_DIR = Path(".")
REHBER_PATH = DATA_DIR / "rehber.json"
SETTINGS_PATH = DATA_DIR / "PyPIRT.settings.json"
LOG_PATH = DATA_DIR / "PyPIRT.log"


# Tema
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ---------- Models ----------


@dataclass
class Kisi:
    ad: str
    numara: str
    etiketler: List[str] = field(default_factory=list)
    favori: bool = False
    profil_foto: Optional[str] = None  # Yeni alan


# ---------- ADB Yardımcı ----------


class ADBClient:
    def __init__(self, on_log):
        self.connected = False
        self.target = ""  # ip:port
        self.on_log = on_log

    def _run(self, args: List[str], timeout: Optional[int] = 15) -> subprocess.CompletedProcess:
        try:
            self.on_log(f"$ {' '.join(args)}")
            # Unicode sorununu çözmek için encoding parametresi ekle
            cp = subprocess.run(
                args, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                timeout=timeout, 
                text=True,
                encoding='utf-8',
                errors='replace'  # Decode edilemeyen karakterleri ? ile değiştir
            )
            out = (cp.stdout or "").strip()
            if out:
                self.on_log(out)
            return cp
        except subprocess.TimeoutExpired:
            self.on_log("Komut zaman aşımına uğradı.")
            raise
        except FileNotFoundError:
            self.on_log("Hata: 'adb' bulunamadı. Lütfen Android Platform Tools kurulu ve PATH'te olsun.")
            raise
        except UnicodeDecodeError as e:
            self.on_log(f"Karakter kodlama hatası: {e}")
            # Fallback: binary mode ile çalıştır
            try:
                cp = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
                out = cp.stdout.decode('utf-8', errors='replace').strip()
                if out:
                    self.on_log(out)
                return cp
            except Exception as fallback_e:
                self.on_log(f"Fallback da başarısız: {fallback_e}")
                raise

    def version(self) -> str:
        cp = self._run(["adb", "version"])
        return cp.stdout.strip()

    def connect(self, target: str) -> bool:
        self.target = target.strip()
        if not self.target:
            self.on_log("IP:Port boş olamaz.")
            return False
        cp = self._run(["adb", "connect", self.target])
        ok = ("connected to" in cp.stdout) or ("already connected to" in cp.stdout)
        self.connected = ok
        return ok

    def disconnect(self) -> None:
        if self.target:
            self._run(["adb", "disconnect", self.target])
        else:
            self._run(["adb", "disconnect"])
        self.connected = False

    def devices(self) -> List[str]:
        cp = self._run(["adb", "devices"])
        lines = (cp.stdout or "").splitlines()
        devs = []
        for ln in lines[1:]:
            if not ln.strip():
                continue  # cihazId\tstatus
            parts = ln.split("\t")
            if len(parts) >= 2 and parts[1].strip() == "device":
                devs.append(parts[0].strip())
        return devs

    def device_model(self) -> Optional[str]:
        try:
            cp = self._run(["adb", "shell", "getprop", "ro.product.model"])
            model = (cp.stdout or "").strip().splitlines()[-1].strip()
            return model if model else None
        except Exception:
            return None

    def _shell_am(self, args: List[str]) -> bool:
        cp = self._run(["adb", "shell", "am"] + args)
        return "Error" not in (cp.stdout or "")

    def call_immediate(self, number: str) -> bool:
        number = sanitize_number(number)
        return self._shell_am(["start", "-a", "android.intent.action.CALL", "-d", f"tel:{number}"])

    def call_dialer(self, number: str) -> bool:
        number = sanitize_number(number)
        return self._shell_am(["start", "-a", "android.intent.action.DIAL", "-d", f"tel:{number}"])

    def open_sms(self, number: str, body: str = "") -> bool:
        number = sanitize_number(number)
        pieces = ["start", "-a", "android.intent.action.SENDTO", "-d", f"sms:{number}"]
        if body:
            pieces += ["--es", "sms_body", body]
        return self._shell_am(pieces)

    def list_packages(self, system_apps=False) -> List[Dict[str, str]]:
        """Yüklü paketleri listele"""
        try:
            cmd = ["adb", "shell", "pm", "list", "packages"]
            if not system_apps:
                cmd.append("-3")  # Sadece kullanıcı uygulamaları
            
            # Paket listesi için özel encoding
            try:
                cp = subprocess.run(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT, 
                    timeout=30,  # Timeout artır
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                self.on_log(f"$ {' '.join(cmd)}")
                if cp.stdout:
                    self.on_log("Paket listesi alındı.")
            except Exception as e:
                self.on_log(f"Paket listesi hatası: {e}")
                return []
            
            packages = []
            for line in cp.stdout.splitlines():
                if line.startswith("package:"):
                    pkg_name = line.replace("package:", "").strip()
                    
                    # Uygulama adını almaya çalışma (basitleştirilmiş)
                    app_name = pkg_name  # Default olarak paket adı
                    
                    # Sadece bilinen paketler için özel isimler
                    if "whatsapp" in pkg_name.lower():
                        app_name = "WhatsApp"
                    elif "instagram" in pkg_name.lower():
                        app_name = "Instagram"
                    elif "facebook" in pkg_name.lower():
                        app_name = "Facebook"
                    elif "chrome" in pkg_name.lower():
                        app_name = "Chrome"
                    elif "youtube" in pkg_name.lower():
                        app_name = "YouTube"
                    elif "gmail" in pkg_name.lower():
                        app_name = "Gmail"
                    elif "maps" in pkg_name.lower():
                        app_name = "Google Maps"
                    elif "spotify" in pkg_name.lower():
                        app_name = "Spotify"
                    elif "netflix" in pkg_name.lower():
                        app_name = "Netflix"
                    elif "telegram" in pkg_name.lower():
                        app_name = "Telegram"
                    
                    packages.append({
                        "package": pkg_name,
                        "name": app_name
                    })
            
            return sorted(packages, key=lambda x: x["name"].lower())
        except Exception as e:
            self.on_log(f"Paket listesi alınamadı: {e}")
            return []

    def get_device_info(self) -> Dict[str, str]:
        info = {}
        try:
            # Her komut için ayrı ayrı try-catch
            try:
                info["model"] = self._run(["adb", "shell", "getprop", "ro.product.model"]).stdout.strip()
            except:
                info["model"] = "Bilinmiyor"
                
            try:
                info["brand"] = self._run(["adb", "shell", "getprop", "ro.product.brand"]).stdout.strip()
            except:
                info["brand"] = "Bilinmiyor"
                
            try:
                info["android_version"] = self._run(["adb", "shell", "getprop", "ro.build.version.release"]).stdout.strip()
            except:
                info["android_version"] = "Bilinmiyor"
                
            try:
                # Battery info için özel handling
                battery_output = self._run(["adb", "shell", "dumpsys", "battery"]).stdout.strip()
                info["battery"] = battery_output[:1000]  # İlk 1000 karakter
            except:
                info["battery"] = "Pil bilgisi alınamadı"
                
        except Exception as e:
            info["error"] = str(e)
        return info

    def launch_app(self, package_name: str) -> bool:
        cp = self._run(["adb", "shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"])
        return "Events injected" in (cp.stdout or "")

    def screenshot(self, save_path: str) -> bool:
        try:
            tmp_path = "/sdcard/PyPIRT_screenshot.png"
            self._run(["adb", "shell", "screencap", "-p", tmp_path])
            self._run(["adb", "pull", tmp_path, save_path])
            self._run(["adb", "shell", "rm", tmp_path])
            return Path(save_path).exists()
        except Exception:
            return False

    def push_file(self, local_path: str, remote_path: str) -> bool:
        cp = self._run(["adb", "push", local_path, remote_path])
        return "file" in (cp.stdout or "")

    def pull_file(self, remote_path: str, local_path: str) -> bool:
        cp = self._run(["adb", "pull", remote_path, local_path])
        return Path(local_path).exists()

    def get_app_info(self, package_name: str) -> Dict[str, str]:
        """Belirli bir uygulamanın detaylı bilgilerini al"""
        try:
            cp = self._run(["adb", "shell", "dumpsys", "package", package_name])
            info = {"package": package_name}
            
            for line in cp.stdout.splitlines():
                line = line.strip()
                if "versionName=" in line:
                    info["version"] = line.split("versionName=")[1].split()[0]
                elif "targetSdk=" in line:
                    info["target_sdk"] = line.split("targetSdk=")[1].split()[0]
                elif "install permissions:" in line.lower():
                    break
            
            return info
        except:
            return {"package": package_name}

    def get_app_icon(self, package_name: str) -> Optional[str]:
        """Uygulamanın ikonunu al ve kaydet"""
        try:
            # Uygulama ikonunu çıkar
            icon_path = f"./icons/{package_name}.png"
            os.makedirs("./icons", exist_ok=True)
            
            # APK yolunu al
            cp = self._run(["adb", "shell", "pm", "path", package_name])
            if "package:" not in cp.stdout:
                return None
                
            apk_path = cp.stdout.split("package:")[1].strip()
            
            # APK'yı geçici olarak çek
            temp_apk = f"./temp_{package_name}.apk"
            self._run(["adb", "pull", apk_path, temp_apk])
            
            if not Path(temp_apk).exists():
                return None
            
            # AAPT ile ikon bilgisini al (basit yöntem)
            # Bu kısım için alternatif yöntem kullanacağız
            
            # Geçici dosyayı temizle
            try:
                Path(temp_apk).unlink()
            except:
                pass
                
            return None  # Şimdilik ikon çıkarma devre dışı
        except Exception:
            return None

# ---------- Yardımcılar ----------


def sanitize_number(num: str) -> str:
    num = (num or "").strip()
    keep = re.sub(r"[^0-9+]", "", num)
    if keep.startswith("0") and len(keep) >= 10:
        keep = keep[1:]
    if keep.startswith("90") and not keep.startswith("+"):
        keep = "+" + keep
    return keep


def load_settings() -> Dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"son_hedef": "", "filtre_favori": False, "son_etiket": ""}


def save_settings(st: Dict):
    try:
        SETTINGS_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def ensure_rehber() -> None:
    if not REHBER_PATH.exists():
        sample = [
            {"ad": "Acil Servis", "numara": "112", "etiketler": ["acil"], "favori": True, "profil_foto": None},
            {"ad": "mergenc.dev", "numara": "+904444444444", "etiketler": ["is"], "favori": True, "profil_foto": None}        ]
        REHBER_PATH.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")


def load_rehber() -> List[Kisi]:
    ensure_rehber()
    try:
        raw = json.loads(REHBER_PATH.read_text(encoding="utf-8"))
        return [Kisi(**k) for k in raw]
    except Exception as e:
        messagebox.showerror(APP_NAME, f"Rehber okunamadı: {e}")
        return []


def save_rehber(kisiler: List[Kisi]):
    try:
        raw = [asdict(k) for k in kisiler]
        REHBER_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        messagebox.showerror(APP_NAME, f"Rehber kaydedilemedi: {e}")


def append_log(line: str):
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {line}\n")
    except Exception:
        pass


# Basit toast (kayan küçük bildirim)
class Toast(ctk.CTkToplevel):
    def __init__(self, master, text: str, ms: int = 1800):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg="#000000")
        self.label = ctk.CTkLabel(self, text=text, font=("Segoe UI", 14))
        self.label.pack(padx=14, pady=10)
        self.after(ms, self.destroy)
        self.update_idletasks()
        x = master.winfo_rootx() + master.winfo_width() - self.winfo_width() - 30
        y = master.winfo_rooty() + master.winfo_height() - self.winfo_height() - 30
        self.geometry(f"+{x}+{y}")


def show_toast(master, text, ms=1800):
    try:
        Toast(master, text, ms)
    except Exception:
        pass


# ---------- UI Uygulaması ----------


class PyPIRTApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME + " — Wi‑Fi ADB")
        self.geometry("1120x700")
        self.minsize(980, 600)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Notebook (Tab) widget ekle
        self.notebook = ctk.CTkTabview(self, width=1120, height=700)
        self.notebook.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=14, pady=14)
        
        # Ana sekme (Rehber)
        self.tab_main = self.notebook.add("📞 Rehber")
        self.tab_main.grid_rowconfigure(0, weight=1)
        self.tab_main.grid_columnconfigure(1, weight=1)
        
        # Uygulamalar sekmesi
        self.tab_apps = self.notebook.add("📱 Uygulamalar")
        self.tab_apps.grid_rowconfigure(0, weight=1)
        self.tab_apps.grid_columnconfigure(1, weight=1)

        self.settings = load_settings()
        self.adb = ADBClient(self._on_log)

        # Ana sekmeye sidebar, center, right ekle
        self._create_main_tab()
        
        # Uygulama sekmesini oluştur
        self._create_apps_tab()

        # ...existing code (başlatma işlemleri)...
        self._log_ui(f"{APP_NAME} başlatıldı.")
        self.kisiler: List[Kisi] = load_rehber()
        self.selected_index: Optional[int] = None
        self.profil_resim_img = None
        self.all_apps = []
        self.filtered_apps = []
        
        self._refresh_list()
        threading.Thread(target=self._adb_version_check, daemon=True).start()
        
        self.bind("<Control-s>", lambda e: self._save_people())
        self.bind("<Control-f>", lambda e: (self.search.focus_set(), "break"))
        self.bind("<Delete>", lambda e: self._delete_person())
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self._auto_status_thread = threading.Thread(target=self._auto_check_status, daemon=True)
        self._auto_status_thread.start()

    def _create_main_tab(self):
        """Ana rehber sekmesini oluştur"""
        # Sidebar
        self.sidebar = ctk.CTkFrame(self.tab_main, corner_radius=16)
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 8), pady=0)
        
        # Row konfigürasyonu
        for i in range(30):
            self.sidebar.grid_rowconfigure(i, weight=0)
        self.sidebar.grid_rowconfigure(20, weight=0)

        # Title
        self.lbl_title = ctk.CTkLabel(self.sidebar, text="PyPIRT", font=("Segoe UI", 28, "bold"))
        self.lbl_title.grid(row=0, column=0, padx=16, pady=(16, 6), sticky="w")

        # Connection bölümü
        self.entry_ip = ctk.CTkEntry(self.sidebar, placeholder_text="Cihaz IP:Port", width=240)
        self.entry_ip.insert(0, self.settings.get("son_hedef", ""))
        self.entry_ip.grid(row=1, column=0, padx=16, pady=(4, 6), sticky="w")

        row_conn = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        row_conn.grid(row=2, column=0, padx=12, pady=(0, 6), sticky="w")
        self.btn_connect = ctk.CTkButton(row_conn, text="🔌 Bağlan", command=self._connect, width=90)
        self.btn_connect.pack(side="left", padx=3)
        self.btn_disconnect = ctk.CTkButton(row_conn, text="⛔ Kes", command=self._disconnect, width=80)
        self.btn_disconnect.pack(side="left", padx=3)
        self.btn_test = ctk.CTkButton(row_conn, text="📡 Test", command=self._test_connection, width=80)
        self.btn_test.pack(side="left", padx=3)

        self.lbl_status = ctk.CTkLabel(self.sidebar, text="Durum: 🔴 Bağlı değil", text_color="#bbbbbb")
        self.lbl_status.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="w")

        self.devices_combo_var = tk.StringVar(value="Cihaz: (bilinmiyor)")
        self.devices_combo = ctk.CTkComboBox(self.sidebar, variable=self.devices_combo_var, values=["Cihaz: (yok)"], width=240, state="readonly")
        self.devices_combo.grid(row=4, column=0, padx=16, pady=(0, 6), sticky="w")
        self.btn_refresh_dev = ctk.CTkButton(self.sidebar, text="🔄 Cihazları Yenile", command=self._refresh_devices, width=240)
        self.btn_refresh_dev.grid(row=5, column=0, padx=16, pady=(0, 10), sticky="w")

        # Filters
        ctk.CTkLabel(self.sidebar, text="Filtreler", font=("Segoe UI", 16, "bold")).grid(row=6, column=0, padx=16, pady=(12, 2), sticky="w")
        self.search = ctk.CTkEntry(self.sidebar, placeholder_text="İsim / numara / etiket ara", width=240)
        self.search.grid(row=7, column=0, padx=16, pady=(6, 6), sticky="w")
        self.search.bind("<KeyRelease>", lambda e: self._refresh_list())

        self.chk_fav_var = tk.BooleanVar(value=self.settings.get("filtre_favori", False))
        self.chk_fav = ctk.CTkCheckBox(self.sidebar, text="Sadece favoriler", variable=self.chk_fav_var, command=self._refresh_list)
        self.chk_fav.grid(row=8, column=0, padx=16, pady=(0, 6), sticky="w")

        self.entry_tag = ctk.CTkEntry(self.sidebar, placeholder_text="Etikete göre filtre", width=240)
        self.entry_tag.insert(0, self.settings.get("son_etiket", ""))
        self.entry_tag.grid(row=9, column=0, padx=16, pady=(0, 12), sticky="w")
        self.entry_tag.bind("<KeyRelease>", lambda e: self._refresh_list())

        # Import/Export
        self.btn_import = ctk.CTkButton(self.sidebar, text="📥 Rehber Yükle", command=self._import_json, width=240)
        self.btn_import.grid(row=10, column=0, padx=16, pady=(4, 4), sticky="w")
        self.btn_export = ctk.CTkButton(self.sidebar, text="📤 Rehber Dışa Aktar", command=self._export_json, width=240)
        self.btn_export.grid(row=11, column=0, padx=16, pady=(4, 8), sticky="w")

        # Device info
        self.device_info_box = ctk.CTkTextbox(self.sidebar, height=80, width=240)
        self.device_info_box.grid(row=20, column=0, padx=16, pady=(0, 10), sticky="ew")
        self.device_info_box.insert("end", "Cihaz bilgisi yok.\n")
        self.device_info_box.configure(state="disabled")

        # Quick tools
        ctk.CTkLabel(self.sidebar, text="Hızlı Araçlar", font=("Segoe UI", 14)).grid(row=21, column=0, padx=16, pady=(0, 2), sticky="w")
        self.entry_package = ctk.CTkEntry(self.sidebar, placeholder_text="com.whatsapp", width=240)
        self.entry_package.grid(row=22, column=0, padx=16, pady=(0, 4), sticky="w")
        self.btn_launch_app = ctk.CTkButton(self.sidebar, text="📱 Uygulama Aç", command=self._launch_app, width=240)
        self.btn_launch_app.grid(row=23, column=0, padx=16, pady=(0, 6), sticky="w")

        self.btn_screenshot = ctk.CTkButton(self.sidebar, text="📸 Ekran Görüntüsü", command=self._take_screenshot, width=240)
        self.btn_screenshot.grid(row=24, column=0, padx=16, pady=(0, 10), sticky="w")

        # Center (Contact list)
        self.center = ctk.CTkFrame(self.tab_main, corner_radius=16)
        self.center.grid(row=0, column=1, sticky="nsew", padx=(8, 8), pady=0)
        self.center.grid_rowconfigure(1, weight=1)
        self.center.grid_columnconfigure(0, weight=1)

        topbar = ctk.CTkFrame(self.center, fg_color="transparent")
        topbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.lbl_list = ctk.CTkLabel(topbar, text="Rehber", font=("Segoe UI", 20, "bold"))
        self.lbl_list.pack(side="left")

        self.btn_add = ctk.CTkButton(topbar, text="➕ Kişi", width=90, command=self._add_person)
        self.btn_add.pack(side="right", padx=(6, 0))
        self.btn_save = ctk.CTkButton(topbar, text="💾 Kaydet", width=90, command=self._save_people)
        self.btn_save.pack(side="right", padx=(6, 0))
        self.btn_reload = ctk.CTkButton(topbar, text="🔁 Yenile", width=90, command=self._reload_people)
        self.btn_reload.pack(side="right", padx=(6, 0))

        self.list_frame = ctk.CTkScrollableFrame(self.center, label_text="Kişiler", corner_radius=14)
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # Right (Contact details)
        self.right = ctk.CTkFrame(self.tab_main, corner_radius=16)
        self.right.grid(row=0, column=2, sticky="nsne", padx=(8, 0), pady=0)
        for i in range(12):
            self.right.grid_rowconfigure(i, weight=0)
        self.right.grid_rowconfigure(12, weight=1)

        self.lbl_detail = ctk.CTkLabel(self.right, text="Seçilen Kişi", font=("Segoe UI", 20, "bold"))
        self.lbl_detail.grid(row=0, column=0, padx=16, pady=(16, 6), sticky="w")

        self.detail_name = ctk.CTkEntry(self.right, placeholder_text="Ad")
        self.detail_name.grid(row=1, column=0, padx=16, pady=6, sticky="ew")

        self.detail_number = ctk.CTkEntry(self.right, placeholder_text="Numara")
        self.detail_number.grid(row=2, column=0, padx=16, pady=6, sticky="ew")

        self.detail_tags = ctk.CTkEntry(self.right, placeholder_text="Etiketler (virgülle)")
        self.detail_tags.grid(row=3, column=0, padx=16, pady=6, sticky="ew")

        self.fav_var = tk.BooleanVar(value=False)
        self.detail_fav = ctk.CTkCheckBox(self.right, text="Favori", variable=self.fav_var)
        self.detail_fav.grid(row=4, column=0, padx=16, pady=(0, 10), sticky="w")

        self.profil_resim_label = ctk.CTkLabel(self.right, text="Profil Resmi Yok", width=120, height=120, corner_radius=60, fg_color="#444444", justify="center")
        self.profil_resim_label.grid(row=5, column=0, padx=16, pady=10, sticky="n")

        self.btn_profil_sec = ctk.CTkButton(self.right, text="📁 Profil Resmi Seç", command=self._select_profile_image)
        self.btn_profil_sec.grid(row=6, column=0, padx=16, pady=(0, 10), sticky="ew")

        self.btn_call_now = ctk.CTkButton(self.right, text="📞 Hemen Ara", command=self._call_now)
        self.btn_call_now.grid(row=7, column=0, padx=16, pady=6, sticky="ew")

        self.btn_call_dialer = ctk.CTkButton(self.right, text="📲 Telefon Uygulaması", command=self._call_dialer)
        self.btn_call_dialer.grid(row=8, column=0, padx=16, pady=6, sticky="ew")

        self.sms_entry = ctk.CTkEntry(self.right, placeholder_text="SMS metni")
        self.sms_entry.grid(row=9, column=0, padx=16, pady=(6, 4), sticky="ew")
        self.btn_sms = ctk.CTkButton(self.right, text="✉️ SMS Gönder", command=self._open_sms)
        self.btn_sms.grid(row=10, column=0, padx=16, pady=(4, 10), sticky="ew")

        self.btn_delete = ctk.CTkButton(self.right, text="🗑️ Kişiyi Sil", fg_color="#8b1e1e", hover_color="#691515", command=self._delete_person)
        self.btn_delete.grid(row=11, column=0, padx=16, pady=(2, 10), sticky="ew")

        self.logbox = ctk.CTkTextbox(self.right, height=180)
        self.logbox.grid(row=12, column=0, padx=16, pady=(6, 16), sticky="nsew")
        self.logbox.bind("<Return>", self._log_command_entered)

    def _create_apps_tab(self):
        """Uygulamalar sekmesini oluştur"""
        # Sol panel - Uygulama kontrolleri
        apps_left = ctk.CTkFrame(self.tab_apps, corner_radius=16)
        apps_left.grid(row=0, column=0, sticky="nsw", padx=(0, 8), pady=0)
        
        ctk.CTkLabel(apps_left, text="Uygulama Yönetimi", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, padx=16, pady=(16, 10), sticky="w")
        
        # ADB durumu
        self.apps_status = ctk.CTkLabel(apps_left, text="Durum: Bağlantı gerekli", text_color="#bbbbbb")
        self.apps_status.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")
        
        # Sistem uygulamaları seçeneği
        self.include_system_var = tk.BooleanVar(value=False)
        self.chk_system = ctk.CTkCheckBox(apps_left, text="Sistem uygulamaları dahil", variable=self.include_system_var)
        self.chk_system.grid(row=2, column=0, padx=16, pady=(0, 10), sticky="w")
        
        # Listele butonu
        self.btn_list_apps = ctk.CTkButton(apps_left, text="📱 Uygulamaları Listele", command=self._list_apps, width=240, height=40)
        self.btn_list_apps.grid(row=3, column=0, padx=16, pady=(0, 15), sticky="w")
        
        # Arama kutusu
        ctk.CTkLabel(apps_left, text="Arama", font=("Segoe UI", 14, "bold")).grid(row=4, column=0, padx=16, pady=(0, 5), sticky="w")
        self.app_search = ctk.CTkEntry(apps_left, placeholder_text="Uygulama ara...", width=240)
        self.app_search.grid(row=5, column=0, padx=16, pady=(0, 15), sticky="w")
        self.app_search.bind("<KeyRelease>", self._filter_apps)
        
        # Hızlı işlemler
        ctk.CTkLabel(apps_left, text="Hızlı İşlemler", font=("Segoe UI", 14, "bold")).grid(row=6, column=0, padx=16, pady=(0, 5), sticky="w")
        
        self.apps_package_entry = ctk.CTkEntry(apps_left, placeholder_text="Paket adı", width=240)
        self.apps_package_entry.grid(row=7, column=0, padx=16, pady=(0, 5), sticky="w")
        
        self.apps_launch_btn = ctk.CTkButton(apps_left, text="🚀 Uygulamayı Aç", command=self._launch_app, width=240)
        self.apps_launch_btn.grid(row=8, column=0, padx=16, pady=(0, 10), sticky="w")
        
        # Dosya işlemleri
        ctk.CTkLabel(apps_left, text="Dosya İşlemleri", font=("Segoe UI", 14, "bold")).grid(row=9, column=0, padx=16, pady=(10, 5), sticky="w")
        
        self.btn_push_file = ctk.CTkButton(apps_left, text="📤 Dosya Gönder", command=self._push_file, width=240)
        self.btn_push_file.grid(row=10, column=0, padx=16, pady=(0, 5), sticky="w")
        
        self.btn_pull_file = ctk.CTkButton(apps_left, text="📥 Dosya Al", command=self._pull_file, width=240)
        self.btn_pull_file.grid(row=11, column=0, padx=16, pady=(0, 5), sticky="w")

        # Ana uygulama listesi
        apps_main = ctk.CTkFrame(self.tab_apps, corner_radius=16)
        apps_main.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        apps_main.grid_rowconfigure(1, weight=1)
        apps_main.grid_columnconfigure(0, weight=1)
        
        # Başlık
        apps_topbar = ctk.CTkFrame(apps_main, fg_color="transparent")
        apps_topbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        
        self.apps_title = ctk.CTkLabel(apps_topbar, text="Yüklü Uygulamalar", font=("Segoe UI", 20, "bold"))
        self.apps_title.pack(side="left")
        
        self.apps_count = ctk.CTkLabel(apps_topbar, text="(0 uygulama)", font=("Segoe UI", 14))
        self.apps_count.pack(side="left", padx=(10, 0))
        
        # Uygulama listesi
        self.apps_frame = ctk.CTkScrollableFrame(apps_main, label_text="Uygulamalar")
        self.apps_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    def _update_apps_list(self):
        """Uygulama listesi UI'sini güncelle"""
        # Mevcut widget'ları temizle
        for widget in self.apps_frame.winfo_children():
            widget.destroy()
            
        if not self.filtered_apps:
            lbl = ctk.CTkLabel(self.apps_frame, text="❌ Uygulama bulunamadı\n\n'📱 Uygulamaları Listele' butonuna basın", 
                             font=("Segoe UI", 14), justify="center")
            lbl.pack(pady=50)
            self.apps_count.configure(text="(0 uygulama)")
            return
            
        self.apps_count.configure(text=f"({len(self.filtered_apps)} uygulama)")
            
        for app in self.filtered_apps:
            app_frame = ctk.CTkFrame(self.apps_frame, height=60)
            app_frame.pack(fill="x", padx=5, pady=3)
            app_frame.grid_propagate(False)
            
            # İkon alanı (şimdilik placeholder)
            icon_frame = ctk.CTkFrame(app_frame, width=48, height=48, corner_radius=8)
            icon_frame.grid(row=0, column=0, padx=10, pady=6, sticky="w")
            icon_frame.grid_propagate(False)
            
            # Android ikonu emoji
            icon_lbl = ctk.CTkLabel(icon_frame, text="📱", font=("Segoe UI", 20))
            icon_lbl.pack(expand=True)
            
            # Uygulama bilgileri
            info_frame = ctk.CTkFrame(app_frame, fg_color="transparent")
            info_frame.grid(row=0, column=1, padx=10, pady=6, sticky="ew")
            app_frame.grid_columnconfigure(1, weight=1)
            
            # Uygulama adı
            app_name = app["name"][:40] + "..." if len(app["name"]) > 40 else app["name"]
            name_lbl = ctk.CTkLabel(info_frame, text=app_name, font=("Segoe UI", 14, "bold"), anchor="w")
            name_lbl.pack(fill="x", pady=(2, 0))
            
            # Paket adı
            package_lbl = ctk.CTkLabel(info_frame, text=app["package"], font=("Segoe UI", 11), 
                                     text_color="#888888", anchor="w")
            package_lbl.pack(fill="x")
            
            # Butonlar
            btn_frame = ctk.CTkFrame(app_frame, fg_color="transparent")
            btn_frame.grid(row=0, column=2, padx=10, pady=6, sticky="e")
            
            # Aç butonu
            btn_open = ctk.CTkButton(btn_frame, text="🚀 Aç", width=70, height=28,
                                   command=lambda pkg=app["package"]: self._launch_app_from_list(pkg))
            btn_open.pack(side="top", pady=2)
            
            # Kopyala butonu
            btn_copy = ctk.CTkButton(btn_frame, text="📋 Kopyala", width=70, height=28,
                                   command=lambda pkg=app["package"]: self._copy_package_name(pkg))
            btn_copy.pack(side="top", pady=2)

    def _copy_package_name(self, package_name: str):
        """Paket adını panoya kopyala"""
        try:
            self.clipboard_clear()
            self.clipboard_append(package_name)
            self.update()
            show_toast(self, f"📋 Kopyalandı: {package_name[:30]}...", 1500)
            
            # Entry'lere de yaz
            self.entry_package.delete(0, "end")
            self.entry_package.insert(0, package_name)
            
            self.apps_package_entry.delete(0, "end")
            self.apps_package_entry.insert(0, package_name)
            
        except Exception:
            show_toast(self, "Kopyalama başarısız", 1400)

    def _launch_app(self):
        """Uygulama aç (her iki entry'den de çalışır)"""
        pkg = self.entry_package.get().strip() or self.apps_package_entry.get().strip()
        if not pkg:
            show_toast(self, "Paket adı girin", 1400)
            return
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return
        def job():
            ok = self.adb.launch_app(pkg)
            self._log_ui(f"{pkg} açma {'başarılı' if ok else 'başarısız'}")
            show_toast(self, "📱 Uygulama açıldı" if ok else "⚠️ Açma başarısız")
        threading.Thread(target=job, daemon=True).start()

    def _take_screenshot(self):
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return
        fp = filedialog.asksaveasfilename(title="Ekran görüntüsü kaydet", defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not fp:
            return
        def job():
            ok = self.adb.screenshot(fp)
            self._log_ui(f"Ekran görüntüsü {'alındı' if ok else 'alınamadı'}: {fp}")
            show_toast(self, "📸 Görüntü alındı" if ok else "⚠️ Alınamadı")
        threading.Thread(target=job, daemon=True).start()

    def _push_file(self):
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return
        fp = filedialog.askopenfilename(title="Gönderilecek dosyayı seç")
        if not fp:
            return
        remote_fp = tk.simpledialog.askstring("Telefona yol", "Telefonda kaydedilecek yol (örn: /sdcard/Download/)")
        if not remote_fp:
            return
        def job():
            ok = self.adb.push_file(fp, remote_fp)
            self._log_ui(f"Dosya gönderme {'başarılı' if ok else 'başarısız'}: {fp} → {remote_fp}")
            show_toast(self, "📤 Dosya gönderildi" if ok else "⚠️ Gönderilemedi")
        threading.Thread(target=job, daemon=True).start()

    def _pull_file(self):
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return
        remote_fp = tk.simpledialog.askstring("Telefondan yol", "Telefondan alınacak dosya yolu (örn: /sdcard/Download/test.txt)")
        if not remote_fp:
            return
        fp = filedialog.asksaveasfilename(title="Bilgisayara kaydet", defaultextension="", filetypes=[("Tüm Dosyalar", "*.*")])
        if not fp:
            return
        def job():
            ok = self.adb.pull_file(remote_fp, fp)
            self._log_ui(f"Dosya alma {'başarılı' if ok else 'başarısız'}: {remote_fp} → {fp}")
            show_toast(self, "📥 Dosya alındı" if ok else "⚠️ Alınamadı")
        threading.Thread(target=job, daemon=True).start()

    def _list_apps(self):
        """Telefondaki uygulamaları listele"""
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return
            
        def job():
            self._log_ui("Uygulamalar listeleniyor...")
            show_toast(self, "📱 Uygulamalar yükleniyor...", 2000)
            
            include_system = self.include_system_var.get()
            apps = self.adb.list_packages(system_apps=include_system)
            
            self.all_apps = apps
            self.filtered_apps = apps.copy();
            
            self._log_ui(f"{len(apps)} uygulama bulundu.")
            
            # UI'yi güncelle
            self.after(0, self._update_apps_list)
            
        threading.Thread(target=job, daemon=True).start()

    def _filter_apps(self, event=None):
        """Uygulama listesini filtrele"""
        search_term = self.app_search.get().lower().strip()
        
        if not search_term:
            self.filtered_apps = self.all_apps.copy()
        else:
            self.filtered_apps = [
                app for app in self.all_apps 
                if search_term in app["name"].lower() or search_term in app["package"].lower()
            ]
            
        self._update_apps_list()

    def _launch_app_from_list(self, package_name: str):
        """Listeden seçilen uygulamayı aç"""
        if not self.adb.connected:
            show_toast(self, "ADB bağlı değil!", 1400)
            return
            
        def job():
            ok = self.adb.launch_app(package_name)
            self._log_ui(f"{package_name} açma {'başarılı' if ok else 'başarısız'}")
            show_toast(self, "📱 Uygulama açıldı" if ok else "⚠️ Açma başarısız")
            
        threading.Thread(target=job, daemon=True).start()

    def _log_ui(self, text: str):
        append_log(text)
        try:
            self.logbox.configure(state="normal")
            self.logbox.insert("end", text + "\n")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        except:
            pass  # Eğer logbox henüz oluşturulmadıysa sessizce geç

    def _on_log(self, text: str):
        self._log_ui(text)

    def _set_status(self, ok: bool, model: Optional[str] = None):
        """Durum güncelle (hem ana hem apps sekmesi için)"""
        if ok:
            label = f"Durum: 🟢 Bağlı"
            if model:
                label += f" — {model}"
        else:
            label = "Durum: 🔴 Bağlı değil"
            
        self.lbl_status.configure(text=label)
        self.apps_status.configure(text=label)
        
        self.btn_connect.configure(state=("disabled" if ok else "normal"))
        self.btn_disconnect.configure(state=("normal" if ok else "disabled"))

        if ok:
            info = self.adb.get_device_info()
            self.device_info_box.configure(state="normal")
            self.device_info_box.delete("1.0", "end")
            self.device_info_box.insert("end", f"Model: {info.get('model','?')}\nMarka: {info.get('brand','?')}\nAndroid: {info.get('android_version','?')}\n")
            bat = info.get("battery", "")
            m = re.search(r"level: (\d+)", bat)
            if m:
                self.device_info_box.insert("end", f"Pil: %{m.group(1)}\n")
            self.device_info_box.configure(state="disabled")
        else:
            self.device_info_box.configure(state="normal")
            self.device_info_box.delete("1.0", "end")
            self.device_info_box.insert("end", "Cihaz bilgisi yok.\n")
            self.device_info_box.configure(state="disabled")

    def _connect(self):
        target = self.entry_ip.get().strip()
        self.settings["son_hedef"] = target
        save_settings(self.settings)

        def job():
            ok = self.adb.connect(target)
            model = None
            if ok:
                model = self.adb.device_model()
            self.after(0, lambda: self._set_status(ok, model))
            if ok:
                self.after(0, lambda: show_toast(self, f"✅ Bağlandı: {target}"))
            else:
                self.after(0, lambda: messagebox.showwarning(APP_NAME, "Bağlantı kurulamadı. IP:Port ve ağ durumunu kontrol edin."))

        threading.Thread(target=job, daemon=True).start()

    def _disconnect(self):
        def job():
            self.adb.disconnect()
            self.after(0, lambda: self._set_status(False))
            self.after(0, lambda: show_toast(self, "🔌 Bağlantı kesildi", 1400))

        threading.Thread(target=job, daemon=True).start()

    def _test_connection(self):
        def job():
            try:
                devs = self.adb.devices()
                if not devs:
                    self.after(0, lambda: messagebox.showerror(APP_NAME, "❌ Telefon bulunamadı."))
                    self.after(0, lambda: self._set_status(False))
                    return
                model = self.adb.device_model()
                self.after(0, lambda: self._set_status(True, model))
                self.after(0, lambda: messagebox.showinfo(APP_NAME, f"✅ Telefon bağlı!\nCihaz: {devs[0]}{(' — ' + model) if model else ''}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(APP_NAME, f"Bağlantı testi başarısız:\n{e}"))

        threading.Thread(target=job, daemon=True).start()

    def _refresh_devices(self):
        def job():
            try:
                devs = self.adb.devices()
                if not devs:
                    self.after(0, lambda: self.devices_combo.configure(values=["(cihaz yok)"]))
                    self.after(0, lambda: self.devices_combo_var.set("(cihaz yok)"))
                    self.after(0, lambda: self._set_status(False))
                    self.after(0, lambda: show_toast(self, "Cihaz bulunamadı"))
                else:
                    self.after(0, lambda: self.devices_combo.configure(values=devs))
                    self.after(0, lambda: self.devices_combo_var.set(devs[0]))
                    self.after(0, lambda: self._set_status(True, self.adb.device_model()))
                    self.after(0, lambda: show_toast(self, f"{len(devs)} cihaz"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(APP_NAME, f"Cihazlar listelenemedi:\n{e}"))

        threading.Thread(target=job, daemon=True).start()

    def _adb_version_check(self):
        try:
            ver = self.adb.version().splitlines()[0]
            self._log_ui(ver)
        except Exception:
            pass

    def _auto_check_status(self):
        """Bağlantı durumunu otomatik kontrol et"""
        while True:
            try:
                time.sleep(10)  # 10 saniyede bir kontrol et
                if hasattr(self, 'adb') and self.adb:
                    devs = self.adb.devices()
                    if not devs:
                        self.after(0, lambda: self._set_status(False))
                    else:
                        model = self.adb.device_model()
                        self.after(0, lambda: self._set_status(True, model))
                else:
                    break
            except Exception:
                self.after(0, lambda: self._set_status(False))

    # ...existing code (rehber metodları)...

    def _refresh_list(self):
        query = self.search.get().lower().strip()
        tagf = self.entry_tag.get().lower().strip()
        favonly = self.chk_fav_var.get()

        for widget in self.list_frame.winfo_children():
            widget.destroy()

        def match(k: Kisi) -> bool:
            if favonly and not k.favori:
                return False
            hay = " ".join([k.ad.lower(), k.numara.lower(), " ".join([t.lower() for t in k.etiketler])])
            if query and query not in hay:
                return False
            if tagf and tagf not in [t.lower() for t in k.etiketler]:
                return False
            return True

        for idx, kisi in enumerate(self.kisiler):
            if not match(kisi):
                continue
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", padx=8, pady=6)

            # Profil fotoğrafı küçük gösterimi (CTkImage kullanarak)
            if PIL_AVAILABLE and kisi.profil_foto and Path(kisi.profil_foto).exists():
                try:
                    img = Image.open(kisi.profil_foto)
                    width, height = img.size
                    size = min(width, height)
                    left = (width - size) // 2
                    top = (height - size) // 2
                    img = img.crop((left, top, left + size, top + size))
                    img = img.resize((32, 32), Image.Resampling.LANCZOS)
                    
                    # CTkImage kullan
                    img_ctk = ctk.CTkImage(light_image=img, dark_image=img, size=(32, 32))
                    lbl_img = ctk.CTkLabel(row, image=img_ctk, text="", width=32, height=32)
                    lbl_img.pack(side="left", padx=(0, 8))
                except Exception:
                    pass

            star = "★" if kisi.favori else "☆"
            btn = ctk.CTkButton(row, text=f"{star} {kisi.ad} — {kisi.numara}", fg_color="transparent", hover_color="#222222", text_color="white", anchor="w", command=lambda i=idx: self._select(i))
            btn.pack(side="left", fill="x", expand=True)
            fav_btn = ctk.CTkButton(row, text="Fav", width=44, command=lambda i=idx: self._toggle_fav(i))
            fav_btn.pack(side="right", padx=(6, 0))
            call_btn = ctk.CTkButton(row, text="Ara", width=44, command=lambda i=idx: self._quick_call(i))
            call_btn.pack(side="right", padx=(6, 0))

    def _toggle_fav(self, idx: int):
        self.kisiler[idx].favori = not self.kisiler[idx].favori
        self._refresh_list()

    def _quick_call(self, idx: int):
        self.selected_index = idx
        self._call_now()

    def _select(self, idx: int):
        self.selected_index = idx
        kisi = self.kisiler[idx]
        self.detail_name.delete(0, "end")
        self.detail_name.insert(0, kisi.ad)
        self.detail_number.delete(0, "end")
        self.detail_number.insert(0, kisi.numara)
        self.detail_tags.delete(0, "end")
        self.detail_tags.insert(0, ", ".join(kisi.etiketler))
        self.fav_var.set(kisi.favori)
        self._load_profile_image(kisi.profil_foto)

    def _load_profile_image(self, image_path: Optional[str]):
        # Eğer PIL mevcut değilse profil resimlerini devre dışı bırak
        if not PIL_AVAILABLE:
            self.profil_resim_label.configure(text="PIL gerekli")
            return

        if image_path and Path(image_path).exists():
            try:
                # Resim dosyasını aç ve boyutlandır
                img = Image.open(image_path)
                
                # Resmi kare yaparak kırp
                width, height = img.size
                size = min(width, height)
                left = (width - size) // 2
                top = (height - size) // 2
                img = img.crop((left, top, left + size, top + size))
                
                # 100x100 boyutuna getir
                img = img.resize((100, 100), Image.Resampling.LANCZOS)
                
                # CTkImage kullan (HighDPI uyarısını önlemek için)
                try:
                    self.profil_resim_img = ctk.CTkImage(light_image=img, dark_image=img, size=(100, 100))
                    self.profil_resim_label.configure(image=self.profil_resim_img, text="")
                except:
                    # Fallback: PhotoImage kullan
                    self.profil_resim_img = ImageTk.PhotoImage(img)
                    self.profil_resim_label.configure(image=self.profil_resim_img, text="")
                
            except Exception as ex:
                self.profil_resim_img = None
                self.profil_resim_label.configure(image="", text="Resim hatası")
                self._log_ui(f"Profil resmi yükleme hatası: {ex}")
        else:
            self.profil_resim_img = None
            self.profil_resim_label.configure(image="", text="Profil Resmi Yok")

    def _select_profile_image(self):
        if not PIL_AVAILABLE:
            show_toast(self, "PIL/Pillow kütüphanesi gerekli", 2000)
            return
            
        if self.selected_index is None:
            show_toast(self, "Önce bir kişi seçin", 1400)
            return
            
        fp = filedialog.askopenfilename(
            title="Profil Resmi Seç", 
            filetypes=[
                ("Tüm Resim Dosyaları", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("PNG Dosyaları", "*.png"),
                ("JPEG Dosyaları", "*.jpg *.jpeg"),
                ("Tüm Dosyalar", "*.*")
            ]
        )
        if not fp:
            return
            
        # Dosyanın gerçekten var olduğunu kontrol et
        if not Path(fp).exists():
            show_toast(self, "Seçilen dosya bulunamadı", 2000)
            return
            
        self.kisiler[self.selected_index].profil_foto = fp
        self._load_profile_image(fp)
        show_toast(self, "Profil resmi seçildi")

    def _read_detail_into_model(self) -> Optional[Kisi]:
        if self.selected_index is None:
            messagebox.showwarning(APP_NAME, "Önce listeden bir kişi seçin.")
            return None
        ad = self.detail_name.get().strip()
        num = self.detail_number.get().strip()
        tags = [t.strip() for t in self.detail_tags.get().split(",") if t.strip()]
        fav = self.fav_var.get()
        profil_foto = self.kisiler[self.selected_index].profil_foto
        if not ad or not num:
            messagebox.showwarning(APP_NAME, "Ad ve numara zorunludur.")
            return None
        self.kisiler[self.selected_index] = Kisi(ad=ad, numara=num, etiketler=tags, favori=fav, profil_foto=profil_foto)
        self._refresh_list()
        return self.kisiler[self.selected_index]

    def _call_now(self):
        kisi = self._read_detail_into_model()
        if not kisi:
            return
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return

        def job():
            ok = self.adb.call_immediate(kisi.numara)
            self._log_ui(f"Arama başlatma {'başarılı' if ok else 'başarısız'}: {kisi.ad}")
            show_toast(self, "📞 Arama başlatıldı" if ok else "⚠️ Arama başlatılamadı")

        threading.Thread(target=job, daemon=True).start()

    def _call_dialer(self):
        kisi = self._read_detail_into_model()
        if not kisi:
            return
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return

        def job():
            ok = self.adb.call_dialer(kisi.numara)
            self._log_ui(f"Telefon uygulaması {'açıldı' if ok else 'açılamadı'}: {kisi.ad}")
            show_toast(self, "📲 Telefon uygulaması açıldı" if ok else "⚠️ Açılamadı")

        threading.Thread(target=job, daemon=True).start()

    def _open_sms(self):
        kisi = self._read_detail_into_model()
        if not kisi:
            return
        if not self.adb.connected:
            messagebox.showwarning(APP_NAME, "Önce ADB bağlantısını kurun.")
            return
        body = self.sms_entry.get().strip()

        def job():
            ok = self.adb.open_sms(kisi.numara, body)
            self._log_ui(f"SMS ekranı {'açıldı' if ok else 'açılamadı'}: {kisi.ad}")
            show_toast(self, "✉️ SMS ekranı açıldı" if ok else "⚠️ Açılamadı")

        threading.Thread(target=job, daemon=True).start()

    def _add_person(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Yeni Kişi")
        dlg.geometry("420x280")
        
        ctk.CTkLabel(dlg, text="Ad").pack(padx=12, pady=(14, 4))
        e_ad = ctk.CTkEntry(dlg)
        e_ad.pack(padx=12, pady=4, fill="x")
        
        ctk.CTkLabel(dlg, text="Numara").pack(padx=12, pady=4)
        e_num = ctk.CTkEntry(dlg)
        e_num.pack(padx=12, pady=4, fill="x")
        
        ctk.CTkLabel(dlg, text="Etiketler (virgülle)").pack(padx=12, pady=4)
        e_tags = ctk.CTkEntry(dlg)
        e_tags.pack(padx=12, pady=4, fill="x")
        
        var_fav = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(dlg, text="Favori", variable=var_fav).pack(padx=12, pady=6)

        profil_resim_path = [None]

        def on_profile_select():
            if not PIL_AVAILABLE:
                show_toast(dlg, "PIL/Pillow kütüphanesi gerekli", 2000)
                return
                
            fp = filedialog.askopenfilename(
                title="Profil Resmi Seç", 
                filetypes=[
                    ("Tüm Resim Dosyaları", "*.png *.jpg *.jpeg *.gif *.bmp"),
                    ("PNG Dosyaları", "*.png"),
                    ("JPEG Dosyaları", "*.jpg *.jpeg"),
                    ("Tüm Dosyalar", "*.*")
                ]
            )
            if fp and Path(fp).exists():
                profil_resim_path[0] = fp
                show_toast(dlg, "Resim seçildi")
            elif fp:
                show_toast(dlg, "Seçilen dosya bulunamadı", 2000)

        ctk.CTkButton(dlg, text="📁 Profil Resmi Seç", command=on_profile_select).pack(padx=12, pady=6, fill="x")

        def on_add_ok():
            ad = e_ad.get().strip()
            num = e_num.get().strip()
            tags = [t.strip() for t in e_tags.get().split(",") if t.strip()]
            fav = var_fav.get()
            if not ad or not num:
                messagebox.showwarning(APP_NAME, "Ad ve numara zorunlu.")
                return
            self.kisiler.append(Kisi(ad=ad, numara=num, etiketler=tags, favori=fav, profil_foto=profil_resim_path[0]))
            self._refresh_list()
            show_toast(self, "Kişi eklendi")
            dlg.destroy()

        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(padx=12, pady=12, fill="x")
        ctk.CTkButton(row, text="Ekle", command=on_add_ok).pack(side="left", expand=True, fill="x", padx=6)
        ctk.CTkButton(row, text="İptal", command=dlg.destroy).pack(side="left", expand=True, fill="x", padx=6)

        dlg.grab_set()

    def _delete_person(self):
        if self.selected_index is None:
            show_toast(self, "Önce bir kişi seçin", 1400)
            return
        kisi = self.kisiler[self.selected_index]
        if messagebox.askyesno(APP_NAME, f"'{kisi.ad}' kişisini silmek istediğine emin misin?"):
            del self.kisiler[self.selected_index]
            self.selected_index = None
            self.detail_name.delete(0, "end")
            self.detail_number.delete(0, "end")
            self.detail_tags.delete(0, "end")
            self.fav_var.set(False)
            self._load_profile_image(None)
            self._refresh_list()
            show_toast(self, "Kişi silindi")

    def _save_people(self):
        if self.selected_index is not None:
            self._read_detail_into_model()
        save_rehber(self.kisiler)
        show_toast(self, "💾 Rehber kaydedildi", 1600)

    def _reload_people(self):
        self.kisiler = load_rehber()
        self._refresh_list()
        show_toast(self, "🔁 Rehber yenilendi", 1400)

    def _import_json(self):
        fp = filedialog.askopenfilename(title="Rehber JSON seç", filetypes=[("JSON", "*.json")])
        if not fp:
            return
        try:
            raw = json.loads(Path(fp).read_text(encoding="utf-8"))
            self.kisiler = [Kisi(**k) for k in raw]
            self._refresh_list()
            messagebox.showinfo(APP_NAME, "Rehber içe aktarıldı (geçici belleğe). Kaydet'e basarsanız rehber.json olarak yazılır.")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"JSON okunamadı: {e}")

    def _export_json(self):
        fp = filedialog.asksaveasfilename(title="Rehberi dışa aktar", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not fp:
            return
        try:
            Path(fp).write_text(json.dumps([asdict(k) for k in self.kisiler], ensure_ascii=False, indent=2), encoding="utf-8")
            messagebox.showinfo(APP_NAME, "Rehber dışa aktarıldı.")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Yazılamadı: {e}")

    def _on_close(self):
        self.settings["filtre_favori"] = self.chk_fav_var.get()
        self.settings["son_etiket"] = self.entry_tag.get()
        save_settings(self.settings)
        self.destroy()

    def _log_command_entered(self, event):
        content = self.logbox.get("1.0", "end-1c")
        lines = content.splitlines()
        if not lines:
            return "break"
        last_line = lines[-1].strip()
        cmd = last_line.lower()
        m = re.match(r"(.+?)['']?i?[ ]?ara$", cmd)
        if m:
            isim = m.group(1).strip()
            if not isim:
                self._log_ui("Komut algılanamadı: isim bulunamadı.")
            else:
                self._call_person_by_name(isim)
        else:
            self._log_ui(f"Tanınmayan komut: {last_line}")
        self.logbox.configure(state="normal")
        self.logbox.insert("end", "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")
        return "break"

    def _call_person_by_name(self, isim: str):
        matches = [(idx, k) for idx, k in enumerate(self.kisiler) if isim in k.ad.lower()]
        if not matches:
            self._log_ui(f"'{isim}' adlı kişi bulunamadı.")
            show_toast(self, f"'{isim}' bulunamadı.")
            return
        idx, kisi = matches[0]
        self.selected_index = idx
        self._select(idx)
        if not self.adb.connected:
            self._log_ui("ADB bağlı değil, önce bağlanın.")
            show_toast(self, "ADB bağlı değil!")
            return
        def job():
            ok = self.adb.call_immediate(kisi.numara)
            self._log_ui(f"Komutla arama {'başarılı' if ok else 'başarısız'}: {kisi.ad}")
            show_toast(self, f"📞 {kisi.ad} aranıyor..." if ok else "⚠️ Arama başarısız")
        threading.Thread(target=job, daemon=True).start()

def main():
    try:
        print("=== PyPIRT Başlatılıyor ===")
        print(f"Python sürümü: {sys.version}")
        print(f"Çalışma dizini: {os.getcwd()}")
        
        # Tkinter kontrolü
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.destroy()
            print("✓ Tkinter çalışıyor")
        except Exception as e:
            print(f"✗ Tkinter hatası: {e}")
            input("Devam etmek için Enter...")
            return
        
        # CustomTkinter kontrolü
        try:
            print(f"✓ CustomTkinter sürümü: {ctk.__version__}")
        except Exception as e:
            print(f"✗ CustomTkinter hatası: {e}")
            input("Devam etmek için Enter...")
            return
            
        # PIL kontrolü
        if PIL_AVAILABLE:
            print("✓ PIL/Pillow mevcut")
        else:
            print("⚠ PIL/Pillow yok (profil resimleri devre dışı)")
            
        print("=== Uygulama Oluşturuluyor ===")
        app = PyPIRTApp()
        print("✓ Uygulama penceresi oluşturuldu")
        
        print("=== Ana Döngü Başlatılıyor ===")
        app.mainloop()
        
    except ImportError as e:
        print(f"✗ İmport hatası: {e}")
        print("\nGerekli kütüphaneler yüklü değil. Lütfen şunları yükleyin:")
        print("pip install customtkinter")
        print("pip install Pillow")
        input("Çıkmak için Enter tuşuna basın...")
    except Exception as e:
        print(f"✗ GENEL HATA: {e}")
        print(f"Hata türü: {type(e).__name__}")
        import traceback
        print("=== Detaylı Hata Bilgisi ===")
        traceback.print_exc()
        print("=== Hata Sonu ===")
        input("Çıkmak için Enter tuşuna basın...")

if __name__ == "__main__":
    main()