# Canonical Linux amd64 tagged ordinary-Int runtime. Regenerate with
# python3 tools/selfhost/emit_integer.py; --check rejects emitter drift.
# Exported helpers200..210 use RAX/RCX operands and preserve RBX/RBP/R12..R15.
# Bigint: GC header24, signed sign24, limb count32, packed uint32 limbs40.
# Every limb is <2^30. No input object is mutated. Zero is always immediate1.
# Arithmetic copies operands into checked anonymous mmap scratch before its
# sole managed allocation. The scratch contains no pointers and is unmapped
# before return. Allocation failures terminate through the runtime failure ABI.
# All internal branches are relative within this one uninterrupted text stream;
# exported calls and failure edges become native Machine relocation records.
.intel_syntax noprefix
.text
.global mgn_add,mgn_sub,mgn_mul,mgn_div,mgn_rem,mgn_cmp,mgn_neg,mgn_signed,mgn_unsigned,mgn_word,mgn_construct
mgn_add:
 mov r8d,0
 jmp fast_binary
mgn_sub:
 mov r8d,1
 jmp fast_binary
mgn_mul:
 mov r8d,2
 jmp fast_binary
mgn_div:
 mov r8d,3
 jmp fast_binary
mgn_rem:
 mov r8d,4
 jmp fast_binary
mgn_cmp:
 mov r8d,5
 jmp fast_binary
mgn_neg:
 test al,1
 jz neg_slow
 mov r8d,6
 mov r9,rax
 sar r9,1
 neg r9
 jmp fast_range
neg_slow:
 mov rcx,1
 mov r8d,1
 xchg rax,rcx
 jmp common
fast_binary:
 test al,1
 jz common
 test cl,1
 jz common
 mov r9,rax
 mov r10,rcx
 sar r9,1
 sar r10,1
 cmp r8d,0
 je fast_add
 cmp r8d,1
 je fast_sub
 cmp r8d,2
 je fast_mul
 cmp r8d,5
 je fast_cmp
 test r10,r10
 jz mgn_zero_failure
 mov r11,rax
 mov rax,r9
 cqo
 idiv r10
 cmp r8d,4
 je fast_rem
 mov r9,rax
 mov rax,r11
 jmp fast_range
fast_rem:
 mov r9,rdx
 jmp fast_tag
fast_add:
 add r9,r10
 jmp fast_range
fast_sub:
 sub r9,r10
 jmp fast_range
fast_mul:
 imul r9,r10
 jo common
fast_range:
 mov r11,r9
 shl r11,1
 sar r11,1
 cmp r11,r9
 jne fast_range_slow
fast_tag:
 lea rax,[r9+r9+1]
 ret
fast_range_slow:
 cmp r8d,5
 ja neg_slow
 jmp common
fast_cmp:
 cmp r9,r10
 mov eax,0
 mov edx,1
 mov rcx,-1
 cmovg rax,rdx
 cmovl rax,rcx
 ret
# Unpack into a borrowed limb view or the caller's three-word scratch.
# RAX tagged input, RSI scratch -> RSI limbs, RCX count, RDX sign.
unpack:
 test al,1
 jz unpack_big
 sar rax,1
 mov edx,1
 test rax,rax
 jns unpack_magnitude
 neg rax
 mov rdx,-1
unpack_magnitude:
 mov r9,rax
 and eax,1073741823
 mov DWORD PTR [rsi],eax
 shr r9,30
 mov rax,r9
 and eax,1073741823
 mov DWORD PTR [rsi+4],eax
 shr r9,30
 mov DWORD PTR [rsi+8],r9d
 mov ecx,3
unpack_trim:
 test rcx,rcx
 jz unpack_zero
 cmp DWORD PTR [rsi+rcx*4-4],0
 jne unpack_ret
 dec rcx
 jmp unpack_trim
unpack_zero:
 mov edx,1
unpack_ret: ret
unpack_big:
 mov rdx,[rax+24]
 mov rcx,[rax+32]
 lea rsi,[rax+40]
 ret
# Compare unsigned limb views. RDI lhs / RCX length; RSI rhs / RDX length.
compare:
 cmp rcx,rdx
 jb compare_less
 ja compare_more
compare_loop:
 test rcx,rcx
 jz compare_equal
 dec rcx
 mov eax,DWORD PTR [rdi+rcx*4]
 cmp eax,DWORD PTR [rsi+rcx*4]
 jb compare_less
 ja compare_more
 jmp compare_loop
compare_equal: xor eax,eax
 ret
compare_less: mov rax,-1
 ret
compare_more: mov eax,1
 ret
