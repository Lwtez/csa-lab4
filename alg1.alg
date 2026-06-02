var hi = read ( )
var lo = 100
var best = 0

var a = hi
while ( a >= lo ) {
    var b = hi
    var go = 1
    while ( go == 1 ) {
        if ( b < a ) {
            go = 0
        } else {
            var prod = a * b
            if ( prod <= best ) {
                go = 0
            } else {
                var x = prod
                var rev = 0
                while ( x != 0 ) {
                    rev = rev * 10 + x % 10
                    x = x / 10
                }
                if ( rev == prod ) {
                    best = prod
                }
                b = b - 1
            }
        }
    }
    a = a - 1
}

print_num ( best )