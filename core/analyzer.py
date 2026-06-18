"""
Static analysis layer — runs BEFORE the LLM.
Catches syntax errors, style issues, complexity metrics
and packages them as structured context for the prompt builder.
"""
import ast
import json
import subprocess
import tempfile
import os
from dataclasses import dataclass, field


@dataclass
class StaticIssue:
    line: int
    col: int
    code: str          # e.g. "E501", "W0611"
    message: str
    severity: str      # "error" | "warning" | "info"


@dataclass
class AnalysisResult:
    syntax_ok: bool
    syntax_error: str | None
    issues: list[StaticIssue] = field(default_factory=list)
    complexity_score: int | None = None   # McCabe complexity
    line_count: int = 0
    function_count: int = 0
    has_docstrings: bool = False
    has_type_hints: bool = False

    def to_dict(self) -> dict:
        return {
            "syntax_ok": self.syntax_ok,
            "syntax_error": self.syntax_error,
            "issues": [
                {
                    "line": i.line,
                    "col": i.col,
                    "code": i.code,
                    "message": i.message,
                    "severity": i.severity,
                }
                for i in self.issues
            ],
            "complexity_score": self.complexity_score,
            "line_count": self.line_count,
            "function_count": self.function_count,
            "has_docstrings": self.has_docstrings,
            "has_type_hints": self.has_type_hints,
        }

    def summary_text(self) -> str:
        """Human-readable summary injected into the LLM prompt."""
        lines = []
        if not self.syntax_ok:
            lines.append(f"SYNTAX ERROR: {self.syntax_error}")
        else:
            lines.append("Syntax: OK")

        errors = [i for i in self.issues if i.severity == "error"]
        warnings = [i for i in self.issues if i.severity == "warning"]
        lines.append(f"Static issues: {len(errors)} errors, {len(warnings)} warnings")

        if self.issues:
            for issue in self.issues[:10]:   # cap at 10 to keep prompt tight
                lines.append(f"  Line {issue.line}: [{issue.code}] {issue.message}")

        lines.append(f"Lines of code: {self.line_count}")
        lines.append(f"Functions defined: {self.function_count}")
        lines.append(f"Has docstrings: {self.has_docstrings}")
        lines.append(f"Has type hints: {self.has_type_hints}")
        if self.complexity_score is not None:
            lines.append(f"Cyclomatic complexity (max): {self.complexity_score}")

        return "\n".join(lines)


def analyze_python(code: str) -> AnalysisResult:
    """Run AST parse + pylint on Python code, return structured result."""

    # Step 1: AST syntax check
    try:
        tree = ast.parse(code)
        syntax_ok = True
        syntax_error = None
    except SyntaxError as e:
        return AnalysisResult(
            syntax_ok=False,
            syntax_error=f"Line {e.lineno}: {e.msg}",
        )

    # Step 2: AST-level metrics
    line_count = len(code.splitlines())
    function_count = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    has_docstrings = any(
        isinstance(ast.get_docstring(node), str)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module))
    )
    has_type_hints = any(
        node.returns is not None or any(a.annotation for a in node.args.args)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    )

    # Step 3: pylint (write code to temp file, run subprocess)
    issues: list[StaticIssue] = []
    complexity_score = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [
                "python", "-m", "pylint",
                tmp_path,
                "--output-format=json",
                "--disable=C0114,C0115,C0116",  # suppress missing-docstring (we check separately)
                "--max-line-length=100",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.stdout.strip():
            raw = json.loads(result.stdout)
            for item in raw:
                severity = "error" if item["type"] in ("error", "fatal") else "warning"
                issues.append(
                    StaticIssue(
                        line=item["line"],
                        col=item["column"],
                        code=item["message-id"],
                        message=item["message"],
                        severity=severity,
                    )
                )

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass   # gracefully skip if pylint unavailable
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return AnalysisResult(
        syntax_ok=syntax_ok,
        syntax_error=syntax_error,
        issues=issues,
        complexity_score=complexity_score,
        line_count=line_count,
        function_count=function_count,
        has_docstrings=has_docstrings,
        has_type_hints=has_type_hints,
    )


def analyze(code: str, language: str = "python") -> AnalysisResult:
    """Entry point — dispatches to the right analyzer by language."""
    if language.lower() == "python":
        return analyze_python(code)
    # Future: add Java, JS, C++ analyzers here
    # For now, return a minimal result for unsupported languages
    return AnalysisResult(
        syntax_ok=True,
        syntax_error=None,
        line_count=len(code.splitlines()),
    )
