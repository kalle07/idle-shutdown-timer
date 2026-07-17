import ctypes
import queue
import subprocess
import sys
import time
import threading
import io
import tempfile
import os
from collections import deque
from typing import Dict, List
import psutil
import tkinter as tk
from tkinter import messagebox
import pystray
from PIL import Image, ImageDraw, ImageFont


# Cache ctypes return types once at module load
ctypes.windll.user32.GetLastInputInfo.restype = ctypes.c_bool
ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong

# Configuration constants
POLL_INTERVAL = 5.0
HISTORY_SIZE = 3
NETWORK_IDLE_THRESHOLD = 1_000_000.0  # 1 MB/s

NetPollData = Dict[str, Dict[str, float]]


class LASTINPUTINFO(ctypes.Structure):
    """Structure required by the GetLastInputInfo Windows API."""
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_ulong)
    ]


def is_cpu_active(cpu_history: deque) -> bool:
    if len(cpu_history) < HISTORY_SIZE:
        return False
    return all(any(core > 50.0 for core in poll) for poll in cpu_history)


def is_cpu_busy_by_sum(cpu_history: deque) -> bool:
    if len(cpu_history) < HISTORY_SIZE:
        return False
    num_cores = len(cpu_history[0])
    threshold = 12.5 * num_cores
    return any(sum(poll) >= threshold for poll in cpu_history)


def is_network_idle(net_history: deque, threshold: float) -> bool:
    if len(net_history) < HISTORY_SIZE:
        return False
    for poll in net_history:
        if not poll:
            continue
        if all(data["sent"] < threshold and data["recv"] < threshold for data in poll.values()):
            return True
    return False


def get_idle_time() -> float:
    last_input_info = LASTINPUTINFO()
    last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
        raise ctypes.WinError(ctypes.get_last_error())
    uptime_ms = ctypes.windll.kernel32.GetTickCount64()
    return (uptime_ms - last_input_info.dwTime) / 1000.0


def shutdown_system() -> None:
    print("Idle timeout reached. Shutting down system...")
    subprocess.run(["shutdown", "/s", "/t", "0"], check=True)


def format_timeout(seconds: int) -> str:
    """Formats seconds into a human-readable string for the tray tooltip."""
    if seconds < 60:
        return f"{seconds}s"
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}m {secs}s" if secs else f"{mins}m"


