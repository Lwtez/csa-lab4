var hi = 0
var done = 0
interrupt function on_key ( ) {
    var c = port_in ( 0 )
    if ( c == 10 ) { done = 1 }
    else { hi = hi * 10 + ( c - 48 ) }
}
set_interrupt_handler ( 0 , on_key )
enable_interrupts ( )
while ( done == 0 ) { }
disable_interrupts ( )
var lo = 90
var best = 0
var a = hi
while ( a >= lo ) {
    var b = a
    while ( b >= lo ) {
        var prod = a * b
        if ( prod > best ) {
            var x = prod
            var rev = 0
            while ( x != 0 ) {
                rev = rev * 10 + x % 10
                x = x / 10
            }
            if ( rev == prod ) { best = prod }
        }
        b = b - 1
    }
    a = a - 1
}
print_num ( best )
