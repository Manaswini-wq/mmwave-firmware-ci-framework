@;
@; core_state_capture.S
@;
@; ARM Cortex-R5 assembly routine to capture the full core register
@; state into a memory buffer for post-mortem analysis.
@;
@; Saves R0-R15, CPSR, SPSR, and banked registers (FIQ, IRQ, SVC,
@; ABT, UND modes) to a contiguous RAM buffer, then triggers a UART
@; output via a C helper function.
@;
@; Target: TI AWR2944 Cortex-R5F
@; Assembler: TI ARM CGT / GNU AS compatible
@;

    .global core_state_capture
    .global g_register_dump_buf

    .section .text, "ax"
    .arm

@; -----------------------------------------------------------------------
@; Register dump buffer layout (offsets in bytes):
@;   0x00 - 0x3C  : R0-R15   (16 x 4 = 64 bytes)
@;   0x40         : CPSR     (4 bytes)
@;   0x44         : SPSR     (4 bytes)
@;   0x48 - 0x5C  : FIQ banked R8-R12, SP, LR  (7 x 4 = 28 bytes)
@;   0x64 - 0x6C  : IRQ banked SP, LR          (2 x 4 = 8 bytes)
@;   0x6C - 0x74  : SVC banked SP, LR          (2 x 4 = 8 bytes)
@;   0x74 - 0x7C  : ABT banked SP, LR          (2 x 4 = 8 bytes)
@;   0x7C - 0x84  : UND banked SP, LR          (2 x 4 = 8 bytes)
@;   Total: 0x84 = 132 bytes
@; -----------------------------------------------------------------------

    .equ BUF_R0,        0x00
    .equ BUF_CPSR,      0x40
    .equ BUF_SPSR,      0x44
    .equ BUF_FIQ_R8,    0x48
    .equ BUF_IRQ_SP,    0x64
    .equ BUF_SVC_SP,    0x6C
    .equ BUF_ABT_SP,    0x74
    .equ BUF_UND_SP,    0x7C
    .equ BUF_SIZE,      0x84

core_state_capture:
    @; Preserve the link register before we clobber anything
    PUSH    {LR}

    @; Load buffer base address
    LDR     R12, =g_register_dump_buf

    @; Save R0-R11 (R12 is our base pointer, saved separately)
    STR     R0,  [R12, #BUF_R0 + 0x00]
    STR     R1,  [R12, #BUF_R0 + 0x04]
    STR     R2,  [R12, #BUF_R0 + 0x08]
    STR     R3,  [R12, #BUF_R0 + 0x0C]
    STR     R4,  [R12, #BUF_R0 + 0x10]
    STR     R5,  [R12, #BUF_R0 + 0x14]
    STR     R6,  [R12, #BUF_R0 + 0x18]
    STR     R7,  [R12, #BUF_R0 + 0x1C]
    STR     R8,  [R12, #BUF_R0 + 0x20]
    STR     R9,  [R12, #BUF_R0 + 0x24]
    STR     R10, [R12, #BUF_R0 + 0x28]
    STR     R11, [R12, #BUF_R0 + 0x2C]

    @; Save R12 (original value was in R12 before we loaded the base)
    MOV     R0, R12
    STR     R0,  [R12, #BUF_R0 + 0x30]

    @; Save SP (R13) and LR (R14)
    STR     SP,  [R12, #BUF_R0 + 0x34]
    STR     LR,  [R12, #BUF_R0 + 0x38]

    @; Save PC (R15) — approximate: address of this instruction
    ADR     R0, .
    STR     R0,  [R12, #BUF_R0 + 0x3C]

    @; Save CPSR
    MRS     R0, CPSR
    STR     R0,  [R12, #BUF_CPSR]

    @; Save SPSR (valid only in exception modes)
    MRS     R0, SPSR
    STR     R0,  [R12, #BUF_SPSR]

    @; --- Save banked registers (switch modes temporarily) ---

    @; Save current mode
    MRS     R1, CPSR

    @; FIQ mode banked registers (R8_fiq - R14_fiq)
    CPS     #0x11               @; Switch to FIQ mode
    STR     R8,  [R12, #BUF_FIQ_R8 + 0x00]
    STR     R9,  [R12, #BUF_FIQ_R8 + 0x04]
    STR     R10, [R12, #BUF_FIQ_R8 + 0x08]
    STR     R11, [R12, #BUF_FIQ_R8 + 0x0C]
    STR     R12, [R12, #BUF_FIQ_R8 + 0x10]
    STR     SP,  [R12, #BUF_FIQ_R8 + 0x14]
    STR     LR,  [R12, #BUF_FIQ_R8 + 0x18]

    @; IRQ mode banked registers (SP_irq, LR_irq)
    CPS     #0x12               @; Switch to IRQ mode
    STR     SP,  [R12, #BUF_IRQ_SP + 0x00]
    STR     LR,  [R12, #BUF_IRQ_SP + 0x04]

    @; SVC mode banked registers (SP_svc, LR_svc)
    CPS     #0x13               @; Switch to SVC mode
    STR     SP,  [R12, #BUF_SVC_SP + 0x00]
    STR     LR,  [R12, #BUF_SVC_SP + 0x04]

    @; ABT mode banked registers (SP_abt, LR_abt)
    CPS     #0x17               @; Switch to ABT mode
    STR     SP,  [R12, #BUF_ABT_SP + 0x00]
    STR     LR,  [R12, #BUF_ABT_SP + 0x04]

    @; UND mode banked registers (SP_und, LR_und)
    CPS     #0x1B               @; Switch to UND mode
    STR     SP,  [R12, #BUF_UND_SP + 0x00]
    STR     LR,  [R12, #BUF_UND_SP + 0x04]

    @; Restore original mode
    MSR     CPSR_c, R1

    @; Call C function to output the buffer via UART
    MOV     R0, R12             @; arg0 = buffer address
    MOV     R1, #BUF_SIZE       @; arg1 = buffer size
    BL      coverage_flush_register_dump

    POP     {PC}

@; -----------------------------------------------------------------------
@; Data section — register dump buffer
@; -----------------------------------------------------------------------

    .section .bss, "aw"
    .align 4
g_register_dump_buf:
    .space  BUF_SIZE
