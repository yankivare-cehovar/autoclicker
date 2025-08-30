
import sys
import threading
import time
import json
import random
import os
import winsound
from pynput import mouse, keyboard
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QCheckBox, QFrame, QListWidget, 
                             QInputDialog, QMessageBox, QTabWidget, QSpinBox, QSystemTrayIcon, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QAction

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- STYLESHEET ---
STYLESHEET = """
QWidget {
    background-color: #2E2E2E;
    color: #F0F0F0;
    font-size: 10pt;
    font-family: Arial;
}
QLabel {
    border: none;
}
QLineEdit, QSpinBox {
    background-color: #3C3C3C;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px;
    color: #F0F0F0;
}
QPushButton {
    background-color: #4A4A4A;
    color: #F0F0F0;
    border: none;
    border-radius: 4px;
    padding: 8px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #5A5A5A;
}
QPushButton:pressed {
    background-color: #6A6A6A;
}
QPushButton:disabled {
    background-color: #404040;
    color: #888888;
}
QFrame#clickerFrame, QFrame#profileFrame {
    background-color: #383838;
    border: 1px solid #444444;
    border-radius: 5px;
}
QCheckBox {
    spacing: 5px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QListWidget {
    background-color: #3C3C3C;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 2px;
}
QListWidget::item {
    padding: 5px;
}
QListWidget::item:selected {
    background-color: #0078D7;
    color: white;
}
QTabWidget::pane {
    border: 1px solid #444;
}
QTabBar::tab {
    background: #2E2E2E;
    color: #F0F0F0;
    padding: 8px;
}
QTabBar::tab:selected {
    background: #383838;
}
QMessageBox, QInputDialog {
    background-color: #383838;
}
"""

# --- COMMUNICATION & WORKERS ---
class Communicate(QObject):
    state_changed = pyqtSignal()
    update_key_text = pyqtSignal(str)
    show_countdown = pyqtSignal(int)
    hide_countdown = pyqtSignal()
    countdown_finished = pyqtSignal()

class CountdownWorker(QObject):
    def __init__(self, seconds, comm):
        super().__init__()
        self.seconds = seconds
        self.comm = comm
        self.is_running = True

    def run(self):
        for i in range(self.seconds, 0, -1):
            if not self.is_running: break
            self.comm.show_countdown.emit(i)
            time.sleep(1)
        if self.is_running:
            self.comm.hide_countdown.emit()
            self.comm.countdown_finished.emit()

