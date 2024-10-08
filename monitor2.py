import sys
import mss
import time
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QLabel, QSpinBox
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QObject
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
import io
import os
import base64
import requests
from dotenv import load_dotenv
# from plyer import notification
import subprocess

# Load environment variables
load_dotenv()

class ScreenCaptureThread(QThread):
    # captured = pyqtSignal(QPixmap)
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
                # pixmap = QPixmap.fromImage(qimage)

                # self.captured.emit(pixmap)
                # time.sleep(self.interval)
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
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not found in environment variables")

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def analyze(self, qimage):
        image_path = os.path.join(os.getcwd(), "debug_images", "capture_latest.png")
        # image_path = "/Users/patrickliu/Desktop/Startups/AI Accountability Partner/debug_images/image.png"
        base64_image = self.encode_image(image_path)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # prompt = "Is this screen of a person coding? If yes reply with 'yes', if no reply with 'no'"
        prompt = "Describe this image"

        payload = {
            "model": "gpt-4o-2024-08-06",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }

        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            response_json = response.json()
            print(response_json)
            # result = "no" in response_json['choices'][0]['message']['content'].lower()
            result = True
            self.analysis_complete.emit(result)
        except requests.RequestException as e:
            print(f"Error in API request: {e}")
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

    #     self.capture_thread = ScreenCaptureThread()
    #     self.capture_thread.captured.connect(self.process_capture)
    #     self.analyzer = DistractionAnalyzer()

    # def toggle_monitoring(self):
    #     if self.start_button.text() == "Start Monitoring":
    #         interval = self.interval_spinbox.value()
    #         self.capture_thread.interval = interval
    #         self.capture_thread.start()
    #         self.start_button.setText("Stop Monitoring")
    #         self.status_label.setText(f"Status: Monitoring (Interval: {interval}s)")
    #         self.interval_spinbox.setEnabled(False)
    #     else:
    #         self.capture_thread.stop()
    #         self.capture_thread.wait()
    #         self.start_button.setText("Start Monitoring")
    #         self.status_label.setText("Status: Not monitoring")
    #         self.interval_spinbox.setEnabled(True)

    # def process_capture(self, pixmap):
    #     scaled_pixmap = pixmap.scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatio)
    #     self.image_label.setPixmap(scaled_pixmap)
        
    #     if self.analyzer.analyze():
    #         print("You seem distracted!")
    #         # Implement notification logic here
    #         # notification.notify(
    #         #     title='Distraction Alert',
    #         #     message='You seem to be distracted. Focus on your work!',
    #         #     app_icon=None,  # e.g. 'path/to/icon.png'
    #         #     timeout=10,  # seconds
    #         # )
    #         self.show_notification("Distraction Alert", "You seem to be distracted. Focus on your work!")
        self.capture_thread = None
        self.analyzer = DistractionAnalyzer()
        self.analyzer.analysis_complete.connect(self.handle_analysis_result)

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
            self.capture_thread.wait(2000)  # Wait for up to 5 seconds
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
    def show_notification(self, title, message):
        apple_script_command = f'''
        display notification "{message}" with title "{title}"
        '''
        subprocess.run(["osascript", "-e", apple_script_command])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    