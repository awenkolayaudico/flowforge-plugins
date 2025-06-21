# plugins/content_creation/ArticleGeneratorPlugin/article_generator_plugin.py

from typing import Any, Dict, List, Optional
import os
import random
from datetime import datetime
import re
import math # Import math untuk fungsi gcd

# PENTING: Periksa apakah kita berjalan dalam konteks FlowForge atau standalone.
if __name__ == "__main__":
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.append(project_root_dir)
    try:
        from plugins.base_plugin import BasePlugin
        from core.data_models import DataPayload, PluginSettingSpec, Article
        # Mocking app_settings dan logger untuk pengujian standalone
        class MockSettingsManager:
            def get_app_setting(self, key: str, default: Any = None):
                if key == "output_folder":
                    return os.path.join(os.path.expanduser("~"), "Documents", "FlowForge_Output", "Generated_Articles")
                return default
            def get_all_design_presets(self): return []
            def get_design_preset(self, name: str): return None
        class MockApp:
            def __init__(self):
                self.settings_manager = MockSettingsManager()
                self.error_logger = type('MockErrorLogger', (), {'log_error': lambda *args, **kwargs: print(f"Mock Error: {args[0]}"), 'log_critical': lambda *args, **kwargs: print(f"Mock Critical: {args[0]}")})()
            def log_message_to_queue(self, level, source, msg):
                print(f"[{level}] [{source}] {msg}")
            def after(self, ms, func, *args):
                func(*args)
    except ImportError as e:
        print(f"Error: Modul yang dibutuhkan untuk pengujian standalone tidak ditemukan: {e}")
        sys.exit(1)
else:
    from plugins.base_plugin import BasePlugin
    from core.data_models import DataPayload, PluginSettingSpec, Article


