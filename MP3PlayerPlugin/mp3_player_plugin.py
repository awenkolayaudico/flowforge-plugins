# plugins/audio_playback/MP3PlayerPlugin/mp3_player_plugin.py

from typing import Any, Dict, List, Optional
import os
import sys
import time

# PENTING: Periksa apakah kita berjalan dalam konteks FlowForge atau standalone.
if __name__ == "__main__":
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.append(project_root_dir)
    try:
        from plugins.base_plugin import BasePlugin
        from core.data_models import DataPayload, PluginSettingSpec, ArticleData
        # Mocking app_settings dan logger untuk pengujian standalone
        class MockSettingsManager:
            def get_all_design_presets(self): return []
            def get_design_preset(self, name: str): return None
        class MockApp:
            def __init__(self):
                self.settings_manager = MockSettingsManager()
                self.error_logger = type('MockErrorLogger', (), {'log_error': lambda *args, **kwargs: print(f"Mock Error: {args[0]}"), 'log_critical': lambda *args, **kwargs: print(f"Mock Critical: {args[0]}")})()
            def log_message_to_queue(self, level, source, msg):
                print(f"[{level}] [{source}] {msg}")
        # Mocking pygame.mixer untuk standalone test
        class MockMixerMusic:
            def load(self, path): print(f"MockMixerMusic: Memuat {path}")
            def play(self): print("MockMixerMusic: Memutar")
            def get_busy(self): return True
            def stop(self): print("MockMixerMusic: Menghentikan")
            def fadeout(self, ms): print(f"MockMixerMusic: Fadeout {ms}ms")
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
    # Pastikan pygame diimpor di sini. Ini akan dicari di venv plugin.
    try:
        import pygame
    except ImportError:
        pygame = None # Set ke None agar bisa diperiksa nanti

