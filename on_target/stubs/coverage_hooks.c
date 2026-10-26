/*
 * coverage_hooks.c
 *
 * Minimal-overhead coverage collection hooks for on-target firmware
 * code coverage during CI test runs.
 *
 * Implements function entry/exit tracing and branch tracking via a
 * bitmap that is flushed to the host over UART on demand.
 *
 * Target: TI AWR2944 / IWR6843
 * Toolchain: TI ARM CGT v20.x  (compile with --instrument_functions)
 */

#include <stdint.h>
#include <string.h>

#include "ti/drivers/UART.h"

/* -----------------------------------------------------------------------
 * Definitions
 * ----------------------------------------------------------------------- */

/* Maximum number of unique function addresses tracked */
#define MAX_FUNCTIONS       1024

/* Branch bitmap size (bits) — covers up to 8192 branch points */
#define BRANCH_BITMAP_BYTES 1024

/* Sentinel value for empty function slots */
#define FUNC_SLOT_EMPTY     0xFFFFFFFF

/* -----------------------------------------------------------------------
 * Coverage data buffers (placed in non-cached SRAM)
 * ----------------------------------------------------------------------- */

#pragma DATA_SECTION(g_func_addrs, ".coverage_data")
static uint32_t g_func_addrs[MAX_FUNCTIONS];

#pragma DATA_SECTION(g_func_counts, ".coverage_data")
static uint32_t g_func_counts[MAX_FUNCTIONS];

#pragma DATA_SECTION(g_branch_bitmap, ".coverage_data")
static uint8_t  g_branch_bitmap[BRANCH_BITMAP_BYTES];

static uint32_t g_func_count = 0;
static UART_Handle g_cov_uart = NULL;

/* -----------------------------------------------------------------------
 * Initialisation
 * ----------------------------------------------------------------------- */

void coverage_init(UART_Handle uart)
{
    g_cov_uart = uart;
    g_func_count = 0;
    memset(g_func_addrs, 0xFF, sizeof(g_func_addrs));
    memset(g_func_counts, 0, sizeof(g_func_counts));
    memset(g_branch_bitmap, 0, sizeof(g_branch_bitmap));
}

/* -----------------------------------------------------------------------
 * Function entry / exit hooks
 *
 * Called automatically by the compiler when -finstrument-functions or
 * the TI equivalent --instrument_functions is enabled.
 * ----------------------------------------------------------------------- */

static int find_or_add_func(uint32_t addr)
{
    uint32_t i;
    /* Linear scan — acceptable for small function counts */
    for (i = 0; i < g_func_count; i++) {
        if (g_func_addrs[i] == addr) {
            return (int)i;
        }
    }
    if (g_func_count < MAX_FUNCTIONS) {
        g_func_addrs[g_func_count] = addr;
        g_func_counts[g_func_count] = 0;
        return (int)(g_func_count++);
    }
    return -1;  /* table full */
}

void __cyg_profile_func_enter(void *this_fn,
                               void *call_site __attribute__((unused)))
{
    int idx = find_or_add_func((uint32_t)this_fn);
    if (idx >= 0) {
        g_func_counts[idx]++;
    }
}

void __cyg_profile_func_exit(void *this_fn __attribute__((unused)),
                              void *call_site __attribute__((unused)))
{
    /* Exit hook intentionally lightweight — only entry is counted. */
}

/* -----------------------------------------------------------------------
 * Branch tracking
 * ----------------------------------------------------------------------- */

/**
 * Record that branch point `id` was taken.
 * Designed to be inserted by a source-level instrumentation pass.
 */
void coverage_branch_taken(uint32_t branch_id)
{
    uint32_t byte_idx = branch_id >> 3;
    uint8_t  bit_mask = (uint8_t)(1u << (branch_id & 7));
    if (byte_idx < BRANCH_BITMAP_BYTES) {
        g_branch_bitmap[byte_idx] |= bit_mask;
    }
}

/* -----------------------------------------------------------------------
 * Flush coverage data to UART
 * ----------------------------------------------------------------------- */

void coverage_flush(void)
{
    if (g_cov_uart == NULL) {
        return;
    }

    /* Header */
    const char header[] = "[COV_START]\r\n";
    UART_write(g_cov_uart, header, sizeof(header) - 1);

    /* Function hit counts */
    uint32_t i;
    char line[80];
    for (i = 0; i < g_func_count; i++) {
        int len = snprintf(line, sizeof(line), "F 0x%08X %u\r\n",
                           (unsigned)g_func_addrs[i],
                           (unsigned)g_func_counts[i]);
        UART_write(g_cov_uart, line, (uint32_t)len);
    }

    /* Branch bitmap (hex-encoded) */
    UART_write(g_cov_uart, "B ", 2);
    for (i = 0; i < BRANCH_BITMAP_BYTES; i++) {
        char hex[3];
        snprintf(hex, sizeof(hex), "%02X", g_branch_bitmap[i]);
        UART_write(g_cov_uart, hex, 2);
    }
    UART_write(g_cov_uart, "\r\n", 2);

    /* Footer */
    const char footer[] = "[COV_END]\r\n";
    UART_write(g_cov_uart, footer, sizeof(footer) - 1);
}
