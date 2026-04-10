import customtkinter as ctk
import cv2
from PIL import Image, ImageTk
import threading
import time
import datetime
import platform
import os
import sys
import subprocess
from collections import deque

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG_DEEP = "#0A0A0C"
BG_PANEL = "#111116"
BG_CARD = "#16161C"
BG_HOVER = "#1E1E26"
ACCENT = "#E8F4FD"
ACCENT_DIM = "#4A90C4"
TEAL = "#00D4AA"
RED = "#FF3B3B"
AMBER = "#F5A623"
BORDER = "#2A2A35"
TEXT_PRI = "#F0F0F5"
TEXT_SEC = "#7A7A9A"
TEXT_MUTE = "#3A3A50"

FONT_DISPLAY = ("SF Pro Display", 28, "bold")
FONT_TITLE = ("SF Pro Display", 13, "bold")
FONT_BODY = ("SF Pro Text", 12)
FONT_SMALL = ("SF Pro Text", 10)
FONT_MONO = ("SF Mono", 11)


CAMERA_INDEXES_ENV = os.getenv("CAMERA_INDEXES")


def detect_available_cameras(max_scan: int = 8):
    detected = []
    for idx in range(max_scan):
        system_name = platform.system().lower()

        if system_name == "windows":
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(idx, cv2.CAP_MSMF)
        elif system_name == "linux":
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(idx)

        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                detected.append(idx)
        cap.release()

    return detected


def resolve_camera_indexes(default_count: int = 2):
    if CAMERA_INDEXES_ENV:
        configured = [
            int(idx.strip())
            for idx in CAMERA_INDEXES_ENV.split(",")
            if idx.strip()
        ]
        if configured:
            print(f"Using CAMERA_INDEXES from env: {configured}")
            return configured

    detected = detect_available_cameras(max_scan=10)
    if detected:
        chosen = detected[:default_count]
        print(f"Auto-detected camera indexes: {detected}; using {chosen}")
        return chosen

    fallback = [0]
    print(f"No readable cameras auto-detected; falling back to {fallback}")
    return fallback


class CameraFeed:
    def __init__(self, index: int):
        self.index = index
        self.cap = None
        self.frame = None
        self.running = False
        self.fps = 0
        self.status = "offline"
        self._fps_times = deque(maxlen=30)

    def _open_capture(self):
        system_name = platform.system().lower()
        if system_name == "windows":
            cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
            if cap.isOpened():
                return cap
            cap.release()
        elif system_name == "linux":
            cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
            if cap.isOpened():
                return cap
            cap.release()

        return cv2.VideoCapture(self.index)

    def start(self):
        self.cap = self._open_capture()
        if self.cap.isOpened():
            self.running = True
            self.status = "live"
            threading.Thread(target=self._loop, daemon=True).start()
        else:
            self.status = "offline"

    def _loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
                now = time.time()
                self._fps_times.append(now)
                if len(self._fps_times) > 1:
                    self.fps = len(self._fps_times) / (
                        self._fps_times[-1] - self._fps_times[0] + 1e-9)
            else:
                self.status = "offline"
                break

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()


class PillBadge(ctk.CTkLabel):
    STATUS_COLORS = {
        "live": (TEAL, "#003328"),
        "offline": (RED, "#2A0000"),
        "idle": (AMBER, "#2A1800"),
    }

    def __init__(self, master, status="live", **kw):
        fg, bg = self.STATUS_COLORS.get(status, (TEXT_SEC, BG_CARD))
        super().__init__(
            master,
            text=f"  ● {status.upper()}  ",
            font=("SF Pro Text", 9, "bold"),
            text_color=fg,
            fg_color=bg,
            corner_radius=8,
            **kw,
        )
        self._status = status

    def set_status(self, status):
        if status == self._status:
            return
        self._status = status
        fg, bg = self.STATUS_COLORS.get(status, (TEXT_SEC, BG_CARD))
        self.configure(text=f"  ● {status.upper()}  ", text_color=fg, fg_color=bg)