common:
 push rbp
 mov rbp,rsp
 push rbx
 push r12
 push r13
 push r14
 push r15
 sub rsp,232
 mov [rbp-48],r8
 mov [rbp-216],rcx
 lea rsi,[rbp-192]
 call unpack
 mov [rbp-56],rdx
 mov [rbp-64],rcx
 mov [rbp-72],rsi
 mov rax,[rbp-216]
 lea rsi,[rbp-208]
 call unpack
 mov [rbp-80],rdx
 mov [rbp-88],rcx
 mov [rbp-96],rsi
 cmp QWORD PTR [rbp-48],5
 je common_compare
 cmp QWORD PTR [rbp-48],3
 jb common_size
 cmp QWORD PTR [rbp-88],0
 je mgn_zero_failure
common_size:
 mov rax,[rbp-64]
 add rax,[rbp-88]
 jo mgn_allocation_failure
 add rax,4
 jo mgn_allocation_failure
 mov [rbp-120],rax
 mov rsi,rax
 shl rsi,4
 shr rsi,4
 cmp rax,rsi
 jne mgn_allocation_failure
 mov rsi,rax
 shl rsi,4
 add rsi,4095
 jc mgn_allocation_failure
 and rsi,-4096
 test rsi,rsi
 jle mgn_allocation_failure
 mov [rbp-112],rsi
 xor edi,edi
 mov eax,9
 mov edx,3
 mov r10d,34
 mov r8,-1
 xor r9d,r9d
 syscall
 cmp rax,-4095
 jae mgn_allocation_failure
 mov [rbp-104],rax
 mov r12,rax
 mov rcx,[rbp-120]
 lea r13,[rax+rcx*4]
 lea r14,[r13+rcx*4]
 lea rbx,[r14+rcx*4]
 mov rsi,[rbp-72]
 mov rdi,r12
 mov rcx,[rbp-64]
 rep movsd
 mov rsi,[rbp-96]
 mov rdi,r13
 mov rcx,[rbp-88]
 rep movsd
 mov rax,[rbp-56]
 mov [rbp-152],rax
 mov rax,[rbp-48]
 cmp rax,2
 je multiply_start
 cmp rax,3
 jae divide_start
 cmp rax,1
 jne add_signs
 neg QWORD PTR [rbp-80]
add_signs:
 mov rax,[rbp-56]
 cmp rax,[rbp-80]
 jne subtract_start
 xor r8d,r8d
 xor r9d,r9d
 mov r10,[rbp-64]
 cmp r10,[rbp-88]
 jae add_loop
 mov r10,[rbp-88]
add_loop:
 cmp r8,r10
 jae add_finish
 mov rax,r9
 cmp r8,[rbp-64]
 jae add_right
 mov edx,DWORD PTR [r12+r8*4]
 add rax,rdx
add_right:
 cmp r8,[rbp-88]
 jae add_store
 mov edx,DWORD PTR [r13+r8*4]
 add rax,rdx
add_store:
 mov r9,rax
 shr r9,30
 and eax,1073741823
 mov DWORD PTR [r14+r8*4],eax
 inc r8
 jmp add_loop
add_finish:
 mov DWORD PTR [r14+r8*4],r9d
 inc r8
 mov [rbp-144],r8
 jmp common_finish
subtract_start:
 mov rdi,r12
 mov rsi,r13
 mov rcx,[rbp-64]
 mov rdx,[rbp-88]
 call compare
 test rax,rax
 jns subtract_ordered
 xchg r12,r13
 mov rax,[rbp-64]
 xchg rax,[rbp-88]
 mov [rbp-64],rax
 mov rax,[rbp-80]
 mov [rbp-152],rax
subtract_ordered:
 xor r8d,r8d
 xor r9d,r9d
 mov r10,[rbp-64]
subtract_loop:
 cmp r8,r10
 jae subtract_finish
 mov eax,DWORD PTR [r12+r8*4]
 sub rax,r9
 xor r9d,r9d
 cmp r8,[rbp-88]
 jae subtract_borrow
 mov edx,DWORD PTR [r13+r8*4]
 sub rax,rdx
subtract_borrow:
 test rax,rax
 jns subtract_store
 add rax,1073741824
 mov r9d,1
subtract_store:
 mov DWORD PTR [r14+r8*4],eax
 inc r8
 jmp subtract_loop
subtract_finish:
 mov [rbp-144],r10
 jmp common_finish
multiply_start:
 mov rax,[rbp-56]
 imul rax,[rbp-80]
 mov [rbp-152],rax
 xor r8d,r8d
multiply_outer:
 cmp r8,[rbp-64]
 jae multiply_finish
 xor r9d,r9d
 xor r10d,r10d
