"""Tests for the LeetCode integration module."""

from http.cookiejar import Cookie
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from aletheia.leetcode.auth import (
    LeetCodeAuthError,
    LeetCodeCredentials,
    clear_credentials,
    extract_browser_cookies,
    get_credentials,
    save_credentials,
)
from aletheia.leetcode.service import (
    LeetCodeError,
    LeetCodeService,
    SubmissionStatus,
    _html_to_text,
    resolve_code_solution,
    resolve_language,
)


class TestCredentials:
    """Tests for credential save/load/clear."""

    def test_save_and_load_round_trip(self, tmp_path: Path):
        """Test saving and loading credentials."""
        creds = LeetCodeCredentials(
            csrftoken="token123",
            leetcode_session="session456",
            username="testuser",
            stored_at="2025-01-01T00:00:00+00:00",
        )
        save_credentials(tmp_path, creds)
        loaded = get_credentials(tmp_path)

        assert loaded is not None
        assert loaded.csrftoken == "token123"
        assert loaded.leetcode_session == "session456"
        assert loaded.username == "testuser"
        assert loaded.stored_at == "2025-01-01T00:00:00+00:00"

    def test_save_creates_directory(self, tmp_path: Path):
        """Test that save creates the state directory if needed."""
        nested = tmp_path / "nested" / "dir"
        creds = LeetCodeCredentials(
            csrftoken="t", leetcode_session="s", username="u", stored_at="now"
        )
        path = save_credentials(nested, creds)
        assert path.exists()
        assert nested.exists()

    def test_load_missing_file_returns_none(self, tmp_path: Path):
        """Test that missing file returns None."""
        result = get_credentials(tmp_path)
        assert result is None

    def test_load_corrupt_file_raises(self, tmp_path: Path):
        """Test that corrupt JSON raises LeetCodeAuthError."""
        (tmp_path / "leetcode_auth.json").write_text("not json")
        with pytest.raises(LeetCodeAuthError, match="Corrupt credentials file"):
            get_credentials(tmp_path)

    @patch.dict(
        "os.environ",
        {"LEETCODE_CSRFTOKEN": "env_csrf", "LEETCODE_SESSION": "env_session"},
    )
    def test_env_var_override(self, tmp_path: Path):
        """Test that env vars take precedence over file."""
        # Save file creds
        creds = LeetCodeCredentials(
            csrftoken="file_csrf",
            leetcode_session="file_session",
            username="fileuser",
            stored_at="2025-01-01T00:00:00+00:00",
        )
        save_credentials(tmp_path, creds)

        loaded = get_credentials(tmp_path)
        assert loaded is not None
        assert loaded.csrftoken == "env_csrf"
        assert loaded.leetcode_session == "env_session"
        assert loaded.username == "env"

    @patch.dict("os.environ", {"LEETCODE_CSRFTOKEN": "only_csrf"}, clear=False)
    def test_env_var_partial_does_not_override(self, tmp_path: Path):
        """Test that partial env vars (only CSRF) fall through to file."""
        import os

        os.environ.pop("LEETCODE_SESSION", None)

        creds = LeetCodeCredentials(
            csrftoken="file_csrf",
            leetcode_session="file_session",
            username="fileuser",
            stored_at="2025-01-01T00:00:00+00:00",
        )
        save_credentials(tmp_path, creds)

        loaded = get_credentials(tmp_path)
        assert loaded is not None
        assert loaded.csrftoken == "file_csrf"

    def test_clear_credentials(self, tmp_path: Path):
        """Test clearing credentials."""
        creds = LeetCodeCredentials(
            csrftoken="t", leetcode_session="s", username="u", stored_at="now"
        )
        save_credentials(tmp_path, creds)
        assert (tmp_path / "leetcode_auth.json").exists()

        result = clear_credentials(tmp_path)
        assert result is True
        assert not (tmp_path / "leetcode_auth.json").exists()

    def test_clear_missing_returns_false(self, tmp_path: Path):
        """Test clearing when no credentials exist."""
        result = clear_credentials(tmp_path)
        assert result is False


