# plugins/text_processing/GoogleTranslatePlugin/google_translate_plugin.py

from typing import Any, Dict, List, Optional
import os
import sys

# PENTING: Periksa apakah kita berjalan dalam konteks FlowForge atau standalone.
# Ini memastikan impor BasePlugin dan DataPayload berfungsi baik saat debugging
# atau saat diintegrasikan ke FlowForge.
if __name__ == "__main__":
    # Ini adalah mode standalone untuk pengujian. Sesuaikan path agar BasePlugin dan DataPayload ditemukan.
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.append(project_root_dir)
    try:
        from plugins.base_plugin import BasePlugin
        from core.data_models import DataPayload, PluginSettingSpec, Article
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
    except ImportError as e:
        print(f"Error: Modul yang dibutuhkan untuk pengujian standalone tidak ditemukan: {e}")
        sys.exit(1)
else:
    # Mode normal saat berjalan di FlowForge
    from plugins.base_plugin import BasePlugin
    from core.data_models import DataPayload, PluginSettingSpec, Article

# Hapus: try-except import Translator di sini.
# Import Translator akan dilakukan di dalam metode run().

class GoogleTranslatePlugin(BasePlugin):
    """
    Plugin ini menerjemahkan konten artikel dari satu bahasa ke bahasa lain
    menggunakan Google Translate (gratis, tanpa API Key).
    """
    def __init__(self, name: str = "Google Translate",
                 description: str = "Menerjemahkan teks dari artikel menggunakan Google Translate."):
        super().__init__(name, description)
        self._settings = {
            "source_language": "auto",  # Mendeteksi bahasa secara otomatis
            "target_language": "id",    # Default ke Bahasa Indonesia
            "translate_title": True,    # Opsi untuk menerjemahkan judul
            "translate_raw_content": True, # Opsi untuk menerjemahkan raw_content
            "translate_filtered_content": False, # Opsi untuk menerjemahkan filtered_content
        }
        self.translator = None # Inisialisasi translator di run() untuk penanganan kesalahan yang lebih baik.

    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        """
        Mendefinisikan spesifikasi untuk membangun GUI konfigurasi plugin ini.
        """
        return [
            PluginSettingSpec(
                field_name="source_language",
                label="Bahasa Sumber (ISO 639-1)",
                type="str",
                default=self._settings["source_language"],
                tooltip="Kode bahasa dua huruf dari teks sumber (misal: 'en', 'id'). 'auto' untuk deteksi otomatis.",
                placeholder="auto"
            ),
            PluginSettingSpec(
                field_name="target_language",
                label="Bahasa Target (ISO 639-1)",
                type="str",
                default=self._settings["target_language"],
                tooltip="Kode bahasa dua huruf yang diinginkan untuk terjemahan (misal: 'id', 'en').",
                placeholder="id",
                required=True
            ),
            PluginSettingSpec(
                field_name="translate_title",
                label="Terjemahkan Judul Artikel",
                type="bool",
                default=self._settings["translate_title"],
                tooltip="Centang untuk menerjemahkan judul setiap artikel."
            ),
            PluginSettingSpec(
                field_name="translate_raw_content",
                label="Terjemahkan Konten Mentah",
                type="bool",
                default=self._settings["translate_raw_content"],
                tooltip="Centang untuk menerjemahkan konten mentah (raw_content) setiap artikel."
            ),
            PluginSettingSpec(
                field_name="translate_filtered_content",
                label="Terjemahkan Konten Terfilter",
                type="bool",
                default=self._settings["translate_filtered_content"],
                tooltip="Centang untuk menerjemahkan konten terfilter (filtered_content) setiap artikel. Jika tidak ada, raw_content akan digunakan sebagai fallback."
            ),
        ]

    def validate_settings(self) -> bool:
        """Memvalidasi pengaturan plugin."""
        target_lang = self.settings.get("target_language")
        if not target_lang or not isinstance(target_lang, str) or len(target_lang) != 2:
            self._log("Validation Error: 'Bahasa Target' harus berupa kode ISO 639-1 dua huruf (misal: 'id').")
            return False

        if not (self.settings.get("translate_title") or self.settings.get("translate_raw_content") or self.settings.get("translate_filtered_content")):
            self._log("Validation Error: Setidaknya satu opsi terjemahan (judul, konten mentah, atau konten terfilter) harus diaktifkan.")
            return False

        self._log("Pengaturan plugin Google Translate divalidasi dan valid.")
        return True

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        self._log("Memulai eksekusi plugin 'Google Translate'.")

        # PENTING: Lakukan impor Translator di sini, di dalam metode run()
        try:
            from googletrans import Translator
            self.translator = Translator()
        except ImportError:
            self._log("ERROR: Pustaka 'googletrans' tidak ditemukan. Pastikan sudah terinstal di virtual environment plugin ini.")
            app_settings.get("error_logger").log_error(
                f"Plugin '{self.name}' gagal: Pustaka 'googletrans' tidak ditemukan.", exc_info=False
            )
            data_payload.last_plugin_status[self.name] = {"success": False, "error_message": "Pustaka 'googletrans' tidak ditemukan."}
            raise ImportError("Pustaka 'googletrans' tidak terinstal untuk Google Translate Plugin.") # Picu error agar WorkflowExecutor menangani
        except Exception as e:
            self._log(f"ERROR: Gagal menginisialisasi Translator: {e}. Terjemahan tidak dapat dilakukan.")
            app_settings.get("error_logger").log_error(
                f"Plugin '{self.name}' gagal menginisialisasi translator: {e}", exc_info=True
            )
            data_payload.last_plugin_status[self.name] = {"success": False, "error_message": f"Gagal inisialisasi translator: {e}"}
            raise # Re-raise untuk penanganan error di WorkflowExecutor

        if not data_payload.articles:
            self._log("Tidak ada artikel dalam payload untuk diterjemahkan. Melewatkan plugin.")
            data_payload.last_plugin_status[self.name] = {"success": True, "message": "Tidak ada artikel untuk diproses."}
            return data_payload

        src_lang = self.settings.get("source_language")
        dest_lang = self.settings.get("target_language")
        translate_title = self.settings.get("translate_title")
        translate_raw = self.settings.get("translate_raw_content")
        translate_filtered = self.settings.get("translate_filtered_content")

        processed_count = 0
        for i, article in enumerate(data_payload.articles):
            self._log(f"Menerjemahkan artikel '{article.title}' ({i+1}/{len(data_payload.articles)}).")

            original_title = article.title
            original_raw_content = article.raw_content
            original_filtered_content = article.filtered_content

            try:
                if translate_title and article.title:
                    translated_title = self.translator.translate(article.title, src=src_lang, dest=dest_lang).text
                    article.title = translated_title
                    self._log(f"  Judul diterjemahkan.")

                if translate_raw and article.raw_content:
                    translated_raw_content = self.translator.translate(article.raw_content, src=src_lang, dest=dest_lang).text
                    article.raw_content = translated_raw_content
                    self._log(f"  Konten mentah diterjemahkan.")

                if translate_filtered and article.filtered_content:
                    # Jika filtered_content kosong tapi opsi diaktifkan, gunakan raw_content sebagai fallback
                    text_to_translate = article.filtered_content if article.filtered_content else article.raw_content
                    if text_to_translate:
                        translated_filtered_content = self.translator.translate(text_to_translate, src=src_lang, dest=dest_lang).text
                        article.filtered_content = translated_filtered_content
                        self._log(f"  Konten terfilter diterjemahkan.")
                    else:
                        self._log("  Peringatan: Opsi terjemahkan konten terfilter aktif, tetapi tidak ada konten terfilter atau mentah. Melewatkan.")

                # Tambahkan metadata terjemahan
                article.metadata[f"translated_from_{src_lang}"] = True
                article.metadata[f"translated_to_{dest_lang}"] = True
                article.metadata["original_title"] = original_title
                article.metadata["original_raw_content"] = original_raw_content
                if original_filtered_content:
                    article.metadata["original_filtered_content"] = original_filtered_content

                processed_count += 1

            except Exception as e:
                self._log(f"ERROR: Gagal menerjemahkan artikel '{article.title}': {e}")
                app_settings.get("error_logger").log_error(
                    f"Plugin '{self.name}' gagal menerjemahkan artikel '{article.title}': {e}", exc_info=True
                )
                # Tandai artikel ini sebagai gagal diterjemahkan jika perlu, atau lanjutkan
                # untuk saat ini, kita hanya akan mencatat error dan melanjutkan ke artikel berikutnya.

        if processed_count > 0:
            self._log(f"Selesai eksekusi plugin 'Google Translate'. Total {processed_count} artikel berhasil diterjemahkan.")
            data_payload.last_plugin_status[self.name] = {"success": True, "message": f"{processed_count} artikel diterjemahkan."}
        else:
            self._log("Selesai eksekusi plugin 'Google Translate'. Tidak ada artikel yang berhasil diterjemahkan.")
            data_payload.last_plugin_status[self.name] = {"success": False, "error_message": "Tidak ada artikel yang berhasil diterjemahkan atau diproses."}

        return data_payload

