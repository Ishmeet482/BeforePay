MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_LENGTH = 100_000
MAX_PDF_PAGES = 100
# Bound the entire request before multipart parsing, including multipart overhead.
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 64 * 1024
