from app.auth import parse, sign
def test_signed_cookie_roundtrip():
    user_id="8c50d55b-5541-438e-a0b6-b4b7c7d3f875"
    assert parse(sign(user_id))==user_id
def test_tampered_cookie_rejected(): assert parse(sign("abc")+"x") is None
