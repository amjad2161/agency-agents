"""Tests for agency.nlu_engine — NLUEngine."""

from __future__ import annotations

import pytest

from agency.nlu_engine import Intent, NLUEngine


class TestIntentClassification:
    def setup_method(self):
        self.engine = NLUEngine()

    def test_greet_hello(self):
        assert self.engine.classify_intent("Hello there!") == Intent.GREET

    def test_greet_hi(self):
        assert self.engine.classify_intent("hi JARVIS") == Intent.GREET

    def test_greet_hebrew(self):
        assert self.engine.classify_intent("שלום JARVIS") == Intent.GREET

    def test_query_what(self):
        assert self.engine.classify_intent("What is the capital of France?") == Intent.QUERY

    def test_query_how(self):
        assert self.engine.classify_intent("How do I sort a list in Python?") == Intent.QUERY

    def test_create_intent(self):
        assert self.engine.classify_intent("Create a new file called test.py") == Intent.CREATE

    def test_delete_intent(self):
        assert self.engine.classify_intent("Delete the old logs folder") == Intent.DELETE

    def test_update_intent(self):
        assert self.engine.classify_intent("Update the config file") == Intent.UPDATE

    def test_navigate_intent(self):
        assert self.engine.classify_intent("Go to the settings page") == Intent.NAVIGATE

    def test_help_intent(self):
        assert self.engine.classify_intent("Help me with this") == Intent.HELP

    def test_help_question_mark(self):
        assert self.engine.classify_intent("?") == Intent.HELP

    def test_command_intent(self):
        result = self.engine.classify_intent("Run the deployment script")
        assert result == Intent.COMMAND

    def test_unknown_intent(self):
        result = self.engine.classify_intent("xyzzy plugh twisty passages")
        assert result == Intent.UNKNOWN


class TestEntityExtraction:
    def setup_method(self):
        self.engine = NLUEngine()

    def test_extract_numbers(self):
        entities = self.engine.extract_entities("I have 42 apples and 3.14 pies")
        assert "42" in entities["numbers"]
        assert "3.14" in entities["numbers"]

    def test_extract_url(self):
        entities = self.engine.extract_entities("Visit https://example.com for info")
        assert any("example.com" in u for u in entities["urls"])

    def test_extract_email(self):
        entities = self.engine.extract_entities("Send mail to user@example.com please")
        assert "user@example.com" in entities["emails"]

    def test_extract_quoted_string(self):
        entities = self.engine.extract_entities('Create a file named "hello world"')
        assert "hello world" in entities["quotes"]

    def test_extract_path(self):
        entities = self.engine.extract_entities("Check the config at /etc/jarvis/config.yaml")
        assert any("/etc/jarvis" in p for p in entities["paths"])

    def test_no_entities_returns_empty_lists(self):
        entities = self.engine.extract_entities("just some plain text")
        assert entities["urls"] == []
        assert entities["emails"] == []
        assert entities["quotes"] == []


class TestAnalyze:
    def setup_method(self):
        self.engine = NLUEngine()

    def test_analyze_returns_all_keys(self):
        result = self.engine.analyze("hello there")
        for key in ("text", "intent", "entities", "confidence"):
            assert key in result

    def test_analyze_confidence_range(self):
        result = self.engine.analyze("what is the weather today?")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_analyze_unknown_has_low_confidence(self):
        result = self.engine.analyze("zxqwvbnm")
        assert result["confidence"] <= 0.5

    def test_analyze_intent_is_string(self):
        result = self.engine.analyze("create a report")
        assert isinstance(result["intent"], str)


class TestHelpers:
    def setup_method(self):
        self.engine = NLUEngine()

    def test_is_question_with_question_mark(self):
        assert self.engine.is_question("What time is it?") is True

    def test_is_question_without_mark_but_keyword(self):
        assert self.engine.is_question("what is Python") is True

    def test_is_question_plain_statement(self):
        assert self.engine.is_question("deploy the service now") is False

    def test_get_language_english(self):
        assert self.engine.get_language("Hello how are you today") == "en"

    def test_get_language_hebrew(self):
        lang = self.engine.get_language("שלום מה שלומך היום")
        assert lang == "he"

    def test_get_language_unknown(self):
        lang = self.engine.get_language("1234 5678")
        assert lang == "unknown"
