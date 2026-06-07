// cat: печатает данные, поданные через ввод (поток, конец = NUL)
var done = 0

interrupt function on_key ( ) {
    var c = port_in ( 0 )
    if ( c == 0 ) { done = 1 }
    else { print ( c ) }
}

set_interrupt_handler ( 0 , on_key )
enable_interrupts ( )
while ( done == 0 ) { }
