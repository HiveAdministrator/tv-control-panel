import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
ADB_CANDIDATES = (
    os.path.join(RESOURCE_DIR, "platform-tools", "adb.exe"),
    os.path.join(BASE_DIR, "android-platform-tools", "platform-tools", "adb.exe"),
)
ADB = next((path for path in ADB_CANDIDATES if os.path.isfile(path)), None) or shutil.which("adb") or ADB_CANDIDATES[0]
SCRCPY = "scrcpy.exe"
COLORS = {
    "background": "#0B1020",
    "panel": "#111A2B",
    "card": "#172338",
    "card_border": "#2A3A54",
    "field": "#0E1727",
    "foreground": "#EDF3FC",
    "muted": "#9DAEC4",
    "subtitle": "#D2DBE8",
    "accent": "#66D9C5",
    "accent_hover": "#83E7D5",
    "button": "#24344C",
    "button_hover": "#304663",
    "danger": "#963F53",
    "danger_hover": "#B64B62",
}
PNG_ICON = os.path.join(RESOURCE_DIR, "ico.png")
ICO_ICON = os.path.join(RESOURCE_DIR, "tv-panel.ico")
APP_DATA_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming")),
    "TV-Control-Panel",
)
CONFIG = os.path.join(APP_DATA_DIR, "tv-panel.json")
LEGACY_CONFIG = os.path.join(BASE_DIR, "tv-panel.json")

DEFAULTS = [
    {"name": "Телевизор 1", "address": ""},
    {"name": "Телевизор 2", "address": ""},
]


def load_config():
    defaults = [dict(tv) for tv in DEFAULTS]
    config_path = CONFIG
    if not os.path.exists(config_path):
        config_path = LEGACY_CONFIG
    if not os.path.exists(config_path):
        return defaults

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return defaults

    if not isinstance(data, list):
        return defaults

    tvs = []
    for index, tv in enumerate(data):
        if not isinstance(tv, dict):
            return defaults
        name = tv.get("name", f"TV {index + 1}")
        address = tv.get("address", "")
        if not isinstance(name, str) or not isinstance(address, str):
            return defaults
        tvs.append({"name": name, "address": address})

    return tvs


def save_config(tvs):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(tvs, f, ensure_ascii=False, indent=2)


def parse_mdns_services(output):
    devices = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        service_name, service_type, endpoint = parts[:3]
        if service_type == "_adb-tls-connect._tcp":
            devices.append({
                "name": f"Android TV ({endpoint})",
                "address": f"{service_name}.{service_type}",
            })
        elif service_type == "_adb._tcp":
            devices.append({
                "name": f"Android TV ({endpoint})",
                "address": endpoint,
            })
    return devices


