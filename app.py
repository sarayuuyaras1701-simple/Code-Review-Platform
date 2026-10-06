import streamlit as st
import os
import ast
import re
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

# Default Gemini model. Override with GEMINI_MODEL in your .env file
# or by typing a different name in the sidebar.
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# Optional comma-separated fallback models, used if the main model is
# overloaded (503) or rate limited (429). Example in .env:
# GEMINI_FALLBACK_MODELS=gemini-3.5-flash-lite
DEFAULT_FALLBACK_MODELS = os.getenv("GEMINI_FALLBACK_MODELS", "")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# HTTP status codes that are temporary and worth retrying
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES_PER_MODEL = 4  # waits 2s, 4s, 8s between attempts

st.set_page_config(
    page_title="AI Code Review Platform",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CUSTOM CSS - FRONTEND
# ============================================================

st.markdown("""
<style>

.main {
    background-color: #f7f9fc;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
}

.hero {
    padding: 25px;
    border-radius: 18px;
    background: linear-gradient(135deg, #111827, #1e3a8a);
    color: white;
    margin-bottom: 25px;
}

.hero h1 {
    font-size: 40px;
    margin-bottom: 5px;
}

.hero p {
    font-size: 17px;
    opacity: 0.9;
}

.metric-card {
    padding: 20px;
    border-radius: 15px;
    background: white;
    border: 1px solid #e5e7eb;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.metric-number {
    font-size: 30px;
    font-weight: bold;
}

.metric-label {
    color: #6b7280;
}

.issue-high {
    padding: 15px;
    border-radius: 10px;
    border-left: 5px solid #dc2626;
    background: #fef2f2;
    margin: 8px 0;
}

.issue-medium {
    padding: 15px;
    border-radius: 10px;
    border-left: 5px solid #f59e0b;
    background: #fffbeb;
    margin: 8px 0;
}

.issue-low {
    padding: 15px;
    border-radius: 10px;
    border-left: 5px solid #16a34a;
    background: #f0fdf4;
    margin: 8px 0;
}

.info-box {
    padding: 15px;
    border-radius: 10px;
    background: #eff6ff;
    border-left: 5px solid #2563eb;
    margin: 10px 0;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# SESSION STATE
# ============================================================

if "review_result" not in st.session_state:
    st.session_state.review_result = None

if "review_history" not in st.session_state:
    st.session_state.review_history = []


# ============================================================
# STATIC CODE ANALYZER
# ============================================================

def analyze_python(code):

    result = {
        "syntax_valid": True,
        "functions": 0,
        "classes": 0,
        "imports": 0,
        "lines": len(code.splitlines()),
        "comments": 0,
        "issues": []
    }

    try:
        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result["functions"] += 1
            elif isinstance(node, ast.ClassDef):
                result["classes"] += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                result["imports"] += 1

        result["comments"] = sum(
            1 for line in code.splitlines()
            if line.strip().startswith("#")
        )

    except SyntaxError as e:
        result["syntax_valid"] = False
        result["issues"].append({
            "severity": "High",
            "type": "Syntax Error",
            "message": str(e)
        })

    return result


# ============================================================
# SECURITY ANALYZER
# ============================================================

def security_scan(code):

    issues = []

    security_patterns = [
        (r"\beval\s*\(", "Use of eval()", "High",
         "eval() can execute arbitrary code."),
        (r"\bexec\s*\(", "Use of exec()", "High",
         "exec() can execute arbitrary code."),
        (r"os\.system\s*\(", "OS command execution", "High",
         "os.system() may allow command injection."),
        (r"subprocess\.(call|run|Popen)\s*\(", "Subprocess execution",
         "Medium", "Validate external input before executing commands."),
        (r"password\s*=\s*[\"'][^\"']+[\"']", "Hard-coded password", "High",
         "Passwords should not be stored directly in source code."),
        (r"api[_-]?key\s*=\s*[\"'][^\"']+[\"']", "Hard-coded API key", "High",
         "API keys should be stored in environment variables or secrets."),
        (r"SELECT\s+.*\+", "Possible SQL injection", "High",
         "Use parameterized SQL queries."),
        (r"verify\s*=\s*False", "SSL verification disabled", "Medium",
         "SSL certificate verification should normally remain enabled."),
    ]

    for pattern, name, severity, description in security_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            issues.append({
                "name": name,
                "severity": severity,
                "description": description
            })

    return issues


# ============================================================
# CODE QUALITY ANALYZER
# ============================================================

def quality_analysis(code):

    issues = []
    lines = code.splitlines()

    for index, line in enumerate(lines, start=1):

        if len(line) > 120:
            issues.append({
                "line": index,
                "type": "Long Line",
                "severity": "Low",
                "message": "Line exceeds 120 characters."
            })

        if "TODO" in line.upper():
            issues.append({
                "line": index,
                "type": "TODO",
                "severity": "Low",
                "message": "Unresolved TODO found."
            })

    if len(lines) > 300:
        issues.append({
            "line": 0,
            "type": "Large File",
            "severity": "Medium",
            "message": "Consider splitting the code into smaller modules."
        })

    return issues


# ============================================================
# CODE SCORE
# ============================================================

def calculate_score(static_result, security_issues, quality_issues):

    score = 100

    for issue in security_issues:
        if issue["severity"] == "High":
            score -= 15
        elif issue["severity"] == "Medium":
            score -= 8
        else:
            score -= 3

    for issue in quality_issues:
        if issue["severity"] == "High":
            score -= 10
        elif issue["severity"] == "Medium":
            score -= 5
        else:
            score -= 2

    if not static_result["syntax_valid"]:
        score -= 25

    return max(0, min(100, score))


# ============================================================
# GEMINI BACKEND
# ============================================================

def get_gemini_key():

    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    return os.getenv("GEMINI_API_KEY")


def build_gemini_prompt(code, language, static_result,
                        security_issues, quality_issues):

    return f"""
You are an expert senior software engineer and security reviewer.

Analyze the following {language} code.

CODE:
-------------------------
{code}
-------------------------

STATIC ANALYSIS:
{json.dumps(static_result, indent=2)}

SECURITY ANALYSIS:
{json.dumps(security_issues, indent=2)}

QUALITY ANALYSIS:
{json.dumps(quality_issues, indent=2)}

Provide a professional code review.

Return the response using these exact sections:

## Executive Summary

Give a short summary.

## Bugs

Identify logical or runtime bugs.

For every bug provide:
- Severity
- Problem
- Explanation
- Suggested Fix

## Security Issues

Identify security vulnerabilities.

For every issue provide:
- Severity
- Vulnerability
- Risk
- Recommended Fix

## Performance

Give performance improvement suggestions.

## Code Quality

Discuss readability, maintainability and best practices.

## Fixed Code

Provide an improved version of the code.

## Final Assessment

Give:
- Code Quality Score out of 100
- Security Score out of 100
- Overall Recommendation

Do not invent vulnerabilities that are not reasonably supported by the code.
"""


def call_gemini_model(model, prompt, api_key):
    """
    Calls one Gemini model with automatic retries for temporary errors
    (503 overloaded, 429 rate limit, 5xx). Returns (text, error).
    """

    url = f"{GEMINI_BASE_URL}/{model}:generateContent"

    # API key is sent in a header, NOT in the URL, so it never shows up
    # in error messages or logs.
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    last_error = None

    for attempt in range(MAX_RETRIES_PER_MODEL):

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=120
            )

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as e:
            # Dropped/aborted connections are usually temporary, so retry
            last_error = (
                f"Network error while contacting Gemini "
                f"(model: {model}): {e}"
            )
            response = None

        except requests.exceptions.RequestException as e:
            return None, f"Network error while contacting Gemini: {e}"

        if response is not None:

            if response.status_code == 200:

                try:
                    data = response.json()
                    candidates = data.get("candidates", [])

                    if not candidates:
                        feedback = data.get("promptFeedback", {})
                        return None, (
                            "Gemini returned no response "
                            f"(possibly blocked). Details: {feedback}"
                        )

                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts)

                    if not text.strip():
                        return None, "Gemini returned an empty response."

                    return text, None

                except (ValueError, KeyError, IndexError) as e:
                    return None, f"Could not read Gemini response: {e}"

            if response.status_code not in RETRYABLE_STATUS:
                # Permanent error (bad key, model not found, bad request...)
                return None, (
                    f"Gemini API Error {response.status_code} "
                    f"(model: {model})\n{response.text}"
                )

            last_error = (
                f"Gemini API Error {response.status_code} "
                f"(model: {model})\n{response.text}"
            )

        # Wait before retrying: 2s, 4s, 8s ...
        if attempt < MAX_RETRIES_PER_MODEL - 1:
            time.sleep(2 ** (attempt + 1))

    return None, last_error


def gemini_review(code, language, static_result,
                  security_issues, quality_issues,
                  model, fallback_models):

    api_key = get_gemini_key()

    if not api_key:
        return None, "Gemini API key not configured.", None

    prompt = build_gemini_prompt(
        code, language, static_result,
        security_issues, quality_issues
    )

    models_to_try = [model] + [
        m for m in fallback_models if m and m != model
    ]

    errors = []

    for candidate in models_to_try:

        text, error = call_gemini_model(candidate, prompt, api_key)

        if text:
            return text, None, candidate

        errors.append(error)

        # Don't bother with fallbacks if the key itself is the problem
        if error and "API_KEY_INVALID" in error:
            break

    return None, "\n\n".join(e for e in errors if e), None


# ============================================================
# OLLAMA BACKEND
# ============================================================

def ollama_review(code, language,
                  static_result,
                  security_issues,
                  quality_issues):

    prompt = f"""
You are a senior software engineer.

Review this {language} code.

CODE:
{code}

STATIC ANALYSIS:
{static_result}

SECURITY ISSUES:
{security_issues}

QUALITY ISSUES:
{quality_issues}

Explain:

1. Bugs
2. Security vulnerabilities
3. Performance problems
4. Code quality problems
5. Best practices
6. Fixed code
7. Overall assessment

Be precise and do not invent issues.
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": prompt,
                "stream": False
            },
            timeout=180
        )

        if response.status_code != 200:
            return None, response.text

        data = response.json()
        return data.get("response"), None

    except requests.exceptions.ConnectionError:
        return None, (
            "Could not connect to Ollama at http://localhost:11434. "
            "Make sure Ollama is running and the 'llama3.2' model is installed."
        )

    except Exception as e:
        return None, str(e)


