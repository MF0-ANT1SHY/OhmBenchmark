import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ProfilerChecksumSnapshotTest(unittest.TestCase):
    def test_snapshot_only_in_profiler_and_continued_updates_remain_standard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib=root/'snapshot.so';src=root/'test.c'
            src.write_text('''#include <string.h>
#include <openssl/sha.h>
int main(int argc,char **argv){
 SHA256_CTX c,original;unsigned char got[32],expected[32];
 SHA256_Init(&c);SHA256_Update(&c,"abc",3);original=c;SHA256_Final(got,&c);
 SHA256((const unsigned char*)"abc",3,expected);if(memcmp(got,expected,32))return 2;
 if(argc>1){if(memcmp(&c,&original,sizeof(c)))return 3;SHA256_Update(&c,"def",3);SHA256_Final(got,&c);SHA256((const unsigned char*)"abcdef",6,expected);return memcmp(got,expected,32)?4:0;}
 return memcmp(&c,&original,sizeof(c))?0:5;
}
''')
            subprocess.run(['cc','-D_GNU_SOURCE','-shared','-fPIC','-O2',str(ROOT/'tools/profiler_sha_snapshot.c'),'-ldl','-pthread','-o',str(lib)],check=True,capture_output=True)
            exe=root/'hiprofilerd';subprocess.run(['cc','-Wno-deprecated-declarations',str(src),'-lcrypto','-o',str(exe)],check=True,capture_output=True)
            other=root/'application';other.write_bytes(exe.read_bytes());other.chmod(0o755)
            env={**os.environ,'LD_PRELOAD':str(lib)}
            subprocess.run([str(exe),'snapshot'],env=env,check=True,capture_output=True)
            subprocess.run([str(other)],env=env,check=True,capture_output=True)