# Contoh penggunaan standalone untuk pengujian
if __name__ == "__main__":
    mock_app = MockApp()
    plugin = GoogleTranslatePlugin()
    plugin.set_app_services(mock_app, mock_app.settings_manager, mock_app.error_logger)

    # Contoh payload dengan satu artikel
    sample_payload = DataPayload(articles=[
        Article(
            id="test_1",
            title="Hello World",
            raw_content="This is a test sentence for translation. How are you today?",
            filtered_content="test sentence translation today",
        ),
        Article(
            id="test_2",
            title="Beautiful Nature",
            raw_content="The sun rises in the east. Birds are singing.",
        )
    ])

    print("\n--- Pengujian Plugin Google Translate ---")
    print("Payload Awal:")
    for article in sample_payload.articles:
        print(f"  Judul: {article.title}, Raw Content: {article.raw_content}")

    # Setel pengaturan plugin untuk terjemahan
    plugin.settings = {
        "source_language": "en",
        "target_language": "fr", # Bahasa Prancis
        "translate_title": True,
        "translate_raw_content": True,
        "translate_filtered_content": False,
    }

    # Jalankan plugin
    try:
        updated_payload = plugin.run(sample_payload, {"app_instance": mock_app, "error_logger": mock_app.error_logger})
        print("\nPayload Setelah Terjemahan:")
        for article in updated_payload.articles:
            print(f"  Judul (Terjemahan): {article.title}")
            print(f"  Konten Mentah (Terjemahan): {article.raw_content}")
            print(f"  Metadata: {article.metadata}")
            print("-" * 20)
        print(f"Status Plugin: {updated_payload.last_plugin_status.get(plugin.name)}")

    except Exception as e:
        print(f"\nPengujian gagal karena error: {e}")
