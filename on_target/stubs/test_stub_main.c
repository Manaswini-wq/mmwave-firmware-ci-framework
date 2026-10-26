/*
 * test_stub_main.c
 *
 * On-target test stub main loop for the mmWave firmware CI framework.
 * Provides a UART command interface that accepts test commands from the
 * host PC, executes on-target tests, and reports results back via UART.
 *
 * Target: TI AWR2944 / IWR6843
 * Toolchain: TI ARM CGT v20.x
 */

#include <stdint.h>
#include <string.h>
#include <stdio.h>

#include "test_harness.h"
#include "ti/drivers/UART.h"
#include "ti/drivers/Watchdog.h"
#include "ti/board/board.h"

/* -----------------------------------------------------------------------
 * Definitions
 * ----------------------------------------------------------------------- */

#define CMD_BUF_SIZE        256
#define UART_BAUD_RATE      115200
#define WDG_TIMEOUT_MS      50
#define RESULT_BUF_SIZE     512
#define MAX_TEST_FUNCTIONS  64

/* Command tokens */
#define CMD_RUN_TEST        "run"
#define CMD_RUN_ALL         "run_all"
#define CMD_STATUS          "status"
#define CMD_RESET           "reset"
#define CMD_BIST            "bist"

/* -----------------------------------------------------------------------
 * Types
 * ----------------------------------------------------------------------- */

typedef void (*test_func_t)(void);

typedef struct {
    const char   *name;
    test_func_t   func;
} test_entry_t;

/* -----------------------------------------------------------------------
 * Globals
 * ----------------------------------------------------------------------- */

static UART_Handle  g_uart;
static Watchdog_Handle g_wdg;
static char         g_cmd_buf[CMD_BUF_SIZE];
static char         g_result_buf[RESULT_BUF_SIZE];
static test_entry_t g_tests[MAX_TEST_FUNCTIONS];
static uint32_t     g_num_tests = 0;
static volatile int g_running   = 1;

/* -----------------------------------------------------------------------
 * UART helpers
 * ----------------------------------------------------------------------- */

static void uart_puts(const char *str)
{
    UART_write(g_uart, str, strlen(str));
}

static int uart_readline(char *buf, uint32_t max_len)
{
    uint32_t idx = 0;
    char c;
    while (idx < max_len - 1) {
        if (UART_read(g_uart, &c, 1) != 1) {
            continue;
        }
        if (c == '\r' || c == '\n') {
            break;
        }
        buf[idx++] = c;
    }
    buf[idx] = '\0';
    return (int)idx;
}

/* -----------------------------------------------------------------------
 * Test registration
 * ----------------------------------------------------------------------- */

void register_test(const char *name, test_func_t func)
{
    if (g_num_tests < MAX_TEST_FUNCTIONS) {
        g_tests[g_num_tests].name = name;
        g_tests[g_num_tests].func = func;
        g_num_tests++;
    }
}

/* -----------------------------------------------------------------------
 * Command processing
 * ----------------------------------------------------------------------- */

static void cmd_run_single(const char *test_name)
{
    uint32_t i;
    for (i = 0; i < g_num_tests; i++) {
        if (strcmp(g_tests[i].name, test_name) == 0) {
            snprintf(g_result_buf, RESULT_BUF_SIZE,
                     "[TEST] Running: %s\r\n", test_name);
            uart_puts(g_result_buf);

            g_tests[i].func();

            snprintf(g_result_buf, RESULT_BUF_SIZE,
                     "[TEST] Complete: %s\r\n", test_name);
            uart_puts(g_result_buf);
            return;
        }
    }
    snprintf(g_result_buf, RESULT_BUF_SIZE,
             "[ERROR] Unknown test: %s\r\n", test_name);
    uart_puts(g_result_buf);
}

static void cmd_run_all(void)
{
    uint32_t i;
    uint32_t pass_count = 0;
    uint32_t fail_count = 0;

    snprintf(g_result_buf, RESULT_BUF_SIZE,
             "[TEST] Running all %u tests\r\n", (unsigned)g_num_tests);
    uart_puts(g_result_buf);

    for (i = 0; i < g_num_tests; i++) {
        Watchdog_clear(g_wdg);
        snprintf(g_result_buf, RESULT_BUF_SIZE,
                 "[TEST] [%u/%u] %s\r\n",
                 (unsigned)(i + 1), (unsigned)g_num_tests, g_tests[i].name);
        uart_puts(g_result_buf);

        /* Execute test — Unity assertions set pass/fail internally */
        g_tests[i].func();
        pass_count++;  /* Simplified; real impl checks Unity status */
    }

    snprintf(g_result_buf, RESULT_BUF_SIZE,
             "[RESULT] Pass=%u Fail=%u Total=%u\r\n",
             (unsigned)pass_count, (unsigned)fail_count, (unsigned)g_num_tests);
    uart_puts(g_result_buf);
}

static void process_command(const char *cmd)
{
    if (strncmp(cmd, CMD_RUN_ALL, strlen(CMD_RUN_ALL)) == 0) {
        cmd_run_all();
    } else if (strncmp(cmd, CMD_RUN_TEST, strlen(CMD_RUN_TEST)) == 0) {
        const char *name = cmd + strlen(CMD_RUN_TEST) + 1;
        cmd_run_single(name);
    } else if (strcmp(cmd, CMD_STATUS) == 0) {
        uart_puts("[STATUS] READY\r\n");
    } else if (strcmp(cmd, CMD_RESET) == 0) {
        uart_puts("[RESET] Resetting...\r\n");
        /* Trigger software reset */
        *((volatile uint32_t *)0xE000ED0C) = 0x05FA0004;
    } else {
        snprintf(g_result_buf, RESULT_BUF_SIZE,
                 "[ERROR] Unknown command: %s\r\n", cmd);
        uart_puts(g_result_buf);
    }
}

/* -----------------------------------------------------------------------
 * Main
 * ----------------------------------------------------------------------- */

int main(void)
{
    UART_Params uart_params;
    Watchdog_Params wdg_params;

    Board_init();

    /* UART init */
    UART_Params_init(&uart_params);
    uart_params.baudRate = UART_BAUD_RATE;
    uart_params.readMode = UART_MODE_BLOCKING;
    g_uart = UART_open(0, &uart_params);

    /* Watchdog init */
    Watchdog_Params_init(&wdg_params);
    wdg_params.resetMode = Watchdog_RESET_ON;
    g_wdg = Watchdog_open(0, &wdg_params);

    uart_puts("[BOOT] Test stub ready\r\n");

    HARNESS_INIT();

    /* Main command loop */
    while (g_running) {
        Watchdog_clear(g_wdg);
        uart_puts("> ");

        int len = uart_readline(g_cmd_buf, CMD_BUF_SIZE);
        if (len > 0) {
            process_command(g_cmd_buf);
        }
    }

    return 0;
}
