# plugins/audio_playback/MP3PlayerPlugin/mp3_player_plugin.py

from typing import Any, Dict, List, Optional
import os
import sys
import time
import random
import threading

# Import GUI components
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

# PENTING: Periksa apakah kita berjalan dalam konteks FlowForge atau standalone.
if __name__ == "__main__":
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.append(project_root_dir)
    try:
        from plugins.base_plugin import BasePlugin
        from core.data_models import DataPayload, PluginSettingSpec, ArticleData, CustomAssetCategory
        from app.gui.utils import ToolTip
        # Mocking app_settings dan logger untuk pengujian standalone
        class MockSettingsManager:
            def __init__(self):
                self._custom_asset_categories = {
                    "Efek Suara": CustomAssetCategory(name='Efek Suara', folder_name='sound_effects', allowed_extensions=['.mp3', '.wav']),
                    "Audio Kustom": CustomAssetCategory(name='Audio Kustom', folder_name='custom_audio', allowed_extensions=['.mp3', '.wav', '.aac'])
                }
                self._app_settings = {
                    "output_folder": os.path.join(os.path.expanduser("~"), "Documents", "FlowForge_Output"),
                    "music_tracks_folder": os.path.join(os.path.expanduser("~"), "Documents", "FlowForge_Output", "Assets", "music_tracks"),
                    "mp3_player_volume": 0.5 # Mock volume
                }
                os.makedirs(self._app_settings["music_tracks_folder"], exist_ok=True)
                os.makedirs(os.path.join(self._app_settings["output_folder"], "Assets", "sound_effects"), exist_ok=True)
                if not os.path.exists(os.path.join(self._app_settings["music_tracks_folder"], "sample_music.mp3")):
                    with open(os.path.join(self._app_settings["music_tracks_folder"], "sample_music.mp3"), "w") as f: f.write("dummy")
                if not os.path.exists(os.path.join(self._app_settings["output_folder"], "Assets", "sound_effects", "ding.wav")):
                    with open(os.path.join(os.path.join(self._app_settings["output_folder"], "Assets", "sound_effects"), "ding.wav"), "w") as f: f.write("dummy")

            def get_all_design_presets(self): return []
            def get_design_preset(self, name: str): return None
            def get_all_custom_asset_categories(self): return list(self._custom_asset_categories.values())
            def get_custom_asset_category(self, name: str): return self._custom_asset_categories.get(name)
            def get_asset_category_path(self, category_name: str):
                if category_name == "Music Tracks":
                    return self._app_settings["music_tracks_folder"]
                custom_cat = self.get_custom_asset_category(category_name)
                if custom_cat:
                    return os.path.join(self._app_settings["output_folder"], "Assets", custom_cat.folder_name)
                return os.path.join(self._app_settings["output_folder"], "Assets", "temp_unknown")
            
            def get_app_setting(self, key: str, default: Any = None): return self._app_settings.get(key, default)
            def set_app_setting(self, key: str, value: Any): self._app_settings[key] = value
            def save_app_settings(self): print("MockSettingsManager: Pengaturan disimpan.")


        class MockApp:
            def __init__(self):
                self.settings_manager = MockSettingsManager()
                self.error_logger = type('MockErrorLogger', (), {'log_error': lambda *args, **kwargs: print(f"Mock Error: {args[0]}"), 'log_critical': lambda *args, **kwargs: print(f"Mock Critical: {args[0]}")})()
                self.asset_manager_tab = type('MockAssetManagerTab', (object,), {
                    'default_asset_categories_info': {
                        "Music Tracks": {"folder_key": "music_tracks_folder", "extensions": [".mp3", ".wav", ".aac"]},
                    },
                    'show_asset_preview': lambda path, cat: print(f"Mock Preview: {path} ({cat})"),
                    'clear_preview': lambda: print("Mock Preview: Cleared")
                })()
                self.workflow_editor_tab = type('MockWorkflowEditorTab', (object,), {
                    '_open_asset_selection_dialog': lambda *args, **kwargs: []
                })()
            def log_message_to_queue(self, level, source, msg):
                print(f"[{level}] [{source}] {msg}")
            def after(self, ms, func, *args):
                func(*args)

        class MockMixerMusic:
            _loaded_path = None
            _is_playing = False
            _volume = 1.0
            def load(self, path): 
                self._loaded_path = path
                print(f"MockMixerMusic: Memuat {path}")
            def play(self): 
                self._is_playing = True
                print("MockMixerMusic: Memutar")
            def get_busy(self): return self._is_playing
            def stop(self): 
                self._is_playing = False
                print("MockMixerMusic: Menghentikan")
            def fadeout(self, ms): 
                print(f"MockMixerMusic: Fadeout {ms}ms")
                self.stop()
            def set_volume(self, volume): 
                self._volume = volume
                print(f"MockMixerMusic: Set volume to {volume}")
            def get_volume(self): return self._volume

        class MockMixer:
            def __init__(self): self.music = MockMixerMusic()
            def get_init(self): return True
            def init(self): print("MockMixer: Diinisialisasi")
        
        pygame = type('MockPygame', (), {'mixer': MockMixer()})()

    except ImportError as e:
        print(f"Error: Modul yang dibutuhkan untuk pengujian standalone tidak ditemukan: {e}")
        sys.exit(1)