def _make_cookie(name: str, value: str) -> Cookie:
    """Create a minimal Cookie object for testing."""
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain="leetcode.com",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
    )


class TestBrowserExtraction:
    """Tests for browser cookie extraction.

    rookiepy is lazily imported inside extract_browser_cookies(), so we mock
    it via sys.modules rather than patching a module-level attribute.
    """

    def _mock_rookiepy(self, cookies):
        """Create a mock rookiepy module that returns the given cookies."""
        mock_rookiepy = MagicMock()
        mock_jar = MagicMock()
        mock_jar.__iter__ = MagicMock(return_value=iter(cookies))
        mock_rookiepy.load.return_value = [{"raw": "data"}]
        mock_rookiepy.to_cookiejar.return_value = mock_jar
        return mock_rookiepy

    def test_extract_success(self):
        """Test successful cookie extraction."""
        mock_rookiepy = self._mock_rookiepy(
            [
                _make_cookie("csrftoken", "csrf_value"),
                _make_cookie("LEETCODE_SESSION", "session_value"),
            ]
        )
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            csrf, session = extract_browser_cookies()
        assert csrf == "csrf_value"
        assert session == "session_value"

    def test_extract_not_installed(self):
        """Test error when rookiepy is not installed."""
        with patch.dict("sys.modules", {"rookiepy": None}):
            with pytest.raises(LeetCodeAuthError, match="rookiepy not installed"):
                extract_browser_cookies()

    def test_extract_missing_csrf(self):
        """Test error when csrftoken cookie is missing."""
        mock_rookiepy = self._mock_rookiepy(
            [
                _make_cookie("LEETCODE_SESSION", "session_value"),
            ]
        )
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            with pytest.raises(LeetCodeAuthError, match="Missing cookies.*csrftoken"):
                extract_browser_cookies()

    def test_extract_missing_session(self):
        """Test error when LEETCODE_SESSION cookie is missing."""
        mock_rookiepy = self._mock_rookiepy(
            [
                _make_cookie("csrftoken", "csrf_value"),
            ]
        )
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            with pytest.raises(LeetCodeAuthError, match="Missing cookies.*LEETCODE_SESSION"):
                extract_browser_cookies()

    def test_extract_rookiepy_failure(self):
        """Test error when rookiepy.load raises."""
        mock_rookiepy = MagicMock()
        mock_rookiepy.load.side_effect = RuntimeError("No browser DB found")
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            with pytest.raises(LeetCodeAuthError, match="Failed to extract"):
                extract_browser_cookies()


# ============================================================================
# Service tests
# ============================================================================


def _make_creds():
    """Create test credentials."""
    return LeetCodeCredentials(
        csrftoken="csrf", leetcode_session="session", username="user", stored_at="now"
    )


def _make_service():
    """Create a LeetCodeService with a mocked API."""
    service = LeetCodeService(_make_creds())
    service._api = MagicMock()
    return service


