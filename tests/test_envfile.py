from app import envfile


def test_parse():
    text = '''
# comment
A=1
B="hello world. x=y"
C='single'
EMPTY=
  SPACED = value
not a pair
'''
    assert envfile.parse(text) == {
        "A": "1", "B": "hello world. x=y", "C": "single", "EMPTY": "", "SPACED": "value",
    }


def test_load_does_not_override(tmp_path, monkeypatch):
    f = tmp_path / "x.env"
    f.write_text("FOO=from_file\nBAR=from_file\n")
    monkeypatch.setenv("FOO", "from_env")
    monkeypatch.delenv("BAR", raising=False)
    envfile.load(f)
    import os
    assert os.environ["FOO"] == "from_env"
    assert os.environ["BAR"] == "from_file"


def test_load_missing_file_is_ok(tmp_path):
    envfile.load(tmp_path / "nope.env")
