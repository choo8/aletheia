"""LeetCode API service — test and submit solutions."""

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path

from aletheia.leetcode.auth import LeetCodeCredentials


class LeetCodeError(Exception):
    """Error from LeetCode service."""


class SubmissionStatus(StrEnum):
    """Known LeetCode submission status values."""

    ACCEPTED = "Accepted"
    WRONG_ANSWER = "Wrong Answer"
    TIME_LIMIT_EXCEEDED = "Time Limit Exceeded"
    MEMORY_LIMIT_EXCEEDED = "Memory Limit Exceeded"
    RUNTIME_ERROR = "Runtime Error"
    COMPILE_ERROR = "Compile Error"
    OUTPUT_LIMIT_EXCEEDED = "Output Limit Exceeded"
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, _value):
        return cls.UNKNOWN


@dataclass
class TestResult:
    """Result from testing a solution against sample test cases."""

    passed: bool
    total_cases: int
    passed_cases: int
    expected: list[str] | None = None
    actual: list[str] | None = None
    runtime_error: str | None = None
    compile_error: str | None = None


@dataclass
class SubmissionResult:
    """Result from submitting a solution."""

    status: SubmissionStatus
    passed: bool
    runtime_ms: int | None = None
    runtime_percentile: float | None = None
    memory_kb: int | None = None
    memory_percentile: float | None = None
    total_cases: int | None = None
    passed_cases: int | None = None
    error_message: str | None = None


@dataclass
class ProblemDetail:
    """Problem description and starter code from LeetCode."""

    content_html: str
    content_text: str
    code_snippets: dict[str, str] = field(default_factory=dict)


class _HTMLToTextParser(HTMLParser):
    """Simple HTML-to-text converter using stdlib."""

    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs):
        if tag in ("p", "br"):
            self._pieces.append("\n")
        elif tag == "li":
            self._pieces.append("\n- ")
        elif tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str):
        if tag in ("p", "div", "ul", "ol"):
            self._pieces.append("\n")
        elif tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str):
        if not self._skip:
            self._pieces.append(data)

    def handle_entityref(self, name: str):
        from html import unescape

        self._pieces.append(unescape(f"&{name};"))

    def handle_charref(self, name: str):
        from html import unescape

        self._pieces.append(unescape(f"&#{name};"))

    def get_text(self) -> str:
        import re

        text = "".join(self._pieces)
        # Collapse runs of 3+ newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text using stdlib HTMLParser."""
    if not html:
        return ""
    parser = _HTMLToTextParser()
    parser.feed(html)
    return parser.get_text()


# Language aliases → LeetCode slug
_LANGUAGE_MAP = {
    "py": "python3",
    "python": "python3",
    "python3": "python3",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "java": "java",
    "cpp": "cpp",
    "c++": "cpp",
    "c": "c",
    "go": "golang",
    "golang": "golang",
    "rs": "rust",
    "rust": "rust",
    "rb": "ruby",
    "ruby": "ruby",
    "swift": "swift",
    "kt": "kotlin",
    "kotlin": "kotlin",
    "scala": "scala",
    "cs": "csharp",
    "csharp": "csharp",
}

# File extension → LeetCode slug
_EXTENSION_MAP = {
    ".py": "python3",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".go": "golang",
    ".rs": "rust",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".cs": "csharp",
}


