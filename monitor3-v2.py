import sys
import mss
import time
import random
from PyQt6.QtWidgets import QDialog, QApplication, QMainWindow, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QLabel, QSpinBox, QLineEdit, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QRectF
from PyQt6.QtGui import QPixmap, QImage, QIcon, QColor, QPainter, QPainterPath, QPen
from PIL import Image
import os
import base64
import requests
from dotenv import load_dotenv
from gtts import gTTS
from playsound import playsound
import datetime
import json
from datetime import timedelta
import os

# Load environment variables
load_dotenv()

class StatsTracker:
    def __init__(self, filename='distraction_stats.json'):
        self.filename = filename
        self.stats = self.load_stats()

    def load_stats(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                return json.load(f)
        return {}

    def save_stats(self):
        with open(self.filename, 'w') as f:
            json.dump(self.stats, f, indent=2)

    def update_stats(self, is_distracted, interval):
        now = datetime.datetime.now()
        date_key = now.strftime('%Y-%m-%d')
        hour_key = now.strftime('%Y-%m-%d %H:00')

        if date_key not in self.stats:
            self.stats[date_key] = {'distractions': 0, 'checks': 0, 'total_time': 0}
        if hour_key not in self.stats:
            self.stats[hour_key] = {'distractions': 0, 'checks': 0, 'total_time': 0}

        self.stats[date_key]['checks'] += 1
        self.stats[date_key]['total_time'] += interval
        self.stats[hour_key]['checks'] += 1
        self.stats[hour_key]['total_time'] += interval

        if is_distracted:
            self.stats[date_key]['distractions'] += 1
            self.stats[hour_key]['distractions'] += 1

        self.save_stats()

    def get_summary(self):
        summary = "Distraction Statistics:\n"
        for key, data in self.stats.items():
            if ' ' in key:  # Hourly stats
                summary += f"\nHour: {key}\n"
            else:  # Daily stats
                summary += f"\nDate: {key}\n"
            
            total_checks = data['checks']
            if total_checks > 0:
                distraction_percentage = (data['distractions'] / total_checks) * 100
                total_time = timedelta(seconds=data['total_time'])
                summary += f"  Distractions: {data['distractions']}\n"
                summary += f"  Percentage Distracted: {distraction_percentage:.2f}%\n"
                summary += f"  Total Time: {total_time}\n"
        return summary

class DistractionPopup(QDialog):
    def __init__(self, message, parent=None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(False)
        self.resize(400, 200)
        self.setStyleSheet("""
            QLabel {
                color: #FFF5E6;
                font-size: 20px;
                font-family: 'Helvetica Neue', sans-serif;
                font-weight: 300;
            }
        """)

        layout = QVBoxLayout()
        self.messageLabel = QLabel(message)
        self.messageLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.messageLabel.setWordWrap(True)
        layout.addWidget(self.messageLabel)
        self.setLayout(layout)
        self.center_on_screen()

    def center_on_screen(self):
        screen_geometry = QApplication.primaryScreen().geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 3
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(255, 103, 0, 200))  # Soft orange color
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawPath(path)

    def resizeEvent(self, event):
        self.center_on_screen()
        super().resizeEvent(event)

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
        self.wait(5000)  # Wait for up to 2 seconds for the thread to finish

class DistractionAnalyzer(QThread):
    analysis_complete = pyqtSignal(bool)

    def __init__(self, possible_activities=None, blacklisted_words=None):
        super().__init__()
        self.possible_activities = possible_activities or []
        self.blacklisted_words = blacklisted_words or []
        self.image_path = None

    def set_image(self, image_path):
        self.image_path = image_path

    def run(self):
        if self.image_path is not None:
            options = ", ".join(self.possible_activities)
            question = f"Describe what this person in this image is doing briefly (5 words max) from these options: {options}"
            try:
                answer = self.ask_llava(question, self.image_path)
                print(f"LLaVA response: {answer}")

                is_distracted = self.check_distraction(answer)
                self.analysis_complete.emit(is_distracted)
            except Exception as e:
                print(f"Error in LLaVA analysis: {e}")
                self.analysis_complete.emit(False)
    
    def check_distraction(self, activity):
        activity = activity.lower()
        for blacklisted in self.blacklisted_words:
            if blacklisted.lower() in activity:
                return True
        return False

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

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

class AudioThread(QThread):
    def __init__(self, text="", audio_path="Radar.mp3"):
        super().__init__()
        self.text = text
        self.audio_path = audio_path

    def run(self):
        if self.text != "":
            # tts = gTTS(text=self.text, lang='en')
            # tts.save("distraction_alert.mp3")
            playsound("distraction_alert.mp3")
            # os.remove("distraction_alert.mp3")  # Clean up the audio file
        else:
            playsound(self.audio_path)

class ReflectionDialog(QDialog):
    refocus_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(False)
        self.resize(450, 280)
        self.setStyleSheet("""
            QLabel, QLineEdit, QPushButton {
                color: #FFF5E6;
                font-size: 20px;
                font-family: 'Helvetica Neue', sans-serif;
                font-weight: 300;
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 20);
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 50);
                padding: 8px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
            }
        """)

        layout = QVBoxLayout()
        
        reflection_label = QLabel("What caused the distraction?")
        reflection_label.setWordWrap(True)
        reflection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(reflection_label)

        self.reflection_input = QLineEdit()
        self.reflection_input.setPlaceholderText("Reflect on your distraction...")
        layout.addWidget(self.reflection_input)

        confirm_button = QPushButton("Refocus")
        confirm_button.clicked.connect(self.on_refocus_clicked)
        layout.addWidget(confirm_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)
        self.center_on_screen()

    def center_on_screen(self):
        screen_geometry = QApplication.primaryScreen().geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) * 2 // 3
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(230, 90, 90, 200))  # Soft red color
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawPath(path)

    def resizeEvent(self, event):
        self.center_on_screen()
        super().resizeEvent(event)

    def on_refocus_clicked(self):
        self.refocus_clicked.emit()
        self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Distraction Monitor")
        self.setGeometry(100, 100, 600, 200)

        self.load_config()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Interval setting
        interval_layout = QHBoxLayout()
        interval_label = QLabel("Capture Interval (seconds):")
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(5, 3600)
        self.interval_spinbox.setValue(self.config['capture_interval'])
        self.interval_spinbox.valueChanged.connect(self.save_config)
        interval_layout.addWidget(interval_label)
        interval_layout.addWidget(self.interval_spinbox)
        layout.addLayout(interval_layout)

        # Possible activities input
        possible_layout = QHBoxLayout()
        possible_label = QLabel("Possible Activities:")
        self.possible_input = QLineEdit()
        self.possible_input.setText(", ".join(self.config['possible_activities']))
        self.possible_input.textChanged.connect(self.save_config)
        possible_layout.addWidget(possible_label)
        possible_layout.addWidget(self.possible_input)
        layout.addLayout(possible_layout)

        # Blacklisted activities input
        blacklisted_layout = QHBoxLayout()
        blacklisted_label = QLabel("Blacklisted Activities:")
        self.blacklisted_input = QLineEdit()
        self.blacklisted_input.setText(", ".join(self.config['blacklisted_words']))
        self.blacklisted_input.textChanged.connect(self.save_config)
        blacklisted_layout.addWidget(blacklisted_label)
        blacklisted_layout.addWidget(self.blacklisted_input)
        layout.addLayout(blacklisted_layout)

        self.start_button = QPushButton("Start Monitoring")
        self.start_button.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.start_button)

        self.image_label = QLabel()
        layout.addWidget(self.image_label)

        # Separate status labels
        self.monitoring_status_label = QLabel("Status: Not monitoring")
        layout.addWidget(self.monitoring_status_label)


        self.capture_thread = None
        self.analyzer = DistractionAnalyzer()  # Initialize without starting the thread yet
        # self.task_locked = False

        # Initialize the notification app
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("debug_images/image.png"))  # Replace with your icon path
        self.tray_menu = QMenu()
        self.tray_menu.addAction("Exit", self.close)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        self.distraction_popup = None
        self.reflection_popup = None

        self.last_distraction_time = datetime.datetime.now()  # Track the last time a distraction was detected
        self.last_praise_time = None  # Track the last time praise was given
        self.last_praise_time2 = datetime.datetime.now()  # Track the last time praise was given

        self.stats_tracker = StatsTracker()
        
        # Add a button to show statistics
        self.show_stats_button = QPushButton("Show Statistics")
        self.show_stats_button.clicked.connect(self.show_statistics)
        layout.addWidget(self.show_stats_button)

    def load_config(self):
        try:
            with open('config.json', 'r') as config_file:
                self.config = json.load(config_file)
        except FileNotFoundError:
            print("Configuration file not found. Using default settings.")
            self.config = {
                "capture_interval": 30,
                "possible_activities": ["being productive", "coding", "writing", "learning", "social media", "gaming", "watching livestream"],
                "blacklisted_words": ["social media", "gaming", "stream"],
                "notification_sound": "Radar.mp3",
                "positive_reinforcement_interval": 1800,
                "positive_reinforcement_chance": 0.3
            }

    def save_config(self):
        self.config['capture_interval'] = self.interval_spinbox.value()
        self.config['possible_activities'] = [a.strip() for a in self.possible_input.text().split(',') if a.strip()]
        self.config['blacklisted_words'] = [a.strip() for a in self.blacklisted_input.text().split(',') if a.strip()]
        
        with open('config.json', 'w') as config_file:
            json.dump(self.config, config_file, indent=4)
                      
    def toggle_monitoring(self):
        if self.start_button.text() == "Start Monitoring":
            possible_activities = [a.strip() for a in self.possible_input.text().split(',') if a.strip()]
            blacklisted_words = [a.strip() for a in self.blacklisted_input.text().split(',') if a.strip()]

            if not possible_activities:
                possible_activities = self.config['possible_activities']
                self.possible_input.setText(", ".join(possible_activities))
            
            if not blacklisted_words:
                blacklisted_words = self.config['blacklisted_words']
                self.blacklisted_input.setText(", ".join(blacklisted_words))

            interval = self.interval_spinbox.value()
            self.analyzer = DistractionAnalyzer(possible_activities, blacklisted_words)
            self.analyzer.analysis_complete.connect(self.handle_analysis_result)

            self.capture_thread = ScreenCaptureThread(interval)
            self.capture_thread.captured.connect(self.process_capture)
            self.capture_thread.start()

            self.start_button.setText("Stop Monitoring")
            self.monitoring_status_label.setText(f"Status: Monitoring (Interval: {interval}s)")
            self.interval_spinbox.setEnabled(False)
            self.possible_input.setEnabled(False)
            self.blacklisted_input.setEnabled(False)
        else:
            self.start_button.setEnabled(False)
            self.monitoring_status_label.setText("Status: Stopping monitoring...")
            QTimer.singleShot(100, self.stop_monitoring)

    def stop_monitoring(self):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread = None
        
        if self.analyzer and self.analyzer.isRunning():
            self.analyzer.quit()
            self.analyzer.wait()

        self.start_button.setText("Start Monitoring")
        self.monitoring_status_label.setText("Status: Not monitoring")
        self.interval_spinbox.setEnabled(True)
        self.possible_input.setEnabled(True)
        self.blacklisted_input.setEnabled(True)
        self.start_button.setEnabled(True)

    def process_capture(self, qimage):
        scaled_pixmap = QPixmap.fromImage(qimage).scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatio)
        self.image_label.setPixmap(scaled_pixmap)
        # Save the QImage to a file, since the analyzer works with file paths
        image_path = os.path.join("debug_images", "capture_latest.png")
        qimage.save(image_path)

        # Set the image path in the analyzer
        self.analyzer.set_image(image_path)

        # Start the analysis in a separate thread
        self.analyzer.start()  # This will call the `run` method in the DistractionAnalyzer

    def handle_analysis_result(self, is_distracted):
        current_time = datetime.datetime.now()
        interval = self.interval_spinbox.value()
        self.stats_tracker.update_stats(is_distracted, interval)

        if is_distracted:
            print("You seem distracted!")
            self.last_distraction_time = current_time
            self.show_notification("Distraction Alert", "You seem to be distracted. Focus on your work!")

            message = "You seem distracted! Get back to work!"

            
            self.show_distraction_popup(message)
            self.play_audio_alert(message)

            if not self.reflection_popup:
                self.reflection_popup = ReflectionDialog()
                self.reflection_popup.refocus_clicked.connect(self.hide_distraction_popup)
            if self.reflection_popup.exec():
                print(f"User reflection: {self.reflection_popup.reflection_input.text()}")
                self.show_notification("Great!", "Let's get back to work!")
        else:
            if (current_time - self.last_distraction_time).total_seconds() > self.config['positive_reinforcement_interval']:
                if not self.last_praise_time or (current_time - self.last_praise_time).total_seconds() > self.config['positive_reinforcement_interval']:
                    # print(current_time)
                    # if random.random() < self.config['positive_reinforcement_chance']:  
                    #     self.give_positive_reinforcement()
                    #     self.last_praise_time = current_time 
                    
                    if current_time.hour >= 20:
                        if not self.last_praise_time2 or (current_time - self.last_praise_time2).total_seconds() > 1800:
                            if random.random() < 1/8:
                                self.praise_audio_thread2 = AudioThread(audio_path="bladerunner.m4a")
                                self.praise_audio_thread2.start()
                                self.last_praise_time2 = current_time

    def give_positive_reinforcement(self):
        # TODO: make this better
        praise_messages = [
            "Great job staying focused! Keep it up!",
            "You're doing amazing work. Stay on track!",
            "Impressive focus! Keep pushing forward!",
            "You're a productivity master! Keep going!",
            "Your dedication is paying off. Well done!"
        ]
        praise_message = random.choice(praise_messages)
        print("Positive Reinforcement: " + praise_message)

        self.show_notification("Well Done!", praise_message)
        self.praise_audio_thread = AudioThread(text=praise_message)
        self.praise_audio_thread.start()


        self.interval_spinbox.setEnabled(False)
    
    def play_audio_alert(self, message):
        self.audio_thread = AudioThread(text=message)
        self.audio_thread2 = AudioThread(audio_path=self.config['notification_sound'])
        self.audio_thread.start()
        self.audio_thread2.start()

    def show_notification(self, title, message):
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def show_distraction_popup(self, message = "Focus on your work!"):
        self.distraction_popup = DistractionPopup(message)
        self.distraction_popup.show()

    def hide_distraction_popup(self):
        if self.distraction_popup:
            self.distraction_popup.hide()

    def show_statistics(self):
        stats_summary = self.stats_tracker.get_summary()
        QMessageBox.information(self, "Distraction Statistics", stats_summary)

    def closeEvent(self, event):
        # Stop monitoring threads
        self.stop_monitoring()

        # Close and delete any open dialogs
        if self.distraction_popup:
            self.distraction_popup.close()
            self.distraction_popup.deleteLater()
        if self.reflection_popup:
            self.reflection_popup.close()
            self.reflection_popup.deleteLater()

        # Clean up the tray icon
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()

        # Clean up any remaining QTimers
        for child in self.findChildren(QTimer):
            child.stop()

        # Ensure all threads are stopped and deleted
        for child in self.findChildren(QThread):
            if child.isRunning():
                child.quit()
                child.wait()
            child.deleteLater()

        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())