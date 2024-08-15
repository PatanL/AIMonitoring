import sys
import mss
import time
import random
import threading
import rumps
from PyQt6.QtWidgets import QDialog, QApplication, QMainWindow, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QLabel, QSpinBox, QLineEdit, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QObject
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PIL import Image
import io
import os
import base64
import requests
from dotenv import load_dotenv
from gtts import gTTS
from playsound import playsound
from threading import Thread

# Load environment variables
load_dotenv()

class DistractionPopup(QDialog):
    def __init__(self, message, parent=None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setModal(False)

        # Set the size of the popup
        self.resize(400, 200) 

        
        styles = [
            "font-size: 24px; color: red; font-weight: bold; background-color: black;",
            "font-size: 24px; color: blue; background-color: black;",
            "font-size: 24px; color: orange; background-color: black;",
            "font-size: 24px; color: white; background-color: red;",
            "font-size: 24px; color: black; font-weight: bold; background-color: red;",
            "font-size: 24px; color: orange; background-color: red;",
            "font-size: 24px; color: white; background-color: black;",
            "font-size: 28px; color: white; font-weight: bold; background-color: purple;",
            "font-size: 24px; color: red; background-color: black;",
            "font-size: 24px; color: white; background-color: purple;",
            "font-size: 24px; color: orange; background-color: black;"
        ]

        style = random.choice(styles)
         # Set the background color of the entire dialog to be the background color of the text
        self.setStyleSheet(style.split(";")[-2] + ";") 

        # Create a layout and message
        layout = QVBoxLayout()


        
        message = QLabel(message)
        message.setStyleSheet(style)  # Increase the font size for visibility
        layout.addWidget(message, alignment=Qt.AlignmentFlag.AlignCenter)  # Center the text within the popup
        self.setLayout(layout)

        self.center_on_screen()

    def center_on_screen(self):
        # Get the screen geometry
        screen_geometry = QApplication.primaryScreen().geometry()

        # Calculate the center position
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) * 1//4

        # Move the popup to the center of the screen
        self.move(x, y)

        def resizeEvent(self, event):
            # Re-center the dialog when it is resized
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
        self.wait(2000)  # Wait for up to 2 seconds for the thread to finish


# class DistractionAnalyzer(QObject):
#     analysis_complete = pyqtSignal(bool)
#     def __init__(self, task=""):
#         super().__init__()
#         self.task = task

#     def encode_image(self, image_path):
#         with open(image_path, "rb") as image_file:
#             return base64.b64encode(image_file.read()).decode('utf-8')
#     def ask_llava(self, prompt, image_path):
#         base64_image = self.encode_image(image_path)
        
#         response = requests.post('http://localhost:11434/api/generate',
#             json={
#                 'model': 'llava',
#                 'prompt': prompt,
#                 'images': [base64_image],
#                 'stream': False,
#                 'options': {
#                     'temperature': 0
#                 }
#             })
        
#         if response.status_code == 200:
#             return response.json()['response']
#         else:
#             return f"Error: {response.status_code}, {response.text}"
#     def analyze(self, qimage):
#             image_path = os.path.join(os.getcwd(), "debug_images", "capture_latest.png")
#             question = f"Is this person doing this: {self.task}, in the image? Reply with one word: 'Yes' or 'No'"
#             # question = "Is this person scrolling on social media, playing games, watching livestream, reading manga/comics, in the image? Reply with: 'Yes' or 'No'"

#             try:
#                 answer = self.ask_llava(question, image_path)
#                 print(f"LLaVA response: {answer}")
#                 is_distracted = answer.strip().lower() == "no"
#                 self.analysis_complete.emit(is_distracted)
#             except Exception as e:
#                 print(f"Error in LLaVA analysis: {e}")
#                 self.analysis_complete.emit(False)

