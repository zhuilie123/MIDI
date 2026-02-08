import mido
import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import customtkinter as ctk
import traceback
from collections import defaultdict
import math
import logging
import time
import threading
import pygame
import pygame.midi
import queue

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 守望工坊字符集（共128个字符）
WORKSHOP_CHARSET = "0¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿĀāĂăĄąĆćĈĉĊċČčĎďĐđĒēĔĕĖėĘęĚěĜĝĞğĠġ"

class MidiConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MIDI转换器-BY追猎")
        
        # 设置窗口大小
        self.geometry("1000x800")
        self.minsize(900, 700)
        
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        # 初始化变量
        self.shift_amount = 0
        self.selected_tracks = []
        self.bpm = 120
        self.subroutine_id = 50
        self.is_playing = False
        self.is_paused = False
        self.playback_thread = None
        self.track_states = {}
        self.total_playback_time = 0.0
        self.midi_output = None
        self.active_notes = {}
        self.track_channels = {}
        self.current_file = None
        self.raw_data = None
        self.compressed_data = None
        self.compressed_floats = None
        self.num_events = 0
        self.seeking = False
        self.current_playback_time = 0.0
        self.was_playing = False
        self.midi_loaded = False
        self.all_events = []
        self.ticks_per_beat = 480
        self.midi_data = None
        self.stop_event = threading.Event()
        self.playback_lock = threading.Lock()
        
        # 创建UI
        self.create_widgets()
        self.init_audio()
        
    def create_widgets(self):
        # 设置网格权重
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # 主容器框架
        main_container = ctk.CTkFrame(self)
        main_container.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        main_container.grid_columnconfigure(0, weight=1)
        
        # 顶部文件选择框架
        top_frame = ctk.CTkFrame(main_container)
        top_frame.grid(row=0, column=0, padx=0, pady=5, sticky="ew")
        
        ctk.CTkLabel(top_frame, text="Ckey MIDI文件:").pack(side="left", padx=(0, 5))
        self.btn_select = ctk.CTkButton(top_frame, text="浏览...", command=self.select_file, width=80)
        self.btn_select.pack(side="left", padx=(0, 10))
        
        self.file_path = ctk.CTkEntry(top_frame, height=30)
        self.file_path.pack(side="left", fill="x", expand=True, padx=(0, 0))
        self.file_path.insert(0, "")
        self.file_path.configure(state="readonly")
        
        # 音区调整框架
        shift_frame = ctk.CTkFrame(main_container)
        shift_frame.grid(row=1, column=0, padx=0, pady=5, sticky="ew")
        shift_frame.grid_columnconfigure(4, weight=1)
        
        ctk.CTkLabel(shift_frame, text="音区调整:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        self.btn_shift_down = ctk.CTkButton(shift_frame, text="↓ 下移1个八度", 
                                           command=lambda: self.set_shift(-12), width=100)
        self.btn_shift_down.grid(row=0, column=1, padx=5, pady=5)
        
        self.btn_shift_up = ctk.CTkButton(shift_frame, text="↑ 上移1个八度", 
                                         command=lambda: self.set_shift(12), width=100)
        self.btn_shift_up.grid(row=0, column=2, padx=5, pady=5)
        
        ctk.CTkLabel(shift_frame, text="半音微调:").grid(row=0, column=3, padx=(20,5), pady=5, sticky="w")
        
        self.slider_shift = ctk.CTkSlider(shift_frame, from_=-24, to=24, width=150)
        self.slider_shift.set(0)
        self.slider_shift.grid(row=0, column=4, padx=5, pady=5, sticky="ew")
        self.slider_shift.bind("<ButtonRelease-1>", self.update_shift_label)
        
        self.lbl_shift_value = ctk.CTkLabel(shift_frame, text="0 半音", width=60)
        self.lbl_shift_value.grid(row=0, column=5, padx=5, pady=5)
        
        # BPM和子程序ID框架
        info_frame = ctk.CTkFrame(main_container)
        info_frame.grid(row=2, column=0, padx=0, pady=5, sticky="ew")
        
        ctk.CTkLabel(info_frame, text="BPM速度:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.lbl_bpm = ctk.CTkLabel(info_frame, text="120", width=60)
        self.lbl_bpm.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(info_frame, text="子程序ID:").grid(row=0, column=2, padx=(20,5), pady=5, sticky="w")
        
        # 子程序ID输入框和上下箭头按钮
        subroutine_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        subroutine_frame.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        # 上箭头按钮
        self.btn_sub_up = ctk.CTkButton(subroutine_frame, text="▲", width=30, height=20,
                                       command=lambda: self.change_subroutine_id(1))
        self.btn_sub_up.pack(side="top", padx=(0, 0))
        
        # 子程序ID输入框
        self.entry_subroutine = ctk.CTkEntry(subroutine_frame, width=50, height=25)
        self.entry_subroutine.insert(0, "50")
        self.entry_subroutine.pack(side="top", padx=0, pady=2)
        
        # 下箭头按钮
        self.btn_sub_down = ctk.CTkButton(subroutine_frame, text="▼", width=30, height=20,
                                         command=lambda: self.change_subroutine_id(-1))
        self.btn_sub_down.pack(side="top", padx=(0, 0))
        
        # 轨道选择框架
        track_frame = ctk.CTkFrame(main_container)
        track_frame.grid(row=3, column=0, padx=0, pady=5, sticky="ew")
        
        ctk.CTkLabel(track_frame, text="轨道选择:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        # 轨道复选框容器框架
        self.track_check_frame = ctk.CTkFrame(track_frame)
        self.track_check_frame.grid(row=1, column=0, columnspan=4, padx=5, pady=5, sticky="ew")
        
        # 全选/取消复选框
        self.select_all_var = tk.IntVar(value=1)
        all_cb = ctk.CTkCheckBox(track_frame, text="全选/取消", variable=self.select_all_var,
                                 command=self.toggle_select_all)
        all_cb.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        
        # 播放控制框架
        control_frame = ctk.CTkFrame(main_container)
        control_frame.grid(row=4, column=0, padx=0, pady=5, sticky="ew")
        control_frame.grid_columnconfigure(3, weight=1)
        
        # 播放/暂停按钮
        self.btn_play = ctk.CTkButton(control_frame, text="▶ 播放", 
                                      command=self.toggle_play, state="disabled", width=80)
        self.btn_play.grid(row=0, column=0, padx=5, pady=5)
        
        # 停止按钮
        self.btn_stop = ctk.CTkButton(control_frame, text="⏹ 停止", 
                                      command=self.stop_playback, state="disabled", width=80)
        self.btn_stop.grid(row=0, column=1, padx=5, pady=5)
        
        # 进度条标签
        ctk.CTkLabel(control_frame, text="播放进度:").grid(row=0, column=2, padx=(20,5), pady=5)
        
        # 进度条
        self.progress_slider = ctk.CTkSlider(control_frame, from_=0, to=100, width=200)
        self.progress_slider.set(0)
        self.progress_slider.grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        # 绑定进度条事件
        self.progress_slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)
        
        self.lbl_progress = ctk.CTkLabel(control_frame, text="0:00 / 0:00", width=80)
        self.lbl_progress.grid(row=0, column=4, padx=5, pady=5)
        
        # 功能按钮框架
        func_frame = ctk.CTkFrame(main_container)
        func_frame.grid(row=5, column=0, padx=0, pady=5, sticky="ew")
        func_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.btn_convert = ctk.CTkButton(func_frame, text="开始转换", 
                                        command=self.convert, state="disabled")
        self.btn_convert.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        self.btn_compress = ctk.CTkButton(func_frame, text="工坊压缩", 
                                         command=self.compress_vectors, state="disabled")
        self.btn_compress.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.btn_verify = ctk.CTkButton(func_frame, text="验证还原", 
                                       command=self.verify_decompression, state="disabled")
        self.btn_verify.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        
        # 标签页容器
        tabs_frame = ctk.CTkFrame(main_container)
        tabs_frame.grid(row=6, column=0, padx=0, pady=5, sticky="nsew")
        main_container.grid_rowconfigure(6, weight=1)
        
        # 创建标签页
        self.tabview = ctk.CTkTabview(tabs_frame)
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 添加标签页
        self.tab_preview = self.tabview.add("预览")
        self.tab_workshop = self.tabview.add("工坊代码")
        self.tab_compressed = self.tabview.add("压缩结果")
        self.tab_verification = self.tabview.add("验证还原")
        
        # 预览框
        preview_frame = ctk.CTkFrame(self.tab_preview)
        preview_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.preview = scrolledtext.ScrolledText(preview_frame, height=15, bg='#2b2b2b', fg='white')
        self.preview.pack(fill="both", expand=True)
        
        # 工坊代码框
        workshop_frame = ctk.CTkFrame(self.tab_workshop)
        workshop_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.workshop_code = scrolledtext.ScrolledText(workshop_frame, height=15, bg='#2b2b2b', fg='white')
        self.workshop_code.pack(fill="both", expand=True)
        
        # 压缩结果框
        compressed_frame = ctk.CTkFrame(self.tab_compressed)
        compressed_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.compressed_text = scrolledtext.ScrolledText(compressed_frame, height=15, bg='#2b2b2b', fg='white')
        self.compressed_text.pack(fill="both", expand=True)
        
        # 验证还原框
        verification_frame = ctk.CTkFrame(self.tab_verification)
        verification_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.verification_text = scrolledtext.ScrolledText(verification_frame, height=15, bg='#2b2b2b', fg='white')
        self.verification_text.pack(fill="both", expand=True)
        
        # 底部按钮框架
        bottom_frame = ctk.CTkFrame(main_container)
        bottom_frame.grid(row=7, column=0, padx=0, pady=5, sticky="ew")
        bottom_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.btn_save = ctk.CTkButton(bottom_frame, text="保存结果", 
                                     command=self.save_file, state="disabled")
        self.btn_save.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        self.btn_save_workshop = ctk.CTkButton(bottom_frame, text="保存工坊代码", 
                                              command=self.save_workshop_code, state="disabled")
        self.btn_save_workshop.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.btn_exit = ctk.CTkButton(bottom_frame, text="退出", 
                                     command=self.destroy)
        self.btn_exit.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        
    def change_subroutine_id(self, delta):
        """更改子程序ID"""
        try:
            current = int(self.entry_subroutine.get())
            new_value = current + delta
            if 1 <= new_value <= 99:  # 限制在1-99范围内
                self.entry_subroutine.delete(0, tk.END)
                self.entry_subroutine.insert(0, str(new_value))
                self.subroutine_id = new_value
        except ValueError:
            self.entry_subroutine.delete(0, tk.END)
            self.entry_subroutine.insert(0, "50")
            self.subroutine_id = 50
        
    def init_audio(self):
        """初始化音频设备"""
        try:
            pygame.mixer.quit()
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.midi.init()
        except Exception as e:
            logging.error(f"初始化音频设备时出错: {e}")
            
    def set_shift(self, semitones):
        """设置整个音区的移动量"""
        self.shift_amount = semitones
        self.slider_shift.set(semitones)
        self.update_shift_label()
        
    def update_shift_label(self, event=None):
        """更新音区移动显示"""
        value = int(self.slider_shift.get())
        self.shift_amount = value
        self.lbl_shift_value.configure(text=f"{value} 半音")
    
    def create_track_checkboxes(self, tracks):
        """创建轨道复选框"""
        # 清除旧的复选框
        for widget in self.track_check_frame.winfo_children():
            widget.destroy()
        
        self.track_vars = []
        self.track_checkboxes = []
        
        # 创建新的复选框
        for i, track in enumerate(tracks):
            var = tk.IntVar(value=1)
            track_name = track.name if track.name else f"轨道{i+1}"
            if len(track_name) > 10:
                track_name = track_name[:8] + ".."
            
            cb = ctk.CTkCheckBox(self.track_check_frame, text=f"轨道 {i+1}: {track_name}", variable=var)
            cb.grid(row=i//3, column=i%3, padx=10, pady=5, sticky="w")
            
            self.track_vars.append(var)
            self.track_checkboxes.append(cb)
            
            # 绑定事件
            var.trace_add("write", lambda *args, idx=i: self.on_track_state_changed(idx))
    
    def on_track_state_changed(self, track_idx):
        """轨道状态变化"""
        if hasattr(self, 'track_states') and self.is_playing and not self.is_paused:
            is_selected = self.track_vars[track_idx].get() == 1
            self.track_states[track_idx] = is_selected
            
            if hasattr(self, 'midi_output') and self.midi_output:
                try:
                    if track_idx in self.track_channels:
                        channel = self.track_channels[track_idx]
                        if is_selected:
                            # 取消静音
                            self.midi_output.write_short(0xB0 + channel, 7, 127)
                        else:
                            # 静音
                            self.midi_output.write_short(0xB0 + channel, 7, 0)
                            # 停止当前音符
                            self.stop_all_notes_for_track(track_idx)
                except Exception as e:
                    logging.error(f"设置轨道{track_idx}静音状态失败: {e}")
    
    def stop_all_notes_for_track(self, track_idx):
        """停止指定轨道的所有音符"""
        if hasattr(self, 'active_notes') and track_idx in self.active_notes:
            for note in self.active_notes[track_idx]:
                try:
                    if hasattr(self, 'midi_output') and self.midi_output:
                        channel = self.track_channels[track_idx]
                        self.midi_output.note_off(note, 0, channel)
                except:
                    pass
            self.active_notes[track_idx] = []
    
    def toggle_select_all(self):
        """切换全选/取消"""
        state = self.select_all_var.get()
        for i, (cb, var) in enumerate(zip(self.track_checkboxes, self.track_vars)):
            var.set(state)
            if hasattr(self, 'track_states'):
                self.track_states[i] = (state == 1)
    
    def select_file(self):
        """选择MIDI文件"""
        filetypes = [("MIDI文件", "*.mid *.midi")]
        filepath = filedialog.askopenfilename(title="选择MIDI文件", filetypes=filetypes)
        
        if filepath:
            # 更新文件路径显示
            if len(filepath) > 50:
                display_path = "..." + filepath[-47:]
            else:
                display_path = filepath
            
            self.file_path.configure(state="normal")
            self.file_path.delete(0, tk.END)
            self.file_path.insert(0, display_path)
            self.file_path.configure(state="readonly")
            
            self.current_file = filepath
            self.is_playing = False
            self.is_paused = False
            self.playback_progress = 0.0
            self.progress_slider.set(0)
            self.lbl_progress.configure(text="0:00 / 0:00")
            self.midi_loaded = False
            
            try:
                # 加载MIDI文件
                self.midi_data = mido.MidiFile(filepath)
                
                # 创建轨道选择
                self.create_track_checkboxes(self.midi_data.tracks)
                
                # 初始化轨道状态
                self.track_states = {i: True for i in range(len(self.midi_data.tracks))}
                
                # 获取BPM
                self.bpm = self.get_bpm_from_midi(self.midi_data)
                self.lbl_bpm.configure(text=str(self.bpm))
                
                # 计算总时长
                self.total_playback_time = self.calculate_midi_duration(self.midi_data)
                self.ticks_per_beat = self.midi_data.ticks_per_beat
                
                # 标记MIDI已加载
                self.midi_loaded = True
                
                # 启用按钮
                self.btn_convert.configure(state="normal")
                self.btn_play.configure(state="normal")
                
            except Exception as e:
                messagebox.showerror("错误", f"加载MIDI文件失败:\n{str(e)}")
                self.btn_convert.configure(state="disabled")
                self.btn_play.configure(state="disabled")
    
    def get_bpm_from_midi(self, mid):
        """从MIDI文件中获取BPM值"""
        default_bpm = 120
        tempo = 500000
        
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                    break
            if tempo != 500000:
                break
        
        bpm = round(60000000 / tempo)
        return bpm if bpm > 0 else default_bpm
    
    def calculate_midi_duration(self, mid):
        """计算MIDI文件总时长"""
        try:
            total_time = mid.length
            
            if total_time > 36000:
                total_time = self.calculate_duration_manually(mid)
            
            if total_time > 86400:
                total_time = 3600
            
            return total_time
            
        except Exception as e:
            logging.error(f"计算MIDI时长出错: {e}")
            return 300
    
    def calculate_duration_manually(self, mid):
        """手动计算MIDI文件时长"""
        try:
            total_ticks = 0
            for track in mid.tracks:
                track_ticks = 0
                for msg in track:
                    track_ticks += msg.time
                if track_ticks > total_ticks:
                    total_ticks = track_ticks
            
            tempo = 500000
            ticks_per_beat = mid.ticks_per_beat
            
            total_time = mido.tick2second(total_ticks, ticks_per_beat, tempo)
            
            return total_time
            
        except:
            return 300
    
    def format_time(self, seconds):
        """格式化时间显示"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"
    
    def update_progress_label(self):
        """更新进度标签"""
        current = self.format_time(self.current_playback_time)
        total = self.format_time(self.total_playback_time) if self.total_playback_time > 0 else "0:00"
        self.lbl_progress.configure(text=f"{current} / {total}")
        
        # 只有在不拖动时才自动更新进度条
        if not self.seeking and self.total_playback_time > 0:
            progress = min(self.current_playback_time / self.total_playback_time, 1.0) * 100
            self.progress_slider.set(progress)
    
    def on_slider_press(self, event):
        """开始拖动滑块"""
        self.seeking = True
        self.was_playing = self.is_playing and not self.is_paused
        
        # 如果正在播放，暂停播放
        if self.was_playing:
            self.is_paused = True
            self.btn_play.configure(text="▶ 播放")
    
    def on_slider_release(self, event):
        """结束拖动滑块"""
        self.seeking = False
        
        # 计算新的播放时间
        progress = self.progress_slider.get() / 100.0
        new_time = progress * self.total_playback_time
        self.current_playback_time = new_time
        
        # 更新显示
        self.update_progress_label()
        
        # 如果之前正在播放，跳转到新位置并继续播放
        if self.was_playing and self.midi_loaded:
            # 使用after延迟执行，避免界面卡死
            self.after(100, self.restart_playback_from_position)
    
    def restart_playback_from_position(self):
        """从新位置重新开始播放"""
        # 停止当前播放
        self.is_playing = False
        self.is_paused = False
        
        # 等待播放线程结束
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.5)
        
        # 重新开始播放
        self.is_playing = True
        self.is_paused = False
        self.btn_play.configure(text="⏸ 暂停")
        
        # 重新开始播放
        self.start_playback()
    
    def toggle_play(self):
        """播放/暂停切换"""
        if not self.current_file:
            messagebox.showerror("错误", "请先选择MIDI文件")
            return
            
        if self.is_playing and not self.is_paused:
            # 暂停播放
            self.is_paused = True
            self.btn_play.configure(text="▶ 播放")
        else:
            # 开始播放或恢复播放
            if self.is_playing and self.is_paused:
                # 恢复播放
                self.is_paused = False
                self.btn_play.configure(text="⏸ 暂停")
            else:
                # 开始播放
                self.start_playback()
    
    def start_playback(self):
        """开始播放"""
        # 如果已经在播放中，恢复播放
        if self.is_playing and self.is_paused:
            self.is_paused = False
            self.btn_play.configure(text="⏸ 暂停")
            return
            
        # 获取选中的轨道
        selected_track_indices = []
        if hasattr(self, 'track_vars'):
            for i, var in enumerate(self.track_vars):
                if var.get() == 1:
                    selected_track_indices.append(i)
                    self.track_states[i] = True
                else:
                    self.track_states[i] = False
        
        if not selected_track_indices:
            messagebox.showinfo("提示", "请选择至少一个轨道")
            return
        
        # 启用按钮
        self.btn_play.configure(text="⏸ 暂停")
        self.btn_stop.configure(state="normal")
        
        # 开启新线程播放
        self.is_playing = True
        self.is_paused = False
        self.stop_event.clear()
        
        self.playback_thread = threading.Thread(target=self._play_midi_safe, 
                                              args=(selected_track_indices,),
                                              daemon=True)
        self.playback_thread.start()
    
    def _play_midi_safe(self, selected_track_indices):
        """安全的MIDI播放函数"""
        try:
            # 加载MIDI文件
            mid = mido.MidiFile(self.current_file)
            
            # 重新初始化MIDI设备
            try:
                pygame.midi.quit()
                pygame.midi.init()
                
                # 尝试获取MIDI输出设备
                output_id = None
                for i in range(pygame.midi.get_count()):
                    info = pygame.midi.get_device_info(i)
                    if info and info[2] == 1:  # 输出设备
                        try:
                            self.midi_output = pygame.midi.Output(i)
                            output_id = i
                            break
                        except:
                            continue
                
                if output_id is None:
                    # 尝试使用默认设备
                    try:
                        self.midi_output = pygame.midi.Output(0)
                    except Exception as e:
                        # 如果还没有设备，使用虚拟设备
                        self.after(0, lambda: messagebox.showwarning("MIDI警告", 
                            "未找到MIDI输出设备，将使用虚拟设备播放。\n"
                            "要听到声音，请确保系统已安装MIDI合成器。"))
                        # 继续执行，但可能没有声音
                        self.midi_output = None
                        
            except Exception as e:
                logging.error(f"初始化MIDI设备失败: {e}")
                self.midi_output = None
            
            # 收集所有MIDI事件
            all_events = []
            current_tempo = 500000
            ticks_per_beat = mid.ticks_per_beat
            
            for track_idx, track in enumerate(mid.tracks):
                if track_idx not in selected_track_indices:
                    continue
                    
                current_tick = 0
                for msg in track:
                    current_tick += msg.time
                    
                    if msg.type == 'set_tempo':
                        current_tempo = msg.tempo
                    
                    if msg.type in ['note_on', 'note_off']:
                        all_events.append((current_tick, msg, track_idx, current_tempo))
            
            # 按时间排序
            all_events.sort(key=lambda x: x[0])
            
            if not all_events:
                self.after(0, self.stop_playback)
                return
            
            # 计算总时间
            max_tick = all_events[-1][0]
            self.total_playback_time = mido.tick2second(max_tick, ticks_per_beat, 500000)
            
            # 根据当前进度调整起始位置
            start_index = 0
            if self.current_playback_time > 0:
                for i, (tick, msg, track_idx, tempo) in enumerate(all_events):
                    event_time = mido.tick2second(tick, ticks_per_beat, tempo)
                    if event_time >= self.current_playback_time:
                        start_index = i
                        break
            
            # 初始化轨道通道
            self.track_channels = {}
            self.active_notes = {}
            
            channel = 0
            for track_idx in selected_track_indices:
                self.track_channels[track_idx] = channel
                self.active_notes[track_idx] = []
                
                if self.midi_output:
                    try:
                        # 设置通道音量
                        self.midi_output.write_short(0xB0 + channel, 7, 127)  # 音量
                        self.midi_output.write_short(0xB0 + channel, 10, 64)  # 声像
                    except:
                        pass
                
                channel += 1
                if channel >= 16:  # MIDI只有16个通道
                    channel = 0
            
            # 开始播放
            start_time = time.time() - self.current_playback_time
            last_update_time = time.time()
            event_index = start_index
            
            while self.is_playing and event_index < len(all_events) and not self.stop_event.is_set():
                if self.is_paused:
                    time.sleep(0.1)
                    continue
                
                current_time = time.time() - start_time
                
                # 处理所有应该在这个时间点发生的事件
                while (event_index < len(all_events) and 
                       mido.tick2second(all_events[event_index][0], ticks_per_beat, all_events[event_index][3]) <= current_time):
                    
                    tick, msg, track_idx, tempo = all_events[event_index]
                    
                    if self.track_states.get(track_idx, True):
                        try:
                            if self.midi_output:
                                if msg.type == 'note_on' and msg.velocity > 0:
                                    # 应用移调
                                    note = msg.note + self.shift_amount
                                    if note < 0:
                                        note = 0
                                    elif note > 127:
                                        note = 127
                                    
                                    channel = self.track_channels[track_idx]
                                    self.midi_output.note_on(note, msg.velocity, channel)
                                    self.active_notes[track_idx].append(note)
                                    
                                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                                    # 应用移调
                                    note = msg.note + self.shift_amount
                                    if note < 0:
                                        note = 0
                                    elif note > 127:
                                        note = 127
                                    
                                    channel = self.track_channels[track_idx]
                                    self.midi_output.note_off(note, 0, channel)
                                    if note in self.active_notes[track_idx]:
                                        self.active_notes[track_idx].remove(note)
                        except Exception as e:
                            logging.error(f"发送MIDI消息失败: {e}")
                    
                    event_index += 1
                
                # 更新进度
                if time.time() - last_update_time >= 0.1:
                    self.current_playback_time = current_time
                    self.after(0, self.update_progress_label)
                    last_update_time = time.time()
                
                time.sleep(0.001)
            
            # 播放完成
            if not self.stop_event.is_set():
                self.after(0, self.stop_playback)
            
        except Exception as e:
            logging.error(f"播放失败: {e}\n{traceback.format_exc()}")
            self.after(0, self.stop_playback)
    
    def stop_playback(self):
        """停止播放"""
        self.is_playing = False
        self.is_paused = False
        self.stop_event.set()
        
        # 停止所有音符
        if hasattr(self, 'midi_output') and self.midi_output:
            try:
                # 发送所有音符关闭消息
                for channel in range(16):
                    for note in range(128):
                        try:
                            self.midi_output.note_off(note, 0, channel)
                        except:
                            pass
            except:
                pass
            
            try:
                self.midi_output.close()
                self.midi_output = None
            except:
                pass
        
        # 等待播放线程结束
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.5)
        
        # 重置进度
        self.current_playback_time = 0.0
        self.progress_slider.set(0)
        self.update_progress_label()
        
        # 更新按钮状态
        self.btn_play.configure(text="▶ 播放")
        self.btn_stop.configure(state="disabled")
    
    def convert(self):
        """转换MIDI文件"""
        if not self.current_file:
            messagebox.showerror("错误", "请先选择MIDI文件")
            return
        
        try:
            # 获取子程序ID
            try:
                self.subroutine_id = int(self.entry_subroutine.get())
                if self.subroutine_id < 1 or self.subroutine_id > 99:
                    messagebox.showwarning("警告", "子程序ID必须在1-99之间，已重置为50")
                    self.subroutine_id = 50
                    self.entry_subroutine.delete(0, tk.END)
                    self.entry_subroutine.insert(0, "50")
            except ValueError:
                messagebox.showwarning("警告", "子程序ID必须是整数，已重置为50")
                self.subroutine_id = 50
                self.entry_subroutine.delete(0, tk.END)
                self.entry_subroutine.insert(0, "50")
            
            mid = mido.MidiFile(self.current_file)
            output = []
            
            # 获取选中的轨道
            self.selected_tracks = []
            if hasattr(self, 'track_vars'):
                for i, var in enumerate(self.track_vars):
                    if var.get() == 1:
                        self.selected_tracks.append(i)
            
            if not self.selected_tracks:
                self.selected_tracks = list(range(len(mid.tracks)))
            
            # 添加文件信息
            output.append(f"MIDI文件转换结果")
            output.append(f"文件名: {os.path.basename(self.current_file)}")
            output.append(f"轨道数: {len(mid.tracks)} (已选择: {len(self.selected_tracks)})")
            output.append(f"时间分辨率: {mid.ticks_per_beat} ticks/beat")
            output.append(f"音区移动: {self.shift_amount} 半音")
            output.append(f"BPM速度: {self.bpm}")
            output.append(f"子程序ID: S{self.subroutine_id}")
            output.append("=" * 50)
            
            # 转换数据
            converted_data = self.convert_to_keyboard(mid)
            output.extend(converted_data)
            
            # 显示结果
            self.preview.delete(1.0, tk.END)
            self.preview.insert(tk.END, "\n".join(output))
            
            self.raw_data = converted_data
            self.num_events = len(converted_data)
            
            # 启用按钮
            self.btn_save.configure(state="normal")
            self.btn_compress.configure(state="normal")
            self.btn_verify.configure(state="disabled")
            self.btn_save_workshop.configure(state="disabled")
            
            # 统计信息
            num_notes = len([e for e in converted_data if '.' in e and float(e.split('.')[0]) < 66])
            num_rests = len(converted_data) - num_notes
            self.preview.insert(tk.END, f"\n\n事件统计: 总事件数={len(converted_data)}, 音符事件={num_notes}, 空拍事件={num_rests}")
            
        except Exception as e:
            error_msg = f"转换过程中出错:\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("转换错误", error_msg)
    
    def convert_to_keyboard(self, mid):
        """转换MIDI为键盘事件"""
        events = []
        tempo = 500000
        current_abs_tick = 0
        ticks_per_beat = mid.ticks_per_beat
        
        for track_index, track in enumerate(mid.tracks):
            if track_index not in self.selected_tracks:
                continue
                
            current_abs_tick = 0
            for msg in track:
                current_abs_tick += msg.time
                
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    events.append((current_abs_tick, "note_on", msg.note))
                
                if msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    events.append((current_abs_tick, "note_off", msg.note))
        
        events.sort(key=lambda x: x[0])
        
        timed_events = []
        for abs_tick, event_type, note in events:
            seconds = mido.tick2second(abs_tick, ticks_per_beat, tempo)
            note += self.shift_amount
            if note < 36:
                note = 36
            if note > 100:
                note = 100
            timed_events.append((seconds, event_type, note))
        
        active_notes = {}
        notes_to_play = []
        
        max_event_time = max(timed_events, key=lambda x: x[0])[0] if timed_events else 0.0
        for time, event_type, note in timed_events:
            if event_type == "note_on":
                if note in active_notes:
                    start_time, _ = active_notes[note]
                    notes_to_play.append((start_time, time, note))
                active_notes[note] = (time, None)
            elif event_type == "note_off":
                if note in active_notes:
                    start_time, _ = active_notes[note]
                    notes_to_play.append((start_time, time, note))
                    del active_notes[note]
        
        for note, (start_time, _) in active_notes.items():
            notes_to_play.append((start_time, max_event_time, note))
        
        result = []
        events_to_emit = []
        
        for start, end, note in notes_to_play:
            duration = end - start
            events_to_emit.append((start, "note_start", note, duration))
        
        events_to_emit.sort(key=lambda x: x[0])
        
        last_time = 0.0
        max_time = events_to_emit[-1][0] if events_to_emit else 0.0
        
        if events_to_emit:
            first_time = events_to_emit[0][0]
            if first_time > 0:
                # 空拍改为 66 + 空拍时间（秒），格式化为两位小数
                gap_seconds = first_time
                result.append(f"{66 + gap_seconds:.2f}")
                last_time = first_time
        
        for time, event_type, note, duration in events_to_emit:
            if time > last_time:
                gap_seconds = time - last_time
                # 空拍改为 66 + 空拍时间（秒），格式化为两位小数
                result.append(f"{66 + gap_seconds:.2f}")
            
            key_num = note - 35
            duration_ms = int(duration * 1000)
            # 音符事件格式化为两位小数
            result.append(f"{key_num}.{duration_ms:02d}")
            last_time = time
        
        if last_time < max_time:
            final_gap = max_time - last_time
            result.append(f"{66 + final_gap:.2f}")

        for _ in range(2):
            result.append("0.00")  # 这里也改为两位小数

        return result
    
    def combine_numbers(self, num1, num2):
        """将两个数字合并成一个六位数"""
        # 移除小数点
        str1 = f"{num1:.2f}".replace(".", "")
        str2 = f"{num2:.2f}".replace(".", "")
        
        # 确保每个字符串是4位数
        if len(str1) < 4:
            str1 = "0" + str1
        if len(str2) < 4:
            str2 = "0" + str2
            
        # 合并成一个8位数
        combined_str = str1 + str2
        return int(combined_str)
    
    def split_combined_number(self, combined_num):
        """将合并的数字拆分成两个原始数字"""
        # 将数字转换为字符串
        num_str = str(combined_num)
        
        # 确保字符串长度是8位
        if len(num_str) < 8:
            num_str = "0" * (8 - len(num_str)) + num_str
        
        # 拆分字符串
        str1 = num_str[:4]
        str2 = num_str[4:]
        
        # 将字符串转换为数字
        num1 = float(str1[:2] + "." + str1[2:])
        num2 = float(str2[:2] + "." + str2[2:])
        
        return num1, num2
    
    def compress_vectors(self):
        """压缩向量"""
        if not hasattr(self, 'raw_data'):
            messagebox.showerror("错误", "请先转换MIDI文件")
            return
        
        try:
            # 检查是否有数据
            if not self.raw_data:
                messagebox.showerror("错误", "没有可压缩的数据，请先成功转换MIDI文件")
                return
            
            self.compressed_text.delete(1.0, tk.END)
            self.compressed_text.insert(tk.END, "原始数值前10个:\n")
            for i, val_str in enumerate(self.raw_data[:10]):
                val = float(val_str)
                if val >= 66:
                    event_type = f"空拍: {val-66:.2f}秒"
                else:
                    key_part = int(val)
                    ms_part = int(round((val - key_part) * 1000))
                    event_type = f"音符: 键{key_part} 持续{ms_part}ms"
                self.compressed_text.insert(tk.END, f"[{i}] {val_str} ({event_type})\n")
            
            # 合并每两个数字
            self.compressed_text.insert(tk.END, "\n合并数字:\n")
            combined_numbers = []
            for i in range(0, len(self.raw_data), 2):
                if i + 1 < len(self.raw_data):
                    num1 = float(self.raw_data[i])
                    num2 = float(self.raw_data[i + 1])
                    combined_num = self.combine_numbers(num1, num2)
                    combined_numbers.append(combined_num)
                    
                    # 显示合并信息
                    if num1 >= 66:
                        event_type1 = f"空拍: {num1-66:.2f}秒"
                    else:
                        key_part1 = int(num1)
                        ms_part1 = int(round((num1 - key_part1) * 1000))
                        event_type1 = f"音符: 键{key_part1} 持续{ms_part1}ms"
                    
                    if num2 >= 66:
                        event_type2 = f"空拍: {num2-66:.2f}秒"
                    else:
                        key_part2 = int(num2)
                        ms_part2 = int(round((num2 - key_part2) * 1000))
                        event_type2 = f"音符: 键{key_part2} 持续{ms_part2}ms"
                    
                    self.compressed_text.insert(tk.END, f"合并 [{i}]{num1:.2f}({event_type1}) 和 [{i+1}]{num2:.2f}({event_type2}) -> {combined_num}\n")
                else:
                    # 如果最后剩一个数字，单独处理
                    num1 = float(self.raw_data[i])
                    combined_num = self.combine_numbers(num1, 0.00)
                    combined_numbers.append(combined_num)
                    
                    if num1 >= 66:
                        event_type1 = f"空拍: {num1-66:.2f}秒"
                    else:
                        key_part1 = int(num1)
                        ms_part1 = int(round((num1 - key_part1) * 1000))
                        event_type1 = f"音符: 键{key_part1} 持续{ms_part1}ms"
                    
                    self.compressed_text.insert(tk.END, f"单独处理 [{i}]{num1:.2f}({event_type1}) -> {combined_num}\n")
            
            self.compressed_text.insert(tk.END, f"\n合并后的数字列表 (共{len(combined_numbers)}个):\n")
            for i, val in enumerate(combined_numbers[:10]):
                self.compressed_text.insert(tk.END, f"[{i}] {val}\n")
            
            # 对合并后的数字进行压缩
            compressed_strings, debug_info = self.compress_sequence(combined_numbers)
            
            self.compressed_text.insert(tk.END, "\n压缩后的字符串数组:\n")
            for i, s in enumerate(compressed_strings):
                self.compressed_text.insert(tk.END, f"[{i}] '{s}' ({len(s)}字符)\n")
            
            self.compressed_text.insert(tk.END, "\n压缩调试信息:\n")
            for i, (orig, scaled, chars) in enumerate(debug_info[:5]):
                self.compressed_text.insert(tk.END, f"事件 {i}: 原始={orig}, 缩放={scaled}, 字符='{chars}'\n")
            
            self.generate_workshop_code(compressed_strings)
            self.btn_save_workshop.configure(state="normal")
            
            self.compressed_data = compressed_strings
            self.compressed_floats = combined_numbers
            self.btn_verify.configure(state="normal")
            
            compressed_size = sum(len(s) for s in compressed_strings)
            input_size = len(combined_numbers) * 8
            
            # 修复除以零错误
            if input_size > 0:
                ratio = compressed_size / input_size
                ratio_text = f"{ratio:.2f}"
            else:
                ratio_text = "N/A (输入数据为空)"
            
            original_events = len(self.raw_data)
            self.compressed_text.insert(tk.END, f"\n压缩统计: 原始事件数={original_events}, 合并后事件数={len(combined_numbers)}, 输出大小={compressed_size}字符, 压缩率={ratio_text}")
            
        except Exception as e:
            error_msg = f"压缩过程中出错:\n{str(e)}\n\n{traceback.format_exc()}"
            logging.error(error_msg)
            messagebox.showerror("压缩错误", error_msg)
    
    def compress_sequence(self, sequence):
        """压缩序列"""
        compressed_strings = []
        debug_info = []
        current_string = ""
        
        for value in sequence:
            # 因为合并后的数字已经很大，我们使用原始值
            scaled_value = int(value)
            
            # 使用128进制编码
            digits = []
            num = scaled_value
            
            if num == 0:
                digits = [0]
            else:
                while num > 0:
                    digit = num % 128
                    digits.append(digit)
                    num = num // 128
            
            digits.reverse()
            component_chars = [WORKSHOP_CHARSET[d] for d in digits]
            component_str = ''.join(component_chars)
            
            # 不需要填充，因为合并后的数字长度不一
            debug_info.append((value, scaled_value, component_str))
            
            if len(current_string) + len(component_str) <= 128:
                current_string += component_str
            else:
                compressed_strings.append(current_string)
                current_string = component_str
        
        if current_string:
            compressed_strings.append(current_string)
        
        return compressed_strings, debug_info
    
    def verify_decompression(self):
        """验证解压缩"""
        if not hasattr(self, 'compressed_data') or not hasattr(self, 'raw_data'):
            messagebox.showerror("错误", "请先进行工坊压缩")
            return
        
        try:
            decompressed_events = self.decompress_events_fixed(self.compressed_data, len(self.raw_data))
            
            self.verification_text.delete(1.0, tk.END)
            self.verification_text.insert(tk.END, "解压缩后的事件数据:\n")
            self.verification_text.insert(tk.END, "="*50 + "\n")
            
            # 限制显示数量
            display_count = min(20, len(decompressed_events))
            for i, event in enumerate(decompressed_events[:display_count]):
                self.verification_text.insert(tk.END, f"[{i}] {event}\n")
            
            self.verification_text.insert(tk.END, "\n原始前20个事件:\n")
            for i, event in enumerate(self.raw_data[:display_count]):
                self.verification_text.insert(tk.END, f"[{i}] {event}\n")
            
            match_count = 0
            diff_positions = []
            compare_limit = min(len(self.raw_data), len(decompressed_events))
            
            for i in range(compare_limit):
                original = self.raw_data[i]
                decompressed = decompressed_events[i]
                
                # 尝试转换为浮点数比较
                try:
                    orig_float = float(original)
                    dec_float = float(decompressed)
                    
                    # 允许微小误差
                    if abs(orig_float - dec_float) < 0.001:
                        match_count += 1
                    else:
                        diff_positions.append(i)
                except:
                    diff_positions.append(i)
            
            match_rate = match_count / compare_limit if compare_limit > 0 else 0
            
            self.tabview.set("验证还原")
            
            if match_rate >= 0.95:
                messagebox.showinfo("验证成功", f"匹配率: {match_rate:.2%}")
            else:
                messagebox.showwarning("验证警告", f"匹配率较低: {match_rate:.2%}\n差异位置: {diff_positions[:10]}")
                
        except Exception as e:
            error_msg = f"解压缩验证过程中出错:\n{str(e)}\n\n{traceback.format_exc()}"
            logging.error(error_msg)
            messagebox.showerror("验证错误", error_msg)
    
    def decompress_events_fixed(self, compressed_data, num_events):
        """解压缩事件"""
        combined = ''.join(compressed_data)
        
        # 解码128进制字符串
        decoded_numbers = []
        i = 0
        while i < len(combined):
            # 由于字符长度不确定，我们需要重建数字
            value = 0
            while i < len(combined):
                char = combined[i]
                idx = WORKSHOP_CHARSET.index(char) if char in WORKSHOP_CHARSET else 0
                value = value * 128 + idx
                i += 1
                # 检查是否应该继续读取字符
                if i >= len(combined) or combined[i] in WORKSHOP_CHARSET[:10]:
                    # 如果下一个字符是较小的数字，可能表示新数字的开始
                    if i < len(combined) and combined[i] in WORKSHOP_CHARSET[:10]:
                        break
            
            decoded_numbers.append(value)
        
        # 将合并的数字拆分回两个原始数字
        decompressed_events = []
        for value in decoded_numbers:
            try:
                num1, num2 = self.split_combined_number(value)
                decompressed_events.append(f"{num1:.2f}")
                decompressed_events.append(f"{num2:.2f}")
            except:
                # 如果无法拆分，直接添加原始值
                decompressed_events.append(f"{value/10000:.2f}")
        
        # 只返回需要的事件数量
        return decompressed_events[:num_events]
    
    def generate_workshop_code(self, compressed_strings):
        """生成工坊代码"""
        if not self.current_file:
            return
        
        filename = os.path.basename(self.current_file)
        filename_without_ext = os.path.splitext(filename)[0]

        string_array = "数组(\n"
        
        for i in range(0, len(compressed_strings), 5):
            line = compressed_strings[i:i+5]
            custom_strings = [f'自定义字符串("{s}")' for s in line]
            prefix = "\t\t" if i == 0 else ",\n\t\t"
            string_array += prefix + ", ".join(custom_strings)
        string_array += ");"
        
        try:
            subroutine_id = int(self.entry_subroutine.get())
        except:
            subroutine_id = 50
        
        code = f"""规则("{filename_without_ext}")
{{
    事件
    {{
        子程序;
        S{subroutine_id};
    }}
    动作
    {{
        事件玩家.Tempo = {self.bpm};
        事件玩家.Sheet = {string_array}
    }}
}}"""
        
        self.workshop_code.delete(1.0, tk.END)
        self.workshop_code.insert(tk.END, code)
    
    def save_file(self):
        """保存结果"""
        if not hasattr(self, 'raw_data'):
            messagebox.showerror("错误", "没有可保存的数据")
            return
        
        filetypes = [("文本文件", "*.txt"), ("所有文件", "*.*")]
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=filetypes,
            title="保存转换结果"
        )
        
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(self.raw_data))
                messagebox.showinfo("保存成功", f"文件已保存至:\n{save_path}")
            except Exception as e:
                messagebox.showerror("保存失败", f"保存文件时出错:\n{str(e)}")
    
    def save_workshop_code(self):
        """保存工坊代码"""
        if not hasattr(self, 'workshop_code'):
            messagebox.showerror("错误", "没有可保存的工坊代码")
            return
        
        filetypes = [("文本文件", "*.txt"), ("所有文件", "*.*")]
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=filetypes,
            title="保存工坊代码"
        )
        
        if save_path:
            try:
                code_text = self.workshop_code.get(1.0, tk.END)
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(code_text)
                messagebox.showinfo("保存成功", f"工坊代码已保存至:\n{save_path}")
            except Exception as e:
                messagebox.showerror("保存失败", f"保存文件时出错:\n{str(e)}")


if __name__ == "__main__":
    app = MidiConverterApp()
    app.mainloop()