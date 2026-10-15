/* Private evaluator only: observe, never inject/intercept, native key events.
 * API declarations are from the installed OpenHarmony native SDK (ohinput).
 * --probe registers/removes immediately and records no keys. A normal run is
 * bounded and records only events for the explicitly selected native window.
 * These timestamps prove MMI observation, NOT ArkUI onChange callback timing.
 */
#include <stdbool.h>
#include <multimodalinput/oh_input_manager.h>
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

_Static_assert(ATOMIC_BOOL_LOCK_FREE == 2, "signal handler requires lock-free atomics");
static atomic_bool stopped;
static int32_t selected_window = -1;

static int64_t mono_ns(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) return -1;
    return (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}

static void stop_handler(int signal_number)
{
    (void)signal_number;
    atomic_store(&stopped, true);
}

static void observe(const Input_KeyEvent *event)
{
    if (selected_window < 0 || atomic_load(&stopped) ||
        OH_Input_GetKeyEventWindowId(event) != selected_window) return;
    printf("{\"kind\":\"key\",\"observer_monotonic_ns\":%" PRId64
           ",\"action_time\":%" PRId64 ",\"window_id\":%" PRId32
           ",\"key_code\":%" PRId32 ",\"action\":%" PRId32 "}\n",
           mono_ns(), OH_Input_GetKeyEventActionTime(event), selected_window,
           OH_Input_GetKeyEventKeyCode(event), OH_Input_GetKeyEventAction(event));
    fflush(stdout);
}

static int parse_number(const char *text, int32_t maximum, int32_t *value)
{
    char *end;
    errno = 0;
    long parsed = strtol(text, &end, 10);
    if (errno || !text[0] || *end || parsed < 0 || parsed > maximum) return 0;
    *value = (int32_t)parsed;
    return 1;
}

int main(int argc, char **argv)
{
    int probe = argc == 2 && !strcmp(argv[1], "--probe");
    int32_t duration = 0;
    if (!probe && (argc != 3 || !parse_number(argv[1], INT32_MAX, &selected_window) ||
                   !parse_number(argv[2], 30, &duration) || duration == 0)) {
        fprintf(stderr, "usage: native-key-observer --probe | WINDOW_ID SECONDS(1..30)\n");
        return 2;
    }
    signal(SIGTERM, stop_handler);
    signal(SIGINT, stop_handler);
    /* Hard lifetime bound even if a service registration/removal IPC hangs.
     * Process death also disconnects the monitor's native client session. */
    alarm(probe ? 10 : (unsigned)duration + 5);
    int64_t started = mono_ns();
    if (started <= 0) return 3;
    Input_Result added = OH_Input_AddKeyEventMonitor(observe);
    printf("{\"kind\":\"registration\",\"result\":%d,\"pid\":%ld,"
           "\"window_id\":%" PRId32 ",\"probe\":%s,\"monotonic_ns\":%" PRId64 "}\n",
           added, (long)getpid(), selected_window, probe ? "true" : "false", started);
    fflush(stdout);
    if (added != INPUT_SUCCESS) return 4;
    int64_t deadline = started + (int64_t)duration * 1000000000;
    while (!probe && !atomic_load(&stopped) && mono_ns() < deadline) {
        struct timespec delay = {0, 10000000};
        nanosleep(&delay, NULL);
    }
    atomic_store(&stopped, true);
    Input_Result removed = OH_Input_RemoveKeyEventMonitor(observe);
    printf("{\"kind\":\"removal\",\"result\":%d,\"monotonic_ns\":%" PRId64 "}\n",
           removed, mono_ns());
    return removed == INPUT_SUCCESS ? 0 : 5;
}