class TVCard(ttk.LabelFrame):
    def __init__(self, master, index, data, on_remove):
        super().__init__(
            master,
            text=f"  ТЕЛЕВИЗОР {index + 1}  ",
            padding=14,
            style="Card.TLabelframe",
        )
        self.index = index
        self.on_remove = on_remove
        self.name = tk.StringVar(value=data.get("name", f"TV {index + 1}"))
        self.address = tk.StringVar(value=data.get("address", ""))
        self.status = tk.StringVar(value="Не проверен")
        self.build()

    def build(self):
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text="Название", style="Muted.Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(self, textvariable=self.name, width=18).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(self, text="ADB-адрес", style="Muted.Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(self, textvariable=self.address, width=24).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(self, textvariable=self.status, style="Status.Card.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(7, 10)
        )
        ttk.Button(self, text="Удалить ТВ", command=self.on_remove, style="Danger.TButton").grid(
            row=2, column=2, sticky="e", pady=(3, 8)
        )

        buttons = [
            ("Подключить", self.connect), ("Просмотр", self.view),
            ("Полный экран", lambda: self.view(fullscreen=True)),
            ("Standby", lambda: self.keyevent("26")), ("Разбудить", lambda: self.keyevent("224")),
            ("Home", lambda: self.keyevent("3")), ("Назад", lambda: self.keyevent("4")),
            ("Вверх", lambda: self.keyevent("19")), ("Вниз", lambda: self.keyevent("20")),
            ("Влево", lambda: self.keyevent("21")), ("Вправо", lambda: self.keyevent("22")),
            ("OK", lambda: self.keyevent("23")), ("Громкость +", lambda: self.keyevent("24")),
            ("Громкость −", lambda: self.keyevent("25")),
        ]
        for n, (label, command) in enumerate(buttons):
            style = "Accent.TButton" if label in ("Подключить", "Просмотр", "Полный экран") else "TButton"
            ttk.Button(self, text=label, command=command, style=style).grid(
                row=3 + n // 3, column=n % 3, sticky="ew", padx=3, pady=3
            )
        for c in range(3):
            self.columnconfigure(c, weight=1)

    def device(self):
        return self.address.get().strip()

    def run_adb(self, args, success="Готово"):
        device = self.device()
        if not device:
            self.status.set("Не указан адрес")
            return False
        try:
            p = subprocess.run([ADB, "-s", device, *args], capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                self.status.set(success)
                return True
            output = (p.stderr or p.stdout or "Ошибка").strip()
            self.status.set((output.splitlines()[-1] if output else "Ошибка")[:70])
        except (OSError, subprocess.SubprocessError) as e:
            self.status.set(str(e)[:70])
        return False

    def connect(self):
        device = self.device()
        if not device:
            self.status.set("Не указан адрес")
            return False

        try:
            if "_adb-tls-connect._tcp" in device:
                p = subprocess.run([ADB, "-s", device, "get-state"], capture_output=True, text=True, timeout=15)
            else:
                p = subprocess.run([ADB, "connect", device], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as e:
            self.status.set(str(e)[:70])
            return False

        output = (p.stdout or p.stderr or "").strip()
        if "_adb-tls-connect._tcp" in device and p.returncode == 0 and output == "device":
            self.status.set("Подключено")
            return True
        if p.returncode == 0 and output.lower().startswith(("connected to ", "already connected to ")):
            self.status.set(output.splitlines()[-1][:70])
            return True

        self.status.set((output.splitlines()[-1] if output else "Не удалось подключиться")[:70])
        return False

    def keyevent(self, key):
        self.run_adb(["shell", "input", "keyevent", key], "Команда выполнена")

    def view(self, fullscreen=False):
        device = self.device()
        if not device:
            self.status.set("Не указан адрес")
            return
        args = [
            SCRCPY,
            "-s",
            device,
            "--window-title",
            self.name.get(),
            "--stay-awake",
            "--window-borderless",
        ]
        if fullscreen:
            args.append("--fullscreen")
        try:
            subprocess.Popen(args)
            self.status.set("Полноэкранный просмотр запущен" if fullscreen else "Окно просмотра запущено")
        except FileNotFoundError:
            messagebox.showerror("scrcpy не найден", "Добавьте scrcpy.exe в PATH или укажите его в переменной SCRCPY в tv-panel.py")
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            self.status.set(str(e)[:70])

    def values(self):
        return {"name": self.name.get().strip(), "address": self.address.get().strip()}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Управление Android TV")
        self.configure(background=COLORS["background"])
        self._wheel_delta = 0
        self.configure_style()
        try:
            self.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        if os.path.exists(ICO_ICON):
            try:
                self.iconbitmap(ICO_ICON)
            except tk.TclError:
                pass
        if os.path.exists(PNG_ICON):
            try:
                self.iconphoto(True, tk.PhotoImage(file=PNG_ICON))
            except tk.TclError:
                pass
        self.geometry("980x720")
        self.minsize(780, 600)
        self.tvs = load_config()
        self.cards = []
        self.build()

    def configure_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Header.TFrame", background=COLORS["background"])
        style.configure("Footer.TFrame", background=COLORS["background"])
        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["foreground"])
        style.configure(
            "Header.TLabel",
            background=COLORS["background"],
            foreground=COLORS["foreground"],
            font=("Segoe UI Semibold", 23),
        )
        style.configure(
            "Card.TLabelframe",
            background=COLORS["card"],
            bordercolor=COLORS["card_border"],
            lightcolor=COLORS["card_border"],
            darkcolor=COLORS["card_border"],
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=COLORS["card"],
            foreground=COLORS["accent"],
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Card.TLabel",
            background=COLORS["card"],
            foreground=COLORS["foreground"],
        )
        style.configure(
            "Muted.Card.TLabel",
            background=COLORS["card"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "Status.Card.TLabel",
            background=COLORS["card"],
            foreground=COLORS["accent"],
        )
        style.configure(
            "TEntry",
            fieldbackground=COLORS["field"],
            foreground=COLORS["foreground"],
            insertcolor=COLORS["foreground"],
            bordercolor=COLORS["card_border"],
            lightcolor=COLORS["card_border"],
            darkcolor=COLORS["card_border"],
            padding=(8, 7),
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", COLORS["accent"])],
            lightcolor=[("focus", COLORS["accent"])],
        )
        style.configure(
            "TButton",
            background=COLORS["button"],
            foreground=COLORS["foreground"],
            bordercolor=COLORS["card_border"],
            lightcolor=COLORS["button"],
            darkcolor=COLORS["button"],
            padding=(10, 8),
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", COLORS["button_hover"]), ("pressed", COLORS["button_hover"])],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground=COLORS["background"],
            bordercolor=COLORS["accent"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent"],
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["accent_hover"]), ("pressed", COLORS["accent_hover"])],
            foreground=[("active", COLORS["background"])],
        )
        style.configure(
            "Danger.TButton",
            background=COLORS["danger"],
            foreground=COLORS["foreground"],
            bordercolor=COLORS["danger"],
            lightcolor=COLORS["danger"],
            darkcolor=COLORS["danger"],
            padding=(8, 6),
        )
        style.map(
            "Danger.TButton",
            background=[("active", COLORS["danger_hover"]), ("pressed", COLORS["danger_hover"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=COLORS["button"],
            troughcolor=COLORS["panel"],
            bordercolor=COLORS["panel"],
            arrowcolor=COLORS["muted"],
            lightcolor=COLORS["button"],
            darkcolor=COLORS["button"],
        )

    def build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self, style="Header.TFrame", padding=(22, 18, 22, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Панель управления", style="Header.TLabel").pack(anchor="w")
        tk.Label(
            header,
            text="Android TV  ·  ADB и удалённый просмотр",
            background=COLORS["background"],
            foreground=COLORS["subtitle"],
            font=("Segoe UI", 10),
            borderwidth=0,
            highlightthickness=0,
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(self, padding=(18, 8, 18, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            body,
            highlightthickness=0,
            background=COLORS["background"],
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            body,
            orient="vertical",
            command=self.canvas.yview,
            style="Vertical.TScrollbar",
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.card_frame = ttk.Frame(self.canvas)
        self.card_window = self.canvas.create_window((0, 0), window=self.card_frame, anchor="nw")
        self.card_frame.bind("<Configure>", self.update_scroll_region)
        self.canvas.bind("<Configure>", self.resize_card_frame)
        self.bind("<MouseWheel>", self.on_mousewheel)
        self.bind("<Button-4>", self.on_mousewheel)
        self.bind("<Button-5>", self.on_mousewheel)

        bottom = ttk.Frame(self, style="Footer.TFrame", padding=(16, 8, 16, 14))
        bottom.grid(row=2, column=0, sticky="ew")
        ttk.Button(bottom, text="Добавить ТВ", command=self.add_tv).pack(side="left", padx=3)
        ttk.Button(bottom, text="Найти по ADB", command=self.discover_devices).pack(side="left", padx=3)
        ttk.Button(bottom, text="Подключить все", command=self.connect_all).pack(side="left", padx=3)
        ttk.Button(bottom, text="Просмотр всех", command=self.view_all).pack(side="left", padx=3)
        ttk.Button(bottom, text="Все в полный экран", command=lambda: self.view_all(fullscreen=True)).pack(side="left", padx=3)
        ttk.Button(bottom, text="Сохранить", command=self.save).pack(side="left", padx=3)
        ttk.Button(bottom, text="О приложении", command=self.about).pack(side="left", padx=3)
        ttk.Button(bottom, text="Выход", command=self.destroy).pack(side="right", padx=3)
        self.render_cards()

    def on_mousewheel(self, event):
        widget = event.widget
        while widget is not None:
            if widget is self.canvas or widget is self.card_frame:
                break
            widget = getattr(widget, "master", None)
        else:
            return None

        if event.num == 4:
            units = 1
        elif event.num == 5:
            units = -1
        else:
            self._wheel_delta += event.delta
            units = int(self._wheel_delta / 120)
            self._wheel_delta -= units * 120

        if units:
            self.canvas.yview_scroll(-units, "units")
        return "break"

    def update_scroll_region(self, event):
        if event.widget is not self.card_frame:
            return
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def resize_card_frame(self, event):
        self.canvas.itemconfigure(self.card_window, width=event.width)

    def render_cards(self):
        for card in self.cards:
            card.destroy()
        self.cards = []
        for index, data in enumerate(self.tvs):
            card = TVCard(self.card_frame, index, data, lambda i=index: self.remove_tv(i))
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=5, pady=5)
            self.cards.append(card)
        for column in range(2):
            self.card_frame.columnconfigure(column, weight=1)

    def add_tv(self, data=None):
        self.tvs = [card.values() for card in self.cards]
        tv = data if data is not None else {"name": f"TV {len(self.tvs) + 1}", "address": ""}
        self.tvs.append(tv)
        self.render_cards()
        self.canvas.yview_moveto(1)

    def remove_tv(self, index):
        self.tvs = [card.values() for card in self.cards]
        del self.tvs[index]
        self.render_cards()

    def discover_devices(self):
        self.tvs = [card.values() for card in self.cards]
        try:
            result = subprocess.run(
                [ADB, "mdns", "services"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as e:
            messagebox.showerror("Ошибка ADB", str(e), parent=self)
            return

        if result.returncode != 0:
            error = (result.stderr or result.stdout or "ADB не смог выполнить обнаружение").strip()
            messagebox.showerror("Ошибка ADB", error, parent=self)
            return

        known_addresses = {card.device() for card in self.cards}
        discovered = [
            device for device in parse_mdns_services(result.stdout)
            if device["address"] not in known_addresses
        ]
        for device in discovered:
            self.tvs.append(device)
            known_addresses.add(device["address"])

        self.render_cards()
        if discovered:
            self.canvas.yview_moveto(1)
            self.cards[-1].status.set(f"Найдено устройств: {len(discovered)}")
        else:
            messagebox.showinfo("Поиск ADB", "Новых ТВ не найдено.", parent=self)

    def about(self):
        messagebox.showinfo(
            "О приложении",
            "Панель управления Android TV\n\n"
            "Управление Android TV через ADB и scrcpy.\n\n"
            "Создал: С.Д.М (@Dab4ick)",
            parent=self,
        )

    def connect_all(self):
        for card in self.cards:
            card.connect()
        self.save(update_status=False)

    def view_all(self, fullscreen=False):
        for card in self.cards:
            card.view(fullscreen=fullscreen)

    def save(self, update_status=True):
        self.tvs = [card.values() for card in self.cards]
        try:
            save_config(self.tvs)
        except OSError as e:
            messagebox.showerror("Не удалось сохранить", str(e), parent=self)
            return False
        if update_status:
            for card in self.cards:
                card.status.set("Настройки сохранены")
        return True


if __name__ == "__main__":
    App().mainloop()
