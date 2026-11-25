"""Tests for BM25 baseline ranking."""

from issuescout.baselines.bm25 import (
    BM25Index,
    _split_identifier,
    tokenize_code,
    tokenize_file_path,
)


class TestSplitIdentifier:
    """Tests for _split_identifier function."""

    def test_snake_case(self):
        """Test snake_case splitting."""
        assert _split_identifier("get_user_name") == ["get", "user", "name"]
        assert _split_identifier("calculate_total_price") == ["calculate", "total", "price"]
        assert _split_identifier("simple") == ["simple"]
        assert _split_identifier("with_underscore") == ["with", "underscore"]

    def test_camel_case(self):
        """Test camelCase splitting."""
        assert _split_identifier("getUserName") == ["get", "User", "Name"]
        assert _split_identifier("calculateTotalPrice") == ["calculate", "Total", "Price"]
        assert _split_identifier("simple") == ["simple"]

    def test_pascal_case(self):
        """Test PascalCase splitting."""
        assert _split_identifier("GetUserName") == ["Get", "User", "Name"]
        assert _split_identifier("CalculateTotalPrice") == ["Calculate", "Total", "Price"]
        assert _split_identifier("XMLParser") == ["XML", "Parser"]
        assert _split_identifier("HTTPSConnection") == ["HTTPS", "Connection"]

    def test_numbers(self):
        """Test identifiers with numbers."""
        # Embedded numbers are split (user2name -> user, 2, name)
        # This is useful for code search as it matches partial queries
        assert _split_identifier("user2name") == ["user", "2", "name"]
        assert _split_identifier("v2_api") == ["v2", "api"]
        assert _split_identifier("error_404") == ["error", "404"]

    def test_acronyms(self):
        """Test acronym handling."""
        assert _split_identifier("parseJSON") == ["parse", "JSON"]
        assert _split_identifier("getURLPath") == ["get", "URL", "Path"]
        assert _split_identifier("IOError") == ["IO", "Error"]


class TestTokenizeCode:
    """Tests for tokenize_code function."""

    def test_basic_python_code(self):
        """Test tokenizing basic Python code."""
        code = "def get_user_name():\n    return 'hello'"
        tokens = tokenize_code(code)
        assert "get" in tokens
        assert "user" in tokens
        assert "name" in tokens
        assert "return" in tokens
        assert "hello" in tokens

    def test_class_and_method_names(self):
        """Test tokenizing class and method names."""
        code = "class UserService:\n    def calculate_total(self):\n        pass"
        tokens = tokenize_code(code)
        assert "User" in tokens
        assert "Service" in tokens
        assert "calculate" in tokens
        assert "total" in tokens

    def test_file_path_in_code(self):
        """Test tokenizing file paths mentioned in code."""
        code = "from src.auth.user import UserModel\nimport os.path"
        tokens = tokenize_code(code)
        assert "src" in tokens
        assert "auth" in tokens
        assert "user" in tokens
        assert "User" in tokens
        assert "Model" in tokens

    def test_short_tokens_filtered(self):
        """Test that short tokens (< 2 chars) are filtered."""
        code = "a = 1\nif x > y:\n    pass"
        tokens = tokenize_code(code)
        # Single letters should be filtered out
        assert "a" not in tokens
        assert "x" not in tokens
        assert "y" not in tokens

    def test_numbers_preserved(self):
        """Test that numbers are preserved."""
        code = "version = 2\ncount = 42"
        tokens = tokenize_code(code)
        assert "2" in tokens
        assert "42" in tokens

    def test_empty_input(self):
        """Test empty input returns empty list."""
        assert tokenize_code("") == []
        assert tokenize_code("   \n\n  ") == []

    def test_special_characters_removed(self):
        """Test that special characters don't create tokens."""
        code = "result = func(arg1, arg2) + other_func()"
        tokens = tokenize_code(code)
        assert "(" not in tokens
        assert ")" not in tokens
        assert "," not in tokens
        assert "+" not in tokens


