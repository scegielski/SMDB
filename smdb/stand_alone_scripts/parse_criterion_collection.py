import re
input_file = "criterion_collection.txt"
output_file = "criterion_collection_all.txt"
separate_file = "criterion_collection_films.txt"

def write_line(file_handle, line_number, tokens, max_linen_number_width, max_widths):
    # Pad line number with spaces to match the maximum width
    file_handle.write(str(line_number).rjust(max_line_number_width) + '\t')
    # Start writing tokens from the second token onwards
    for i, token in enumerate(tokens[1:], start=1):
        # Pad each token with spaces to match the maximum width of the column
        file_handle.write(
            (token[:min(50, max_widths[i])] + '\t').ljust(max_widths[i] + 1))  # Add 1 for extra space between columns
    file_handle.write('\n')  # Add a newline character at the end of each output line


try:
    # Determine max_widths for tokens and max_line_number_width
    max_widths = []
    max_line_number_width = 0
    with open(input_file, 'r', encoding='utf-8') as input_f:
        line_number = 1
        for line in input_f:
            tokens = re.split(r'\t+', line.strip())  # Use '\t+' as the delimiter to split on one or more tabs

            # Calculate max_line_number_width
            max_line_number_width = max(max_line_number_width, len(str(line_number)))

            # Calculate max_widths for tokens
            if len(max_widths) < len(tokens):
                max_widths.extend([0] * (len(tokens) - len(max_widths)))
            for i, token in enumerate(tokens):
                max_widths[i] = min(max(max_widths[i], len(token)), 50)  # Limit max width to 50 characters

            line_number += 1  # Increment line number counter

    with open(input_file, 'r', encoding='utf-8') as input_f, \
            open(output_file, 'w', encoding='utf-8') as output_f, \
            open(separate_file, 'w', encoding='utf-8') as separate_f:
        line_number = 1  # Reset line number counter
        for line in input_f:
            tokens = re.split(r'\t+', line.strip())  # Use '\t+' as the delimiter to split on one or more tabs

            write_line(output_f, line_number, tokens, max_line_number_width, max_widths)

            if len(tokens) > 4:
                write_line(separate_f, line_number, tokens, max_line_number_width, max_widths)

            line_number += 1  # Increment line number counter

    print(
        f"Tokens extracted from '{input_file}' (omitting the first token of each line) and written to '{output_file}'.")
    print(f"Lines with less than 4 tokens written to '{separate_file}'.")
except FileNotFoundError:
    print(f"File '{input_file}' not found.")
except Exception as e:
    print(f"An error occurred: {e}")