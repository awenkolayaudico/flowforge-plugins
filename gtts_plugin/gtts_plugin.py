# plugins/media_creation/gtts_plugin.py
from typing import Any, Dict, List, Optional
import os
import uuid
from gtts import gTTS
import re

import sys
if __name__ == "__main__":
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.append(project_root_dir)
    try:
        from plugins.base_plugin import BasePlugin
        from core.data_models import DataPayload, PluginSettingSpec, Article
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
        print(f"Error: Required modules for standalone testing not found: {e}")
        sys.exit(1)
else:
    from plugins.base_plugin import BasePlugin
    from core.data_models import DataPayload, PluginSettingSpec, Article

class GTTSTextToSpeechPlugin(BasePlugin):
    """
    Plugin ini mengubah teks dari artikel menjadi audio (voiceover) menggunakan Google Text-to-Speech (gTTS).
    """
    def __init__(self, name: str = "GTTS Text-to-Speech", description: str = "Mengubah teks dari artikel menjadi audio (voiceover) menggunakan Google Text-to-Speech."):
        super().__init__(name, description)
        self._settings = {
            "language": "en",  # Default bahasa Inggris, karena id mungkin tidak terdeteksi tanpa i18n
            "slow_speech": False,
            "output_audio_filename_prefix": "voiceover_",
            "output_subfolder": "audio_voiceovers"
        }

    def get_gui_config_spec(self) -> List[PluginSettingSpec]:
        """
        Mendefinisikan spesifikasi untuk membangun GUI konfigurasi plugin ini.
        """
        return [
            PluginSettingSpec(
                field_name="language",
                label="Language Code (e.g., en, id)",
                type="str", # Ubah dari dropdown ke str agar pengguna bisa mengetik atau ada default
                default=self._settings["language"],
                tooltip="Two-letter language code for Text-to-Speech voice (e.g., 'en' for English, 'id' for Indonesian)."
            ),
            PluginSettingSpec(
                field_name="slow_speech",
                label="Slow Speech",
                type="bool",
                default=self._settings["slow_speech"],
                tooltip="If checked, voice will be generated at a slower speech rate."
            ),
            PluginSettingSpec(
                field_name="output_audio_filename_prefix",
                label="Output Audio Filename Prefix",
                type="str",
                default=self._settings["output_audio_filename_prefix"],
                tooltip="Prefix to be added to the generated audio file names (e.g., 'voiceover_')."
            ),
            PluginSettingSpec(
                field_name="output_subfolder",
                label="Output Audio Subfolder",
                type="str",
                default=self._settings["output_subfolder"],
                tooltip="Name of the subfolder within the main output folder where audio files will be saved."
            )
        ]

    def run(self, data_payload: DataPayload, app_settings: Dict[str, Any]) -> DataPayload:
        self._log("Starting 'GTTS Text-to-Speech' plugin execution.")

        if not data_payload.articles:
            self._log("No articles in payload to convert to audio. Skipping plugin.")
            return data_payload

        language = self.settings.get("language")
        slow_speech = self.settings.get("slow_speech")
        output_prefix = self.settings.get("output_audio_filename_prefix")
        output_subfolder_name = self.settings.get("output_subfolder")

        main_output_folder = app_settings.get("output_folder")
        if not main_output_folder:
            self._log("Error: Main output folder not defined in app settings. Failed to generate audio.")
            if 'error_logger' in app_settings and app_settings['error_logger']:
                app_settings['error_logger'].log_error("Output folder not defined in app settings for GTTS plugin.", exc_info=False)
            return data_payload

        audio_output_folder = os.path.join(main_output_folder, output_subfolder_name)
        try:
            os.makedirs(audio_output_folder, exist_ok=True)
            self._log(f"Ensuring audio output folder exists: {audio_output_folder}")
        except Exception as e:
            self._log(f"Error: Failed to create audio output folder '{audio_output_folder}': {e}. Failed to generate audio.")
            if 'error_logger' in app_settings and app_settings['error_logger']:
                app_settings['error_logger'].log_error(f"Failed to create audio output folder '{audio_output_folder}': {e}", exc_info=True)
            return data_payload

        processed_count = 0
        for article in data_payload.articles:
            text_to_convert = article.filtered_content if article.filtered_content else article.raw_content

            if not text_to_convert or text_to_convert.isspace():
                self._log(f"Warning: Article '{article.title}' has no text to convert to audio. Skipping.")
                continue

            cleaned_text = re.sub(r'[^a-zA-Z0-9\s.,?!]', '', text_to_convert)
            cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

            if not cleaned_text:
                self._log(f"Warning: Article '{article.title}' has empty text after cleaning. Skipping audio generation.")
                continue

            try:
                tts = gTTS(text=cleaned_text, lang=language, slow=slow_speech)
                audio_filename = f"{output_prefix}{article.id}.mp3"
                audio_path = os.path.join(audio_output_folder, audio_filename)

                tts.save(audio_path)
                article.audio_path = audio_path
                self._log(f"Audio for article '{article.title}' successfully created and saved at: {audio_path}")
                processed_count += 1
            except Exception as e:
                self._log(f"Error: Failed to create audio for article '{article.title}': {e}")
                if 'error_logger' in app_settings and app_settings['error_logger']:
                    app_settings['error_logger'].log_error(f"Failed to create TTS audio for article '{article.title}': {e}", exc_info=True)

        self._log(f"Finished 'GTTS Text-to-Speech' plugin execution. Total {processed_count} audios created.")
        return data_payload

    def validate_settings(self) -> bool:
        """Memvalidasi pengaturan plugin."""
        lang = self.settings.get("language")
        prefix = self.settings.get("output_audio_filename_prefix")
        subfolder = self.settings.get("output_subfolder")

        # Validasi bahasa: Cukup pastikan string tidak kosong
        if not lang or not isinstance(lang, str) or not lang.strip():
            self._log("Validation Error: Language code cannot be empty.")
            return False

        if not prefix or not isinstance(prefix, str) or not prefix.strip():
            self._log("Validation Error: Output audio filename prefix cannot be empty.")
            return False

        if not subfolder or not isinstance(subfolder, str) or not subfolder.strip():
            self._log("Validation Error: Output audio subfolder name cannot be empty.")
            return False

        self._log("GTTS Text-to-Speech plugin settings validated and are valid.")
        return True
