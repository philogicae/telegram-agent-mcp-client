#!/bin/bash
# Export variables from a docker-style .env file into the environment.
# Parsed instead of `source`d: values may contain shell metacharacters (e.g. `|`).

load_env() {
	local file=${1:-.env}
	[ -f "$file" ] || return 0

	local line key value
	while IFS= read -r line || [ -n "$line" ]; do
		line="${line%$'\r'}"
		# Skip blank lines and comments
		[[ $line =~ ^[[:space:]]*(#.*)?$ ]] && continue
		[[ $line == *=* ]] || continue

		key="${line%%=*}"
		value="${line#*=}"
		key="${key//[[:space:]]/}"
		# Trim surrounding whitespace from value
		value="${value#"${value%%[![:space:]]*}"}"
		value="${value%"${value##*[![:space:]]}"}"
		# Strip one pair of matching surrounding quotes (dotenv semantics)
		if [[ ${#value} -ge 2 ]]; then
			case $value in
			\"*\") value="${value:1:${#value}-2}" ;;
			\'*\') value="${value:1:${#value}-2}" ;;
			esac
		fi

		[ -n "$key" ] && export "$key=$value"
	done <"$file"
}