class CameraCard(ctk.CTkFrame):
    W, H = 480, 270

    def __init__(self, master, feed: CameraFeed, label="CAM", on_open=None, **kw):
        super().__init__(
            master,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
            **kw,
        )
        self.feed = feed
        self.label = label
        self.on_open = on_open
        self._build()
        self._update()

    def _build(self):
        self.canvas = ctk.CTkCanvas(
            self, width=self.W, height=self.H, bg=BG_DEEP, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True, padx=1, pady=1)

        hud = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=36)
        hud.pack(fill="x", side="bottom")
        hud.pack_propagate(False)

        self.lbl_name = ctk.CTkLabel(
            hud, text=self.label, font=FONT_TITLE, text_color=TEXT_PRI
        )
        self.lbl_name.pack(side="left", padx=12)

        self.badge = PillBadge(hud, status=self.feed.status)
        self.badge.pack(side="left", padx=4)

        self.lbl_fps = ctk.CTkLabel(hud, text="-- fps", font=FONT_MONO, text_color=TEXT_SEC)
        self.lbl_fps.pack(side="right", padx=12)

        self.lbl_time = ctk.CTkLabel(hud, text="", font=FONT_MONO, text_color=TEXT_MUTE)
        self.lbl_time.pack(side="right", padx=4)

        self.canvas.bind("<Enter>", lambda _e: self.configure(border_color=ACCENT_DIM))
        self.canvas.bind("<Leave>", lambda _e: self.configure(border_color=BORDER))
        self.canvas.bind("<Button-1>", self._open_fullscreen)

    def _open_fullscreen(self, _event=None):
        if self.on_open is not None:
            self.on_open(self.feed, self.label)

    def _draw_placeholder(self):
        w = self.canvas.winfo_width() or self.W
        h = self.canvas.winfo_height() or self.H
        self.canvas.delete("all")
        for x in range(0, w, 40):
            self.canvas.create_line(x, 0, x, h, fill="#1A1A22", width=1)
        for y in range(0, h, 40):
            self.canvas.create_line(0, y, w, y, fill="#1A1A22", width=1)
        cx, cy = w // 2, h // 2
        self.canvas.create_oval(
            cx - 30, cy - 30, cx + 30, cy + 30, outline=TEXT_MUTE, width=1
        )
        self.canvas.create_line(cx - 18, cy - 18, cx + 18, cy + 18, fill=TEXT_MUTE, width=2)
        self.canvas.create_line(cx + 18, cy - 18, cx - 18, cy + 18, fill=TEXT_MUTE, width=2)
        self.canvas.create_text(
            cx,
            cy + 52,
            text="NO SIGNAL",
            fill=TEXT_MUTE,
            font=("SF Pro Text", 11, "bold"),
        )

    def _draw_frame(self, frame):
        w = self.canvas.winfo_width() or self.W
        h = self.canvas.winfo_height() or self.H
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((w, h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=photo)
        self.canvas._photo = photo

        blen, gap, thick = 18, 6, 2
        for (ox, oy, sx, sy) in [
            (gap, gap, 1, 1),
            (w - gap, gap, -1, 1),
            (gap, h - gap, 1, -1),
            (w - gap, h - gap, -1, -1),
        ]:
            self.canvas.create_line(ox, oy, ox + sx * blen, oy, fill=TEAL, width=thick)
            self.canvas.create_line(ox, oy, ox, oy + sy * blen, fill=TEAL, width=thick)

        self.canvas.create_text(
            w - 10,
            10,
            anchor="ne",
            text=f"{self.feed.fps:.0f} fps",
            fill=TEAL,
            font=("SF Mono", 9),
        )

    def _update(self):
        if self.feed.frame is not None and self.feed.status == "live":
            self._draw_frame(self.feed.frame)
            self.lbl_fps.configure(text=f"{self.feed.fps:.0f} fps")
        else:
            self._draw_placeholder()
            self.lbl_fps.configure(text="-- fps")

        self.badge.set_status(self.feed.status)
        self.lbl_time.configure(text=datetime.datetime.now().strftime("%H:%M:%S"))
        self.after(33, self._update)


class FullscreenViewer(ctk.CTkToplevel):
    def __init__(self, master, feed: CameraFeed, label: str):
        super().__init__(master)
        self.feed = feed
        self.title(f"{label} - Fullscreen")
        self.configure(fg_color=BG_DEEP)
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda _e: self.destroy())

        self.canvas = ctk.CTkCanvas(self, bg=BG_DEEP, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        top = ctk.CTkFrame(self, fg_color=BG_PANEL, height=42, corner_radius=0)
        top.place(relx=0, rely=0, relwidth=1)
        top.pack_propagate(False)

        ctk.CTkLabel(top, text=label, font=FONT_TITLE, text_color=TEXT_PRI).pack(
            side="left", padx=12
        )
        ctk.CTkLabel(
            top,
            text="Press ESC to exit fullscreen",
            font=FONT_SMALL,
            text_color=TEXT_SEC,
        ).pack(side="right", padx=12)

        self._tick()

    def _tick(self):
        if not self.winfo_exists():
            return

        frame = self.feed.frame
        self.canvas.delete("all")
        if frame is not None and self.feed.status == "live":
            w = max(1, self.canvas.winfo_width())
            h = max(1, self.canvas.winfo_height())
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb).resize((w, h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, anchor="nw", image=photo)
            self.canvas._photo = photo

        self.after(33, self._tick)


class Sidebar(ctk.CTkFrame):
    NAV = [
        ("⊞", "Dashboard"),
        ("◇", "Cameras"),
        ("◉", "Analytics"),
        ("⌖", "Alerts"),
        ("⚙", "Settings"),
    ]

    def __init__(self, master, on_select, **kw):
        super().__init__(master, width=72, fg_color=BG_PANEL, corner_radius=0, **kw)
        self.pack_propagate(False)
        self.on_select = on_select
        self._active = "Dashboard"
        self._btns = {}
        self._build()

    def _build(self):
        logo = ctk.CTkLabel(self, text="◇", font=("SF Pro Display", 24), text_color=TEAL)
        logo.pack(pady=(24, 32))

        for icon, name in self.NAV:
            btn = ctk.CTkButton(
                self,
                text=icon,
                width=48,
                height=48,
                font=("SF Pro Display", 20),
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=TEXT_SEC,
                corner_radius=10,
                command=lambda n=name: self._select(n),
            )
            btn.pack(pady=4)
            self._btns[name] = btn

        self._highlight(self._active)

        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(
            fill="x", padx=12, side="bottom", pady=8
        )
        ctk.CTkLabel(self, text="◎", font=("SF Pro Display", 20), text_color=TEXT_SEC).pack(
            side="bottom", pady=8
        )

    def _highlight(self, name):
        for n, b in self._btns.items():
            if n == name:
                b.configure(text_color=TEAL, fg_color=BG_HOVER)
            else:
                b.configure(text_color=TEXT_SEC, fg_color="transparent")

    def _select(self, name):
        self._active = name
        self._highlight(name)
        self.on_select(name)


class TopBar(ctk.CTkFrame):
    def __init__(self, master, on_back, **kw):
        super().__init__(master, height=56, fg_color=BG_PANEL, corner_radius=0, **kw)
        self.pack_propagate(False)
        self._on_back = on_back
        self._build()

    def _build(self):
        self.back_btn = ctk.CTkButton(
            self,
            text="Apps",
            width=68,
            height=30,
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_SEC,
            hover_color=BG_HOVER,
            corner_radius=6,
            command=self._on_back,
        )
        self.back_btn.pack(side="left", padx=(14, 8))

        self.title_lbl = ctk.CTkLabel(
            self, text="DASHBOARD", font=("SF Pro Display", 13, "bold"), text_color=TEXT_PRI
        )
        self.title_lbl.pack(side="left", padx=8)

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=16)

        self.clock = ctk.CTkLabel(right, text="", font=FONT_MONO, text_color=TEXT_SEC)
        self.clock.pack(side="right", padx=12)

        self.date_lbl = ctk.CTkLabel(right, text="", font=FONT_MONO, text_color=TEXT_MUTE)
        self.date_lbl.pack(side="right")

        ctk.CTkFrame(self, fg_color=BORDER, width=1).pack(side="bottom", fill="x")
        self._tick()

    def _tick(self):
        now = datetime.datetime.now()
        self.clock.configure(text=now.strftime("%H:%M:%S"))
        self.date_lbl.configure(text=now.strftime("%a %d %b %Y  "))
        self.after(1000, self._tick)

    def set_title(self, title):
        self.title_lbl.configure(text=title.upper())


