// Двойная точность: 64-битные числа на 32-битной машине.
// 64-битное число = 4 лимба по 16 бит, база B = 65536, лимбы l0..l3 (l0 — младший).
// B не влезает в 16-битный immediate, поэтому собираем как 256 * 256.
var B = 256
B = B * 256

// A = 0x0001_0000_FFFF_FFFF  (лимбы lo..hi: FFFF FFFF 0000 0001)
var a0 = B - 1
var a1 = B - 1
var a2 = 0
var a3 = 1
// C = 0x0000_0000_0000_0002
var c0 = 2
var c1 = 0
var c2 = 0
var c3 = 0

// --- сложение 64-бит по лимбам с переносом ---
var carry = 0
var s0 = a0 + c0 + carry
carry = s0 / B
s0 = s0 % B
var s1 = a1 + c1 + carry
carry = s1 / B
s1 = s1 % B
var s2 = a2 + c2 + carry
carry = s2 / B
s2 = s2 % B
var s3 = a3 + c3 + carry
s3 = s3 % B

print_str ( "A+C limbs hi..lo: " )
print_num ( s3 )
print ( 32 )
print_num ( s2 )
print ( 32 )
print_num ( s1 )
print ( 32 )
print_num ( s0 )
print ( 10 )

// --- умножение 64-бит на маленькую константу k = 3 ---
var k = 3
carry = 0
var m0 = a0 * k + carry
carry = m0 / B
m0 = m0 % B
var m1 = a1 * k + carry
carry = m1 / B
m1 = m1 % B
var m2 = a2 * k + carry
carry = m2 / B
m2 = m2 % B
var m3 = a3 * k + carry
m3 = m3 % B

print_str ( "A*3 limbs hi..lo: " )
print_num ( m3 )
print ( 32 )
print_num ( m2 )
print ( 32 )
print_num ( m1 )
print ( 32 )
print_num ( m0 )
