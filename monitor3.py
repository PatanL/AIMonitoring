import sys
import mss
import time
import threading
import rumps
from PyQt6.QtWidgets import QDialog, QApplication, QMainWindow, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QLabel, QSpinBox, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QObject
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PIL import Image
import io
import os
import base64
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DistractionPopup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setModal(False)
        layout = QVBoxLayout()
        message = QLabel("You seem distracted! Focus on your work!")
        message.setStyleSheet("font-size: 18px; color: red;")
        layout.addWidget(message)
        self.setLayout(layout)
        self.setGeometry(100, 100, 300, 100)

class ScreenCaptureThread(QThread):
    captured = pyqtSignal(QImage)

    def __init__(self, interval=30):
        super().__init__()
        self.interval = interval
        self.debug_dir = "debug_images"
        self.running = True
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)

    def run(self):
        with mss.mss() as sct:
            while self.running:
                monitor = sct.monitors[0]
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                image_path = os.path.join(self.debug_dir, "capture_latest.png")
                img.save(image_path, "PNG")

                qimage = QImage(img.tobytes(), img.width, img.height, QImage.Format.Format_RGB888)
                self.captured.emit(qimage)
                for _ in range(int(self.interval * 10)):  # Check every 100ms if we should stop
                    if not self.running:
                        return
                    time.sleep(0.1)

    def stop(self):
        self.running = False


class DistractionAnalyzer(QObject):
    analysis_complete = pyqtSignal(bool)
    def __init__(self):
        super().__init__()

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    def ask_llava(self, prompt, image_path):
        base64_image = self.encode_image(image_path)
        
        response = requests.post('http://localhost:11434/api/generate',
            json={
                'model': 'llava',
                'prompt': prompt,
                'images': [base64_image],
                'stream': False,
                'options': {
                    'temperature': 0
                }
            })
        
        if response.status_code == 200:
            return response.json()['response']
        else:
            return f"Error: {response.status_code}, {response.text}"

    def analyze(self, qimage):
        image_path = os.path.join(os.getcwd(), "debug_images", "capture_latest.png")
        question = "Is this person coding in this image? Reply with one word: 'Yes' or 'No'"

        try:
            answer = self.ask_llava(question, image_path)
            print(f"LLaVA response: {answer}")
            is_distracted = answer.strip().lower() == "no"
            self.analysis_complete.emit(is_distracted)
        except Exception as e:
            print(f"Error in LLaVA analysis: {e}")
            self.analysis_complete.emit(False)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Distraction Monitor")
        self.setGeometry(100, 100, 300, 200)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Interval setting
        interval_layout = QHBoxLayout()
        interval_label = QLabel("Capture Interval (seconds):")
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(5, 3600)
        self.interval_spinbox.setValue(30)
        interval_layout.addWidget(interval_label)
        interval_layout.addWidget(self.interval_spinbox)
        layout.addLayout(interval_layout)

        self.start_button = QPushButton("Start Monitoring")
        self.start_button.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.start_button)

        self.image_label = QLabel()
        layout.addWidget(self.image_label)

        self.status_label = QLabel("Status: Not monitoring")
        layout.addWidget(self.status_label)

        self.capture_thread = None
        self.analyzer = DistractionAnalyzer()
        self.analyzer.analysis_complete.connect(self.handle_analysis_result)

        # Initialize the rumps notification app
        # self.notification_app = NotificationApp()
        # self.notification_thread = threading.Thread(target=self.notification_app.run)
        # self.notification_thread.start()
        # Remove the rumps notification app initialization
        # Instead, initialize QSystemTrayIcon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("/Users/patrickliu/Desktop/Startups/AIMonitoring/debug_images/image.png"))  # Replace with your icon path
        self.tray_menu = QMenu()
        self.tray_menu.addAction("Exit", self.close)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        self.distraction_popup = None


    def toggle_monitoring(self):
        if self.start_button.text() == "Start Monitoring":
            interval = self.interval_spinbox.value()
            self.capture_thread = ScreenCaptureThread(interval)
            self.capture_thread.captured.connect(self.process_capture)
            self.capture_thread.start()
            self.start_button.setText("Stop Monitoring")
            self.status_label.setText(f"Status: Monitoring (Interval: {interval}s)")
            self.interval_spinbox.setEnabled(False)
        else:
            self.start_button.setEnabled(False)
            self.status_label.setText("Status: Stopping monitoring...")
            QTimer.singleShot(100, self.stop_monitoring)

    def stop_monitoring(self):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait(2000)  # Wait for up to 2 seconds
            if self.capture_thread.isRunning():
                self.capture_thread.terminate()  # Force termination if thread doesn't stop
            self.capture_thread = None
        self.start_button.setText("Start Monitoring")
        self.status_label.setText("Status: Not monitoring")
        self.interval_spinbox.setEnabled(True)
        self.start_button.setEnabled(True)

    def process_capture(self, qimage):
        scaled_pixmap = QPixmap.fromImage(qimage).scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatio)
        self.image_label.setPixmap(scaled_pixmap)
        QTimer.singleShot(0, lambda: self.analyzer.analyze(qimage))

    def handle_analysis_result(self, is_distracted):
        if is_distracted:
            print("You seem distracted!")
            self.show_notification("Distraction Alert", "You seem to be distracted. Focus on your work!")
            self.show_distraction_popup()

    def show_notification(self, title, message):
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def show_distraction_popup(self):
        if not self.distraction_popup:
            self.distraction_popup = DistractionPopup(self)
        self.distraction_popup.show()
        # Optionally, set a timer to hide the popup after a certain duration
        QTimer.singleShot(10000, self.hide_distraction_popup)  # Hide after 10 seconds
    def hide_distraction_popup(self):
        if self.distraction_popup:
            self.distraction_popup.hide()

    def closeEvent(self, event):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
                                     