def create_icon_image() -> Image.Image:
    """Generates a dark-blue icon with white 'Zz' text and returns a PIL Image."""
    width, height = 16, 16
    # Create a new RGBA image with dark blue background (0, 0, 128, 255)
    img = Image.new("RGBA", (width, height), (0, 0, 128, 255))
    draw = ImageDraw.Draw(img)
    
    # Load a standard font, falling back to PIL's default if Arial isn't found
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except OSError:
        font = ImageFont.load_default()
        
    # Calculate bounding box to perfectly center the text
    bbox = draw.textbbox((0, 0), "Zz", font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (width - text_w) // 2
    y = (height - text_h) // 2
    
    draw.text((x, y), "Zz", fill="white", font=font)
    return img



def run_idle_monitor(timeout: int, force_shutdown: bool, stop_event: threading.Event) -> None:
    mode_label = "Force Shutdown Mode" if force_shutdown else "Standard Idle Monitoring"
    print(f"Starting {mode_label}. Timeout: {timeout} seconds.")
    if not force_shutdown:
        print("System will only shut down when idle, CPU, and network conditions are simultaneously met.")
    else:
        print("All idle checks are disabled. Shutdown will trigger unconditionally after timeout.")
    print("Press Ctrl+C to abort monitoring.")

    cpu_history: deque[List[float]] = deque(maxlen=HISTORY_SIZE)
    net_history: deque[NetPollData] = deque(maxlen=HISTORY_SIZE)
    last_net_counters = psutil.net_io_counters(pernic=True)

    valid_nics = [nic for nic, stats in psutil.net_if_stats().items() if stats.isup and stats.speed > 0]
    if not valid_nics and not force_shutdown:
        print("Warning: No active network adapters with speed > 0 detected. Network check will be bypassed.")

    start_time = time.monotonic()
    last_poll_time = time.monotonic()
    prev_idle_seconds = get_idle_time()

    try:
        if not force_shutdown:
            psutil.cpu_percent(percpu=True)
            time.sleep(POLL_INTERVAL)

        while True:
            if stop_event.is_set():
                return

            now = time.monotonic()
            actual_interval = now - last_poll_time
            last_poll_time = now

            if not force_shutdown:
                cpu_perc = psutil.cpu_percent(percpu=True)
                cpu_history.append(cpu_perc)

                current_counters = psutil.net_io_counters(pernic=True)
                net_poll: NetPollData = {}
                for nic in valid_nics:
                    if nic in current_counters and nic in last_net_counters:
                        divisor = max(actual_interval, 1e-9)
                        delta_sent = max(0, current_counters[nic].bytes_sent - last_net_counters[nic].bytes_sent)
                        delta_recv = max(0, current_counters[nic].bytes_recv - last_net_counters[nic].bytes_recv)
                        net_poll[nic] = {"sent": delta_sent / divisor, "recv": delta_recv / divisor}

                net_history.append(net_poll)
                last_net_counters = current_counters

                idle_seconds = get_idle_time()
                input_active = idle_seconds < prev_idle_seconds
                cpu_active = is_cpu_active(cpu_history) or is_cpu_busy_by_sum(cpu_history)
                net_active = valid_nics and not is_network_idle(net_history, NETWORK_IDLE_THRESHOLD)

                if input_active or cpu_active or net_active:
                    start_time = time.monotonic()
                prev_idle_seconds = idle_seconds

            if time.monotonic() - start_time >= timeout:
                shutdown_system()
                break

            sleep_time = POLL_INTERVAL - (time.monotonic() - last_poll_time)
            if sleep_time > 0:
                # Interruptible sleep: returns True if stop_event is set
                if stop_event.wait(sleep_time):
                    return

    except KeyboardInterrupt:
        print("\nMonitoring aborted by user.")
        sys.exit(0)


def setup_shutdown_gui(root: tk.Tk) -> Dict[str, object]:
    """Displays a small Tkinter window to select the shutdown timeout."""
    result: Dict[str, object] = {"timeout": 900, "force_shutdown": False}
    root.title("Shutdown Timer")
    root.resizable(False, False)
    root.geometry("550x350")
    # Close via X exits the program as requested
    root.protocol("WM_DELETE_WINDOW", lambda: sys.exit(0))

    tk.Label(root, text="Select shutdown timeout:", font=("Arial", 10, "bold")).pack(pady=10)

    preset_frame = tk.Frame(root)
    preset_frame.pack(pady=5)

    presets = [(300, "5 min"), (900, "15 min"), (1800, "30 min"), (3600, "1 hour"), (10800, "3 hours")]
    entry: tk.Entry

    input_frame = tk.Frame(root)
    input_frame.pack(pady=10)
    tk.Label(input_frame, text="Custom (seconds):").pack(side=tk.LEFT)

    def validate_input(new_value: str) -> bool:
        return new_value == "" or new_value.isdigit()

    entry = tk.Entry(input_frame, width=8, justify=tk.CENTER, validate="key",
                     validatecommand=(root.register(validate_input), "%P"))
    entry.pack(side=tk.LEFT, padx=5)
    entry.insert(0, "900")

    def on_select(seconds: int) -> None:
        entry.delete(0, tk.END)
        entry.insert(0, str(seconds))

    for seconds, label in presets:
        tk.Button(preset_frame, text=label, width=8, command=lambda s=seconds: on_select(s)).pack(side=tk.LEFT, padx=5)

    def on_ok() -> None:
        try:
            value = int(entry.get())
            if value < 5 or value > 86400:
                messagebox.showerror("Invalid Input", "Please enter a whole number between 5 and 86400 seconds.")
                return
            result["timeout"] = value
            result["force_shutdown"] = force_shutdown_var.get()
            root.destroy()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a whole number (no decimals allowed).")

    explanation_frame = tk.Frame(root, padx=10, pady=5)
    explanation_frame.pack(fill=tk.X, padx=20, pady=5)
    explanation_text = (
        "Idle Check Logic (3 × 5s polls = 15s window):\n\n"
        "When will idle timer Reset:\n"
        "⌨/🖱	Mouse/keyboard/touch activity.\n"
        "🖥	CPU: Active if ANY poll has ≥1 core >50% OR total usage >12.5% × cores.\n"
        "🌐	Network: Active if ALL polls show ≥1 MB/s on at least one NIC.\n"
        "⚠️	Note: Discrete GPU workloads mostly uses one core >50%."
    )
    tk.Label(explanation_frame, text=explanation_text, justify=tk.LEFT, font=("Arial", 9),
             anchor="w", wraplength=480).pack(anchor="w", fill=tk.X)

    force_shutdown_var = tk.BooleanVar(value=False)
    tk.Checkbutton(root, text="Force shutdown after timeout (ignore idle checks)",
                   variable=force_shutdown_var, font=("Arial", 9)).pack(pady=5)

    action_frame = tk.Frame(root)
    action_frame.pack(pady=15)
    tk.Button(action_frame, text="OK", width=6, command=on_ok).pack(side=tk.LEFT, padx=10)
    tk.Button(action_frame, text="Exit", width=6, command=lambda: sys.exit(0)).pack(side=tk.LEFT, padx=10)

    root.mainloop()
    return result


class IdleMonitorApp:
    """Manages the application lifecycle, system tray, threading, and GUI state."""
    def __init__(self):
        self.config: Dict[str, object] = {"timeout": 900, "force_shutdown": False}
        self.stop_event = threading.Event()
        self.monitor_thread: threading.Thread | None = None
        self.tray_icon: pystray.Icon | None = None
        self.gui_queue: queue.Queue[str] = queue.Queue()  # Thread-safe command queue

        self._check_single_instance()
        self._create_tray_icon()
        self._show_gui()
        self._start_monitor()

        # Run pystray in a background thread to avoid blocking tkinter's event loop
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

        # Keep main thread alive to process GUI requests safely
        self._main_thread_loop()


    def _main_thread_loop(self) -> None:
        """Runs in the main thread to handle tkinter dialogs safely."""
        while not self.stop_event.is_set():
            try:
                # Block until a command arrives or timeout elapses
                cmd = self.gui_queue.get(timeout=0.1)
                if cmd == "show_gui":
                    self._show_gui_from_tray()
            except queue.Empty:
                continue


    def _show_gui_from_tray(self) -> None:
        """Executes GUI creation in the main thread."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.stop_event.set()
            self.monitor_thread.join(timeout=2.0)
            self.stop_event.clear()

        root = tk.Tk()
        self.config = setup_shutdown_gui(root)
        self._update_tray_tooltip()
        self._start_monitor()

    def _check_single_instance(self) -> None:
        mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "IdleTimer_Mutex")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            print("Another instance is already running. Exiting.")
            sys.exit(0)

    def _create_tray_icon(self) -> None:
        icon_img = create_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Open GUI", self._on_open_gui),
            pystray.MenuItem("Exit", self._on_exit)
        )
        self.tray_icon = pystray.Icon(
            "idle_timer",
            icon_img,  # Pass PIL Image directly
            f"Idle Timer: {format_timeout(self.config['timeout'])}",
            menu
        )

    def _update_tray_tooltip(self) -> None:
        if self.tray_icon:
            self.tray_icon.title = f"Idle Timer: {format_timeout(self.config['timeout'])}"

    def _on_open_gui(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        # Safely request GUI display from the main thread
        self.gui_queue.put("show_gui")

    def _on_exit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        self.tray_icon.stop()
        sys.exit(0)

    def _show_gui(self) -> None:
        root = tk.Tk()
        self.config = setup_shutdown_gui(root)
        self._update_tray_tooltip()

    def _start_monitor(self) -> None:
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(
            target=run_idle_monitor,
            args=(self.config["timeout"], self.config["force_shutdown"], self.stop_event),
            daemon=True
        )
        self.monitor_thread.start()


def main() -> None:
    IdleMonitorApp()


if __name__ == "__main__":
    main()
