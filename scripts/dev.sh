#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Python tooling
# ---------------------------------------------------------------------------

echo "==> Locking and syncing dependencies"
uv lock && uv sync -U --link-mode=copy

echo "==> Formatting Python code"
uv run ruff format

echo "==> Linting Python code (with autofix)"
uv run ruff check --fix

echo "==> Type checking"
uv run ty check

# ---------------------------------------------------------------------------
# Bash checks (scripts + config)
# ---------------------------------------------------------------------------

echo "==> Checking bash files..."

BASH_DIRS=("./scripts")
EXCLUDE_PATTERN="deploy-*.sh"

# Collect bash files safely
mapfile -t BASH_FILES < <(
	find "${BASH_DIRS[@]}" -type f -name "*.sh" ! -name "$EXCLUDE_PATTERN" 2>/dev/null | sort
)

if [[ ${#BASH_FILES[@]} -eq 0 ]]; then
	echo "==> No bash files found under ${BASH_DIRS[*]} – skipping"
else
	echo "==> Found ${#BASH_FILES[@]} bash file(s) to check"

	# Format with shfmt
	echo "==> Formatting bash files"
	changed=0
	for file in "${BASH_FILES[@]}"; do
		if ! shfmt -d "$file" >/dev/null 2>&1; then
			shfmt -w "$file"
			((changed++)) || true
		fi
	done

	if [[ $changed -eq 0 ]]; then
		echo "All bash files already formatted correctly!"
	else
		echo "Formatted $changed bash file(s)"
	fi

	# Lint with shellcheck
	echo "==> Linting bash files with shellcheck"
	if shellcheck "${BASH_FILES[@]}"; then
		echo "All bash files passed shellcheck!"
	else
		echo "shellcheck found issues" >&2
		exit 1
	fi
fi
