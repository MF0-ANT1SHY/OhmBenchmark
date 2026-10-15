/* Standalone evaluator calibration. No app is launched, linked, or attached. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    const char *prefix = "/data/local/tmp/ohm-file-write-probe-";
    if (argc != 2 || strncmp(argv[1], prefix, strlen(prefix))) return 2;
    for (const char *p = argv[1]+strlen(prefix); *p; p++)
        if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return 2;
    alarm(10);
    int fd = open(argv[1], O_CREAT | O_EXCL | O_WRONLY, 0600);
    if (fd < 0) return 3;
    const char bytes[] = "native-write-calibration";
    ssize_t first = write(fd, bytes, sizeof(bytes)-1);
    ssize_t second = pwrite(fd, "1234567", 7, sizeof(bytes)-1);
    struct stat info;
    memset(&info, 0, sizeof(info));
    int stat_result = fstat(fd, &info);
    int synced = fsync(fd);
    int closed = close(fd);
    int passed = first == 24 && second == 7 && !stat_result &&
                 info.st_size == 31 && !synced && !closed;
    printf("{\"pid\":%ld,\"dev\":%" PRIu64 ",\"ino\":%" PRIu64
           ",\"write_return\":%ld,\"pwrite_return\":%ld,\"file_bytes\":%ld,\"passed\":%s}\n",
           (long)getpid(), (uint64_t)info.st_dev, (uint64_t)info.st_ino,
           (long)first, (long)second, (long)info.st_size, passed ? "true" : "false");
    return passed ? 0 : 1;
}