class TestLeetCodeService:
    """Tests for LeetCodeService."""

    def test_whoami_success(self):
        """Test successful whoami returns username."""
        service = _make_service()
        service._api.graphql_post.return_value = SimpleNamespace(
            data=SimpleNamespace(user=SimpleNamespace(username="leetcoder"))
        )
        assert service.whoami() == "leetcoder"

    def test_whoami_expired_session(self):
        """Test whoami with expired session raises."""
        service = _make_service()
        service._api.graphql_post.return_value = SimpleNamespace(data=SimpleNamespace(user=None))
        with pytest.raises(LeetCodeError, match="expired or invalid"):
            service.whoami()

    def test_whoami_api_failure(self):
        """Test whoami propagates API errors."""
        service = _make_service()
        service._api.graphql_post.side_effect = RuntimeError("network error")
        with pytest.raises(LeetCodeError, match="Failed to verify"):
            service.whoami()

    def test_resolve_question_id_by_title_slug(self):
        """Test resolving question ID via direct title_slug query."""
        service = _make_service()
        service._api.graphql_post.return_value = _raw_response(
            {"data": {"question": {"questionId": "317"}}}
        )
        assert service.resolve_question_id("42", title_slug="trapping-rain-water") == "317"

    def test_resolve_question_id_by_title_slug_not_found(self):
        """Test title_slug query when problem doesn't exist."""
        service = _make_service()
        service._api.graphql_post.return_value = _raw_response({"data": {"question": None}})
        with pytest.raises(LeetCodeError, match="not found"):
            service.resolve_question_id("99999", title_slug="nonexistent")

    def test_resolve_question_id_search_fallback(self):
        """Test resolving frontend ID via search when no title_slug."""
        service = _make_service()
        service._api.graphql_post.return_value = SimpleNamespace(
            data=SimpleNamespace(
                problemset_question_list=SimpleNamespace(
                    questions=[
                        SimpleNamespace(
                            frontend_question_id="42",
                            question_id="317",
                            title_slug="trapping-rain-water",
                        )
                    ]
                )
            )
        )
        assert service.resolve_question_id("42") == "317"

    def test_resolve_question_id_not_found(self):
        """Test resolving non-existent problem via search."""
        service = _make_service()
        service._api.graphql_post.return_value = SimpleNamespace(
            data=SimpleNamespace(problemset_question_list=SimpleNamespace(questions=[]))
        )
        with pytest.raises(LeetCodeError, match="not found"):
            service.resolve_question_id("99999")

    def test_test_solution_pass(self):
        """Test running a solution that passes all test cases."""
        service = _make_service()
        service._api.problems_problem_interpret_solution_post.return_value = _raw_response(
            {"interpret_id": "interp-123"}
        )
        service._api.submissions_detail_id_check_get.return_value = _raw_response(
            {
                "state": "SUCCESS",
                "run_success": True,
                "total_testcases": 3,
                "total_correct": 3,
                "expected_code_answer": ["[1,2]"],
                "code_answer": ["[1,2]"],
            }
        )

        result = service.test_solution("two-sum", "1", "code", "python3")
        assert result.passed is True
        assert result.total_cases == 3
        assert result.passed_cases == 3

    def test_test_solution_fail(self):
        """Test running a solution that fails test cases."""
        service = _make_service()
        service._api.problems_problem_interpret_solution_post.return_value = _raw_response(
            {"interpret_id": "interp-456"}
        )
        service._api.submissions_detail_id_check_get.return_value = _raw_response(
            {
                "state": "SUCCESS",
                "run_success": True,
                "total_testcases": 3,
                "total_correct": 1,
                "expected_code_answer": ["[1,2]"],
                "code_answer": ["[2,3]"],
            }
        )

        result = service.test_solution("two-sum", "1", "code", "python3")
        assert result.passed is False
        assert result.passed_cases == 1

    def test_test_solution_runtime_error(self):
        """Test running a solution with a runtime error."""
        service = _make_service()
        service._api.problems_problem_interpret_solution_post.return_value = _raw_response(
            {"interpret_id": "interp-789"}
        )
        service._api.submissions_detail_id_check_get.return_value = _raw_response(
            {
                "state": "SUCCESS",
                "run_success": False,
                "total_testcases": 0,
                "total_correct": 0,
                "runtime_error": "IndexError: list index out of range",
            }
        )

        result = service.test_solution("two-sum", "1", "code", "python3")
        assert result.passed is False
        assert result.runtime_error is not None

    def test_submit_accepted(self):
        """Test submitting a solution that gets accepted."""
        service = _make_service()
        service._api.problems_problem_submit_post.return_value = _raw_response(
            {"submission_id": 12345}
        )
        service._api.submissions_detail_id_check_get.return_value = _raw_response(
            {
                "state": "SUCCESS",
                "status_msg": "Accepted",
                "run_success": True,
                "total_testcases": 100,
                "total_correct": 100,
                "status_runtime": "40 ms",
                "runtime_percentile": 85.5,
                "status_memory": "16.2 MB",
                "memory_percentile": 70.0,
            }
        )

        result = service.submit_solution("two-sum", "1", "code", "python3")
        assert result.passed is True
        assert result.status is SubmissionStatus.ACCEPTED
        assert result.runtime_ms == 40
        assert result.memory_kb == int(16.2 * 1024)
        assert result.runtime_percentile == 85.5

    def test_submit_wrong_answer(self):
        """Test submitting a solution that gets wrong answer."""
        service = _make_service()
        service._api.problems_problem_submit_post.return_value = _raw_response(
            {"submission_id": 12346}
        )
        service._api.submissions_detail_id_check_get.return_value = _raw_response(
            {
                "state": "SUCCESS",
                "status_msg": "Wrong Answer",
                "run_success": True,
                "total_testcases": 100,
                "total_correct": 50,
            }
        )

        result = service.submit_solution("two-sum", "1", "code", "python3")
        assert result.passed is False
        assert result.status is SubmissionStatus.WRONG_ANSWER
        assert result.passed_cases == 50

    @patch("aletheia.leetcode.service.time.sleep")
    def test_poll_timeout(self, mock_sleep):
        """Test that polling times out correctly."""
        service = _make_service()
        # Always return PENDING
        service._api.submissions_detail_id_check_get.return_value = _raw_response(
            {"state": "PENDING"}
        )
        with pytest.raises(LeetCodeError, match="timed out"):
            service._poll_result("some-id", timeout=3)

    def test_import_error_message(self):
        """Test helpful error when python-leetcode not installed."""
        with patch.dict("sys.modules", {"leetcode": None}):
            with pytest.raises(LeetCodeError, match="python-leetcode not installed"):
                LeetCodeService(_make_creds())


