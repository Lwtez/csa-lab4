"""Проверка AST (требование варианта: "проверка AST в тестах").

AST должно быть человекочитаемым, поэтому проверяем двумя способами:
структуру (dict) и текстовый рендер format_ast.
"""
from translator import tokenize, parse, format_ast


def test_ast_expression_precedence():
    # 2 + 3 * 4  ->  умножение глубже сложения
    tree = parse(tokenize("var x = 2 + 3 * 4"))
    assert tree == {
        "type": "Program",
        "functions": [],
        "body": [
            {
                "type": "VarDecl",
                "name": "x",
                "value": {
                    "type": "BinOp",
                    "op": "+",
                    "left": {"type": "Num", "value": 2},
                    "right": {
                        "type": "BinOp",
                        "op": "*",
                        "left": {"type": "Num", "value": 3},
                        "right": {"type": "Num", "value": 4},
                    },
                },
            }
        ],
    }


def test_ast_while_and_if():
    src = "while ( a > 0 ) { if ( a == 1 ) { a = 0 } }"
    tree = parse(tokenize(src))
    (loop,) = tree["body"]
    assert loop["type"] == "While"
    assert loop["cond"] == {
        "type": "BinOp", "op": ">",
        "left": {"type": "Var", "name": "a"},
        "right": {"type": "Num", "value": 0},
    }
    (branch,) = loop["body"]
    assert branch["type"] == "If"
    assert branch["else"] == []


def test_ast_interrupt_function():
    src = "interrupt function on_key ( ) { x = port_in ( 0 ) }"
    tree = parse(tokenize(src))
    (fn,) = tree["functions"]
    assert fn["type"] == "FuncDecl"
    assert fn["name"] == "on_key"
    assert fn["is_interrupt"] is True
    assert fn["params"] == []


def test_format_ast_human_readable():
    # format_ast должен давать читаемое дерево с правильной вложенностью
    tree = parse(tokenize("var x = 2 + 3 * 4"))
    rendered = format_ast(tree)
    assert rendered == (
        "Program\n"
        "  body:\n"
        "    VarDecl x =\n"
        "      BinOp +\n"
        "        Num 2\n"
        "        BinOp *\n"
        "          Num 3\n"
        "          Num 4"
    )