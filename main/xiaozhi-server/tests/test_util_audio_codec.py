import unittest
from unittest.mock import MagicMock, patch

from core.utils import util


class AudioCodecSelectionTest(unittest.TestCase):
    def test_mp3_uses_explicit_decoder(self):
        audio = MagicMock()
        audio.set_channels.return_value = audio
        audio.set_frame_rate.return_value = audio
        audio.set_sample_width.return_value = audio
        audio.raw_data = b""

        with patch.object(util.AudioSegment, "from_file", return_value=audio) as load:
            with patch.object(util, "pcm_to_data_stream"):
                util.audio_bytes_to_data_stream(
                    b"mp3-data",
                    "mp3",
                    True,
                    callback=lambda _: None,
                )

        self.assertEqual(load.call_args.kwargs["codec"], "mp3")

    def test_unknown_format_keeps_probe_fallback(self):
        self.assertIsNone(util._audio_codec_for_file_type("aac"))


if __name__ == "__main__":
    unittest.main()
