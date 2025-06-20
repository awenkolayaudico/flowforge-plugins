# plugins/utilities/workflow_counter_plugin.py
# --- AWAL PERBAIKAN: Menambahkan import datetime ---
from datetime import datetime
# --- AKHIR PERBAIKAN ---
from plugins.base_plugin import BasePlugin
from core.data_models import DataPayload, PluginSettingSpec
from typing import List, Any, Dict

class WorkflowCounterPlugin(BasePlugin):
    def __init__(self):
        super().__init__(
            name="Workflow Counter",
            description="Menghitung berapa kali alur kerja ini telah dijalankan."
        )

    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        # Plugin ini tidak memerlukan konfigurasi GUI
        return []

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        self._log("Memulai eksekusi Workflow Counter.")

        # Ambil state_manager dari app_settings
        state_manager = app_settings.get("state_manager")

        if state_manager:
            # Gunakan metode increment_state untuk menambah nilai variabel 'total_workflow_runs'
            total_runs = state_manager.increment_state("total_workflow_runs")
            self._log(f"Alur kerja ini telah dijalankan sebanyak {total_runs} kali.")

            # Anda juga bisa menyimpan informasi lain
            last_run_timestamp = datetime.now().isoformat()
            state_manager.set_state("last_workflow_run_timestamp", last_run_timestamp)
            self._log(f"Timestamp eksekusi terakhir disimpan: {last_run_timestamp}")
        else:
            self._log("WARNING: StateManager tidak ditemukan. Tidak dapat menghitung eksekusi.")

        return data_payload
