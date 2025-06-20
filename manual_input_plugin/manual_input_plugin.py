# plugins/input_output/manual_input_plugin.py
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime

# Impor komponen inti FlowForge
from plugins.base_plugin import BasePlugin
from core.data_models import DataPayload, ArticleData, PluginSettingSpec

class ManualInputPlugin(BasePlugin):
    """
    Plugin input yang berfungsi untuk menerima teks manual dari pengguna
    dan mengubahnya menjadi sebuah ArticleData di dalam data payload.
    """
    def __init__(self):
        """
        Metode inisialisasi untuk mendefinisikan nama, deskripsi,
        dan pengaturan default untuk plugin ini.
        """
        super().__init__(
            name="Manual Input",
            description="Memasukkan teks secara manual untuk diproses dalam alur kerja."
        )
        # Pengaturan default yang akan muncul di form konfigurasi
        self.settings = {
            "input_text": "Tulis atau tempel teks Anda di sini..."
        }

    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        """
        Mendefinisikan bagaimana antarmuka pengguna (GUI) untuk konfigurasi
        plugin ini seharusnya dibangun.
        """
        return [
            PluginSettingSpec(
                field_name="input_text",
                label="Teks Masukan",
                type="multiline_text",  # Menggunakan widget teks multi-baris
                default=self.settings["input_text"],
                tooltip="Teks yang Anda masukkan di sini akan menjadi konten utama (raw_content) dari artikel baru di dalam data payload.",
                required=True
            )
        ]

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        """
        Logika utama dari plugin. Metode ini akan dieksekusi oleh WorkflowExecutor.
        """
        self._log("Memulai eksekusi plugin 'Manual Input'.")
        
        input_text = self.settings.get("input_text", "").strip()

        if not input_text:
            self._log("Peringatan: Tidak ada teks masukan yang diberikan. Plugin tidak akan membuat artikel baru.")
            # Tetap laporkan status, tetapi sebagai 'gagal' karena tidak ada output.
            data_payload.last_plugin_status[self.name] = {"success": False, "message": "Tidak ada teks masukan."}
            return data_payload

        # Membuat objek ArticleData baru dari teks yang dimasukkan
        try:
            new_article = ArticleData(
                id=f"art_{uuid.uuid4()}",
                title=f"Manual Input: {input_text[:50]}...", # Judul diambil dari 50 karakter pertama
                url=None, # Tidak ada URL untuk input manual
                raw_content=input_text,
                filtered_content="", # Dibiarkan kosong untuk diproses oleh plugin lain
                image_paths=[],
                audio_path=None,
                video_clip_path=None,
                metadata={
                    "source_plugin": self.name,
                    "scraped_at": datetime.now().isoformat()
                }
            )

            # Menambahkan artikel baru ke dalam "pembawa pesan" (DataPayload)
            data_payload.articles.append(new_article)
            self._log(f"Berhasil menambahkan artikel baru dari input manual. ID: {new_article.id}")

            # Mencatat ke database riwayat melalui layanan yang disuntikkan
            db_manager = app_settings.get("db_manager")
            if db_manager:
                db_manager.add_article_history(
                    article_id=new_article.id,
                    title=new_article.title,
                    url=new_article.url,
                    status="input_received",
                    source_plugin=self.name
                )
                self._log(f"Riwayat untuk artikel '{new_article.title}' telah dicatat di database.")
            
            # --- AWAL PERBAIKAN KRUSIAL ---
            # Kode ini wajib ada agar langkah kondisional (IF/ELSE) dapat berfungsi.
            # Ia memberitahu alur kerja bahwa plugin ini telah berhasil dijalankan.
            self._log("Menetapkan status 'success' ke True untuk plugin Manual Input.")
            data_payload.last_plugin_status[self.name] = {"success": True, "message": "Artikel berhasil dibuat dari input manual."}
            # --- AKHIR PERBAIKAN KRUSIAL ---

        except Exception as e:
            self._log(f"ERROR: Terjadi kesalahan tak terduga saat menjalankan plugin Manual Input: {e}")
            # Jika terjadi error, laporkan sebagai 'gagal'.
            data_payload.last_plugin_status[self.name] = {"success": False, "message": f"Terjadi error: {e}"}
            
            error_logger = app_settings.get("error_logger")
            if error_logger:
                error_logger.log_error(f"Plugin '{self.name}' mengalami kegagalan: {e}", exc_info=True)

        self._log("Eksekusi plugin 'Manual Input' selesai.")
        return data_payload
