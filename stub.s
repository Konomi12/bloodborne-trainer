# Wstawka trainera w głównej pętli Bloodborne 1.09 (zamiast `lea rax,[rip+...]` pod 0x802018e3d).
# Po zmianie: as --64 stub.s -o stub.o && objcopy -O binary -j .text stub.o stub.bin
# i wkleić bajty do STUB w engine.py.
.intel_syntax noprefix
start:
  movabs r11, 0x00000008056D3800          # skrzynka (MAILBOX)
  inc qword ptr [r11+0x58]                # licznik klatek
  vmovss xmm0, dword ptr [rbp-0x38]       # krok czasu tej klatki
  vmulss xmm0, xmm0, dword ptr [r11+0x08] # * prędkość gry
  vmovss dword ptr [rbp-0x38], xmm0
  mov eax, dword ptr [r11+0x0C]           # zlecenie != potwierdzenie -> wywołaj
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
  movabs rax, 0x0000000805540510          # to, co robiła zastąpiona instrukcja
  movabs r11, 0x0000000802018E44
  jmp r11