# ============================================================
# GITHUB CODE LOADER
# ============================================================

def load_github_file(url):

    try:
        url = url.strip()

        if "github.com" not in url:
            return None, "Please enter a valid GitHub URL."

        # Already a raw URL
        if "raw.githubusercontent.com" in url:
            final_url = url

        else:
            parts = url.replace("https://", "").replace("http://", "").split("/")

            # Expected: github.com / user / repo / blob / branch / path...
            if len(parts) < 6 or parts[3] != "blob":
                return None, (
                    "Invalid GitHub file URL. Use a link like "
                    "https://github.com/user/repo/blob/main/app.py"
                )

            username = parts[1]
            repository = parts[2]
            branch = parts[4]
            file_path = "/".join(parts[5:])

            final_url = (
                f"https://raw.githubusercontent.com/"
                f"{username}/{repository}/{branch}/{file_path}"
            )

        response = requests.get(final_url, timeout=20)

        if response.status_code != 200:
            return None, "Could not retrieve GitHub file."

        return response.text, None

    except Exception as e:
        return None, str(e)


# ============================================================
# REVIEW ENGINE
# ============================================================

def perform_review(code, language, ai_provider,
                   model=DEFAULT_GEMINI_MODEL, fallback_models=None):

    fallback_models = fallback_models or []

    static_result = {
        "syntax_valid": True,
        "functions": 0,
        "classes": 0,
        "imports": 0,
        "lines": len(code.splitlines()),
        "comments": 0,
        "issues": []
    }

    if language == "Python":
        static_result = analyze_python(code)

    security_issues = security_scan(code)
    quality_issues = quality_analysis(code)

    score = calculate_score(
        static_result,
        security_issues,
        quality_issues
    )

    ai_result = None
    error = None
    model_used = None

    if ai_provider == "Gemini":

        ai_result, error, model_used = gemini_review(
            code,
            language,
            static_result,
            security_issues,
            quality_issues,
            model,
            fallback_models
        )

    elif ai_provider == "Ollama":

        ai_result, error = ollama_review(
            code,
            language,
            static_result,
            security_issues,
            quality_issues
        )
        model_used = "llama3.2"

    return {
        "static": static_result,
        "security": security_issues,
        "quality": quality_issues,
        "score": score,
        "ai_review": ai_result,
        "error": error,
        "model_used": model_used,
        "code": code,
        "language": language,
        "provider": ai_provider
    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Review Settings")

    language = st.selectbox(
        "Programming Language",
        ["Python", "Java", "C", "C++", "JavaScript"]
    )

    provider = st.selectbox(
        "AI Engine",
        ["Gemini", "Ollama"]
    )

    gemini_model = DEFAULT_GEMINI_MODEL
    fallback_models = []

    if provider == "Gemini":

        gemini_model = st.text_input(
            "Gemini Model",
            value=DEFAULT_GEMINI_MODEL,
            help="Model name as shown in Google AI Studio."
        ).strip()

        fallback_input = st.text_input(
            "Fallback Models (comma separated)",
            value=DEFAULT_FALLBACK_MODELS,
            help="Tried automatically if the main model is overloaded."
        )

        fallback_models = [
            m.strip() for m in fallback_input.split(",") if m.strip()
        ]

    st.divider()

    st.subheader("Analysis Modules")

    st.checkbox("Bug Detection", value=True, disabled=True)
    st.checkbox("Security Analysis", value=True, disabled=True)
    st.checkbox("Performance Analysis", value=True, disabled=True)
    st.checkbox("Code Quality", value=True, disabled=True)

    st.divider()

    st.info(
        "💡 Gemini provides cloud-based AI analysis. "
        "Ollama can be used for local/private analysis."
    )


# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class="hero">

<h1>🔍 AI Code Review Platform</h1>

<p>
An intelligent code review assistant that detects bugs,
security vulnerabilities, performance issues and code-quality
problems using AI.
</p>

</div>
""", unsafe_allow_html=True)


# ============================================================
# INPUT TABS
# ============================================================

tab1, tab2 = st.tabs(["📝 Paste Code", "🔗 GitHub File"])


# ============================================================
# TAB 1 - CODE INPUT
# ============================================================

with tab1:

    st.subheader("Enter Your Source Code")

    code = st.text_area(
        "Source Code",
        height=350,
        placeholder="""Paste your code here...

Example:

def calculate_average(numbers):
    return sum(numbers) / len(numbers)
""",
        label_visibility="collapsed"
    )


# ============================================================
# TAB 2 - GITHUB
# ============================================================

with tab2:

    st.subheader("Analyze a GitHub File")

    github_url = st.text_input(
        "GitHub File URL",
        placeholder="https://github.com/user/repository/blob/main/app.py"
    )

    if st.button("📥 Load GitHub Code"):

        if github_url:

            with st.spinner("Loading GitHub file..."):
                loaded_code, github_error = load_github_file(github_url)

            if github_error:
                st.error(github_error)
            else:
                st.session_state.github_code = loaded_code
                st.success("GitHub code loaded successfully.")
                st.code(loaded_code, language=language.lower())

        else:
            st.warning("Enter a GitHub URL.")

    if st.session_state.get("github_code"):
        if st.button("🗑️ Clear loaded GitHub code"):
            st.session_state.github_code = None
            st.rerun()


# ============================================================
# USE GITHUB CODE (only if nothing was pasted)
# ============================================================

if not code.strip() and st.session_state.get("github_code"):
    code = st.session_state.github_code


# ============================================================
# REVIEW BUTTON
# ============================================================

st.divider()

col1, col2, col3 = st.columns([1, 1, 1])

with col2:
    review_button = st.button(
        "🚀 REVIEW CODE",
        use_container_width=True,
        type="primary"
    )


# ============================================================
# RUN REVIEW
# ============================================================

if review_button:

    if not code.strip():
        st.warning("⚠️ Please enter source code before starting the review.")
        st.stop()

    with st.spinner(
        "🔎 Analyzing your code with AI... "
        "(retries automatically if the model is busy)"
    ):
        result = perform_review(
            code,
            language,
            provider,
            model=gemini_model,
            fallback_models=fallback_models
        )

    st.session_state.review_result = result

    st.session_state.review_history.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "language": language,
        "model": result.get("model_used") or "-",
        "score": result["score"]
    })


# ============================================================
# DISPLAY RESULTS
# ============================================================

result = st.session_state.review_result

if result:

    # Use the code/settings that were actually reviewed
    reviewed_code = result.get("code", code)
    reviewed_language = result.get("language", language)
    reviewed_provider = result.get("provider", provider)

    st.divider()

    st.header("📊 Review Dashboard")

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    security_count = len(result["security"])
    quality_count = len(result["quality"])
    score = result["score"]

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">{score}</div>
            <div class="metric-label">Code Score</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">{security_count}</div>
            <div class="metric-label">Security Issues</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">{quality_count}</div>
            <div class="metric-label">Quality Issues</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c4:
        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">{result["static"]["lines"]}</div>
            <div class="metric-label">Lines Analyzed</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.write("")

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    st.subheader("🎯 Overall Code Quality")

    st.progress(score / 100)

    if score >= 80:
        st.success("Excellent! The code has relatively few detected issues.")
    elif score >= 60:
        st.warning("Moderate quality. Some improvements are recommended.")
    else:
        st.error("Significant issues detected. The code requires attention.")

    # --------------------------------------------------------
    # STATIC ANALYSIS
    # --------------------------------------------------------

    with st.expander("🔬 Static Analysis", expanded=True):

        s1, s2, s3, s4 = st.columns(4)

        s1.metric(
            "Syntax",
            "Valid" if result["static"]["syntax_valid"] else "Invalid"
        )
        s2.metric("Functions", result["static"]["functions"])
        s3.metric("Classes", result["static"]["classes"])
        s4.metric("Imports", result["static"]["imports"])

        for issue in result["static"]["issues"]:
            st.error(
                f"{issue['severity']}: "
                f"{issue['type']} - "
                f"{issue['message']}"
            )

    # --------------------------------------------------------
    # SECURITY
    # --------------------------------------------------------

    with st.expander("🛡️ Security Analysis", expanded=True):

        if not result["security"]:
            st.success("No obvious security patterns were detected.")

        else:
            for issue in result["security"]:

                severity = issue["severity"]

                if severity == "High":
                    css_class, icon = "issue-high", "🔴"
                elif severity == "Medium":
                    css_class, icon = "issue-medium", "🟠"
                else:
                    css_class, icon = "issue-low", "🟢"

                st.markdown(
                    f"""
                    <div class="{css_class}">

                    <b>{icon} {severity}</b><br>

                    <b>{issue["name"]}</b><br>

                    {issue["description"]}

                    </div>
                    """,
                    unsafe_allow_html=True
                )

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    with st.expander("✨ Code Quality Analysis"):

        if not result["quality"]:
            st.success("No major code-quality problems detected.")

        else:
            for issue in result["quality"]:
                st.warning(
                    f"Line {issue['line']} | "
                    f"{issue['severity']} | "
                    f"{issue['type']} | "
                    f"{issue['message']}"
                )

    # --------------------------------------------------------
    # AI REVIEW
    # --------------------------------------------------------

    st.header("🤖 AI Senior Developer Review")

    if result["ai_review"]:

        if result.get("model_used"):
            st.caption(f"Generated by: {result['model_used']}")

        st.markdown(result["ai_review"])

    else:

        st.warning("AI review could not be generated.")

        error_text = result.get("error") or ""

        if "503" in error_text or "UNAVAILABLE" in error_text:
            st.info(
                "The AI model is temporarily overloaded. The app already "
                "retried automatically. Wait a minute and click "
                "REVIEW CODE again, or add a fallback model in the sidebar."
            )
        elif "API_KEY_INVALID" in error_text:
            st.info(
                "Your Gemini API key is invalid. Check GEMINI_API_KEY in "
                "your .env file or Streamlit secrets, then restart the app."
            )
        elif "NOT_FOUND" in error_text or "404" in error_text:
            st.info(
                "The selected Gemini model was not found or is no longer "
                "available. Change the model name in the sidebar."
            )

        if error_text:
            st.code(error_text)

    # --------------------------------------------------------
    # ORIGINAL CODE
    # --------------------------------------------------------

    with st.expander("📄 View Submitted Code"):
        st.code(reviewed_code, language=reviewed_language.lower())

    # --------------------------------------------------------
    # DOWNLOAD REPORT
    # --------------------------------------------------------

    report = f"""
AI CODE REVIEW PLATFORM
=======================

Date:
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Language:
{reviewed_language}

AI Engine:
{reviewed_provider} ({result.get("model_used") or "n/a"})

Overall Score:
{score}/100


STATIC ANALYSIS
---------------

Syntax Valid:
{result["static"]["syntax_valid"]}

Lines:
{result["static"]["lines"]}

Functions:
{result["static"]["functions"]}

Classes:
{result["static"]["classes"]}

Imports:
{result["static"]["imports"]}


SECURITY ISSUES
---------------

{json.dumps(result["security"], indent=2)}


QUALITY ISSUES
--------------

{json.dumps(result["quality"], indent=2)}


AI REVIEW
---------

{result["ai_review"] or "AI review unavailable."}


SUBMITTED CODE
--------------

{reviewed_code}
"""

    st.download_button(
        "⬇️ Download Complete Review Report",
        report,
        file_name="AI_Code_Review_Report.txt",
        mime="text/plain"
    )


# ============================================================
# REVIEW HISTORY
# ============================================================

if st.session_state.review_history:

    st.divider()

    with st.expander("📚 Review History"):
        st.dataframe(
            st.session_state.review_history,
            use_container_width=True
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.markdown(
    """
<center>

<b>AI Code Review Platform</b><br>

Automated • Intelligent • Secure • Developer Friendly

<br><br>

Built using Python + Streamlit + AI

</center>
""",
    unsafe_allow_html=True
)