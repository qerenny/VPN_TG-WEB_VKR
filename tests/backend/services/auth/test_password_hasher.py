from backend.services.auth.password_hasher import PasswordHasher


def test_hash_password_roundtrip():
    hasher = PasswordHasher()

    password_hash = hasher.hash_password("correct horse battery staple")

    assert password_hash.startswith("scrypt$")
    assert hasher.verify_password("correct horse battery staple", password_hash) is True
    assert hasher.verify_password("wrong password", password_hash) is False


def test_verify_password_returns_false_for_invalid_hash():
    hasher = PasswordHasher()

    assert hasher.verify_password("secret", None) is False
    assert hasher.verify_password("secret", "invalid") is False
