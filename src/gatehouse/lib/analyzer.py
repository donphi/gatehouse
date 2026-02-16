"""SourceAnalyzer — single-parse, single-metadata-resolve analysis of Python source.

Every Gatehouse rule queries this object.  No rule touches raw source text.
The CST and metadata providers give deterministic, grammar-defined checks.
Each file is parsed exactly once into a concrete syntax tree, and a shared
MetadataWrapper resolves all provider data in a single pass.

Design notes:
    The single-parse strategy means each Python file is parsed into a CST
    exactly once.  A shared MetadataWrapper resolves ParentNodeProvider and
    PositionProvider for all visitors, avoiding redundant tree traversals.
    Every check function receives the pre-built SourceAnalyzer rather than
    raw source, ensuring consistent, grammar-level analysis across all rules.
"""

import os
from typing import Optional

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider


# ---------------------------------------------------------------------------
# CST visitor for collecting literals inside function bodies
# ---------------------------------------------------------------------------


class _LiteralCollector(cst.CSTVisitor):
    """Walk the CST and collect literal nodes inside function/method bodies.

    Attributes:
        safe_values: Set of values exempt from hardcoded-literal checks.
        safe_contexts: List of context names where literals are allowed.
        violations: Accumulated violation dicts found during traversal.
        _func_depth: Nesting depth counter to track whether traversal is
            inside a function body.
    """

    METADATA_DEPENDENCIES = (ParentNodeProvider, PositionProvider)

    def __init__(self, safe_values: set, safe_contexts: list) -> None:
        self.safe_values = safe_values
        self.safe_contexts = safe_contexts
        self.violations: list[dict] = []
        self._func_depth = 0

    # Track function nesting depth
    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        """Enter a function body."""
        self._func_depth += 1
        return True

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        """Leave a function body."""
        self._func_depth -= 1

    def _is_safe_value(self, value: object) -> bool:
        """Type-aware safe value check. Prevents True==1 / False==0 collision."""
        for sv in self.safe_values:
            # Use type() identity instead of isinstance() because bool is a
            # subclass of int in Python; isinstance(True, int) is True, so
            # True == 1 and False == 0 would incorrectly pass an int check.
            if type(sv) is type(value) and sv == value:
                return True
        return False

    def _is_docstring(self, node: cst.CSTNode) -> bool:
        """Check if a string node is a docstring (first Expr statement in a body)."""
        # Traverse a 4-level parent chain: String → Expr → SimpleStatementLine
        # → IndentedBlock.  A docstring is a bare string expression that is the
        # first statement inside an indented block (function, class, or module).
        parent = self.get_metadata(ParentNodeProvider, node, None)
        if not isinstance(parent, cst.Expr):
            return False
        grandparent = self.get_metadata(ParentNodeProvider, parent, None)
        if not isinstance(grandparent, cst.SimpleStatementLine):
            return False
        greatgrand = self.get_metadata(ParentNodeProvider, grandparent, None)
        if isinstance(greatgrand, cst.IndentedBlock) and greatgrand.body and greatgrand.body[0] is grandparent:
            return True
        return False

    def _check_literal(self, node: cst.CSTNode, value: object, value_type: str) -> None:
        """Check a single literal node against rules."""
        if self._func_depth == 0:
            return

        if self._is_safe_value(value):
            return

        parent = self.get_metadata(ParentNodeProvider, node, None)

        if ("dict_key" in self.safe_contexts or "dict_value" in self.safe_contexts) and isinstance(parent, cst.DictElement):
            return

        if "call_argument" in self.safe_contexts and value_type == "string":
            if isinstance(parent, cst.Arg):
                return

        pos = self.get_metadata(PositionProvider, node, None)
        line = pos.start.line if pos else 0

        self.violations.append({
            "line": line,
            "value": str(value),
            "value_type": value_type,
        })

    def _parent_is_negation(self, node: cst.CSTNode) -> bool:
        """Check if the node's parent is a UnaryOperation with Minus operator."""
        parent = self.get_metadata(ParentNodeProvider, node, None)
        return isinstance(parent, cst.UnaryOperation) and isinstance(parent.operator, cst.Minus)

    def visit_Integer(self, node: cst.Integer) -> None:
        """Check integer literals. Skip if parent is negation (handled by visit_UnaryOperation)."""
        if self._parent_is_negation(node):
            return
        try:
            value = int(node.value)
        except (ValueError, TypeError):
            value = node.value
        self._check_literal(node, value, "numeric")

    def visit_Float(self, node: cst.Float) -> None:
        """Check float literals. Skip if parent is negation (handled by visit_UnaryOperation)."""
        if self._parent_is_negation(node):
            return
        try:
            value = float(node.value)
        except (ValueError, TypeError):
            value = node.value
        self._check_literal(node, value, "numeric")

    def visit_SimpleString(self, node: cst.SimpleString) -> None:
        """Check simple string literals (not f-strings)."""
        raw = node.evaluated_value
        if raw is None:
            return
        if self._is_docstring(node):
            return
        self._check_literal(node, raw, "string")

    def visit_ConcatenatedString(self, node: cst.ConcatenatedString) -> None:
        """Skip concatenated strings — they may contain f-string parts."""
        return False

    def visit_FormattedString(self, node: cst.FormattedString) -> None:
        """Skip f-strings entirely — they are display text, not config values."""
        return False

    def visit_Name(self, node: cst.Name) -> None:
        """Check True/False as hardcoded boolean values. None is exempt."""
        if node.value == "None":
            return
        if node.value not in ("True", "False"):
            return
        python_val = node.value == "True"
        self._check_literal(node, python_val, "boolean")

    def visit_UnaryOperation(self, node: cst.UnaryOperation) -> None:
        """Handle negative numbers: -1 is UnaryOperation(Minus, Integer)."""
        # In the CST, negative literals like -1 are not Integer(-1) but
        # UnaryOperation(operator=Minus, expression=Integer("1")).  This
        # visitor reconstructs the negative value for safe-value matching.
        if not isinstance(node.operator, cst.Minus):
            return
        if self._func_depth == 0:
            return

        expr = node.expression
        if isinstance(expr, cst.Integer):
            try:
                neg_val = -int(expr.value)
            except (ValueError, TypeError):
                return
            if self._is_safe_value(neg_val):
                return
        elif isinstance(expr, cst.Float):
            try:
                neg_val = -float(expr.value)
            except (ValueError, TypeError):
                return
            if self._is_safe_value(neg_val):
                return
        else:
            return

        parent = self.get_metadata(ParentNodeProvider, node, None)
        if ("dict_key" in self.safe_contexts or "dict_value" in self.safe_contexts) and isinstance(parent, cst.DictElement):
            return

        pos = self.get_metadata(PositionProvider, node, None)
        line = pos.start.line if pos else 0
        self.violations.append({
            "line": line,
            "value": str(neg_val),
            "value_type": "numeric",
        })


