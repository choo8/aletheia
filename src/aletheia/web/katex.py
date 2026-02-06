"""KaTeX server-side rendering utilities.

This module provides LaTeX rendering for card content. It attempts to use
the KaTeX CLI for server-side rendering, falling back to client-side
rendering via KaTeX auto-render if the CLI is not available.
"""

import functools
import html
import re
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

# Regex patterns for LaTeX delimiters
DISPLAY_MATH = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")


@functools.lru_cache(maxsize=1000)
def render_latex(latex: str, display_mode: bool = False) -> str:
    """Render LaTeX to HTML using KaTeX CLI.

    Args:
        latex: The LaTeX string to render
        display_mode: If True, render in display mode (centered, larger)

    Returns:
        HTML string with rendered KaTeX, or escaped LaTeX in a span on failure
    """
    try:
        cmd = ["katex"]
        if display_mode:
            cmd.append("--display-mode")

        result = subprocess.run(
            cmd,
            input=latex,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # Return error with original LaTeX visible
            escaped = html.escape(latex)
            error = html.escape(result.stderr[:100])
            return f'<span class="katex-error text-red-500" title="{error}">${escaped}$</span>'

    except FileNotFoundError:
        # KaTeX CLI not installed - return LaTeX for client-side rendering
        escaped = html.escape(latex)
        if display_mode:
            return f'<span class="katex-display-placeholder">$${escaped}$$</span>'
        return f'<span class="katex-inline-placeholder">${escaped}$</span>'

    except subprocess.TimeoutExpired:
        escaped = html.escape(latex)
        return f'<code class="text-red-500">{escaped}</code>'


def render_math(text: str) -> str:
    """Render all LaTeX in text to HTML.

    Processes both display math ($$...$$) and inline math ($...$).

    Args:
        text: Text containing LaTeX expressions

    Returns:
        Text with LaTeX replaced by rendered HTML
    """
    if not text:
        return text

    # Display math first ($$...$$)
    def replace_display(match: re.Match) -> str:
        return render_latex(match.group(1), display_mode=True)

    text = DISPLAY_MATH.sub(replace_display, text)

    # Inline math ($...$)
    def replace_inline(match: re.Match) -> str:
        return render_latex(match.group(1), display_mode=False)

    text = INLINE_MATH.sub(replace_inline, text)

    return text


def setup_katex_filter(templates: "Jinja2Templates") -> None:
    """Add KaTeX filter to Jinja2 templates.

    Args:
        templates: Jinja2Templates instance to add the filter to
    """
    templates.env.filters["katex"] = render_math
    templates.env.globals["katex_css"] = (
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">'
    )
    # Add auto-render script for client-side fallback
    templates.env.globals["katex_autorender"] = """
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
    onload="renderMathInElement(document.body, {
        delimiters: [
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false}
        ]
    });"></script>
"""
