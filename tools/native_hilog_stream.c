/* Private evaluator launcher, never linked into or loaded by an app.
 * Retain the ordinary native HiLog stream with a bounded process lifetime.
 * --probe selects only this logger's own PID, not any application.
 */
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int number(const char *text, long maximum)
{
    char *end;
    errno = 0;
    long value = strtol(text, &end, 10);
    return errno || !text[0] || *end || value < 1 || value > maximum ? 0 : (int)value;
}

int main(int argc, char **argv)
{
    int pid, duration;
    if (argc == 2 && !strcmp(argv[1], "--probe")) {
        pid = (int)getpid();
        duration = 2;
    } else if (argc == 3 && (pid = number(argv[1], INT_MAX)) &&
               (duration = number(argv[2], 180))) {
        /* Validated ordinary application PID and hard duration bound. */
    } else {
        fprintf(stderr, "usage: native-hilog-stream --probe | PID SECONDS(1..180)\n");
        return 2;
    }
    char selected[32];
    snprintf(selected, sizeof(selected), "%d", pid);
    printf("__OHM_HILOG_OWNER__%ld\n", (long)getpid());
    fflush(stdout);
    signal(SIGALRM, SIG_DFL);
    /* The timer survives exec; the logger retains this exact process PID. */
    alarm((unsigned)duration);
    execlp("hilog", "hilog", "-P", selected, "-v", "epoch", "-v", "nsec", (char *)NULL);
    perror("exec native hilog");
    return 3;
}
