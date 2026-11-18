default:
    @just --list

set positional-arguments

# Crawl a TopTurnier results page
crawl *args:
    uv run python -m etl.crawler "$@"

# Evaluate stored results for a pair
eval *args:
    uv run python -m etl.auswertung "$@"

# Run dashboard
run:
    env -u VIRTUAL_ENV uv run python -m streamlit run app.py

# Run isolated unit and dashboard tests
test:
    uv run python -m unittest discover -s tests -v

# Format Python files
format:
    uv run --group dev python -m black .

# Check formatting and lint
lint:
    uv run --group dev python -m black --check .
    uv run --group dev python -m ruff check .
    uvx --from uv==0.12.3 uv check --preview-features check-command
