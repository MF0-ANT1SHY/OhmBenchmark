/* Private evaluator capability calibration. Traces ONLY its own child, never
 * an app. No injected code, modified registers, or tracee memory access.
 * Successful calibration is NOT app-write evidence or app-attach permission.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <elf.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/ptrace.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

static volatile sig_atomic_t child_pid;
static int nr_phase_mode, unanchored_writes, raw_register_mode;

/* Linux arm64 kernels expose syscall direction through x7 at syscall stops.
 * Kernel ABI source: Linux arch/arm64/kernel/ptrace.c, report_syscall().
 * https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kernel/ptrace.c
 * This is a calibration hypothesis, NOT a promise for HongMeng Kernel.
 * Read-only GETREGSET fallback; no register or tracee memory writes.
 */
static long syscall_info(pid_t child, struct ptrace_syscall_info *info)
{
    long size = ptrace(PTRACE_GET_SYSCALL_INFO, child, sizeof(*info), info);
    if (size >= 0 || errno != EINVAL) return size;
#if defined(__aarch64__)
    struct { uint64_t regs[31], sp, pc, pstate; } regs;
    memset(&regs, 0, sizeof(regs));
    struct iovec io = { &regs, sizeof(regs) };
    errno = 0;
    long result = ptrace(PTRACE_GETREGSET, child, (void *)(long)NT_PRSTATUS, &io);
    int saved_errno = errno;
    printf("{\"kind\":\"arm64_readonly_regset_result\",\"result\":%ld,\"errno\":%d,\"register_bytes\":%zu,\"x7\":%" PRIu64 "}\n",
           result, saved_errno, io.iov_len, regs.regs[7]);
    if (raw_register_mode) {
        printf("{\"kind\":\"own_child_raw_regset\",\"registers\":[");
        for (int i = 0; i < 31; i++) printf("%s%" PRIu64, i ? "," : "", regs.regs[i]);
        printf("],\"sp\":%" PRIu64 ",\"pc\":%" PRIu64 ",\"pstate\":%" PRIu64 "}\n", regs.sp, regs.pc, regs.pstate);
        struct { uint64_t regs[31], sp, pc, pstate; } alternate;
        memset(&alternate, 0, sizeof(alternate));
        errno = 0;
        long alternate_result = ptrace(PTRACE_GETREGS, child, 0, &alternate);
        int alternate_errno = errno;
        printf("{\"kind\":\"own_child_raw_getregs\",\"result\":%ld,\"errno\":%d,\"registers\":[", alternate_result, alternate_errno);
        for (int i = 0; i < 31; i++) printf("%s%" PRIu64, i ? "," : "", alternate.regs[i]);
        printf("],\"sp\":%" PRIu64 ",\"pc\":%" PRIu64 ",\"pstate\":%" PRIu64 "}\n", alternate.sp, alternate.pc, alternate.pstate);
    }
    if (result || io.iov_len != sizeof(regs) || (!nr_phase_mode && regs.regs[7] > 1)) {
        errno = result ? saved_errno : EPROTO;
        return -1;
    }
    memset(info, 0, sizeof(*info));
    unsigned direction = (unsigned)regs.regs[7];
    if (nr_phase_mode) {
        /* Own-child-only experiment: a syscall-number transition anchors an
         * entry, then require paired equal-number entry/exit stops. Do not
         * generalize this calibration to app-thread coverage or permission.
         */
        static int have_previous, anchored;
        static uint64_t previous;
        static unsigned next_direction;
        uint64_t number = regs.regs[8];
        if (!anchored) {
            if (have_previous && number != previous) {
                anchored = 1;
                direction = 0;
            } else {
                if (number == SYS_write || number == SYS_pwrite64) unanchored_writes++;
                previous = number;
                have_previous = 1;
                printf("{\"kind\":\"unanchored_own_child_stop\",\"syscall\":%" PRIu64 "}\n", number);
                return sizeof(*info);
            }
        } else {
            direction = next_direction;
            if (direction == 1 && number != previous) { errno = EPROTO; return -1; }
        }
        previous = number;
        next_direction = 1-direction;
        printf("{\"kind\":\"own_child_nr_phase_stop\",\"syscall\":%" PRIu64 ",\"direction\":%u}\n", number, direction);
    }
    if (direction == 0) {
        info->op = PTRACE_SYSCALL_INFO_ENTRY;
        info->entry.nr = regs.regs[8];
        for (int i = 0; i < 6; i++) info->entry.args[i] = regs.regs[i];
    } else {
        info->op = PTRACE_SYSCALL_INFO_EXIT;
        info->exit.rval = (int64_t)regs.regs[0];
        info->exit.is_error = info->exit.rval < 0 && info->exit.rval >= -4095;
    }
    printf("{\"kind\":\"arm64_readonly_regset_stop\",\"direction\":%u}\n", info->op);
    return sizeof(*info);
#else
    return -1;
#endif
}
static void timeout_handler(int sig)
{
    (void)sig;
    if (child_pid > 0) kill((pid_t)child_pid, SIGKILL);
    _exit(124);
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--nr-phase")) nr_phase_mode = 1;
    else if (argc == 2 && !strcmp(argv[1], "--raw-registers")) nr_phase_mode = raw_register_mode = 1;
    else if (argc != 1) return 2;
    int gate[2], status = 0, failed = 0;
    char path[128];
    snprintf(path, sizeof(path), "/data/local/tmp/ohm-syscall-calibration-%ld", (long)getpid());
    if (pipe(gate)) return 2;
    signal(SIGALRM, timeout_handler);
    signal(SIGTERM, timeout_handler);
    signal(SIGINT, timeout_handler);
    alarm(15);
    pid_t owner = getpid(), child = fork();
    if (child < 0) return 3;
    if (child == 0) {
        /* Own-child lifetime protection, including the fork/prctl race. */
        prctl(PR_SET_PDEATHSIG, SIGKILL);
        if (getppid() != owner) _exit(90);
        close(gate[1]);
        char token;
        if (read(gate[0], &token, 1) != 1) _exit(91);
        close(gate[0]);
        int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd < 0) _exit(92);
        const char bytes[] = "native-write-calibration";
        if (write(fd, bytes, sizeof(bytes)-1) != (ssize_t)(sizeof(bytes)-1)) _exit(93);
        if (pwrite(fd, "1234567", 7, sizeof(bytes)-1) != 7) _exit(94);
        close(fd);
        _exit(0);
    }
    child_pid = child;
    close(gate[0]);
    errno = 0;
    long seized = ptrace(PTRACE_SEIZE, child, 0, (void *)(long)PTRACE_O_TRACESYSGOOD);
    printf("{\"kind\":\"seize_own_child\",\"result\":%ld,\"errno\":%d}\n", seized, errno);
    fflush(stdout);
    if (seized || ptrace(PTRACE_INTERRUPT, child, 0, 0) || waitpid(child, &status, 0) != child || !WIFSTOPPED(status)) {
        failed = 1;
        goto cleanup;
    }
    if (write(gate[1], "x", 1) != 1) { failed = 1; goto cleanup; }
    close(gate[1]);
    gate[1] = -1;
    uint64_t number = 0;
    int selected = 0, writes = 0;
    int64_t total = 0;
    while (1) {
        if (ptrace(PTRACE_SYSCALL, child, 0, 0)) { failed = 1; break; }
        if (waitpid(child, &status, 0) != child) { failed = 1; break; }
        if (WIFEXITED(status)) { failed |= WEXITSTATUS(status) != 0; child_pid = 0; break; }
        if (!WIFSTOPPED(status) || WSTOPSIG(status) != (SIGTRAP | 0x80)) { failed = 1; break; }
        struct ptrace_syscall_info info;
        memset(&info, 0, sizeof(info));
        long size = syscall_info(child, &info);
        if (size < 0) {
            printf("{\"kind\":\"syscall_info_failure\",\"errno\":%d}\n", errno);
            failed = 1;
            break;
        }
        if (info.op == PTRACE_SYSCALL_INFO_ENTRY) {
            number = info.entry.nr;
            selected = 0;
            if (number == SYS_write || number == SYS_pwrite64) {
                char fdpath[128], resolved[256];
                snprintf(fdpath, sizeof(fdpath), "/proc/%ld/fd/%" PRIu64, (long)child, (uint64_t)info.entry.args[0]);
                ssize_t n = readlink(fdpath, resolved, sizeof(resolved)-1);
                if (n >= 0) { resolved[n] = 0; selected = !strcmp(path, resolved); }
            }
        } else if (info.op == PTRACE_SYSCALL_INFO_EXIT && selected) {
            printf("{\"kind\":\"native_write_exit\",\"syscall\":%" PRIu64 ",\"returned_bytes\":%" PRId64 ",\"is_error\":%u}\n",
                   number, (int64_t)info.exit.rval, info.exit.is_error);
            if (info.exit.is_error || info.exit.rval <= 0) failed = 1;
            else { total += info.exit.rval; writes++; }
            selected = 0;
        }
    }
    failed |= writes != 2 || total != 31 || unanchored_writes != 0;
    printf("{\"kind\":\"calibration\",\"writes\":%d,\"returned_bytes\":%" PRId64 ",\"expected_bytes\":31,\"passed\":%s,\"app_traced\":false,\"nr_phase_experiment\":%s,\"unanchored_write_stops\":%d}\n",
           writes, total, failed ? "false" : "true", nr_phase_mode ? "true" : "false", unanchored_writes);
cleanup:
    if (child_pid > 0) {
        kill(child, SIGKILL);
        while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
        child_pid = 0;
    }
    if (gate[1] >= 0) close(gate[1]);
    unlink(path);
    alarm(0);
    return failed ? 1 : 0;
}
