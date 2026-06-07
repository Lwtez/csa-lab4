// Спрашивает имя (ввод до '\n') и печатает приветствие.
// Символы имени эхо-печатаются по мере чтения, поэтому хранить строку не нужно.
var done = 0

interrupt function on_key ( ) {
    var c = port_in ( 0 )
    if ( c == 10 ) { done = 1 }
    else { print ( c ) }
}

print_str ( "What is your name?" )
print ( 10 )
print_str ( "Hello, " )
set_interrupt_handler ( 0 , on_key )
enable_interrupts ( )
while ( done == 0 ) { }
disable_interrupts ( )
print ( 33 )
