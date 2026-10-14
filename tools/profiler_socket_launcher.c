/* Evaluator-only daemon supervisor supplying the documented init socket ABI.
 * Refuses existing socket paths; never starts an application or edits init cfg.
 */
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#ifndef PROFILER_SOCKET_DIRECTORY
#define PROFILER_SOCKET_DIRECTORY "/dev/unix/socket"
#endif
#ifndef PROFILER_EXECUTABLE
#define PROFILER_EXECUTABLE "/system/bin/hiprofilerd"
#endif
#ifndef NATIVE_EXECUTABLE
#define NATIVE_EXECUTABLE "/system/bin/native_daemon"
#endif
static void remove_owned(const char *path,const struct stat *owned){
 struct stat current;
 if(!lstat(path,&current)&&S_ISSOCK(current.st_mode)&&current.st_dev==owned->st_dev&&current.st_ino==owned->st_ino)unlink(path);
}
static volatile sig_atomic_t stop;
static void stopped(int signal){(void)signal;stop=1;}
int main(int argc,char**argv){
 if(argc<3||argc>4)return 2;
 const char *name=argv[1],*exe=argv[2];
 if((strcmp(name,"hiprofiler_unix_socket")||strcmp(exe,PROFILER_EXECUTABLE))&&
    (strcmp(name,"hook_unix_socket")||strcmp(exe,NATIVE_EXECUTABLE)))return 3;
 if(argc==4&&strcmp(exe,PROFILER_EXECUTABLE))return 4;
 char path[108],envname[96],fdtext[24];
 snprintf(path,sizeof(path),PROFILER_SOCKET_DIRECTORY "/%s",name);
 struct stat old,owned;if(lstat(path,&old)==0||errno!=ENOENT)return 5;
 int fd=socket(AF_UNIX,SOCK_STREAM,0);if(fd<0)return 6;
 struct sockaddr_un address={.sun_family=AF_UNIX};strcpy(address.sun_path,path);
 if(bind(fd,(struct sockaddr*)&address,sizeof(address))){close(fd);return 7;}
 if(lstat(path,&owned)){close(fd);return 8;}
 if(chmod(path,strcmp(name,"hook_unix_socket")?0600:0666)){close(fd);remove_owned(path,&owned);return 8;}
 int option=1;if(!strcmp(name,"hiprofiler_unix_socket"))setsockopt(fd,SOL_SOCKET,SO_PASSCRED,&option,sizeof(option));
 snprintf(envname,sizeof(envname),"OHOS_SOCKET_%s",name);snprintf(fdtext,sizeof(fdtext),"%d",fd);
 setenv(envname,fdtext,1);if(argc==4)setenv("LD_PRELOAD",argv[3],1);
 signal(SIGTERM,stopped);signal(SIGINT,stopped);
 pid_t child=fork();if(child<0){close(fd);remove_owned(path,&owned);return 9;}
 if(!child){signal(SIGTERM,SIG_DFL);signal(SIGINT,SIG_DFL);execl(exe,exe,(char*)0);_exit(127);}
 printf("owned child=%d socket=%s\n",child,path);fflush(stdout);
 int status=0;pid_t result;
 while(!stop&&(result=waitpid(child,&status,WNOHANG))==0)usleep(200000);
 if(stop){
  kill(child,SIGTERM);
  int done=0;for(int i=0;i<10;i++){if(waitpid(child,&status,WNOHANG)==child){done=1;break;}usleep(200000);}
  if(!done){kill(child,SIGKILL);waitpid(child,&status,0);}
 }
 close(fd);
 remove_owned(path,&owned);
 return stop?0:(WIFEXITED(status)?WEXITSTATUS(status):128);
}
