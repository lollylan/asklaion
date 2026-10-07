"""
Globale Tastenkürzel und Texteinfügung (Windows, reines ctypes)
================================================================
* HotkeyManager: systemweiter Low-Level-Tastaturhook. Kennt
    - Aktions-Kürzel (z. B. "ctrl+shift+f9" -> Start),
    - eine Push-to-Talk-Taste (gedrückt halten = Diktat, loslassen = Ende),
    - einen Aufnahmemodus für die Einstellungen ("Taste drücken ...").
  Links/rechts wird unterschieden ("rctrl" = rechte Strg-Taste allein).
  Auch von Makro-Tools (AutoHotkey, Stream Deck, Maustasten-Software)
  gesendete Tasten werden erkannt.
* insert_text(): schreibt Text in das aktive Fenster eines beliebigen
  Programms – per Zwischenablage + Strg+V oder Zeichen für Zeichen.

Kürzel-Format: Tokens mit "+" verbunden, z. B. "ctrl+alt+d", "f13", "rctrl".
Auf anderen Plattformen ist alles ein No-op (start() liefert False).
"""

import sys
import threading
import queue
import time

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    ULONG_PTR = ctypes.c_size_t
    LRESULT = ctypes.c_ssize_t

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_QUIT = 0x0100, 0x0101, 0x0104, 0x0105, 0x0012
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
VK_RETURN, VK_TAB, VK_CONTROL = 0x0D, 0x09, 0x11

# Kennzeichnet eigene SendInput-Ereignisse, damit der Hook sie ignoriert.
# Ereignisse fremder Makro-Tools werden dagegen normal ausgewertet.
_OWN_MARKER = 0x41534B4C  # "ASKL"

# ---------------------------------------------------------------------------
# Tastennamen
# ---------------------------------------------------------------------------
_LSHIFT, _RSHIFT, _LCTRL, _RCTRL, _LALT, _RALT, _LWIN, _RWIN = 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C
MODIFIER_VKS = {_LSHIFT, _RSHIFT, _LCTRL, _RCTRL, _LALT, _RALT, _LWIN, _RWIN}
# generische VKs (selten im LL-Hook) auf die linke Variante abbilden
_GENERIC_TO_SIDE = {0x10: _LSHIFT, 0x11: _LCTRL, 0x12: _LALT}

_MODIFIER_TOKENS = {
    "ctrl": {_LCTRL, _RCTRL}, "lctrl": {_LCTRL}, "rctrl": {_RCTRL},
    "shift": {_LSHIFT, _RSHIFT}, "lshift": {_LSHIFT}, "rshift": {_RSHIFT},
    "alt": {_LALT, _RALT}, "lalt": {_LALT}, "ralt": {_RALT},
    "win": {_LWIN, _RWIN}, "lwin": {_LWIN}, "rwin": {_RWIN},
}
_TOKEN_ALIASES = {"strg": "ctrl", "control": "ctrl", "umschalt": "shift", "altgr": "ralt", "escape": "esc",
                  "return": "enter", "del": "delete", "entf": "delete", "ins": "insert", "einfg": "insert",
                  "pgup": "pageup", "pgdn": "pagedown", "leertaste": "space"}

_KEY_TOKENS = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27,
    "down": 0x28, "pause": 0x13, "scrolllock": 0x91, "capslock": 0x14, "printscreen": 0x2C, "numlock": 0x90,
    "apps": 0x5D, "nummul": 0x6A, "numplus": 0x6B, "numminus": 0x6D, "numdec": 0x6E, "numdiv": 0x6F,
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF, "nexttrack": 0xB0, "prevtrack": 0xB1,
    "mediastop": 0xB2, "playpause": 0xB3,
}
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    _KEY_TOKENS[_c] = ord(_c.upper())
for _n in range(1, 25):
    _KEY_TOKENS[f"f{_n}"] = 0x70 + _n - 1