# ---------------------------------------------------------------------------
# CST visitor for docstring-less functions
# ---------------------------------------------------------------------------

class _FunctionDocstringCollector(cst.CSTVisitor):
    """Collect functions that are missing docstrings.

    Attributes:
        violations: Accumulated violation dicts for functions without docstrings.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.violations: list[dict] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        """Check if function has a docstring as first statement."""
        if not _has_docstring(node):
            params = _format_params(node.params)
            pos = self.get_metadata(PositionProvider, node, None)
            line = pos.start.line if pos else 0
            self.violations.append({
                "line": line,
                "source": "",
                "function_name": node.name.value,
                "params": params,
            })
        return True


# ---------------------------------------------------------------------------
# CST visitor for decorated function checks
# ---------------------------------------------------------------------------

class _DecoratedFunctionCollector(cst.CSTVisitor):
    """Check decorated functions for docstrings or try/except.

    Attributes:
        decorator_patterns: Substrings to match against decorator names.
        check_type: The kind of check to perform (``"docstring"`` or ``"try_except"``).
        violations: Accumulated violation dicts for failing functions.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, decorator_patterns: list, check_type: str) -> None:
        self.decorator_patterns = decorator_patterns
        self.check_type = check_type
        self.violations: list[dict] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        """Check decorated functions."""
        for dec in node.decorators:
            dec_name = _get_cst_decorator_name(dec.decorator)
            if not any(p in dec_name for p in self.decorator_patterns):
                continue

            pos = self.get_metadata(PositionProvider, node, None)
            line = pos.start.line if pos else 0

            if self.check_type == "docstring" and not _has_docstring(node):
                self.violations.append({"line": line, "function_name": node.name.value})
            elif self.check_type == "try_except" and not _has_try_except(node):
                self.violations.append({"line": line, "function_name": node.name.value})
        return True


# ---------------------------------------------------------------------------
# CST visitor for for-loop progress checks
# ---------------------------------------------------------------------------

