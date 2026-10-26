/*
 * test_harness.h
 *
 * Macros and helper declarations for the on-target test harness
 * used by the mmWave firmware CI framework.
 *
 * Provides:
 *   - HARNESS_INIT / HARNESS_RUN_TEST / HARNESS_COMPLETE lifecycle macros
 *   - UART output helpers
 *   - Timeout assertion macro for deadlock detection
 *
 * Target: TI AWR2944 / IWR6843
 */

#ifndef TEST_HARNESS_H
#define TEST_HARNESS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* -----------------------------------------------------------------------
 * UART output helpers (implemented in unity_runner.c / test_stub_main.c)
 * ----------------------------------------------------------------------- */

void unity_output_char(char c);
void unity_output_string(const char *str);

/* Convenience: print a formatted line (max 256 chars) */
#define HARNESS_PRINTF(fmt, ...)                          \
    do {                                                  \
        char _hbuf[256];                                  \
        snprintf(_hbuf, sizeof(_hbuf), fmt, __VA_ARGS__); \
        unity_output_string(_hbuf);                       \
    } while (0)

/* -----------------------------------------------------------------------
 * Lifecycle macros
 * ----------------------------------------------------------------------- */

/**
 * HARNESS_INIT — called once at startup before any test execution.
 * Emits a machine-parseable banner so the host knows tests are about
 * to start.
 */
#define HARNESS_INIT()                                     \
    do {                                                   \
        unity_output_string("[HARNESS] INIT\r\n");         \
    } while (0)

/**
 * HARNESS_RUN_TEST — wrapper around Unity's RUN_TEST that adds
 * watchdog servicing and UART progress output.
 */
#define HARNESS_RUN_TEST(test_func)                        \
    do {                                                   \
        unity_output_string("[HARNESS] RUN " #test_func    \
                            "\r\n");                       \
        RUN_TEST(test_func);                               \
    } while (0)

/**
 * HARNESS_COMPLETE — called after all tests have finished.
 * Emits the final status line used by the host to determine pass/fail.
 */
#define HARNESS_COMPLETE(result)                            \
    do {                                                   \
        if ((result) == 0) {                               \
            unity_output_string("[HARNESS] COMPLETE PASS"  \
                                "\r\n");                   \
        } else {                                           \
            unity_output_string("[HARNESS] COMPLETE FAIL"  \
                                "\r\n");                   \
        }                                                  \
    } while (0)

/* -----------------------------------------------------------------------
 * Timeout assertion macro
 *
 * Spins up to `timeout_ms` milliseconds waiting for `condition` to
 * become true. If it does not, the test fails with a descriptive
 * message.  Uses a simple busy-wait loop calibrated to the CPU clock;
 * for more accurate timing use a hardware timer.
 * ----------------------------------------------------------------------- */

/* Approximate loop iterations per millisecond at 200 MHz R5F */
#define HARNESS_LOOPS_PER_MS  40000U

#define ASSERT_TIMEOUT_MS(condition, timeout_ms, msg)      \
    do {                                                   \
        uint32_t _loops = (uint32_t)(timeout_ms)           \
                          * HARNESS_LOOPS_PER_MS;          \
        volatile uint32_t _i;                              \
        for (_i = 0; _i < _loops; _i++) {                  \
            if (condition) { break; }                      \
        }                                                  \
        if (!(condition)) {                                \
            TEST_FAIL_MESSAGE(msg);                        \
        }                                                  \
    } while (0)

#ifdef __cplusplus
}
#endif

#endif /* TEST_HARNESS_H */