class TestSubmissionStatus:
    """Tests for SubmissionStatus enum."""

    def test_known_status(self):
        """Test that known status values resolve correctly."""
        assert SubmissionStatus("Accepted") is SubmissionStatus.ACCEPTED
        assert SubmissionStatus("Wrong Answer") is SubmissionStatus.WRONG_ANSWER

    def test_unknown_status_falls_back(self):
        """Test that unrecognized status values fall back to UNKNOWN."""
        assert SubmissionStatus("Some New Status") is SubmissionStatus.UNKNOWN

    def test_string_comparison(self):
        """Test that StrEnum allows string comparison."""
        assert SubmissionStatus.ACCEPTED == "Accepted"


class TestResolveCodeSolution:
    """Tests for resolve_code_solution helper."""

    def test_inline_code(self):
        """Test resolving inline code (no file extension)."""
        card = SimpleNamespace(code_solution="def twoSum(nums, target): pass")
        result = resolve_code_solution(card)
        assert result == "def twoSum(nums, target): pass"

    def test_file_path(self, tmp_path: Path):
        """Test resolving code from a file path."""
        solution_file = tmp_path / "solution.py"
        solution_file.write_text("class Solution: pass")

        card = SimpleNamespace(code_solution=str(solution_file))
        result = resolve_code_solution(card)
        assert result == "class Solution: pass"

    def test_relative_file_path(self, tmp_path: Path):
        """Test resolving relative file path against ALETHEIA_DATA_DIR."""
        solution_file = tmp_path / "solution.py"
        solution_file.write_text("class Solution: pass")

        card = SimpleNamespace(code_solution="solution.py")
        with patch.dict("os.environ", {"ALETHEIA_DATA_DIR": str(tmp_path)}):
            result = resolve_code_solution(card)
        assert result == "class Solution: pass"

    def test_missing_code(self):
        """Test error when code_solution is not set."""
        card = SimpleNamespace(code_solution=None)
        with pytest.raises(LeetCodeError, match="no code_solution"):
            resolve_code_solution(card)

    def test_missing_file(self):
        """Test error when solution file does not exist."""
        card = SimpleNamespace(code_solution="/nonexistent/solution.py")
        with pytest.raises(LeetCodeError, match="not found"):
            resolve_code_solution(card)


