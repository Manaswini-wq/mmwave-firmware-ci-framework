/*
 * unity_runner.c
 *
 * Unity test framework runner for on-target execution on the
 * TI AWR2944 / IWR6843 mmWave radar sensor.
 *
 * Integrates Unity's output with the board UART, registers all
 * on-target test suites, and provides setUp/tearDown hooks for
 * hardware state management.
 *
 * Target: TI AWR2944 / IWR6843
 * Toolchain: TI ARM CGT v20.x
 * Dependencies: Unity (ThrowTheSwitch), TI Drivers
 */

#include <stdint.h>
#include <string.h>
#include <stdio.h>

#include "unity.h"
#include "test_harness.h"
#include "ti/drivers/UART.h"
#include "ti/drivers/Watchdog.h"
#include "ti/board/board.h"

/* -----------------------------------------------------------------------
 * Globals
 * ----------------------------------------------------------------------- */

static UART_Handle  g_uart       = NULL;
static Watchdog_Handle g_wdg     = NULL;
static uint32_t     g_test_count = 0;
static uint32_t     g_fail_count = 0;

/* -----------------------------------------------------------------------
 * Unity output redirection
 *
 * Unity calls putchar-style output; redirect it to our UART handle.
 * ----------------------------------------------------------------------- */

void unity_output_char(char c)
{
    if (g_uart != NULL) {
        UART_write(g_uart, &c, 1);
    }
}

void unity_output_string(const char *str)
{
    if (g_uart != NULL) {
        UART_write(g_uart, str, strlen(str));
    }
}

/* -----------------------------------------------------------------------
 * setUp / tearDown hooks
 *
 * Called by Unity before and after each individual test case.
 * ----------------------------------------------------------------------- */

void setUp(void)
{
    /* Service the watchdog so long-running suites don't trigger a reset */
    if (g_wdg != NULL) {
        Watchdog_clear(g_wdg);
    }
    g_test_count++;
}

void tearDown(void)
{
    /* Collect any per-test cleanup here (e.g. flush DMA, reset GPIO) */
    if (Unity.CurrentTestFailed) {
        g_fail_count++;
    }
}

/* -----------------------------------------------------------------------
 * Test declarations (extern — defined in individual test_*.c files)
 * ----------------------------------------------------------------------- */

/* Safety tests */
extern void test_watchdog_fires_on_hang(void);
extern void test_ecc_single_bit_correction(void);
extern void test_ecc_double_bit_detection(void);
extern void test_lockstep_mismatch_detected(void);
extern void test_safe_state_entry(void);

/* Data path tests */
extern void test_adc_buffer_filled(void);
extern void test_chirp_interrupt_fires(void);
extern void test_frame_counter_increments(void);

/* BIST tests */
extern void test_pbist_ram_check(void);
extern void test_lbist_logic_check(void);

/* -----------------------------------------------------------------------
 * Suite runner
 * ----------------------------------------------------------------------- */

static void run_safety_suite(void)
{
    RUN_TEST(test_watchdog_fires_on_hang);
    RUN_TEST(test_ecc_single_bit_correction);
    RUN_TEST(test_ecc_double_bit_detection);
    RUN_TEST(test_lockstep_mismatch_detected);
    RUN_TEST(test_safe_state_entry);
}

static void run_datapath_suite(void)
{
    RUN_TEST(test_adc_buffer_filled);
    RUN_TEST(test_chirp_interrupt_fires);
    RUN_TEST(test_frame_counter_increments);
}

static void run_bist_suite(void)
{
    RUN_TEST(test_pbist_ram_check);
    RUN_TEST(test_lbist_logic_check);
}

/* -----------------------------------------------------------------------
 * Main entry point
 * ----------------------------------------------------------------------- */

int main(void)
{
    UART_Params     uart_params;
    Watchdog_Params wdg_params;
    char            msg[128];

    /* Board and driver initialisation */
    Board_init();

    UART_Params_init(&uart_params);
    uart_params.baudRate  = 115200;
    uart_params.readMode  = UART_MODE_BLOCKING;
    uart_params.writeMode = UART_MODE_BLOCKING;
    g_uart = UART_open(0, &uart_params);

    Watchdog_Params_init(&wdg_params);
    wdg_params.resetMode = Watchdog_RESET_ON;
    g_wdg = Watchdog_open(0, &wdg_params);

    /* Banner */
    unity_output_string("\r\n");
    unity_output_string("========================================\r\n");
    unity_output_string(" mmWave On-Target Test Runner (Unity)\r\n");
    unity_output_string("========================================\r\n");

    HARNESS_INIT();

    /* Run all suites */
    UNITY_BEGIN();

    unity_output_string("\r\n--- Safety Suite ---\r\n");
    run_safety_suite();

    unity_output_string("\r\n--- Data Path Suite ---\r\n");
    run_datapath_suite();

    unity_output_string("\r\n--- BIST Suite ---\r\n");
    run_bist_suite();

    int result = UNITY_END();

    /* Summary over UART for host parsing */
    snprintf(msg, sizeof(msg),
             "\r\n[RESULT] Total=%u Fail=%u Status=%s\r\n",
             (unsigned)g_test_count,
             (unsigned)g_fail_count,
             (result == 0) ? "PASS" : "FAIL");
    unity_output_string(msg);

    HARNESS_COMPLETE(result);

    /* Halt — host will power-cycle or reset via JTAG */
    while (1) {
        Watchdog_clear(g_wdg);
    }

    return 0;
}
