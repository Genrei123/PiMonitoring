==============================================================
  WebRTC Multi-Camera MVP — Agent Implementation Instructions
==============================================================

PROJECT STRUCTURE
-----------------
Two folders already exist:
  - cammonitoringapp/   (Flutter application, already initialized)
  - cammonitoringpy/    (Python application, already created)

Your job is to populate both folders with the files listed below.
Do NOT reinitialize either project. Just create/modify the files.


==============================================================
  PART 1 — PYTHON (cammonitoringpy/)
==============================================================

--------------------------------------------------------------
FILE: cammonitoringpy/requirements.txt
--------------------------------------------------------------
aiortc==1.6.0
aiohttp==3.9.3
opencv-python==4.9.0.80
firebase-admin==6.4.0


--------------------------------------------------------------
FILE: cammonitoringpy/streamer.py
--------------------------------------------------------------
import asyncio
import cv2
import firebase_admin
from firebase_admin import credentials, db
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

# ── Firebase setup ──────────────────────────────────────────────
# Replace with your Firebase service account key path and DB URL
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://YOUR_PROJECT_ID.firebaseio.com"
})

# List your physical camera indexes here (0, 1, 2 ...)
CAMERA_INDEXES = [0, 1]

peer_connections = {}


# ── Custom OpenCV camera track ──────────────────────────────────
class CameraTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, cam_index: int):
        super().__init__()
        self.cap = cv2.VideoCapture(cam_index)
        self.cam_index = cam_index

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            raise Exception(f"Camera {self.cam_index} read failed")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


# ── Handle one Flutter client offer ────────────────────────────
async def handle_offer(cam_index: int, offer_data: dict):
    pc = RTCPeerConnection()
    peer_connections[cam_index] = pc

    pc.addTrack(CameraTrack(cam_index))

    offer = RTCSessionDescription(sdp=offer_data["sdp"], type=offer_data["type"])
    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    db.reference(f"sessions/cam{cam_index}/answer").set({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    })

    print(f"[cam{cam_index}] Answer sent to Firebase")

    @pc.on("connectionstatechange")
    async def on_state():
        print(f"[cam{cam_index}] Connection state: {pc.connectionState}")


# ── Watch Firebase for incoming offers ─────────────────────────
def watch_offers():
    for cam_index in CAMERA_INDEXES:
        ref = db.reference(f"sessions/cam{cam_index}/offer")

        def make_listener(idx):
            def listener(event):
                if event.data:
                    print(f"[cam{idx}] Offer received from Flutter")
                    asyncio.run(handle_offer(idx, event.data))
            return listener

        ref.listen(make_listener(cam_index))


if __name__ == "__main__":
    print("Python WebRTC streamer started. Waiting for Flutter offers...")
    watch_offers()
    asyncio.get_event_loop().run_forever()


--------------------------------------------------------------
FILE: cammonitoringpy/serviceAccountKey.json
--------------------------------------------------------------
!! DO NOT CREATE THIS FILE AUTOMATICALLY !!
The user must download this manually from:
  Firebase Console → Project Settings → Service Accounts → Generate new private key
Place the downloaded JSON file at: cammonitoringpy/serviceAccountKey.json


==============================================================
  PART 2 — FLUTTER (cammonitoringapp/)
==============================================================

--------------------------------------------------------------
FILE: cammonitoringapp/pubspec.yaml
--------------------------------------------------------------
Merge these dependencies into the existing pubspec.yaml.
Do NOT replace the whole file — only add the packages below
under the existing `dependencies:` section:

  flutter_webrtc: ^0.9.47
  firebase_core: ^2.27.0
  firebase_database: ^10.4.9

After editing, run: flutter pub get


--------------------------------------------------------------
FILE: cammonitoringapp/lib/camera_viewer.dart
--------------------------------------------------------------
import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:firebase_database/firebase_database.dart';

class CameraViewer extends StatefulWidget {
  final int camIndex;
  const CameraViewer({super.key, required this.camIndex});

  @override
  State<CameraViewer> createState() => _CameraViewerState();
}