else:
    from plugins.base_plugin import BasePlugin
    from core.data_models import DataPayload, PluginSettingSpec, ArticleData, CustomAssetCategory
    from app.gui.utils import ToolTip
    from tkinter import messagebox
    try:
        import pygame
    except ImportError:
        pygame = None

class MP3PlayerPlugin(BasePlugin):
    """
    Plugin ini memungkinkan pemutaran file audio (MP3, WAV, AAC) secara acak
    dari folder yang dipilih di Asset Manager, dan memiliki UI kustom sebagai tab.
    """
    def __init__(self, name: str = "MP3 Player",
                 description: str = "Memutar file audio secara acak dari folder yang dipilih."):
        super().__init__(name, description)
        self.music_category_name: str = ""
        self.current_playlist: List[str] = []
        self.current_track_index: int = -1
        self.is_playing_randomly: bool = False
        self.stop_playback_event = threading.Event()
        self.playback_thread: Optional[threading.Thread] = None
        self.playback_mode: str = "random" # Default playback mode: random

        self._current_app_instance: Any = None
        self.music_category_display_var = tk.StringVar(value="Tidak ada kategori dipilih") # Akan diinisialisasi ulang di create_tab_ui
        self.playback_mode_var = tk.StringVar(value=self.playback_mode) # Variable untuk Radiobutton
        self.volume_var = tk.DoubleVar(value=0.5) # Default volume 50% (0.0 - 1.0)

        # Hapus dua baris berikut dari __init__
        # if self.music_category_name:
        #     self._load_playlist_from_folder()
        # self._update_playlist_ui()

    def set_app_services(self, app_instance: Any, settings_manager: Any, error_logger: Any):
        self._current_app_instance = app_instance
        # Muat volume yang tersimpan saat service diset
        saved_volume = self._current_app_instance.settings_manager.get_app_setting("mp3_player_volume", 0.5)
        self.volume_var.set(saved_volume)
        if pygame and pygame.mixer.get_init():
            pygame.mixer.music.set_volume(saved_volume)
            self._log(f"Volume awal diatur ke: {saved_volume}")


    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        return []

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        self._log("Plugin 'MP3 Player' dipanggil dalam workflow. Silakan gunakan tab 'MP3 Player' untuk kontrol.")
        data_payload.last_plugin_status[self.name] = {"success": True, "message": "Plugin hanya berfungsi melalui UI tab-nya."}
        return data_payload

    def create_tab_ui(self, master_notebook: ttk.Notebook, app_instance: Any) -> Optional[ttk.Frame]:
        self._current_app_instance = app_instance

        tab_frame = ttk.Frame(master_notebook, padding=15)
        tab_frame.grid_columnconfigure(0, weight=1)
        tab_frame.grid_columnconfigure(1, weight=1)

        # Bagian Sumber Musik
        folder_selection_frame = ttk.LabelFrame(tab_frame, text="Sumber Musik", padding=10)
        folder_selection_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,10))
        folder_selection_frame.grid_columnconfigure(0, weight=1)

        self.music_category_display_var = tk.StringVar(value=self.music_category_name or "Tidak ada kategori dipilih")

        ttk.Label(folder_selection_frame, text="Kategori Musik:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        category_entry = ttk.Entry(folder_selection_frame, textvariable=self.music_category_display_var, state=DISABLED)
        category_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        select_category_btn = ttk.Button(folder_selection_frame, text="Pilih Kategori...", command=self._select_music_category, bootstyle="info")
        select_category_btn.grid(row=0, column=2, padx=5, pady=5)
        ToolTip(select_category_btn, "Pilih kategori aset (misal: 'Music Tracks', 'Efek Suara') yang berisi file audio Anda.")

        # Bagian Kontrol Pemutar
        playback_control_frame = ttk.LabelFrame(tab_frame, text="Kontrol Pemutar", padding=10)
        playback_control_frame.grid(row=1, column=0, sticky="nsew", pady=(0,10), padx=(0,5))
        playback_control_frame.grid_columnconfigure(0, weight=1)

        self.current_track_label = ttk.Label(playback_control_frame, text="Tidak ada lagu diputar", font=("Arial", 10, "bold"), bootstyle="primary")
        self.current_track_label.pack(pady=10, fill=X, padx=5)

        control_buttons_frame = ttk.Frame(playback_control_frame)
        control_buttons_frame.pack(pady=5)
        control_buttons_frame.grid_columnconfigure((0,1,2), weight=1)

        play_random_btn = ttk.Button(control_buttons_frame, text="Putar Acak", command=self._play_random_track, bootstyle="success")
        play_random_btn.grid(row=0, column=0, padx=5)
        ToolTip(play_random_btn, "Mulai memutar lagu secara acak dari kategori yang dipilih.")

        next_track_btn = ttk.Button(control_buttons_frame, text="Lagu Berikutnya", command=self._play_next_random_track, bootstyle="info")
        next_track_btn.grid(row=0, column=1, padx=5)
        ToolTip(next_track_btn, "Lewati ke lagu acak berikutnya.")

        stop_btn = ttk.Button(control_buttons_frame, text="Hentikan", command=self._stop_playback, bootstyle="danger")
        stop_btn.grid(row=0, column=2, padx=5)
        ToolTip(stop_btn, "Hentikan pemutaran audio.")

        # Playback Mode Selection
        mode_selection_frame = ttk.LabelFrame(playback_control_frame, text="Mode Pemutaran", padding=5)
        mode_selection_frame.pack(pady=10, fill=X, padx=5)
        
        random_radio = ttk.Radiobutton(mode_selection_frame, text="Acak", variable=self.playback_mode_var, value="random", command=self._on_playback_mode_change)
        random_radio.pack(side=LEFT, padx=5)
        ToolTip(random_radio, "Lagu akan diputar dalam urutan acak.")
        
        sequential_radio = ttk.Radiobutton(mode_selection_frame, text="Berurutan", variable=self.playback_mode_var, value="sequential", command=self._on_playback_mode_change)
        sequential_radio.pack(side=LEFT, padx=5)
        ToolTip(sequential_radio, "Lagu akan diputar dalam urutan playlist.")

        # --- AWAL PERBAIKAN: Kontrol Volume ---
        volume_control_frame = ttk.LabelFrame(playback_control_frame, text="Volume", padding=5)
        volume_control_frame.pack(pady=10, fill=X, padx=5)
        
        self.volume_scale = ttk.Scale(
            volume_control_frame,
            from_=0.0, to=1.0, # Pygame volume range
            orient=HORIZONTAL,
            variable=self.volume_var,
            command=self._set_volume_from_scale # Panggil metode saat slider digeser
        )
        self.volume_scale.set(self._current_app_instance.settings_manager.get_app_setting("mp3_player_volume", 0.5)) # Set nilai awal
        self.volume_scale.pack(fill=X, expand=True, padx=5, pady=5)
        ToolTip(self.volume_scale, "Geser untuk mengatur volume pemutar musik.")
        # --- AKHIR PERBAIKAN ---

        playlist_info_frame = ttk.LabelFrame(tab_frame, text="Info Playlist", padding=10)
        playlist_info_frame.grid(row=1, column=1, sticky="nsew", pady=(0,10), padx=(5,0))
        playlist_info_frame.grid_rowconfigure(0, weight=1)
        playlist_info_frame.grid_columnconfigure(0, weight=1)

        self.playlist_listbox = tk.Listbox(playlist_info_frame, font=("Arial", 9))
        self.playlist_listbox.grid(row=0, column=0, sticky="nsew")
        playlist_scrollbar = ttk.Scrollbar(playlist_info_frame, orient=VERTICAL, command=self.playlist_listbox.yview)
        playlist_scrollbar.grid(row=0, column=1, sticky="ns")
        self.playlist_listbox.config(yscrollcommand=playlist_scrollbar.set)
        
        self.playlist_listbox.bind('<<ListboxSelect>>', self._play_specific_track_from_listbox)

        master_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed_in_plugin)
        
        # Panggil ini DI SINI, setelah self.playlist_listbox dibuat
        if self.music_category_name:
            self._load_playlist_from_folder() 
        self._update_playlist_ui()
        
        return tab_frame

    def _on_playback_mode_change(self):
        """Memperbarui mode pemutaran saat radiobutton diubah."""
        self.playback_mode = self.playback_mode_var.get()
        self._log(f"Mode pemutaran diubah menjadi: {self.playback_mode}")
        # Hentikan pemutaran acak jika beralih ke sequential saat sedang random
        if self.playback_mode == "sequential" and self.is_playing_randomly:
            self._stop_playback()
            self._log("Pemutaran acak dihentikan karena mode diubah ke berurutan.")

    # --- AWAL PERBAIKAN: Metode set volume ---
    def _set_volume_from_scale(self, value: str):
        """Memperbarui volume mixer Pygame berdasarkan nilai slider."""
        try:
            vol = float(value)
            if pygame and pygame.mixer.get_init():
                pygame.mixer.music.set_volume(vol)
                self._log(f"Volume diatur ke: {vol:.2f}")
                # Simpan pengaturan volume ke app_settings
                self._current_app_instance.settings_manager.set_app_setting("mp3_player_volume", vol)
                self._current_app_instance.settings_manager.save_app_settings()
        except ValueError:
            self._log(f"Peringatan: Nilai volume tidak valid diterima: {value}")
        except Exception as e:
            self._log(f"Error mengatur volume: {e}")
            self._current_app_instance.error_logger.log_error(f"Failed to set MP3 Player volume: {e}", exc_info=True)
    # --- AKHIR PERBAIKAN ---


    def _play_specific_track_from_listbox(self, event):
        """Memutar lagu yang dipilih langsung dari listbox."""
        selected_indices = self.playlist_listbox.curselection()
        if not selected_indices:
            return

        index_to_play = selected_indices[0]
        if 0 <= index_to_play < len(self.current_playlist):
            self._stop_playback() # Hentikan pemutaran yang sedang berjalan
            self.is_playing_randomly = False # Ini bukan pemutaran acak otomatis
            self.current_track_index = index_to_play
            self._start_playback_thread(specific_track_index=index_to_play) # Mulai pemutaran pada indeks ini
        else:
            self._log(f"Peringatan: Indeks lagu yang dipilih tidak valid: {index_to_play}")


    def _on_tab_changed_in_plugin(self, event):
        """Dipanggil saat tab di notebook utama berubah."""
        selected_tab_id = event.widget.select()
        selected_tab_text = event.widget.tab(selected_tab_id, "text")
        
        if selected_tab_text == f"🔌 {self.name}":
            self._log(f"Tab '{self.name}' mendapatkan fokus. Memperbarui UI pemutar.")
            self._update_playlist_ui()

    def _open_category_picker_dialog(self, parent_dialog: Any) -> Optional[str]:
        """
        Membuka dialog sederhana untuk memilih satu kategori aset audio dari yang tersedia.
        """
        dialog = ttk.Toplevel(parent_dialog)
        dialog.title("Pilih Kategori Musik")
        dialog.transient(parent_dialog)
        dialog.grab_set()
        dialog.geometry("400x300")
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(0, weight=1)

        result_category_name: Optional[str] = None
        
        category_listbox = tk.Listbox(dialog, selectmode=tk.SINGLE, font=("Arial", 10))
        category_listbox.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        available_categories = []
        self._log("Mencari kategori bawaan yang relevan untuk audio...")
        for cat_name, cat_info in self._current_app_instance.asset_manager_tab.default_asset_categories_info.items():
            current_extensions = cat_info.get("extensions", [])
            self._log(f"  Kategori bawaan: '{cat_name}', ekstensi: {current_extensions}")
            if any(ext in ['.mp3', '.wav', '.aac'] for ext in current_extensions):
                available_categories.append(cat_name)
                self._log(f"    Menambahkan kategori bawaan '{cat_name}'")

        self._log("Mencari kategori kustom yang relevan untuk audio...")
        for custom_cat in self._current_app_instance.settings_manager.get_all_custom_asset_categories():
            self._log(f"  Kategori kustom: '{custom_cat.name}', ekstensi: {custom_cat.allowed_extensions}")
            if any(ext in ['.mp3', '.wav', '.aac'] for ext in custom_cat.allowed_extensions):
                available_categories.append(custom_cat.name)
                self._log(f"    Menambahkan kategori kustom '{custom_cat.name}'")
        
        available_categories = sorted(list(set(available_categories)))
        self._log(f"Kategori audio yang tersedia di dialog: {available_categories}")

        if not available_categories:
            category_listbox.insert(tk.END, "Tidak ada kategori audio yang tersedia.")
            category_listbox.config(state=DISABLED)
            self._log("Tidak ada kategori audio ditemukan, Listbox dialog dikunci.")
        else:
            for cat_name in available_categories:
                category_listbox.insert(tk.END, cat_name)
        
        def on_ok():
            nonlocal result_category_name
            if category_listbox.curselection():
                selected_cat = category_listbox.get(category_listbox.curselection()[0])
                result_category_name = selected_cat
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=1, column=0, sticky="e", pady=5)
        ttk.Button(button_frame, text="Pilih", command=on_ok, bootstyle="success").pack(side=LEFT, padx=5)
        ttk.Button(button_frame, text="Batal", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT)

        dialog.wait_window(dialog)
        return result_category_name

    def _select_music_category(self):
        """
        Membuka dialog pemilihan kategori aset dan mengatur folder musik berdasarkan pilihan.
        """
        selected_category_name = self._open_category_picker_dialog(self._current_app_instance)
        
        if selected_category_name:
            self.music_category_name = selected_category_name
            self.music_category_display_var.set(self.music_category_name)
            self._log(f"Kategori musik dipilih: {self.music_category_name}")
            self._load_playlist_from_folder()
        else:
            self._log("Pemilihan kategori musik dibatalkan.")
            messagebox.showwarning("Pemilihan Dibatalkan", "Anda harus memilih kategori musik untuk memutar lagu.", parent=self._current_app_instance)


    def _load_playlist_from_folder(self):
        """Memuat daftar file audio dari folder yang dipilih."""
        self.current_playlist = []
        
        if not self.music_category_name:
            self._log("Tidak ada kategori musik yang dipilih. Playlist kosong.")
            self._update_playlist_ui()
            return
        # Dapatkan jalur folder fisik dari SettingsManager
        folder_path = self._current_app_instance.settings_manager.get_asset_category_path(self.music_category_name)

        if not folder_path or not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            self._log(f"Jalur folder musik tidak valid atau tidak ada untuk kategori '{self.music_category_name}': {folder_path}")
            messagebox.showerror("Folder Tidak Ditemukan", f"Folder untuk kategori '{self.music_category_name}' tidak ditemukan atau tidak valid: {folder_path}", parent=self._current_app_instance)
            self._update_playlist_ui()
            return
        
        allowed_audio_exts = [".mp3", ".wav", ".aac"] 

        try:
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                if os.path.isfile(file_path) and os.path.splitext(filename)[1].lower() in allowed_audio_exts:
                    self.current_playlist.append(file_path)
            random.shuffle(self.current_playlist) # Awalnya selalu acak, akan diubah oleh mode
            self._log(f"Playlist dimuat: {len(self.current_playlist)} lagu dari kategori '{self.music_category_name}' ({folder_path})")
        except Exception as e:
            self._log(f"Error memuat playlist dari {folder_path}: {e}")
            self._current_app_instance.error_logger.log_error(f"Failed to load playlist for MP3 Player from {folder_path}: {e}", exc_info=True)

        self._update_playlist_ui()

    def _update_playlist_ui(self):
        """Memperbarui Listbox playlist dan label lagu yang sedang diputar."""
        self.playlist_listbox.delete(0, tk.END)
        if not self.current_playlist:
            self.current_track_label.config(text="Tidak ada lagu diputar")
            self.playlist_listbox.insert(tk.END, "Tidak ada lagu di playlist.")
            return

        for i, track_path in enumerate(self.current_playlist):
            display_name = os.path.basename(track_path)
            self.playlist_listbox.insert(tk.END, f"{i+1}. {display_name}")
        
        if self.current_track_index != -1 and 0 <= self.current_track_index < len(self.current_playlist):
            current_track_name = os.path.basename(self.current_playlist[self.current_track_index])
            self.current_track_label.config(text=f"Memutar: {current_track_name}")
            self.playlist_listbox.selection_clear(0, tk.END)
            self.playlist_listbox.selection_set(self.current_track_index)
            self.playlist_listbox.see(self.current_track_index)
        else:
            self.current_track_label.config(text="Siap memutar")

    def _play_random_track(self):
        """Memulai pemutaran lagu secara acak (dan terus-menerus acak)."""
        if not self.current_playlist:
            messagebox.showwarning("Playlist Kosong", "Tidak ada lagu di playlist. Harap pilih kategori musik yang berisi file audio.", parent=self._current_app_instance)
            self._log("Tidak dapat memutar: playlist kosong.")
            return
        
        self.playback_mode = "random" # Pastikan mode acak
        self.playback_mode_var.set("random")
        self.is_playing_randomly = True # Aktifkan flag pemutaran acak
        self._stop_playback() # Hentikan pemutaran sebelumnya
        self.stop_playback_event.clear()
        
        # Mulai putar dari indeks acak pertama
        self.current_track_index = random.randrange(len(self.current_playlist))
        self._start_playback_thread() # _playback_loop akan mengurus seleksi acak berikutnya


    def _play_next_random_track(self):
        """Memutar lagu acak atau berurutan berikutnya sesuai mode."""
        if not self.current_playlist:
            messagebox.showwarning("Playlist Kosong", "Tidak ada lagu di playlist.", parent=self._current_app_instance)
            self._log("Tidak dapat memutar lagu berikutnya: playlist kosong.")
            return
        
        self._stop_playback() # Hentikan lagu yang sedang diputar
        self.is_playing_randomly = (self.playback_mode == "random") # Atur flag berdasarkan mode
        self.stop_playback_event.clear()
        
        if self.playback_mode == "sequential":
            self.current_track_index = (self.current_track_index + 1) % len(self.current_playlist)
            self._log(f"Memutar lagu berikutnya (berurutan) pada indeks: {self.current_track_index}")
            self._play_track_at_index(self.current_track_index) # Langsung putar lagu berurutan
        else: # Random (fallback)
            self.current_track_index = random.randrange(len(self.current_playlist))
            self._log(f"Memutar lagu berikutnya (acak) pada indeks: {self.current_track_index}")
            self._start_playback_thread() # _playback_loop akan mengurus seleksi acak berikutnya


    def _start_playback_thread(self, specific_track_index: Optional[int] = None):
        """Memulai thread pemutaran audio."""
        if self.playback_thread and self.playback_thread.is_alive():
            self._log("Thread pemutaran sudah berjalan, mencoba menghentikan yang lama.")
            self.stop_playback_event.set()
            self.playback_thread.join(timeout=0.5) # Beri waktu singkat untuk berhenti
            if self.playback_thread.is_alive():
                 self._log("Peringatan: Thread pemutaran lama tidak berhenti.")
        
        self.stop_playback_event.clear()
        self.playback_thread = threading.Thread(target=self._playback_loop_handler, args=(specific_track_index,), daemon=True)
        self.playback_thread.start()
        self._log("Thread pemutaran audio dimulai.")

    def _playback_loop_handler(self, start_index: Optional[int] = None):
        """
        Handler untuk loop pemutaran utama yang memanggil _playback_loop_sequential atau _playback_loop_random.
        """
        if not pygame:
            self._log("ERROR: Pygame tidak tersedia untuk pemutaran. Menghentikan pemutaran.")
            self.is_playing_randomly = False
            self._current_app_instance.after(0, lambda: self._update_playlist_ui())
            return

        if start_index is not None:
            self._play_track_once_thread(start_index)
        else:
            if self.playback_mode == "random":
                self._playback_loop_random()
            elif self.playback_mode == "sequential":
                self._playback_loop_sequential()
        
        self.is_playing_randomly = False
        self._current_app_instance.after(0, lambda: self._update_playlist_ui())
        self._log("Thread handler pemutaran selesai.")


    def _play_track_once_thread(self, index: int):
        """Memutar lagu sekali saja di thread. Digunakan untuk klik listbox."""
        if not self.current_playlist or not (0 <= index < len(self.current_playlist)):
            self._log(f"Peringatan: Indeks {index} tidak valid untuk pemutaran satu kali.")
            return
        
        current_track_path = self.current_playlist[index]
        self.current_track_index = index # Update index di UI
        self._current_app_instance.after(0, lambda: self._update_playlist_ui())

        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            pygame.mixer.music.load(current_track_path)
            pygame.mixer.music.play()
            self._log(f"Memutar satu lagu: {os.path.basename(current_track_path)}")

            while pygame.mixer.music.get_busy() and not self.stop_playback_event.is_set():
                time.sleep(0.5)
            
            if self.stop_playback_event.is_set():
                self._log("Pemutaran satu lagu dihentikan oleh pengguna.")
        
        except pygame.error as e:
            self._log(f"Pygame Error saat memutar satu lagu {os.path.basename(current_track_path)}: {e}")
            self._current_app_instance.error_logger.log_error(f"Pygame error in MP3 Player single track: {e}", exc_info=True)
        except Exception as e:
            self._log(f"Error tidak terduga saat memutar satu lagu {os.path.basename(current_track_path)}: {e}")
            self._current_app_instance.error_logger.log_error(f"Unexpected error in MP3 Player single track: {e}", exc_info=True)
        finally:
            self._current_app_instance.after(0, lambda: self._update_playlist_ui())


    def _playback_loop_random(self):
        """Loop pemutaran acak yang berjalan di thread terpisah."""
        self._log("Memulai loop pemutaran acak.")
        while not self.stop_playback_event.is_set():
            if not self.current_playlist:
                self._log("Playlist kosong, menghentikan pemutaran acak.")
                break

            self.current_track_index = random.randrange(len(self.current_playlist))
            current_track_path = self.current_playlist[self.current_track_index]
            
            self._current_app_instance.after(0, lambda: self._update_playlist_ui()) # Update UI dari main thread

            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                pygame.mixer.music.load(current_track_path)
                pygame.mixer.music.play()
                self._log(f"Memutar: {os.path.basename(current_track_path)}")

                while pygame.mixer.music.get_busy() and not self.stop_playback_event.is_set():
                    time.sleep(0.5)

            except pygame.error as e:
                self._log(f"Pygame Error saat memutar {os.path.basename(current_track_path)}: {e}")
                self._current_app_instance.error_logger.log_error(f"Pygame error in MP3 Player: {e}", exc_info=True)
            except Exception as e:
                self._log(f"Error tidak terduga saat memutar {os.path.basename(current_track_path)}: {e}")
                self._current_app_instance.error_logger.log_error(f"Unexpected error in MP3 Player playback: {e}", exc_info=True)
                
            if self.stop_playback_event.is_set():
                break
            
            time.sleep(1) # Jeda singkat antar lagu


    def _playback_loop_sequential(self):
        """Loop pemutaran berurutan yang berjalan di thread terpisah."""
        self._log("Memulai loop pemutaran berurutan.")
        # Mulai dari indeks saat ini atau 0 jika baru dimulai
        if self.current_track_index == -1:
            self.current_track_index = 0

        while not self.stop_playback_event.is_set():
            if not self.current_playlist:
                self._log("Playlist kosong, menghentikan pemutaran berurutan.")
                break

            # Pastikan indeks dalam batas
            if self.current_track_index >= len(self.current_playlist):
                self.current_track_index = 0 # Kembali ke awal playlist

            current_track_path = self.current_playlist[self.current_track_index]
            
            self._current_app_instance.after(0, lambda: self._update_playlist_ui()) # Update UI dari main thread

            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                pygame.mixer.music.load(current_track_path)
                pygame.mixer.music.play()
                self._log(f"Memutar: {os.path.basename(current_track_path)}")

                while pygame.mixer.music.get_busy() and not self.stop_playback_event.is_set():
                    time.sleep(0.5)

            except pygame.error as e:
                self._log(f"Pygame Error saat memutar {os.path.basename(current_track_path)}: {e}")
                self._current_app_instance.error_logger.log_error(f"Pygame error in MP3 Player: {e}", exc_info=True)
            except Exception as e:
                self._log(f"Error tidak terduga saat memutar {os.path.basename(current_track_path)}: {e}")
                self._current_app_instance.error_logger.log_error(f"Unexpected error in MP3 Player playback: {e}", exc_info=True)
                
            if self.stop_playback_event.is_set():
                break
            
            self.current_track_index += 1 # Lanjut ke lagu berikutnya
            time.sleep(1) # Jeda singkat antar lagu


    def _stop_playback(self):
        """Menghentikan semua pemutaran."""
        self.stop_playback_event.set()
        if pygame and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            self._log("Pemutaran audio dihentikan.")
        self.is_playing_randomly = False
        # current_track_index tidak perlu direset ke -1 di sini agar _play_next_random_track bisa melanjutkan sequential
        self._current_app_instance.after(0, lambda: self._update_playlist_ui())

# Contoh penggunaan standalone untuk pengujian
if __name__ == "__main__":
    print("--- Pengujian Plugin MP3 Player (Standalone) ---")
    mock_app = MockApp()
    plugin = MP3PlayerPlugin()
    plugin.set_app_services(mock_app, mock_app.settings_manager, mock_app.error_logger)

    # Inisialisasi jendela Tkinter untuk menampilkan tab UI
    root = ttk.Window(themename="superhero")
    root.title("MP3 Player Standalone Test")
    root.geometry("800x600")

    notebook = ttk.Notebook(root)
    notebook.pack(fill=BOTH, expand=True)

    mp3_player_tab_frame = plugin.create_tab_ui(notebook, mock_app)
    if mp3_player_tab_frame:
        notebook.add(mp3_player_tab_frame, text="🔌 MP3 Player Test")

    root.mainloop()

    plugin._stop_playback()
    print("--- Pengujian MP3 Player Selesai ---")