# --- CLICKER WIDGET --- 
class ClickerWidget(QFrame):
    def __init__(self, title, button, main_window):
        super().__init__()
        self.setObjectName("clickerFrame")
        self.title = title
        self.button = button
        self.main_window = main_window
        self.clicking = False
        self.trigger_key = None
        self.countdown_worker = None

        self.comm = Communicate()
        self.comm.state_changed.connect(self.update_gui_state)
        self.comm.show_countdown.connect(self.main_window.show_countdown)
        self.comm.hide_countdown.connect(self.main_window.hide_countdown)
        self.comm.countdown_finished.connect(self.start_clicking_after_countdown)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        title_label = QLabel(self.title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title_label)

        self.enable_button = QPushButton("Disabled")
        self.enable_button.setCheckable(True)
        self.enable_button.setChecked(False)
        self.enable_button.setStyleSheet("background-color: #4A4A4A;")
        self.enable_button.toggled.connect(self.on_enable_toggled)
        layout.addWidget(self.enable_button)

        self.random_interval_check = QCheckBox("Random Interval")
        self.random_interval_check.toggled.connect(self.toggle_interval_widgets)
        layout.addWidget(self.random_interval_check)

        self.fixed_interval_widget = QWidget()
        fixed_layout = QHBoxLayout(self.fixed_interval_widget)
        fixed_layout.setContentsMargins(0,0,0,0)
        fixed_layout.addWidget(QLabel("Interval (s):"))
        self.interval_entry = QLineEdit("0.1")
        fixed_layout.addWidget(self.interval_entry)
        layout.addWidget(self.fixed_interval_widget)

        self.random_interval_widget = QWidget()
        random_layout = QHBoxLayout(self.random_interval_widget)
        random_layout.setContentsMargins(0,0,0,0)
        random_layout.addWidget(QLabel("Min:"))
        self.min_interval_entry = QLineEdit("0.1")
        random_layout.addWidget(self.min_interval_entry)
        random_layout.addWidget(QLabel("Max:"))
        self.max_interval_entry = QLineEdit("0.5")
        random_layout.addWidget(self.max_interval_entry)
        layout.addWidget(self.random_interval_widget)
        self.random_interval_widget.hide()

        self.clicks_entry = QLineEdit("0")
        layout.addWidget(QLabel("Clicks (0=inf):"))
        layout.addWidget(self.clicks_entry)

        self.set_key_button = QPushButton("Set Trigger Key")
        self.set_key_button.clicked.connect(self.set_trigger_key)
        layout.addWidget(self.set_key_button)

        self.status_label = QLabel("Status: Disabled")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-style: italic; color: grey;")
        layout.addWidget(self.status_label)

        self.comm.update_key_text.connect(self.set_key_button.setText)

    def toggle_interval_widgets(self, checked):
        self.fixed_interval_widget.setVisible(not checked)
        self.random_interval_widget.setVisible(checked)

    def get_trigger_key_str(self):
        if not self.trigger_key: return "Not Set"
        try: return f"'{self.trigger_key.char}'"
        except AttributeError: return str(self.trigger_key).replace("Key.", "")

    def on_enable_toggled(self, checked):
        if checked:
            self.enable_button.setText("Enabled")
            self.enable_button.setStyleSheet("background-color: #4CAF50;")
        else:
            self.enable_button.setText("Disabled")
            self.enable_button.setStyleSheet("background-color: #4A4A4A;")

    def set_trigger_key(self):
        self.set_key_button.setText("Press a key...")
        self.set_key_button.setDisabled(True)
        listener = keyboard.Listener(on_press=self.on_key_press_capture)
        listener.start()

    def on_key_press_capture(self, key):
        self.trigger_key = key
        self.comm.update_key_text.emit(f"Trigger: {self.get_trigger_key_str()}")
        self.set_key_button.setDisabled(False)
        return False

    def start_clicking_after_countdown(self):
        self.clicking = True
        self.update_gui_state()

    def toggle_clicking(self):
        if not self.enable_button.isChecked(): return

        if self.clicking or (self.countdown_worker and self.countdown_worker.is_running):
            if self.countdown_worker: self.countdown_worker.is_running = False
            self.clicking = False
            self.update_gui_state()
            return

        if self.main_window.prefs["countdown_enabled"].isChecked():
            seconds = self.main_window.prefs["countdown_seconds"].value()
            self.countdown_worker = CountdownWorker(seconds, self.comm)
            threading.Thread(target=self.countdown_worker.run, daemon=True).start()
        else:
            self.clicking = True
            self.update_gui_state()

    def update_gui_state(self):
        if self.main_window.prefs["sounds_enabled"].isChecked():
            sound_thread = threading.Thread(target=lambda: winsound.MessageBeep(winsound.MB_OK if self.clicking else winsound.MB_ICONASTERISK), daemon=True)
            sound_thread.start()
        
        self.main_window.update_on_screen_display()
        if self.clicking:
            self.status_label.setText("Status: Running")
            self.status_label.setStyleSheet("font-style: italic; color: #4CAF50;")
            click_thread = threading.Thread(target=self.click_worker, daemon=True)
            click_thread.start()
        else:
            self.status_label.setText("Status: Stopped")
            self.status_label.setStyleSheet("font-style: italic; color: red;")

    def click_worker(self):
        try:
            num_clicks = int(self.clicks_entry.text())
            is_random = self.random_interval_check.isChecked()
            if is_random:
                min_delay = float(self.min_interval_entry.text())
                max_delay = float(self.max_interval_entry.text())
            else:
                interval = float(self.interval_entry.text())
        except ValueError:
            self.status_label.setText("Status: Invalid input"); self.clicking = False; return

        clicks_done = 0
        while self.clicking:
            if 0 < num_clicks <= clicks_done: break
            self.main_window.mouse_controller.click(self.button)
            clicks_done += 1
            delay = random.uniform(min_delay, max_delay) if is_random else interval
            time.sleep(delay)
        
        if self.clicking:
            self.clicking = False
            self.comm.state_changed.emit()