class _CameraViewerState extends State<CameraViewer> {
  final RTCVideoRenderer _renderer = RTCVideoRenderer();
  RTCPeerConnection? _pc;
  bool _connected = false;

  @override
  void initState() {
    super.initState();
    _renderer.initialize().then((_) => _startWebRTC());
  }

  Future<void> _startWebRTC() async {
    // 1. Create peer connection with Google STUN server
    _pc = await createPeerConnection({
      'iceServers': [
        {'urls': 'stun:stun.l.google.com:19302'},
      ]
    });

    // 2. When remote video track arrives, attach to renderer
    _pc!.onTrack = (RTCTrackEvent event) {
      if (event.streams.isNotEmpty) {
        setState(() {
          _renderer.srcObject = event.streams[0];
          _connected = true;
        });
      }
    };

    // 3. Create SDP offer
    RTCSessionDescription offer = await _pc!.createOffer({
      'offerToReceiveVideo': 1,
    });
    await _pc!.setLocalDescription(offer);

    // 4. Push offer to Firebase so Python can pick it up
    final ref = FirebaseDatabase.instance
        .ref('sessions/cam${widget.camIndex}/offer');
    await ref.set({'sdp': offer.sdp, 'type': offer.type});

    // 5. Listen for Python's answer on Firebase
    FirebaseDatabase.instance
        .ref('sessions/cam${widget.camIndex}/answer')
        .onValue
        .listen((event) async {
      final data = event.snapshot.value as Map?;
      if (data != null && _pc != null) {
        final answer = RTCSessionDescription(
          data['sdp'] as String,
          data['type'] as String,
        );
        await _pc!.setRemoteDescription(answer);
      }
    });
  }

  @override
  void dispose() {
    _renderer.dispose();
    _pc?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            'Camera ${widget.camIndex}',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
        ),
        AspectRatio(
          aspectRatio: 16 / 9,
          child: _connected
              ? RTCVideoView(_renderer, objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover)
              : const Center(child: CircularProgressIndicator()),
        ),
        const SizedBox(height: 16),
      ],
    );
  }
}


--------------------------------------------------------------
FILE: cammonitoringapp/lib/main.dart
--------------------------------------------------------------
Replace the contents of the existing main.dart with this:

import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'camera_viewer.dart';

// Number of cameras streamed by Python (must match CAMERA_INDEXES in streamer.py)
const int kCameraCount = 2;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  runApp(const CamMonitoringApp());
}

class CamMonitoringApp extends StatelessWidget {
  const CamMonitoringApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cam Monitoring',
      theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
      home: const CameraListScreen(),
    );
  }
}

class CameraListScreen extends StatelessWidget {
  const CameraListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Live Cameras')),
      body: ListView(
        children: List.generate(
          kCameraCount,
          (i) => CameraViewer(camIndex: i),
        ),
      ),
    );
  }
}


==============================================================
  PART 3 — FIREBASE SETUP (manual steps for the user)
==============================================================

These steps must be done manually by the user. The agent
cannot perform them.

1. Go to https://console.firebase.google.com
2. Create a new project (or use an existing one)
3. Enable Realtime Database:
     Firebase Console → Build → Realtime Database → Create database
     Choose "Start in test mode" for the MVP
4. Download service account key:
     Firebase Console → Project Settings → Service Accounts
     → Generate new private key → save as:
     cammonitoringpy/serviceAccountKey.json
5. Connect Flutter to Firebase using FlutterFire CLI:
     Run these commands inside cammonitoringapp/:
       dart pub global activate flutterfire_cli
       flutterfire configure
     This generates: lib/firebase_options.dart
     Then update main.dart Firebase.initializeApp() call to:
       await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
     And add this import at the top of main.dart:
       import 'firebase_options.dart';
6. In streamer.py, replace YOUR_PROJECT_ID with your actual
   Firebase project ID in the databaseURL string.


==============================================================
  PART 4 — HOW TO RUN
==============================================================

PYTHON (run first):
  cd cammonitoringpy
  pip install -r requirements.txt
  python streamer.py

FLUTTER:
  cd cammonitoringapp
  flutter pub get
  flutter run