class TestTokenizeFilePath:
    """Tests for tokenize_file_path function."""

    def test_basic_path(self):
        """Test basic file path tokenization."""
        tokens = tokenize_file_path("src/auth/user.py")
        assert "src" in tokens
        assert "auth" in tokens
        assert "user" in tokens
        assert "py" in tokens

    def test_nested_path(self):
        """Test deeply nested path."""
        tokens = tokenize_file_path("a/b/c/d/e.py")
        assert set(tokens) == {"a", "b", "c", "d", "e", "py"}

    def test_snake_case_in_path(self):
        """Test snake_case components in path."""
        tokens = tokenize_file_path("src/user_service/models.py")
        assert "user" in tokens
        assert "service" in tokens
        assert "models" in tokens

    def test_camel_case_in_path(self):
        """Test camelCase components in path."""
        tokens = tokenize_file_path("src/UserService/Models.py")
        assert "User" in tokens
        assert "Service" in tokens
        assert "Models" in tokens

    def test_extension_preserved(self):
        """Test file extension is preserved as token."""
        tokens = tokenize_file_path("config.json")
        assert "config" in tokens
        assert "json" in tokens

        tokens = tokenize_file_path("script.js")
        assert "script" in tokens
        assert "js" in tokens

    def test_no_extension(self):
        """Test path without extension."""
        tokens = tokenize_file_path("README")
        assert "README" in tokens

    def test_root_file(self):
        """Test file at root level."""
        tokens = tokenize_file_path("main.py")
        assert "main" in tokens
        assert "py" in tokens


class TestBM25Index:
    """Tests for BM25Index class."""

    def test_build_empty(self):
        """Test building index with no documents."""
        index = BM25Index()
        index.build([])
        assert index.is_empty()
        assert len(index) == 0

    def test_build_single_document(self):
        """Test building index with one document."""
        index = BM25Index()
        index.build([("src/main.py", "def main():\n    print('hello')")])
        assert not index.is_empty()
        assert len(index) == 1

    def test_build_multiple_documents(self):
        """Test building index with multiple documents."""
        docs = [
            ("src/auth.py", "class Auth:\n    def login(self): pass"),
            ("src/models.py", "class User:\n    def get_name(self): pass"),
            ("tests/test_auth.py", "def test_login(): pass"),
        ]
        index = BM25Index()
        index.build(docs)
        assert len(index) == 3

    def test_query_empty_index(self):
        """Test querying empty index returns empty results."""
        index = BM25Index()
        index.build([])
        results = index.query("login", k=5)
        assert results == []

    def test_query_basic_match(self):
        """Test basic query matching."""
        docs = [
            ("src/auth.py", "class Auth:\n    def login(self):\n        return True"),
            ("src/models.py", "class User:\n    def get_name(self):\n        return 'John'"),
        ]
        index = BM25Index()
        index.build(docs)

        results = index.query("login authentication", k=2)
        assert len(results) == 1
        assert results[0][0] == "src/auth.py"
        assert results[0][1] > 0

    def test_query_ranks_by_relevance(self):
        """Test that results are ranked by relevance."""
        auth_content = (
            "class Auth:\n    def login(self):\n        return True\n    def logout(self): pass"
        )
        user_content = "class User:\n    def login_count(self):\n        return 5"
        docs = [
            ("src/auth.py", auth_content),
            ("src/user.py", user_content),
            ("src/config.py", "DEBUG = True"),
        ]
        index = BM25Index()
        index.build(docs)

        results = index.query("login logout", k=3)
        assert len(results) == 2
        # auth.py should rank higher (has both login and logout)
        assert results[0][0] == "src/auth.py"
        assert results[1][0] == "src/user.py"

    def test_query_file_path_tokens(self):
        """Test that file path tokens contribute to ranking."""
        docs = [
            ("src/auth/login.py", "def helper():\n    pass"),
            (
                "src/payment/process.py",
                "def login():\n    pass",
            ),  # has login in content but not path
        ]
        index = BM25Index()
        index.build(docs)

        results = index.query("auth login", k=2)
        # auth/login.py should rank higher due to path tokens
        assert results[0][0] == "src/auth/login.py"

    def test_query_k_limit(self):
        """Test that k parameter limits results."""
        docs = [(f"src/file{i}.py", f"content {i}") for i in range(20)]
        index = BM25Index()
        index.build(docs)

        results = index.query("content", k=5)
        assert len(results) == 5

        results = index.query("content", k=100)
        assert len(results) == 20

    def test_query_no_matches(self):
        """Test query with no matching terms returns empty."""
        docs = [
            ("src/auth.py", "class Auth:\n    def login(self): pass"),
        ]
        index = BM25Index()
        index.build(docs)

        results = index.query("completely unrelated terms", k=5)
        assert results == []

    def test_custom_k1_b_parameters(self):
        """Test custom BM25 parameters."""
        index = BM25Index(k1=1.2, b=0.5)
        assert index.k1 == 1.2
        assert index.b == 0.5

    def test_query_empty_string(self):
        """Test query with empty string returns empty results."""
        docs = [("src/main.py", "def main(): pass")]
        index = BM25Index()
        index.build(docs)

        results = index.query("", k=5)
        assert results == []

    def test_query_whitespace_only(self):
        """Test query with only whitespace returns empty results."""
        docs = [("src/main.py", "def main(): pass")]
        index = BM25Index()
        index.build(docs)

        results = index.query("   \n\t  ", k=5)
        assert results == []


