# ===========================================================================
# Makefile — Build on-target test stubs with TI ARM CGT
#
# Target:    TI AWR2944 Cortex-R5F
# Toolchain: TI ARM Code Generation Tools v20.x
# ===========================================================================

# --- Toolchain paths (override via environment or command line) ---
CGT_ROOT   ?= C:/ti/ti-cgt-arm_20.2.7.LTS
CC          = $(CGT_ROOT)/bin/armcl
AS          = $(CGT_ROOT)/bin/armasm
LD          = $(CGT_ROOT)/bin/armlnk
UNITY_ROOT ?= ../../third_party/unity

# --- Device and SDK ---
SDK_ROOT   ?= C:/ti/mmwave_sdk_03_06
DEVICE      = AWR2944
LINKER_CMD  = $(SDK_ROOT)/packages/ti/platform/$(DEVICE)/r5f_linker.cmd

# --- Directories ---
STUB_DIR    = ../stubs
HARNESS_DIR = .
OBJ_DIR     = obj
BIN_DIR     = bin

# --- Source files ---
C_SRCS  = $(HARNESS_DIR)/unity_runner.c       \
          $(STUB_DIR)/test_stub_main.c         \
          $(STUB_DIR)/fault_inject_stub.c      \
          $(STUB_DIR)/coverage_hooks.c         \
          $(UNITY_ROOT)/src/unity.c

ASM_SRCS = $(STUB_DIR)/core_state_capture.S

# --- Object files ---
C_OBJS   = $(patsubst %.c, $(OBJ_DIR)/%.obj, $(notdir $(C_SRCS)))
ASM_OBJS = $(patsubst %.S, $(OBJ_DIR)/%.obj, $(notdir $(ASM_SRCS)))
OBJS     = $(C_OBJS) $(ASM_OBJS)

# --- Compiler / assembler flags ---
CFLAGS  = --silicon_version=7R5           \
          --code_state=32                 \
          --float_support=vfpv3d16        \
          -O2                             \
          --diag_warning=225              \
          --display_error_number          \
          --instrument_functions          \
          -I$(CGT_ROOT)/include           \
          -I$(SDK_ROOT)/packages          \
          -I$(UNITY_ROOT)/src             \
          -I$(HARNESS_DIR)                \
          -DUNITY_OUTPUT_CHAR=unity_output_char

AFLAGS  = --silicon_version=7R5

LFLAGS  = --rom_model                    \
          --heap_size=0x4000              \
          --stack_size=0x2000             \
          -i$(CGT_ROOT)/lib              \
          -lrtsv7R4_T_le_v3D16_eabi.lib

# --- Targets ---
TARGET  = $(BIN_DIR)/test_firmware.out

.PHONY: all clean dirs

all: dirs $(TARGET)

dirs:
	@if not exist $(OBJ_DIR) mkdir $(OBJ_DIR)
	@if not exist $(BIN_DIR) mkdir $(BIN_DIR)

$(TARGET): $(OBJS) $(LINKER_CMD)
	$(LD) $(LFLAGS) -o $@ $(OBJS) $(LINKER_CMD)
	@echo [LINK] $@

$(OBJ_DIR)/%.obj: $(HARNESS_DIR)/%.c
	$(CC) $(CFLAGS) -c $< --output_file=$@

$(OBJ_DIR)/%.obj: $(STUB_DIR)/%.c
	$(CC) $(CFLAGS) -c $< --output_file=$@

$(OBJ_DIR)/%.obj: $(UNITY_ROOT)/src/%.c
	$(CC) $(CFLAGS) -c $< --output_file=$@

$(OBJ_DIR)/%.obj: $(STUB_DIR)/%.S
	$(AS) $(AFLAGS) $< -o $@

clean:
	@if exist $(OBJ_DIR) rmdir /s /q $(OBJ_DIR)
	@if exist $(BIN_DIR) rmdir /s /q $(BIN_DIR)
	@echo Clean complete.
