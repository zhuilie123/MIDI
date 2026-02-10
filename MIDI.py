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

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Workshop character set (128 characters)
WORKSHOP_CHARSET = "0!@#$%^&*+ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzΑΒΓΔΕΖΗΘΙΚΛΜαβγδεζηθικλμΝΞΟΠΡΣΤΥΦΧΨΩνξοπρστυφχψωÀÁÂÃÄÅÆÇÈÉÊËàáâãäå"

class MidiConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MIDI Converter - BY ZHUILIE")
        
        # Set window size
        self.geometry("1000x800")
        self.minsize(900, 700)
        
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        # Initialize variables
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
        
        # Create UI
        self.create_widgets()
        self.init_audio()
        
    def create_widgets(self):
        # Set grid weights
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Main container frame
        main_container = ctk.CTkFrame(self)
        main_container.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        main_container.grid_columnconfigure(0, weight=1)
        
        # Top file selection frame
        top_frame = ctk.CTkFrame(main_container)
        top_frame.grid(row=0, column=0, padx=0, pady=5, sticky="ew")
        
        ctk.CTkLabel(top_frame, text="MIDI File:").pack(side="left", padx=(0, 5))
        self.btn_select = ctk.CTkButton(top_frame, text="Browse...", command=self.select_file, width=80)
        self.btn_select.pack(side="left", padx=(0, 10))
        
        self.file_path = ctk.CTkEntry(top_frame, height=30)
        self.file_path.pack(side="left", fill="x", expand=True, padx=(0, 0))
        self.file_path.insert(0, "")
        self.file_path.configure(state="readonly")
        
        # Pitch shift frame
        shift_frame = ctk.CTkFrame(main_container)
        shift_frame.grid(row=1, column=0, padx=0, pady=5, sticky="ew")
        shift_frame.grid_columnconfigure(4, weight=1)
        
        ctk.CTkLabel(shift_frame, text="Pitch Shift:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        self.btn_shift_down = ctk.CTkButton(shift_frame, text="↓ Down 1 Octave", 
                                           command=lambda: self.set_shift(-12), width=100)
        self.btn_shift_down.grid(row=0, column=1, padx=5, pady=5)
        
        self.btn_shift_up = ctk.CTkButton(shift_frame, text="↑ Up 1 Octave", 
                                         command=lambda: self.set_shift(12), width=100)
        self.btn_shift_up.grid(row=0, column=2, padx=5, pady=5)
        
        ctk.CTkLabel(shift_frame, text="Fine Tune:").grid(row=0, column=3, padx=(20,5), pady=5, sticky="w")
        
        self.slider_shift = ctk.CTkSlider(shift_frame, from_=-24, to=24, width=150)
        self.slider_shift.set(0)
        self.slider_shift.grid(row=0, column=4, padx=5, pady=5, sticky="ew")
        self.slider_shift.bind("<ButtonRelease-1>", self.update_shift_label)
        
        self.lbl_shift_value = ctk.CTkLabel(shift_frame, text="0 Semitones", width=60)
        self.lbl_shift_value.grid(row=0, column=5, padx=5, pady=5)
        
        # BPM and Subroutine ID frame
        info_frame = ctk.CTkFrame(main_container)
        info_frame.grid(row=2, column=0, padx=0, pady=5, sticky="ew")
        
        ctk.CTkLabel(info_frame, text="BPM Tempo:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.lbl_bpm = ctk.CTkLabel(info_frame, text="120", width=60)
        self.lbl_bpm.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(info_frame, text="Subroutine ID:").grid(row=0, column=2, padx=(20,5), pady=5, sticky="w")
        
        # Subroutine ID entry and up/down arrow buttons
        subroutine_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        subroutine_frame.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        # Up arrow button
        self.btn_sub_up = ctk.CTkButton(subroutine_frame, text="▲", width=30, height=20,
                                       command=lambda: self.change_subroutine_id(1))
        self.btn_sub_up.pack(side="top", padx=(0, 0))
        
        # Subroutine ID entry
        self.entry_subroutine = ctk.CTkEntry(subroutine_frame, width=50, height=25)
        self.entry_subroutine.insert(0, "50")
        self.entry_subroutine.pack(side="top", padx=0, pady=2)
        
        # Down arrow button
        self.btn_sub_down = ctk.CTkButton(subroutine_frame, text="▼", width=30, height=20,
                                         command=lambda: self.change_subroutine_id(-1))
        self.btn_sub_down.pack(side="top", padx=(0, 0))
        
        # Track selection frame
        track_frame = ctk.CTkFrame(main_container)
        track_frame.grid(row=3, column=0, padx=0, pady=5, sticky="ew")
        
        ctk.CTkLabel(track_frame, text="Track Selection:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        # Track checkbox container frame
        self.track_check_frame = ctk.CTkFrame(track_frame)
        self.track_check_frame.grid(row=1, column=0, columnspan=4, padx=5, pady=5, sticky="ew")
        
        # Select All/None checkbox
        self.select_all_var = tk.IntVar(value=1)
        all_cb = ctk.CTkCheckBox(track_frame, text="Select All/None", variable=self.select_all_var,
                                 command=self.toggle_select_all)
        all_cb.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        
        # Playback control frame
        control_frame = ctk.CTkFrame(main_container)
        control_frame.grid(row=4, column=0, padx=0, pady=5, sticky="ew")
        control_frame.grid_columnconfigure(3, weight=1)
        
        # Play/Pause button
        self.btn_play = ctk.CTkButton(control_frame, text="▶ Play", 
                                      command=self.toggle_play, state="disabled", width=80)
        self.btn_play.grid(row=0, column=0, padx=5, pady=5)
        
        # Stop button
        self.btn_stop = ctk.CTkButton(control_frame, text="⏹ Stop", 
                                      command=self.stop_playback, state="disabled", width=80)
        self.btn_stop.grid(row=0, column=1, padx=5, pady=5)
        
        # Progress bar label
        ctk.CTkLabel(control_frame, text="Playback Progress:").grid(row=0, column=2, padx=(20,5), pady=5)
        
        # Progress slider
        self.progress_slider = ctk.CTkSlider(control_frame, from_=0, to=100, width=200)
        self.progress_slider.set(0)
        self.progress_slider.grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        # Bind progress slider events
        self.progress_slider.bind("<ButtonPress-1>", self.on_slider_press)
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)
        
        self.lbl_progress = ctk.CTkLabel(control_frame, text="0:00 / 0:00", width=80)
        self.lbl_progress.grid(row=0, column=4, padx=5, pady=5)
        
        # Function buttons frame
        func_frame = ctk.CTkFrame(main_container)
        func_frame.grid(row=5, column=0, padx=0, pady=5, sticky="ew")
        func_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        # Combined Convert & Compress button
        self.btn_convert_compress = ctk.CTkButton(func_frame, text="Convert & Compress", 
                                                command=self.convert_and_compress, state="disabled")
        self.btn_convert_compress.grid(row=0, column=0, padx=5, pady=5, sticky="ew", columnspan=2)
        
        # Verify button (optional, can be removed if not needed)
        self.btn_verify = ctk.CTkButton(func_frame, text="Verify", 
                                       command=self.verify_decompression, state="disabled")
        self.btn_verify.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        
        # Tab container
        tabs_frame = ctk.CTkFrame(main_container)
        tabs_frame.grid(row=6, column=0, padx=0, pady=5, sticky="nsew")
        main_container.grid_rowconfigure(6, weight=1)
        
        # Create tabs - Only Workshop Code tab
        self.tabview = ctk.CTkTabview(tabs_frame)
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Add only Workshop Code tab
        self.tab_workshop = self.tabview.add("Workshop Code")
        
        # Workshop code frame
        workshop_frame = ctk.CTkFrame(self.tab_workshop)
        workshop_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.workshop_code = scrolledtext.ScrolledText(workshop_frame, height=15, bg='#2b2b2b', fg='white')
        self.workshop_code.pack(fill="both", expand=True)
        
        # Bottom buttons frame
        bottom_frame = ctk.CTkFrame(main_container)
        bottom_frame.grid(row=7, column=0, padx=0, pady=5, sticky="ew")
        bottom_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.btn_save = ctk.CTkButton(bottom_frame, text="Save Result", 
                                     command=self.save_file, state="disabled")
        self.btn_save.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        self.btn_save_workshop = ctk.CTkButton(bottom_frame, text="Save Workshop Code", 
                                              command=self.save_workshop_code, state="disabled")
        self.btn_save_workshop.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.btn_exit = ctk.CTkButton(bottom_frame, text="Exit", 
                                     command=self.destroy)
        self.btn_exit.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        
    def change_subroutine_id(self, delta):
        """Change subroutine ID"""
        try:
            current = int(self.entry_subroutine.get())
            new_value = current + delta
            if 1 <= new_value <= 99:  # Limit to 1-99 range
                self.entry_subroutine.delete(0, tk.END)
                self.entry_subroutine.insert(0, str(new_value))
                self.subroutine_id = new_value
        except ValueError:
            self.entry_subroutine.delete(0, tk.END)
            self.entry_subroutine.insert(0, "50")
            self.subroutine_id = 50
        
    def init_audio(self):
        """Initialize audio devices"""
        try:
            pygame.mixer.quit()
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.midi.init()
        except Exception as e:
            logging.error(f"Error initializing audio devices: {e}")
            
    def set_shift(self, semitones):
        """Set pitch shift amount"""
        self.shift_amount = semitones
        self.slider_shift.set(semitones)
        self.update_shift_label()
        
    def update_shift_label(self, event=None):
        """Update pitch shift display"""
        value = int(self.slider_shift.get())
        self.shift_amount = value
        self.lbl_shift_value.configure(text=f"{value} Semitones")
    
    def create_track_checkboxes(self, tracks):
        """Create track checkboxes"""
        # Clear old checkboxes
        for widget in self.track_check_frame.winfo_children():
            widget.destroy()
        
        self.track_vars = []
        self.track_checkboxes = []
        
        # Create new checkboxes
        for i, track in enumerate(tracks):
            var = tk.IntVar(value=1)
            track_name = track.name if track.name else f"Track{i+1}"
            if len(track_name) > 10:
                track_name = track_name[:8] + ".."
            
            cb = ctk.CTkCheckBox(self.track_check_frame, text=f"Track {i+1}: {track_name}", variable=var)
            cb.grid(row=i//3, column=i%3, padx=10, pady=5, sticky="w")
            
            self.track_vars.append(var)
            self.track_checkboxes.append(cb)
            
            # Bind events
            var.trace_add("write", lambda *args, idx=i: self.on_track_state_changed(idx))
    
    def on_track_state_changed(self, track_idx):
        """Track state changed"""
        if hasattr(self, 'track_states') and self.is_playing and not self.is_paused:
            is_selected = self.track_vars[track_idx].get() == 1
            self.track_states[track_idx] = is_selected
            
            if hasattr(self, 'midi_output') and self.midi_output:
                try:
                    if track_idx in self.track_channels:
                        channel = self.track_channels[track_idx]
                        if is_selected:
                            # Unmute
                            self.midi_output.write_short(0xB0 + channel, 7, 127)
                        else:
                            # Mute
                            self.midi_output.write_short(0xB0 + channel, 7, 0)
                            # Stop current notes
                            self.stop_all_notes_for_track(track_idx)
                except Exception as e:
                    logging.error(f"Failed to set track{track_idx} mute state: {e}")
    
    def stop_all_notes_for_track(self, track_idx):
        """Stop all notes for specified track"""
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
        """Toggle select all/none"""
        state = self.select_all_var.get()
        for i, (cb, var) in enumerate(zip(self.track_checkboxes, self.track_vars)):
            var.set(state)
            if hasattr(self, 'track_states'):
                self.track_states[i] = (state == 1)
    
    def select_file(self):
        """Select MIDI file"""
        filetypes = [("MIDI Files", "*.mid *.midi")]
        filepath = filedialog.askopenfilename(title="Select MIDI File", filetypes=filetypes)
        
        if filepath:
            # Update file path display
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
                # Load MIDI file
                self.midi_data = mido.MidiFile(filepath)
                
                # Create track selection
                self.create_track_checkboxes(self.midi_data.tracks)
                
                # Initialize track states
                self.track_states = {i: True for i in range(len(self.midi_data.tracks))}
                
                # Get BPM
                self.bpm = self.get_bpm_from_midi(self.midi_data)
                self.lbl_bpm.configure(text=str(self.bpm))
                
                # Calculate total duration
                self.total_playback_time = self.calculate_midi_duration(self.midi_data)
                self.ticks_per_beat = self.midi_data.ticks_per_beat
                
                # Mark MIDI as loaded
                self.midi_loaded = True
                
                # Enable buttons
                self.btn_convert_compress.configure(state="normal")
                self.btn_play.configure(state="normal")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load MIDI file:\n{str(e)}")
                self.btn_convert_compress.configure(state="disabled")
                self.btn_play.configure(state="disabled")
    
    def get_bpm_from_midi(self, mid):
        """Get BPM value from MIDI file"""
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
        """Calculate MIDI file total duration"""
        try:
            total_time = mid.length
            
            if total_time > 36000:
                total_time = self.calculate_duration_manually(mid)
            
            if total_time > 86400:
                total_time = 3600
            
            return total_time
            
        except Exception as e:
            logging.error(f"Error calculating MIDI duration: {e}")
            return 300
    
    def calculate_duration_manually(self, mid):
        """Manually calculate MIDI file duration"""
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
        """Format time display"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"
    
    def update_progress_label(self):
        """Update progress label"""
        current = self.format_time(self.current_playback_time)
        total = self.format_time(self.total_playback_time) if self.total_playback_time > 0 else "0:00"
        self.lbl_progress.configure(text=f"{current} / {total}")
        
        # Only auto-update progress slider when not dragging
        if not self.seeking and self.total_playback_time > 0:
            progress = min(self.current_playback_time / self.total_playback_time, 1.0) * 100
            self.progress_slider.set(progress)
    
    def on_slider_press(self, event):
        """Start dragging slider"""
        self.seeking = True
        self.was_playing = self.is_playing and not self.is_paused
        
        # If playing, pause playback
        if self.was_playing:
            self.is_paused = True
            self.btn_play.configure(text="▶ Play")
    
    def on_slider_release(self, event):
        """End dragging slider"""
        self.seeking = False
        
        # Calculate new playback time
        progress = self.progress_slider.get() / 100.0
        new_time = progress * self.total_playback_time
        self.current_playback_time = new_time
        
        # Update display
        self.update_progress_label()
        
        # If was playing, jump to new position and continue
        if self.was_playing and self.midi_loaded:
            # Use after delay to avoid UI freezing
            self.after(100, self.restart_playback_from_position)
    
    def restart_playback_from_position(self):
        """Restart playback from new position"""
        # Stop current playback
        self.is_playing = False
        self.is_paused = False
        
        # Wait for playback thread to end
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.5)
        
        # Restart playback
        self.is_playing = True
        self.is_paused = False
        self.btn_play.configure(text="⏸ Pause")
        
        # Restart playback
        self.start_playback()
    
    def toggle_play(self):
        """Play/Pause toggle"""
        if not self.current_file:
            messagebox.showerror("Error", "Please select a MIDI file first")
            return
            
        if self.is_playing and not self.is_paused:
            # Pause playback
            self.is_paused = True
            self.btn_play.configure(text="▶ Play")
        else:
            # Start or resume playback
            if self.is_playing and self.is_paused:
                # Resume playback
                self.is_paused = False
                self.btn_play.configure(text="⏸ Pause")
            else:
                # Start playback
                self.start_playback()
    
    def start_playback(self):
        """Start playback"""
        # If already playing, resume playback
        if self.is_playing and self.is_paused:
            self.is_paused = False
            self.btn_play.configure(text="⏸ Pause")
            return
            
        # Get selected tracks
        selected_track_indices = []
        if hasattr(self, 'track_vars'):
            for i, var in enumerate(self.track_vars):
                if var.get() == 1:
                    selected_track_indices.append(i)
                    self.track_states[i] = True
                else:
                    self.track_states[i] = False
        
        if not selected_track_indices:
            messagebox.showinfo("Note", "Please select at least one track")
            return
        
        # Enable buttons
        self.btn_play.configure(text="⏸ Pause")
        self.btn_stop.configure(state="normal")
        
        # Start new thread for playback
        self.is_playing = True
        self.is_paused = False
        self.stop_event.clear()
        
        self.playback_thread = threading.Thread(target=self._play_midi_safe, 
                                              args=(selected_track_indices,),
                                              daemon=True)
        self.playback_thread.start()
    
    def _play_midi_safe(self, selected_track_indices):
        """Safe MIDI playback function"""
        try:
            # Load MIDI file
            mid = mido.MidiFile(self.current_file)
            
            # Reinitialize MIDI devices
            try:
                pygame.midi.quit()
                pygame.midi.init()
                
                # Try to get MIDI output device
                output_id = None
                for i in range(pygame.midi.get_count()):
                    info = pygame.midi.get_device_info(i)
                    if info and info[2] == 1:  # Output device
                        try:
                            self.midi_output = pygame.midi.Output(i)
                            output_id = i
                            break
                        except:
                            continue
                
                if output_id is None:
                    # Try using default device
                    try:
                        self.midi_output = pygame.midi.Output(0)
                    except Exception as e:
                        # If no device found, use virtual device
                        self.after(0, lambda: messagebox.showwarning("MIDI Warning", 
                            "No MIDI output device found, using virtual device for playback.\n"
                            "To hear sound, ensure system has MIDI synthesizer installed."))
                        # Continue execution but may have no sound
                        self.midi_output = None
                        
            except Exception as e:
                logging.error(f"Failed to initialize MIDI devices: {e}")
                self.midi_output = None
            
            # Collect all MIDI events
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
            
            # Sort by time
            all_events.sort(key=lambda x: x[0])
            
            if not all_events:
                self.after(0, self.stop_playback)
                return
            
            # Calculate total time
            max_tick = all_events[-1][0]
            self.total_playback_time = mido.tick2second(max_tick, ticks_per_beat, 500000)
            
            # Adjust starting position based on current progress
            start_index = 0
            if self.current_playback_time > 0:
                for i, (tick, msg, track_idx, tempo) in enumerate(all_events):
                    event_time = mido.tick2second(tick, ticks_per_beat, tempo)
                    if event_time >= self.current_playback_time:
                        start_index = i
                        break
            
            # Initialize track channels
            self.track_channels = {}
            self.active_notes = {}
            
            channel = 0
            for track_idx in selected_track_indices:
                self.track_channels[track_idx] = channel
                self.active_notes[track_idx] = []
                
                if self.midi_output:
                    try:
                        # Set channel volume
                        self.midi_output.write_short(0xB0 + channel, 7, 127)  # Volume
                        self.midi_output.write_short(0xB0 + channel, 10, 64)  # Pan
                    except:
                        pass
                
                channel += 1
                if channel >= 16:  # MIDI has only 16 channels
                    channel = 0
            
            # Start playback
            start_time = time.time() - self.current_playback_time
            last_update_time = time.time()
            event_index = start_index
            
            while self.is_playing and event_index < len(all_events) and not self.stop_event.is_set():
                if self.is_paused:
                    time.sleep(0.1)
                    continue
                
                current_time = time.time() - start_time
                
                # Process all events that should occur at this time point
                while (event_index < len(all_events) and 
                       mido.tick2second(all_events[event_index][0], ticks_per_beat, all_events[event_index][3]) <= current_time):
                    
                    tick, msg, track_idx, tempo = all_events[event_index]
                    
                    if self.track_states.get(track_idx, True):
                        try:
                            if self.midi_output:
                                if msg.type == 'note_on' and msg.velocity > 0:
                                    # Apply pitch shift
                                    note = msg.note + self.shift_amount
                                    if note < 0:
                                        note = 0
                                    elif note > 127:
                                        note = 127
                                    
                                    channel = self.track_channels[track_idx]
                                    self.midi_output.note_on(note, msg.velocity, channel)
                                    self.active_notes[track_idx].append(note)
                                    
                                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                                    # Apply pitch shift
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
                            logging.error(f"Failed to send MIDI message: {e}")
                    
                    event_index += 1
                
                # Update progress
                if time.time() - last_update_time >= 0.1:
                    self.current_playback_time = current_time
                    self.after(0, self.update_progress_label)
                    last_update_time = time.time()
                
                time.sleep(0.001)
            
            # Playback complete
            if not self.stop_event.is_set():
                self.after(0, self.stop_playback)
            
        except Exception as e:
            logging.error(f"Playback failed: {e}\n{traceback.format_exc()}")
            self.after(0, self.stop_playback)
    
    def stop_playback(self):
        """Stop playback"""
        self.is_playing = False
        self.is_paused = False
        self.stop_event.set()
        
        # Stop all notes
        if hasattr(self, 'midi_output') and self.midi_output:
            try:
                # Send all note off messages
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
        
        # Wait for playback thread to end
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.5)
        
        # Reset progress
        self.current_playback_time = 0.0
        self.progress_slider.set(0)
        self.update_progress_label()
        
        # Update button states
        self.btn_play.configure(text="▶ Play")
        self.btn_stop.configure(state="disabled")
    
    def convert_and_compress(self):
        """Convert MIDI file and compress in one step"""
        if not self.current_file:
            messagebox.showerror("Error", "Please select a MIDI file first")
            return
        
        try:
            # Get subroutine ID
            try:
                self.subroutine_id = int(self.entry_subroutine.get())
                if self.subroutine_id < 1 or self.subroutine_id > 99:
                    messagebox.showwarning("Warning", "Subroutine ID must be between 1-99, reset to 50")
                    self.subroutine_id = 50
                    self.entry_subroutine.delete(0, tk.END)
                    self.entry_subroutine.insert(0, "50")
            except ValueError:
                messagebox.showwarning("Warning", "Subroutine ID must be an integer, reset to 50")
                self.subroutine_id = 50
                self.entry_subroutine.delete(0, tk.END)
                self.entry_subroutine.insert(0, "50")
            
            mid = mido.MidiFile(self.current_file)
            
            # Get selected tracks
            self.selected_tracks = []
            if hasattr(self, 'track_vars'):
                for i, var in enumerate(self.track_vars):
                    if var.get() == 1:
                        self.selected_tracks.append(i)
            
            if not self.selected_tracks:
                self.selected_tracks = list(range(len(mid.tracks)))
            
            # Step 1: Convert MIDI to keyboard events
            converted_data = self.convert_to_keyboard(mid)
            self.raw_data = converted_data
            self.num_events = len(converted_data)
            
            # Statistics
            num_notes = len([e for e in converted_data if '.' in e])
            num_rests = len([e for e in converted_data if '.' not in e])
            
            # Step 2: Compress the data
            float_list = []
            for event in converted_data:
                if '.' in event:
                    key, duration = event.split('.')
                    float_val = float(f"{key}.{duration}")
                    float_list.append(float_val)
                else:
                    float_list.append(float(event))
            
            # Compress sequence
            compressed_strings, debug_info = self.compress_sequence(float_list)
            
            # Generate workshop code
            self.generate_workshop_code(compressed_strings)
            
            # Enable buttons
            self.btn_save.configure(state="normal")
            self.btn_save_workshop.configure(state="normal")
            self.btn_verify.configure(state="normal")
            
            # Save compressed data
            self.compressed_data = compressed_strings
            self.compressed_floats = float_list
            
            # Show success message
            messagebox.showinfo("Success", f"Conversion and compression completed successfully!\n"
                                         f"Total events: {len(converted_data)}\n"
                                         f"Note events: {num_notes}\n"
                                         f"Rest events: {num_rests}\n"
                                         f"Compressed to {len(compressed_strings)} strings")
            
        except Exception as e:
            error_msg = f"Error during conversion and compression:\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("Conversion Error", error_msg)
    
    def convert_to_keyboard(self, mid):
        """Convert MIDI to keyboard events"""
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
                silence_ms = int(first_time * 1000)
                result.append(str(-silence_ms))
                last_time = first_time
        
        for time, event_type, note, duration in events_to_emit:
            if time > last_time:
                gap_ms = int((time - last_time) * 1000)
                if gap_ms > 0:
                    result.append(str(-gap_ms))
            
            key_num = note - 35
            duration_ms = int(duration * 1000)
            result.append(f"{key_num}.{duration_ms}")
            last_time = time
        
        if last_time < max_time:
            final_silence = int((max_time - last_time) * 1000)
            result.append(str(-final_silence))

        for _ in range(2):
            result.append("0.1")

        return result
    
    def compress_sequence(self, sequence):
        """Compress sequence"""
        compressed_strings = []
        debug_info = []
        current_string = ""
        
        for value in sequence:
            scaled_value = int(value * 100)
            
            if scaled_value < 0:
                scaled_value = scaled_value + 2097152
                if scaled_value < 1048576:
                    scaled_value = 1048576
                elif scaled_value > 2097151:
                    scaled_value = 2097151
            elif scaled_value > 1048575:
                scaled_value = 1048575
            
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
            
            if len(component_str) < 3:
                component_str = WORKSHOP_CHARSET[0] * (3 - len(component_str)) + component_str
            
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
        """Verify decompression"""
        if not hasattr(self, 'compressed_data') or not hasattr(self, 'raw_data'):
            messagebox.showerror("Error", "Please perform conversion and compression first")
            return
        
        try:
            decompressed_events = self.decompress_events_fixed(self.compressed_data, len(self.raw_data))
            
            match_count = 0
            diff_positions = []
            compare_limit = min(len(self.raw_data), len(decompressed_events))
            
            for i in range(compare_limit):
                original = self.raw_data[i]
                decompressed = decompressed_events[i]
                
                if '.' in original and '.' in decompressed:
                    try:
                        orig_key, orig_ms = original.split('.')
                        dec_key, dec_ms = decompressed.split('.')
                        
                        if orig_key == dec_key and abs(int(orig_ms) - int(dec_ms)) < 10:
                            match_count += 1
                        else:
                            diff_positions.append(i)
                    except:
                        diff_positions.append(i)
                elif '.' not in original and '.' not in decompressed:
                    try:
                        # Fix negative number comparison
                        orig_int = int(original)
                        dec_int = int(decompressed)
                        
                        if abs(orig_int - dec_int) < 10:
                            match_count += 1
                        else:
                            diff_positions.append(i)
                    except:
                        diff_positions.append(i)
                else:
                    diff_positions.append(i)
            
            match_rate = match_count / compare_limit if compare_limit > 0 else 0
            
            if match_rate >= 0.95:
                messagebox.showinfo("Verification Success", f"Match rate: {match_rate:.2%}")
            else:
                messagebox.showwarning("Verification Warning", f"Low match rate: {match_rate:.2%}\n"
                                                               f"Difference positions: {diff_positions[:10]}")
                
        except Exception as e:
            error_msg = f"Error during decompression verification:\n{str(e)}\n\n{traceback.format_exc()}"
            logging.error(error_msg)
            messagebox.showerror("Verification Error", error_msg)
    
    def decompress_events_fixed(self, compressed_data, num_events):
        """Decompress events - fixed negative number handling"""
        combined = ''.join(compressed_data)
        
        chunk_size = 3
        chunks = [combined[i:i+chunk_size] for i in range(0, min(len(combined), num_events * chunk_size), chunk_size)]
        
        processed_values = []
        for chunk in chunks:
            value = 0
            for char in chunk:
                idx = WORKSHOP_CHARSET.index(char) if char in WORKSHOP_CHARSET else 0
                value = value * 128 + idx
            
            # Fix negative number handling logic
            if value >= 1048576:
                # This is a negative number, need to subtract offset
                value = (value - 2097152) / 100.0
            else:
                # This is a positive number
                value = value / 100.0
            
            processed_values.append(value)
        
        decompressed_events = []
        for value in processed_values:
            if value < 0:
                # Negative number represents rest, need to convert to "-milliseconds" format
                int_val = int(round(abs(value)))
                decompressed_events.append(f"-{int_val}")
            else:
                # Positive number represents note, format is "key.milliseconds"
                key_part = int(value)
                ms_part = int(round((value - key_part) * 1000))
                decompressed_events.append(f"{key_part}.{ms_part}")
        
        return decompressed_events
    
    def generate_workshop_code(self, compressed_strings):
        """Generate workshop code"""
        if not self.current_file:
            return
        
        filename = os.path.basename(self.current_file)
        filename_without_ext = os.path.splitext(filename)[0]

        string_array = "Array(\n"
        
        for i in range(0, len(compressed_strings), 5):
            line = compressed_strings[i:i+5]
            custom_strings = [f'Custom String("{s}")' for s in line]
            prefix = "\t\t" if i == 0 else ",\n\t\t"
            string_array += prefix + ", ".join(custom_strings)
        string_array += ");"
        
        try:
            subroutine_id = int(self.entry_subroutine.get())
        except:
            subroutine_id = 50
        
        code = f"""Rule("{filename_without_ext}")
{{
    Event
    {{
        Subroutine;
        S{subroutine_id};
    }}
    Action
    {{
        Event Player.Tempo = {self.bpm};
        Event Player.Sheet = {string_array}
    }}
}}"""
        
        self.workshop_code.delete(1.0, tk.END)
        self.workshop_code.insert(tk.END, code)
    
    def save_file(self):
        """Save result"""
        if not hasattr(self, 'raw_data'):
            messagebox.showerror("Error", "No data to save")
            return
        
        filetypes = [("Text Files", "*.txt"), ("All Files", "*.*")]
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=filetypes,
            title="Save Conversion Result"
        )
        
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(self.raw_data))
                messagebox.showinfo("Save Success", f"File saved to:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Error saving file:\n{str(e)}")
    
    def save_workshop_code(self):
        """Save workshop code"""
        if not hasattr(self, 'workshop_code'):
            messagebox.showerror("Error", "No workshop code to save")
            return
        
        filetypes = [("Text Files", "*.txt"), ("All Files", "*.*")]
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=filetypes,
            title="Save Workshop Code"
        )
        
        if save_path:
            try:
                code_text = self.workshop_code.get(1.0, tk.END)
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(code_text)
                messagebox.showinfo("Save Success", f"Workshop code saved to:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Error saving file:\n{str(e)}")


if __name__ == "__main__":
    app = MidiConverterApp()
    app.mainloop()