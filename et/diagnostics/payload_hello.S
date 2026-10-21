// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2025 Ainekko, Co.
//
// Minimal S-mode test payload for OpenSBI FW_PAYLOAD on the ET-SoC-1 Maxion:
//   * prints a line through the SBI console (legacy extension 0x01, one ecall
//     per character) and one through the Debug Console extension,
//   * then brings up the other harts one after the other with SBI HSM
//     hart_start (what Linux does for SMP) -- each one prints its hartid --
//     and parks.
// Position independent (no GOT: .option nopic), no stack, no memory other
// than the code itself and one flag word.
        .option nopic                   // la -> auipc/addi (PC-relative), not GOT loads
        .section .text
        .globl _start
_start:
        mv      s1, a0                  // our hartid (boot hart)
        la      s0, msg
        jal     ra, puts
        la      a1, msg2                // DBCN: sbi_debug_console_write(num_bytes, lo, hi)
        la      a0, msg2_end
        sub     a0, a0, a1
        li      a2, 0
        li      a7, 0x4442434E          // SBI_EXT_DBCN
        li      a6, 0                   // SBI_EXT_DBCN_CONSOLE_WRITE
        ecall

        // secondaries: for hart = 0..3, hart != me: hart_start(hart, secondary, hart)
        li      s2, 0
1:      beq     s2, s1, 3f
        la      t0, flag
        sw      zero, 0(t0)
        la      s0, msg_start
        jal     ra, puts
        mv      a0, s2
        jal     ra, puthex1
        la      s0, msg_crlf
        jal     ra, puts
        mv      a0, s2                  // hartid
        la      a1, secondary           // start address
        mv      a2, s2                  // opaque (a1 of the started hart)
        li      a7, 0x48534D            // SBI_EXT_HSM
        li      a6, 0                   // SBI_EXT_HSM_HART_START
        ecall
        mv      s3, a0                  // sbi error code (0 = SBI_SUCCESS, -ve otherwise)
        // wait (bounded) for the secondary's flag before printing anything else,
        // the secondary prints its own line meanwhile (no locking in this toy)
        li      t1, 0x4000000
2:      la      t0, flag
        lw      t2, 0(t0)
        bnez    t2, 8f
        bnez    s3, 8f                  // start refused: do not wait
        addi    t1, t1, -1
        bnez    t1, 2b
        la      s0, msg_timeout
        jal     ra, puts
8:      la      s0, msg_rc
        jal     ra, puts
        mv      a0, s3
        jal     ra, puthex1             // low nibble of the error code
        la      s0, msg_crlf
        jal     ra, puts
3:      addi    s2, s2, 1
        li      t0, 4
        blt     s2, t0, 1b
        la      s0, msg_done
        jal     ra, puts
4:      wfi
        j       4b

        // secondary hart entry: a0 = hartid, a1 = opaque
secondary:
        mv      s1, a0
        la      s0, msg_sec
        jal     ra, puts
        mv      a0, s1
        jal     ra, puthex1
        la      s0, msg_crlf
        jal     ra, puts
        la      t0, flag
        li      t1, 1
        sw      t1, 0(t0)
5:      wfi
        j       5b

        // puts: s0 -> NUL-terminated string, clobbers a0, a6, a7, t3; link in ra
puts:   mv      t3, ra
6:      lbu     a0, 0(s0)
        beqz    a0, 7f
        li      a7, 0x1                 // SBI_EXT_0_1_CONSOLE_PUTCHAR
        li      a6, 0
        ecall
        addi    s0, s0, 1
        j       6b
7:      jr      t3
        // puthex1: print the low nibble of a0 as a hex digit (clobbers a6, a7)
puthex1:
        mv      t3, ra
        andi    a0, a0, 0xf
        la      t0, hexdigits
        add     t0, t0, a0
        lbu     a0, 0(t0)
        li      a7, 0x1
        li      a6, 0
        ecall
        jr      t3

        .section .data
        .align  3
flag:   .word   0
msg:    .asciz  "\r\nHello from S-mode on the ET-SoC-1 Maxion (SBI legacy console)\r\n"
msg2:   .ascii  "Hello again via SBI DBCN.\r\n"
msg2_end:
msg_start:   .asciz "sbi_hart_start(hart "
msg_rc:      .asciz ") rc="
msg_sec:     .asciz "hello from secondary hart "
msg_timeout: .asciz "(no sign of life from that hart) "
msg_done:    .asciz "All done, parking.\r\n"
msg_crlf:    .asciz "\r\n"
hexdigits:   .ascii "0123456789abcdef"
