import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from bundled_font_fixture import identify


class FontFixtureTest(unittest.TestCase):
    def package(self,font=b'\x00\x01\x00\x00ordinary-font',code=b'code',omit=False):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('ets/modules.abc',code)
            archive.writestr('resources/rawfile/iconfont.ttf',font)
            if not omit:archive.writestr('resources/rawfile/DINCOROS-Regular.ttf',font)
        output.seek(0);return output

    def test_code_change_does_not_change_font_identity(self):
        self.assertEqual(identify(self.package(code=b'unfixed')),identify(self.package(code=b'fixed')))
        self.assertNotEqual(identify(self.package()),identify(self.package(font=b'\x00\x01\x00\x00changed-font')))

    def test_missing_or_invalid_business_fonts_rejected(self):
        for package in [self.package(omit=True),self.package(font=b'not-a-font')]:
            with self.assertRaises(ValueError):identify(package)


if __name__=='__main__':unittest.main()
