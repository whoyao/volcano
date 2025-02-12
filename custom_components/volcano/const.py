"""Constants for the Volcano TTS integration."""

DOMAIN = "volcano_audio"

CONF_APPID = "appid"
CONF_ACCESS_TOKEN = "access_token"
CONF_TTS_CLUSTER = "tts_cluster"
CONF_STT_CLUSTER = "stt_cluster"
CONF_VOICE_TYPE = "voice_type"
CONF_HOST = "host_url"

DEFAULT_HOST = "openspeech.bytedance.com"
DEFAULT_VOICE_TYPE = "BV005_streaming"
DEFAULT_TTS_CLUSTER = "volcano_tts"
DEFAULT_STT_CLUSTER = "volcengine_input_common"

API_ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"