class TestBM25Integration:
    """Integration tests for BM25 with realistic scenarios."""

    def test_issue_title_and_body(self):
        """Test querying with issue title + body."""
        login_content = (
            "class LoginHandler:\n    def authenticate(self, user, pwd):\n"
            "        return check_credentials(user, pwd)"
        )
        session_content = (
            "class SessionManager:\n    def create_session(self, user_id):\n"
            "        return generate_token(user_id)"
        )
        user_content = (
            "class User:\n    def verify_password(self, pwd):\n"
            "        return hash(pwd) == self.password_hash"
        )
        docs = [
            ("src/auth/login.py", login_content),
            ("src/auth/session.py", session_content),
            ("src/models/user.py", user_content),
        ]
        index = BM25Index()
        index.build(docs)

        # Simulate issue: "User authentication fails when password is correct"
        issue_text = "User authentication fails when password is correct login"
        results = index.query(issue_text, k=3)

        # Only 2 docs have matching terms (session.py doesn't match query terms)
        assert len(results) == 2
        # user.py ranks highest due to "User" class name and "password" appearing twice
        assert results[0][0] == "src/models/user.py"
        assert results[1][0] == "src/auth/login.py"

    def test_java_code(self):
        """Test with Java-style code."""
        java_content = (
            "public class AuthService {\n    public boolean authenticate("
            "String username, String password) {\n        return "
            "userRepository.checkCredentials(username, password);\n    }\n}"
        )
        docs = [
            ("src/main/java/com/example/AuthService.java", java_content),
        ]
        index = BM25Index()
        index.build(docs)

        results = index.query("authentication username password", k=1)
        assert len(results) == 1
        assert "AuthService" in results[0][0] or "authenticate" in tokenize_code(results[0][0])

    def test_javascript_code(self):
        """Test with JavaScript-style code."""
        js_content = (
            "async function authenticateUser(username, password) {\n"
            "    const user = await db.findUser(username);\n"
            "    return bcrypt.compare(password, user.hashedPassword);\n}"
        )
        docs = [
            ("src/auth/login.js", js_content),
        ]
        index = BM25Index()
        index.build(docs)

        results = index.query("user authentication password", k=1)
        assert len(results) == 1
        assert results[0][0] == "src/auth/login.js"