multiply_inner:
 cmp r9,[rbp-88]
 jae multiply_carry
 mov eax,DWORD PTR [r12+r8*4]
 mov edx,DWORD PTR [r13+r9*4]
 imul rax,rdx
 lea r11,[r8+r9]
 mov edx,DWORD PTR [r14+r11*4]
 add rax,rdx
 add rax,r10
 mov r10,rax
 shr r10,30
 and eax,1073741823
 mov DWORD PTR [r14+r11*4],eax
 inc r9
 jmp multiply_inner
multiply_carry:
 lea r11,[r8+r9]
 mov DWORD PTR [r14+r11*4],r10d
 inc r8
 jmp multiply_outer
multiply_finish:
 mov rax,[rbp-64]
 add rax,[rbp-88]
 mov [rbp-144],rax
 jmp common_finish
# Binary long division. Workspaces remain private and immutable inputs untouched.
divide_start:
 cmp QWORD PTR [rbp-88],1
 jne divide_multiple_limbs
 # A single-limb divisor carries a bounded remainder from high to low.
 mov r8,[rbp-64]
 mov r10d,DWORD PTR [r13]
 xor r9d,r9d
divide_single_loop:
 test r8,r8
 jz divide_single_done
 dec r8
 mov rax,r9
 shl rax,30
 mov edx,DWORD PTR [r12+r8*4]
 or rax,rdx
 xor edx,edx
 div r10
 mov DWORD PTR [r14+r8*4],eax
 mov r9,rdx
 jmp divide_single_loop
divide_single_done:
 mov DWORD PTR [rbx],r9d
 xor eax,eax
 test r9,r9
 setne al
 mov [rbp-176],rax
 jmp divide_finish
divide_multiple_limbs:
 mov rax,[rbp-64]
 imul rax,30
 jo common_resource_failure
 dec rax
 mov [rbp-168],rax
 mov QWORD PTR [rbp-176],0
divide_bit:
 mov rax,[rbp-168]
 test rax,rax
 js divide_finish
 xor edx,edx
 mov ecx,30
 div rcx
 mov r8d,DWORD PTR [r12+rax*4]
 mov rcx,rdx
 shr r8,cl
 and r8d,1
 xor r9d,r9d
 mov r10,[rbp-176]
divide_shift:
 cmp r9,r10
 jae divide_shift_finish
 mov eax,DWORD PTR [rbx+r9*4]
 shl rax,1
 add rax,r8
 mov r8,rax
 shr r8,30
 and eax,1073741823
 mov DWORD PTR [rbx+r9*4],eax
 inc r9
 jmp divide_shift
divide_shift_finish:
 test r8,r8
 jz divide_compare
 mov DWORD PTR [rbx+r10*4],r8d
 inc r10
 mov [rbp-176],r10
divide_compare:
 mov rdi,rbx
 mov rsi,r13
 mov rcx,[rbp-176]
 mov rdx,[rbp-88]
 call compare
 test rax,rax
 js divide_next
 xor r8d,r8d
 xor r9d,r9d
 mov r10,[rbp-176]
divide_subtract:
 cmp r8,r10
 jae divide_trim
 mov eax,DWORD PTR [rbx+r8*4]
 sub rax,r9
 xor r9d,r9d
 cmp r8,[rbp-88]
 jae divide_borrow
 mov edx,DWORD PTR [r13+r8*4]
 sub rax,rdx
divide_borrow:
 test rax,rax
 jns divide_store
 add rax,1073741824
 mov r9d,1
divide_store:
 mov DWORD PTR [rbx+r8*4],eax
 inc r8
 jmp divide_subtract
divide_trim:
 test r10,r10
 jz divide_quotient
 cmp DWORD PTR [rbx+r10*4-4],0
 jne divide_quotient
 dec r10
 jmp divide_trim
divide_quotient:
 mov [rbp-176],r10
 mov rax,[rbp-168]
 xor edx,edx
 mov ecx,30
 div rcx
 mov rcx,rdx
 mov edx,1
 shl rdx,cl
 or DWORD PTR [r14+rax*4],edx
divide_next:
 dec QWORD PTR [rbp-168]
 jmp divide_bit
divide_finish:
 cmp QWORD PTR [rbp-48],4
 je divide_remainder
 mov rax,[rbp-56]
 imul rax,[rbp-80]
 mov [rbp-152],rax
 mov rax,[rbp-64]
 mov [rbp-144],rax
 jmp common_finish
divide_remainder:
 mov r14,rbx
 mov rax,[rbp-176]
 mov [rbp-144],rax