FLOW:
  1. Flutter creates a WebRTC offer → pushes to Firebase
  2. Python detects the offer → creates an answer → pushes to Firebase
  3. Flutter reads the answer → WebRTC handshake completes
  4. Video streams directly peer-to-peer (Firebase no longer involved)

To add more cameras:
  - Python:  add more indexes to CAMERA_INDEXES = [0, 1, 2]
  - Flutter: change kCameraCount = 3 in main.dart


==============================================================
  END OF INSTRUCTIONS
==============================================================

==============================================================
  CAM MONITOR — CustomTkinter Desktop App
  Tesla-inspired dark UI with dynamic multi-camera layout
==============================================================

TARGET FOLDER: cammonitoringpy/

Your job is to create/replace the two files listed below
inside the cammonitoringpy/ folder. Do NOT touch the Flutter
folder (cammonitoringapp/) — this is Python only.


==============================================================
  FILE 1 — cammonitoringpy/requirements.txt
==============================================================

customtkinter==5.2.2
opencv-python==4.9.0.80
Pillow==10.3.0


==============================================================
  FILE 2 — cammonitoringpy/app.py
==============================================================

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk
import threading
import time
import datetime
from collections import deque

# ── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG_DEEP    = "#0A0A0C"
BG_PANEL   = "#111116"
BG_CARD    = "#16161C"
BG_HOVER   = "#1E1E26"
ACCENT     = "#E8F4FD"
ACCENT_DIM = "#4A90C4"
TEAL       = "#00D4AA"
TEAL_DIM   = "#007A62"
RED        = "#FF3B3B"
AMBER      = "#F5A623"
BORDER     = "#2A2A35"
TEXT_PRI   = "#F0F0F5"
TEXT_SEC   = "#7A7A9A"
TEXT_MUTE  = "#3A3A50"

FONT_DISPLAY = ("SF Pro Display", 28, "bold")
FONT_TITLE   = ("SF Pro Display", 13, "bold")
FONT_BODY    = ("SF Pro Text",    12)
FONT_SMALL   = ("SF Pro Text",    10)
FONT_MONO    = ("SF Mono",        11)
FONT_HUGE    = ("SF Pro Display", 48, "bold")


# ── Camera Feed Thread ───────────────────────────────────────────────────────
class CameraFeed:
    def __init__(self, index: int):
        self.index   = index
        self.cap     = None
        self.frame   = None
        self.running = False
        self.fps     = 0
        self.status  = "offline"
        self._fps_times = deque(maxlen=30)

    def start(self):
        self.cap = cv2.VideoCapture(self.index)
        if self.cap.isOpened():
            self.running = True
            self.status  = "live"
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


# ── Pill Badge ───────────────────────────────────────────────────────────────
class PillBadge(ctk.CTkLabel):
    STATUS_COLORS = {
        "live":    (TEAL,  "#003328"),
        "offline": (RED,   "#2A0000"),
        "idle":    (AMBER, "#2A1800"),
    }

    def __init__(self, master, status="live", **kw):
        fg, bg = self.STATUS_COLORS.get(status, (TEXT_SEC, BG_CARD))
        super().__init__(master,
                         text=f"  \u25cf {status.upper()}  ",
                         font=("SF Pro Text", 9, "bold"),
                         text_color=fg,
                         fg_color=bg,
                         corner_radius=8,
                         **kw)
        self._status = status

    def set_status(self, status):
        if status == self._status:
            return
        self._status = status
        fg, bg = self.STATUS_COLORS.get(status, (TEXT_SEC, BG_CARD))
        self.configure(
            text=f"  \u25cf {status.upper()}  ",
            text_color=fg,
            fg_color=bg)


