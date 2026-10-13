import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from bundled_audio_fixture import identify


class BundledAudioTests(unittest.TestCase):
    def package(self,code,audio):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            archive.writestr('ets/modules.abc',code)
            archive.writestr('resources/rawfile/audio/Track.mp3',audio)
        data.seek(0)
        return data

    def test_repair_code_changes_do_not_change_audio_identity(self):
        first=identify(self.package(b'unfixed-code',b'ordinary-audio'))
        second=identify(self.package(b'fixed-code',b'ordinary-audio'))
        self.assertEqual(first,second)
        self.assertNotEqual(first['sha256'],identify(self.package(b'fixed-code',b'changed-audio'))['sha256'])

    def test_missing_audio_is_not_treated_as_a_matching_empty_fixture(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            archive.writestr('ets/modules.abc',b'code')
        data.seek(0)
        with self.assertRaises(ValueError):identify(data)


if __name__=='__main__':unittest.main()
