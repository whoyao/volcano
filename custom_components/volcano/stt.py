"""Support for Volcano speech-to-text services."""
from __future__ import annotations

import asyncio
import gzip
import json
import uuid
from typing import Any

import websockets

from homeassistant.components import stt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_APPID,
    CONF_STT_CLUSTER,
    DEFAULT_HOST,
    DOMAIN,
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Volcano STT platform."""
    provider = VolcanoSttProvider(config_entry)
    async_add_entities([provider])

# Protocol constants
PROTOCOL_VERSION = 0b0001
CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010
NO_SEQUENCE = 0b0000
NEG_SEQUENCE = 0b0010
JSON_SERIALIZATION = 0b0001
GZIP_COMPRESSION = 0b0001

class VolcanoSttProvider(stt.Provider):
    """Volcano speech-to-text provider."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize Volcano STT provider."""
        self.entry = entry
        self.ws_url = f"wss://{DEFAULT_HOST}/api/v2/asr"
        self.success_code = 1000

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return ["zh-CN", "en-US"]

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        """Return a list of supported formats."""
        return [stt.AudioFormats.WAV, stt.AudioFormats.MP3]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        """Return a list of supported codecs."""
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        """Return a list of supported bit rates."""
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        """Return a list of supported sample rates."""
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        """Return a list of supported channels."""
        return [stt.AudioChannels.CHANNEL_MONO]

    def _generate_header(
        self,
        message_type=CLIENT_FULL_REQUEST,
        message_type_specific_flags=NO_SEQUENCE,
    ) -> bytearray:
        """Generate protocol header."""
        header = bytearray()
        header_size = 1
        header.append((PROTOCOL_VERSION << 4) | header_size)
        header.append((message_type << 4) | message_type_specific_flags)
        header.append((JSON_SERIALIZATION << 4) | GZIP_COMPRESSION)
        header.append(0x00)  # reserved
        return header

    def _construct_request(self, metadata: stt.SpeechMetadata) -> dict[str, Any]:
        """Construct the request payload."""
        return {
            "app": {
                "appid": self.entry.data[CONF_APPID],
                "cluster": self.entry.data[CONF_CLUSTER],
                "token": self.entry.data[CONF_ACCESS_TOKEN],
            },
            "user": {"uid": "homeassistant"},
            "request": {
                "reqid": str(uuid.uuid4()),
                "nbest": 1,
                "workflow": "audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate",
                "show_language": False,
                "show_utterances": False,
                "result_type": "full",
                "sequence": 1,
            },
            "audio": {
                "format": metadata.format.value,
                "rate": metadata.sample_rate,
                "language": metadata.language,
                "bits": metadata.bit_rate,
                "channel": metadata.channel,
                "codec": metadata.codec.value,
            },
        }

    def _parse_response(self, res: bytes) -> dict[str, Any]:
        """Parse server response."""
        header_size = res[0] & 0x0f
        message_type = res[1] >> 4
        message_compression = res[2] & 0x0f
        payload = res[header_size * 4:]

        if message_compression == GZIP_COMPRESSION:
            payload = gzip.decompress(payload)

        if message_type == 0x09:  # SERVER_FULL_RESPONSE
            payload_size = int.from_bytes(payload[:4], "big", signed=True)
            payload_msg = payload[4:]
            return json.loads(payload_msg.decode("utf-8"))

        return {}

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Process an audio stream to STT service."""
        try:
            # Prepare initial request
            request = self._construct_request(metadata)
            payload = json.dumps(request).encode()
            payload = gzip.compress(payload)

            full_request = bytearray(self._generate_header())
            full_request.extend(len(payload).to_bytes(4, "big"))
            full_request.extend(payload)

            headers = {"Authorization": f"Bearer; {self.entry.data[CONF_ACCESS_TOKEN]}"}

            async with websockets.connect(
                self.ws_url, additional_headers=headers, max_size=1000000000
            ) as ws:
                # Send initial request
                await ws.send(full_request)
                response = await ws.recv()
                result = self._parse_response(response)

                if result.get("code") != self.success_code:
                    return stt.SpeechResult(
                        text=None, result=stt.SpeechResultState.ERROR
                    )

                # Process audio chunks
                async for chunk in stream:
                    payload = gzip.compress(chunk)
                    audio_request = bytearray(
                        self._generate_header(
                            message_type=CLIENT_AUDIO_ONLY_REQUEST,
                            message_type_specific_flags=NEG_SEQUENCE,
                        )
                    )
                    audio_request.extend(len(payload).to_bytes(4, "big"))
                    audio_request.extend(payload)

                    await ws.send(audio_request)
                    response = await ws.recv()
                    result = self._parse_response(response)

                    if result.get("code") != self.success_code:
                        return stt.SpeechResult(
                            text=None, result=stt.SpeechResultState.ERROR
                        )

                # Get final result
                if "text" in result:
                    return stt.SpeechResult(
                        text=result["text"], result=stt.SpeechResultState.SUCCESS
                    )

        except Exception as err:
            return stt.SpeechResult(text=None, result=stt.SpeechResultState.ERROR)

        return stt.SpeechResult(text=None, result=stt.SpeechResultState.ERROR)
