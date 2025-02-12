"""Support for Volcano speech-to-text services."""
from __future__ import annotations

import asyncio
import gzip
import json
import uuid
from typing import Any

import websockets

from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechMetadata,
    SpeechResult,
    SpeechResultState,
    SpeechToTextEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_APPID,
    CONF_STT_CLUSTER,
    CONF_HOST,
    DOMAIN,
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Volcano STT platform."""
    async_add_entities([VolcanoSpeechToTextEntity(config_entry)])

# Protocol constants
PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

PROTOCOL_VERSION_BITS = 4
HEADER_BITS = 4
MESSAGE_TYPE_BITS = 4
MESSAGE_TYPE_SPECIFIC_FLAGS_BITS = 4
MESSAGE_SERIALIZATION_BITS = 4
MESSAGE_COMPRESSION_BITS = 4
RESERVED_BITS = 8

# Message Type:
CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010
SERVER_FULL_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111

# Message Type Specific Flags
NO_SEQUENCE = 0b0000  # no check sequence
POS_SEQUENCE = 0b0001
NEG_SEQUENCE = 0b0010
NEG_SEQUENCE_1 = 0b0011

# Message Serialization
NO_SERIALIZATION = 0b0000
JSON = 0b0001
THRIFT = 0b0011
CUSTOM_TYPE = 0b1111

# Message Compression
NO_COMPRESSION = 0b0000
GZIP = 0b0001
CUSTOM_COMPRESSION = 0b1111


class VolcanoSpeechToTextEntity(SpeechToTextEntity):
    """Volcano speech-to-text entity."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize Volcano STT entity."""
        self._attr_unique_id = f"{entry.entry_id}"
        self._attr_name = entry.title
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Volcano",
            model="Cloud",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        self._entry = entry
        # f"wss://{self._entry.data[CONF_HOST]}/api/v2/asr"
        # self._ws_url = f"wss://{DEFAULT_HOST}/api/v2/asr"
        self._ws_url = f"wss://{self._entry.data[CONF_HOST]}/api/v2/asr"
        self._success_code = 1000

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return ["zh-CN", "en-US"]

    @property
    def supported_formats(self) -> list[AudioFormats]:
        """Return a list of supported formats."""
        return [AudioFormats.WAV, AudioFormats.OGG]

    @property
    def supported_codecs(self) -> list[AudioCodecs]:
        """Return a list of supported codecs."""
        return [AudioCodecs.PCM, AudioCodecs.OPUS]

    @property
    def supported_bit_rates(self) -> list[AudioBitRates]:
        """Return a list of supported bit rates."""
        return [AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        """Return a list of supported sample rates."""
        return [AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[AudioChannels]:
        """Return a list of supported channels."""
        return [AudioChannels.CHANNEL_MONO]

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

    def _construct_request(self, metadata: SpeechMetadata) -> dict[str, Any]:
        """Construct the request payload."""
        codec = metadata.codec.value
        if metadata.codec == AudioCodecs.PCM:
            codec = "raw"

        return {
            "app": {
                "appid": self._entry.data[CONF_APPID],
                "cluster": self._entry.data[CONF_STT_CLUSTER],
                "token": self._entry.data[CONF_ACCESS_TOKEN],
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
                "codec": codec,
            },
        }

    def _parse_response(self, res: bytes) -> dict[str, Any]:
        """Parse server response."""
        protocol_version = res[0] >> 4
        header_size = res[0] & 0x0f
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0f
        serialization_method = res[2] >> 4
        message_compression = res[2] & 0x0f
        reserved = res[3]
        header_extensions = res[4:header_size * 4]
        payload = res[header_size * 4:]
        result = {}
        payload_msg = None
        payload_size = 0
        if message_type == SERVER_FULL_RESPONSE:
            payload_size = int.from_bytes(payload[:4], "big", signed=True)
            payload_msg = payload[4:]
        elif message_type == SERVER_ACK:
            seq = int.from_bytes(payload[:4], "big", signed=True)
            result['seq'] = seq
            if len(payload) >= 8:
                payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                payload_msg = payload[8:]
        elif message_type == SERVER_ERROR_RESPONSE:
            code = int.from_bytes(payload[:4], "big", signed=False)
            result['code'] = code
            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
            payload_msg = payload[8:]
        if payload_msg is None:
            return result
        if message_compression == GZIP:
            payload_msg = gzip.decompress(payload_msg)
        if serialization_method == JSON:
            payload_msg = json.loads(str(payload_msg, "utf-8"))
        elif serialization_method != NO_SERIALIZATION:
            payload_msg = str(payload_msg, "utf-8")
        result['payload_msg'] = payload_msg
        result['payload_size'] = payload_size
        return result

    async def async_process_audio_stream(
        self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> SpeechResult:
        """Process an audio stream to STT service."""
        try:
            # Prepare initial request
            request = self._construct_request(metadata)
            payload = json.dumps(request).encode()
            payload = gzip.compress(payload)

            full_request = bytearray(self._generate_header())
            full_request.extend(len(payload).to_bytes(4, "big"))
            full_request.extend(payload)

            headers = {"Authorization": f"Bearer {self._entry.data[CONF_ACCESS_TOKEN]}"}

            async with websockets.connect(
                self._ws_url, additional_headers=headers, max_size=1000000000
            ) as ws:
                # Send initial request
                await ws.send(full_request)
                response = await ws.recv()
                result = self._parse_response(response)
                
                if 'payload_msg' not in result:
                    return SpeechResult(None, SpeechResultState.ERROR)

                if result['payload_msg']['code'] != self._success_code:
                    return SpeechResult(None, SpeechResultState.ERROR)

                last_chunk = None
                # Process audio chunks
                async for chunk in stream:
                    if last_chunk is not None:
                        payload = gzip.compress(last_chunk)
                        audio_request = bytearray(
                            self._generate_header(
                                message_type=CLIENT_AUDIO_ONLY_REQUEST
                            )
                        )
                        audio_request.extend(len(payload).to_bytes(4, "big"))
                        audio_request.extend(payload)

                        await ws.send(audio_request)

                        res = await ws.recv()
                        result = parse_response(res)
                        if 'payload_msg' in result and result['payload_msg']['code'] != self.success_code:
                            return SpeechResult(None, SpeechResultState.ERROR)

                    last_chunk = chunk

                payload = gzip.compress(last_chunk)
                audio_request = bytearray(
                    self._generate_header(
                        message_type=CLIENT_AUDIO_ONLY_REQUEST,
                        message_type_specific_flags=NEG_SEQUENCE
                    )
                )
                audio_request.extend(len(payload).to_bytes(4, "big"))
                audio_request.extend(payload)

                await ws.send(audio_request)

                res = await ws.recv()
                result = parse_response(res)
                if 'payload_msg' in result and result['payload_msg']['code'] != self.success_code:
                    return SpeechResult(None, SpeechResultState.ERROR)

                if "payload_msg" not in result or "text" not in result["payload_msg"]:
                    return SpeechResult(None, SpeechResultState.ERROR)
                    
                return SpeechResult(result["payload_msg"]["text"], SpeechResultState.SUCCESS)


        except Exception as err:
            return SpeechResult(None, SpeechResultState.ERROR)

        return SpeechResult(None, SpeechResultState.ERROR)
