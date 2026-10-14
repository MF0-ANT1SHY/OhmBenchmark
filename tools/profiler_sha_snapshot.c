/* Evaluator-side SHA finalization repair. Never preload this into an app.
 * Device hiprofilerd disassembly confirms 136-byte shared allocation with a
 * 24-byte control block and 112-byte public OpenSSL SHA256_CTX ABI.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdio.h>
#include <dlfcn.h>
#include <pthread.h>

typedef struct { uint32_t h[8], nl, nh, data[16], num, md_len; } Context;
_Static_assert(sizeof(Context)==112,"SHA256_CTX ABI mismatch");
static pthread_once_t once=PTHREAD_ONCE_INIT;
static int (*real_final)(unsigned char *,void *);
static int enabled;
static void init(void){
 real_final=(int(*)(unsigned char*,void*))dlsym(RTLD_NEXT,"SHA256_Final");
 if(!real_final)_exit(120);
 char command[256]={0};int fd=open("/proc/self/cmdline",O_RDONLY);
 if(fd>=0){read(fd,command,sizeof(command)-1);close(fd);}
 const char *name=strrchr(command,'/');name=name?name+1:command;
 enabled=strcmp(name,"hiprofilerd")==0;
 if(enabled){
  char path[128];snprintf(path,sizeof(path),"/data/local/tmp/profiler-sha-snapshot-%d.receipt",getpid());
  fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);
  if(fd>=0){const char note[]="hiprofilerd-only SHA256_Final snapshot; ABI=112\n";write(fd,note,sizeof(note)-1);close(fd);}
 }
}
int SHA256_Final(unsigned char *digest,void *context){
 pthread_once(&once,init);
 if(!enabled)return real_final(digest,context);
 Context snapshot;memcpy(&snapshot,context,sizeof(snapshot));
 int result=real_final(digest,&snapshot);
 memset(&snapshot,0,sizeof(snapshot));return result;
}
