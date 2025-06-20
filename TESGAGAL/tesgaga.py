# plugins/utilities/always_fail_plugin.py
from plugins.base_plugin import BasePlugin
from core.data_models import DataPayload, PluginSettingSpec
from typing import Any, Dict, List, Optional

class AlwaysFailPlugin(BasePlugin):
    """
    Plugin ini dirancang untuk selalu gagal saat dijalankan, berguna untuk menguji
    alur kerja penanganan kegagalan (on_failure_steps).
    """
    def __init__(self):
        super().__init__(
            name="Always Fail Plugin",
            description="Plugin ini dirancang untuk selalu gagal saat dijalankan. Berguna untuk menguji alur kerja penanganan kegagalan."
        )
        self.settings = {
            "fail_message": "Plugin gagal sesuai permintaan."
        }

    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        """
        Mengembalikan spesifikasi untuk membangun GUI konfigurasi plugin.
        """
        return [
            PluginSettingSpec(
                field_name="fail_message",
                label="Pesan Kegagalan",
                type="str",
                default=self.settings["fail_message"],
                tooltip="Pesan yang akan dicatat saat plugin ini gagal.",
                placeholder="Plugin ini sengaja gagal."
            )
        ]

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        """
        Logika inti plugin. Plugin ini akan selalu memunculkan Exception.
        """
        fail_message = self.settings.get("fail_message", "Plugin gagal sesuai permintaan.")
        self._log(f"Memulai eksekusi 'Always Fail Plugin'.")
        self._log(f"Plugin ini akan gagal: {fail_message}")

        # Mengatur status kegagalan untuk plugin ini di DataPayload
        data_payload.last_plugin_status[self.name] = {
            "success": False,
            "error_message": fail_message
        }

        # Menggunakan error_logger untuk mencatat kegagalan
        error_logger = app_settings.get("error_logger")
        if error_logger:
            error_logger.log_error(f"Plugin '{self.name}' gagal secara sengaja: {fail_message}", exc_info=False)

        # Memunculkan Exception untuk mensimulasikan kegagalan
        raise Exception(fail_message)
