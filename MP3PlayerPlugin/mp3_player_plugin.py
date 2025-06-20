# plugins/audio_playback/MP3PlayerPlugin/mp3_player_plugin.py

from typing import Any, Dict, List, Optional
import os
import sys
import time
import random # Tambahkan untuk pemilihan acak
import threading # Untuk menjalankan pemutaran di thread terpisah agar UI tidak freeze

# Import GUI components
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

# PENTING: Periksa apakah kita berjalan dalam konteks FlowForge atau standalone.
if __name__ == "__main__":
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.append(project_root_dir)
    try:
        from plugins.base_plugin import BasePlugin
        from core.data_models import DataPayload, PluginSettingSpec, ArticleData
        from app.gui.utils import ToolTip # Impor ToolTip untuk standalone
        # Mocking app_settings dan logger untuk pengujian standalone
        class MockSettingsManager:
            def __init__(self):
                self._custom_asset_categories = {
                    "Music Tracks": type('CustomCat', (object,), {'name': 'Music Tracks', 'folder_name': 'music_tracks', 'allowed_extensions': ['.mp3', '.wav', '.aac']})()
                }
                self._app_settings = {
                    "output_folder": os.path.join(os.path.expanduser("~"), "Documents", "VidShort_Output")
                }
            def get_all_design_presets(self): return []
            def get_design_preset(self, name: str): return None
            def get_all_custom_asset_categories(self): return list(self._custom_asset_categories.values())
            def get_custom_asset_category(self, name: str): return self._custom_asset_categories.get(name)
            def get_asset_category_path(self, category_name: str):
                if category_name == "Music Tracks":
                    return os.path.join(self._app_settings["output_folder"], "Assets", "music_tracks")
                custom_cat = self.get_custom_asset_category(category_name)
                if custom_cat:
                    return os.path.join(self._app_settings["output_folder"], "Assets", custom_cat.folder_name)
                return os.path.join(self._app_settings["output_folder"], "Assets", "temp_unknown")

        class MockApp:
            def __init__(self):
                self.settings_manager = MockSettingsManager()
                self.error_logger = type('MockErrorLogger', (), {'log_error': lambda *args, **kwargs: print(f"Mock Error: {args[0]}"), 'log_critical': lambda *args, **kwargs: print(f"Mock Critical: {args[0]}")})()
                # Mock untuk AssetManagerTab dan WorkflowEditorTab
                self.asset_manager_tab = type('MockAssetManagerTab', (object,), {
                    'default_asset_categories_info': {
                        "Music Tracks": {"folder_key": "music_tracks_folder", "extensions": [".mp3", ".wav", ".aac"]},
                    },
                    'show_asset_preview': lambda path, cat: print(f"Mock Preview: {path} ({cat})"),
                    'clear_preview': lambda: print("Mock Preview: Cleared")
                })()
                self.workflow_editor_tab = type('MockWorkflowEditorTab', (object,), {'_open_asset_selection_dialog': lambda *args, **kwargs: None})()
            def log_message_to_queue(self, level, source, msg):
                print(f"[{level}] [{source}] {msg}")
            def after(self, ms, func, *args): # Mock after for standalone
                func(*args)

        # Mocking pygame.mixer untuk standalone test
        class MockMixerMusic:
            _loaded_path = None
            _is_playing = False
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
    from core.data_models import DataPayload, PluginSettingSpec, ArticleData
    from app.gui.utils import ToolTip # Impor ToolTip untuk lingkungan normal
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
        self.music_folder_path: str = ""
        self.current_playlist: List[str] = []
        self.current_track_index: int = -1
        self.is_playing_randomly: bool = False
        self.stop_playback_event = threading.Event()
        self.playback_thread: Optional[threading.Thread] = None

        self._current_app_instance: Any = None # Akan disuntikkan dari MainApp

    # Perbaikan: Hapus panggilan super().set_app_services dari sini
    def set_app_services(self, app_instance: Any, settings_manager: Any, error_logger: Any):
        """Menyuntikkan referensi ke MainApp dan layanan inti."""
        # super().set_app_services(app_instance, settings_manager, error_logger) # Hapus baris ini
        self._current_app_instance = app_instance # Simpan referensi app_instance

    # Plugin ini tidak memerlukan konfigurasi GUI standar di Workflow Editor
    # karena ia akan memiliki tab UI-nya sendiri.
    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        return []

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        """
        Metode run() untuk plugin ini bisa kosong atau digunakan untuk memicu
        aksi default jika plugin dipanggil dalam workflow.
        Untuk konsep ini, kontrol utama ada di UI tab kustom.
        """
        self._log("Plugin 'MP3 Player' dipanggil dalam workflow. Silakan gunakan tab 'MP3 Player' untuk kontrol.")
        data_payload.last_plugin_status[self.name] = {"success": True, "message": "Plugin hanya berfungsi melalui UI tab-nya."}
        return data_payload

    # --- AWAL PERBAIKAN: Implementasi create_tab_ui ---
    def create_tab_ui(self, master_notebook: ttk.Notebook, app_instance: Any) -> Optional[ttk.Frame]:
        """
        Membuat antarmuka pengguna kustom untuk plugin MP3 Player ini.
        """
        self._current_app_instance = app_instance # Pastikan referensi app_instance tersedia

        tab_frame = ttk.Frame(master_notebook, padding=15)
        tab_frame.grid_columnconfigure(0, weight=1)
        tab_frame.grid_columnconfigure(1, weight=1) # Untuk kolom detail

        # Bagian Pemilihan Folder Musik
        folder_selection_frame = ttk.LabelFrame(tab_frame, text="Folder Musik", padding=10)
        folder_selection_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,10))
        folder_selection_frame.grid_columnconfigure(0, weight=1)

        self.music_folder_var = tk.StringVar(value=self.music_folder_path) # Inisialisasi dari atribut

        ttk.Label(folder_selection_frame, text="Jalur Folder Musik:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        folder_entry = ttk.Entry(folder_selection_frame, textvariable=self.music_folder_var, state=DISABLED) # Biasanya read-only
        folder_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        select_folder_btn = ttk.Button(folder_selection_frame, text="Pilih Folder...", command=self._select_music_folder, bootstyle="info")
        select_folder_btn.grid(row=0, column=2, padx=5, pady=5)
        ToolTip(select_folder_btn, "Pilih folder yang berisi file musik Anda dari kategori aset.")

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
        ToolTip(play_random_btn, "Mulai memutar lagu secara acak dari folder yang dipilih.")

        next_track_btn = ttk.Button(control_buttons_frame, text="Lagu Berikutnya", command=self._play_next_random_track, bootstyle="info")
        next_track_btn.grid(row=0, column=1, padx=5)
        ToolTip(next_track_btn, "Lewati ke lagu acak berikutnya.")

        stop_btn = ttk.Button(control_buttons_frame, text="Hentikan", command=self._stop_playback, bootstyle="danger")
        stop_btn.grid(row=0, column=2, padx=5)
        ToolTip(stop_btn, "Hentikan pemutaran audio.")

        # Bagian Informasi Playlist
        playlist_info_frame = ttk.LabelFrame(tab_frame, text="Info Playlist", padding=10)
        playlist_info_frame.grid(row=1, column=1, sticky="nsew", pady=(0,10), padx=(5,0))
        playlist_info_frame.grid_rowconfigure(0, weight=1)
        playlist_info_frame.grid_columnconfigure(0, weight=1)

        self.playlist_listbox = tk.Listbox(playlist_info_frame, font=("Arial", 9))
        self.playlist_listbox.grid(row=0, column=0, sticky="nsew")
        playlist_scrollbar = ttk.Scrollbar(playlist_info_frame, orient=VERTICAL, command=self.playlist_listbox.yview)
        playlist_scrollbar.grid(row=0, column=1, sticky="ns")
        self.playlist_listbox.config(yscrollcommand=playlist_scrollbar.set)
        
        # Load ulang playlist saat tab dipilih (atau ketika folder diubah)
        master_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed_in_plugin)
        
        self._update_playlist_ui() # Perbarui UI playlist saat pertama kali dimuat
        
        return tab_frame

    def _on_tab_changed_in_plugin(self, event):
        """Dipanggil saat tab di notebook utama berubah."""
        selected_tab_id = event.widget.select()
        selected_tab_text = event.widget.tab(selected_tab_id, "text")
        
        if selected_tab_text == f"🔌 {self.name}": # Jika tab ini yang aktif
            self._log(f"Tab '{self.name}' mendapatkan fokus. Memperbarui UI pemutar.")
            self._update_playlist_ui()

    def _select_music_folder(self):
        """
        Membuka dialog pemilihan folder aset yang terintegrasi dengan Asset Manager.
        """
        mock_spec = PluginSettingSpec(
            field_name="music_folder",
            label="Folder Musik",
            type="folderpath",
            asset_filter_category=["Music Tracks", "Efek Suara", "Audio Kustom"], # Kategori audio
            file_selection_type="folder", # Pilih folder, bukan file
            tooltip="Pilih folder yang berisi file musik dari Asset Manager."
        )
        
        if hasattr(self._current_app_instance, 'workflow_editor_tab') and \
           hasattr(self._current_app_instance.workflow_editor_tab, '_open_asset_selection_dialog'):
            
            selected_paths = self._current_app_instance.workflow_editor_tab._open_asset_selection_dialog(
                allowed_categories=mock_spec.asset_filter_category,
                parent_dialog=self._current_app_instance,
                selection_type="folder",
                allow_multiple_selection=False
            )
            
            if selected_paths and len(selected_paths) > 0:
                self.music_folder_path = selected_paths[0]
                self.music_folder_var.set(self.music_folder_path)
                self._log(f"Folder musik dipilih: {self.music_folder_path}")
                self._load_playlist_from_folder()
            else:
                self._log("Pemilihan folder musik dibatalkan.")
        else:
            messagebox.showwarning("Fitur Tidak Tersedia", "Dialog pemilihan aset tidak dapat dibuka. Pastikan Workflow Editor Tab terinisialisasi.", parent=self._current_app_instance) # Tambahkan parent
            self._log("Peringatan: Tidak dapat mengakses _open_asset_selection_dialog dari WorkflowEditorTab.")

    def _load_playlist_from_folder(self):
        """Memuat daftar file audio dari folder yang dipilih."""
        self.current_playlist = []
        if not self.music_folder_path or not os.path.exists(self.music_folder_path):
            self._log(f"Jalur folder musik tidak valid: {self.music_folder_path}")
            self._update_playlist_ui()
            return
        
        allowed_audio_exts = [".mp3", ".wav", ".aac"] 

        try:
            for filename in os.listdir(self.music_folder_path):
                file_path = os.path.join(self.music_folder_path, filename)
                if os.path.isfile(file_path) and os.path.splitext(filename)[1].lower() in allowed_audio_exts:
                    self.current_playlist.append(file_path)
            random.shuffle(self.current_playlist)
            self._log(f"Playlist dimuat: {len(self.current_playlist)} lagu dari {self.music_folder_path}")
        except Exception as e:
            self._log(f"Error memuat playlist dari {self.music_folder_path}: {e}")
            self._current_app_instance.error_logger.log_error(f"Failed to load playlist for MP3 Player: {e}", exc_info=True)

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
        """Memulai pemutaran lagu secara acak."""
        if not self.current_playlist:
            messagebox.showwarning("Playlist Kosong", "Tidak ada lagu di playlist. Harap pilih folder musik yang berisi file audio.", parent=self._current_app_instance)
            self._log("Tidak dapat memutar: playlist kosong.")
            return
        
        self._stop_playback()
        self.is_playing_randomly = True
        self.stop_playback_event.clear()
        self._start_playback_thread()

    def _play_next_random_track(self):
        """Memutar lagu acak berikutnya."""
        self._stop_playback()
        self.is_playing_randomly = True
        self.stop_playback_event.clear()
        self._start_playback_thread()

    def _start_playback_thread(self):
        """Memulai thread pemutaran audio."""
        if self.playback_thread and self.playback_thread.is_alive():
            self._log("Thread pemutaran sudah berjalan.")
            return
        
        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()
        self._log("Thread pemutaran acak dimulai.")

    def _playback_loop(self):
        """Loop pemutaran acak yang berjalan di thread terpisah."""
        if not pygame:
            self._log("ERROR: Pygame tidak tersedia untuk pemutaran.")
            self.is_playing_randomly = False
            return
            
        while not self.stop_playback_event.is_set() and self.is_playing_randomly:
            if not self.current_playlist:
                self._log("Playlist kosong, menghentikan pemutaran.")
                self.is_playing_randomly = False
                break

            self.current_track_index = random.randrange(len(self.current_playlist))
            current_track_path = self.current_playlist[self.current_track_index]
            
            self._current_app_instance.after(0, lambda: self._update_playlist_ui())

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
            
            time.sleep(1) 
        
        self._log("Loop pemutaran acak dihentikan.")
        self.is_playing_randomly = False
        self._current_app_instance.after(0, lambda: self._update_playlist_ui())

    def _stop_playback(self):
        """Menghentikan semua pemutaran."""
        self.stop_playback_event.set()
        if pygame and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            self._log("Pemutaran audio dihentikan.")
        self.is_playing_randomly = False
        self.current_track_index = -1
        self._update_playlist_ui()