class LeetCodeService:
    """Wrapper around the python-leetcode API."""

    def __init__(self, credentials: LeetCodeCredentials):
        try:
            import leetcode
        except ImportError as e:
            raise LeetCodeError(
                "python-leetcode not installed. Install with: pip install aletheia[leetcode]"
            ) from e

        config = leetcode.Configuration()
        config.api_key["LEETCODE_SESSION"] = credentials.leetcode_session
        config.api_key["csrftoken"] = credentials.csrftoken
        config.api_key["x-csrftoken"] = credentials.csrftoken
        config.api_key["Referer"] = "https://leetcode.com"

        self._api = leetcode.DefaultApi(leetcode.ApiClient(config))

    def whoami(self) -> str:
        """Verify credentials and return the username.

        Raises LeetCodeError if credentials are invalid.
        """
        import leetcode

        query = leetcode.GraphqlQuery(
            query="""
            {
                user {
                    username
                }
            }
            """,
            variables={},
        )
        try:
            response = self._api.graphql_post(body=query)
        except Exception as e:
            raise LeetCodeError(f"Failed to verify credentials: {e}") from e

        try:
            return response.data.user.username
        except AttributeError:
            raise LeetCodeError("Session expired or invalid credentials")

    def resolve_question_id(self, frontend_id: str) -> str:
        """Look up the internal questionId for a frontend problem number.

        The LeetCode API uses internal IDs that differ from the frontend
        numbers shown on the website (e.g., problem #42 may have internal
        ID 317).

        Raises LeetCodeError if the problem is not found.
        """
        import leetcode

        query = leetcode.GraphqlQuery(
            query="""
            query problemsetQuestionList(
                $categorySlug: String, $limit: Int,
                $skip: Int, $filters: QuestionListFilterInput
            ) {
                problemsetQuestionList: questionList(
                    categorySlug: $categorySlug, limit: $limit,
                    skip: $skip, filters: $filters
                ) {
                    questions: data {
                        frontendQuestionId: questionFrontendId
                        questionId
                        titleSlug
                    }
                }
            }
            """,
            variables={
                "categorySlug": "",
                "limit": 1,
                "skip": 0,
                "filters": {"searchKeywords": frontend_id},
            },
        )

        try:
            response = self._api.graphql_post(body=query)
        except Exception as e:
            raise LeetCodeError(f"Failed to resolve question ID: {e}") from e

        try:
            questions = response.data.problemset_question_list.questions
            for q in questions:
                if str(q.frontend_question_id) == str(frontend_id):
                    return str(q.question_id)
        except AttributeError:
            pass

        raise LeetCodeError(f"Problem #{frontend_id} not found on LeetCode")

    def get_problem_detail(self, title_slug: str) -> ProblemDetail:
        """Fetch problem description and starter code snippets.

        Args:
            title_slug: Problem URL slug (e.g., "two-sum")

        Returns:
            ProblemDetail with HTML content, plain-text content, and code
            snippets keyed by LeetCode language slug.

        Raises LeetCodeError if the problem is not found or API fails.
        """
        import leetcode

        query = leetcode.GraphqlQuery(
            query="""
            query questionDetail($titleSlug: String!) {
                question(titleSlug: $titleSlug) {
                    content
                    codeSnippets {
                        langSlug
                        code
                    }
                }
            }
            """,
            variables={"titleSlug": title_slug},
        )

        try:
            response = self._api.graphql_post(body=query)
        except Exception as e:
            raise LeetCodeError(f"Failed to fetch problem detail: {e}") from e

        question = getattr(getattr(response, "data", None), "question", None)
        if question is None:
            raise LeetCodeError(f"Problem not found: {title_slug}")

        content_html = getattr(question, "content", "") or ""
        code_snippets_raw = getattr(question, "code_snippets", None) or []

        snippets: dict[str, str] = {}
        for snippet in code_snippets_raw:
            lang_slug = getattr(snippet, "lang_slug", None)
            code = getattr(snippet, "code", None)
            if lang_slug and code:
                snippets[lang_slug] = code

        return ProblemDetail(
            content_html=content_html,
            content_text=_html_to_text(content_html),
            code_snippets=snippets,
        )

    def test_solution(
        self,
        title_slug: str,
        question_id: str,
        code: str,
        language: str,
        data_input: str = "",
    ) -> TestResult:
        """Run solution against sample test cases.

        Args:
            title_slug: Problem URL slug (e.g., "two-sum")
            question_id: Internal question ID
            code: Solution source code
            language: LeetCode language slug (e.g., "python3")
            data_input: Custom test input (uses default if empty)
        """
        import leetcode

        body = leetcode.TestSubmission(
            data_input=data_input,
            lang=language,
            question_id=question_id,
            test_mode=True,
            typed_code=code,
        )

        try:
            interpretation = self._api.problems_problem_interpret_solution_post(
                problem=title_slug, body=body
            )
        except Exception as e:
            raise LeetCodeError(f"Failed to submit test: {e}") from e

        result = self._poll_result(interpretation.interpret_id)
        return self._parse_test_result(result)

    def submit_solution(
        self,
        title_slug: str,
        question_id: str,
        code: str,
        language: str,
    ) -> SubmissionResult:
        """Submit solution for full judging.

        Args:
            title_slug: Problem URL slug (e.g., "two-sum")
            question_id: Internal question ID
            code: Solution source code
            language: LeetCode language slug (e.g., "python3")
        """
        import leetcode

        body = leetcode.Submission(
            judge_type="large",
            lang=language,
            question_id=question_id,
            test_mode=False,
            typed_code=code,
        )

        try:
            submission = self._api.problems_problem_submit_post(problem=title_slug, body=body)
        except Exception as e:
            raise LeetCodeError(f"Failed to submit solution: {e}") from e

        result = self._poll_result(submission.submission_id)
        return self._parse_submission_result(result)

    def _poll_result(self, submission_id, timeout: int = 30):
        """Poll for submission result with exponential backoff.

        Raises LeetCodeError on timeout.
        """
        delay = 1.0
        elapsed = 0.0

        while elapsed < timeout:
            time.sleep(delay)
            elapsed += delay

            try:
                result = self._api.submissions_detail_id_check_get(id=submission_id)
            except Exception as e:
                raise LeetCodeError(f"Failed to check submission status: {e}") from e

            state = getattr(result, "state", None)
            if state == "SUCCESS":
                return result

            delay = min(delay * 1.5, 5.0)

        raise LeetCodeError(f"Submission timed out after {timeout}s")

    @staticmethod
    def _parse_test_result(result) -> TestResult:
        """Parse a raw poll result into a TestResult."""
        runtime_error = getattr(result, "runtime_error", None) or None
        compile_error = getattr(result, "compile_error", None) or None
        run_success = getattr(result, "run_success", False)
        total = getattr(result, "total_testcases", 0) or 0
        correct = getattr(result, "total_correct", 0) or 0

        expected = getattr(result, "expected_code_answer", None)
        actual = getattr(result, "code_answer", None)

        passed = run_success and (not runtime_error) and (not compile_error)
        if total > 0:
            passed = passed and (correct == total)

        return TestResult(
            passed=passed,
            total_cases=total,
            passed_cases=correct,
            expected=expected,
            actual=actual,
            runtime_error=runtime_error,
            compile_error=compile_error,
        )

    @staticmethod
    def _parse_submission_result(result) -> SubmissionResult:
        """Parse a raw poll result into a SubmissionResult."""
        status = SubmissionStatus(getattr(result, "status_msg", "Unknown"))
        passed = status is SubmissionStatus.ACCEPTED
        total = getattr(result, "total_testcases", None)
        correct = getattr(result, "total_correct", None)

        runtime_ms = None
        status_runtime = getattr(result, "status_runtime", None)
        if status_runtime:
            try:
                runtime_ms = int(status_runtime.replace(" ms", "").strip())
            except (ValueError, AttributeError):
                pass

        memory_kb = None
        status_memory = getattr(result, "status_memory", None)
        if status_memory:
            try:
                mem_str = status_memory.strip()
                if "MB" in mem_str:
                    memory_kb = int(float(mem_str.replace(" MB", "")) * 1024)
                elif "KB" in mem_str:
                    memory_kb = int(float(mem_str.replace(" KB", "")))
            except (ValueError, AttributeError):
                pass

        error_parts = []
        for attr in ("runtime_error", "compile_error", "full_runtime_error"):
            val = getattr(result, attr, None)
            if val:
                error_parts.append(str(val))
        error_message = "\n".join(error_parts) if error_parts else None

        return SubmissionResult(
            status=status,
            passed=passed,
            runtime_ms=runtime_ms,
            runtime_percentile=getattr(result, "runtime_percentile", None),
            memory_kb=memory_kb,
            memory_percentile=getattr(result, "memory_percentile", None),
            total_cases=total,
            passed_cases=correct,
            error_message=error_message,
        )


