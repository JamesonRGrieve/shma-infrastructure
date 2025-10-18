#!/bin/bash
output_file="dump.txt"
script_name=$(basename "$0")
>"$output_file"
echo "Starting export..."
# Process command line arguments
mode=""
paths=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
    -n)
        if [ "$mode" = "include" ]; then
            echo "Error: Cannot use both -n and -y options"
            exit 1
        fi
        mode="exclude"
        shift
        ;;
    -y)
        if [ "$mode" = "exclude" ]; then
            echo "Error: Cannot use both -n and -y options"
            exit 1
        fi
        mode="include"
        shift
        ;;
    *)
        # Remove trailing slash if present
        arg=${1%/}
        paths+=("$arg")

        if [ -d "$arg" ]; then
            echo "Will ${mode} directory: $arg"
        elif [ -f "$arg" ]; then
            echo "Will ${mode} file: $arg"
        else
            echo "Warning: $arg does not exist, but will be ${mode}d if found"
        fi
        shift
        ;;
    esac
done

# Default to processing all files if no mode is specified
if [ -z "$mode" ]; then
    mode="all"
    echo "No filter specified. Processing all files."
fi

# Combine tracked and untracked but not ignored files
(
    git ls-files
    git ls-files --others --exclude-standard
) | sort -u | while read -r file; do
    # Skip the output file itself
    if [ "$file" = "$output_file" ]; then
        continue
    fi

    # Skip the script itself
    if [ "$(basename "$file")" = "$script_name" ]; then
        echo "Skipping self: $file"
        continue
    fi

    # Apply path filters based on mode
    if [ "$mode" = "exclude" ]; then
        skip=false
        for path in "${paths[@]}"; do
            if [ "$file" = "$path" ] || [[ "$file" == "$path"/* ]]; then
                echo "Skipping excluded path: $file"
                skip=true
                break
            fi
        done
        [ "$skip" = true ] && continue
    elif [ "$mode" = "include" ]; then
        include=false
        for path in "${paths[@]}"; do
            if [ "$file" = "$path" ] || [[ "$file" == "$path"/* ]]; then
                include=true
                break
            fi
        done

        if [ "$include" = false ]; then
            echo "Skipping non-included path: $file"
            continue
        fi
    fi

    # Skip binary files
    if file -b --mime-encoding "$file" | grep -q binary; then
        echo "Skipping binary file: $file"
        continue
    fi

    # Show progress in console
    echo "Processing: $file"

    # Write the header with the file path
    echo "# ./$file" >>"$output_file"
    echo "" >>"$output_file"
    echo "\`\`\`" >>"$output_file"

    # Write the file contents with a timeout
    timeout 5s cat "$file" >>"$output_file" || {
        echo "Warning: Timeout processing $file - skipping"
        # Remove the partial entry
        sed -i '$ d' "$output_file" # Remove the last line
        continue
    }

    # Add newline before closing code block
    echo "" >>"$output_file"
    # Close the code block and add a blank line
    echo "\`\`\`" >>"$output_file"
    echo "" >>"$output_file"
done

echo "Export complete. Check $output_file for the results."
