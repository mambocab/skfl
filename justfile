test *args:
    uv run --with pytest --with click --with tomli-w pytest tests/test_skfl.py {{args}}
