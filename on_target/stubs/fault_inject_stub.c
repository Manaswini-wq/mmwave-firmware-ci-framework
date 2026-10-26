/*
 * fault_inject_stub.c
 *
 * Fault injection hooks for the mmWave firmware CI framework.
 * These functions are designed to be called from JTAG breakpoint
 * scripts to inject controlled faults into the running firmware
 * for safety mechanism validation.
 *
 * Target: TI AWR2944 / IWR6843
 * Toolchain: TI ARM CGT v20.x
 *
 * WARNING: These functions are for TEST ONLY and must never be
 * included in production firmware builds.
 */

#include <stdint.h>
#include <string.h>

/* -----------------------------------------------------------------------
 * Register definitions
 * ----------------------------------------------------------------------- */

/* Cortex-R5 system control registers */
#define SCR_BASE            0xE000E000
#define AIRCR               (*(volatile uint32_t *)(0xE000ED0C))
#define AIRCR_VECTKEY       0x05FA0000
#define AIRCR_SYSRESETREQ   0x00000004

/* Watchdog registers (TI-specific) */
#define WDG_BASE            0xFFFFFC00
#define WDG_CONTROL         (*(volatile uint32_t *)(WDG_BASE + 0x00))
#define WDG_DISABLE_KEY1    0x0000E51A
#define WDG_DISABLE_KEY2    0x0000A35C

/* Clock module registers */
#define CLK_BASE            0xFFFFFF00
#define CLK_CNTRL           (*(volatile uint32_t *)(CLK_BASE + 0x00))
#define CLK_DISABLE_MASK    0x00000001

/* -----------------------------------------------------------------------
 * Memory corruption injection
 * ----------------------------------------------------------------------- */

/**
 * Inject memory corruption at a specified address.
 *
 * @param addr   Target address in SRAM (must be ECC-protected region)
 * @param mask   Bitmask of bits to flip (XOR)
 */
void fault_inject_memory(volatile uint32_t *addr, uint32_t mask)
{
    uint32_t original = *addr;
    *addr = original ^ mask;
    /* Force a read-back to trigger ECC check */
    volatile uint32_t readback = *addr;
    (void)readback;
}

/**
 * Corrupt a contiguous block of memory with a pattern.
 *
 * @param base   Start address
 * @param len    Number of bytes to corrupt
 * @param pattern Fill pattern
 */
void fault_inject_memory_block(volatile uint8_t *base, uint32_t len,
                               uint8_t pattern)
{
    uint32_t i;
    for (i = 0; i < len; i++) {
        base[i] = pattern;
    }
}

/* -----------------------------------------------------------------------
 * Register corruption
 * ----------------------------------------------------------------------- */

/**
 * Corrupt a general-purpose register via inline assembly.
 * The caller selects the register index (0-12).
 *
 * @param reg_index  Register number (0 = R0, ... 12 = R12)
 * @param value      Value to write
 */
void fault_inject_register(uint32_t reg_index, uint32_t value)
{
    /* Use R0 as a representative example; in a real implementation
       a jump table or computed branch would select the register. */
    switch (reg_index) {
        case 0:  __asm volatile("MOV R0, %0" : : "r"(value)); break;
        case 1:  __asm volatile("MOV R1, %0" : : "r"(value)); break;
        case 2:  __asm volatile("MOV R2, %0" : : "r"(value)); break;
        case 3:  __asm volatile("MOV R3, %0" : : "r"(value)); break;
        default: break;  /* Higher registers omitted for brevity */
    }
}

/* -----------------------------------------------------------------------
 * Watchdog disable (trigger timeout)
 * ----------------------------------------------------------------------- */

/**
 * Disable the watchdog counter so that it will never be serviced,
 * forcing a watchdog timeout reset.
 */
void fault_inject_watchdog_timeout(void)
{
    /* Write the disable sequence to the watchdog control register */
    WDG_CONTROL = WDG_DISABLE_KEY1;
    WDG_CONTROL = WDG_DISABLE_KEY2;
    /* With the watchdog disabled from servicing but the timer still
       running, the next timeout will trigger a reset. */
}

/* -----------------------------------------------------------------------
 * Clock disable for timeout injection
 * ----------------------------------------------------------------------- */

/**
 * Disable the peripheral clock to a specified module to induce
 * communication timeouts on that bus.
 *
 * @param module_offset  Offset into the clock control register bank
 */
void fault_inject_clock_disable(uint32_t module_offset)
{
    volatile uint32_t *clk_reg =
        (volatile uint32_t *)(CLK_BASE + module_offset);
    *clk_reg &= ~CLK_DISABLE_MASK;
}

/* -----------------------------------------------------------------------
 * Software reset (for recovery after fault injection)
 * ----------------------------------------------------------------------- */

/**
 * Trigger a full system reset via the Application Interrupt and
 * Reset Control Register.
 */
void fault_inject_system_reset(void)
{
    AIRCR = AIRCR_VECTKEY | AIRCR_SYSRESETREQ;
    /* Should not reach here */
    while (1) { ; }
}