# ── Camera Card ───────────────────────────────────────────────────────────────
class CameraCard(ctk.CTkFrame):
    W, H = 480, 270

    def __init__(self, master, feed: CameraFeed, label="CAM", **kw):
        super().__init__(master,
                         fg_color=BG_CARD,
                         corner_radius=12,
                         border_width=1,
                         border_color=BORDER,
                         **kw)
        self.feed  = feed
        self.label = label
        self._build()
        self._update()

    def _build(self):
        self.canvas = ctk.CTkCanvas(self, width=self.W, height=self.H,
                                    bg=BG_DEEP, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=1, pady=1)

        hud = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=36)
        hud.pack(fill="x", side="bottom")
        hud.pack_propagate(False)

        self.lbl_name = ctk.CTkLabel(hud, text=self.label,
                                     font=FONT_TITLE, text_color=TEXT_PRI)
        self.lbl_name.pack(side="left", padx=12)

        self.badge = PillBadge(hud, status=self.feed.status)
        self.badge.pack(side="left", padx=4)

        self.lbl_fps = ctk.CTkLabel(hud, text="-- fps",
                                    font=FONT_MONO, text_color=TEXT_SEC)
        self.lbl_fps.pack(side="right", padx=12)

        self.lbl_time = ctk.CTkLabel(hud, text="",
                                     font=FONT_MONO, text_color=TEXT_MUTE)
        self.lbl_time.pack(side="right", padx=4)

        self.canvas.bind("<Enter>",
            lambda e: self.configure(border_color=ACCENT_DIM))
        self.canvas.bind("<Leave>",
            lambda e: self.configure(border_color=BORDER))

    def _draw_placeholder(self):
        w, h = self.W, self.H
        self.canvas.delete("all")
        for x in range(0, w, 40):
            self.canvas.create_line(x, 0, x, h, fill="#1A1A22", width=1)
        for y in range(0, h, 40):
            self.canvas.create_line(0, y, w, y, fill="#1A1A22", width=1)
        cx, cy = w // 2, h // 2
        self.canvas.create_oval(cx-30, cy-30, cx+30, cy+30,
                                 outline=TEXT_MUTE, width=1)
        self.canvas.create_line(cx-18, cy-18, cx+18, cy+18,
                                 fill=TEXT_MUTE, width=2)
        self.canvas.create_line(cx+18, cy-18, cx-18, cy+18,
                                 fill=TEXT_MUTE, width=2)
        self.canvas.create_text(cx, cy+52,
                                 text="NO SIGNAL",
                                 fill=TEXT_MUTE,
                                 font=("SF Pro Text", 11, "bold"))

    def _draw_frame(self, frame):
        w = self.canvas.winfo_width()  or self.W
        h = self.canvas.winfo_height() or self.H
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img   = Image.fromarray(rgb).resize((w, h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=photo)
        self.canvas._photo = photo

        blen, gap, thick = 18, 6, 2
        col = TEAL
        for (ox, oy, sx, sy) in [
            (gap,   gap,   1,  1),
            (w-gap, gap,  -1,  1),
            (gap,   h-gap, 1, -1),
            (w-gap, h-gap,-1, -1)
        ]:
            self.canvas.create_line(ox, oy, ox+sx*blen, oy,
                                     fill=col, width=thick)
            self.canvas.create_line(ox, oy, ox, oy+sy*blen,
                                     fill=col, width=thick)

        self.canvas.create_text(w-10, 10, anchor="ne",
                                 text=f"{self.feed.fps:.0f} fps",
                                 fill=TEAL, font=("SF Mono", 9))

    def _update(self):
        if self.feed.frame is not None and self.feed.status == "live":
            self._draw_frame(self.feed.frame)
            self.lbl_fps.configure(text=f"{self.feed.fps:.0f} fps")
        else:
            self._draw_placeholder()
            self.lbl_fps.configure(text="-- fps")

        self.badge.set_status(self.feed.status)
        self.lbl_time.configure(
            text=datetime.datetime.now().strftime("%H:%M:%S"))
        self.after(33, self._update)


# ── Sidebar ──────────────────────────────────────────────────────────────────
class Sidebar(ctk.CTkFrame):
    NAV = [
        ("\u229e", "Dashboard"),
        ("\u25c8", "Cameras"),
        ("\u25c9", "Analytics"),
        ("\u2316", "Alerts"),
        ("\u2699", "Settings"),
    ]

    def __init__(self, master, on_select, **kw):
        super().__init__(master, width=72, fg_color=BG_PANEL,
                         corner_radius=0, **kw)
        self.pack_propagate(False)
        self.on_select = on_select
        self._active   = "Dashboard"
        self._btns     = {}
        self._build()

    def _build(self):
        logo = ctk.CTkLabel(self, text="\u25c8",
                             font=("SF Pro Display", 24),
                             text_color=TEAL)
        logo.pack(pady=(24, 32))

        for icon, name in self.NAV:
            btn = ctk.CTkButton(
                self, text=icon, width=48, height=48,
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
            fill="x", padx=12, side="bottom", pady=8)
        ctk.CTkLabel(self, text="\u25ce",
                     font=("SF Pro Display", 20),
                     text_color=TEXT_SEC).pack(side="bottom", pady=8)

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


# ── Top Bar ──────────────────────────────────────────────────────────────────
class TopBar(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, height=56, fg_color=BG_PANEL,
                         corner_radius=0, **kw)
        self.pack_propagate(False)
        self._build()

    def _build(self):
        self.title_lbl = ctk.CTkLabel(
            self, text="DASHBOARD",
            font=("SF Pro Display", 13, "bold"),
            text_color=TEXT_PRI)
        self.title_lbl.pack(side="left", padx=24)

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=16)

        self.clock = ctk.CTkLabel(right, text="",
                                  font=FONT_MONO, text_color=TEXT_SEC)
        self.clock.pack(side="right", padx=12)

        self.date_lbl = ctk.CTkLabel(right, text="",
                                     font=FONT_MONO, text_color=TEXT_MUTE)
        self.date_lbl.pack(side="right")

        ctk.CTkFrame(self, fg_color=BORDER, width=1).pack(
            side="bottom", fill="x")

        self._tick()

    def _tick(self):
        now = datetime.datetime.now()
        self.clock.configure(text=now.strftime("%H:%M:%S"))
        self.date_lbl.configure(text=now.strftime("%a %d %b %Y  "))
        self.after(1000, self._tick)

    def set_title(self, title):
        self.title_lbl.configure(text=title.upper())


