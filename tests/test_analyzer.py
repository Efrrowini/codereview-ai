"""Tests for the static analysis layer — no API key needed."""
import sys
sys.path.insert(0, "/home/claude/codereview-ai")

from core.analyzer import analyze_python


def test_syntax_error():
    code = "def foo(\n    x = \n"
    result = analyze_python(code)
    assert not result.syntax_ok
    assert result.syntax_error is not None


def test_valid_code_metrics():
    code = '''
def add(a: int, b: int) -> int:
    """Return the sum of a and b."""
    return a + b

result = add(1, 2)
print(result)
'''
    result = analyze_python(code)
    assert result.syntax_ok
    assert result.line_count > 0
    assert result.function_count == 1
    assert result.has_docstrings is True
    assert result.has_type_hints is True


def test_no_docstring_no_hints():
    code = '''
def multiply(x, y):
    return x * y
'''
    result = analyze_python(code)
    assert result.syntax_ok
    assert result.has_docstrings is False
    assert result.has_type_hints is False


def test_summary_text_syntax_error():
    code = "def f(:"
    result = analyze_python(code)
    summary = result.summary_text()
    assert "SYNTAX ERROR" in summary


def test_summary_text_valid():
    code = "x = 1 + 1"
    result = analyze_python(code)
    summary = result.summary_text()
    assert "Syntax: OK" in summary


if __name__ == "__main__":
    test_syntax_error()
    test_valid_code_metrics()
    test_no_docstring_no_hints()
    test_summary_text_syntax_error()
    test_summary_text_valid()
    print("All analyzer tests passed.")