class MP3PlayerPlugin(BasePlugin):
    """
    Plugin ini memungkinkan pemutaran file audio (MP3, WAV, AAC) yang dipilih
    dari Asset Manager FlowForge.
    """
    def __init__(self, name: str = "MP3 Player",
                 description: str = "Memutar file audio yang dipilih dari Asset Manager."):
        super().__init__(name, description)
        self._settings = {
            "audio_file_path": "", # Jalur file audio yang akan dipilih dari Asset Manager
            "playback_duration_seconds": 0, # Durasi putar, 0 untuk penuh
            "fade_out_duration_ms": 0 # Durasi fade out di akhir
        }

    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        """
        Mendefinisikan spesifikasi untuk membangun GUI konfigurasi plugin ini.
        """
        return [
            PluginSettingSpec(
                field_name="audio_file_path",
                label="Pilih File Audio",
                type="filepath", # Ini akan memicu dialog pemilihan aset
                asset_filter_category=["Music Tracks", "Efek Suara", "Audio Kustom"], # Contoh kategori yang diizinkan
                file_selection_type="file",
                default=self._settings["audio_file_path"],
                tooltip="Pilih file audio (MP3, WAV, AAC) dari Asset Manager.",
                required=True
            ),
            PluginSettingSpec(
                field_name="playback_duration_seconds",
                label="Durasi Putar (detik, 0=penuh)",
                type="int",
                default=self._settings["playback_duration_seconds"],
                tooltip="Durasi file audio akan diputar dalam detik. Atur ke 0 untuk memutar seluruh file."
            ),
            PluginSettingSpec(
                field_name="fade_out_duration_ms",
                label="Durasi Fade Out (ms, 0=mati langsung)",
                type="int",
                default=self._settings["fade_out_duration_ms"],
                tooltip="Durasi fade out audio di akhir pemutaran dalam milidetik. Atur ke 0 untuk mematikan langsung."
            ),
        ]

    def validate_settings(self) -> bool:
        """Memvalidasi pengaturan plugin."""
        audio_path = self.settings.get("audio_file_path")
        if not audio_path:
            self._log("Validation Error: Jalur file audio tidak boleh kosong.")
            return False
        if not os.path.exists(audio_path):
            self._log(f"Validation Error: File audio tidak ditemukan di jalur: {audio_path}")
            return False
        
        # Periksa ekstensi file
        file_ext = os.path.splitext(audio_path)[1].lower()
        if file_ext not in [".mp3", ".wav", ".aac"]:
            self._log(f"Validation Error: Hanya file MP3, WAV, atau AAC yang didukung. Ditemukan: {file_ext}")
            return False

        duration = self.settings.get("playback_duration_seconds")
        if not isinstance(duration, int) or duration < 0:
            self._log("Validation Error: Durasi putar harus angka bulat non-negatif.")
            return False

        fade_out = self.settings.get("fade_out_duration_ms")
        if not isinstance(fade_out, int) or fade_out < 0:
            self._log("Validation Error: Durasi fade out harus angka bulat non-negatif.")
            return False

        self._log("Pengaturan plugin MP3 Player divalidasi dan valid.")
        return True

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        self._log("Memulai eksekusi plugin 'MP3 Player'.")

        if pygame is None or not pygame.mixer.get_init():
            self._log("ERROR: Pygame atau Pygame mixer tidak diinisialisasi. Pastikan Pygame terinstal di virtual environment plugin ini dan mixer diinisialisasi oleh aplikasi.")
            app_settings.get("error_logger").log_error(
                f"Plugin '{self.name}' gagal: Pygame atau mixer tidak diinisialisasi.", exc_info=False
            )
            data_payload.last_plugin_status[self.name] = {"success": False, "error_message": "Pygame mixer tidak diinisialisasi."}
            raise ImportError("Pygame mixer tidak terinisialisasi untuk MP3 Player Plugin.")

        audio_path = self.settings.get("audio_file_path")
        duration = self.settings.get("playback_duration_seconds")
        fade_out = self.settings.get("fade_out_duration_ms")

        if not audio_path or not os.path.exists(audio_path):
            self._log(f"ERROR: File audio tidak valid atau tidak ditemukan: {audio_path}")
            app_settings.get("error_logger").log_error(
                f"Plugin '{self.name}' gagal: File audio tidak ditemukan di {audio_path}", exc_info=False
            )
            data_payload.last_plugin_status[self.name] = {"success": False, "error_message": "File audio tidak ditemukan."}
            return data_payload

        try:
            pygame.mixer.music.load(audio_path)
            self._log(f"Memutar audio: {os.path.basename(audio_path)}")
            pygame.mixer.music.play()

            if duration > 0:
                # Tambahkan sedikit jeda agar lagu mulai memutar sebelum timer dimulai
                time.sleep(0.1) 
                start_time = time.time()
                while time.time() - start_time < duration:
                    if not pygame.mixer.music.get_busy(): # Jika lagu sudah selesai duluan
                        break
                    time.sleep(0.1) # Cek setiap 100ms
                
                # Setelah durasi habis, lakukan fade out jika ada
                if pygame.mixer.music.get_busy() and fade_out > 0:
                    self._log(f"Melakukan fade out selama {fade_out} ms.")
                    pygame.mixer.music.fadeout(fade_out)
                    time.sleep(fade_out / 1000.0 + 0.1) # Tunggu fade out selesai + buffer
                elif pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop() # Hentikan langsung jika tidak ada fade out
                    self._log("Pemutaran dihentikan setelah durasi.")
            else: # Putar sampai selesai jika duration 0
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1) # Tunggu sampai lagu selesai
                self._log("Pemutaran selesai (full duration).")

            self._log(f"Selesai eksekusi plugin 'MP3 Player'.")
            data_payload.last_plugin_status[self.name] = {"success": True, "message": f"File '{os.path.basename(audio_path)}' berhasil diputar."}

        except Exception as e:
            self._log(f"ERROR: Terjadi kesalahan saat memutar audio: {e}")
            app_settings.get("error_logger").log_error(
                f"Plugin '{self.name}' gagal memutar audio: {e}", exc_info=True
            )
            data_payload.last_plugin_status[self.name] = {"success": False, "error_message": f"Gagal memutar audio: {e}"}
        finally:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop() # Pastikan audio berhenti sepenuhnya

        return data_payload

# Contoh penggunaan standalone untuk pengujian (Anda perlu file audio di folder yang sama)
if __name__ == "__main__":
    mock_app = MockApp()
    plugin = MP3PlayerPlugin()
    plugin.set_app_services(mock_app, mock_app.settings_manager, mock_app.error_logger)

    # Contoh penggunaan untuk pengujian. Anda perlu menempatkan file test.mp3
    # atau test.wav di folder 'plugins/audio_playback/MP3PlayerPlugin/' Anda.
    test_audio_file = os.path.join(os.path.dirname(__file__), "test_audio.mp3") # Ganti dengan nama file Anda

    if not os.path.exists(test_audio_file):
        print(f"Peringatan: File audio pengujian '{test_audio_file}' tidak ditemukan. Melewatkan pengujian standalone.")
    else:
        print(f"\n--- Pengujian Plugin MP3 Player (Standalone) ---")
        plugin.settings = {
            "audio_file_path": test_audio_file,
            "playback_duration_seconds": 5, # Putar 5 detik
            "fade_out_duration_ms": 1000 # Fade out 1 detik
        }

        try:
            updated_payload = plugin.run(DataPayload(), {"app_instance": mock_app, "error_logger": mock_app.error_logger})
            print(f"\nStatus Plugin Setelah Pengujian: {updated_payload.last_plugin_status.get(plugin.name)}")
        except Exception as e:
            print(f"\nPengujian standalone gagal karena error: {e}")
