from plugins.base_plugin import BasePlugin
from core.data_models import DataPayload
from typing import Dict, Any, List

class HelloWorldPlugin(BasePlugin):
    def __init__(self, name: str = "Hello World Plugin", description: str = "Plugin sederhana untuk marketplace."):
        super().__init__(name, description)

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        self._log("Hello from the installed plugin!")
        return data_payload