class TestResolveLanguage:
    """Tests for resolve_language helper."""

    def test_from_problem_source(self):
        """Test resolving language from problem source."""
        card = SimpleNamespace(
            problem_source=SimpleNamespace(language="python3"),
            code_solution=None,
        )
        assert resolve_language(card) == "python3"

    def test_from_alias(self):
        """Test resolving language alias."""
        card = SimpleNamespace(
            problem_source=SimpleNamespace(language="py"),
            code_solution=None,
        )
        assert resolve_language(card) == "python3"

    def test_from_file_extension(self):
        """Test inferring language from file extension."""
        card = SimpleNamespace(
            problem_source=None,
            code_solution="solution.cpp",
        )
        assert resolve_language(card) == "cpp"

    def test_unknown_language(self):
        """Test error for unknown language."""
        card = SimpleNamespace(
            problem_source=SimpleNamespace(language="brainfuck"),
            code_solution=None,
        )
        with pytest.raises(LeetCodeError, match="Unknown language"):
            resolve_language(card)

    def test_missing_language(self):
        """Test error when no language can be determined."""
        card = SimpleNamespace(
            problem_source=None,
            code_solution="some inline code",
        )
        with pytest.raises(LeetCodeError, match="Cannot determine language"):
            resolve_language(card)

    def test_source_language_none_fallback_to_extension(self):
        """Test fallback to file extension when source language is None."""
        card = SimpleNamespace(
            problem_source=SimpleNamespace(language=None),
            code_solution="solution.java",
        )
        assert resolve_language(card) == "java"


class TestHtmlToText:
    """Tests for _html_to_text helper."""

    def test_paragraphs(self):
        """Test paragraph tags become newlines."""
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        text = _html_to_text(html)
        assert "First paragraph." in text
        assert "Second paragraph." in text
        # Paragraphs should be on separate lines
        assert "\n" in text

    def test_list_items(self):
        """Test list items get bullet prefixes."""
        html = "<ul><li>one</li><li>two</li></ul>"
        text = _html_to_text(html)
        assert "- one" in text
        assert "- two" in text

    def test_html_entities(self):
        """Test HTML entities are decoded."""
        html = "<p>a &lt; b &amp; c &gt; d</p>"
        text = _html_to_text(html)
        assert "a < b & c > d" in text

    def test_numeric_entities(self):
        """Test numeric character references are decoded."""
        html = "<p>&#60;tag&#62;</p>"
        text = _html_to_text(html)
        assert "<tag>" in text

    def test_empty_input(self):
        """Test empty/falsy input returns empty string."""
        assert _html_to_text("") == ""
        assert _html_to_text(None) == ""

    def test_br_tags(self):
        """Test <br> tags become newlines."""
        html = "line one<br>line two"
        text = _html_to_text(html)
        assert "line one" in text
        assert "line two" in text


def _raw_response(data: dict) -> SimpleNamespace:
    """Create a mock raw HTTP response with JSON data."""
    import json

    return SimpleNamespace(data=json.dumps(data).encode())


class TestProblemDetail:
    """Tests for get_problem_detail."""

    def test_success(self):
        """Test successful fetch of problem detail."""
        service = _make_service()
        service._api.graphql_post.return_value = _raw_response(
            {
                "data": {
                    "question": {
                        "content": "<p>Given an array...</p>",
                        "codeSnippets": [
                            {
                                "langSlug": "python3",
                                "code": "class Solution:\n    def twoSum(self, nums, target):",
                            },
                            {
                                "langSlug": "cpp",
                                "code": "class Solution {\npublic:\n};",
                            },
                        ],
                    }
                }
            }
        )

        detail = service.get_problem_detail("two-sum")
        assert "Given an array" in detail.content_html
        assert "Given an array" in detail.content_text
        assert "python3" in detail.code_snippets
        assert "cpp" in detail.code_snippets
        assert "twoSum" in detail.code_snippets["python3"]

    def test_not_found(self):
        """Test error when problem slug is invalid."""
        service = _make_service()
        service._api.graphql_post.return_value = _raw_response({"data": {"question": None}})

        with pytest.raises(LeetCodeError, match="not found"):
            service.get_problem_detail("nonexistent-problem")

    def test_api_error(self):
        """Test error when API call fails."""
        service = _make_service()
        service._api.graphql_post.side_effect = RuntimeError("network error")

        with pytest.raises(LeetCodeError, match="Failed to fetch"):
            service.get_problem_detail("two-sum")
