import os,subprocess,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ProfilerSocketLauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.child=self.root/'daemon';src=self.root/'daemon.c';self.ack=self.root/'ack'
        src.write_text('''#include <stdlib.h>
#include <unistd.h>
#include <stdio.h>
#include <sys/socket.h>
int main(){char *value=getenv("OHOS_SOCKET_hiprofiler_unix_socket");if(!value)return 2;int fd=atoi(value),family=0;socklen_t n=sizeof(family);if(getsockopt(fd,SOL_SOCKET,SO_DOMAIN,&family,&n)||family!=AF_UNIX)return 3;FILE*f=fopen(ACK,"w");fputs("VALID",f);fclose(f);for(;;)pause();}
''')
        subprocess.run(['cc',str(src),f'-DACK="{self.ack}"','-o',str(self.child)],check=True,capture_output=True)
        self.launcher=self.root/'launcher'
        subprocess.run(['cc',str(ROOT/'tools/profiler_socket_launcher.c'),f'-DPROFILER_SOCKET_DIRECTORY="{self.root}"',f'-DPROFILER_EXECUTABLE="{self.child}"','-o',str(self.launcher)],check=True,capture_output=True)
        self.socket=self.root/'hiprofiler_unix_socket'
    def start(self):
        p=subprocess.Popen([str(self.launcher),'hiprofiler_unix_socket',str(self.child)],stdout=subprocess.PIPE,text=True)
        self.addCleanup(lambda:p.poll() is None and (p.terminate(),p.wait(timeout=5)))
        self.assertIn('owned child=',p.stdout.readline())
        deadline=time.monotonic()+3
        while not self.ack.exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.ack.read_text(),'VALID');return p
    def test_supplies_real_inherited_socket_and_cleans_owned_child_and_path(self):
        p=self.start();self.assertTrue(self.socket.is_socket());p.terminate();self.assertEqual(p.wait(timeout=5),0);self.assertFalse(self.socket.exists());p.stdout.close()
    def test_existing_resource_is_not_overwritten(self):
        self.socket.write_text('EXISTING')
        p=subprocess.run([str(self.launcher),'hiprofiler_unix_socket',str(self.child)],capture_output=True)
        self.assertEqual(p.returncode,5);self.assertEqual(self.socket.read_text(),'EXISTING')
    def test_replacement_resource_is_not_removed_during_cleanup(self):
        p=self.start();self.socket.unlink();self.socket.write_text('REPLACED')
        p.terminate();self.assertEqual(p.wait(timeout=5),0);self.assertEqual(self.socket.read_text(),'REPLACED');p.stdout.close()