# --- MAIN WINDOW --- 
class AutoClickerProQT(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("mainWindow")
        self.mouse_controller = mouse.Controller()
        self.profiles = {}
        self.profile_file = "profiles.json"
        self.prefs = {}
        self.init_ui()
        self.init_listeners()
        self.load_profiles()

    def init_ui(self):
        self.setWindowTitle("Autoclicker")
        # self.setStyleSheet(STYLESHEET) # Style is now applied globally

        # System Tray Icon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("Autoclicker Pro")
        icon_path = resource_path("mouse_icon_138363.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)
            self.tray_icon.setIcon(icon)
        else:
            print(f"Icon not found at {icon_path}, using default.")
            try:
                icon = QIcon(self.style().standardIcon(getattr(self.style(), 'SP_DesktopIcon')))
                self.setWindowIcon(icon)
                self.tray_icon.setIcon(icon)
            except AttributeError:
                print("Standard icons not found, using default.")
        
        tray_menu = QMenu(); show_action = QAction("Show", self); quit_action = QAction("Quit", self)
        show_action.triggered.connect(self.show); quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(show_action); tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        main_layout = QHBoxLayout(self)

        # Profile Panel
        profile_panel = QFrame(); profile_panel.setObjectName("profileFrame")
        profile_layout = QVBoxLayout(profile_panel)
        profile_layout.addWidget(QLabel("Profiles"))
        self.profile_list = QListWidget(); self.profile_list.currentItemChanged.connect(self.load_selected_profile)
        profile_layout.addWidget(self.profile_list)
        profile_button_layout = QHBoxLayout()
        new_profile_btn = QPushButton("New"); new_profile_btn.clicked.connect(self.new_profile)
        profile_button_layout.addWidget(new_profile_btn)
        save_profile_btn = QPushButton("Save"); save_profile_btn.clicked.connect(self.save_profile)
        profile_button_layout.addWidget(save_profile_btn)
        delete_profile_btn = QPushButton("Delete"); delete_profile_btn.clicked.connect(self.delete_profile)
        profile_button_layout.addWidget(delete_profile_btn)
        profile_layout.addLayout(profile_button_layout)
        main_layout.addWidget(profile_panel)

        # Tabs
        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # Clickers Tab
        clickers_tab = QWidget()
        right_layout = QVBoxLayout(clickers_tab)
        clickers_layout = QHBoxLayout()
        self.left_frame = ClickerWidget("Left Clicker", mouse.Button.left, self)
        clickers_layout.addWidget(self.left_frame)
        line = QFrame(); line.setFrameShape(QFrame.Shape.VLine); line.setFrameShadow(QFrame.Shadow.Sunken)
        clickers_layout.addWidget(line)
        self.right_frame = ClickerWidget("Right Clicker", mouse.Button.right, self)
        clickers_layout.addWidget(self.right_frame)
        right_layout.addLayout(clickers_layout)
        tabs.addTab(clickers_tab, "Clickers")

        # Preferences Tab
        prefs_tab = QWidget()
        prefs_layout = QVBoxLayout(prefs_tab)
        self.prefs["show_notification"] = QCheckBox("Show On-Screen Notification"); self.prefs["show_notification"].setChecked(True)
        prefs_layout.addWidget(self.prefs["show_notification"], alignment=Qt.AlignmentFlag.AlignLeft)
        self.prefs["sounds_enabled"] = QCheckBox("Enable Start/Stop Sounds"); self.prefs["sounds_enabled"].setChecked(True)
        prefs_layout.addWidget(self.prefs["sounds_enabled"], alignment=Qt.AlignmentFlag.AlignLeft)
        
        countdown_layout = QHBoxLayout()
        self.prefs["countdown_enabled"] = QCheckBox("Enable Start Countdown"); self.prefs["countdown_enabled"].setChecked(False)
        countdown_layout.addWidget(self.prefs["countdown_enabled"])
        self.prefs["countdown_seconds"] = QSpinBox(); self.prefs["countdown_seconds"].setRange(1, 60); self.prefs["countdown_seconds"].setValue(3)
        countdown_layout.addWidget(self.prefs["countdown_seconds"])
        countdown_layout.addWidget(QLabel("seconds"))
        prefs_layout.addLayout(countdown_layout)

        self.prefs["ask_on_close"] = QCheckBox("Ask what to do when closing window"); self.prefs["ask_on_close"].setChecked(True)
        prefs_layout.addWidget(self.prefs["ask_on_close"], alignment=Qt.AlignmentFlag.AlignLeft)

        prefs_layout.addStretch()
        tabs.addTab(prefs_tab, "Preferences")

        # Instructions Tab
        instructions_tab = QWidget()
        instructions_layout = QVBoxLayout(instructions_tab)
        instructions_text = '''
        <b>Instructions</b>
        <p>This autoclicker was created by yankivare cehovar.</p>
        <p>You can find the source code on <a href="https://github.com/yankivare-cehovar" style="color: #0078D7;">GitHub</a>.</p>
        <br/>
        <b>How to Use:</b>
        <ol>
            <li><b>Enable:</b> First, enable the left or right clicker using the "Enabled/Disabled" button.</li>
            <li><b>Set Trigger Key:</b> Click "Set Trigger Key" and press any key on your keyboard to assign it as the start/stop trigger for that clicker.</li>
            <li><b>Interval:</b>
                <ul>
                    <li><b>Fixed:</b> Uncheck "Random Interval" and set a fixed interval in seconds between each click.</li>
                    <li><b>Random:</b> Check "Random Interval" and provide a minimum and maximum delay in seconds.</li>
                </ul>
            </li>
            <li><b>Number of Clicks:</b> Set the number of clicks to perform. Use <code>0</code> for infinite clicks.</li>
            <li><b>Start/Stop:</b> Press the assigned trigger key to start or stop clicking.</li>
            <li><b>Profiles:</b> You can save and load your settings as profiles on the left panel.</li>
            <li><b>Preferences:</b> Customize countdown timers, sounds, and closing behavior in the "Preferences" tab.</li>
        </ol>
        <br/>
        <b>Important:</b> The application will minimize to the system tray when you close the window (this can be changed in Preferences). Right-click the tray icon to show the window or quit the application.
        '''
        instructions_label = QLabel(instructions_text)
        instructions_label.setWordWrap(True)
        instructions_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        instructions_label.setStyleSheet("padding: 10px;") # Add some padding
        instructions_label.setOpenExternalLinks(True)
        instructions_layout.addWidget(instructions_label)
        tabs.addTab(instructions_tab, "Instructions")

        # Status & Countdown Windows
        self.status_window = QWidget(); self.status_window.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool); self.status_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        status_layout = QVBoxLayout(self.status_window); self.status_window.setLayout(status_layout)
        self.left_status_label = QLabel(""); self.left_status_label.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 2px;")
        status_layout.addWidget(self.left_status_label)
        self.right_status_label = QLabel(""); self.right_status_label.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 2px;")
        status_layout.addWidget(self.right_status_label)
        self.countdown_label = QLabel(""); self.countdown_label.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool); self.countdown_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.countdown_label.setStyleSheet("background-color: rgba(0,0,0,180); color: white; font-weight: bold; font-size: 48pt; padding: 20px; border-radius: 10px;")

    def key_to_str(self, key):
        if key is None: return None
        if isinstance(key, keyboard.Key): return key.name
        if isinstance(key, keyboard.KeyCode): return key.char
        return None

    def str_to_key(self, key_str):
        if key_str is None: return None
        try: return keyboard.Key[key_str]
        except KeyError: return keyboard.KeyCode.from_char(key_str.replace("'",""))

    def get_current_settings(self, is_template=False):
        def get_widget_settings(widget):
            s = {"enabled": False, "trigger_key": None, "is_random": False, "interval": "0.1", "min_interval": "0.1", "max_interval": "0.5", "num_clicks": "0"}
            if not is_template:
                s.update({"enabled": widget.enable_button.isChecked(), "trigger_key": self.key_to_str(widget.trigger_key), "is_random": widget.random_interval_check.isChecked(), "interval": widget.interval_entry.text(), "min_interval": widget.min_interval_entry.text(), "max_interval": widget.max_interval_entry.text(), "num_clicks": widget.clicks_entry.text()})
            return s
        prefs = {key: w.isChecked() for key, w in self.prefs.items() if isinstance(w, QCheckBox)}
        prefs["countdown_seconds"] = self.prefs["countdown_seconds"].value()
        return {"left": get_widget_settings(self.left_frame), "right": get_widget_settings(self.right_frame), "prefs": prefs}

    def load_settings_to_ui(self, settings):
        def set_widget_settings(widget, s): # ...
            widget.enable_button.setChecked(s["enabled"])
            widget.trigger_key = self.str_to_key(s.get("trigger_key"))
            widget.set_key_button.setText(f"Trigger: {widget.get_trigger_key_str()}")
            widget.random_interval_check.setChecked(s["is_random"])
            widget.interval_entry.setText(s["interval"])
            widget.min_interval_entry.setText(s["min_interval"])
            widget.max_interval_entry.setText(s["max_interval"])
            widget.clicks_entry.setText(s["num_clicks"])
        set_widget_settings(self.left_frame, settings["left"])
        set_widget_settings(self.right_frame, settings["right"])
        if "prefs" in settings:
            for key, w in self.prefs.items():
                if isinstance(w, QCheckBox): w.setChecked(settings["prefs"].get(key, True))
                if isinstance(w, QSpinBox): w.setValue(settings["prefs"].get(key, 3))

    def load_profiles(self):
        if os.path.exists(self.profile_file):
            with open(self.profile_file, 'r') as f: self.profiles = json.load(f)
        else: self.profiles = {"Default": self.get_current_settings(is_template=True)}
        self.profile_list.clear(); self.profile_list.addItems(self.profiles.keys())
        if self.profile_list.count() > 0: self.profile_list.setCurrentRow(0)

    def save_profiles(self): # ...
        with open(self.profile_file, 'w') as f: json.dump(self.profiles, f, indent=4)

    def new_profile(self): # ...
        name, ok = QInputDialog.getText(self, "New Profile", "Enter profile name:")
        if ok and name and name not in self.profiles:
            self.profiles[name] = self.get_current_settings(is_template=True)
            self.profile_list.addItem(name); self.profile_list.setCurrentRow(self.profile_list.count() - 1); self.save_profiles()

    def save_profile(self): # ...
        current_item = self.profile_list.currentItem()
        if not current_item: return
        name = current_item.text()
        self.profiles[name] = self.get_current_settings()
        self.save_profiles(); QMessageBox.information(self, "Success", f"Profile '{name}' saved.")

    def delete_profile(self): # ...
        current_item = self.profile_list.currentItem()
        if not current_item or self.profile_list.count() <= 1: return
        name = current_item.text()
        if QMessageBox.question(self, "Delete Profile", f"Are you sure you want to delete '{name}'?") == QMessageBox.StandardButton.Yes:
            del self.profiles[name]; self.profile_list.takeItem(self.profile_list.row(current_item)); self.save_profiles()

    def load_selected_profile(self, current, previous):
        if current: self.load_settings_to_ui(self.profiles[current.text()])

    def update_on_screen_display(self):
        if not self.prefs["show_notification"].isChecked(): self.status_window.hide(); return
        left_on, right_on = self.left_frame.clicking, self.right_frame.clicking
        if left_on: self.left_status_label.setText(f"Left Clicker ON ({self.left_frame.get_trigger_key_str()})")
        self.left_status_label.setVisible(left_on)
        if right_on: self.right_status_label.setText(f"Right Clicker ON ({self.right_frame.get_trigger_key_str()})")
        self.right_status_label.setVisible(right_on)
        if left_on or right_on: self.status_window.adjustSize(); self.status_window.move(10, 10); self.status_window.show()
        else: self.status_window.hide()

    def show_countdown(self, num):
        self.countdown_label.setText(str(num)); self.countdown_label.adjustSize(); self.countdown_label.show()

    def hide_countdown(self):
        self.countdown_label.hide()

    def init_listeners(self):
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press); self.keyboard_listener.daemon = True; self.keyboard_listener.start()

    def on_press(self, key):
        if self.left_frame.trigger_key is not None and key == self.left_frame.trigger_key: self.left_frame.toggle_clicking()
        if self.right_frame.trigger_key is not None and key == self.right_frame.trigger_key: self.right_frame.toggle_clicking()

    def closeEvent(self, event):
        # Save current profile before closing
        current_item = self.profile_list.currentItem()
        if current_item:
            self.profiles[current_item.text()] = self.get_current_settings()
            self.save_profiles()

        if self.prefs["ask_on_close"].isChecked():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Exit Autoclicker Pro")
            msg_box.setText("What would you like to do?")
            msg_box.setIcon(QMessageBox.Icon.Question)
            minimize_button = msg_box.addButton("Minimize to Tray", QMessageBox.ButtonRole.ActionRole)
            exit_button = msg_box.addButton("Exit Application", QMessageBox.ButtonRole.ActionRole)
            cancel_button = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()

            if msg_box.clickedButton() == minimize_button:
                self.hide()
                event.ignore()
            elif msg_box.clickedButton() == exit_button:
                self.quit_app()
            else:
                event.ignore()
        else:
            self.hide()
            event.ignore()

    def quit_app(self):
        self.tray_icon.hide(); QApplication.instance().quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    ex = AutoClickerProQT()
    ex.show()
    sys.exit(app.exec())
