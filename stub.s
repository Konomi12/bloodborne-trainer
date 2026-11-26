# The trainer's stub in the Bloodborne 1.09 main loop (replaces `lea rax,[rip+...]` at 0x802018e3d).
# After a change: as --64 stub.s -o stub.o && objcopy -O binary -j .text stub.o stub.bin
# and paste the bytes into STUB in engine.py.
.intel_syntax noprefix
start:
  movabs r11, 0x00000008056D3800          # the mailbox (MAILBOX)
  inc qword ptr [r11+0x58]                # frame counter
  vmovss xmm0, dword ptr [rbp-0x38]       # this frame's time step
  vmulss xmm0, xmm0, dword ptr [r11+0x08] # * game speed
  vmovss dword ptr [rbp-0x38], xmm0
  mov eax, dword ptr [r11+0x0C]           # request != acknowledge -> call
  cmp eax, dword ptr [r11+0x10]
  je done
  push rbx
  push r12
  push r13
  push r14
  mov r12d, eax
  mov r13, r11
  mov rbx, rsp
  and rsp, -16
  sub rsp, 16                             # the seventh argument goes on the stack
  mov rax, qword ptr [r13+0x60]
  mov qword ptr [rsp], rax
  mov rdi, qword ptr [r13+0x20]
  mov rsi, qword ptr [r13+0x28]
  mov rdx, qword ptr [r13+0x30]
  mov rcx, qword ptr [r13+0x38]
  mov r8,  qword ptr [r13+0x40]
  mov r9,  qword ptr [r13+0x48]
  call qword ptr [r13+0x18]
  mov qword ptr [r13+0x50], rax
  mov dword ptr [r13+0x10], r12d
  mov rsp, rbx
  pop r14
  pop r13
  pop r12
  pop rbx
done:
  movabs rax, 0x0000000805540510          # what the replaced instruction did
  movabs r11, 0x0000000802018E44
  jmp r11