for _n in range(10):
    _KEY_TOKENS[f"num{_n}"] = 0x60 + _n
_VK_TO_TOKEN = {vk: tok for tok, vk in _KEY_TOKENS.items()}
_SIDE_TOKEN = {_LCTRL: "lctrl", _RCTRL: "rctrl", _LSHIFT: "lshift", _RSHIFT: "rshift",
               _LALT: "lalt", _RALT: "ralt", _LWIN: "lwin", _RWIN: "rwin"}
_GENERIC_TOKEN = {_LCTRL: "ctrl", _RCTRL: "ctrl", _LSHIFT: "shift", _RSHIFT: "shift",
                  _LALT: "alt", _RALT: "alt", _LWIN: "win", _RWIN: "win"}
_MOD_ORDER = ["ctrl", "lctrl", "rctrl", "shift", "lshift", "rshift", "alt", "lalt", "ralt", "win", "lwin", "rwin"]

_DISPLAY = {
    "ctrl": "Strg", "lctrl": "Strg links", "rctrl": "Strg rechts", "shift": "Umschalt",
    "lshift": "Umschalt links", "rshift": "Umschalt rechts", "alt": "Alt", "lalt": "Alt links", "ralt": "AltGr",
    "win": "Win", "lwin": "Win links", "rwin": "Win rechts", "space": "Leertaste", "enter": "Eingabe",
    "esc": "Esc", "backspace": "Rücktaste", "insert": "Einfg", "delete": "Entf", "home": "Pos1", "end": "Ende",
    "pageup": "Bild auf", "pagedown": "Bild ab", "left": "Pfeil links", "up": "Pfeil hoch",
    "right": "Pfeil rechts", "down": "Pfeil runter", "pause": "Pause", "scrolllock": "Rollen",
    "capslock": "Feststell", "printscreen": "Druck", "apps": "Menü", "playpause": "Play/Pause",
}
# Anzeigenamen ("Strg rechts", "Bild auf", ...) dürfen auch eingetippt werden
for _tok, _name in _DISPLAY.items():
    _TOKEN_ALIASES.setdefault(_name.replace(" ", "").lower(), _tok)


class Combo:
    """Eine Tastenkombination: Liste von 'Slots', jeder Slot = Menge passender VK-Codes."""

    def __init__(self, text: str):
        self.text = normalize_combo(text)
        if not self.text:
            raise ValueError("leeres Kürzel")
        self.slots = []
        self.modifier_only = True
        for tok in self.text.split("+"):
            if tok in _MODIFIER_TOKENS:
                self.slots.append(frozenset(_MODIFIER_TOKENS[tok]))
            else:
                self.slots.append(frozenset({_token_to_vk(tok)}))
                self.modifier_only = False
        self.all_vks = frozenset().union(*self.slots)

    def matches(self, pressed: set) -> bool:
        """Alle Slots belegt und keine zusätzlichen Tasten gedrückt."""
        if not all(slot & pressed for slot in self.slots):
            return False
        return all(vk in self.all_vks for vk in pressed)

    def contains(self, vk: int) -> bool:
        return vk in self.all_vks


def _token_to_vk(tok: str) -> int:
    if tok in _KEY_TOKENS:
        return _KEY_TOKENS[tok]
    if tok.startswith("vk") and tok[2:].isdigit():
        return int(tok[2:])
    raise ValueError(f"unbekannte Taste '{tok}'")


def normalize_combo(text: str) -> str:
    toks = [t.strip().lower() for t in (text or "").replace(" ", "").split("+") if t.strip()]
    toks = [_TOKEN_ALIASES.get(t, t) for t in toks]
    mods = sorted((t for t in toks if t in _MODIFIER_TOKENS), key=_MOD_ORDER.index)
    keys = [t for t in toks if t not in _MODIFIER_TOKENS]
    return "+".join(dict.fromkeys(mods + keys))


