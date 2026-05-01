"""Tests for agency.code_gen_repl — CodeGenREPL."""

from __future__ import annotations

import pytest

from agency.code_gen_repl import CodeGenREPL


class TestCodeGenREPL:
    # ------------------------------------------------------------------
    # generate()
    # ------------------------------------------------------------------

    def test_generate_print(self):
        repl = CodeGenREPL()
        code = repl.generate("print Hello World")
        assert "print" in code
        assert "Hello World" in code

    def test_generate_calculate(self):
        repl = CodeGenREPL()
        code = repl.generate("calculate 2 + 2")
        assert "2 + 2" in code

    def test_generate_list_files(self):
        repl = CodeGenREPL()
        code = repl.generate("list files in /tmp")
        assert "os.listdir" in code
        assert "/tmp" in code

    def test_generate_fibonacci(self):
        repl = CodeGenREPL()
        code = repl.generate("fibonacci 10")
        assert "fibonacci" in code.lower()
        assert "10" in code

    def test_generate_fallback_unknown(self):
        repl = CodeGenREPL()
        code = repl.generate("dance a jig")
        assert isinstance(code, str)
        assert len(code) > 0

    def test_generate_returns_string(self):
        repl = CodeGenREPL()
        result = repl.generate("print test")
        assert isinstance(result, str)

    # ------------------------------------------------------------------
    # execute()
    # ------------------------------------------------------------------

    def test_execute_simple_print(self):
        repl = CodeGenREPL()
        result = repl.execute('print("hello")')
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]
        assert result["elapsed_s"] >= 0

    def test_execute_returns_stderr_on_error(self):
        repl = CodeGenREPL()
        result = repl.execute("raise ValueError('boom')")
        assert result["returncode"] != 0
        assert "ValueError" in result["stderr"] or "boom" in result["stderr"]

    def test_execute_timeout_returns_minus_one(self):
        repl = CodeGenREPL()
        result = repl.execute("import time; time.sleep(60)", timeout_s=1)
        assert result["returncode"] == -1
        assert "Timeout" in result["stderr"] or "timeout" in result["stderr"].lower()

    def test_execute_result_has_all_keys(self):
        repl = CodeGenREPL()
        result = repl.execute("x = 1")
        for key in ("stdout", "stderr", "returncode", "elapsed_s"):
            assert key in result

    # ------------------------------------------------------------------
    # generate_and_run()
    # ------------------------------------------------------------------

    def test_generate_and_run_fibonacci(self):
        repl = CodeGenREPL()
        entry = repl.generate_and_run("fibonacci 5")
        # fib(5) = 5
        assert "5" in entry["result"]["stdout"]
        assert entry["description"] == "fibonacci 5"
        assert "code" in entry
        assert "result" in entry

    def test_generate_and_run_appends_history(self):
        repl = CodeGenREPL()
        repl.generate_and_run("print something")
        assert len(repl.history()) == 1

    # ------------------------------------------------------------------
    # history() / clear_history()
    # ------------------------------------------------------------------

    def test_history_returns_most_recent_n(self):
        repl = CodeGenREPL()
        for i in range(5):
            repl.generate_and_run(f"print {i}")
        hist = repl.history(n=3)
        assert len(hist) == 3

    def test_clear_history_empties_list(self):
        repl = CodeGenREPL()
        repl.generate_and_run("print hi")
        repl.clear_history()
        assert repl.history() == []
