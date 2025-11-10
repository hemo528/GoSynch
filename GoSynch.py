import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QComboBox, QLineEdit, QPushButton, QListWidget,
                             QLabel, QMessageBox, QListWidgetItem)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont, QColor
import datetime
import time


class SerialMonitorThread(QThread):
    """串口监控线程"""
    data_received = pyqtSignal(str)  # 接收到数据的信号
    timeout_occurred = pyqtSignal(str)  # 超时发生的信号
    error_occurred = pyqtSignal(str)  # 错误发生的信号

    def __init__(self, port, baudrate, timeout_seconds):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.serial_conn = None
        self.is_running = False
        self.last_received_time = None

    def run(self):
        """线程主函数"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1  # 读取超时1秒
            )
            self.is_running = True
            self.last_received_time = datetime.datetime.now()

            while self.is_running:
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    try:
                        data = self.serial_conn.readline().decode('utf-8', errors='ignore')
                        if data.strip():  # 只处理非空数据
                            self.last_received_time = datetime.datetime.now()
                            self.data_received.emit(data.strip())
                    except Exception as e:
                        self.error_occurred.emit(f"数据读取错误: {str(e)}")

                # 检查超时
                if self.last_received_time:
                    current_time = datetime.datetime.now()
                    time_diff = (current_time - self.last_received_time).total_seconds()
                    if time_diff > self.timeout_seconds:
                        timeout_str = self.last_received_time.strftime("%Y-%m-%d %H:%M:%S")
                        self.timeout_occurred.emit(f"最后数据时间: {timeout_str}")
                        # 重置计时，避免重复触发
                        self.last_received_time = current_time

                # 短暂休眠，减少CPU占用
                self.msleep(100)

        except Exception as e:
            self.error_occurred.emit(f"串口连接错误: {str(e)}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()

    def stop(self):
        """停止监控"""
        self.is_running = False
        self.wait(1000)  # 等待线程结束，最多1秒


class SerialMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.monitor_thread = None
        self.init_ui()
        self.refresh_ports()

        # 定时刷新串口列表
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_ports)
        self.refresh_timer.start(2000)  # 每2秒刷新一次

    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("串口监控 v0.1")
        self.setGeometry(100, 100, 600, 500)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        layout = QVBoxLayout(central_widget)

        # 标题
        title_label = QLabel("串口监控")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 串口选择区域
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("串口:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(150)
        port_layout.addWidget(self.port_combo)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_ports)
        port_layout.addWidget(refresh_btn)

        port_layout.addStretch()
        layout.addLayout(port_layout)

        # 波特率设置区域
        baud_layout = QHBoxLayout()
        baud_layout.addWidget(QLabel("波特率:"))
        self.baud_edit = QLineEdit("9600")
        self.baud_edit.setMaximumWidth(100)
        baud_layout.addWidget(self.baud_edit)

        baud_layout.addWidget(QLabel("超时时间(秒):"))
        self.timeout_edit = QLineEdit("600")
        self.timeout_edit.setMaximumWidth(100)
        baud_layout.addWidget(self.timeout_edit)

        baud_layout.addStretch()
        layout.addLayout(baud_layout)

        # 按钮区域
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始监控")
        self.start_btn.clicked.connect(self.toggle_monitoring)
        self.start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        button_layout.addWidget(self.start_btn)

        self.clear_btn = QPushButton("清空记录")
        self.clear_btn.clicked.connect(self.clear_records)
        self.clear_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
        button_layout.addWidget(self.clear_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("QLabel { background-color: #e0e0e0; padding: 5px; }")
        layout.addWidget(self.status_label)

        # 记录列表
        layout.addWidget(QLabel("超时记录:"))
        self.record_list = QListWidget()
        layout.addWidget(self.record_list)

        # 数据接收显示
        layout.addWidget(QLabel("接收数据:"))
        self.data_list = QListWidget()
        self.data_list.setMaximumHeight(150)
        layout.addWidget(self.data_list)

    def refresh_ports(self):
        """刷新可用串口列表"""
        current_selection = self.port_combo.currentText()
        self.port_combo.clear()

        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)

        # 尝试恢复之前的选择
        if current_selection and self.port_combo.findText(current_selection) >= 0:
            self.port_combo.setCurrentText(current_selection)
        elif self.port_combo.count() > 0:
            self.port_combo.setCurrentIndex(0)

    def toggle_monitoring(self):
        """开始/停止监控"""
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def start_monitoring(self):
        """开始监控"""
        if self.port_combo.count() == 0:
            QMessageBox.warning(self, "警告", "没有可用的串口!")
            return

        port = self.port_combo.currentText()

        try:
            baudrate = int(self.baud_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "波特率必须是整数!")
            return

        try:
            timeout_seconds = int(self.timeout_edit.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "超时时间必须是整数!")
            return

        # 创建并启动监控线程
        self.monitor_thread = SerialMonitorThread(port, baudrate, timeout_seconds)
        self.monitor_thread.data_received.connect(self.on_data_received)
        self.monitor_thread.timeout_occurred.connect(self.on_timeout_occurred)
        self.monitor_thread.error_occurred.connect(self.on_error_occurred)
        self.monitor_thread.start()

        # 更新界面状态
        self.start_btn.setText("停止监控")
        self.start_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
        self.status_label.setText(f"正在监控 {port}，波特率 {baudrate}")
        self.status_label.setStyleSheet("QLabel { background-color: #4CAF50; color: white; padding: 5px; }")

    def stop_monitoring(self):
        """停止监控"""
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread = None

        # 更新界面状态
        self.start_btn.setText("开始监控")
        self.start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        self.status_label.setText("监控已停止")
        self.status_label.setStyleSheet("QLabel { background-color: #e0e0e0; padding: 5px; }")

    def on_data_received(self, data):
        """处理接收到的数据"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        item_text = f"[{timestamp}] {data}"

        # 添加到数据列表
        self.data_list.addItem(item_text)
        self.data_list.scrollToBottom()

        # 限制数据列表长度
        if self.data_list.count() > 100:
            self.data_list.takeItem(0)

    def on_timeout_occurred(self, timeout_info):
        """处理超时事件"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item_text = f"[{timestamp}] 串口超时 - {timeout_info}"

        # 创建列表项
        item = QListWidgetItem(item_text)
        item.setBackground(QColor(255, 235, 238))  # 浅红色背景

        # 添加到记录列表
        self.record_list.addItem(item)
        self.record_list.scrollToBottom()

    def on_error_occurred(self, error_msg):
        """处理错误事件"""
        self.status_label.setText(f"错误: {error_msg}")
        self.status_label.setStyleSheet("QLabel { background-color: #ffcdd2; padding: 5px; }")
        self.stop_monitoring()
        QMessageBox.critical(self, "错误", error_msg)

    def clear_records(self):
        """清空记录"""
        self.record_list.clear()
        self.data_list.clear()

    def closeEvent(self, event):
        """关闭窗口事件"""
        self.stop_monitoring()
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SerialMonitorApp()
    window.show()
    sys.exit(app.exec_())