def resolve_code_solution(card) -> str:
    """Resolve the code_solution field to actual source code.

    If code_solution looks like a file path (has a known extension), read
    the file. Otherwise, return it as inline code.

    Raises LeetCodeError if code_solution is missing or file not found.
    """
    code = getattr(card, "code_solution", None)
    if not code:
        raise LeetCodeError("Card has no code_solution set")

    # Check if it looks like a file path
    path = Path(code)
    if path.suffix in _EXTENSION_MAP:
        # Resolve relative paths against ALETHEIA_DATA_DIR
        if not path.is_absolute():
            data_dir = os.environ.get("ALETHEIA_DATA_DIR", ".")
            path = Path(data_dir) / path

        if not path.exists():
            raise LeetCodeError(f"Solution file not found: {path}")
        return path.read_text()

    return code


def resolve_language(card) -> str:
    """Resolve the language for a card's solution.

    Checks (in order):
    1. card.problem_source.language
    2. Extension of code_solution if it's a file path
    3. Raises if neither is available

    Returns the normalized LeetCode language slug.
    Raises LeetCodeError if language cannot be determined.
    """
    # Check problem_source.language first
    source = getattr(card, "problem_source", None)
    if source:
        lang = getattr(source, "language", None)
        if lang:
            normalized = _LANGUAGE_MAP.get(lang.lower())
            if normalized:
                return normalized
            raise LeetCodeError(f"Unknown language: {lang}")

    # Try to infer from file extension
    code = getattr(card, "code_solution", None)
    if code:
        ext = Path(code).suffix
        if ext in _EXTENSION_MAP:
            return _EXTENSION_MAP[ext]

    raise LeetCodeError(
        "Cannot determine language. Set language on the problem source "
        "or use a file path with a known extension."
    )