# ── Stat Card ────────────────────────────────────────────────────────────────
class StatCard(ctk.CTkFrame):
    def __init__(self, master, icon, label, value, accent=TEAL, **kw):
        super().__init__(master, fg_color=BG_CARD,
                         corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        ctk.CTkLabel(self, text=icon,
                     font=("SF Pro Display", 22),
                     text_color=accent).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(self, text=label,
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(
                     anchor="w", padx=16)
        self.val = ctk.CTkLabel(self, text=value,
                                font=("SF Pro Display", 26, "bold"),
                                text_color=TEXT_PRI)
        self.val.pack(anchor="w", padx=16, pady=(0, 14))

    def update(self, value):
        self.val.configure(text=value)


# ── Layout Switcher ───────────────────────────────────────────────────────────
class LayoutSwitcher(ctk.CTkFrame):
    LAYOUTS = ["1x1", "1x2", "2x2", "2x3"]

    def __init__(self, master, on_change, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._cb   = on_change
        self._cur  = "2x2"
        self._btns = {}
        ctk.CTkLabel(self, text="LAYOUT",
                     font=FONT_SMALL, text_color=TEXT_MUTE).pack(
                     side="left", padx=(0, 8))
        for lay in self.LAYOUTS:
            b = ctk.CTkButton(
                self, text=lay, width=48, height=28,
                font=FONT_SMALL,
                fg_color=BG_HOVER if lay == self._cur else "transparent",
                text_color=TEAL if lay == self._cur else TEXT_SEC,
                hover_color=BG_HOVER,
                border_width=1,
                border_color=BORDER,
                corner_radius=6,
                command=lambda l=lay: self._pick(l))
            b.pack(side="left", padx=2)
            self._btns[lay] = b

    def _pick(self, lay):
        self._cur = lay
        for l, b in self._btns.items():
            b.configure(
                fg_color=BG_HOVER if l == lay else "transparent",
                text_color=TEAL if l == lay else TEXT_SEC)
        self._cb(lay)


# ── Dashboard Page ────────────────────────────────────────────────────────────
class DashboardPage(ctk.CTkFrame):
    def __init__(self, master, feeds, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.feeds  = feeds
        self._cards = []
        self._layout = "2x2"
        self._build()

    def _build(self):
        stats_row = ctk.CTkFrame(self, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 16))

        live_count = sum(1 for f in self.feeds if f.status == "live")
        self._stat_live = StatCard(stats_row, "\u25c9", "CAMERAS LIVE",
                                   str(live_count), accent=TEAL)
        self._stat_live.pack(side="left", fill="both",
                             expand=True, padx=(0, 8))

        self._stat_fps = StatCard(stats_row, "\u25c8", "AVG FPS",
                                  "--", accent=ACCENT_DIM)
        self._stat_fps.pack(side="left", fill="both", expand=True, padx=8)

        self._stat_up = StatCard(stats_row, "\u2316", "UPTIME",
                                 "00:00:00", accent=AMBER)
        self._stat_up.pack(side="left", fill="both",
                           expand=True, padx=(8, 0))

        self._start = time.time()

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(toolbar, text="CAMERA FEEDS",
                     font=FONT_TITLE, text_color=TEXT_PRI).pack(side="left")
        self._switcher = LayoutSwitcher(toolbar, self._change_layout)
        self._switcher.pack(side="right")

        self._grid = ctk.CTkFrame(self, fg_color="transparent")
        self._grid.pack(fill="both", expand=True)

        self._render_layout()
        self._tick()

    def _change_layout(self, layout):
        self._layout = layout
        for w in self._grid.winfo_children():
            w.destroy()
        self._cards.clear()
        self._render_layout()

    def _render_layout(self):
        mapping = {"1x1": (1,1), "1x2": (1,2), "2x2": (2,2), "2x3": (2,3)}
        rows, cols = mapping.get(self._layout, (2, 2))

        for i in range(cols):
            self._grid.columnconfigure(i, weight=1, uniform="col")
        for j in range(rows):
            self._grid.rowconfigure(j, weight=1, uniform="row")

        idx = 0
        for r in range(rows):
            for c in range(cols):
                feed = self.feeds[idx % len(self.feeds)]
                card = CameraCard(self._grid, feed,
                                  label=f"CAM {feed.index:02d}")
                card.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
                self._cards.append(card)
                idx += 1

    def _tick(self):
        live = sum(1 for f in self.feeds if f.status == "live")
        fps_vals = [f.fps for f in self.feeds if f.status == "live"]
        avg_fps  = sum(fps_vals) / len(fps_vals) if fps_vals else 0
        up = int(time.time() - self._start)
        h, m, s = up // 3600, (up % 3600) // 60, up % 60

        self._stat_live.update(str(live))
        self._stat_fps.update(f"{avg_fps:.1f}")
        self._stat_up.update(f"{h:02d}:{m:02d}:{s:02d}")
        self.after(1000, self._tick)


# ── Cameras Page ──────────────────────────────────────────────────────────────
class CamerasPage(ctk.CTkFrame):
    def __init__(self, master, feeds, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        ctk.CTkLabel(self, text="Camera Management",
                     font=FONT_DISPLAY, text_color=TEXT_PRI).pack(
                     anchor="w", pady=(0, 20))

        self._feeds = feeds
        self._badges = {}

        for feed in feeds:
            row = ctk.CTkFrame(self, fg_color=BG_CARD,
                               corner_radius=10, border_width=1,
                               border_color=BORDER)
            row.pack(fill="x", pady=4)

            ctk.CTkLabel(row, text=f"CAM {feed.index:02d}",
                         font=FONT_TITLE, text_color=TEXT_PRI,
                         width=80).pack(side="left", padx=16, pady=14)

            badge = PillBadge(row, status=feed.status)
            badge.pack(side="left", padx=8)
            self._badges[feed.index] = (feed, badge)

            ctk.CTkLabel(row,
                         text=f"Index  /dev/video{feed.index}",
                         font=FONT_MONO,
                         text_color=TEXT_SEC).pack(side="left", padx=24)

            ctk.CTkButton(
                row, text="Restart", width=80, height=30,
                font=FONT_SMALL,
                fg_color="transparent",
                border_width=1, border_color=BORDER,
                text_color=TEXT_SEC,
                hover_color=BG_HOVER,
                corner_radius=6,
                command=lambda f=feed: self._restart(f)
            ).pack(side="right", padx=16)

        self._refresh()

    def _restart(self, feed):
        feed.stop()
        feed.start()

    def _refresh(self):
        for idx, (feed, badge) in self._badges.items():
            badge.set_status(feed.status)
        self.after(1000, self._refresh)


# ── Placeholder Page ──────────────────────────────────────────────────────────
class PlaceholderPage(ctk.CTkFrame):
    def __init__(self, master, title, icon, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        ctk.CTkFrame(self, fg_color="transparent").pack(expand=True, fill="both")
        ctk.CTkLabel(self, text=icon,
                     font=("SF Pro Display", 56),
                     text_color=TEXT_MUTE).pack()
        ctk.CTkLabel(self, text=title,
                     font=FONT_DISPLAY, text_color=TEXT_SEC).pack(pady=8)
        ctk.CTkLabel(self, text="This module is not yet configured.",
                     font=FONT_BODY, text_color=TEXT_MUTE).pack()
        ctk.CTkFrame(self, fg_color="transparent").pack(expand=True, fill="both")


# ── Main App ──────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    # ↓ Change these to your actual connected camera indexes
    CAMERA_INDEXES = [0, 1]

    def __init__(self):
        super().__init__()
        self.title("CAM MONITOR")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.configure(fg_color=BG_DEEP)
        self._feeds  = []
        self._pages  = {}
        self._active = None
        self._start_feeds()
        self._build_ui()
        self._switch_page("Dashboard")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_feeds(self):
        for idx in self.CAMERA_INDEXES:
            f = CameraFeed(idx)
            f.start()
            self._feeds.append(f)

    def _build_ui(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True)

        self._sidebar = Sidebar(root, on_select=self._switch_page)
        self._sidebar.pack(side="left", fill="y")

        ctk.CTkFrame(root, width=1, fg_color=BORDER).pack(side="left", fill="y")

        main = ctk.CTkFrame(root, fg_color="transparent")
        main.pack(side="left", fill="both", expand=True)

        self._topbar = TopBar(main)
        self._topbar.pack(fill="x")

        self._content = ctk.CTkFrame(main, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=20, pady=16)

        self._pages = {
            "Dashboard": DashboardPage(self._content, self._feeds),
            "Cameras":   CamerasPage(self._content, self._feeds),
            "Analytics": PlaceholderPage(self._content, "Analytics", "\u25c8"),
            "Alerts":    PlaceholderPage(self._content, "Alerts",    "\u2316"),
            "Settings":  PlaceholderPage(self._content, "Settings",  "\u2699"),
        }

    def _switch_page(self, name):
        if self._active:
            self._pages[self._active].pack_forget()
        self._pages[name].pack(fill="both", expand=True)
        self._active = name
        self._topbar.set_title(name)

    def _on_close(self):
        for f in self._feeds:
            f.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()


==============================================================
  HOW TO RUN
==============================================================

1. Install dependencies:
     cd cammonitoringpy
     pip install -r requirements.txt

2. Edit CAMERA_INDEXES in app.py:
     CAMERA_INDEXES = [0, 1]
     Change to match your connected camera indexes.
     Use [0] if you only have one camera (e.g. laptop webcam).

3. Run:
     python app.py


==============================================================
  WHAT EACH PAGE DOES
==============================================================

Dashboard  — Live camera grid with stat cards at top.
             Switch layouts: 1x1 / 1x2 / 2x2 / 2x3 dynamically.
             Each card shows: live video, FPS, status badge, timestamp.
             Corner bracket HUD overlay on each live feed.

Cameras    — Management list. Shows each camera's status badge.
             Restart button to reconnect a dropped camera.

Analytics  — Placeholder (ready to build out).
Alerts     — Placeholder (ready to build out).
Settings   — Placeholder (ready to build out).


==============================================================
  END OF INSTRUCTIONS
==============================================================