def format_combo(text: str) -> str:
    """Anzeigename, z. B. 'ctrl+shift+f9' -> 'Strg + Umschalt + F9'."""
    norm = normalize_combo(text)
    if not norm:
        return ""
    return " + ".join(_DISPLAY.get(t, t.upper()) for t in norm.split("+"))


def validate_combo(text: str) -> str:
    """Gibt eine Fehlermeldung zurück oder '' wenn gültig (leer = deaktiviert ist gültig)."""
    if not (text or "").strip():
        return ""
    try:
        Combo(text)
        return ""
    except ValueError as e:
        return str(e)


def _combo_from_vks(vks: list) -> str:
    """Kürzel aus den beim Festlegen gedrückten Tasten (in Drückreihenfolge)."""
    mods = [vk for vk in vks if vk in MODIFIER_VKS]
    keys = [vk for vk in vks if vk not in MODIFIER_VKS]
    if keys:   # mit Haupttaste: Seite der Modifikatoren egal (bequemer)
        toks = [_GENERIC_TOKEN[vk] for vk in mods]
    else:      # nur Modifikatoren (z. B. rechte Strg allein): Seite ist entscheidend
        toks = [_SIDE_TOKEN[vk] for vk in mods]
    toks += [_VK_TO_TOKEN.get(vk, f"vk{vk}") for vk in keys]
    return normalize_combo("+".join(toks))


# ---------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------
class _Binding:
    def __init__(self, name, combo, kind, callbacks):
        self.name, self.combo, self.kind, self.callbacks = name, combo, kind, callbacks