class _ForLoopProgressCollector(cst.CSTVisitor):
    """Check for loops that don't use progress tracking.

    Attributes:
        violations: Accumulated violation dicts for loops missing progress wrappers.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.violations: list[dict] = []

    def visit_For(self, node: cst.For) -> bool:
        """Check if the iterable is wrapped in track() or tqdm()."""
        iter_code = self._module_for_codegen.code_for_node(node.iter)
        if "track" not in iter_code and "tqdm" not in iter_code:
            pos = self.get_metadata(PositionProvider, node, None)
            line = pos.start.line if pos else 0
            self.violations.append({
                "line": line,
                "source": "",
            })
        return True


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _has_docstring(func_node: cst.FunctionDef) -> bool:
    """Check if a FunctionDef has a docstring as its first statement."""
    body = func_node.body
    if isinstance(body, cst.IndentedBlock) and body.body:
        first_stmt = body.body[0]
        if isinstance(first_stmt, cst.SimpleStatementLine) and first_stmt.body:
            expr = first_stmt.body[0]
            if isinstance(expr, cst.Expr) and isinstance(expr.value, (cst.SimpleString, cst.ConcatenatedString, cst.FormattedString)):
                raw = expr.value
                if isinstance(raw, cst.SimpleString):
                    val = raw.evaluated_value
                    return isinstance(val, str)
                return True
    return False


def _format_params(params: cst.Parameters) -> str:
    """Format function parameters as a string."""
    parts = []
    for p in params.params:
        parts.append(p.name.value)
    return ", ".join(parts)


def _get_cst_decorator_name(dec: cst.BaseExpression) -> str:
    """Extract decorator name as a dotted string from a CST decorator node."""
    if isinstance(dec, cst.Name):
        return dec.value
    elif isinstance(dec, cst.Attribute):
        parts = []
        node = dec
        while isinstance(node, cst.Attribute):
            parts.append(node.attr.value)
            node = node.value
        if isinstance(node, cst.Name):
            parts.append(node.value)
        return ".".join(reversed(parts))
    elif isinstance(dec, cst.Call):
        return _get_cst_decorator_name(dec.func)
    return ""


def _has_try_except(func_node: cst.FunctionDef) -> bool:
    """Check if a function body contains a Try statement."""
    body = func_node.body
    if not isinstance(body, cst.IndentedBlock):
        return False
    for stmt in body.body:
        if isinstance(stmt, cst.Try):
            return True
    return False


# ---------------------------------------------------------------------------
# SourceAnalyzer — the single entry point for all rule checks
# ---------------------------------------------------------------------------

class SourceAnalyzer:
    """Single parse and metadata resolution for a Python source file.

    All rules query this object.  Rules never parse, tokenize, or scan raw
    source directly.  Created once per file in ``scan_file()``.

    Attributes:
        source: Raw source text of the file.
        filepath: Absolute or relative path to the source file.
        source_lines: Source text split into individual lines.
        module: Parsed libcst Module node.
        wrapper: MetadataWrapper providing resolved metadata for all visitors.
    """

    def __init__(self, source: str, filepath: str) -> None:
        """Parse source and resolve metadata providers."""
        self.source = source
        self.filepath = filepath
        self.source_lines = source.splitlines()
        self.module = cst.parse_module(source)
        self.wrapper = MetadataWrapper(self.module)

    # ------------------------------------------------------------------
    # File-level queries
    # ------------------------------------------------------------------

    def line_count(self) -> int:
        """Return the number of lines in the source."""
        return len(self.source_lines)

    def header_comments(self) -> list[str]:
        """Return comment text from the Module.header (top-of-file comments)."""
        comments = []
        for line in self.module.header:
            if isinstance(line, cst.EmptyLine) and line.comment:
                comments.append(line.comment.value)
        # Also check leading_lines of the first body statement
        if self.module.body:
            first = self.module.body[0]
            if hasattr(first, "leading_lines"):
                for ll in first.leading_lines:
                    if isinstance(ll, cst.EmptyLine) and ll.comment:
                        comments.append(ll.comment.value)
        return comments

    def has_module_docstring(self) -> bool:
        """Check if the module has a docstring (first statement is a string expression)."""
        return self.get_module_docstring() is not None

    def get_module_docstring(self) -> Optional[str]:
        """Return the module docstring text, or None."""
        if not self.module.body:
            return None
        first = self.module.body[0]
        if isinstance(first, cst.SimpleStatementLine) and first.body:
            expr = first.body[0]
            if isinstance(expr, cst.Expr) and isinstance(expr.value, cst.SimpleString):
                return expr.value.evaluated_value
            if isinstance(expr, cst.Expr) and isinstance(expr.value, cst.ConcatenatedString):
                return str(expr.value)
        return None

    def has_import(self) -> bool:
        """Check if the module has any import statements."""
        for stmt in self.module.body:
            if isinstance(stmt, cst.SimpleStatementLine):
                for item in stmt.body:
                    if isinstance(item, (cst.Import, cst.ImportFrom)):
                        return True
        return False

    def has_main_guard(self) -> bool:
        """Check for a module-level if __name__ == '__main__' guard via CST structure."""
        for stmt in self.module.body:
            if not isinstance(stmt, cst.If):
                continue
            test = stmt.test
            if not isinstance(test, cst.Comparison):
                continue
            left = test.left
            comparisons = test.comparisons
            if not comparisons:
                continue
            right = comparisons[0].comparator
            if self._is_name_main_comparison(left, right):
                return True
            if self._is_name_main_comparison(right, left):
                return True
        return False

    def has_print_call(self) -> bool:
        """Check if the module contains any print() call."""
        class _PrintFinder(cst.CSTVisitor):
            """Find print() calls."""
            METADATA_DEPENDENCIES = (PositionProvider,)
            def __init__(self) -> None:
                self.found = False
            def visit_Call(self, node: cst.Call) -> None:
                """Check call target."""
                if isinstance(node.func, cst.Name) and node.func.value == "print":
                    self.found = True
        finder = _PrintFinder()
        self.wrapper.visit(finder)
        return finder.found

    def module_level_constants(self) -> list[dict]:
        """Return module-level UPPER_SNAKE_CASE assignments."""
        constants = []
        for stmt in self.module.body:
            if isinstance(stmt, cst.SimpleStatementLine):
                for item in stmt.body:
                    if isinstance(item, cst.Assign):
                        for target in item.targets:
                            if isinstance(target.target, cst.Name):
                                name = target.target.value
                                if name == name.upper() and len(name) >= 2 and not name.startswith("_"):
                                    constants.append({"name": name})
        return constants

    # ------------------------------------------------------------------
    # Function-level queries
    # ------------------------------------------------------------------

    def functions_missing_docstrings(self) -> list[dict]:
        """Return violations for functions missing docstrings."""
        collector = _FunctionDocstringCollector()
        self.wrapper.visit(collector)
        return collector.violations

    def decorated_functions_check(self, decorator_patterns: list, check_type: str) -> list[dict]:
        """Check decorated functions for docstrings or try/except."""
        collector = _DecoratedFunctionCollector(decorator_patterns, check_type)
        self.wrapper.visit(collector)
        return collector.violations

    def for_loops_without_progress(self) -> list[dict]:
        """Return violations for for-loops without progress tracking."""
        collector = _ForLoopProgressCollector()
        collector._module_for_codegen = self.module
        self.wrapper.visit(collector)
        return collector.violations

    # ------------------------------------------------------------------
    # Hardcoded values (scope-aware literal detection)
    # ------------------------------------------------------------------

    def literals_in_function_bodies(self, safe_values: set, safe_contexts: list) -> list[dict]:
        """Find literal values inside function bodies that violate the no-hardcoded-values rule."""
        collector = _LiteralCollector(safe_values, safe_contexts)
        self.wrapper.visit(collector)

        # Attach source lines to violations
        for v in collector.violations:
            line = v.get("line", 0)
            if line and line <= len(self.source_lines):
                v["source"] = self.source_lines[line - 1].rstrip()
            else:
                v["source"] = ""

        return collector.violations

    # ------------------------------------------------------------------
    # Variable injection helpers
    # ------------------------------------------------------------------

    def build_variables(self, extra: Optional[dict] = None) -> dict:
        """Build the variable dict for error template injection."""
        # 1. Derive file identity variables from the path
        filename = os.path.basename(self.filepath)
        directory = os.path.dirname(self.filepath)
        module_name = os.path.splitext(filename)[0]

        # 2. Populate the base variable dict
        variables: dict = {
            "filename": filename,
            "filepath": self.filepath,
            "directory": directory,
            "module_name": module_name,
            "line_count": self.line_count(),
        }

        # 3. Collect function and class names via a lightweight CST visitor
        func_names = []
        class_names = []

        class _NameCollector(cst.CSTVisitor):
            """Collect function and class names."""
            METADATA_DEPENDENCIES = (PositionProvider,)
            def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
                """Record function name."""
                func_names.append(node.name.value)
            def visit_ClassDef(self, node: cst.ClassDef) -> None:
                """Record class name."""
                class_names.append(node.name.value)

        self.wrapper.visit(_NameCollector())

        # 4. Join collected names into comma-separated strings
        variables["function_names"] = ", ".join(func_names)
        variables["class_names"] = ", ".join(class_names)

        # 5. Merge any caller-supplied extra variables
        if extra:
            variables.update(extra)

        return variables

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_name_main_comparison(left: cst.BaseExpression, right: cst.BaseExpression) -> bool:
        """Check if left is __name__ and right is '__main__'."""
        if not isinstance(left, cst.Name) or left.value != "__name__":
            return False
        if isinstance(right, cst.SimpleString):
            val = right.evaluated_value
            return val == "__main__"
        return False
