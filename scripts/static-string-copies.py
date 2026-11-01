"""Interpret only straight-line literal-copy instructions, never execute native code.

Unknown bytes remain unknown. Branches and unrecognised calls/instructions fail.
The sole admitted call models allocation of unknown storage, not vendor code.
"""
import capstone


class LiteralCopies:
    def __init__(self, read_image, allocator):
        self.read_image = read_image
        self.allocator = allocator
        self.registers = {}
        self.memory = {}
        self.allocations = []
        self.next_heap = 0x30000000
        self.write_register('rbp', list((0x10000000).to_bytes(8, 'little')))
        self.write_register('rsp', list((0x20000000).to_bytes(8, 'little')))

    @staticmethod
    def register(name):
        names = [('rax', 'eax', 'ax', 'al'), ('rbx', 'ebx', 'bx', 'bl'),
                 ('rcx', 'ecx', 'cx', 'cl'), ('rdx', 'edx', 'dx', 'dl'),
                 ('rsi', 'esi', 'si', 'sil'), ('rdi', 'edi', 'di', 'dil'),
                 ('rbp', 'ebp', 'bp', 'bpl'), ('rsp', 'esp', 'sp', 'spl')]
        names += [(f'r{i}', f'r{i}d', f'r{i}w', f'r{i}b') for i in range(8, 16)]
        for row in names:
            if name in row:
                return row[0], (8, 4, 2, 1)[row.index(name)]
        if name.startswith('xmm') and name[3:].isdigit():
            return name, 16
        raise ValueError('Unsupported register: ' + name)

    def read_register(self, name):
        key, size = self.register(name)
        return self.registers.get(key, [None] * (16 if key.startswith('xmm') else 8))[:size]

    def write_register(self, name, data):
        key, size = self.register(name)
        width = 16 if key.startswith('xmm') else 8
        previous = self.registers.get(key, [None] * width)
        value = (list(data) + [None] * size)[:size]
        self.registers[key] = value + ([0] * 4 if size == 4 else previous[size:])

    @staticmethod
    def integer(data):
        if not data or any(x is None for x in data):
            raise ValueError('Unknown value cannot become an address or length')
        return int.from_bytes(bytes(data), 'little')

    def address(self, instruction, operand):
        memory = operand.mem
        if memory.index:
            raise ValueError('Indexed addressing is outside literal-copy scope')
        if memory.base == capstone.x86.X86_REG_RIP:
            return instruction.address + instruction.size + memory.disp
        if not memory.base:
            raise ValueError('Absolute addressing is outside literal-copy scope')
        return self.integer(self.read_register(instruction.reg_name(memory.base))) + memory.disp

    def read_memory(self, address, size):
        if 0x10000000 - 0x10000 <= address < 0x40000000:
            return [self.memory.get(address + n) for n in range(size)]
        value = self.read_image(address, size)
        if len(value) != size:
            raise ValueError('Incomplete image literal')
        return list(value)

    def operand(self, instruction, operand):
        if operand.type == capstone.x86.X86_OP_REG:
            return self.read_register(instruction.reg_name(operand.reg))
        if operand.type == capstone.x86.X86_OP_MEM:
            return self.read_memory(self.address(instruction, operand), operand.size)
        if operand.type == capstone.x86.X86_OP_IMM:
            return list((operand.imm & ((1 << (operand.size * 8)) - 1)).to_bytes(operand.size, 'little'))
        raise ValueError('Unsupported operand')

    def write(self, instruction, operand, data):
        value = (list(data) + [None] * operand.size)[:operand.size]
        if operand.type == capstone.x86.X86_OP_REG:
            self.write_register(instruction.reg_name(operand.reg), value)
        elif operand.type == capstone.x86.X86_OP_MEM:
            address = self.address(instruction, operand)
            stack = any(base - 0x10000 <= address and address + len(value) <= base + 0x10000
                        for base in (0x10000000, 0x20000000))
            heap = any(base <= address and address + len(value) <= base + size for base, size in self.allocations)
            if not stack and not heap:
                raise ValueError('Cannot modify image or unallocated model memory')
            for n, byte in enumerate(value):
                self.memory[address + n] = byte
        else:
            raise ValueError('Unsupported destination')

    def run(self, instructions):
        for instruction in instructions:
            op = instruction.operands
            mnemonic = instruction.mnemonic
            if mnemonic in ('mov', 'movabs', 'movups', 'movaps', 'movdqu', 'movdqa', 'movsd', 'movzx'):
                value = self.operand(instruction, op[1])
                if mnemonic in ('movzx', 'movsd') and op[0].type == capstone.x86.X86_OP_REG:
                    value += [0] * (op[0].size - len(value))
                self.write(instruction, op[0], value)
            elif mnemonic == 'lea':
                self.write(instruction, op[0], list(self.address(instruction, op[1]).to_bytes(8, 'little')))
            elif mnemonic in ('xor', 'xorps') and all(x.type == capstone.x86.X86_OP_REG for x in op) and op[0].reg == op[1].reg:
                self.write(instruction, op[0], [0] * op[0].size)
            elif mnemonic == 'call' and op[0].type == capstone.x86.X86_OP_IMM and op[0].imm == self.allocator:
                size = self.integer(self.read_register('ecx'))
                if not 0 < size <= 4096:
                    raise ValueError('Allocation outside literal-copy bound')
                address = self.next_heap
                self.next_heap += 0x1000
                self.allocations.append((address, size))
                for n in range(size):
                    self.memory[address + n] = None
                for register in ('rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                    self.write_register(register, [None] * 8)
                for n in range(6):
                    self.write_register(f'xmm{n}', [None] * 16)
                self.write_register('rax', list(address.to_bytes(8, 'little')))
            else:
                raise ValueError(f'Outside literal-copy scope at {instruction.address:x}: {mnemonic} {instruction.op_str}')

    def string_argument(self, register):
        address = self.integer(self.read_register(register))
        length = self.integer(self.read_memory(address + 16, 8))
        capacity = self.integer(self.read_memory(address + 24, 8))
        if not 0 < length <= min(capacity, 256) or capacity > 4096:
            raise ValueError('String length/capacity outside bound')
        data_address = address if capacity <= 15 else self.integer(self.read_memory(address, 8))
        data = self.read_memory(data_address, length + 1)
        if any(x is None for x in data) or data[-1] != 0 or 0 in data[:-1]:
            raise ValueError('String bytes or terminator are not proved')
        return bytes(data[:-1]).decode('utf-8')
