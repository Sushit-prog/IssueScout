"""BM25 ranking baseline with custom tokenizer for source code."""

import logging
import re

from rank_bm25 import BM25L  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Tokenizer patterns - match snake_case, camelCase, PascalCase, and alphanumeric
# Don't split on digits embedded in identifiers (e.g., user2name stays as one token)
# Split camelCase/PascalCase at boundaries
IDENTIFIER_PATTERN = re.compile(
    r"""
    [a-z]+(?=[A-Z])          # lowercase before uppercase: getUser -> get
    | [A-Z]+(?=[A-Z][a-z])   # acronyms: XMLParser -> XML
    | [A-Z]?[a-z]+           # camelCase/PascalCase words: User, Name
    | \d+                    # standalone numbers
    | [a-zA-Z]+              # plain words
    """,
    re.VERBOSE,
)


def tokenize_code(text: str) -> list[str]:
    """Tokenize source code text for BM25 indexing.

    Splits on:
    - Snake_case identifiers: get_user_name -> [get, user, name]
    - camelCase/PascalCase identifiers: getUserName -> [get, User, Name]
    - File path components: src/auth/user.py -> [src, auth, user, py]
    - Regular words and numbers

    Args:
        text: Source code or file path text

    Returns:
        List of tokens (preserving case, min length 1 for numbers)
    """
    tokens = []

    # Split by non-alphanumeric first to get identifiers and path components
    parts = re.split(r"[^\w]+", text)

    for part in parts:
        if not part:
            continue

        # Handle file path components (split by /)
        if "/" in part:
            path_parts = part.split("/")
            for p in path_parts:
                if p:
                    tokens.extend(_split_identifier(p))
        else:
            tokens.extend(_split_identifier(part))

    # Filter out empty tokens
    # Keep single-char tokens if they are digits (e.g., "2", "4")
    tokens = [t for t in tokens if t and (len(t) >= 2 or t.isdigit())]

    return tokens


def _split_identifier(identifier: str) -> list[str]:
    """Split a single identifier into tokens (snake_case, camelCase, PascalCase).

    Does NOT split on digits embedded in identifiers (e.g., user2name stays as one token).
    """
    # First try snake_case
    if "_" in identifier:
        return [p for p in identifier.split("_") if p]

    # Check if identifier has embedded digits (e.g., user2name, v2_api)
    # If so, don't split on camelCase boundaries that would separate letters from digits
    # We'll use the regex which naturally handles this

    # Try camelCase/PascalCase using regex
    matches = IDENTIFIER_PATTERN.findall(identifier)
    if matches:
        return matches

    # Fallback: whole identifier
    return [identifier]


def tokenize_file_path(file_path: str) -> list[str]:
    """Tokenize a file path for BM25 indexing.

    Extracts meaningful tokens from path components.

    Args:
        file_path: POSIX-style file path (e.g., "src/auth/user.py")

    Returns:
        List of tokens (preserving case, min length 1 for path components)
    """
    tokens = []

    # Split by path separator
    parts = file_path.split("/")
    for part in parts:
        if not part:
            continue

        # Remove extension
        if "." in part:
            name, ext = part.rsplit(".", 1)
            tokens.extend(_split_identifier(name))
            if ext:  # Keep extensions even if short (py, js, etc.)
                tokens.append(ext)
        else:
            tokens.extend(_split_identifier(part))

    # For file paths, allow single-char tokens but filter out empty strings
    tokens = [t for t in tokens if t]

    return tokens


class BM25Index:
    """BM25 index for ranking candidate files against an issue query.

    Uses BM25L variant which has better IDF behavior for small corpora.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """Initialize BM25 index.

        Args:
            k1: Term frequency saturation parameter (default 1.5)
            b: Length normalization parameter (default 0.75)
        """
        self.k1 = k1
        self.b = b
        self._bm25: BM25L | None = None
        self._doc_paths: list[str] = []
        self._doc_tokens: list[list[str]] = []

    def build(self, documents: list[tuple[str, str]]) -> None:
        """Build the BM25 index from documents.

        Args:
            documents: List of (file_path, content) tuples
        """
        self._doc_paths = []
        self._doc_tokens = []

        for file_path, content in documents:
            self._doc_paths.append(file_path)
            # Combine file path tokens with content tokens for better matching
            path_tokens = tokenize_file_path(file_path)
            content_tokens = tokenize_code(content)
            # Weight path tokens more heavily by duplicating them
            combined_tokens = path_tokens * 2 + content_tokens
            self._doc_tokens.append(combined_tokens)

        if self._doc_tokens:
            self._bm25 = BM25L(self._doc_tokens, k1=self.k1, b=self.b)
            logger.debug(f"Built BM25 index with {len(self._doc_paths)} documents")
        else:
            self._bm25 = None
            logger.warning("BM25 index built with zero documents")

    def query(self, query_text: str, k: int = 10) -> list[tuple[str, float]]:
        """Query the index for top-k matching documents.

        Args:
            query_text: Issue text (title + body) to search for
            k: Number of top results to return

        Returns:
            List of (file_path, score) tuples sorted by score descending
        """
        if self._bm25 is None or not self._doc_tokens:
            return []

        query_tokens = tokenize_code(query_text)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Get top-k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self._doc_paths[idx], scores[idx]))

        return results

    def __len__(self) -> int:
        """Return number of indexed documents."""
        return len(self._doc_paths)

    def is_empty(self) -> bool:
        """Check if index is empty."""
        return self._bm25 is None or len(self._doc_paths) == 0
