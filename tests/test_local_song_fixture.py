import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from seed_local_songs import APP_FILES, generate, fixture_digest, deploy
from ui_driver import UI


class LocalSongFixtureTests(unittest.TestCase):
    def test_real_mp3_and_relative_business_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            generate(folder,3,APP_FILES)
            with sqlite3.connect(folder/'LocalSongs.db') as db:
                rows=list(db.execute('SELECT songId,songFile FROM songs'))
            self.assertEqual([sid for sid,_ in rows],[0,0,0])
            spec=json.loads((folder/'files.json').read_text())
            self.assertEqual([name for _,name in rows],spec['files'])
            self.assertTrue(all(not Path(name).is_absolute() for _,name in rows))
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(folder/spec['audio'])]))
            self.assertEqual(info['streams'][0]['codec_name'],'mp3')
            self.assertGreaterEqual(float(info['format']['duration']),60)
            before=fixture_digest(folder)
            with (folder/spec['audio']).open('ab') as audio:
                audio.write(b'changed-audio')
            self.assertNotEqual(fixture_digest(folder),before)

    def test_bad_absolute_database_paths_rejected_before_remote_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            generate(folder,1,APP_FILES)
            with sqlite3.connect(folder/'LocalSongs.db') as db:
                db.execute('UPDATE songs SET songFile=?',(APP_FILES+'/blue_0.mp3',))
            with self.assertRaisesRegex(ValueError,'relative filenames'):
                deploy(folder,'unreachable-host-must-not-be-used')

    def test_ui_result_regex_cannot_match_unfiltered_rows(self):
        ui=UI(lambda command:'','app.bundle')
        layout={'attributes':{'bundleName':'app.bundle'},'children':[
            {'attributes':{'text':'Track 9999','bounds':'[0,0][10,10]'}},
            {'attributes':{'text':'Track 9901','bounds':'[20,20][30,30]'}}]}
        ui.layout=lambda:layout
        self.assertEqual(ui.find({'text':r'Track (?:[0-9]*01|1)','match':'regex'},timeout=0)['text'],'Track 9901')
        with self.assertRaises(RuntimeError):
            ui.find({'text':r'Track (?:[0-9]*00|0)','match':'regex'},timeout=0)


if __name__=='__main__':
    unittest.main()