class ArticleGeneratorPlugin(BasePlugin):
    """
    Plugin ini menghasilkan artikel berdasarkan daftar judul dan konten yang disediakan,
    dengan kontrol duplikasi dan output ke file.
    """
    def __init__(self, name: str = "Article Generator",
                 description: str = "Menghasilkan artikel dengan judul dan konten bergilir, menghindari duplikasi dalam satu siklus."):
        super().__init__(name, description)
        self._settings = {
            "list_of_titles": "",
            "list_of_articles": "",
            "number_of_articles_to_create": 1,
            "rotation_mode": "sequential", # Opsi baru: "sequential" atau "random"
            "output_destination": "folder", # Opsi baru: "folder" atau "payload_only"
            "output_folder_path": ""
        }
        self.generation_counter = 0 # Menggunakan counter ini sebagai indeks utama untuk rotasi

    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        return [
            PluginSettingSpec(
                field_name="list_of_titles",
                label="Daftar Judul (Setiap judul dipisahkan dengan '|')",
                type="multiline_text",
                default=self._settings["list_of_titles"],
                tooltip="Masukkan setiap judul dipisahkan dengan karakter pipa '|'. Contoh: Judul 1|Judul 2|Judul 3. Plugin akan memutar judul secara berurutan."
            ),
            PluginSettingSpec(
                field_name="list_of_articles",
                label="Daftar Artikel (Setiap artikel dipisahkan dengan '|')",
                type="multiline_text",
                default=self._settings["list_of_articles"],
                tooltip="Masukkan setiap konten artikel dipisahkan dengan karakter pipa '|'. Contoh: Artikel A|Artikel B|Artikel C. Plugin akan memutar artikel secara berurutan."
            ),
            PluginSettingSpec(
                field_name="number_of_articles_to_create",
                label="Jumlah Artikel yang Akan Dibuat",
                type="int",
                default=self._settings["number_of_articles_to_create"],
                tooltip="Jumlah total artikel yang ingin Anda hasilkan dalam eksekusi ini. Plugin akan memutar judul/artikel jika diperlukan."
            ),
            # Opsi baru: Mode Rotasi
            PluginSettingSpec(
                field_name="rotation_mode",
                label="Mode Rotasi Judul & Artikel",
                type="dropdown",
                options=["sequential", "random"],
                default=self._settings["rotation_mode"],
                tooltip="Pilih 'Berurutan' untuk pasangan sinkron (J1-A1, J2-A2, dst.) atau 'Acak' untuk pasangan acak."
            ),
            # Opsi baru: Tujuan Output
            PluginSettingSpec(
                field_name="output_destination",
                label="Tujuan Output Artikel",
                type="dropdown",
                options=["folder", "payload_only"],
                default=self._settings["output_destination"],
                tooltip="Pilih 'Folder' untuk menyimpan artikel ke file atau 'Hanya Payload' untuk memproses di plugin selanjutnya."
            ),
            PluginSettingSpec(
                field_name="output_folder_path",
                label="Folder untuk Menyimpan Artikel",
                type="folderpath",
                default=self._settings["output_folder_path"],
                tooltip="Pilih folder di mana artikel yang dihasilkan akan disimpan sebagai file teks. (Hanya jika Tujuan Output: Folder)"
            )
        ]

    def validate_settings(self) -> bool:
        titles_raw = self.settings.get("list_of_titles", "").strip()
        articles_raw = self.settings.get("list_of_articles", "").strip()
        num_to_create = self.settings.get("number_of_articles_to_create", 0)
        rotation_mode = self.settings.get("rotation_mode")
        output_destination = self.settings.get("output_destination")
        output_folder = self.settings.get("output_folder_path", "").strip()

        titles = [t.strip() for t in titles_raw.split('|') if t.strip()]
        articles_content = [a.strip() for a in articles_raw.split('|') if a.strip()]

        if not titles:
            self._log("Validation Error: Daftar judul tidak boleh kosong. Gunakan format 'Judul1|Judul2'.")
            return False
        if not articles_content:
            self._log("Validation Error: Daftar artikel tidak boleh kosong. Gunakan format 'Artikel1|Artikel2'.")
            return False
        if num_to_create <= 0:
            self._log("Validation Error: Jumlah artikel yang akan dibuat harus lebih dari 0.")
            return False

        if output_destination == "folder":
            if not output_folder or not os.path.isdir(output_folder):
                self._log(f"Validation Error: Folder output tidak valid atau tidak ada: '{output_folder}'.")
                return False

        if rotation_mode not in ["sequential", "random"]:
            self._log("Validation Error: Mode rotasi tidak valid. Pilih 'sequential' atau 'random'.")
            return False

        if output_destination not in ["folder", "payload_only"]:
            self._log("Validation Error: Tujuan output tidak valid. Pilih 'folder' atau 'payload_only'.")
            return False

        self._log("Pengaturan plugin Article Generator divalidasi dan valid.")
        return True

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        self._log("Memulai eksekusi plugin 'Article Generator'.")

        titles = [t.strip() for t in self.settings.get("list_of_titles").split('|') if t.strip()]
        articles_content = [a.strip() for a in self.settings.get("list_of_articles").split('|') if a.strip()]
        num_to_create = self.settings.get("number_of_articles_to_create")
        rotation_mode = self.settings.get("rotation_mode")
        output_destination = self.settings.get("output_destination")
        output_folder = self.settings.get("output_folder_path")

        if not titles or not articles_content:
            self._log("Daftar judul atau artikel kosong. Tidak ada artikel yang dihasilkan.")
            data_payload.last_plugin_status[self.name] = {"success": False, "error_message": "Daftar judul atau artikel kosong."}
            return data_payload

        # Reset generation_counter setiap kali run dipanggil untuk memastikan mulai dari awal
        self.generation_counter = 0

        while self.generation_counter < num_to_create:
            title_to_use = ""
            article_to_use = ""

            if rotation_mode == "sequential":
                # Rotasi berurutan sinkron
                title_to_use = titles[self.generation_counter % len(titles)]
                article_to_use = articles_content[self.generation_counter % len(articles_content)]
            elif rotation_mode == "random":
                # Rotasi acak
                title_to_use = random.choice(titles)
                article_to_use = random.choice(articles_content)

            article_id = f"gen_art_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{self.generation_counter}"
            new_article_data = Article(
                id=article_id,
                title=title_to_use,
                raw_content=article_to_use,
                filtered_content=article_to_use
            )
            data_payload.articles.append(new_article_data)

            # --- Proses Output ---
            if output_destination == "folder":
                sanitized_title = re.sub(r'[<>:"/\\|?*]', '_', title_to_use)
                sanitized_title = re.sub(r'\s+', '_', sanitized_title)
                sanitized_title = re.sub(r'__+', '_', sanitized_title).strip('_')
                if not sanitized_title:
                    sanitized_title = "untitled_article"

                filename = f"{sanitized_title}_{self.generation_counter+1}.txt"
                file_path = os.path.join(output_folder, filename)
                try:
                    os.makedirs(output_folder, exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(f"Judul: {title_to_use}\n\n")
                        f.write(article_to_use)
                    self._log(f"Artikel baru '{title_to_use}' disimpan ke: {file_path}")
                except Exception as e:
                    self._log(f"Error menyimpan artikel '{title_to_use}' ke file: {e}")
                    app_settings.get("error_logger").log_error(
                        f"Plugin '{self.name}' gagal menyimpan artikel '{title_to_use}' ke file: {e}", exc_info=True
                    )
            else: # output_destination == "payload_only"
                self._log(f"Artikel '{title_to_use}' dihasilkan dan ditambahkan ke payload (tidak disimpan ke folder).")
            # --- Akhir Proses Output ---

            self._log(f"Artikel dihasilkan: '{title_to_use}' dengan Artikel (Indeks Judul: {self.generation_counter % len(titles)}, Indeks Artikel: {self.generation_counter % len(articles_content)}) ({self.generation_counter + 1}/{num_to_create}).")

            # Majukan counter generasi untuk iterasi berikutnya
            self.generation_counter += 1

        self._log(f"Selesai eksekusi plugin 'Article Generator'. Total {self.generation_counter} artikel dihasilkan.")
        data_payload.last_plugin_status[self.name] = {"success": True, "message": f"{self.generation_counter} artikel dihasilkan."}
        return data_payload

# Contoh penggunaan standalone untuk pengujian
if __name__ == "__main__":
    print("--- Pengujian Plugin Article Generator (Standalone) ---")
    mock_app = MockApp()
    plugin = ArticleGeneratorPlugin()
    plugin.set_app_services(mock_app, mock_app.settings_manager, mock_app.error_logger)

    # Contoh pengaturan
    output_test_folder = os.path.join(os.path.expanduser("~"), "Documents", "FlowForge_Output", "Generated_Articles_Test")
    os.makedirs(output_test_folder, exist_ok=True)

    # --- Skenario 1: Berurutan, Output ke Folder, Buat 100 Artikel ---
    print("\n--- Skenario 1: Berurutan, Output ke Folder, Buat 100 Artikel ---")
    plugin.settings = {
        "list_of_titles": "J1|J2|J3|J4|J5|J6",
        "list_of_articles": "A1|A2|A3|A4|A5|A6",
        "number_of_articles_to_create": 100,
        "rotation_mode": "sequential",
        "output_destination": "folder",
        "output_folder_path": output_test_folder
    }
    initial_payload = DataPayload()
    updated_payload = plugin.run(initial_payload, {"app_instance": mock_app, "error_logger": mock_app.error_logger})
    print(f"Total Artikel Dihasilkan: {len(updated_payload.articles)}. (Cek folder '{output_test_folder}')")


    # --- Skenario 2: Acak, Output Hanya Payload, Buat 10 Artikel ---
    print("\n--- Skenario 2: Acak, Output Hanya Payload, Buat 10 Artikel ---")
    plugin.settings = {
        "list_of_titles": "Judul Random A|Judul Random B|Judul Random C",
        "list_of_articles": "Isi Random X|Isi Random Y|Isi Random Z",
        "number_of_articles_to_create": 10,
        "rotation_mode": "random",
        "output_destination": "payload_only",
        "output_folder_path": "" # Tidak dipakai dalam mode ini
    }
    initial_payload = DataPayload()
    updated_payload = plugin.run(initial_payload, {"app_instance": mock_app, "error_logger": mock_app.error_logger})
    print(f"Total Artikel Dihasilkan: {len(updated_payload.articles)}. (Hanya di payload)")
    for article in updated_payload.articles: print(f"  Judul: {article.title}, Artikel: {article.raw_content[:20]}...")

    # --- Skenario 3: Berurutan, Output ke Folder, Judul 4 Artikel 2, Buat 5 Artikel ---
    print("\n--- Skenario 3: Berurutan, Output ke Folder, Judul 4 Artikel 2, Buat 5 Artikel ---")
    plugin.settings = {
        "list_of_titles": "J1|J2|J3|J4",
        "list_of_articles": "A1|A2",
        "number_of_articles_to_create": 5,
        "rotation_mode": "sequential",
        "output_destination": "folder",
        "output_folder_path": output_test_folder
    }
    initial_payload = DataPayload()
    updated_payload = plugin.run(initial_payload, {"app_instance": mock_app, "error_logger": mock_app.error_logger})
    print(f"Total Artikel Dihasilkan: {len(updated_payload.articles)}. (Cek folder '{output_test_folder}')")
    for article in updated_payload.articles: print(f"  Judul: {article.title}, Artikel: {article.raw_content}")