class StatCard(ctk.CTkFrame):
    def __init__(self, master, icon, label, value, accent=TEAL, **kw):
        super().__init__(
            master, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER, **kw
        )
        ctk.CTkLabel(self, text=icon, font=("SF Pro Display", 22), text_color=accent).pack(
            anchor="w", padx=16, pady=(14, 2)
        )
        ctk.CTkLabel(self, text=label, font=FONT_SMALL, text_color=TEXT_SEC).pack(
            anchor="w", padx=16
        )
        self.val = ctk.CTkLabel(
            self, text=value, font=("SF Pro Display", 26, "bold"), text_color=TEXT_PRI
        )
        self.val.pack(anchor="w", padx=16, pady=(0, 14))

    def update(self, value):
        self.val.configure(text=value)


class LayoutSwitcher(ctk.CTkFrame):
    LAYOUTS = ["1x1", "1x2", "2x2", "2x3"]

    def __init__(self, master, on_change, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._cb = on_change
        self._cur = "2x2"
        self._btns = {}
        ctk.CTkLabel(self, text="LAYOUT", font=FONT_SMALL, text_color=TEXT_MUTE).pack(
            side="left", padx=(0, 8)
        )
        for lay in self.LAYOUTS:
            b = ctk.CTkButton(
                self,
                text=lay,
                width=48,
                height=28,
                font=FONT_SMALL,
                fg_color=BG_HOVER if lay == self._cur else "transparent",
                text_color=TEAL if lay == self._cur else TEXT_SEC,
                hover_color=BG_HOVER,
                border_width=1,
                border_color=BORDER,
                corner_radius=6,
                command=lambda l=lay: self._pick(l),
            )
            b.pack(side="left", padx=2)
            self._btns[lay] = b

    def _pick(self, lay):
        self._cur = lay
        for l, b in self._btns.items():
            b.configure(fg_color=BG_HOVER if l == lay else "transparent", text_color=TEAL if l == lay else TEXT_SEC)
        self._cb(lay)


class DashboardPage(ctk.CTkFrame):
    def __init__(self, master, feeds, on_open_fullscreen, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.feeds = feeds
        self._cards = []
        self._layout = "2x2"
        self._on_open_fullscreen = on_open_fullscreen
        self._last_width = 0
        self._build()
        self.bind("<Configure>", self._handle_resize)

    def _build(self):
        self.stats_row = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_row.pack(fill="x", pady=(0, 16))

        live_count = sum(1 for f in self.feeds if f.status == "live")
        self._stat_live = StatCard(self.stats_row, "◉", "CAMERAS LIVE", str(live_count), accent=TEAL)
        self._stat_live.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self._stat_fps = StatCard(self.stats_row, "◇", "AVG FPS", "--", accent=ACCENT_DIM)
        self._stat_fps.pack(side="left", fill="both", expand=True, padx=8)

        self._stat_up = StatCard(self.stats_row, "⌖", "UPTIME", "00:00:00", accent=AMBER)
        self._stat_up.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._start = time.time()

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(toolbar, text="CAMERA FEEDS", font=FONT_TITLE, text_color=TEXT_PRI).pack(side="left")
        self._switcher = LayoutSwitcher(toolbar, self._change_layout)
        self._switcher.pack(side="right")

        self._grid = ctk.CTkFrame(self, fg_color="transparent")
        self._grid.pack(fill="both", expand=True)

        self._render_layout()
        self._tick()

    def _handle_resize(self, event):
        width = event.width
        if abs(width - self._last_width) < 40:
            return
        self._last_width = width

        if width < 620 and self._layout != "1x1":
            self._layout = "1x1"
            self._rebuild_grid()
        elif width >= 620 and len(self._cards) == 1:
            self._layout = "2x2"
            self._rebuild_grid()

    def _change_layout(self, layout):
        self._layout = layout
        self._rebuild_grid()

    def _rebuild_grid(self):
        for w in self._grid.winfo_children():
            w.destroy()
        self._cards.clear()
        self._render_layout()

    def _render_layout(self):
        mapping = {"1x1": (1, 1), "1x2": (1, 2), "2x2": (2, 2), "2x3": (2, 3)}
        rows, cols = mapping.get(self._layout, (2, 2))

        for i in range(cols):
            self._grid.columnconfigure(i, weight=1, uniform="col")
        for j in range(rows):
            self._grid.rowconfigure(j, weight=1, uniform="row")

        idx = 0
        for r in range(rows):
            for c in range(cols):
                feed = self.feeds[idx % len(self.feeds)]
                card = CameraCard(
                    self._grid,
                    feed,
                    label=f"CAM {feed.index:02d}",
                    on_open=self._on_open_fullscreen,
                )
                card.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
                self._cards.append(card)
                idx += 1

    def _tick(self):
        live = sum(1 for f in self.feeds if f.status == "live")
        fps_vals = [f.fps for f in self.feeds if f.status == "live"]
        avg_fps = sum(fps_vals) / len(fps_vals) if fps_vals else 0
        up = int(time.time() - self._start)
        h, m, s = up // 3600, (up % 3600) // 60, up % 60

        self._stat_live.update(str(live))
        self._stat_fps.update(f"{avg_fps:.1f}")
        self._stat_up.update(f"{h:02d}:{m:02d}:{s:02d}")
        self.after(1000, self._tick)


class CamerasPage(ctk.CTkFrame):
    def __init__(self, master, feeds, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        ctk.CTkLabel(self, text="Camera Management", font=FONT_DISPLAY, text_color=TEXT_PRI).pack(
            anchor="w", pady=(0, 20)
        )

        self._feeds = feeds
        self._badges = {}
        self._device_prefix = "camera" if platform.system().lower() == "windows" else "/dev/video"

        for feed in feeds:
            row = ctk.CTkFrame(
                self, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER
            )
            row.pack(fill="x", pady=4)

            ctk.CTkLabel(
                row,
                text=f"CAM {feed.index:02d}",
                font=FONT_TITLE,
                text_color=TEXT_PRI,
                width=80,
            ).pack(side="left", padx=16, pady=14)

            badge = PillBadge(row, status=feed.status)
            badge.pack(side="left", padx=8)
            self._badges[feed.index] = (feed, badge)

            ctk.CTkLabel(
                row,
                text=f"Index  {self._device_prefix}{feed.index}",
                font=FONT_MONO,
                text_color=TEXT_SEC,
            ).pack(side="left", padx=24)

            ctk.CTkButton(
                row,
                text="Restart",
                width=80,
                height=30,
                font=FONT_SMALL,
                fg_color="transparent",
                border_width=1,
                border_color=BORDER,
                text_color=TEXT_SEC,
                hover_color=BG_HOVER,
                corner_radius=6,
                command=lambda f=feed: self._restart(f),
            ).pack(side="right", padx=16)

        self._refresh()

    def _restart(self, feed):
        feed.stop()
        feed.start()

    def _refresh(self):
        for feed, badge in self._badges.values():
            badge.set_status(feed.status)
        self.after(1000, self._refresh)


class PlaceholderPage(ctk.CTkFrame):
    def __init__(self, master, title, icon, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        ctk.CTkFrame(self, fg_color="transparent").pack(expand=True, fill="both")
        ctk.CTkLabel(self, text=icon, font=("SF Pro Display", 56), text_color=TEXT_MUTE).pack()
        ctk.CTkLabel(self, text=title, font=FONT_DISPLAY, text_color=TEXT_SEC).pack(pady=8)
        ctk.CTkLabel(
            self,
            text="This module is not yet configured.",
            font=FONT_BODY,
            text_color=TEXT_MUTE,
        ).pack()
        ctk.CTkFrame(self, fg_color="transparent").pack(expand=True, fill="both")


class HomePage(ctk.CTkFrame):
    def __init__(self, master, on_open_cam_monitor, **kw):
        super().__init__(master, fg_color=BG_DEEP, **kw)
        self._on_open_cam_monitor = on_open_cam_monitor
        self._clock_label = None
        self._date_label = None
        self._temp_label = None
        self._temp_text = os.getenv("KIOSK_TEMP", "--°C")
        self._build()
        self._tick()

    def _build(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.grid_columnconfigure(0, weight=1, uniform="home")
        body.grid_columnconfigure(1, weight=1, uniform="home")
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(
            body,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        left_inner = ctk.CTkFrame(left, fg_color="transparent")
        left_inner.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            left_inner,
            text="Status",
            font=FONT_TITLE,
            text_color=TEXT_SEC,
        ).pack(anchor="w")

        self._clock_label = ctk.CTkLabel(
            left_inner,
            text="--:--:--",
            font=("SF Pro Display", 54, "bold"),
            text_color=TEXT_PRI,
        )
        self._clock_label.pack(anchor="w", pady=(18, 6))

        self._date_label = ctk.CTkLabel(
            left_inner,
            text="",
            font=FONT_MONO,
            text_color=TEXT_SEC,
        )
        self._date_label.pack(anchor="w", pady=(0, 28))

        self._temp_label = ctk.CTkLabel(
            left_inner,
            text=f"Temperature  {self._temp_text}",
            font=("SF Pro Display", 20, "bold"),
            text_color=TEAL,
        )
        self._temp_label.pack(anchor="w")

        right = ctk.CTkFrame(
            body,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        right_inner = ctk.CTkFrame(right, fg_color="transparent")
        right_inner.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(right_inner, text="Apps", font=FONT_DISPLAY, text_color=TEXT_PRI).pack(
            anchor="w", pady=(0, 8)
        )
        ctk.CTkLabel(
            right_inner,
            text="Select a module",
            font=FONT_BODY,
            text_color=TEXT_SEC,
        ).pack(anchor="w", pady=(0, 20))

        card = ctk.CTkFrame(
            right_inner,
            fg_color=BG_PANEL,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        card.pack(fill="x")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(row, text="◉", font=("SF Pro Display", 22), text_color=TEAL).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkLabel(
            row,
            text="Cam Monitoring",
            font=FONT_TITLE,
            text_color=TEXT_PRI,
        ).pack(side="left")

        ctk.CTkButton(
            row,
            text="Open",
            width=90,
            height=32,
            font=FONT_SMALL,
            fg_color=BG_HOVER,
            hover_color="#262632",
            text_color=TEAL,
            corner_radius=6,
            command=self._on_open_cam_monitor,
        ).pack(side="right")

    def _tick(self):
        if self._clock_label is None or not self.winfo_exists():
            return
        now = datetime.datetime.now()
        self._clock_label.configure(text=now.strftime("%H:%M:%S"))
        self._date_label.configure(text=now.strftime("%a %d %b %Y"))
        self.after(1000, self._tick)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CAM MONITOR")
        self.geometry("1100x760")
        self.minsize(360, 240)
        self.configure(fg_color=BG_DEEP)

        self._feeds = []
        self._pages = {}
        self._active = None
        self._fullscreen_window = None
        self._streamer_process = None
        self._camera_indexes = resolve_camera_indexes(default_count=2)

        self._start_streamer_process()

        self._home = HomePage(self, on_open_cam_monitor=self._open_cam_monitor)
        self._home.pack(fill="both", expand=True)

        self._monitor_root = None
        self._topbar = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_streamer_process(self):
        if self._streamer_process is not None and self._streamer_process.poll() is None:
            return

        streamer_path = os.path.join(os.path.dirname(__file__), "streamer.py")
        if not os.path.exists(streamer_path):
            print(f"streamer.py not found: {streamer_path}")
            return

        try:
            self._streamer_process = subprocess.Popen(
                [sys.executable, streamer_path],
                cwd=os.path.dirname(__file__),
            )
            print("Started streamer.py process")
        except Exception as exc:
            print(f"Failed to start streamer.py: {exc}")

    def _stop_streamer_process(self):
        if self._streamer_process is None:
            return
        if self._streamer_process.poll() is not None:
            return

        try:
            self._streamer_process.terminate()
            self._streamer_process.wait(timeout=5)
            print("Stopped streamer.py process")
        except Exception:
            self._streamer_process.kill()

    def _start_feeds(self):
        if self._feeds:
            return

        for idx in self._camera_indexes:
            feed = CameraFeed(idx)
            feed.start()
            self._feeds.append(feed)

    def _build_monitor_ui(self):
        if self._monitor_root is not None:
            return

        self._start_feeds()

        self._monitor_root = ctk.CTkFrame(self, fg_color="transparent")

        self._sidebar = Sidebar(self._monitor_root, on_select=self._switch_page)
        self._sidebar.pack(side="left", fill="y")

        ctk.CTkFrame(self._monitor_root, width=1, fg_color=BORDER).pack(side="left", fill="y")

        main = ctk.CTkFrame(self._monitor_root, fg_color="transparent")
        main.pack(side="left", fill="both", expand=True)

        self._topbar = TopBar(main, on_back=self._go_home)
        self._topbar.pack(fill="x")

        self._content = ctk.CTkScrollableFrame(main, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=12, pady=10)

        self._pages = {
            "Dashboard": DashboardPage(self._content, self._feeds, self._open_fullscreen),
            "Cameras": CamerasPage(self._content, self._feeds),
            "Analytics": PlaceholderPage(self._content, "Analytics", "◇"),
            "Alerts": PlaceholderPage(self._content, "Alerts", "⌖"),
            "Settings": PlaceholderPage(self._content, "Settings", "⚙"),
        }

    def _open_cam_monitor(self):
        self._start_streamer_process()
        self._build_monitor_ui()
        self._home.pack_forget()
        self._monitor_root.pack(fill="both", expand=True)
        self._switch_page("Dashboard")

    def _go_home(self):
        if self._monitor_root is not None:
            self._monitor_root.pack_forget()
        self._home.pack(fill="both", expand=True)

    def _switch_page(self, name):
        if self._active:
            self._pages[self._active].pack_forget()
        self._pages[name].pack(fill="both", expand=True)
        self._active = name
        self._topbar.set_title(name)

    def _open_fullscreen(self, feed: CameraFeed, label: str):
        if self._fullscreen_window is not None and self._fullscreen_window.winfo_exists():
            self._fullscreen_window.destroy()
        self._fullscreen_window = FullscreenViewer(self, feed, label)

    def _on_close(self):
        if self._fullscreen_window is not None and self._fullscreen_window.winfo_exists():
            self._fullscreen_window.destroy()
        for feed in self._feeds:
            feed.stop()
        self._stop_streamer_process()
        self.destroy()


if __name__ == "__main__":
    is_linux = platform.system().lower() == "linux"
    has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))

    if is_linux and not has_display:
        streamer_path = os.path.join(os.path.dirname(__file__), "streamer.py")
        print("No GUI display detected (DISPLAY/WAYLAND_DISPLAY is not set).")
        print("Starting headless streamer mode instead of CustomTkinter UI.")

        if os.path.exists(streamer_path):
            try:
                subprocess.call([sys.executable, streamer_path], cwd=os.path.dirname(__file__))
            except Exception as exc:
                print(f"Failed to start headless streamer: {exc}")
        else:
            print(f"streamer.py not found: {streamer_path}")
    else:
        App().mainloop()