class DistractionAnalyzer(QThread):
    analysis_complete = pyqtSignal(bool)

    def __init__(self, task=""):
        super().__init__()
        self.task = task
        self.image_path = None

    def set_image(self, image_path):
        self.image_path = image_path

    def run(self):
        # Perform the analysis in this method
        if self.image_path is not None:
            # question = f"In this image, is this person doing anything related to: {self.task}? Reply with one word: 'Yes' if they are or 'No' if they are definetely distracted."
            question = "Describe what this person in this image is doing briefly (5 words max) from these options: reading a book, learning, coding, watching educational youtube video, watching uneducational youtube video, browsing twitter/social media, reading comics, gaming, playing chess, watching twitch stream, writing."
            try:
                blacklisted_words = ["twitter", "comics", "gaming", "live stream", "watching shortform video", "uneducational"]
                answer = self.ask_llava(question, self.image_path)
                print(f"LLaVA response: {answer}")

                # is_distracted = answer.strip().lower() == "no"
                is_distracted = any(word in answer.strip().lower() for word in blacklisted_words)
                self.analysis_complete.emit(is_distracted)
            except Exception as e:
                print(f"Error in LLaVA analysis: {e}")
                self.analysis_complete.emit(False)

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
    def __init__(self, text, audio_path = "distraction_alert.mp3"):
        super().__init__()
        self.text = text
        self.audio_path = audio_path

    def run(self):
        # tts = gTTS(text=self.text, lang='en')
        # tts.save(self.audio_path)
        playsound("Radar.mp3")
        # Play the generated audio file
        playsound(self.audio_path)
        # os.remove("distraction_alert.mp3")  # Clean up the audio file

class ReflectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint | 
                                Qt.WindowType.FramelessWindowHint | 
                                Qt.WindowType.WindowStaysOnTopHint)

        self.setModal(False) # Make sure it's modal so it blocks interaction with other windows

        self.setWindowTitle("Reflection Time")
        self.setGeometry(100, 100, 400, 200)

        layout = QVBoxLayout()

        # Add a reflection message
        reflection_label = QLabel("You seemed distracted. What caused the distraction and how can you refocus?")
        reflection_label.setStyleSheet("font-size: 18px; font-weight: bold;")  
        layout.addWidget(reflection_label)

        # Text input for the user to reflect on their distraction
        self.reflection_input = QLineEdit()
        self.reflection_input.setPlaceholderText("Type your reflection here...")
        self.reflection_input.setStyleSheet("font-size: 16px;")  # Set the font size for the text input
        layout.addWidget(self.reflection_input)

        # Add a button to allow the user to confirm and close the dialog
        confirm_button = QPushButton("I'm ready to refocus!")
        confirm_button.setStyleSheet("font-size: 16px;")  # Set the font size for the button text
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)

        self.setLayout(layout)
        self.center_on_screen()

    def center_on_screen(self):
        # Get the screen geometry
        screen_geometry = QApplication.primaryScreen().geometry()

        # Calculate the center position
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2

        # Move the popup to the center of the screen
        self.move(x, y)
        
    def resizeEvent(self, event):
        # Re-center the dialog when it is resized
        self.center_on_screen()
        super().resizeEvent(event)

    def closeEvent(self, event):
        event.ignore()



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

        # Task input field and lock button
        task_layout = QHBoxLayout()
        task_label = QLabel("Task:")
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("e.g., coding, writing, etc.")
        task_layout.addWidget(task_label)
        task_layout.addWidget(self.task_input)
        self.lock_task_button = QPushButton("Lock Task")
        self.lock_task_button.clicked.connect(self.toggle_task_lock)
        task_layout.addWidget(self.lock_task_button)
        layout.addLayout(task_layout)

        self.task_lock_status_label = QLabel("Task Status: Unlocked")
        layout.addWidget(self.task_lock_status_label)

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
        self.analyzer.analysis_complete.connect(self.handle_analysis_result)  # Connect the signal
        self.task_locked = False

        # Initialize the rumps notification app
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("debug_images/image.png"))  # Replace with your icon path
        self.tray_menu = QMenu()
        self.tray_menu.addAction("Exit", self.close)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        self.distraction_popup = None
        self.reflection_popup = None


    def toggle_monitoring(self):
        if self.start_button.text() == "Start Monitoring":
            task = self.task_input.text().strip()
            if not task:
                self.monitoring_status_label.setText("Status: Please enter a task before starting.")
                return

            interval = self.interval_spinbox.value()
            self.analyzer = DistractionAnalyzer(task)  # Initialize with the task
            self.analyzer.analysis_complete.connect(self.handle_analysis_result)  # Connect the signal

            self.capture_thread = ScreenCaptureThread(interval)
            self.capture_thread.captured.connect(self.process_capture)
            self.capture_thread.start()

            self.start_button.setText("Stop Monitoring")
            self.monitoring_status_label.setText(f"Status: Monitoring (Interval: {interval}s)")
            self.interval_spinbox.setEnabled(False)
        else:
            self.start_button.setEnabled(False)
            self.monitoring_status_label.setText("Status: Stopping monitoring...")
            QTimer.singleShot(100, self.stop_monitoring)

    def stop_monitoring(self):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait(3000)  # Wait for up to 3 seconds
            # if self.capture_thread.isRunning():
            #     self.capture_thread.terminate()  # Force termination if thread doesn't stop
            self.capture_thread = None

        self.start_button.setText("Start Monitoring")
        self.monitoring_status_label.setText("Status: Not monitoring")
        self.interval_spinbox.setEnabled(True)
        self.start_button.setEnabled(True)

    def toggle_task_lock(self):
        if not self.task_locked:
            # Lock the task input
            self.task_input.setEnabled(False)
            self.lock_task_button.setText("Unlock Task")
            self.task_locked = True

            # Get the current task from the input field
            task = self.task_input.text().strip()

            if not task:
                self.task_lock_status_label.setText("Task Status: Please enter a task before locking.")
                return

            # Reinitialize the DistractionAnalyzer with the new task
            self.analyzer = DistractionAnalyzer(task)
            self.analyzer.analysis_complete.connect(self.handle_analysis_result)  # Reconnect the signal

            # Update status to reflect the task is locked
            self.task_lock_status_label.setText(f"Task Status: Locked with task '{task}'")
        else:
            # Unlock the task input
            self.task_input.setEnabled(True)
            self.lock_task_button.setText("Lock Task")
            self.task_locked = False

            # Optionally, update status to reflect the task is unlocked
            self.task_lock_status_label.setText("Task Status: Unlocked. You can edit the task now.")


    # def process_capture(self, qimage):
    #     scaled_pixmap = QPixmap.fromImage(qimage).scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatio)
    #     self.image_label.setPixmap(scaled_pixmap)
    #     QTimer.singleShot(0, lambda: self.analyzer.analyze(qimage))
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
        if is_distracted:
            print("You seem distracted!")
            self.show_notification("Distraction Alert", "You seem to be distracted. Focus on your work!")

            messages = [
                "You seem distracted! Focus on your work!",
                "Stay on track! Don't lose your focus.",
                "Stop slacking! Get back to work NOW!",
                "Get back to work! You can do it!",
                "Your goal is important. Stay focused!",
                "No room for weakness. Push through and stay on task!",
                "Every minute you waste is a minute you’ll regret. Focus!",
                "Mediocrity is not an option. Focus harder!",
                "What’s more important than your goals? Nothing. Get back to work!"
            ]

            message = random.choice(messages)

            self.show_distraction_popup(message)
            self.play_audio_alert(message)

            self.stop_monitoring()

            reflection_dialog = ReflectionDialog()
            if reflection_dialog.exec():
                print(f"User reflection: {reflection_dialog.reflection_input.text()}")
                self.show_notification("Great!", "Let's get back to work!")

                self.hide_distraction_popup()

                self.start_monitoring()
    def start_monitoring(self):
        task = self.task_input.text().strip()
        if not task:
            self.monitoring_status_label.setText("Status: Please enter a task before starting.")
            return

        interval = self.interval_spinbox.value()
        self.analyzer = DistractionAnalyzer(task)  # Initialize with the task
        self.analyzer.analysis_complete.connect(self.handle_analysis_result)  # Connect the signal

        self.capture_thread = ScreenCaptureThread(interval)
        self.capture_thread.captured.connect(self.process_capture)
        self.capture_thread.start()

        self.start_button.setText("Stop Monitoring")
        self.monitoring_status_label.setText(f"Status: Monitoring (Interval: {interval}s)")
        self.interval_spinbox.setEnabled(False)
    
    def play_audio_alert(self, message):
        self.audio_thread = AudioThread(message, "distraction_alert.mp3")
        self.audio_thread.start()

    def show_notification(self, title, message):
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def show_distraction_popup(self, message = "Focus on your work!"):
        self.distraction_popup = DistractionPopup(message)
        self.distraction_popup.show()
        # Optionally, set a timer to hide the popup after a certain duration
        # QTimer.singleShot(10000, self.hide_distraction_popup)  # Hide after 10 seconds
    def hide_distraction_popup(self):
        if self.distraction_popup:
            self.distraction_popup.hide()
    def show_reflection_popup(self):
        # Create and show the reflection dialog
        reflection_dialog = ReflectionDialog(self)
        if reflection_dialog.exec():  # This will block until the user closes the dialog
            print(f"User reflection: {reflection_dialog.reflection_input.text()}")
            self.show_notification("Great!", "Let's get back to work!")

            # Hide the distraction popup once reflection is done
            self.hide_distraction_popup()

            # Resume monitoring
            self.start_monitoring()
    def hide_reflection_popup(self):
        if self.reflection_popup:
            self.reflection_popup.hide()

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
                                     