class HotkeyManager:
    """Systemweiter Tastaturhook in eigenem Thread; Rückrufe laufen in einem Dispatcher-Thread
    (nacheinander, nie im Hook selbst – der muss in wenigen ms zurückkehren)."""

    def __init__(self, on_error=None):
        self.on_error = on_error or (lambda msg: print(f"Hotkeys: {msg}"))
        self._bindings = []
        self._lock = threading.Lock()
        self._pressed = set()
        self._suppressed = set()
        self._ptt = None            # aktive PTT-Bindung, solange gehalten
        self._tap = None            # Kandidat für reine Modifikator-Kürzel (Auslösung beim Loslassen)
        self._capture_cb = None
        self._capture_keys = []
        self._capture_down = set()
        self._dispatch_q = queue.Queue()
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._proc = None
        self.running = False

    # -------------------------------------------------------------- Steuerung
    def start(self) -> bool:
        if not IS_WINDOWS:
            return False
        if self.running:
            return True
        ready = threading.Event()
        self._thread = threading.Thread(target=self._hook_loop, args=(ready,), daemon=True, name="hotkey-hook")
        self._thread.start()
        threading.Thread(target=self._dispatch_loop, daemon=True, name="hotkey-dispatch").start()
        ready.wait(3)
        return self.running

    def stop(self):
        if self.running and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def set_bindings(self, actions: dict, ptt=None) -> list:
        """actions: {name: (kürzel, callback)}; ptt: (kürzel, on_press, on_release, on_cancel) oder None.
        Leere Kürzel werden übersprungen. Gibt eine Liste von Fehlermeldungen zurück."""
        errors, bindings, seen = [], [], {}
        items = [(n, c, "action", (cb,)) for n, (c, cb) in actions.items()]
        if ptt:
            items.append(("Diktat (gedrückt halten)", ptt[0], "ptt", tuple(ptt[1:])))
        for name, text, kind, cbs in items:
            if not (text or "").strip():
                continue
            try:
                combo = Combo(text)
            except ValueError as e:
                errors.append(f"{name}: {e}")
                continue
            if combo.text in seen:
                errors.append(f"{name}: {format_combo(combo.text)} ist schon für '{seen[combo.text]}' vergeben")
                continue
            seen[combo.text] = name
            bindings.append(_Binding(name, combo, kind, cbs))
        # PTT zuerst prüfen, damit es bei Überschneidungen Vorrang hat
        bindings.sort(key=lambda b: b.kind != "ptt")
        with self._lock:
            self._bindings = bindings
            self._ptt = None
            self._tap = None
        return errors

    def capture(self, callback):
        """Nächste gedrückte Tastenkombination aufnehmen; callback(kürzel) bzw. callback(None) bei Esc."""
        with self._lock:
            self._capture_cb = callback
            self._capture_keys = []
            self._capture_down = set()

    def cancel_capture(self):
        with self._lock:
            self._capture_cb = None

    # -------------------------------------------------------------- Threads
    def _dispatch(self, fn, *args):
        self._dispatch_q.put((fn, args))

    def _dispatch_loop(self):
        while True:
            fn, args = self._dispatch_q.get()
            try:
                fn(*args)
            except Exception as e:
                self.on_error(f"Fehler im Kürzel-Rückruf: {e}")

    def _hook_loop(self, ready):
        self._thread_id = kernel32.GetCurrentThreadId()

        def proc(n_code, w_param, l_param):
            if n_code == 0:
                try:
                    kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if kb.dwExtraInfo != _OWN_MARKER:
                        down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                        if self._on_key(_GENERIC_TO_SIDE.get(kb.vkCode, kb.vkCode), down):
                            return 1   # Taste schlucken
                except Exception as e:
                    print(f"Hotkey-Hook: {e}")
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)   # Referenz halten, sonst räumt der GC den Callback ab
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            self.on_error(f"Tastaturhook konnte nicht installiert werden (Fehler {ctypes.get_last_error()})")
            ready.set()
            return
        self.running = True
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(self._hook)
        self.running = False

    # -------------------------------------------------------------- Logik
    def _prune(self, current_vk):
        """Hängende Tasten entfernen (z. B. Keyup verpasst bei Sperrbildschirm/UAC)."""
        for vk in list(self._pressed):
            if vk != current_vk and not (user32.GetAsyncKeyState(vk) & 0x8000):
                self._pressed.discard(vk)
                self._suppressed.discard(vk)

    def _on_key(self, vk, down) -> bool:
        """Gibt True zurück, wenn die Taste geschluckt werden soll."""
        with self._lock:
            if self._capture_cb is not None:
                return self._on_capture(vk, down)
            if down:
                repeat = vk in self._pressed
                self._prune(vk)
                self._pressed.add(vk)
                if repeat:                       # Autorepeat beim Halten
                    return vk in self._suppressed
                if self._ptt is not None:
                    if not self._ptt.combo.contains(vk):
                        # andere Taste dazu -> war wohl ein normales Tastenkürzel (z. B. Strg+C)
                        b, self._ptt = self._ptt, None
                        self._dispatch(b.callbacks[2])
                    return False
                self._tap = None
                for b in self._bindings:
                    if not b.combo.matches(self._pressed):
                        continue
                    if b.kind == "ptt":
                        self._ptt = b
                        self._dispatch(b.callbacks[0])
                    elif b.combo.modifier_only:
                        self._tap = b            # erst beim Loslassen auslösen
                        return False
                    else:
                        self._dispatch(b.callbacks[0])
                    if vk not in MODIFIER_VKS:   # Haupttaste nicht an das aktive Programm weitergeben
                        self._suppressed.add(vk)
                        return True
                    return False
                return False
            # Taste losgelassen
            self._pressed.discard(vk)
            swallow = vk in self._suppressed
            self._suppressed.discard(vk)
            if self._ptt is not None and self._ptt.combo.contains(vk):
                b, self._ptt = self._ptt, None
                self._dispatch(b.callbacks[1])
            if self._tap is not None:
                b, self._tap = self._tap, None
                if b.combo.contains(vk):
                    self._dispatch(b.callbacks[0])
            return swallow

    def _on_capture(self, vk, down) -> bool:
        if down:
            if vk == 0x1B and not self._capture_keys:     # Esc bricht ab
                cb, self._capture_cb = self._capture_cb, None
                self._dispatch(cb, None)
                return True
            if vk not in self._capture_keys:
                self._capture_keys.append(vk)
            self._capture_down.add(vk)
            return True
        self._capture_down.discard(vk)
        if not self._capture_down and self._capture_keys:
            combo = _combo_from_vks(self._capture_keys)
            cb, self._capture_cb = self._capture_cb, None
            self._pressed.clear()
            self._dispatch(cb, combo)
        return True


