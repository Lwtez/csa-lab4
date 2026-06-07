// sort: пользователь загружает список через ввод.
// Формат (по аналогии с pstr — длина впереди): сначала количество,
// затем элементы через пробелы, конец = '\n'. Ввод идёт через прерывания.
var data[16]
var n = 0          // сколько элементов уже прочитано
var count = 0      // объявленная длина списка
var have_count = 0 // прочитали ли уже длину
var cur = 0        // текущее собираемое число
var done = 0

interrupt function on_key ( ) {
    var c = port_in ( 0 )
    if ( c == 32 ) {
        if ( have_count == 0 ) {
            count = cur
            have_count = 1
        } else {
            data[n] = cur
            n = n + 1
        }
        cur = 0
    } else {
        if ( c == 10 ) {
            data[n] = cur
            n = n + 1
            done = 1
        } else {
            cur = cur * 10 + ( c - 48 )
        }
    }
}

set_interrupt_handler ( 0 , on_key )
enable_interrupts ( )
while ( done == 0 ) { }
disable_interrupts ( )

// пузырьковая сортировка data[0..count-1]
var i = 0
while ( i < count ) {
    var j = 0
    while ( j < count - 1 ) {
        if ( data[j] > data[j + 1] ) {
            var t = data[j]
            data[j] = data[j + 1]
            data[j + 1] = t
        }
        j = j + 1
    }
    i = i + 1
}

// печать отсортированного списка через пробел
var k = 0
while ( k < count ) {
    print_num ( data[k] )
    if ( k < count - 1 ) { print ( 32 ) }
    k = k + 1
}