common_finish:
 mov rsi,r14
 mov rcx,[rbp-144]
 mov rdx,[rbp-152]
 call mgn_construct
 mov [rbp-224],rax
 mov rdi,[rbp-104]
 mov rsi,[rbp-112]
 mov eax,11
 syscall
 mov rax,[rbp-224]
 jmp common_return
common_resource_failure:
 mov rdi,[rbp-104]
 mov rsi,[rbp-112]
 mov eax,11
 syscall
 jmp mgn_allocation_failure
common_compare:
 mov rax,[rbp-56]
 cmp rax,[rbp-80]
 jne compare_sign
 mov rdi,[rbp-72]
 mov rsi,[rbp-96]
 mov rcx,[rbp-64]
 mov rdx,[rbp-88]
 call compare
 imul rax,[rbp-56]
 jmp common_return
compare_sign:
 mov rax,[rbp-56]
common_return:
 add rsp,232
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbx
 pop rbp
 ret
# Normalize a private limb view, then allocate/copy only for a large result.
mgn_construct:
 push rbp
 mov rbp,rsp
 push rbx
 push r12
 push r13
 push r14
 push r15
 sub rsp,8
 mov r12,rsi
 mov r13,rcx
 mov r14,rdx
construct_trim:
 test r13,r13
 jz construct_zero
 cmp DWORD PTR [r12+r13*4-4],0
 jne construct_nonzero
 dec r13
 jmp construct_trim
construct_zero:
 mov eax,1
 jmp construct_return
construct_nonzero:
 cmp r13,3
 ja construct_large
 xor eax,eax
 mov rcx,r13
construct_word:
 dec rcx
 shl rax,30
 mov edx,DWORD PTR [r12+rcx*4]
 or rax,rdx
 test rcx,rcx
 jne construct_word
 # count3 can hold up to90 bits; never silently discard high bits.
 cmp r13,3
 jne construct_small_test
 cmp DWORD PTR [r12+8],4
 ja construct_large
construct_small_test:
 mov rdx,4611686018427387904
 cmp r14,0
 jl construct_negative
 cmp rax,rdx
 jae construct_large
 jmp construct_tag
construct_negative:
 cmp rax,rdx
 ja construct_large
 neg rax
construct_tag:
 shl rax,1
 or rax,1
 jmp construct_return
construct_large:
 mov rdi,r13
 shl rdi,2
 shr rdi,2
 cmp rdi,r13
 jne mgn_allocation_failure
 shl rdi,2
 add rdi,40
 jo mgn_allocation_failure
 test rdi,rdi
 js mgn_allocation_failure
 xor esi,esi
 call mgn_allocate
 mov [rax+24],r14
 mov [rax+32],r13
 lea rdi,[rax+40]
 mov rsi,r12
 mov rcx,r13
 rep movsd
construct_return:
 add rsp,8
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbx
 pop rbp
 ret
mgn_signed:
 mov edx,1
 test rax,rax
 jns raw_magnitude
 neg rax
 mov rdx,-1
 jmp raw_magnitude
mgn_unsigned:
 mov edx,1
raw_magnitude:
 sub rsp,24
 mov r8,rax
 and eax,1073741823
 mov DWORD PTR [rsp],eax
 shr r8,30
 mov rax,r8
 and eax,1073741823
 mov DWORD PTR [rsp+4],eax
 shr r8,30
 mov DWORD PTR [rsp+8],r8d
 mov rsi,rsp
 mov ecx,3
 call mgn_construct
 add rsp,24
 ret
# Decode to a raw word and report signed64 and unsigned64 validity separately.
mgn_word:
 test al,1
 jz word_big
 sar rax,1
 mov edx,1
 xor ecx,ecx
 test rax,rax
 setns cl
 ret
word_big:
 mov r8,[rax+24]
 mov r9,[rax+32]
 cmp r9,3
 ja word_invalid
 lea r10,[rax+40]
 cmp r9,3
 jne word_read
 cmp DWORD PTR [r10+8],15
 ja word_invalid
word_read:
 xor eax,eax
 mov rcx,r9
word_loop:
 test rcx,rcx
 jz word_sign
 dec rcx
 shl rax,30
 mov edx,DWORD PTR [r10+rcx*4]
 or rax,rdx
 jmp word_loop
word_sign:
 xor edx,edx
 xor ecx,ecx
 test r8,r8
 js word_negative
 mov ecx,1
 test rax,rax
 setns dl
 ret
word_negative:
 mov r9,-9223372036854775808
 cmp rax,r9
 seta dl
 xor edx,1
 neg rax
 ret
word_invalid:
 xor eax,eax
 xor edx,edx
 xor ecx,ecx
 ret