# ---------------------------------------------------------------------------
# Text in fremde Programme einfügen
# ---------------------------------------------------------------------------
def _key_input(vk=0, scan=0, flags=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=_OWN_MARKER)
    return inp


def _send(inputs):
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def foreground_window():
    return user32.GetForegroundWindow() if IS_WINDOWS else None


def wait_for_modifiers_released(timeout=2.0):
    """Erst einfügen, wenn der Nutzer Strg/Umschalt/Alt/Win losgelassen hat –
    sonst wird aus Strg+V z. B. Strg+Umschalt+V."""
    if not IS_WINDOWS:
        return
    end = time.time() + timeout
    while time.time() < end:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, _LWIN, _RWIN)):
            return
        time.sleep(0.02)


def focus_window(hwnd):
    if IS_WINDOWS and hwnd and user32.IsWindow(hwnd) and user32.GetForegroundWindow() != hwnd:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)


def type_text(text: str):
    """Zeichen für Zeichen als Unicode-Tastendrücke (funktioniert auch, wo Strg+V gesperrt ist)."""
    if not IS_WINDOWS:
        return
    batch = []

    def flush():
        _send(batch)
        batch.clear()
        time.sleep(0.005)

    for ch in text.replace("\r\n", "\n"):
        if ch == "\n":
            batch += [_key_input(VK_RETURN), _key_input(VK_RETURN, flags=KEYEVENTF_KEYUP)]
        elif ch == "\t":
            batch += [_key_input(VK_TAB), _key_input(VK_TAB, flags=KEYEVENTF_KEYUP)]
        else:
            units = ch.encode("utf-16-le")
            for i in range(0, len(units), 2):
                code = int.from_bytes(units[i:i + 2], "little")
                batch += [_key_input(scan=code, flags=KEYEVENTF_UNICODE),
                          _key_input(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
        if len(batch) >= 60:
            flush()
    flush()


def paste_text(text: str, restore_clipboard=True):
    """Über die Zwischenablage + Strg+V einfügen; der vorherige Text der Zwischenablage
    wird danach wiederhergestellt (z. B. das zuletzt erzeugte Analyse-Ergebnis)."""
    if not IS_WINDOWS:
        return
    import pyperclip
    old = None
    if restore_clipboard:
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
    pyperclip.copy(text.replace("\r\n", "\n").replace("\n", "\r\n"))
    time.sleep(0.03)
    _send([_key_input(VK_CONTROL), _key_input(0x56), _key_input(0x56, flags=KEYEVENTF_KEYUP),
           _key_input(VK_CONTROL, flags=KEYEVENTF_KEYUP)])
    if old:
        # Das Zielprogramm liest die Zwischenablage asynchron – kurz warten.
        time.sleep(0.4)
        try:
            pyperclip.copy(old)
        except Exception:
            pass


def insert_text(text: str, mode="paste", target_hwnd=None):
    if not IS_WINDOWS or not text:
        return
    wait_for_modifiers_released()
    focus_window(target_hwnd)
    if mode == "type":
        type_text(text)
    else:
        paste_text(text)


def make_no_activate(tk_window):
    """Tk-Fenster so markieren, dass es beim Anzeigen nie den Fokus stiehlt
    (sonst landet der diktierte Text im Overlay statt im PVS)."""
    if not IS_WINDOWS:
        return
    GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = -20, 0x08000000, 0x00000080, 0x00000008
    tk_window.update_idletasks()
    hwnd = user32.GetParent(tk_window.winfo_id()) or tk_window.winfo_id()
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
